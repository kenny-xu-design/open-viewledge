from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .domain.models import SourceRecord, TranscriptSegment, utc_now


CACHE_SCHEMA_VERSION = "1.0"
CACHE_ARTIFACT_TYPES = frozenset(
    {
        "metadata",
        "subtitle",
        "audio",
        "transcript",
        "frames",
        "text_analysis",
        "visual_analysis",
        "comments",
    }
)
def default_cache_root() -> Path:
    """Return the writable cache root for the current local runtime.

    Portable/read-only checkouts keep mutable state outside the project when
    ``VIEWLEDGE_STATE_ROOT`` is configured.  ``VIEWLEDGE_CACHE_ROOT`` remains
    an explicit override for operators that want a dedicated cache location.
    """
    explicit = os.environ.get("VIEWLEDGE_CACHE_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    state_root = os.environ.get("VIEWLEDGE_STATE_ROOT", "").strip()
    if state_root:
        return Path(state_root).expanduser() / "cache" / "v1"
    return Path(__file__).resolve().parents[1] / ".local" / "cache" / "v1"


DEFAULT_CACHE_ROOT = default_cache_root()
_CACHE_KEY_RE = re.compile(r"[0-9a-f]{64}")


def build_cache_key(artifact_type: str, **dimensions: Any) -> str:
    _validate_artifact_type(artifact_type)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "dimensions": _normalize_value(dimensions),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def source_cache_dimensions(source: SourceRecord, input_value: str = "") -> dict[str, Any]:
    url = source.canonical_url or source.source_url or input_value
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    part = (query.get("p") or [""])[0]
    youtube_id = (query.get("v") or [""])[0]
    if parsed.netloc.lower().endswith("youtu.be"):
        youtube_id = parsed.path.strip("/").split("/", 1)[0]
    return {
        "platform": source.platform,
        "source_id": source.source_id,
        "canonical_url": url,
        "bilibili_part": part,
        "youtube_video_id": youtube_id or (source.source_id if source.platform == "youtube" else ""),
    }


def transcript_content_hash(segments: list[TranscriptSegment]) -> str:
    payload = [
        {
            "index": item.index,
            "start": item.start,
            "end": item.end,
            "text": item.text,
            "language": item.language,
            "source": item.source,
        }
        for item in segments
    ]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class CacheStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_cache_root()

    def get(self, artifact_type: str, cache_key: str) -> Any | None:
        path = self._path_for(artifact_type, cache_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("artifact_type") != artifact_type or payload.get("cache_key") != cache_key:
            return None
        return payload.get("data")

    def put(self, artifact_type: str, cache_key: str, data: Any) -> Path:
        path = self._path_for(artifact_type, cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "artifact_type": artifact_type,
            "cache_key": cache_key,
            "created_at": utc_now(),
            "data": data,
        }
        handle, temporary_name = tempfile.mkstemp(prefix="cache-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return path

    def _path_for(self, artifact_type: str, cache_key: str) -> Path:
        _validate_artifact_type(artifact_type)
        if not _CACHE_KEY_RE.fullmatch(cache_key):
            raise ValueError("cache_key 格式无效。")
        return self.root / artifact_type / f"{cache_key}.json"


def _validate_artifact_type(artifact_type: str) -> None:
    if artifact_type not in CACHE_ARTIFACT_TYPES:
        raise ValueError(f"不支持的缓存产物类型：{artifact_type}")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
