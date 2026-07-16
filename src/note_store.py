from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


MAX_NOTE_BYTES = 1024 * 1024
USER_NOTES_FILENAME = "user_notes.md"
_NOTE_LOCK = threading.RLock()


class NoteConflictError(ValueError):
    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__("笔记已被其他页面更新，请确认最新内容后再保存。")
        self.current = current


class NoteStore:
    def __init__(self, resolve_directory: Callable[[str], Path]) -> None:
        self._resolve_directory = resolve_directory

    def load(self, knowledge_id: str) -> dict[str, Any]:
        path = self._path(knowledge_id)
        with _NOTE_LOCK:
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            updated_at = (
                datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                if path.exists()
                else ""
            )
        return {
            "knowledge_id": knowledge_id,
            "content": content,
            "revision": _revision(content),
            "updated_at": updated_at,
        }

    def save(
        self,
        knowledge_id: str,
        content: str,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(content, str):
            raise ValueError("笔记内容必须是字符串。")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_NOTE_BYTES:
            raise ValueError("笔记内容不能超过 1 MiB。")

        path = self._path(knowledge_id)
        with _NOTE_LOCK:
            current = self.load(knowledge_id)
            if expected_revision is not None and expected_revision != current["revision"]:
                raise NoteConflictError(current)
            handle, temporary_name = tempfile.mkstemp(prefix="notes-", suffix=".md", dir=path.parent)
            try:
                with os.fdopen(handle, "wb") as temporary:
                    temporary.write(encoded)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, path)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        return self.load(knowledge_id)

    def _path(self, knowledge_id: str) -> Path:
        return self._resolve_directory(knowledge_id) / USER_NOTES_FILENAME


def _revision(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
