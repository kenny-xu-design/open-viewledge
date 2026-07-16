from __future__ import annotations

import io
import json
import unittest

from src.providers.llm import GeminiProvider, ProviderRegistry
from src.providers.llm.base import LLMProvider, LLMResponse
from src.utils import UserFacingError


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeProvider(LLMProvider):
    is_cloud = True

    def __init__(self, name: str, available: bool) -> None:
        self.name = name
        self.model_name = f"{name}-model"
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def complete(self, messages, **kwargs):
        return LLMResponse("ok", self.name, self.model_name)


class GeminiProviderTests(unittest.TestCase):
    def test_unconfigured_provider_has_clear_error(self) -> None:
        with self.assertRaisesRegex(UserFacingError, "Gemini 未配置"):
            GeminiProvider(api_key="").complete([{"role": "user", "content": "你好"}])

    def test_text_completion_uses_official_generate_content_contract(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["key"] = request.headers.get("X-goog-api-key")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _Response(
                {
                    "candidates": [{"content": {"parts": [{"text": "真实回答"}]}, "finishReason": "STOP"}],
                    "modelVersion": "gemini-test",
                    "usageMetadata": {"totalTokenCount": 9},
                }
            )

        provider = GeminiProvider(api_key="test-key", model_name="gemini-test", opener=opener)
        result = provider.complete([{"role": "system", "content": "受控"}, {"role": "user", "content": "问题"}])
        self.assertEqual(result.content, "真实回答")
        self.assertEqual(result.model, "gemini-test")
        self.assertTrue(captured["url"].endswith("/models/gemini-test:generateContent"))
        self.assertEqual(captured["key"], "test-key")
        self.assertNotIn("test-key", json.dumps(captured["body"]))

    def test_registry_routes_text_and_visual_questions(self) -> None:
        registry = ProviderRegistry(
            {"deepseek": _FakeProvider("deepseek", True), "gemini": _FakeProvider("gemini", True)}
        )
        self.assertEqual(registry.resolve("auto", "总结字幕").name, "deepseek")
        self.assertEqual(registry.resolve("auto", "画面里有什么按钮").name, "gemini")

    def test_registry_falls_back_to_deepseek_when_gemini_is_missing(self) -> None:
        registry = ProviderRegistry(
            {"deepseek": _FakeProvider("deepseek", True), "gemini": _FakeProvider("gemini", False)}
        )
        self.assertEqual(registry.resolve("auto", "截图里有什么").name, "deepseek")


if __name__ == "__main__":
    unittest.main()
