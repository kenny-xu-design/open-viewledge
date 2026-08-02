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
from src.knowledge_identity import KnowledgeRequestDimensions, build_input_knowledge_identity
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

    def test_pipeline_receives_resolved_output_root(self) -> None:
        package = SimpleNamespace(
            output_dir=Path("output/demo"),
            manifest=ProcessingManifest(task_id="task", status="completed"),
            analysis=AnalysisResult(status="skipped"),
        )
        with (
            patch("src.main.load_config", return_value=AppConfig(output_dir="output")),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.return_value = package
            run_pipeline(url="https://example.com/video", no_summary=True)

        config = orchestrator.call_args.args[0]
        self.assertEqual(Path(config.output_dir), (Path(__file__).resolve().parents[1] / "output").resolve())

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

    def test_run_pipeline_returns_manifest_knowledge_identity_not_legacy_directory(self) -> None:
        package = SimpleNamespace(
            output_dir=Path("output/legacy-demo"),
            manifest=ProcessingManifest(
                task_id="task",
                status="completed",
                knowledge_id="k1-web-stable",
                identity_schema_version="1.0",
                request_fingerprint="request-fp",
            ),
            analysis=AnalysisResult(status="skipped"),
        )
        with (
            patch("src.main.load_config", return_value=AppConfig(language="zh")),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.return_value = package
            result = run_pipeline(url="https://example.com/video", no_summary=True)

        self.assertEqual(result["knowledge_id"], "k1-web-stable")
        self.assertEqual(result["identity_schema_version"], "1.0")
        self.assertEqual(result["request_fingerprint"], "request-fp")
        self.assertTrue(orchestrator.call_args.kwargs["knowledge_identity"].knowledge_id.startswith("k1-web-"))

    def test_run_pipeline_applies_transcript_group_seconds_to_config_and_identity(self) -> None:
        package = SimpleNamespace(
            output_dir=Path("output/demo"),
            manifest=ProcessingManifest(
                task_id="task",
                status="completed",
                knowledge_id="k1-web-stable",
                identity_schema_version="1.0",
                request_fingerprint="request-fp",
                transcript_group_seconds=30,
            ),
            analysis=AnalysisResult(status="skipped"),
        )
        with (
            patch("src.main.load_config", return_value=AppConfig(transcript_group_seconds=60)),
            patch("src.main.PipelineOrchestrator") as orchestrator,
        ):
            orchestrator.return_value.run.return_value = package
            run_pipeline(
                url="https://example.com/video",
                no_summary=True,
                transcript_group_seconds=30,
            )

        config = orchestrator.call_args.args[0]
        identity = orchestrator.call_args.kwargs["knowledge_identity"]
        expected_30 = build_input_knowledge_identity(
            "https://example.com/video",
            is_url=True,
            dimensions=KnowledgeRequestDimensions(
                language="zh",
                transcript_only=True,
                transcript_group_seconds=30,
            ),
        )
        expected_60 = build_input_knowledge_identity(
            "https://example.com/video",
            is_url=True,
            dimensions=KnowledgeRequestDimensions(
                language="zh",
                transcript_only=True,
                transcript_group_seconds=60,
            ),
        )

        self.assertEqual(config.transcript_group_seconds, 30)
        self.assertEqual(identity.request_fingerprint, expected_30.request_fingerprint)
        self.assertNotEqual(identity.request_fingerprint, expected_60.request_fingerprint)

    def test_run_pipeline_rejects_transcript_group_seconds_below_minimum(self) -> None:
        with patch("src.main.load_config", return_value=AppConfig()):
            with self.assertRaises(ExitWithCode) as context:
                run_pipeline(
                    url="https://example.com/video",
                    no_summary=True,
                    transcript_group_seconds=14,
                )

        self.assertEqual(context.exception.code, 2)
        self.assertIn("不能小于 15", context.exception.message)


if __name__ == "__main__":
    unittest.main()
