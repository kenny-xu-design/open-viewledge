from __future__ import annotations

from pathlib import Path

from ..sources.ytdlp_source import is_bilibili_input, normalize_bilibili_input
from .base import AdapterResult
from .ytdlp_adapter import YtdlpAdapter


def is_bilibili_url(value: str) -> bool:
    """Compatibility name retained for callers that also pass a bare BV id."""
    return is_bilibili_input(value)


class BilibiliAdapter:
    """Project-owned Bilibili compatibility adapter backed only by yt-dlp."""

    name = "bilibili-ytdlp"

    @property
    def available(self) -> bool:
        return True

    def fetch(
        self,
        url: str,
        work_dir: Path,
        metadata_path: Path,
        transcript_path: Path,
        comments_json_path: Path,
        comments_md_path: Path,
        comments: bool = False,
    ) -> AdapterResult:
        result = YtdlpAdapter().fetch(
            normalize_bilibili_input(url),
            work_dir,
            metadata_path,
            comments=comments,
        )
        result.adapter_name = self.name
        return result
