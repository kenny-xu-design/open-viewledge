from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlparse

from ..domain.models import SourceRecord
from ..downloader import _download_media_for_transcription, _download_subtitle, _import_ytdlp
from ..utils import UserFacingError
from .base import SourceAdapter


class YtdlpSource(SourceAdapter):
    def __init__(self) -> None:
        self.url = ""
        self.info: dict = {}
        self.record: SourceRecord | None = None
        self._yt_dlp = None

    @classmethod
    def supports(cls, input_value: str) -> bool:
        return urlparse(input_value).scheme in {"http", "https"} or bool(_BV_RE.fullmatch(input_value.strip()))

    def resolve(self, input_value: str) -> SourceRecord:
        if not self.supports(input_value):
            raise UserFacingError(f"不是可识别的公开视频 URL：{input_value}")
        self.url = normalize_bilibili_input(input_value)
        self._yt_dlp = _import_ytdlp()
        self.record = SourceRecord(
            source_type="online_video",
            platform=_platform_from_url(self.url),
            source_url=self.url,
            canonical_url=self.url,
            source_id=_source_id_from_url(self.url),
            title="online-video",
        )
        return self.record

    def collect_metadata(self) -> SourceRecord:
        if not self.record or not self._yt_dlp:
            raise RuntimeError("请先调用 resolve()。")
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
        try:
            with self._yt_dlp.YoutubeDL(opts) as ydl:
                self.info = ydl.extract_info(self.url, download=False)
        except Exception as exc:
            raise UserFacingError(f"视频链接无效或 yt-dlp 无法读取：{exc}") from exc
        info = self.info
        self.record = self.record.model_copy(update={
            "platform": _platform_from_info(info, self.url),
            "canonical_url": info.get("webpage_url") or self.url,
            "source_id": str(info.get("id") or self.record.source_id),
            "title": info.get("title") or "未命名视频",
            "author": info.get("uploader") or info.get("channel") or "未知",
            "published_at": str(info.get("upload_date") or info.get("release_date") or ""),
            "description": info.get("description") or "",
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail") or "",
            "language": info.get("language") or "",
            "chapters": info.get("chapters") or [],
        })
        return self.record

    def acquire_subtitles(self, work_dir: Path, language: str) -> Path | None:
        if not self._yt_dlp:
            raise RuntimeError("请先调用 resolve()。")
        return _download_subtitle(self._yt_dlp, self.url, work_dir, language)

    def acquire_media(
        self,
        work_dir: Path,
        sample_seconds: int | None = None,
        *,
        audio_only: bool = False,
    ) -> Path:
        if not self._yt_dlp:
            raise RuntimeError("请先调用 resolve()。")
        return _download_media_for_transcription(
            self._yt_dlp,
            self.url,
            work_dir,
            sample_seconds,
            audio_only=audio_only,
        )


def _platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "bilibili.com" in host or "b23.tv" in host:
        return "bilibili"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return "yt-dlp"


_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}", re.IGNORECASE)


def is_bilibili_input(value: str) -> bool:
    stripped = value.strip()
    if _BV_RE.fullmatch(stripped):
        return True
    host = urlparse(stripped).netloc.lower()
    return "bilibili.com" in host or "b23.tv" in host


def normalize_bilibili_input(value: str) -> str:
    stripped = value.strip()
    if _BV_RE.fullmatch(stripped):
        return f"https://www.bilibili.com/video/{stripped}"
    return stripped


def _platform_from_info(info: dict, url: str) -> str:
    initial = _platform_from_url(url)
    if initial != "yt-dlp":
        return initial
    return str(info.get("extractor_key") or info.get("extractor") or initial).lower()


def _source_id_from_url(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
