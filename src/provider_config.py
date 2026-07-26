from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:  # type: ignore[no-redef]
        return False

from .defaults import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
)
from .providers.llm import DeepSeekProvider, GeminiProvider
from .providers.llm.base import LLMProvider
from .utils import UserFacingError


SUPPORTED_WEB_PROVIDERS = {"deepseek", "gemini"}


@dataclass
class ProviderSessionConfig:
    provider: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    updated_at: float = field(default_factory=time.time)
    last_test: dict[str, Any] = field(default_factory=dict)


class WebProviderConfigStore:
    """Process-local web session Provider configuration.

    API keys are intentionally kept in memory only. This object is created by
    the Web server process and is not serialized to job records, packages, or
    frontend storage.
    """

    def __init__(self) -> None:
        self._configs: dict[str, ProviderSessionConfig] = {}

    def set_config(
        self,
        provider: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> ProviderSessionConfig:
        name = normalize_provider_name(provider)
        current = self._configs.get(name) or ProviderSessionConfig(provider=name)
        current.api_key = str(api_key) if api_key is not None and str(api_key) else current.api_key
        if api_key is not None and not str(api_key):
            current.api_key = ""
        if base_url is not None:
            current.base_url = str(base_url).strip()
        if model is not None:
            current.model = str(model).strip()
        current.updated_at = time.time()
        self._configs[name] = current
        return current

    def set_last_test(self, provider: str, result: dict[str, Any]) -> None:
        name = normalize_provider_name(provider)
        current = self._configs.get(name) or ProviderSessionConfig(provider=name)
        current.last_test = dict(result)
        current.updated_at = time.time()
        self._configs[name] = current

    def get(self, provider: str) -> ProviderSessionConfig | None:
        return self._configs.get(normalize_provider_name(provider))

    def clear(self, provider: str) -> None:
        self._configs.pop(normalize_provider_name(provider), None)

    def clear_all(self) -> None:
        self._configs.clear()


@dataclass(frozen=True)
class ResolvedProviderConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    key_source: str
    config_source: str
    key_tail: str = ""
    last_test: dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    def public_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "name": self.provider,
            "configured": self.configured,
            "baseUrl": self.base_url,
            "model": self.model,
            "keySource": self.key_source,
            "configSource": self.config_source,
            "keyTail": self.key_tail,
            "lastTest": _public_last_test(self.last_test),
        }


class ProviderConfigResolver:
    def __init__(self, store: WebProviderConfigStore | None = None) -> None:
        load_dotenv()
        self.store = store

    def resolve(self, provider: str) -> ResolvedProviderConfig:
        name = normalize_provider_name(provider)
        session = self.store.get(name) if self.store else None
        defaults = _defaults_for(name)
        env = _env_for(name)
        api_key = session.api_key if session and session.api_key else env["api_key"]
        base_url = session.base_url if session and session.base_url else env["base_url"] or defaults["base_url"]
        model = session.model if session and session.model else env["model"] or defaults["model"]
        key_source = "web_session" if session and session.api_key else "environment" if env["api_key"] else "missing"
        config_source = "web_session" if session and (session.base_url or session.model) else "environment" if env["base_url"] or env["model"] else "default"
        return ResolvedProviderConfig(
            provider=name,
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            key_source=key_source,
            config_source=config_source,
            key_tail=mask_key_tail(api_key),
            last_test=session.last_test if session else {},
        )

    def provider(self, provider: str) -> LLMProvider:
        resolved = self.resolve(provider)
        if resolved.provider == "deepseek":
            return DeepSeekProvider(
                api_key=resolved.api_key,
                base_url=resolved.base_url,
                model_name=resolved.model,
                prefer_env=False,
            )
        if resolved.provider == "gemini":
            return GeminiProvider(
                api_key=resolved.api_key,
                base_url=resolved.base_url,
                model_name=resolved.model,
                prefer_env=False,
            )
        raise ValueError("Provider 不受支持。")

    def env_overrides(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for provider in ("deepseek", "gemini"):
            session = self.store.get(provider) if self.store else None
            if not session:
                continue
            prefix = "DEEPSEEK" if provider == "deepseek" else "GEMINI"
            if session.api_key:
                values[f"{prefix}_API_KEY"] = session.api_key
            if session.base_url:
                values[f"{prefix}_BASE_URL"] = session.base_url.rstrip("/")
            if session.model:
                values[f"{prefix}_MODEL"] = session.model
        return values

    def statuses(self) -> list[dict[str, Any]]:
        return [self.resolve(name).public_status() for name in ("deepseek", "gemini")]


def test_provider_connection(
    provider: LLMProvider,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    started = clock()
    try:
        if not provider.is_available():
            raise UserFacingError(f"{_provider_label(provider.name)} 缺少 API Key。")
        response = provider.complete(
            [
                {"role": "system", "content": "只回复 JSON。"},
                {"role": "user", "content": '{"ping": true}'},
            ],
            json_mode=True,
            temperature=0,
            max_tokens=32,
        )
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider.name,
            "model": getattr(provider, "model_name", ""),
            "durationMs": int(max(0, (clock() - started) * 1000)),
            "error": sanitize_provider_error(str(exc)),
            "errorType": classify_provider_error(str(exc)),
        }
    return {
        "ok": True,
        "provider": response.provider,
        "model": response.model or getattr(provider, "model_name", ""),
        "durationMs": int(max(0, (clock() - started) * 1000)),
        "error": "",
        "errorType": "",
    }


def normalize_provider_name(value: str) -> str:
    name = str(value or "").strip().lower()
    if name in {"openai-compatible", "openai_compatible", "deepseek"}:
        return "deepseek"
    if name == "gemini":
        return name
    raise ValueError("provider 只能是 deepseek 或 gemini。")


def mask_key_tail(value: str) -> str:
    text = str(value or "")
    return text[-4:] if text else ""


def sanitize_provider_error(value: str) -> str:
    cleaned = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    cleaned = re.sub(r"(?i)(authorization|x-goog-api-key|api[_-]?key|token|cookie)\s*[:=]\s*[^,\s]+", r"\1=[redacted]", cleaned)
    cleaned = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-[redacted]", cleaned)
    cleaned = re.sub(r"sk_[A-Za-z0-9_-]+", "sk_[redacted]", cleaned)
    cleaned = re.sub(r"key=[^&\s]+", "key=[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned[:500] or "Provider 请求失败。"


def classify_provider_error(value: str) -> str:
    text = str(value or "").lower()
    if "缺少 api key" in text or "未配置" in text or "api_key" in text and "未检测" in text:
        return "missing_api_key"
    if "鉴权" in text or "unauthorized" in text or "http 401" in text or "http 403" in text:
        return "invalid_api_key"
    if "http 400" in text or "请求格式" in text:
        return "bad_request_or_model"
    if "model" in text or "模型" in text:
        return "model_not_found"
    if "429" in text or "限流" in text or "额度" in text or "quota" in text:
        return "rate_limited"
    if "超时" in text or "timeout" in text or "network" in text or "网络" in text:
        return "network_timeout"
    if "base url" in text or "url" in text:
        return "bad_base_url"
    if "500" in text or "502" in text or "503" in text or "504" in text:
        return "upstream_error"
    return "provider_error"


def _defaults_for(provider: str) -> dict[str, str]:
    if provider == "deepseek":
        return {"api_key": "", "base_url": DEFAULT_DEEPSEEK_BASE_URL, "model": DEFAULT_DEEPSEEK_MODEL}
    if provider == "gemini":
        return {"api_key": "", "base_url": DEFAULT_GEMINI_BASE_URL, "model": DEFAULT_GEMINI_MODEL}
    raise ValueError("Provider 不受支持。")


def _env_for(provider: str) -> dict[str, str]:
    if provider == "deepseek":
        return {
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "base_url": os.getenv("DEEPSEEK_BASE_URL", ""),
            "model": os.getenv("DEEPSEEK_MODEL", ""),
        }
    if provider == "gemini":
        return {
            "api_key": os.getenv("GEMINI_API_KEY", ""),
            "base_url": os.getenv("GEMINI_BASE_URL", ""),
            "model": os.getenv("GEMINI_MODEL", ""),
        }
    raise ValueError("Provider 不受支持。")


def _public_last_test(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"ok", "provider", "model", "durationMs", "error", "errorType", "testedAt"}
    return {
        key: sanitize_provider_error(str(item)) if key == "error" else item
        for key, item in value.items()
        if key in allowed
    }


def _provider_label(provider: str) -> str:
    return "Gemini" if provider == "gemini" else "DeepSeek"
