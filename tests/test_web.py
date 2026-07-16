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
    runtime_status_payload,
    _timestamp_seconds,
    _external_player_descriptor,
)


class WebCommandTests(unittest.TestCase):
    def test_official_external_player_descriptors(self) -> None:
        self.assertEqual(
            _external_player_descriptor("https://www.youtube.com/watch?v=BqF6PUAXY1M"),
            {"provider": "youtube", "videoId": "BqF6PUAXY1M"},
        )
        bilibili = _external_player_descriptor("https://www.bilibili.com/video/BV19mMu66Eap/")
        self.assertEqual(bilibili["provider"], "bilibili")
        self.assertEqual(bilibili["videoId"], "BV19mMu66Eap")
        self.assertIsNone(_external_player_descriptor("https://example.com/video"))

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

    def test_runtime_status_reports_tools_and_provider_models_without_keys(self) -> None:
        with patch("src.web.runtime_tool_statuses") as mocked_tools, patch("src.web.ProviderRegistry") as registry:
            mocked_tools.return_value = [
                __import__("src.runtime_tools", fromlist=["ExecutableStatus"]).ExecutableStatus(
                    name="ffmpeg",
                    available=True,
                    path="C:/tools/ffmpeg.exe",
                    source="PATH",
                )
            ]
            registry.return_value.statuses.return_value = [
                {"name": "deepseek", "model": "deepseek-v4-flash", "configured": True}
            ]
            payload = runtime_status_payload()

        self.assertEqual(payload["tools"][0]["name"], "ffmpeg")
        self.assertEqual(payload["providers"][0]["model"], "deepseek-v4-flash")
        self.assertNotIn("api_key", json.dumps(payload).lower())


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
        (package / "index.md").write_text("# 真实记录\n\n## 摘要\n\n摘要内容。\n", encoding="utf-8")
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
        self.assertEqual(detail["analysis"]["status"], "failed")
        self.assertEqual(detail["status"], "partial")
        self.assertEqual(detail["inspection"]["analysis_status"], "invalid")

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

    def test_completed_manifest_with_empty_analysis_is_exposed_as_invalid(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "manifest.json").write_text(
                '{"task_id":"task","status":"completed","source":{"source_type":"online_video","platform":"youtube","source_url":"https://example.com","source_id":"id","title":"Demo"},"stage_status":{"run_analysis":"completed"}}',
                encoding="utf-8",
            )
            (package / "analysis.json").write_text("{}", encoding="utf-8")
            with patch("src.web.OUTPUT_ROOT", root):
                detail = load_knowledge_package("demo")
                items = list_library_items()

        self.assertEqual(detail["status"], "invalid")
        self.assertEqual(detail["analysis"]["status"], "failed")
        self.assertEqual(items[0]["status"], "invalid")


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

    @patch("src.web.chat_with_knowledge")
    def test_chat_endpoint_returns_grounded_response(self, mocked_chat) -> None:
        mocked_chat.return_value = {
            "answer": "回答 [1]",
            "citations": [{"index": 1, "start": 30}],
            "provider": "deepseek",
            "model": "test-model",
            "usage": {},
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps({"knowledge_id": "demo", "question": "test"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["answer"], "回答 [1]")
        self.assertEqual(payload["citations"][0]["start"], 30)

    def test_runtime_endpoint_reports_current_python(self) -> None:
        with urlopen(f"{self.base_url}/api/runtime", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["pythonExecutable"], __import__("sys").executable)
        self.assertIn("tools", payload)
        self.assertIn("providers", payload)
        self.assertIn("inProjectVenv", payload)

    def test_notes_endpoint_persists_and_updates_compatible_export(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = WebLibraryTests()._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with urlopen(f"{self.base_url}/api/library/demo/notes", timeout=3) as response:
                    initial = json.loads(response.read().decode("utf-8"))["note"]
                request = Request(
                    f"{self.base_url}/api/library/demo/notes",
                    data=json.dumps({"content": "持久化笔记", "revision": initial["revision"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with urlopen(request, timeout=3) as response:
                    saved = json.loads(response.read().decode("utf-8"))
                with urlopen(f"{self.base_url}/api/library/demo/notes", timeout=3) as response:
                    reloaded = json.loads(response.read().decode("utf-8"))["note"]
            self.assertEqual(saved["note"]["content"], "持久化笔记")
            self.assertEqual(reloaded["content"], "持久化笔记")
            self.assertEqual((package / "user_notes.md").read_text(encoding="utf-8"), "持久化笔记")
            self.assertIn("持久化笔记", (package / "export_note.md").read_text(encoding="utf-8"))

    def test_notes_endpoint_rejects_stale_revision(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            WebLibraryTests()._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with urlopen(f"{self.base_url}/api/library/demo/notes", timeout=3) as response:
                    initial = json.loads(response.read().decode("utf-8"))["note"]
                first = Request(
                    f"{self.base_url}/api/library/demo/notes",
                    data=json.dumps({"content": "第一版", "revision": initial["revision"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with urlopen(first, timeout=3):
                    pass
                stale = Request(
                    f"{self.base_url}/api/library/demo/notes",
                    data=json.dumps({"content": "过期版本", "revision": initial["revision"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with self.assertRaises(HTTPError) as context:
                    urlopen(stale, timeout=3)

        self.assertEqual(context.exception.code, 409)


if __name__ == "__main__":
    unittest.main()
