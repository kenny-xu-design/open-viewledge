from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import AppConfig
from ..domain.models import (
    AnalysisResult,
    KnowledgePackage,
    ProcessingManifest,
    ProviderAttempt,
    SourceRecord,
    TimelineEntry,
    utc_now,
)
from ..exporters import export_knowledge_package
from ..pipeline.context import PipelineContext
from ..providers.llm.deepseek import DeepSeekProvider
from ..transcripts import group_segments, read_jsonl
from ..utils import UserFacingError, load_json, write_text
from .service import AnalysisService
from .profiles import resolve_analysis_profile


def reanalyze_knowledge_package(
    package_dir: Path,
    config: AppConfig,
    *,
    provider: Any | None = None,
) -> KnowledgePackage:
    """Re-run only AI analysis for an existing knowledge package."""
    root = package_dir.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)

    metadata = load_json(root / "metadata.json")
    manifest = ProcessingManifest.model_validate(load_json(root / "manifest.json"))
    source = manifest.source or SourceRecord.model_validate(metadata)
    segments = read_jsonl(root / "transcript.raw.jsonl")
    if not segments:
        raise UserFacingError("知识包没有可用于重新分析的逐句字幕。")

    groups = group_segments(
        segments,
        source.chapters,
        target_seconds=config.transcript_group_seconds,
        max_segments=config.transcript_group_max_segments,
    )
    if not groups:
        raise UserFacingError("知识包字幕无法生成有效分组，不能重新分析。")

    previous_analysis = _load_optional_json(root / "analysis.json")
    profile = resolve_analysis_profile(
        None,
        str(previous_analysis.get("analysis_profile") or ""),
        title=source.title,
        transcript="\n".join(item.text for item in groups),
    )
    timeline_payload = _load_optional_json(root / "timeline.json")
    timeline = [
        TimelineEntry.model_validate(item)
        for item in timeline_payload.get("items", [])
        if isinstance(item, dict)
    ]
    context = PipelineContext(
        config=config,
        input_value=source.canonical_url or source.source_url or source.local_path,
        output_dir=root,
        analysis_profile=profile,
    )
    context.source = source
    context.segments = segments
    context.groups = groups
    context.timeline = timeline
    context.manifest = manifest
    if previous_analysis:
        try:
            context.analysis = AnalysisResult.model_validate(previous_analysis)
        except ValueError:
            context.analysis = None

    manifest.source = source
    source.analysis_profile = profile
    manifest.analysis_profile = profile
    manifest.current_stage = "run_analysis"
    manifest.status = "processing"
    manifest.analysis_status = "pending"
    manifest.analysis_error = ""
    manifest.stage_status["run_analysis"] = "running"
    manifest.errors = [message for message in manifest.errors if "run_analysis" not in message]
    _persist_package(context)
    # Keep the previous result on disk while the request is running, but make
    # sure a new failure cannot accidentally reuse its stale error details.
    context.analysis = None

    selected_provider = provider or DeepSeekProvider(
        base_url=config.deepseek_base_url,
        model_name=config.deepseek_model,
    )
    provider_name = str(getattr(selected_provider, "name", "deepseek"))
    model_name = str(getattr(selected_provider, "model_name", config.deepseek_model))
    manifest.llm_provider = provider_name
    manifest.llm_model = model_name
    attempt = ProviderAttempt(provider=provider_name, model=model_name, stage="run_analysis")

    try:
        if not selected_provider.is_available():
            raise UserFacingError("未检测到 DEEPSEEK_API_KEY，请在项目 .env 中配置后重试。")
        context.analysis = AnalysisService(selected_provider).analyze(groups, profile, context)
        manifest.llm_model = context.analysis.model or model_name
        manifest.analysis_status = "completed"
        manifest.analysis_error = ""
        manifest.stage_status["run_analysis"] = "completed"
        manifest.status = "completed_with_warnings" if manifest.errors else "completed"
        manifest.completed_at = utc_now()
        attempt.model = manifest.llm_model
        attempt.success = True
    except Exception as exc:
        if context.analysis is None:
            context.analysis = AnalysisResult(
                status="failed",
                error=str(exc),
                analysis_profile=profile,
                provider=provider_name,
                model=model_name,
            )
        attempt.error_type = "configuration" if not selected_provider.is_available() else type(exc).__name__
        attempt.error_message = str(exc)
        manifest.analysis_status = "failed"
        manifest.analysis_error = context.analysis.error or str(exc)
        manifest.stage_status["run_analysis"] = "failed"
        manifest.status = "completed_with_warnings"
        manifest.errors.append(f"阶段 run_analysis 失败：{str(exc)}")
        raise UserFacingError(str(exc)) from exc
    finally:
        attempt.finished_at = utc_now()
        manifest.provider_attempts.append(attempt)
        _persist_package(context)

    return _build_package(context)


def _build_package(context: PipelineContext) -> KnowledgePackage:
    assert context.source and context.manifest
    return KnowledgePackage(
        source=context.source,
        transcript_segments=context.segments,
        transcript_groups=context.groups,
        timeline=context.timeline,
        analysis=context.analysis,
        manifest=context.manifest,
        output_dir=context.output_dir,
    )


def _load_optional_json(path: Path) -> dict[str, Any]:
    try:
        return load_json(path)
    except (OSError, ValueError):
        return {}


def _persist_package(context: PipelineContext) -> None:
    package = _build_package(context)
    export_knowledge_package(
        package,
        export_legacy_note=(context.output_dir / "export_note.md").is_file(),
    )
    analysis = context.analysis
    if not analysis:
        return
    if analysis.summary:
        write_text(context.output_dir / "summary.md", "# 摘要\n\n" + analysis.summary.strip() + "\n")
    if analysis.highlights:
        write_text(
            context.output_dir / "highlight_notes.md",
            "# 亮点\n\n" + "\n".join(f"- **{item.title}**：{item.explanation}" for item in analysis.highlights) + "\n",
        )
    if analysis.chapters:
        write_text(
            context.output_dir / "chapter_summary.md",
            "# 章节总结\n\n" + "\n\n".join(f"## {item.title}\n\n{item.summary}" for item in analysis.chapters) + "\n",
        )
