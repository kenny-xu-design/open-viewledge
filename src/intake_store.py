from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .domain.models import SourceRecord
from .knowledge_identity import (
    DuplicateDecision,
    KnowledgeIdentity,
    KnowledgeRequestDimensions,
    TaskIdentityRecord,
    build_input_knowledge_identity,
    build_knowledge_identity,
    detect_duplicate,
    normalize_source_url,
)


SCHEMA_VERSION = "1.0"
SUPPORTED_STATES = frozenset(
    {"queued", "processing", "needs_attention", "ready", "failed", "duplicate", "cancelled"}
)
MAX_ITEMS = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: object, *, field_name: str, max_length: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是字符串。")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"{field_name} 不能超过 {max_length} 个字符。")
    return value


@dataclass
class IntakeRecord:
    intake_id: str
    client_request_id: str
    idempotency_key: str
    source_kind: str
    source_url: str
    canonical_url: str
    creation_fingerprint: str = ""
    title: str = ""
    selected_text: str = ""
    visible_text: str = ""
    content_sha256: str = ""
    capture_scope: str = ""
    capture_ref: str = ""
    captured_at: str = field(default_factory=_utc_now)
    user_initiated: bool = True
    content_upload_allowed: bool = False
    analysis_profile: str = "summary"
    processing_profile: str = "fast"
    output_languages: list[str] = field(default_factory=lambda: ["source"])
    knowledge_id: str | None = None
    source_fingerprint: str = ""
    request_fingerprint: str = ""
    state: str = "queued"
    duplicate_kind: str = "none"
    duplicate_knowledge_id: str | None = None
    duplicate_allowed_actions: list[str] = field(default_factory=list)
    local_job_id: str = ""
    action_idempotency_key: str = ""
    action_name: str = ""
    last_error: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_record(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("selected_text", None)
        value.pop("visible_text", None)
        return value

    def to_public(self) -> dict[str, Any]:
        return {
            "intake_id": self.intake_id,
            "knowledge_id": self.knowledge_id,
            "state": self.state,
            "source": {
                "kind": self.source_kind,
                "url": self.source_url,
                "canonical_url": self.canonical_url,
                "title": self.title,
            },
            "capture": {
                "captured_at": self.captured_at,
                "user_initiated": self.user_initiated,
                "scope": self.capture_scope,
            },
            "preferences": {
                "analysis_profile": self.analysis_profile,
                "processing_profile": self.processing_profile,
                "output_languages": list(self.output_languages),
            },
            "duplicate": {
                "detected": self.state == "duplicate" or self.duplicate_kind != "none",
                "knowledge_id": self.duplicate_knowledge_id,
                "allowed_actions": list(self.duplicate_allowed_actions),
            },
            "attention": {
                "message": self.last_error,
                "retryable": self.state in {"failed", "needs_attention"},
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> "IntakeRecord":
        return cls(
            intake_id=str(value.get("intake_id") or ""),
            client_request_id=str(value.get("client_request_id") or ""),
            idempotency_key=str(value.get("idempotency_key") or ""),
            creation_fingerprint=str(value.get("creation_fingerprint") or ""),
            source_kind=str(value.get("source_kind") or "video"),
            source_url=str(value.get("source_url") or ""),
            canonical_url=str(value.get("canonical_url") or ""),
            title=str(value.get("title") or ""),
            selected_text=str(value.get("selected_text") or ""),
            visible_text=str(value.get("visible_text") or ""),
            content_sha256=str(value.get("content_sha256") or ""),
            capture_scope=str(value.get("capture_scope") or ""),
            capture_ref=str(value.get("capture_ref") or ""),
            captured_at=str(value.get("captured_at") or _utc_now()),
            user_initiated=bool(value.get("user_initiated", True)),
            content_upload_allowed=bool(value.get("content_upload_allowed", False)),
            analysis_profile=str(value.get("analysis_profile") or "summary"),
            processing_profile=str(value.get("processing_profile") or "fast"),
            output_languages=[str(item) for item in value.get("output_languages", ["source"]) if isinstance(item, str)] or ["source"],
            knowledge_id=str(value.get("knowledge_id")) if value.get("knowledge_id") else None,
            source_fingerprint=str(value.get("source_fingerprint") or ""),
            request_fingerprint=str(value.get("request_fingerprint") or ""),
            state=str(value.get("state") or "failed"),
            duplicate_kind=str(value.get("duplicate_kind") or "none"),
            duplicate_knowledge_id=str(value.get("duplicate_knowledge_id")) if value.get("duplicate_knowledge_id") else None,
            duplicate_allowed_actions=[str(item) for item in value.get("duplicate_allowed_actions", []) if isinstance(item, str)],
            local_job_id=str(value.get("local_job_id") or ""),
            action_idempotency_key=str(value.get("action_idempotency_key") or ""),
            action_name=str(value.get("action_name") or ""),
            last_error=str(value.get("last_error") or ""),
            created_at=str(value.get("created_at") or _utc_now()),
            updated_at=str(value.get("updated_at") or value.get("created_at") or _utc_now()),
        )


class IntakeStore:
    """Durable local Bridge intake registry.

    Captured page text is private local state. Public responses intentionally
    expose only source metadata, consent-safe capture metadata, and inbox state.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._items: dict[str, IntakeRecord] | None = None

    def create(self, payload: dict[str, Any], idempotency_key: str) -> tuple[IntakeRecord, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            idem = _text(idempotency_key, field_name="Idempotency-Key", max_length=200)
            if not idem:
                raise ValueError("缺少 Idempotency-Key。")
            creation_fingerprint = _payload_fingerprint(payload)
            existing = next((item for item in self._items.values() if item.idempotency_key == idem), None)
            if existing:
                if existing.client_request_id != str(payload.get("client_request_id") or ""):
                    raise ValueError("Idempotency-Key 已用于其他请求。")
                if existing.creation_fingerprint and existing.creation_fingerprint != creation_fingerprint:
                    raise ValueError("Idempotency-Key 的请求内容与首次创建不一致。")
                return existing, True

            item = self._build_item(payload, idem, creation_fingerprint)
            item.capture_ref = f"{item.intake_id}.json" if (item.selected_text or item.visible_text) else ""
            if item.capture_ref:
                self._write_capture(item)
            self._items[item.intake_id] = item
            ordered = sorted(self._items.values(), key=lambda value: value.created_at, reverse=True)[:MAX_ITEMS]
            retained_ids = {value.intake_id for value in ordered}
            evicted = [value for value in self._items.values() if value.intake_id not in retained_ids]
            self._items = {value.intake_id: value for value in ordered}
            self._write()
            for value in evicted:
                self._remove_capture(value)
            return item, False

    def get(self, intake_id: str) -> IntakeRecord | None:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            return self._items.get(intake_id)

    def begin_action(self, intake_id: str, action: str, idempotency_key: str) -> tuple[IntakeRecord, bool]:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            item = self._items.get(intake_id)
            if item is None:
                raise KeyError(intake_id)
            key = _text(idempotency_key, field_name="Idempotency-Key", max_length=200)
            if not key:
                raise ValueError("缺少 Idempotency-Key。")
            if item.action_idempotency_key:
                if item.action_idempotency_key != key:
                    if item.state not in {"failed", "needs_attention"} or action != "retry":
                        raise ValueError("该 Intake 已有进行中的操作。")
                if item.action_name != action:
                    if action != "retry" or item.state not in {"failed", "needs_attention"}:
                        raise ValueError("Idempotency-Key 已用于其他操作。")
                if item.action_idempotency_key == key:
                    return item, True
            if action == "start" and item.state != "queued":
                raise ValueError("当前 Intake 不是可启动的 queued 状态。")
            if action == "retry" and item.state not in {"failed", "needs_attention"}:
                raise ValueError("当前 Intake 不是可重试的失败状态。")
            if action == "cancel" and item.state not in {"queued", "needs_attention"}:
                raise ValueError("当前 Intake 不能取消。")
            if item.state == "duplicate":
                raise ValueError("duplicate_intake")
            item.action_idempotency_key = key
            item.action_name = action
            item.state = "cancelled" if action == "cancel" else "processing"
            item.last_error = ""
            item.updated_at = _utc_now()
            self._write()
            return item, False

    def attach_job(self, intake_id: str, local_job_id: str, knowledge_id: str = "") -> IntakeRecord:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            item = self._items.get(intake_id)
            if item is None:
                raise KeyError(intake_id)
            item.local_job_id = local_job_id
            if knowledge_id:
                item.knowledge_id = knowledge_id
            item.state = "processing"
            item.updated_at = _utc_now()
            self._write()
            return item

    def fail_action(self, intake_id: str, message: str) -> IntakeRecord:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            item = self._items.get(intake_id)
            if item is None:
                raise KeyError(intake_id)
            item.state = "needs_attention"
            item.last_error = _text(message, field_name="error", max_length=500)
            item.updated_at = _utc_now()
            self._write()
            return item

    def mark_duplicate(self, intake_id: str, *, kind: str, knowledge_id: str, actions: list[str]) -> IntakeRecord:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            item = self._items.get(intake_id)
            if item is None:
                raise KeyError(intake_id)
            item.state = "duplicate"
            item.duplicate_kind = kind
            item.duplicate_knowledge_id = knowledge_id or None
            item.duplicate_allowed_actions = list(actions)
            item.updated_at = _utc_now()
            self._write()
            return item

    def reconcile_job(self, intake_id: str, *, state: str, knowledge_id: str = "", error: str = "") -> IntakeRecord | None:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            item = self._items.get(intake_id)
            if item is None:
                return None
            if state not in {"processing", "ready", "failed"}:
                return item
            item.state = state
            if knowledge_id:
                item.knowledge_id = knowledge_id
            item.last_error = _text(error, field_name="error", max_length=500) if error else ""
            item.updated_at = _utc_now()
            self._write()
            return item

    def list_inbox(self, cursor: str = "", limit: int = 50) -> tuple[list[IntakeRecord], str | None]:
        with self._lock:
            self._ensure_loaded()
            assert self._items is not None
            try:
                bounded_limit = max(1, min(int(limit), 100))
            except (TypeError, ValueError) as exc:
                raise ValueError("limit 必须是 1 到 100 之间的整数。") from exc
            items = sorted(self._items.values(), key=lambda value: (value.created_at, value.intake_id), reverse=True)
            start = 0
            if cursor:
                matches = [index for index, item in enumerate(items) if item.intake_id == cursor]
                if not matches:
                    raise ValueError("cursor 无效。")
                start = matches[0] + 1
            page = items[start : start + bounded_limit]
            next_cursor = page[-1].intake_id if start + bounded_limit < len(items) else None
            return page, next_cursor

    def _build_item(
        self,
        payload: dict[str, Any],
        idempotency_key: str,
        creation_fingerprint: str,
    ) -> IntakeRecord:
        if str(payload.get("schema_version") or "") != SCHEMA_VERSION:
            raise ValueError("schema_version 必须是 1.0。")
        client_request_id = _text(payload.get("client_request_id"), field_name="client_request_id", max_length=200)
        if not client_request_id:
            raise ValueError("缺少 client_request_id。")
        source = payload.get("source")
        capture = payload.get("capture") or {}
        preferences = payload.get("preferences") or {}
        consent = payload.get("consent") or {}
        if not isinstance(source, dict):
            raise ValueError("source 必须是对象。")
        if not isinstance(capture, dict) or not isinstance(preferences, dict) or not isinstance(consent, dict):
            raise ValueError("capture、preferences、consent 必须是对象。")
        source_kind = _text(source.get("kind"), field_name="source.kind", max_length=40).lower()
        if source_kind not in {"video", "page"}:
            raise ValueError("source.kind 只能是 video 或 page。")
        source_url = _text(source.get("url"), field_name="source.url", max_length=4000)
        canonical_url = normalize_source_url(source_url)
        hint = _text(source.get("canonical_url_hint"), field_name="source.canonical_url_hint", max_length=4000)
        if hint and normalize_source_url(hint) != canonical_url:
            raise ValueError("canonical_url_hint 与 source.url 不一致。")
        title = _text(capture.get("title"), field_name="capture.title", max_length=500)
        selected_text = _text(
            capture.get("selected_text"),
            field_name="capture.selected_text",
            max_length=50_000,
        )
        visible_text = _text(
            capture.get("visible_text"),
            field_name="capture.visible_text",
            max_length=200_000,
        )
        if selected_text:
            # A user selection is the complete capture scope. Do not retain a
            # second, broader page snapshot that the user did not choose to use.
            visible_text = ""
        if source_kind == "page" and not (selected_text or visible_text):
            raise ValueError("网页 Intake 必须包含用户选择文本或当前页面可见正文。")
        capture_scope = "selection" if selected_text else "visible" if visible_text else ""
        content_sha256 = _capture_content_hash(selected_text or visible_text, capture_scope)
        captured_at = _text(capture.get("captured_at"), field_name="capture.captured_at", max_length=80) or _utc_now()
        if consent.get("user_initiated") is not True:
            raise ValueError("只接受用户主动发起的 Intake。")
        analysis_profile = _text(preferences.get("analysis_profile") or "summary", field_name="preferences.analysis_profile", max_length=40).lower()
        if analysis_profile not in {"summary", "tutorial", "viral", "close-reading"}:
            raise ValueError("preferences.analysis_profile 不受支持。")
        processing_profile = _text(preferences.get("processing_profile") or "fast", field_name="preferences.processing_profile", max_length=20).lower()
        if processing_profile not in {"fast", "complete"}:
            raise ValueError("preferences.processing_profile 只能是 fast 或 complete。")
        languages = preferences.get("output_languages", ["source"])
        if not isinstance(languages, list) or not languages or any(not isinstance(item, str) or not item.strip() for item in languages):
            raise ValueError("preferences.output_languages 必须是非空字符串数组。")
        languages = list(dict.fromkeys(item.strip().lower() for item in languages))
        dimensions = KnowledgeRequestDimensions(analysis_profile=analysis_profile, processing_profile=processing_profile)
        identity = _build_identity(
            canonical_url,
            source_kind,
            dimensions,
            content_sha256=content_sha256 if source_kind == "page" else "",
        )
        records = [
            TaskIdentityRecord(
                task_id=existing.intake_id,
                knowledge_id=existing.knowledge_id or "",
                request_fingerprint=existing.request_fingerprint,
                status=_identity_status(existing.state),
            )
            for existing in self._items.values()
            if existing.knowledge_id
        ]
        duplicate = detect_duplicate(identity, records)
        now = _utc_now()
        return IntakeRecord(
            intake_id=f"in_{uuid.uuid4().hex}",
            client_request_id=client_request_id,
            idempotency_key=idempotency_key,
            creation_fingerprint=creation_fingerprint,
            source_kind=source_kind,
            source_url=source_url,
            canonical_url=canonical_url,
            title=title,
            selected_text=selected_text,
            visible_text=visible_text,
            content_sha256=content_sha256,
            capture_scope=capture_scope,
            captured_at=captured_at,
            user_initiated=True,
            content_upload_allowed=bool(consent.get("content_upload_allowed", False)),
            analysis_profile=analysis_profile,
            processing_profile=processing_profile,
            output_languages=languages,
            knowledge_id=identity.knowledge_id,
            source_fingerprint=identity.source_fingerprint,
            request_fingerprint=identity.request_fingerprint,
            state="duplicate" if duplicate.detected else "queued",
            duplicate_kind=duplicate.kind.value,
            duplicate_knowledge_id=duplicate.matched_knowledge_id or None,
            duplicate_allowed_actions=list(duplicate.allowed_actions) if duplicate.detected else [],
            created_at=now,
            updated_at=now,
        )

    def _ensure_loaded(self) -> None:
        if self._items is not None:
            return
        values: dict[str, IntakeRecord] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            for value in payload.get("items", []) if isinstance(payload, dict) else []:
                if isinstance(value, dict):
                    item = IntakeRecord.from_record(value)
                    if item.intake_id and item.state in SUPPORTED_STATES:
                        self._read_capture(item)
                        values[item.intake_id] = item
        self._items = values

    def _write(self) -> None:
        assert self._items is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA_VERSION, "items": [item.to_record() for item in self._items.values()]}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    @property
    def _capture_root(self) -> Path:
        return self.path.parent / "intakes"

    def _write_capture(self, item: IntakeRecord) -> None:
        if not item.capture_ref or Path(item.capture_ref).name != item.capture_ref:
            raise ValueError("Intake capture reference is invalid.")
        self._capture_root.mkdir(parents=True, exist_ok=True)
        target = self._capture_root / item.capture_ref
        temporary = target.with_suffix(target.suffix + ".tmp")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "intake_id": item.intake_id,
            "capture_scope": item.capture_scope,
            "selected_text": item.selected_text,
            "visible_text": item.visible_text,
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)

    def _read_capture(self, item: IntakeRecord) -> None:
        if not item.capture_ref or Path(item.capture_ref).name != item.capture_ref:
            return
        try:
            payload = json.loads((self._capture_root / item.capture_ref).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict) or str(payload.get("intake_id") or "") != item.intake_id:
            return
        item.capture_scope = str(payload.get("capture_scope") or item.capture_scope)
        item.selected_text = str(payload.get("selected_text") or "")
        item.visible_text = str(payload.get("visible_text") or "")

    def _remove_capture(self, item: IntakeRecord) -> None:
        if not item.capture_ref or Path(item.capture_ref).name != item.capture_ref:
            return
        try:
            (self._capture_root / item.capture_ref).unlink()
        except FileNotFoundError:
            return


def _build_identity(
    canonical_url: str,
    source_kind: str,
    dimensions: KnowledgeRequestDimensions,
    *,
    content_sha256: str = "",
) -> KnowledgeIdentity:
    if source_kind == "video":
        return build_input_knowledge_identity(canonical_url, is_url=True, dimensions=dimensions)
    source_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]
    base = build_knowledge_identity(
        SourceRecord(
            source_type="web_page",
            platform="web",
            source_url=canonical_url,
            canonical_url=canonical_url,
            source_id=source_id,
        ),
        dimensions,
        input_value=canonical_url,
    )
    request_payload = {
        "schema_version": "1.0",
        "knowledge_id": base.knowledge_id,
        "dimensions": dimensions.normalized(),
        "content_sha256": content_sha256,
    }
    request_fingerprint = hashlib.sha256(json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return KnowledgeIdentity(
        base.schema_version,
        base.knowledge_id,
        base.source_fingerprint,
        request_fingerprint,
    )


def _capture_content_hash(content: str, scope: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""
    payload = json.dumps(
        {"scope": scope, "content": normalized},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Intake 请求必须是可序列化的 JSON 对象。") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _identity_status(state: str) -> str:
    return {"queued": "queued", "processing": "running", "ready": "completed", "failed": "failed", "needs_attention": "failed"}.get(state, state)


__all__ = ["IntakeRecord", "IntakeStore", "SCHEMA_VERSION"]
