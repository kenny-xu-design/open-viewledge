from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from src.downloader import _download_media_for_transcription, _download_subtitle, _missing_ytdlp_message, _subtitle_languages


class DownloaderMessageTests(unittest.TestCase):
    def test_missing_ytdlp_message_includes_environment_details(self) -> None:
        message = _missing_ytdlp_message()

        self.assertIn(str(sys.executable), message)
        self.assertIn(str(Path.cwd()), message)
        self.assertIn("python -m pip install -r requirements.txt", message)

    def test_subtitle_languages_do_not_request_wildcard_translations(self) -> None:
        languages = _subtitle_languages("zh-Hans")
        self.assertEqual(languages[0], "zh-Hans")
        self.assertFalse(any("*" in item for item in languages))

    def test_partial_subtitle_success_is_not_discarded(self) -> None:
        class FakeYdl:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def download(self, _urls):
                output = Path(self.opts["outtmpl"]).parent / "video.zh-Hans.vtt"
                output.write_text("WEBVTT\n", encoding="utf-8")
                raise RuntimeError("later translated track failed")

        class FakeYtDlp:
            YoutubeDL = FakeYdl

        with tempfile.TemporaryDirectory() as temp:
            subtitle = _download_subtitle(FakeYtDlp, "https://example.com/video", Path(temp), "zh-Hans")
            self.assertIsNotNone(subtitle)
            self.assertEqual(subtitle.name, "video.zh-Hans.vtt")

    def test_media_sample_uses_download_section(self) -> None:
        captured = {}

        class FakeYdl:
            def __init__(self, opts):
                captured.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def download(self, _urls):
                output = Path(captured["outtmpl"].replace("%(ext)s", "webm"))
                output.write_bytes(b"sample")

        class FakeYtDlp:
            YoutubeDL = FakeYdl

        with tempfile.TemporaryDirectory() as temp:
            media = _download_media_for_transcription(FakeYtDlp, "https://example.com/video", Path(temp), 30)
            self.assertTrue(media.exists())
            self.assertEqual(captured["download_sections"], ["*0-30"])


if __name__ == "__main__":
    unittest.main()
