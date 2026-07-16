# Architecture

This document separates the architecture that exists today from later evolution. Code is authoritative when documentation and implementation disagree.

## Current Architecture

### Entry Points

```text
src.main
src.web
.agents/skills/video-summary/SKILL.md
```

- `src.main` validates CLI input and runs `PipelineOrchestrator`.
- `src.web` serves the local Web UI and starts CLI processing as a subprocess using `sys.executable`.
- The Agent Skill invokes the existing CLI and does not duplicate business logic.

### Processing Pipeline

```text
Input
  |
  v
SourceAdapter
  |- LocalMediaSource
  `- YtdlpSource
  |
  v
Transcript Acquisition
  |- platform subtitles
  `- FFmpeg -> LocalWhisperProvider
  |
  v
Transcript Normalization
  |- transcript.raw.jsonl
  |- transcript.grouped.md
  `- transcript.md
  |
  v
Timeline
  |- timeline.json
  `- local-video frame extraction
  |
  v
AnalysisService
  `- DeepSeekProvider
  |
  v
Knowledge Package Exporter
```

`PipelineOrchestrator` owns stage ordering, manifest updates, cache reuse, provider attempts, soft failures, and package export.

### Domain Models

`src/domain/models.py` defines:

- `SourceRecord`
- `TranscriptSegment`
- `TranscriptGroup`
- `TimelineEntry`
- `AnalysisResult`
- `ProcessingManifest`
- `KnowledgePackage`

Pydantic models are the structured boundary between pipeline stages and exported JSON.

### Source Layer

`LocalMediaSource`:

- Validates local media extensions.
- Creates a stable source ID from file size and sampled bytes.
- Returns the original local path for processing.

`YtdlpSource`:

- Accepts HTTP/HTTPS URLs and Bilibili BV identifiers.
- Normalizes Bilibili identifiers.
- Uses `yt-dlp` for metadata, subtitles, and audio-only fallback media.
- Does not invoke `bilibili-cli`.

`WebSource` is a placeholder and is not active.

### ASR Layer

`LocalWhisperProvider` delegates to `transcriber.transcribe_segments`.

Current invariant:

```text
models/faster-whisper-small/model.bin must exist
```

The absolute local model directory is passed to `WhisperModel`. No implicit model download is allowed.

### Analysis Layer

CLI analysis:

```text
AnalysisService -> DeepSeekProvider
```

- JSON response mode.
- Pydantic parsing.
- Timestamp bounds validation.
- One schema-repair attempt.
- Provider/model/usage recording.

The legacy LLM adapter and Ollama summarizer remain historical compatibility code and are not part of the active pipeline.

### Chat Layer

```text
Web /api/chat
-> load knowledge package
-> load grouped transcript
-> ContextRetriever
-> ProviderRegistry
-> DeepSeekProvider or GeminiProvider
-> ChatStore
```

Retrieval is local and lexical:

- Latin word tokens.
- Chinese character bigrams.
- BM25-style scoring.
- Neighboring transcript groups.
- Context character budget.

Chat history is persisted in `chat.json` beside the knowledge package.

### Web Layer

The Web server uses Python's `ThreadingHTTPServer`.

Responsibilities:

- Static UI delivery.
- Knowledge-package listing and reads.
- Allowlisted package file delivery.
- Local media range responses.
- Official YouTube and Bilibili embed descriptors.
- Processing job creation and status.
- Chat endpoints and storage.

Long processing remains in a background thread that starts the core CLI subprocess. The request thread does not execute the full media pipeline.

### Export Layer

The package exporter writes JSON and Markdown, including a Jinja2-rendered `index.md`.

`export_note.md` is an Obsidian-compatible Markdown copy. It is not a Vault integration.

## Existing Duplication

The repository still contains pre-orchestrator modules:

- `src/adapters/`
- legacy portions of `src/main.py` after the active pipeline return
- `src/summarizer.py`
- `src/providers/llm/legacy_adapter.py`
- historical comment prompts

They must not be treated as the current architecture. v1.2 may archive or remove unreachable paths only after dependency checks and tests.

## v1.2 Evolution

The current architecture will be extended without replacing the pipeline:

1. Shared FFmpeg/FFprobe executable discovery.
2. Unified Provider model defaults and reporting.
3. Knowledge-package integrity validation.
4. Durable user notes.
5. Durable local Web job history.
6. Explicit removal or archival of disabled paths.
7. Testable Gemini image-input Provider boundary.
8. CLI inspection and release metadata.

## Future Scale Architecture

Scale work begins only after v1.2 is stable. Potential additions:

- Durable multi-worker queue.
- Content-addressed media cache.
- Database-backed package index.
- Provider quota routing.
- Batch processing.
- Observable worker lifecycle.

These are not v1.2 requirements and must not be introduced into the local Web server prematurely.

## Future SaaS Architecture

SaaS may add:

- Authentication and tenancy.
- Managed object storage.
- Billing and quotas.
- Hosted worker pools.
- Security and compliance controls.
- Cloud deployment and monitoring.

The local knowledge package remains the portable data contract. SaaS must not force the local core pipeline to depend on Web infrastructure.
