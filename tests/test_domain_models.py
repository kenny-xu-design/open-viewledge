from __future__ import annotations

import unittest

from src.domain.models import AnalysisResult, ProcessingManifest, SourceRecord, TranscriptGroup, TranscriptSegment
from src.main import normalize_backend
from src.utils import UserFacingError


class DomainModelTests(unittest.TestCase):
    def test_transcript_segment_json_round_trip(self) -> None:
        segment = TranscriptSegment(index=0, start=1.2, end=3.4, text="hello", language="en", source="asr")
        self.assertEqual(TranscriptSegment.model_validate_json(segment.model_dump_json()), segment)

    def test_group_keeps_segment_indexes(self) -> None:
        group = TranscriptGroup(index=0, start=0, end=10, title="topic", text="text", segment_indexes=[1, 2, 3])
        self.assertEqual(group.model_dump()["segment_indexes"], [1, 2, 3])

    def test_analysis_optional_fields_default_to_empty(self) -> None:
        result = AnalysisResult(summary="ok")
        self.assertEqual(result.highlights, [])
        self.assertEqual(result.thoughts, [])
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.schema_version, "2")

    def test_manifest_records_stage_status(self) -> None:
        manifest = ProcessingManifest(task_id="task", stage_status={"resolve_source": "completed"}, sample_seconds=30)
        self.assertEqual(manifest.stage_status["resolve_source"], "completed")
        self.assertEqual(manifest.sample_seconds, 30)

    def test_only_deepseek_backend_is_active(self) -> None:
        self.assertEqual(normalize_backend(None), "deepseek")
        with self.assertRaisesRegex(UserFacingError, "已停用"):
            normalize_backend("ollama")
