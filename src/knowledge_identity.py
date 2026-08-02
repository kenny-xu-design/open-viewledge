from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .domain.models import SourceRecord


KNOWLEDGE_IDENTITY_SCHEMA_VERSION = "1.0"
_TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
    }
)
_ACTIVE_STATUSES = frozenset({"created", "queued", "running", "resuming"})
_COMPLETED_STATUSES = frozenset({"completed", "success"})
_RECOVERABLE_STATUSES = frozenset({"failed", "interrupted", "timeout"})
_BILIBILI_ID_RE = re.compile(r"(?i)(BV[0-9A-Za-z]{10})")
_SAFE_PREFIX_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class KnowledgeRequestDimensions:
    language: str = ""
    analysis_profile: str = "summary"
    processing_profile: str = "complete"
    transcript_only: bool = False
    comments_enabled: bool = False
    sample_seconds: int | None = None
    transcript_group_seconds: int = 30
    asr_route: str = "cloud"
    asr_fallback_enabled: bool = True
    generate_frames: bool = True

    def normalized(self) -> dict[str, object]:
        processing_profile = self.processing_profile.strip().lower()
        if processing_profile not in {"fast", "complete"}:
            raise ValueError("processing_profile must be fast or complete.")
        asr_route = self.asr_route.strip().lower()
        if asr_route not in {"cloud", "local_gpu", "local_cpu"}:
            raise ValueError("asr_route must be cloud, local_gpu, or local_cpu.")
        if self.sample_seconds is not None and self.sample_seconds <= 0:
            raise ValueError("sample_seconds must be greater than zero.")
        if self.transcript_group_seconds < 15:
            raise ValueError("transcript_group_seconds must be at least 15.")
        if self.transcript_group_seconds > 300:
            raise ValueError("transcript_group_seconds must be at most 300.")
        analysis_profile = self.analysis_profile.strip().lower()
        if not analysis_profile:
            raise ValueError("analysis_profile cannot be empty.")
        return {
            "language": self.language.strip().lower().replace("_", "-"),
            "analysis_profile": analysis_profile,
            "processing_profile": processing_profile,
            "transcript_only": bool(self.transcript_only),
            "comments_enabled": bool(self.comments_enabled),
            "sample_seconds": self.sample_seconds,
            "transcript_group_seconds": int(self.transcript_group_seconds),
            "asr_route": asr_route,
            "asr_fallback_enabled": bool(self.asr_fallback_enabled),
            "generate_frames": bool(self.generate_frames),
        }


@dataclass(frozen=True, slots=True)
class KnowledgeIdentity:
    schema_version: str
    knowledge_id: str
    source_fingerprint: str
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class TaskIdentityRecord:
    task_id: str
    knowledge_id: str
    request_fingerprint: str
    status: str


class DuplicateKind(str, Enum):
    NONE = "none"
    ACTIVE_EXACT = "active_exact"
    COMPLETED_EXACT = "completed_exact"
    RECOVERABLE_EXACT = "recoverable_exact"
    SOURCE_REVISION = "source_revision"


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    kind: DuplicateKind
    matched_task_id: str = ""
    matched_knowledge_id: str = ""
    allowed_actions: tuple[str, ...] = ("create",)

    @property
    def detected(self) -> bool:
        return self.kind is not DuplicateKind.NONE


def build_knowledge_identity(
    source: SourceRecord,
    dimensions: KnowledgeRequestDimensions | None = None,
    *,
    input_value: str = "",
) -> KnowledgeIdentity:
    source_material, prefix = _source_identity_material(source, input_value)
    source_fingerprint = _sha256(source_material)
    knowledge_id = f"k1-{prefix}-{source_fingerprint[:20]}"
    request_payload = {
        "schema_version": KNOWLEDGE_IDENTITY_SCHEMA_VERSION,
        "knowledge_id": knowledge_id,
        "dimensions": (dimensions or KnowledgeRequestDimensions()).normalized(),
    }
    return KnowledgeIdentity(
        schema_version=KNOWLEDGE_IDENTITY_SCHEMA_VERSION,
        knowledge_id=knowledge_id,
        source_fingerprint=source_fingerprint,
        request_fingerprint=_sha256(_canonical_json(request_payload)),
    )


def build_input_knowledge_identity(
    input_value: str,
    *,
    is_url: bool,
    dimensions: KnowledgeRequestDimensions | None = None,
) -> KnowledgeIdentity:
    if is_url:
        normalized = normalize_source_url(input_value)
        platform = _infer_url_platform(normalized)
        return build_knowledge_identity(
            SourceRecord(
                source_type="online_video",
                platform=platform,
                source_url=normalized,
                canonical_url=normalized,
                source_id=_input_url_source_id(normalized, platform),
            ),
            dimensions,
            input_value=input_value,
        )

    from .sources.local_media import LocalMediaSource

    source = LocalMediaSource().resolve(str(Path(input_value).expanduser()))
    return build_knowledge_identity(source, dimensions, input_value=input_value)


def detect_duplicate(
    identity: KnowledgeIdentity,
    records: Iterable[TaskIdentityRecord],
) -> DuplicateDecision:
    same_source: list[TaskIdentityRecord] = []
    exact: list[TaskIdentityRecord] = []
    for record in records:
        if record.knowledge_id != identity.knowledge_id:
            continue
        same_source.append(record)
        if record.request_fingerprint == identity.request_fingerprint:
            exact.append(record)

    for statuses, kind, actions in (
        (_ACTIVE_STATUSES, DuplicateKind.ACTIVE_EXACT, ("reject",)),
        (_COMPLETED_STATUSES, DuplicateKind.COMPLETED_EXACT, ("reuse", "refresh", "reject")),
        (_RECOVERABLE_STATUSES, DuplicateKind.RECOVERABLE_EXACT, ("resume", "refresh", "reject")),
    ):
        match = next(
            (record for record in exact if record.status.strip().lower() in statuses),
            None,
        )
        if match:
            return _decision(kind, match, actions)

    if same_source:
        return _decision(
            DuplicateKind.SOURCE_REVISION,
            same_source[0],
            ("revision", "refresh", "reject"),
        )
    return DuplicateDecision(kind=DuplicateKind.NONE)


def normalize_source_url(value: str) -> str:
    stripped = value.strip()
    parsed = urlsplit(stripped)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source URL must use http or https.")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_key(key)
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, host, path, query, ""))


def _source_identity_material(source: SourceRecord, input_value: str) -> tuple[str, str]:
    source_type = source.source_type.strip().lower()
    platform = source.platform.strip().lower() or "unknown"
    source_id = source.source_id.strip()
    url = source.canonical_url or source.source_url or input_value

    if source_type in {"local_video", "local_audio"}:
        if not source_id:
            raise ValueError("local source is missing stable source_id.")
        return f"{source_type}|local|{source_id}", "local"

    if source_type not in {"online_video", "web_page"}:
        raise ValueError(f"unsupported source type: {source.source_type}")

    normalized_url = normalize_source_url(url) if url else ""
    if normalized_url:
        youtube_id = _youtube_video_id(normalized_url)
        if platform == "youtube" and youtube_id:
            return f"{source_type}|youtube|{youtube_id}", "youtube"
        bilibili_id = _bilibili_video_id(normalized_url)
        if platform == "bilibili" and bilibili_id:
            part = _query_value(normalized_url, "p")
            return f"{source_type}|bilibili|{bilibili_id}|p={part or '1'}", "bilibili"

    if source_id:
        return f"{source_type}|{platform}|{source_id}", _safe_prefix(platform)
    if normalized_url:
        return f"{source_type}|{platform}|{normalized_url}", _safe_prefix(platform)
    raise ValueError("online source is missing source_id and URL.")


def _youtube_video_id(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if host == "youtu.be":
        return parsed.path.strip("/").split("/", 1)[0]
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return _query_value(url, "v")
        match = re.match(r"^/(?:shorts|embed|live)/([^/]+)", parsed.path)
        return match.group(1) if match else ""
    return ""


def _bilibili_video_id(url: str) -> str:
    parsed = urlsplit(url)
    if not ((parsed.hostname or "").endswith("bilibili.com")):
        return ""
    match = _BILIBILI_ID_RE.search(parsed.path)
    if not match:
        return ""
    raw = match.group(1)
    return "BV" + raw[2:]


def _query_value(url: str, key: str) -> str:
    return next((value for name, value in parse_qsl(urlsplit(url).query) if name == key), "")


def _infer_url_platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host == "youtu.be" or host.endswith("youtube.com"):
        return "youtube"
    if host.endswith("bilibili.com") or host == "b23.tv":
        return "bilibili"
    return "web"


def _input_url_source_id(url: str, platform: str) -> str:
    if platform == "youtube":
        return _youtube_video_id(url)
    if platform == "bilibili":
        return _bilibili_video_id(url)
    return ""


def _is_tracking_query_key(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("utm_") or normalized in _TRACKING_QUERY_KEYS


def _safe_prefix(value: str) -> str:
    normalized = _SAFE_PREFIX_RE.sub("-", value.strip().lower()).strip("-")
    return (normalized or "source")[:16]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decision(
    kind: DuplicateKind,
    record: TaskIdentityRecord,
    actions: tuple[str, ...],
) -> DuplicateDecision:
    return DuplicateDecision(
        kind=kind,
        matched_task_id=record.task_id,
        matched_knowledge_id=record.knowledge_id,
        allowed_actions=actions,
    )
