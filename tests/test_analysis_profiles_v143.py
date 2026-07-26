from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.analysis.profiles import PROFILES
from src.analysis.schemas import AnalysisParseError, parse_analysis_response
from src.domain.models import AnalysisResult, KnowledgePackage, ProcessingManifest, SourceRecord, TimelineEntry, TutorialStep
from src.exporters.analysis_markdown import render_profile_analysis
from src.exporters.markdown_renderer import render_knowledge_markdown
from src.exporters.models import selection_from_preset
from src.visual import generate_tutorial_step_snapshots
from src.web import SUPPORTED_MODES


class V143AnalysisProfileContractTests(unittest.TestCase):
    def test_four_profiles_use_different_content_structures(self) -> None:
        payloads = {
            "summary": {"content": {"one_sentence": "视频概括了核心内容。", "summary": "这是整合后的摘要。"}},
            "tutorial": {"content": {"tutorial_goal": "学会操作", "workflow_overview": "先后完成", "steps": [{"timestamp": 1, "title": "打开软件", "action": "点击打开", "expected_result": "进入界面"}]}},
            "viral": {"content": {"content_positioning": "工具分享", "target_audience": ["创作者"], "risks_and_limitations": ["未明确说明"]}},
            "close-reading": {"content": {"core_thesis": "核心命题", "key_concepts": ["概念"], "facts_to_verify": ["未明确说明"]}},
        }
        results = {
            profile: parse_analysis_response(json.dumps(payload, ensure_ascii=False), profile, "fake", "model")
            for profile, payload in payloads.items()
        }
        self.assertIn("one_sentence", results["summary"].content)
        self.assertIn("tutorial_goal", results["tutorial"].content)
        self.assertIn("content_positioning", results["viral"].content)
        self.assertIn("core_thesis", results["close-reading"].content)
        self.assertNotEqual(set(results["summary"].content), set(results["tutorial"].content))
        for result in results.values():
            self.assertFalse(result.generation.comments_included)
            self.assertIn(result.analysis_profile, SUPPORTED_MODES)
            self.assertIn(result.analysis_profile, PROFILES)

    def test_summary_markdown_has_stable_headings_and_no_images(self) -> None:
        result = parse_analysis_response(
            json.dumps(
                {
                    "content": {
                        "one_sentence": "视频完整说明了核心结论。",
                        "summary": "摘要以自然段整合背景、主要内容和结论。",
                        "professional_terms": [
                            {"term": "术语一", "definition": "解释一", "core_related": True, "reliable": True},
                            {"term": "术语二", "definition": "解释二", "core_related": True, "reliable": True},
                            {"term": "术语三", "definition": "解释三", "core_related": True, "reliable": True},
                        ],
                        "highlights": [{"title": f"亮点 {index}", "explanation": "说明"} for index in range(1, 7)],
                        "thoughts": [{"question": f"思考 {index}？"} for index in range(1, 7)],
                        "chapter_summaries": [{"title": f"章节 {index}", "start": index * 10, "summary": "章节总结"} for index in range(1, 7)],
                    }
                },
                ensure_ascii=False,
            ),
            "summary",
            "fake",
            "model",
        )
        text = "\n".join(render_profile_analysis(result))
        headings = ["## 一句话", "## 摘要", "## 专业术语", "## 亮点", "## 思考", "## 章节总结"]
        self.assertEqual(sorted(headings, key=text.index), headings)
        self.assertIn("亮点 6", text)
        self.assertIn("思考 6", text)
        self.assertIn("章节 6", text)
        self.assertNotIn("## 内容概览", text)
        self.assertNotIn("## 核心观点", text)
        self.assertNotIn("## 关键结论", text)
        self.assertNotIn("![[", text)
        self.assertNotIn("爆款公式", text)
        self.assertNotIn("完整教程步骤", text)

    def test_summary_professional_terms_are_hidden_below_three(self) -> None:
        result = parse_analysis_response(
            json.dumps(
                {
                    "content": {
                        "one_sentence": "视频说明了两个相关术语。",
                        "summary": "这是摘要。",
                        "professional_terms": [
                            {"term": "术语一", "definition": "解释一"},
                            {"term": "术语二", "definition": "解释二"},
                        ],
                    }
                },
                ensure_ascii=False,
            ),
            "summary",
            "fake",
            "model",
        )
        text = "\n".join(render_profile_analysis(result))
        self.assertNotIn("## 专业术语", text)
        self.assertNotIn("暂无术语", text)

    def test_summary_one_sentence_rejects_multiple_sentences_and_lists(self) -> None:
        invalid_values = ["第一句。第二句。", "- 这是列表。", "第一行。\n第二行"]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(AnalysisParseError):
                parse_analysis_response(
                    json.dumps({"content": {"one_sentence": value, "summary": "摘要。"}}, ensure_ascii=False),
                    "summary",
                    "fake",
                    "model",
                )

    def test_summary_one_sentence_accepts_one_english_sentence(self) -> None:
        result = parse_analysis_response(
            '{"content":{"one_sentence":"This video explains the core method.","summary":"A concise paragraph."}}',
            "summary",
            "fake",
            "model",
        )
        self.assertEqual(result.content["one_sentence"], "This video explains the core method.")

    def test_tutorial_fast_keeps_step_structure_without_images(self) -> None:
        result = parse_analysis_response(
            '{"content":{"tutorial_goal":"目标","steps":[{"timestamp":2,"title":"步骤","objective":"目标","action":"操作","expected_result":"结果"}]}}',
            "tutorial",
            "fake",
            "model",
            processing_profile="fast",
        )
        self.assertEqual(result.processing_profile, "fast")
        self.assertEqual(result.steps[0].action, "操作")
        self.assertEqual(result.content["steps"][0]["image"], "")

    def test_tutorial_complete_can_include_relative_tutorial_image(self) -> None:
        result = parse_analysis_response(
            '{"content":{"tutorial_goal":"目标","steps":[{"timestamp":2,"title":"步骤","action":"操作","expected_result":"结果","image":"assets/tutorial/tutorial_step_001.webp"}]}}',
            "tutorial",
            "fake",
            "model",
            processing_profile="complete",
        )
        text = "\n".join(render_profile_analysis(result))
        self.assertIn("![[assets/tutorial/tutorial_step_001.webp]]", text)

    def test_viral_and_close_reading_do_not_render_tutorial_steps_or_images(self) -> None:
        viral = parse_analysis_response('{"content":{"content_positioning":"定位","steps":[{"title":"不应出现","image":"assets/tutorial/x.webp"}]}}', "viral", "fake", "model")
        close = parse_analysis_response('{"content":{"core_thesis":"命题","steps":[{"title":"不应出现","image":"assets/tutorial/x.webp"}]}}', "close-reading", "fake", "model")
        for result in (viral, close):
            text = "\n".join(render_profile_analysis(result))
            self.assertNotIn("完整教程步骤", text)
            self.assertNotIn("![[", text)

    def test_comments_and_credentials_are_not_in_main_report(self) -> None:
        result = parse_analysis_response(
            '{"content":{"one_sentence":"视频概括了核心内容。","summary":"api_key=sk-secret 评论说很好"}}',
            "summary",
            "fake",
            "model",
        )
        text = "\n".join(render_profile_analysis(result))
        self.assertNotIn("sk-secret", json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        self.assertNotIn("评论区洞察", text)

    def test_old_knowledge_package_payload_is_compatible(self) -> None:
        result = AnalysisResult.model_validate({"status": "success", "summary": "旧摘要"})
        self.assertEqual(result.summary, "旧摘要")
        self.assertEqual(result.content["summary"], "旧摘要")
        self.assertEqual(result.content["one_sentence"], "旧摘要")

    def test_markdown_export_uses_profile_content_without_comments(self) -> None:
        source = SourceRecord(source_type="online_video", platform="youtube", source_url="https://youtube.com/watch?v=abc", source_id="abc", title="测试")
        analysis = AnalysisResult.model_validate({"status": "success", "analysis_profile": "viral", "content": {"content_positioning": "定位", "target_audience": ["观众"]}})
        package = KnowledgePackage(source=source, analysis=analysis, manifest=ProcessingManifest(task_id="t"), output_dir=Path("."))
        text = render_knowledge_markdown(package, selection_from_preset("abc", "light"), comment_insight={"hot_topics": ["评论热点"]})
        self.assertIn("## 内容定位", text)
        self.assertNotIn("评论热点", text)

    def test_tutorial_snapshot_writes_assets_tutorial_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "video.mp4"
            media.write_bytes(b"video")
            frame = root / "frames" / "frame.jpg"
            frame.parent.mkdir()
            frame.write_bytes(b"frame")
            analysis = AnalysisResult(
                status="success",
                analysis_profile="tutorial",
                processing_profile="complete",
                steps=[TutorialStep(title="步骤", timestamp=5, action="操作", expected_result="结果")],
            )
            timeline = [TimelineEntry(index=0, start=0, end=10, title="片段", representative_time=5, frame_path="frames/frame.jpg")]

            def fake_run(command):
                Path(command[-1]).write_bytes(b"webp")

            with (
                patch("src.visual.highlight_snapshots.resolve_executable", return_value="ffmpeg"),
                patch("src.visual.highlight_snapshots.run_command", side_effect=fake_run),
            ):
                result = generate_tutorial_step_snapshots(media, analysis, timeline, root)

            self.assertEqual(result.analysis.steps[0].image, "assets/tutorial/tutorial_step_001.webp")
            self.assertTrue((root / result.analysis.steps[0].image).is_file())


if __name__ == "__main__":
    unittest.main()
