# Decisions

This file records durable product and architecture decisions. Historical experiments belong in `docs/archive/`.

## D001: One Core Pipeline

CLI, Web, Agent Skill, and future products must use the same processing pipeline and knowledge-package contract.

The Web UI may start the CLI as a subprocess, but it must not reimplement media processing.

## D002: Local Media Processing Remains Local

`yt-dlp`, FFmpeg, and faster-whisper remain local components.

The project does not silently download large models or binaries and does not modify the system PATH.

## D003: Platform Subtitles First

For public video URLs:

1. Try platform subtitles or automatic subtitles.
2. Skip ASR when usable subtitles exist.
3. Otherwise acquire audio-only media.
4. Normalize with FFmpeg only when required.
5. Transcribe with the local ASR Provider.

## D004: No bilibili-cli Runtime Dependency

Bilibili URLs are handled by the project's own source layer and `yt-dlp`.

The project does not:

- depend on `bilibili-cli`;
- call its CLI;
- copy its source;
- require it for Bilibili processing.

## D005: DeepSeek Is The Active CLI Analysis Provider

CLI structured analysis currently uses DeepSeek.

- The Key belongs in ignored `.env`.
- Provider and model are recorded in package metadata.
- Missing configuration is an explicit failure, not a simulated success.
- Ollama is not an active runtime backend.

## D006: Gemini Has A Separate Capability Boundary

Gemini text completion can be used by Web chat when configured.

Image-input support is a separate Provider capability exposed through `KeyframeAnalysisService`. It is not part of the default pipeline or text-chat path, and an empty frame set must never produce a network call.

The image request code and service boundary are mock tested. Real API validation must be reported separately and remains unverified.

## D007: Knowledge Packages Are The Data Contract

Generated files are not merely UI artifacts. A package must have:

- a valid source record;
- meaningful transcript data;
- coherent manifest stage status;
- valid analysis status when analysis is requested;
- allowlisted, portable outputs.

File existence alone is not proof of success.

## D008: User Content Must Be Separate From Generated Content

User-authored notes must be stored in a dedicated package-adjacent file and must not overwrite generated transcript, analysis, or source files.

## D009: Web Jobs Stay Local In v1.2

v1.2 may use a lightweight local persistence mechanism for jobs.

It must not introduce a cloud queue, hosted worker system, or SaaS infrastructure. Interrupted jobs must not remain displayed as running after restart.

## D010: Comment Analysis Is Disabled

Comment retrieval and comment analysis are not current product features.

Compatibility flags may produce a deprecation message, but docs and UI must not advertise comment analysis.

## D011: Platform Preview Must Use Official Boundaries

- YouTube uses the official IFrame API.
- Bilibili uses the official player iframe.
- The product must not claim reliable Bilibili programmatic time synchronization.
- Unsupported or blocked embeds fall back to an external source link.

## D012: Obsidian Means Compatible Markdown In v1.2

`--export obsidian` means generating Markdown suitable for use in Obsidian.

It does not mean:

- Vault discovery;
- direct Vault writes;
- synchronization;
- bidirectional note management.

## D013: Secrets And Local Assets Stay Out Of Git

Never track:

- `.env`;
- API Keys or Authorization headers;
- local models;
- media;
- generated output;
- virtual environments;
- local job databases;
- caches and logs.

Tracked examples contain empty secret values only.

## D014: Scale And SaaS Are Later Phases

v1.2 completes the local product. Scale and SaaS work must remain separate and must build on, rather than fork, the local pipeline and package contract.
