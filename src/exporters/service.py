from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..domain.models import AnalysisResult, KnowledgePackage, ProcessingManifest, SourceRecord, TimelineEntry
from ..analysis.entities import normalize_analysis_entities
from ..utils import UserFacingError, sanitize_filename
from .markdown_renderer import render_knowledge_markdown
from .models import ExportSelection, selection_from_preset
from .obsidian_exporter import safe_export_filename, write_to_vault


def load_package_for_export(directory: Path) -> tuple[KnowledgePackage, dict[str, Any], str, dict[str, Any]]:
    root = directory.resolve()
    metadata = _json(root / "metadata.json")
    manifest_payload = _json(root / "manifest.json")
    source_payload = manifest_payload.get("source") if isinstance(manifest_payload.get("source"), dict) else dict(metadata)
    source_payload.setdefault("source_type", "local_video" if source_payload.get("local_path") or source_payload.get("source_path") else "online_video")
    source_payload.setdefault("platform", "local" if source_payload["source_type"].startswith("local") else "unknown")
    source_payload.setdefault("source_id", root.name)
    source_payload.setdefault("title", root.name)
    source = SourceRecord.model_validate(source_payload)
    manifest_payload.setdefault("task_id", root.name)
    manifest_payload["source"] = source.model_dump(mode="json")
    manifest = ProcessingManifest.model_validate(manifest_payload)
    analysis_payload = _json(root / "analysis.json")
    analysis = normalize_analysis_entities(AnalysisResult.model_validate(analysis_payload)) if analysis_payload else None
    timeline = [TimelineEntry.model_validate(item) for item in _json(root / "timeline.json").get("items", []) if isinstance(item, dict)]
    package = KnowledgePackage(source=source, analysis=analysis, timeline=timeline, manifest=manifest, output_dir=root)
    chat = _json(root / "chat.json")
    notes = (root / "user_notes.md").read_text(encoding="utf-8") if (root / "user_notes.md").is_file() else ""
    comment_insight = _json(root / "comment_insights.json")
    return package, chat, notes, comment_insight


def render_directory_export(directory: Path, selection: ExportSelection) -> tuple[str, str]:
    package, chat, notes, comment_insight = load_package_for_export(directory)
    filename = selection.filename or safe_export_filename(package.source.title or selection.knowledge_id)
    return render_knowledge_markdown(
        package,
        selection,
        chat=chat,
        user_notes=notes,
        comment_insight=comment_insight,
    ), safe_export_filename(Path(filename).stem)


def export_directory_to_vault(
    directory: Path,
    selection: ExportSelection,
    *,
    vault_path: str,
    vault_name: str = "",
    subdir: str = "外源/视频",
) -> dict[str, Any]:
    package, chat, notes, comment_insight = load_package_for_export(directory)
    filename = selection.filename or safe_export_filename(package.source.title or selection.knowledge_id)
    filename = safe_export_filename(Path(filename).stem)
    asset_prefix = (
        Path("assets")
        / "video-summary"
        / sanitize_filename(selection.knowledge_id, "knowledge")
        / "tutorial"
    ).as_posix()
    markdown = render_knowledge_markdown(
        package,
        selection,
        chat=chat,
        user_notes=notes,
        comment_insight=comment_insight,
        highlight_image_prefix=asset_prefix,
    )
    path, uri = write_to_vault(markdown, vault_path, subdir, filename, overwrite=selection.overwrite)
    copied_assets = []
    if package.analysis and package.analysis.analysis_profile == "tutorial":
        for item in package.analysis.steps:
            if not item.image:
                continue
            source = (directory / item.image).resolve()
            try:
                source.relative_to(directory.resolve())
            except ValueError:
                continue
            if not source.is_file():
                continue
            target = path.parent / asset_prefix / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_assets.append(target.relative_to(Path(vault_path).expanduser().resolve()).as_posix())
    return {
        "success": True,
        "knowledge_id": selection.knowledge_id,
        "format": "obsidian-markdown",
        "file_path": str(path),
        "relative_vault_path": path.relative_to(Path(vault_path).expanduser().resolve()).as_posix(),
        "obsidian_uri": uri if not vault_name else uri.replace("vault=" + Path(vault_path).name, "vault=" + vault_name),
        "included_sections": selection.normalized_sections(),
        "copied_assets": copied_assets,
    }


def selection_for_request(knowledge_id: str, payload: dict[str, Any]) -> ExportSelection:
    selection = selection_from_preset(
        knowledge_id,
        str(payload.get("preset") or "full"),
        schema_version=str(payload.get("schema_version") or "1.0"),
        destination=str(payload.get("destination") or "preview"),
        overwrite=bool(payload.get("overwrite", False)),
        open_after_export=bool(payload.get("open_after_export", False)),
        filename=str(payload.get("filename") or ""),
    )
    if isinstance(payload.get("sections"), list):
        selection.sections = [str(value) for value in payload["sections"]]
    if isinstance(payload.get("order"), list):
        selection.order = [str(value) for value in payload["order"]]
    if not selection.normalized_sections():
        raise UserFacingError("至少选择一个可导出的内容栏目。")
    return selection


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}
