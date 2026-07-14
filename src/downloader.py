from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .utils import UserFacingError, ensure_dir, format_seconds, now_iso, save_json


def _import_ytdlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise UserFacingError(_missing_ytdlp_message()) from exc
    return yt_dlp


def _missing_ytdlp_message() -> str:
    return "\n".join(
        [
            "未安装 yt-dlp，当前 Python 环境无法解析 URL 视频。",
            f"当前 sys.executable：{sys.executable}",
            f"当前工作目录：{Path.cwd()}",
            "建议执行：python -m pip install -r requirements.txt",
            "如果使用项目虚拟环境，请先用 .venv\\Scripts\\python.exe 启动 CLI 或 Web UI。",
        ]
    )


def metadata_from_local_file(file_path: Path, metadata_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        raise UserFacingError(f"本地视频文件不存在：{file_path}")
    metadata = {
        "title": file_path.stem,
        "source": "local_file",
        "source_path": str(file_path),
        "author": "未知",
        "duration": "未知",
        "processed_at": now_iso(),
    }
    save_json(metadata_path, metadata)
    return metadata


def fetch_url_resources(
    url: str,
    work_dir: Path,
    metadata_path: Path,
    language: str = "zh",
) -> tuple[dict[str, Any], Path | None, Path | None]:
    yt_dlp = _import_ytdlp()
    ensure_dir(work_dir)

    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise UserFacingError(f"视频链接无效或 yt-dlp 无法读取：{exc}") from exc

    metadata = _build_metadata(info, url)
    save_json(metadata_path, metadata)

    subtitle_path = _download_subtitle(yt_dlp, url, work_dir, language)
    media_path: Path | None = None
    if subtitle_path is None:
        media_path = _download_media_for_transcription(yt_dlp, url, work_dir)
    return metadata, subtitle_path, media_path


def _build_metadata(info: dict[str, Any], url: str) -> dict[str, Any]:
    return {
        "title": info.get("title") or "未命名视频",
        "source": info.get("extractor_key") or info.get("extractor") or "url",
        "source_url": url,
        "author": info.get("uploader") or info.get("channel") or "未知",
        "duration": format_seconds(info.get("duration")),
        "duration_seconds": info.get("duration"),
        "processed_at": now_iso(),
    }


def _download_subtitle(yt_dlp: Any, url: str, work_dir: Path, language: str) -> Path | None:
    subtitle_dir = ensure_dir(work_dir / "subtitles")
    existing = _subtitle_candidates(subtitle_dir, language)
    if existing:
        return existing[0]

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "subtitlesformat": "vtt/srt",
        "subtitleslangs": _subtitle_languages(language),
        "outtmpl": str(subtitle_dir / "%(title).80s.%(ext)s"),
        "noplaylist": True,
    }
    # Official subtitles are attempted separately so an automatic/translated
    # track failure cannot invalidate a subtitle file that already succeeded.
    for allow_automatic in (False, True):
        opts = {**base_opts, "writeautomaticsub": allow_automatic}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception:
            pass
        candidates = _subtitle_candidates(subtitle_dir, language)
        if candidates:
            return candidates[0]
    return None


def _subtitle_languages(language: str) -> list[str]:
    normalized = (language or "zh").strip()
    if normalized.lower().startswith("zh"):
        values = [normalized, "zh-Hans", "zh-Hant", "zh", "en"]
    elif normalized.lower().startswith("en"):
        values = [normalized, "en", "en-US", "en-GB"]
    else:
        values = [normalized, "zh-Hans", "en"]
    return list(dict.fromkeys(value for value in values if value))


def _subtitle_candidates(subtitle_dir: Path, language: str) -> list[Path]:
    candidates = [path for path in subtitle_dir.rglob("*") if path.suffix.lower() in {".srt", ".vtt"}]
    token = f".{language}.".lower()
    return sorted(candidates, key=lambda path: (token not in path.name.lower(), path.suffix.lower() != ".vtt", path.name.lower()))


def _download_media_for_transcription(
    yt_dlp: Any,
    url: str,
    work_dir: Path,
    sample_seconds: int | None = None,
) -> Path:
    media_dir = ensure_dir(work_dir / "media")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": str(media_dir / "source.%(ext)s"),
        "noplaylist": True,
    }
    if sample_seconds:
        opts["download_sections"] = [f"*0-{sample_seconds}"]
        opts["force_keyframes_at_cuts"] = True
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        raise UserFacingError(f"视频没有可用字幕，且下载音频用于转写失败：{exc}") from exc

    candidates = sorted(p for p in media_dir.iterdir() if p.is_file())
    if not candidates:
        raise UserFacingError("视频没有可用字幕，且 yt-dlp 未能生成音频或视频文件。")
    return candidates[0]
