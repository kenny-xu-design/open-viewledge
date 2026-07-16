from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


MAX_MESSAGES = 200
MAX_CONTENT_LENGTH = 20_000
_CHAT_LOCK = threading.RLock()


class ChatStore:
    def __init__(self, resolve_directory: Callable[[str], Path]) -> None:
        self._resolve_directory = resolve_directory

    def load(self, knowledge_id: str) -> dict[str, Any]:
        path = self._path(knowledge_id)
        with _CHAT_LOCK:
            if not path.exists():
                return {"knowledge_id": knowledge_id, "updated_at": "", "messages": []}
            payload = json.loads(path.read_text(encoding="utf-8"))
        messages = payload.get("messages") if isinstance(payload, dict) else []
        return {
            "knowledge_id": knowledge_id,
            "updated_at": str(payload.get("updated_at") or "") if isinstance(payload, dict) else "",
            "messages": self._normalize_messages(messages if isinstance(messages, list) else []),
        }

    def append(self, knowledge_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        with _CHAT_LOCK:
            payload = self.load(knowledge_id)
            payload["messages"] = (payload["messages"] + self._normalize_messages(messages))[-MAX_MESSAGES:]
            return self._save(knowledge_id, payload["messages"])

    def replace(self, knowledge_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        with _CHAT_LOCK:
            return self._save(knowledge_id, self._normalize_messages(messages)[-MAX_MESSAGES:])

    def clear(self, knowledge_id: str) -> None:
        path = self._path(knowledge_id)
        with _CHAT_LOCK:
            if path.exists():
                path.unlink()

    def _save(self, knowledge_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        path = self._path(knowledge_id)
        payload = {
            "knowledge_id": knowledge_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "messages": messages,
        }
        handle, temporary_name = tempfile.mkstemp(prefix="chat-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return payload

    def _path(self, knowledge_id: str) -> Path:
        return self._resolve_directory(knowledge_id) / "chat.json"

    @staticmethod
    def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized: dict[str, Any] = {
                "id": str(item.get("id") or uuid.uuid4().hex),
                "role": role,
                "content": content[:MAX_CONTENT_LENGTH],
                "created_at": str(item.get("created_at") or datetime.now(timezone.utc).isoformat()),
            }
            if role == "assistant":
                normalized["citations"] = item.get("citations") if isinstance(item.get("citations"), list) else []
                normalized["provider"] = str(item.get("provider") or "")
                normalized["model"] = str(item.get("model") or "")
                normalized["warning"] = str(item.get("warning") or "")
            result.append(normalized)
        return result
