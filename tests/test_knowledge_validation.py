from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from src.domain.models import AnalysisResult, ProcessingManifest, SourceRecord, TranscriptSegment
from src.knowledge_validation import inspect_knowledge_package
from src.main import app


class KnowledgeValidationTests(unittest.TestCase):
    def _package(
        self,
        root: Path,
        *,
        analysis: dict | None = None,
        analysis_status: str = "completed",
        task_status: str = "completed",
        stage_status: str = "completed",
    ) -> Path:
        package = root / "demo"
        package.mkdir()
        source = SourceRecord(
            source_type="online_video",
            platform="youtube",
            source_url="https://example.com/video",
            source_id="video-id",
            title="Demo",
        )
        manifest = ProcessingManifest(
            task_id="task",
            source=source,
            status=task_status,
            current_stage="export_knowledge_package",
            analysis_status=analysis_status,
            stage_status={
                "acquire_transcript": "completed",
                "run_analysis": stage_status,
                "export_knowledge_package": "completed",
            },
            output_files=[
                "index.md",
                "metadata.json",
                "manifest.json",
                "analysis.json",
                "timeline.json",
                "source.md",
                "transcript.raw.jsonl",
                "transcript.grouped.md",
                "transcript.md",
            ],
        )
        result = analysis or AnalysisResult(
            status="success",
            summary="Meaningful summary",
            provider="deepseek",
            model="test-model",
        ).model_dump(mode="json")
        (package / "metadata.json").write_text(
            json.dumps(source.model_dump(mode="json"), ensure_ascii=False),
            encoding="utf-8",
        )
        (package / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False),
            encoding="utf-8",
        )
        (package / "analysis.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        (package / "timeline.json").write_text(
            '{"items":[{"index":0,"start":0,"end":2,"title":"Demo"}]}',
            encoding="utf-8",
        )
        segment = TranscriptSegment(index=0, start=0, end=2, text="Transcript")
        (package / "transcript.raw.jsonl").write_text(segment.model_dump_json() + "\n", encoding="utf-8")
        for name, text in {
            "index.md": "# Demo\n\nSummary",
            "source.md": "# Demo\n\nSource",
            "transcript.grouped.md": "# Grouped\n\n## Demo\n\nTranscript",
            "transcript.md": "# Transcript\n\nTranscript",
        }.items():
            (package / name).write_text(text, encoding="utf-8")
        return package

    def test_valid_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = inspect_knowledge_package(self._package(Path(temp)))
        self.assertTrue(report.valid)
        self.assertEqual(report.level, "valid")
        self.assertEqual(report.analysis_status, "success")
        self.assertEqual(report.transcript_segments, 1)

    def test_empty_analysis_is_invalid_and_conflicts_with_completed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = self._package(Path(temp))
            (package / "analysis.json").write_text("{}", encoding="utf-8")
            before = (package / "manifest.json").read_text(encoding="utf-8")
            report = inspect_knowledge_package(package)
            after = (package / "manifest.json").read_text(encoding="utf-8")
        self.assertFalse(report.valid)
        self.assertEqual(report.analysis_status, "invalid")
        self.assertIn("analysis_manifest_conflict", {item.code for item in report.issues})
        self.assertEqual(before, after)

    def test_legacy_analysis_without_status_and_without_content_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = self._package(Path(temp))
            (package / "analysis.json").write_text(
                json.dumps(
                    {
                        "one_sentence_summary": "",
                        "summary": "",
                        "highlights": [],
                        "thoughts": [],
                        "chapters": [],
                        "terminology": [],
                        "actions": [],
                        "provider": "",
                        "model": "",
                    }
                ),
                encoding="utf-8",
            )
            report = inspect_knowledge_package(package)
        self.assertFalse(report.valid)
        self.assertEqual(report.analysis_status, "invalid")
        self.assertIn("analysis_invalid", {item.code for item in report.issues})

    def test_failed_analysis_is_reported_as_warning_when_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            analysis = AnalysisResult(status="failed", error="quota", provider="deepseek").model_dump(mode="json")
            package = self._package(
                Path(temp),
                analysis=analysis,
                analysis_status="failed",
                task_status="completed_with_warnings",
                stage_status="failed",
            )
            report = inspect_knowledge_package(package)
        self.assertTrue(report.valid)
        self.assertEqual(report.level, "warning")
        self.assertEqual(report.analysis_status, "failed")

    def test_malformed_json_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = self._package(Path(temp))
            (package / "timeline.json").write_text("{", encoding="utf-8")
            report = inspect_knowledge_package(package)
        self.assertFalse(report.valid)
        self.assertIn("json_invalid", {item.code for item in report.issues})

    @unittest.skipIf(app is None, "Typer is not installed")
    def test_cli_inspect_returns_json_and_nonzero_for_invalid_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = self._package(Path(temp))
            (package / "analysis.json").write_text("{}", encoding="utf-8")
            result = CliRunner().invoke(app, ["inspect", str(package), "--json"])
        self.assertEqual(result.exit_code, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["level"], "invalid")
