# Current Task

Last updated: 2026-07-24

## Active Work

v1.4.1 字幕优先、缓存和 fast path 实现与验收。

Repository: `E:\AGT\git\video-summary-skill`

Branch: `feat/v1.4-processing-pipeline`

Baseline: `e5d9b55 v1.4.0`, committed and pushed externally while v1.4.1 work was in progress.

## Scope

This task implements the reviewed v1.4.1 work unit on top of the uncommitted v1.4.0 contract.

In scope:

- Typed cache keys and atomic local cache storage.
- Metadata, platform subtitle, transcript, and text-analysis cache reuse.
- Subtitle-priority verification for YouTube and Bilibili.
- Audio-only acquisition for no-subtitle fast tasks.
- Fast-mode keyframe skipping.
- First-readable-result and full-completion timing.
- Cache, pipeline, downloader, schema, Web, and CLI tests.

Out of scope:

- Changing Providers, download, ASR, package artifact formats, database, or dependencies.
- Fetching comments.
- Connecting Gemini video APIs.
- Visual-analysis or highlight-image implementation.
- Durable worker queue, batch, or SQLite persistence.
- Committing, pushing, merging, rebasing, tagging, or releasing.

## Current Findings

- Current processing is a single serial `PipelineOrchestrator.run()` flow.
- Web processing starts the public CLI with `--jsonl`; Web does not execute the media pipeline directly.
- Platform subtitles are already attempted before ASR.
- Raw transcript reuse exists, but there is no unified cache key contract.
- Whisper model loading happens inside each transcription call.
- Gemini supports text and inline image requests, not native YouTube video chat or Files API.
- Comments are disabled except for a compatibility warning.
- Web can display coarse stage progress from JSONL/logs but does not have durable stage records.

## Next Work Unit

After v1.4.1 review/commit, start v1.4.2 only: visual pipeline, highlight snapshots, and Gemini video-conversation routing.

## Verification

- Focused v1.4.1/Web/CLI tests: 127 passed.
- Full unit suite: 216 passed.
- `python -m compileall src`: passed after allowing project `__pycache__` writes.
- CLI and Web help checks: passed.
- `node --check src/web_ui/app.js`: passed.
- `git diff --check`: passed.
- Browser contract from v1.4.0 remains valid; v1.4.1 selector copy and separate `mode` / `processingProfile` fields are covered by Web UI/API tests.
