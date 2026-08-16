from __future__ import annotations

import unittest
import json
import os
import stat
import threading
import time
from types import SimpleNamespace
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src import __version__
from src.intake_store import IntakeStore
from src.clip_store import ClipStore
from src.folder_sets import FolderSetStore
from src.knowledge_sets import KnowledgeSetStore
from src.project_groups import ProjectGroupStore
from src.knowledge_identity import KnowledgeRequestDimensions, build_input_knowledge_identity
from src.job_store import Job
from src.utils import UserFacingError
from src.web import (
    KnowledgeDeletionError,
    PROJECT_ROOT,
    DuplicateTaskError,
    VideoSummaryHandler,
    VideoSummaryServer,
    _is_project_venv_python,
    _runtime_python_warning,
    _strip_product_details,
    build_cli_command,
    delete_knowledge_packages,
    list_library_items,
    library_items_with_membership,
    load_knowledge_package,
    load_transcript_groups,
    job_to_dict,
    resolve_library_file,
    runtime_status_payload,
    search_local_knowledge,
    start_job,
    _timestamp_seconds,
    _external_player_descriptor,
    _handle_cli_output_line,
    _normalize_analysis_view,
)


class WebCommandTests(unittest.TestCase):
    def test_asr_status_preserves_cpu_stall_error_code(self) -> None:
        job = Job(id="job", command=[])
        payload = {
            "schema_version": "1.0",
            "event": "asr_status",
            "requested_route": "local_gpu",
            "actual_provider": "faster-whisper",
            "actual_device": "cpu",
            "fallback_used": True,
            "fallback_reason": "cpu_transcription_stalled",
            "asr_worker_status": "terminated",
            "transcript_status": "timeout",
        }
        with patch("src.web._persist_job"):
            _handle_cli_output_line(job, json.dumps(payload))
        self.assertEqual(job.transcript_actual_device, "cpu")
        self.assertEqual(job.transcript_status, "timeout")
        self.assertEqual(job.error_code, "cpu_transcription_stalled")

    def test_product_and_diagnostic_job_payloads_keep_credentials_redacted(self) -> None:
        job = Job(
            id="diagnostic",
            command=["python", "--authorization=Bearer secret-token"],
            analysis_model="private-model",
            transcript_model="turbo",
            logs=[
                f"project={PROJECT_ROOT}",
                "Cookie: session=private-cookie",
                "Authorization: Bearer secret-token",
            ],
        )
        with patch.dict(os.environ, {}, clear=True):
            product = job_to_dict(job)
        self.assertNotIn("analysisModel", product)
        self.assertNotIn("transcriptModel", product)
        self.assertNotIn("command", product)
        self.assertNotIn(str(PROJECT_ROOT), json.dumps(product))

        with patch.dict(
            os.environ,
            {
                "VIEWLEDGE_UI_MODE": "diagnostic",
                "SHOW_TECH_DETAILS": "1",
                "SHOW_RAW_PROCESS_LOGS": "1",
            },
            clear=True,
        ):
            diagnostic = job_to_dict(job)
        self.assertEqual(diagnostic["analysisModel"], "private-model")
        self.assertEqual(diagnostic["transcriptModel"], "turbo")
        serialized = json.dumps(diagnostic)
        self.assertNotIn("private-cookie", serialized)
        self.assertNotIn("secret-token", serialized)

    def test_product_payload_keeps_media_embed_fields_for_preview(self) -> None:
        payload = {
            "analysis": {"provider": "deepseek", "model": "private-model"},
            "media": {
                "embed": {
                    "provider": "youtube",
                    "videoId": "BqF6PUAXY1M",
                    "url": "https://player.example/embed",
                }
            },
        }

        product = _strip_product_details(payload)

        self.assertNotIn("provider", product["analysis"])
        self.assertNotIn("model", product["analysis"])
        self.assertEqual(product["media"]["embed"]["provider"], "youtube")
        self.assertEqual(product["media"]["embed"]["videoId"], "BqF6PUAXY1M")
        self.assertEqual(product["media"]["embed"]["url"], "https://player.example/embed")

    def test_web_reads_public_cli_jsonl_completion(self) -> None:
        job = Job(id="job", command=[])
        _handle_cli_output_line(
            job,
            json.dumps({"schema_version": "1.0", "event": "task_created", "task_id": "task"}),
        )
        _handle_cli_output_line(
            job,
            json.dumps(
                {
                    "schema_version": "1.0",
                    "event": "first_readable_result",
                    "task_id": "task",
                    "stage": "group_transcript",
                    "duration_ms": 42,
                }
            ),
        )
        _handle_cli_output_line(
            job,
            json.dumps(
                {
                    "schema_version": "1.0",
                    "event": "task_completed",
                    "task_id": "task",
                    "result": {
                        "output_dir": "output/demo",
                        "knowledge_id": "demo",
                        "analysis_requested": True,
                        "analysis_status": "completed",
                        "analysis_provider": "deepseek",
                        "analysis_model": "test-model",
                        "transcript_only": False,
                        "analysis": {
                            "status": "success",
                            "provider": "deepseek",
                            "model": "test-model",
                        },
                    },
                }
            ),
        )
        self.assertEqual(job.output_dir, "output/demo")
        self.assertEqual(job.knowledge_id, "demo")
        self.assertEqual(job.cli_task_id, "task")
        self.assertTrue(job.analysis_requested)
        self.assertEqual(job.analysis_status, "completed")
        self.assertEqual(job.analysis_provider, "deepseek")
        self.assertEqual(job.analysis_model, "test-model")
        self.assertFalse(job.transcript_only)
        self.assertTrue(any("first_readable_result" in line for line in job.logs))

    def test_official_external_player_descriptors(self) -> None:
        self.assertEqual(
            _external_player_descriptor("https://www.youtube.com/watch?v=BqF6PUAXY1M"),
            {"provider": "youtube", "videoId": "BqF6PUAXY1M"},
        )
        bilibili = _external_player_descriptor("https://www.bilibili.com/video/BV19mMu66Eap/")
        self.assertEqual(bilibili["provider"], "bilibili")
        self.assertEqual(bilibili["videoId"], "BV19mMu66Eap")
        self.assertIn("p=1", bilibili["url"])
        bilibili_part = _external_player_descriptor("https://www.bilibili.com/video/BV19mMu66Eap/?from=search&p=3")
        self.assertIn("bvid=BV19mMu66Eap", bilibili_part["url"])
        self.assertIn("p=3", bilibili_part["url"])
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
                "analyze",
                "--url",
                "https://www.bilibili.com/video/BV123",
                "--backend",
                "deepseek",
                "--mode",
                "viral",
                "--processing-profile",
                "complete",
                "--export",
                "obsidian",
                "--jsonl",
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
                "analyze",
                "--file",
                r"E:\Downloads_E\video.mp4",
                "--lang",
                "zh",
                "--backend",
                "deepseek",
                "--mode",
                "summary",
                "--processing-profile",
                "complete",
                "--no-summary",
                "--jsonl",
            ],
        )

    def test_analysis_is_requested_by_default_and_false_strings_do_not_skip(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "url",
                "source": "https://example.com/video",
                "skip_analysis": "false",
                "transcribe_only": False,
                "analysis_enabled": True,
                "analysis_requested": True,
            },
            python_executable="python",
        )
        self.assertNotIn("--no-summary", command)

    def test_legacy_and_canonical_transcript_only_flags_are_honored(self) -> None:
        for payload in (
            {"skip_analysis": True},
            {"transcribe_only": True},
            {"analysis_enabled": False},
            {"analysis_requested": False},
        ):
            with self.subTest(payload=payload):
                command = build_cli_command(
                    {
                        "sourceType": "url",
                        "source": "https://example.com/video",
                        **payload,
                    },
                    python_executable="python",
                )
                self.assertIn("--no-summary", command)

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

        self.assertEqual(command[-3:], ["--sample-seconds", "30", "--jsonl"])

    def test_build_command_with_transcript_group_seconds(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "file",
                "source": r"E:\Downloads_E\video.mp4",
                "backend": "deepseek",
                "mode": "summary",
                "transcriptGroupSeconds": "15",
            },
            python_executable=r"C:\test\.venv\Scripts\python.exe",
        )

        group_index = command.index("--transcript-group-seconds")
        self.assertEqual(command[group_index + 1], "15")

    def test_build_command_rejects_too_small_transcript_group_seconds(self) -> None:
        with self.assertRaisesRegex(ValueError, "transcriptGroupSeconds"):
            build_cli_command(
                {
                    "sourceType": "file",
                    "source": r"E:\Downloads_E\video.mp4",
                    "backend": "deepseek",
                    "mode": "summary",
                    "transcriptGroupSeconds": "14",
                },
                python_executable=r"C:\test\.venv\Scripts\python.exe",
            )

    def test_build_command_accepts_fast_processing_profile(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "url",
                "source": "https://example.com/video",
                "backend": "deepseek",
                "mode": "summary",
                "processingProfile": "fast",
                "noFrames": True,
            },
            python_executable=r"C:\test\.venv\Scripts\python.exe",
        )

        profile_index = command.index("--processing-profile")
        self.assertEqual(command[profile_index + 1], "fast")
        self.assertIn("--no-frames", command)

    def test_build_command_can_enable_comments(self) -> None:
        command = build_cli_command(
            {
                "sourceType": "url",
                "source": "https://www.youtube.com/watch?v=abc123",
                "backend": "deepseek",
                "mode": "summary",
                "comments": True,
            },
            python_executable=r"C:\test\.venv\Scripts\python.exe",
        )

        self.assertIn("--comments", command)

    def test_build_command_rejects_invalid_processing_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "processing_profile"):
            build_cli_command(
                {
                    "sourceType": "url",
                    "source": "https://example.com/video",
                    "processingProfile": "turbo",
                },
                python_executable=r"C:\test\.venv\Scripts\python.exe",
            )

    def test_job_api_payload_exposes_separate_profiles(self) -> None:
        payload = job_to_dict(
            Job(
                id="job",
                command=[],
                analysis_profile="tutorial",
                processing_profile="fast",
            )
        )

        self.assertEqual(payload["analysisProfile"], "tutorial")
        self.assertEqual(payload["processingProfile"], "fast")

    def test_cli_jsonl_identity_fields_update_web_job(self) -> None:
        job = Job(id="job", command=[])
        _handle_cli_output_line(
            job,
            json.dumps(
                {
                    "schema_version": "1.0",
                    "event": "task_created",
                    "task_id": "task",
                    "knowledge_id": "k1-web-source",
                    "identity_schema_version": "1.0",
                    "request_fingerprint": "request-fp",
                }
            ),
        )

        self.assertEqual(job.knowledge_id, "k1-web-source")
        self.assertEqual(job.identity_schema_version, "1.0")
        self.assertEqual(job.request_fingerprint, "request-fp")

    def test_start_job_rejects_active_exact_duplicate_before_thread_start(self) -> None:
        payload = {
            "sourceType": "url",
            "source": "https://example.com/video",
            "mode": "summary",
            "noSummary": True,
        }
        identity = build_input_knowledge_identity(
            payload["source"],
            is_url=True,
            dimensions=KnowledgeRequestDimensions(language="zh", transcript_only=True),
        )
        active = Job(
            id="active",
            command=[],
            status="running",
            knowledge_id=identity.knowledge_id,
            request_fingerprint=identity.request_fingerprint,
        )
        with (
            patch("src.web.JOBS", {"active": active}),
            patch("src.web.ensure_data_directory_writable"),
            patch("src.web.threading.Thread") as thread,
        ):
            with self.assertRaises(DuplicateTaskError):
                start_job(payload)

        thread.assert_not_called()

    def test_start_job_reuses_completed_exact_duplicate_without_thread_start(self) -> None:
        payload = {
            "sourceType": "url",
            "source": "https://example.com/video",
            "mode": "summary",
            "noSummary": True,
            "duplicateAction": "reuse",
        }
        identity = build_input_knowledge_identity(
            payload["source"],
            is_url=True,
            dimensions=KnowledgeRequestDimensions(language="zh", transcript_only=True),
        )
        completed = Job(
            id="completed",
            command=[],
            status="success",
            returncode=0,
            cli_task_id="cli-completed",
            knowledge_id=identity.knowledge_id,
            request_fingerprint=identity.request_fingerprint,
            identity_schema_version=identity.schema_version,
            output_dir="output/existing-package",
            analysis_status="skipped",
            transcript_status="success",
        )
        with (
            patch("src.web.JOBS", {"completed": completed}),
            patch("src.web.ensure_data_directory_writable"),
            patch("src.web._persist_job"),
            patch("src.web.threading.Thread") as thread,
        ):
            job = start_job(payload)

        self.assertEqual(job.status, "success")
        self.assertEqual(job.returncode, 0)
        self.assertEqual(job.output_dir, "output/existing-package")
        self.assertEqual(job.cli_task_id, "cli-completed")
        self.assertEqual(job.duplicate_kind, "completed_exact")
        self.assertEqual(job.duplicate_matched_task_id, "completed")
        self.assertIn("reuse", job.duplicate_allowed_actions)
        thread.assert_not_called()

    def test_start_job_resumes_recoverable_exact_duplicate_with_cli_resume_command(self) -> None:
        payload = {
            "sourceType": "url",
            "source": "https://example.com/video",
            "mode": "summary",
            "noSummary": True,
            "duplicateAction": "resume",
        }
        identity = build_input_knowledge_identity(
            payload["source"],
            is_url=True,
            dimensions=KnowledgeRequestDimensions(language="zh", transcript_only=True),
        )
        recoverable = Job(
            id="failed",
            command=[],
            status="failed",
            cli_task_id="cli-failed",
            knowledge_id=identity.knowledge_id,
            request_fingerprint=identity.request_fingerprint,
            identity_schema_version=identity.schema_version,
        )
        with (
            patch("src.web.JOBS", {"failed": recoverable}),
            patch("src.web.ensure_data_directory_writable"),
            patch("src.web._persist_job"),
            patch("src.web.threading.Thread") as thread,
        ):
            job = start_job(payload)

        self.assertEqual(job.command[-4:], ["src.main", "resume", "cli-failed", "--jsonl"])
        self.assertEqual(job.duplicate_kind, "recoverable_exact")
        self.assertEqual(job.duplicate_matched_task_id, "failed")
        self.assertIn("resume", job.duplicate_allowed_actions)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_start_job_rejects_invalid_duplicate_action_before_thread_start(self) -> None:
        payload = {
            "sourceType": "url",
            "source": "https://example.com/video",
            "mode": "summary",
            "noSummary": True,
            "duplicateAction": "resume",
        }
        identity = build_input_knowledge_identity(
            payload["source"],
            is_url=True,
            dimensions=KnowledgeRequestDimensions(language="zh", transcript_only=True),
        )
        completed = Job(
            id="completed",
            command=[],
            status="success",
            knowledge_id=identity.knowledge_id,
            request_fingerprint=identity.request_fingerprint,
            identity_schema_version=identity.schema_version,
            output_dir="output/existing-package",
        )
        with (
            patch("src.web.JOBS", {"completed": completed}),
            patch("src.web.ensure_data_directory_writable"),
            patch("src.web.threading.Thread") as thread,
        ):
            with self.assertRaisesRegex(ValueError, "duplicateAction"):
                start_job(payload)

        thread.assert_not_called()

    def test_rejects_retired_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "只能是 deepseek"):
            build_cli_command(
                {"sourceType": "url", "source": "https://example.com/video", "backend": "ollama"},
                python_executable=r"C:\test\.venv\Scripts\python.exe",
            )

    def test_timestamp_conversion(self) -> None:
        self.assertEqual(_timestamp_seconds("01:30"), 90)
        self.assertEqual(_timestamp_seconds("01:01:01"), 3661)

    def test_runtime_status_reports_provider_models_only_in_diagnostic_mode(self) -> None:
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
            with patch.dict(
                os.environ,
                {
                    "VIEWLEDGE_UI_MODE": "diagnostic",
                    "SHOW_TECH_DETAILS": "1",
                },
                clear=False,
            ):
                payload = runtime_status_payload()

        self.assertEqual(payload["tools"][0]["name"], "ffmpeg")
        self.assertEqual(payload["providers"][0]["model"], "deepseek-v4-flash")
        self.assertNotIn("api_key", json.dumps(payload).lower())
        self.assertNotIn("keyTail", json.dumps(payload))

    def test_product_capabilities_use_only_generic_fields(self) -> None:
        raw = {
            "status": "available",
            "updatedAt": 1,
            "capabilities": {
                "deepseek": {"status": "available", "model": "private-model"},
                "groq": {"status": "config_required", "reason": "groq_api_key_missing"},
                "gemini": {"status": "available", "model": "vision-model"},
                "ffmpeg": {"status": "available", "source": "C:/private/ffmpeg.exe"},
                "ffprobe": {"status": "available", "source": "C:/private/ffprobe.exe"},
                "local_model": {"status": "available", "models": ["small", "turbo"]},
                "local_cpu": {"status": "available"},
                "local_gpu": {"status": "unavailable", "computeTypes": ["float16"]},
            },
        }
        module = __import__("src.web", fromlist=["capability_payload"])
        old_cache = module.CAPABILITY_CACHE
        try:
            with patch.dict(os.environ, {"VIEWLEDGE_UI_MODE": "product"}, clear=False), patch(
                "src.web.CapabilityRegistry.inspect",
                return_value=raw,
            ):
                module.CAPABILITY_CACHE = {}
                payload = module.capability_payload(refresh=True)
        finally:
            module.CAPABILITY_CACHE = old_cache
        serialized = json.dumps(payload)
        self.assertEqual(
            set(payload["capabilities"]),
            {
                "analysis_text",
                "cloud_transcription",
                "visual_understanding",
                "media_processing",
                "local_model",
                "local_cpu",
                "local_gpu",
            },
        )
        for forbidden in ("deepseek", "groq", "gemini", "private-model", "small", "turbo", "C:/private"):
            self.assertNotIn(forbidden, serialized)

    def test_product_provider_status_does_not_return_credentials_or_models(self) -> None:
        module = __import__("src.web", fromlist=["provider_config_payload"])
        statuses = [
            {
                "provider": "deepseek",
                "name": "deepseek",
                "configured": True,
                "baseUrl": "https://private.invalid",
                "model": "secret-model",
                "keyTail": "1234",
                "lastTest": {"ok": True, "model": "secret-model"},
            }
        ]
        with patch.dict(os.environ, {"VIEWLEDGE_UI_MODE": "product"}, clear=False), patch(
            "src.web.ProviderConfigResolver.statuses",
            return_value=statuses,
        ):
            payload = module.provider_config_payload()
        serialized = json.dumps(payload)
        self.assertEqual(payload["providers"][0]["service"], "analysis_text")
        for forbidden in ("deepseek", "secret-model", "private.invalid", "1234", "keyTail"):
            self.assertNotIn(forbidden, serialized)


    def test_scheduler_runs_fifo_with_a_persisted_queue_state(self) -> None:
        import src.web as web_module

        first = Job(id="first", command=[], created_at=1)
        second = Job(id="second", command=[], created_at=2)
        completed: list[str] = []

        def fake_run(job: Job) -> None:
            completed.append(job.id)
            job.status = "success"

        with (
            patch.object(web_module, "JOBS", {first.id: first, second.id: second}),
            patch.object(web_module, "_persist_job"),
            patch.object(web_module, "_run_job", side_effect=fake_run),
        ):
            t1 = threading.Thread(target=web_module._run_scheduled_job, args=(first,))
            t2 = threading.Thread(target=web_module._run_scheduled_job, args=(second,))
            t1.start()
            t2.start()
            t1.join(2)
            t2.join(2)

        self.assertEqual(completed, ["first", "second"])


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
        self.assertEqual(items[0]["processingProfile"], "complete")

    def test_local_search_keeps_transcript_out_of_fast_results_until_deep_enabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "analysis.json").write_text(
                json.dumps({"summary": "摘要中包含快速检索词", "tags": ["标签词"]}),
                encoding="utf-8",
            )
            (package / "transcript.grouped.md").write_text(
                "# 分组字幕\n\n只有深度字幕词会出现在正文中。\n",
                encoding="utf-8",
            )
            with patch("src.web.OUTPUT_ROOT", root):
                library = list_library_items()
            with (
                patch("src.web.OUTPUT_ROOT", root),
                patch("src.web.library_items_with_membership", return_value=library),
                patch("src.web.KNOWLEDGE_SET_STORE", Mock(list=Mock(return_value=[]))),
                patch("src.web.FOLDER_SET_STORE", Mock(list=Mock(return_value=[]))),
                patch("src.web.PROJECT_GROUP_STORE", Mock(list=Mock(return_value=[]))),
            ):
                fast = search_local_knowledge("深度字幕词")
                deep = search_local_knowledge("深度字幕词", deep=True)
                summary = search_local_knowledge("快速检索词")

        self.assertEqual(fast["items"], [])
        self.assertEqual(deep["items"][0]["matchField"], "字幕正文")
        self.assertEqual(summary["items"][0]["matchField"], "knowledge")
        self.assertNotIn("C:/private", json.dumps(deep, ensure_ascii=False))

    def test_local_search_rejects_invalid_query_shape(self) -> None:
        with self.assertRaises(ValueError):
            search_local_knowledge("x", kind="unsupported")
        with self.assertRaises(ValueError):
            search_local_knowledge("x", limit=51)
        with self.assertRaises(ValueError):
            search_local_knowledge("x" * 201)

    def test_library_item_exposes_video_duration_and_analysis_date(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "completed_at": "2026-08-08T02:03:04+00:00",
                        "source": {"title": "真实记录", "platform": "local", "duration": 125.5},
                    }
                ),
                encoding="utf-8",
            )
            with patch("src.web.OUTPUT_ROOT", root):
                item = list_library_items()[0]

        self.assertEqual(item["duration"], 125.5)
        self.assertEqual(item["analysisAt"], "2026-08-08T02:03:04+00:00")

    def test_library_item_exposes_completed_processing_duration(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "created_at": "2026-07-28T00:00:00+00:00",
                        "completed_at": "2026-07-28T00:02:03.500000+00:00",
                        "source": {"title": "真实记录", "platform": "local"},
                    }
                ),
                encoding="utf-8",
            )
            with patch("src.web.OUTPUT_ROOT", root):
                item = list_library_items()[0]

        self.assertEqual(item["processingDurationMs"], 123500)
        self.assertFalse(item["processingTimingLive"])

    def test_library_item_prefers_recorded_full_completion_duration(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "full_completion_duration_ms": 4567,
                        "source": {"title": "真实记录", "platform": "local"},
                    }
                ),
                encoding="utf-8",
            )
            with patch("src.web.OUTPUT_ROOT", root):
                item = list_library_items()[0]

        self.assertEqual(item["processingDurationMs"], 4567)
        self.assertFalse(item["processingTimingLive"])

    def test_analysis_view_hides_legacy_placeholder_modules(self) -> None:
        analysis = _normalize_analysis_view({
            "status": "success",
            "analysis_profile": "tutorial",
            "content": {
                "tutorial_goal": "完成真实操作",
                "prerequisites": ["未明确说明"],
                "tools_and_materials": ["未明确说明"],
                "limitations": ["未明确说明"],
            },
        })
        self.assertEqual(analysis["content"]["tutorial_goal"], "完成真实操作")
        self.assertEqual(analysis["content"]["prerequisites"], [])
        self.assertEqual(analysis["content"]["tools_and_materials"], [])
        self.assertEqual(analysis["content"]["limitations"], [])

    def test_detail_reports_transcript_and_analysis_readiness_independently(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "manifest.json").write_text(
                json.dumps(
                    {
                        "task_id": "task",
                        "status": "completed",
                        "analysis_requested": False,
                        "analysis_status": "skipped",
                        "analysis_skip_reason": "user_requested_transcript_only",
                        "transcript_only": True,
                        "source": {
                            "source_type": "online_video",
                            "platform": "youtube",
                            "source_url": "https://example.com/video",
                            "source_id": "id",
                            "title": "Demo",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (package / "analysis.json").write_text(
                '{"status":"skipped","analysis_profile":"summary"}',
                encoding="utf-8",
            )
            inspection = Mock(
                analysis_status="skipped",
                transcript_segments=1,
                level="warning",
                issues=[],
            )
            inspection.to_dict.return_value = {
                "analysis_status": "skipped",
                "transcript_segments": 1,
                "level": "warning",
                "issues": [],
            }
            with (
                patch("src.web.OUTPUT_ROOT", root),
                patch("src.web.inspect_knowledge_package", return_value=inspection),
            ):
                detail = load_knowledge_package("demo")

        self.assertTrue(detail["transcriptReady"])
        self.assertFalse(detail["analysisReady"])
        self.assertFalse(detail["analysisRequested"])
        self.assertEqual(detail["analysisStatus"], "skipped")
        self.assertEqual(
            detail["analysisSkipReason"],
            "user_requested_transcript_only",
        )

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
        self.assertEqual(detail["manifest"]["processing_profile"], "complete")
        self.assertEqual(detail["manifest"]["stage_metrics"], {})

    def test_grouped_transcript_is_parsed_without_loading_raw_transcript(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                groups = load_transcript_groups("demo")

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["title"], "开场")
        self.assertEqual(groups[0]["text"], "这是分组字幕。")

    def test_grouped_transcript_marks_video_content_kind(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                groups = load_transcript_groups("demo")
        self.assertEqual(groups[0]["contentKind"], "video_subtitle")

    def test_library_file_rejects_path_traversal_and_non_whitelisted_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with self.assertRaises(ValueError):
                    resolve_library_file("demo", "../metadata.json")
                with self.assertRaises(ValueError):
                    resolve_library_file("demo", "secret.txt")

    def test_library_file_allows_only_webp_highlight_assets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            assets = package / "assets" / "highlights"
            assets.mkdir(parents=True)
            image = assets / "highlight_001.webp"
            image.write_bytes(b"webp")
            with patch("src.web.OUTPUT_ROOT", root):
                self.assertEqual(
                    resolve_library_file("demo", "assets/highlights/highlight_001.webp"),
                    image,
                )
                with self.assertRaises(ValueError):
                    resolve_library_file("demo", "assets/highlights/script.html")

    def test_library_batch_delete_validates_all_targets_before_removal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = self._write_package(root, "first")
            second = self._write_package(root, "second")
            with patch("src.web.OUTPUT_ROOT", root):
                deleted = delete_knowledge_packages(["first"])
                with self.assertRaises(FileNotFoundError):
                    delete_knowledge_packages(["second", "missing"])

            self.assertEqual(deleted, ["first"])
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())

    def test_library_delete_removes_non_empty_directory_recursively(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            nested = package / "frames" / "nested"
            nested.mkdir(parents=True)
            (nested / "frame.jpg").write_bytes(b"frame")
            with patch("src.web.OUTPUT_ROOT", root):
                self.assertEqual(delete_knowledge_packages(["demo"]), ["demo"])
            self.assertFalse(package.exists())

    @unittest.skipUnless(os.name == "nt", "Windows read-only attribute behavior")
    def test_library_delete_clears_read_only_file_attribute(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            read_only = package / "index.md"
            read_only.chmod(stat.S_IREAD)
            with patch("src.web.OUTPUT_ROOT", root):
                self.assertEqual(delete_knowledge_packages(["demo"]), ["demo"])
            self.assertFalse(package.exists())

    @unittest.skipUnless(os.name == "nt", "Windows sharing violation behavior")
    def test_library_delete_reports_locked_file_and_preserves_package(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            locked_path = package / "index.md"
            with self.assertLogs("src.web", level="ERROR") as logs:
                with locked_path.open("rb") as locked_handle, patch("src.web.OUTPUT_ROOT", root):
                    self.assertFalse(locked_handle.closed)
                    with self.assertRaises(KnowledgeDeletionError) as caught:
                        delete_knowledge_packages(["demo"])
            self.assertEqual(caught.exception.code, "knowledge_package_locked")
            self.assertEqual(caught.exception.target, package)
            self.assertTrue(package.exists())
            self.assertIn(str(package), "\n".join(logs.output))

    def test_library_delete_rejects_path_outside_output_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with self.assertRaises(ValueError):
                    delete_knowledge_packages(["../demo"])

    def test_library_delete_rejects_stale_path_without_removing_other_package(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with self.assertRaises(FileNotFoundError):
                    delete_knowledge_packages(["missing"])
            self.assertTrue(package.exists())

    def test_job_payload_hides_stale_output_reference(self) -> None:
        job = Job(id="stale", command=[], output_dir="output/missing", knowledge_id="missing")
        payload = __import__("src.web", fromlist=["job_to_dict"]).job_to_dict(job)
        self.assertEqual(payload["knowledgeId"], "")
        self.assertNotIn("outputDir", payload)

    def test_job_payload_exposes_asr_fallback_state_only_in_diagnostic_mode(self) -> None:
        job = Job(
            id="fallback",
            command=[],
            transcript_route_requested="local_gpu",
            transcript_actual_provider="faster-whisper",
            transcript_actual_device="cpu",
            transcript_fallback_used=True,
            transcript_fallback_reason="gpu_model_load_timeout",
            asr_worker_status="completed",
            last_segment_end=12.5,
            transcript_progress=1,
        )
        with patch.dict(
            os.environ,
            {"VIEWLEDGE_UI_MODE": "diagnostic", "SHOW_TECH_DETAILS": "1"},
            clear=False,
        ):
            payload = job_to_dict(job)
        self.assertEqual(payload["transcriptActualDevice"], "cpu")
        self.assertEqual(
            payload["transcriptFallbackReason"],
            "gpu_model_load_timeout",
        )
        self.assertTrue(payload["transcriptFallbackUsed"])

    def test_job_payload_handles_absolute_shared_output_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            job = Job(id="done", command=[], output_dir=str(package), knowledge_id="demo")
            with patch("src.web.OUTPUT_ROOT", root), patch.dict(
                os.environ,
                {
                    "VIEWLEDGE_UI_MODE": "diagnostic",
                    "SHOW_TECH_DETAILS": "1",
                },
                clear=False,
            ):
                payload = job_to_dict(job)

        self.assertEqual(payload["knowledgeId"], "demo")
        self.assertEqual(payload["outputDir"], str(package.resolve()))
        self.assertIn({"name": "index.md", "url": "/output/demo/index.md"}, payload["outputFiles"])

    def test_library_delete_rejects_processing_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root)
            (package / "manifest.json").write_text('{"status":"processing"}', encoding="utf-8")
            with patch("src.web.OUTPUT_ROOT", root):
                with self.assertRaisesRegex(ValueError, "仍在处理中"):
                    delete_knowledge_packages(["demo"])

            self.assertTrue(package.exists())

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

    def test_library_membership_marks_collection_items_and_project(self) -> None:
        library = [
            {"id": "series-item", "title": "系列视频"},
            {"id": "folder-item", "title": "文件夹视频"},
            {"id": "independent", "title": "独立记录"},
        ]
        knowledge_store = Mock()
        knowledge_store.list.return_value = [SimpleNamespace(
            set_id="series-1", title="系列一", items=[SimpleNamespace(knowledge_id="series-item")]
        )]
        folder_store = Mock()
        folder_store.list.return_value = [SimpleNamespace(
            set_id="folder-1", title="文件夹一", items=[SimpleNamespace(knowledge_id="folder-item")]
        )]
        project_store = Mock()
        project_store.memberships.return_value = {"series-item": "project-1", "independent": "project-1"}
        with patch("src.web.list_library_items", return_value=library), patch(
            "src.web.KNOWLEDGE_SET_STORE", knowledge_store
        ), patch("src.web.FOLDER_SET_STORE", folder_store), patch(
            "src.web.PROJECT_GROUP_STORE", project_store
        ):
            items = library_items_with_membership()
        by_id = {item["id"]: item for item in items}
        self.assertTrue(by_id["series-item"]["inCollection"])
        self.assertEqual(by_id["series-item"]["collectionMemberships"][0]["kind"], "series")
        self.assertTrue(by_id["folder-item"]["inCollection"])
        self.assertFalse(by_id["independent"]["inCollection"])
        self.assertEqual(by_id["independent"]["projectId"], "project-1")


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

    def test_local_search_endpoint_validates_query_and_returns_private_shape(self) -> None:
        payload = {
            "query": "教程",
            "kind": "all",
            "deep": False,
            "items": [{"kind": "knowledge", "id": "k1", "title": "教程", "snippet": "摘要"}],
            "truncated": False,
        }
        with patch("src.web.search_local_knowledge", return_value=payload) as search:
            with urlopen(f"{self.base_url}/api/search?q=%E6%95%99%E7%A8%8B", timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))
        self.assertEqual(body["items"][0]["id"], "k1")
        search.assert_called_once_with("教程", kind="all", deep=False, limit=50)

        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/search?kind=unsupported", timeout=3)
        self.assertEqual(context.exception.code, 400)

    def test_project_crud_and_membership_endpoints_do_not_delete_knowledge(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "knowledge-demo"
            package.mkdir()
            marker = package / "manifest.json"
            marker.write_text('{"knowledge_id":"knowledge-demo"}', encoding="utf-8")
            before = marker.read_bytes()
            store = ProjectGroupStore(root / "projects" / "registry.json")
            library = [{"id": "knowledge-demo", "title": "示例记录"}]
            with patch("src.web.PROJECT_GROUP_STORE", store), patch(
                "src.web.list_library_items", return_value=library
            ), patch("src.web._available_knowledge_ids", return_value={"knowledge-demo"}), patch(
                "src.web.resolve_library_dir", return_value=package
            ):
                create = Request(
                    f"{self.base_url}/api/projects",
                    data=json.dumps({"title": "设计项目"}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Idempotency-Key": "project-create-1"},
                    method="POST",
                )
                with urlopen(create, timeout=3) as response:
                    created = json.loads(response.read().decode("utf-8"))
                project_id = created["project"]["projectId"]

                move = Request(
                    f"{self.base_url}/api/projects/{project_id}/records/knowledge-demo",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with urlopen(move, timeout=3) as response:
                    moved = json.loads(response.read().decode("utf-8"))
                self.assertEqual(moved["project"]["knowledgeIds"], ["knowledge-demo"])

                rename = Request(
                    f"{self.base_url}/api/projects/{project_id}",
                    data=json.dumps({"title": "更新名称"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                with urlopen(rename, timeout=3) as response:
                    renamed = json.loads(response.read().decode("utf-8"))
                self.assertEqual(renamed["project"]["title"], "更新名称")

                with urlopen(f"{self.base_url}/api/projects", timeout=3) as response:
                    projects = json.loads(response.read().decode("utf-8"))
                self.assertEqual(projects["projects"][0]["itemCount"], 1)

                delete = Request(f"{self.base_url}/api/projects/{project_id}", method="DELETE")
                with urlopen(delete, timeout=3) as response:
                    deleted = json.loads(response.read().decode("utf-8"))
                self.assertEqual(deleted["unlinkedCount"], 1)
            self.assertTrue(package.is_dir())
            self.assertEqual(marker.read_bytes(), before)

    def test_bridge_transcript_read_returns_sanitized_side_panel_payload(self) -> None:
        knowledge = {
            "manifest": {
                "source": {
                    "source_type": "online_video",
                    "title": "Demo",
                    "source_url": "https://example.com/video",
                    "local_path": "C:/private/video.mp4",
                }
            }
        }
        groups = [{"index": 0, "start": 1.5, "end": 4.0, "title": "片段 1", "text": "字幕正文", "sourceLink": "https://example.com/video"}]
        with patch("src.web.load_knowledge_package", return_value=knowledge), patch("src.web.load_transcript_groups", return_value=groups):
            with urlopen(f"{self.base_url}/v1/knowledge/demo/transcript", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["data"]["knowledge_id"], "demo")
        self.assertEqual(payload["data"]["source"], {"kind": "video", "url": "https://example.com/video"})
        self.assertEqual(payload["data"]["groups"], groups)
        self.assertNotIn("local_path", json.dumps(payload, ensure_ascii=False))

    def test_bridge_page_transcript_does_not_fabricate_media_timestamps(self) -> None:
        knowledge = {
            "manifest": {
                "source": {
                    "source_type": "web_page",
                    "title": "Page",
                    "canonical_url": "https://example.com/article",
                }
            }
        }
        with TemporaryDirectory() as temp_dir, patch("src.web.OUTPUT_ROOT", Path(temp_dir)), patch(
            "src.web.load_knowledge_package", return_value=knowledge
        ), patch("src.web.load_transcript_groups", return_value=[{
            "index": 0,
            "start": None,
            "end": None,
            "title": "Block 1",
            "text": "Page text",
            "contentKind": "web_page",
            "position": 1,
        }]):
            with urlopen(f"{self.base_url}/v1/knowledge/page/transcript", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        group = payload["data"]["groups"][0]
        self.assertIsNone(group["start"])
        self.assertIsNone(group["end"])
        self.assertEqual(group["contentKind"], "web_page")
        self.assertEqual(group["position"], 1)

    def test_bridge_source_url_resolves_to_sanitized_knowledge_matches(self) -> None:
        library = [{"id": "demo", "updatedAt": 2}, {"id": "older", "updatedAt": 1}]

        def package_for(knowledge_id: str) -> dict[str, object]:
            return {
                "title": knowledge_id,
                "source": {
                    "source_type": "online_video",
                    "title": "Demo",
                    "canonical_url": "https://example.com/video/?utm_source=test",
                    "local_path": "C:/private/video.mp4",
                },
                "transcriptReady": True,
                "analysisReady": knowledge_id == "demo",
            }

        with patch("src.web.list_library_items", return_value=library), patch("src.web.load_knowledge_package", side_effect=package_for):
            with urlopen(
                f"{self.base_url}/v1/knowledge/resolve?source_url=https%3A%2F%2Fexample.com%2Fvideo%3Futm_source%3Dclient",
                timeout=3,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["data"]["source_url"], "https://example.com/video")
        self.assertEqual([item["knowledge_id"] for item in payload["data"]["matches"]], ["demo", "older"])
        self.assertEqual(payload["data"]["matches"][0]["source"], {"kind": "video", "url": "https://example.com/video"})
        self.assertNotIn("local_path", json.dumps(payload, ensure_ascii=False))

    def test_bridge_source_url_resolves_bilibili_default_url_to_p1(self) -> None:
        library = [{"id": "part-one", "updatedAt": 2}]

        def package_for(knowledge_id: str) -> dict[str, object]:
            return {
                "title": "Part one",
                "source": {
                    "source_type": "online_video",
                    "title": "Part one",
                    "canonical_url": "https://www.bilibili.com/video/BV1wx5y6NEDv?p=1",
                },
                "transcriptReady": True,
                "analysisReady": True,
            }

        with patch("src.web.list_library_items", return_value=library), patch("src.web.load_knowledge_package", side_effect=package_for):
            with urlopen(
                f"{self.base_url}/v1/knowledge/resolve?source_url=https%3A%2F%2Fwww.bilibili.com%2Fvideo%2FBV1wx5y6NEDv%3Fspm_id_from%3D333",
                timeout=3,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual([item["knowledge_id"] for item in payload["data"]["matches"]], ["part-one"])

    def test_bridge_source_url_resolve_rejects_missing_or_unknown_urls(self) -> None:
        with self.assertRaises(HTTPError) as missing:
            urlopen(f"{self.base_url}/v1/knowledge/resolve", timeout=3)
        self.assertEqual(missing.exception.code, 400)
        with patch("src.web.list_library_items", return_value=[]):
            with self.assertRaises(HTTPError) as unknown:
                urlopen(f"{self.base_url}/v1/knowledge/resolve?source_url=https%3A%2F%2Fexample.com%2Fmissing", timeout=3)
        self.assertEqual(unknown.exception.code, 404)

    def test_bridge_clip_create_and_replay(self) -> None:
        body = {
            "schema_version": "1.0",
            "client_request_id": "client-clip",
            "kind": "highlight",
            "target": {"knowledge_id": "demo"},
            "source": {"url": "https://example.com/video", "title": "Demo"},
            "selection": {"text": "用户选择的字幕", "media_start_seconds": 2, "media_end_seconds": 5},
            "note": "稍后复习",
        }
        with TemporaryDirectory() as temp_dir, patch("src.web.CLIP_STORE", ClipStore(Path(temp_dir) / "clips.json")):
            request = Request(f"{self.base_url}/v1/clips", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "Idempotency-Key": "clip-web-key"}, method="POST")
            with urlopen(request, timeout=3) as response:
                first = json.loads(response.read().decode("utf-8"))
            with urlopen(request, timeout=3) as response:
                second = json.loads(response.read().decode("utf-8"))
            with urlopen(f"{self.base_url}/v1/clips?knowledge_id=demo", timeout=3) as response:
                listing = json.loads(response.read().decode("utf-8"))
        self.assertEqual(first["data"]["clip_id"], second["data"]["clip_id"])
        self.assertEqual(first["data"]["kind"], "highlight")
        self.assertFalse(first["data"]["idempotency_replayed"])
        self.assertTrue(second["data"]["idempotency_replayed"])
        self.assertTrue(any(item["clip_id"] == first["data"]["clip_id"] for item in listing["data"]["clips"]))

    def test_bridge_cors_requires_explicit_extension_origin(self) -> None:
        origin = "chrome-extension://abcdefghijklmnop"
        with patch.dict("os.environ", {"VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN": origin}, clear=False):
            request = Request(f"{self.base_url}/v1/inbox", headers={"Origin": origin})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)
                self.assertEqual(response.headers.get("Vary"), "Origin")

            options = Request(
                f"{self.base_url}/v1/clips",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Content-Length": "0"},
                method="OPTIONS",
            )
            with urlopen(options, timeout=3) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)
                self.assertEqual(response.headers.get("Access-Control-Allow-Methods"), "GET, POST, OPTIONS")
                self.assertIn("Idempotency-Key", response.headers.get("Access-Control-Allow-Headers", ""))

        request = Request(f"{self.base_url}/v1/inbox", headers={"Origin": "https://evil.example"})
        with urlopen(request, timeout=3) as response:
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

        blocked_options = Request(
            f"{self.base_url}/v1/clips",
            headers={
                "Origin": "chrome-extension://other",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
                "Content-Length": "0",
            },
            method="OPTIONS",
        )
        with urlopen(blocked_options, timeout=3) as response:
            self.assertEqual(response.status, 204)
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_web_ui_assets_require_cache_revalidation(self) -> None:
        with urlopen(f"{self.base_url}/", timeout=3) as response:
            self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
        with urlopen(f"{self.base_url}/static/app.workspace-14.js", timeout=3) as response:
            source = response.read().decode("utf-8")
            self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
            self.assertIn("function handleDeleteAction()", source)

    def test_output_route_serves_files_from_configured_output_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            WebLibraryTests()._write_package(root)
            with patch("src.web.OUTPUT_ROOT", root):
                with urlopen(f"{self.base_url}/output/demo/index.md", timeout=3) as response:
                    body = response.read().decode("utf-8")

        self.assertIn("# 真实记录", body)

    def test_web_server_does_not_reuse_an_active_port(self) -> None:
        self.assertFalse(VideoSummaryServer.allow_reuse_address)
        self.assertFalse(VideoSummaryServer.allow_reuse_port)

    @patch("src.web.delete_knowledge_packages")
    def test_library_delete_endpoint_returns_deleted_ids(self, delete_packages) -> None:
        delete_packages.return_value = ["first", "second"]
        request = Request(
            f"{self.base_url}/api/library",
            data=json.dumps({"knowledge_ids": ["first", "second"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )

        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))

        delete_packages.assert_called_once_with(["first", "second"])
        self.assertEqual(payload, {"deleted": ["first", "second"], "count": 2})

    @patch("src.web.delete_knowledge_packages")
    def test_library_delete_endpoint_returns_locked_error_code(self, delete_packages) -> None:
        target = Path("C:/output/demo")
        delete_packages.side_effect = KnowledgeDeletionError(
            "knowledge_package_locked",
            "知识包文件正在被其他进程占用。",
            target,
            PermissionError(13, "locked", str(target)),
        )
        request = Request(
            f"{self.base_url}/api/library",
            data=json.dumps({"knowledge_ids": ["demo"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, HTTPStatus.LOCKED)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(payload["code"], "knowledge_package_locked")
        self.assertTrue(payload["retryable"])
        self.assertNotIn(str(target), payload["error"])

    @patch("src.web.delete_knowledge_packages")
    def test_library_delete_endpoint_returns_access_denied_code(self, delete_packages) -> None:
        target = Path("C:/output/demo")
        delete_packages.side_effect = KnowledgeDeletionError(
            "knowledge_package_access_denied",
            "无法删除知识包，请检查 ACL。",
            target,
            PermissionError(13, "denied", str(target)),
        )
        request = Request(
            f"{self.base_url}/api/library",
            data=json.dumps({"knowledge_ids": ["demo"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, HTTPStatus.FORBIDDEN)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(payload["code"], "knowledge_package_access_denied")

    @unittest.skipUnless(os.name == "nt", "Windows sharing violation behavior")
    def test_library_delete_endpoint_reports_real_locked_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = WebLibraryTests()._write_package(root)
            locked_path = package / "index.md"
            request = Request(
                f"{self.base_url}/api/library",
                data=json.dumps({"knowledge_ids": ["demo"]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="DELETE",
            )
            with self.assertLogs("src.web", level="ERROR") as logs:
                with locked_path.open("rb"), patch("src.web.OUTPUT_ROOT", root):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, HTTPStatus.LOCKED)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["code"], "knowledge_package_locked")
            self.assertTrue(package.exists())
            self.assertIn(str(package), "\n".join(logs.output))

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
        self.assertEqual(payload["version"], __version__)
        self.assertNotIn("pythonExecutable", payload)
        self.assertEqual(payload["uiMode"], "product")
        self.assertNotIn("tools", payload)
        self.assertNotIn("providers", payload)
        self.assertNotIn("inProjectVenv", payload)
        self.assertIn("dataDirectory", payload)

    def test_bridge_intake_is_idempotent_and_exposes_inbox_state(self) -> None:
        payload = {
            "schema_version": "1.0",
            "client_request_id": "browser-1",
            "source": {"kind": "video", "url": "https://youtu.be/abc123"},
            "capture": {"title": "Captured", "selected_text": "must not be returned"},
            "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
            "consent": {"user_initiated": True, "content_upload_allowed": False},
        }
        with TemporaryDirectory() as temp_dir, patch("src.web.INTAKE_STORE", IntakeStore(Path(temp_dir) / "intakes.json")):
            request = Request(
                f"{self.base_url}/v1/intakes",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-idem-1"},
                method="POST",
            )
            with urlopen(request, timeout=3) as response:
                created = json.loads(response.read().decode("utf-8"))
            self.assertEqual(created["schema_version"], "1.0")
            self.assertIn("data", created)
            intake_id = created["data"]["intake_id"]
            self.assertFalse(created["data"]["idempotency_replayed"])

            with urlopen(request, timeout=3) as response:
                replayed = json.loads(response.read().decode("utf-8"))
            self.assertTrue(replayed["data"]["idempotency_replayed"])
            self.assertEqual(replayed["data"]["intake_id"], intake_id)

            with urlopen(f"{self.base_url}/v1/intakes/{intake_id}", timeout=3) as response:
                detail = json.loads(response.read().decode("utf-8"))
            self.assertEqual(detail["data"]["state"], "queued")
            self.assertNotIn("must not be returned", json.dumps(detail, ensure_ascii=False))

            with urlopen(f"{self.base_url}/v1/inbox?limit=10", timeout=3) as response:
                inbox = json.loads(response.read().decode("utf-8"))
            self.assertEqual(inbox["data"]["items"][0]["intake_id"], intake_id)

    def test_bridge_intake_requires_idempotency_key(self) -> None:
        with TemporaryDirectory() as temp_dir, patch("src.web.INTAKE_STORE", IntakeStore(Path(temp_dir) / "intakes.json")):
            request = Request(
                f"{self.base_url}/v1/intakes",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, HTTPStatus.BAD_REQUEST)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], "invalid_request")

    def test_bridge_intake_action_hands_off_to_local_job_once(self) -> None:
        intake_payload = {
            "schema_version": "1.0",
            "client_request_id": "browser-action-1",
            "source": {"kind": "video", "url": "https://youtu.be/abc123"},
            "capture": {"title": "Captured"},
            "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
            "consent": {"user_initiated": True, "content_upload_allowed": False},
        }
        fake_job = Job(id="local-job-1", command=["python", "-m", "src.main"], status="queued", knowledge_id="k1-youtube-demo")
        with TemporaryDirectory() as temp_dir, patch("src.web.INTAKE_STORE", IntakeStore(Path(temp_dir) / "intakes.json")), patch("src.web.start_job", return_value=fake_job) as start:
            create_request = Request(
                f"{self.base_url}/v1/intakes",
                data=json.dumps(intake_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-create-action-1"},
                method="POST",
            )
            with urlopen(create_request, timeout=3) as response:
                intake_id = json.loads(response.read().decode("utf-8"))["data"]["intake_id"]

            action_request = Request(
                f"{self.base_url}/v1/intakes/{intake_id}/actions",
                data=b'{"action":"start"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-action-1"},
                method="POST",
            )
            with urlopen(action_request, timeout=3) as response:
                started = json.loads(response.read().decode("utf-8"))
            self.assertEqual(started["data"]["state"], "processing")
            self.assertFalse(started["data"]["idempotency_replayed"])
            self.assertEqual(start.call_count, 1)
            self.assertEqual(start.call_args.args[0]["source"], "https://youtu.be/abc123")

            with urlopen(action_request, timeout=3) as response:
                replayed = json.loads(response.read().decode("utf-8"))
            self.assertTrue(replayed["data"]["idempotency_replayed"])
            self.assertEqual(start.call_count, 1)

    def test_page_intake_runs_local_only_to_ready_knowledge_record(self) -> None:
        intake_payload = {
            "schema_version": "1.0",
            "client_request_id": "browser-page-1",
            "source": {"kind": "page", "url": "https://example.com/guide?utm_source=test"},
            "capture": {
                "title": "Captured Guide",
                "selected_text": "第一部分说明。\n\n第二部分说明。",
                "visible_text": "不应保留的更大页面快照",
            },
            "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
            "consent": {"user_initiated": True, "content_upload_allowed": False},
        }
        with TemporaryDirectory() as temp_dir, patch(
            "src.web.INTAKE_STORE",
            IntakeStore(Path(temp_dir) / "intakes.json"),
        ), patch("src.web.OUTPUT_ROOT", Path(temp_dir) / "knowledge"):
            create_request = Request(
                f"{self.base_url}/v1/intakes",
                data=json.dumps(intake_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Idempotency-Key": "page-create-1"},
                method="POST",
            )
            with urlopen(create_request, timeout=3) as response:
                intake_id = json.loads(response.read().decode("utf-8"))["data"]["intake_id"]

            start_request = Request(
                f"{self.base_url}/v1/intakes/{intake_id}/actions",
                data=b'{"action":"start"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "page-start-1"},
                method="POST",
            )
            with urlopen(start_request, timeout=3) as response:
                started = json.loads(response.read().decode("utf-8"))
            self.assertIn(started["data"]["state"], {"processing", "ready"})

            detail = started
            for _ in range(40):
                with urlopen(f"{self.base_url}/v1/intakes/{intake_id}", timeout=3) as response:
                    detail = json.loads(response.read().decode("utf-8"))
                if detail["data"]["state"] != "processing":
                    break
                time.sleep(0.025)

            self.assertEqual(detail["data"]["state"], "ready")
            self.assertNotIn("第一部分说明", json.dumps(detail, ensure_ascii=False))
            with urlopen(f"{self.base_url}/api/library", timeout=3) as response:
                library = json.loads(response.read().decode("utf-8"))
            page_item = next(item for item in library["items"] if item["id"] == detail["data"]["knowledge_id"])
            self.assertEqual(page_item["sourceType"], "web_page")

    def test_bridge_intake_action_failure_enters_attention_and_retry_can_recover(self) -> None:
        intake_payload = {
            "schema_version": "1.0",
            "client_request_id": "browser-retry-1",
            "source": {"kind": "video", "url": "https://youtu.be/retry123"},
            "capture": {"title": "Retry"},
            "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
            "consent": {"user_initiated": True},
        }
        fake_job = Job(id="local-job-retry", command=[], status="queued")
        with TemporaryDirectory() as temp_dir, patch("src.web.INTAKE_STORE", IntakeStore(Path(temp_dir) / "intakes.json")), patch("src.web.start_job", side_effect=[ValueError("private provider detail"), fake_job]) as start:
            create_request = Request(
                f"{self.base_url}/v1/intakes",
                data=json.dumps(intake_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-create-retry-1"},
                method="POST",
            )
            with urlopen(create_request, timeout=3) as response:
                intake_id = json.loads(response.read().decode("utf-8"))["data"]["intake_id"]
            first_action = Request(
                f"{self.base_url}/v1/intakes/{intake_id}/actions",
                data=b'{"action":"start"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-start-retry-1"},
                method="POST",
            )
            with urlopen(first_action, timeout=3) as response:
                attention = json.loads(response.read().decode("utf-8"))
            self.assertEqual(attention["data"]["state"], "needs_attention")
            self.assertNotIn("private provider detail", json.dumps(attention, ensure_ascii=False))

            retry_action = Request(
                f"{self.base_url}/v1/intakes/{intake_id}/actions",
                data=b'{"action":"retry"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-retry-action-1"},
                method="POST",
            )
            with urlopen(retry_action, timeout=3) as response:
                recovered = json.loads(response.read().decode("utf-8"))
            self.assertEqual(recovered["data"]["state"], "processing")
            self.assertEqual(start.call_count, 2)

    def test_bridge_intake_action_rejects_duplicate_intake(self) -> None:
        base = {
            "schema_version": "1.0",
            "source": {"kind": "video", "url": "https://youtu.be/duplicate123"},
            "capture": {"title": "Duplicate"},
            "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
            "consent": {"user_initiated": True},
        }
        with TemporaryDirectory() as temp_dir, patch("src.web.INTAKE_STORE", IntakeStore(Path(temp_dir) / "intakes.json")), patch("src.web.start_job") as start:
            for client_id, idem in (("first", "create-dup-1"), ("second", "create-dup-2")):
                create = dict(base)
                create["client_request_id"] = client_id
                request = Request(
                    f"{self.base_url}/v1/intakes",
                    data=json.dumps(create).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Idempotency-Key": idem},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    last = json.loads(response.read().decode("utf-8"))
            duplicate_id = last["data"]["intake_id"]
            action = Request(
                f"{self.base_url}/v1/intakes/{duplicate_id}/actions",
                data=b'{"action":"start"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "action-dup-1"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(action, timeout=3)
            self.assertEqual(caught.exception.code, HTTPStatus.CONFLICT)
            result = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(result["error"]["code"], "duplicate_intake")
            start.assert_not_called()

    def test_bridge_intake_can_be_cancelled_before_handoff(self) -> None:
        intake_payload = {
            "schema_version": "1.0",
            "client_request_id": "browser-cancel-1",
            "source": {"kind": "video", "url": "https://youtu.be/cancel123"},
            "capture": {"title": "Cancel"},
            "preferences": {"analysis_profile": "summary", "processing_profile": "fast", "output_languages": ["source"]},
            "consent": {"user_initiated": True},
        }
        with TemporaryDirectory() as temp_dir, patch("src.web.INTAKE_STORE", IntakeStore(Path(temp_dir) / "intakes.json")), patch("src.web.start_job") as start:
            create = Request(
                f"{self.base_url}/v1/intakes",
                data=json.dumps(intake_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-create-cancel-1"},
                method="POST",
            )
            with urlopen(create, timeout=3) as response:
                intake_id = json.loads(response.read().decode("utf-8"))["data"]["intake_id"]
            cancel = Request(
                f"{self.base_url}/v1/intakes/{intake_id}/actions",
                data=b'{"action":"cancel"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "browser-cancel-action-1"},
                method="POST",
            )
            with urlopen(cancel, timeout=3) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(result["data"]["state"], "cancelled")
            start.assert_not_called()

    def test_bilibili_collection_inspect_create_set_and_analyze_item(self) -> None:
        inspection = {
            "kind": "bilibili_parts",
            "isCollection": True,
            "title": "B站教程合集",
            "sourceUrl": "https://www.bilibili.com/video/BV1234567890",
            "uploader": "作者",
            "items": [
                {"sequence": 1, "title": "第一节", "sourceUrl": "https://www.bilibili.com/video/BV1234567890?p=1", "partition": "分P"},
                {"sequence": 2, "title": "第二节", "sourceUrl": "https://www.bilibili.com/video/BV1234567890?p=2", "partition": "分P"},
            ],
        }
        fake_job = Job(id="set-job-1", command=[], status="queued", knowledge_id="k1-part-1")
        with TemporaryDirectory() as temp_dir, patch("src.web.KNOWLEDGE_SET_STORE", KnowledgeSetStore(Path(temp_dir) / "sets.json")), patch("src.web.inspect_bilibili_input", return_value=inspection), patch("src.web.start_job", return_value=fake_job) as start:
            inspect_request = Request(
                f"{self.base_url}/api/source/inspect",
                data=b'{"sourceType":"url","source":"https://www.bilibili.com/video/BV1234567890"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(inspect_request, timeout=3) as response:
                inspected = json.loads(response.read().decode("utf-8"))
            self.assertTrue(inspected["isCollection"])
            self.assertEqual(len(inspected["items"]), 2)

            create_request = Request(
                f"{self.base_url}/api/knowledge-sets",
                data=json.dumps({"inspection": inspection, "analysisProfile": "close-reading", "processingProfile": "fast", "transcriptGroupSeconds": 60}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Idempotency-Key": "set-create-1"},
                method="POST",
            )
            with urlopen(create_request, timeout=3) as response:
                created = json.loads(response.read().decode("utf-8"))
            set_id = created["set"]["setId"]
            item_id = created["set"]["items"][0]["itemId"]
            self.assertEqual(created["set"]["itemCount"], 2)
            self.assertEqual(created["set"]["analysisProfile"], "close-reading")
            self.assertEqual(created["set"]["processingProfile"], "fast")
            self.assertEqual(created["set"]["transcriptGroupSeconds"], 60)

            analyze_request = Request(
                f"{self.base_url}/api/knowledge-sets/{set_id}/items/{item_id}/analyze",
                data=b"{}",
                headers={"Content-Type": "application/json", "Idempotency-Key": "set-item-1"},
                method="POST",
            )
            with urlopen(analyze_request, timeout=3) as response:
                analyzed = json.loads(response.read().decode("utf-8"))
            self.assertEqual(analyzed["set"]["items"][0]["state"], "processing")
            self.assertEqual(start.call_args.args[0]["source"], inspection["items"][0]["sourceUrl"])
            self.assertEqual(start.call_args.args[0]["mode"], "close-reading")
            self.assertEqual(start.call_args.args[0]["processingProfile"], "fast")
            self.assertEqual(start.call_args.args[0]["transcriptGroupSeconds"], 60)

            with urlopen(analyze_request, timeout=3) as response:
                replayed = json.loads(response.read().decode("utf-8"))
            self.assertTrue(replayed["idempotencyReplayed"])
            self.assertEqual(start.call_count, 1)

            conflict_request = Request(
                f"{self.base_url}/api/knowledge-sets/{set_id}/items/{item_id}/analyze",
                data=b'{"mode":"tutorial","processingProfile":"complete"}',
                headers={"Content-Type": "application/json", "Idempotency-Key": "set-item-2"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as conflict:
                urlopen(conflict_request, timeout=3)
            self.assertEqual(conflict.exception.code, HTTPStatus.BAD_REQUEST)
            self.assertEqual(start.call_count, 1)

            with urlopen(f"{self.base_url}/api/knowledge-sets/{set_id}", timeout=3) as response:
                detail = json.loads(response.read().decode("utf-8"))
            self.assertEqual(detail["set"]["items"][0]["itemId"], item_id)

    def test_folder_set_endpoint_accepts_quoted_windows_style_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.ts").write_bytes(b"video")
            quoted = f'"{root}"'
            with patch("src.web.FOLDER_SET_STORE", FolderSetStore(root / "state.json")):
                request = Request(
                    f"{self.base_url}/api/folder-sets",
                    data=json.dumps({"source": quoted, "title": "Course"}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Idempotency-Key": "quoted-folder-1"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["set"]["itemCount"], 1)
            self.assertNotIn(str(root), json.dumps(payload, ensure_ascii=False))

    def test_source_inspect_accepts_single_quoted_folder_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.ts").write_bytes(b"video")
            quoted = f"'{root}'"
            with patch("src.web.FOLDER_SET_STORE", FolderSetStore(root / "state.json")):
                request = Request(
                    f"{self.base_url}/api/source/inspect",
                    data=json.dumps({"sourceType": "file", "source": quoted}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["kind"], "local_folder")
            self.assertEqual(payload["videoCount"], 1)
            self.assertNotIn(str(root), json.dumps(payload, ensure_ascii=False))

    def test_source_inspect_single_file_does_not_return_absolute_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "lesson.ts"
            video.write_bytes(b"video")
            request = Request(
                f"{self.base_url}/api/source/inspect",
                data=json.dumps({"sourceType": "file", "source": str(video)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["kind"], "single")
            self.assertEqual(payload["sourceType"], "file")
            self.assertNotIn("source", payload)
            self.assertNotIn(str(root), json.dumps(payload, ensure_ascii=False))

    def test_folder_set_batch_analyze_recurses_into_child_sets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "root.ts").write_bytes(b"root")
            (root / "child").mkdir()
            (root / "child" / "child.ts").write_bytes(b"child")
            store = FolderSetStore(root / "state.json")
            root_set, _ = store.create(str(root), "Course", "recursive-batch")
            jobs = [
                Job(id="folder-root-job", command=[], status="queued", knowledge_id="k-root"),
                Job(id="folder-child-job", command=[], status="queued", knowledge_id="k-child"),
            ]
            with patch("src.web.FOLDER_SET_STORE", store), patch("src.web.start_job", side_effect=jobs) as start:
                request = Request(
                    f"{self.base_url}/api/folder-sets/{root_set.set_id}/analyze-all",
                    data=b'{"mode":"tutorial","processingProfile":"complete"}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["started"], 2)
            self.assertEqual(start.call_count, 2)
            child = store.get(root_set.child_set_ids[0])
            self.assertEqual(root_set.items[0].state, "processing")
            self.assertEqual(child.items[0].state, "processing")

    def test_folder_set_batch_analyze_uses_persisted_settings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.ts").write_bytes(b"video")
            store = FolderSetStore(root / "state.json")
            root_set, _ = store.create(str(root), "Course", "settings-batch", analysis_profile="close-reading", processing_profile="fast", transcript_group_seconds=60)
            captured = []
            job = Job(id="folder-settings-job", command=[], status="queued", knowledge_id="k-settings")
            def start(payload):
                captured.append(payload)
                return job
            with patch("src.web.FOLDER_SET_STORE", store), patch("src.web.start_job", side_effect=start):
                request = Request(
                    f"{self.base_url}/api/folder-sets/{root_set.set_id}/analyze-all",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["started"], 1)
            self.assertEqual(captured[0]["mode"], "close-reading")
            self.assertEqual(captured[0]["processingProfile"], "fast")
            self.assertEqual(captured[0]["transcriptGroupSeconds"], 60)

    def test_folder_set_item_start_failure_is_recoverable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "lesson.ts").write_bytes(b"video")
            store = FolderSetStore(root / "state.json")
            root_set, _ = store.create(str(root), "Course", "failure-recovery")
            with patch("src.web.FOLDER_SET_STORE", store), patch("src.web.start_job", side_effect=ValueError("private provider detail")):
                request = Request(
                    f"{self.base_url}/api/folder-sets/{root_set.set_id}/items/{root_set.items[0].item_id}/analyze",
                    data=b'{"mode":"tutorial","processingProfile":"complete"}',
                    headers={"Content-Type": "application/json", "Idempotency-Key": "folder-failure-1"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["set"]["items"][0]["state"], "failed")
            self.assertNotIn("private provider detail", json.dumps(payload, ensure_ascii=False))

    @patch("src.web.load_knowledge_package")
    @patch("src.web.reanalyze_knowledge_package")
    @patch("src.web.resolve_library_dir")
    def test_analysis_retry_endpoint_returns_refreshed_knowledge(
        self,
        resolve_directory,
        reanalyze,
        load_knowledge,
    ) -> None:
        resolve_directory.return_value = Path("demo")
        load_knowledge.return_value = {"id": "demo", "analysis": {"status": "success"}}
        request = Request(
            f"{self.base_url}/api/library/demo/analysis/retry",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))

        resolve_directory.assert_called_once_with("demo")
        reanalyze.assert_called_once()
        self.assertEqual(payload["knowledge"]["analysis"]["status"], "success")

    @patch("src.web.reanalyze_knowledge_package")
    @patch("src.web.resolve_library_dir", return_value=Path("demo"))
    def test_analysis_retry_timeout_returns_gateway_timeout(
        self,
        _resolve_directory,
        reanalyze,
    ) -> None:
        reanalyze.side_effect = UserFacingError("DeepSeek 请求超时，请稍后重试。")
        request = Request(
            f"{self.base_url}/api/library/demo/analysis/retry",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, HTTPStatus.GATEWAY_TIMEOUT)

    @patch("src.web.render_directory_export")
    @patch("src.web.resolve_library_dir")
    def test_knowledge_export_preview_uses_structured_renderer(self, resolve_directory, render_export) -> None:
        resolve_directory.return_value = Path("demo")
        render_export.return_value = ("# Export\n", "demo.md")
        request = Request(
            f"{self.base_url}/api/knowledge/demo/export",
            data=json.dumps({"preset": "summary-chat", "destination": "preview"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["markdown"], "# Export\n")
        self.assertIn("chat", payload["included_sections"])

    @patch("src.web.answer_question")
    @patch("src.web.ProviderRegistry")
    @patch("src.web.ChatStore")
    @patch("src.web.load_transcript_groups")
    @patch("src.web.load_knowledge_package")
    def test_visual_chat_question_is_explicitly_text_only(
        self,
        load_knowledge,
        load_groups,
        chat_store,
        registry,
        answer,
    ) -> None:
        load_knowledge.return_value = {"analysis": {}, "source": {}}
        load_groups.return_value = [{"index": 0, "start": 0, "end": 5, "text": "字幕"}]
        registry.return_value.resolve.return_value = object()
        chat_store.return_value.load.return_value = {"messages": []}
        answer.return_value = {
            "knowledge_id": "demo",
            "answer": "回答",
            "citations": [],
            "provider": "deepseek",
            "model": "test",
            "usage": {},
        }

        result = __import__("src.web", fromlist=["chat_with_knowledge"]).chat_with_knowledge(
            {"knowledge_id": "demo", "question": "画面里有什么按钮？"}
        )

        self.assertIn("未附带关键帧", result["warning"])

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
