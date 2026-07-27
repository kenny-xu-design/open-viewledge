from __future__ import annotations

import hashlib
import shutil
import time
import uuid
from pathlib import Path

from ..analysis import AnalysisService, KeyframeAnalysisService
from ..analysis.profiles import resolve_analysis_profile
from ..asr_runtime import asr_cache_dimensions
from ..audio import extract_audio
from ..cache import CacheStore, build_cache_key, source_cache_dimensions, transcript_content_hash
from ..comments import CommentInsightService, CommentRepository, CommentSyncService
from ..config import AppConfig
from ..domain.models import AnalysisResult, ChapterSummary, KnowledgePackage, NormalizedComment, ProcessingManifest, ProviderAttempt, SourceRecord, StageMetric, TranscriptSegment, utc_now
from ..exporters import export_knowledge_package
from ..exporters.analysis_markdown import render_profile_analysis
from ..transcription_router import PlatformSubtitleProvider, TranscriptionRouter, normalize_asr_route
from ..providers.asr import LocalWhisperProvider  # compatibility for existing mocks
from ..providers.llm import DeepSeekProvider, GeminiProvider
from ..processing_profiles import ProcessingProfile
from ..knowledge_validation import inspect_knowledge_package
from ..sources import LocalMediaSource, YtdlpSource
from ..timeline import build_timeline, extract_frames
from ..transcripts import group_segments, parse_subtitle_file, read_jsonl, write_grouped_markdown, write_jsonl, write_legacy_transcript
from ..transcripts.normalizer import normalize_segments
from ..utils import UserFacingError, ensure_dir, is_timeout_error, load_json, sanitize_filename, save_json, write_text
from ..visual import generate_tutorial_step_snapshots
from ..cli_contract import sanitize_message
from .context import PipelineContext
from .stages import STAGES


def _apply_transcript_result(context: PipelineContext, result) -> None:
    assert context.manifest
    context.manifest.transcript_status = "completed"
    context.manifest.transcript_provider = result.provider
    context.manifest.transcript_model = result.model
    context.manifest.transcript_fallback_used = result.fallback_used
    context.manifest.asr_provider = result.provider
    context.manifest.asr_model = result.model
    context.manifest.asr_device = result.device
    context.manifest.asr_audio_duration_seconds = result.duration_seconds


class PipelineOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        *,
        backend: str | None = None,
        analysis_profile: str = "summary",
        processing_profile: ProcessingProfile = "complete",
        comments_enabled: bool = False,
        no_analysis: bool = False,
        asr_route: str = "cloud",
        asr_fallback_enabled: bool = True,
        generate_frames: bool | None = None,
        sample_seconds: int | None = None,
        export_legacy_note: bool = False,
        log_callback=None,
        event_callback=None,
        task_id: str | None = None,
        cache_store: CacheStore | None = None,
    ) -> None:
        self.config = config
        self.backend = backend or config.summary_backend
        self.analysis_profile = analysis_profile
        self.processing_profile = processing_profile
        self.comments_enabled = comments_enabled
        self.no_analysis = no_analysis
        self.asr_route = normalize_asr_route(asr_route)
        self.asr_fallback_enabled = bool(asr_fallback_enabled)
        self.generate_frames = config.generate_frames if generate_frames is None else generate_frames
        self.sample_seconds = sample_seconds
        self.export_legacy_note = export_legacy_note
        self.log_callback = log_callback
        self.event_callback = event_callback
        self.task_id = task_id
        self.cache_store = cache_store or CacheStore()

    def run(self, input_value: str, is_url: bool) -> KnowledgePackage:
        run_started = time.perf_counter()
        task_id = self.task_id or uuid.uuid4().hex[:12]
        source_adapter = YtdlpSource() if is_url else LocalMediaSource()
        context = PipelineContext(
            config=self.config,
            input_value=input_value,
            output_dir=Path(self.config.output_dir),
            analysis_profile=self.analysis_profile,
            processing_profile=self.processing_profile,
            no_analysis=self.no_analysis,
            generate_frames=self.generate_frames,
            sample_seconds=self.sample_seconds,
            log_callback=self.log_callback,
            manifest=ProcessingManifest(
                task_id=task_id,
                privacy_mode=False,
                sample_seconds=self.sample_seconds,
                processing_profile=self.processing_profile,
                analysis_requested=not self.no_analysis,
                analysis_status="skipped" if self.no_analysis else "pending",
                analysis_skip_reason=(
                    "user_requested_transcript_only" if self.no_analysis else ""
                ),
                transcript_only=self.no_analysis,
                transcript_route_requested=self.asr_route,
            ),
        )
        try:
            self._stage(context, "resolve_source", lambda: setattr(context, "source", source_adapter.resolve(input_value)))

            def collect_metadata() -> None:
                assert context.source and context.manifest
                metadata_key = build_cache_key(
                    "metadata",
                    input=input_value,
                    platform=context.source.platform,
                    source_id=context.source.source_id,
                )
                context.manifest.cache_keys["metadata"] = metadata_key
                cached = self._cache_get(context, "metadata", metadata_key)
                if isinstance(cached, dict):
                    try:
                        context.source = SourceRecord.model_validate(cached)
                    except ValueError:
                        context.log("元数据缓存无效，将重新读取来源信息。")
                    else:
                        context.mark_cache_hit("collect_metadata")
                        context.log("命中元数据缓存。")
                        return
                context.source = source_adapter.collect_metadata()
                self._cache_put(
                    context,
                    "metadata",
                    metadata_key,
                    context.source.model_dump(mode="json"),
                )

            self._stage(context, "collect_metadata", collect_metadata)
            assert context.source and context.manifest
            context.output_dir = ensure_dir(Path(self.config.output_dir) / _package_name(context.source.title, context.source.source_id))
            context.previous_manifest = load_json(context.output_dir / "manifest.json")
            ensure_dir(context.output_dir / "audio")
            ensure_dir(context.output_dir / "frames")
            ensure_dir(context.output_dir / "assets" / "highlights")
            ensure_dir(context.output_dir / "assets" / "tutorial")
            context.manifest.source = context.source
            self._save_manifest(context)
            source_dimensions = source_cache_dimensions(context.source, input_value)
            subtitle_key = build_cache_key(
                "subtitle",
                source=source_dimensions,
                language=self.config.language,
            )
            audio_key = build_cache_key(
                "audio",
                source=source_dimensions,
                sample_start=0,
                sample_end=self.sample_seconds,
                audio_only=self.processing_profile == "fast",
            )
            transcript_key = build_cache_key(
                "transcript",
                source=source_dimensions,
                language=self.config.language,
                sample_start=0,
                sample_end=self.sample_seconds,
                asr_route=self.asr_route,
                asr_fallback_enabled=self.asr_fallback_enabled,
                cloud_asr_provider=self.config.cloud_asr_provider,
                cloud_asr_model=self.config.cloud_asr_model,
                vad_filter=True,
                processing_profile=self.processing_profile,
                normalizer_version="1",
                **asr_cache_dimensions(self.config),
            )
            context.manifest.cache_keys.update(
                {
                    "subtitle": subtitle_key,
                    "audio": audio_key,
                    "transcript": transcript_key,
                }
            )

            def acquire() -> None:
                cached_transcript = _segments_from_cache(
                    self._cache_get(context, "transcript", transcript_key)
                )
                if cached_transcript and _cache_matches_language(cached_transcript, self.config.language):
                    context.segments = cached_transcript
                    context.manifest.transcript_status = "completed"
                    context.manifest.transcript_provider = str(
                        context.previous_manifest.get("transcript_provider") or "cache"
                    )
                    context.mark_cache_hit("acquire_transcript")
                    context.log("命中逐句字幕缓存，跳过字幕下载、媒体下载和 ASR。")
                    return

                cached_subtitle = _segments_from_cache(
                    self._cache_get(context, "subtitle", subtitle_key)
                )
                if cached_subtitle and _cache_matches_language(cached_subtitle, self.config.language):
                    context.segments = cached_subtitle
                    context.manifest.transcript_status = "completed"
                    context.manifest.transcript_provider = "platform"
                    context.mark_cache_hit("acquire_transcript")
                    context.log("命中平台字幕缓存，跳过字幕下载、媒体下载和 ASR。")
                    return

                cached_raw = context.output_dir / "transcript.raw.jsonl"
                if cached_raw.exists():
                    cached_segments = read_jsonl(cached_raw)
                    cached_manifest = context.previous_manifest
                    cache_sample = cached_manifest.get("sample_seconds")
                    previous_key = (cached_manifest.get("cache_keys") or {}).get("transcript")
                    if (
                        cached_segments
                        and _cache_matches_language(cached_segments, self.config.language)
                        and cache_sample == self.sample_seconds
                        and (not previous_key or previous_key == transcript_key)
                    ):
                        context.segments = cached_segments
                        context.manifest.transcript_status = "completed"
                        context.manifest.transcript_provider = str(
                            cached_manifest.get("transcript_provider") or "cache"
                        )
                        context.mark_cache_hit("acquire_transcript")
                        context.log(f"复用已有逐句字幕：{cached_raw}")
                        return
                    if cached_segments:
                        context.log(f"已有字幕语言与请求不一致，将重新获取：{self.config.language}")
                context.subtitle_path = source_adapter.acquire_subtitles(context.output_dir / "_temp", self.config.language)
                if context.subtitle_path:
                    context.log("已获取平台字幕，跳过 ASR。")
                    context.log("已使用平台字幕")
                    result = PlatformSubtitleProvider().build_result(
                        parse_subtitle_file(context.subtitle_path, self.config.language),
                        self.config.language,
                        context.source.duration or 0,
                    )
                    context.segments = result.segments
                    _apply_transcript_result(context, result)
                    self._cache_put(
                        context,
                        "subtitle",
                        subtitle_key,
                        [item.model_dump(mode="json") for item in context.segments],
                    )
                    return
                context.log("未获取到平台字幕，进入 FFmpeg + 本地 faster-whisper。")
                context.log("未检测到平台字幕")
                context.log(
                    "用户选择："
                    + {
                        "cloud": "云端快速转写",
                        "local_gpu": "本地 GPU",
                        "local_cpu": "本地 CPU",
                    }[self.asr_route]
                )
                context.log("正在提取音频")
                context.media_path = source_adapter.acquire_media(
                    context.output_dir / "_temp",
                    self.sample_seconds,
                    audio_only=self.processing_profile == "fast",
                )
                wav_path = extract_audio(
                    context.media_path,
                    context.output_dir / "audio" / "audio_16k.wav",
                    sample_seconds=self.sample_seconds,
                    ffmpeg_path=self.config.ffmpeg_path,
                    timeout_seconds=self.config.ffmpeg_timeout_seconds,
                )
                if self.asr_route == "cloud":
                    context.log("云端 ASR：Groq")
                    context.log(f"模型：{self.config.cloud_asr_model}")
                result = TranscriptionRouter(
                    self.config,
                    route=self.asr_route,
                    fallback_enabled=self.asr_fallback_enabled,
                ).transcribe(wav_path, context)
                context.segments = result.segments
                _apply_transcript_result(context, result)
                context.log("开始运行 AI 分析")

            self._stage(context, "acquire_transcript", acquire)

            def normalize() -> None:
                context.segments = normalize_segments(context.segments)
                if self.sample_seconds:
                    context.segments = _limit_segments(context.segments, self.sample_seconds)
                if not any(item.text.strip() for item in context.segments):
                    raise UserFacingError("字幕或转写结果为空，不能生成知识包。")
                write_jsonl(context.output_dir / "transcript.raw.jsonl", context.segments)
                self._cache_put(
                    context,
                    "transcript",
                    transcript_key,
                    [item.model_dump(mode="json") for item in context.segments],
                )
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
            self._mark_first_readable(context, run_started)
            resolved_profile = resolve_analysis_profile(
                self.analysis_profile,
                title=context.source.title,
                transcript="\n".join(item.text for item in context.groups),
            )
            context.analysis_profile = resolved_profile
            context.source.analysis_profile = resolved_profile
            context.manifest.analysis_profile = resolved_profile
            self._stage(context, "build_timeline", lambda: setattr(context, "timeline", build_timeline(context.groups, context.source)))
            frames_key = build_cache_key(
                "frames",
                source=source_dimensions,
                timestamps=[item.representative_time for item in context.timeline],
                strategy="timeline_representative_time",
                ffmpeg_path=self.config.ffmpeg_path,
            )
            context.manifest.cache_keys["frames"] = frames_key

            def frames() -> None:
                if (
                    self.processing_profile == "fast"
                    or not self.generate_frames
                    or context.source.source_type != "local_video"
                ):
                    context.mark_stage_skipped("extract_frames")
                    return
                frame_source = Path(context.source.local_path)
                context.timeline, errors = extract_frames(
                    frame_source,
                    context.timeline,
                    context.output_dir / "frames",
                    ffmpeg_path=self.config.ffmpeg_path,
                )
                context.manifest.errors.extend(errors)

            def analyze() -> None:
                if self.no_analysis:
                    context.analysis = AnalysisResult(status="skipped", analysis_profile=context.analysis_profile)
                    context.manifest.analysis_requested = False
                    context.manifest.analysis_status = "skipped"
                    context.manifest.analysis_skip_reason = "user_requested_transcript_only"
                    context.manifest.analysis_provider = ""
                    context.manifest.analysis_model = ""
                    context.manifest.transcript_only = True
                    context.manifest.analysis_error = ""
                    return
                context.manifest.analysis_requested = True
                context.manifest.analysis_skip_reason = ""
                context.manifest.transcript_only = False
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
                context.manifest.analysis_provider = provider.name
                context.manifest.analysis_model = provider.model_name
                analysis_key = build_cache_key(
                    "text_analysis",
                    source=source_dimensions,
                    transcript_hash=transcript_content_hash(context.segments),
                    analysis_profile=context.analysis_profile,
                    processing_profile=context.processing_profile,
                    provider=provider.name,
                    model=provider.model_name,
                    prompt_version=context.manifest.prompt_version,
                    transcript_group_seconds=self.config.transcript_group_seconds,
                    transcript_group_max_segments=self.config.transcript_group_max_segments,
                )
                context.manifest.cache_keys["text_analysis"] = analysis_key
                cached_analysis = _analysis_from_cache(
                    self._cache_get(context, "text_analysis", analysis_key)
                )
                if cached_analysis and cached_analysis.status == "success":
                    context.analysis = cached_analysis
                    context.manifest.llm_provider = cached_analysis.provider or provider.name
                    context.manifest.llm_model = cached_analysis.model or provider.model_name
                    context.manifest.analysis_status = "completed"
                    context.manifest.analysis_provider = context.manifest.llm_provider
                    context.manifest.analysis_model = context.manifest.llm_model
                    context.manifest.analysis_error = ""
                    context.mark_cache_hit("run_analysis")
                    context.log("命中文本分析缓存，跳过 LLM 请求。")
                    _write_legacy_analysis_files(context)
                    save_json(
                        context.output_dir / "analysis.json",
                        context.analysis.model_dump(mode="json"),
                    )
                    return
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
                    context.manifest.analysis_provider = provider.name
                    context.manifest.analysis_model = context.manifest.llm_model
                    context.manifest.analysis_error = ""
                    attempt.model = context.manifest.llm_model
                    attempt.success = True
                    self._cache_put(
                        context,
                        "text_analysis",
                        analysis_key,
                        context.analysis.model_dump(mode="json"),
                    )
                except Exception as exc:
                    timed_out = is_timeout_error(exc)
                    if context.analysis is None:
                        context.analysis = AnalysisResult(
                            status="timeout" if timed_out else "failed",
                            error=str(exc),
                            analysis_profile=context.analysis_profile,
                            provider=provider.name,
                            model=provider.model_name,
                        )
                    attempt.error_type = type(exc).__name__
                    attempt.error_message = str(exc)
                    context.manifest.analysis_status = "timeout" if timed_out else "failed"
                    context.manifest.analysis_error = context.analysis.error or str(exc)
                    raise
                finally:
                    attempt.finished_at = utc_now()
                    context.manifest.provider_attempts.append(attempt)
                _write_legacy_analysis_files(context)
                save_json(
                    context.output_dir / "analysis.json",
                    context.analysis.model_dump(mode="json"),
                )

            self._stage(context, "run_analysis", analyze, soft_fail=True)
            if context.analysis is None:
                context.analysis = AnalysisResult(
                    status="failed",
                    error="分析阶段未生成结果。",
                    analysis_profile=context.analysis_profile,
                )
                context.manifest.analysis_status = "failed"
                context.manifest.analysis_error = context.analysis.error
            save_json(
                context.output_dir / "analysis.json",
                context.analysis.model_dump(mode="json"),
            )

            self._stage(context, "extract_frames", frames, soft_fail=True)

            def visual_analysis() -> None:
                if self.processing_profile == "fast" or not self.generate_frames:
                    context.mark_stage_skipped("visual_analysis")
                    return
                frame_paths = [
                    context.output_dir / item.frame_path
                    for item in context.timeline
                    if item.frame_path and (context.output_dir / item.frame_path).is_file()
                ][:12]
                if not frame_paths:
                    context.mark_stage_skipped("visual_analysis")
                    return
                provider = GeminiProvider(
                    base_url=self.config.gemini_base_url,
                    model_name=self.config.gemini_model,
                )
                if not provider.is_available():
                    context.mark_stage_skipped("visual_analysis")
                    context.log("Gemini 未配置，跳过可选视觉分析；文本结果不受影响。")
                    return
                visual_key = build_cache_key(
                    "visual_analysis",
                    source=source_dimensions,
                    frame_hashes=[_file_sha256(path) for path in frame_paths],
                    provider=provider.name,
                    model=provider.model_name,
                    prompt_version=context.manifest.prompt_version,
                )
                context.manifest.cache_keys["visual_analysis"] = visual_key
                cached_visual = self._cache_get(context, "visual_analysis", visual_key)
                if (
                    isinstance(cached_visual, dict)
                    and cached_visual.get("status") == "success"
                    and str(cached_visual.get("content") or "").strip()
                ):
                    save_json(context.output_dir / "visual_insights.json", cached_visual)
                    write_text(
                        context.output_dir / "visual_insights.md",
                        "# 视觉观察\n\n" + str(cached_visual["content"]).strip() + "\n",
                    )
                    context.mark_cache_hit("visual_analysis")
                    context.log("命中视觉分析缓存，跳过 Gemini 图片请求。")
                    return
                result = KeyframeAnalysisService(provider).analyze(
                    frame_paths,
                    (
                        "按时间顺序分析这些视频关键帧。只描述画面中可见的信息，"
                        "指出界面、图表、演示动作和重要视觉变化；不要猜测不可见内容。"
                    ),
                    system_prompt="输出简洁的中文视觉观察，并在不确定时明确说明。",
                    max_tokens=1_500,
                )
                payload = {
                    "status": result.status,
                    "frame_count": result.frame_count,
                    "provider": result.response.provider if result.response else "",
                    "model": result.response.model if result.response else "",
                    "content": result.response.content if result.response else "",
                    "message": result.message,
                }
                save_json(context.output_dir / "visual_insights.json", payload)
                self._cache_put(context, "visual_analysis", visual_key, payload)
                if result.response:
                    write_text(
                        context.output_dir / "visual_insights.md",
                        "# 视觉观察\n\n" + result.response.content.strip() + "\n",
                    )

            self._stage(context, "visual_analysis", visual_analysis, soft_fail=True)

            def highlight_snapshot() -> None:
                if (
                    self.processing_profile == "fast"
                    or not self.generate_frames
                    or context.source.source_type != "local_video"
                    or not context.analysis
                    or context.analysis.analysis_profile != "tutorial"
                    or not context.analysis.steps
                ):
                    context.mark_stage_skipped("highlight_snapshot")
                    return
                result = generate_tutorial_step_snapshots(
                    Path(context.source.local_path),
                    context.analysis,
                    context.timeline,
                    context.output_dir,
                    ffmpeg_path=self.config.ffmpeg_path,
                )
                context.analysis = result.analysis
                save_json(
                    context.output_dir / "analysis.json",
                    context.analysis.model_dump(mode="json"),
                )
                if result.errors:
                    context.manifest.errors.extend(result.errors)
                    raise UserFacingError("；".join(result.errors[:3]))
                context.log(
                    f"教程步骤截图：新截取 {result.generated_count} 张，复用关键帧 {result.reused_count} 张。"
                )

            self._stage(context, "highlight_snapshot", highlight_snapshot, soft_fail=True)

            synced_comments = []

            def comments_fetch() -> None:
                nonlocal synced_comments
                comment_key = build_cache_key(
                    "comments",
                    source=source_dimensions,
                    processing_profile=self.processing_profile,
                    sync_version="1",
                    enabled=self.comments_enabled,
                )
                context.manifest.cache_keys["comments"] = comment_key
                if not self.comments_enabled:
                    context.mark_stage_skipped("comments_fetch")
                    return
                cached_comments = self._cache_get(context, "comments", comment_key)
                if isinstance(cached_comments, list):
                    try:
                        synced_comments = [
                            NormalizedComment.model_validate(item)
                            for item in cached_comments
                            if isinstance(item, dict)
                        ]
                    except ValueError:
                        context.log("评论缓存无效，将重新同步。")
                    else:
                        if synced_comments:
                            CommentRepository(context.output_dir).save(synced_comments)
                            context.mark_cache_hit("comments_fetch")
                            context.log(f"命中评论缓存：{len(synced_comments)} 条。")
                            return
                result = CommentSyncService().sync(
                    context.source,
                    processing_profile=self.processing_profile,
                    enabled=self.comments_enabled,
                    existing=CommentRepository(context.output_dir).load(),
                )
                if result.status != "success":
                    context.mark_stage_skipped("comments_fetch")
                    context.log(result.message or "未同步到评论。")
                    return
                synced_comments = result.comments
                CommentRepository(context.output_dir).save(synced_comments)
                self._cache_put(
                    context,
                    "comments",
                    comment_key,
                    [item.model_dump(mode="json") for item in synced_comments],
                )
                context.log(f"评论同步：{len(synced_comments)} 条，模式 {result.mode}/{result.sort}。")

            self._stage(context, "comments_fetch", comments_fetch, soft_fail=True)

            def comments_analysis() -> None:
                if not synced_comments:
                    context.mark_stage_skipped("comments_analysis")
                    return
                provider = DeepSeekProvider(
                    base_url=self.config.deepseek_base_url,
                    model_name=self.config.deepseek_model,
                )
                insight = CommentInsightService(provider).analyze(synced_comments)
                CommentInsightService.save(context.output_dir, insight)
                if insight.status == "failed":
                    raise UserFacingError(insight.error or "评论洞察生成失败。")
                context.log(f"评论洞察：{insight.provider}/{insight.model}。")

            self._stage(context, "comments_analysis", comments_analysis, soft_fail=True)

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
                optional_files = [
                    name
                    for name in (
                        "visual_insights.json",
                        "visual_insights.md",
                        "comments.json",
                        "comments.md",
                        "comment_insights.json",
                        "comment_insights.md",
                    )
                    if (context.output_dir / name).is_file()
                ]
                highlight_files = [
                    path.relative_to(context.output_dir).as_posix()
                    for path in sorted((context.output_dir / "assets" / "highlights").glob("*.webp"))
                ]
                tutorial_files = [
                    path.relative_to(context.output_dir).as_posix()
                    for path in sorted((context.output_dir / "assets" / "tutorial").glob("*.webp"))
                ]
                context.manifest.output_files = [path.name for path in files] + [
                    "transcript.raw.jsonl",
                    "transcript.grouped.md",
                    "transcript.md",
                    *optional_files,
                    *highlight_files,
                    *tutorial_files,
                ]
                self._save_manifest(context)
                for name in context.manifest.output_files:
                    self._emit("artifact_created", task_id=context.manifest.task_id, stage="export_knowledge_package", artifact=str(context.output_dir / name))
                inspection = inspect_knowledge_package(context.output_dir)
                if not inspection.valid:
                    messages = [issue.message for issue in inspection.issues if issue.severity == "error"]
                    raise UserFacingError("知识包完整性检查失败：" + "；".join(messages[:5]))

            self._stage(context, "export_knowledge_package", export)
            context.manifest.full_completion_duration_ms = max(
                0,
                round((time.perf_counter() - run_started) * 1000),
            )
            self._save_manifest(context)
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
        previous_metric = context.manifest.stage_metrics.get(name)
        metric = StageMetric(attempt=(previous_metric.attempt + 1) if previous_metric else 1)
        context.manifest.stage_metrics[name] = metric
        started = time.perf_counter()
        context.manifest.current_stage = name
        context.manifest.stage_status[name] = "running"
        context.log(f"阶段：{name}")
        self._emit(
            "stage_started",
            task_id=context.manifest.task_id,
            stage=name,
            progress=stage_index / total_stages,
            analysis_profile=context.analysis_profile,
            processing_profile=context.processing_profile,
            attempt=metric.attempt,
        )
        self._save_manifest(context)
        try:
            action()
            metric.cache_hit = name in context.cache_hits
            if name in context.skipped_stages or (
                name == "run_analysis" and context.manifest.analysis_status == "skipped"
            ):
                context.manifest.stage_status[name] = "skipped"
            else:
                context.manifest.stage_status[name] = "completed"
        except Exception as exc:
            message = sanitize_message(f"阶段 {name} 失败：{exc}")
            context.manifest.errors.append(message)
            metric.error_code = type(exc).__name__
            metric.error_message = message
            if name == "run_analysis":
                context.manifest.stage_status[name] = (
                    "timeout"
                    if context.manifest.analysis_status == "timeout"
                    else "failed"
                )
            elif name == "acquire_transcript":
                context.manifest.transcript_status = "failed"
                context.manifest.stage_status[name] = "failed"
            else:
                context.manifest.stage_status[name] = "warning" if soft_fail else "failed"
            self._finish_stage_metric(metric, started)
            self._save_manifest(context)
            if not soft_fail:
                raise UserFacingError(message) from exc
            context.log(message)
            self._emit("warning", task_id=context.manifest.task_id, stage=name, message=message)
        else:
            self._finish_stage_metric(metric, started)
        self._save_manifest(context)
        self._emit(
            "stage_completed",
            task_id=context.manifest.task_id,
            stage=name,
            status=context.manifest.stage_status[name],
            progress=(stage_index + 1) / total_stages,
            analysis_profile=context.analysis_profile,
            processing_profile=context.processing_profile,
            duration_ms=metric.duration_ms,
            attempt=metric.attempt,
            cache_hit=metric.cache_hit,
        )
        self._emit(
            "progress",
            task_id=context.manifest.task_id,
            stage=name,
            progress=(stage_index + 1) / total_stages,
            processing_profile=context.processing_profile,
        )

    def _emit(self, event: str, **payload) -> None:
        if self.event_callback:
            self.event_callback(event, **payload)

    def _cache_get(self, context: PipelineContext, artifact_type: str, cache_key: str):
        try:
            return self.cache_store.get(artifact_type, cache_key)
        except (OSError, ValueError) as exc:
            context.log(sanitize_message(f"读取 {artifact_type} 缓存失败，将继续执行：{exc}"))
            return None

    def _cache_put(self, context: PipelineContext, artifact_type: str, cache_key: str, data) -> None:
        try:
            self.cache_store.put(artifact_type, cache_key, data)
        except (OSError, TypeError, ValueError) as exc:
            context.log(sanitize_message(f"写入 {artifact_type} 缓存失败，不影响本次任务：{exc}"))

    def _mark_first_readable(self, context: PipelineContext, started: float) -> None:
        assert context.manifest
        if context.manifest.first_readable_result_at:
            return
        context.manifest.first_readable_result_at = utc_now()
        context.manifest.first_readable_result_duration_ms = max(
            0,
            round((time.perf_counter() - started) * 1000),
        )
        self._save_manifest(context)
        self._emit(
            "first_readable_result",
            task_id=context.manifest.task_id,
            stage="group_transcript",
            duration_ms=context.manifest.first_readable_result_duration_ms,
            processing_profile=context.processing_profile,
        )

    @staticmethod
    def _finish_stage_metric(metric: StageMetric, started: float) -> None:
        metric.completed_at = utc_now()
        metric.duration_ms = max(0, round((time.perf_counter() - started) * 1000))

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


def _segments_from_cache(value) -> list[TranscriptSegment]:
    if not isinstance(value, list):
        return []
    try:
        return [TranscriptSegment.model_validate(item) for item in value if isinstance(item, dict)]
    except ValueError:
        return []


def _analysis_from_cache(value) -> AnalysisResult | None:
    if not isinstance(value, dict):
        return None
    try:
        return AnalysisResult.model_validate(value)
    except ValueError:
        return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _limit_segments(segments, sample_seconds: int):
    return [
        item.model_copy(update={"index": index, "end": min(item.end, float(sample_seconds))})
        for index, item in enumerate(item for item in segments if item.start < sample_seconds)
    ]


def _write_legacy_analysis_files(context: PipelineContext) -> None:
    analysis = context.analysis
    if not analysis:
        return
    if analysis.content or analysis.summary:
        write_text(context.output_dir / "summary.md", "# 分析报告\n\n" + "\n".join(render_profile_analysis(analysis, heading_level=2)).strip() + "\n")
    if analysis.highlights:
        write_text(context.output_dir / "highlight_notes.md", "# 亮点\n\n" + "\n".join(f"- **{item.title}**：{item.explanation}" for item in analysis.highlights) + "\n")
    if analysis.chapters:
        write_text(context.output_dir / "chapter_summary.md", "# 章节总结\n\n" + "\n\n".join(f"## {item.title}\n\n{item.summary}" for item in analysis.chapters) + "\n")
    mode_files = {"tutorial": "tutorial_report.md", "viral": "viral_analysis.md", "close-reading": "close_reading.md"}
    if context.analysis_profile in mode_files and analysis.raw_response:
        write_text(context.output_dir / mode_files[context.analysis_profile], analysis.raw_response.strip() + "\n")
