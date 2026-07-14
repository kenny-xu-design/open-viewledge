from __future__ import annotations

from pathlib import Path

from .cleaner import format_transcript_segment
from .domain.models import TranscriptSegment
from .utils import UserFacingError, console, write_text


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

    segments = transcribe_segments(audio_path, language=language, source="asr")
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
) -> list[TranscriptSegment]:
    if not audio_path.exists():
        raise UserFacingError(f"音频文件不存在：{audio_path}")

    local_model_path = LOCAL_WHISPER_MODEL_DIR.resolve()
    if not (local_model_path / "model.bin").exists():
        raise UserFacingError(LOCAL_WHISPER_MODEL_HINT)

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise UserFacingError("未安装 faster-whisper。请先运行 pip install -r requirements.txt。") from exc

    try:
        console.print(f"使用本地 faster-whisper 模型：{local_model_path}")
        model = WhisperModel(str(local_model_path), device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), language=language or None, vad_filter=True)
        items = [
            TranscriptSegment(
                index=index,
                start=float(segment.start),
                end=float(segment.end),
                text=segment.text.strip(),
                language=language or "",
                source=source,
            )
            for index, segment in enumerate(segments)
            if segment.text.strip()
        ]
    except Exception as exc:
        raise UserFacingError(f"faster-whisper 转写失败：{exc}") from exc

    if not items:
        raise UserFacingError("转写完成，但没有得到有效文本。")
    return items
