from __future__ import annotations

import unittest

from src.domain.models import AnalysisResult, ProcessingManifest, SourceRecord, StageMetric, TranscriptGroup, TranscriptSegment
from src.main import normalize_backend
from src.pipeline.context import PipelineContext
from src.config import AppConfig
from src.defaults import DEFAULT_DEEPSEEK_MODEL, DEFAULT_GEMINI_MODEL
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
        manifest = ProcessingManifest(
            task_id="task",
            stage_status={"resolve_source": "completed"},
            sample_seconds=30,
            analysis_status="skipped",
        )
        self.assertEqual(manifest.stage_status["resolve_source"], "completed")
        self.assertEqual(manifest.sample_seconds, 30)
        self.assertEqual(manifest.analysis_status, "skipped")
        self.assertEqual(manifest.processing_profile, "complete")
        self.assertEqual(manifest.stage_metrics, {})

    def test_manifest_processing_profile_and_stage_metric_contract(self) -> None:
        manifest = ProcessingManifest(
            task_id="task",
            processing_profile="fast",
            stage_metrics={
                "resolve_source": StageMetric(
                    duration_ms=12,
                    attempt=1,
                    cache_hit=False,
                    error_code="",
                    error_message="",
                )
            },
        )

        self.assertEqual(manifest.processing_profile, "fast")
        self.assertEqual(manifest.stage_metrics["resolve_source"].duration_ms, 12)
        with self.assertRaises(ValueError):
            ProcessingManifest(task_id="task", processing_profile="turbo")

    def test_only_deepseek_backend_is_active(self) -> None:
        self.assertEqual(normalize_backend(None), "deepseek")
        with self.assertRaisesRegex(UserFacingError, "已停用"):
            normalize_backend("ollama")

    def test_pipeline_context_keeps_previous_manifest_for_cache_validation(self) -> None:
        context = PipelineContext(
            config=AppConfig(),
            input_value="video.mp4",
            output_dir=__import__("pathlib").Path("output"),
            analysis_profile="summary",
            previous_manifest={"sample_seconds": 30},
        )
        self.assertEqual(context.previous_manifest["sample_seconds"], 30)

    def test_app_config_uses_central_provider_defaults(self) -> None:
        config = AppConfig()
        self.assertEqual(config.deepseek_model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(config.gemini_model, DEFAULT_GEMINI_MODEL)
        self.assertEqual(config.ffmpeg_path, "")
        self.assertEqual(config.ffprobe_path, "")
