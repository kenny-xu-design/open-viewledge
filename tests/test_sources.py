from __future__ import annotations

import unittest

from src.sources.ytdlp_source import YtdlpSource, _platform_from_url, normalize_bilibili_input


class YtdlpSourceTests(unittest.TestCase):
    def test_bare_bv_is_normalized_and_supported(self) -> None:
        self.assertEqual(
            normalize_bilibili_input("BV1xx411c7mD"),
            "https://www.bilibili.com/video/BV1xx411c7mD",
        )
        self.assertTrue(YtdlpSource.supports("BV1xx411c7mD"))

    def test_bilibili_and_youtube_platforms_are_identified(self) -> None:
        self.assertEqual(_platform_from_url("https://www.bilibili.com/video/BV1xx411c7mD"), "bilibili")
        self.assertEqual(_platform_from_url("https://www.youtube.com/watch?v=abc123"), "youtube")


if __name__ == "__main__":
    unittest.main()
