from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:  # type: ignore[no-redef]
        return False

from ...defaults import DEFAULT_GEMINI_BASE_URL, DEFAULT_GEMINI_MODEL
from ...utils import UserFacingError
from .base import LLMProvider, LLMResponse


@dataclass(frozen=True)
class GeminiUploadedFile:
    name: str
    uri: str
    mime_type: str
    state: str
    expiration_time: str = ""


class GeminiProvider(LLMProvider):
    name = "gemini"
    is_cloud = True
    supports_images = True
    supports_video = True

    MAX_INLINE_IMAGES = 12
    MAX_INLINE_IMAGE_BYTES = 18 * 1024 * 1024
    IMAGE_MIME_TYPES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    VIDEO_MIME_TYPES = {
        ".mp4": "video/mp4",
        ".mpeg": "video/mpeg",
        ".mpg": "video/mpg",
        ".mov": "video/mov",
        ".avi": "video/avi",
        ".flv": "video/x-flv",
        ".webm": "video/webm",
        ".wmv": "video/wmv",
        ".3gp": "video/3gpp",
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        opener: Any | None = None,
        sleeper: Any | None = None,
        prefer_env: bool = True,
    ) -> None:
        load_dotenv()
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        env_base_url = os.getenv("GEMINI_BASE_URL") if prefer_env else ""
        env_model = os.getenv("GEMINI_MODEL") if prefer_env else ""
        self.base_url = (env_base_url or base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        self.model_name = env_model or model_name or DEFAULT_GEMINI_MODEL
        self._opener = opener or urlopen
        self._sleep = sleeper or time.sleep

    def is_available(self) -> bool:
        return bool(self.api_key.strip())

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not self.is_available():
            raise UserFacingError("Gemini 未配置，请在项目 .env 中设置 GEMINI_API_KEY。")
        system_parts = [str(item.get("content") or "") for item in messages if item.get("role") == "system"]
        contents = []
        for item in messages:
            role = str(item.get("role") or "user")
            if role == "system":
                continue
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": str(item.get("content") or "")}],
                }
            )
        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        return self._generate(payload)

    def generate_with_images(
        self,
        prompt: str,
        image_paths: list[Path],
        *,
        system_prompt: str = "",
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("Gemini 图片分析 prompt 不能为空。")
        if not image_paths:
            raise UserFacingError("未提供关键帧，本次不会调用 Gemini。")
        if len(image_paths) > self.MAX_INLINE_IMAGES:
            raise UserFacingError(f"Gemini 单次最多处理 {self.MAX_INLINE_IMAGES} 张关键帧。")
        if not self.is_available():
            raise UserFacingError("Gemini 未配置，请在项目 .env 中设置 GEMINI_API_KEY。")

        parts: list[dict[str, Any]] = [{"text": normalized_prompt}]
        total_bytes = 0
        for raw_path in image_paths:
            path = Path(raw_path)
            if not path.is_file():
                raise UserFacingError(f"关键帧文件不存在：{path}")
            mime_type = self.IMAGE_MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
            if mime_type not in set(self.IMAGE_MIME_TYPES.values()):
                raise UserFacingError(f"不支持的关键帧格式：{path.suffix or path.name}")
            data = path.read_bytes()
            total_bytes += len(data)
            if total_bytes > self.MAX_INLINE_IMAGE_BYTES:
                raise UserFacingError("关键帧总大小超过 18 MiB，请减少图片数量或尺寸。")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(data).decode("ascii"),
                    }
                }
            )

        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        if system_prompt.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_prompt.strip()}]}
        return self._generate(payload)

    def complete_with_video_url(
        self,
        messages: list[dict[str, Any]],
        video_url: str,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        normalized_url = video_url.strip()
        if not normalized_url:
            raise ValueError("Gemini YouTube URL 不能为空。")
        payload = self._messages_payload(
            messages,
            media_part={"file_data": {"file_uri": normalized_url}},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._generate(payload)

    def complete_with_uploaded_file(
        self,
        messages: list[dict[str, Any]],
        uploaded_file: GeminiUploadedFile,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if uploaded_file.state != "ACTIVE":
            raise UserFacingError("Gemini 视频文件尚未处理完成，暂时不能用于对话。")
        payload = self._messages_payload(
            messages,
            media_part={
                "file_data": {
                    "mime_type": uploaded_file.mime_type,
                    "file_uri": uploaded_file.uri,
                }
            },
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._generate(payload)

    def upload_video(
        self,
        video_path: Path,
        *,
        max_polls: int = 30,
        poll_interval: float = 2.0,
    ) -> GeminiUploadedFile:
        if not self.is_available():
            raise UserFacingError("Gemini 未配置，请在项目 .env 中设置 GEMINI_API_KEY。")
        path = Path(video_path)
        if not path.is_file():
            raise UserFacingError("待上传的视频文件不存在。")
        mime_type = self.VIDEO_MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
        if mime_type not in set(self.VIDEO_MIME_TYPES.values()):
            raise UserFacingError(f"Gemini Files API 不支持该视频格式：{path.suffix or path.name}")
        size = path.stat().st_size
        upload_root = self.base_url.rsplit("/v1beta", 1)[0]
        start_request = Request(
            f"{upload_root}/upload/v1beta/files",
            data=json.dumps({"file": {"display_name": path.name}}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(size),
                "X-Goog-Upload-Header-Content-Type": mime_type,
            },
            method="POST",
        )
        try:
            with self._opener(start_request, timeout=90) as response:
                upload_url = str(response.headers.get("X-Goog-Upload-URL") or "")
            if not upload_url:
                raise UserFacingError("Gemini Files API 未返回上传地址。")
            upload_request = Request(
                upload_url,
                data=_file_chunks(path),
                headers={
                    "Content-Length": str(size),
                    "Content-Type": mime_type,
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                method="POST",
            )
            with self._opener(upload_request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except (URLError, TimeoutError) as exc:
            raise UserFacingError("Gemini 视频上传超时或网络不可用，请稍后重试。") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise UserFacingError("Gemini 视频上传响应无效。") from exc

        uploaded = self._uploaded_file(payload.get("file") if isinstance(payload, dict) else None)
        for _ in range(max(0, max_polls)):
            if uploaded.state == "ACTIVE":
                return uploaded
            if uploaded.state == "FAILED":
                raise UserFacingError("Gemini 无法处理上传的视频文件。")
            if uploaded.state not in {"PROCESSING", "STATE_UNSPECIFIED", ""}:
                raise UserFacingError(f"Gemini 视频文件状态异常：{uploaded.state}。")
            self._sleep(max(0.0, poll_interval))
            uploaded = self.get_uploaded_file(uploaded.name)
        if uploaded.state != "ACTIVE":
            raise UserFacingError("Gemini 视频文件处理超时，请稍后重试。")
        return uploaded

    def get_uploaded_file(self, name: str) -> GeminiUploadedFile:
        normalized = name.strip().lstrip("/")
        if not normalized.startswith("files/"):
            raise ValueError("Gemini 文件资源名称不合法。")
        request = Request(
            f"{self.base_url}/{normalized}",
            headers={"x-goog-api-key": self.api_key},
            method="GET",
        )
        try:
            with self._opener(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except (URLError, TimeoutError) as exc:
            raise UserFacingError("Gemini 文件状态查询超时或网络不可用。") from exc
        except json.JSONDecodeError as exc:
            raise UserFacingError("Gemini 文件状态响应无效。") from exc
        return self._uploaded_file(payload)

    def _messages_payload(
        self,
        messages: list[dict[str, Any]],
        *,
        media_part: dict[str, Any],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        system_parts = [str(item.get("content") or "") for item in messages if item.get("role") == "system"]
        contents: list[dict[str, Any]] = []
        media_attached = False
        for item in messages:
            role = str(item.get("role") or "user")
            if role == "system":
                continue
            parts: list[dict[str, Any]] = []
            if role != "assistant" and not media_attached:
                parts.append(media_part)
                media_attached = True
            parts.append({"text": str(item.get("content") or "")})
            contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
        if not media_attached:
            contents.append({"role": "user", "parts": [media_part, {"text": "请分析该视频。"}]})
        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        payload: dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        return payload

    @staticmethod
    def _uploaded_file(payload: Any) -> GeminiUploadedFile:
        if not isinstance(payload, dict):
            raise UserFacingError("Gemini Files API 返回内容为空或格式异常。")
        name = str(payload.get("name") or "")
        uri = str(payload.get("uri") or "")
        if not name or not uri:
            raise UserFacingError("Gemini Files API 未返回可复用的文件引用。")
        return GeminiUploadedFile(
            name=name,
            uri=uri,
            mime_type=str(payload.get("mimeType") or payload.get("mime_type") or "video/mp4"),
            state=str(payload.get("state") or ""),
            expiration_time=str(payload.get("expirationTime") or payload.get("expiration_time") or ""),
        )

    @staticmethod
    def _http_error(exc: HTTPError) -> UserFacingError:
        if exc.code in {401, 403}:
            return UserFacingError("Gemini 鉴权失败，请检查 GEMINI_API_KEY。")
        if exc.code == 429:
            return UserFacingError("Gemini 请求过于频繁或额度不足，请稍后重试。")
        return UserFacingError(f"Gemini 请求失败：HTTP {exc.code}。")

    def _generate(self, payload: dict[str, Any]) -> LLMResponse:
        if not self.is_available():
            raise UserFacingError("Gemini 未配置，请在项目 .env 中设置 GEMINI_API_KEY。")
        request = Request(
            f"{self.base_url}/models/{self.model_name}:generateContent",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with self._opener(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except (URLError, TimeoutError) as exc:
            raise UserFacingError("Gemini 请求超时或网络不可用，请检查网络后重试。") from exc
        try:
            candidate = data["candidates"][0]
            content = "".join(str(part.get("text") or "") for part in candidate["content"]["parts"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise UserFacingError("Gemini 返回内容为空或格式异常。") from exc
        if not content:
            raise UserFacingError("Gemini 返回内容为空。")
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            content=content,
            provider=self.name,
            model=str(data.get("modelVersion") or self.model_name),
            finish_reason=str(candidate.get("finishReason") or ""),
            usage={
                key: int(usage[source])
                for key, source in {
                    "prompt_tokens": "promptTokenCount",
                    "completion_tokens": "candidatesTokenCount",
                    "total_tokens": "totalTokenCount",
                }.items()
                if usage.get(source) is not None
            },
        )


def _file_chunks(path: Path, chunk_size: int = 1024 * 1024):
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk
