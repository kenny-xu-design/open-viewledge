from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.analysis.retry import reanalyze_knowledge_package
from src.config import AppConfig
from src.domain.models import (
    AnalysisResult,
    KnowledgePackage,
    ProcessingManifest,
    SourceRecord,
    TimelineEntry,
    TranscriptSegment,
)
from src.exporters import export_knowledge_package
from src.providers.llm.base import LLMResponse
from src.transcripts import write_jsonl
from src.utils import UserFacingError


class FakeProvider:
    name = "deepseek"
    model_name = "test-model"

    def __init__(self) -> None:
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def complete(self, _messages, **_kwargs) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=json.dumps(
                {
                    "one_sentence_summary": "一句话总结",
                    "summary": "重新生成的摘要。",
                    "highlights": [],
                    "thoughts": [],
                    "chapters": [],
                    "terminology": [],
                    "actions": [],
                },
                ensure_ascii=False,
            ),
            provider=self.name,
            model=self.model_name,
            finish_reason="stop",
            usage={"total_tokens": 10},
        )


class UnavailableProvider:
    name = "deepseek"
    model_name = "unavailable-model"

    def is_available(self) -> bool:
        return False


class AnalysisRetryTests(unittest.TestCase):
    def test_retry_reuses_transcript_and_updates_existing_package(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "demo"
            root.mkdir()
            source = SourceRecord(
                source_type="online_video",
                platform="bilibili",
                source_url="https://www.bilibili.com/video/BV1234567890",
                source_id="BV1234567890",
                title="测试视频",
            )
            manifest = ProcessingManifest(
                task_id="task",
                source=source,
                status="completed_with_warnings",
                analysis_status="failed",
                analysis_error="未配置 Key",
                stage_status={"run_analysis": "failed"},
                errors=["阶段 run_analysis 失败：未配置 Key"],
            )
            package = KnowledgePackage(
                source=source,
                transcript_segments=[],
                timeline=[TimelineEntry(index=0, start=0, end=12, title="片段")],
                analysis=AnalysisResult(status="failed", error="未配置 Key", analysis_profile="summary"),
                manifest=manifest,
                output_dir=root,
            )
            export_knowledge_package(package)
            write_jsonl(
                root / "transcript.raw.jsonl",
                [TranscriptSegment(index=0, start=0, end=12, text="这是已有字幕。", language="zh")],
            )
            (root / "analysis.json").write_text("{invalid", encoding="utf-8")
            provider = FakeProvider()

            result = reanalyze_knowledge_package(root, AppConfig(), provider=provider)

            self.assertEqual(provider.calls, 1)
            self.assertEqual(result.analysis.status, "success")
            self.assertEqual(result.analysis.summary, "重新生成的摘要。")
            self.assertEqual(result.manifest.analysis_status, "completed")
            self.assertEqual(result.manifest.stage_status["run_analysis"], "completed")
            self.assertEqual(result.manifest.errors, [])
            self.assertIn("重新生成的摘要。", (root / "index.md").read_text(encoding="utf-8"))
            self.assertIn("重新生成的摘要。", (root / "summary.md").read_text(encoding="utf-8"))

    def test_retry_failure_replaces_stale_error_and_persists_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "demo"
            root.mkdir()
            source = SourceRecord(
                source_type="online_video",
                platform="bilibili",
                source_url="https://www.bilibili.com/video/BV1234567890",
                source_id="BV1234567890",
                title="测试视频",
            )
            manifest = ProcessingManifest(
                task_id="task",
                source=source,
                status="completed_with_warnings",
                analysis_status="failed",
                analysis_error="旧错误",
                stage_status={"run_analysis": "failed"},
                errors=["阶段 run_analysis 失败：旧错误"],
            )
            package = KnowledgePackage(
                source=source,
                analysis=AnalysisResult(status="failed", error="旧错误", analysis_profile="summary"),
                manifest=manifest,
                output_dir=root,
            )
            export_knowledge_package(package)
            write_jsonl(
                root / "transcript.raw.jsonl",
                [TranscriptSegment(index=0, start=0, end=12, text="这是已有字幕。", language="zh")],
            )

            with self.assertRaisesRegex(UserFacingError, "DEEPSEEK_API_KEY"):
                reanalyze_knowledge_package(root, AppConfig(), provider=UnavailableProvider())

            analysis = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
            saved_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(analysis["status"], "failed")
            self.assertIn("DEEPSEEK_API_KEY", analysis["error"])
            self.assertNotIn("旧错误", analysis["error"])
            self.assertEqual(saved_manifest["analysis_status"], "failed")
            self.assertIn("DEEPSEEK_API_KEY", saved_manifest["analysis_error"])
            self.assertEqual(saved_manifest["provider_attempts"][-1]["error_type"], "configuration")


if __name__ == "__main__":
    unittest.main()
