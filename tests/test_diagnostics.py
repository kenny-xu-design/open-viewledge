from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.config import AppConfig
from src.diagnostics import _writable_check, run_doctor
from src.runtime_tools import ExecutableStatus


class DoctorTests(unittest.TestCase):
    def test_writable_check_uses_deterministic_probe_file_and_cleans_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = _writable_check("output", root, required=True)
            leftovers = list(root.glob(".viewledge-doctor-*.tmp"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(leftovers, [])

    def test_doctor_reports_required_and_optional_failures_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tools = [
                ExecutableStatus(name="ffmpeg", available=False, error="missing"),
                ExecutableStatus(name="ffprobe", available=True, path="C:/tools/ffprobe.exe"),
            ]
            registry = SimpleNamespace(
                statuses=lambda: [
                    {"name": "deepseek", "model": "model", "configured": False, "capabilities": ["text"]}
                ]
            )
            with (
                patch("src.diagnostics.runtime_tool_statuses", return_value=tools),
                patch("src.diagnostics.ProviderRegistry", return_value=registry),
                patch("src.diagnostics.importlib.util.find_spec", return_value=object()),
            ):
                result = run_doctor(AppConfig(output_dir=str(root / "output")), project_root=root)
        self.assertFalse(result["healthy"])
        by_name = {item["name"]: item for item in result["checks"]}
        self.assertEqual(by_name["ffmpeg"]["status"], "error")
        self.assertEqual(by_name["provider:deepseek"]["status"], "warning")
        self.assertNotIn("api_key", str(result).lower())

    def test_missing_optional_provider_does_not_make_doctor_unhealthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tools = [
                ExecutableStatus(name="ffmpeg", available=True, path="ffmpeg"),
                ExecutableStatus(name="ffprobe", available=True, path="ffprobe"),
            ]
            registry = SimpleNamespace(
                statuses=lambda: [
                    {"name": "gemini", "model": "model", "configured": False, "capabilities": ["text", "images"]}
                ]
            )
            with (
                patch("src.diagnostics.runtime_tool_statuses", return_value=tools),
                patch("src.diagnostics.ProviderRegistry", return_value=registry),
                patch("src.diagnostics.importlib.util.find_spec", return_value=object()),
            ):
                result = run_doctor(AppConfig(output_dir=str(root / "output")), project_root=root)
        self.assertTrue(result["healthy"])
