# Changelog

All notable changes to this project are documented in this file.

## [Unreleased] - 1.3.0

### Added

- Stable public `analyze`, `inspect`, `export`, `resume`, `doctor`, and `config` commands.
- Versioned JSON result envelopes and JSONL task/stage/artifact lifecycle events.
- Central exit-code contract and secret-free resumable CLI task records.
- Doctor checks for runtime tools, local models, Providers, storage, and Schema versions.
- Explicit Schema compatibility rules for configuration, tasks, manifests, analysis, and export requests.
- CLI contract, exit-code, Schema, lifecycle, migration, release, security, and privacy documentation.

### Changed

- Web processing now invokes the public `analyze --jsonl` command and consumes lifecycle events.
- Agent Skill now documents only public CLI usage and result/error handling.
- Pipeline and local Whisper diagnostics are routed to stderr while stdout remains machine-readable.
- Root-level analyze options remain as an explicitly deprecated compatibility path.

## [1.2.1] - 2026-07-20

### Added

- Unified analysis-profile resolution with tutorial detection and backward-compatible learning fields.
- Platform-aware timestamp formatting and targets shared by timelines and Markdown exports.
- Selectable Markdown rendering for summary, chat, user notes, tutorial sections, and source materials.
- Safe local Obsidian Vault writes, conflict uniquifying, URI generation, CLI export, Web API, and an original export panel.

### Changed

- Main and compatible notes now share one structured Markdown renderer.
- Package version advanced to 1.2.1.

## [1.2.0] - 2026-07-16

### Added

- Read-only knowledge-package inspection with JSON output and meaningful exit codes.
- Durable `user_notes.md` storage with revision conflict detection and compatible Markdown refresh.
- Durable local Web job history with interrupted-job recovery.
- Testable Gemini keyframe image-request and analysis-service boundaries.
- Shared project version metadata and CLI/Web version reporting.
- Web UI action for retrying failed AI analysis from an existing transcript without reprocessing media.
- Confirmed multi-select deletion for completed knowledge records, restricted to validated package directories.

### Changed

- Unified FFmpeg and FFprobe discovery across CLI processing and Web diagnostics.
- Prevented multiple Windows Web UI processes from sharing port 5188 and serving mixed code versions.
- Renamed the sidebar groups to “资源库” and “产出库”.
- Centralized DeepSeek and Gemini model defaults and runtime reporting.
- Tightened manifest, transcript, timeline, and analysis consistency validation.
- Clarified Bilibili iframe control limits and Obsidian-compatible Markdown scope.
- Updated README, Agent Skill, architecture, decisions, and roadmap to match active behavior.

### Removed

- Unreachable legacy CLI processing branch.
- Retired adapter package, Ollama summarizer, and legacy LLM adapter.
- Active comment-analysis route; `--comments` remains only as a compatibility warning.

### Verification

- 147 unit tests pass.
- `python -m compileall src` passes.
- `python -m src.main --help` and `python -m src.web --help` pass.
- Gemini image input is mock verified only; no real Gemini API request was made.

### Known Limits

- Gemini keyframe analysis has no CLI or Web product trigger in v1.2.
- Bilibili iframe playback cannot be reliably synchronized by the application.
- Obsidian output is compatible Markdown, not Vault synchronization.
- Scale and SaaS infrastructure are outside v1.2.
