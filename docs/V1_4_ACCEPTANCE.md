# v1.4 Acceptance Plan

Status: design phase only

Last updated: 2026-07-24

## Version Gates

### v1.4.0

Implementation status: complete on the working branch. Automated contract coverage and browser form/request checks pass.

- `processing_profile` is present in CLI, Web payload, API response, task record, and manifest.
- Missing `processing_profile` in old data maps to `complete`.
- `analysis_profile` remains separate and existing `--mode` behavior is unchanged.
- Stage metrics contract records duration, attempts, cache status, and errors.
- `--no-frames` compatibility is documented and tested.

### v1.4.1

- YouTube/Bilibili videos with subtitles do not download full video.
- YouTube/Bilibili videos with subtitles do not run local ASR.
- No-subtitle fast mode downloads audio only.
- Repeated identical input hits cache and avoids repeated download, ASR, and text analysis.
- First readable result duration is recorded and surfaced.

### v1.4.2

- Complete mode can produce text output before visual output.
- Highlight cards show at most one lightweight image each.
- Highlight image failure does not remove highlight text.
- Markdown and Obsidian exports use relative image references.
- Gemini native YouTube URL chat, Files API fallback, frame+text fallback, and text-only fallback each have explicit route status.
- YouTube Ask page availability is never used as capability evidence.

### v1.4.3

- Comment sync failure does not fail the video task.
- Comment insights are separated from main summary.
- Comment timestamps call existing preview seek behavior.
- Fast mode fetches a small bounded comment set and can disable comments.
- Complete mode supports bounded hot/latest/reply/incremental sync.

### v1.4.4

- Whisper model load time and ASR time are measured separately.
- Worker mode avoids repeated model load across same-profile tasks.
- CPU thread and batch size recommendations are based on measured runs, not constants.
- Fast and complete ASR profiles are covered by benchmark records.

### v1.4.5

- Queue records `Job`, `Stage`, `Artifact`, `Event`, and worker lease state.
- Cancel, resume, retry, dependency, and partial success are tested.
- Interrupted tasks resume only incomplete or invalidated stages.
- Resource-specific concurrency limits are enforced.
- Batch submission creates independent resumable jobs.

### v1.4.6

- Fixed test set passes.
- Old v1.2/v1.3 knowledge packages still read.
- Old exports remain compatible.
- Web, CLI, and task API status agree for success, warning, failure, and partial success.
- Package deletion removes v1.4 highlight/comment artifacts under the package root.

## Fixed Test Set

Use stable fixtures or pinned manually verified inputs:

- YouTube with platform subtitles.
- YouTube without subtitles.
- Public YouTube where the webpage shows Ask.
- Public YouTube where the webpage does not show Ask.
- YouTube accepted by Gemini URL input.
- YouTube rejected by Gemini URL input.
- Bilibili with subtitles.
- Bilibili without subtitles.
- Video with popular comments.
- Video with closed or restricted comments.
- Short local video.
- Long local video.
- Vertical local video.
- Cache-hit task.
- Visual failure task.
- Comment failure task.
- Interrupted recovery task.
- Duplicate submission task.
- Batch task.

## Performance Metrics

Record per job:

- metadata duration.
- subtitle fetch duration.
- media download duration.
- audio extraction duration.
- model load duration.
- transcription duration.
- transcription realtime factor.
- text analysis duration.
- keyframe extraction duration.
- visual analysis duration.
- highlight snapshot duration.
- comments fetch duration.
- comments analysis duration.
- package build duration.
- first readable result duration.
- full completion duration.
- CPU, memory, and where available temperature/throttling notes.

## Required Regression Checks

- `python -m unittest discover`.
- `python -m compileall src`.
- `python -m src.main --help`.
- `python -m src.web --help`.
- `node --check src/web_ui/app.js`.
- `git diff --check`.
- Focused Web UI/API tests.
- CLI JSON/JSONL contract tests.
- Schema compatibility tests.
- Knowledge package validation tests.
- Export tests.

## Browser Acceptance

Do not add visual redesign requirements here. v1.4 browser acceptance focuses on processing behavior:

- New task form exposes processing mode without hiding existing analysis mode.
- Fast task can show readable text before complete-mode artifacts exist.
- Stage list shows pending/running/completed/skipped/warning/failed.
- Highlight images appear when available and degrade to text-only.
- Comment hotspots appear separately from AI highlights.
- Gemini video chat route and fallback status are visible.
- Existing summary, transcript, chat, notes, export, deletion, preview seek, and media controls still work.

## Failure And Degradation Paths

- Subtitle fetch fails: proceed to audio download and ASR when allowed.
- ASR fails: task fails only if no transcript exists.
- Text LLM fails: package can be partial with transcript and timeline.
- Visual analysis fails: text package remains usable.
- Highlight image capture fails: highlight text remains.
- Comment fetch fails: summary remains.
- Gemini native URL chat fails: try Files API, then frames+text, then text-only.
- Cache entry invalid: rerun only the invalidated stage and downstream dependents.
- Worker crash: lease expires and the stage becomes retryable.

## Release Exit Criteria

- All fixed tests pass.
- Performance numbers are captured for fast and complete modes.
- No new secrets appear in logs, frontend storage, package files, exports, or task records.
- All new package files are documented and validated.
- Manual acceptance confirms old packages and old exports are readable.
