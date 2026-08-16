from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any


SCHEMA_VERSION = "1.0"
PROJECT_DIRECTORY = "projects"
PROJECT_REGISTRY = "registry.json"
MAX_PROJECTS = 200
MAX_TITLE_LENGTH = 120


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_registry_path(output_root: Path) -> Path:
    return output_root / PROJECT_DIRECTORY / PROJECT_REGISTRY


def _normalized_title(value: str) -> str:
    title = " ".join(str(value or "").split()).strip()
    if not title:
        raise ValueError("项目名称不能为空。")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"项目名称不能超过 {MAX_TITLE_LENGTH} 个字符。")
    return title


@dataclass
class ProjectGroupRecord:
    project_id: str
    title: str
    position: int
    idempotency_key: str = ""
    knowledge_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_public(self, *, valid_knowledge_ids: set[str] | None = None) -> dict[str, Any]:
        knowledge_ids = self.knowledge_ids
        if valid_knowledge_ids is not None:
            knowledge_ids = [value for value in knowledge_ids if value in valid_knowledge_ids]
        return {
            "projectId": self.project_id,
            "title": self.title,
            "position": self.position,
            "knowledgeIds": list(knowledge_ids),
            "itemCount": len(knowledge_ids),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "position": self.position,
            "idempotency_key": self.idempotency_key,
            "knowledge_ids": list(self.knowledge_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> "ProjectGroupRecord":
        raw_ids = value.get("knowledge_ids")
        knowledge_ids = []
        if isinstance(raw_ids, list):
            knowledge_ids = list(dict.fromkeys(str(item).strip() for item in raw_ids if str(item).strip()))
        return cls(
            project_id=str(value.get("project_id") or "").strip(),
            title=str(value.get("title") or "").strip(),
            position=int(value.get("position") or 0),
            idempotency_key=str(value.get("idempotency_key") or "").strip(),
            knowledge_ids=knowledge_ids,
            created_at=str(value.get("created_at") or _utc_now()),
            updated_at=str(value.get("updated_at") or value.get("created_at") or _utc_now()),
        )


class ProjectGroupStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._projects: dict[str, ProjectGroupRecord] | None = None

    def list(self) -> list[ProjectGroupRecord]:
        with self._lock:
            self._ensure_loaded()
            assert self._projects is not None
            return sorted(self._projects.values(), key=lambda value: (value.position, value.created_at, value.project_id))

    def get(self, project_id: str) -> ProjectGroupRecord | None:
        with self._lock:
            self._ensure_loaded()
            assert self._projects is not None
            return self._projects.get(str(project_id or "").strip())

    def create(self, title: str, idempotency_key: str) -> tuple[ProjectGroupRecord, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._projects is not None
            key = str(idempotency_key or "").strip()
            if not key:
                raise ValueError("缺少 Idempotency-Key。")
            existing = next((item for item in self._projects.values() if item.idempotency_key == key), None)
            if existing is not None:
                return existing, True
            if len(self._projects) >= MAX_PROJECTS:
                raise ValueError(f"项目数量不能超过 {MAX_PROJECTS} 个。")
            now = _utc_now()
            record = ProjectGroupRecord(
                project_id=f"pg-{uuid.uuid4().hex[:16]}",
                title=_normalized_title(title),
                position=max((item.position for item in self._projects.values()), default=-1) + 1,
                idempotency_key=key,
                created_at=now,
                updated_at=now,
            )
            self._projects[record.project_id] = record
            self._write()
            return record, False

    def rename(self, project_id: str, title: str) -> ProjectGroupRecord:
        with self._lock:
            record = self._require(project_id)
            next_title = _normalized_title(title)
            if record.title != next_title:
                record.title = next_title
                record.updated_at = _utc_now()
                self._write()
            return record

    def delete(self, project_id: str) -> ProjectGroupRecord:
        with self._lock:
            record = self._require(project_id)
            assert self._projects is not None
            del self._projects[record.project_id]
            self._write()
            return record

    def move_knowledge(self, project_id: str, knowledge_id: str) -> ProjectGroupRecord:
        with self._lock:
            target = self._require(project_id)
            knowledge_id = str(knowledge_id or "").strip()
            if not knowledge_id:
                raise ValueError("knowledge_id 不能为空。")
            assert self._projects is not None
            changed = False
            now = _utc_now()
            for record in self._projects.values():
                if knowledge_id not in record.knowledge_ids:
                    continue
                if record.project_id == target.project_id:
                    continue
                record.knowledge_ids = [value for value in record.knowledge_ids if value != knowledge_id]
                record.updated_at = now
                changed = True
            if knowledge_id not in target.knowledge_ids:
                target.knowledge_ids.append(knowledge_id)
                target.updated_at = now
                changed = True
            if changed:
                self._write()
            return target

    def remove_knowledge(self, project_id: str, knowledge_id: str) -> ProjectGroupRecord:
        with self._lock:
            record = self._require(project_id)
            knowledge_id = str(knowledge_id or "").strip()
            next_ids = [value for value in record.knowledge_ids if value != knowledge_id]
            if next_ids != record.knowledge_ids:
                record.knowledge_ids = next_ids
                record.updated_at = _utc_now()
                self._write()
            return record

    def memberships(self) -> dict[str, str]:
        return {
            knowledge_id: record.project_id
            for record in self.list()
            for knowledge_id in record.knowledge_ids
        }

    def _require(self, project_id: str) -> ProjectGroupRecord:
        self._ensure_loaded()
        assert self._projects is not None
        record = self._projects.get(str(project_id or "").strip())
        if record is None:
            raise KeyError(project_id)
        return record

    def _ensure_loaded(self) -> None:
        if self._projects is not None:
            return
        values: dict[str, ProjectGroupRecord] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            raw_projects = payload.get("projects", []) if isinstance(payload, dict) else []
            for raw in raw_projects:
                if not isinstance(raw, dict):
                    continue
                record = ProjectGroupRecord.from_record(raw)
                if record.project_id and record.title:
                    values[record.project_id] = record
        # Enforce the one-project invariant in memory without rewriting on read.
        seen: set[str] = set()
        for record in sorted(values.values(), key=lambda value: (value.position, value.created_at, value.project_id)):
            record.knowledge_ids = [value for value in record.knowledge_ids if value not in seen]
            seen.update(record.knowledge_ids)
        self._projects = values

    def _write(self) -> None:
        assert self._projects is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "projects": [record.to_record() for record in self.list()],
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)


__all__ = [
    "PROJECT_DIRECTORY",
    "PROJECT_REGISTRY",
    "ProjectGroupRecord",
    "ProjectGroupStore",
    "project_registry_path",
]
