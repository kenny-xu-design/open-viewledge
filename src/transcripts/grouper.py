from __future__ import annotations

import re

from ..domain.models import TranscriptGroup, TranscriptSegment


def group_segments(segments: list[TranscriptSegment], chapters: list[dict] | None = None, target_seconds: int = 60, max_segments: int = 12) -> list[TranscriptGroup]:
    if not segments:
        return []
    chapter_starts = sorted(float(item.get("start_time", item.get("start", 0))) for item in (chapters or []) if isinstance(item, dict))
    groups: list[TranscriptGroup] = []
    current: list[TranscriptSegment] = []
    for segment in segments:
        if current and _should_split(current, segment, chapter_starts, target_seconds, max_segments):
            groups.append(_make_group(len(groups), current))
            current = []
        current.append(segment)
    if current:
        groups.append(_make_group(len(groups), current))
    return groups


def _should_split(current: list[TranscriptSegment], incoming: TranscriptSegment, chapter_starts: list[float], target_seconds: int, max_segments: int) -> bool:
    chapter_boundary = any(current[-1].start < point <= incoming.start for point in chapter_starts)
    too_long = incoming.end - current[0].start > target_seconds
    long_pause = incoming.start - current[-1].end >= 3.0
    sentence_complete = bool(re.search(r"[。！？.!?]$", current[-1].text))
    return chapter_boundary or len(current) >= max_segments or (too_long and (sentence_complete or long_pause or len(current) >= 5))


def _make_group(index: int, items: list[TranscriptSegment]) -> TranscriptGroup:
    text = " ".join(item.text for item in items).strip()
    sentence = re.split(r"[。！？.!?]", text, maxsplit=1)[0].strip()
    title = (sentence[:28] + ("..." if len(sentence) > 28 else "")) if sentence else f"片段 {index + 1}"
    start, end = items[0].start, items[-1].end
    return TranscriptGroup(index=index, start=start, end=end, title=title, text=text,
        segment_indexes=[item.index for item in items], representative_time=(start + end) / 2)

