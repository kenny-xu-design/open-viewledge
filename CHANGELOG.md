# Changelog

All notable changes to this project are documented in this file.

## [1.2.0] - 2026-07-16

### Added

- Read-only knowledge-package inspection with JSON output and meaningful exit codes.
- Durable `user_notes.md` storage with revision conflict detection and compatible Markdown refresh.
- Durable local Web job history with interrupted-job recovery.
- Testable Gemini keyframe image-request and analysis-service boundaries.
- Shared project version metadata and CLI/Web version reporting.

### Changed

- Unified FFmpeg and FFprobe discovery across CLI processing and Web diagnostics.
- Centralized DeepSeek and Gemini model defaults and runtime reporting.
- Tightened manifest, transcript, timeline, and analysis consistency validation.
- Clarified Bilibili iframe control limits and Obsidian-compatible Markdown scope.
- Updated README, Agent Skill, architecture, decisions, and roadmap to match active behavior.

### Removed

- Unreachable legacy CLI processing branch.
- Retired adapter package, Ollama summarizer, and legacy LLM adapter.
- Active comment-analysis route; `--comments` remains only as a compatibility warning.

### Verification

- 130 unit tests pass.
- `python -m compileall src` passes.
- `python -m src.main --help` and `python -m src.web --help` pass.
- Gemini image input is mock verified only; no real Gemini API request was made.

### Known Limits

- Gemini keyframe analysis has no CLI or Web product trigger in v1.2.
- Bilibili iframe playback cannot be reliably synchronized by the application.
- Obsidian output is compatible Markdown, not Vault synchronization.
- Scale and SaaS infrastructure are outside v1.2.
