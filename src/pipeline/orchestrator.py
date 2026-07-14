from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from ..analysis import AnalysisService
from ..audio import extract_audio
from ..config import AppConfig
from ..domain.models import AnalysisResult, ChapterSummary, KnowledgePackage, ProcessingManifest, utc_now
from ..exporters import export_knowledge_package
from ..providers.asr import LocalWhisperProvider
from ..providers.llm import LegacyLLMProvider
from ..sources import LocalMediaSource, YtdlpSource
from ..timeline import build_timeline, extract_frames
from ..transcripts import group_segments, parse_subtitle_file, read_jsonl, write_grouped_markdown, write_jsonl, write_legacy_transcript
from ..transcripts.normalizer import normalize_segments
from ..utils import UserFacingError, ensure_dir, load_json, sanitize_filename, save_json, write_text
from .context import PipelineContext
from .stages import STAGES


class PipelineOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        *,
        backend: str | None = None,
        privacy_mode: bool | None = None,
        analysis_profile: str = "summary",
        no_analysis: bool = False,
        generate_frames: bool | None = None,
        sample_seconds: int | None = None,
        export_legacy_note: bool = False,
        log_callback=None,
    ) -> None:
        self.config = config
        self.backend = backend or config.summary_backend
        self.privacy_mode = config.privacy_mode if privacy_mode is None else privacy_mode
        self.analysis_profile = analysis_profile
        self.no_analysis = no_analysis
        self.generate_frames = config.generate_frames if generate_frames is None else generate_frames
        self.sample_seconds = sample_seconds
        self.export_legacy_note = export_legacy_note
        self.log_callback = log_callback

    def run(self, input_value: str, is_url: bool) -> KnowledgePackage:
        task_id = uuid.uuid4().hex[:12]
        source_adapter = YtdlpSource() if is_url else LocalMediaSource()
        context = PipelineContext(
            config=self.config,
            input_value=input_value,
            output_dir=Path(self.config.output_dir),
            privacy_mode=self.privacy_mode,
            analysis_profile=self.analysis_profile,
            no_analysis=self.no_analysis,
            generate_frames=self.generate_frames,
            sample_seconds=self.sample_seconds,
            log_callback=self.log_callback,
            manifest=ProcessingManifest(task_id=task_id, privacy_mode=self.privacy_mode, sample_seconds=self.sample_seconds),
        )
        try:
            self._stage(context, "resolve_source", lambda: setattr(context, "source", source_adapter.resolve(input_value)))
            self._stage(context, "collect_metadata", lambda: setattr(context, "source", source_adapter.collect_metadata()))
            assert context.source and context.manifest
            context.output_dir = ensure_dir(Path(self.config.output_dir) / _package_name(context.source.title, context.source.source_id))
            ensure_dir(context.output_dir / "audio")
            ensure_dir(context.output_dir / "frames")
            context.manifest.source = context.source
            self._save_manifest(context)

            def acquire() -> None:
                cached_raw = context.output_dir / "transcript.raw.jsonl"
                if cached_raw.exists():
                    cached_segments = read_jsonl(cached_raw)
                    cached_manifest = load_json(context.output_dir / "manifest.json")
                    cache_sample = cached_manifest.get("sample_seconds")
                    if (
                        cached_segments
                        and _cache_matches_language(cached_segments, self.config.language)
                        and cache_sample == self.sample_seconds
                    ):
                        context.segments = cached_segments
                        context.log(f"复用已有逐句字幕：{cached_raw}")
                        return
                    if cached_segments:
                        context.log(f"已有字幕语言与请求不一致，将重新获取：{self.config.language}")
                context.subtitle_path = source_adapter.acquire_subtitles(context.output_dir / "_temp", self.config.language)
                if context.subtitle_path:
                    context.log("已获取平台字幕，跳过 ASR。")
                    context.segments = parse_subtitle_file(context.subtitle_path, self.config.language)
                    if self.sample_seconds:
                        context.segments = [item for item in context.segments if item.start < self.sample_seconds]
                    return
                context.log("未获取到平台字幕，进入 FFmpeg + 本地 faster-whisper。")
                context.media_path = source_adapter.acquire_media(context.output_dir / "_temp", self.sample_seconds)
                wav_path = extract_audio(
                    context.media_path,
                    context.output_dir / "audio" / "audio_16k.wav",
                    sample_seconds=self.sample_seconds,
                )
                provider = LocalWhisperProvider()
                if not provider.is_available():
                    raise UserFacingError("本地 faster-whisper 模型不可用。")
                context.segments = provider.transcribe(wav_path, context)
                context.manifest.asr_provider = provider.name
                context.manifest.asr_model = provider.model_name

            self._stage(context, "acquire_transcript", acquire)

            def normalize() -> None:
                context.segments = normalize_segments(context.segments)
                if self.sample_seconds:
                    context.segments = _limit_segments(context.segments, self.sample_seconds)
                write_jsonl(context.output_dir / "transcript.raw.jsonl", context.segments)
                context.legacy_transcript_path = write_legacy_transcript(
                    context.output_dir / "transcript.md", context.segments, context.source.canonical_url or context.source.source_url
                )

            self._stage(context, "normalize_transcript", normalize)

            def group() -> None:
                context.groups = group_segments(
                    context.segments,
                    context.source.chapters,
                    self.config.transcript_group_seconds,
                    self.config.transcript_group_max_segments,
                )
                write_grouped_markdown(context.output_dir / "transcript.grouped.md", context.groups, context.source.source_url)

            self._stage(context, "group_transcript", group)
            self._stage(context, "build_timeline", lambda: setattr(context, "timeline", build_timeline(context.groups, context.source)))

            def frames() -> None:
                if not self.generate_frames or context.source.source_type != "local_video":
                    return
                frame_source = Path(context.source.local_path)
                context.timeline, errors = extract_frames(frame_source, context.timeline, context.output_dir / "frames")
                context.manifest.errors.extend(errors)

            self._stage(context, "extract_frames", frames, soft_fail=True)

            def analyze() -> None:
                if self.no_analysis:
                    context.analysis = AnalysisResult(analysis_profile=self.analysis_profile)
                    return
                model = self.config.ollama_model if self.backend == "ollama" else self.config.openai_model
                provider = LegacyLLMProvider(self.backend, model)
                context.manifest.llm_provider = provider.name
                if not provider.is_available():
                    raise UserFacingError(f"LLM Provider 不可用：{provider.name} / {provider.model_name}")
                try:
                    context.analysis = AnalysisService(provider).analyze(context.groups, self.analysis_profile, context)
                finally:
                    context.manifest.llm_model = provider.model_name
                _write_legacy_analysis_files(context)

            self._stage(context, "run_analysis", analyze, soft_fail=True)
            if context.analysis is None:
                context.analysis = AnalysisResult(analysis_profile=self.analysis_profile)

            def export() -> None:
                assert context.source and context.manifest
                context.manifest.completed_at = utc_now()
                context.manifest.status = "completed_with_warnings" if context.manifest.errors else "completed"
                package = KnowledgePackage(
                    source=context.source,
                    transcript_segments=context.segments,
                    transcript_groups=context.groups,
                    timeline=context.timeline,
                    analysis=context.analysis,
                    manifest=context.manifest,
                    output_dir=context.output_dir,
                )
                files = export_knowledge_package(package, self.export_legacy_note)
                context.manifest.output_files = [path.name for path in files] + ["transcript.raw.jsonl", "transcript.grouped.md", "transcript.md"]
                self._save_manifest(context)

            self._stage(context, "export_knowledge_package", export)
            if not self.config.keep_temp_files:
                shutil.rmtree(context.output_dir / "_temp", ignore_errors=True)
            return KnowledgePackage(
                source=context.source, transcript_segments=context.segments, transcript_groups=context.groups,
                timeline=context.timeline, analysis=context.analysis, manifest=context.manifest, output_dir=context.output_dir,
            )
        except UserFacingError:
            if context.manifest:
                context.manifest.status = "failed"
                self._save_manifest(context)
            raise
        except Exception as exc:
            if context.manifest:
                context.manifest.status = "failed"
                context.manifest.errors.append(str(exc))
                self._save_manifest(context)
            raise UserFacingError(f"处理管线失败：{exc}") from exc

    def _stage(self, context: PipelineContext, name: str, action, soft_fail: bool = False) -> None:
        assert context.manifest
        context.manifest.current_stage = name
        context.manifest.stage_status[name] = "running"
        context.log(f"阶段：{name}")
        self._save_manifest(context)
        try:
            action()
            context.manifest.stage_status[name] = "completed"
        except Exception as exc:
            message = f"阶段 {name} 失败：{exc}"
            context.manifest.errors.append(message)
            context.manifest.stage_status[name] = "warning" if soft_fail else "failed"
            self._save_manifest(context)
            if not soft_fail:
                raise UserFacingError(message) from exc
            context.log(message)
        self._save_manifest(context)

    @staticmethod
    def _save_manifest(context: PipelineContext) -> None:
        if context.manifest and context.output_dir.exists() and context.output_dir.is_dir():
            save_json(context.output_dir / "manifest.json", context.manifest.model_dump(mode="json"))


def _package_name(title: str, source_id: str) -> str:
    return f"{sanitize_filename(title, 'media')}_{sanitize_filename(source_id, 'unknown')}"


def _cache_matches_language(segments, language: str) -> bool:
    requested = (language or "").strip().lower()
    if not requested:
        return True
    return all((item.language or "").strip().lower() == requested for item in segments)


def _limit_segments(segments, sample_seconds: int):
    return [
        item.model_copy(update={"index": index, "end": min(item.end, float(sample_seconds))})
        for index, item in enumerate(item for item in segments if item.start < sample_seconds)
    ]


def _write_legacy_analysis_files(context: PipelineContext) -> None:
    analysis = context.analysis
    if not analysis:
        return
    if analysis.summary:
        write_text(context.output_dir / "summary.md", "# 摘要\n\n" + analysis.summary.strip() + "\n")
    if analysis.highlights:
        write_text(context.output_dir / "highlight_notes.md", "# 亮点\n\n" + "\n".join(f"- **{item.title}**：{item.explanation}" for item in analysis.highlights) + "\n")
    if analysis.chapters:
        write_text(context.output_dir / "chapter_summary.md", "# 章节总结\n\n" + "\n\n".join(f"## {item.title}\n\n{item.summary}" for item in analysis.chapters) + "\n")
    mode_files = {"tutorial": "tutorial_report.md", "viral": "viral_analysis.md", "close-reading": "close_reading.md"}
    if context.analysis_profile in mode_files and analysis.raw_response:
        write_text(context.output_dir / mode_files[context.analysis_profile], analysis.raw_response.strip() + "\n")
