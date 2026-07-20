from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.analysis.profiles import resolve_analysis_profile
from src.domain.models import AnalysisResult, GlossaryItem, HighlightItem, KnowledgePackage, ProcessingManifest, SourceRecord, TimedTextItem, TutorialStep
from src.exporters.markdown_renderer import render_knowledge_markdown
from src.exporters.models import selection_from_preset
from src.exporters.obsidian_exporter import build_obsidian_uri, write_to_vault
from src.timestamps import build_timestamp_target, format_timestamp
from src.utils import UserFacingError


class ProfileAndTimestampTests(unittest.TestCase):
    def test_profile_priority_and_tutorial_detection(self) -> None:
        transcript = "第一步创建项目目录，然后配置 AGENTS.md，最后运行命令。"
        self.assertEqual(resolve_analysis_profile("summary", title="教程", transcript=transcript), "summary")
        self.assertEqual(resolve_analysis_profile("auto", title="长期项目教程", transcript=transcript), "tutorial")
        self.assertEqual(resolve_analysis_profile("unknown", title="教程", transcript=transcript), "summary")

    def test_timestamp_format_and_platform_targets(self) -> None:
        self.assertEqual(format_timestamp(88.9), "01:28")
        self.assertEqual(format_timestamp(3735), "01:02:15")
        self.assertEqual(format_timestamp(-1), "")
        self.assertEqual(build_timestamp_target("https://youtu.be/abc?x=1&t=2#part", 88), "https://youtu.be/abc?x=1&t=88s#part")
        self.assertEqual(build_timestamp_target("https://www.bilibili.com/video/BV123/?p=2", 88), "https://www.bilibili.com/video/BV123/?p=2&t=88")


class MarkdownAndVaultTests(unittest.TestCase):
    def _package(self, root: Path) -> KnowledgePackage:
        source = SourceRecord(source_type="online_video", platform="bilibili", source_url="https://www.bilibili.com/video/BV123/", source_id="BV123", title='标题: "教程"', author="作者", analysis_profile="tutorial")
        analysis = AnalysisResult(status="success", analysis_profile="tutorial", summary="教程摘要。", highlights=[HighlightItem(title="第一项", explanation="说明", tags=["中文 标签"], start=88), HighlightItem(title="第二项", explanation="说明二")], prerequisites=[TimedTextItem(text="已有项目", timestamp=30)], steps=[TutorialStep(title="创建 AGENTS.md", description="在项目根目录创建文件。", timestamp=88, expected_result="规则可读取")], glossary=[GlossaryItem(term="AGENTS.md", definition="项目入口文件")], action_items=[TimedTextItem(text="检查 AGENTS.md", timestamp=88)])
        return KnowledgePackage(source=source, analysis=analysis, manifest=ProcessingManifest(task_id="task", status="completed", analysis_profile="tutorial"), output_dir=root)

    def test_tutorial_markdown_is_structured_and_hides_empty_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = self._package(Path(temp))
            selection = selection_from_preset("demo", "full")
            chat = {"messages": [{"role": "system", "content": "secret"}, {"role": "user", "content": "问题"}, {"role": "assistant", "content": "回答", "citations": [{"start": 88, "excerpt": "证据"}], "debug": "hidden"}]}
            text = render_knowledge_markdown(package, selection, chat=chat, user_notes="原始笔记")
        self.assertIn('title: "标题: \\"教程\\""', text)
        self.assertIn("## 操作步骤", text)
        self.assertIn("- [ ] 检查 AGENTS.md", text)
        self.assertIn("  `#中文-标签`", text)
        self.assertIn("\n\n- **第二项**", text)
        self.assertIn("## AI 对话记录", text)
        self.assertIn("## 我的笔记", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("debug", text)
        self.assertNotIn("## 注意事项", text)

    def test_vault_write_is_safe_atomic_and_uniquifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            first, uri = write_to_vault("# Note\n", str(vault), "外源/视频", "测试:标题.md")
            second, _ = write_to_vault("# Note\n", str(vault), "外源/视频", "测试:标题.md")
            self.assertTrue(first.is_file())
            self.assertNotEqual(first, second)
            self.assertIn("obsidian://open?", uri)
            with self.assertRaises(UserFacingError):
                write_to_vault("x", str(vault), ".obsidian", "x.md")

    def test_obsidian_uri_encodes_values(self) -> None:
        uri = build_obsidian_uri("我的 Vault", "外源/视频/笔记.md")
        self.assertIn("%E6%88%91%E7%9A%84%20Vault", uri)
        self.assertIn("%E5%A4%96%E6%BA%90%2F%E8%A7%86%E9%A2%91", uri)


if __name__ == "__main__":
    unittest.main()
