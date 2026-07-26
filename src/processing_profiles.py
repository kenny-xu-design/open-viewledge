from __future__ import annotations

from typing import Literal, cast


ProcessingProfile = Literal["fast", "complete"]

DEFAULT_PROCESSING_PROFILE: ProcessingProfile = "complete"
SUPPORTED_PROCESSING_PROFILES = ("fast", "complete")


def normalize_processing_profile(value: str | None) -> ProcessingProfile:
    normalized = str(value or DEFAULT_PROCESSING_PROFILE).strip().lower()
    if normalized not in SUPPORTED_PROCESSING_PROFILES:
        supported = " / ".join(SUPPORTED_PROCESSING_PROFILES)
        raise ValueError(f"processing_profile 参数不合法：{value}。支持的模式：{supported}。")
    return cast(ProcessingProfile, normalized)
