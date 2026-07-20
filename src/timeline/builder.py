from __future__ import annotations

from ..domain.models import SourceRecord, TimelineEntry, TranscriptGroup
from ..timestamps import build_timestamp_target


def build_timeline(groups: list[TranscriptGroup], source: SourceRecord) -> list[TimelineEntry]:
    return [TimelineEntry(index=group.index, start=group.start, end=group.end, title=group.title,
        summary=group.text, keywords=group.keywords,
        representative_time=group.representative_time if group.representative_time is not None else (group.start + group.end) / 2,
        source_link=build_source_link(source, group.start)) for group in groups]


def build_source_link(source: SourceRecord, seconds: float) -> str:
    return build_timestamp_target(source, seconds)

