from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AdapterResult:
    metadata: dict[str, Any]
    adapter_name: str
    subtitle_path: Path | None = None
    transcript_path: Path | None = None
    media_path: Path | None = None
    comments_json_path: Path | None = None
    comments_md_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def has_transcript(self) -> bool:
        return bool(self.transcript_path and self.transcript_path.exists())
