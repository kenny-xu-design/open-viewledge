from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..domain.models import SourceRecord


class SourceAdapter(ABC):
    @classmethod
    @abstractmethod
    def supports(cls, input_value: str) -> bool: ...

    @abstractmethod
    def resolve(self, input_value: str) -> SourceRecord: ...

    @abstractmethod
    def collect_metadata(self) -> SourceRecord: ...

    @abstractmethod
    def acquire_subtitles(self, work_dir: Path, language: str) -> Path | None: ...

    @abstractmethod
    def acquire_media(
        self,
        work_dir: Path,
        sample_seconds: int | None = None,
        *,
        audio_only: bool = False,
    ) -> Path: ...
