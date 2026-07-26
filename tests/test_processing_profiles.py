from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import AppConfig
from src.domain.models import ProcessingManifest
from src.pipeline.context import PipelineContext
from src.pipeline.orchestrator import PipelineOrchestrator
from src.processing_profiles import normalize_processing_profile


class ProcessingProfileTests(unittest.TestCase):
    def test_normalization_defaults_to_complete(self) -> None:
        self.assertEqual(normalize_processing_profile(None), "complete")
        self.assertEqual(normalize_processing_profile(" FAST "), "fast")
        with self.assertRaises(ValueError):
            normalize_processing_profile("turbo")

    def test_stage_metrics_record_success_and_soft_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "demo"
            output.mkdir()
            config = AppConfig(output_dir=str(root))
            context = PipelineContext(
                config=config,
                input_value="video.mp4",
                output_dir=output,
                analysis_profile="summary",
                processing_profile="fast",
                manifest=ProcessingManifest(task_id="task", processing_profile="fast"),
            )
            orchestrator = PipelineOrchestrator(config, processing_profile="fast")

            orchestrator._stage(context, "resolve_source", lambda: None)

            def fail() -> None:
                raise RuntimeError("visual unavailable")

            orchestrator._stage(context, "extract_frames", fail, soft_fail=True)

        success = context.manifest.stage_metrics["resolve_source"]
        warning = context.manifest.stage_metrics["extract_frames"]
        self.assertEqual(context.manifest.stage_status["resolve_source"], "completed")
        self.assertGreaterEqual(success.duration_ms, 0)
        self.assertEqual(success.attempt, 1)
        self.assertFalse(success.cache_hit)
        self.assertEqual(context.manifest.stage_status["extract_frames"], "warning")
        self.assertEqual(warning.error_code, "RuntimeError")
        self.assertIn("visual unavailable", warning.error_message)


if __name__ == "__main__":
    unittest.main()
