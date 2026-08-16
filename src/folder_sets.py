from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
MAX_DEPTH = 2  # root + two nested levels = three levels total
MAX_SETS = 500
MAX_ITEMS_PER_SET = 500
VIDEO_EXTENSIONS = frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".mts", ".m2ts"})
SUPPORTED_ANALYSIS_PROFILES = frozenset({"summary", "tutorial", "viral", "close-reading"})
SUPPORTED_PROCESSING_PROFILES = frozenset({"fast", "complete"})


def normalize_local_path(value: str) -> str:
    """Normalize a user-entered local path without changing its target."""
    cleaned = str(value or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_title(value: str, fallback: str) -> str:
    value = " ".join(str(value or "").strip().split())
    return value[:160] or fallback


@dataclass
class FolderSetItem:
    item_id: str
    sequence: int
    title: str
    relative_path: str
    source_path: str
    extension: str
    size: int
    state: str = "queued"
    knowledge_id: str = ""
    local_job_id: str = ""
    action_idempotency_key: str = ""
    last_error: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "sequence": self.sequence,
            "title": self.title,
            "relativePath": self.relative_path,
            "extension": self.extension,
            "size": self.size,
            "state": self.state,
            "knowledgeId": self.knowledge_id or None,
            "draggable": False,
            "attention": {"message": self.last_error, "retryable": self.state in {"failed", "needs_attention"}},
        }


@dataclass
class FolderSetRecord:
    set_id: str
    title: str
    relative_path: str
    source_path: str
    parent_set_id: str
    depth: int
    position: int
    idempotency_key: str
    analysis_profile: str = "tutorial"
    processing_profile: str = "complete"
    transcript_group_seconds: int = 30
    items: list[FolderSetItem] = field(default_factory=list)
    child_set_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_public(self) -> dict[str, Any]:
        return {
            "setId": self.set_id,
            "title": self.title,
            "relativePath": self.relative_path,
            "parentSetId": self.parent_set_id or None,
            "depth": self.depth,
            "position": self.position,
            "kind": "local_folder",
            "analysisProfile": self.analysis_profile,
            "processingProfile": self.processing_profile,
            "transcriptGroupSeconds": self.transcript_group_seconds,
            "itemCount": len(self.items),
            "items": [item.to_public() for item in sorted(self.items, key=lambda value: value.sequence)],
            "childSetIds": list(self.child_set_ids),
            "draggable": self.depth > 0,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> "FolderSetRecord":
        items: list[FolderSetItem] = []
        for value in raw.get("items", []) if isinstance(raw.get("items"), list) else []:
            if not isinstance(value, dict):
                continue
            item = FolderSetItem(
                item_id=str(value.get("item_id") or ""), sequence=int(value.get("sequence") or 0),
                title=str(value.get("title") or "未命名视频"), relative_path=str(value.get("relative_path") or ""),
                source_path=str(value.get("source_path") or ""), extension=str(value.get("extension") or ""),
                size=int(value.get("size") or 0), state=str(value.get("state") or "queued"),
                knowledge_id=str(value.get("knowledge_id") or ""), local_job_id=str(value.get("local_job_id") or ""),
                action_idempotency_key=str(value.get("action_idempotency_key") or ""), last_error=str(value.get("last_error") or ""),
            )
            if item.item_id:
                items.append(item)
        return cls(
            set_id=str(raw.get("set_id") or ""), title=str(raw.get("title") or "未命名文件夹"),
            relative_path=str(raw.get("relative_path") or ""), source_path=str(raw.get("source_path") or ""),
            parent_set_id=str(raw.get("parent_set_id") or ""), depth=min(max(int(raw.get("depth") or 0), 0), MAX_DEPTH),
            position=int(raw.get("position") or 0), idempotency_key=str(raw.get("idempotency_key") or ""),
            analysis_profile=str(raw.get("analysis_profile") or "tutorial"),
            processing_profile=str(raw.get("processing_profile") or "complete"),
            transcript_group_seconds=int(raw.get("transcript_group_seconds") or 30),
            items=items, child_set_ids=[str(x) for x in raw.get("child_set_ids", []) if str(x)],
            created_at=str(raw.get("created_at") or _utc_now()), updated_at=str(raw.get("updated_at") or raw.get("created_at") or _utc_now()),
        )


def inspect_folder(path_value: str) -> dict[str, Any]:
    normalized = normalize_local_path(path_value)
    if not normalized:
        raise ValueError("本地文件夹路径不能为空")
    root = Path(normalized).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("本地文件夹不存在或不是文件夹")
    folders: list[dict[str, Any]] = []

    def walk(folder: Path, depth: int, relative: str) -> None:
        files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS), key=lambda p: p.name.casefold())
        children = sorted((p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.name.casefold()) if depth < MAX_DEPTH else []
        folders.append({
            "title": folder.name or root.name or "本地视频集", "relativePath": relative, "depth": depth,
            "videoCount": len(files), "childCount": len(children),
            "items": [{"title": p.stem, "relativePath": str(p.relative_to(root)), "extension": p.suffix.lower(), "size": p.stat().st_size} for p in files],
        })
        for child in children:
            walk(child, depth + 1, str(child.relative_to(root)))

    walk(root, 0, "")
    return {"kind": "local_folder", "isCollection": True, "title": root.name or "本地视频集", "folderCount": len(folders), "videoCount": sum(int(x["videoCount"]) for x in folders), "folders": folders}


class FolderSetStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._sets: dict[str, FolderSetRecord] | None = None

    def create(
        self,
        source_path: str,
        title: str,
        idempotency_key: str,
        *,
        analysis_profile: str = "tutorial",
        processing_profile: str = "complete",
        transcript_group_seconds: int = 30,
    ) -> tuple[FolderSetRecord, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._sets is not None
            key = str(idempotency_key or "").strip()
            if not key:
                raise ValueError("缺少 Idempotency-Key")
            analysis_profile = str(analysis_profile or "tutorial").strip()
            processing_profile = str(processing_profile or "complete").strip()
            try:
                transcript_group_seconds = int(transcript_group_seconds)
            except (TypeError, ValueError) as exc:
                raise ValueError("transcriptGroupSeconds must be an integer") from exc
            if analysis_profile not in SUPPORTED_ANALYSIS_PROFILES:
                raise ValueError("analysisProfile is not supported")
            if processing_profile not in SUPPORTED_PROCESSING_PROFILES:
                raise ValueError("processingProfile is not supported")
            if not 15 <= transcript_group_seconds <= 300:
                raise ValueError("transcriptGroupSeconds must be between 15 and 300")
            existing = next((x for x in self._sets.values() if x.idempotency_key == key), None)
            if existing:
                return existing, True
            normalized = normalize_local_path(source_path)
            if not normalized:
                raise ValueError("本地文件夹路径不能为空")
            root = Path(normalized).expanduser().resolve()
            inspection = inspect_folder(str(root))
            created: list[FolderSetRecord] = []
            by_relative: dict[str, FolderSetRecord] = {}
            for folder in inspection["folders"]:
                rel = str(folder["relativePath"])
                parent_rel = str(Path(rel).parent) if rel else ""
                if parent_rel == ".":
                    parent_rel = ""
                parent = by_relative.get(parent_rel)
                depth = int(folder["depth"])
                record = FolderSetRecord(
                    set_id=f"fs1-{uuid.uuid4().hex[:20]}", title=_safe_title(folder["title"], "本地视频集"),
                    relative_path=rel, source_path=str(root / rel), parent_set_id=parent.set_id if parent else "",
                    depth=depth, position=len(parent.child_set_ids) if parent else len([x for x in created if not x.parent_set_id]),
                    idempotency_key=key if not created else f"{key}:{rel}",
                    analysis_profile=analysis_profile,
                    processing_profile=processing_profile,
                    transcript_group_seconds=transcript_group_seconds,
                )
                for index, raw in enumerate(folder.get("items", [])[:MAX_ITEMS_PER_SET], start=1):
                    item_path = root / str(raw["relativePath"])
                    record.items.append(FolderSetItem(
                        item_id=f"item_{index:03d}", sequence=index, title=_safe_title(raw.get("title"), f"第 {index} 个视频"),
                        relative_path=str(raw["relativePath"]), source_path=str(item_path), extension=str(raw.get("extension") or item_path.suffix.lower()), size=int(raw.get("size") or 0),
                    ))
                self._sets[record.set_id] = record
                created.append(record)
                by_relative[rel] = record
                if parent:
                    parent.child_set_ids.append(record.set_id)
            if not created:
                raise ValueError("文件夹中没有可分析的视频文件")
            self._write()
            return created[0], False

    def list(self) -> list[FolderSetRecord]:
        with self._lock:
            self._ensure_loaded(); assert self._sets is not None
            return sorted(self._sets.values(), key=lambda x: (x.depth, x.position, x.created_at))

    def get(self, set_id: str) -> FolderSetRecord | None:
        with self._lock:
            self._ensure_loaded(); assert self._sets is not None
            return self._sets.get(set_id)

    def descendants(self, set_id: str, *, include_self: bool = False) -> list[FolderSetRecord]:
        """Return a folder-set subtree in persisted child order."""
        with self._lock:
            self._ensure_loaded(); assert self._sets is not None
            root = self._sets.get(set_id)
            if root is None:
                raise KeyError(set_id)
            result: list[FolderSetRecord] = []

            def visit(record: FolderSetRecord) -> None:
                if include_self or record.set_id != root.set_id:
                    result.append(record)
                for child_id in record.child_set_ids:
                    child = self._sets.get(child_id)
                    if child is not None:
                        visit(child)

            visit(root)
            return result

    def begin_item_action(self, set_id: str, item_id: str, key: str) -> tuple[FolderSetRecord, FolderSetItem, bool]:
        with self._lock:
            record, item = self._find(set_id, item_id)
            key = str(key or "").strip()
            if not key: raise ValueError("缺少 Idempotency-Key")
            if item.action_idempotency_key == key: return record, item, True
            if item.action_idempotency_key and item.state not in {"failed", "needs_attention"}: raise ValueError("该视频已有进行中的任务")
            if item.state not in {"queued", "failed", "needs_attention"}: raise ValueError("当前视频不可开始分析")
            item.action_idempotency_key, item.state, item.last_error = key, "processing", ""
            record.updated_at = _utc_now(); self._write(); return record, item, False

    def attach_job(self, set_id: str, item_id: str, job_id: str, knowledge_id: str = "") -> None:
        with self._lock:
            record, item = self._find(set_id, item_id); item.local_job_id = job_id; item.knowledge_id = knowledge_id or item.knowledge_id; record.updated_at = _utc_now(); self._write()

    def reconcile_item(self, set_id: str, item_id: str, state: str, knowledge_id: str = "", error: str = "") -> None:
        self.reconcile_items(
            set_id,
            [{"item_id": item_id, "state": state, "knowledge_id": knowledge_id, "error": error}],
        )

    def reconcile_items(self, set_id: str, updates: list[dict[str, str]]) -> FolderSetRecord | None:
        with self._lock:
            self._ensure_loaded(); assert self._sets is not None
            record = self._sets.get(set_id)
            if record is None: return None
            items_by_id = {item.item_id: item for item in record.items}
            changed = False
            for update in updates:
                item = items_by_id.get(str(update.get("item_id") or ""))
                state = str(update.get("state") or "")
                if item is None or state not in {"processing", "ready", "failed", "needs_attention"}: continue
                knowledge_id = str(update.get("knowledge_id") or "")
                error = str(update.get("error") or "")[:500]
                next_knowledge_id = knowledge_id or item.knowledge_id
                if item.state == state and item.knowledge_id == next_knowledge_id and item.last_error == error: continue
                item.state, item.knowledge_id, item.last_error = state, next_knowledge_id, error
                changed = True
            if changed:
                record.updated_at = _utc_now(); self._write()
            return record

    def reorder_children(self, set_id: str, child_ids: list[str]) -> FolderSetRecord:
        with self._lock:
            parent = self._sets.get(set_id) if self._sets is not None else None
            if parent is None: raise KeyError(set_id)
            if set(child_ids) != set(parent.child_set_ids) or len(child_ids) != len(parent.child_set_ids): raise ValueError("只能排序当前文件夹的直接子文件夹")
            parent.child_set_ids = list(child_ids)
            for index, child_id in enumerate(child_ids): self._sets[child_id].position = index
            parent.updated_at = _utc_now(); self._write(); return parent

    def create_child(self, parent_id: str, title: str) -> FolderSetRecord:
        with self._lock:
            parent = self._sets.get(parent_id) if self._sets is not None else None
            if parent is None: raise KeyError(parent_id)
            if parent.depth >= MAX_DEPTH: raise ValueError("知识集最多支持三层文件夹")
            record = FolderSetRecord(set_id=f"fs1-{uuid.uuid4().hex[:20]}", title=_safe_title(title, "新建文件夹"), relative_path="", source_path=parent.source_path, parent_set_id=parent.set_id, depth=parent.depth + 1, position=len(parent.child_set_ids), idempotency_key=f"manual:{uuid.uuid4().hex}")
            record.analysis_profile = parent.analysis_profile
            record.processing_profile = parent.processing_profile
            record.transcript_group_seconds = parent.transcript_group_seconds
            self._sets[record.set_id] = record; parent.child_set_ids.append(record.set_id); self._write(); return record

    def create_parent(self, set_id: str, title: str) -> FolderSetRecord:
        with self._lock:
            self._ensure_loaded(); assert self._sets is not None
            current = self._sets.get(set_id)
            if current is None: raise KeyError(set_id)
            if current.depth >= MAX_DEPTH: raise ValueError("当前文件夹无法再创建上层文件夹")
            if current.depth == 0:
                descendants = [x for x in self._sets.values() if x.set_id != current.set_id and (x.depth >= 1)]
                if any(x.depth >= MAX_DEPTH for x in descendants): raise ValueError("当前树已达到三层，无法插入上层文件夹")
                parent = FolderSetRecord(set_id=f"fs1-{uuid.uuid4().hex[:20]}", title=_safe_title(title, "上层文件夹"), relative_path="", source_path=current.source_path, parent_set_id="", depth=0, position=current.position, idempotency_key=f"manual-parent:{uuid.uuid4().hex}")
                parent.analysis_profile = current.analysis_profile
                parent.processing_profile = current.processing_profile
                parent.transcript_group_seconds = current.transcript_group_seconds
                for sibling in self._sets.values():
                    if not sibling.parent_set_id and sibling.position >= current.position: sibling.position += 1
                current.parent_set_id = parent.set_id; current.depth = 1
                for child in self._sets.values():
                    if child.parent_set_id == current.set_id: child.depth += 1
                parent.child_set_ids.append(current.set_id); self._sets[parent.set_id] = parent; self._write(); return parent
            if current.child_set_ids: raise ValueError("请先移动或收起子文件夹后再创建上层文件夹")
            old_parent = self._sets.get(current.parent_set_id) if current.parent_set_id else None
            parent = FolderSetRecord(set_id=f"fs1-{uuid.uuid4().hex[:20]}", title=_safe_title(title, "上层文件夹"), relative_path="", source_path=current.source_path, parent_set_id=old_parent.set_id if old_parent else "", depth=current.depth, position=current.position, idempotency_key=f"manual-parent:{uuid.uuid4().hex}")
            parent.analysis_profile = current.analysis_profile
            parent.processing_profile = current.processing_profile
            parent.transcript_group_seconds = current.transcript_group_seconds
            if old_parent:
                index = old_parent.child_set_ids.index(current.set_id)
                old_parent.child_set_ids[index] = parent.set_id
            current.parent_set_id = parent.set_id
            current.depth += 1
            self._sets[parent.set_id] = parent
            self._sets[current.set_id] = current
            self._write(); return parent

    def _find(self, set_id: str, item_id: str) -> tuple[FolderSetRecord, FolderSetItem]:
        self._ensure_loaded(); assert self._sets is not None
        record = self._sets.get(set_id)
        if record is None: raise KeyError(set_id)
        item = next((x for x in record.items if x.item_id == item_id), None)
        if item is None: raise KeyError(item_id)
        return record, item

    def _ensure_loaded(self) -> None:
        if self._sets is not None: return
        values: dict[str, FolderSetRecord] = {}
        if self.path.exists():
            try: payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): payload = {}
            for raw in payload.get("sets", []) if isinstance(payload, dict) else []:
                if isinstance(raw, dict):
                    record = FolderSetRecord.from_record(raw)
                    if record.set_id: values[record.set_id] = record
        self._sets = values

    def _write(self) -> None:
        assert self._sets is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "sets": [asdict(x) for x in self._sets.values()]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


__all__ = ["FolderSetItem", "FolderSetRecord", "FolderSetStore", "VIDEO_EXTENSIONS", "inspect_folder", "MAX_DEPTH", "normalize_local_path"]
