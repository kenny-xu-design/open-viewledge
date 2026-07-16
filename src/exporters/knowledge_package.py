from __future__ import annotations

from pathlib import Path

from ..domain.models import KnowledgePackage
from ..utils import save_json, write_text
from .compatible_note import refresh_compatible_export
from .markdown import render_index


def export_knowledge_package(package: KnowledgePackage, export_legacy_note: bool = False) -> list[Path]:
    root = package.output_dir
    metadata = root / "metadata.json"
    manifest = root / "manifest.json"
    analysis = root / "analysis.json"
    timeline = root / "timeline.json"
    source_md = root / "source.md"
    index = root / "index.md"
    save_json(metadata, package.source.model_dump(mode="json"))
    save_json(manifest, package.manifest.model_dump(mode="json"))
    save_json(analysis, (package.analysis or {}).model_dump(mode="json") if package.analysis else {})
    save_json(timeline, {"items": [item.model_dump(mode="json") for item in package.timeline]})
    write_text(source_md, _source_markdown(package))
    render_index(package, Path(__file__).parent / "templates", index)
    files = [index, metadata, manifest, analysis, timeline, source_md]
    if export_legacy_note:
        legacy = refresh_compatible_export(root)
        files.append(legacy)
    return files


def _source_markdown(package: KnowledgePackage) -> str:
    source = package.source
    lines = [f"# {source.title}", "", source.description or "暂无来源简介。", ""]
    if source.chapters:
        lines.extend(["## 原始章节", ""])
        for chapter in source.chapters:
            lines.append(f"- {chapter.get('title', '未命名章节')} ({chapter.get('start_time', chapter.get('start', 0))}s)")
    return "\n".join(lines).rstrip() + "\n"

