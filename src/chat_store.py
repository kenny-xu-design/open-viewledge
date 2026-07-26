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
                return self._default(knowledge_id)
            payload = json.loads(path.read_text(encoding="utf-8"))
        messages = payload.get("messages") if isinstance(payload, dict) else []
        result = self._default(knowledge_id)
        if isinstance(payload, dict):
            for key in (
                "chat_id",
                "source_url",
                "source_fingerprint",
                "provider",
                "model",
                "route",
                "route_status",
                "remote_session_id",
                "remote_file_id",
                "remote_expires_at",
                "recovery_state",
                "degradation_reason",
                "updated_at",
            ):
                result[key] = str(payload.get(key) or "")
        result["messages"] = self._normalize_messages(messages if isinstance(messages, list) else [])
        return result

    def append(self, knowledge_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        with _CHAT_LOCK:
            payload = self.load(knowledge_id)
            payload["messages"] = (payload["messages"] + self._normalize_messages(messages))[-MAX_MESSAGES:]
            return self._save(knowledge_id, payload)

    def replace(self, knowledge_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        with _CHAT_LOCK:
            payload = self.load(knowledge_id)
            payload["messages"] = self._normalize_messages(messages)[-MAX_MESSAGES:]
            return self._save(knowledge_id, payload)

    def update_state(self, knowledge_id: str, **values: str) -> dict[str, Any]:
        allowed = {
            "chat_id",
            "source_url",
            "source_fingerprint",
            "provider",
            "model",
            "route",
            "route_status",
            "remote_session_id",
            "remote_file_id",
            "remote_expires_at",
            "recovery_state",
            "degradation_reason",
        }
        with _CHAT_LOCK:
            payload = self.load(knowledge_id)
            for key, value in values.items():
                if key in allowed:
                    payload[key] = str(value or "")
            if not payload["chat_id"]:
                payload["chat_id"] = uuid.uuid4().hex
            return self._save(knowledge_id, payload)

    def reset_for_source(
        self,
        knowledge_id: str,
        *,
        source_url: str,
        source_fingerprint: str,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        payload = self._default(knowledge_id)
        payload.update(
            {
                "chat_id": uuid.uuid4().hex,
                "source_url": source_url,
                "source_fingerprint": source_fingerprint,
                "provider": provider,
                "model": model,
                "recovery_state": "source_changed",
            }
        )
        with _CHAT_LOCK:
            return self._save(knowledge_id, payload)

    def clear(self, knowledge_id: str) -> None:
        path = self._path(knowledge_id)
        with _CHAT_LOCK:
            if path.exists():
                path.unlink()

    def _save(self, knowledge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._path(knowledge_id)
        payload = {**self._default(knowledge_id), **payload}
        payload["knowledge_id"] = knowledge_id
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["messages"] = self._normalize_messages(payload.get("messages") or [])[-MAX_MESSAGES:]
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
                normalized["route"] = str(item.get("route") or "")
                normalized["route_status"] = str(item.get("route_status") or "")
            result.append(normalized)
        return result

    @staticmethod
    def _default(knowledge_id: str) -> dict[str, Any]:
        return {
            "chat_id": "",
            "knowledge_id": knowledge_id,
            "source_url": "",
            "source_fingerprint": "",
            "provider": "",
            "model": "",
            "route": "",
            "route_status": "",
            "remote_session_id": "",
            "remote_file_id": "",
            "remote_expires_at": "",
            "recovery_state": "",
            "degradation_reason": "",
            "updated_at": "",
            "messages": [],
        }
