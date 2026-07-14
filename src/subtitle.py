from __future__ import annotations

from pathlib import Path

from .cleaner import clean_subtitle_text
from .utils import UserFacingError, write_text

SUPPORTED_SUBTITLE_EXTS = {".srt", ".vtt"}


def find_subtitle_file(directory: Path) -> Path | None:
    if not directory.exists():
        return None
    candidates = sorted(
        path for path in directory.rglob("*") if path.suffix.lower() in SUPPORTED_SUBTITLE_EXTS
    )
    return candidates[0] if candidates else None


def subtitle_to_transcript(subtitle_path: Path, transcript_path: Path, source_url: str = "") -> Path:
    if not subtitle_path.exists():
        raise UserFacingError(f"字幕文件不存在：{subtitle_path}")
    if subtitle_path.suffix.lower() not in SUPPORTED_SUBTITLE_EXTS:
        raise UserFacingError(f"暂不支持该字幕格式：{subtitle_path.suffix}")

    raw = subtitle_path.read_text(encoding="utf-8", errors="replace")
    cleaned = clean_subtitle_text(raw, keep_timestamps=True, source_url=source_url)
    if not cleaned.strip():
        raise UserFacingError("字幕文件为空或无法清洗出有效文本。")

    write_text(transcript_path, "# 字幕 / 转写全文\n\n" + cleaned)
    return transcript_path
