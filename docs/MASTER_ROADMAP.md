# Viewledge Master Roadmap

Last updated: 2026-08-02

This is the canonical forward roadmap. Version scopes are ordered dependencies,
not promises of public release dates.

## Product direction

```text
browser discovery
-> knowledge inbox
-> subtitles or cloud/local transcription
-> structured analysis
-> claims, evidence, and timestamps
-> bilingual knowledge package
-> multi-source research
-> Obsidian and personal knowledge assets
-> creator-account batch research
```

## Cross-version rules

- Keep `video-summary-skill` private and preserve one core processing pipeline.
- Keep current Git history private; public repositories start with new history.
- Freeze a version before starting the next version branch.
- Preserve knowledge-package and public contract compatibility.
- Keep formal cloud keys and commercial authorization on the server.
- Do not destabilize the ASR Worker or GPU-to-CPU fallback without a blocking
  defect and focused regression coverage.
- Each version requires unit, compile, CLI/Web help, JavaScript, diff, privacy,
  and relevant manual acceptance checks.

## v1.4.5 — Portable internal beta freeze

Status: candidate implemented; freeze audit pending user-approved stable commit.

Scope:

- product/diagnostic mode separation;
- portable Windows launcher and FFmpeg runtime;
- internal base ZIP and optional local ASR model extension;
- backend product-detail redaction;
- release scanning and verification.

Exit criteria:

- all candidate changes are reviewed and committed by the user;
- a fresh `v1.4.5-beta.1` artifact is built from that exact commit;
- automated verification and clean-Windows product smoke checks pass;
- internal source ZIPs are not uploaded to a public release.

## v1.4.6 — Knowledge identity, duplicate tasks, and recovery

Status: implementation complete and audit-verified in the uncommitted working
tree. Identity/request-fingerprint, duplicate decisions, runtime persistence,
Web task-entry integration, API-config session-test reuse, package-level
claim/stale-claim recovery, task-level transcript grouping, and initial
stage-aware package repair are implemented and tested. The final audit verified
CLI recovery against an incomplete package, Web active-duplicate decision
handling, and the 15/30/60/120-second grouping selector. User review and a
stable commit remain pending.

Scope:

- deterministic `knowledge_id` based on normalized source identity;
- separate request fingerprint for relevant processing dimensions;
- duplicate-task detection before expensive work begins;
- explicit reuse, refresh, revision, or reject decisions;
- package-level locking and stale-lock recovery;
- interrupted-task recovery and stage-aware repair;
- analysis-only rerun using existing valid transcript artifacts;
- unit tests first for identity and duplicate detection.

Exit criteria:

- the same source cannot accidentally create conflicting concurrent packages;
- identity is stable across CLI, Web, and later Intake clients;
- interrupted work can resume without reacquiring valid artifacts;
- legacy packages remain readable.

## v1.4.7 — Private/public architecture boundary

Status: implementation in progress on `feat/v1.4.7-private-public-boundary`.

The first boundary milestone now has a reviewed allowlist, independent public
Bridge Schema fixture, deterministic staging manifest, and secondary sensitive
data scan. No public repository or public artifact has been created.

The next gate is an independently reviewed clean staging run with `verify`,
followed by the documented no-source packaging decision and licensing review.

Scope:

- codify the four-repository ownership model;
- version public Schemas independently of private implementations;
- create an allowlist-based public artifact generator and sensitive-data scan;
- define private build/signing and public release handoff;
- decide the no-source packaging approach through a documented comparison;
- create new public repositories only after boundary and licensing review.

Exit criteria:

- public outputs can be reproduced from an explicit allowlist;
- public contracts contain no private module, prompt, Provider route, secret, or
  machine-path dependency;
- private history cannot leak through the publication workflow.

## v1.5.0 — Browser Intake and knowledge inbox

Status: planned.

Repository ownership:

- thin capture client in future `viewledge-clipper`;
- public Schemas and product documentation in future `viewledge`;
- ingestion, normalization, processing, and identity in private services/core.

Scope:

- Chrome extension Manifest and minimal permissions;
- page/video discovery and explicit user-triggered capture;
- Bridge API client with idempotent Intake requests;
- knowledge inbox with queued, processing, needs-attention, ready, failed, and
  duplicate states;
- source provenance, capture time, canonical URL, and user intent;
- local Bridge first, with cloud transport remaining an interchangeable
  contract implementation.

Exit criteria:

- a user can capture a supported page/video into the inbox without exposing
  private implementation details;
- repeated capture is safely deduplicated through v1.4.6 identity;
- the extension contains no production cloud key or private algorithm.

## v1.5.1 — Subtitle side panel and web clipping

Status: planned.

Scope:

- Side Panel transcript reading and timestamp navigation;
- search, copy, note, highlight, and selected-text clipping;
- provenance for quote, page location, media time range, and source URL;
- clip-to-existing-knowledge and clip-to-new-intake flows;
- clear permission, privacy, unsupported-page, and restricted-content behavior.

Exit criteria:

- every clip retains source provenance and can be traced back to its page or
  media timestamp;
- clipping remains user-triggered and does not bypass access control;
- public client behavior is testable against public Schemas alone.

## v1.5.2 — Accounts, quota, and Usage Ledger

Status: planned.

Repository ownership: private `viewledge-cloud`.

Scope:

- accounts, sessions, plans, entitlements, and tenant isolation;
- immutable append-only Usage Ledger;
- reservation, authorization, settlement, refund, and reconciliation states;
- per-capability quotas, cost controls, rate limits, and abuse prevention;
- cloud jobs linked to Intake without placing formal service credentials in
  desktop or browser code.

Exit criteria:

- every billable or quota-consuming action is traceable and idempotent;
- client-visible balance is derived from the ledger, not a mutable counter;
- retries cannot double-charge;
- authorization and tenant boundaries pass security review.

## v1.5.3 — Bilingual knowledge packages

Status: planned.

Scope:

- source-language preservation plus a selected second language;
- aligned titles, summaries, claims, evidence, chapters, quotes, and timestamps;
- glossary and named-entity consistency across languages;
- per-field translation provenance and missing/partial states;
- bilingual Markdown, JSON, and Obsidian-ready export.

Exit criteria:

- translated claims remain linked to the same evidence and timestamps;
- users can distinguish source text, translation, and generated inference;
- monolingual historical packages remain compatible.

## v1.6.0 — Multi-source research

Status: planned.

Scope:

- research projects containing multiple knowledge packages and clips;
- source comparison, claim clustering, evidence matrix, agreement/conflict
  detection, and research gaps;
- citation and timestamp preservation through synthesis;
- incremental updates when sources are added or refreshed;
- exportable research dossier.

Exit criteria:

- every synthesis statement links to one or more source artifacts;
- conflicting sources are represented rather than silently collapsed;
- project recomputation reuses unchanged source analyses.

## v1.6.1 — Creator Intelligence

Status: planned.

Scope:

- explicit creator/account research jobs;
- bounded batch ingestion and refresh policies;
- topic, format, hook, cadence, audience, evidence, and performance pattern
  analysis;
- cross-video and cross-period comparison;
- reusable creator research reports with provenance;
- commercial capability authorization through private cloud controls.

Exit criteria:

- batch work is resumable, quota-aware, and auditable;
- platform rules, user authorization, and rate limits are respected;
- reported patterns are linked to specific source works and time ranges.

## v1.7.0 — Paid beta

Status: planned.

Scope:

- onboarding, plans, payment integration, quota UX, and support flow;
- privacy policy, terms, data retention, deletion, export, and incident process;
- signed builds, update channel, rollback, telemetry consent, and operational
  monitoring;
- billing reconciliation, abuse controls, and support tooling;
- controlled cohort release with explicit service limits.

Exit criteria:

- security, privacy, licensing, billing, recovery, and support readiness reviews
  pass;
- usage and payment records reconcile;
- users can export and delete their data;
- public documentation describes the product without disclosing private core
  implementation.

## Dependency chain

```text
v1.4.5 freeze
-> v1.4.6 identity and recovery
-> v1.4.7 repository and contract boundary
-> v1.5.0 Intake/inbox
-> v1.5.1 side panel/clipping
-> v1.5.2 accounts/ledger
-> v1.5.3 bilingual package
-> v1.6.0 multi-source research
-> v1.6.1 Creator Intelligence
-> v1.7.0 paid beta
```
