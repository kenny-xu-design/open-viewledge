from __future__ import annotations

from pathlib import Path
from typing import Callable

from .asr_runtime import transcribe_with_local_asr
from .cleaner import format_transcript_segment
from .domain.models import TranscriptSegment
from .utils import UserFacingError, write_text


LOCAL_WHISPER_MODEL_DIR = Path("models/faster-whisper-small")
LOCAL_WHISPER_MODEL_HINT = (
    "未找到完整的本地 faster-whisper 模型，请先执行：\n"
    "hf download Systran/faster-whisper-small --local-dir models/faster-whisper-small"
)


def transcribe_audio(
    audio_path: Path,
    transcript_path: Path,
    model_name: str = "small",
    language: str | None = "zh",
    source_url: str = "",
) -> Path:
    if not audio_path.exists():
        raise UserFacingError(f"音频文件不存在：{audio_path}")

    config = type(
        "LegacyASRConfig",
        (),
        {
            "asr_profile": "balanced",
            "asr_model": model_name,
            "asr_device": "",
            "asr_compute_type": "",
            "asr_task": "transcribe",
            "whisper_model": model_name,
        },
    )()
    segments = transcribe_segments(
        audio_path,
        language=language,
        source="asr",
        config=config,
    )
    lines = [
        format_transcript_segment(item.start, item.end, item.text, source_url=source_url)
        for item in segments
    ]
    write_text(transcript_path, "# 字幕 / 转写全文\n\n" + "\n\n".join(lines) + "\n")
    return transcript_path


def transcribe_segments(
    audio_path: Path,
    language: str | None = "zh",
    source: str = "asr",
    log_callback: Callable[[str], None] | None = None,
    config: object | None = None,
) -> list[TranscriptSegment]:
    if not audio_path.exists():
        raise UserFacingError(f"音频文件不存在：{audio_path}")
    outcome = transcribe_with_local_asr(
        audio_path,
        config=config,
        language=language,
        source=source,
        log_callback=log_callback,
    )
    return outcome.segments
