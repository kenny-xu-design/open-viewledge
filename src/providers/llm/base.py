from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...utils import UserFacingError


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(ABC):
    name: str
    model_name: str
    is_cloud: bool = False
    supports_images: bool = False
    supports_video: bool = False

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

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
        raise UserFacingError(f"{self.name} 不支持图片输入。")
