from __future__ import annotations

import re
from urllib.parse import urlparse
from .timestamps import build_timestamp_target, format_timestamp


TIMESTAMP_RE = re.compile(
    r"(?:(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[,.]\d{1,3})?)\s*-->\s*"
    r"(?:(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[,.]\d{1,3})?)"
)


def strip_subtitle_markup(text: str) -> str:
    text = re.sub(r"WEBVTT.*?(?:\n\n|\Z)", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?[^>]+>", "", text)
    text = re.sub(r"\{\\.*?\}", "", text)
    return text


def normalize_line(line: str) -> str:
    line = line.replace("\ufeff", "").strip()
    line = re.sub(r"\s+", " ", line)
    return line


def clean_subtitle_text(raw_text: str, keep_timestamps: bool = True, source_url: str = "") -> str:
    raw_text = strip_subtitle_markup(raw_text)
    lines: list[str] = []
    previous_text = ""
    pending_time = ""

    for raw_line in raw_text.splitlines():
        line = normalize_line(raw_line)
        if not line:
            continue
        if line.isdigit():
            continue
        if line.upper().startswith(("NOTE", "STYLE", "REGION")):
            continue
        if "-->" in line:
            match = TIMESTAMP_RE.search(line)
            if match and keep_timestamps:
                pending_time = match.group()
            continue
        if line == previous_text:
            continue
        if pending_time:
            lines.append(format_timestamped_line(pending_time, line, source_url))
            pending_time = ""
        else:
            lines.append(line)
        previous_text = line

    return merge_short_paragraphs(lines)


def merge_short_paragraphs(lines: list[str], min_chars: int = 30) -> str:
    merged: list[str] = []
    buffer = ""

    for line in lines:
        if (line.startswith("[") or line.startswith("- [")) and "]" in line:
            if buffer:
                merged.append(buffer.strip())
            buffer = line
            continue
        if not buffer:
            buffer = line
        elif len(buffer) < min_chars:
            buffer = f"{buffer} {line}"
        else:
            merged.append(buffer.strip())
            buffer = line

    if buffer:
        merged.append(buffer.strip())
    return "\n\n".join(merged).strip() + "\n"


def format_transcript_segment(start: float, end: float, text: str, source_url: str = "") -> str:
    start_label = seconds_to_timestamp(start)
    end_label = seconds_to_timestamp(end)
    label = f"{start_label} - {end_label}"
    link = build_timestamp_link(source_url, int(start))
    content = normalize_line(text)
    if link:
        return f"- [{label}]({link}) {content}"
    return f"- [{label}] {content}"


def seconds_to_timestamp(seconds: float) -> str:
    return format_timestamp(seconds)


def timestamp_to_seconds(value: str) -> int:
    value = value.strip().replace(",", ".")
    value = re.sub(r"\.\d+$", "", value)
    parts = [int(part) for part in value.split(":") if part.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return 0


def format_timestamped_line(timestamp_range: str, text: str, source_url: str = "") -> str:
    left, right = timestamp_range.split("-->", 1)
    start = _trim_time(left)
    end = _trim_time(right)
    label = f"{start} - {end}"
    link = build_timestamp_link(source_url, timestamp_to_seconds(left))
    content = normalize_line(text)
    if link:
        return f"- [{label}]({link}) {content}"
    return f"- [{label}] {content}"


def build_timestamp_link(source_url: str, seconds: int) -> str:
    return build_timestamp_target(source_url, seconds)


def _compact_timestamp(value: str) -> str:
    left, right = value.split("-->", 1)
    return f"{_trim_time(left)} - {_trim_time(right)}"


def _trim_time(value: str) -> str:
    value = value.strip().replace(",", ".")
    value = re.sub(r"\.\d+$", "", value)
    parts = value.split(":")
    if len(parts) == 3 and parts[0] == "00":
        return ":".join(parts[1:])
    return value
