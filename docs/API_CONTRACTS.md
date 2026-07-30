# Viewledge API Contracts

Last updated: 2026-07-30

This document separates implemented local contracts from future public Bridge
contracts. A documented future contract is not an implemented endpoint.

## Contract levels

| Level | Status | Consumers |
|---|---|---|
| CLI contract 1.x | Implemented and compatibility-sensitive | Local CLI, Web subprocess, Agent/automation |
| Local Web API | Implemented, private and product-internal | Bundled Web UI on the local loopback service |
| Public Bridge API 1.x | Design for v1.4.7/v1.5.x | Browser clipper and approved product clients |
| Cloud account/usage API | Design for v1.5.2 | Approved clients through authenticated sessions |

Public consumers must never depend on the local Web API or private Python
imports. The local Web API may evolve with the bundled UI.

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
frame, sample, export, and machine-output options.

The current `knowledge_id` is a package identifier, but v1.4.6 must formalize
its deterministic identity and duplicate semantics before it becomes part of a
public Intake contract.

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
- Markdown/Obsidian-ready export preview and generation;
- confirmed knowledge-package deletion.

Product mode removes sensitive implementation fields in backend responses.
Diagnostic mode may expose sanitized technical details locally but must still
never expose credentials, authorization headers, cookies, prompt bodies, or
formal cloud secrets.

The local routes are private implementation details. Public clients must use the
future Bridge contract below.

## Public Bridge API design

Target contract version: `1.0`.

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

### Read Intake and inbox

```text
GET /v1/intakes/{intake_id}
GET /v1/inbox?cursor=<opaque>&limit=<bounded>
```

An inbox item exposes stable product state, source provenance, user-facing
progress, timestamps, and retry/attention actions. It does not expose internal
stage names, subprocess logs, Provider/model routes, or local paths.

### Create clip

```text
POST /v1/clips
```

Request:

```json
{
  "schema_version": "1.0",
  "client_request_id": "client-generated-opaque-id",
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

The response returns an opaque `clip_id`, resolved target identifiers, and
provenance status. Every clip must preserve its original URL and, when
available, media time range or page selection context.

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

1. Update public Schema fixtures first.
2. Add compatibility tests independent of private classes.
3. Implement the contract in private core/cloud.
4. Generate the public Schema/client allowlist output.
5. Verify an older client against the new server.
6. Increment the major version only for an intentionally incompatible change.
