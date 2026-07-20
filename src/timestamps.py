from __future__ import annotations

from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from .domain.models import SourceRecord


def normalize_seconds(value: float | int | None) -> int | None:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def format_timestamp(value: float | int | None) -> str:
    seconds = normalize_seconds(value)
    if seconds is None:
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def build_timestamp_target(
    source: SourceRecord | str,
    value: float | int | None,
    *,
    knowledge_id: str | None = None,
) -> str:
    seconds = normalize_seconds(value)
    if seconds is None:
        return ""
    if isinstance(source, SourceRecord):
        if source.source_type in {"local_video", "local_audio"}:
            return f"/api/library/{quote(knowledge_id or source.source_id, safe='')}/media?t={seconds}" if (knowledge_id or source.source_id) else ""
        url = source.canonical_url or source.source_url
    else:
        url = str(source or "")
    if not url:
        return ""
    parts = urlsplit(url)
    host = parts.netloc.lower().split(":", 1)[0]
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"}:
        return ""
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key.lower() != "t"]
    query.append(("t", f"{seconds}s" if "youtube" in host or host == "youtu.be" else str(seconds)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
