from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from src import __version__
from src.config import AppConfig
from src.cli_contract import CliEmitter
from src.domain.models import AnalysisResult, ProcessingManifest
from src.main import ExitWithCode, app, run_pipeline


class MainPipelineTests(unittest.TestCase):
    @unittest.skipIf(app is None, "Typer is not installed")
    def test_version_option_reports_package_version(self) -> None:
        result = CliRunner().invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), f"video-summary-skill {__version__}")

    def test_comments_flag_enables_comment_pipeline(self) -> None:
        package = SimpleNamespace(
            output_dir=Path("output/demo"),
            manifest=ProcessingManifest(task_id="task", status="completed"),
            analysis=AnalysisResult(status="skipped"),
        )
        with (
            patch("src.main.load_config", return_value=AppConfig()),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.return_value = package
            run_pipeline(
                url="https://example.com/video",
                comments=True,
                export="obsidian",
                no_summary=True,
                emitter=CliEmitter("analyze", stderr=StringIO()),
            )

        self.assertTrue(orchestrator.call_args.kwargs["comments_enabled"])
        orchestrator.return_value.run.assert_called_once_with("https://example.com/video", is_url=True)

    def test_unexpected_pipeline_error_has_clean_exit(self) -> None:
        stderr = StringIO()
        with (
            patch("src.main.load_config", return_value=AppConfig()),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.side_effect = RuntimeError("boom")
            with self.assertRaises(ExitWithCode) as context:
                run_pipeline(url="https://example.com/video", emitter=CliEmitter("analyze", stderr=stderr))

        self.assertEqual(context.exception.code, 1)
        self.assertIn("处理失败", context.exception.message)

    def test_processing_profile_is_separate_from_analysis_profile(self) -> None:
        package = SimpleNamespace(
            output_dir=Path("output/demo"),
            manifest=ProcessingManifest(
                task_id="task",
                status="completed",
                analysis_profile="tutorial",
                processing_profile="fast",
            ),
            analysis=AnalysisResult(status="skipped", analysis_profile="tutorial"),
        )
        with (
            patch("src.main.load_config", return_value=AppConfig()),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.return_value = package
            result = run_pipeline(
                url="https://example.com/video",
                mode="tutorial",
                processing_profile="fast",
                no_summary=True,
            )

        self.assertEqual(result["analysis_profile"], "tutorial")
        self.assertEqual(result["processing_profile"], "fast")
        self.assertEqual(orchestrator.call_args.kwargs["analysis_profile"], "tutorial")
        self.assertEqual(orchestrator.call_args.kwargs["processing_profile"], "fast")


if __name__ == "__main__":
    unittest.main()
