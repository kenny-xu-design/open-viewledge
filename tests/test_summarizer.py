from __future__ import annotations

import unittest
from unittest.mock import patch

from src.summarizer import choose_ollama_model, discover_ollama_models
from src.utils import UserFacingError


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class OllamaModelSelectionTests(unittest.TestCase):
    def test_keeps_explicit_installed_model(self) -> None:
        selected = choose_ollama_model(["qwen3.5:9b", "llama3.1:8b"], "llama3.1:8b")
        self.assertEqual(selected, "llama3.1:8b")

    def test_missing_explicit_model_falls_back_to_priority(self) -> None:
        selected = choose_ollama_model(["qwen3:4b", "qwen3.5:9b"], "missing:model")
        self.assertEqual(selected, "qwen3.5:9b")

    def test_auto_uses_first_supported_candidate(self) -> None:
        selected = choose_ollama_model(["gemma4:e4b", "llama3.1:8b"], "auto")
        self.assertEqual(selected, "llama3.1:8b")

    def test_auto_can_use_other_installed_model(self) -> None:
        self.assertEqual(choose_ollama_model(["custom:latest"], "auto"), "custom:latest")

    def test_empty_model_list_has_actionable_error(self) -> None:
        with self.assertRaisesRegex(UserFacingError, "未检测到已安装模型"):
            choose_ollama_model([], "auto")

    @patch("src.summarizer.urllib.request.urlopen")
    def test_discovers_names_from_tags_endpoint(self, mocked_urlopen) -> None:
        mocked_urlopen.return_value = _Response('{"models":[{"name":"qwen3.5:9b"},{"model":"llama3.1:8b"}]}')
        self.assertEqual(
            discover_ollama_models("http://localhost:11434"),
            ["qwen3.5:9b", "llama3.1:8b"],
        )


if __name__ == "__main__":
    unittest.main()
