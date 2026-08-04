from __future__ import annotations

import re


DEFAULT_SUMMARY_BACKEND = "deepseek"

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def normalize_deepseek_model(value: str | None) -> str:
    """Map console display/version labels to the official API model ID."""

    model = str(value or "").strip()
    folded = model.casefold().replace("_", "-")
    if folded in {"deepseek-v4-flash", "deepseek-v4-pro"}:
        return folded
    if re.fullmatch(r"deepseek-v4-flash-\d{4}", folded):
        return DEFAULT_DEEPSEEK_MODEL
    return model


DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_ASR_MODEL = "whisper-large-v3-turbo"
