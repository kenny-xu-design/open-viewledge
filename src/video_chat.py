from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .providers.llm import GeminiProvider, GeminiUploadedFile
from .providers.llm.base import LLMResponse
from .utils import UserFacingError


VIDEO_ROUTES = (
    "gemini_youtube_url",
    "gemini_files_api",
    "gemini_frames_text",
    "text_only",
)


@dataclass(frozen=True)
class VideoChatResult:
    response: LLMResponse
    route: str
    route_status: str
    degradation_reason: str = ""
    remote_file_id: str = ""
    remote_expires_at: str = ""
    attempts: list[dict[str, str]] = field(default_factory=list)


class GeminiVideoChatRouter:
    def __init__(self, provider: GeminiProvider) -> None:
        self.provider = provider

    def answer(
        self,
        messages: list[dict[str, Any]],
        *,
        source_url: str = "",
        media_path: Path | None = None,
        frame_paths: list[Path] | None = None,
        remote_file_id: str = "",
    ) -> VideoChatResult:
        attempts: list[dict[str, str]] = []
        reasons: list[str] = []

        if _is_youtube_url(source_url):
            try:
                response = self.provider.complete_with_video_url(
                    messages,
                    source_url,
                    max_tokens=1_500,
                )
            except UserFacingError as exc:
                self._failed(attempts, reasons, "gemini_youtube_url", exc)
            else:
                attempts.append({"route": "gemini_youtube_url", "status": "available", "reason": ""})
                return VideoChatResult(response, "gemini_youtube_url", "available", attempts=attempts)
        else:
            reason = "当前来源不是公开 YouTube URL。"
            attempts.append({"route": "gemini_youtube_url", "status": "failed", "reason": reason})
            reasons.append(f"gemini_youtube_url: {reason}")

        uploaded: GeminiUploadedFile | None = None
        if remote_file_id or (media_path and media_path.is_file()):
            try:
                if remote_file_id:
                    try:
                        uploaded = self.provider.get_uploaded_file(remote_file_id)
                    except (ValueError, UserFacingError) as exc:
                        if not media_path or not media_path.is_file():
                            raise
                        reasons.append(f"gemini_files_api remote recovery: {exc}")
                        uploaded = self.provider.upload_video(Path(media_path))
                else:
                    uploaded = self.provider.upload_video(Path(media_path))
                response = self.provider.complete_with_uploaded_file(
                    messages,
                    uploaded,
                    max_tokens=1_500,
                )
            except (OSError, ValueError, UserFacingError) as exc:
                self._failed(attempts, reasons, "gemini_files_api", exc)
            else:
                attempts.append({"route": "gemini_files_api", "status": "available", "reason": ""})
                return VideoChatResult(
                    response,
                    "gemini_files_api",
                    "available",
                    "；".join(reasons),
                    uploaded.name,
                    uploaded.expiration_time,
                    attempts,
                )
        else:
            reason = "知识包没有可上传的本地视频。"
            attempts.append({"route": "gemini_files_api", "status": "failed", "reason": reason})
            reasons.append(f"gemini_files_api: {reason}")

        usable_frames = [Path(path) for path in (frame_paths or []) if Path(path).is_file()][:8]
        if usable_frames:
            try:
                response = self.provider.generate_with_images(
                    _messages_as_prompt(messages),
                    usable_frames,
                    system_prompt="结合关键帧和只读字幕证据回答；无法确认的视觉信息必须明确说明。",
                    max_tokens=1_500,
                )
            except (OSError, ValueError, UserFacingError) as exc:
                self._failed(attempts, reasons, "gemini_frames_text", exc)
            else:
                attempts.append({"route": "gemini_frames_text", "status": "degraded", "reason": ""})
                return VideoChatResult(
                    response,
                    "gemini_frames_text",
                    "degraded",
                    "；".join(reasons),
                    attempts=attempts,
                )
        else:
            reason = "知识包没有可用关键帧。"
            attempts.append({"route": "gemini_frames_text", "status": "failed", "reason": reason})
            reasons.append(f"gemini_frames_text: {reason}")

        try:
            response = self.provider.complete(messages, max_tokens=1_500)
        except UserFacingError as exc:
            self._failed(attempts, reasons, "text_only", exc)
            raise UserFacingError("Gemini 视频对话及全部降级路由均失败。") from exc
        attempts.append({"route": "text_only", "status": "degraded", "reason": ""})
        return VideoChatResult(
            response,
            "text_only",
            "degraded",
            "；".join(reasons),
            attempts=attempts,
        )

    @staticmethod
    def _failed(
        attempts: list[dict[str, str]],
        reasons: list[str],
        route: str,
        exc: Exception,
    ) -> None:
        reason = str(exc)
        attempts.append({"route": route, "status": "failed", "reason": reason})
        reasons.append(f"{route}: {reason}")


def _is_youtube_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower().split(":", 1)[0]
    return parsed.scheme in {"http", "https"} and host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }


def _messages_as_prompt(messages: list[dict[str, Any]]) -> str:
    lines = []
    for item in messages:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n\n".join(lines)
