from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_UI = Path(__file__).resolve().parents[1] / "src" / "web_ui"


class WebUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEB_UI / "index.html").read_text(encoding="utf-8")
        cls.css = (WEB_UI / "app.css").read_text(encoding="utf-8")
        cls.js = (WEB_UI / "app.js").read_text(encoding="utf-8")

    def test_three_pane_and_mobile_view_contracts_exist(self) -> None:
        for element_id in (
            "sidebar",
            "resultPane",
            "paneResizer",
            "centerPane",
            "rightPaneResizer",
            "collaborationPane",
            "insightPane",
            "notesPane",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn('class="workspace-header"', self.html)
        self.assertIn("@media (max-width: 1179px)", self.css)
        self.assertIn('data-mobile-view="result"', self.html)

    def test_workspace_order_is_configurable(self) -> None:
        self.assertIn('id="layoutDialog"', self.html)
        self.assertIn('id="layoutPosition1"', self.html)
        self.assertIn("function applyModuleOrder()", self.js)
        self.assertIn("DEFAULT_MODULE_ORDER", self.js)

    def test_media_controller_contracts_exist(self) -> None:
        self.assertIn("class MediaController", self.js)
        self.assertIn("class HtmlMediaController", self.js)
        self.assertIn("class ExternalLinkController", self.js)
        self.assertIn("class YouTubeMediaController", self.js)
        self.assertIn("class BilibiliEmbedController", self.js)
        self.assertIn("class LocalVideoController", self.js)
        self.assertIn("class LocalAudioController", self.js)
        self.assertIn("supportsSeek()", self.js)
        self.assertIn("mediaController?.destroy()", self.js)
        self.assertIn("mediaController?.openExternally", self.js)

    def test_chat_uses_real_endpoint_and_has_no_simulated_answer(self) -> None:
        self.assertIn('api("/api/chat"', self.js)
        self.assertIn("data.citations", self.js)
        self.assertNotIn("上下文对话功能尚未接入", self.js)
        self.assertNotIn("模拟回答", self.js)
        self.assertIn("currentChatHistory()", self.js)
        self.assertIn("data.model", self.js)
        self.assertIn("AbortController", self.js)
        self.assertIn("data.knowledge_id !== knowledgeId", self.js)
        self.assertIn("/chat`", self.js)

    def test_provider_selector_and_chat_controls_exist(self) -> None:
        self.assertIn('id="chatProvider"', self.html)
        self.assertIn('value="deepseek"', self.html)
        self.assertIn('value="gemini"', self.html)
        self.assertIn('id="clearChat"', self.html)
        self.assertIn("regenerateLastAnswer", self.js)

    def test_local_storage_is_limited_to_ui_settings(self) -> None:
        settings_match = re.search(r"const SETTINGS = \{(?P<body>.*?)\};", self.js, re.S)
        self.assertIsNotNone(settings_match)
        stored_keys = set(re.findall(r'"(vs\.[^"]+)"', settings_match.group("body")))
        self.assertEqual(
            stored_keys,
            {
                "vs.moduleOrder",
                "vs.moduleWidths",
                "vs.activeResultTab",
                "vs.transcriptFollowMode",
                "vs.playbackRate",
            },
        )
        self.assertNotIn("vs.note", self.js)
        self.assertNotIn("vs.chat", self.js)

    def test_deepseek_is_the_only_task_backend(self) -> None:
        self.assertIn('id="taskBackend" type="hidden" value="deepseek"', self.html)
        self.assertNotIn('value="ollama"', self.html)
        self.assertNotIn('value="openai"', self.html)
        self.assertNotIn("taskPrivacy", self.html)

    def test_unavailable_features_are_explicitly_disabled(self) -> None:
        self.assertRegex(self.html, r'data-media="capture"[^>]*disabled')
        self.assertRegex(self.html, r'id="captureNote"[^>]*disabled')
        self.assertIn("Obsidian 数据层 · 规划中", self.html)

    def test_raw_transcript_is_only_loaded_on_explicit_action(self) -> None:
        self.assertNotIn("transcript.raw.jsonl", self.html)
        self.assertIn('openFile("transcript.raw.jsonl")', self.js)


if __name__ == "__main__":
    unittest.main()
