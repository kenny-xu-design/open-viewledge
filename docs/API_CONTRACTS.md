# Viewledge API Contracts

Last updated: 2026-08-14

This document separates implemented local contracts from future public Bridge
contracts. The v1.5.0 first slice implements the local loopback Bridge Intake
and inbox endpoints below; the public browser client remains a separate
allowlisted repository concern.

## Contract levels

| Level | Status | Consumers |
|---|---|---|
| CLI contract 1.x | Implemented and compatibility-sensitive | Local CLI, Web subprocess, Agent/automation |
| Local Web API | Implemented, private and product-internal | Bundled Web UI on the local loopback service |
| Public Bridge API 1.x | Contract fixture plus local v1.5.0 Intake slice | Browser clipper and approved product clients |
| Cloud account/usage API | Design for v1.5.2 | Approved clients through authenticated sessions |

Public consumers must never depend on the local Web API or private Python
imports. The local Web API may evolve with the bundled UI.

The reviewed public Schema fixture is maintained independently at
`public_boundary/schemas/bridge_api_v1.schema.json`. It is copied only through
the v1.4.7 allowlist generator; the fixture is not an import path into `src/`
and does not define Provider, model, prompt, filesystem, or billing details.

## Implemented CLI contract

Entry point:

```text
python -m src.main <command> [options]
```

Commands:

- `analyze`
- `inspect`
- `export`
- `resume`
- `doctor`
- `config`

All commands support a versioned JSON result. Long-running `analyze` and
`resume` commands also support JSONL lifecycle events. Standard output contains
only the requested result/event representation; diagnostics belong on standard
error.

Current versions:

| Object | Version |
|---|---:|
| CLI result envelope | `1.0` |
| JSONL event | `1.0` |
| CLI task record | `1.0` |
| Web job record/store | `1.0` |
| Knowledge manifest | `1.0` |
| Analysis result | `2` |
| Export request | `1.0` |
| Configuration file | `1.0` |

Stable JSON result envelope:

```json
{
  "schema_version": "1.0",
  "command": "analyze",
  "success": true,
  "timestamp": "RFC3339",
  "data": {}
}
```

Stable error object:

```json
{
  "code": "SYMBOLIC_ERROR",
  "exit_code": 1,
  "message": "sanitized user-facing message",
  "retryable": false
}
```

Exit codes `0` through `8` are locked by tests. Existing meanings must not be
changed within CLI major version 1.

Lifecycle event vocabulary:

```text
task_created
stage_started
progress
artifact_created
warning
first_readable_result
stage_completed
task_failed
task_completed
```

Every event contains `schema_version`, `event`, `task_id`, and `timestamp`.
`analysis_profile` and `processing_profile` are separate concepts and fields.

Current `analyze` input includes exactly one URL or local file plus optional
language, analysis profile, processing profile, ASR route/fallback, comment,
frame, sample, transcript grouping, export, and machine-output options.

The v1.4.6 identity contract defines an opaque, versioned `knowledge_id` from
normalized source identity and a separate request fingerprint for exact task
matching. Duplicate decisions distinguish active, completed, recoverable, and
same-source revision cases.

Current local integration:

- `analyze` JSON results include stable `knowledge_id`,
  `identity_schema_version`, and `request_fingerprint`;
- JSONL `task_created` and `task_completed` carry the identity fields;
- CLI task records persist stable `knowledge_id` and `request_fingerprint`;
- Web job records persist identity and duplicate-decision metadata;
- transcript grouping is a task dimension: the default target is 30 seconds,
  Web exposes 15/30/60/120 second choices, and values below 15 seconds are
  rejected before a task starts;
- local Web job creation rejects active exact duplicates before starting the
  CLI subprocess;
- local Web job creation accepts explicit `duplicateAction` values for detected
  duplicates: `reuse` reuses a completed exact package without starting a new
  subprocess, `resume` starts the CLI `resume` command for a recoverable exact
  duplicate, `reject` returns a conflict, and `refresh`/`revision` proceed as a
  new run;
- direct package writes are guarded by an internal atomic claim keyed by stable
  `knowledge_id`; active claims are retryable, stale claims may be recovered,
  and claim records are not public API objects;
- CLI/Web recovery of an incomplete package with a matching stable
  `knowledge_id` reuses valid source information and raw transcript artifacts
  before reacquiring source metadata, subtitles, media, or ASR;
- knowledge-package lookup accepts both stable `knowledge_id` and historical
  package directory name.

Package directories remain the historical `<title>_<source-id>` names for
compatibility. Public clients must always treat `knowledge_id` values as opaque
and must not reproduce the private identity algorithm.

## Implemented knowledge-package contract

Required stable package files:

```text
index.md
metadata.json
manifest.json
analysis.json
timeline.json
source.md
transcript.raw.jsonl
transcript.grouped.md
```

Compatibility readers accept documented legacy defaults, do not rewrite
historical packages merely to add a version, and reject unsupported newer major
versions explicitly.

An analysis-requested package is not successful merely because files exist. It
requires meaningful transcript data, a coherent manifest, a valid analysis
status, a non-empty timeline, and required declared outputs.

User-authored notes and chat state remain separate from generated analysis and
transcript artifacts.

## Implemented local Web API

The local Web service is intended for the bundled UI and binds to loopback by
default. It is not a public or cloud API and currently has no multi-tenant
authentication contract.

Endpoint groups:

- runtime, capability, and masked Provider configuration status;
- knowledge library list/detail, transcript, inspection, allowlisted files, and
  local media streaming;
- local job create/list/detail;
- analysis retry using existing package artifacts;
- chat and user-note persistence;
- local global search over knowledge records, collections, and projects;
- Markdown/Obsidian-ready export preview and generation;
- confirmed knowledge-package deletion.

The private global search endpoint is:

```text
GET /api/search?q=<0-200 chars>&kind=all|knowledge|collection|project&deep=0|1&limit=1..50
```

It is a loopback-only, read-only endpoint used by the bundled Web UI. Empty
`q` returns recently updated assets without scanning transcript or page-body
content. Fast searches cover record metadata, analysis summary/highlights,
tags, notes, collection titles, and project titles. `deep=1` additionally
searches local subtitle or captured-page text and returns only a bounded
sanitized snippet. Results use one shape with `kind`, opaque `id`, `title`,
`subtitle`, `status`, `updatedAt`, `duration`, `itemCount`, `collectionKind`,
`matchField`, `snippet`, `preview`, and `score`. The endpoint never returns
absolute paths, credentials, prompts, raw Provider output, or complete
transcripts. Search indexing is process-local and invalidated by package file
modification signatures; it is not a public Bridge contract.

The current private Web UI also uses these local-only Bilibili knowledge-set
routes:

- `POST /api/source/inspect` accepts a public Bilibili URL and performs a
  metadata-only `yt-dlp` inspection. A multi-P or playlist result returns
  `kind`, `isCollection`, `totalCount`, and ordered `items`; it never downloads
  media.
  The Web validation flow initializes tutorial/complete/30-second settings for
  a detected collection before either knowledge-set creation or current-item
  analysis.
- `GET /api/knowledge-sets` and `GET /api/knowledge-sets/{set_id}` return the
  local ordered set registry. Each item carries its sequence, partition, title,
  source URL, and state (`queued`, `processing`, `ready`, `failed`, or
  `needs_attention`). The linked `/api/library` record exposes optional video
  `duration` and analysis completion timestamp `analysisAt` for the UI metadata
  column.
- `POST /api/knowledge-sets` creates an ordered set from an inspection payload;
  it requires `Idempotency-Key` and does not start analysis.
  It also accepts `analysisProfile`, `processingProfile`, and
  `transcriptGroupSeconds`; these are returned in the set envelope and reused
  for item analysis. Legacy sets default to tutorial/complete/30 seconds.
- `POST /api/knowledge-sets/{set_id}/items/{item_id}/analyze` starts the
  existing local task pipeline for exactly one selected item and reconciles its
  state. Duplicate-task decisions remain private and are returned only as
  sanitized conflict data.

These endpoints are intentionally not part of the public Bridge contract. They
are implementation details of the local product and may change with the
bundled UI.

Product mode removes sensitive implementation fields in backend responses.
Diagnostic mode may expose sanitized technical details locally but must still
never expose credentials, authorization headers, cookies, prompt bodies, or
formal cloud secrets.

The local routes are private implementation details. Public clients must use the
future Bridge contract below.

## Public Bridge API design

Target contract version: `1.0` (independent of the private core package version).

### Common rules

- HTTPS for non-loopback transport.
- Authenticated user or local trusted-session context.
- `Idempotency-Key` required for mutating Intake and clip operations.
- Request and response contain `schema_version`.
- Timestamps use RFC 3339 UTC.
- Unknown optional fields are ignored within major version 1.
- Existing field meaning cannot change within a major version.
- URLs are canonicalized server-side; client hints are not authoritative.
- Responses never contain Provider/model routing, prompts, Worker details,
  filesystem paths, billing internals, or secrets.

### Error envelope

```json
{
  "schema_version": "1.0",
  "request_id": "opaque-request-id",
  "error": {
    "code": "duplicate_intake",
    "message": "user-facing message",
    "retryable": false,
    "details": {}
  }
}
```

`code` is stable. `message` is localized and must not be parsed. `details` may
add optional, non-sensitive fields.

### Create Intake

```text
POST /v1/intakes
```

Request:

```json
{
  "schema_version": "1.0",
  "client_request_id": "client-generated-opaque-id",
  "source": {
    "kind": "video",
    "url": "https://example.invalid/watch/123",
    "canonical_url_hint": "https://example.invalid/watch/123"
  },
  "capture": {
    "title": "Captured title",
    "selected_text": "",
    "visible_text": "",
    "captured_at": "RFC3339"
  },
  "preferences": {
    "analysis_profile": "summary",
    "processing_profile": "fast",
    "output_languages": ["source"]
  },
  "consent": {
    "user_initiated": true,
    "content_upload_allowed": false
  }
}
```

Response:

```json
{
  "schema_version": "1.0",
  "intake_id": "opaque-intake-id",
  "knowledge_id": null,
  "state": "queued",
  "duplicate": {
    "detected": false,
    "knowledge_id": null,
    "allowed_actions": []
  },
  "created_at": "RFC3339"
}
```

Allowed `state` values:

```text
queued
processing
needs_attention
ready
failed
duplicate
cancelled
```

Duplicate handling must use the v1.4.6 identity contract. When a duplicate is
detected, `allowed_actions` may include `reuse`, `refresh`, `revision`, or
`reject`; the public client must not infer the private identity algorithm.

The current private-core implementation supports this contract on the local
loopback Bridge at `/v1/intakes`. It records the capture as `queued` or
`duplicate`, persists an idempotency-safe intake registry, and does not start a
processing subprocess yet. Captured text and implementation diagnostics are
not returned in the Bridge envelope.

### Start or retry an Intake handoff

```text
POST /v1/intakes/{intake_id}/actions
Idempotency-Key: opaque-action-key
```

Request:

```json
{"action": "start"}
```

`start` is allowed for a queued video or page Intake. `retry` is allowed after a
failed or needs-attention handoff. `cancel` is allowed before a task is
started. The local core converts video Intake into the existing task request,
and page Intake into the local page-ingestion path, stores only an opaque local
association, and returns the sanitized Intake state. Repeating the same action
key returns the same result without creating a second task.

### Read Intake and inbox

```text
GET /v1/intakes/{intake_id}
GET /v1/inbox?cursor=<opaque>&limit=<bounded>
```

An inbox item exposes stable product state, source provenance, user-facing
progress, timestamps, and retry/attention actions. It does not expose internal
stage names, subprocess logs, Provider/model routes, or local paths.

The current local slice implements `GET /v1/intakes/{intake_id}` and
`GET /v1/inbox` with cursor pagination. Items currently expose queued or
duplicate state, plus processing/ready/failed/needs-attention after an explicit
action. Internal job IDs, subprocess logs, Provider/model routes, and local
paths remain private.

### Resolve a source URL to local knowledge records

```text
GET /v1/knowledge/resolve?source_url={url}
```

The loopback Bridge normalizes the supplied HTTP(S) URL using the same
tracking-parameter and host/path rules as knowledge identity, then performs a
local package-index lookup. It never fetches the URL. The response contains
ordered matching opaque `knowledge_id` values, sanitized title/source data,
and transcript/analysis availability flags. Local paths, Provider details,
prompts, and process metadata are never returned. Multiple matches represent
historical revisions of the same normalized source; the newest library item
is first.

### Read a knowledge-package transcript

```text
GET /v1/knowledge/{knowledge_id}/transcript
```

The loopback Bridge returns an opaque knowledge ID, sanitized source kind and
URL, title, and ordered transcript/page groups. It never returns local package
paths, Provider/model details, prompts, or raw process logs. This read contract
is the server-side foundation for the future public Side Panel; the Side Panel
itself remains in `viewledge-clipper` and is not part of this private core.

For video records, group `start` and `end` are media seconds. For captured web
pages, groups use `contentKind: "web_page"`, a one-based `position`, and
`start`/`end: null`; the Bridge never fabricates `00:00` media timestamps for
page text.

The local server does not enable cross-origin Bridge access by default. For a
locally installed, reviewed extension build, the operator may explicitly set
`VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN` to that exact `chrome-extension://...`
origin. Only that exact origin receives CORS response headers; requests never
include credentials. This opt-in is a local integration setting, not a public
authentication or cloud authorization mechanism.

The reviewed Side Panel client separately restricts its configurable Bridge
base to the local loopback hosts `localhost`, `127.0.0.1`, and `[::1]`. A remote
HTTP(S) base is rejected before any transcript, clip, or Intake request is sent.
Active-page HTTP(S) URLs containing embedded username/password credentials are
also rejected, and URL fragments are removed before local source resolution.
The client also validates the `schema_version: "1.0"` envelope and requires
exactly one of `data` or `error`; malformed or unsupported responses become a
sanitized client error rather than being rendered as product data.

The local Web process may be pointed at an operator-selected writable state
directory with `VIEWLEDGE_STATE_ROOT`; when unset, the existing `.local`
directory remains the default. The official Windows launchers set this to
`%LOCALAPPDATA%\Viewledge\state` when no override is supplied.

### Create clip

```text
POST /v1/clips
```

Request:

```json
{
  "schema_version": "1.0",
  "client_request_id": "client-generated-opaque-id",
  "kind": "clip",
  "target": {
    "intake_id": "opaque-intake-id",
    "knowledge_id": null
  },
  "source": {
    "url": "https://example.invalid/article",
    "title": "Page title"
  },
  "selection": {
    "text": "User-selected text",
    "prefix": "",
    "suffix": "",
    "media_start_seconds": null,
    "media_end_seconds": null
  },
  "note": "",
  "captured_at": "RFC3339"
}
```

`kind` is optional and defaults to `clip`; `highlight` stores the same bounded
selection and provenance as a visually distinguished user highlight. The
response returns an opaque `clip_id`, resolved target identifiers, and
provenance status. Every clip must preserve its original URL and, when
available, media time range or page selection context.

For page captures, `selection.media_start_seconds` and
`selection.media_end_seconds` are `null`; page character positions are not
represented as fake media timestamps. Video subtitle clips may carry the
actual non-negative media range.

The current local loopback implementation supports `POST /v1/clips`,
`GET /v1/clips/{clip_id}`, and filtered `GET /v1/clips`. The private Web
transcript reader uses the same create contract for its per-group “clip”
action, sending bounded neighboring context and the group's media range when
available. Creation is
idempotent, requires user-provided selected text and an HTTP(S) source URL, and
stores only the bounded clip payload in private local state. It never fetches
the page or accepts cookies, headers, filesystem paths, or Provider details.
The stored source URL uses the same tracking-parameter, host, path, and
fragment normalization as the knowledge-identity contract.

The private transcript reader also exposes a user-triggered receive action for a
group or an in-group text selection. It creates a `page` Intake through
`POST /v1/intakes`, carries only the selected text and HTTP(S) source URL,
sets `content_upload_allowed=false`, and refreshes the local knowledge inbox.
The reader does not auto-start that Intake; the user starts or cancels it from
the inbox, preserving the explicit-consent and idempotency contract.

The candidate MV3 Side Panel uses the same contract without private imports. It
offers separate user actions for `kind=clip` and `kind=highlight`, keeps the
most recent in-group selection in memory until submission, and assigns an
independent idempotency key to each action. This client behavior is validated
by private boundary tests and the allowlist staging verifier; it is not a
public repository or a cloud-authenticated client.
The page Intake action is limited to web-page groups; video subtitle groups
remain subtitle/media records and expose timestamp seeking instead.
The boundary client enforces this source-type check inside the action handler as
well as hiding the button, so a future UI refactor cannot turn a video subtitle
into a page capture by accident.

## Cloud account and Usage Ledger design

These endpoints belong to private `viewledge-cloud` and are planned for v1.5.2.
They are not implemented by the local Web service.

Public concepts:

- account/session;
- plan and entitlement summary;
- quota availability;
- usage authorization/reservation;
- settled/refunded outcome;
- user-visible ledger entry.

Clients may receive an opaque, short-lived authorization for a specific action.
They never receive formal Provider, billing, signing, or infrastructure keys.

Every usage mutation requires an idempotency key. Retries must return the same
reservation or settlement result instead of consuming quota twice. User-visible
balances are derived from an append-only ledger, not accepted from clients.

## Privacy and logging

## Local folder collections (v1.5.0 working slice)

```text
POST /api/source/inspect {"sourceType":"file","source":"<local path>"}
POST /api/folder-sets
GET  /api/folder-sets
POST /api/folder-sets/{set_id}/items/{item_id}/analyze
POST /api/folder-sets/{set_id}/analyze-all
POST /api/folder-sets/{set_id}/children
POST /api/folder-sets/{set_id}/parent
POST /api/folder-sets/{set_id}/reorder
```

Folder-set creation accepts optional `analysisProfile`, `processingProfile`,
and `transcriptGroupSeconds` fields. The path-validation UI supplies the
current validated values (tutorial/complete/30 by default); the returned set
envelope exposes the same fields, and item or subtree analysis reuses them when
the action does not override a setting. Legacy state without these fields is
read as tutorial/complete/30 for compatibility.

Folder inspection accepts a local directory or single supported video file and recognizes common video
extensions including `.ts`. The tree is limited to three levels (depth 0-2).
Only child folder sets are reorderable; video/package items are explicitly
non-draggable and retain their scan sequence. Public responses return relative
names and opaque IDs only; single-file inspection also omits the absolute path;
absolute paths remain private. `analyze-all` starts
the existing file-processing jobs and inherits their provider, ASR fallback,
duplicate, and idempotency contracts.

- Capture only data required for a user-triggered action.
- Do not include complete page content by default when selected text or a URL is
  sufficient.
- Do not log request bodies that may contain captured content or notes.
- Store sanitized error codes separately from private diagnostic detail.
- Public issue/report exports remove credentials, private paths, Provider/model
  routing, prompt data, and user content unless the user explicitly includes a
  reviewed excerpt.
- Retention, export, and deletion behavior must be documented before cloud
  rollout.

## Contract change process

The v1.5.0 release freeze does not change the knowledge identity, duplicate,
recovery, knowledge-package, or Bridge `1.0` wire contracts. v1.5.1 continues
to use Bridge `1.0`; additive optional fields require compatibility tests, and
an incompatible change requires a separately versioned public Schema.

Account, entitlement, quota, task-authorization, and Usage Ledger contracts
start in the separate private `viewledge-cloud` v1.5.2 scope. The desktop and
browser clients may receive only user credentials or opaque short-lived action
authorizations, never formal Provider or infrastructure keys.

1. Update public Schema fixtures first.
2. Add compatibility tests independent of private classes.
3. Implement the contract in private core/cloud.
4. Generate the public Schema/client allowlist output.
5. Verify an older client against the new server.
6. Increment the major version only for an intentionally incompatible change.

## Local project grouping and collection membership

The local Web sidebar uses these private, loopback-only endpoints:

```text
GET    /api/projects
POST   /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
PUT    /api/projects/{project_id}/records/{knowledge_id}
DELETE /api/projects/{project_id}/records/{knowledge_id}
```

Project creation requires `Idempotency-Key`. A knowledge record belongs to at
most one user project; `PUT` moves it from any previous project. Deleting a
project or removing a member only deletes grouping metadata and never deletes
or rewrites a knowledge package. Project state lives in
`<output-root>/projects/registry.json`; stale member IDs are ignored in public
responses without rewriting the registry during reads.

`GET /api/library` additionally exposes `inCollection`,
`collectionMemberships`, and `projectId`. Collection membership is derived
from the existing video-series and local-folder registries. It does not change
either registry or the knowledge-package format.
