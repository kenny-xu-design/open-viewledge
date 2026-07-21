"use strict";

document.documentElement.dataset.uiVersion = "workspace-15";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const DEFAULT_MODULE_ORDER = ["result", "media", "collaboration"];
const EXPORT_SECTION_LABELS = { metadata: "基本信息", summary: "摘要", highlights: "亮点", prerequisites: "前置条件", steps: "操作步骤", glossary: "关键术语", thoughts: "思考", action_items: "可执行动作", warnings: "注意事项", chapters: "章节", keyframes: "关键帧", chat: "AI 对话", user_notes: "我的笔记", source_materials: "原文资料" };
const EXPORT_PRESETS = { light: ["metadata", "summary", "highlights", "chapters"], "summary-chat": ["metadata", "summary", "highlights", "chat", "user_notes"], full: Object.keys(EXPORT_SECTION_LABELS) };
const SETTINGS = {
  moduleOrder: "vs.moduleOrder",
  moduleWidths: "vs.moduleWidths",
  activeResultTab: "vs.activeResultTab",
  transcriptFollowMode: "vs.transcriptFollowMode",
  playbackRate: "vs.playbackRate",
};
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function uiScrollBehavior() {
  return typeof window.matchMedia === "function" && window.matchMedia(REDUCED_MOTION_QUERY).matches ? "auto" : "smooth";
}

const state = {
  selectedKnowledgeId: "",
  libraryItems: [],
  activeResultTab: localStorage.getItem(SETTINGS.activeResultTab) || "summary",
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
  deleteMode: false,
  selectedDeleteIds: new Set(),
  deleting: false,
  exportPreset: "full",
  exportSections: new Set(EXPORT_PRESETS.full),
  exportMarkdown: "",
};

const knowledgeCache = new Map();
let mediaController = null;
let toastTimer = 0;
let taskPoller = 0;
let activeSourceType = "url";

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
  constructor(element, videoId, source) { super(); this.element = element; this.videoId = videoId; this.load(source); }
  destroy() { this.element.src = "about:blank"; }
  play() { showToast("请在播放器内点击播放"); }
  seek() {}
  getCurrentTime() { return state.currentTime; }
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
  loadRuntimeInfo();
  loadProviderStatuses();
  setResultTab(state.activeResultTab, false);
  $("#followPlayback").checked = state.transcriptFollowMode;
  $("#footerFollow").checked = state.transcriptFollowMode;
  await refreshLibrary();
}

async function loadRuntimeInfo() {
  try {
    const runtime = await api("/api/runtime");
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
    [$("#taskRuntime"), $("#settingsRuntime")].forEach((element) => {
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
  $("#newSummary").addEventListener("click", openNewTask);
  $("#refreshJobs").addEventListener("click", loadJobHistory);
  $("#focusSearch").addEventListener("click", focusSidebarSearch);
  $("#librarySearch").addEventListener("input", renderLibrary);
  $("#refreshLibrary").addEventListener("click", refreshLibrary);
  $("#toggleDeleteMode").addEventListener("click", handleDeleteAction);
  $("#confirmDeleteKnowledge").addEventListener("click", confirmDeleteKnowledge);
  $("#reloadKnowledge").addEventListener("click", () => state.selectedKnowledgeId && loadKnowledge(state.selectedKnowledgeId, true));
  $("#toggleSidebar").addEventListener("click", toggleSidebar);
  $("#collapseSidebar").addEventListener("click", toggleSidebar);
  $("#mobileMenu").addEventListener("click", () => $("#app").classList.add("drawer-open"));
  $("#drawerScrim").addEventListener("click", closeDrawer);
  $("#summarySettings").addEventListener("click", () => $("#settingsDialog").showModal());
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
  $("#expandChat").addEventListener("click", () => { setMobileView("collaboration"); $("#chatPane").scrollIntoView({ behavior: uiScrollBehavior(), block: "start" }); });
  $("#playbackRate").addEventListener("change", (event) => setPlaybackRate(Number(event.target.value)));
  $("#followPlayback").addEventListener("change", (event) => setFollowMode(event.target.checked));
  $("#footerFollow").addEventListener("change", (event) => setFollowMode(event.target.checked));
  $("#resultScroll").addEventListener("scroll", () => state.scrollPositions[state.activeResultTab] = $("#resultScroll").scrollTop, { passive: true });

  $$("[data-result-tab]").forEach((button) => button.addEventListener("click", () => setResultTab(button.dataset.resultTab)));
  $$("[data-mobile-tab]").forEach((button) => button.addEventListener("click", () => setMobileView(button.dataset.mobileTab)));
  $$("[data-media]").forEach((button) => button.addEventListener("click", () => handleMediaAction(button.dataset.media)));
  $$("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  $$("[data-filter]").forEach((button) => button.addEventListener("click", () => setLibraryFilter(button.dataset.filter, button)));
  $$("[data-source-type]").forEach((button) => button.addEventListener("click", () => setTaskSourceType(button.dataset.sourceType)));

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
    if (target) seekTo(Number(target.dataset.seek));
  });
  $("#chatHistory").addEventListener("click", (event) => {
    const target = event.target.closest("[data-seek]");
    if (target) seekTo(Number(target.dataset.seek));
    if (event.target.closest("[data-regenerate]")) regenerateLastAnswer();
  });
  $("#noteEditor").addEventListener("input", saveNoteDraft);
  $("#insertTimestamp").addEventListener("click", insertNoteTimestamp);
  $$('[id^="layoutPosition"]').forEach((select) => select.addEventListener("change", updateLayoutFromControls));
  $("#resetLayout").addEventListener("click", resetWorkspaceLayout);
  $("#newTaskForm").addEventListener("submit", submitTask);
  $("#paneResizer").addEventListener("pointerdown", startResize);
  $("#rightPaneResizer").addEventListener("pointerdown", startResize);
  $$(".pane-resizer").forEach((resizer) => resizer.addEventListener("dblclick", resetModuleWidths));
  document.addEventListener("keydown", handleKeyboard);
  window.addEventListener("hashchange", selectFromHash);
  window.addEventListener("resize", () => window.innerWidth >= 980 && closeDrawer());
  window.addEventListener("beforeunload", () => {
    clearInterval(taskPoller);
    flushPendingNotesOnUnload();
  });
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
    state.providerStatuses = Object.fromEntries((data.providers || []).map((item) => [item.name, item]));
  } catch (error) {
    state.providerStatuses = {};
  }
  renderProviderStatus();
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
      <span class="record-copy"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(platformLabel(item.platform))} · ${formatRelativeDate(item.updatedAt)}</small></span>
      <span class="record-state ${escapeAttr(item.status)}" aria-label="${escapeAttr(statusLabel(item.status))}"></span>
    </button>`;
  }).join("");
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
  closeDrawer();
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
  renderStatus(knowledge.manifest || {});
  renderSummary(knowledge);
  renderInsightPanel(knowledge);
  renderQuestionChips(knowledge.analysis?.thoughts || []);
  renderChatHistory();
  renderNoteState(knowledge.id);
  $("#workspaceTitle").textContent = knowledge.source?.title || knowledge.id || "视频知识工作台";
  const model = knowledge.manifest?.llm_model || knowledge.analysis?.model || "";
  const provider = knowledge.manifest?.llm_provider || knowledge.analysis?.provider || "";
  $("#modelBadge").textContent = model ? `${providerLabel(provider)} · ${model}` : "未运行 AI 分析";
  $("#modelBadge").title = model ? `本知识包实际使用模型：${model}` : "当前知识包未记录分析模型";
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
  const failed = knowledge.analysis?.status === "failed" || knowledge.inspection?.analysis_status === "invalid";
  button.classList.toggle("hidden", !failed);
  button.disabled = !failed;
  button.removeAttribute("aria-busy");
}

async function retryAnalysis() {
  const knowledgeId = state.selectedKnowledgeId;
  if (!knowledgeId) return;
  const button = $("#retryAnalysis");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.title = "正在重新生成摘要";
  showToast("正在重新生成摘要，仅重新执行 AI 分析…");
  try {
    const data = await api(`/api/library/${encodeURIComponent(knowledgeId)}/analysis/retry`, {
      method: "POST",
      body: "{}",
    });
    knowledgeCache.set(knowledgeId, data.knowledge);
    state.activeSource = data.knowledge;
    renderKnowledge(data.knowledge);
    showToast("摘要已重新生成");
  } catch (error) {
    knowledgeCache.delete(knowledgeId);
    showToast(`重新生成摘要失败：${error.message}`);
    await loadKnowledge(knowledgeId, true);
  } finally {
    button.title = "重新生成摘要";
    button.removeAttribute("aria-busy");
  }
}

function renderMedia(knowledge) {
  const surface = $("#mediaSurface");
  const media = knowledge.media || {};
  surface.className = "media-surface";
  surface.innerHTML = "";
  if (media.kind === "video" && media.available) {
    const video = document.createElement("video");
    video.src = media.url;
    video.preload = "metadata";
    video.playsInline = true;
    video.addEventListener("timeupdate", throttle(handleTimeUpdate, 300));
    video.addEventListener("loadedmetadata", updateTimeDisplay);
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
    mediaController = new BilibiliEmbedController(player, media.embed.videoId, knowledge.source);
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
  const externallyControlled = mediaController instanceof BilibiliEmbedController || mediaController instanceof ExternalLinkController;
  $$('[data-media="play"], [data-media="back"], [data-media="forward"]').forEach((button) => {
    button.disabled = externallyControlled;
    button.title = externallyControlled ? "当前平台播放器需在播放器内控制；时间引用会在原网站打开" : "";
  });
  $("#playbackRate").disabled = !seekable;
  $('[data-media="repeat"]').disabled = !htmlMedia;
  $('[data-media="fullscreen"]').disabled = !(htmlMedia || iframeMedia);
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
  if (message) {
    const notice = document.createElement("span");
    notice.className = "external-notice";
    notice.textContent = message;
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

function renderStatus(manifest) {
  const element = $("#processingStatus");
  const status = manifest.status || "unknown";
  let className = "";
  if (status === "completed") className = "success";
  else if (status === "completed_with_warnings") className = "warning";
  else if (status === "failed" || status === "invalid") className = "error";
  const errors = Array.isArray(manifest.errors) && manifest.errors.length ? ` · ${manifest.errors[0]}` : "";
  element.className = `processing-status ${className}`;
  element.innerHTML = `<svg><use href="#${className === "error" || className === "warning" ? "i-warning" : "i-check"}"/></svg><span>${escapeHtml(statusLabel(status))}${manifest.current_stage ? ` · ${escapeHtml(stageLabel(manifest.current_stage))}` : ""}${escapeHtml(errors)}</span>`;
}

function renderSummary(knowledge) {
  const analysis = knowledge.analysis || {};
  const timeline = Array.isArray(knowledge.timeline) ? knowledge.timeline : [];
  const sections = [];
  if (analysis.summary) sections.push(`<section class="result-section"><h2>摘要</h2><p>${escapeHtml(analysis.summary)}</p></section>`);
  else if (analysis.status === "failed") sections.push(`<div class="analysis-empty">AI 分析失败：${escapeHtml(analysis.error || "请检查 DeepSeek 配置后重试。")} 字幕和时间轴仍可正常查看。</div>`);
  else sections.push('<div class="analysis-empty">AI 分析已跳过。字幕、时间轴和原文细读仍可正常查看。</div>');

  if (Array.isArray(analysis.highlights) && analysis.highlights.length) {
    sections.push(`<section class="result-section"><h2>亮点</h2><ul class="highlight-list">${analysis.highlights.map((item) => `
      <li class="highlight-item"><span class="highlight-icon">${escapeHtml(item.icon || "◆")}</span><div class="highlight-copy"><strong>${escapeHtml(item.title || "亮点")}</strong>${item.explanation ? `<p>${escapeHtml(item.explanation)}</p>` : ""}<div class="tag-list">${(item.tags || []).map((tag) => `<button class="tag-button" data-tag="${escapeAttr(tag)}">#${escapeHtml(tag)}</button>`).join("")}</div></div></li>`).join("")}</ul></section>`);
  }
  if (Array.isArray(analysis.thoughts) && analysis.thoughts.length) {
    sections.push(`<section class="result-section"><h2>思考</h2><ol class="thought-list">${analysis.thoughts.slice(0, 3).map((item) => `<li><button class="thought-button" data-question="${escapeAttr(item.question || "")}">${escapeHtml(item.question || "")}</button></li>`).join("")}</ol></section>`);
  }

  const chapters = Array.isArray(analysis.chapters) && analysis.chapters.length ? analysis.chapters : timeline;
  if (chapters.length) {
    sections.push(`<section class="result-section" id="chapterSection"><h2>视频章节总结</h2><div class="chapter-list">${chapters.map((chapter, index) => renderChapter(chapter, index, knowledge.id)).join("")}</div></section>`);
  }
  sections.push(`<section class="result-section"><h2>原文资料</h2><div class="source-entry"><button class="quiet-button" data-open-transcript>查看分组字幕</button>${knowledge.files?.["transcript.raw.jsonl"] ? '<button class="icon-button small" data-open-raw aria-label="打开逐句原始数据"><svg><use href="#i-file"/></svg></button>' : ""}</div></section>`);
  $("#summaryView").innerHTML = sections.join("");
}

function renderInsightPanel(knowledge) {
  const highlights = Array.isArray(knowledge.analysis?.highlights) ? knowledge.analysis.highlights : [];
  const timeline = Array.isArray(knowledge.timeline) ? knowledge.timeline : [];
  const source = highlights.length ? highlights : timeline;
  const usingHighlights = highlights.length > 0;
  $("#insightMode").textContent = usingHighlights ? "AI 结果" : "字幕时间轴";
  $("#insightCount").textContent = source.length;
  if (!source.length) {
    $("#insightContent").innerHTML = '<div class="module-empty">当前知识包没有高光或时间轴数据。</div>';
    return;
  }
  $("#insightContent").innerHTML = source.map((item, index) => {
    const hasTime = item.start != null && Number.isFinite(Number(item.start));
    const detail = usingHighlights ? item.explanation : item.summary;
    const tags = usingHighlights ? (item.tags || []) : (item.keywords || []);
    return `<article class="insight-item" data-insight-index="${index}">
      <div class="insight-row">
        <span class="insight-marker ${usingHighlights ? "ai" : "timeline"}"></span>
        <strong>${escapeHtml(item.title || (usingHighlights ? `高光 ${index + 1}` : `片段 ${index + 1}`))}</strong>
        ${hasTime ? `<button class="timestamp-button" data-seek="${Number(item.start)}">${formatTime(item.start)}</button>` : ""}
      </div>
      ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
      ${tags.length ? `<div class="tag-list">${tags.slice(0, 5).map((tag) => `<span class="static-tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
    </article>`;
  }).join("");
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

function handleResultClick(event) {
  const seek = event.target.closest("[data-seek]");
  if (seek) { event.preventDefault(); event.stopPropagation(); seekTo(Number(seek.dataset.seek)); return; }
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
  if (seek) { seekTo(Number(seek.dataset.seek)); return; }
  const copy = event.target.closest("[data-copy-group]");
  if (copy) {
    const group = state.transcriptGroups.find((item) => String(item.index) === copy.dataset.copyGroup);
    if (group) copyText(`${formatTime(group.start)}–${formatTime(group.end)} ${group.title}\n\n${group.text}`);
  }
}

function handleMediaAction(action) {
  if (!mediaController) return;
  if (action === "play") togglePlay();
  else if (action === "back") seekTo(Math.max(0, mediaController.getCurrentTime() - 10));
  else if (action === "forward") seekTo(mediaController.getCurrentTime() + 10);
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

function seekTo(seconds) {
  state.currentTime = Math.max(0, seconds || 0);
  if (mediaController?.supportsSeek()) mediaController.seek(state.currentTime);
  else mediaController?.openExternally(state.currentTime);
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
    chatState.messages.push({ role: "assistant", content: data.answer || "", citations: data.citations || [], provider: data.provider || "", model: data.model || "", warning: data.warning || "" });
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
    const modelHtml = item.role === "assistant" && item.model ? `<small class="chat-model">${escapeHtml(providerLabel(item.provider))} · ${escapeHtml(item.model)} · ${citations.length} 条证据 <button type="button" data-regenerate>重新生成</button></small>` : "";
    return `<div class="chat-message ${escapeAttr(item.role)}"><div>${escapeHtml(item.content)}</div>${warningHtml}${citationHtml}${modelHtml}</div>`;
  }).join("") : '<div class="chat-empty">针对当前视频提问，回答会附带可跳转的字幕时间引用。</div>';
  if (currentChatState().loading) root.insertAdjacentHTML("beforeend", '<div class="chat-message assistant loading">正在检索当前视频并请求模型…</div>');
  root.scrollTop = root.scrollHeight;
}

function focusChatQuestion(question) {
  $("#chatInput").value = question || "";
  setMobileView("collaboration");
  $("#chatPane").scrollIntoView({ behavior: uiScrollBehavior(), block: "start" });
  setTimeout(() => $("#chatInput").focus(), 200);
}

function openNewTask() {
  $("#taskProgress").classList.add("hidden");
  $("#newTaskForm").reset();
  $("#taskFrames").checked = true;
  setTaskSourceType("url");
  $("#newTaskDialog").showModal();
  loadJobHistory();
}

function setTaskSourceType(type) {
  activeSourceType = type === "file" ? "file" : "url";
  $$("[data-source-type]").forEach((button) => button.classList.toggle("active", button.dataset.sourceType === activeSourceType));
  $("#taskSourceLabel").textContent = activeSourceType === "url" ? "视频链接" : "本地文件路径";
  $("#taskSource").placeholder = activeSourceType === "url" ? "https://www.bilibili.com/video/BV…" : "E:\\Downloads_E\\video.mp4";
}

async function submitTask(event) {
  event.preventDefault();
  const payload = {
    sourceType: activeSourceType,
    source: $("#taskSource").value,
    backend: $("#taskBackend").value,
    mode: $("#taskMode").value,
    lang: $("#taskLanguage").value,
    export: $("#taskExport").value,
    noFrames: !$("#taskFrames").checked,
    noSummary: $("#taskNoSummary").checked,
    sampleSeconds: $("#taskSampleSeconds").value,
  };
  const button = $("#startTask");
  button.disabled = true;
  try {
    const data = await api("/api/process", { method: "POST", body: JSON.stringify(payload) });
    state.taskStatus = data.job;
    $("#taskProgress").classList.remove("hidden");
    pollTask(data.job.id);
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
  }
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
        $("#startTask").disabled = false;
        if (data.job.status === "success") {
          await refreshLibrary();
          const outputId = (data.job.outputDir || "").split("/").pop();
          if (outputId) await loadKnowledge(outputId, true);
          setTimeout(() => $("#newTaskDialog").close(), 700);
        }
      }
    } catch (error) {
      clearInterval(taskPoller);
      showToast(error.message);
    }
  };
  update();
  taskPoller = setInterval(update, 1400);
}

function renderTaskProgress(job) {
  const stageOrder = ["resolve_source", "collect_metadata", "acquire_transcript", "normalize_transcript", "group_transcript", "build_timeline", "extract_frames", "run_analysis", "export_knowledge_package"];
  const logs = job.logs || [];
  const latestStage = [...logs].reverse().find((line) => line.includes("阶段：")) || "";
  const stage = latestStage.split("阶段：").pop();
  const stageIndex = Math.max(0, stageOrder.indexOf(stage));
  const terminal = ["success", "failed", "interrupted"].includes(job.status);
  const percent = terminal ? 100 : Math.max(8, Math.round(((stageIndex + 1) / stageOrder.length) * 100));
  $("#taskStatusText").textContent = job.status === "failed"
    ? (job.error || "处理失败")
    : job.status === "interrupted"
      ? (job.error || "任务已中断")
      : job.status === "success"
        ? "处理完成"
        : stageLabel(stage || "queued");
  $("#taskPercent").textContent = `${percent}%`;
  $("#progressBar").style.width = `${percent}%`;
  $("#taskLogs").textContent = logs.slice(-10).join("\n") || "等待任务日志…";
}

function toggleSidebar() {
  $("#app").classList.toggle("drawer-open");
}

function closeDrawer() { $("#app").classList.remove("drawer-open"); }
function focusSidebarSearch() { $("#app").classList.add("drawer-open"); setTimeout(() => $("#librarySearch").focus(), 80); }

function startResize(event) {
  if (window.innerWidth < 1180) return;
  const resizer = event.currentTarget;
  const dividerOrder = Number(resizer.style.order);
  const modules = $$(".workspace-module").sort((a, b) => Number(a.style.order) - Number(b.style.order));
  const left = [...modules].reverse().find((module) => Number(module.style.order) < dividerOrder);
  const right = modules.find((module) => Number(module.style.order) > dividerOrder);
  if (!left || !right) return;
  const startX = event.clientX;
  const leftWidth = left.getBoundingClientRect().width;
  const rightWidth = right.getBoundingClientRect().width;
  resizer.setPointerCapture(event.pointerId);
  resizer.classList.add("dragging");
  const move = (moveEvent) => {
    const delta = moveEvent.clientX - startX;
    const nextLeft = clamp(leftWidth + delta, 300, leftWidth + rightWidth - 300);
    const nextRight = leftWidth + rightWidth - nextLeft;
    left.style.flexBasis = `${nextLeft}px`;
    right.style.flexBasis = `${nextRight}px`;
    state.moduleWidths[left.dataset.module] = Math.round(nextLeft);
    state.moduleWidths[right.dataset.module] = Math.round(nextRight);
  };
  const end = () => {
    resizer.classList.remove("dragging");
    resizer.removeEventListener("pointermove", move);
    resizer.removeEventListener("pointerup", end);
    localStorage.setItem(SETTINGS.moduleWidths, JSON.stringify(state.moduleWidths));
  };
  resizer.addEventListener("pointermove", move);
  resizer.addEventListener("pointerup", end);
}

function resetModuleWidths() {
  state.moduleWidths = {};
  localStorage.removeItem(SETTINGS.moduleWidths);
  $$(".workspace-module").forEach((module) => module.style.removeProperty("flex-basis"));
}

function setMobileView(view) {
  const next = ["result", "media", "collaboration"].includes(view) ? view : "result";
  $("#app").dataset.mobileView = next;
  $$("[data-mobile-tab]").forEach((button) => button.setAttribute("aria-selected", String(button.dataset.mobileTab === next)));
}

function openLayoutSettings() {
  syncLayoutControls();
  $("#layoutDialog").showModal();
}

function syncLayoutControls() {
  state.moduleOrder.forEach((module, index) => {
    $(`#layoutPosition${index + 1}`).value = module;
  });
}

function updateLayoutFromControls(event) {
  const selects = [$("#layoutPosition1"), $("#layoutPosition2"), $("#layoutPosition3")];
  const changedIndex = selects.indexOf(event.currentTarget);
  const selected = event.currentTarget.value;
  const duplicateIndex = selects.findIndex((select, index) => index !== changedIndex && select.value === selected);
  if (duplicateIndex >= 0) selects[duplicateIndex].value = state.moduleOrder[changedIndex];
  state.moduleOrder = selects.map((select) => select.value);
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
  return Array.isArray(value) && value.length === 3 && new Set(value).size === 3 && value.every((item) => DEFAULT_MODULE_ORDER.includes(item))
    ? value
    : [...DEFAULT_MODULE_ORDER];
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
  root.innerHTML = jobs.slice(0, 8).map((job) => `
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
  $$("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
  renderLibrary();
}

function setLoadingState() {
  $("#sourceInfo").innerHTML = '<h1>正在加载记录…</h1><p>请稍候</p>';
  $("#summaryView").innerHTML = '<div class="result-empty"><p>正在读取知识包…</p></div>';
  $("#processingStatus").className = "processing-status";
  $("#processingStatus").innerHTML = '<svg><use href="#i-refresh"/></svg><span>加载中</span>';
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
  const editing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if (event.ctrlKey && event.key.toLowerCase() === "k") { event.preventDefault(); focusSidebarSearch(); return; }
  if (event.key === "Escape") {
    closeDrawer();
    const openDialogs = $$("dialog[open]");
    if (openDialogs.length) openDialogs.forEach((dialog) => dialog.close());
    else if (state.deleteMode) setDeleteMode(false);
    return;
  }
  if (editing) return;
  if (event.code === "Space") { event.preventDefault(); togglePlay(); }
  if (event.key === "ArrowLeft") { event.preventDefault(); seekTo(Math.max(0, (mediaController?.getCurrentTime() || 0) - 5)); }
  if (event.key === "ArrowRight") { event.preventDefault(); seekTo((mediaController?.getCurrentTime() || 0) + 5); }
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
  const host = new URL(url).hostname.toLowerCase();
  const separator = url.includes("?") ? "&" : "?";
  if (host.includes("youtube.com") || host === "youtu.be") return `${url}${separator}t=${Math.floor(seconds)}s`;
  if (host.includes("bilibili.com") || host === "b23.tv") return `${url}${separator}t=${Math.floor(seconds)}`;
  return url;
}

function statusLabel(status) {
  return ({ completed: "总结完成", completed_with_warnings: "部分完成", running: "处理中", processing: "处理中", created: "等待处理", failed: "处理失败", invalid: "知识包异常", unknown: "状态未知" })[status] || status || "状态未知";
}

function stageLabel(stage) {
  return ({ queued: "等待处理", resolve_source: "识别来源", collect_metadata: "读取来源信息", acquire_transcript: "获取字幕或转写", normalize_transcript: "标准化字幕", group_transcript: "字幕分组", build_timeline: "构建时间轴", extract_frames: "生成关键帧", run_analysis: "结构化分析", export_knowledge_package: "导出知识包" })[stage] || stage || "处理中";
}

function platformLabel(platform) {
  const value = String(platform || "unknown").toLowerCase();
  if (value.includes("bilibili")) return "B站";
  if (value.includes("youtube")) return "YouTube";
  if (value === "local" || value === "local_file") return "本地媒体";
  return platform || "未知来源";
}

function providerLabel(provider) {
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
