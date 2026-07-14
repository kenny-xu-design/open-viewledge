from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ...domain.models import TranscriptSegment


class ASRProvider(ABC):
    name: str
    model_name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def transcribe(self, audio_path: Path, context: object) -> list[TranscriptSegment]: ...

