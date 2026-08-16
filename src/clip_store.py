from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledge_identity import normalize_source_url


SCHEMA_VERSION = "1.0"
MAX_CLIPS = 5000
MAX_TEXT = 12000
MAX_NOTE = 4000
MAX_CONTEXT = 800


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: object, field_name: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{field_name} exceeds {limit} characters")
    return value


def _canonical_url(value: object) -> str:
    raw = _bounded_text(value, "source.url", 4000)
    try:
        return normalize_source_url(raw)
    except ValueError as exc:
        raise ValueError("source.url must be an http or https URL") from exc


@dataclass
class ClipRecord:
    clip_id: str
    client_request_id: str
    kind: str
    idempotency_key: str
    creation_fingerprint: str
    intake_id: str
    knowledge_id: str
    source_url: str
    source_title: str
    selected_text: str
    prefix: str
    suffix: str
    media_start_seconds: float | None
    media_end_seconds: float | None
    note: str
    captured_at: str
    created_at: str = field(default_factory=_utc_now)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    def to_public(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "clip_id": self.clip_id,
            "client_request_id": self.client_request_id,
            "kind": self.kind,
            "target": {"intake_id": self.intake_id or None, "knowledge_id": self.knowledge_id or None},
            "source": {"url": self.source_url, "title": self.source_title},
            "selection": {
                "text": self.selected_text,
                "prefix": self.prefix,
                "suffix": self.suffix,
                "media_start_seconds": self.media_start_seconds,
                "media_end_seconds": self.media_end_seconds,
            },
            "note": self.note,
            "captured_at": self.captured_at,
            "created_at": self.created_at,
            "provenance": {"status": "captured", "source_url": self.source_url},
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> "ClipRecord":
        return cls(
            clip_id=str(raw.get("clip_id") or ""), client_request_id=str(raw.get("client_request_id") or ""),
            kind=str(raw.get("kind") or "clip"),
            idempotency_key=str(raw.get("idempotency_key") or ""), creation_fingerprint=str(raw.get("creation_fingerprint") or ""),
            intake_id=str(raw.get("intake_id") or ""), knowledge_id=str(raw.get("knowledge_id") or ""),
            source_url=str(raw.get("source_url") or ""), source_title=str(raw.get("source_title") or ""),
            selected_text=str(raw.get("selected_text") or ""), prefix=str(raw.get("prefix") or ""), suffix=str(raw.get("suffix") or ""),
            media_start_seconds=float(raw["media_start_seconds"]) if isinstance(raw.get("media_start_seconds"), (int, float)) else None,
            media_end_seconds=float(raw["media_end_seconds"]) if isinstance(raw.get("media_end_seconds"), (int, float)) else None,
            note=str(raw.get("note") or ""), captured_at=str(raw.get("captured_at") or _utc_now()), created_at=str(raw.get("created_at") or _utc_now()),
        )


class ClipStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._clips: dict[str, ClipRecord] | None = None

    def create(self, payload: dict[str, Any], idempotency_key: str) -> tuple[ClipRecord, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._clips is not None
            key = str(idempotency_key or "").strip()
            if not key:
                raise ValueError("Idempotency-Key is required")
            fingerprint = _fingerprint(payload)
            existing = next((item for item in self._clips.values() if item.idempotency_key == key), None)
            if existing:
                if existing.creation_fingerprint != fingerprint:
                    raise ValueError("Idempotency-Key payload does not match the original request")
                return existing, True
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            intake_id = _bounded_text(target.get("intake_id"), "target.intake_id", 200)
            knowledge_id = _bounded_text(target.get("knowledge_id"), "target.knowledge_id", 200)
            if not intake_id and not knowledge_id:
                raise ValueError("target.intake_id or target.knowledge_id is required")
            source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
            source_url = _canonical_url(source.get("url"))
            source_title = _bounded_text(source.get("title"), "source.title", 400)
            selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
            kind = _bounded_text(payload.get("kind"), "kind", 20).lower() or "clip"
            if kind not in {"clip", "highlight"}:
                raise ValueError("kind must be clip or highlight")
            selected_text = _bounded_text(selection.get("text"), "selection.text", MAX_TEXT)
            if not selected_text:
                raise ValueError("selection.text is required")
            prefix = _bounded_text(selection.get("prefix"), "selection.prefix", MAX_CONTEXT)
            suffix = _bounded_text(selection.get("suffix"), "selection.suffix", MAX_CONTEXT)
            start = _seconds(selection.get("media_start_seconds"), "selection.media_start_seconds")
            end = _seconds(selection.get("media_end_seconds"), "selection.media_end_seconds")
            if start is not None and end is not None and end < start:
                raise ValueError("selection.media_end_seconds must be greater than or equal to start")
            captured_at = _bounded_text(payload.get("captured_at"), "captured_at", 80) or _utc_now()
            record = ClipRecord(
                clip_id=f"clip1-{uuid.uuid4().hex[:20]}", client_request_id=_bounded_text(payload.get("client_request_id"), "client_request_id", 200),
                kind=kind,
                idempotency_key=key, creation_fingerprint=fingerprint, intake_id=intake_id, knowledge_id=knowledge_id,
                source_url=source_url, source_title=source_title, selected_text=selected_text, prefix=prefix, suffix=suffix,
                media_start_seconds=start, media_end_seconds=end, note=_bounded_text(payload.get("note"), "note", MAX_NOTE), captured_at=captured_at,
            )
            self._clips[record.clip_id] = record
            if len(self._clips) > MAX_CLIPS:
                oldest = sorted(self._clips.values(), key=lambda item: item.created_at)[: len(self._clips) - MAX_CLIPS]
                for item in oldest:
                    self._clips.pop(item.clip_id, None)
            self._write()
            return record, False

    def get(self, clip_id: str) -> ClipRecord | None:
        with self._lock:
            self._ensure_loaded(); assert self._clips is not None
            return self._clips.get(str(clip_id))

    def list(self, *, knowledge_id: str = "", intake_id: str = "") -> list[ClipRecord]:
        with self._lock:
            self._ensure_loaded(); assert self._clips is not None
            values = list(self._clips.values())
            if knowledge_id:
                values = [item for item in values if item.knowledge_id == knowledge_id]
            if intake_id:
                values = [item for item in values if item.intake_id == intake_id]
            return sorted(values, key=lambda item: item.created_at, reverse=True)

    def _ensure_loaded(self) -> None:
        if self._clips is not None:
            return
        values: dict[str, ClipRecord] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            for raw in payload.get("clips", []) if isinstance(payload, dict) else []:
                if isinstance(raw, dict):
                    item = ClipRecord.from_record(raw)
                    if item.clip_id:
                        values[item.clip_id] = item
        self._clips = values

    def _write(self) -> None:
        assert self._clips is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "clips": [item.to_record() for item in self._clips.values()]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def _seconds(value: object, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    if not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative number")
    return float(value)


def _fingerprint(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


__all__ = ["ClipRecord", "ClipStore", "SCHEMA_VERSION"]
