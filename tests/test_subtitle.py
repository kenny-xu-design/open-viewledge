from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.subtitle import find_subtitle_file, subtitle_to_transcript
from src.utils import UserFacingError


class SubtitleTests(unittest.TestCase):
    def test_find_subtitle_file_returns_first_supported_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "b.txt").write_text("ignored", encoding="utf-8")
            (root / "nested").mkdir()
            first = root / "a.srt"
            second = root / "nested" / "z.vtt"
            second.write_text("WEBVTT\n\ntext", encoding="utf-8")
            first.write_text("1\n00:00:01 --> 00:00:02\nhello", encoding="utf-8")

            self.assertEqual(find_subtitle_file(root), first)

    def test_subtitle_to_transcript_rejects_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle_path = Path(temp_dir) / "sample.txt"
            subtitle_path.write_text("hello", encoding="utf-8")

            with self.assertRaises(UserFacingError):
                subtitle_to_transcript(subtitle_path, Path(temp_dir) / "transcript.md")

    def test_subtitle_to_transcript_writes_cleaned_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subtitle_path = root / "sample.srt"
            transcript_path = root / "transcript.md"
            subtitle_path.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
                encoding="utf-8",
            )

            result = subtitle_to_transcript(subtitle_path, transcript_path)
            content = transcript_path.read_text(encoding="utf-8")

            self.assertEqual(result, transcript_path)
            self.assertIn("# 字幕 / 转写全文", content)
            self.assertIn("- [00:01 - 00:02] hello", content)


if __name__ == "__main__":
    unittest.main()
