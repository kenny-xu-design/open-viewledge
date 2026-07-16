from __future__ import annotations

import json
import os
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

    def generate_with_images(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise UserFacingError("Gemini 关键帧视觉问答将在下一阶段接入。")
