from __future__ import annotations

from urllib.parse import urlparse

from ..domain.models import SourceRecord, TimelineEntry, TranscriptGroup


def build_timeline(groups: list[TranscriptGroup], source: SourceRecord) -> list[TimelineEntry]:
    return [TimelineEntry(index=group.index, start=group.start, end=group.end, title=group.title,
        summary=group.text, keywords=group.keywords,
        representative_time=group.representative_time if group.representative_time is not None else (group.start + group.end) / 2,
        source_link=build_source_link(source, int(group.start))) for group in groups]


def build_source_link(source: SourceRecord, seconds: int) -> str:
    url = source.canonical_url or source.source_url
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
    separator = "&" if "?" in url else "?"
    if "youtube.com" in host or "youtu.be" in host:
        return f"{url}{separator}t={seconds}s"
    if "bilibili.com" in host:
        return f"{url}{separator}t={seconds}"
    return url

