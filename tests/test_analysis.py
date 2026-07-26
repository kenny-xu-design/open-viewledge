from __future__ import annotations

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from src.analysis.service import AnalysisService
from src.analysis.schemas import AnalysisParseError, parse_analysis_response
from src.domain.models import TranscriptGroup
from src.defaults import DEFAULT_DEEPSEEK_MODEL
from src.providers.llm import DeepSeekProvider, LLMResponse
from src.utils import UserFacingError


def _response(content: str, *, model: str = "deepseek-chat", finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


class _FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _client(responses: list[object]) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(responses)))


class AnalysisSchemaTests(unittest.TestCase):
    def test_valid_json_parses(self) -> None:
        result = parse_analysis_response('{"summary":"ok"}', "summary", "test", "model")
        self.assertEqual(result.summary, "ok")
        self.assertEqual(result.status, "success")

    def test_markdown_fence_is_removed(self) -> None:
        result = parse_analysis_response('```json\n{"summary":"ok"}\n```', "summary", "test", "model")
        self.assertEqual(result.summary, "ok")

    def test_invalid_json_keeps_raw_response(self) -> None:
        with self.assertRaises(AnalysisParseError) as caught:
            parse_analysis_response("not json", "summary", "test", "model")
        self.assertEqual(caught.exception.partial_result.raw_response, "not json")

    def test_string_terminology_is_normalized(self) -> None:
        result = parse_analysis_response('{"terminology":["ASR", {"term":"LLM"}]}', "summary", "test", "model")
        self.assertEqual(result.terminology, [{"term": "ASR"}, {"term": "LLM"}])

    def test_object_actions_are_normalized(self) -> None:
        result = parse_analysis_response(
            '{"actions":[{"action":"复习字幕","description":"确认关键步骤"},"记录问题"]}',
            "summary",
            "test",
            "model",
        )
        self.assertEqual(result.actions, ["复习字幕：确认关键步骤", "记录问题"])

    def test_timestamp_outside_transcript_is_rejected(self) -> None:
        with self.assertRaisesRegex(AnalysisParseError, "超出字幕时间范围"):
            parse_analysis_response(
                '{"highlights":[{"title":"late","start":31,"end":32}]}',
                "summary",
                "deepseek",
                "model",
                max_duration=30,
            )

    def test_empty_analysis_is_not_marked_successful(self) -> None:
        with self.assertRaisesRegex(AnalysisParseError, "没有包含任何有效内容"):
            parse_analysis_response("{}", "summary", "deepseek", "model")


class DeepSeekProviderTests(unittest.TestCase):
    @patch("src.providers.llm.deepseek.load_dotenv", return_value=False)
    @patch.dict("os.environ", {}, clear=True)
    def test_default_model_is_centralized(self, _load_dotenv) -> None:
        provider = DeepSeekProvider(api_key="test-key", client=_client([]))
        self.assertEqual(provider.model_name, DEFAULT_DEEPSEEK_MODEL)

    def test_json_completion_records_model_usage_and_format(self) -> None:
        client = _client([_response('{"summary":"ok"}', model="resolved-model")])
        provider = DeepSeekProvider(api_key="test-key", client=client)

        result = provider.complete([{"role": "user", "content": "JSON"}], json_mode=True, max_tokens=100)

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.model, "resolved-model")
        self.assertEqual(result.usage["total_tokens"], 15)
        call = client.chat.completions.calls[0]
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertEqual(call["max_tokens"], 100)

    def test_empty_response_retries_then_succeeds(self) -> None:
        sleeps: list[float] = []
        client = _client([_response(""), _response('{"summary":"ok"}')])
        provider = DeepSeekProvider(api_key="test-key", client=client, sleep=sleeps.append)

        result = provider.complete([{"role": "user", "content": "JSON"}], json_mode=True)

        self.assertIn("summary", result.content)
        self.assertEqual(sleeps, [1.0])

    def test_authentication_failure_is_not_retried_or_leaked(self) -> None:
        error = RuntimeError("upstream error included secret-value")
        error.status_code = 401  # type: ignore[attr-defined]
        client = _client([error])
        provider = DeepSeekProvider(api_key="secret-value", client=client, sleep=lambda _: None)

        with self.assertRaisesRegex(UserFacingError, "鉴权失败") as caught:
            provider.complete([{"role": "user", "content": "test"}])

        self.assertNotIn("secret-value", str(caught.exception))
        self.assertEqual(len(client.chat.completions.calls), 1)

    def test_rate_limit_retries_then_succeeds(self) -> None:
        error = RuntimeError("quota details")
        error.status_code = 429  # type: ignore[attr-defined]
        sleeps: list[float] = []
        client = _client([error, _response('{"summary":"ok"}')])
        provider = DeepSeekProvider(api_key="test-key", client=client, sleep=sleeps.append)

        result = provider.complete([{"role": "user", "content": "JSON"}], json_mode=True)

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(sleeps, [1.0])

    def test_bad_request_includes_safe_upstream_message(self) -> None:
        error = RuntimeError("raw wrapper")
        error.status_code = 400  # type: ignore[attr-defined]
        error.response = SimpleNamespace(  # type: ignore[attr-defined]
            text='{"error":{"message":"The supported API model names are deepseek-v4-pro or deepseek-v4-flash, but you passed deepseek-chat."}}'
        )
        client = _client([error])
        provider = DeepSeekProvider(api_key="test-key", client=client, sleep=lambda _: None)

        with self.assertRaisesRegex(UserFacingError, "deepseek-v4-flash.*deepseek-chat"):
            provider.complete([{"role": "user", "content": "test"}])

    def test_missing_key_has_actionable_error(self) -> None:
        provider = DeepSeekProvider(api_key="", client=_client([]))
        with self.assertRaisesRegex(UserFacingError, "DEEPSEEK_API_KEY"):
            provider.complete([{"role": "user", "content": "test"}])

    def test_environment_can_override_configured_model(self) -> None:
        with patch.dict("os.environ", {"DEEPSEEK_MODEL": "account-model"}):
            provider = DeepSeekProvider(api_key="test-key", model_name="deepseek-chat", client=_client([]))
        self.assertEqual(provider.model_name, "account-model")


class AnalysisServiceTests(unittest.TestCase):
    def test_invalid_first_response_is_repaired_once(self) -> None:
        class Provider:
            name = "deepseek"
            model_name = "deepseek-chat"

            def __init__(self) -> None:
                self.calls = 0

            def complete(self, messages, **kwargs):
                self.calls += 1
                content = "not json" if self.calls == 1 else '{"summary":"repaired"}'
                return LLMResponse(content, self.name, self.model_name)

        provider = Provider()
        group = TranscriptGroup(index=0, start=0, end=30, title="开场", text="字幕", segment_indexes=[0])
        result = AnalysisService(provider).analyze([group], "summary", SimpleNamespace())

        self.assertEqual(result.summary, "repaired")
        self.assertEqual(provider.calls, 2)
