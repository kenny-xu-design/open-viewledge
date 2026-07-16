from __future__ import annotations

import os
import tempfile
from pathlib import Path


def refresh_compatible_export(directory: Path) -> Path:
    index_path = directory / "index.md"
    if not index_path.is_file():
        raise FileNotFoundError("index.md")
    content = index_path.read_text(encoding="utf-8").rstrip()
    notes_path = directory / "user_notes.md"
    notes = notes_path.read_text(encoding="utf-8").strip() if notes_path.is_file() else ""
    if notes:
        content = f"{content}\n\n## 自写笔记\n\n{notes}"
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
