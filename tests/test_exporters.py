from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.domain.models import (
    AnalysisResult,
    ChapterSummary,
    HighlightItem,
    KnowledgePackage,
    ProcessingManifest,
    SourceRecord,
    ThoughtQuestion,
    TimelineEntry,
    TranscriptSegment,
)
from src.exporters import export_knowledge_package


class ExporterTests(unittest.TestCase):
    def _render(self) -> str:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = SourceRecord(source_type="online_video", platform="youtube", source_url="https://youtube.com/watch?v=abc", source_id="abc", title="测试视频", author="作者")
        analysis = AnalysisResult(
            summary="这是摘要。",
            highlights=[HighlightItem(title="亮点", explanation="说明", tags=["知识"])],
            thoughts=[ThoughtQuestion(question="值得思考什么？")],
            chapters=[ChapterSummary(title="第一章", start=0, end=20, summary="章节总结", frame_path="frames/frame_0001.jpg", source_link="https://youtube.com/watch?v=abc&t=0s")],
        )
        package = KnowledgePackage(
            source=source,
            transcript_segments=[TranscriptSegment(index=0, start=0, end=2, text="不应嵌入主笔记的逐句字幕")],
            timeline=[TimelineEntry(index=0, start=0, end=20, title="第一章")],
            analysis=analysis,
            manifest=ProcessingManifest(task_id="task", status="completed", completed_at="now"),
            output_dir=root,
        )
        export_knowledge_package(package)
        return (root / "index.md").read_text(encoding="utf-8")

    def tearDown(self) -> None:
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def test_index_contains_core_sections(self) -> None:
        text = self._render()
        for heading in ("## 摘要", "## 亮点", "## 思考", "## 视频章节总结"):
            self.assertIn(heading, text)

    def test_index_excludes_raw_transcript_and_provider_logs(self) -> None:
        text = self._render()
        self.assertNotIn("不应嵌入主笔记的逐句字幕", text)
        self.assertNotIn("provider_attempts", text)

    def test_index_uses_relative_frame_and_has_no_bibigpt_link(self) -> None:
        text = self._render()
        self.assertIn("![[frames/frame_0001.jpg]]", text)
        self.assertNotIn("BibiGPT", text)

    def test_empty_optional_sections_are_hidden(self) -> None:
        text = self._render()
        self.assertNotIn("## 术语", text)
        self.assertNotIn("null", text)

