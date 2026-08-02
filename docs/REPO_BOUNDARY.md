# Repository Boundary

Last updated: 2026-08-02

This document defines the long-term private/public ownership boundary. It is a
design and governance contract; it does not authorize repository creation or
code publication.

## Repository map

| Repository | Visibility | Responsibility |
|---|---|---|
| `video-summary-skill` | Private | Core pipeline, source handling, subtitles/ASR, Providers, prompts, analysis, knowledge packages, research algorithms, private builds and tests |
| `viewledge-cloud` | Private | Accounts, plans, entitlements, quotas, Usage Ledger, cloud jobs, billing, secret storage, rate limits and abuse prevention |
| `viewledge-clipper` | Public, future | Thin browser client, Manifest, Popup, Side Panel, page capture, public Schemas and Bridge API client |
| `viewledge` | Public, future | Product presentation, downloads, installation docs, public changelog/roadmap, privacy policy, issues and feedback |

The two public repositories must be created separately with new Git histories.
They must not be derived by changing visibility, deleting a few files, filtering
the current history, or pushing a branch from either private repository.

## Private-only assets

The following remain private:

- video source adapters and normalization;
- subtitle acquisition and fallback decisions;
- cloud/local ASR implementation;
- ASR Worker, device selection, quality retry, and GPU-to-CPU fallback;
- Provider implementations, credentials, model routing, and cost routing;
- prompt text, prompt assembly, repair prompts, and analysis constraints;
- analysis templates and validation/repair implementation;
- comment, visual, ranking, multi-source, and research algorithms;
- knowledge identity, duplicate detection, locks, and recovery internals;
- account, plan, quota, Usage Ledger, billing, and anti-abuse logic;
- private build, packaging, signing, release scanning, and operational tooling;
- private tests, fixtures, architecture notes, incident details, and full Git
  histories.

## Allowlisted public assets

Only explicitly reviewed assets may be public:

- Chrome extension Manifest with least-privilege permissions;
- Popup and Side Panel UI;
- page metadata, selected-text, and user-triggered capture code;
- Bridge API client;
- public request/response Schemas and error codes;
- public product documentation and installation guides;
- privacy policy, terms, support, and issue templates;
- release notes and links to approved signed product packages.

An asset is not public merely because it is frontend code or documentation.
Anything outside the publication allowlist is denied by default.

## Publication rules

1. Public repositories use fresh Git histories.
2. Public files are generated or copied into a clean staging directory from an
   explicit allowlist.
3. A denylist is only a secondary scan; it never replaces the allowlist.
4. The staging output is scanned for secrets, credentials, private paths,
   prompt text, private module names, internal routes, source maps, debug logs,
   user data, local models, and source archives.
5. Public artifacts are built and signed through private infrastructure.
6. Only the reviewed staging result is introduced into a public repository.
7. Public repository commits never merge from private histories.
8. A release manifest records source revision, public Schema versions, artifact
   hashes, dependency notices, and approval without exposing private history.

## v1.4.7 boundary tooling

The first v1.4.7 boundary milestone is represented by the private
`public_boundary/allowlist.json` and `scripts/public_boundary.py` tooling. The
allowlist is default-deny: every source file needs an explicit destination, and
missing entries fail the build. The generator refuses an output directory inside
the private repository or a non-empty output directory, then writes a
deterministic `publication-manifest.json` containing the source revision,
independent public Schema versions, and SHA-256 hashes.

The generator runs a secondary sensitive-data scan over the clean staging
directory. The scan rejects private path components, source archives, machine
absolute paths, credentials, authorization/cookie headers, key-shaped values,
and private module/prompt/Provider/Worker references. A passing scan is a gate,
not publication approval: licensing review, human boundary review, fresh Git
history, private build/signing, and release approval remain mandatory.

The current allowlist contains only the implementation-independent Bridge API
Schema fixture and its public usage note. It intentionally creates no public
repository and does not copy private source, tests, prompts, models, or build
outputs.

## Contract direction

Public contracts must describe product concepts only:

- Intake request;
- inbox item;
- clip and provenance;
- knowledge status;
- quota/usage authorization result;
- stable error envelope.

They must not require:

- private Python module names or class paths;
- Provider or model identifiers;
- prompt versions or prompt bodies;
- Worker/PID/device details;
- filesystem paths;
- internal queue, table, or billing implementation details.

The private core and private cloud may implement public contracts. Public
clients must be replaceable without importing private packages.

## Credential boundary

- Browser and desktop clients never contain a shared production cloud key.
- User-provided local Provider credentials remain local and are masked.
- Cloud authentication uses user sessions and short-lived, scoped tokens.
- Formal Provider, billing, signing, and infrastructure credentials remain in
  private server-side secret storage.
- Logs, API responses, exports, crash reports, and public issue templates must
  redact secrets and machine-specific paths.

## Browser boundary

The public clipper is a thin client. It may:

- read allowlisted page metadata after explicit user action;
- capture selected text and visible page context within granted permissions;
- show inbox state returned by the Bridge contract;
- navigate official player/page timestamps where supported.

It must not:

- embed private prompts or analysis algorithms;
- perform hidden bulk crawling;
- bypass authentication, paywalls, DRM, or access controls;
- store formal cloud keys;
- expose private Provider/model routing;
- execute the private processing pipeline.

## Release boundary

Internal source packages may contain the private runtime for trusted testing but
must remain private.

Future public product packages must be produced by the private build system and
must not directly ship:

- the core source tree;
- tests or private fixtures;
- prompts;
- Provider implementations;
- ASR Worker source;
- internal documentation;
- developer launchers;
- Git metadata;
- local environment, models, media, output, or credentials.

No packaging approach is assumed to make reverse engineering impossible.
Packaging, signing, licensing, attribution, antivirus behavior, update and
rollback must be reviewed before a public release.

### No-source packaging comparison

| Approach | Boundary result | Decision for v1.4.7 |
|---|---|---|
| Internal source ZIP | Ships private implementation, tests, prompts, and operational detail | Rejected for public release; remains private/trusted-user only |
| Bundled desktop executable | Can reduce casual source exposure, but still embeds core behavior and requires private signing, dependency, and update review | Deferred; not a public boundary deliverable in v1.4.7 |
| Thin public clipper + private Bridge/cloud | Public history contains only the reviewed browser client and public Schemas; processing and credentials remain private | Preferred public architecture for v1.4.7/v1.5.x |
| Remote-only private service | Strongest core isolation, but requires account, quota, privacy, outage, and abuse controls | Deferred until private cloud/account milestones |

The v1.4.7 decision is therefore to publish only the thin public client and
implementation-independent Schemas after review. The private core remains a
separate implementation and is not made public by packaging.

## Current audit limit

This audit creates no repository, performs no code split, generates no public
artifact, and changes no repository visibility.
