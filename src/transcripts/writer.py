from __future__ import annotations

import json
from pathlib import Path

from ..cleaner import format_transcript_segment, seconds_to_timestamp
from ..domain.models import TranscriptGroup, TranscriptSegment
from ..utils import ensure_dir, write_text


def write_jsonl(path: Path, segments: list[TranscriptSegment]) -> Path:
    ensure_dir(path.parent)
    path.write_text("".join(json.dumps(item.model_dump(), ensure_ascii=False) + "\n" for item in segments), encoding="utf-8")
    return path


def read_jsonl(path: Path) -> list[TranscriptSegment]:
    return [TranscriptSegment.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_grouped_markdown(path: Path, groups: list[TranscriptGroup], source_url: str = "") -> Path:
    lines = ["# 分组字幕", ""]
    for group in groups:
        label = f"{seconds_to_timestamp(group.start)} - {seconds_to_timestamp(group.end)}"
        lines.extend([f"## {group.index + 1}. {group.title}", "", f"**时间：{label}**", "", group.text, ""])
    write_text(path, "\n".join(lines).rstrip() + "\n")
    return path


def write_legacy_transcript(path: Path, segments: list[TranscriptSegment], source_url: str = "") -> Path:
    lines = [format_transcript_segment(item.start, item.end, item.text, source_url) for item in segments]
    write_text(path, "# 字幕 / 转写全文\n\n" + "\n\n".join(lines) + "\n")
    return path

