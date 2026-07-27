from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import web
from src.chat_store import ChatStore
from src.domain.models import TranscriptGroup
from src.provider_config import (
    ProviderConfigResolver,
    WebProviderConfigStore,
    classify_provider_error,
    sanitize_provider_error,
    test_groq_connection,
    test_provider_connection,
)
from src.providers.llm.base import LLMResponse
from src.utils import UserFacingError


class _Provider:
    name = "deepseek"
    model_name = "session-model"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def is_available(self) -> bool:
        return True

    def complete(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return LLMResponse('{"ok":true}', self.name, self.model_name)


class _HttpResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> "_HttpResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ProviderConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dotenv_patch = patch("src.provider_config.load_dotenv", return_value=False)
        self._dotenv_patch.start()

    def tearDown(self) -> None:
        self._dotenv_patch.stop()
        web.WEB_PROVIDER_CONFIG.clear_all()
        web.JOB_ENV_OVERRIDES.clear()

    @patch.dict(os.environ, {}, clear=True)
    def test_session_config_masks_key_and_overrides_defaults(self) -> None:
        store = WebProviderConfigStore()
        store.set_config(
            "deepseek",
            api_key="unit-test-secret-1234",
            base_url="https://example.test/v1",
            model="test-model",
        )

        resolved = ProviderConfigResolver(store).resolve("deepseek")
        status = resolved.public_status()

        self.assertEqual(resolved.api_key, "unit-test-secret-1234")
        self.assertEqual(status["keyTail"], "1234")
        self.assertTrue(status["configured"])
        self.assertEqual(status["keySource"], "web_session")
        self.assertNotIn("unit-test-secret-1234", json.dumps(status))

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-secret", "DEEPSEEK_MODEL": "env-model"}, clear=True)
    def test_environment_remains_compatible_when_session_missing(self) -> None:
        resolved = ProviderConfigResolver(WebProviderConfigStore()).resolve("deepseek")

        self.assertEqual(resolved.api_key, "env-secret")
        self.assertEqual(resolved.model, "env-model")
        self.assertEqual(resolved.key_source, "environment")

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-secret", "DEEPSEEK_MODEL": "env-model"}, clear=True)
    def test_session_config_takes_priority_over_environment(self) -> None:
        store = WebProviderConfigStore()
        store.set_config("deepseek", api_key="session-secret", model="session-model")

        resolved = ProviderConfigResolver(store).resolve("deepseek")

        self.assertEqual(resolved.api_key, "session-secret")
        self.assertEqual(resolved.model, "session-model")
        self.assertEqual(resolved.key_source, "web_session")

    def test_clear_removes_only_process_local_session_key(self) -> None:
        store = WebProviderConfigStore()
        store.set_config("gemini", api_key="gemini-secret", model="gemini-model")
        store.clear("gemini")

        status = ProviderConfigResolver(store).resolve("gemini").public_status()

        self.assertFalse(status["configured"])
        self.assertEqual(status["keySource"], "missing")
        self.assertNotIn("gemini-secret", json.dumps(status))

    @patch.dict(os.environ, {}, clear=True)
    def test_web_apply_and_clear_payload_never_return_full_key(self) -> None:
        applied = web.apply_provider_config(
            {
                "provider": "deepseek",
                "apiKey": "unit-session-secret-9999",
                "baseUrl": "https://example.test",
                "model": "model-a",
            }
        )

        self.assertIn("9999", json.dumps(applied))
        self.assertNotIn("unit-session-secret-9999", json.dumps(applied))

        cleared = web.clear_provider_config("deepseek")
        self.assertFalse(next(item for item in cleared["providers"] if item["provider"] == "deepseek")["configured"])

    def test_env_overrides_are_available_for_web_subprocess_without_job_record(self) -> None:
        store = WebProviderConfigStore()
        store.set_config("deepseek", api_key="session-secret", model="session-model")

        overrides = ProviderConfigResolver(store).env_overrides()
        record = web.job_to_dict(web.Job(id="job", command=["python"]))

        self.assertEqual(overrides["DEEPSEEK_API_KEY"], "session-secret")
        self.assertNotIn("session-secret", json.dumps(record))

    def test_groq_session_config_is_passed_to_web_subprocess_only(self) -> None:
        store = WebProviderConfigStore()
        store.set_config("groq", api_key="unit-groq-session-secret", model="whisper-large-v3-turbo")

        overrides = ProviderConfigResolver(store).env_overrides()
        status = ProviderConfigResolver(store).resolve("groq").public_status()
        record = web.job_to_dict(web.Job(id="job", command=["python"]))

        self.assertEqual(overrides["GROQ_API_KEY"], "unit-groq-session-secret")
        self.assertEqual(overrides["CLOUD_ASR_PROVIDER"], "groq")
        self.assertEqual(overrides["CLOUD_ASR_MODEL"], "whisper-large-v3-turbo")
        self.assertEqual(status["keyTail"], "cret")
        self.assertNotIn("unit-groq-session-secret", json.dumps(status))
        self.assertNotIn("unit-groq-session-secret", json.dumps(record))

    def test_connection_success_and_error_classes_are_sanitized(self) -> None:
        ok = test_provider_connection(_Provider())
        self.assertTrue(ok["ok"])

        failed = test_provider_connection(_Provider(UserFacingError("HTTP 401 Authorization: Bearer sk-abc")))
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["errorType"], "invalid_api_key")
        self.assertNotIn("sk-abc", failed["error"])

    def test_groq_connection_uses_model_list_without_leaking_key(self) -> None:
        store = WebProviderConfigStore()
        store.set_config("groq", api_key="unit-groq-secret-token", model="whisper-large-v3-turbo")
        resolved = ProviderConfigResolver(store).resolve("groq")
        captured = {}

        def fake_opener(request, timeout=0):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers.get("Authorization")
            captured["timeout"] = timeout
            return _HttpResponse('{"data":[{"id":"whisper-large-v3-turbo"}]}')

        result = test_groq_connection(resolved, opener=fake_opener)

        self.assertTrue(result["ok"])
        self.assertEqual(captured["url"], "https://api.groq.com/openai/v1/models")
        self.assertEqual(captured["authorization"], "Bearer unit-groq-secret-token")
        self.assertEqual(captured["timeout"], 20)
        self.assertNotIn("unit-groq-secret-token", json.dumps(result))

    def test_error_classification_covers_common_provider_failures(self) -> None:
        cases = {
            "缺少 API Key": "missing_api_key",
            "HTTP 400 model invalid": "bad_request_or_model",
            "HTTP 429 quota": "rate_limited",
            "请求超时或网络不可用": "network_timeout",
            "HTTP 500": "upstream_error",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(classify_provider_error(message), expected)

    def test_sanitizer_removes_tokens_and_key_query(self) -> None:
        message = sanitize_provider_error("Authorization: Bearer sk-abc https://x.test?a=1&key=abc123")

        self.assertNotIn("sk-abc", message)
        self.assertNotIn("key=abc123", message)

    def test_web_config_is_used_by_chat_provider(self) -> None:
        web.WEB_PROVIDER_CONFIG.set_config(
            "deepseek",
            api_key="session-secret",
            base_url="https://session.example/v1",
            model="session-model",
        )
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "demo"
            package.mkdir()
            (package / "chat.json").write_text("{}", encoding="utf-8")
            captured = {}

            def fake_answer_question(**kwargs):
                provider = kwargs["provider"]
                captured["provider"] = provider.name
                captured["model"] = provider.model_name
                captured["base_url"] = provider.base_url
                captured["api_key"] = provider.api_key
                return {
                    "answer": "ok",
                    "citations": [],
                    "provider": provider.name,
                    "model": provider.model_name,
                }

            with (
                patch("src.web.load_knowledge_package", return_value={"source": {}, "analysis": {}}),
                patch("src.web.load_transcript_groups", return_value=[
                    TranscriptGroup(index=0, start=0, end=3, title="片段", text="字幕", segment_indexes=[0]).model_dump()
                ]),
                patch("src.web.resolve_library_dir", return_value=package),
                patch("src.web.answer_question", side_effect=fake_answer_question),
            ):
                result = web.chat_with_knowledge({"knowledge_id": "demo", "question": "测试", "provider": "deepseek"})

        self.assertEqual(result["answer"], "ok")
        self.assertEqual(captured["model"], "session-model")
        self.assertEqual(captured["base_url"], "https://session.example/v1")
        self.assertEqual(captured["api_key"], "session-secret")
        if (package / "chat.json").exists():
            self.assertNotIn("session-secret", (package / "chat.json").read_text(encoding="utf-8"))

    @patch.dict(os.environ, {}, clear=True)
    def test_new_store_simulates_service_restart_without_session_key(self) -> None:
        store = WebProviderConfigStore()
        store.set_config("deepseek", api_key="session-secret")

        restarted = WebProviderConfigStore()
        status = ProviderConfigResolver(restarted).resolve("deepseek").public_status()

        self.assertFalse(status["configured"])
        self.assertNotIn("session-secret", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
