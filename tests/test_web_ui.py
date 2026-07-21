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
        self.assertIn('/static/app.workspace-', self.html)
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

    def test_cupertino_design_token_categories_exist(self) -> None:
        required_tokens = {
            "--ui-canvas",
            "--ui-surface",
            "--ui-surface-secondary",
            "--ui-text-primary",
            "--ui-text-secondary",
            "--ui-separator",
            "--ui-accent",
            "--ui-success",
            "--ui-warning",
            "--ui-danger",
            "--ui-info",
            "--font-sans",
            "--font-size-body",
            "--line-height-body",
            "--font-weight-semibold",
            "--space-4",
            "--radius-control",
            "--shadow-overlay",
            "--control-height",
            "--z-toolbar",
            "--ui-material",
            "--material-blur",
            "--motion-standard",
            "--ease-out-ui",
            "--breakpoint-single-pane",
        }
        for token in required_tokens:
            self.assertIn(f"{token}:", self.css, token)
        self.assertIn(
            '--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
            self.css,
        )

    def test_light_dark_and_native_color_scheme_are_defined(self) -> None:
        self.assertIn('content="light dark"', self.html)
        self.assertIn("color-scheme: light dark", self.css)
        dark_theme = re.search(
            r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(?P<body>.*?)\}\s*\}",
            self.css,
            re.S,
        )
        self.assertIsNotNone(dark_theme)
        for token in ("--ui-canvas", "--ui-surface", "--ui-text-primary", "--ui-separator", "--ui-accent", "--ui-focus-ring"):
            self.assertIn(f"{token}:", dark_theme.group("body"), token)

    def test_every_css_variable_use_has_a_definition(self) -> None:
        defined = set(re.findall(r"--([a-zA-Z0-9-]+)\s*:", self.css))
        used = set(re.findall(r"var\(--([a-zA-Z0-9-]+)", self.css))
        self.assertEqual(used - defined, set())
        self.assertIn("--surface:", self.css)
        self.assertIn("--text-muted:", self.css)

    def test_reduced_motion_tokens_and_scroll_behavior_exist(self) -> None:
        reduced = re.search(
            r"@media \(prefers-reduced-motion: reduce\)\s*\{(?P<body>.*?)\n\}",
            self.css,
            re.S,
        )
        self.assertIsNotNone(reduced)
        self.assertIn("--motion-standard: 0ms", reduced.group("body"))
        self.assertIn("scroll-behavior: auto !important", reduced.group("body"))
        self.assertIn("animation-iteration-count: 1 !important", reduced.group("body"))
        self.assertIn('const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)"', self.js)
        self.assertIn("window.matchMedia(REDUCED_MOTION_QUERY).matches", self.js)
        self.assertNotIn('behavior: "smooth"', self.js)

    def test_cupertino_component_primitives_and_states_exist(self) -> None:
        component_css = re.search(
            r"/\* Cupertino component primitives\.(?P<body>.*?)/\* End Cupertino component primitives\. \*/",
            self.css,
            re.S,
        )
        self.assertIsNotNone(component_css)
        body = component_css.group("body")
        for component in (
            ".ui-button",
            ".ui-icon-button",
            ".ui-field",
            ".ui-text-field",
            ".ui-select",
            ".ui-segmented-control",
            ".ui-toggle",
            ".ui-status-badge",
            ".ui-inline-status",
            ".ui-progress",
            ".ui-spinner",
            ".ui-empty-state",
            ".ui-error-state",
        ):
            self.assertIn(component, body, component)
        for state in (
            ".ui-button--primary",
            ".ui-button--secondary",
            ".ui-button--tertiary",
            ".ui-button--destructive",
            '[aria-busy="true"]',
            ":disabled",
            '[aria-invalid="true"]',
            '[aria-checked="true"]',
            ".ui-status-badge--info",
            ".ui-status-badge--success",
            ".ui-status-badge--warning",
            ".ui-status-badge--danger",
            ".ui-progress--indeterminate",
        ):
            self.assertIn(state, body, state)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}|rgba?\(", body))
        self.assertNotIn("transition: all", body)
        self.assertNotIn("scale(0)", body)

    def test_migrated_button_field_select_and_status_contracts(self) -> None:
        self.assertRegex(self.html, r'class="[^"]*ui-button--primary[^"]*" id="startTask" aria-busy="false"')
        self.assertRegex(self.html, r'class="[^"]*ui-button--secondary[^"]*" data-close-dialog')
        self.assertRegex(self.html, r'class="[^"]*ui-button--destructive[^"]*" id="confirmDeleteKnowledge"')
        self.assertIn('class="icon-button ui-icon-button" id="refreshJobs"', self.html)
        self.assertIn('aria-label="刷新任务历史"', self.html)
        self.assertIn('id="taskSourceField" data-invalid="false"', self.html)
        self.assertIn('class="ui-field__label" for="taskSource"', self.html)
        self.assertIn('aria-describedby="taskSourceDescription"', self.html)
        self.assertIn('aria-errormessage="taskSourceError"', self.html)
        self.assertIn('id="taskSourceError" role="alert" hidden', self.html)
        self.assertIn('class="ui-select" id="taskMode"', self.html)
        self.assertIn("function setTaskSourceError(invalid)", self.js)
        self.assertIn('input.setAttribute("aria-invalid", String(invalid))', self.js)
        self.assertIn('id="modelBadge" role="status"', self.html)
        self.assertIn('id="processingStatus" role="status" aria-live="polite"', self.html)

    def test_segmented_control_has_radio_semantics_and_keyboard_navigation(self) -> None:
        self.assertIn('role="radiogroup" aria-label="来源类型" data-segmented-control', self.html)
        self.assertRegex(self.html, r'role="radio" aria-checked="true" tabindex="0" data-source-type="url"')
        self.assertRegex(self.html, r'role="radio" aria-checked="false" tabindex="-1" data-source-type="file"')
        handler = re.search(
            r"function handleSegmentedControlKeydown\(event\) \{(?P<body>.*?)\n\}",
            self.js,
            re.S,
        )
        self.assertIsNotNone(handler)
        for key in ("ArrowLeft", "ArrowRight", "Home", "End"):
            self.assertIn(f'"{key}"', handler.group("body"))
        self.assertIn("event.preventDefault()", handler.group("body"))
        self.assertIn("options[nextIndex].focus()", handler.group("body"))
        self.assertIn("options[nextIndex].click()", handler.group("body"))
        self.assertIn('button.setAttribute("aria-checked", String(selected))', self.js)
        self.assertIn("button.tabIndex = selected ? 0 : -1", self.js)

    def test_toggle_keeps_native_checkbox_keyboard_behavior(self) -> None:
        self.assertRegex(
            self.html,
            r'<label class="ui-toggle"><input id="taskFrames" type="checkbox" checked><span class="ui-toggle__track" aria-hidden="true"></span><span>生成关键帧</span></label>',
        )
        self.assertIn('.ui-toggle input:focus-visible + .ui-toggle__track', self.css)
        self.assertIn('.ui-toggle input:disabled ~ *', self.css)
        self.assertIn('if (event.defaultPrevented) return;', self.js)
        self.assertIn('const editing = ["INPUT", "TEXTAREA", "SELECT"]', self.js)

    def test_progress_loading_and_empty_state_are_accessible(self) -> None:
        self.assertIn('id="taskProgress" role="status" aria-live="polite"', self.html)
        self.assertIn('id="taskProgressBar" role="progressbar" aria-label="任务处理进度"', self.html)
        self.assertIn('aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"', self.html)
        self.assertIn('setAttribute("aria-valuenow", String(percent))', self.js)
        self.assertIn('setAttribute("aria-valuetext", $("#taskStatusText").textContent)', self.js)
        self.assertIn('function setTaskButtonLoading(loading)', self.js)
        self.assertIn('button.setAttribute("aria-busy", String(loading))', self.js)
        self.assertIn('class="result-empty ui-empty-state"', self.html)
        self.assertIn('class="ui-empty-state__title"', self.html)
        self.assertIn('class="ui-empty-state__description"', self.html)

    def test_component_motion_has_reduced_motion_fallbacks(self) -> None:
        reduced = re.search(
            r"@media \(prefers-reduced-motion: reduce\)\s*\{(?P<body>.*?)\n\}",
            self.css,
            re.S,
        )
        self.assertIsNotNone(reduced)
        self.assertIn("--motion-spinner: 0ms", reduced.group("body"))
        self.assertIn("--motion-progress: 0ms", reduced.group("body"))
        self.assertIn(".ui-progress--indeterminate .ui-progress__bar", reduced.group("body"))

    def test_frontend_remains_framework_free(self) -> None:
        self.assertNotRegex(self.html, r'https?://[^"\']+(react|vue|svelte|bootstrap|material|shadcn)')
        self.assertEqual(self.html.count("<script "), 1)
        self.assertEqual(self.html.count('rel="stylesheet"'), 1)

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

    def test_notes_use_backend_persistence_instead_of_session_drafts(self) -> None:
        self.assertIn("/notes`", self.js)
        self.assertIn('method: "PUT"', self.js)
        self.assertIn("flushNoteSave", self.js)
        self.assertIn("keepalive: true", self.js)
        self.assertNotIn("noteDrafts", self.js)
        self.assertIn('id="noteSaveStatus">未加载', self.html)

    def test_recent_job_history_is_visible_and_reloadable(self) -> None:
        self.assertIn('id="jobHistory"', self.html)
        self.assertIn('id="refreshJobs"', self.html)
        self.assertIn('api("/api/jobs")', self.js)
        self.assertIn("interrupted", self.js)

    def test_deepseek_is_the_only_task_backend(self) -> None:
        self.assertIn('id="taskBackend" type="hidden" value="deepseek"', self.html)
        self.assertNotIn('value="ollama"', self.html)
        self.assertNotIn('value="openai"', self.html)
        self.assertNotIn("taskPrivacy", self.html)

    def test_runtime_panel_displays_tools_and_provider_models(self) -> None:
        self.assertIn("runtime.tools", self.js)
        self.assertIn("runtime.providers", self.js)
        self.assertIn("未配置或未发现", self.js)

    def test_invalid_knowledge_package_is_not_rendered_as_success(self) -> None:
        self.assertIn('status === "failed" || status === "invalid"', self.js)
        self.assertIn('invalid: "知识包异常"', self.js)

    def test_failed_analysis_can_be_retried_without_reprocessing_media(self) -> None:
        self.assertIn('id="retryAnalysis"', self.html)
        self.assertIn("function retryAnalysis()", self.js)
        self.assertIn("/analysis/retry`", self.js)
        self.assertIn("仅重新执行 AI 分析", self.js)

    def test_library_records_support_confirmed_multi_delete(self) -> None:
        self.assertIn("<span>资源库</span>", self.html)
        self.assertIn("<span>产出库</span>", self.html)
        self.assertNotIn("知 · 资源库", self.html)
        self.assertNotIn("行 · 产出物", self.html)
        self.assertIn('id="toggleDeleteMode"', self.html)
        self.assertIn('id="deleteKnowledgeDialog"', self.html)
        self.assertIn('id="confirmDeleteKnowledge"', self.html)
        self.assertIn("function toggleKnowledgeDeleteSelection", self.js)
        self.assertIn('method: "DELETE"', self.js)
        self.assertIn("确认永久删除", self.html)

    def test_original_export_panel_supports_preview_download_and_vault(self) -> None:
        self.assertIn('id="exportKnowledgeDialog"', self.html)
        self.assertIn('data-export-preset="summary-chat"', self.html)
        self.assertIn('id="exportMarkdownPreview"', self.html)
        self.assertIn("function previewKnowledgeExport()", self.js)
        self.assertIn("function downloadKnowledgeExport()", self.js)
        self.assertIn("function saveKnowledgeExportToVault()", self.js)
        self.assertIn("/api/knowledge/${encodeURIComponent(state.selectedKnowledgeId)}/export", self.js)

    def test_unavailable_features_are_explicitly_disabled(self) -> None:
        self.assertRegex(self.html, r'data-media="capture"[^>]*disabled')
        self.assertRegex(self.html, r'id="captureNote"[^>]*disabled')
        self.assertIn("Obsidian 兼容 Markdown", self.html)

    def test_bilibili_controls_do_not_claim_programmatic_sync(self) -> None:
        self.assertIn("function syncMediaControls()", self.js)
        self.assertIn("mediaController instanceof BilibiliEmbedController", self.js)
        self.assertIn("当前平台播放器需在播放器内控制", self.js)
        self.assertIn("mediaController?.openExternally", self.js)

    def test_raw_transcript_is_only_loaded_on_explicit_action(self) -> None:
        self.assertNotIn("transcript.raw.jsonl", self.html)
        self.assertIn('openFile("transcript.raw.jsonl")', self.js)


if __name__ == "__main__":
    unittest.main()
