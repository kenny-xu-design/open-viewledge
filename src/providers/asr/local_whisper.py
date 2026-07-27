from __future__ import annotations

from pathlib import Path

from ...asr_runtime import (
    ASRSettings,
    ASRTelemetry,
    has_local_asr_model,
    transcribe_with_local_asr,
)
from ...domain.models import TranscriptSegment
from .base import ASRProvider


class LocalWhisperProvider(ASRProvider):
    name = "local-faster-whisper"
    model_name = "faster-whisper-small"

    def __init__(
        self,
        config: object | None = None,
        *,
        device: str = "",
        fallback_enabled: bool = True,
    ) -> None:
        if config is not None and device:
            config = config.model_copy(
                update={
                    "asr_device": device,
                    "asr_compute_type": "int8" if device == "cpu" else "",
                    "asr_fallback_enabled": fallback_enabled,
                }
            )
        self.config = config
        self.telemetry = ASRTelemetry(profile=ASRSettings.from_config(config).profile)

    def is_available(self) -> bool:
        return has_local_asr_model(self.config)

    def transcribe(self, audio_path: Path, context: object) -> list[TranscriptSegment]:
        config = self.config or getattr(context, "config", None)
        language = getattr(config, "language", "zh")
        log_callback = getattr(context, "log", None)
        outcome = transcribe_with_local_asr(
            audio_path,
            config=config,
            language=language,
            source="asr",
            log_callback=log_callback,
        )
        self.telemetry = outcome.telemetry
        self.model_name = outcome.telemetry.model
        return outcome.segments
