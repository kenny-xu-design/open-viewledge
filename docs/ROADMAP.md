# Roadmap

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

Status: completed on `feat/v1.2-product-completion`.

- Persist user notes by knowledge ID.
- Include notes in compatible export.
- Persist Web job history.
- Mark interrupted jobs correctly after restart.

### 5. Disabled Routes And Product Limits

Status: completed on `feat/v1.2-product-completion`.

- Remove or archive unreachable comment and legacy runtime paths.
- Document Bilibili player control limits.
- Keep YouTube IFrame behavior.
- Describe Obsidian output accurately as compatible Markdown.

### 6. Gemini Image Boundary

Status: completed on `feat/v1.2-product-completion`; mock verified, real API unverified.

- Implement image-input requests in the Gemini Provider.
- Skip calls when there are no frames.
- Add mock-based tests.
- Record that real API validation is pending until a user-provided Key is available.

### 7. Release Completion

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
