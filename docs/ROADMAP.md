# Roadmap

> Compatibility entry point. The canonical forward plan is
> [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md). The material below is the older
> v1.2-v1.5 planning model and is retained only as historical context.

- [x] v1.2.1 structured tutorial profile and backward-compatible analysis fields.
- [x] Unified Markdown/Obsidian export with summary, chat, and user-note selection.
- [x] Safe local Vault writes and Obsidian URI generation.
- [ ] Keyframe export enrichment beyond existing artifacts.
- [ ] Notion/Readwise and cloud Vault synchronization remain explicitly deferred.

The roadmap is split into local product completion, later Scale work, and possible SaaS work.

## v1.2 Product Completion

Goal: finish the existing local product without redesigning it.

### 1. Documentation Truth

- Align Skill and README with the active implementation.
- Establish current-state, architecture, roadmap, and decision documents.
- Archive historical route documents.

### 2. Runtime Discovery And Configuration

- Add project-level FFmpeg and FFprobe discovery.
- Support explicit configuration and environment variables.
- Keep discovery lazy.
- Unify Provider and model defaults across code and examples.

### 3. Knowledge-Package Integrity

- Define minimum transcript, analysis, timeline, and manifest validity.
- Add an inspection entry point.
- Detect historical invalid packages without silently rewriting them.
- Prevent empty analysis from appearing successful.

### 4. Local Persistence

Status: released in `v1.2.1`.

- Persist user notes by knowledge ID.
- Include notes in compatible export.
- Persist Web job history.
- Mark interrupted jobs correctly after restart.

### 5. Disabled Routes And Product Limits

Status: released in `v1.2.1`.

- Remove or archive unreachable comment and legacy runtime paths.
- Document Bilibili player control limits.
- Keep YouTube IFrame behavior.
- Describe Obsidian output accurately as compatible Markdown.

### 6. Gemini Image Boundary

Status: released in `v1.2.1`; mock verified, real API unverified.

- Implement image-input requests in the Gemini Provider.
- Skip calls when there are no frames.
- Add mock-based tests.
- Record that real API validation is pending until a user-provided Key is available.

### 7. Release Completion

Status: released in `v1.2.1`.

- Complete CLI inspection and validation commands.
- Align Web and CLI contracts.
- Add release notes and version metadata.
- Run the full suite and diff review.

## Scale

Scale begins after v1.2 is released and stable.

Candidate work:

- Durable worker queue.
- Parallel media processing.
- Content-addressed caching.
- Package indexing and search.
- Batch APIs.
- Provider rate-limit and cost controls.
- Operational metrics and structured logs.

Scale must preserve the knowledge-package contract and must not fork the core processing logic.

## SaaS

SaaS is a separate product phase.

Candidate work:

- User accounts and organizations.
- Tenant isolation.
- Managed storage.
- Hosted media workers.
- Subscription and quota management.
- Cloud secret management.
- Abuse prevention and compliance.
- Deployment, monitoring, and support tooling.

No SaaS infrastructure belongs in the v1.2 local product completion branch.

## v1.3 Agent And CLI Contract

- Stable `analyze`, `inspect`, `export`, `resume`, `doctor`, and `config` commands.
- JSON results, JSONL lifecycle events, centralized exit codes, and versioned Schemas.
- Public CLI as the only Web/Agent automation boundary.
- Backward-compatible legacy CLI entry during the deprecation window.

## v1.4 Scale Foundation

- Durable local queue and worker leases behind abstractions.
- Idempotency, retries, stage-specific concurrency, cost ledger, batches, and observability.
- Preserve the complete v1.3 CLI contract.

## v1.5 Local Product

- No registration, login, or email verification.
- Default local workspace and skippable first-run API wizard.
- Shared Provider Catalog and credential service for Web, CLI, and Worker.
- Independent text, visual, and ASR Provider setup.
- Windows Credential Manager/system Keyring, masked status, connection test, Key update/delete.
- OpenAI-compatible custom Providers only in advanced settings.
