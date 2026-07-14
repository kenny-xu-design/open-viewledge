from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.adapters import BilibiliAdapter, is_bilibili_url
from src.adapters.base import AdapterResult
from src.sources.ytdlp_source import YtdlpSource, normalize_bilibili_input


class AdapterResultTests(unittest.TestCase):
    def test_has_transcript_requires_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript_path = Path(temp_dir) / "transcript.md"

            missing_result = AdapterResult(
                metadata={},
                adapter_name="test",
                transcript_path=transcript_path,
            )
            self.assertFalse(missing_result.has_transcript)

            transcript_path.write_text("hello", encoding="utf-8")
            existing_result = AdapterResult(
                metadata={},
                adapter_name="test",
                transcript_path=transcript_path,
            )
            self.assertTrue(existing_result.has_transcript)


class BilibiliAdapterTests(unittest.TestCase):
    def test_recognizes_full_short_and_bv_inputs(self) -> None:
        self.assertTrue(is_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD"))
        self.assertTrue(is_bilibili_url("https://b23.tv/example"))
        self.assertTrue(is_bilibili_url("BV1xx411c7mD"))
        self.assertFalse(is_bilibili_url("https://www.youtube.com/watch?v=abc"))

    def test_bare_bv_is_normalized(self) -> None:
        self.assertEqual(
            normalize_bilibili_input("BV1xx411c7mD"),
            "https://www.bilibili.com/video/BV1xx411c7mD",
        )
        self.assertTrue(YtdlpSource.supports("BV1xx411c7mD"))

    def test_adapter_delegates_to_ytdlp_without_external_command(self) -> None:
        expected = AdapterResult(metadata={"source": "bilibili"}, adapter_name="yt-dlp")
        with tempfile.TemporaryDirectory() as temp, patch(
            "src.adapters.bilibili_adapter.YtdlpAdapter.fetch", return_value=expected
        ) as fetch:
            root = Path(temp)
            result = BilibiliAdapter().fetch(
                "BV1xx411c7mD",
                root,
                root / "metadata.json",
                root / "transcript.md",
                root / "comments.json",
                root / "comments.md",
            )
        self.assertEqual(result.adapter_name, "bilibili-ytdlp")
        self.assertEqual(fetch.call_args.args[0], "https://www.bilibili.com/video/BV1xx411c7mD")


if __name__ == "__main__":
    unittest.main()
