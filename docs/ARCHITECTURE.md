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

### Runtime Tool Discovery

`src/runtime_tools.py` is the shared FFmpeg and FFprobe discovery boundary.

Resolution order:

```text
explicit AppConfig path
-> FFMPEG_PATH / FFPROBE_PATH
-> shutil.which()
-> allowlisted project-local candidates
-> UserFacingError
```

CLI media operations and Web diagnostics use the same resolver. Discovery is lazy for processing commands, so `--help` does not require external media tools.

### Provider Defaults

`src/defaults.py` contains public Provider defaults:

- DeepSeek base URL and model.
- Gemini base URL and model.
- Active summary backend.

Secrets remain environment-only. Provider constructors expose the effective model but never the Key.

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

### Visual Provider Boundary

Gemini image input is isolated from text chat and the processing pipeline:

```text
explicit caller
-> KeyframeAnalysisService
-> GeminiProvider.generate_with_images()
-> Gemini generateContent REST endpoint
```

- Empty frame lists return a local `skipped` result and never call Gemini.
- The Provider accepts JPEG, PNG, and WebP frames as Base64 inline data.
- Image count and aggregate byte limits are enforced before the request.
- `ProviderRegistry` resolves text and image capabilities independently.
- The default pipeline and Web chat do not invoke this boundary.
- Tests use fake HTTP openers and Providers; real API validation remains separate.

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

Local Web state is deliberately small and file based:

```text
output/<knowledge_id>/user_notes.md
output/<knowledge_id>/chat.json
.local/web_jobs.json
```

- Notes and chat are isolated by knowledge package.
- Notes use atomic replacement and revision checks.
- Web jobs are persisted independently of the knowledge package and restored on restart.
- In-process jobs that survive only as records are marked `interrupted`; the Web server does not pretend to resume a subprocess.
- `.local/` is ignored and is not a distributed task queue.

### Export Layer

The package exporter writes JSON and Markdown, including a Jinja2-rendered `index.md`.

`export_note.md` is an Obsidian-compatible Markdown copy. It is not a Vault integration.

### Knowledge-Package Validation

`src/knowledge_validation.py` is the read-only integrity boundary for generated and historical packages.

It validates required files, JSON roots, domain schemas, meaningful transcript content, timeline content, analysis semantics, manifest consistency, and declared outputs.

The pipeline validates newly exported packages before reporting success. The Web UI uses the same inspection result for display status. CLI `inspect` can audit historical packages without rewriting them.

## Retired Paths

The v1.2 branch removed the unreachable pre-orchestrator branch from `src.main`, the unused legacy adapter package, the Ollama summarizer, and the legacy LLM adapter after dependency checks.

The retired comment-analysis prompt is kept only under `docs/archive/prompts/`. The `--comments` option is a compatibility warning and does not activate comment retrieval or analysis.

## v1.2 Evolution

Completed in the v1.2 branch:

1. Durable user notes.
2. Durable local Web job history.
3. Explicit removal or archival of disabled paths.
4. Testable Gemini image-input Provider and keyframe-service boundary.

The remaining architecture work is release completion:

1. Release metadata and final validation.

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
