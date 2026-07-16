from __future__ import annotations

import base64
import json
import mimetypes
import os
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


class GeminiProvider(LLMProvider):
    name = "gemini"
    is_cloud = True
    supports_images = True

    MAX_INLINE_IMAGES = 12
    MAX_INLINE_IMAGE_BYTES = 18 * 1024 * 1024
    IMAGE_MIME_TYPES = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        opener: Any | None = None,
    ) -> None:
        load_dotenv()
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.base_url = (os.getenv("GEMINI_BASE_URL") or base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        self.model_name = os.getenv("GEMINI_MODEL") or model_name or DEFAULT_GEMINI_MODEL
        self._opener = opener or urlopen

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
            if exc.code in {401, 403}:
                raise UserFacingError("Gemini 鉴权失败，请检查 GEMINI_API_KEY。") from exc
            if exc.code == 429:
                raise UserFacingError("Gemini 请求过于频繁或额度不足，请稍后重试。") from exc
            raise UserFacingError(f"Gemini 请求失败：HTTP {exc.code}。") from exc
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
