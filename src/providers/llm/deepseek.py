from __future__ import annotations

import os
import time
import json
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:  # type: ignore[no-redef]
        return False

from ...utils import UserFacingError
from ...defaults import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL
from .base import LLMProvider, LLMResponse


class DeepSeekProvider(LLMProvider):
    name = "deepseek"
    is_cloud = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        client: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
        prefer_env: bool = True,
    ) -> None:
        load_dotenv()
        self.api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
        env_base_url = os.getenv("DEEPSEEK_BASE_URL") if prefer_env else ""
        env_model = os.getenv("DEEPSEEK_MODEL") if prefer_env else ""
        self.base_url = (env_base_url or base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
        self.model_name = env_model or model_name or DEFAULT_DEEPSEEK_MODEL
        self._client = client
        self._sleep = sleep

    def is_available(self) -> bool:
        return bool(self.api_key.strip())

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not self.is_available():
            raise UserFacingError("未检测到 DEEPSEEK_API_KEY，请在项目 .env 中配置后重试。")
        client = self._client or self._create_client()
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        last_error = ""
        for attempt in range(3):
            try:
                response = client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                content = str(choice.message.content or "").strip()
                if not content:
                    last_error = "DeepSeek 返回了空内容。"
                    if attempt < 2:
                        self._sleep(float(2 ** attempt))
                        continue
                    raise UserFacingError(last_error)
                usage = getattr(response, "usage", None)
                usage_data = {
                    key: int(value)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if (value := getattr(usage, key, None)) is not None
                }
                return LLMResponse(
                    content=content,
                    provider=self.name,
                    model=str(getattr(response, "model", "") or self.model_name),
                    finish_reason=str(getattr(choice, "finish_reason", "") or ""),
                    usage=usage_data,
                )
            except UserFacingError:
                raise
            except Exception as exc:
                status = _status_code(exc)
                if status in {401, 403}:
                    raise UserFacingError("DeepSeek 鉴权失败，请检查 DEEPSEEK_API_KEY。") from exc
                last_error = _safe_error(exc, status)
                if attempt < 2 and (status in {408, 409, 429} or status is None or status >= 500):
                    self._sleep(float(2 ** attempt))
                    continue
                raise UserFacingError(last_error) from exc
        raise UserFacingError(last_error or "DeepSeek 请求失败。")

    def _create_client(self) -> object:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise UserFacingError("未安装 openai，请先运行 python -m pip install -r requirements.txt。") from exc
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _safe_error(exc: Exception, status: int | None) -> str:
    if status == 429:
        return "DeepSeek 请求过于频繁或额度不足，请稍后重试。"
    if status is not None:
        detail = _response_error_message(exc)
        return f"DeepSeek 请求失败：HTTP {status}{f'：{detail}' if detail else ''}。"
    return "DeepSeek 请求超时或网络不可用，请检查网络后重试。"


def _response_error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    text = str(getattr(response, "text", "") or "")
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return _sanitize_detail(message)
    return _sanitize_detail(text)


def _sanitize_detail(value: str) -> str:
    cleaned = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    for key in ("sk-", "sk_"):
        if key in cleaned:
            cleaned = cleaned.split(key, 1)[0].rstrip() + " [redacted]"
    return cleaned[:300]
