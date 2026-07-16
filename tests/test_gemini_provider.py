from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from src.analysis import KeyframeAnalysisService
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


class _FakeVisionProvider(_FakeProvider):
    supports_images = True

    def __init__(self, available: bool = True) -> None:
        super().__init__("gemini", available)
        self.image_calls = 0

    def generate_with_images(self, prompt, image_paths, **kwargs):
        self.image_calls += 1
        return LLMResponse("视觉结果", self.name, self.model_name)


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

    def test_image_completion_uses_inline_data_without_exposing_key(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["key"] = request.headers.get("X-goog-api-key")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _Response(
                {
                    "candidates": [{"content": {"parts": [{"text": "画面分析"}]}, "finishReason": "STOP"}],
                    "modelVersion": "gemini-test",
                }
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            frame = Path(temp_dir) / "frame.jpg"
            frame.write_bytes(b"\xff\xd8fake-jpeg")
            provider = GeminiProvider(api_key="test-key", model_name="gemini-test", opener=opener)
            result = provider.generate_with_images(
                "分析关键帧",
                [frame],
                system_prompt="只描述可见信息",
                json_mode=True,
            )

        inline = captured["body"]["contents"][0]["parts"][1]["inline_data"]
        self.assertEqual(result.content, "画面分析")
        self.assertEqual(inline["mime_type"], "image/jpeg")
        self.assertEqual(base64.b64decode(inline["data"]), b"\xff\xd8fake-jpeg")
        self.assertEqual(captured["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(captured["key"], "test-key")
        self.assertNotIn("test-key", json.dumps(captured["body"]))

    def test_empty_frames_never_call_gemini(self) -> None:
        called = False

        def opener(request, timeout):
            nonlocal called
            called = True
            return _Response({})

        provider = GeminiProvider(api_key="test-key", opener=opener)
        with self.assertRaisesRegex(UserFacingError, "未提供关键帧"):
            provider.generate_with_images("分析", [])
        self.assertFalse(called)

    def test_registry_separates_text_and_image_capabilities(self) -> None:
        gemini = _FakeVisionProvider()
        registry = ProviderRegistry(
            {"deepseek": _FakeProvider("deepseek", True), "gemini": gemini}
        )
        self.assertEqual(registry.resolve("auto", "总结字幕").name, "deepseek")
        self.assertEqual(registry.resolve("auto", "画面里有什么按钮").name, "deepseek")
        self.assertEqual(registry.resolve("auto", "分析关键帧", capability="images").name, "gemini")
        statuses = {item["name"]: item for item in registry.statuses()}
        self.assertEqual(statuses["deepseek"]["capabilities"], ["text"])
        self.assertEqual(statuses["gemini"]["capabilities"], ["text", "images"])

    def test_image_capability_requires_gemini_configuration(self) -> None:
        gemini = _FakeProvider("gemini", False)
        gemini.supports_images = True
        registry = ProviderRegistry(
            {"deepseek": _FakeProvider("deepseek", True), "gemini": gemini}
        )
        with self.assertRaisesRegex(UserFacingError, "Gemini 未配置"):
            registry.resolve("auto", "截图里有什么", capability="images")

    def test_keyframe_service_skips_empty_input_without_provider_call(self) -> None:
        provider = _FakeVisionProvider()
        service = KeyframeAnalysisService(provider)
        result = service.analyze([], "分析画面")
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.frame_count, 0)
        self.assertEqual(provider.image_calls, 0)

    def test_keyframe_service_returns_provider_response(self) -> None:
        provider = _FakeVisionProvider()
        result = KeyframeAnalysisService(provider).analyze([Path("frame.jpg")], "分析画面")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.response.content, "视觉结果")
        self.assertEqual(provider.image_calls, 1)

    def test_keyframe_service_requires_configured_gemini(self) -> None:
        provider = _FakeVisionProvider(available=False)
        with self.assertRaisesRegex(UserFacingError, "Gemini 未配置"):
            KeyframeAnalysisService(provider).analyze([Path("frame.jpg")], "分析画面")
        self.assertEqual(provider.image_calls, 0)


if __name__ == "__main__":
    unittest.main()
