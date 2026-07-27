# Changelog

All notable changes to this project are documented in this file.

## [1.4.3] - 2026-07-28

- Added local faster-whisper `fast`, `balanced`, and `quality` routing with
  bounded CUDA preflight, adaptive batches, quality guards, and safe CPU fallback.
- Added Windows project-venv CUDA 12 cuBLAS/cuDNN dependencies and startup DLL
  discovery for Web and spawned GPU preflight processes.
- Replaced the `doctor` writable-directory `mkstemp` probe with a deterministic,
  cleaned probe file to avoid hangs on synchronized/shared Windows directories.
- Current release-candidate QA passes 312 unit tests, compileall, CLI/Web help,
  `pip check`, JavaScript syntax and diff checks. Fixed Chinese, English and
  mixed ASR samples complete with both small and turbo CUDA FP16. Default
  balanced routing selects local turbo on the audited RTX 5060 Ti.
- Fixed transcript-only state propagation so AI analysis is skipped only after
  an explicit user request. Analysis failures and timeouts now remain distinct,
  transcript and analysis readiness are evaluated independently, and existing
  transcripts can run analysis without media download or ASR.
- Added a knowledge-detail “仅运行 AI 分析” action and corrected transcript-only
  completion copy so it no longer reports “总结完成”.
- Added unified platform/Groq/local transcription routing, Groq audio chunking,
  bounded cloud-to-GPU-to-CPU fallback, and per-record processing-duration timers.

### Added

- Stable public `analyze`, `inspect`, `export`, `resume`, `doctor`, and `config` commands.
- Versioned JSON result envelopes and JSONL task/stage/artifact lifecycle events.
- Central exit-code contract and secret-free resumable CLI task records.
- Doctor checks for runtime tools, local models, Providers, storage, and Schema versions.
- Explicit Schema compatibility rules for configuration, tasks, manifests, analysis, and export requests.
- CLI contract, exit-code, Schema, lifecycle, migration, release, security, and privacy documentation.
- Cupertino AppShell structure with unified Sidebar, Toolbar, primary content region, and responsive Inspector shell.
- Accessible Sidebar, Inspector, and split-view divider behavior, including focus return and keyboard resizing.
- Unified `seekPreview(seconds)` handling for local media, YouTube, and Bilibili preview timestamp clicks.
- Local video display ratio controls for original, 16:9, 4:3, 1:1, and 9:16, with fit/fill display modes.
- Safer knowledge-record deletion with path validation, recursive directory handling, clearer API errors, and regression tests.
- v1.4 processing profiles, cache-aware subtitle-first fast path, and first-readable-result timing.
- Optional v1.4 visual analysis and bounded `tutorial + complete` step screenshots under `assets/tutorial/` that preserve text on failure.
- Gemini video chat routing through public YouTube URL, Files API, keyframes plus text, and text-only fallback with recoverable local route state.
- Explicit v1.4 comment sync with normalized public comments and independent comment-insight artifacts.
- Local Web API configuration entry for DeepSeek/OpenAI-compatible and Gemini real-interaction testing, with process-memory API Keys, masked status, test connection, apply, and clear actions.
- Dedicated v1.4.3 `content` contracts for `summary`, `tutorial`, `viral`, and `close-reading`, with a shared analysis envelope and legacy field compatibility.
- Adaptive long-video segmentation for v1.4.3, including duration/density policy routing, semantic windows, reducer metadata, coverage-gap checks, and tutorial chapter/step hierarchy.

### Changed

- Web processing now invokes the public `analyze --jsonl` command and consumes lifecycle events.
- Agent Skill now documents only public CLI usage and result/error handling.
- Pipeline and local Whisper diagnostics are routed to stderr while stdout remains machine-readable.
- Root-level analyze options remain as an explicitly deprecated compatibility path.
- Web UI layout now uses one AppShell generation instead of the legacy competing three/four-column layout rules.
- Bilibili timestamp clicks stay inside the preview area by reloading the embedded player URL instead of opening the original source link.
- v1.4.3 comment insights are shown in the video-side feature area as a peer tab beside AI highlights, instead of being appended to the main factual summary.
- Web summary tasks, comment insights, Gemini visual analysis, Gemini video chat, and right-side AI chat now resolve Provider settings through the same Web session/environment/default priority chain.
- All four analysis profiles now use the restored flat summary base: summary, conditional professional terms, highlights, thoughts, video chapter summary, and source materials.
- `tutorial`, `viral`, and `close-reading` retain their requested mode-specific details, but render only populated modules instead of fixed “未明确说明” placeholders.
- Long-video reduction preserves specialized `tutorial`, `viral`, and `close-reading` details and merges 3–8 reliable professional terms for every profile.
- Screenshot export is restricted to `tutorial + complete`; `summary`, `viral`, and `close-reading` can use textual visual observations but do not export images.
- Dense long videos no longer rely on one global Top list; window candidates are merged and checked for coverage before final chapters, highlights, and tutorial steps are written.
- Adaptive long-video routing remains responsible only for windowing, density guidance, and hierarchical reduction; it does not define standard-summary heading order.

### Fixed

- DeepSeek HTTP 400 failures now surface the sanitized upstream model/configuration message so unsupported model names can be corrected without exposing secrets.
- Web job listing and job-detail APIs snapshot task state before formatting responses, avoiding lock re-entry that could leave the task UI stuck on “处理中”.
- Web job persistence avoids the Windows `tempfile.mkstemp` hang observed in this environment by writing through a deterministic temporary file before atomic replace.
- Provider test-connection errors are classified and sanitized for missing Key, invalid Key, wrong Base URL, wrong model, bad request, rate limit, timeout, and upstream failures.

### Verification

- Focused Web UI/API tests pass: `python -m unittest tests.test_web_ui tests.test_web` reports 78 tests.
- `node --check src/web_ui/app.js` and `git diff --check` were used during the v1.3.1 implementation pass.
- v1.4.3 final QA on `feat/v1.4-processing-pipeline` passes: focused comment/Web/export tests report 99 tests, full `unittest discover` reports 237 tests, `compileall`, CLI/Web help, `node --check`, and `git diff --check` pass.
- v1.4.3 browser spot-check confirms `评论区` and `高光片段` render as peer video-side tabs, with comment insights kept out of the left factual summary.
- v1.4.3 Web API configuration increment adds Provider config tests; full local unit coverage now reports 249 tests.
- v1.4.3 standard-summary correction passes 85 focused analysis/segmentation/export/Web UI tests and all 271 unit tests, plus compileall, CLI/Web help, JavaScript syntax, and diff checks.
- Final stable source-package verification on 2026-07-28 passes all 327 unit
  tests, compileall, CLI/Web help, JavaScript syntax, diff checks, and tracked
  source credential scanning.

## [1.2.1] - 2026-07-20

### Added

- Unified analysis-profile resolution with tutorial detection and backward-compatible learning fields.
- Platform-aware timestamp formatting and targets shared by timelines and Markdown exports.
- Selectable Markdown rendering for summary, chat, user notes, tutorial sections, and source materials.
- Safe local Obsidian Vault writes, conflict uniquifying, URI generation, CLI export, Web API, and an original export panel.

### Changed

- Main and compatible notes now share one structured Markdown renderer.
- Package version advanced to 1.2.1.

## [1.2.0] - 2026-07-16

### Added

- Read-only knowledge-package inspection with JSON output and meaningful exit codes.
- Durable `user_notes.md` storage with revision conflict detection and compatible Markdown refresh.
- Durable local Web job history with interrupted-job recovery.
- Testable Gemini keyframe image-request and analysis-service boundaries.
- Shared project version metadata and CLI/Web version reporting.
- Web UI action for retrying failed AI analysis from an existing transcript without reprocessing media.
- Confirmed multi-select deletion for completed knowledge records, restricted to validated package directories.

### Changed

- Unified FFmpeg and FFprobe discovery across CLI processing and Web diagnostics.
- Prevented multiple Windows Web UI processes from sharing port 5188 and serving mixed code versions.
- Renamed the sidebar groups to “资源库” and “产出库”.
- Centralized DeepSeek and Gemini model defaults and runtime reporting.
- Tightened manifest, transcript, timeline, and analysis consistency validation.
- Clarified Bilibili iframe control limits and Obsidian-compatible Markdown scope.
- Updated README, Agent Skill, architecture, decisions, and roadmap to match active behavior.

### Removed

- Unreachable legacy CLI processing branch.
- Retired adapter package, Ollama summarizer, and legacy LLM adapter.
- Active comment-analysis route; `--comments` remains only as a compatibility warning.

### Verification

- 147 unit tests pass.
- `python -m compileall src` passes.
- `python -m src.main --help` and `python -m src.web --help` pass.
- Gemini image input is mock verified only; no real Gemini API request was made.

### Known Limits

- Gemini keyframe analysis has no CLI or Web product trigger in v1.2.
- Bilibili iframe playback cannot be reliably synchronized by the application.
- Obsidian output is compatible Markdown, not Vault synchronization.
- Scale and SaaS infrastructure are outside v1.2.
