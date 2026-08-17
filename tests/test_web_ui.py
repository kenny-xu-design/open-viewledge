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

    def test_app_shell_and_responsive_view_contracts_exist(self) -> None:
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
        self.assertIn("Authoritative Cupertino AppShell", self.css)
        self.assertIn("@media (min-width: 1280px)", self.css)
        self.assertIn("@media (max-width: 1279px)", self.css)
        self.assertIn("@media (max-width: 959px)", self.css)
        self.assertIn('data-mobile-view="result"', self.html)

    def test_legacy_layout_generation_is_removed(self) -> None:
        for legacy_contract in (
            "sidebar-collapsed",
            "@media (max-width: 979px)",
            "@media (max-width: 620px)",
            "drawer-open",
            "grid-template-columns: var(--sidebar-width) minmax(500px, var(--center-width))",
        ):
            self.assertNotIn(legacy_contract, self.css + self.js, legacy_contract)

    def test_sidebar_and_inspector_have_accessible_sheet_controls(self) -> None:
        self.assertRegex(self.html, r'id="toggleSidebar"[^>]+aria-controls="sidebar"[^>]+aria-expanded="true"')
        self.assertRegex(self.html, r'id="toggleInspector"[^>]+aria-controls="collaborationPane"[^>]+aria-expanded="true"')
        self.assertIn('id="closeInspector" aria-label="关闭检查器"', self.html)
        self.assertIn('id="sidebar" aria-label="知识记录导航" tabindex="-1"', self.html)
        self.assertIn('id="collaborationPane" data-module="collaboration" aria-label="检查器" tabindex="-1"', self.html)
        self.assertIn("function syncShellAccessibility()", self.js)
        self.assertIn("function trapLayerFocus(event)", self.js)
        self.assertIn('layer.setAttribute("aria-modal", "true")', self.js)
        self.assertIn("sidebar.inert = !sidebarExpanded", self.js)
        self.assertIn("lastSidebarTrigger", self.js)
        self.assertIn("lastInspectorTrigger", self.js)

    def test_desktop_sidebar_reserves_a_real_navigation_column(self) -> None:
        self.assertIn("grid-template-columns: minmax(0, 1fr);", self.css)
        self.assertIn("position: fixed;", self.css)
        self.assertIn("--ui-sidebar-overlay: rgba(246, 246, 248, .60);", self.css)
        self.assertIn("background: var(--ui-sidebar-overlay);", self.css)
        self.assertIn("transform: translateX(-103%);", self.css)
        self.assertIn(".app-shell { grid-template-columns: var(--sidebar-width) minmax(0, 1fr); }", self.css)
        self.assertIn(".app-shell.sidebar-hidden { grid-template-columns: 56px minmax(0, 1fr); }", self.css)
        self.assertIn(".workspace-grid { grid-column: 2; }", self.css)
        self.assertIn(".app-shell.sidebar-hidden > .sidebar { display: none; transform: none; }", self.css)

    def test_deepseek_model_field_explains_api_id_and_console_label(self) -> None:
        self.assertIn('id="deepseekModel"', self.html)
        self.assertIn('placeholder="deepseek-v4-flash"', self.html)
        self.assertIn("DeepSeek-V4-Flash-0731", self.html)

    def test_sidebar_navigation_exposes_current_and_expanded_state(self) -> None:
        self.assertIn('id="resourceOverviewNav" aria-current="page"', self.html)
        self.assertIn('id="countResourceNav"', self.html)
        self.assertIn('<summary aria-expanded="false">', self.html)
        self.assertIn('$("#resourceOverviewNav").setAttribute("aria-current", "page")', self.js)
        self.assertIn('setAttribute("aria-expanded", String(details.open))', self.js)

    def test_source_validation_and_folder_set_contracts_exist(self) -> None:
        self.assertIn('id="validateTaskSource"', self.html)
        self.assertIn("async function validateTaskSource()", self.js)
        self.assertIn('id="taskSourceValidation"', self.html)
        self.assertIn("function setTaskSourceValidation(kind, text)", self.js)
        self.assertIn('setTaskSourceValidation("success"', self.js)
        self.assertIn('验证成功：路径有效，可稍后从文件夹知识集启动分析。', self.js)
        self.assertIn('setTaskSourceValidation("collection"', self.js)
        self.assertIn('setTaskSourceValidation("", "")', self.js)
        self.assertIn('setTaskSourceValidation("error", "验证失败', self.js)
        self.assertIn('api("/api/source/inspect"', self.js)
        self.assertIn('api("/api/folder-sets"', self.js)
        self.assertIn('analysisProfile: $("#taskMode").value', self.js)
        self.assertIn('processingProfile: $("#taskProcessingProfile").value', self.js)
        self.assertIn('transcriptGroupSeconds: $("#taskTranscriptGroupSeconds").value', self.js)
        self.assertIn('folderSet?.analysisProfile', self.js)
        self.assertIn('body: JSON.stringify({ inspection, analysisProfile:', self.js)
        self.assertIn('data-folder-item-id', self.js)
        self.assertIn('draggable="false"', self.js)
        self.assertIn("data.started || 0", self.js)
        self.assertIn("function formatFolderSetItemMeta", self.js)
        self.assertIn("formatFolderSetItemMeta(item, libraryItem)", self.js)
        self.assertIn("/v1/knowledge/{knowledge_id}/transcript", (Path(__file__).resolve().parents[1] / "docs" / "API_CONTRACTS.md").read_text(encoding="utf-8"))

    def test_transcript_groups_expose_clip_bridge_action(self) -> None:
        self.assertIn("function renderTranscriptGroupsWithClips()", self.js)
        self.assertIn("data-clip-group", self.js)
        self.assertIn("data-highlight-group", self.js)
        self.assertIn("data-intake-group", self.js)
        self.assertIn("async function clipTranscriptGroup(groupIndex, article = null)", self.js)
        self.assertIn("async function highlightTranscriptGroup(groupIndex, article = null)", self.js)
        self.assertIn('kind,', self.js)
        self.assertIn("async function intakeTranscriptGroup(groupIndex, article = null)", self.js)
        self.assertIn("function transcriptSelectionForClip(group, article, previous, next)", self.js)
        self.assertIn("function rememberTranscriptSelection()", self.js)
        self.assertIn("state.transcriptSelection", self.js)
        self.assertIn("transcriptActionMeta", self.js)
        self.assertIn("function transcriptActionRequest(group, kind, fingerprint = \"\")", self.js)
        self.assertIn("value.fingerprint !== fingerprint", self.js)
        self.assertIn("state.transcriptActionMeta.clear()", self.js)
        self.assertIn("const action = transcriptActionRequest(group, kind,", self.js)
        self.assertIn('transcriptActionRequest(group, "intake",', self.js)
        self.assertIn("captured_at: action.capturedAt", self.js)
        self.assertIn('document.addEventListener("selectionchange", rememberTranscriptSelection)', self.js)
        self.assertIn("window.getSelection", self.js)
        self.assertIn("selection.toString()", self.js)
        self.assertIn("media_start_seconds: pageSource ? null", self.js)
        self.assertIn("media_end_seconds: pageSource ? null", self.js)
        self.assertIn('api("/v1/clips"', self.js)
        self.assertIn('api("/v1/intakes"', self.js)
        self.assertIn('headers: { "Idempotency-Key": requestId }', self.js)
        self.assertIn("transcript-actions .clip-group-button", self.css)
        self.assertIn("transcript-actions .highlight-group-button", self.css)
        self.assertIn("transcript-actions .intake-group-button", self.css)

    def test_saved_clip_list_can_be_loaded_from_bridge(self) -> None:
        self.assertIn('id="toggleClips"', self.html)
        self.assertIn('id="clipList"', self.html)
        self.assertIn('id="transcriptClipNote"', self.html)
        self.assertIn("async function loadClipList()", self.js)
        self.assertIn("/v1/clips?knowledge_id=", self.js)
        self.assertIn("payload?.clips", self.js)
        self.assertIn('if (path.startsWith("/v1/"))', self.js)
        self.assertIn('data.schema_version !== "1.0"', self.js)
        self.assertIn('Object.prototype.hasOwnProperty.call(data, "data")', self.js)
        self.assertIn("return data.data", self.js)
        self.assertNotIn("response?.data?.clips", self.js)
        self.assertIn('note: $("#transcriptClipNote").value.trim()', self.js)
        self.assertIn("clip.note", self.js)
        self.assertIn("clip-card", self.css)
        self.assertIn("clip-note-field", self.css)

    def test_split_view_dividers_support_pointer_keyboard_and_values(self) -> None:
        for divider_id in ("paneResizer", "rightPaneResizer"):
            divider = re.search(rf'id="{divider_id}"[^>]+', self.html)
            self.assertIsNotNone(divider)
            for attribute in ('role="separator"', 'aria-orientation="vertical"', 'aria-valuemin=', 'aria-valuemax=', 'aria-valuenow=', 'tabindex="0"'):
                self.assertIn(attribute, divider.group(0))
        self.assertIn("function startResize(event)", self.js)
        self.assertIn("function handleDividerKeydown(event)", self.js)
        self.assertIn('event.shiftKey ? 48 : 16', self.js)
        self.assertIn('setAttribute("aria-valuenow"', self.js)
        self.assertIn(".pane-resizer:focus-visible::after", self.css)
        self.assertNotRegex(self.css, r"\.pane-resizer[^}]*transition\s*:\s*[^;]*(width|flex)")

    def test_divider_bounds_follow_panel_constraints_and_viewport_changes(self) -> None:
        self.assertIn("function moduleMinimumWidth(module)", self.js)
        self.assertIn("function moduleMaximumWidth(module)", self.js)
        self.assertIn("function reconcileLayoutWidths()", self.js)
        self.assertIn("requestAnimationFrame(reconcileLayoutWidths)", self.js)
        self.assertIn('max-width: min(520px, 48vw)', self.css)
        self.assertIn(".header-actions > * { flex: 0 0 auto; }", self.css)

    def test_preview_seek_keeps_bilibili_inside_the_embed(self) -> None:
        self.assertIn("function seekPreview(seconds)", self.js)
        self.assertIn('url.searchParams.set("bvid", this.videoId)', self.js)
        self.assertIn('url.searchParams.set("t", String(Math.floor(state.currentTime)))', self.js)
        self.assertIn("supportsSeek() { return true; }", self.js)
        seek_preview = re.search(r"function seekPreview\(seconds\)\s*\{(?P<body>.*?)\n\}", self.js, re.S)
        self.assertIsNotNone(seek_preview)
        self.assertNotIn("openExternally", seek_preview.group("body"))
        self.assertIn("event.preventDefault()", self.js)

    def test_local_video_display_ratios_do_not_apply_to_iframes(self) -> None:
        for value in ("original", "16/9", "4/3", "1/1", "9/16"):
            self.assertIn(f'value="{value}"', self.html)
        self.assertIn('id="videoObjectFit"', self.html)
        self.assertIn('value="contain" selected', self.html)
        self.assertIn('value="cover"', self.html)
        self.assertIn("video.videoWidth", self.js)
        self.assertIn("video.videoHeight", self.js)
        self.assertIn("mediaController instanceof LocalVideoController", self.js)
        self.assertIn('surface.style.setProperty("--media-aspect", String(selectedRatio))', self.js)
        self.assertIn(".media-surface.local-video-surface", self.css)
        self.assertIn("video.style.objectFit = fitSetting", self.js)

    def test_one_summary_region_uses_reading_surface(self) -> None:
        self.assertEqual(self.html.count("reading-surface"), 1)
        self.assertIn('id="summaryView" class="result-view reading-surface"', self.html)
        self.assertIn(".reading-surface", self.css)
        self.assertIn("width: min(calc(100% - 24px), 760px)", self.css)
        self.assertIn("border-radius: var(--radius-group)", self.css)

    def test_comment_feature_is_video_panel_sibling_before_highlights(self) -> None:
        self.assertIn('class="insight-tabs" role="tablist" aria-label="视频功能"', self.html)
        self.assertIn('data-insight-tab="comments"', self.html)
        self.assertIn('data-insight-tab="highlights"', self.html)
        self.assertNotIn("<h2>评论区洞察</h2>", self.js)
        comment_tab = self.html.index('data-insight-tab="comments"')
        highlight_tab = self.html.index('data-insight-tab="highlights"')
        self.assertLess(comment_tab, highlight_tab)
        self.assertIn("function setInsightTab(tab)", self.js)
        self.assertIn(".insight-tabs button.active", self.css)

    def test_dynamic_sections_do_not_truncate_to_first_five_items(self) -> None:
        self.assertNotIn(".slice(0, 5)", self.js)
        self.assertNotIn("analysis.thoughts.slice", self.js)
        self.assertIn("renderTutorialChapters", self.js)
        self.assertIn("renderTutorialSteps", self.js)

    def test_summary_uses_legacy_field_rendering(self) -> None:
        profile_contract = re.search(r'const PROFILE_RENDER_SECTIONS = \{(?P<body>.*?)\n\};', self.js, re.S)
        self.assertIsNotNone(profile_contract)
        self.assertNotIn("summary:", profile_contract.group("body"))
        render_summary = re.search(r"function renderSummary\(knowledge\) \{(?P<body>.*?)\n\}", self.js, re.S)
        self.assertIsNotNone(render_summary)
        body = render_summary.group("body")
        self.assertIn('profile !== "summary"', body)
        self.assertIn("<h2>摘要</h2>", body)
        self.assertIn("<h2>亮点</h2>", self.js)
        self.assertIn("<h2>思考</h2>", self.js)
        self.assertIn("视频章节总结", self.js)
        self.assertIn("页面结构", self.js)
        self.assertIn("<h2>专业术语</h2>", self.js)
        self.assertIn("if (terms.length < 3) return", self.js)
        self.assertNotIn('"一句话"', profile_contract.group("body"))

    def test_specialized_profiles_share_common_sections_and_hide_empty_details(self) -> None:
        render_summary = re.search(r"function renderSummary\(knowledge\) \{(?P<body>.*?)\n\}", self.js, re.S)
        self.assertIsNotNone(render_summary)
        body = render_summary.group("body")
        self.assertIn("if (hasProfileDetails) sections.push(renderProfileReport", body)
        self.assertNotIn("!profileReportRendered", body)
        render_field = re.search(r"function renderProfileField\(.*?\) \{(?P<body>.*?)\n\}", self.js, re.S)
        self.assertIsNotNone(render_field)
        self.assertIn('if (!html) return "";', render_field.group("body"))
        self.assertNotIn("<p>未明确说明</p>", render_field.group("body"))

    def test_toolbar_has_visible_page_hierarchy(self) -> None:
        self.assertIn('class="workspace-heading"', self.html)
        self.assertIn('<small>视频知识工作台</small>', self.html)
        self.assertIn(".workspace-heading", self.css)
        self.assertIn("--workspace-header-height: 56px", self.css)

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
        self.assertIn('id="taskAsrStatus"', self.html)
        self.assertIn("function renderTaskAsrStatus(job)", self.js)
        self.assertIn('gpu_model_load_timeout: "GPU 模型加载超时"', self.js)
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
        self.assertIn("function openOriginal()", self.js)
        self.assertIn('media.previewStatus === "external_only"', self.js)
        self.assertIn('$("#mediaControls").classList.toggle("hidden", externalOnly)', self.js)
        self.assertIn("当前来源不支持工作台内播放，字幕、摘要和知识包功能不受影响。", self.js)

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

    def test_api_config_entry_and_secret_handling_exist(self) -> None:
        self.assertIn('id="apiSettings"', self.html)
        self.assertIn('id="apiConfigDialog"', self.html)
        self.assertIn("API Key 默认仅用于当前本地运行会话", self.html)
        for element_id in ("deepseekApiKey", "geminiApiKey", "groqApiKey"):
            self.assertRegex(self.html, rf'id="{element_id}" type="password"')
        self.assertIn('id="deepseekBaseUrl"', self.html)
        self.assertIn('id="deepseekModel"', self.html)
        self.assertIn('id="geminiModel"', self.html)
        self.assertIn('id="groqModel"', self.html)
        self.assertIn('data-provider-test="groq"', self.html)
        self.assertIn('"deepseek", "gemini", "groq"', self.js)
        self.assertIn('/api/provider-config"', self.js)
        self.assertIn('/api/provider-config/test"', self.js)
        self.assertIn("toggleSecretField", self.js)
        self.assertNotIn("keyTail", self.js)
        self.assertNotIn("localStorage.setItem(SETTINGS.api", self.js)
        self.assertNotIn("sessionStorage", self.js)

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
                "vs.activeInsightTab",
                "vs.sidebarCollapsed",
                "vs.transcriptFollowMode",
                "vs.playbackRate",
                "vs.videoAspectRatio",
                "vs.videoObjectFit",
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

    def test_duplicate_task_decision_flow_is_user_visible(self) -> None:
        self.assertIn('id="taskDuplicateDecision"', self.html)
        self.assertIn('id="taskDuplicateActions"', self.html)
        self.assertIn("function renderDuplicateDecision", self.js)
        self.assertIn("function handleDuplicateAction", self.js)
        self.assertIn("isDuplicateTaskError(error)", self.js)
        self.assertIn("payload.duplicateAction = duplicateAction", self.js)
        self.assertIn("data.job.knowledgeId ||", self.js)
        self.assertIn("data-duplicate-action", self.js)
        for action in ("reuse", "resume", "refresh", "revision", "reject"):
            self.assertIn(action, self.js)
        self.assertIn(".task-duplicate", self.css)

    def test_transcript_group_selector_is_visible_and_submitted(self) -> None:
        self.assertIn('id="taskTranscriptGroupSeconds"', self.html)
        self.assertIn('<option value="30" selected>30秒（推荐）</option>', self.html)
        for value in ("15", "30", "60", "120"):
            self.assertIn(f'<option value="{value}"', self.html)
        self.assertIn('transcriptGroupSeconds: $("#taskTranscriptGroupSeconds").value', self.js)
        self.assertNotIn("60秒（当前配置）", self.html)

    def test_library_records_show_processing_duration_timer(self) -> None:
        self.assertIn("processingDurationMs", self.js)
        self.assertIn("formatProcessingDuration", self.js)
        self.assertIn("updateProcessingTimers", self.js)
        self.assertIn("record-processing-time", self.css)

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
        self.assertIn("仅运行 AI 分析", self.html)
        self.assertIn("knowledge.transcriptReady", self.js)
        self.assertIn("knowledge.analysisReady", self.js)
        self.assertIn("转写完成，AI 分析未运行", self.js)
        self.assertIn("AI 分析超时", self.js)
        self.assertIn("analysis_requested: !transcriptOnly", self.js)
        self.assertIn('$("#taskNoSummary").checked = false', self.js)
        self.assertNotIn("taskNoSummary: ", self.js)

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

    def test_processing_profile_is_exposed_separately_from_analysis_mode(self) -> None:
        self.assertIn('id="taskMode"', self.html)
        self.assertIn('id="taskProcessingProfile"', self.html)
        self.assertIn('<option value="complete">complete（完整兼容）</option>', self.html)
        self.assertIn('<option value="fast">fast（优先文本）</option>', self.html)
        self.assertIn('processingProfile: $("#taskProcessingProfile").value', self.js)

    def test_bilibili_series_detection_offers_knowledge_set_or_current_video(self) -> None:
        self.assertIn('id="seriesDecision"', self.html)
        self.assertIn('id="seriesCreateSet"', self.html)
        self.assertIn('id="seriesAnalyzeCurrent"', self.html)
        self.assertIn('/api/source/inspect', self.js)
        self.assertIn('/api/knowledge-sets', self.js)
        self.assertIn("pendingSeriesInspection", self.js)
        self.assertIn('activeSourceType === "url" && inspection.isCollection', self.js)
        self.assertIn('$("#taskTranscriptGroupSeconds").value = "30"', self.js)
        self.assertIn("seriesCreateSet", self.js)
        self.assertIn("function analyzeKnowledgeSetItem", self.js)
        self.assertIn('set?.analysisProfile || "tutorial"', self.js)
        self.assertIn('set?.processingProfile || "complete"', self.js)
        self.assertIn('set?.transcriptGroupSeconds || 30', self.js)
        self.assertIn("function isBilibiliUrl", self.js)
        self.assertIn('data-output-kind="series"', self.js)
        self.assertIn("function selectOutputCollection", self.js)
        self.assertIn("function renderCollectionRecords", self.js)
        self.assertIn("formatKnowledgeSetItemMeta", self.js)
        self.assertIn("analysisAt", self.js)
        self.assertNotIn("(set.items || []).slice(0, 6)", self.js)

    def test_bilibili_timestamp_seek_reloads_the_embedded_player(self) -> None:
        self.assertIn("function syncMediaControls()", self.js)
        self.assertIn("mediaController instanceof BilibiliEmbedController", self.js)
        self.assertIn("请在 B站播放器内点击播放", self.js)
        self.assertIn("this.element.src = url.toString()", self.js)
        self.assertIn("function openOriginal()", self.js)

    def test_local_media_playback_failure_is_explained(self) -> None:
        self.assertIn("本地视频无法播放，请检查视频文件或 FFmpeg 配置", self.js)

    def test_knowledge_inbox_is_integrated_into_the_resource_overview(self) -> None:
        for element_id in (
            "resourceOverviewPane",
            "resourceOverviewInbox",
            "inboxList",
            "refreshInbox",
            "inboxStateFilter",
            "loadMoreInbox",
            "overviewCountInbox",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn('data-overview-tab="inbox"', self.html)
        self.assertNotIn('id="inboxSidebarView"', self.html)
        self.assertIn("function refreshInbox", self.js)
        self.assertIn("function performIntakeAction", self.js)
        self.assertIn("data-inbox-retry", self.js)
        self.assertIn("重试加载", self.js)
        self.assertIn('data-intake-action="start"', self.js)
        self.assertIn('data-intake-action="retry"', self.js)
        self.assertIn('data-intake-action="cancel"', self.js)
        self.assertIn("data-open-intake-record", self.js)
        self.assertIn('headers: { "Idempotency-Key":', self.js)
        self.assertIn('item.state === "processing"', self.js)
        self.assertIn("function scheduleKnowledgeSetPoll()", self.js)
        self.assertIn("knowledgeSetPoller", self.js)
        self.assertIn("const libraryChanged = await refreshKnowledgeSets();", self.js)
        self.assertIn("if (libraryChanged) await refreshLibrary();", self.js)
        self.assertIn('.inbox-card.state-processing', self.css)
        for label in ("等待处理", "处理中", "需要处理", "已就绪", "处理失败", "重复来源", "已取消"):
            self.assertIn(label, self.js)

    def test_folder_set_drag_rules_keep_videos_fixed_and_reorder_siblings_only(self) -> None:
        self.assertIn("folder-set-card[draggable='true']", self.js)
        self.assertIn('draggable="false"', self.js)
        self.assertIn('data-folder-set-id=', self.js)
        self.assertIn('sourceSet.parentSetId !== targetSet.parentSetId', self.js)
        self.assertIn("/reorder", self.js)

    def test_resource_output_project_and_collapsed_rail_contracts_exist(self) -> None:
        self.assertIn('id="outputCollectionList"', self.html)
        self.assertIn('id="projectList"', self.html)
        self.assertIn('id="sidebarRail"', self.html)
        self.assertIn('id="sidebarFlyout"', self.html)
        self.assertIn('data-rail-action="resource"', self.html)
        self.assertIn('data-rail-panel="output"', self.html)
        self.assertIn('data-rail-panel="projects"', self.html)
        self.assertIn('state.libraryItems.filter((item) => !item.inCollection)', self.js)
        self.assertIn('api("/api/projects"', self.js)
        self.assertIn('data-record-menu', self.js)
        self.assertIn('data-project-action="move"', self.js)
        self.assertIn('data-project-action="create"', self.js)
        self.assertIn('data-project-action="remove"', self.js)
        self.assertIn('localStorage.setItem(SETTINGS.sidebarCollapsed', self.js)
        self.assertIn('.app-shell.sidebar-hidden > .sidebar-rail { display: flex; }', self.css)
        self.assertIn('.app-shell.sidebar-hidden > .sidebar-flyout:not([hidden]) { display: grid; }', self.css)

    def test_global_search_replaces_header_action_and_keeps_local_filter_separate(self) -> None:
        self.assertNotIn('id="focusSearch"', self.html)
        self.assertNotIn('class="new-summary" id="newSummary"', self.html)
        self.assertIn('class="new-summary sidebar-new-summary sidebar-only-expanded" id="newSummary"', self.html)
        self.assertIn('id="openGlobalSearch"', self.html)
        self.assertIn('id="globalSearchDialog"', self.html)
        self.assertIn('id="globalSearchInput"', self.html)
        self.assertIn('id="globalSearchDeep"', self.html)
        self.assertIn('data-global-search-kind="all"', self.html)
        self.assertIn('data-global-search-kind="collection"', self.html)
        self.assertIn('data-global-search-kind="project"', self.html)
        self.assertIn('data-rail-action="global-search"', self.html)
        self.assertIn("function openGlobalSearch", self.js)
        self.assertIn("function runGlobalSearch", self.js)
        self.assertIn('api(`/api/search?', self.js)
        self.assertIn('event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "k"', self.js)
        self.assertIn('event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === "k"', self.js)
        self.assertIn(".sidebar-search-row", self.css)
        self.assertIn(".rail-button.rail-new-summary", self.css)
        self.assertIn(".global-search-body", self.css)
        self.assertIn("@media (max-width: 640px)", self.css)

    def test_resource_overview_routes_filters_and_preserves_detail_deep_links(self) -> None:
        for element_id in (
            "resourceOverviewPane",
            "resourceOverviewRecords",
            "resourceOverviewSearch",
            "resourceSourceFilter",
            "resourceSort",
            "overviewDeleteMode",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        for tab in ("all", "inbox", "processing", "completed"):
            self.assertIn(f'data-overview-tab="{tab}"', self.html)
        self.assertIn('history.pushState(null, "", "#/resources")', self.js)
        self.assertIn('history.replaceState(null, "", "#/resources")', self.js)
        self.assertIn('`#/knowledge/${encodeURIComponent(id)}`', self.js)
        self.assertIn("function renderResourceOverview()", self.js)
        self.assertIn("function independentResourceItems()", self.js)
        self.assertIn("state.libraryItems.filter((item) => !item.inCollection)", self.js)
        self.assertIn('renderRecordMenu(item.id, "overview")', self.js)
        self.assertIn("resource-overview-active .workspace-grid > .workspace-module", self.css)

    def test_bridge_object_errors_are_rendered_as_messages(self) -> None:
        self.assertIn("data?.error?.message || data?.error", self.js)
        self.assertNotIn("new Error(data?.error ||", self.js)

    def test_web_page_records_hide_media_timestamps_and_show_page_copy(self) -> None:
        self.assertIn('media.kind === "page"', self.js)
        self.assertIn("打开原网页", self.js)
        self.assertIn("页面正文", self.js)
        self.assertIn("function isActivePage()", self.js)
        self.assertIn('page ? "页面结构" : "视频章节总结"', self.js)
        self.assertIn('isActivePage() ? `<span class="page-position">', self.js)
        self.assertIn(".page-position", self.css)

    def test_raw_transcript_is_only_loaded_on_explicit_action(self) -> None:
        self.assertNotIn("transcript.raw.jsonl", self.html)
        self.assertIn('openFile("transcript.raw.jsonl")', self.js)


if __name__ == "__main__":
    unittest.main()
