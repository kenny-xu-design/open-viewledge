from __future__ import annotations

import hashlib
import html
import re
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from .analysis import AnalysisService
from .domain.models import (
    AnalysisResult,
    KnowledgePackage,
    ProcessingManifest,
    SourceRecord,
    TranscriptGroup,
    TranscriptSegment,
    TranscriptStatus,
    utc_now,
)
from .exporters import export_knowledge_package
from .knowledge_validation import inspect_knowledge_package
from .package_claim import acquire_package_claim
from .transcripts import write_jsonl
from .utils import UserFacingError, ensure_dir, sanitize_filename, save_json, write_text


PAGE_CHUNK_CHARACTERS = 1_800


def ingest_page_capture(record: object, output_root: Path, *, provider: object | None = None) -> KnowledgePackage:
    """Build a normal knowledge package from an explicit browser page capture.

    The adapter never fetches the URL. It only processes text already captured
    by a user action and stored in the private local Intake record.
    """

    if str(getattr(record, "source_kind", "")) != "page":
        raise ValueError("page ingestion only accepts page Intake records.")
    selected_text = str(getattr(record, "selected_text", "") or "").strip()
    visible_text = str(getattr(record, "visible_text", "") or "").strip()
    captured_text = selected_text or visible_text
    if not captured_text:
        raise UserFacingError("网页捕获正文为空，请重新从浏览器加入知识收件箱。")

    canonical_url = str(getattr(record, "canonical_url", "") or "").strip()
    title = str(getattr(record, "title", "") or "").strip() or _fallback_title(canonical_url)
    knowledge_id = str(getattr(record, "knowledge_id", "") or "").strip()
    request_fingerprint = str(getattr(record, "request_fingerprint", "") or "").strip()
    source_fingerprint = str(getattr(record, "source_fingerprint", "") or "").strip()
    if not (knowledge_id and request_fingerprint and source_fingerprint):
        raise UserFacingError("网页 Intake 缺少稳定身份信息，请重新捕获。")

    task_id = f"page-{uuid.uuid4().hex[:12]}"
    source_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]
    output_root = output_root.expanduser().resolve()
    output_dir = output_root / f"{sanitize_filename(title, 'page')}_{source_id}"
    ensure_dir(output_root)
    claim = acquire_package_claim(
        output_root,
        knowledge_id=knowledge_id,
        request_fingerprint=request_fingerprint,
        task_id=task_id,
        output_dir=output_dir,
    )
    started = time.perf_counter()
    source = SourceRecord(
        source_type="web_page",
        platform="web",
        source_url=canonical_url,
        canonical_url=canonical_url,
        source_id=source_id,
        title=title,
        captured_at=str(getattr(record, "captured_at", "") or utc_now()),
        description=(
            f"由用户通过浏览器明确选择并捕获的页面内容（{_page_platform(canonical_url)}）。"
            if selected_text
            else f"由用户通过浏览器明确捕获的当前页面可见正文（{_page_platform(canonical_url)}）。"
        ),
        analysis_profile=str(getattr(record, "analysis_profile", "summary") or "summary"),
    )
    analysis_allowed = bool(getattr(record, "content_upload_allowed", False))
    manifest = ProcessingManifest(
        task_id=task_id,
        identity_schema_version="1.0",
        knowledge_id=knowledge_id,
        source_fingerprint=source_fingerprint,
        request_fingerprint=request_fingerprint,
        source=source,
        status="running",
        current_stage="capture_page_content",
        privacy_mode=not analysis_allowed,
        content_kind="web_page_capture",
        capture_scope=str(getattr(record, "capture_scope", "") or ("selection" if selected_text else "visible")),
        content_upload_allowed=analysis_allowed,
        transcript_status=TranscriptStatus.RUNNING,
        analysis_requested=analysis_allowed,
        analysis_status="pending" if analysis_allowed else "skipped",
        analysis_skip_reason="" if analysis_allowed else "content_upload_not_allowed",
        transcript_only=not analysis_allowed,
        analysis_profile=source.analysis_profile,
        processing_profile=str(getattr(record, "processing_profile", "fast") or "fast"),
    )
    ensure_dir(output_dir)
    try:
        blocks = _page_blocks(captured_text)
        chunks = [str(item["text"]) for item in blocks]
        segments = _segments_from_chunks(chunks)
        groups = _groups_from_segments(segments)
        timeline = []

        write_jsonl(output_dir / "transcript.raw.jsonl", segments)
        save_json(
            output_dir / "page_content.json",
            {
                "schema_version": "1.0",
                "capture_scope": str(getattr(record, "capture_scope", "") or ("selection" if selected_text else "visible")),
                "captured_at": source.captured_at,
                "content_sha256": str(getattr(record, "content_sha256", "") or ""),
                "blocks": blocks,
            },
        )
        write_text(output_dir / "page.md", _page_markdown(source, blocks))
        write_text(output_dir / "transcript.grouped.md", _compat_grouped_markdown(blocks))
        write_text(output_dir / "transcript.md", _compat_transcript_markdown(blocks))
        manifest.transcript_status = TranscriptStatus.COMPLETED
        manifest.transcript_provider = "browser_capture"
        manifest.transcript_actual_provider = "browser_capture"
        manifest.transcript_actual_device = "local"
        manifest.transcript_progress = 1
        manifest.last_segment_end = 0
        manifest.first_readable_result_at = utc_now()
        manifest.first_readable_result_duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        manifest.stage_status.update(
            {
                "capture_page_content": "completed",
                "normalize_page_content": "completed",
                "group_page_content": "completed",
                "build_timeline": "completed",
                "extract_frames": "skipped",
                "visual_analysis": "skipped",
                "comments_fetch": "skipped",
                "comments_analysis": "skipped",
            }
        )

        if analysis_allowed:
            if provider is None or not bool(getattr(provider, "is_available", lambda: False)()):
                raise UserFacingError("文字分析服务尚未配置，请完成 API 配置后重试。")
            manifest.current_stage = "run_analysis"
            context = SimpleNamespace(
                source=source,
                processing_profile=manifest.processing_profile,
                analysis=None,
            )
            analysis = AnalysisService(provider).analyze(groups, source.analysis_profile, context)
            manifest.analysis_status = "completed"
            manifest.analysis_provider = str(getattr(provider, "name", "") or analysis.provider)
            manifest.analysis_model = str(getattr(provider, "model_name", "") or analysis.model)
            manifest.llm_provider = manifest.analysis_provider
            manifest.llm_model = manifest.analysis_model
            manifest.stage_status["run_analysis"] = "completed"
        else:
            analysis = AnalysisResult(
                status="skipped",
                analysis_profile=source.analysis_profile,
                processing_profile=manifest.processing_profile,
                source={
                    "platform": source.platform,
                    "url": source.canonical_url,
                    "title": source.title,
                    "source_id": source.source_id,
                },
            )
            manifest.stage_status["run_analysis"] = "skipped"

        manifest.current_stage = "export_knowledge_package"
        manifest.completed_at = utc_now()
        manifest.status = "completed"
        package = KnowledgePackage(
            source=source,
            transcript_segments=segments,
            transcript_groups=groups,
            timeline=timeline,
            analysis=analysis,
            manifest=manifest,
            output_dir=output_dir,
        )
        exported = export_knowledge_package(package)
        manifest.output_files = [
            "page_content.json",
            "page.md",
            "transcript.raw.jsonl",
            "transcript.grouped.md",
            "transcript.md",
            *[path.name for path in exported],
        ]
        manifest.stage_status["export_knowledge_package"] = "completed"
        manifest.full_completion_duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        export_knowledge_package(package)
        inspection = inspect_knowledge_package(output_dir)
        if not inspection.valid:
            errors = [issue.message for issue in inspection.issues if issue.severity == "error"]
            raise UserFacingError("网页知识包完整性检查失败：" + "；".join(errors[:3]))
        return package
    except Exception as exc:
        manifest.status = "failed"
        manifest.completed_at = utc_now()
        manifest.current_stage = manifest.current_stage or "page_ingestion"
        manifest.errors = [str(exc)[:500]]
        if manifest.analysis_requested and manifest.analysis_status == "pending":
            manifest.analysis_status = "failed"
            manifest.analysis_error = str(exc)[:500]
            manifest.stage_status["run_analysis"] = "failed"
        save_json(output_dir / "metadata.json", source.model_dump(mode="json"))
        save_json(output_dir / "manifest.json", manifest.model_dump(mode="json"))
        raise
    finally:
        claim.release()


def _page_chunks(value: str) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", value).strip()
    paragraphs = [re.sub(r"[ \t]+", " ", item).strip() for item in re.split(r"\n\s*\n+", normalized)]
    chunks: list[str] = []
    for paragraph in (item for item in paragraphs if item):
        remaining = paragraph
        while len(remaining) > PAGE_CHUNK_CHARACTERS:
            boundary = remaining.rfind(" ", 0, PAGE_CHUNK_CHARACTERS + 1)
            if boundary < PAGE_CHUNK_CHARACTERS // 2:
                boundary = PAGE_CHUNK_CHARACTERS
            chunks.append(remaining[:boundary].strip())
            remaining = remaining[boundary:].strip()
        if remaining:
            chunks.append(remaining)
    if not chunks:
        raise UserFacingError("网页捕获正文为空，请重新捕获。")
    return chunks


def _page_blocks(value: str) -> list[dict[str, object]]:
    chunks = _page_chunks(value)
    blocks: list[dict[str, object]] = []
    offset = 0
    for index, text in enumerate(chunks):
        start = value.find(text, offset)
        if start < 0:
            start = offset
        end = start + len(text)
        blocks.append(
            {
                "index": index,
                "heading": _section_title(text, index),
                "text": text,
                "char_start": start,
                "char_end": end,
            }
        )
        offset = end
    return blocks


def _segments_from_chunks(chunks: list[str]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            index=index,
            start=0,
            end=0,
            text=text,
            source="browser_page_capture",
        )
        for index, text in enumerate(chunks)
    ]


def _groups_from_segments(segments: list[TranscriptSegment]) -> list[TranscriptGroup]:
    return [
        TranscriptGroup(
            index=item.index,
            start=0,
            end=0,
            title=_section_title(item.text, item.index),
            text=item.text,
            segment_indexes=[item.index],
            representative_time=None,
        )
        for item in segments
    ]


def _section_title(text: str, index: int) -> str:
    first_line = re.sub(r"\s+", " ", text).strip()
    return first_line[:48].rstrip("，。；：,. ;:") or f"页面片段 {index + 1}"


def _page_platform(url: str) -> str:
    host = (urlsplit(url).hostname or "web").lower()
    return host.removeprefix("www.") or "web"


def _fallback_title(url: str) -> str:
    host = (urlsplit(url).hostname or "网页内容").removeprefix("www.")
    return host or "网页内容"


def _page_markdown(source: SourceRecord, blocks: list[dict[str, object]]) -> str:
    lines = [
        f"# {_markdown_text(source.title)}",
        "",
        f"> 来源：[{_markdown_text(source.canonical_url)}]({_markdown_url(source.canonical_url)})",
        f"> 捕获时间：{_markdown_text(source.captured_at)}",
        "",
        "## 页面正文",
        "",
    ]
    for block in blocks:
        lines.extend(
            [
                f"### {int(block['index']) + 1}. {_markdown_text(block['heading'])}",
                "",
                _markdown_text(block["text"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _compat_grouped_markdown(blocks: list[dict[str, object]]) -> str:
    lines = ["# 页面正文分组", ""]
    for block in blocks:
        lines.extend(
            [
                f"## {int(block['index']) + 1}. {_markdown_text(block['heading'])}",
                "",
                _markdown_text(block["text"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _compat_transcript_markdown(blocks: list[dict[str, object]]) -> str:
    text = "\n\n".join(_markdown_text(block["text"]) for block in blocks)
    return f"# 页面正文\n\n{text}\n"


def _markdown_text(value: object) -> str:
    escaped = html.escape(str(value or ""), quote=False)
    return re.sub(r"([\\`*_{}\[\]<>#+.!|-])", r"\\\1", escaped)


def _markdown_url(value: str) -> str:
    return str(value or "").replace("(", "%28").replace(")", "%29").replace(" ", "%20")


__all__ = ["ingest_page_capture"]
