from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str
    model_name: str
    is_cloud: bool = False

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def generate(self, request: str, context: object) -> str: ...

