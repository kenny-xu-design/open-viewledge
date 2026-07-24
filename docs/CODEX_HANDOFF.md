# Codex Handoff

Last updated: 2026-07-24

## Repository State

- Repository: `E:\AGT\git\video-summary-skill`
- Branch: `feat/v1.4-processing-pipeline`
- Baseline commit: `52c1bb7` (`feat: add v1.4.1 cache-aware fast processing`)
- Upstream v1.3.1 branch marker: `origin/feat/v1.3.1-cupertino-ui`
- Scope: v1.4.2 visual pipeline, highlight snapshots, and Gemini video-conversation routing.

## Completed

- Created `docs/V1_4_ROADMAP.md`.
- Created `docs/V1_4_ARCHITECTURE.md`.
- Created `docs/V1_4_DATA_CONTRACTS.md`.
- Created `docs/V1_4_ACCEPTANCE.md`.
- Created `docs/V1_4_RISKS.md`.
- Created `docs/CURRENT_TASK.md`.
- Updated this handoff file from stale v1.3 Agent CLI handoff to the current v1.4 design state.
- Added `processing_profile: fast | complete` with a compatibility default of `complete`.
- Added separate profile fields to CLI results/events, CLI task records, Web job records/API payloads, and manifests.
- Added stage metrics for duration, attempts, cache placeholder, and sanitized errors.
- Added the Web processing-mode selector without changing application styling or motion.
- Kept `--no-frames` behavior independent and kept fast/complete execution identical in v1.4.0.
- Added focused compatibility and request/response tests.
- Added typed SHA-256 cache keys and atomic local cache storage under `.local/cache/v1`.
- Added metadata, platform-subtitle, transcript, and successful text-analysis reuse.
- Verified YouTube and Bilibili subtitle hits do not acquire media or instantiate Whisper.
- Added fast audio-only acquisition and fast keyframe-stage skipping.
- Added first-readable-result and full-completion timing fields.
- Made cache failures degrade to ordinary execution instead of failing the task.
- Moved text analysis before all optional visual stages and writes the text analysis artifact before visual work.
- Added compatible highlight image fields and bounded WebP snapshot generation under the package root.
- Connected optional keyframe analysis without making Gemini a requirement for text packages.
- Added official Gemini public-YouTube URL and resumable Files API request paths.
- Added explicit URL, Files, keyframe+text, and text-only chat route statuses and degradation reasons.
- Extended `chat.json` with source-bound recovery and remote-file state while excluding credentials.
- Added Web and Markdown rendering for relative highlight images and visible chat route status.

## Current Architecture Notes

- The processing path remains serial, but its text result completes before optional visual stages.
- The stage list is fixed in `src/pipeline/stages.py:STAGES`.
- Web starts a CLI subprocess in `src/web.py:_run_job()` and consumes JSONL events through `_handle_cli_output_line()`.
- Local Web job storage in `src/job_store.py:JobStore` is not a durable worker queue.
- CLI task storage in `src/cli_tasks.py:CliTaskStore` is a resumable invocation record, not stage-level recovery.
- Gemini supports text, inline images, public YouTube URL input, and resumable Files API video references.
- `src/analysis/vision.py:KeyframeAnalysisService` is called only after complete-mode local keyframe extraction.
- Comments remain disabled; `src/main.py` only emits a compatibility warning for `--comments`.

## Next Work Unit

Stop after v1.4.2 review/commit. Do not start comments, ASR worker, queue, or batch work without a separate instruction.

## Verification

- Focused v1.4.2/Gemini/chat/export/pipeline/Web suite passes locally.
- Full unit suite passes: 226 tests.
- Python compileall, CLI/Web help, JavaScript syntax, and diff checks pass.
- Browser checks at 1440×900, 1024×768, and 390×844 have no horizontal overflow; mocked highlight and degraded-route rendering pass.
- The production FFmpeg WebP command was exercised successfully against a generated two-second video.
- Gemini request contracts are mock verified only; no real API request or cost/quota claim has been made.

## Open Decisions

- Whether new Web tasks should default to `fast` immediately, or keep `complete` until users see an explicit mode selector.
- Real-account compatibility of the configured Gemini model with preview YouTube URL input.
- Whether SQLite queue lands in v1.4.5 only, or a minimal stage table appears earlier behind a feature flag.
- Cache root location and retention policy.
- Benchmark fixture policy for long videos and platform URLs that may change over time.

## Git Notes

- `52c1bb7` is the committed and pushed v1.4.1 baseline.
- This Codex task did not run commit, push, merge, rebase, tag, checkout, or branch creation commands.
- Current uncommitted changes are the v1.4.2 implementation, tests, and documentation.
