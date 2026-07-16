from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..providers.llm.base import LLMProvider, LLMResponse
from ..utils import UserFacingError


@dataclass(frozen=True)
class VisualAnalysisResult:
    status: Literal["success", "skipped"]
    frame_count: int
    message: str = ""
    response: LLMResponse | None = None


class KeyframeAnalysisService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def analyze(
        self,
        frame_paths: list[Path],
        prompt: str,
        *,
        system_prompt: str = "",
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> VisualAnalysisResult:
        if not frame_paths:
            return VisualAnalysisResult(
                status="skipped",
                frame_count=0,
                message="没有可用关键帧，已跳过 Gemini 视觉分析。",
            )
        if not self.provider.supports_images:
            raise UserFacingError(f"{self.provider.name} 不支持关键帧图片输入。")
        if not self.provider.is_available():
            raise UserFacingError("Gemini 未配置，无法执行关键帧视觉分析。")
        response = self.provider.generate_with_images(
            prompt,
            frame_paths,
            system_prompt=system_prompt,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )
        return VisualAnalysisResult(
            status="success",
            frame_count=len(frame_paths),
            response=response,
        )
