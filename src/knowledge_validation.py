from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from .domain.models import AnalysisResult, ProcessingManifest, SourceRecord, TranscriptSegment


REQUIRED_PACKAGE_FILES = (
    "index.md",
    "metadata.json",
    "manifest.json",
    "analysis.json",
    "timeline.json",
    "source.md",
    "transcript.raw.jsonl",
    "transcript.grouped.md",
    "transcript.md",
)
PAGE_REQUIRED_PACKAGE_FILES = ("page_content.json", "page.md")


@dataclass(frozen=True)
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    file: str = ""


@dataclass
class KnowledgePackageInspection:
    package_path: str
    knowledge_id: str
    level: Literal["valid", "warning", "invalid"] = "valid"
    valid: bool = True
    manifest_status: str = ""
    analysis_status: str = ""
    transcript_segments: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, severity: Literal["error", "warning"], code: str, message: str, file: str = "") -> None:
        self.issues.append(ValidationIssue(severity=severity, code=code, message=message, file=file))
        if severity == "error":
            self.level = "invalid"
            self.valid = False
        elif self.level == "valid":
            self.level = "warning"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


def inspect_knowledge_package(package_path: Path) -> KnowledgePackageInspection:
    root = package_path.expanduser().resolve()
    report = KnowledgePackageInspection(package_path=str(root), knowledge_id=root.name)
    if not root.exists() or not root.is_dir():
        report.add("error", "package_missing", f"知识包目录不存在：{root}")
        return report

    for name in REQUIRED_PACKAGE_FILES:
        if not (root / name).is_file():
            report.add("error", "required_file_missing", f"缺少知识包文件：{name}", name)

    metadata = _load_json_object(root / "metadata.json", report, required=True)
    manifest_data = _load_json_object(root / "manifest.json", report, required=True)
    analysis_data = _load_json_object(root / "analysis.json", report, required=True)
    timeline_data = _load_json_object(root / "timeline.json", report, required=True)
    source_data = manifest_data.get("source") if isinstance(manifest_data.get("source"), dict) else metadata
    is_page = str(source_data.get("source_type") or "") == "web_page" if isinstance(source_data, dict) else False
    if is_page:
        for name in PAGE_REQUIRED_PACKAGE_FILES:
            if not (root / name).is_file():
                report.add("error", "required_file_missing", f"缺少网页知识包文件：{name}", name)

    manifest = _validate_manifest(manifest_data, report)
    report.manifest_status = str(manifest_data.get("status") or "")
    _validate_source(source_data, report)
    _validate_transcript(root, report)
    _validate_timeline(timeline_data, report, allow_empty=is_page)
    if is_page:
        _validate_page_content(root / "page_content.json", report)
    _validate_analysis(analysis_data, manifest_data, report)
    _validate_markdown(root, report)
    _validate_declared_outputs(root, manifest, report)
    return report


def meaningful_analysis(data: dict[str, Any]) -> bool:
    return any(
        (
            str(data.get("one_sentence_summary") or "").strip(),
            str(data.get("summary") or "").strip(),
            data.get("highlights") if isinstance(data.get("highlights"), list) else [],
            data.get("thoughts") if isinstance(data.get("thoughts"), list) else [],
            data.get("chapters") if isinstance(data.get("chapters"), list) else [],
            data.get("terminology") if isinstance(data.get("terminology"), list) else [],
            data.get("actions") if isinstance(data.get("actions"), list) else [],
            data.get("content") if isinstance(data.get("content"), dict) else {},
        )
    )


def _load_json_object(path: Path, report: KnowledgePackageInspection, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.add("error", "json_invalid", f"{path.name} 不是有效 JSON：{exc}", path.name)
        return {}
    if not isinstance(value, dict):
        report.add("error", "json_root_invalid", f"{path.name} 顶层必须是 JSON 对象。", path.name)
        return {}
    if required and not value:
        report.add("error", "json_empty", f"{path.name} 不能为空对象。", path.name)
    return value


def _validate_manifest(data: dict[str, Any], report: KnowledgePackageInspection) -> ProcessingManifest | None:
    if not data:
        return None
    try:
        manifest = ProcessingManifest.model_validate(data)
    except ValidationError as exc:
        report.add("error", "manifest_schema_invalid", f"manifest.json 结构无效：{exc}", "manifest.json")
        return None
    if not manifest.task_id.strip():
        report.add("error", "manifest_task_missing", "manifest.json 缺少 task_id。", "manifest.json")
    if manifest.status == "failed":
        report.add("warning", "task_failed", "该目录来自失败任务，不是完整成功知识包。", "manifest.json")
    return manifest


def _validate_source(data: Any, report: KnowledgePackageInspection) -> None:
    if not isinstance(data, dict) or not data:
        report.add("error", "source_missing", "缺少有效来源信息。", "metadata.json")
        return
    try:
        source = SourceRecord.model_validate(data)
    except ValidationError as exc:
        report.add("error", "source_schema_invalid", f"来源信息结构无效：{exc}", "metadata.json")
        return
    if not source.title.strip():
        report.add("error", "source_title_missing", "来源标题不能为空。", "metadata.json")
    if not source.source_id.strip():
        report.add("error", "source_id_missing", "来源 ID 不能为空。", "metadata.json")


def _validate_transcript(root: Path, report: KnowledgePackageInspection) -> None:
    path = root / "transcript.raw.jsonl"
    if not path.is_file():
        return
    segments: list[TranscriptSegment] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            segment = TranscriptSegment.model_validate_json(line)
        except (ValidationError, ValueError) as exc:
            report.add(
                "error",
                "transcript_segment_invalid",
                f"transcript.raw.jsonl 第 {line_number} 行无效：{exc}",
                path.name,
            )
            continue
        if segment.end < segment.start:
            report.add(
                "error",
                "transcript_time_invalid",
                f"字幕段 {segment.index} 的结束时间早于开始时间。",
                path.name,
            )
        if segment.text.strip():
            segments.append(segment)
    report.transcript_segments = len(segments)
    if not segments:
        report.add("error", "transcript_empty", "逐句字幕没有有效文本。", path.name)


def _validate_timeline(
    data: dict[str, Any],
    report: KnowledgePackageInspection,
    *,
    allow_empty: bool = False,
) -> None:
    if not data:
        return
    items = data.get("items")
    if not isinstance(items, list):
        report.add("error", "timeline_items_invalid", "timeline.json 的 items 必须是数组。", "timeline.json")
    elif not items and not allow_empty:
        report.add("error", "timeline_empty", "timeline.json 没有有效时间轴条目。", "timeline.json")


def _validate_page_content(path: Path, report: KnowledgePackageInspection) -> None:
    data = _load_json_object(path, report, required=True)
    if not data:
        return
    if str(data.get("schema_version") or "") != "1.0":
        report.add("error", "page_schema_invalid", "page_content.json schema_version 必须是 1.0。", path.name)
    if str(data.get("capture_scope") or "") not in {"selection", "visible"}:
        report.add("error", "page_scope_invalid", "page_content.json 缺少有效捕获范围。", path.name)
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        report.add("error", "page_blocks_empty", "page_content.json 没有有效正文分块。", path.name)
        return
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or not str(block.get("text") or "").strip():
            report.add("error", "page_block_invalid", f"页面正文分块 {index + 1} 无效。", path.name)
            break


def _validate_analysis(
    data: dict[str, Any],
    manifest: dict[str, Any],
    report: KnowledgePackageInspection,
) -> None:
    if not data:
        report.analysis_status = "invalid"
        _analysis_manifest_conflict(report, manifest, "analysis.json 为空，不能视为分析成功。")
        return
    raw_status = str(data.get("status") or "").strip()
    if not raw_status and not meaningful_analysis(data):
        report.analysis_status = "invalid"
        _analysis_manifest_conflict(
            report,
            manifest,
            "analysis.json 缺少 status，且摘要、亮点、章节等内容全部为空。",
        )
        return
    if not raw_status:
        report.add(
            "warning",
            "analysis_status_legacy",
            "analysis.json 缺少显式 status；根据有效内容按旧格式读取。",
            "analysis.json",
        )
        data = {**data, "status": "success"}
    try:
        result = AnalysisResult.model_validate(data)
    except ValidationError as exc:
        report.analysis_status = "invalid"
        report.add("error", "analysis_schema_invalid", f"analysis.json 结构无效：{exc}", "analysis.json")
        return

    report.analysis_status = result.status
    manifest_analysis_status = str(manifest.get("analysis_status") or "pending")
    stage_status = str((manifest.get("stage_status") or {}).get("run_analysis") or "")
    overall_status = str(manifest.get("status") or "")

    if result.status == "success":
        if not meaningful_analysis(data):
            report.analysis_status = "invalid"
            _analysis_manifest_conflict(report, manifest, "analysis.json 标记 success，但没有有效分析内容。")
            return
        if manifest_analysis_status == "pending":
            report.add(
                "warning",
                "analysis_manifest_legacy",
                "manifest.json 缺少显式 analysis_status；这是旧知识包格式。",
                "manifest.json",
            )
        elif manifest_analysis_status != "completed":
            report.add(
                "error",
                "analysis_manifest_conflict",
                f"analysis.json 为 success，但 manifest analysis_status={manifest_analysis_status}。",
                "manifest.json",
            )
        if stage_status and stage_status != "completed":
            report.add(
                "error",
                "analysis_stage_conflict",
                f"分析内容成功，但 run_analysis 阶段状态为 {stage_status}。",
                "manifest.json",
            )
    elif result.status in {"failed", "timeout"}:
        if not result.error.strip():
            report.add("error", "analysis_error_missing", "失败或超时分析必须记录 error。", "analysis.json")
        expected_manifest_status = result.status
        if manifest_analysis_status == "pending":
            report.add(
                "warning",
                "analysis_manifest_legacy",
                "manifest.json 未显式记录分析失败状态。",
                "manifest.json",
            )
        elif manifest_analysis_status != expected_manifest_status:
            report.add(
                "error",
                "analysis_manifest_conflict",
                f"analysis.json 为 {result.status}，但 manifest analysis_status={manifest_analysis_status}。",
                "manifest.json",
            )
        if overall_status == "completed":
            report.add(
                "error",
                "task_status_conflict",
                "分析失败时任务不能标记为 completed；应为 completed_with_warnings 或 failed。",
                "manifest.json",
            )
        report.add(
            "warning",
            "analysis_timeout" if result.status == "timeout" else "analysis_failed",
            f"AI 分析{'超时' if result.status == 'timeout' else '失败'}：{result.error}",
            "analysis.json",
        )
    elif result.status == "skipped":
        if manifest_analysis_status == "pending":
            report.add(
                "warning",
                "analysis_manifest_legacy",
                "manifest.json 未显式记录分析跳过状态。",
                "manifest.json",
            )
        elif manifest_analysis_status != "skipped":
            report.add(
                "error",
                "analysis_manifest_conflict",
                f"analysis.json 为 skipped，但 manifest analysis_status={manifest_analysis_status}。",
                "manifest.json",
            )
        if stage_status and stage_status not in {"skipped", "completed"}:
            report.add(
                "error",
                "analysis_stage_conflict",
                f"分析已跳过，但 run_analysis 阶段状态为 {stage_status}。",
                "manifest.json",
            )


def _analysis_manifest_conflict(
    report: KnowledgePackageInspection,
    manifest: dict[str, Any],
    message: str,
) -> None:
    report.add("error", "analysis_invalid", message, "analysis.json")
    stage_status = str((manifest.get("stage_status") or {}).get("run_analysis") or "")
    if stage_status == "completed" or str(manifest.get("status") or "") == "completed":
        report.add(
            "error",
            "analysis_manifest_conflict",
            "Manifest 把无效分析标记为完成。",
            "manifest.json",
        )


def _validate_markdown(root: Path, report: KnowledgePackageInspection) -> None:
    for name in ("index.md", "source.md", "transcript.grouped.md", "transcript.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            report.add("error", "text_read_failed", f"{name} 无法按 UTF-8 读取：{exc}", name)
            continue
        if len(text) < 10:
            report.add("error", "text_empty", f"{name} 没有有效内容。", name)


def _validate_declared_outputs(
    root: Path,
    manifest: ProcessingManifest | None,
    report: KnowledgePackageInspection,
) -> None:
    if not manifest:
        return
    for name in manifest.output_files:
        if not (root / name).exists():
            report.add(
                "error",
                "declared_output_missing",
                f"manifest.json 声明的输出不存在：{name}",
                "manifest.json",
            )
