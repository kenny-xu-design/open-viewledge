from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .defaults import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_SUMMARY_BACKEND,
)
from .utils import load_json


class AppConfig(BaseModel):
    output_dir: str = "output"
    whisper_model: str = "small"
    language: str = "zh"
    summary_backend: str = DEFAULT_SUMMARY_BACKEND
    deepseek_model: str = DEFAULT_DEEPSEEK_MODEL
    deepseek_base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    gemini_model: str = DEFAULT_GEMINI_MODEL
    gemini_base_url: str = DEFAULT_GEMINI_BASE_URL
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    keep_temp_files: bool = False
    generate_frames: bool = True
    transcript_group_seconds: int = 60
    transcript_group_max_segments: int = 12


def load_config(config_path: Path) -> AppConfig:
    data = load_json(config_path) if config_path.exists() else {}
    return AppConfig(**data)
