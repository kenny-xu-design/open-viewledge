# Current Task

Last updated: 2026-07-26

## Active Work

v1.4.3 评论同步、Web API 配置、四种分析模式输出结构，以及自适应长视频分层分析收尾。

Repository: `E:\AGT\git\video-summary-skill`

Branch: `feat/v1.4-processing-pipeline`

Baseline: v1.4.2 visual pipeline, highlight snapshots, and Gemini video chat implementation on this branch.

## Scope

This task implements the reviewed v1.4.3 work unit on top of the v1.4.2 implementation.

In scope:

- Explicit `--comments` / Web task checkbox to enable public comment sync.
- YouTube, Bilibili, and generic `yt-dlp` comment adapter boundaries.
- Normalized public comment records without private profile URLs, cookies, credentials, or secrets.
- `comments_fetch` and `comments_analysis` stages with soft-failure behavior.
- Package outputs: `comments.json`, `comments.md`, `comment_insights.json`, and `comment_insights.md`.
- Comment timestamps that use the existing preview seek target behavior.
- Export and Web knowledge detail support for separate comment insights.
- Web knowledge detail video-side feature tabs: `评论区` and `高光片段` as peer functions below the preview.
- DeepSeek HTTP 400 diagnostics for unsupported model/configuration errors.
- Web task-state fixes for job listing/detail lock re-entry and Windows job-store atomic writes.
- Local Web API configuration entry for DeepSeek/OpenAI-compatible and Gemini real-interaction testing.
- Dedicated output structures for `summary`, `tutorial`, `viral`, and `close-reading` using a shared envelope plus mode-specific `content`.
- Corrected standard-summary contract with six core sections and a conditional same-call `professional_terms` module; adaptive long-video windows and reducer coverage remain enabled.
- `tutorial + complete` step screenshots under `assets/tutorial/`; other analysis modes do not export screenshots.
- Adaptive segmentation policy routing based on duration, transcript density, profile, processing mode, native chapters and visual availability.
- Windowed map/reduce text analysis for dense 30-minute-plus videos and default layered analysis for dense 60-minute-plus videos.
- Coverage guard for overlarge chapter/step gaps, with repair based only on real transcript groups and no midpoint-only fake insertion.
- Tutorial hierarchy that separates top-level chapters from `tutorial_steps`.

Out of scope:

- Private API use, browser automation, login-gated comments, cookies, or platform bypass.
- Writing comment opinions into `analysis.json` or the main factual summary.
- Durable queue, batch processing, worker leases, or ASR worker changes.
- Real platform claims without fixed YouTube/Bilibili manual acceptance.
- Persisting API Keys to files, frontend storage, job records, knowledge packages, Markdown, exports, or repository files.
- Merging comment insights into the main analysis report.
- Starting v1.4.4 ASR/worker performance work.
- Committing, pushing, merging, rebasing, tagging, or releasing.

## Current Findings

- Current processing remains a single serial `PipelineOrchestrator.run()` flow.
- Web processing starts the public CLI with `--jsonl`; Web does not execute the media pipeline directly.
- Comment sync is explicit opt-in and disabled by default.
- Comment failures are captured as stage warnings and do not fail text summaries or knowledge package export.
- Comment insight uses DeepSeek JSON mode when configured and falls back to a local heuristic when no Provider is available.
- Comment insights stay out of the left-side `全文总结`; the video lower feature region now switches between `评论区` and `高光片段`.
- One real Bilibili knowledge package was retried after fixing the DeepSeek model configuration and completed text analysis plus comment insight generation.
- `/api/jobs` and `/api/jobs/{id}` now snapshot job state before response formatting, preventing lock re-entry while the UI polls task state.
- Web job persistence now writes through a deterministic temporary file and `os.replace`, avoiding the observed Windows `tempfile.mkstemp` hang.
- DeepSeek HTTP 400 errors include sanitized upstream details, making unsupported model-name failures actionable without exposing secrets.
- Web now exposes API configuration status/apply/clear/test endpoints. API Keys are process-local only; status returns only provider, source, Base URL, model, configured state, Key tail, and sanitized last-test result.
- Provider resolution priority is Web session configuration, then environment variables, then project defaults. Web-launched CLI tasks receive the same session configuration through transient subprocess environment overrides that are not stored in job records.
- Summary analysis, comment insight, Gemini visual analysis, Gemini video chat, and right-side AI chat all use the same resolved Provider configuration.
- Four analysis modes now render stable Chinese report structures. The shared envelope preserves source, profile, processing profile, generation metadata and warnings, while `content` differs per mode.
- `generation.comments_included` is fixed to `false`; public comments and comment insights remain separate artifacts and separate Web tabs.
- Only `tutorial + complete` can attach step images; screenshot failures mark the step image status but do not remove text steps.
- Fixed-count root cause: the main analysis path previously used one global LLM request and asked for one global result set, so long videos could collapse to a small number of broad chapters/highlights even without explicit `slice(0, 5)` in Web rendering.
- New segmentation metadata is written to `analysis.json` under `segmentation` using `policy_version=adaptive-v2`.
- Web and Markdown rendering no longer truncate the visible chapter/highlight/tutorial-step lists to the first five items.
- Standard-summary Web and Markdown rendering no longer duplicates legacy highlight/thought/chapter blocks, and neither renderer truncates those lists to a fixed first-five subset.

## Next Work Unit

After v1.4.3 review/commit, stop. v1.4.4 ASR and worker performance must start only under a separate instruction.

## Verification

- Focused Provider/comment/Web/export tests passed locally on 2026-07-25: 127 tests.
- Full unit suite passed locally on 2026-07-25 after the API configuration increment: 249 tests.
- `python -m compileall src`, CLI/Web help checks, `node --check src/web_ui/app.js`, and `git diff --check` passed on 2026-07-25.
- Browser spot-check on 2026-07-25 confirmed the video-side feature tabs render as `评论区` and `高光片段`, with comments separated from the left summary and no horizontal overflow in the checked viewport.
- Real public YouTube comment acceptance remains pending. One real Bilibili package has been repaired and accepted locally; more fixed Bilibili samples remain useful but are not required to prove the code path.
- Checkpoint A/B/C for adaptive long-video segmentation completed on 2026-07-26 with mock-backed coverage; real 71-minute tutorial API acceptance remains pending.
- Standard-summary correction verification on 2026-07-26 passed 85 focused analysis/segmentation/export/Web UI tests and all 271 unit tests; compileall, CLI/Web help, `node --check`, and `git diff --check` also passed.
