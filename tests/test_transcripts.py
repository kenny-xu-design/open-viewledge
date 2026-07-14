from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.domain.models import TranscriptSegment
from src.transcripts import group_segments, read_jsonl, write_grouped_markdown, write_jsonl
from src.pipeline.orchestrator import _cache_matches_language, _limit_segments


class TranscriptDataTests(unittest.TestCase):
    def test_jsonl_round_trip(self) -> None:
        segments = [TranscriptSegment(index=0, start=0, end=4, text="第一句", language="zh")]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "transcript.raw.jsonl"
            write_jsonl(path, segments)
            self.assertEqual(read_jsonl(path), segments)

    def test_multiple_segments_are_grouped(self) -> None:
        segments = [TranscriptSegment(index=i, start=i * 4, end=i * 4 + 3, text=f"句子{i}。") for i in range(6)]
        groups = group_segments(segments, target_seconds=60, max_segments=12)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].segment_indexes, list(range(6)))

    def test_max_time_splits_groups(self) -> None:
        segments = [TranscriptSegment(index=i, start=i * 20, end=i * 20 + 10, text=f"句子{i}。") for i in range(6)]
        self.assertGreater(len(group_segments(segments, target_seconds=30, max_segments=12)), 1)

    def test_chapter_boundary_splits_groups(self) -> None:
        segments = [TranscriptSegment(index=i, start=i * 10, end=i * 10 + 5, text=f"句子{i}") for i in range(5)]
        groups = group_segments(segments, chapters=[{"start_time": 20}], target_seconds=100)
        self.assertEqual(len(groups), 2)

    def test_grouped_markdown_does_not_make_each_segment_a_paragraph(self) -> None:
        segments = [TranscriptSegment(index=i, start=i, end=i + 1, text=f"句子{i}") for i in range(4)]
        groups = group_segments(segments)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "transcript.grouped.md"
            write_grouped_markdown(path, groups)
            content = path.read_text(encoding="utf-8")
            self.assertEqual(content.count("## "), 1)

    def test_transcript_cache_respects_requested_language(self) -> None:
        segments = [TranscriptSegment(index=0, start=0, end=1, text="字幕", language="zh")]
        self.assertTrue(_cache_matches_language(segments, "zh"))
        self.assertFalse(_cache_matches_language(segments, "zh-Hans"))

    def test_sample_segments_are_clamped_to_boundary(self) -> None:
        segments = [
            TranscriptSegment(index=0, start=29.6, end=30.1, text="结尾", language="zh"),
            TranscriptSegment(index=1, start=30.1, end=31.0, text="越界", language="zh"),
        ]
        limited = _limit_segments(segments, 30)
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0].end, 30.0)
