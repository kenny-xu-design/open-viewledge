from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .utils import load_json


class AppConfig(BaseModel):
    output_dir: str = "output"
    whisper_model: str = "small"
    language: str = "zh"
    summary_backend: str = "deepseek"
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    keep_temp_files: bool = False
    generate_frames: bool = True
    transcript_group_seconds: int = 60
    transcript_group_max_segments: int = 12


def load_config(config_path: Path) -> AppConfig:
    data = load_json(config_path) if config_path.exists() else {}
    return AppConfig(**data)
