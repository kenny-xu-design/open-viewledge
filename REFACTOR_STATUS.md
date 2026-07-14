# Framework Refactor Status

## Current architecture

The CLI and Web UI now share `PipelineOrchestrator` through `python -m src.main`.
The pipeline produces a stable knowledge package with raw transcript data, grouped
transcript, timeline, optional frames, structured analysis data, and a concise
Jinja2-rendered `index.md`.

Implemented in this refactor:

- Unified serializable domain models and processing manifest.
- Local video/audio and yt-dlp source interfaces.
- Local faster-whisper provider wrapper using the existing local model.
- Legacy LLM provider wrapper and validated structured analysis boundary.
- Raw JSONL transcript, grouped Markdown transcript, timeline, key frames.
- Knowledge package exporter and concise Obsidian-compatible main note.
- Privacy-mode configuration boundary. Cloud providers are blocked when enabled.
- Stable output IDs and reuse of an existing `transcript.raw.jsonl`.
- Comments removed from the default pipeline; the old CLI flag is deprecated.

Temporarily retained legacy modules:

- `src/adapters/` remains for compatibility and historical migration context.
- `src/summarizer.py`, `src/transcriber.py`, and `src/audio.py` are wrapped by the
  new provider/pipeline layers and remain the verified implementation underneath.
- Old output folders and old comment files are not deleted.

## Follow-up stages

### Stage A (code complete, real-link verification pending)

- Removed the remaining external Bilibili CLI runtime implementation and references.
- Bilibili now routes entirely through the project yt-dlp source.
- Run real Bilibili subtitle and no-subtitle tests.

### Stage B

- Discover installed Ollama models through `/api/tags`.
- Remove the forced `qwen3:8b` model behavior.

### Stage C

- Add optional Gemini and cloud ASR providers.
- Add cloud-first/local-fallback policy and 401/403/429/timeout handling.

### Stage D

- Enforce privacy mode across every future cloud provider.
- Record complete `ProviderAttempt` history.

### Stage E

- Add transcript context retrieval and same-window AI conversation.
- Add timestamp citations and visual questions over key frames.

### Stage F

- Add ordinary web-page import, clipping templates, content cleaning, deduplication,
  caching, and an Obsidian vault destination allowlist.
