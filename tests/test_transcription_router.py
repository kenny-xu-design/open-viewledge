from __future__ import annotations

import os
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.config import AppConfig
from src.domain.models import TranscriptResult, TranscriptSegment
from src.transcription_router import (
    GroqASRProvider,
    PlatformSubtitleProvider,
    TranscriptionRouter,
    classify_groq_error,
    merge_overlapping_segments,
    normalize_asr_route,
    prepare_cloud_audio_chunks,
)
from src.utils import UserFacingError


def result(provider: str, device: str = "cloud") -> TranscriptResult:
    return TranscriptResult(
        provider=provider,
        model="model",
        device=device,
        language="zh",
        duration_seconds=2,
        segments=[
            TranscriptSegment(index=0, start=0, end=2, text="测试", language="zh")
        ],
    )


class Context:
    def __init__(self) -> None:
        self.logs: list[str] = []
        self.config = AppConfig()

    def log(self, message: str) -> None:
        self.logs.append(message)


class FakeLocal:
    calls: list[str] = []
    failures: set[str] = set()

    def __init__(self, config, *, device, fallback):
        self.device = device

    def transcribe(self, audio, context):
        self.calls.append(self.device)
        if self.device in self.failures:
            raise UserFacingError(f"{self.device} unavailable")
        return result("faster-whisper", self.device)


class TranscriptionRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeLocal.calls = []
        FakeLocal.failures = set()
        self.audio = Path(__file__)
        self.context = Context()

    def test_default_route_is_cloud(self) -> None:
        self.assertEqual(normalize_asr_route(None), "cloud")

    def test_platform_result_needs_no_asr(self) -> None:
        item = TranscriptSegment(index=0, start=0, end=1, text="字幕")
        value = PlatformSubtitleProvider().build_result([item], "zh", 1)
        self.assertEqual(value.provider, "platform")
        self.assertEqual(value.segments[0].text, "字幕")

    def test_cloud_success_does_not_load_local(self) -> None:
        cloud = Mock()
        cloud.transcribe.return_value = result("groq")
        value = TranscriptionRouter(
            AppConfig(), cloud_provider=cloud, local_provider_factory=FakeLocal
        ).transcribe(self.audio, self.context)
        self.assertEqual(value.provider, "groq")
        self.assertEqual(FakeLocal.calls, [])

    def test_cloud_failure_falls_back_gpu(self) -> None:
        cloud = Mock()
        cloud.transcribe.side_effect = UserFacingError("timeout")
        value = TranscriptionRouter(
            AppConfig(), cloud_provider=cloud, local_provider_factory=FakeLocal
        ).transcribe(self.audio, self.context)
        self.assertEqual(value.device, "cuda")
        self.assertTrue(value.fallback_used)

    def test_gpu_failure_falls_back_cpu(self) -> None:
        FakeLocal.failures = {"cuda"}
        value = TranscriptionRouter(
            AppConfig(),
            route="local_gpu",
            local_provider_factory=FakeLocal,
        ).transcribe(self.audio, self.context)
        self.assertEqual(FakeLocal.calls, ["cuda", "cpu"])
        self.assertEqual(value.device, "cpu")

    def test_cloud_without_fallback_fails_directly(self) -> None:
        cloud = Mock()
        cloud.transcribe.side_effect = UserFacingError("timeout")
        with self.assertRaises(UserFacingError):
            TranscriptionRouter(
                AppConfig(),
                fallback_enabled=False,
                cloud_provider=cloud,
                local_provider_factory=FakeLocal,
            ).transcribe(self.audio, self.context)
        self.assertEqual(FakeLocal.calls, [])

    def test_local_gpu_never_calls_cloud(self) -> None:
        cloud = Mock()
        TranscriptionRouter(
            AppConfig(),
            route="local_gpu",
            cloud_provider=cloud,
            local_provider_factory=FakeLocal,
        ).transcribe(self.audio, self.context)
        cloud.transcribe.assert_not_called()

    def test_local_cpu_only_uses_cpu(self) -> None:
        cloud = Mock()
        value = TranscriptionRouter(
            AppConfig(),
            route="local_cpu",
            cloud_provider=cloud,
            local_provider_factory=FakeLocal,
        ).transcribe(self.audio, self.context)
        self.assertEqual(value.device, "cpu")
        self.assertEqual(FakeLocal.calls, ["cpu"])
        cloud.transcribe.assert_not_called()

    def test_missing_groq_key_is_explicit(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "src.transcription_router.load_dotenv", return_value=False
        ):
            with self.assertRaisesRegex(UserFacingError, "GROQ_API_KEY"):
                GroqASRProvider(AppConfig()).transcribe(
                    self.audio, language="zh"
                )

    def test_overlap_merge_offsets_and_deduplicates(self) -> None:
        first = [TranscriptSegment(index=0, start=0, end=2, text="重复文字")]
        second = [
            TranscriptSegment(index=0, start=1.8, end=3, text="重复文字"),
            TranscriptSegment(index=1, start=3, end=4, text="新内容"),
        ]
        merged = merge_overlapping_segments(first, second)
        self.assertEqual([item.text for item in merged], ["重复文字", "新内容"])
        self.assertEqual(merged[0].end, 3)
        self.assertEqual(merged[1].index, 1)

    def test_chunk_offsets_preserve_global_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "audio.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\0\0" * 16000 * 10)

            def fake_convert(source, target, config, **kwargs):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"x" * 1000)

            config = AppConfig(
                cloud_asr_file_limit_mb=0.0005,
                cloud_asr_chunk_overlap_seconds=2,
            )
            with patch(
                "src.transcription_router._convert_audio", side_effect=fake_convert
            ):
                chunks = prepare_cloud_audio_chunks(audio, config)
            self.assertGreater(len(chunks), 1)
            self.assertEqual(chunks[0].offset_seconds, 0)
            self.assertGreater(chunks[1].offset_seconds, 0)

    def test_error_classification(self) -> None:
        error = RuntimeError("request timed out")
        self.assertEqual(classify_groq_error(error), ("请求超时", True))


if __name__ == "__main__":
    unittest.main()
