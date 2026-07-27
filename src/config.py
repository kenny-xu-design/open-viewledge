from __future__ import annotations

from pathlib import Path
import os

from pydantic import BaseModel, Field, ValidationError, field_validator

from .defaults import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_SUMMARY_BACKEND,
)
from .utils import load_json
from .schema_compat import UnsupportedSchemaVersion, require_supported_schema

VIEWLEDGE_OUTPUT_ROOT_ENV = "VIEWLEDGE_OUTPUT_ROOT"


class AppConfig(BaseModel):
    schema_version: str = "1.0"
    output_dir: str = "output"
    whisper_model: str = "small"
    asr_profile: str = "balanced"
    asr_model: str = ""
    asr_device: str = ""
    asr_compute_type: str = ""
    asr_task: str = "transcribe"
    asr_logprob_threshold: float = -1.0
    asr_compression_ratio_threshold: float = Field(default=2.4, gt=0)
    asr_no_speech_threshold: float = Field(default=0.6, ge=0, le=1)
    asr_language_probability_threshold: float = Field(default=0.5, ge=0, le=1)
    asr_low_confidence_ratio_threshold: float = Field(default=0.2, ge=0, le=1)
    asr_gap_retry_seconds: float = Field(default=30.0, ge=5)
    asr_max_local_retries: int = Field(default=8, ge=0, le=50)
    cloud_asr_provider: str = "groq"
    cloud_asr_model: str = "whisper-large-v3-turbo"
    cloud_asr_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    cloud_asr_max_retries: int = Field(default=2, ge=0, le=10)
    cloud_asr_file_limit_mb: float = Field(default=25, gt=0)
    cloud_asr_chunk_overlap_seconds: float = Field(default=2, ge=0, le=30)
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
    obsidian_vault_path: str = ""
    obsidian_vault_name: str = ""
    obsidian_export_subdir: str = "外源/视频"
    obsidian_export_overwrite: bool = False

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        return require_supported_schema(value, supported_major=1, object_name="配置文件")

    @field_validator("asr_profile")
    @classmethod
    def validate_asr_profile(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"fast", "balanced", "quality"}:
            raise ValueError("asr_profile 必须是 fast、balanced 或 quality。")
        return normalized

    @field_validator("asr_task")
    @classmethod
    def validate_asr_task(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"transcribe", "translate"}:
            raise ValueError("asr_task 必须是 transcribe 或 translate。")
        return normalized


def load_config(config_path: Path) -> AppConfig:
    data = load_json(config_path) if config_path.exists() else {}
    env_values = {
        "output_dir": os.getenv(VIEWLEDGE_OUTPUT_ROOT_ENV, ""),
        "asr_profile": os.getenv("ASR_PROFILE", ""),
        "asr_model": os.getenv("ASR_MODEL", ""),
        "asr_device": os.getenv("ASR_DEVICE", ""),
        "asr_compute_type": os.getenv("ASR_COMPUTE_TYPE", ""),
        "asr_task": os.getenv("ASR_TASK", ""),
        "asr_logprob_threshold": os.getenv("ASR_LOGPROB_THRESHOLD", ""),
        "asr_compression_ratio_threshold": os.getenv("ASR_COMPRESSION_RATIO_THRESHOLD", ""),
        "asr_no_speech_threshold": os.getenv("ASR_NO_SPEECH_THRESHOLD", ""),
        "asr_language_probability_threshold": os.getenv(
            "ASR_LANGUAGE_PROBABILITY_THRESHOLD", ""
        ),
        "asr_low_confidence_ratio_threshold": os.getenv(
            "ASR_LOW_CONFIDENCE_RATIO_THRESHOLD", ""
        ),
        "asr_gap_retry_seconds": os.getenv("ASR_GAP_RETRY_SECONDS", ""),
        "asr_max_local_retries": os.getenv("ASR_MAX_LOCAL_RETRIES", ""),
        "cloud_asr_provider": os.getenv("CLOUD_ASR_PROVIDER", ""),
        "cloud_asr_model": os.getenv("CLOUD_ASR_MODEL", ""),
        "cloud_asr_timeout_seconds": os.getenv("CLOUD_ASR_TIMEOUT_SECONDS", ""),
        "cloud_asr_max_retries": os.getenv("CLOUD_ASR_MAX_RETRIES", ""),
        "cloud_asr_file_limit_mb": os.getenv("CLOUD_ASR_FILE_LIMIT_MB", ""),
        "cloud_asr_chunk_overlap_seconds": os.getenv(
            "CLOUD_ASR_CHUNK_OVERLAP_SECONDS", ""
        ),
        "obsidian_vault_path": os.getenv("OBSIDIAN_VAULT_PATH", ""),
        "obsidian_vault_name": os.getenv("OBSIDIAN_VAULT_NAME", ""),
        "obsidian_export_subdir": os.getenv("OBSIDIAN_EXPORT_SUBDIR", ""),
        "obsidian_export_overwrite": os.getenv("OBSIDIAN_EXPORT_OVERWRITE", "").lower() in {"1", "true", "yes"},
    }
    for key, value in env_values.items():
        if value not in {"", False}:
            data[key] = value
    try:
        return AppConfig(**data)
    except (ValidationError, UnsupportedSchemaVersion) as exc:
        from .utils import UserFacingError

        raise UserFacingError(f"配置文件无效：{exc}") from exc


def resolve_output_root(config: AppConfig, project_root: Path | None = None) -> Path:
    path = Path(config.output_dir).expanduser()
    if path.is_absolute():
        return path.resolve()
    base = project_root if project_root is not None else Path.cwd()
    return (base / path).resolve()
