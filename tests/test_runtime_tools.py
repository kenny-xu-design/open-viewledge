from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.runtime_tools import executable_status, resolve_executable, runtime_tool_statuses
from src.utils import UserFacingError


class RuntimeToolTests(unittest.TestCase):
    def _tool(self, root: Path, name: str) -> Path:
        path = root / f"{name}.exe"
        path.write_bytes(b"tool")
        return path

    def test_explicit_path_precedes_environment_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            explicit = self._tool(root, "explicit")
            env_tool = self._tool(root, "environment")
            found = resolve_executable(
                "ffmpeg",
                explicit,
                environ={"FFMPEG_PATH": str(env_tool)},
                which=lambda _: str(root / "path.exe"),
                project_root=root / "project",
            )
        self.assertEqual(found, str(explicit.resolve()))

    def test_invalid_explicit_path_is_not_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(UserFacingError, "配置项 ffmpeg_path"):
                resolve_executable(
                    "ffmpeg",
                    root / "missing.exe",
                    environ={"FFMPEG_PATH": str(self._tool(root, "environment"))},
                    which=lambda _: str(self._tool(root, "path")),
                    project_root=root,
                )

    def test_environment_precedes_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env_tool = self._tool(root, "environment")
            found = resolve_executable(
                "ffprobe",
                environ={"FFPROBE_PATH": str(env_tool)},
                which=lambda _: str(root / "path.exe"),
                project_root=root / "project",
            )
        self.assertEqual(found, str(env_tool.resolve()))

    def test_path_discovery_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tool = self._tool(Path(temp), "ffmpeg")
            found = resolve_executable(
                "ffmpeg",
                environ={},
                which=lambda _: str(tool),
                project_root=Path(temp) / "project",
            )
        self.assertEqual(found, str(tool.resolve()))

    def test_project_local_fallback_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tool = root / "tools" / "ffmpeg" / "bin" / "ffprobe.exe"
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b"tool")
            found = resolve_executable(
                "ffprobe",
                environ={},
                which=lambda _: None,
                project_root=root,
            )
        self.assertEqual(found, str(tool.resolve()))

    def test_missing_error_lists_all_configuration_options(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(UserFacingError, "FFMPEG_PATH") as caught:
                resolve_executable(
                    "ffmpeg",
                    environ={},
                    which=lambda _: None,
                    project_root=Path(temp),
                )
        message = str(caught.exception)
        self.assertIn("ffmpeg_path", message)
        self.assertIn("PATH", message)
        self.assertIn("不会自动下载", message)

    def test_ffmpeg_and_ffprobe_statuses_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ffmpeg = self._tool(root, "ffmpeg")
            statuses = runtime_tool_statuses(
                ffmpeg_path=ffmpeg,
                environ={},
                which=lambda _: None,
                project_root=root / "project",
            )
        self.assertTrue(statuses[0].available)
        self.assertFalse(statuses[1].available)
        self.assertIn("FFPROBE_PATH", statuses[1].error)

    def test_status_reports_discovery_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            tool = self._tool(Path(temp), "ffmpeg")
            status = executable_status(
                "ffmpeg",
                environ={},
                which=lambda _: str(tool),
                project_root=Path(temp) / "project",
            )
        self.assertEqual(status.source, "PATH")
