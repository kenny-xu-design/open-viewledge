# Decisions

## 2026-07-18: Structured local Markdown export

Analysis profile resolution happens once before analysis. Markdown templates do not infer profile, tags, timestamps, or entities. Obsidian notes are `.md`; `.obsidian` is forbidden as an export destination. Vault paths come only from local server configuration, and SaaS deployments cannot write a user's local Vault.

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

## D010: Comment Analysis Is Disabled (superseded by D021)

This was the v1.2 decision. It is retained as history and is no longer current.

See D021 for the implemented opt-in, separately stored comment contract.

## D011: Platform Preview Must Use Official Boundaries

- YouTube uses the official IFrame API.
- Bilibili uses the official player iframe.
- The product must not claim reliable Bilibili programmatic time synchronization.
- Unsupported or blocked embeds fall back to an external source link.

## D012: Obsidian Means Compatible Markdown In v1.2 (partially superseded)

`--export obsidian` means generating Markdown suitable for use in Obsidian.

The product may also write a generated Markdown file to a locally configured,
server-owned Vault path. It still does not mean:

- Vault discovery;
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

## D015: The Public CLI Is The Automation Boundary

From v1.3, Web, Agent Skills, and automation invoke only the public `python -m src.main <command>` contract. JSON results, JSONL events, exit codes, and Schema versions are centralized. Internal Python call construction is not a public integration contract.

## D016: v1.5 Is Account-Free And Local (superseded by D025)

This was an earlier local-product scope. The current roadmap keeps v1.5.0 and
v1.5.1 usable through a local Bridge, then introduces private cloud accounts,
quota, and the Usage Ledger in v1.5.2. See D025.

Text, visual, and ASR Provider configuration is independent. Optional missing Providers do not block unrelated capabilities. Secrets prefer Windows Credential Manager or the system Keyring and are never returned to the frontend in full.

## D017: Knowledge Package Location Is Runtime Configuration

Knowledge packages belong to the configured output root, not to the HTTP port or the browser origin.

Web, CLI, export, diagnostics, and file serving resolve the same output root. The default remains the project-local `output/`, while `VIEWLEDGE_OUTPUT_ROOT` can point multiple local versions at one shared knowledge-package directory.

## D018: Viewledge Network Proxy Is Process-Scoped Configuration

`VIEWLEDGE_HTTP_PROXY` provides one optional proxy endpoint for Viewledge network clients. At process startup it populates standard HTTP and HTTPS proxy variables only when they are not already configured, so `yt-dlp`, DeepSeek, Gemini, Web jobs, and direct CLI runs follow the same network route.

Runtime diagnostics expose only the proxy source and credential-free endpoint. Existing standard proxy variables take precedence, and Viewledge does not modify the operating system's global proxy configuration.

## D019: Analysis Profiles Share A Flat Report Base

`summary`, `tutorial`, `viral`, and `close-reading` write the flat `summary`, `terminology`, `highlights`, `thoughts`, and `chapters` fields used before the v1.4.3 fixed-section change.

The latter three profiles keep their requested specialized details in `content`, but render only populated modules. Professional terms use the same 3–8 threshold for every profile, and long-video reduction must preserve specialized content. Historical v1.4.3 `content` packages remain readable.

## D020: Local ASR Is Profile-Routed And Quality-Guarded

Local faster-whisper defaults to a balanced profile instead of a fixed
small/CPU route. Candidate selection combines CTranslate2 CUDA visibility,
supported compute types, available VRAM, local model presence, actual model
loading, and an isolated first-batch inference probe.

GPU failure is recoverable: OOM lowers batch size, broken CUDA runtime support
falls through to small CPU INT8, and media is never downloaded again. Only one
local ASR task and one model instance are active per process. Models are always
local-only; quality mode does not implicitly download large-v3.

Balanced and quality outputs retain per-segment quality metrics. Suspect ranges
receive a bounded same-model retry with stronger decoding, after which the best
result is kept and unresolved segments are marked low-confidence.

## D021: Comments Are Explicit, Optional, And Separate

Public comment collection is implemented only when the user explicitly enables
it. Comment fetch and comment analysis are non-blocking stages.

Comment artifacts and opinions remain separate from the main factual
`analysis.json`. A comment failure must not invalidate an otherwise successful
knowledge package.

## D022: The Current Core And History Remain Private

`video-summary-skill` remains the private core repository. It must not be made
public and its Git history must not seed a public repository.

Future public `viewledge-clipper` and `viewledge` repositories use new histories
and receive only explicitly allowlisted files. Private `viewledge-cloud` owns
accounts, plans, quotas, the Usage Ledger, cloud jobs, billing, secret storage,
and abuse prevention.

## D023: Public Contracts Do Not Depend On Private Implementations

Public Schemas describe Intake, inbox, clips, knowledge state, quota/usage
authorization, and stable errors. They must not expose or require private module
names, Provider/model routes, prompts, Worker details, filesystem paths, queue
tables, or billing implementation.

Private core and cloud services may implement public contracts. Public clients
must be buildable and testable from public Schemas alone.

## D024: Knowledge Identity Precedes Browser Intake

Stable `knowledge_id`, duplicate-task recognition, package locking, and
interrupted-task recovery belong in v1.4.6 and must land before browser Intake.

Identity and duplicate detection are implemented test-first. Public clients can
request reuse, refresh, revision, or reject behavior but do not reproduce the
private identity algorithm.

## D025: Cloud Authorization And Usage Are Server-Owned

v1.5.0 and v1.5.1 may use a local Bridge without an account. v1.5.2 introduces
accounts, entitlements, quotas, and an append-only Usage Ledger in the private
cloud repository.

Desktop and browser clients never contain shared production cloud keys. They use
authenticated sessions and short-lived, scoped action authorization. Usage
mutations are idempotent, retries cannot double-charge, and user-visible balance
is derived from ledger entries rather than accepted from clients.

## D026: Internal Source Betas Are Not Public Releases

The v1.4.5 Windows ZIP contains runnable private source and is restricted to
internal or trusted-user testing. Passing release verification does not make it
eligible for a public release.

Future public product artifacts are generated by private build/signing
infrastructure from a user-approved stable commit, scanned through an explicit
allowlist boundary, and introduced only into a fresh-history public repository.

## D027: Knowledge Identity Is Separate From Request Revision

`knowledge_id` identifies normalized source knowledge and remains stable across
analysis or processing choices. A separate `request_fingerprint` identifies an
exact processing request, including language, profiles, transcript-only mode,
comments, sampling, ASR route/fallback, and frame generation.

Public consumers treat `knowledge_id` as opaque and do not reproduce the private
normalization or hashing algorithm. The physical package directory remains
`<title>_<source-id>`.

## D028: Active Exact Duplicates Are Rejected Before Expensive Processing

Web task creation computes v1.4.6 identity before starting the CLI subprocess.
An active exact duplicate is rejected with a duplicate decision. Completed,
recoverable, and same-source revision matches are recorded until explicit
resume/reuse UX is implemented.

## D029: Package Claims Guard Stable Knowledge Writes

v1.4.6 uses a private, atomic package-claim file keyed by stable `knowledge_id`
to prevent concurrent CLI/Web tasks from mutating the same knowledge package.
The claim stores only task/identity metadata, a relative output directory, and
heartbeat timestamps; stale claims may be recovered, and stale owners cannot
overwrite a recovered claim.

## D030: Duplicate Follow-Up Actions Are Explicit

Local Web task creation keeps backward compatibility when no duplicate action is
provided, but explicit duplicate handling uses action names. `reuse` returns an
already completed exact package without starting a new CLI subprocess. `resume`
starts the public CLI `resume` command for a recoverable exact duplicate.
`reject` returns the duplicate conflict. `refresh` and `revision` intentionally
start a new run. Public clients may use the same action vocabulary without
depending on private identity implementation details.

## D031: Recovery Reuses Valid Stage Artifacts Before Reacquiring

v1.4.6 recovery searches existing knowledge packages by stable `knowledge_id`.
When an incomplete package has valid source metadata and a compatible
`transcript.raw.jsonl`, recovery claims that package, records repaired
`resolve_source` and `collect_metadata` stages as cache hits, and skips source
metadata collection, subtitle acquisition, media download, and ASR. Invalid or
dimension-mismatched artifacts are not trusted and are reacquired through the
normal pipeline.

## D032: Duplicate UI Resubmits Through The Same Action Contract

The local Web UI does not invent a separate duplicate-resolution path. It
surfaces the backend duplicate decision and resubmits the original task payload
with one explicit `duplicateAction`. Successful jobs are loaded by stable
`knowledgeId` first, with the historical output directory name kept only as a
fallback.

## D033: Transcript Grouping Is A Task-Level Processing Dimension

v1.4.6 lowers the default transcript grouping target from 60 seconds to 30
seconds and exposes task-level Web choices of 15, 30, 60, and 120 seconds. The
minimum accepted value is 15 seconds. Grouping seconds are included in the
request fingerprint because they change transcript groups, timeline inputs,
analysis context, retrieval granularity, and exported grouped transcripts.

Different grouping choices for the same source are therefore same-source
revisions, not exact duplicates. Historical packages are not silently regrouped.

## D034: Public Publication Is Explicitly Allowlisted

v1.4.7 public output starts from a private, reviewed source-to-destination
allowlist. The generator copies no implicit directories, refuses staging inside
the private repository, and refuses a non-empty destination. A denylist scan is
required as a second gate, but it never replaces the allowlist. This keeps the
publication decision reviewable and prevents accidental inclusion of private
history or source files.

## D035: Public Schemas Have Independent Versioning

Public Bridge Schemas use their own compatibility version (`1.0`) and live as
implementation-independent fixtures. The private package version may change
without changing the public Schema, and public clients must not import private
modules or reproduce identity, Provider, prompt, Worker, or filesystem logic.

## D036: Fresh History Is A Release Gate

Future public repositories are created with fresh Git histories after boundary
and licensing review. The v1.4.7 staging manifest records the private source
revision for auditability only; it is not a permission to publish that history
or to merge private commits into a public repository.

## D037: Structured DeepSeek JSON Uses Non-Thinking Mode

DeepSeek V4 thinking is enabled by default and shares the `max_tokens` budget
with the final answer. For deterministic structured analysis, the private
provider sends `extra_body.thinking.type=disabled`, uses an 8,192-token output
budget, and retries malformed or length-truncated JSON from scratch. This is
limited to JSON analysis; normal chat retains the provider's default behavior.
