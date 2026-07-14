from __future__ import annotations

import hashlib
from pathlib import Path

from ..domain.models import SourceRecord
from ..utils import UserFacingError
from .base import SourceAdapter

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}


class LocalMediaSource(SourceAdapter):
    def __init__(self) -> None:
        self.path: Path | None = None
        self.record: SourceRecord | None = None

    @classmethod
    def supports(cls, input_value: str) -> bool:
        return Path(input_value).suffix.lower() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

    def resolve(self, input_value: str) -> SourceRecord:
        path = Path(input_value).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise UserFacingError(f"本地媒体文件不存在：{path}")
        suffix = path.suffix.lower()
        if suffix not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
            raise UserFacingError(f"暂不支持该本地媒体格式：{suffix}")
        self.path = path
        self.record = SourceRecord(
            source_type="local_audio" if suffix in AUDIO_EXTENSIONS else "local_video",
            platform="local",
            source_id=_local_stable_id(path),
            local_path=str(path),
            title=path.stem,
        )
        return self.record

    def collect_metadata(self) -> SourceRecord:
        if not self.record:
            raise RuntimeError("请先调用 resolve()。")
        return self.record

    def acquire_subtitles(self, work_dir: Path, language: str) -> Path | None:
        return None

    def acquire_media(self, work_dir: Path, sample_seconds: int | None = None) -> Path:
        if not self.path:
            raise RuntimeError("请先调用 resolve()。")
        return self.path


def _local_stable_id(path: Path) -> str:
    digest = hashlib.sha256()
    stat = path.stat()
    digest.update(str(stat.st_size).encode("ascii"))
    with path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
        if stat.st_size > 1024 * 1024:
            handle.seek(max(0, stat.st_size - 1024 * 1024))
            digest.update(handle.read(1024 * 1024))
    return digest.hexdigest()[:12]
