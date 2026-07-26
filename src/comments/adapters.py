from __future__ import annotations

import re
from typing import Any

from ..domain.models import NormalizedComment, SourceRecord, utc_now
from ..downloader import _import_ytdlp

_TIMESTAMP_RE = re.compile(r"(?<!\d)(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)(?!\d)")


class YtdlpCommentAdapter:
    platform = "yt-dlp"

    def __init__(self, yt_dlp_module: Any | None = None) -> None:
        self._yt_dlp = yt_dlp_module

    def fetch(self, source: SourceRecord, *, limit: int, sort: str = "top") -> list[NormalizedComment]:
        if source.source_type != "online_video":
            return []
        url = source.canonical_url or source.source_url
        if not url:
            return []
        yt_dlp = self._yt_dlp or _import_ytdlp()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "getcomments": True,
            "extractor_args": _extractor_args(source, limit, sort),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        comments = info.get("comments") if isinstance(info, dict) else None
        if not isinstance(comments, list):
            return []
        normalized = [
            comment
            for item in comments
            if isinstance(item, dict)
            for comment in [self._normalize(item, source)]
            if comment is not None
        ]
        return _rank_comments(normalized, sort)[:limit]

    def _normalize(self, item: dict[str, Any], source: SourceRecord) -> NormalizedComment | None:
        content = _clean_text(item.get("text") or item.get("content") or item.get("comment") or "")
        if not content:
            return None
        comment_id = str(item.get("id") or item.get("comment_id") or _fallback_id(source, content))
        published_at = _published_at(item)
        platform = source.platform if source.platform in {"youtube", "bilibili"} else "yt-dlp"
        return NormalizedComment(
            comment_id=comment_id,
            parent_id=str(item.get("parent") or item.get("parent_id") or ""),
            author=_clean_text(item.get("author") or item.get("author_name") or "匿名用户")[:80],
            content=content,
            likes=_safe_int(item.get("like_count") or item.get("likes") or item.get("votes")),
            reply_count=_safe_int(item.get("reply_count") or item.get("replies")),
            is_pinned=bool(item.get("is_pinned") or item.get("pinned")),
            is_creator=bool(item.get("is_uploader") or item.get("is_creator") or item.get("author_is_uploader")),
            published_at=published_at,
            source_url=source.canonical_url or source.source_url,
            timestamps=_extract_timestamps(content),
            platform=platform,
            sync_cursor=str(item.get("id") or item.get("timestamp") or ""),
            fetched_at=utc_now(),
        )


class YouTubeCommentAdapter(YtdlpCommentAdapter):
    platform = "youtube"


class BilibiliCommentAdapter(YtdlpCommentAdapter):
    platform = "bilibili"


def _extractor_args(source: SourceRecord, limit: int, sort: str) -> dict[str, dict[str, list[str]]]:
    if source.platform == "youtube":
        youtube_sort = "top" if sort == "top" else "new"
        return {"youtube": {"comment_sort": [youtube_sort], "max_comments": [str(limit)]}}
    if source.platform == "bilibili":
        bilibili_sort = "hot" if sort == "top" else "time"
        return {"bilibili": {"comment_sort": [bilibili_sort], "max_comments": [str(limit)]}}
    return {}


def _rank_comments(comments: list[NormalizedComment], sort: str) -> list[NormalizedComment]:
    if sort == "latest":
        return sorted(comments, key=lambda item: item.published_at or item.fetched_at, reverse=True)
    return sorted(
        comments,
        key=lambda item: (item.is_pinned, item.likes, item.reply_count, bool(item.timestamps)),
        reverse=True,
    )


def _extract_timestamps(value: str) -> list[float]:
    seconds: list[float] = []
    for match in _TIMESTAMP_RE.finditer(value):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        secs = int(match.group(3))
        total = float(hours * 3600 + minutes * 60 + secs)
        if total not in seconds:
            seconds.append(total)
    return seconds


def _published_at(item: dict[str, Any]) -> str:
    value = item.get("timestamp") or item.get("published_at") or item.get("time")
    if isinstance(value, (int, float)):
        from datetime import datetime, timezone

        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value or "")


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _fallback_id(source: SourceRecord, content: str) -> str:
    import hashlib

    basis = f"{source.platform}:{source.source_id}:{content}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
