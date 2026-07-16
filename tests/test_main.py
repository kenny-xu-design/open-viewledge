from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.config import AppConfig
from src.main import ExitWithCode, run_pipeline


class _Console:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, message: object) -> None:
        self.messages.append(str(message))


class MainPipelineTests(unittest.TestCase):
    def test_comments_flag_only_emits_compatibility_warning(self) -> None:
        console = _Console()
        package = SimpleNamespace(output_dir=Path("output/demo"))
        with (
            patch("src.main.console", console),
            patch("src.main.load_config", return_value=AppConfig()),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.return_value = package
            run_pipeline(
                url="https://example.com/video",
                comments=True,
                export="obsidian",
                no_summary=True,
            )

        self.assertTrue(any("不会获取或分析评论" in message for message in console.messages))
        self.assertTrue(any("export_note.md" in message for message in console.messages))
        orchestrator.return_value.run.assert_called_once_with("https://example.com/video", is_url=True)

    def test_unexpected_pipeline_error_has_clean_exit(self) -> None:
        console = _Console()
        with (
            patch("src.main.console", console),
            patch("src.main.load_config", return_value=AppConfig()),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.side_effect = RuntimeError("boom")
            with self.assertRaises(ExitWithCode) as context:
                run_pipeline(url="https://example.com/video")

        self.assertEqual(context.exception.code, 1)
        self.assertTrue(any("处理失败" in message for message in console.messages))


if __name__ == "__main__":
    unittest.main()
