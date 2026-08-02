from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.config import AppConfig
from src.domain.models import ProcessingManifest, SourceRecord, TranscriptSegment
from src.knowledge_identity import KnowledgeRequestDimensions, build_knowledge_identity
from src.package_claim import package_claim_path
from src.pipeline.orchestrator import PipelineOrchestrator
from src.transcripts import write_jsonl


class _NoReacquireSourceAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve(self, _input_value: str) -> SourceRecord:
        self.calls.append("resolve")
        raise AssertionError("source resolution should be repaired from existing manifest")

    def collect_metadata(self) -> SourceRecord:
        self.calls.append("collect_metadata")
        raise AssertionError("metadata collection should be repaired from existing manifest")

    def acquire_subtitles(self, _work_dir: Path, _language: str) -> Path | None:
        self.calls.append("acquire_subtitles")
        raise AssertionError("subtitle acquisition should reuse existing raw transcript")

    def acquire_media(self, _work_dir: Path, _sample_seconds: int | None, *, audio_only: bool = False) -> Path:
        self.calls.append("acquire_media")
        raise AssertionError("media acquisition should reuse existing raw transcript")


class PipelineRepairTests(unittest.TestCase):
    def test_repair_reuses_existing_source_and_raw_transcript_without_reacquiring(self) -> None:
        with TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            package_dir = output_root / "Existing_video"
            package_dir.mkdir(parents=True)
            source = SourceRecord(
                source_type="online_video",
                platform="web",
                source_url="https://example.com/video",
                canonical_url="https://example.com/video",
                source_id="video",
                title="Existing",
            )
            identity = build_knowledge_identity(
                source,
                KnowledgeRequestDimensions(language="zh", transcript_only=True),
                input_value="https://example.com/video",
            )
            manifest = ProcessingManifest(
                task_id="failed-task",
                source=source,
                status="failed",
                identity_schema_version=identity.schema_version,
                knowledge_id=identity.knowledge_id,
                source_fingerprint=identity.source_fingerprint,
                request_fingerprint=identity.request_fingerprint,
                sample_seconds=None,
                transcript_status="completed",
                transcript_provider="platform",
                transcript_only=True,
                analysis_requested=False,
                analysis_status="skipped",
                analysis_skip_reason="user_requested_transcript_only",
                stage_status={
                    "resolve_source": "completed",
                    "collect_metadata": "completed",
                    "acquire_transcript": "completed",
                    "run_analysis": "skipped",
                    "export_knowledge_package": "failed",
                },
            )
            (package_dir / "manifest.json").write_text(
                json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False),
                encoding="utf-8",
            )
            write_jsonl(
                package_dir / "transcript.raw.jsonl",
                [TranscriptSegment(index=0, start=0, end=10, text="已有有效字幕。", language="zh")],
            )
            adapter = _NoReacquireSourceAdapter()

            with patch("src.pipeline.orchestrator.YtdlpSource", return_value=adapter):
                package = PipelineOrchestrator(
                    AppConfig(output_dir=str(output_root)),
                    processing_profile="fast",
                    no_analysis=True,
                    knowledge_identity=identity,
                    task_id="resume-task",
                ).run("https://example.com/video", is_url=True)

            self.assertEqual(adapter.calls, [])
            self.assertEqual(package.output_dir, package_dir)
            self.assertEqual(package.source.title, "Existing")
            self.assertEqual(package.transcript_segments[0].text, "已有有效字幕。")
            self.assertFalse(package_claim_path(output_root, identity.knowledge_id).exists())
            saved_manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["task_id"], "resume-task")
            self.assertEqual(saved_manifest["knowledge_id"], identity.knowledge_id)
            self.assertEqual(saved_manifest["stage_status"]["resolve_source"], "completed")
            self.assertEqual(saved_manifest["stage_status"]["collect_metadata"], "completed")
            self.assertEqual(saved_manifest["stage_status"]["acquire_transcript"], "completed")
            self.assertTrue(saved_manifest["stage_metrics"]["resolve_source"]["cache_hit"])
            self.assertTrue(saved_manifest["stage_metrics"]["collect_metadata"]["cache_hit"])
            self.assertTrue(saved_manifest["stage_metrics"]["acquire_transcript"]["cache_hit"])


if __name__ == "__main__":
    unittest.main()
