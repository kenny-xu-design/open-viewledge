from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from src.cli_contract import CLI_SCHEMA_VERSION, CliEmitter, ExitCode
from src.cli_tasks import CliTaskRecord, CliTaskStore
from src.config import AppConfig, load_config
from src.domain.models import AnalysisResult, ProcessingManifest
from src.exporters.models import ExportSelection
from src.exporters.service import selection_for_request
from src.main import app
from src.utils import UserFacingError


class ExitCodeContractTests(unittest.TestCase):
    def test_exit_code_table_is_stable(self) -> None:
        self.assertEqual(
            {item.name: int(item) for item in ExitCode},
            {
                "SUCCESS": 0,
                "EXECUTION_FAILED": 1,
                "USAGE_OR_CONFIG": 2,
                "INPUT_INACCESSIBLE": 3,
                "PROVIDER_NOT_CONFIGURED": 4,
                "EXTERNAL_TOOL_MISSING": 5,
                "KNOWLEDGE_PACKAGE_DAMAGED": 6,
                "CANCELLED": 7,
                "RETRYABLE_FAILURE": 8,
            },
        )

    def test_jsonl_events_are_one_object_per_line(self) -> None:
        stdout = StringIO()
        emitter = CliEmitter("analyze", jsonl_output=True, stdout=stdout, stderr=StringIO())
        required = (
            "task_created",
            "stage_started",
            "progress",
            "artifact_created",
            "warning",
            "stage_completed",
            "task_failed",
            "task_completed",
        )
        for event in required:
            emitter.event(event, task_id="task", stage="demo", progress=0.5)
        payloads = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([item["event"] for item in payloads], list(required))
        self.assertTrue(all(item["schema_version"] == "1.0" for item in payloads))

    def test_json_result_and_diagnostics_use_separate_streams(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        emitter = CliEmitter("config", json_output=True, stdout=stdout, stderr=stderr)
        emitter.diagnostic("diagnostic")
        emitter.result({"value": 1})
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema_version"], CLI_SCHEMA_VERSION)
        self.assertEqual(payload["data"]["value"], 1)
        self.assertNotIn("diagnostic", stdout.getvalue())
        self.assertIn("diagnostic", stderr.getvalue())

    def test_diagnostics_and_errors_redact_environment_secrets(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        emitter = CliEmitter("analyze", json_output=True, stdout=stdout, stderr=stderr)
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret-value"}):
            emitter.diagnostic("provider leaked secret-value")
            emitter.failure(ExitCode.PROVIDER_NOT_CONFIGURED, "API_KEY=secret-value", task_id="task")
        self.assertNotIn("secret-value", stdout.getvalue())
        self.assertNotIn("secret-value", stderr.getvalue())
        self.assertIn("[REDACTED]", stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["data"]["task_id"], "task")


class SchemaCompatibilityTests(unittest.TestCase):
    def test_legacy_missing_versions_use_safe_defaults(self) -> None:
        manifest = ProcessingManifest.model_validate({"task_id": "task"})
        self.assertEqual(manifest.schema_version, "1.0")
        self.assertEqual(manifest.processing_profile, "complete")
        self.assertEqual(manifest.stage_metrics, {})
        self.assertEqual(AppConfig.model_validate({"unknown_future_field": True}).schema_version, "1.0")

    def test_unknown_fields_are_ignored_in_same_major_version(self) -> None:
        manifest = ProcessingManifest.model_validate(
            {"schema_version": "1.7", "task_id": "task", "future_optional_field": "value"}
        )
        self.assertEqual(manifest.schema_version, "1.7")

    def test_newer_major_versions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProcessingManifest.model_validate({"schema_version": "2.0", "task_id": "task"})
        with self.assertRaises(ValueError):
            AnalysisResult.model_validate({"schema_version": "3.0"})
        with self.assertRaises(ValueError):
            ExportSelection.model_validate({"schema_version": "2.0", "knowledge_id": "demo"})
        with self.assertRaises(ValueError):
            selection_for_request("demo", {"schema_version": "2.0", "preset": "full"})

    def test_config_loader_rejects_unsupported_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text('{"schema_version":"2.0"}', encoding="utf-8")
            with self.assertRaisesRegex(UserFacingError, "不支持"):
                load_config(path)


class CliTaskStoreTests(unittest.TestCase):
    def test_task_round_trip_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = CliTaskStore(root)
            store.save(CliTaskRecord(task_id="task-1", source_type="url", source="https://example.com"))
            payload = json.loads((root / "task-1.json").read_text(encoding="utf-8"))
            payload["future_optional_field"] = True
            (root / "task-1.json").write_text(json.dumps(payload), encoding="utf-8")
            restored = store.load("task-1")
        self.assertEqual(restored.task_id, "task-1")
        self.assertEqual(restored.schema_version, "1.0")
        self.assertEqual(restored.processing_profile, "complete")

    def test_task_processing_profile_accepts_valid_and_rejects_invalid_values(self) -> None:
        record = CliTaskRecord(
            task_id="task",
            source_type="url",
            source="https://example.com",
            processing_profile="fast",
        )
        self.assertEqual(record.processing_profile, "fast")
        with self.assertRaises(ValueError):
            CliTaskRecord(
                task_id="task",
                source_type="url",
                source="https://example.com",
                processing_profile="turbo",
            )

    def test_future_task_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("task.json").write_text(
                json.dumps({"schema_version": "2.0", "task_id": "task", "source_type": "url", "source": "x"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(UserFacingError, "不支持"):
                CliTaskStore(root).load("task")


@unittest.skipIf(app is None, "Typer is not installed")
class PublicCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_public_command_set(self) -> None:
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        for command in ("analyze", "inspect", "export", "resume", "doctor", "config"):
            self.assertIn(command, result.stdout)

    def test_every_public_command_exposes_json_option(self) -> None:
        for command in ("analyze", "inspect", "export", "resume", "doctor", "config"):
            result = self.runner.invoke(app, [command, "--help"])
            self.assertEqual(result.exit_code, 0, command)
            self.assertIn("--json", result.stdout, command)
        for command in ("analyze", "resume"):
            result = self.runner.invoke(app, [command, "--help"])
            self.assertIn("--jsonl", result.stdout, command)
        self.assertIn("--processing-profile", self.runner.invoke(app, ["analyze", "--help"]).stdout)

    def test_analyze_rejects_invalid_processing_profile(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "analyze",
                "--url",
                "https://example.com/video",
                "--processing-profile",
                "turbo",
                "--json",
            ],
        )

        self.assertEqual(result.exit_code, int(ExitCode.USAGE_OR_CONFIG))
        self.assertIn("processing_profile", json.loads(result.stdout)["error"]["message"])

    def test_config_supports_json_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text('{"schema_version":"1.0","language":"en"}', encoding="utf-8")
            result = self.runner.invoke(app, ["config", "--config", str(path), "--json"])
        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["command"], "config")
        self.assertEqual(payload["data"]["values"]["language"], "en")

    def test_doctor_supports_json_envelope(self) -> None:
        doctor_result = {"schema_version": "1.0", "healthy": True, "checks": [], "summary": {}}
        with patch("src.main.run_doctor", return_value=doctor_result):
            result = self.runner.invoke(app, ["doctor", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(json.loads(result.stdout)["command"], "doctor")

    def test_export_supports_json_envelope(self) -> None:
        exported = {"success": True, "knowledge_id": "demo", "file_path": "demo.md"}
        with patch("src.main.export_existing_knowledge", return_value=exported):
            result = self.runner.invoke(app, ["export", "--knowledge-id", "demo", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(json.loads(result.stdout)["data"]["knowledge_id"], "demo")

    def test_analyze_jsonl_persists_task_and_emits_lifecycle(self) -> None:
        completed = {
            "task_id": "ignored",
            "knowledge_id": "demo",
            "output_dir": "output/demo",
            "status": "completed",
            "analysis_profile": "summary",
            "processing_profile": "complete",
            "analysis": {"status": "skipped", "provider": "", "model": ""},
            "artifacts": {},
        }
        with tempfile.TemporaryDirectory() as temp:
            with patch("src.main.CLI_TASK_ROOT", Path(temp)), patch("src.main.run_pipeline", return_value=completed):
                result = self.runner.invoke(
                    app,
                    ["analyze", "--url", "https://example.com/video", "--no-summary", "--jsonl"],
                )
                records = list(Path(temp).glob("*.json"))
        self.assertEqual(result.exit_code, 0)
        payloads = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([item["event"] for item in payloads], ["task_created", "task_completed"])
        self.assertEqual(payloads[0]["analysis_profile"], "summary")
        self.assertEqual(payloads[0]["processing_profile"], "complete")
        self.assertEqual(payloads[1]["result"]["processing_profile"], "complete")
        self.assertEqual(len(records), 1)

    def test_legacy_root_analyze_usage_remains_supported_with_warning(self) -> None:
        completed = {
            "task_id": "ignored",
            "knowledge_id": "demo",
            "output_dir": "output/demo",
            "status": "completed",
            "analysis": {"status": "skipped", "provider": "", "model": ""},
            "artifacts": {},
        }
        with tempfile.TemporaryDirectory() as temp:
            with patch("src.main.CLI_TASK_ROOT", Path(temp)), patch("src.main.run_pipeline", return_value=completed):
                result = self.runner.invoke(app, ["--url", "https://example.com/video", "--no-summary", "--json"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("已废弃", result.stderr)
        self.assertEqual(json.loads(result.stdout)["command"], "analyze")

    def test_failed_task_can_resume_with_original_options(self) -> None:
        completed = {
            "task_id": "task-1",
            "knowledge_id": "demo",
            "output_dir": "output/demo",
            "status": "completed",
            "analysis": {"status": "skipped", "provider": "", "model": ""},
            "artifacts": {},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = CliTaskStore(root)
            store.save(
                CliTaskRecord(
                    task_id="task-1",
                    status="failed",
                    source_type="url",
                    source="https://example.com/video",
                    processing_profile="fast",
                    options={"mode": "tutorial", "no_summary": True, "config": "config.example.json"},
                )
            )
            with patch("src.main.CLI_TASK_ROOT", root), patch("src.main.run_pipeline", return_value=completed) as run:
                result = self.runner.invoke(app, ["resume", "task-1", "--json"])
            restored = store.load("task-1")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(json.loads(result.stdout)["command"], "resume")
        self.assertEqual(restored.status, "completed")
        self.assertEqual(run.call_args.kwargs["mode"], "tutorial")
        self.assertEqual(run.call_args.kwargs["processing_profile"], "fast")

    def test_real_process_json_exit_code_and_stream_separation(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "future-config.json"
            path.write_text('{"schema_version":"2.0"}', encoding="utf-8")
            process = subprocess.run(
                [sys.executable, "-m", "src.main", "config", "--config", str(path), "--json"],
                cwd=project_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(process.returncode, int(ExitCode.USAGE_OR_CONFIG))
        payload = json.loads(process.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["exit_code"], int(ExitCode.USAGE_OR_CONFIG))
        self.assertEqual(process.stderr, "")
