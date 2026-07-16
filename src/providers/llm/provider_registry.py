from __future__ import annotations

import re
from typing import Any

from ...utils import UserFacingError
from .base import LLMProvider
from .deepseek import DeepSeekProvider
from .gemini import GeminiProvider


class ProviderRegistry:
    def __init__(self, providers: dict[str, LLMProvider] | None = None) -> None:
        self._providers = providers or {
            "deepseek": DeepSeekProvider(),
            "gemini": GeminiProvider(),
        }

    def statuses(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "model": provider.model_name,
                "configured": provider.is_available(),
                "capabilities": ["text", *(["images"] if provider.supports_images else [])],
            }
            for name, provider in self._providers.items()
        ]

    def resolve(
        self,
        requested: str,
        question: str,
        model: str | None = None,
        *,
        capability: str = "text",
    ) -> LLMProvider:
        if capability not in {"text", "images"}:
            raise ValueError("capability 只能是 text 或 images。")
        name = requested.strip().lower() or "auto"
        if name == "auto":
            name = "gemini" if capability == "images" else "deepseek"
        if name not in self._providers:
            raise ValueError("provider 只能是 auto、deepseek 或 gemini。")
        provider = self._providers[name]
        if model:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", model):
                raise ValueError("model 名称不合法。")
            provider.model_name = model
        if capability == "images" and not provider.supports_images:
            raise UserFacingError(f"{provider.name} 不支持图片输入。")
        if not provider.is_available():
            label = "Gemini" if name == "gemini" else "DeepSeek"
            raise UserFacingError(f"{label} 未配置，无法发送请求。")
        return provider
