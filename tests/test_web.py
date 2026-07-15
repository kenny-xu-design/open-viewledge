from __future__ import annotations

import unittest
import json
import threading
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.web import (
    PROJECT_ROOT,
    VideoSummaryHandler,
    _is_project_venv_python,
    _runtime_python_warning,
    build_cli_command,
    list_library_items,
    load_knowledge_package,
    load_transcript_groups,
    resolve_library_file,
    _timestamp_seconds,
)


class WebCommandTests(unittest.TestCase):
    def test_build_url_command(self) -> None:
        python_executable = r"C:\test\.venv\Scripts\python.exe"
        command = build_cli_command(
            {
                "sourceType": "url",
                "source": "https://www.bilibili.com/video/BV123",
                "backend": "deepseek",
                "mode": "viral",
                "export": "obsidian",
            },
            python_executable=python_executable,
        )

        self.assertEqual(
            command,
            [
                python_executable,
                "-m",
                "src.main",
                "--url",
                "https://www.bilibili.com/video/BV123",
                "--backend",
                "deepseek",
                "--mode",
                "viral",
                "--export",
                "obsidian",
            ],
        )

    def test_build_command_defaults_to_current_python_executable(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "url",
                "source": "https://example.com/video",
                "backend": "deepseek",
                "mode": "summary",
            }
        )

        self.assertEqual(command[0], __import__("sys").executable)

    def test_project_venv_python_detection(self) -> None:
        venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
        self.assertTrue(_is_project_venv_python(str(venv_python)))

    def test_non_venv_python_warning(self) -> None:
        global_python = str(Path("C:/Users/example/AppData/Local/Programs/Python/Python312/python.exe"))
        self.assertIn("当前 Web UI 未运行在项目虚拟环境中", _runtime_python_warning(global_python))

    def test_build_file_command_with_no_summary(self) -> None:
        python_executable = r"C:\test\.venv\Scripts\python.exe"
        command = build_cli_command(
            {
                "sourceType": "file",
                "source": r"E:\Downloads_E\video.mp4",
                "backend": "deepseek",
                "mode": "summary",
                "noSummary": True,
                "lang": "zh",
            },
            python_executable=python_executable,
        )

        self.assertEqual(
            command,
            [
                python_executable,
                "-m",
                "src.main",
                "--file",
                r"E:\Downloads_E\video.mp4",
                "--lang",
                "zh",
                "--backend",
                "deepseek",
                "--mode",
                "summary",
                "--no-summary",
            ],
        )

    def test_build_file_command_strips_wrapping_quotes(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "file",
                "source": r' "E:\Downloads_E\video.mp4" ',
                "backend": "deepseek",
                "mode": "summary",
            },
            python_executable=r"C:\test\.venv\Scripts\python.exe",
        )

        self.assertIn(r"E:\Downloads_E\video.mp4", command)
        self.assertNotIn(r'"E:\Downloads_E\video.mp4"', command)

    def test_build_file_command_strips_chinese_wrapping_quotes(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "file",
                "source": r"“E:\Downloads_E\video.mp4”",
                "backend": "deepseek",
                "mode": "summary",
            },
            python_executable=r"C:\test\.venv\Scripts\python.exe",
        )

        self.assertIn(r"E:\Downloads_E\video.mp4", command)

    def test_reject_empty_source(self) -> None:
        with self.assertRaises(ValueError):
            build_cli_command({"sourceType": "url", "source": ""}, python_executable=r"C:\test\.venv\Scripts\python.exe")

    def test_build_command_with_sample_seconds(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "file",
                "source": r"E:\Downloads_E\video.mp4",
                "backend": "deepseek",
                "mode": "summary",
                "sampleSeconds": "30",
            },
            python_executable=r"C:\test\.venv\Scripts\python.exe",
        )

        self.assertEqual(command[-2:], ["--sample-seconds", "30"])

    def test_rejects_retired_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "只能是 deepseek"):
            build_cli_command(
                {"sourceType": "url", "source": "https://example.com/video", "backend": "ollama"},
                python_executable=r"C:\test\.venv\Scripts\python.exe",
            )

    def test_timestamp_conversion(self) -> None:
        self.assertEqual(_timestamp_seconds("01:30"), 90)
        self.assertEqual(_timestamp_seconds("01:01:01"), 3661)


class WebLibraryTests(unittest.TestCase):
    def _write_package(self, root: Path, name: str = "demo") -> Path:
        package = root / name
        package.mkdir()
        (package / "metadata.json").write_text(
            '{"title":"真实记录","platform":"local","source_path":"C:/private/video.mp4"}',
            encoding="utf-8",
        )
        (package / "manifest.json").write_text(
            '{"status":"partial","source":{"title":"真实记录","platform":"local","local_path":"C:/private/video.mp4"}}',
            encoding="utf-8",
        )
        (package / "transcript.grouped.md").write_text(
            "# 分组字幕\n\n## 1. 开场\n\n**时间：00:00 - 00:12**\n\n这是分组字幕。\n",
            encoding="utf-8",
        )
        return package

    def test_library_lists_only_knowledge_packages(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            (root / "unrelated").mkdir()
            with patch("src.web.OUTPUT_ROOT", root):
                items = list_library_items()

        self.assertEqual([item["id"] for item in items], ["demo"])
        self.assertEqual(items[0]["status"], "partial")

    def test_detail_omits_private_local_path_and_tolerates_missing_analysis(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                detail = load_knowledge_package("demo")

        self.assertNotIn("local_path", detail["source"])
        self.assertNotIn("source_path", detail["source"])
        self.assertEqual(detail["analysis"], {})
        self.assertEqual(detail["status"], "partial")

    def test_grouped_transcript_is_parsed_without_loading_raw_transcript(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                groups = load_transcript_groups("demo")

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["title"], "开场")
        self.assertEqual(groups[0]["text"], "这是分组字幕。")

    def test_library_file_rejects_path_traversal_and_non_whitelisted_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with self.assertRaises(ValueError):
                    resolve_library_file("demo", "../metadata.json")
                with self.assertRaises(ValueError):
                    resolve_library_file("demo", "secret.txt")


class QuietVideoSummaryHandler(VideoSummaryHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietVideoSummaryHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_missing_knowledge_package_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/library/definitely-missing", timeout=3)
        self.assertEqual(context.exception.code, 404)

    def test_chat_endpoint_returns_real_not_implemented_response(self) -> None:
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps({"knowledge_id": "demo", "question": "test"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=3)
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 501)
        self.assertEqual(payload["error"], "上下文对话功能尚未接入")

    def test_runtime_endpoint_reports_current_python(self) -> None:
        with urlopen(f"{self.base_url}/api/runtime", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["pythonExecutable"], __import__("sys").executable)
        self.assertIn("inProjectVenv", payload)


if __name__ == "__main__":
    unittest.main()
