from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.domain.models import SourceRecord, TranscriptGroup
from src.timeline import build_timeline, extract_frames


class TimelineTests(unittest.TestCase):
    def test_group_converts_to_timeline_with_midpoint(self) -> None:
        group = TranscriptGroup(index=0, start=10, end=30, title="主题", text="正文", segment_indexes=[0])
        source = SourceRecord(source_type="online_video", platform="youtube", source_url="https://www.youtube.com/watch?v=abc", source_id="abc")
        entry = build_timeline([group], source)[0]
        self.assertEqual(entry.representative_time, 20)
        self.assertEqual(entry.source_link, "https://www.youtube.com/watch?v=abc&t=10s")

    def test_frame_failure_does_not_raise(self) -> None:
        group = TranscriptGroup(index=0, start=0, end=10, title="主题", text="正文", segment_indexes=[0])
        source = SourceRecord(source_type="local_video", platform="local", source_id="id")
        entries = build_timeline([group], source)
        with tempfile.TemporaryDirectory() as temp, patch("src.timeline.frame_extractor.run_command", side_effect=RuntimeError("boom")), patch("src.timeline.frame_extractor.require_executable", return_value="ffmpeg"):
            result, errors = extract_frames(Path(temp) / "video.mp4", entries, Path(temp) / "frames")
        self.assertEqual(len(result), 1)
        self.assertTrue(errors)

