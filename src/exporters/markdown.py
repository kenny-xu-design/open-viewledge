from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..cleaner import seconds_to_timestamp
from ..domain.models import KnowledgePackage
from ..utils import write_text


def render_index(package: KnowledgePackage, template_dir: Path, output_path: Path) -> Path:
    environment = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape(default=False), trim_blocks=True, lstrip_blocks=True)
    environment.filters["timestamp"] = seconds_to_timestamp
    template = environment.get_template("index.md.j2")
    write_text(output_path, template.render(
        source=package.source.model_dump(),
        analysis=package.analysis.model_dump() if package.analysis else {},
        timeline=[item.model_dump() for item in package.timeline],
        manifest=package.manifest.model_dump(),
    ).strip() + "\n")
    return output_path

