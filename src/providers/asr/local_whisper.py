from __future__ import annotations

from pathlib import Path

from ...domain.models import TranscriptSegment
from ...transcriber import LOCAL_WHISPER_MODEL_DIR, transcribe_segments
from .base import ASRProvider


class LocalWhisperProvider(ASRProvider):
    name = "local-faster-whisper"
    model_name = "faster-whisper-small"

    def is_available(self) -> bool:
        return (LOCAL_WHISPER_MODEL_DIR.resolve() / "model.bin").exists()

    def transcribe(self, audio_path: Path, context: object) -> list[TranscriptSegment]:
        language = getattr(getattr(context, "config", None), "language", "zh")
        return transcribe_segments(audio_path, language=language, source="asr")

