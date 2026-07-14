from __future__ import annotations

from pathlib import Path

from ..downloader import metadata_from_local_file
from .base import AdapterResult


class LocalFileAdapter:
    name = "local-file"

    def fetch(self, file_path: Path, metadata_path: Path) -> AdapterResult:
        metadata = metadata_from_local_file(file_path, metadata_path)
        return AdapterResult(
            metadata=metadata,
            adapter_name=self.name,
            media_path=file_path,
        )
