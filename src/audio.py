from __future__ import annotations

from pathlib import Path

from .runtime_tools import resolve_executable
from .utils import UserFacingError, run_command


def extract_audio(
    video_path: Path,
    wav_path: Path,
    sample_seconds: int | None = None,
    *,
    ffmpeg_path: str | Path | None = None,
) -> Path:
    if not video_path.exists():
        raise UserFacingError(f"视频文件不存在：{video_path}")

    ffmpeg = resolve_executable("ffmpeg", ffmpeg_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
    ]
    if sample_seconds:
        args.extend(["-t", str(sample_seconds)])
    args.append(str(wav_path))
    run_command(args)
    if not wav_path.exists():
        raise UserFacingError("FFmpeg 未能生成音频文件。")
    return wav_path
