# v1.4 Architecture

Status: design phase only

Last updated: 2026-07-24

## Current Architecture Findings

The following conclusions come from current repository files, not prior chat history.

| Question | Current answer | Evidence |
|---|---|---|
| Task execution shape | Single serial pipeline. Stages run in `PipelineOrchestrator.run()` in fixed order. | `src/pipeline/orchestrator.py:PipelineOrchestrator.run()`, `src/pipeline/stages.py:STAGES` |
| Reusable stages | Metadata, subtitle acquisition, raw transcript reuse, grouping, timeline, local frame extraction, DeepSeek text analysis, package export. | `YtdlpSource`, `LocalMediaSource`, `read_jsonl()`, `group_segments()`, `build_timeline()`, `extract_frames()`, `AnalysisService`, `export_knowledge_package()` |
| Direct Web coupling | Web does not call pipeline directly; it builds a CLI command and starts `src.main analyze --jsonl` in a background thread. | `src/web.py:build_cli_command()`, `start_job()`, `_run_job()` |
| Existing adapters | `LocalMediaSource`, `YtdlpSource`, inactive `WebSource`. | `src/sources/local_media.py`, `src/sources/ytdlp_source.py`, `src/sources/web_source.py` |
| Keyframes | Generated only for local video when `generate_frames` is true. | `PipelineOrchestrator.run()` stage `extract_frames` |
| Visual analysis | Isolated service exists, but default pipeline and Web chat do not call it. | `src/analysis/vision.py:KeyframeAnalysisService`, `src/providers/llm/gemini.py:generate_with_images()` |
| Comments | Active retrieval is disabled; `--comments` is a warning-only compatibility option. | `src/main.py:run_pipeline()`, `docs/archive/prompts/comment_insights_prompt.md` |
| Comment outputs | `comments.json`, `comments.md`, and `comment_insights.md` are not active package outputs. | `src/exporters/knowledge_package.py:export_knowledge_package()` output list |
| Chat context | Current chat uses grouped transcript plus existing analysis summary/highlights/chapters. | `src/chat.py:answer_question()`, `src/web.py:chat_with_knowledge()` |
| Gemini video input | Current Gemini Provider supports text and inline images only. | `src/providers/llm/gemini.py:complete()`, `generate_with_images()` |
| Remote chat state | No remote interaction/session identifier is stored; `ChatStore` saves local messages only. | `src/chat_store.py:ChatStore` |
| Whisper loading | `WhisperModel` is constructed inside every `transcribe_segments()` call. | `src/transcriber.py:transcribe_segments()` |
| Cache keys | Only raw transcript reuse exists, based on file presence, requested language, and `sample_seconds`; no unified cache key. | `PipelineOrchestrator.run()` local `acquire()` |
| Incremental package writes | Manifest and artifacts are written during the serial run, but package schema has no formal partial stage artifact contract. | `ProcessingManifest`, `_save_manifest()` |
| Stage status in Web | Web can show stage progress, but it derives UI progress from parsed logs/events and a fixed frontend stage list. | `src/web.py:_handle_cli_output_line()`, `src/web_ui/app.js:renderTaskProgress()` |
| Delete behavior | Deletes the validated package directory recursively; future assets under the same package root are cleaned with it. | `src/web.py:delete_knowledge_packages()`, `_remove_knowledge_directory()` |

## Target Architecture

v1.4 keeps `src.main` as the public command boundary and makes the internal pipeline stage-based, cache-aware, and eventually queue-backed.

```text
CLI / Web / Agent
  |
  v
Analyze Request
  |- analysis_profile
  `- processing_profile
  |
  v
Stage Planner
  |- fast plan
  `- complete plan
  |
  v
Durable Job + Stage Records
  |
  +--> Text Pipeline
  +--> Visual Pipeline
  +--> Comment Pipeline
  |
  v
Knowledge Package Writer
  |
  v
Web / CLI / Export / Chat
```

## Text Pipeline

```text
resolve_source
-> collect_metadata
-> subtitle_fetch
-> media_download only when needed
-> audio_extract only when needed
-> transcription only when needed
-> normalize_transcript
-> group_transcript
-> build_timeline
-> text_analysis
-> package_build
```

Rules:

- Platform subtitles have priority for YouTube and Bilibili.
- A subtitle hit must not start Whisper.
- Text analysis must not wait for visual or comment stages.
- Existing transcript artifacts can be reused when cache keys match.

## Visual Pipeline

```text
video or local media artifact
-> keyframe_extract
-> visual_analysis
-> highlight_snapshot
-> assets/highlights/*.webp
-> package manifest and exports
```

Rules:

- Fast mode skips visual stages by default.
- Complete mode schedules visual stages after source/media availability.
- Visual failures produce stage warnings and do not fail text output.
- Highlight snapshots prefer existing frames and only perform local supplemental capture near highlight timestamps when needed.

## Comment Pipeline

```text
source_url and platform identity
-> comments_fetch
-> comments_normalize
-> comments_repository
-> comments_analysis
-> comments.json / comments.md / comment_insights.md
```

Rules:

- Comment opinions are separate from main summary.
- Comment timestamps reuse preview seeking.
- Comment fetch failures never fail the video task.
- Fast mode fetches bounded high-value comments only.
- Complete mode supports bounded hot/latest/reply/incremental sync.

## Gemini YouTube Video Conversation

The application must judge capability from backend API results, not from YouTube UI or Gemini Web UI.

```text
Chat request
-> source_url and knowledge_id
-> provider capability probe/result
-> route:
   1. Gemini native YouTube URL video understanding
   2. Gemini Files API video upload/reference
   3. transcript + chapters + highlight images
   4. text-only transcript context
-> local ChatStore record with route state
```

State to store locally:

- `chat_id`.
- `knowledge_id`.
- `source_url`.
- `source_fingerprint`.
- `provider`.
- `model`.
- `route`.
- `route_status`.
- `remote_session_id` or `remote_file_id` when returned by the Provider.
- `remote_expires_at` when known.
- local `messages`.
- degradation reason.

If the source URL or source fingerprint changes, the video conversation state becomes invalid and a new `chat_id` is required.

## Cache Architecture

v1.4 introduces a cache service with typed keys:

Implementation status: v1.4.1 implements deterministic SHA-256 keys and atomic JSON cache entries in `.local/cache/v1`. Metadata, platform subtitles, normalized transcripts, and successful text analysis are actively reused. Audio and frame keys are recorded for planning/invalidation; large binary artifact copying and retention cleanup remain deferred.

- metadata: platform, source ID, canonical URL, playlist/part.
- subtitle: platform, source ID, part, language, subtitle kind.
- audio: source ID, part, sample range, audio format.
- transcript: source ID, part, language, ASR provider/model/config, sample range.
- text analysis: transcript hash, analysis profile, Provider, model, prompt version.
- keyframes: video hash/source ID, strategy, timestamps, FFmpeg version.
- visual analysis: frame hashes, Provider, model, prompt version.
- comments: platform, source ID, mode, sort, page/reply bounds, sync cursor.

Cache events should record `cache_hit`, `cache_key`, and `artifact_id` without leaking private local paths to the frontend.

## Queue And Worker Boundary

The v1.4.5 queue should be SQLite-backed and local by default.

Core tables or logical records:

- `Job`.
- `Stage`.
- `Artifact`.
- `Event`.
- `WorkerLease`.
- `Retry`.
- `Dependency`.

Workers claim stages by lease and heartbeat. A crashed worker releases work after lease expiry. Stage actions must be idempotent and validate existing artifacts before doing expensive work.

## Module Boundaries

Suggested new modules:

- `src/processing_profiles.py`: `fast` and `complete` profile definitions.
- `src/cache/`: cache key and artifact registry.
- `src/jobs/`: SQLite queue and stage records.
- `src/workers/`: worker leases and resource-specific executors.
- `src/comments/`: platform adapters, repository, insight service.
- `src/visual/`: highlight snapshot and visual analysis orchestration.
- `src/video_chat/`: Gemini video chat route planner and state.

Existing modules should remain public boundaries:

- `src/main.py` keeps CLI command shape.
- `src/pipeline/orchestrator.py` can become a stage planner/executor adapter during migration.
- `src/domain/models.py` remains the compatibility model boundary.
- `src/web.py` continues to call public CLI or task API, not private pipeline internals.

## Data Flow

```text
Input URL/File
  |
  v
SourceRecord
  |
  +--> Text artifacts: subtitles/audio/transcript/groups/analysis
  |
  +--> Visual artifacts: frames/highlight images/visual insights
  |
  +--> Comment artifacts: comments/comment insights
  |
  v
Manifest + package files
  |
  +--> Web reader
  +--> Markdown/Obsidian export
  +--> Chat context
  `--> Delete package directory
```
