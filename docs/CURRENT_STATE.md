# Current State

Last verified: 2026-07-16

This document describes the implementation that currently exists. Planned work belongs in `ROADMAP.md`.

## Repository

- Formal repository: `E:\AGT\git\video-summary-skill`
- Stable baseline: `main` at `33a4cc7` (`v1.1`)
- v1.2 development branch: `feat/v1.2-product-completion`
- Remote: `origin`
- Python: 3.12.13 in the project `.venv`

The v1.1 baseline passed:

```text
97 unit tests
python -m compileall src
python -m src.main --help
python -m src.web --help
```

Latest v1.2 feature-branch verification:

```text
123 unit tests
python -m compileall src
python -m src.main --help
python -m src.web --help
node --check src/web_ui/app.js
```

## v1.2 Progress

- Documentation truth synchronization: completed on the feature branch.
- Runtime executable discovery and model configuration unification: completed on the feature branch.
- Knowledge-package integrity validation: completed on the feature branch.
- User-note and Web-job persistence: completed on the feature branch.
- Disabled-route cleanup and platform-limit documentation: completed on the feature branch.
- Gemini image-input implementation: pending.
- Release validation: pending.

## Active Product Path

```text
CLI / Web subprocess
-> PipelineOrchestrator
-> LocalMediaSource / YtdlpSource
-> platform subtitles
-> FFmpeg + local faster-whisper when subtitles are unavailable
-> normalized transcript
-> grouped transcript
-> timeline and optional local-video frames
-> DeepSeek structured analysis
-> knowledge package
```

CLI and Web processing share `PipelineOrchestrator`. The Web server launches `src.main` with the Web process `sys.executable`.

## Inputs

Implemented:

- Local video.
- Local audio.
- YouTube.
- Bilibili.
- Other public video URLs supported by `yt-dlp`.

Not implemented:

- General web-page article extraction.
- Private platform automation beyond the user's locally authorized environment.
- Paid-content or DRM bypass.

## Transcription

- Platform subtitles are preferred.
- When no subtitle is available, media is acquired for transcription and normalized through FFmpeg.
- ASR uses the local `models/faster-whisper-small` directory.
- The model loader passes the resolved local path to `WhisperModel`.
- Missing `model.bin` causes a Chinese configuration error.
- The project does not silently download a Whisper model.
- Existing `transcript.raw.jsonl` can be reused when language and sample settings match.

Runtime discovery:

- FFmpeg and FFprobe use one shared resolver.
- Priority: explicit config, environment variable, PATH, project-local candidates, clear error.
- `FFMPEG_PATH` and `FFPROBE_PATH` are supported.
- Web runtime diagnostics report each tool independently.
- The audited machine still does not expose either tool through PATH, but explicit configuration is supported.

## Analysis

- CLI structured analysis supports DeepSeek only.
- Analysis uses JSON mode and Pydantic validation.
- Invalid structured output receives one repair request.
- Provider, model, usage, status, and errors are represented in analysis and manifest models.
- Analysis modes: `summary`, `tutorial`, `viral`, and `close-reading`.
- `--no-summary` skips LLM analysis.

Verified historical successful packages include:

- A full local video analysis using DeepSeek.
- A full YouTube analysis using DeepSeek.

One historical Bilibili package contains an empty analysis object while its manifest reports completion. The v1.2 inspector detects this conflict without silently rewriting historical output.

## Knowledge Package

Core files:

```text
index.md
metadata.json
manifest.json
analysis.json
timeline.json
source.md
transcript.raw.jsonl
transcript.grouped.md
transcript.md
```

Conditional files:

```text
summary.md
chapter_summary.md
highlight_notes.md
export_note.md
chat.json
user_notes.md
audio/audio_16k.wav
frames/*.jpg
```

The package is rendered through the exporter and Jinja2 template.

`src/knowledge_validation.py` now checks:

- required files;
- JSON object structure;
- source and manifest schema;
- meaningful transcript segments;
- timeline items;
- analysis status and meaningful content;
- manifest/analysis consistency;
- declared output existence.

CLI `inspect` reports existing package anomalies without mutating them. Web package views use the same inspection result and do not display empty analysis as successful.

## Web UI

Implemented:

- Three-pane knowledge workspace.
- Knowledge-package library.
- URL and local path processing tasks.
- Runtime Python reporting.
- Local video and audio playback.
- YouTube official IFrame API preview.
- Bilibili official iframe preview.
- Summary, chapter, timeline, transcript, and frame display.
- Configurable pane order and widths.
- Grounded AI chat.

Limitations:

- Bilibili iframe playback cannot be reliably controlled or synchronized by the application.
- Some online videos prohibit embedding and fall back to the external source.
- Frame capture API returns `501`.

Local persistence:

- Web task state is stored in ignored `.local/web_jobs.json`.
- Historical tasks are restored after Web restart.
- Jobs left in `queued` or `running` state are restored as `interrupted`.
- The task dialog exposes recent persisted jobs and their output knowledge IDs.

## AI Chat

Implemented:

```text
/api/chat
-> knowledge_id
-> grouped transcript loading
-> local BM25-style retrieval
-> DeepSeek or Gemini text Provider
-> timestamp citations
-> output/<knowledge_id>/chat.json
```

- Chat state is isolated by `knowledge_id`.
- Stored history is reloaded when switching packages.
- The server reloads package context and does not trust client-provided evidence.
- DeepSeek text chat is configured in the audited local environment.
- Gemini text Provider exists but Gemini is not configured in the audited local environment.

## Gemini

- Text completion Provider exists.
- Provider registry supports selecting Gemini for text chat.
- Image input currently raises an explicit not-implemented error.
- Gemini visual analysis has not been implemented or real-API verified.

## Notes And Obsidian

- User notes are stored as `output/<knowledge_id>/user_notes.md`.
- `GET/PUT /api/library/<knowledge_id>/notes` provide isolated read and save operations.
- Writes are atomic, limited to 1 MiB, and protected by SHA-256 revision checks.
- The Web editor saves after an 800 ms debounce and flushes before package switching.
- Saving a note refreshes `export_note.md` so the compatible export includes user content.
- `--export obsidian` creates `export_note.md`, a compatible Markdown copy.
- There is no Vault allowlist, Vault synchronization, or bidirectional Obsidian data layer.

## Disabled Or Historical Paths

- Comment retrieval and analysis are disabled.
- `--comments` remains only for old command compatibility and never enters a comment pipeline.
- Ollama is not an active backend.
- `bilibili-cli` is not an active dependency or runtime command.
- The unreachable pre-orchestrator branch, legacy adapters, Ollama summarizer, and legacy LLM adapter have been removed from active source.
- The historical comment-analysis prompt is retained only under `docs/archive/prompts/`.

## Configuration

- Real secrets belong only in ignored `.env`.
- `.env.example` contains empty keys and public defaults.
- Models, output, media, virtual environments, logs, caches, and archives are ignored.
- Provider defaults are centralized in `src/defaults.py`.
- DeepSeek default: `deepseek-v4-flash`.
- Gemini default: `gemini-3.1-flash-lite`.
- Environment variables can explicitly override defaults; unknown model names are passed through and never silently substituted.
- Web runtime diagnostics show the effective provider and model without exposing Keys.

## Known Risks

- A browser closed before its final keepalive request is accepted can leave the latest keystrokes unsaved; normal edits are persisted after 800 ms.
- The local JSON job store is intentionally single-process and is not a Scale queue.
- Archived documents can describe retired routes and must not be treated as current specifications.
