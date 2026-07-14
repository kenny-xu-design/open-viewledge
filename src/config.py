from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .utils import load_json


class AppConfig(BaseModel):
    output_dir: str = "output"
    whisper_model: str = "small"
    language: str = "zh"
    summary_backend: str = "ollama"
    ollama_model: str = "auto"
    ollama_base_url: str = "http://localhost:11434"
    openai_model: str = "gpt-4o-mini"
    keep_temp_files: bool = False
    privacy_mode: bool = False
    generate_frames: bool = True
    transcript_group_seconds: int = 60
    transcript_group_max_segments: int = 12


def load_config(config_path: Path) -> AppConfig:
    data = load_json(config_path) if config_path.exists() else {}
    return AppConfig(**data)
