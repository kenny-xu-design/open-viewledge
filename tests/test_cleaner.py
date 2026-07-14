from __future__ import annotations

import unittest

from src.cleaner import (
    build_timestamp_link,
    clean_subtitle_text,
    format_transcript_segment,
    seconds_to_timestamp,
    timestamp_to_seconds,
)


class CleanerTests(unittest.TestCase):
    def test_timestamp_helpers(self) -> None:
        self.assertEqual(seconds_to_timestamp(65), "01:05")
        self.assertEqual(seconds_to_timestamp(3661), "01:01:01")
        self.assertEqual(timestamp_to_seconds("00:02:10.500"), 130)
        self.assertEqual(timestamp_to_seconds("02:10,000"), 130)

    def test_build_timestamp_link_for_supported_platforms(self) -> None:
        self.assertEqual(
            build_timestamp_link("https://www.bilibili.com/video/BV123", 130),
            "https://www.bilibili.com/video/BV123?t=130",
        )
        self.assertEqual(
            build_timestamp_link("https://www.youtube.com/watch?v=abc", 130),
            "https://www.youtube.com/watch?v=abc&t=130s",
        )
        self.assertEqual(build_timestamp_link("https://example.com/video", 130), "")

    def test_format_transcript_segment_adds_link_when_available(self) -> None:
        line = format_transcript_segment(
            130,
            135,
            "  hello   world  ",
            "https://youtu.be/abc",
        )
        self.assertEqual(line, "- [02:10 - 02:15](https://youtu.be/abc?t=130s) hello world")

    def test_clean_subtitle_text_removes_markup_and_duplicates(self) -> None:
        raw = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
<c>Hello</c>

2
00:00:03.000 --> 00:00:05.000
<c>Hello</c>

3
00:00:05.000 --> 00:00:07.000
World
"""

        cleaned = clean_subtitle_text(raw, source_url="https://www.bilibili.com/video/BV123")

        self.assertIn("- [00:01 - 00:03](https://www.bilibili.com/video/BV123?t=1) Hello", cleaned)
        self.assertIn("- [00:05 - 00:07](https://www.bilibili.com/video/BV123?t=5) World", cleaned)
        self.assertEqual(cleaned.count("Hello"), 1)


if __name__ == "__main__":
    unittest.main()
