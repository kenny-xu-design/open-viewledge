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
            {"name": name, "model": provider.model_name, "configured": provider.is_available()}
            for name, provider in self._providers.items()
        ]

    def resolve(self, requested: str, question: str, model: str | None = None) -> LLMProvider:
        name = requested.strip().lower() or "auto"
        if name == "auto":
            visual_terms = ("画面", "截图", "界面", "按钮", "图表", "图像", "视觉")
            name = "gemini" if any(term in question for term in visual_terms) else "deepseek"
            if name == "gemini" and not self._providers.get("gemini", _MissingProvider()).is_available():
                name = "deepseek"
        if name not in self._providers:
            raise ValueError("provider 只能是 auto、deepseek 或 gemini。")
        provider = self._providers[name]
        if model:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", model):
                raise ValueError("model 名称不合法。")
            provider.model_name = model
        if not provider.is_available():
            label = "Gemini" if name == "gemini" else "DeepSeek"
            raise UserFacingError(f"{label} 未配置，无法发送请求。")
        return provider


class _MissingProvider:
    def is_available(self) -> bool:
        return False
