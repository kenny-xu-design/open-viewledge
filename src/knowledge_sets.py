from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
MAX_SETS = 100
MAX_ITEMS_PER_SET = 200
ITEM_STATES = frozenset({"queued", "processing", "ready", "failed", "needs_attention", "duplicate", "cancelled"})
KNOWLEDGE_SET_DIRECTORY = "knowledge_sets"
KNOWLEDGE_SET_REGISTRY = "registry.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class KnowledgeSetItem:
    item_id: str
    sequence: int
    partition: str
    title: str
    source_url: str
    duration: float | None = None
    state: str = "queued"
    knowledge_id: str | None = None
    local_job_id: str = ""
    action_idempotency_key: str = ""
    last_error: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "sequence": self.sequence,
            "partition": self.partition,
            "title": self.title,
            "sourceUrl": self.source_url,
            "duration": self.duration,
            "state": self.state,
            "knowledgeId": self.knowledge_id,
            "attention": {
                "message": self.last_error,
                "retryable": self.state in {"failed", "needs_attention"},
            },
        }


@dataclass
class KnowledgeSetRecord:
    set_id: str
    title: str
    source_url: str
    kind: str
    uploader: str
    idempotency_key: str
    analysis_profile: str = "tutorial"
    processing_profile: str = "complete"
    transcript_group_seconds: int = 30
    items: list[KnowledgeSetItem] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_public(self) -> dict[str, Any]:
        return {
            "setId": self.set_id,
            "title": self.title,
            "sourceUrl": self.source_url,
            "kind": self.kind,
            "uploader": self.uploader,
            "analysisProfile": self.analysis_profile,
            "processingProfile": self.processing_profile,
            "transcriptGroupSeconds": self.transcript_group_seconds,
            "itemCount": len(self.items),
            "items": [item.to_public() for item in sorted(self.items, key=lambda value: value.sequence)],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> "KnowledgeSetRecord":
        items = []
        for raw in value.get("items", []) if isinstance(value.get("items"), list) else []:
            if not isinstance(raw, dict):
                continue
            item = KnowledgeSetItem(
                item_id=str(raw.get("item_id") or ""),
                sequence=int(raw.get("sequence") or 0),
                partition=str(raw.get("partition") or "系列教程"),
                title=str(raw.get("title") or "未命名视频"),
                source_url=str(raw.get("source_url") or ""),
                duration=float(raw["duration"]) if isinstance(raw.get("duration"), (int, float)) else None,
                state=str(raw.get("state") or "queued"),
                knowledge_id=str(raw.get("knowledge_id")) if raw.get("knowledge_id") else None,
                local_job_id=str(raw.get("local_job_id") or ""),
                action_idempotency_key=str(raw.get("action_idempotency_key") or ""),
                last_error=str(raw.get("last_error") or ""),
            )
            if item.item_id and item.state in ITEM_STATES:
                items.append(item)
        return cls(
            set_id=str(value.get("set_id") or ""),
            title=str(value.get("title") or "B站知识集"),
            source_url=str(value.get("source_url") or ""),
            kind=str(value.get("kind") or "bilibili_parts"),
            uploader=str(value.get("uploader") or ""),
            idempotency_key=str(value.get("idempotency_key") or ""),
            analysis_profile=str(value.get("analysis_profile") or "tutorial"),
            processing_profile=str(value.get("processing_profile") or "complete"),
            transcript_group_seconds=int(value.get("transcript_group_seconds") or 30),
            items=items,
            created_at=str(value.get("created_at") or _utc_now()),
            updated_at=str(value.get("updated_at") or value.get("created_at") or _utc_now()),
        )


class KnowledgeSetStore:
    def __init__(self, path: Path, *, legacy_paths: tuple[Path, ...] = ()) -> None:
        self.path = path
        primary = path.resolve()
        self.legacy_paths = tuple(
            candidate
            for candidate in dict.fromkeys(legacy_paths)
            if candidate.resolve() != primary
        )
        self._lock = threading.RLock()
        self._sets: dict[str, KnowledgeSetRecord] | None = None

    def create(self, inspection: dict[str, Any], idempotency_key: str, *, analysis_profile: str = "tutorial", processing_profile: str = "complete", transcript_group_seconds: int = 30) -> tuple[KnowledgeSetRecord, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._sets is not None
            key = str(idempotency_key or "").strip()
            if not key:
                raise ValueError("缺少 Idempotency-Key。")
            analysis_profile = str(analysis_profile or "tutorial").strip()
            processing_profile = str(processing_profile or "complete").strip()
            transcript_group_seconds = int(transcript_group_seconds)
            if analysis_profile not in {"summary", "tutorial", "viral", "close-reading"}:
                raise ValueError("analysisProfile is not supported")
            if processing_profile not in {"fast", "complete"}:
                raise ValueError("processingProfile is not supported")
            if not 15 <= transcript_group_seconds <= 300:
                raise ValueError("transcriptGroupSeconds must be between 15 and 300")
            existing = next((value for value in self._sets.values() if value.idempotency_key == key), None)
            if existing:
                return existing, True
            kind = str(inspection.get("kind") or "")
            raw_items = inspection.get("items")
            if kind not in {"bilibili_parts", "bilibili_series"} or not isinstance(raw_items, list) or len(raw_items) < 2:
                raise ValueError("当前来源不是可建立知识集的 B站分批教程。")
            items: list[KnowledgeSetItem] = []
            for index, raw in enumerate(raw_items[:MAX_ITEMS_PER_SET], start=1):
                if not isinstance(raw, dict) or not str(raw.get("sourceUrl") or "").strip():
                    continue
                items.append(
                    KnowledgeSetItem(
                        item_id=f"item_{index:03d}",
                        sequence=int(raw.get("sequence") or index),
                        partition=str(raw.get("partition") or "系列教程"),
                        title=str(raw.get("title") or f"第 {index} 集"),
                        source_url=str(raw.get("sourceUrl")),
                        duration=float(raw["duration"]) if isinstance(raw.get("duration"), (int, float)) else None,
                    )
                )
            if len(items) < 2:
                raise ValueError("B站分批条目不足，无法建立知识集。")
            now = _utc_now()
            record = KnowledgeSetRecord(
                set_id=f"ks1-{uuid.uuid4().hex[:20]}",
                title=str(inspection.get("title") or "B站知识集"),
                source_url=str(inspection.get("sourceUrl") or ""),
                kind=kind,
                uploader=str(inspection.get("uploader") or ""),
                idempotency_key=key,
                analysis_profile=analysis_profile,
                processing_profile=processing_profile,
                transcript_group_seconds=transcript_group_seconds,
                items=items,
                created_at=now,
                updated_at=now,
            )
            self._sets[record.set_id] = record
            ordered = sorted(self._sets.values(), key=lambda value: value.created_at, reverse=True)[:MAX_SETS]
            self._sets = {value.set_id: value for value in ordered}
            self._write()
            return record, False

    def get(self, set_id: str) -> KnowledgeSetRecord | None:
        with self._lock:
            self._ensure_loaded()
            assert self._sets is not None
            return self._sets.get(set_id)

    def list(self) -> list[KnowledgeSetRecord]:
        with self._lock:
            self._ensure_loaded()
            assert self._sets is not None
            return sorted(self._sets.values(), key=lambda value: value.created_at, reverse=True)

    def begin_item_action(self, set_id: str, item_id: str, idempotency_key: str) -> tuple[KnowledgeSetRecord, KnowledgeSetItem, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._sets is not None
            record = self._sets.get(set_id)
            if record is None:
                raise KeyError(set_id)
            item = next((value for value in record.items if value.item_id == item_id), None)
            if item is None:
                raise KeyError(item_id)
            key = str(idempotency_key or "").strip()
            if not key:
                raise ValueError("缺少 Idempotency-Key。")
            if item.action_idempotency_key:
                if item.action_idempotency_key != key:
                    if item.state not in {"failed", "needs_attention"}:
                        raise ValueError("该知识集条目已有进行中的操作。")
                else:
                    return record, item, True
            if item.state not in {"queued", "failed", "needs_attention"}:
                raise ValueError("当前知识集条目不可开始分析。")
            item.action_idempotency_key = key
            item.state = "processing"
            item.last_error = ""
            record.updated_at = _utc_now()
            self._write()
            return record, item, False

    def attach_job(self, set_id: str, item_id: str, local_job_id: str, knowledge_id: str = "") -> KnowledgeSetRecord:
        with self._lock:
            record, item = self._find(set_id, item_id)
            item.local_job_id = local_job_id
            if knowledge_id:
                item.knowledge_id = knowledge_id
            item.state = "processing"
            record.updated_at = _utc_now()
            self._write()
            return record

    def fail_item(self, set_id: str, item_id: str, message: str) -> KnowledgeSetRecord:
        with self._lock:
            record, item = self._find(set_id, item_id)
            item.state = "needs_attention"
            item.last_error = str(message)[:500]
            record.updated_at = _utc_now()
            self._write()
            return record

    def mark_duplicate(self, set_id: str, item_id: str, message: str) -> KnowledgeSetRecord:
        with self._lock:
            record, item = self._find(set_id, item_id)
            item.state = "duplicate"
            item.last_error = str(message)[:500]
            record.updated_at = _utc_now()
            self._write()
            return record

    def reconcile_item(self, set_id: str, item_id: str, *, state: str, knowledge_id: str = "", error: str = "") -> KnowledgeSetRecord | None:
        return self.reconcile_items(
            set_id,
            [{"item_id": item_id, "state": state, "knowledge_id": knowledge_id, "error": error}],
        )

    def reconcile_items(self, set_id: str, updates: list[dict[str, str]]) -> KnowledgeSetRecord | None:
        with self._lock:
            self._ensure_loaded()
            assert self._sets is not None
            record = self._sets.get(set_id)
            if record is None:
                return None
            items_by_id = {item.item_id: item for item in record.items}
            changed = False
            for update in updates:
                item = items_by_id.get(str(update.get("item_id") or ""))
                state = str(update.get("state") or "")
                if item is None or state not in {"processing", "ready", "failed", "needs_attention"}:
                    continue
                knowledge_id = str(update.get("knowledge_id") or "")
                error = str(update.get("error") or "")[:500]
                next_knowledge_id = knowledge_id or item.knowledge_id
                if item.state == state and item.knowledge_id == next_knowledge_id and item.last_error == error:
                    continue
                item.state = state
                item.knowledge_id = next_knowledge_id
                item.last_error = error
                changed = True
            if changed:
                record.updated_at = _utc_now()
                self._write()
            return record

    def _find(self, set_id: str, item_id: str) -> tuple[KnowledgeSetRecord, KnowledgeSetItem]:
        self._ensure_loaded()
        assert self._sets is not None
        record = self._sets.get(set_id)
        if record is None:
            raise KeyError(set_id)
        item = next((value for value in record.items if value.item_id == item_id), None)
        if item is None:
            raise KeyError(item_id)
        return record, item

    def _ensure_loaded(self) -> None:
        if self._sets is not None:
            return
        values = self._read(self.path)
        migrated = False
        for legacy_path in self.legacy_paths:
            for set_id, record in self._read(legacy_path).items():
                current = values.get(set_id)
                if current is None or record.updated_at > current.updated_at:
                    values[set_id] = record
                    migrated = True
        ordered = sorted(values.values(), key=lambda value: value.created_at, reverse=True)[:MAX_SETS]
        self._sets = {value.set_id: value for value in ordered}
        if migrated:
            self._write()

    @staticmethod
    def _read(path: Path) -> dict[str, KnowledgeSetRecord]:
        values: dict[str, KnowledgeSetRecord] = {}
        if not path.exists():
            return values
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return values
        for raw in payload.get("sets", []) if isinstance(payload, dict) else []:
            if isinstance(raw, dict):
                record = KnowledgeSetRecord.from_record(raw)
                if record.set_id:
                    values[record.set_id] = record
        return values

    def _write(self) -> None:
        assert self._sets is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA_VERSION, "sets": [asdict(value) for value in self._sets.values()]}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def knowledge_set_registry_path(output_root: Path) -> Path:
    return output_root / KNOWLEDGE_SET_DIRECTORY / KNOWLEDGE_SET_REGISTRY


__all__ = [
    "KNOWLEDGE_SET_DIRECTORY",
    "KNOWLEDGE_SET_REGISTRY",
    "KnowledgeSetItem",
    "KnowledgeSetRecord",
    "KnowledgeSetStore",
    "knowledge_set_registry_path",
]
