# Viewledge Master Roadmap

Last updated: 2026-08-17

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

## Incremental feature consolidation

The following increments are part of the existing version chain; they do not
create an extra release number or justify starting v1.6 early.

| Increment | Version | Current disposition |
| --- | --- | --- |
| Stable `knowledge_id`, duplicate decisions, package claims, interrupted-task recovery, analysis-only rerun | v1.4.6 → v1.5.0 | Implemented, committed, and absorbed into the v1.5.0 baseline |
| 30-second subtitle grouping default with 15/30/60/120-second choices; saved API-config test reuse | v1.4.6 → v1.5.0 | Implemented and covered by regression tests |
| Private/public repository boundary, allowlist staging, translucent overlay sidebar, DeepSeek V4 Flash compatibility, malformed/truncated JSON retry | v1.4.7 → v1.5.0 | Implemented and absorbed into the v1.5.0 baseline; no public history was created |
| Bilibili P-part/series metadata inspection, ordered knowledge-set creation, item-scoped analysis, duplicate/failure reconciliation | v1.5.0 | Implemented; formal release freeze and clean-Windows acceptance remain |
| Local page Intake, three-level folder collections, projects, resource overview, global search, and resource governance | v1.5.0 | Implemented and committed at source baseline `3854828` |
| Subtitle Side Panel, clipping, highlighting, focus reading, and public Bridge client | v1.5.1 | Private prototype implemented; real Chrome acceptance remains |

### Version progression gates

1. **v1.5.0 formal freeze** — align the visible version, documentation, test
   baseline, and Windows artifact; pass real Bilibili-series, local-folder,
   page-Intake, global-search, API-configuration, restart, and clean-Windows
   acceptance without changing knowledge identity or package Schemas.
2. **v1.5.1 Side Panel acceptance** — validate the allowlisted MV3 client in
   real Chrome, including exact-Origin CORS, timestamp navigation, focus
   reading, clip/highlight replay, unsupported pages, and service restarts.
3. **v1.5.2 private cloud foundation** — create accounts, sessions, plans,
   entitlements, quotas, and an idempotent append-only Usage Ledger in the
   separate private `viewledge-cloud` repository.
4. **v1.5.3+ knowledge and research value** — add bilingual packages,
   multi-source research, Creator Intelligence, and paid beta in dependency
   order, with all billable work authorized through the ledger.

## v1.4.5 — Portable internal beta freeze

Status: historical internal portable baseline. Its stable processing and
portable-runtime behavior is preserved in v1.5.0; it is no longer an active
release target.

Scope:

- product/diagnostic mode separation;
- portable Windows launcher and FFmpeg runtime;
- internal base ZIP and optional local ASR model extension;
- backend product-detail redaction;
- release scanning and verification.

Historical closure:

- the portable launcher, FFmpeg runtime, product-mode redaction, and internal
  source ZIP behavior are preserved as compatibility requirements in v1.5.0;
- the historical v1.4.5 ZIP remains internal-only and is not rebuilt as a new
  release line;
- no v1.4.5 public repository, public artifact, or history transfer exists.

## v1.4.6 — Knowledge identity, duplicate tasks, and recovery

Status: implementation complete, committed, and consolidated into the v1.5.0
release baseline. Identity/request-fingerprint, duplicate decisions, runtime
persistence, API-config reuse, package claims, recovery, transcript grouping,
and stage-aware repair remain compatibility requirements.

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

Status: boundary milestone implemented and consolidated into v1.5.0. The
private repository remains private; no public repository or history migration
has been created.

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

Status: formal freeze in progress on `release/v1.5.0`, based on committed source
baseline `3854828`. Automated validation passes 483 tests; release-artifact and
remaining clean-Windows/manual acceptance gates are tracked separately.

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

Implemented first slice:

- `POST /v1/intakes` accepts only explicit user-triggered captures and requires
  `Idempotency-Key`;
- `GET /v1/intakes/{intake_id}` and `GET /v1/inbox` expose sanitized queued or
  duplicate state;
- URL normalization and opaque identity/request-fingerprint generation reuse
  the v1.4.6 contract;
- repeated exact captures are marked duplicate without starting analysis;
- local intake records persist under private local state and never return
  captured text by default.
- explicit `start`, `retry`, and pre-handoff `cancel` actions;
- queued video handoff to the existing local task API with sanitized
  processing-state reconciliation.
- Bilibili multi-part/series inspection with a user choice between analyzing
  the current video and creating an ordered knowledge set first;
- private local knowledge-set persistence with per-item, on-demand analysis;
- ordered partition/title/source metadata retained without downloading media
  during set creation.
- knowledge-set cards can be collapsed without hiding the separate knowledge
  record list;
- completed set items surface linked package duration and analysis date in one
  compact metadata column;
- completed set items resolve to the same knowledge record and package used by
  the main library, preventing a set-only phantom entry.
- three-level local folder collections with explicit path validation, movable
  child sets, fixed video-item order, and item/subtree analysis;
- user-managed projects that group records without moving or rewriting their
  knowledge packages;
- a resource overview, output-collection navigation, responsive compute
  governance, and unified local global search with opt-in transcript/page-body
  matching.

The local page ingestion adapter, Inbox UI, and loopback Bridge handoff are now
implemented. The remaining public-client work is the future thin browser
capture client; no private Provider or pipeline detail may cross that boundary.

Exit criteria:

- a user can capture a supported page/video into the inbox without exposing
  private implementation details;
- repeated capture is safely deduplicated through v1.4.6 identity;
- the extension contains no production cloud key or private algorithm;
- the visible package and release-builder version is `1.5.0`;
- the internal Windows ZIP is rebuilt from the release branch and passes the
  release verifier and sensitive-data scan;
- real series, folder, Intake, search, API-configuration, restart, and
  clean-Windows acceptance are recorded against the exact release candidate.

## v1.5.1 — Subtitle side panel and web clipping

Status: Bridge contract and private Web transcript clipping slice implemented;
boundary-only MV3 client prototype implemented; public repository remains
planned and unpublished.

Development resumes from the final v1.5.0 freeze commit. v1.5.0 functionality
such as projects, resource overview, global search, and folder collections is
not re-scoped or reimplemented in this version.

Current acceptance state: the allowlisted MV3 directory passes staging and
verification, the Manifest references existing module/service-worker and Side
Panel files, and the local client exposes copy, clip, highlight, and inbox
actions. Final release status remains pending Chrome unpacked-extension smoke.

Scope:

- Side Panel transcript reading and timestamp navigation;
- video subtitle groups expose an explicit user-triggered seek action that
  updates the current page's time parameter without reading page content;
- after a seek changes the page URL, source resolution ignores only playback
  position parameters (`t` and `start`) so the same knowledge record remains
  readable while the current URL is retained for provenance;
- an explicit focus-reading mode with larger subtitle cards, while keeping
  transcript text isolated inside the extension rather than injecting it into
  host-page DOM;
- search, copy, note, highlight, and selected-text clipping;
- provenance for quote, page location, media time range, and source URL;
- clip-to-existing-knowledge and clip-to-new-intake flows;
- page Intake is shown only for captured web-page groups; video subtitle groups
  cannot be mislabeled as page captures;
- clear permission, privacy, unsupported-page, and restricted-content behavior.

Current private validation slice:

- Web transcript/page reading exposes a user-triggered clip action per group;
- a URL-resolution Bridge lookup lets a future Side Panel discover matching
  local knowledge IDs without receiving filesystem details;
- the action prefers an in-group text selection and falls back to the full
  group when no text is selected;
- the reader keeps the most recent valid in-group selection in memory so a
  button click cannot accidentally erase the user's selected-text intent;
- the candidate Side Panel exposes a bounded note field for clip and highlight
  actions, capped at 500 characters before the Bridge request;
- clip and highlight idempotency keys are kept in Side Panel session state by
  knowledge ID, group index, and action kind, so search re-renders do not create
  a second record after a lost response;
- an optional bounded note can be attached in the transcript reader and is
  shown again in the saved-clips list;
- the private Web transcript view can load and review saved clips by knowledge
  ID;
- clips preserve source URL, bounded neighboring context, knowledge ID, and
  optional media time range through `POST /v1/clips`;
- the transcript reader can send a selected group or in-group selection to the
  v1.5.0 knowledge inbox as a page Intake without auto-starting processing;
- the same Bridge clip record supports a durable `highlight` kind, rendered
  distinctly in the saved selection list;
- the action refuses records without a safe HTTP source and does not fetch page
  content or expose private filesystem/provider data.
- a candidate MV3 Side Panel under `public_boundary/client/` reads the active
  HTTP(S) URL, resolves the newest opaque match, reads ordered groups, and
  creates a clip only after an explicit click; it uses no private imports,
  credentials, or hidden page crawling;
- tab activation and active-tab URL changes trigger a fresh local resolution,
  keeping the Side Panel aligned with the page currently being viewed;
- cross-origin use is closed by default and requires the local operator to set
  one exact `VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN` value.
- the prototype can send selected text to the knowledge inbox with
  `content_upload_allowed=false`; it never starts processing implicitly.
- unmatched pages and transient local Bridge failures show a sanitized empty
  state with an explicit Retry action; raw Bridge error details are not copied
  into the public client UI.
- the private Web transcript reader and boundary Side Panel keep a stable
  idempotency key for the same knowledge/group/action and request content;
  changing the selected text or bounded note intentionally creates a new key.
- portable Web launches route the cache under the external state root, keeping
  read-only project directories usable without changing the ASR or package
  processing contract.

The v1.5.1 local acceptance slice is now automation-complete for the private
core and boundary contract. A real Chrome unpacked-extension smoke remains a
release-facing manual check, not a prerequisite for the local Bridge/API
contract to be exercised in CI or focused tests.

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

## v1.5.0 incremental slice: local folder collections

The Intake/inbox phase now has a local-core extension for importing a folder
of videos as a private knowledge-set tree. Path validation is explicit, the
tree is capped at three levels, child sets can be reordered, and individual
video packages remain fixed-sequence items. Explorer-style quoted Windows
paths are normalized consistently during validation, registration, and local
media resolution, while empty paths are rejected. Folder-set video rows reuse
the same compact duration/analysis-date metadata column when a package is
ready. Batch analysis walks the selected folder subtree, and failed task
startup returns items to a retryable failed state instead of leaving them
stuck in processing. The validation click persists tutorial/complete/30-second
defaults with the folder-set record, and later item or subtree runs reuse those
settings. This slice is local and does not expand the public
repository boundary.

## Dependency chain

```text
v1.5.0 local knowledge-workspace freeze
-> v1.5.1 side panel/clipping
-> v1.5.2 accounts/ledger
-> v1.5.3 bilingual package
-> v1.6.0 multi-source research
-> v1.6.1 Creator Intelligence
-> v1.7.0 paid beta
```
