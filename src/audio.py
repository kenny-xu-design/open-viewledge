from __future__ import annotations

from pathlib import Path

from .utils import UserFacingError, require_executable, run_command


FFMPEG_HINT = "请先安装 FFmpeg，并确认 ffmpeg 命令已加入 PATH。Windows 可使用 winget install Gyan.FFmpeg。"


def extract_audio(video_path: Path, wav_path: Path, sample_seconds: int | None = None) -> Path:
    if not video_path.exists():
        raise UserFacingError(f"视频文件不存在：{video_path}")

    ffmpeg = require_executable("ffmpeg", FFMPEG_HINT)
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
