"use strict";

document.documentElement.dataset.uiVersion = "workspace-18";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const DEFAULT_MODULE_ORDER = ["result", "media", "collaboration"];
const EXPORT_SECTION_LABELS = { metadata: "基本信息", summary: "摘要", highlights: "亮点", prerequisites: "前置条件", steps: "操作步骤", glossary: "关键术语", thoughts: "思考", action_items: "可执行动作", warnings: "注意事项", chapters: "章节", keyframes: "关键帧", chat: "AI 对话", comment_insights: "评论区洞察", user_notes: "我的笔记", source_materials: "原文资料" };
const EXPORT_PRESETS = { light: ["metadata", "summary", "highlights", "chapters"], "summary-chat": ["metadata", "summary", "highlights", "chat", "user_notes"], full: Object.keys(EXPORT_SECTION_LABELS) };
const ANALYSIS_MODE_META = {
  summary: { label: "标准摘要", description: "适合资讯、访谈、介绍和一般知识视频" },
  tutorial: { label: "教程提取", description: "适合软件、编程、设计和制作教程" },
  viral: { label: "爆款分析", description: "适合热门、短视频、广告和自媒体内容" },
  "close-reading": { label: "深度精读", description: "适合课程、演讲、长访谈和观点内容" },
};
const PROFILE_RENDER_SECTIONS = {
  tutorial: [["教程目标", "tutorial_goal", "text"], ["最终成果", "final_result", "text"], ["前置条件", "prerequisites", "list"], ["工具与材料", "tools_and_materials", "list"], ["流程总览", "workflow_overview", "text"], ["完整教程步骤", "steps", "steps"], ["关键参数与设置", "key_parameters", "list"], ["常见错误与排查", "troubleshooting", "list"], ["完成验收清单", "acceptance_checklist", "checklist"], ["可复用命令或模板", "reusable_commands_or_templates", "list"], ["教程局限", "limitations", "list"]],
  viral: [["内容定位", "content_positioning", "text"], ["目标受众", "target_audience", "list"], ["标题与封面承诺", "title_and_cover_promise", "text"], ["前 30 秒钩子", "first_30_seconds_hook", "text"], ["内容结构", "content_structure", "list"], ["节奏与留存设计", "retention_design", "list"], ["情绪与叙事机制", "emotion_and_narrative", "list"], ["视觉包装与剪辑", "visual_packaging_and_editing", "list"], ["互动与传播设计", "interaction_and_distribution", "list"], ["可复用内容公式", "reusable_content_formula", "list"], ["可借鉴点", "takeaways", "list"], ["风险与局限", "risks_and_limitations", "list"]],
  "close-reading": [["核心命题", "core_thesis", "text"], ["关键概念", "key_concepts", "list"], ["论证地图", "argument_map", "list"], ["证据评估", "evidence_assessment", "list"], ["隐含假设", "implicit_assumptions", "list"], ["可能的反方观点", "counterarguments", "list"], ["论证局限", "argument_limits", "list"], ["视觉证据", "visual_evidence", "list"], ["延伸联系", "extended_connections", "list"], ["待核查事实", "facts_to_verify", "list"]],
};
const SETTINGS = {
  moduleOrder: "vs.moduleOrder",
  moduleWidths: "vs.moduleWidths",
  activeResultTab: "vs.activeResultTab",
  activeInsightTab: "vs.activeInsightTab",
  transcriptFollowMode: "vs.transcriptFollowMode",
  playbackRate: "vs.playbackRate",
  videoAspectRatio: "vs.videoAspectRatio",
  videoObjectFit: "vs.videoObjectFit",
};
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const WIDE_SHELL_QUERY = "(min-width: 1280px)";
const SINGLE_PANE_QUERY = "(max-width: 959px)";
const RECENT_JOB_LIMIT = 5;

function uiScrollBehavior() {
  return typeof window.matchMedia === "function" && window.matchMedia(REDUCED_MOTION_QUERY).matches ? "auto" : "smooth";
}

const state = {
  selectedKnowledgeId: "",
  libraryItems: [],
  activeResultTab: localStorage.getItem(SETTINGS.activeResultTab) || "summary",
  activeInsightTab: localStorage.getItem(SETTINGS.activeInsightTab) || "comments",
  activeSource: null,
  currentTime: 0,
  currentChapter: -1,
  transcriptFollowMode: localStorage.getItem(SETTINGS.transcriptFollowMode) === "true",
  moduleOrder: readModuleOrder(),
  moduleWidths: readJsonSetting(SETTINGS.moduleWidths, {}),
  taskStatus: null,
  chatStateByKnowledgeId: {},
  loading: false,
  error: "",
  filter: "all",
  transcriptGroups: [],
  transcriptLoadedFor: "",
  scrollPositions: { summary: 0, transcript: 0 },
  noteStateByKnowledgeId: {},
  providerStatuses: {},
  providerConfig: {},
  deleteMode: false,
  selectedDeleteIds: new Set(),
  deleting: false,
  exportPreset: "full",
  exportSections: new Set(EXPORT_PRESETS.full),
  exportMarkdown: "",
  uiMode: "product",
};

const knowledgeCache = new Map();
let mediaController = null;
let toastTimer = 0;
let taskPoller = 0;
let activeSourceType = "url";
let lastSidebarTrigger = null;
let lastInspectorTrigger = null;
let pendingDuplicatePayload = null;

class MediaController {
  load(source) { this.source = source; }
  destroy() {}
  play() {}
  pause() {}
  seek() {}
  getCurrentTime() { return 0; }
  setPlaybackRate() {}
  setLoop() {}
  supportsSeek() { return false; }
  openExternally(seconds = 0) {
    const url = timestampLink(this.source?.canonical_url || this.source?.source_url || "", seconds);
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  }
  fullscreen() {}
}

class HtmlMediaController extends MediaController {
  constructor(element) {
    super();
    this.element = element;
  }
  destroy() { this.pause(); this.element.removeAttribute("src"); this.element.load(); }
  load() { this.element.load(); }
  play() { return this.element.play(); }
  pause() { this.element.pause(); }
  seek(seconds) { this.element.currentTime = Math.max(0, Math.min(seconds, this.element.duration || seconds)); }
  getCurrentTime() { return this.element.currentTime || 0; }
  setPlaybackRate(rate) { this.element.playbackRate = rate; }
  setLoop(value) { this.element.loop = value; }
  supportsSeek() { return true; }
  fullscreen() { this.element.requestFullscreen?.(); }
}

class LocalVideoController extends HtmlMediaController {}
class LocalAudioController extends HtmlMediaController {}

class ExternalLinkController extends MediaController {
  constructor(source) {
    super();
    this.load(source);
  }
  play() { showToast("在线视频预览未嵌入，请在原网站播放"); }
  seek() {}
  getCurrentTime() { return state.currentTime; }
  setPlaybackRate() {}
  fullscreen() {}
}

class YouTubeMediaController extends MediaController {
  constructor(element, videoId, source, onFallback) {
    super();
    this.load(source);
    this.element = element;
    this.ready = false;
    this.player = null;
    this.timer = 0;
    loadYouTubeApi().then(() => {
      if (!element.isConnected || state.activeSource?.media?.embed?.videoId !== videoId) return;
      this.player = new window.YT.Player(element, {
        videoId,
        playerVars: { playsinline: 1, rel: 0 },
        events: {
          onReady: () => {
            this.ready = true;
            this.timer = window.setInterval(() => {
              state.currentTime = this.getCurrentTime();
              updateTimeDisplay();
              updateActiveChapter();
            }, 500);
            updateTimeDisplay();
          },
          onStateChange: (event) => setPlayIcon(event.data === window.YT.PlayerState.PLAYING),
          onError: () => onFallback("YouTube 视频不允许嵌入"),
        },
      });
    }).catch(() => onFallback("YouTube 播放器加载失败"));
  }
  destroy() { window.clearInterval(this.timer); this.ready = false; this.player?.destroy?.(); this.player = null; }
  play() { if (this.ready) this.player.playVideo(); }
  pause() { if (this.ready) this.player.pauseVideo(); }
  seek(seconds) {
    state.currentTime = Math.max(0, seconds);
    if (this.ready) {
      this.player.seekTo(state.currentTime, true);
      this.player.playVideo();
    }
  }
  getCurrentTime() { return this.ready ? Number(this.player.getCurrentTime() || 0) : state.currentTime; }
  setPlaybackRate(rate) { if (this.ready) this.player.setPlaybackRate(rate); }
  supportsSeek() { return true; }
  fullscreen() { this.player?.getIframe?.().requestFullscreen?.(); }
}

class BilibiliEmbedController extends MediaController {
  constructor(element, videoId, source, embedUrl) { super(); this.element = element; this.videoId = videoId; this.embedUrl = embedUrl; this.load(source); }
  destroy() { this.element.src = "about:blank"; }
  play() { showToast("请在播放器内点击播放"); }
  seek(seconds) {
    state.currentTime = Math.max(0, Number(seconds) || 0);
    const url = new URL(this.embedUrl, window.location.href);
    url.searchParams.set("bvid", this.videoId);
    url.searchParams.set("t", String(Math.floor(state.currentTime)));
    this.element.src = url.toString();
  }
  getCurrentTime() { return state.currentTime; }
  supportsSeek() { return true; }
  fullscreen() { this.element.requestFullscreen?.(); }
}

let youtubeApiPromise = null;
function loadYouTubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (youtubeApiPromise) return youtubeApiPromise;
  youtubeApiPromise = new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { previous?.(); resolve(window.YT); };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.onerror = reject;
    document.head.appendChild(script);
  });
  return youtubeApiPromise;
}

function currentChatHistory() {
  if (!state.selectedKnowledgeId) return [];
  return currentChatState().messages;
}

function currentChatState() {
  const id = state.selectedKnowledgeId;
  if (!id) return { messages: [], draft: "", loading: false, controller: null, provider: "auto" };
  return state.chatStateByKnowledgeId[id] || (state.chatStateByKnowledgeId[id] = {
    messages: [], draft: "", loading: false, controller: null, provider: "auto", loaded: false,
  });
}

function currentNoteState(knowledgeId = state.selectedKnowledgeId) {
  if (!knowledgeId) return { content: "", revision: "", loaded: false, dirty: false, saving: false, timer: 0 };
  return state.noteStateByKnowledgeId[knowledgeId] || (state.noteStateByKnowledgeId[knowledgeId] = {
    content: "",
    revision: "",
    updatedAt: "",
    loaded: false,
    loading: false,
    dirty: false,
    saving: false,
    timer: 0,
    savePromise: null,
    error: "",
  });
}

document.addEventListener("DOMContentLoaded", init);

async function init() {
  applyPersistedLayout();
  bindEvents();
  updateAnalysisModeDescriptions();
  syncShellAccessibility();
  requestAnimationFrame(reconcileLayoutWidths);
  loadRuntimeInfo();
  loadProviderStatuses();
  loadProviderConfig();
  setResultTab(state.activeResultTab, false);
  $("#followPlayback").checked = state.transcriptFollowMode;
  $("#footerFollow").checked = state.transcriptFollowMode;
  await refreshLibrary();
}

async function loadRuntimeInfo() {
  try {
    const runtime = await api("/api/runtime");
    state.uiMode = runtime.uiMode === "diagnostic" ? "diagnostic" : "product";
    document.body.dataset.uiMode = state.uiMode;
    const diagnostic = state.uiMode === "diagnostic";
    [$("#taskRuntime"), $("#settingsRuntime"), $("#taskCapabilities")].forEach((element) => {
      element.classList.toggle("hidden", !diagnostic);
    });
    const toolLines = (runtime.tools || []).map((tool) => (
      `${tool.name}: ${tool.available ? `${tool.path} (${tool.source})` : "未配置或未发现"}`
    ));
    const providerLines = (runtime.providers || []).map((provider) => (
      `${provider.name}: ${provider.model} (${provider.configured ? "已配置" : "未配置 Key"})`
    ));
    const text = [
      runtime.inProjectVenv ? "项目虚拟环境" : "非项目虚拟环境",
      runtime.pythonExecutable,
      ...toolLines,
      ...providerLines,
      runtime.warning || "",
    ].filter(Boolean).join("\n");
    [$("#taskRuntime"), $("#settingsRuntime")].forEach((element) => {
      element.textContent = text;
      const missingRequiredRuntime = (runtime.tools || []).some((tool) => !tool.available);
      element.classList.toggle("warning", !runtime.inProjectVenv || missingRequiredRuntime);
    });
  } catch (error) {
    state.uiMode = "product";
    [$("#taskRuntime"), $("#settingsRuntime")].forEach((element) => {
      element.classList.add("hidden");
      element.textContent = `运行环境读取失败：${error.message}`;
      element.classList.add("warning");
    });
  }
}

function applyPersistedLayout() {
  applyModuleOrder();
  Object.entries(state.moduleWidths).forEach(([module, width]) => {
    const element = $(`[data-module="${module}"]`);
    if (element && Number(width) > 0) element.style.flexBasis = `${Number(width)}px`;
  });
}

function bindEvents() {
  bindSegmentedControls();
  $("#newSummary").addEventListener("click", openNewTask);
  $("#refreshJobs").addEventListener("click", loadJobHistory);
  $("#focusSearch").addEventListener("click", focusSidebarSearch);
  $("#librarySearch").addEventListener("input", renderLibrary);
  $("#refreshLibrary").addEventListener("click", refreshLibrary);
  $("#toggleDeleteMode").addEventListener("click", handleDeleteAction);
  $("#confirmDeleteKnowledge").addEventListener("click", confirmDeleteKnowledge);
  $("#reloadKnowledge").addEventListener("click", () => state.selectedKnowledgeId && loadKnowledge(state.selectedKnowledgeId, true));
  $("#toggleSidebar").addEventListener("click", (event) => toggleSidebar(event.currentTarget));
  $("#collapseSidebar").addEventListener("click", () => closeSidebar(true));
  $("#toggleInspector").addEventListener("click", (event) => toggleInspector(event.currentTarget));
  $("#closeInspector").addEventListener("click", () => closeInspector(true));
  $("#drawerScrim").addEventListener("click", () => closeActiveSheet(true));
  $("#summarySettings").addEventListener("click", () => $("#settingsDialog").showModal());
  $("#taskMode").addEventListener("change", updateAnalysisModeDescriptions);
  $("#taskProcessingProfile").addEventListener("change", updateAnalysisModeDescriptions);
  $("#settingsMode").addEventListener("change", updateAnalysisModeDescriptions);
  $("#apiSettings").addEventListener("click", openApiConfig);
  $("#layoutSettings").addEventListener("click", openLayoutSettings);
  $("#openExternal").addEventListener("click", openOriginal);
  $("#downloadSource").addEventListener("click", () => downloadFile("index.md"));
  $("#copyResult").addEventListener("click", copyCurrentResult);
  $("#downloadResult").addEventListener("click", () => downloadFile(state.activeResultTab === "summary" ? "index.md" : "transcript.grouped.md"));
  $("#exportResult").addEventListener("click", openKnowledgeExport);
  $("#previewKnowledgeExport").addEventListener("click", previewKnowledgeExport);
  $("#downloadKnowledgeExport").addEventListener("click", downloadKnowledgeExport);
  $("#copyKnowledgeExport").addEventListener("click", copyKnowledgeExport);
  $("#vaultKnowledgeExport").addEventListener("click", saveKnowledgeExportToVault);
  $$('[data-export-preset]').forEach((button) => button.addEventListener("click", () => setExportPreset(button.dataset.exportPreset)));
  $("#retryAnalysis").addEventListener("click", retryAnalysis);
  $("#chapterDirectory").addEventListener("click", () => $(".chapter", $("#summaryView"))?.scrollIntoView({ behavior: uiScrollBehavior() }));
  $("#readTranscript").addEventListener("click", () => setResultTab(state.activeResultTab === "summary" ? "transcript" : "summary"));
  $("#backToTop").addEventListener("click", () => $("#resultScroll").scrollTo({ top: 0, behavior: uiScrollBehavior() }));
  $("#transcriptSearch").addEventListener("input", renderTranscriptGroups);
  $("#sendChat").addEventListener("click", sendChat);
  $("#clearChat").addEventListener("click", clearCurrentChat);
  $("#chatProvider").addEventListener("change", (event) => {
    currentChatState().provider = event.target.value;
    renderProviderStatus();
  });
  $("#chatInput").addEventListener("input", (event) => currentChatState().draft = event.target.value);
  $("#chatInput").addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); sendChat(); }
  });
  $$("[data-toggle-secret]").forEach((button) => button.addEventListener("click", () => toggleSecretField(button.dataset.toggleSecret, button)));
  $$("[data-provider-apply]").forEach((button) => button.addEventListener("click", () => applyApiProviderConfig(button.dataset.providerApply)));
  $$("[data-provider-test]").forEach((button) => button.addEventListener("click", () => testApiProviderConfig(button.dataset.providerTest)));
  $$("[data-provider-clear]").forEach((button) => button.addEventListener("click", () => clearApiProviderConfig(button.dataset.providerClear)));
  $("#expandChat").addEventListener("click", (event) => { openInspector(event.currentTarget); $("#chatPane").scrollIntoView({ behavior: uiScrollBehavior(), block: "start" }); });
  $("#playbackRate").addEventListener("change", (event) => setPlaybackRate(Number(event.target.value)));
  $("#videoAspectRatio").addEventListener("change", applyLocalVideoDisplay);
  $("#videoObjectFit").addEventListener("change", applyLocalVideoDisplay);
  $("#followPlayback").addEventListener("change", (event) => setFollowMode(event.target.checked));
  $("#footerFollow").addEventListener("change", (event) => setFollowMode(event.target.checked));
  $("#resultScroll").addEventListener("scroll", () => state.scrollPositions[state.activeResultTab] = $("#resultScroll").scrollTop, { passive: true });

  $$("[data-result-tab]").forEach((button) => button.addEventListener("click", () => setResultTab(button.dataset.resultTab)));
  $$("[data-insight-tab]").forEach((button) => button.addEventListener("click", () => setInsightTab(button.dataset.insightTab)));
  $$("[data-mobile-tab]").forEach((button) => button.addEventListener("click", () => setMobileView(button.dataset.mobileTab)));
  $(".mobile-tabs").addEventListener("keydown", handleWorkspaceTabKeydown);
  $$("[data-media]").forEach((button) => button.addEventListener("click", () => handleMediaAction(button.dataset.media)));
  $$("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  $$("[data-filter]").forEach((button) => button.addEventListener("click", () => setLibraryFilter(button.dataset.filter, button)));
  $$("[data-source-type]").forEach((button) => button.addEventListener("click", () => setTaskSourceType(button.dataset.sourceType)));
  $("#taskDuplicateActions").addEventListener("click", handleDuplicateAction);

  $("#libraryList").addEventListener("click", (event) => {
    const item = event.target.closest("[data-knowledge-id]");
    if (!item) return;
    if (state.deleteMode) toggleKnowledgeDeleteSelection(item.dataset.knowledgeId);
    else loadKnowledge(item.dataset.knowledgeId);
  });
  $("#summaryView").addEventListener("click", handleResultClick);
  $("#transcriptGroups").addEventListener("click", handleTranscriptClick);
  $("#questionChips").addEventListener("click", (event) => {
    const button = event.target.closest("[data-question]");
    if (button) focusChatQuestion(button.dataset.question);
  });
  $("#insightContent").addEventListener("click", (event) => {
    const target = event.target.closest("[data-seek]");
    if (target) { event.preventDefault(); seekPreview(Number(target.dataset.seek)); }
  });
  $("#chatHistory").addEventListener("click", (event) => {
    const target = event.target.closest("[data-seek]");
    if (target) { event.preventDefault(); seekPreview(Number(target.dataset.seek)); }
    if (event.target.closest("[data-regenerate]")) regenerateLastAnswer();
  });
  $("#noteEditor").addEventListener("input", saveNoteDraft);
  $("#insertTimestamp").addEventListener("click", insertNoteTimestamp);
  $$('[id^="layoutPosition"]').forEach((select) => select.addEventListener("change", updateLayoutFromControls));
  $$(".nav-groups details").forEach((details) => details.addEventListener("toggle", () => {
    $("summary", details)?.setAttribute("aria-expanded", String(details.open));
  }));
  $("#resetLayout").addEventListener("click", resetWorkspaceLayout);
  $("#newTaskForm").addEventListener("submit", submitTask);
  $("#taskSource").addEventListener("invalid", () => setTaskSourceError(true));
  $("#taskSource").addEventListener("input", () => {
    if ($("#taskSource").validity.valid) setTaskSourceError(false);
  });
  $("#paneResizer").addEventListener("pointerdown", startResize);
  $("#rightPaneResizer").addEventListener("pointerdown", startResize);
  $$(".pane-resizer").forEach((resizer) => {
    resizer.addEventListener("dblclick", resetModuleWidths);
    resizer.addEventListener("keydown", handleDividerKeydown);
  });
  document.addEventListener("keydown", handleKeyboard);
  window.addEventListener("hashchange", selectFromHash);
  window.addEventListener("resize", handleViewportChange);
  window.addEventListener("beforeunload", () => {
    clearInterval(taskPoller);
    flushPendingNotesOnUnload();
  });
}

function bindSegmentedControls() {
  $$('[data-segmented-control]').forEach((control) => {
    control.addEventListener("keydown", handleSegmentedControlKeydown);
  });
}

function handleSegmentedControlKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const options = $$('[role="radio"]:not(:disabled)', event.currentTarget);
  if (!options.length) return;
  const currentIndex = Math.max(0, options.indexOf(document.activeElement));
  let nextIndex = currentIndex;
  if (event.key === "Home") nextIndex = 0;
  else if (event.key === "End") nextIndex = options.length - 1;
  else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + options.length) % options.length;
  else nextIndex = (currentIndex + 1) % options.length;
  event.preventDefault();
  options[nextIndex].focus();
  options[nextIndex].click();
}

function handleWorkspaceTabKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const tabs = $$("[data-mobile-tab]", event.currentTarget);
  const current = Math.max(0, tabs.indexOf(document.activeElement));
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  tabs[next].click();
  tabs[next].focus();
}

function setTaskSourceError(invalid) {
  const input = $("#taskSource");
  const field = $("#taskSourceField");
  const error = $("#taskSourceError");
  field.dataset.invalid = String(invalid);
  input.setAttribute("aria-invalid", String(invalid));
  input.setAttribute("aria-describedby", invalid ? "taskSourceDescription taskSourceError" : "taskSourceDescription");
  error.hidden = !invalid;
}

function setTaskButtonLoading(loading) {
  const button = $("#startTask");
  button.disabled = loading;
  button.setAttribute("aria-busy", String(loading));
  button.textContent = loading ? "正在处理…" : "开始处理";
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const error = new Error(data?.error || `请求失败：${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

async function loadProviderStatuses() {
  try {
    const data = await api("/api/providers");
    state.providerStatuses = providerStateEntries(data.providers || []);
  } catch (error) {
    state.providerStatuses = {};
  }
  renderProviderStatus();
}

async function loadProviderConfig() {
  try {
    const data = await api("/api/provider-config");
    state.providerConfig = providerStateEntries(data.providers || []);
    renderApiConfig();
  } catch (error) {
    state.providerConfig = {};
    renderApiConfigError(error.message);
  }
}

function openApiConfig() {
  loadProviderConfig();
  $("#apiConfigDialog").showModal();
}

function renderApiConfig() {
  ["deepseek", "gemini", "groq"].forEach(renderOneApiProvider);
}

function renderApiConfigError(message) {
  ["deepseek", "gemini", "groq"].forEach((provider) => {
    const result = $(`#${provider}TestResult`);
    if (result) {
      result.className = "api-test-result failed";
      result.textContent = `配置状态读取失败：${message}`;
    }
  });
}

function renderOneApiProvider(provider) {
  const config = state.providerConfig[provider] || {};
  const status = $(`#${provider}ConfigStatus`);
  const keyHint = $(`#${provider}KeyHint`);
  const testResult = $(`#${provider}TestResult`);
  if (!status || !keyHint || !testResult) return;
  const tested = config.lastTest || {};
  const statusText = !config.configured ? "未配置" : tested.ok === true ? "测试成功" : tested.ok === false ? "测试失败" : "已配置未测试";
  status.textContent = state.uiMode === "diagnostic"
    ? `${statusText} · ${sourceLabel(config.keySource)} · ${config.model || ""}`.trim()
    : statusText;
  keyHint.textContent = config.configured
    ? "凭据已配置；出于安全考虑不会返回或显示其内容。"
    : "尚未配置凭据，可填写后应用。";
  if (provider === "deepseek") {
    $("#deepseekBaseUrl").value = config.baseUrl || "https://api.deepseek.com";
    $("#deepseekModel").value = config.model || "deepseek-v4-flash";
    $("#deepseekApiKey").value = "";
  } else if (provider === "groq") {
    $("#groqModel").value = config.model || "whisper-large-v3-turbo";
    $("#groqApiKey").value = "";
  } else {
    $("#geminiModel").value = config.model || "gemini-3.1-flash-lite";
    $("#geminiApiKey").value = "";
  }
  if (tested.ok === true) {
    testResult.className = "api-test-result success";
    testResult.textContent = state.uiMode === "diagnostic"
      ? `最近测试成功：${tested.model || config.model || ""}，${tested.durationMs ?? 0} ms。`
      : "最近测试成功。";
  } else if (tested.ok === false) {
    testResult.className = "api-test-result failed";
    testResult.textContent = `最近测试失败：${tested.error || "请检查配置。"}（${tested.errorType || "provider_error"}）`;
  } else {
    testResult.className = "api-test-result";
    testResult.textContent = "尚未测试当前配置。";
  }
}

function collectProviderConfig(provider, includeEmptyKey = false) {
  const payload = { provider };
  if (provider === "deepseek") {
    const key = $("#deepseekApiKey").value;
    if (key || includeEmptyKey) payload.apiKey = key;
    payload.baseUrl = $("#deepseekBaseUrl").value.trim();
    payload.model = $("#deepseekModel").value.trim();
  } else if (provider === "groq") {
    const key = $("#groqApiKey").value;
    if (key || includeEmptyKey) payload.apiKey = key;
    payload.model = $("#groqModel").value.trim();
  } else {
    const key = $("#geminiApiKey").value;
    if (key || includeEmptyKey) payload.apiKey = key;
    payload.model = $("#geminiModel").value.trim();
  }
  return payload;
}

async function applyApiProviderConfig(provider) {
  try {
    const data = await api("/api/provider-config", {
      method: "POST",
      body: JSON.stringify(collectProviderConfig(provider)),
    });
    updateProviderConfigState(data);
    showToast(`${providerLabel(provider)} 配置已应用`);
  } catch (error) {
    showToast(error.message);
  }
}

async function testApiProviderConfig(provider) {
  const result = $(`#${provider}TestResult`);
  result.className = "api-test-result";
  result.textContent = "正在测试连接…";
  try {
    const data = await api("/api/provider-config/test", {
      method: "POST",
      body: JSON.stringify(collectProviderConfig(provider, true)),
    });
    updateProviderConfigState(data);
  } catch (error) {
    result.className = "api-test-result failed";
    result.textContent = `测试失败：${error.message}`;
  }
}

async function clearApiProviderConfig(provider) {
  try {
    const data = await api(`/api/provider-config/${encodeURIComponent(provider)}`, { method: "DELETE" });
    updateProviderConfigState(data);
    showToast(`${providerLabel(provider)} Web 会话配置已清除`);
  } catch (error) {
    showToast(error.message);
  }
}

function updateProviderConfigState(data) {
  state.providerConfig = providerStateEntries(data.providers || []);
  state.providerStatuses = providerStateEntries(data.providers || []);
  renderApiConfig();
  renderProviderStatus();
  loadRuntimeInfo();
}

function providerStateEntries(items) {
  const serviceToProvider = {
    analysis_text: "deepseek",
    visual_understanding: "gemini",
    cloud_transcription: "groq",
  };
  return Object.fromEntries(items.map((item) => [
    serviceToProvider[item.service] || item.provider || item.name,
    item,
  ]));
}

function toggleSecretField(id, button) {
  const input = $(`#${id}`);
  if (!input) return;
  const visible = input.type === "text";
  input.type = visible ? "password" : "text";
  button.textContent = visible ? "显示" : "隐藏";
}

function sourceLabel(source) {
  return ({ web_session: "Web 会话", environment: "环境变量", default: "默认值", missing: "未配置" })[source] || source || "未知来源";
}

function renderProviderStatus() {
  const chatState = currentChatState();
  const selected = chatState.provider || "auto";
  const status = selected === "auto" ? null : state.providerStatuses[selected];
  $("#chatProvider").value = selected;
  const configured = selected === "auto" ? Object.values(state.providerStatuses).some((item) => item.configured) : Boolean(status?.configured);
  $("#chatProviderDot").className = configured ? "available-dot" : "unavailable-dot";
  $("#chatProviderStatus").textContent = selected === "auto" ? "自动路由" : (configured ? "已配置" : "未配置");
  $("#chatModelLabel").textContent = status?.model || "当前视频字幕";
  $("#sendChat").disabled = chatState.loading || !configured;
  $("#sendChat").title = configured ? "发送问题" : `${selected === "gemini" ? "Gemini" : "模型"} 未配置`;
}

async function refreshLibrary() {
  const list = $("#libraryList");
  list.innerHTML = '<div class="loading-list">正在读取知识记录…</div>';
  try {
    const data = await api("/api/library");
    state.libraryItems = data.items || [];
    const availableIds = new Set(state.libraryItems.map((item) => item.id));
    state.selectedDeleteIds = new Set([...state.selectedDeleteIds].filter((id) => availableIds.has(id)));
    updateLibraryCounts();
    renderLibrary();
    if (!state.selectedKnowledgeId && state.libraryItems.length) {
      const hashId = decodeHashId();
      const preferred = state.libraryItems.find((item) => item.id === hashId)
        || state.libraryItems.find((item) => item.sourceType === "local_video" && item.status.startsWith("completed"))
        || state.libraryItems[0];
      await loadKnowledge(preferred.id);
    }
  } catch (error) {
    list.innerHTML = `<div class="library-empty">记录加载失败<br>${escapeHtml(error.message)}</div>`;
  }
}

function renderLibrary() {
  const query = $("#librarySearch").value.trim().toLowerCase();
  const items = state.libraryItems.filter((item) => {
    const searchMatch = !query || `${item.title} ${item.author} ${item.platform}`.toLowerCase().includes(query);
    const status = item.status || "";
    const filterMatch = state.filter === "all"
      || (state.filter === "video" && ["local_video", "online_video"].includes(item.sourceType))
      || (state.filter === "processing" && ["created", "running", "processing"].includes(status))
      || (state.filter === "completed" && status.startsWith("completed"));
    return searchMatch && filterMatch;
  });
  const list = $("#libraryList");
  if (!items.length) {
    list.innerHTML = '<div class="library-empty">暂无处理记录<br><button class="quiet-button" data-empty-new>新总结</button></div>';
    $("[data-empty-new]", list)?.addEventListener("click", openNewTask);
    updateDeleteAction();
    return;
  }
  list.innerHTML = items.map((item) => {
    const deleteSelected = state.selectedDeleteIds.has(item.id);
    const leading = state.deleteMode
      ? `<span class="record-selector ${deleteSelected ? "selected" : ""}" aria-hidden="true">${deleteSelected ? '<svg><use href="#i-check"/></svg>' : ""}</span>`
      : `<span class="record-icon"><svg><use href="#${item.sourceType === "web_page" ? "i-file" : "i-video"}"/></svg></span>`;
    return `
    <button class="library-item ${!state.deleteMode && item.id === state.selectedKnowledgeId ? "active" : ""} ${deleteSelected ? "delete-selected" : ""}" data-knowledge-id="${escapeAttr(item.id)}" aria-current="${!state.deleteMode && item.id === state.selectedKnowledgeId ? "true" : "false"}" ${state.deleteMode ? `aria-pressed="${deleteSelected ? "true" : "false"}"` : ""}>
      ${leading}
      <span class="record-copy">
        <strong>${escapeHtml(item.title)}</strong>
        <small>${escapeHtml(platformLabel(item.platform))} · ${formatRelativeDate(item.updatedAt)}</small>
        ${item.processingDurationMs != null ? `<small class="record-processing-time" data-processing-duration="${Number(item.processingDurationMs) || 0}" data-processing-started-at="${Number(item.processingStartedAt) || 0}" data-processing-live="${item.processingTimingLive ? "true" : "false"}">${item.processingTimingLive ? "处理中" : "耗时"} ${formatProcessingDuration(item.processingDurationMs)}</small>` : ""}
      </span>
      <span class="record-state ${escapeAttr(item.status)}" aria-label="${escapeAttr(statusLabel(item.status))}"></span>
    </button>`;
  }).join("");
  updateProcessingTimers();
  updateDeleteAction();
}

function updateLibraryCounts() {
  $("#countAll").textContent = state.libraryItems.length;
  $("#countVideo").textContent = state.libraryItems.filter((item) => ["local_video", "online_video"].includes(item.sourceType)).length;
  $("#countProcessing").textContent = state.libraryItems.filter((item) => ["created", "running", "processing"].includes(item.status)).length;
  $("#countCompleted").textContent = state.libraryItems.filter((item) => (item.status || "").startsWith("completed")).length;
}

async function loadKnowledge(id, force = false) {
  if (!id) return;
  if (state.selectedKnowledgeId && state.selectedKnowledgeId !== id) {
    await flushNoteSave(state.selectedKnowledgeId);
    const previousChat = currentChatState();
    previousChat.draft = $("#chatInput")?.value || previousChat.draft;
    previousChat.controller?.abort();
    previousChat.loading = false;
    mediaController?.destroy();
    mediaController = null;
  }
  state.selectedKnowledgeId = id;
  state.loading = true;
  renderLibrary();
  setLoadingState();
  if (!isWideShell()) closeSidebar(false);
  try {
    let knowledge = force ? null : knowledgeCache.get(id);
    if (!knowledge) {
      const data = await api(`/api/library/${encodeURIComponent(id)}`);
      knowledge = data.knowledge;
      knowledgeCache.set(id, knowledge);
    }
    state.activeSource = knowledge;
    state.currentTime = 0;
    state.currentChapter = -1;
    if (state.transcriptLoadedFor !== id) {
      state.transcriptGroups = [];
      state.transcriptLoadedFor = "";
    }
    history.replaceState(null, "", `#/knowledge/${encodeURIComponent(id)}`);
    renderKnowledge(knowledge);
    await Promise.all([loadChatHistory(id), loadNote(id, force)]);
    if (state.activeResultTab === "transcript") await ensureTranscriptLoaded();
  } catch (error) {
    state.error = error.message;
    renderLoadError(error.message);
  } finally {
    state.loading = false;
  }
}

function renderKnowledge(knowledge) {
  renderMedia(knowledge);
  renderSourceInfo(knowledge);
  renderStatus(knowledge);
  renderSummary(knowledge);
  renderInsightPanel(knowledge);
  renderQuestionChips(knowledge.analysis?.thoughts || []);
  renderChatHistory();
  renderNoteState(knowledge.id);
  $("#workspaceTitle").textContent = knowledge.source?.title || knowledge.id || "视频知识工作台";
  const model = knowledge.manifest?.llm_model || knowledge.analysis?.model || "";
  const provider = knowledge.manifest?.llm_provider || knowledge.analysis?.provider || "";
  $("#modelBadge").textContent = model
    ? `${providerLabel(provider)} · ${model}`
    : knowledge.analysisReady ? "AI 分析已完成" : "未运行 AI 分析";
  $("#modelBadge").title = model ? `本知识包实际使用模型：${model}` : $("#modelBadge").textContent;
  $("#chapterCount").textContent = (knowledge.analysis?.chapters?.length || knowledge.timeline?.length || 0);
  renderAnalysisRetry(knowledge);
  renderLibrary();
}

function handleDeleteAction() {
  if (!state.deleteMode) {
    if (!state.libraryItems.length) { showToast("没有可删除的知识记录"); return; }
    state.deleteMode = true;
    state.selectedDeleteIds.clear();
    renderLibrary();
    return;
  }
  if (!state.selectedDeleteIds.size) {
    setDeleteMode(false);
    return;
  }
  openDeleteConfirmation();
}

function setDeleteMode(enabled) {
  state.deleteMode = enabled;
  if (!enabled) state.selectedDeleteIds.clear();
  renderLibrary();
}

function toggleKnowledgeDeleteSelection(knowledgeId) {
  if (state.selectedDeleteIds.has(knowledgeId)) state.selectedDeleteIds.delete(knowledgeId);
  else state.selectedDeleteIds.add(knowledgeId);
  renderLibrary();
}

function updateDeleteAction() {
  const button = $("#toggleDeleteMode");
  if (!button) return;
  const count = state.selectedDeleteIds.size;
  const confirming = state.deleteMode && count > 0;
  $("#deleteActionIcon")?.setAttribute("href", confirming ? "#i-check" : "#i-trash");
  $("#recordHeadingLabel").textContent = state.deleteMode ? `已选择 ${count} 项` : "知识记录";
  button.classList.toggle("delete-confirm-action", confirming);
  button.disabled = state.deleting || (!state.deleteMode && !state.libraryItems.length);
  const label = confirming ? `确认删除已选择的 ${count} 条记录` : (state.deleteMode ? "退出删除模式" : "选择要删除的记录");
  button.title = label;
  button.setAttribute("aria-label", label);
}

function openDeleteConfirmation() {
  const selectedItems = state.libraryItems.filter((item) => state.selectedDeleteIds.has(item.id));
  if (!selectedItems.length) return;
  $("#deleteConfirmSummary").textContent = `即将永久删除 ${selectedItems.length} 条知识记录：`;
  $("#deleteConfirmList").innerHTML = selectedItems.map((item) => `<li>${escapeHtml(item.title || item.id)}</li>`).join("");
  $("#deleteKnowledgeDialog").showModal();
}

async function confirmDeleteKnowledge() {
  const knowledgeIds = [...state.selectedDeleteIds];
  if (!knowledgeIds.length || state.deleting) return;
  state.deleting = true;
  const button = $("#confirmDeleteKnowledge");
  button.disabled = true;
  button.textContent = "正在删除…";
  updateDeleteAction();
  try {
    await Promise.all(knowledgeIds.map((id) => flushNoteSave(id)));
    const data = await api("/api/library", {
      method: "DELETE",
      body: JSON.stringify({ knowledge_ids: knowledgeIds }),
    });
    knowledgeIds.forEach((id) => {
      knowledgeCache.delete(id);
      delete state.chatStateByKnowledgeId[id];
      delete state.noteStateByKnowledgeId[id];
    });
    $("#deleteKnowledgeDialog").close();
    if (knowledgeIds.includes(state.selectedKnowledgeId)) history.replaceState(null, "", location.pathname);
    showToast(`已删除 ${data.count || knowledgeIds.length} 条知识记录`);
    window.setTimeout(() => window.location.reload(), 450);
  } catch (error) {
    showToast(`删除失败：${error.message}`);
  } finally {
    state.deleting = false;
    button.disabled = false;
    button.textContent = "确认永久删除";
    updateDeleteAction();
  }
}

function openKnowledgeExport() {
  if (!state.selectedKnowledgeId) { showToast("请先选择知识记录"); return; }
  renderExportSections();
  $("#exportKnowledgeDialog").showModal();
  previewKnowledgeExport();
}

function setExportPreset(preset) {
  state.exportPreset = EXPORT_PRESETS[preset] ? preset : "full";
  state.exportSections = new Set(EXPORT_PRESETS[state.exportPreset]);
  $$('[data-export-preset]').forEach((button) => button.classList.toggle("active", button.dataset.exportPreset === state.exportPreset));
  renderExportSections();
  previewKnowledgeExport();
}

function renderExportSections() {
  const root = $("#exportSections");
  root.innerHTML = Object.entries(EXPORT_SECTION_LABELS).map(([key, label]) => `<label><input type="checkbox" data-export-section="${key}" ${state.exportSections.has(key) ? "checked" : ""}>${label}</label>`).join("");
  $$('[data-export-section]', root).forEach((input) => input.addEventListener("change", () => {
    if (input.checked) state.exportSections.add(input.dataset.exportSection); else state.exportSections.delete(input.dataset.exportSection);
    state.exportPreset = "custom";
    $$('[data-export-preset]').forEach((button) => button.classList.remove("active"));
  }));
}

function exportRequest(destination) {
  return { preset: state.exportPreset === "custom" ? "full" : state.exportPreset, sections: [...state.exportSections], order: [...state.exportSections], destination };
}

async function previewKnowledgeExport() {
  if (!state.selectedKnowledgeId || !state.exportSections.size) return;
  $("#exportMarkdownPreview").textContent = "正在生成预览…";
  try {
    const data = await api(`/api/knowledge/${encodeURIComponent(state.selectedKnowledgeId)}/export`, { method: "POST", body: JSON.stringify(exportRequest("preview")) });
    state.exportMarkdown = data.markdown || "";
    $("#exportMarkdownPreview").textContent = state.exportMarkdown || "没有可导出的内容。";
  } catch (error) { $("#exportMarkdownPreview").textContent = `预览失败：${error.message}`; }
}

async function downloadKnowledgeExport() {
  const response = await fetch(`/api/knowledge/${encodeURIComponent(state.selectedKnowledgeId)}/export`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(exportRequest("download")) });
  if (!response.ok) { const data = await response.json(); showToast(`下载失败：${data.error || response.status}`); return; }
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "video-note.md"; anchor.click(); URL.revokeObjectURL(url);
}

async function copyKnowledgeExport() { if (!state.exportMarkdown) await previewKnowledgeExport(); if (state.exportMarkdown) copyText(state.exportMarkdown); }

async function saveKnowledgeExportToVault() {
  try {
    const data = await api(`/api/knowledge/${encodeURIComponent(state.selectedKnowledgeId)}/export`, { method: "POST", body: JSON.stringify(exportRequest("obsidian-open")) });
    $("#exportVaultState").textContent = `已保存：${data.relative_vault_path}`;
    if (data.obsidian_uri) window.location.href = data.obsidian_uri;
  } catch (error) { $("#exportVaultState").textContent = `保存失败：${error.message}`; }
}

function renderAnalysisRetry(knowledge) {
  const button = $("#retryAnalysis");
  const canAnalyze = Boolean(knowledge.transcriptReady) && !Boolean(knowledge.analysisReady);
  button.classList.toggle("hidden", !canAnalyze);
  button.disabled = !canAnalyze;
  button.removeAttribute("aria-busy");
}

async function retryAnalysis() {
  const knowledgeId = state.selectedKnowledgeId;
  if (!knowledgeId) return;
  const button = $("#retryAnalysis");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.title = "正在运行 AI 分析";
  showToast("正在复用已有字幕，仅重新执行 AI 分析…");
  try {
    const data = await api(`/api/library/${encodeURIComponent(knowledgeId)}/analysis/retry`, {
      method: "POST",
      body: "{}",
    });
    knowledgeCache.set(knowledgeId, data.knowledge);
    state.activeSource = data.knowledge;
    renderKnowledge(data.knowledge);
    showToast("AI 分析已完成");
  } catch (error) {
    knowledgeCache.delete(knowledgeId);
    showToast(`AI 分析失败：${error.message}`);
    await loadKnowledge(knowledgeId, true);
  } finally {
    button.title = "仅运行 AI 分析";
    button.removeAttribute("aria-busy");
  }
}

function renderMedia(knowledge) {
  const surface = $("#mediaSurface");
  const media = knowledge.media || {};
  const savedRatio = localStorage.getItem(SETTINGS.videoAspectRatio);
  const savedFit = localStorage.getItem(SETTINGS.videoObjectFit);
  $("#videoAspectRatio").value = ["original", "16/9", "4/3", "1/1", "9/16"].includes(savedRatio) ? savedRatio : "original";
  $("#videoObjectFit").value = savedFit === "cover" ? "cover" : "contain";
  surface.className = "media-surface";
  surface.style.removeProperty("aspect-ratio");
  surface.innerHTML = "";
  if (media.kind === "video" && media.available) {
    const video = document.createElement("video");
    video.src = media.url;
    video.preload = "metadata";
    video.playsInline = true;
    video.addEventListener("timeupdate", throttle(handleTimeUpdate, 300));
    video.addEventListener("loadedmetadata", () => { updateTimeDisplay(); applyLocalVideoDisplay(); });
    video.addEventListener("play", () => setPlayIcon(true));
    video.addEventListener("pause", () => setPlayIcon(false));
    surface.appendChild(video);
    mediaController = new LocalVideoController(video);
  } else if (media.kind === "audio" && media.available) {
    surface.innerHTML = '<div class="audio-surface"><svg><use href="#i-file"/></svg></div>';
    const audio = document.createElement("audio");
    audio.src = media.url;
    audio.preload = "metadata";
    audio.controls = true;
    audio.addEventListener("timeupdate", throttle(handleTimeUpdate, 300));
    audio.addEventListener("loadedmetadata", updateTimeDisplay);
    $(".audio-surface", surface).appendChild(audio);
    mediaController = new LocalAudioController(audio);
  } else if (media.embed?.provider === "youtube" && media.embed.videoId) {
    const player = document.createElement("div");
    player.className = "official-player";
    surface.appendChild(player);
    mediaController = new YouTubeMediaController(player, media.embed.videoId, knowledge.source, (message) => {
      if (state.selectedKnowledgeId === knowledge.id) renderExternalMedia(surface, knowledge, message);
    });
  } else if (media.embed?.provider === "bilibili" && media.embed.videoId && isSafeHttpUrl(media.embed.url)) {
    const player = document.createElement("iframe");
    player.className = "official-player";
    player.src = media.embed.url;
    player.allow = "autoplay; fullscreen; picture-in-picture";
    player.allowFullscreen = true;
    player.referrerPolicy = "strict-origin-when-cross-origin";
    surface.appendChild(player);
    mediaController = new BilibiliEmbedController(player, media.embed.videoId, knowledge.source, media.embed.url);
  } else if (media.externalUrl) {
    renderExternalMedia(surface, knowledge);
  } else {
    surface.className = "media-surface empty-surface";
    surface.innerHTML = '<div class="media-empty"><svg><use href="#i-video"/></svg><p>当前记录没有可预览媒体</p></div>';
    mediaController = new MediaController();
  }
  syncMediaControls();
  setPlaybackRate(Number(localStorage.getItem(SETTINGS.playbackRate)) || 1);
  updateTimeDisplay();
}

function syncMediaControls() {
  const seekable = Boolean(mediaController?.supportsSeek());
  const htmlMedia = mediaController instanceof HtmlMediaController;
  const iframeMedia = mediaController instanceof YouTubeMediaController || mediaController instanceof BilibiliEmbedController;
  const externalOnly = mediaController instanceof ExternalLinkController;
  const embeddedBilibili = mediaController instanceof BilibiliEmbedController;
  $("#mediaControls").classList.toggle("hidden", externalOnly);
  $('[data-media="play"]').disabled = externalOnly || embeddedBilibili;
  $$('[data-media="back"], [data-media="forward"]').forEach((button) => button.disabled = externalOnly);
  $('[data-media="play"]').title = embeddedBilibili ? "请在 B站播放器内点击播放" : externalOnly ? "请打开原视频播放" : "";
  $("#playbackRate").disabled = !(htmlMedia || mediaController instanceof YouTubeMediaController);
  $('[data-media="repeat"]').disabled = !htmlMedia;
  $('[data-media="fullscreen"]').disabled = !(htmlMedia || iframeMedia);
  $("#localVideoDisplay").classList.toggle("hidden", !(mediaController instanceof LocalVideoController));
}

function applyLocalVideoDisplay() {
  if (!(mediaController instanceof LocalVideoController)) return;
  const video = mediaController.element;
  const ratioSetting = $("#videoAspectRatio").value;
  const fitSetting = $("#videoObjectFit").value === "cover" ? "cover" : "contain";
  const originalRatio = video.videoWidth > 0 && video.videoHeight > 0 ? video.videoWidth / video.videoHeight : 16 / 9;
  const selectedRatio = ratioSetting === "original" ? originalRatio : Number(ratioSetting.split("/")[0]) / Number(ratioSetting.split("/")[1]);
  const surface = $("#mediaSurface");
  surface.classList.add("local-video-surface");
  surface.style.aspectRatio = String(selectedRatio);
  surface.style.setProperty("--media-aspect", String(selectedRatio));
  video.style.objectFit = fitSetting;
  localStorage.setItem(SETTINGS.videoAspectRatio, ratioSetting);
  localStorage.setItem(SETTINGS.videoObjectFit, fitSetting);
}

function renderExternalMedia(surface, knowledge, message = "") {
  mediaController?.destroy();
  surface.innerHTML = "";
  const media = knowledge.media || {};
  const wrapper = document.createElement("div");
  wrapper.className = "external-media";
  if (isSafeHttpUrl(media.thumbnail)) {
    const image = document.createElement("img");
    image.className = "media-poster";
    image.alt = `${knowledge.source?.title || "在线视频"}封面`;
    image.src = media.thumbnail;
    image.referrerPolicy = "no-referrer";
    wrapper.appendChild(image);
  }
  const source = knowledge.source || {};
  const details = document.createElement("div");
  details.className = "external-details";
  const title = document.createElement("strong");
  title.textContent = source.title || "外部视频";
  details.appendChild(title);
  const meta = [
    source.author,
    Number(knowledge.duration || 0) > 0 ? formatTime(Number(knowledge.duration)) : "",
  ].filter(Boolean);
  if (meta.length) {
    const metaLine = document.createElement("span");
    metaLine.textContent = meta.join(" · ");
    details.appendChild(metaLine);
  }
  wrapper.appendChild(details);
  const externalMessage = message || (
    media.previewStatus === "external_only"
      ? "当前来源不支持工作台内播放，字幕、摘要和知识包功能不受影响。"
      : ""
  );
  if (externalMessage) {
    const notice = document.createElement("span");
    notice.className = "external-notice";
    notice.textContent = externalMessage;
    wrapper.appendChild(notice);
  }
  const button = document.createElement("button");
  button.className = "external-open";
  button.innerHTML = '<svg><use href="#i-external"/></svg><span>在原网站打开</span>';
  button.addEventListener("click", openOriginal);
  wrapper.appendChild(button);
  surface.appendChild(wrapper);
  mediaController = new ExternalLinkController(knowledge.source);
}

function renderSourceInfo(knowledge) {
  const source = knowledge.source || {};
  const external = source.canonical_url || source.source_url || "";
  const description = source.description || "";
  $("#sourceInfo").innerHTML = `
    <h1>${escapeHtml(source.title || knowledge.id)}</h1>
    <div class="source-meta">
      ${source.author ? `<span>${escapeHtml(source.author)}</span>` : ""}
      <span>${escapeHtml(platformLabel(source.platform))}</span>
      ${source.published_at ? `<span>${escapeHtml(formatPublished(source.published_at))}</span>` : ""}
      ${source.duration != null ? `<span>${formatTime(source.duration)}</span>` : ""}
      ${external && isSafeHttpUrl(external) ? `<a href="${escapeAttr(external)}" target="_blank" rel="noopener noreferrer">原链接</a>` : ""}
    </div>
    ${description ? `<details class="source-description"><summary>来源简介</summary><p>${escapeHtml(description)}</p></details>` : ""}`;
}

function renderStatus(knowledge) {
  const manifest = knowledge.manifest || {};
  const element = $("#processingStatus");
  const status = manifest.status || "unknown";
  const analysisStatus = knowledge.analysisStatus || manifest.analysis_status || knowledge.analysis?.status || "pending";
  const transcriptWithoutAnalysis = Boolean(knowledge.transcriptReady) && !Boolean(knowledge.analysisReady);
  let className = "";
  if (status === "completed") className = "success";
  else if (status === "completed_with_warnings") className = "warning";
  else if (status === "failed" || status === "invalid") className = "error";
  if (transcriptWithoutAnalysis) className = "warning";
  const errors = Array.isArray(manifest.errors) && manifest.errors.length ? ` · ${manifest.errors[0]}` : "";
  let label = statusLabel(status);
  if (transcriptWithoutAnalysis && analysisStatus === "skipped") label = "转写完成，AI 分析未运行";
  else if (transcriptWithoutAnalysis && analysisStatus === "timeout") label = "转写完成，AI 分析超时";
  else if (transcriptWithoutAnalysis && analysisStatus === "failed") label = "转写完成，AI 分析失败";
  const semanticClass = className === "success"
    ? "ui-inline-status--success"
    : className === "warning"
      ? "ui-inline-status--warning"
      : className === "error"
        ? "ui-inline-status--danger"
        : "";
  element.className = `processing-status ui-inline-status ${semanticClass}`.trim();
  element.innerHTML = `<svg><use href="#${className === "error" || className === "warning" || transcriptWithoutAnalysis ? "i-warning" : "i-check"}"/></svg><span>${escapeHtml(label)}${manifest.current_stage ? ` · ${escapeHtml(stageLabel(manifest.current_stage))}` : ""}${escapeHtml(errors)}</span>`;
}

function renderSummary(knowledge) {
  const analysis = knowledge.analysis || {};
  const timeline = Array.isArray(knowledge.timeline) ? knowledge.timeline : [];
  const sections = [];
  const profile = analysis.analysis_profile || "summary";
  const hasProfileDetails = profile !== "summary" && analysis.content && Object.keys(analysis.content).length;
  if (analysis.summary) sections.push(`<section class="result-section"><h2>摘要</h2><p>${escapeHtml(analysis.summary)}</p></section>`);
  else if (analysis.status === "timeout") sections.push(`<div class="analysis-empty">AI 分析超时：${escapeHtml(analysis.error || "请求超过时限，请稍后仅运行 AI 分析。")} 字幕和时间轴仍可正常查看。</div>`);
  else if (analysis.status === "failed") sections.push(`<div class="analysis-empty">AI 分析失败：${escapeHtml(analysis.error || "请检查 DeepSeek 配置后重试。")} 字幕和时间轴仍可正常查看。</div>`);
  else if (!hasProfileDetails) {
    const reason = knowledge.analysisSkipReason || knowledge.manifest?.analysis_skip_reason || "";
    const message = reason === "user_requested_transcript_only"
      ? "用户选择了仅转写，AI 分析未运行。"
      : "AI 分析未运行。";
    sections.push(`<div class="analysis-empty">${escapeHtml(message)} 字幕、时间轴和原文细读仍可正常查看。</div>`);
  }

  const terms = renderProfessionalTerms(analysis.terminology?.length ? analysis.terminology : analysis.glossary);
  if (terms) sections.push(`<section class="result-section"><h2>专业术语</h2>${terms}</section>`);
  if (hasProfileDetails) sections.push(renderProfileReport(analysis, knowledge.id));

  if (Array.isArray(analysis.highlights) && analysis.highlights.length) {
    sections.push(`<section class="result-section"><h2>亮点</h2><ul class="highlight-list">${analysis.highlights.map((item) => {
      const imageUrl = knowledgeAssetUrl(knowledge.id, item.image);
      const detail = item.summary || item.explanation || "";
      return `<li class="highlight-item${imageUrl ? " has-image" : ""}">${imageUrl ? `<img class="highlight-image" src="${imageUrl}" alt="${escapeAttr(item.title || "亮点画面")}" loading="lazy" data-preview-image="${imageUrl}">` : `<span class="highlight-icon">${escapeHtml(item.icon || "◆")}</span>`}<div class="highlight-copy"><strong>${escapeHtml(item.title || "亮点")}</strong>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}<div class="tag-list">${(item.tags || []).map((tag) => `<button class="tag-button" data-tag="${escapeAttr(tag)}">#${escapeHtml(tag)}</button>`).join("")}</div></div></li>`;
    }).join("")}</ul></section>`);
  }
  if (Array.isArray(analysis.thoughts) && analysis.thoughts.length) {
    sections.push(`<section class="result-section"><h2>思考</h2><ol class="thought-list">${analysis.thoughts.map((item) => `<li><button class="thought-button" data-question="${escapeAttr(item.question || "")}">${escapeHtml(item.question || "")}</button></li>`).join("")}</ol></section>`);
  }

  const chapters = Array.isArray(analysis.chapters) && analysis.chapters.length ? analysis.chapters : timeline;
  if (chapters.length) {
    sections.push(`<section class="result-section" id="chapterSection"><h2>视频章节总结</h2><div class="chapter-list">${chapters.map((chapter, index) => renderChapter(chapter, index, knowledge.id)).join("")}</div></section>`);
  }
  sections.push(`<section class="result-section"><h2>原文资料</h2><div class="source-entry"><button class="quiet-button" data-open-transcript>查看分组字幕</button>${knowledge.files?.["transcript.raw.jsonl"] ? '<button class="icon-button small" data-open-raw aria-label="打开逐句原始数据"><svg><use href="#i-file"/></svg></button>' : ""}</div></section>`);
  $("#summaryView").innerHTML = sections.join("");
}

function renderProfileReport(analysis, knowledgeId) {
  const profile = analysis.analysis_profile || "summary";
  const content = analysis.content || {};
  const sections = PROFILE_RENDER_SECTIONS[profile] || [];
  const body = sections.map(([title, key, kind]) => renderProfileField(title, content[key], kind, profile, knowledgeId)).join("");
  const evidence = [
    content.factual_basis ? `<section class="result-section"><h2>视频事实依据</h2><p>${escapeHtml(content.factual_basis)}</p></section>` : "",
    Array.isArray(content.ai_inferences) && content.ai_inferences.length ? `<section class="result-section"><h2>AI 推断</h2><ul>${content.ai_inferences.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>` : "",
  ].join("");
  return `${body}${evidence}`;
}

function renderProfileField(title, value, kind, profile, knowledgeId) {
  const html = renderProfileValue(value, kind, profile, knowledgeId);
  if (!html) return "";
  return `<section class="result-section"><h2>${escapeHtml(title)}</h2>${html}</section>`;
}

function renderProfileValue(value, kind, profile, knowledgeId) {
  if (kind === "text") return value ? `<p>${escapeHtml(value)}</p>` : "";
  if (kind === "list") return renderSimpleList(value);
  if (kind === "checklist") return Array.isArray(value) && value.length ? `<ul>${value.map((item) => `<li>☐ ${escapeHtml(item)}</li>`).join("")}</ul>` : "";
  if (kind === "chapters") return renderProfileChapters(value);
  if (kind === "tutorialChapters") return renderTutorialChapters(value, profile, knowledgeId);
  if (kind === "steps") return renderTutorialSteps(value, profile, knowledgeId);
  if (kind === "terms") return renderProfessionalTerms(value);
  if (kind === "highlights") return renderSummaryHighlights(value);
  if (kind === "thoughts") return renderSummaryThoughts(value);
  return "";
}

function renderProfessionalTerms(value) {
  if (!Array.isArray(value)) return "";
  const seen = new Set();
  const terms = value.filter((item) => {
    const term = textFromValue(item?.term).trim();
    const definition = textFromValue(item?.definition).trim();
    const identity = term.toLocaleLowerCase().replace(/\s+/g, "");
    if (!identity || !definition || seen.has(identity)) return false;
    seen.add(identity);
    return true;
  }).slice(0, 8);
  if (terms.length < 3) return "";
  return `<dl>${terms.map((item) => `<dt>${escapeHtml(item.term)}</dt><dd>${escapeHtml(item.definition)}</dd>`).join("")}</dl>`;
}

function renderSummaryHighlights(value) {
  if (!Array.isArray(value) || !value.length) return "";
  return `<ul class="highlight-list">${value.map((item) => {
    const seconds = item?.timestamp ?? item?.start;
    const time = seconds != null ? `<button class="time-button" data-seek="${Number(seconds) || 0}">${escapeHtml(formatTime(seconds))}</button>` : "";
    const title = textFromValue(item?.title) || "亮点";
    const detail = textFromValue(item?.explanation || item?.summary);
    return `<li class="highlight-item"><span class="highlight-icon">◆</span><div class="highlight-copy"><strong>${time}${escapeHtml(title)}</strong>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</div></li>`;
  }).join("")}</ul>`;
}

function renderSummaryThoughts(value) {
  if (!Array.isArray(value) || !value.length) return "";
  return `<ul class="thought-list">${value.map((item) => {
    const question = textFromValue(item?.question || item);
    return `<li><button class="thought-button" data-question="${escapeAttr(question)}">${escapeHtml(question)}</button></li>`;
  }).join("")}</ul>`;
}

function renderSimpleList(value) {
  if (!Array.isArray(value) || !value.length) return "";
  const items = value.map((item) => textFromValue(item).trim()).filter(Boolean);
  return items.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "";
}

function renderProfileChapters(value) {
  if (!Array.isArray(value) || !value.length) return "";
  return `<div class="chapter-list">${value.map((item, index) => {
    const title = textFromValue(item?.title) || `章节 ${index + 1}`;
    const time = item?.start != null ? `<span class="time-pill">${escapeHtml(formatTime(item.start))}</span>` : "";
    const summary = textFromValue(item?.summary || item);
    return `<article class="chapter"><h3>${time}${escapeHtml(title)}</h3>${summary ? `<p>${escapeHtml(summary)}</p>` : ""}</article>`;
  }).join("")}</div>`;
}

function renderTutorialChapters(value, profile, knowledgeId) {
  if (!Array.isArray(value) || !value.length) return "";
  const steps = Array.isArray(state.activeSource?.analysis?.content?.steps) ? state.activeSource.analysis.content.steps : [];
  return `<div class="chapter-list">${value.map((chapter, index) => {
    const chapterId = chapter?.id || `ch${index + 1}`;
    const childSteps = steps.filter((step) => step.chapter_id === chapterId || step.chapterId === chapterId);
    const time = chapter?.start != null ? `<span class="time-pill">${escapeHtml(formatTime(chapter.start))}</span>` : "";
    const summary = textFromValue(chapter?.summary || chapter);
    return `<details class="chapter tutorial-stage" open><summary><h3>${time}${escapeHtml(chapter?.title || `阶段 ${index + 1}`)}</h3></summary>${summary ? `<p>${escapeHtml(summary)}</p>` : ""}${childSteps.length ? renderTutorialSteps(childSteps, profile, knowledgeId) : ""}</details>`;
  }).join("")}</div>`;
}

function renderTutorialSteps(value, profile, knowledgeId) {
  if (!Array.isArray(value) || !value.length) return "";
  return `<div class="chapter-list">${value.map((item, index) => {
    const imageUrl = profile === "tutorial" ? knowledgeAssetUrl(knowledgeId, item.image) : "";
    const lines = [
      ["目标", item.objective],
      ["操作", item.action || item.description],
      ["预期结果", item.expected_result],
      ["参数", Array.isArray(item.parameters) ? item.parameters.join("；") : ""],
      ["注意", Array.isArray(item.cautions) ? item.cautions.join("；") : ""],
    ].filter(([, text]) => String(text || "").trim()).map(([label, text]) => `<li><strong>${label}：</strong>${escapeHtml(text)}</li>`).join("");
    const time = item.timestamp != null ? `<button class="time-button" data-seek="${Number(item.timestamp) || 0}">${escapeHtml(formatTime(item.timestamp))}</button>` : "";
    return `<article class="chapter tutorial-step"><h3>${time}${escapeHtml(item.title || `步骤 ${index + 1}`)}</h3>${imageUrl ? `<img class="chapter-frame" src="${imageUrl}" alt="${escapeAttr(item.title || "教程步骤截图")}" loading="lazy" data-preview-image="${imageUrl}">` : ""}${lines ? `<ul>${lines}</ul>` : ""}</article>`;
  }).join("")}</div>`;
}

function textFromValue(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "object") return value.text || value.summary || value.description || value.explanation || value.title || "";
  return String(value);
}

function renderInsightPanel(knowledge) {
  const highlights = Array.isArray(knowledge.analysis?.highlights) ? knowledge.analysis.highlights : [];
  const timeline = Array.isArray(knowledge.timeline) ? knowledge.timeline : [];
  const source = highlights.length ? highlights : timeline;
  const usingHighlights = highlights.length > 0;
  const comments = Array.isArray(knowledge.comments) ? knowledge.comments : [];
  const commentInsight = knowledge.commentInsights || {};
  const insightItems = ["hot_topics", "consensus", "controversies", "corrections", "frequent_questions"]
    .flatMap((key) => Array.isArray(commentInsight[key]) ? commentInsight[key].slice(0, 3) : []);
  const commentItems = insightItems.length ? insightItems : comments.slice(0, 8).map((item) => item.text || item.content || "");
  const filteredComments = commentItems.filter(Boolean).slice(0, 8);
  const activeTab = state.activeInsightTab === "highlights" ? "highlights" : "comments";
  $$("[data-insight-tab]").forEach((button) => {
    const active = button.dataset.insightTab === activeTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  if (activeTab === "comments") {
    $("#insightContent").innerHTML = filteredComments.length
      ? `<section class="insight-section" data-feature="comments">${filteredComments.map((item) => `<article class="insight-item comment-insight-item"><div class="insight-row"><span class="insight-marker comment"></span><strong>${escapeHtml(item)}</strong></div></article>`).join("")}</section>`
      : '<div class="module-empty">当前知识包没有同步评论区数据。</div>';
    return;
  }
  if (source.length) {
    $("#insightContent").innerHTML = `<section class="insight-section" data-feature="highlights">${source.map((item, index) => {
      const itemTime = usingHighlights ? (item.timestamp ?? item.start) : item.start;
      const hasTime = itemTime != null && Number.isFinite(Number(itemTime));
      const detail = usingHighlights ? (item.summary || item.explanation) : item.summary;
      const tags = usingHighlights ? (item.tags || []) : (item.keywords || []);
      return `<article class="insight-item" data-insight-index="${index}">
        <div class="insight-row">
          <span class="insight-marker ${usingHighlights ? "ai" : "timeline"}"></span>
          <strong>${escapeHtml(item.title || (usingHighlights ? `高光 ${index + 1}` : `片段 ${index + 1}`))}</strong>
          ${hasTime ? `<button class="timestamp-button" data-seek="${Number(itemTime)}">${formatTime(itemTime)}</button>` : ""}
        </div>
        ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
        ${tags.length ? `<div class="tag-list">${tags.map((tag) => `<span class="static-tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
      </article>`;
    }).join("")}</section>`;
    return;
  }
  $("#insightContent").innerHTML = '<div class="module-empty">当前知识包没有高光片段，已保留此功能位。</div>';
}

function renderChapter(chapter, index, knowledgeId) {
  const start = Number(chapter.start || 0);
  const framePath = chapter.frame_path || "";
  const frameUrl = framePath ? `/api/library/${encodeURIComponent(knowledgeId)}/file/${framePath.split("/").map(encodeURIComponent).join("/")}` : "";
  return `<article class="chapter" data-chapter-index="${index}" data-start="${start}" data-end="${Number(chapter.end || start)}">
    <button class="chapter-header" data-toggle-chapter><span class="timestamp-button" data-seek="${start}">${formatTime(start)}</span><h3>${escapeHtml(chapter.title || `章节 ${index + 1}`)}</h3><svg class="chapter-toggle"><use href="#i-chevron"/></svg></button>
    <div class="chapter-body">${frameUrl ? `<img class="chapter-frame" src="${frameUrl}" alt="${escapeAttr(chapter.title || "章节关键帧")}" loading="lazy" data-preview-image="${frameUrl}">` : ""}${chapter.summary ? `<p>${escapeHtml(chapter.summary)}</p>` : ""}</div>
  </article>`;
}

async function ensureTranscriptLoaded() {
  if (!state.selectedKnowledgeId || state.transcriptLoadedFor === state.selectedKnowledgeId) return;
  $("#transcriptGroups").innerHTML = '<div class="loading-list">正在加载分组字幕…</div>';
  try {
    const data = await api(`/api/library/${encodeURIComponent(state.selectedKnowledgeId)}/transcript`);
    state.transcriptGroups = data.groups || [];
    state.transcriptLoadedFor = state.selectedKnowledgeId;
    renderTranscriptGroups();
  } catch (error) {
    $("#transcriptGroups").innerHTML = `<div class="analysis-empty">分组字幕加载失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderTranscriptGroups() {
  const query = $("#transcriptSearch").value.trim().toLowerCase();
  const groups = state.transcriptGroups.filter((group) => !query || `${group.title} ${group.text}`.toLowerCase().includes(query));
  if (!groups.length) {
    $("#transcriptGroups").innerHTML = '<div class="result-empty"><p>没有可显示的分组字幕。</p></div>';
    return;
  }
  $("#transcriptGroups").innerHTML = groups.map((group) => `
    <article class="transcript-group" data-group-index="${group.index}" data-start="${Number(group.start || 0)}" data-end="${Number(group.end || 0)}">
      <header><button class="timestamp-button" data-seek="${Number(group.start || 0)}">${formatTime(group.start)}–${formatTime(group.end)}</button><h3>${escapeHtml(group.title || `片段 ${Number(group.index) + 1}`)}</h3><span class="transcript-actions"><button data-copy-group="${group.index}">复制</button></span></header>
      <p>${escapeHtml(group.text || "")}</p>
    </article>`).join("");
}

function renderQuestionChips(thoughts) {
  const questions = (thoughts || []).map((item) => item.question).filter(Boolean).slice(0, 4);
  $("#questionChips").innerHTML = questions.map((question) => `<button data-question="${escapeAttr(question)}">${escapeHtml(question)}</button>`).join("");
}

function setResultTab(tab, restoreScroll = true) {
  const next = tab === "transcript" ? "transcript" : "summary";
  state.scrollPositions[state.activeResultTab] = $("#resultScroll")?.scrollTop || 0;
  state.activeResultTab = next;
  localStorage.setItem(SETTINGS.activeResultTab, next);
  $$("[data-result-tab]").forEach((button) => {
    const active = button.dataset.resultTab === next;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $("#summaryView").classList.toggle("hidden", next !== "summary");
  $("#transcriptView").classList.toggle("hidden", next !== "transcript");
  $("#readTranscript").textContent = next === "summary" ? "阅读全文" : "返回总结";
  if (next === "transcript") ensureTranscriptLoaded();
  if (restoreScroll) requestAnimationFrame(() => $("#resultScroll").scrollTop = state.scrollPositions[next] || 0);
}

function setInsightTab(tab) {
  state.activeInsightTab = tab === "highlights" ? "highlights" : "comments";
  localStorage.setItem(SETTINGS.activeInsightTab, state.activeInsightTab);
  if (state.activeSource) renderInsightPanel(state.activeSource);
}

function handleResultClick(event) {
  const seek = event.target.closest("[data-seek]");
  if (seek) { event.preventDefault(); event.stopPropagation(); seekPreview(Number(seek.dataset.seek)); return; }
  const toggle = event.target.closest("[data-toggle-chapter]");
  if (toggle) { toggle.closest(".chapter").classList.toggle("collapsed"); return; }
  const thought = event.target.closest("[data-question]");
  if (thought) { focusChatQuestion(thought.dataset.question); return; }
  const tag = event.target.closest("[data-tag]");
  if (tag) { $("#librarySearch").value = tag.dataset.tag; renderLibrary(); focusSidebarSearch(); return; }
  const image = event.target.closest("[data-preview-image]");
  if (image) { $("#imagePreview").src = image.dataset.previewImage; $("#imageDialog").showModal(); return; }
  if (event.target.closest("[data-open-transcript]")) setResultTab("transcript");
  if (event.target.closest("[data-open-raw]")) openFile("transcript.raw.jsonl");
}

function handleTranscriptClick(event) {
  const seek = event.target.closest("[data-seek]");
  if (seek) { event.preventDefault(); seekPreview(Number(seek.dataset.seek)); return; }
  const copy = event.target.closest("[data-copy-group]");
  if (copy) {
    const group = state.transcriptGroups.find((item) => String(item.index) === copy.dataset.copyGroup);
    if (group) copyText(`${formatTime(group.start)}–${formatTime(group.end)} ${group.title}\n\n${group.text}`);
  }
}

function handleMediaAction(action) {
  if (!mediaController) return;
  if (action === "play") togglePlay();
  else if (action === "back") seekPreview(Math.max(0, mediaController.getCurrentTime() - 10));
  else if (action === "forward") seekPreview(mediaController.getCurrentTime() + 10);
  else if (action === "repeat") { const element = mediaController.element; if (element) { element.loop = !element.loop; showToast(element.loop ? "已开启循环" : "已关闭循环"); } }
  else if (action === "capture") captureFrame();
  else if (action === "fullscreen") mediaController.fullscreen();
}

function togglePlay() {
  if (mediaController instanceof HtmlMediaController) {
    if (mediaController.element.paused) mediaController.play();
    else mediaController.pause();
    return;
  }
  mediaController?.play();
}

function seekPreview(seconds) {
  state.currentTime = Math.max(0, seconds || 0);
  if (mediaController?.supportsSeek()) mediaController.seek(state.currentTime);
  updateTimeDisplay();
  updateActiveChapter();
  setMobileView("media");
  $("#mediaSection").scrollIntoView({ behavior: uiScrollBehavior(), block: "start" });
}

function handleTimeUpdate() {
  state.currentTime = mediaController?.getCurrentTime() || 0;
  updateTimeDisplay();
  updateActiveChapter();
}

function updateTimeDisplay() {
  $("#currentTime").textContent = formatTime(mediaController?.getCurrentTime() || state.currentTime || 0);
  $("#durationTime").textContent = formatTime(mediaController?.element?.duration || state.activeSource?.source?.duration || 0);
}

function updateActiveChapter() {
  const time = state.currentTime;
  let active = -1;
  const items = state.activeResultTab === "transcript" ? $$(".transcript-group") : $$(".chapter");
  items.forEach((element, index) => {
    const inside = time >= Number(element.dataset.start || 0) && time < Number(element.dataset.end || Infinity);
    element.classList.toggle("active", inside);
    if (inside) active = index;
  });
  if (active !== state.currentChapter) {
    state.currentChapter = active;
    if (state.transcriptFollowMode && active >= 0 && state.activeResultTab === "transcript") items[active]?.scrollIntoView({ behavior: uiScrollBehavior(), block: "center" });
  }
}

function setPlaybackRate(rate) {
  const value = Number.isFinite(rate) && rate > 0 ? rate : 1;
  $("#playbackRate").value = String(value);
  mediaController?.setPlaybackRate(value);
  localStorage.setItem(SETTINGS.playbackRate, String(value));
}

function setPlayIcon(playing) {
  const use = $("[data-media=play] use");
  if (use) use.setAttribute("href", playing ? "#i-pause" : "#i-play");
}

async function captureFrame() {
  if (!(mediaController instanceof HtmlMediaController) || mediaController.element.tagName !== "VIDEO") {
    showToast("当前媒体不支持本地截图");
    return;
  }
  try {
    await api(`/api/library/${encodeURIComponent(state.selectedKnowledgeId)}/capture-frame`, { method: "POST", body: JSON.stringify({ time: mediaController.getCurrentTime() }) });
  } catch (error) { showToast(error.message); }
}

async function sendChat() {
  const input = $("#chatInput");
  const question = input.value.trim();
  if (!question || !state.selectedKnowledgeId) return;
  input.value = "";
  currentChatState().draft = "";
  await requestChat(question, true);
}

async function requestChat(question, appendUser) {
  const knowledgeId = state.selectedKnowledgeId;
  const chatState = currentChatState();
  if (appendUser) chatState.messages.push({ role: "user", content: question });
  chatState.loading = true;
  chatState.controller?.abort();
  chatState.controller = new AbortController();
  renderChatHistory();
  renderProviderStatus();
  try {
    const data = await api("/api/chat", {
      method: "POST",
      signal: chatState.controller.signal,
      body: JSON.stringify({ knowledge_id: knowledgeId, question, provider: chatState.provider, model: null, history: chatState.messages.slice(0, -1) }),
    });
    if (state.selectedKnowledgeId !== knowledgeId || data.knowledge_id !== knowledgeId) return;
    chatState.messages.push({ role: "assistant", content: data.answer || "", citations: data.citations || [], provider: data.provider || "", model: data.model || "", warning: data.warning || "", route: data.route || "", route_status: data.route_status || "" });
  } catch (error) {
    if (error.name !== "AbortError" && state.selectedKnowledgeId === knowledgeId) {
      chatState.messages.push({ role: "system", content: error.message || "上下文对话请求失败" });
    }
  } finally {
    chatState.loading = false;
    chatState.controller = null;
  }
  if (state.selectedKnowledgeId === knowledgeId) {
    renderChatHistory();
    renderProviderStatus();
  }
}

async function loadChatHistory(knowledgeId) {
  const chatState = currentChatState();
  if (!chatState.loaded) {
    try {
      const data = await api(`/api/library/${encodeURIComponent(knowledgeId)}/chat`);
      if (state.selectedKnowledgeId !== knowledgeId) return;
      chatState.messages = data.chat?.messages || [];
      chatState.loaded = true;
    } catch (error) {
      chatState.messages = [{ role: "system", content: `聊天记录加载失败：${error.message}` }];
    }
  }
  $("#chatInput").value = chatState.draft || "";
  renderChatHistory();
  renderProviderStatus();
}

async function clearCurrentChat() {
  if (!state.selectedKnowledgeId) return;
  const knowledgeId = state.selectedKnowledgeId;
  const chatState = currentChatState();
  chatState.controller?.abort();
  try {
    await api(`/api/library/${encodeURIComponent(knowledgeId)}/chat`, { method: "DELETE" });
    chatState.messages = [];
    chatState.draft = "";
    $("#chatInput").value = "";
    renderChatHistory();
  } catch (error) { showToast(error.message); }
}

async function regenerateLastAnswer() {
  const chatState = currentChatState();
  const userIndex = [...chatState.messages].map((item) => item.role).lastIndexOf("user");
  if (userIndex < 0 || chatState.loading) return;
  const question = chatState.messages[userIndex].content;
  chatState.messages = chatState.messages.slice(0, userIndex + 1);
  await api(`/api/library/${encodeURIComponent(state.selectedKnowledgeId)}/chat`, {
    method: "POST",
    body: JSON.stringify({ messages: chatState.messages }),
  });
  await requestChat(question, false);
}

function renderChatHistory() {
  const root = $("#chatHistory");
  const chatHistory = currentChatHistory();
  root.innerHTML = chatHistory.length ? chatHistory.map((item) => {
    const citations = Array.isArray(item.citations) ? item.citations : [];
    const citationHtml = citations.length ? `<div class="chat-citations">${citations.map((citation) => `<button type="button" data-seek="${Number(citation.start || 0)}" title="${escapeAttr(citation.excerpt || citation.title || "字幕证据")}">[${Number(citation.index || 0)}] ${formatTime(Number(citation.start || 0))}</button>`).join("")}</div>` : "";
    const warningHtml = item.warning ? `<div class="chat-warning">${escapeHtml(item.warning)}</div>` : "";
    const routeHtml = item.route ? ` · ${escapeHtml(videoChatRouteLabel(item.route, item.route_status))}` : "";
    const modelHtml = item.role === "assistant" && item.model ? `<small class="chat-model">${escapeHtml(providerLabel(item.provider))} · ${escapeHtml(item.model)}${routeHtml} · ${citations.length} 条证据 <button type="button" data-regenerate>重新生成</button></small>` : "";
    return `<div class="chat-message ${escapeAttr(item.role)}"><div>${escapeHtml(item.content)}</div>${warningHtml}${citationHtml}${modelHtml}</div>`;
  }).join("") : '<div class="chat-empty">针对当前视频提问，回答会附带可跳转的字幕时间引用。</div>';
  if (currentChatState().loading) root.insertAdjacentHTML("beforeend", '<div class="chat-message assistant loading">正在检索当前视频并请求模型…</div>');
  root.scrollTop = root.scrollHeight;
}

function focusChatQuestion(question) {
  $("#chatInput").value = question || "";
  openInspector($("#toggleInspector"));
  $("#chatPane").scrollIntoView({ behavior: uiScrollBehavior(), block: "start" });
  requestAnimationFrame(() => $("#chatInput").focus());
}

function openNewTask() {
  $("#taskProgress").classList.add("hidden");
  $("#newTaskForm").reset();
  $("#taskFrames").checked = true;
  $("#taskComments").checked = false;
  $("#taskNoSummary").checked = false;
  $("#taskAsrRoute").value = "cloud";
  $("#taskAsrFallback").checked = true;
  setTaskSourceError(false);
  setTaskButtonLoading(false);
  setTaskSourceType("url");
  updateAnalysisModeDescriptions();
  $("#newTaskDialog").showModal();
  refreshTaskCapabilities();
  loadJobHistory();
}

async function refreshTaskCapabilities() {
  const root = $("#taskCapabilities");
  root.textContent = "正在检查当前可用能力…";
  try {
    renderTaskCapabilities(await api("/api/capabilities"));
    renderTaskCapabilities(await api("/api/capabilities/refresh", {
      method: "POST",
      body: "{}",
    }));
  } catch (error) {
    root.textContent = `能力检查失败：${error.message}`;
  }
}

function renderTaskCapabilities(payload) {
  const capabilities = payload.capabilities || {};
  const labels = state.uiMode === "diagnostic"
    ? {
        deepseek: "DeepSeek",
        groq: "Groq",
        gemini: "Gemini",
        ffmpeg: "FFmpeg",
        ffprobe: "ffprobe",
        local_model: "本地模型",
        local_cpu: "本地 CPU",
        local_gpu: "本地 GPU",
      }
    : {
        analysis_text: "文字分析",
        cloud_transcription: "云端转写",
        visual_understanding: "视觉理解",
        media_processing: "媒体处理",
        local_model: "本地模型",
        local_cpu: "本地 CPU",
        local_gpu: "本地 GPU",
      };
  $("#taskCapabilities").innerHTML = Object.entries(labels).map(([name, label]) => {
    const item = capabilities[name] || { status: "checking", displayMessage: "检测中" };
    return `<span class="capability-item ${escapeAttr(item.status)}"><strong>${label}</strong>：${escapeHtml(item.displayMessage || item.status)}</span>`;
  }).join("<br>");
  $("#taskCapabilities").classList.toggle("hidden", state.uiMode !== "diagnostic");
  const route = $("#taskAsrRoute");
  const cloudOption = route.querySelector('option[value="cloud"]');
  const gpuOption = route.querySelector('option[value="local_gpu"]');
  const cpuOption = route.querySelector('option[value="local_cpu"]');
  const cloudCapability = capabilities.cloud_transcription || capabilities.groq;
  cloudOption.disabled = cloudCapability?.status !== "available";
  gpuOption.disabled = capabilities.local_gpu?.status !== "available";
  cpuOption.disabled = capabilities.local_cpu?.status !== "available";
  if (route.selectedOptions[0]?.disabled) {
    const next = [...route.options].find((option) => !option.disabled);
    if (next) route.value = next.value;
  }
}

function updateAnalysisModeDescriptions() {
  const mode = $("#taskMode")?.value || "summary";
  const processing = $("#taskProcessingProfile")?.value || "complete";
  const taskMeta = ANALYSIS_MODE_META[mode] || ANALYSIS_MODE_META.summary;
  const taskDescription = mode === "tutorial" && processing === "complete"
    ? `${taskMeta.description}。将提取完整教程步骤并生成对应操作截图。`
    : taskMeta.description;
  if ($("#taskModeDescription")) $("#taskModeDescription").textContent = taskDescription;
  const settingsMode = $("#settingsMode")?.value || mode;
  const settingsMeta = ANALYSIS_MODE_META[settingsMode] || ANALYSIS_MODE_META.summary;
  if ($("#settingsModeDescription")) $("#settingsModeDescription").textContent = settingsMeta.description;
}

function setTaskSourceType(type) {
  activeSourceType = type === "file" ? "file" : "url";
  $$("[data-source-type]").forEach((button) => {
    const selected = button.dataset.sourceType === activeSourceType;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-checked", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $("#taskSourceLabel").textContent = activeSourceType === "url" ? "视频链接" : "本地文件路径";
  $("#taskSource").placeholder = activeSourceType === "url" ? "https://www.bilibili.com/video/BV…" : "E:\\Downloads_E\\video.mp4";
  $("#taskSourceError").textContent = activeSourceType === "url" ? "请输入视频链接。" : "请输入本地文件路径。";
}

function knowledgeAssetUrl(knowledgeId, relativePath) {
  if (!knowledgeId || !relativePath || String(relativePath).includes("..")) return "";
  return `/api/library/${encodeURIComponent(knowledgeId)}/file/${String(relativePath).split("/").map(encodeURIComponent).join("/")}`;
}

async function submitTask(event) {
  event.preventDefault();
  await startTaskPayload(buildTaskPayload());
}

function buildTaskPayload(duplicateAction = "") {
  const transcriptOnly = $("#taskNoSummary").checked;
  const payload = {
    sourceType: activeSourceType,
    source: $("#taskSource").value,
    backend: $("#taskBackend").value,
    mode: $("#taskMode").value,
    processingProfile: $("#taskProcessingProfile").value,
    lang: $("#taskLanguage").value,
    export: $("#taskExport").value,
    noFrames: !$("#taskFrames").checked,
    comments: $("#taskComments").checked,
    asr_route: $("#taskAsrRoute").value,
    asr_fallback_enabled: $("#taskAsrFallback").checked,
    noSummary: transcriptOnly,
    skip_analysis: transcriptOnly,
    transcribe_only: transcriptOnly,
    transcriptOnly,
    analysis_enabled: !transcriptOnly,
    analysis_requested: !transcriptOnly,
    sampleSeconds: $("#taskSampleSeconds").value,
    transcriptGroupSeconds: $("#taskTranscriptGroupSeconds").value,
  };
  if (duplicateAction) payload.duplicateAction = duplicateAction;
  return payload;
}

async function startTaskPayload(payload) {
  hideDuplicateDecision();
  setTaskButtonLoading(true);
  try {
    const data = await api("/api/process", { method: "POST", body: JSON.stringify(payload) });
    state.taskStatus = data.job;
    $("#taskProgress").classList.remove("hidden");
    pollTask(data.job.id);
  } catch (error) {
    if (isDuplicateTaskError(error)) {
      renderDuplicateDecision(payload, error.data.duplicate);
      setTaskButtonLoading(false);
      return;
    }
    showToast(error.message);
    setTaskButtonLoading(false);
  }
}

function isDuplicateTaskError(error) {
  return error?.status === 409 && error?.data?.duplicate;
}

function renderDuplicateDecision(payload, duplicate) {
  pendingDuplicatePayload = { ...payload };
  const panel = $("#taskDuplicateDecision");
  const kind = duplicate?.kind || "unknown";
  const labels = {
    active_exact: "已有完全相同的任务正在处理。",
    completed_exact: "已有完全相同的知识包处理完成。",
    recoverable_exact: "已有完全相同的任务中断或失败，可以恢复。",
    source_revision: "该来源已有知识包，但处理选项不同。",
  };
  $("#taskDuplicateTitle").textContent = "检测到重复任务";
  $("#taskDuplicateMessage").textContent = labels[kind] || "检测到相同或相关来源，请选择处理方式。";
  const actionLabels = {
    reuse: "复用已有结果",
    resume: "恢复上次任务",
    refresh: "重新处理",
    revision: "作为新版本处理",
    reject: "取消",
  };
  $("#taskDuplicateActions").innerHTML = (duplicate?.allowedActions || [])
    .map((action) => `<button type="button" data-duplicate-action="${escapeHtml(action)}">${escapeHtml(actionLabels[action] || action)}</button>`)
    .join("");
  panel.classList.remove("hidden");
}

function hideDuplicateDecision() {
  pendingDuplicatePayload = null;
  $("#taskDuplicateDecision")?.classList.add("hidden");
  if ($("#taskDuplicateActions")) $("#taskDuplicateActions").innerHTML = "";
}

async function handleDuplicateAction(event) {
  const button = event.target.closest("[data-duplicate-action]");
  if (!button || !pendingDuplicatePayload) return;
  const action = button.dataset.duplicateAction;
  if (action === "reject") {
    hideDuplicateDecision();
    return;
  }
  await startTaskPayload({ ...pendingDuplicatePayload, duplicateAction: action });
}

function pollTask(jobId) {
  clearInterval(taskPoller);
  const update = async () => {
    try {
      const data = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      state.taskStatus = data.job;
      renderTaskProgress(data.job);
      if (["success", "failed", "interrupted"].includes(data.job.status)) {
        clearInterval(taskPoller);
        setTaskButtonLoading(false);
        if (data.job.status === "success") {
          await refreshLibrary();
          const outputId = data.job.knowledgeId || (data.job.outputDir || "").split("/").pop();
          if (outputId) await loadKnowledge(outputId, true);
          setTimeout(() => $("#newTaskDialog").close(), 700);
        }
      }
    } catch (error) {
      clearInterval(taskPoller);
      setTaskButtonLoading(false);
      showToast(error.message);
    }
  };
  update();
  taskPoller = setInterval(update, 1400);
}

function renderTaskProgress(job) {
  const stageOrder = ["resolve_source", "collect_metadata", "acquire_transcript", "normalize_transcript", "group_transcript", "build_timeline", "run_analysis", "extract_frames", "visual_analysis", "highlight_snapshot", "comments_fetch", "comments_analysis", "export_knowledge_package"];
  const logs = job.logs || [];
  const latestStage = [...logs].reverse().find((line) => line.includes("阶段：")) || "";
  const stage = latestStage.split("阶段：").pop();
  const stageIndex = Math.max(0, stageOrder.indexOf(stage));
  const transcriptProgress = Math.max(0, Math.min(1, Number(job.transcriptProgress || 0)));
  const stageProgress = stage === "acquire_transcript" ? transcriptProgress : 0.5;
  const calculatedPercent = Math.max(8, Math.round(((stageIndex + stageProgress) / stageOrder.length) * 100));
  const percent = job.status === "success" ? 100 : calculatedPercent;
  $("#taskStatusText").textContent = job.status === "failed"
    ? (job.error || "处理失败")
    : job.status === "interrupted"
      ? (job.error || "任务已中断")
      : job.status === "success"
        ? "处理完成"
        : stageLabel(stage || "queued");
  $("#taskPercent").textContent = `${percent}%`;
  $("#progressBar").style.width = `${percent}%`;
  $("#taskProgressBar").setAttribute("aria-valuenow", String(percent));
  $("#taskProgressBar").setAttribute("aria-valuetext", $("#taskStatusText").textContent);
  renderTaskAsrStatus(job);
  $("#taskLogs").textContent = logs.slice(-10).join("\n") || "等待任务日志…";
}

function renderTaskAsrStatus(job) {
  const root = $("#taskAsrStatus");
  const requested = ({ cloud: "云端快速转写", local_gpu: "本地 GPU", local_cpu: "本地 CPU" })[job.transcriptRouteRequested] || job.transcriptRouteRequested || "";
  const actualDevice = ({ cuda: "本地 GPU", cpu: "本地 CPU", cloud: "云端" })[job.transcriptActualDevice] || job.transcriptActualDevice || "";
  const reasons = {
    cuda_unavailable: "CUDA 不可用",
    gpu_model_load_failed: "GPU 模型加载失败",
    gpu_model_load_timeout: "GPU 模型加载超时",
    gpu_first_batch_failed: "GPU 首批推理失败",
    gpu_first_batch_timeout: "GPU 首批推理超时",
    gpu_transcription_failed: "GPU 转写失败",
    gpu_transcription_stalled: "GPU 转写长时间无进展",
    gpu_out_of_memory: "GPU 显存不足",
    cpu_transcription_stalled: "本地 CPU 转写长时间无进展，任务已终止",
  };
  if (!requested && !actualDevice && !job.transcriptFallbackUsed) {
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }
  root.classList.remove("hidden");
  root.innerHTML = [
    requested ? `<span>用户选择：${escapeHtml(requested)}</span>` : "",
    actualDevice ? `<span>实际设备：${escapeHtml(actualDevice)}</span>` : "",
    `<span>已发生回退：${job.transcriptFallbackUsed ? "是" : "否"}</span>`,
    job.transcriptFallbackReason ? `<span>回退原因：${escapeHtml(reasons[job.transcriptFallbackReason] || "本地转写不可用")}</span>` : "",
  ].filter(Boolean).join("<br>");
}

function isWideShell() { return window.matchMedia(WIDE_SHELL_QUERY).matches; }
function isSinglePane() { return window.matchMedia(SINGLE_PANE_QUERY).matches; }

function toggleSidebar(trigger = $("#toggleSidebar")) {
  const app = $("#app");
  lastSidebarTrigger = trigger;
  if (isWideShell()) {
    app.classList.toggle("sidebar-hidden");
    app.classList.remove("sidebar-open");
    syncShellAccessibility();
    return;
  }
  if (app.classList.contains("sidebar-open")) closeSidebar(true);
  else openSidebar(trigger);
}

function openSidebar(trigger = $("#toggleSidebar"), focusSearch = false) {
  const app = $("#app");
  lastSidebarTrigger = trigger;
  app.classList.remove("sidebar-hidden", "inspector-open");
  app.classList.add("sidebar-open");
  syncShellAccessibility();
  requestAnimationFrame(() => (focusSearch ? $("#librarySearch") : $("#sidebar")).focus());
}

function closeSidebar(returnFocus = false) {
  const app = $("#app");
  if (isWideShell()) app.classList.add("sidebar-hidden");
  app.classList.remove("sidebar-open");
  syncShellAccessibility();
  if (returnFocus) (lastSidebarTrigger || $("#toggleSidebar")).focus();
}

function focusSidebarSearch() { openSidebar($("#toggleSidebar"), true); }

function toggleInspector(trigger = $("#toggleInspector")) {
  const app = $("#app");
  lastInspectorTrigger = trigger;
  const expanded = isWideShell() ? !app.classList.contains("inspector-hidden") : app.classList.contains("inspector-open");
  if (expanded) closeInspector(true);
  else openInspector(trigger);
}

function openInspector(trigger = $("#toggleInspector")) {
  const app = $("#app");
  lastInspectorTrigger = trigger;
  app.classList.remove("inspector-hidden", "sidebar-open");
  if (!isWideShell()) app.classList.add("inspector-open");
  syncShellAccessibility();
  if (!isWideShell()) requestAnimationFrame(() => $("#collaborationPane").focus());
}

function closeInspector(returnFocus = false) {
  const app = $("#app");
  if (isWideShell()) app.classList.add("inspector-hidden");
  app.classList.remove("inspector-open");
  syncShellAccessibility();
  if (returnFocus) (lastInspectorTrigger || $("#toggleInspector")).focus();
}

function closeActiveSheet(returnFocus = false) {
  if ($("#app").classList.contains("sidebar-open")) closeSidebar(returnFocus);
  else if ($("#app").classList.contains("inspector-open")) closeInspector(returnFocus);
}

function syncShellAccessibility() {
  const app = $("#app");
  const wide = isWideShell();
  const sidebarExpanded = wide ? !app.classList.contains("sidebar-hidden") : app.classList.contains("sidebar-open");
  const inspectorExpanded = wide ? !app.classList.contains("inspector-hidden") : app.classList.contains("inspector-open");
  const sidebar = $("#sidebar");
  const inspector = $("#collaborationPane");
  $("#toggleSidebar").setAttribute("aria-expanded", String(sidebarExpanded));
  $("#toggleSidebar").setAttribute("aria-label", sidebarExpanded ? "隐藏知识库" : "打开知识库");
  $("#toggleInspector").setAttribute("aria-expanded", String(inspectorExpanded));
  $("#toggleInspector").setAttribute("aria-label", inspectorExpanded ? "隐藏检查器" : "打开检查器");
  sidebar.setAttribute("aria-hidden", String(!sidebarExpanded));
  inspector.setAttribute("aria-hidden", String(!inspectorExpanded));
  sidebar.inert = !sidebarExpanded;
  inspector.inert = !inspectorExpanded;
  [sidebar, inspector].forEach((layer) => {
    if (wide) {
      layer.removeAttribute("role");
      layer.removeAttribute("aria-modal");
    } else {
      layer.setAttribute("role", "dialog");
      layer.setAttribute("aria-modal", "true");
    }
  });
  $("#drawerScrim").setAttribute("aria-hidden", String(!(app.classList.contains("sidebar-open") || app.classList.contains("inspector-open"))));
}

function handleViewportChange() {
  $("#app").classList.remove("sidebar-open", "inspector-open");
  syncShellAccessibility();
  requestAnimationFrame(reconcileLayoutWidths);
}

function activeModalLayer() {
  if (isWideShell()) return null;
  if ($("#app").classList.contains("sidebar-open")) return $("#sidebar");
  if ($("#app").classList.contains("inspector-open")) return $("#collaborationPane");
  return null;
}

function trapLayerFocus(event) {
  if (event.key !== "Tab") return false;
  const layer = activeModalLayer();
  if (!layer) return false;
  const focusable = $$('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])', layer)
    .filter((element) => element.getClientRects().length);
  if (!focusable.length) { event.preventDefault(); layer.focus(); return true; }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); return true; }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); return true; }
  return false;
}

function dividerModules(resizer) {
  if (isSinglePane() || (resizer.id === "rightPaneResizer" && !isWideShell())) return null;
  if (!isWideShell()) return [$("#resultPane"), $("#centerPane")];
  const dividerOrder = Number(resizer.style.order);
  const modules = $$(".workspace-module").filter((module) => !module.matches("[aria-hidden=true]")).sort((a, b) => Number(a.style.order) - Number(b.style.order));
  const left = [...modules].reverse().find((module) => Number(module.style.order) < dividerOrder);
  const right = modules.find((module) => Number(module.style.order) > dividerOrder);
  return left && right ? [left, right] : null;
}

function moduleMinimumWidth(module) {
  const minimum = Number.parseFloat(getComputedStyle(module).minWidth);
  return Number.isFinite(minimum) ? minimum : 0;
}

function moduleMaximumWidth(module) {
  const maximum = Number.parseFloat(getComputedStyle(module).maxWidth);
  return Number.isFinite(maximum) ? maximum : Infinity;
}

function dividerBounds(left, right) {
  const total = left.getBoundingClientRect().width + right.getBoundingClientRect().width;
  const minimum = Math.round(Math.max(moduleMinimumWidth(left), total - moduleMaximumWidth(right)));
  const rightMinimum = Math.round(moduleMinimumWidth(right));
  const maximum = Math.max(minimum, Math.round(Math.min(moduleMaximumWidth(left), total - rightMinimum)));
  return { minimum, rightMinimum, maximum, total };
}

function setDividerWidths(resizer, left, right, nextLeft) {
  const { minimum, maximum, total } = dividerBounds(left, right);
  const leftWidth = clamp(nextLeft, minimum, maximum);
  const rightWidth = total - leftWidth;
  left.style.flexBasis = `${leftWidth}px`;
  right.style.flexBasis = `${rightWidth}px`;
  state.moduleWidths[left.dataset.module] = Math.round(leftWidth);
  state.moduleWidths[right.dataset.module] = Math.round(rightWidth);
  updateDividerAria(resizer, left, right);
}

function startResize(event) {
  if (event.button !== 0) return;
  const resizer = event.currentTarget;
  const modules = dividerModules(resizer);
  if (!modules) return;
  const [left, right] = modules;
  const startX = event.clientX;
  const leftWidth = left.getBoundingClientRect().width;
  resizer.setPointerCapture(event.pointerId);
  resizer.classList.add("dragging");
  const move = (moveEvent) => setDividerWidths(resizer, left, right, leftWidth + moveEvent.clientX - startX);
  const end = () => {
    resizer.classList.remove("dragging");
    resizer.removeEventListener("pointermove", move);
    resizer.removeEventListener("pointerup", end);
    resizer.removeEventListener("pointercancel", end);
    localStorage.setItem(SETTINGS.moduleWidths, JSON.stringify(state.moduleWidths));
  };
  resizer.addEventListener("pointermove", move);
  resizer.addEventListener("pointerup", end);
  resizer.addEventListener("pointercancel", end);
}

function handleDividerKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const modules = dividerModules(event.currentTarget);
  if (!modules) return;
  event.preventDefault();
  const [left, right] = modules;
  const { minimum, maximum } = dividerBounds(left, right);
  const current = left.getBoundingClientRect().width;
  const step = event.shiftKey ? 48 : 16;
  const next = event.key === "Home" ? minimum : event.key === "End" ? maximum : current + (event.key === "ArrowRight" ? step : -step);
  setDividerWidths(event.currentTarget, left, right, next);
  localStorage.setItem(SETTINGS.moduleWidths, JSON.stringify(state.moduleWidths));
}

function updateDividerAria(resizer, left, right) {
  if (!left || !right) return;
  const { minimum, maximum } = dividerBounds(left, right);
  const current = Math.round(left.getBoundingClientRect().width);
  resizer.setAttribute("aria-valuemin", String(minimum));
  resizer.setAttribute("aria-valuemax", String(maximum));
  resizer.setAttribute("aria-valuenow", String(clamp(current, minimum, maximum)));
  resizer.setAttribute("aria-valuetext", `${left.dataset.module} ${current} 像素`);
  resizer.setAttribute("aria-controls", `${left.id} ${right.id}`);
}

function updateAllDividerAria() {
  $$(".pane-resizer").forEach((resizer) => {
    const modules = dividerModules(resizer);
    if (modules) updateDividerAria(resizer, ...modules);
  });
}

function reconcileLayoutWidths() {
  if (!isSinglePane()) {
    $$(".pane-resizer").forEach((resizer) => {
      const modules = dividerModules(resizer);
      if (!modules) return;
      const [left, right] = modules;
      const { minimum, rightMinimum, total } = dividerBounds(left, right);
      if (total < minimum + rightMinimum) return;
      setDividerWidths(resizer, left, right, left.getBoundingClientRect().width);
    });
    localStorage.setItem(SETTINGS.moduleWidths, JSON.stringify(state.moduleWidths));
  }
  updateAllDividerAria();
}

function resetModuleWidths() {
  state.moduleWidths = {};
  localStorage.removeItem(SETTINGS.moduleWidths);
  $$(".workspace-module").forEach((module) => module.style.removeProperty("flex-basis"));
  requestAnimationFrame(updateAllDividerAria);
}

function setMobileView(view) {
  const next = ["result", "media"].includes(view) ? view : "result";
  $("#app").dataset.mobileView = next;
  $$("[data-mobile-tab]").forEach((button) => {
    const active = button.dataset.mobileTab === next;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
}

function openLayoutSettings() {
  syncLayoutControls();
  $("#layoutDialog").showModal();
}

function syncLayoutControls() {
  $("#layoutPosition1").value = state.moduleOrder[0];
  $("#layoutPosition2").value = state.moduleOrder[1];
  $("#layoutPosition3").value = "collaboration";
}

function updateLayoutFromControls(event) {
  const selects = [$("#layoutPosition1"), $("#layoutPosition2")];
  const changedIndex = selects.indexOf(event.currentTarget);
  if (changedIndex < 0) return;
  const selected = event.currentTarget.value;
  const otherIndex = changedIndex === 0 ? 1 : 0;
  if (selects[otherIndex].value === selected) selects[otherIndex].value = state.moduleOrder[changedIndex];
  state.moduleOrder = [...selects.map((select) => select.value), "collaboration"];
  localStorage.setItem(SETTINGS.moduleOrder, JSON.stringify(state.moduleOrder));
  applyModuleOrder();
}

function applyModuleOrder() {
  const order = state.moduleOrder.length === 3 ? state.moduleOrder : [...DEFAULT_MODULE_ORDER];
  order.forEach((module, index) => {
    const element = $(`[data-module="${module}"]`);
    if (element) element.style.order = String(index * 2);
  });
  $("#paneResizer").style.order = "1";
  $("#rightPaneResizer").style.order = "3";
}

function resetWorkspaceLayout() {
  state.moduleOrder = [...DEFAULT_MODULE_ORDER];
  localStorage.setItem(SETTINGS.moduleOrder, JSON.stringify(state.moduleOrder));
  resetModuleWidths();
  applyModuleOrder();
  syncLayoutControls();
  showToast("已恢复默认三栏布局");
}

function readModuleOrder() {
  const value = readJsonSetting(SETTINGS.moduleOrder, DEFAULT_MODULE_ORDER);
  if (!Array.isArray(value) || value.length !== 3 || new Set(value).size !== 3 || !value.every((item) => DEFAULT_MODULE_ORDER.includes(item))) return [...DEFAULT_MODULE_ORDER];
  return [...value.filter((item) => item !== "collaboration"), "collaboration"];
}

function readJsonSetting(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}

async function loadNote(knowledgeId, force = false) {
  const noteState = currentNoteState(knowledgeId);
  if (noteState.loaded && !force) {
    if (state.selectedKnowledgeId === knowledgeId) renderNoteState(knowledgeId);
    return;
  }
  noteState.loading = true;
  noteState.error = "";
  if (state.selectedKnowledgeId === knowledgeId) renderNoteState(knowledgeId);
  try {
    const data = await api(`/api/library/${encodeURIComponent(knowledgeId)}/notes`);
    if (noteState.dirty && !force) return;
    noteState.content = data.note?.content || "";
    noteState.revision = data.note?.revision || "";
    noteState.updatedAt = data.note?.updated_at || "";
    noteState.loaded = true;
  } catch (error) {
    noteState.error = error.message;
    noteState.loaded = true;
  } finally {
    noteState.loading = false;
    if (state.selectedKnowledgeId === knowledgeId) renderNoteState(knowledgeId);
  }
}

function saveNoteDraft() {
  const knowledgeId = state.selectedKnowledgeId;
  if (!knowledgeId) return;
  const noteState = currentNoteState(knowledgeId);
  noteState.content = $("#noteEditor").value;
  noteState.loaded = true;
  noteState.dirty = true;
  noteState.error = "";
  clearTimeout(noteState.timer);
  noteState.timer = window.setTimeout(() => flushNoteSave(knowledgeId), 800);
  renderNoteSaveStatus(noteState);
}

async function flushNoteSave(knowledgeId) {
  const noteState = currentNoteState(knowledgeId);
  clearTimeout(noteState.timer);
  noteState.timer = 0;
  if (noteState.saving) return noteState.savePromise;
  if (!noteState.dirty || noteState.error) return null;
  const content = noteState.content;
  const revision = noteState.revision;
  noteState.saving = true;
  noteState.error = "";
  if (state.selectedKnowledgeId === knowledgeId) renderNoteSaveStatus(noteState);
  noteState.savePromise = api(`/api/library/${encodeURIComponent(knowledgeId)}/notes`, {
    method: "PUT",
    body: JSON.stringify({ content, revision }),
  }).then((data) => {
    noteState.revision = data.note?.revision || noteState.revision;
    noteState.updatedAt = data.note?.updated_at || "";
    noteState.dirty = noteState.content !== content;
    if (state.selectedKnowledgeId === knowledgeId && data.export?.url && state.activeSource) {
      state.activeSource.files = state.activeSource.files || {};
      state.activeSource.files[data.export.name || "export_note.md"] = data.export.url;
    }
  }).catch((error) => {
    noteState.error = error.message;
    if (error.status === 409 && error.data?.note) {
      noteState.revision = error.data.note.revision || noteState.revision;
    }
  }).finally(() => {
    noteState.saving = false;
    noteState.savePromise = null;
    if (state.selectedKnowledgeId === knowledgeId) renderNoteSaveStatus(noteState);
    if (noteState.dirty && !noteState.error) {
      noteState.timer = window.setTimeout(() => flushNoteSave(knowledgeId), 800);
    }
  });
  return noteState.savePromise;
}

function renderNoteState(knowledgeId = state.selectedKnowledgeId) {
  const noteState = currentNoteState(knowledgeId);
  const editor = $("#noteEditor");
  editor.disabled = !knowledgeId || noteState.loading;
  if (editor.value !== noteState.content) editor.value = noteState.content;
  renderNoteSaveStatus(noteState);
}

function renderNoteSaveStatus(noteState) {
  const status = $("#noteSaveStatus");
  status.classList.toggle("error", Boolean(noteState.error));
  status.textContent = noteState.loading
    ? "正在读取…"
    : noteState.error
      ? `保存失败 · ${noteState.error}`
      : noteState.saving
        ? "正在保存…"
        : noteState.dirty
          ? "等待保存…"
          : noteState.loaded
            ? "已保存"
            : "未加载";
}

function flushPendingNotesOnUnload() {
  Object.entries(state.noteStateByKnowledgeId).forEach(([knowledgeId, noteState]) => {
    if (!noteState.dirty || noteState.saving || noteState.error) return;
    fetch(`/api/library/${encodeURIComponent(knowledgeId)}/notes`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: noteState.content, revision: noteState.revision }),
      keepalive: true,
    });
  });
}

function insertNoteTimestamp() {
  if (!state.selectedKnowledgeId) { showToast("请先选择知识记录"); return; }
  const editor = $("#noteEditor");
  const timestamp = `[${formatTime(mediaController?.getCurrentTime() || state.currentTime || 0)}] `;
  editor.setRangeText(timestamp, editor.selectionStart, editor.selectionEnd, "end");
  editor.focus();
  saveNoteDraft();
}

async function loadJobHistory() {
  const root = $("#jobHistory");
  root.innerHTML = '<div class="task-history-empty">正在读取历史任务…</div>';
  try {
    const data = await api("/api/jobs");
    renderJobHistory(data.jobs || []);
  } catch (error) {
    root.innerHTML = `<div class="task-history-empty">历史任务读取失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderJobHistory(jobs) {
  const root = $("#jobHistory");
  if (!jobs.length) {
    root.innerHTML = '<div class="task-history-empty">暂无历史任务</div>';
    return;
  }
  root.innerHTML = jobs.slice(0, RECENT_JOB_LIMIT).map((job) => `
    <button type="button" class="task-history-item" data-job-knowledge="${escapeAttr(job.knowledgeId || "")}" ${job.knowledgeId ? "" : "disabled"}>
      <span><strong>${escapeHtml(job.knowledgeId || job.id)}</strong><small>${escapeHtml(formatJobTime(job.updatedAt || job.createdAt))}</small></span>
      <em class="${escapeAttr(job.status)}">${escapeHtml(jobStatusLabel(job.status))}</em>
    </button>`).join("");
  $$("[data-job-knowledge]", root).forEach((button) => button.addEventListener("click", async () => {
    const knowledgeId = button.dataset.jobKnowledge;
    if (!knowledgeId) return;
    $("#newTaskDialog").close();
    await loadKnowledge(knowledgeId, true);
  }));
}

function jobStatusLabel(status) {
  return ({ queued: "等待", running: "处理中", success: "完成", failed: "失败", interrupted: "已中断" })[status] || status;
}

function formatJobTime(value) {
  if (!value) return "";
  return new Date(Number(value) * 1000).toLocaleString("zh-CN", { hour12: false });
}

function setFollowMode(value) {
  state.transcriptFollowMode = value;
  $("#followPlayback").checked = value;
  $("#footerFollow").checked = value;
  localStorage.setItem(SETTINGS.transcriptFollowMode, String(value));
}

function setLibraryFilter(filter, button) {
  state.filter = filter;
  $$("[data-filter]").forEach((item) => {
    const active = item === button;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  renderLibrary();
}

function setLoadingState() {
  $("#sourceInfo").innerHTML = '<h1>正在加载记录…</h1><p>请稍候</p>';
  $("#summaryView").innerHTML = '<div class="result-empty"><p>正在读取知识包…</p></div>';
  $("#processingStatus").className = "processing-status ui-inline-status ui-inline-status--info";
  $("#processingStatus").innerHTML = '<span class="ui-spinner" aria-hidden="true"></span><span>加载中</span>';
}

function renderLoadError(message) {
  $("#summaryView").innerHTML = `<div class="result-empty"><h2>记录加载失败</h2><p>${escapeHtml(message)}</p><button class="quiet-button" id="retryLoad">重试</button></div>`;
  $("#retryLoad")?.addEventListener("click", () => loadKnowledge(state.selectedKnowledgeId, true));
}

function openOriginal() {
  const url = state.activeSource?.media?.externalUrl;
  if (isSafeHttpUrl(url)) window.open(url, "_blank", "noopener,noreferrer");
  else showToast("当前记录没有外部链接");
}

function openFile(name) {
  const url = state.activeSource?.files?.[name];
  if (url) window.open(url, "_blank", "noopener,noreferrer");
  else showToast(`${name} 不存在`);
}

function downloadFile(name, fallback = "") {
  const url = state.activeSource?.files?.[name] || (fallback ? state.activeSource?.files?.[fallback] : "");
  if (!url) { showToast(`${name} 不存在`); return; }
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
}

async function copyCurrentResult() {
  const name = state.activeResultTab === "summary" ? "index.md" : "transcript.grouped.md";
  const url = state.activeSource?.files?.[name];
  if (!url) { showToast(`${name} 不存在`); return; }
  try { copyText(await (await fetch(url)).text()); } catch { showToast("复制失败"); }
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); showToast("已复制"); }
  catch { showToast("浏览器未允许剪贴板访问"); }
}

function handleKeyboard(event) {
  if (event.defaultPrevented) return;
  if (trapLayerFocus(event)) return;
  const editing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if (event.ctrlKey && event.key.toLowerCase() === "k") { event.preventDefault(); focusSidebarSearch(); return; }
  if (event.key === "Escape") {
    const openDialogs = $$("dialog[open]");
    if (openDialogs.length) openDialogs.forEach((dialog) => dialog.close());
    else if (activeModalLayer()) closeActiveSheet(true);
    else if ($("#collaborationPane").contains(document.activeElement)) closeInspector(true);
    else if ($("#sidebar").contains(document.activeElement)) closeSidebar(true);
    else if (state.deleteMode) setDeleteMode(false);
    return;
  }
  if (editing) return;
  if (event.code === "Space") { event.preventDefault(); togglePlay(); }
  if (event.key === "ArrowLeft") { event.preventDefault(); seekPreview(Math.max(0, (mediaController?.getCurrentTime() || 0) - 5)); }
  if (event.key === "ArrowRight") { event.preventDefault(); seekPreview((mediaController?.getCurrentTime() || 0) + 5); }
}

function selectFromHash() {
  const id = decodeHashId();
  if (id && id !== state.selectedKnowledgeId) loadKnowledge(id);
}

function decodeHashId() {
  const match = location.hash.match(/^#\/knowledge\/(.+)$/);
  if (!match) return "";
  try { return decodeURIComponent(match[1]); } catch { return ""; }
}

function timestampLink(url, seconds) {
  if (!isSafeHttpUrl(url)) return "";
  const target = new URL(url);
  const host = target.hostname.toLowerCase();
  if (host.includes("youtube.com") || host === "youtu.be") target.searchParams.set("t", `${Math.floor(seconds)}s`);
  else if (host.includes("bilibili.com") || host === "b23.tv") target.searchParams.set("t", String(Math.floor(seconds)));
  else return url;
  return target.toString();
}

function statusLabel(status) {
  return ({ completed: "总结完成", transcript_completed: "转写完成，AI 分析未运行", completed_with_warnings: "部分完成", running: "处理中", processing: "处理中", created: "等待处理", failed: "处理失败", invalid: "知识包异常", unknown: "状态未知" })[status] || status || "状态未知";
}

function stageLabel(stage) {
  return ({ queued: "等待处理", resolve_source: "识别来源", collect_metadata: "读取来源信息", acquire_transcript: "获取字幕或转写", normalize_transcript: "标准化字幕", group_transcript: "字幕分组", build_timeline: "构建时间轴", run_analysis: "结构化分析", extract_frames: "生成关键帧", visual_analysis: "分析关键帧", highlight_snapshot: "生成教程截图", comments_fetch: "同步评论", comments_analysis: "评论区洞察", export_knowledge_package: "导出知识包" })[stage] || stage || "处理中";
}

function videoChatRouteLabel(route, status) {
  const label = ({ gemini_youtube_url: "YouTube 原生视频", gemini_files_api: "Files API 视频", gemini_frames_text: "关键帧+文本", text_only: "纯文本" })[route] || route;
  return status === "degraded" ? `${label}（已降级）` : label;
}

function platformLabel(platform) {
  const value = String(platform || "unknown").toLowerCase();
  if (value.includes("bilibili")) return "B站";
  if (value.includes("youtube")) return "YouTube";
  if (value === "local" || value === "local_file") return "本地媒体";
  return platform || "未知来源";
}

function providerLabel(provider) {
  if (state.uiMode !== "diagnostic") return "AI";
  const value = String(provider || "").toLowerCase();
  if (value.includes("deepseek")) return "DeepSeek";
  if (value.includes("gemini")) return "Gemini";
  return provider || "AI";
}

function formatTime(value) {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}` : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatPublished(value) {
  const text = String(value || "");
  return /^\d{8}$/.test(text) ? `${text.slice(0,4)}-${text.slice(4,6)}-${text.slice(6,8)}` : text;
}

function formatProcessingDuration(value) {
  const totalSeconds = Math.max(0, Math.floor((Number(value) || 0) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours) return `${hours}小时${minutes}分${seconds}秒`;
  if (minutes) return `${minutes}分${seconds}秒`;
  return `${seconds}秒`;
}

function updateProcessingTimers() {
  $$(".record-processing-time[data-processing-live='true']").forEach((element) => {
    const startedAt = Number(element.dataset.processingStartedAt) || 0;
    const fallback = Number(element.dataset.processingDuration) || 0;
    const elapsed = startedAt > 0 ? Math.max(fallback, Date.now() - startedAt) : fallback;
    element.textContent = `处理中 ${formatProcessingDuration(elapsed)}`;
  });
}

window.setInterval(updateProcessingTimers, 1000);

function formatRelativeDate(timestamp) {
  const delta = Math.max(0, Date.now() - Number(timestamp) * 1000);
  const days = Math.floor(delta / 86400000);
  if (days === 0) return "今天";
  if (days === 1) return "昨天";
  if (days < 30) return `${days}天前`;
  return new Date(Number(timestamp) * 1000).toLocaleDateString("zh-CN");
}

function isSafeHttpUrl(value) {
  try { return ["http:", "https:"].includes(new URL(value).protocol); } catch { return false; }
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

function escapeAttr(value) { return escapeHtml(value); }
function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function throttle(fn, delay) { let last = 0; return (...args) => { const now = Date.now(); if (now - last >= delay) { last = now; fn(...args); } }; }
