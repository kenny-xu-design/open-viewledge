from __future__ import annotations

import re
from pathlib import Path

from ..cleaner import normalize_line
from ..domain.models import TranscriptSegment
from ..utils import UserFacingError

TIMING_RE = re.compile(
    r"(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})"
)


def parse_subtitle_file(path: Path, language: str = "", source: str = "platform_subtitle") -> list[TranscriptSegment]:
    if not path.exists():
        raise UserFacingError(f"字幕文件不存在：{path}")
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    segments: list[TranscriptSegment] = []
    previous = ""
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = TIMING_RE.search(lines[timing_index])
        if not match:
            continue
        content = normalize_line(" ".join(lines[timing_index + 1 :]))
        content = re.sub(r"</?[^>]+>", "", content)
        if not content or content == previous:
            continue
        segments.append(TranscriptSegment(
            index=len(segments), start=_time_to_seconds(match.group("start")), end=_time_to_seconds(match.group("end")),
            text=content, language=language, source=source,
        ))
        previous = content
    if not segments:
        raise UserFacingError(f"字幕文件为空或无法解析逐句时间戳：{path}")
    return segments


def normalize_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    normalized: list[TranscriptSegment] = []
    for item in segments:
        text = normalize_line(item.text)
        if text:
            normalized.append(item.model_copy(update={"index": len(normalized), "text": text}))
    return normalized


def _time_to_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    return (int(parts[-3]) * 3600 if len(parts) >= 3 else 0) + (int(parts[-2]) * 60 if len(parts) >= 2 else 0) + float(parts[-1])

