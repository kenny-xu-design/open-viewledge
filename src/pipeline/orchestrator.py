from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from ..analysis import AnalysisService
from ..analysis.profiles import resolve_analysis_profile
from ..audio import extract_audio
from ..config import AppConfig
from ..domain.models import AnalysisResult, ChapterSummary, KnowledgePackage, ProcessingManifest, ProviderAttempt, utc_now
from ..exporters import export_knowledge_package
from ..providers.asr import LocalWhisperProvider
from ..providers.llm import DeepSeekProvider
from ..knowledge_validation import inspect_knowledge_package
from ..sources import LocalMediaSource, YtdlpSource
from ..timeline import build_timeline, extract_frames
from ..transcripts import group_segments, parse_subtitle_file, read_jsonl, write_grouped_markdown, write_jsonl, write_legacy_transcript
from ..transcripts.normalizer import normalize_segments
from ..utils import UserFacingError, ensure_dir, load_json, sanitize_filename, save_json, write_text
from ..cli_contract import sanitize_message
from .context import PipelineContext
from .stages import STAGES


class PipelineOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        *,
        backend: str | None = None,
        analysis_profile: str = "summary",
        no_analysis: bool = False,
        generate_frames: bool | None = None,
        sample_seconds: int | None = None,
        export_legacy_note: bool = False,
        log_callback=None,
        event_callback=None,
        task_id: str | None = None,
    ) -> None:
        self.config = config
        self.backend = backend or config.summary_backend
        self.analysis_profile = analysis_profile
        self.no_analysis = no_analysis
        self.generate_frames = config.generate_frames if generate_frames is None else generate_frames
        self.sample_seconds = sample_seconds
        self.export_legacy_note = export_legacy_note
        self.log_callback = log_callback
        self.event_callback = event_callback
        self.task_id = task_id

    def run(self, input_value: str, is_url: bool) -> KnowledgePackage:
        task_id = self.task_id or uuid.uuid4().hex[:12]
        source_adapter = YtdlpSource() if is_url else LocalMediaSource()
        context = PipelineContext(
            config=self.config,
            input_value=input_value,
            output_dir=Path(self.config.output_dir),
            analysis_profile=self.analysis_profile,
            no_analysis=self.no_analysis,
            generate_frames=self.generate_frames,
            sample_seconds=self.sample_seconds,
            log_callback=self.log_callback,
            manifest=ProcessingManifest(task_id=task_id, privacy_mode=False, sample_seconds=self.sample_seconds),
        )
        try:
            self._stage(context, "resolve_source", lambda: setattr(context, "source", source_adapter.resolve(input_value)))
            self._stage(context, "collect_metadata", lambda: setattr(context, "source", source_adapter.collect_metadata()))
            assert context.source and context.manifest
            context.output_dir = ensure_dir(Path(self.config.output_dir) / _package_name(context.source.title, context.source.source_id))
            context.previous_manifest = load_json(context.output_dir / "manifest.json")
            ensure_dir(context.output_dir / "audio")
            ensure_dir(context.output_dir / "frames")
            context.manifest.source = context.source
            self._save_manifest(context)

            def acquire() -> None:
                cached_raw = context.output_dir / "transcript.raw.jsonl"
                if cached_raw.exists():
                    cached_segments = read_jsonl(cached_raw)
                    cached_manifest = context.previous_manifest
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
                    ffmpeg_path=self.config.ffmpeg_path,
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
                if not any(item.text.strip() for item in context.segments):
                    raise UserFacingError("字幕或转写结果为空，不能生成知识包。")
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
                if not any(item.text.strip() for item in context.groups):
                    raise UserFacingError("字幕分组为空，不能生成知识包。")
                write_grouped_markdown(context.output_dir / "transcript.grouped.md", context.groups, context.source.source_url)

            self._stage(context, "group_transcript", group)
            resolved_profile = resolve_analysis_profile(
                self.analysis_profile,
                title=context.source.title,
                transcript="\n".join(item.text for item in context.groups),
            )
            context.analysis_profile = resolved_profile
            context.source.analysis_profile = resolved_profile
            context.manifest.analysis_profile = resolved_profile
            self._stage(context, "build_timeline", lambda: setattr(context, "timeline", build_timeline(context.groups, context.source)))

            def frames() -> None:
                if not self.generate_frames or context.source.source_type != "local_video":
                    return
                frame_source = Path(context.source.local_path)
                context.timeline, errors = extract_frames(
                    frame_source,
                    context.timeline,
                    context.output_dir / "frames",
                    ffmpeg_path=self.config.ffmpeg_path,
                )
                context.manifest.errors.extend(errors)

            self._stage(context, "extract_frames", frames, soft_fail=True)

            def analyze() -> None:
                if self.no_analysis:
                    context.analysis = AnalysisResult(status="skipped", analysis_profile=context.analysis_profile)
                    context.manifest.analysis_status = "skipped"
                    context.manifest.analysis_error = ""
                    return
                if self.backend != "deepseek":
                    raise UserFacingError(
                        f"后端 {self.backend} 已停用。当前仅支持 deepseek，请改用 --backend deepseek。"
                    )
                provider = DeepSeekProvider(
                    base_url=self.config.deepseek_base_url,
                    model_name=self.config.deepseek_model,
                )
                context.log(f"AI Provider：{provider.name} / {provider.model_name}")
                context.manifest.llm_provider = provider.name
                context.manifest.llm_model = provider.model_name
                attempt = ProviderAttempt(provider=provider.name, model=provider.model_name, stage="run_analysis")
                if not provider.is_available():
                    context.analysis = AnalysisResult(
                        status="failed",
                        error="未配置 DEEPSEEK_API_KEY。",
                        analysis_profile=context.analysis_profile,
                        provider=provider.name,
                        model=provider.model_name,
                    )
                    attempt.finished_at = utc_now()
                    attempt.error_type = "configuration"
                    attempt.error_message = context.analysis.error
                    context.manifest.analysis_status = "failed"
                    context.manifest.analysis_error = context.analysis.error
                    context.manifest.provider_attempts.append(attempt)
                    raise UserFacingError("未检测到 DEEPSEEK_API_KEY，请在项目 .env 中配置后重试。")
                try:
                    context.analysis = AnalysisService(provider).analyze(context.groups, context.analysis_profile, context)
                    context.manifest.llm_model = context.analysis.model or provider.model_name
                    context.manifest.analysis_status = "completed"
                    context.manifest.analysis_error = ""
                    attempt.model = context.manifest.llm_model
                    attempt.success = True
                except Exception as exc:
                    if context.analysis is None:
                        context.analysis = AnalysisResult(
                            status="failed",
                            error=str(exc),
                            analysis_profile=context.analysis_profile,
                            provider=provider.name,
                            model=provider.model_name,
                        )
                    attempt.error_type = type(exc).__name__
                    attempt.error_message = str(exc)
                    context.manifest.analysis_status = "failed"
                    context.manifest.analysis_error = context.analysis.error or str(exc)
                    raise
                finally:
                    attempt.finished_at = utc_now()
                    context.manifest.provider_attempts.append(attempt)
                _write_legacy_analysis_files(context)

            self._stage(context, "run_analysis", analyze, soft_fail=True)
            if context.analysis is None:
                context.analysis = AnalysisResult(
                    status="failed",
                    error="分析阶段未生成结果。",
                    analysis_profile=context.analysis_profile,
                )
                context.manifest.analysis_status = "failed"
                context.manifest.analysis_error = context.analysis.error

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
                for name in context.manifest.output_files:
                    self._emit("artifact_created", task_id=context.manifest.task_id, stage="export_knowledge_package", artifact=str(context.output_dir / name))
                inspection = inspect_knowledge_package(context.output_dir)
                if not inspection.valid:
                    messages = [issue.message for issue in inspection.issues if issue.severity == "error"]
                    raise UserFacingError("知识包完整性检查失败：" + "；".join(messages[:5]))

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
                context.manifest.errors.append(sanitize_message(str(exc)))
                self._save_manifest(context)
            raise UserFacingError(f"处理管线失败：{exc}") from exc

    def _stage(self, context: PipelineContext, name: str, action, soft_fail: bool = False) -> None:
        assert context.manifest
        stage_index = STAGES.index(name) if name in STAGES else 0
        total_stages = len(STAGES)
        context.manifest.current_stage = name
        context.manifest.stage_status[name] = "running"
        context.log(f"阶段：{name}")
        self._emit(
            "stage_started",
            task_id=context.manifest.task_id,
            stage=name,
            progress=stage_index / total_stages,
        )
        self._save_manifest(context)
        try:
            action()
            if name == "run_analysis" and context.manifest.analysis_status == "skipped":
                context.manifest.stage_status[name] = "skipped"
            else:
                context.manifest.stage_status[name] = "completed"
        except Exception as exc:
            message = sanitize_message(f"阶段 {name} 失败：{exc}")
            context.manifest.errors.append(message)
            if name == "run_analysis":
                context.manifest.stage_status[name] = "failed"
            else:
                context.manifest.stage_status[name] = "warning" if soft_fail else "failed"
            self._save_manifest(context)
            if not soft_fail:
                raise UserFacingError(message) from exc
            context.log(message)
            self._emit("warning", task_id=context.manifest.task_id, stage=name, message=message)
        self._save_manifest(context)
        self._emit(
            "stage_completed",
            task_id=context.manifest.task_id,
            stage=name,
            status=context.manifest.stage_status[name],
            progress=(stage_index + 1) / total_stages,
        )
        self._emit(
            "progress",
            task_id=context.manifest.task_id,
            stage=name,
            progress=(stage_index + 1) / total_stages,
        )

    def _emit(self, event: str, **payload) -> None:
        if self.event_callback:
            self.event_callback(event, **payload)

    @staticmethod
    def _save_manifest(context: PipelineContext) -> None:
        configured_root = Path(context.config.output_dir).resolve()
        output_dir = context.output_dir.resolve()
        if output_dir == configured_root:
            return
        if context.manifest and output_dir.exists() and output_dir.is_dir():
            save_json(output_dir / "manifest.json", context.manifest.model_dump(mode="json"))


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
