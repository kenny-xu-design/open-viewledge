from __future__ import annotations

import os
from pathlib import Path

from ...summarizer import generate_report, resolve_ollama_model
from ...utils import UserFacingError, write_text
from .base import LLMProvider


class LegacyLLMProvider(LLMProvider):
    def __init__(self, backend: str, model_name: str) -> None:
        self.backend = backend
        self.name = f"legacy-{backend}"
        self.model_name = model_name
        self.is_cloud = backend != "ollama"

    def is_available(self) -> bool:
        return self.backend == "ollama" or bool(os.getenv("OPENAI_API_KEY"))

    def generate(self, request: str, context: object) -> str:
        if getattr(context, "privacy_mode", False) and self.is_cloud:
            raise UserFacingError("隐私模式已开启，禁止调用云端 LLM Provider。")
        output_dir = Path(getattr(context, "output_dir"))
        temp_dir = output_dir / "_temp"
        transcript_path = temp_dir / "analysis_input.md"
        prompt_path = temp_dir / "analysis_prompt.md"
        response_path = temp_dir / "analysis_response.txt"
        write_text(transcript_path, request)
        write_text(prompt_path, "请严格根据用户内容完成任务，不得编造。")
        config = getattr(context, "config")
        if self.backend == "ollama":
            self.model_name = resolve_ollama_model(config.ollama_base_url, config.ollama_model)
        result = generate_report(
            transcript_path, response_path, prompt_path,
            backend=self.backend,
            model=config.openai_model,
            ollama_model=self.model_name,
            ollama_base_url=config.ollama_base_url,
            report_name="结构化分析",
        )
        if result is None:
            raise UserFacingError("当前 LLM Provider 不可用，未生成分析结果。")
        return response_path.read_text(encoding="utf-8")
