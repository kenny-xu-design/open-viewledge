from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.cache import CacheStore
from src.config import AppConfig
from src.domain.models import AnalysisResult, SourceRecord, TranscriptResult, TranscriptSegment
from src.pipeline.orchestrator import PipelineOrchestrator


class FakeOnlineSource:
    def __init__(
        self,
        root: Path,
        *,
        has_subtitle: bool,
        platform: str = "youtube",
        source_id: str = "video-id",
    ) -> None:
        self.root = root
        self.has_subtitle = has_subtitle
        self.platform = platform
        self.source_id = source_id
        self.source_url = ""
        self.collect_metadata = Mock(side_effect=self._collect_metadata)
        self.acquire_subtitles = Mock(side_effect=self._acquire_subtitles)
        self.acquire_media = Mock(side_effect=self._acquire_media)

    def resolve(self, input_value: str) -> SourceRecord:
        self.source_url = input_value
        return SourceRecord(
            source_type="online_video",
            platform=self.platform,
            source_url=input_value,
            canonical_url=input_value,
            source_id=self.source_id,
            title="online-video",
        )

    def _collect_metadata(self) -> SourceRecord:
        return SourceRecord(
            source_type="online_video",
            platform=self.platform,
            source_url=self.source_url,
            canonical_url=self.source_url,
            source_id=self.source_id,
            title="Demo",
        )

    def _acquire_subtitles(self, work_dir: Path, language: str) -> Path | None:
        if not self.has_subtitle:
            return None
        path = work_dir / "subtitle.vtt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("WEBVTT\n", encoding="utf-8")
        return path

    def _acquire_media(
        self,
        work_dir: Path,
        sample_seconds: int | None = None,
        *,
        audio_only: bool = False,
    ) -> Path:
        path = work_dir / "source.webm"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return path


class FakeWhisperProvider:
    name = "local-faster-whisper"
    model_name = "faster-whisper-small"
    transcribe_calls = 0

    def __init__(self, _config: object | None = None, **_kwargs) -> None:
        self.telemetry = SimpleNamespace(
            profile="balanced",
            device="cpu",
            compute_type="int8",
            batch_size=1,
            beam_size=1,
            low_confidence_segments=0,
            local_retries=0,
            audio_duration_seconds=3.0,
            transcription_seconds=0.1,
            rtf=0.03,
        )

    def is_available(self) -> bool:
        return True

    def transcribe(self, _audio_path: Path, _context: object) -> TranscriptResult:
        type(self).transcribe_calls += 1
        return TranscriptResult(
            provider="faster-whisper",
            model=self.model_name,
            device="cpu",
            language="zh",
            duration_seconds=3,
            segments=[
                TranscriptSegment(
                    index=0,
                    start=0,
                    end=3,
                    text="ASR transcript",
                    language="zh",
                    source="asr",
                )
            ],
        )


class PipelineCacheTests(unittest.TestCase):
    def test_platform_subtitle_skips_media_download_and_whisper(self) -> None:
        cases = (
            ("youtube", "video-id", "https://www.youtube.com/watch?v=video-id"),
            ("bilibili", "BV123", "https://www.bilibili.com/video/BV123?p=2"),
        )
        for platform, source_id, url in cases:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = FakeOnlineSource(
                    root,
                    has_subtitle=True,
                    platform=platform,
                    source_id=source_id,
                )
                config = AppConfig(output_dir=str(root / "output"), keep_temp_files=True)
                cache = CacheStore(root / "cache")
                with (
                    patch("src.pipeline.orchestrator.YtdlpSource", return_value=source),
                    patch(
                        "src.pipeline.orchestrator.parse_subtitle_file",
                        return_value=[
                            TranscriptSegment(
                                index=0,
                                start=0,
                                end=3,
                                text="Platform subtitle",
                                language="zh",
                                source="subtitle",
                            )
                        ],
                    ),
                    patch("src.pipeline.orchestrator.LocalWhisperProvider") as whisper,
                    patch(
                        "src.pipeline.orchestrator.inspect_knowledge_package",
                        return_value=SimpleNamespace(valid=True, issues=[]),
                    ),
                ):
                    whisper.name = "local-faster-whisper"
                    whisper.model_name = "faster-whisper-small"
                    package = PipelineOrchestrator(
                        config,
                        no_analysis=True,
                        cache_store=cache,
                    ).run(url, is_url=True)

                source.acquire_subtitles.assert_called_once()
                source.acquire_media.assert_not_called()
                whisper.assert_not_called()
                self.assertIsNotNone(package.manifest.first_readable_result_duration_ms)
                self.assertEqual(package.manifest.stage_status["extract_frames"], "skipped")
                self.assertFalse(package.manifest.analysis_requested)
                self.assertTrue(package.manifest.transcript_only)
                self.assertEqual(package.manifest.analysis_status, "skipped")
                self.assertEqual(
                    package.manifest.analysis_skip_reason,
                    "user_requested_transcript_only",
                )

    def test_transcript_only_result_runs_missing_analysis_without_retranscribing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_source = FakeOnlineSource(root, has_subtitle=True)
            second_source = FakeOnlineSource(root, has_subtitle=True)
            config = AppConfig(output_dir=str(root / "output"), keep_temp_files=True)
            cache = CacheStore(root / "cache")
            provider = SimpleNamespace(
                name="deepseek",
                model_name="test-model",
                is_available=lambda: True,
            )
            analysis_service = Mock()
            analysis_service.analyze.return_value = AnalysisResult(
                status="success",
                summary="补跑完成",
                analysis_profile="summary",
                provider="deepseek",
                model="test-model",
            )
            subtitle_segments = [
                TranscriptSegment(
                    index=0,
                    start=0,
                    end=3,
                    text="可复用的字幕",
                    language="zh",
                    source="subtitle",
                )
            ]
            with (
                patch(
                    "src.pipeline.orchestrator.YtdlpSource",
                    side_effect=[first_source, second_source],
                ),
                patch(
                    "src.pipeline.orchestrator.parse_subtitle_file",
                    return_value=subtitle_segments,
                ) as parse_subtitle,
                patch("src.pipeline.orchestrator.LocalWhisperProvider") as whisper,
                patch("src.pipeline.orchestrator.DeepSeekProvider", return_value=provider),
                patch(
                    "src.pipeline.orchestrator.AnalysisService",
                    return_value=analysis_service,
                ),
                patch(
                    "src.pipeline.orchestrator.inspect_knowledge_package",
                    return_value=SimpleNamespace(valid=True, issues=[]),
                ),
            ):
                first = PipelineOrchestrator(
                    config,
                    no_analysis=True,
                    cache_store=cache,
                ).run("https://www.youtube.com/watch?v=video-id", is_url=True)
                second = PipelineOrchestrator(
                    config,
                    no_analysis=False,
                    cache_store=cache,
                ).run("https://www.youtube.com/watch?v=video-id", is_url=True)

            self.assertEqual(first.manifest.analysis_status, "skipped")
            self.assertEqual(second.manifest.analysis_status, "completed")
            self.assertEqual(second.analysis.summary, "补跑完成")
            self.assertTrue(second.manifest.stage_metrics["acquire_transcript"].cache_hit)
            second_source.acquire_subtitles.assert_not_called()
            second_source.acquire_media.assert_not_called()
            whisper.assert_not_called()
            parse_subtitle.assert_called_once()
            analysis_service.analyze.assert_called_once()

    def test_repeated_fast_task_skips_subtitle_media_asr_and_text_analysis(self) -> None:
        FakeWhisperProvider.transcribe_calls = 0
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_source = FakeOnlineSource(root, has_subtitle=False)
            second_source = FakeOnlineSource(root, has_subtitle=False)
            config = AppConfig(output_dir=str(root / "output"), keep_temp_files=True)
            cache = CacheStore(root / "cache")
            provider = SimpleNamespace(
                name="deepseek",
                model_name="test-model",
                is_available=lambda: True,
            )
            analysis_service = Mock()
            analysis_service.analyze.return_value = AnalysisResult(
                status="success",
                summary="Cached summary",
                analysis_profile="summary",
                provider="deepseek",
                model="test-model",
            )

            def fake_extract_audio(_media: Path, output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"wav")
                return output

            common_patches = (
                patch(
                    "src.pipeline.orchestrator.YtdlpSource",
                    side_effect=[first_source, second_source],
                ),
                patch(
                    "src.transcription_router.LocalFasterWhisperProvider",
                    FakeWhisperProvider,
                ),
                patch(
                    "src.pipeline.orchestrator.DeepSeekProvider",
                    return_value=provider,
                ),
                patch(
                    "src.pipeline.orchestrator.AnalysisService",
                    return_value=analysis_service,
                ),
                patch(
                    "src.pipeline.orchestrator.extract_audio",
                    side_effect=fake_extract_audio,
                ),
                patch(
                    "src.pipeline.orchestrator.inspect_knowledge_package",
                    return_value=SimpleNamespace(valid=True, issues=[]),
                ),
            )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5]:
                first = PipelineOrchestrator(
                    config,
                    processing_profile="fast",
                    asr_route="local_cpu",
                    cache_store=cache,
                ).run("https://www.youtube.com/watch?v=video-id", is_url=True)
                second = PipelineOrchestrator(
                    config,
                    processing_profile="fast",
                    asr_route="local_cpu",
                    cache_store=cache,
                ).run("https://www.youtube.com/watch?v=video-id", is_url=True)

        first_source.acquire_subtitles.assert_called_once()
        first_source.acquire_media.assert_called_once()
        self.assertTrue(first_source.acquire_media.call_args.kwargs["audio_only"])
        second_source.collect_metadata.assert_not_called()
        second_source.acquire_subtitles.assert_not_called()
        second_source.acquire_media.assert_not_called()
        self.assertEqual(FakeWhisperProvider.transcribe_calls, 1)
        analysis_service.analyze.assert_called_once()
        self.assertFalse(first.manifest.stage_metrics["acquire_transcript"].cache_hit)
        self.assertTrue(second.manifest.stage_metrics["collect_metadata"].cache_hit)
        self.assertTrue(second.manifest.stage_metrics["acquire_transcript"].cache_hit)
        self.assertTrue(second.manifest.stage_metrics["run_analysis"].cache_hit)
        self.assertEqual(second.manifest.stage_status["extract_frames"], "skipped")
        self.assertIsNotNone(second.manifest.full_completion_duration_ms)


if __name__ == "__main__":
    unittest.main()
