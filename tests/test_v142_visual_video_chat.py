from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.chat_store import ChatStore
from src.domain.models import AnalysisResult, HighlightItem, TimelineEntry
from src.pipeline.stages import STAGES
from src.providers.llm import GeminiProvider
from src.providers.llm.base import LLMResponse
from src.utils import UserFacingError
from src.video_chat import GeminiVideoChatRouter
from src.visual import generate_highlight_snapshots


class _Response:
    def __init__(self, payload: dict, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _RouterProvider:
    name = "gemini"
    model_name = "gemini-test"

    def __init__(self) -> None:
        self.calls = []

    def complete_with_video_url(self, messages, video_url, **kwargs):
        self.calls.append("url")
        raise UserFacingError("URL 不受支持")

    def upload_video(self, path):
        self.calls.append("upload")
        raise UserFacingError("上传不可用")

    def get_uploaded_file(self, name):
        self.calls.append("get")
        raise UserFacingError("远程文件已过期")

    def complete_with_uploaded_file(self, messages, uploaded_file, **kwargs):
        raise AssertionError("上传失败后不应调用")

    def generate_with_images(self, prompt, image_paths, **kwargs):
        self.calls.append("frames")
        return LLMResponse("关键帧回答", self.name, self.model_name)

    def complete(self, messages, **kwargs):
        self.calls.append("text")
        return LLMResponse("文本回答", self.name, self.model_name)


class V142VisualVideoChatTests(unittest.TestCase):
    def test_text_analysis_precedes_optional_visual_stages(self) -> None:
        self.assertLess(STAGES.index("run_analysis"), STAGES.index("extract_frames"))
        self.assertLess(STAGES.index("run_analysis"), STAGES.index("visual_analysis"))
        self.assertLess(STAGES.index("visual_analysis"), STAGES.index("highlight_snapshot"))

    def test_highlight_legacy_and_v14_fields_stay_compatible(self) -> None:
        legacy = HighlightItem(title="旧", start=12.5, explanation="说明")
        self.assertEqual(legacy.timestamp, 12.5)
        self.assertEqual(legacy.summary, "说明")
        current = HighlightItem(title="新", timestamp=8, summary="摘要")
        self.assertEqual(current.start, 8)
        self.assertEqual(current.explanation, "摘要")

    def test_highlight_snapshot_reuses_frame_and_keeps_relative_webp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame = root / "frames" / "frame.jpg"
            frame.parent.mkdir()
            frame.write_bytes(b"frame")
            media = root / "video.mp4"
            media.write_bytes(b"video")
            analysis = AnalysisResult(
                status="success",
                highlights=[HighlightItem(title="亮点", start=10, explanation="说明")],
            )
            timeline = [
                TimelineEntry(
                    index=0,
                    start=0,
                    end=20,
                    title="片段",
                    representative_time=11,
                    frame_path="frames/frame.jpg",
                )
            ]

            def fake_run(command):
                Path(command[-1]).write_bytes(b"webp")

            with (
                patch("src.visual.highlight_snapshots.resolve_executable", return_value="ffmpeg"),
                patch("src.visual.highlight_snapshots.run_command", side_effect=fake_run),
            ):
                result = generate_highlight_snapshots(media, analysis, timeline, root)

            item = result.analysis.highlights[0]
            self.assertEqual(item.image, "assets/highlights/highlight_001.webp")
            self.assertEqual(item.image_generation_status, "reused")
            self.assertEqual(item.image_source_timestamp, 11)
            self.assertTrue((root / item.image).is_file())

    def test_highlight_capture_failure_preserves_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "video.mp4"
            media.write_bytes(b"video")
            analysis = AnalysisResult(
                status="success",
                highlights=[HighlightItem(title="仍保留", timestamp=4, summary="文本")],
            )
            with (
                patch("src.visual.highlight_snapshots.resolve_executable", return_value="ffmpeg"),
                patch("src.visual.highlight_snapshots.run_command", side_effect=OSError("locked")),
            ):
                result = generate_highlight_snapshots(media, analysis, [], root)
            self.assertEqual(result.analysis.highlights[0].title, "仍保留")
            self.assertEqual(result.analysis.highlights[0].summary, "文本")
            self.assertEqual(result.analysis.highlights[0].image_generation_status, "failed")

    def test_gemini_youtube_url_uses_file_data_contract(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _Response(
                {"candidates": [{"content": {"parts": [{"text": "视频回答"}]}}]}
            )

        provider = GeminiProvider(api_key="key", model_name="gemini-test", opener=opener)
        response = provider.complete_with_video_url(
            [{"role": "user", "content": "总结"}],
            "https://www.youtube.com/watch?v=abc",
        )
        part = captured["body"]["contents"][0]["parts"][0]
        self.assertEqual(part["file_data"]["file_uri"], "https://www.youtube.com/watch?v=abc")
        self.assertEqual(response.content, "视频回答")

    def test_gemini_files_upload_uses_resumable_contract(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append(request)
            if "/upload/v1beta/files" in request.full_url:
                return _Response({}, {"X-Goog-Upload-URL": "https://upload.example/session"})
            return _Response(
                {
                    "file": {
                        "name": "files/demo",
                        "uri": "https://files.example/demo",
                        "mimeType": "video/mp4",
                        "state": "ACTIVE",
                    }
                }
            )

        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "video.mp4"
            video.write_bytes(b"video")
            provider = GeminiProvider(api_key="key", opener=opener, sleeper=lambda _: None)
            uploaded = provider.upload_video(video)
        self.assertEqual(uploaded.name, "files/demo")
        self.assertEqual(requests[0].headers["X-goog-upload-command"], "start")
        self.assertEqual(requests[1].headers["X-goog-upload-command"], "upload, finalize")

    def test_router_records_url_and_files_failures_before_frame_fallback(self) -> None:
        provider = _RouterProvider()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "video.mp4"
            frame = root / "frame.jpg"
            media.write_bytes(b"video")
            frame.write_bytes(b"frame")
            result = GeminiVideoChatRouter(provider).answer(
                [{"role": "user", "content": "画面是什么"}],
                source_url="https://www.youtube.com/watch?v=abc",
                media_path=media,
                frame_paths=[frame],
            )
        self.assertEqual(result.route, "gemini_frames_text")
        self.assertEqual(result.route_status, "degraded")
        self.assertEqual([item["route"] for item in result.attempts], [
            "gemini_youtube_url",
            "gemini_files_api",
            "gemini_frames_text",
        ])

    def test_chat_store_persists_route_state_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            store = ChatStore(lambda _: package)
            state = store.update_state(
                "demo",
                source_url="https://youtube.com/watch?v=abc",
                source_fingerprint="fingerprint",
                provider="gemini",
                model="gemini-test",
                route="gemini_youtube_url",
                route_status="available",
                api_key="must-not-be-stored",
            )
            self.assertTrue(state["chat_id"])
            self.assertEqual(store.load("demo")["route"], "gemini_youtube_url")
            self.assertNotIn("api_key", json.loads((package / "chat.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
