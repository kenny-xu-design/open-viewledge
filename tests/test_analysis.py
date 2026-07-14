from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.analysis.schemas import AnalysisParseError, parse_analysis_response
from src.providers.llm import LegacyLLMProvider
from src.utils import UserFacingError


class AnalysisSchemaTests(unittest.TestCase):
    def test_valid_json_parses(self) -> None:
        result = parse_analysis_response('{"summary":"ok"}', "summary", "test", "model")
        self.assertEqual(result.summary, "ok")

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

    def test_privacy_mode_blocks_cloud_provider(self) -> None:
        provider = LegacyLLMProvider("openai", "test-model")
        context = SimpleNamespace(privacy_mode=True)
        with self.assertRaisesRegex(UserFacingError, "隐私模式"):
            provider.generate("request", context)
