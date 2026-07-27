from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.domain.models import (
    AnalysisResult,
    ChapterSummary,
    HighlightItem,
    KnowledgePackage,
    NormalizedComment,
    ProcessingManifest,
    SourceRecord,
    ThoughtQuestion,
    TimelineEntry,
    TranscriptSegment,
)
from src.exporters import export_directory_to_vault, export_knowledge_package, selection_from_preset


class ExporterTests(unittest.TestCase):
    def _render(self, export_legacy_note: bool = False, user_note: str = "") -> str:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = SourceRecord(source_type="online_video", platform="youtube", source_url="https://youtube.com/watch?v=abc", source_id="abc", title="测试视频", author="作者")
        analysis = AnalysisResult(
            summary="这是摘要。",
            terminology=[
                {"term": "术语一", "definition": "解释一"},
                {"term": "术语二", "definition": "解释二"},
                {"term": "术语三", "definition": "解释三"},
            ],
            highlights=[HighlightItem(title="亮点", explanation="说明", tags=["知识"], image="assets/highlights/highlight_001.webp")],
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
        if user_note:
            (root / "user_notes.md").write_text(user_note, encoding="utf-8")
        export_knowledge_package(package, export_legacy_note=export_legacy_note)
        return (root / "index.md").read_text(encoding="utf-8")

    def tearDown(self) -> None:
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def test_index_contains_core_sections(self) -> None:
        text = self._render()
        for heading in ("## 摘要", "## 专业术语", "## 亮点", "## 思考", "## 视频章节总结", "## 原文资料"):
            self.assertIn(heading, text)
        self.assertNotIn("## 一句话", text)
        self.assertNotIn("## 内容概览", text)
        self.assertNotIn("## 关键结论", text)

    def test_index_excludes_raw_transcript_and_provider_logs(self) -> None:
        text = self._render()
        self.assertNotIn("不应嵌入主笔记的逐句字幕", text)
        self.assertNotIn("provider_attempts", text)

    def test_index_does_not_export_images_for_summary_profile_and_has_no_bibigpt_link(self) -> None:
        text = self._render()
        self.assertNotIn("![[frames/frame_0001.jpg]]", text)
        self.assertNotIn("![[assets/highlights/highlight_001.webp]]", text)
        self.assertNotIn("BibiGPT", text)

    def test_empty_optional_sections_are_hidden(self) -> None:
        text = self._render()
        self.assertNotIn("## 术语", text)
        self.assertNotIn("null", text)

    def test_compatible_export_includes_user_notes(self) -> None:
        self._render(export_legacy_note=True, user_note="这是用户自己的判断。")
        text = (Path(self.temp.name) / "export_note.md").read_text(encoding="utf-8")
        self.assertIn("## 我的笔记", text)
        self.assertIn("这是用户自己的判断。", text)

    def test_directory_export_can_include_comment_sections(self) -> None:
        self._render()
        root = Path(self.temp.name)
        (root / "comments.json").write_text(
            json_dump(
                {
                    "items": [
                        NormalizedComment(
                            comment_id="c1",
                            author="观众",
                            content="01:28 这里很有帮助",
                            likes=5,
                            source_url="https://youtube.com/watch?v=abc",
                            timestamps=[88.0],
                            platform="youtube",
                        ).model_dump(mode="json")
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "comment_insights.json").write_text(
            json_dump({"hot_topics": ["片段清晰"], "needs_verification": ["评论观点需核查"]}),
            encoding="utf-8",
        )

        from src.exporters import render_directory_export

        markdown, _ = render_directory_export(root, selection_from_preset(root.name, "full"))

        self.assertNotIn("## 评论摘录", markdown)
        self.assertNotIn("[01:28]", markdown)
        self.assertIn("## 评论区洞察", markdown)
        self.assertIn("评论观点需核查", markdown)

    def test_obsidian_export_copies_tutorial_assets_with_relative_reference(self) -> None:
        self._render()
        root = Path(self.temp.name)
        analysis_path = root / "analysis.json"
        import json
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        payload["analysis_profile"] = "tutorial"
        payload["steps"] = [{
            "title": "步骤",
            "description": "操作",
            "timestamp": 1,
            "expected_result": "结果",
            "image": "assets/tutorial/tutorial_step_001.webp",
        }]
        payload["content"] = {
            "tutorial_goal": "目标",
            "workflow_overview": "流程",
            "steps": payload["steps"],
        }
        analysis_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        image = root / "assets" / "tutorial" / "tutorial_step_001.webp"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"webp")
        with tempfile.TemporaryDirectory() as vault:
            selection = selection_from_preset(root.name, "light")
            result = export_directory_to_vault(
                root,
                selection,
                vault_path=vault,
                subdir="外源/视频",
            )
            markdown = Path(result["file_path"]).read_text(encoding="utf-8")
            self.assertEqual(len(result["copied_assets"]), 1)
            copied = Path(vault) / result["copied_assets"][0]
            self.assertTrue(copied.is_file())
            self.assertIn(f"![[assets/video-summary/{root.name}/tutorial/tutorial_step_001.webp]]", markdown)


def json_dump(payload: object) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
