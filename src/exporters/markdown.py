from __future__ import annotations

from pathlib import Path

from ..domain.models import KnowledgePackage
from ..utils import write_text
from .markdown_renderer import render_knowledge_markdown
from .models import selection_from_preset


def render_index(package: KnowledgePackage, template_dir: Path, output_path: Path) -> Path:
    selection = selection_from_preset(package.output_dir.name, "full")
    selection.sections = [value for value in selection.sections if value not in {"chat", "user_notes", "keyframes"}]
    write_text(output_path, render_knowledge_markdown(package, selection))
    return output_path

