from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .downloader import _import_ytdlp
from .sources.ytdlp_source import is_bilibili_input, normalize_bilibili_input
from .utils import UserFacingError


MAX_COLLECTION_ITEMS = 200


def inspect_bilibili_input(input_value: str) -> dict[str, Any]:
    """Inspect a Bilibili URL without downloading media.

    The extractor is intentionally flat and metadata-only. A normal BV with
    multiple `pages` becomes an ordered parts collection; a playlist-like
    extractor result becomes an ordered series collection.
    """

    value = normalize_bilibili_input(input_value)
    if not is_bilibili_input(value):
        raise ValueError("仅支持 B 站视频或合集链接。")
    yt_dlp = _import_ytdlp()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": False,
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(value, download=False)
    except Exception as exc:
        raise UserFacingError(f"B站链接暂时无法读取：{exc}") from exc
    if not isinstance(info, dict):
        raise UserFacingError("B站返回的来源信息无效。")

    pages = info.get("pages")
    if isinstance(pages, list) and len(pages) > 1:
        items = []
        for index, page in enumerate(pages[:MAX_COLLECTION_ITEMS], start=1):
            if not isinstance(page, dict):
                continue
            items.append(
                _item(
                    index=index,
                    title=str(page.get("part") or page.get("title") or f"P{index}"),
                    source_url=_with_part(value, index),
                    partition="分P",
                    duration=page.get("duration"),
                )
            )
        return _collection(
            kind="bilibili_parts",
            title=str(info.get("title") or "B站分P教程"),
            source_url=value,
            items=items,
            total_count=len(pages),
            uploader=str(info.get("uploader") or info.get("channel") or ""),
        )

    entries = info.get("entries")
    if entries is not None:
        try:
            entries = list(entries)
        except TypeError:
            entries = []
    if isinstance(entries, list) and len(entries) > 1:
        items = []
        for index, entry in enumerate(entries[:MAX_COLLECTION_ITEMS], start=1):
            if not isinstance(entry, dict):
                continue
            source_url = _entry_url(entry)
            if not source_url:
                continue
            items.append(
                _item(
                    index=index,
                    title=str(entry.get("title") or entry.get("id") or f"第 {index} 集"),
                    source_url=source_url,
                    partition=str(entry.get("section") or entry.get("category") or "系列教程"),
                    duration=entry.get("duration"),
                )
            )
        if len(items) > 1:
            return _collection(
                kind="bilibili_series",
                title=str(info.get("title") or info.get("playlist_title") or "B站系列教程"),
                source_url=value,
                items=items,
                total_count=len(entries),
                uploader=str(info.get("uploader") or info.get("channel") or ""),
            )

    return {
        "kind": "single",
        "isCollection": False,
        "title": str(info.get("title") or "B站视频"),
        "sourceUrl": str(info.get("webpage_url") or value),
        "uploader": str(info.get("uploader") or info.get("channel") or ""),
        "items": [],
    }


def _collection(*, kind: str, title: str, source_url: str, items: list[dict[str, Any]], total_count: int, uploader: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "isCollection": True,
        "title": title,
        "sourceUrl": source_url,
        "uploader": uploader,
        "totalCount": total_count,
        "truncated": total_count > len(items),
        "items": items,
    }


def _item(*, index: int, title: str, source_url: str, partition: str, duration: Any) -> dict[str, Any]:
    return {
        "sequence": index,
        "title": title,
        "sourceUrl": source_url,
        "partition": partition,
        "duration": duration if isinstance(duration, (int, float)) else None,
    }


def _entry_url(entry: dict[str, Any]) -> str:
    value = str(entry.get("webpage_url") or entry.get("url") or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    identifier = str(entry.get("id") or "").strip()
    return f"https://www.bilibili.com/video/{identifier}" if identifier else ""


def _with_part(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "p"]
    query.append(("p", str(page)))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.params, urlencode(query), ""))


__all__ = ["MAX_COLLECTION_ITEMS", "inspect_bilibili_input"]
