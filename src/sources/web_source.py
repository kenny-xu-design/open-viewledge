from __future__ import annotations

from pathlib import Path

from ..domain.models import SourceRecord
from .base import SourceAdapter


class WebSource(SourceAdapter):
    @classmethod
    def supports(cls, input_value: str) -> bool:
        return False

    def resolve(self, input_value: str) -> SourceRecord:
        raise NotImplementedError("普通网页正文采集将在后续阶段实现。")

    def collect_metadata(self) -> SourceRecord:
        raise NotImplementedError("普通网页正文采集将在后续阶段实现。")

    def acquire_subtitles(self, work_dir: Path, language: str) -> Path | None:
        raise NotImplementedError("普通网页没有视频字幕接口。")

    def acquire_media(
        self,
        work_dir: Path,
        sample_seconds: int | None = None,
        *,
        audio_only: bool = False,
    ) -> Path:
        raise NotImplementedError("普通网页媒体采集将在后续阶段实现。")
