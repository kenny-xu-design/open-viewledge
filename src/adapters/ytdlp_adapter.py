from __future__ import annotations

from pathlib import Path

from ..downloader import fetch_url_resources
from .base import AdapterResult


class YtdlpAdapter:
    name = "yt-dlp"

    def fetch(
        self,
        url: str,
        work_dir: Path,
        metadata_path: Path,
        language: str = "zh",
        comments: bool = False,
    ) -> AdapterResult:
        metadata, subtitle_path, media_path = fetch_url_resources(
            url,
            work_dir,
            metadata_path,
            language,
        )
        warnings = []
        if comments:
            warnings.append("评论功能已停用，本次任务不会抓取或分析评论。")
        return AdapterResult(
            metadata=metadata,
            adapter_name=self.name,
            subtitle_path=subtitle_path,
            media_path=media_path,
            warnings=warnings,
        )
