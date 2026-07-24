# Codex Handoff

Last updated: 2026-07-24

## Repository State

- Repository: `E:\AGT\git\video-summary-skill`
- Branch: `feat/v1.4-processing-pipeline`
- Baseline commit: `e5d9b55` (`v1.4.0`)
- Upstream v1.3.1 branch marker: `origin/feat/v1.3.1-cupertino-ui`
- Scope: v1.4.0 contracts plus v1.4.1 subtitle priority, cache, and fast path.

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

## Current Architecture Notes

- The processing path is currently serial in `src/pipeline/orchestrator.py:PipelineOrchestrator.run()`.
- The stage list is fixed in `src/pipeline/stages.py:STAGES`.
- Web starts a CLI subprocess in `src/web.py:_run_job()` and consumes JSONL events through `_handle_cli_output_line()`.
- Local Web job storage in `src/job_store.py:JobStore` is not a durable worker queue.
- CLI task storage in `src/cli_tasks.py:CliTaskStore` is a resumable invocation record, not stage-level recovery.
- Gemini currently supports text and image input through `src/providers/llm/gemini.py`, but not YouTube URL video chat or Files API.
- `src/analysis/vision.py:KeyframeAnalysisService` exists but is not called by the default pipeline or Web chat.
- Comments remain disabled; `src/main.py` only emits a compatibility warning for `--comments`.

## Next Work Unit

After v1.4.1 is reviewed and committed, v1.4.2 may add the visual pipeline, highlight snapshots, and Gemini video-conversation routing. Do not start comments, ASR worker, queue, or batch work in the v1.4.1 handoff.

## Verification

- Focused v1.4.1/Web/CLI suite: 127 tests passed.
- Full unit suite: 216 tests passed.
- Python compileall, CLI/Web help, JavaScript syntax, and diff checks passed.
- Browser contract check passed for default complete and separate tutorial/fast request fields.
- The only browser console message was the existing missing `favicon.ico` 404.

## Open Decisions

- Whether new Web tasks should default to `fast` immediately, or keep `complete` until users see an explicit mode selector.
- Exact Gemini model names and endpoint shapes for native YouTube URL input and Files API.
- Whether SQLite queue lands in v1.4.5 only, or a minimal stage table appears earlier behind a feature flag.
- Cache root location and retention policy.
- Benchmark fixture policy for long videos and platform URLs that may change over time.

## Git Notes

- `e5d9b55 v1.4.0` appeared on the local branch and `origin/feat/v1.4-processing-pipeline` during v1.4.1 implementation.
- This Codex task did not run commit, push, merge, rebase, tag, checkout, or branch creation commands.
- Current uncommitted changes are the v1.4.1 implementation and tests.
