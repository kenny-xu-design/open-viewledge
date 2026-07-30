# Viewledge Product Release Strategy

> Internal development document. Do not copy this file into a future public
> showcase repository or public release package.
>
> The repository and release-boundary principles remain current. Its older
> version-number route is superseded by `MASTER_ROADMAP.md`: repository/public
> packaging boundaries move to v1.4.7, and v1.5.0 begins Browser Intake and the
> knowledge inbox.

## Purpose

Viewledge will use a private-core, public-product release model until a separate
open-source decision and license review is completed.

The working direction is:

- Keep the core implementation private.
- Make the product publicly available through compiled or packaged releases.
- Do not publish release packages that allow direct reuse of the core Python
  source tree.
- Use a future public GitHub repository only for product presentation, release
  downloads, documentation, issues, feedback, and roadmap communication.

This strategy does not claim perfect protection. Local applications can be
reverse engineered. The goal is to raise the copy threshold from "copy source,
rename, and republish" to "reverse engineer, analyze, reconstruct, and retest".

## Current Baseline

- Current private development branch: `feat/v1.4.5-portable-release`.
- v1.4.4 established the stable core loop for video parsing, subtitles, ASR,
  AI analysis, and knowledge package generation.
- v1.4.5 adds product mode, diagnostic separation, portable FFmpeg, Windows
  launcher hardening, capability redaction, and release build verification.
- The current v1.4.5 Windows ZIP still includes the Python source required to
  run the product.
- Therefore the current ZIP is an internal and trusted-user beta package, not a
  public GitHub Release artifact.

## Private Core Repository Boundary

The current `video-summary-skill` repository should remain private.

It may contain:

- `src/`
- `tests/`
- pipeline orchestration and task state logic
- source adapters and subtitle acquisition
- `TranscriptionRouter`
- ASR Worker and GPU to CPU fallback control
- provider implementations
- prompt templates and analysis profile constraints
- analysis validation and repair logic
- knowledge package generation
- `CapabilityRegistry`
- release build scripts
- internal architecture and decision documents
- full Git history
- local diagnostic launchers and development-only configuration

All core development continues in this repository.

Do not convert this private repository directly to Public. Do not push its full
Git history into a public repository.

## Future Public Showcase Repository Boundary

A separate future repository, for example `Viewledge`, may be created for public
product presentation.

That repository may contain:

- product introduction
- screenshots
- demo GIFs or videos
- user-facing usage guides
- update notes and changelog
- roadmap
- issues and feedback
- privacy statement
- GitHub Release download links

It must clearly say:

```text
This repository is for Viewledge product presentation, releases, and feedback.
The core source code is not public at this time.
```

It must not contain:

- `src/`
- `tests/`
- complete internal `requirements.txt`
- `pyproject.toml` or internal build configuration
- provider implementations
- ASR routing or Worker code
- prompt templates
- internal architecture documentation
- developer machine configuration
- `start_dev.bat`
- Python-source release packages
- full technical stack explanations

The public repository must not pretend to be an open-source code repository.

## Release Package Boundary

### Internal Test Package

The current v1.4.5 ZIP belongs to this category.

It may contain:

- Python runtime source
- structures needed for debugging
- local development validation assets

It is intended only for:

- personal testing
- trusted-user testing
- clean Windows smoke tests

It must not be uploaded to a public GitHub Release.

### Future Public Product Package

The public package should use `Viewledge.exe` or an equivalent compiled product
entry point.

Target structure:

```text
Viewledge/
├─ Viewledge.exe
├─ runtime/
├─ tools/
│  └─ ffmpeg/
├─ web_assets/
├─ licenses/
├─ README-使用说明.md
└─ start_viewledge.bat
```

The public package must not directly include:

- `src/`
- `tests/`
- core `*.py` source files
- prompt source text
- provider implementations
- pipeline implementation
- ASR Worker source
- development comments and internal test tools
- `start_dev.bat`
- `.git`
- `.venv`
- `.env`
- API keys, cookies, credentials, or user data

## Product Mode And Diagnostic Mode

Public product entry points default to product mode.

Product mode must hide or redact:

- developer machine paths
- Python executable and virtual environment details
- provider names and provider internals
- concrete model names
- CUDA, cuDNN, CTranslate2, Worker, PID, and exit codes
- raw subprocess logs
- API keys, cookies, request headers, and credentials

Redaction must happen in backend API responses as well as the frontend. Frontend
only hiding is not sufficient.

Diagnostic mode is local and developer-only:

- launched by `start_dev.bat`
- excluded through `.git/info/exclude`
- not tracked by Git
- not included in any release package
- allowed to show necessary redacted technical information
- still prohibited from showing API keys, cookies, headers, or credentials

## Protected Core Capabilities

The following modules and behaviors are high-value private assets:

- `PipelineOrchestrator`
- `TranscriptionRouter`
- ASR Worker
- GPU to CPU fallback control
- task state machine
- incremental stage decisions
- knowledge identity and duplicate task handling
- analysis result validation and repair
- prompt structures and four analysis profile constraints
- batch analysis and future commercial capabilities

Public material may expose only product-level concepts such as screenshots,
usage flow, Markdown export examples, redacted release notes, and generic feature
descriptions.

## Commercial Capability Layering

Local baseline capabilities:

- single video analysis
- platform subtitle acquisition
- basic transcription
- basic summarization
- Markdown knowledge package generation
- local reading and search

Future advanced capabilities:

- batch video analysis
- creator account analysis
- viral account and work-pattern research
- advanced analysis templates
- cloud task queues
- account quotas
- subscriptions
- team knowledge spaces

High-value commercial capabilities should not all be shipped as static local
client code. A future architecture can keep the local client responsible for
capture, baseline processing, display, and local data management, while a server
handles account permissions, quotas, advanced batch analysis, commercial
templates, and continuously updated capabilities.

This document records the direction only. It does not implement SaaS.

## Version Route

### v1.4.5

Position: internal portable beta.

Scope:

- product mode
- diagnostic isolation
- Windows startup hardening
- portable FFmpeg
- data directory checks
- capability redaction
- basic release build

The source ZIP is internal only.

### v1.4.6

Position: private-core stability enhancement.

Scope:

- stable `knowledge_id`
- duplicate task recognition for the same video
- reuse / refresh / revision / reject
- knowledge package locks
- stale lock recovery
- interrupted task recovery
- run AI analysis only
- incremental stage repair

This version remains in the private repository. The product protection route
does not cancel v1.4.6.

### v1.5.0

Position: public product release foundation.

Scope:

- review and choose a no-source Windows release approach
- compile or package core Python modules
- avoid shipping `src/` in public packages
- build and verify public product artifacts
- establish private-core to public-showcase release flow
- separate internal source packages from public product packages
- complete clean Windows first-run validation

Before implementation, compare packaging candidates on:

- source exposure
- Windows compatibility
- first startup speed
- package size
- web static asset handling
- multiprocessing Worker compatibility
- FFmpeg invocation
- local GPU and CPU ASR
- dynamic dependencies
- upgrades and patches
- antivirus false positives
- build reproducibility

Do not choose a packaging tool before this review.

### v1.5.1

Position: knowledge capture and export experience.

Scope:

- modular Markdown export
- AI chat export
- user note export
- Obsidian-ready knowledge packages
- safe Vault writing
- export path safety checks
- opening export results

Until fully implemented, public wording should use:

```text
Obsidian-ready Markdown knowledge packages
```

Do not advertise:

```text
Direct Obsidian Sync
```

## Public Messaging Boundary

Allowed public wording:

- Local-first AI video analysis
- Video knowledge extraction
- Subtitle-first processing
- Optional transcription
- Structured summaries
- Visual timelines
- Video Q&A
- Markdown knowledge packages
- Windows Beta
- Obsidian-ready

Avoid public wording for now:

- Open-source
- OpenViewledge
- Direct Obsidian Sync
- AGPL
- Whisper
- DeepSeek
- Groq
- Gemini
- CUDA
- CTranslate2
- concrete model names
- complete internal architecture diagrams

This is a positioning choice. These technologies may exist internally, but the
current strategy does not publicly disclose the implementation route.

## Public GitHub Release Flow

Recommended future flow:

```text
private core repository development
-> tests pass
-> private build script generates public product package
-> sensitive data and source scans
-> clean Windows validation
-> manual upload to public showcase repository Release
-> public README, changelog, and download notes update
```

Forbidden:

- converting the private repository directly to Public
- pushing the private repository's full Git history to a public repository
- uploading source-containing ZIPs to public Releases
- relying on public branches to hide implementation details
- creating a so-called hidden source branch in a public repository

All branches in a public repository must be treated as public content.

## Conflicts With Current Repository State

- `README.md` should not describe Viewledge as an AGPL Community Edition or
  open-source project. It should state that the core source is currently private
  and that v1.4.5 source ZIPs are internal or trusted-user beta packages.
- `LICENSE` and `COMMERCIAL-LICENSE.md` still contain historical AGPL and
  commercial licensing materials. These files require a separate licensing
  decision and should not be deleted or replaced as part of ordinary README
  cleanup.
- The current v1.4.5 ZIP contains runnable Python source. It must remain an
  internal or trusted-user package until v1.5.0 establishes a no-source public
  package.
- The current release build scripts produce internal beta artifacts, not final
  public product packages.
- Frontend static resources remain inspectable in a local web product. A future
  public packaging review must decide what static assets are acceptable to ship.
- Existing provider and model details still exist in private docs and code. The
  public showcase repository must not copy private technical documentation.

## Risks And Open Decisions

- Python compiled or packaged artifacts can still be reverse engineered.
- Frontend static assets may be readable by users.
- FFmpeg and third-party components require license files and attribution.
- Model file redistribution rights must be reviewed separately.
- Public product packages require credential, path, source, and private metadata
  scans before release.
- Packaging may break multiprocessing, GPU detection, local ASR, dynamic
  libraries, or FFmpeg invocation.
- Self-packaged Windows executables may trigger antivirus false positives.
- No-source packaging increases the copying threshold but does not provide
  absolute protection.
- High-value commercial features should eventually move behind server-side
  authorization and update control.
- A formal license and public-use policy must be decided before any public
  repository or broad public release.
