from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import selection_from_preset


def refresh_compatible_export(directory: Path) -> Path:
    from .service import render_directory_export

    if not (directory / "index.md").is_file():
        raise FileNotFoundError("index.md")
    content, _ = render_directory_export(directory, selection_from_preset(directory.name, "full"))
    output_path = directory / "export_note.md"
    _atomic_write_text(output_path, content.rstrip() + "\n")
    return output_path


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix="export-note-", suffix=".md", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
