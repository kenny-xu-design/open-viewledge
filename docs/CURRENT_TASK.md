# Current Task

Last updated: 2026-07-24

## Active Work

v1.4.0 `processing_profile` 契约实现与验收。

Repository: `E:\AGT\git\video-summary-skill`

Branch: `feat/v1.4-processing-pipeline`

Baseline: `7790ed1 v1.3.12`, based on the completed v1.3.1 UI/acceptance branch.

## Scope

This task implements the reviewed v1.4.0 contract only.

In scope:

- `processing_profile: fast | complete`.
- CLI and deprecated root compatibility option.
- Web request and task API fields.
- CLI task, Web job, and manifest compatibility defaults.
- Stage metrics schema and current serial-stage duration recording.
- Contract, schema, Web, and CLI tests.

Out of scope:

- Cache-aware or stage-skipping fast execution.
- Changing Providers, download, ASR, package artifact formats, database, or dependencies.
- Fetching comments.
- Connecting Gemini video APIs.
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

After v1.4.0 review/commit, start v1.4.1 only: subtitle-priority verification, cache keys, cache reuse, and fast-path stage planning.

## Verification

- Focused v1.4.0 tests: 84 passed.
- Full unit suite: 209 passed.
- `python -m compileall src`: passed after allowing project `__pycache__` writes.
- CLI and Web help checks: passed.
- `node --check src/web_ui/app.js`: passed.
- `git diff --check`: passed.
- Browser: analysis and processing selectors are both present; complete is the default; intercepted `tutorial + fast` request preserved separate `mode` and `processingProfile` fields.
