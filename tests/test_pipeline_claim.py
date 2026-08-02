from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.config import AppConfig
from src.domain.models import SourceRecord
from src.knowledge_identity import KnowledgeRequestDimensions, build_knowledge_identity
from src.package_claim import PackageClaimLocked, acquire_package_claim, package_claim_path
from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils import UserFacingError


class _FakeSourceAdapter:
    def __init__(self, source: SourceRecord) -> None:
        self.source = source

    def resolve(self, _input_value: str) -> SourceRecord:
        return self.source

    def collect_metadata(self) -> SourceRecord:
        return self.source


class PipelineClaimTests(unittest.TestCase):
    def test_active_package_claim_blocks_pipeline_before_mutating_package(self) -> None:
        with TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            source = SourceRecord(
                source_type="online_video",
                platform="web",
                source_url="https://example.com/video",
                source_id="video",
                title="Demo",
            )
            identity = build_knowledge_identity(
                source,
                KnowledgeRequestDimensions(language="zh"),
                input_value="https://example.com/video",
            )
            active = acquire_package_claim(
                output_root,
                knowledge_id=identity.knowledge_id,
                request_fingerprint=identity.request_fingerprint,
                task_id="active-task",
                output_dir=output_root / "Demo_video",
            )

            def stage(_self, _context, name, action, soft_fail=False):
                if name in {"resolve_source", "collect_metadata"}:
                    action()
                    return
                raise AssertionError(f"unexpected stage after blocked claim: {name}")

            with (
                patch("src.pipeline.orchestrator.YtdlpSource", return_value=_FakeSourceAdapter(source)),
                patch.object(PipelineOrchestrator, "_stage", stage),
            ):
                with self.assertRaises(PackageClaimLocked) as caught:
                    PipelineOrchestrator(AppConfig(output_dir=str(output_root))).run(
                        "https://example.com/video",
                        is_url=True,
                    )

            self.assertEqual(caught.exception.task_id, "active-task")
            self.assertFalse((output_root / "Demo_video").exists())
            active.release()

    def test_pipeline_releases_package_claim_on_failure(self) -> None:
        with TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            source = SourceRecord(
                source_type="online_video",
                platform="web",
                source_url="https://example.com/video",
                source_id="video",
                title="Demo",
            )
            identity = build_knowledge_identity(
                source,
                KnowledgeRequestDimensions(language="zh"),
                input_value="https://example.com/video",
            )

            def stage(_self, _context, name, action, soft_fail=False):
                if name in {"resolve_source", "collect_metadata"}:
                    action()
                    return
                raise UserFacingError("stop after claim")

            with (
                patch("src.pipeline.orchestrator.YtdlpSource", return_value=_FakeSourceAdapter(source)),
                patch.object(PipelineOrchestrator, "_stage", stage),
            ):
                with self.assertRaises(UserFacingError):
                    PipelineOrchestrator(AppConfig(output_dir=str(output_root))).run(
                        "https://example.com/video",
                        is_url=True,
                    )

            self.assertFalse(package_claim_path(output_root, identity.knowledge_id).exists())
            self.assertTrue((output_root / "Demo_video" / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
