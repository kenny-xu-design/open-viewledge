# v1.4 Roadmap

Status: v1.4.0-v1.4.3 implemented; v1.4.3 final local QA plus API-configuration and analysis-profile contract increments complete; v1.4.4-v1.4.6 planned

Branch: `feat/v1.4-processing-pipeline`

Last updated: 2026-07-25

## Scope

v1.4 keeps the v1.3 CLI, Web, knowledge-package, export, and local-first behavior intact. It adds processing profiles, cache-aware fast paths, visual and comment pipelines, Gemini video conversation, and a durable local queue in independent version units.

v1.4 must not merge `analysis_profile` and `processing_profile`.

- `analysis_profile` decides what to generate: `summary`, `tutorial`, `viral_analysis`, `close_reading`, and compatible aliases.
- `processing_profile` decides how to execute: `fast` or `complete`.

## Current Baseline

The current implementation is a serial pipeline:

```text
src.main.run_pipeline()
-> PipelineOrchestrator.run()
-> SourceAdapter
-> acquire_transcript
-> normalize_transcript
-> group_transcript
-> build_timeline
-> extract_frames
-> run_analysis
-> export_knowledge_package
```

Relevant code:

- `src/main.py`: `run_pipeline()`, `execute_analyze()`, `execute_resume()`.
- `src/pipeline/orchestrator.py`: `PipelineOrchestrator.run()`, `_stage()`.
- `src/pipeline/stages.py`: `STAGES`.
- `src/domain/models.py`: `ProcessingManifest`, `AnalysisResult`, `HighlightItem`.
- `src/web.py`: `build_cli_command()`, `start_job()`, `_run_job()`, `_handle_cli_output_line()`.
- `src/job_store.py`: file-backed `JobStore`, not a worker queue.

## Work Units

### v1.4.0: Processing Profiles And Data Contract

Status: committed as `e5d9b55 v1.4.0`.

Goal: establish `processing_profile: fast | complete` across CLI, Web, API, task record, manifest, and migration rules.

Input:

- Existing v1.3 CLI contract in `docs/CLI_CONTRACT.md`.
- Existing manifest model `ProcessingManifest`.
- Existing Web task payload built by `src/web.py:build_cli_command()`.

Output:

- Add `processing_profile` as a compatible optional field.
- CLI adds `--processing-profile fast|complete`; root compatibility path mirrors it only during deprecation.
- Web task payload adds `processingProfile`.
- JSONL events and manifest keep `analysis_profile` separate.
- Stage duration fields are defined before implementation.
- `--no-frames` and `generate_frames` map into the visual-stage plan without changing old behavior.

Acceptance:

- Old task records without `processing_profile` read as `complete` for compatibility.
- New tasks default to current behavior unless the user explicitly selects fast.
- Existing JSONL events remain parseable by current Web consumers.
- Schema compatibility tests cover missing, valid, and invalid `processing_profile`.

### v1.4.1: Subtitle Priority, Cache, And Fast Path

Status: implemented on `feat/v1.4-processing-pipeline`; pending final review/commit.

Goal: reduce time to first readable result.

Input:

- `YtdlpSource.acquire_subtitles()`.
- `downloader._download_subtitle()`.
- Current `transcript.raw.jsonl` reuse in `PipelineOrchestrator.run()`.

Output:

- Cache keys for metadata, subtitles, audio, transcript, frames, text analysis, visual analysis, and comments.
- Cache dimensions include source platform, source ID, Bilibili `p`, YouTube video ID, language, sample range, ASR config, analysis profile, processing profile, Provider, model, and prompt version.
- Fast mode skips default frame extraction, visual analysis, tutorial step screenshots, and comments.
- First readable result timing is recorded independently from full task completion.

Acceptance:

- A video with platform subtitles does not download full video.
- A video with platform subtitles does not instantiate Whisper.
- Cache hit does not repeat subtitle download, audio download, ASR, or text analysis.
- First readable result duration is visible in manifest or stage metrics.

### v1.4.2: Visual Pipeline, Highlight Snapshots, And Gemini YouTube Video Chat

Status: implemented on `feat/v1.4-processing-pipeline`; automated and real-API acceptance pending final verification.

Goal: turn existing frame and Gemini image boundaries into visible product features without blocking text results.

Input:

- `timeline.frame_extractor.extract_frames()`.
- `analysis.vision.KeyframeAnalysisService`.
- `providers.llm.GeminiProvider.generate_with_images()`.
- `web.chat_with_knowledge()` and `chat.answer_question()`.

Output:

- Parallel text and visual route design.
- `assets/tutorial/tutorial_step_001.webp` style output for tutorial steps.
- Highlight fields: `timestamp`, `title`, `summary`, `tags`, `image`, `image_source_timestamp`, `image_generation_status`.
- Gemini video conversation strategy:
  1. public YouTube URL to Gemini native video understanding;
  2. downloaded/uploaded video through Gemini Files API;
  3. transcript plus chapters plus available keyframe/tutorial context.
- Chat state includes `chat_id`, `source_url`, provider, model, local messages, optional remote session ID, and recovery state.

Acceptance:

- Text summary and chapters can complete before visual stages.
- Tutorial step text remains available when image capture fails.
- Markdown and Obsidian exports use relative tutorial image references.
- Gemini native URL failure falls back with explicit status.
- No UI claims are based on whether YouTube shows an Ask button.

### v1.4.3: Comment Sync, API Configuration, And Profile Contracts

Status: implemented on `feat/v1.4-processing-pipeline`; final local QA plus API-configuration and analysis-profile contract increments complete, pending user review/commit.

Goal: add public comment synchronization, comment insights beside AI highlights, local Web API configuration, and distinct output contracts for `summary`, `tutorial`, `viral`, and `close-reading`.
Additional v1.4.3 finish: add adaptive long-video segmentation so long videos are not collapsed into a fixed small global chapter/highlight list.

Input:

- Current comment feature is disabled: `main.py --comments` emits a compatibility warning.
- Archived prompt exists at `docs/archive/prompts/comment_insights_prompt.md`.

Output:

- `BilibiliCommentAdapter`.
- `YouTubeCommentAdapter`.
- `NormalizedComment`.
- `CommentRepository`.
- `CommentSyncService`.
- `CommentInsightService`.
- Package files: `comments.json`, `comments.md`, `comment_insights.md`.

Acceptance:

- Comment failures never fail the video summary task.
- Comment opinions are not written into the main factual summary.
- Comment timestamps use existing `seekPreview(seconds)` behavior.
- Fast mode fetches limited high-value comments only and can disable comments.
- Complete mode supports bounded hot/latest/reply/incremental sync.
- Web presents comments and AI highlights as peer video-side functions: `评论区` and `高光片段`.
- Comment content is never merged into the main factual summary.
- Web exposes a local API configuration entry for real DeepSeek/OpenAI-compatible and Gemini interaction testing.
- API Keys are process-memory only and are not written to frontend storage, job records, packages, Markdown, exports, or repository files.
- Provider resolution is unified for summary analysis, comment insight, Gemini visual/video routes, and right-side AI chat.
- The four analysis modes use a shared envelope with mode-specific `content` fields; old knowledge packages still read through compatibility fields.
- `generation.comments_included=false` is preserved in main analysis results.
- Only `tutorial + complete` can generate/export relative `assets/tutorial/` step screenshots. `summary`, `viral`, `close-reading`, and `tutorial + fast` do not export screenshots.
- Adaptive policy routes by duration, transcript density, analysis profile, processing profile, native chapters, subtitle-group count, and visual availability.
- Dense 60-minute-plus videos default to hierarchical semantic Map/Reduce with overlap windows and reducer metadata.
- Coverage guard reports and, where possible, repairs large gaps using real transcript groups rather than midpoint insertion.

### v1.4.4: ASR And Worker Performance

Goal: speed up no-subtitle videos and avoid repeated model load.

Input:

- `transcriber.transcribe_segments()` currently creates `WhisperModel(...)` per call.
- `LocalWhisperProvider.transcribe()` delegates directly to `transcribe_segments()`.

Output:

- Model-resident Whisper worker design.
- Measured profiles for CPU int8, `beam_size`, VAD, word timestamps, batching, `cpu_threads`, GPU, and LAN worker.
- Test audio set and benchmark record format.

Acceptance:

- No hard-coded thread count without benchmark data.
- Model load time and transcription time are recorded separately.
- Fast mode has a measured lower-latency ASR profile.
- Complete mode can trade speed for richer timestamps where needed.

### v1.4.5: Durable Queue, Resume, Concurrency, And Batch

Goal: replace ad hoc local task persistence with a recoverable stage queue while preserving the public CLI.

Input:

- `.local/cli_tasks` record in `CliTaskStore`.
- `.local/web_jobs.json` record in `JobStore`.
- JSONL event vocabulary in `cli_contract.CliEmitter`.

Output:

- SQLite queue with `Job`, `Stage`, `Artifact`, `Event`, `WorkerLease`, heartbeat, retry, idempotency key, cancel, resume, dependency, and partial success.
- Resource-specific concurrency limits: download, ASR, text LLM, Gemini video, comments API, export.
- Batch submission that decomposes into independent jobs.

Acceptance:

- Interrupted jobs rerun only incomplete or invalidated stages.
- Completed downloads, subtitles, ASR, and text analysis are not repeated.
- Fast tasks receive higher response priority.
- CLI/Web/API stage status is consistent.

### v1.4.6: Performance, Stability, And Compatibility Acceptance

Goal: verify v1.4 under fixed tests, failure modes, cache reuse, and legacy compatibility.

Output:

- Fixed test set documented in `docs/V1_4_ACCEPTANCE.md`.
- Performance report template.
- Compatibility gate for old knowledge packages and exports.

Acceptance:

- YouTube Ask UI availability is irrelevant to capability detection.
- Subtitle videos do not run Whisper.
- Fast mode skips unnecessary visual stages.
- Complete mode allows text, visual, and comment stages to finish independently.
- Deleting a knowledge package removes associated tutorial images, legacy highlight images, and comment files when they live under the package root.

## Dependencies

```text
v1.4.0 contracts
  -> v1.4.1 cache and fast path
  -> v1.4.2 visual and Gemini video chat
  -> v1.4.3 comments
  -> v1.4.4 ASR workers
  -> v1.4.5 queue and batch
  -> v1.4.6 acceptance
```

v1.4.2, v1.4.3, and v1.4.4 can be prototyped after v1.4.0, but they should not change task persistence independently of v1.4.5.

## Out Of Scope

- SaaS accounts, tenancy, billing, hosted storage, or cloud worker pools.
- Browser automation against Gemini Web, YouTube Ask, cookies, or private APIs.
- DRM, paid-content bypass, login-gated scraping, or watermark removal.
- New UI visual style work unrelated to v1.4 processing states.
- New third-party dependencies during the design phase.
