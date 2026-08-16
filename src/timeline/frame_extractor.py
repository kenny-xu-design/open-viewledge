from __future__ import annotations

from pathlib import Path

from ..domain.models import TimelineEntry
from ..runtime_tools import resolve_executable
from ..utils import run_command


def extract_frames(
    media_path: Path,
    entries: list[TimelineEntry],
    frames_dir: Path,
    *,
    ffmpeg_path: str | Path | None = None,
    ffmpeg_threads: int = 1,
) -> tuple[list[TimelineEntry], list[str]]:
    errors: list[str] = []
    try:
        ffmpeg = resolve_executable("ffmpeg", ffmpeg_path)
    except Exception as exc:
        return entries, [str(exc)]
    frames_dir.mkdir(parents=True, exist_ok=True)
    result: list[TimelineEntry] = []
    for entry in entries:
        frame = frames_dir / f"frame_{entry.index + 1:04d}_{int(entry.representative_time or 0):06d}.jpg"
        try:
            run_command([ffmpeg, "-y", "-threads", str(max(1, ffmpeg_threads)), "-ss", str(entry.representative_time or 0), "-i", str(media_path), "-frames:v", "1", "-q:v", "3", str(frame)])
            relative = str(Path("frames") / frame.name).replace("\\", "/") if frame.exists() else ""
            result.append(entry.model_copy(update={"frame_path": relative}))
        except Exception as exc:
            errors.append(f"关键帧 {entry.index + 1} 截取失败：{exc}")
            result.append(entry)
    return result, errors

