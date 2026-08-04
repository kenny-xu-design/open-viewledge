# Viewledge Project State

Last verified: 2026-08-02

This is the canonical current-state document. Git state, current code, and
reproducible commands take precedence over older notes.

## Repository baseline

- Repository role: private Viewledge core.
- Current branch: `feat/v1.4.7-private-public-boundary`.
- Branch point/current HEAD: `bae85c6 v1.4.6`.
- The branch currently has no upstream and has no new commit yet.
- Package version: `1.4.5`, defined by `src/__init__.py`.
- No release tag was created during this audit.
- The working tree is intentionally uncommitted. No staging, commit, push,
  merge, rebase, or tag action was performed.

## v1.4.5 implemented baseline

The verified v1.4.5 candidate provides:

- a local-first URL and local-media processing pipeline;
- platform subtitles first, followed by selectable cloud or local ASR routes;
- the stable isolated local ASR Worker and GPU-to-CPU recovery path;
- summary, tutorial, viral, and close-reading analysis profiles;
- adaptive long-video segmentation and structured timestamped output;
- optional public-comment collection with separate comment insight artifacts;
- local Web product mode and developer-only diagnostic mode;
- backend redaction of product-facing capability, job, knowledge, and chat
  payloads;
- a portable Windows launcher, bundled FFmpeg/FFprobe, and a user-writable
  knowledge directory default;
- Markdown and Obsidian-ready knowledge-package export;
- an internal base Windows ZIP and a separate local ASR model extension ZIP.

The current base ZIP contains runnable Python source and is therefore an
internal or trusted-user beta artifact only. It is not eligible for a public
release.

## v1.4.6 identity, duplicate, and claim baseline

The current v1.4.6 working tree adds:

- a versioned opaque `knowledge_id` from normalized source identity;
- a separate `request_fingerprint` for processing dimensions;
- duplicate decisions for active exact, completed exact, recoverable exact, and
  same-source revision cases;
- manifest, CLI task record, Web job record, JSONL, and local Web API
  persistence of identity fields;
- Web active-exact duplicate rejection before starting the CLI subprocess;
- explicit Web duplicate actions: `reuse` returns an already completed exact
  package without starting a new CLI subprocess, `resume` starts
  `src.main resume <task_id> --jsonl` for a recoverable exact duplicate,
  `reject` returns the duplicate conflict, and `refresh`/`revision` keep the
  existing new-run behavior;
- stable `knowledge_id` library lookup while preserving historical directory
  lookup;
- package-level atomic claims under `.viewledge_claims/`, heartbeat refresh on
  manifest save, normal release on success/failure, stale-claim recovery, and
  stale-owner overwrite prevention;
- stage-aware repair for incomplete packages with a matching stable
  `knowledge_id`: recovery reuses valid manifest/metadata source information
  and `transcript.raw.jsonl` instead of reacquiring source metadata, subtitles,
  media, or ASR;
- task-level subtitle grouping selection: default target grouping is now 30
  seconds, Web exposes 15/30/60/120 second choices, CLI accepts
  `--transcript-group-seconds`, and grouping seconds participate in the
  request fingerprint so different grouping requests are same-source revisions
  rather than exact duplicates;
- the API configuration regression fix: testing a saved Provider with empty
  input fields reuses the process-local saved session configuration.

Historical package directories remain `<title>_<source-id>/`. Stable
`knowledge_id` is the manifest/API identifier, not the physical directory name.

## v1.4.7 boundary milestone

The branch is based exactly on the committed v1.4.6 baseline. The initial
boundary tranche adds:

- `public_boundary/allowlist.json` with explicit source-to-destination entries;
- an implementation-independent Bridge API 1.0 Schema fixture and public note;
- `scripts/public_boundary.py build`, which stages only allowlisted files into a
  clean directory outside this repository and emits deterministic hashes;
- `scripts/public_boundary.py scan`, which blocks sensitive values, private path
  components, and private implementation references.
- `scripts/public_boundary.py verify`, which checks the generated file set and
  SHA-256 hashes before any handoff.
- The desktop sidebar now uses a fixed, translucent overlay layer instead of
  reserving a grid column that narrows the summary reading surface; narrow
  screens retain the same drawer interaction and accessibility state.
- DeepSeek model configuration accepts the console label pattern
  `DeepSeek-V4-Flash-####` and normalizes it to the official API model ID
  `deepseek-v4-flash` before a request is sent. The default remains the stable
  API ID, so no provider key or internal route is exposed by this compatibility
  rule.
- Structured DeepSeek analysis requests disable V4 thinking mode, reserve an
  8,192-token JSON budget, and retry malformed/truncated output from scratch;
  the provider keeps its existing empty-content retry and sanitized errors.

The generator is private release tooling. No public repository, code split,
public release artifact, or history transfer exists. Human boundary/licensing
review and fresh-history publication remain future gates.

## Local-only development launcher

`start_dev.bat` exists locally and is excluded by the repository-local
`.git/info/exclude` rule `/start_dev.bat`. It is not tracked, is not reported as
an untracked file, and is absent from the audited release ZIP.

## Release artifacts

The ignored `release/` directory currently contains:

- `Viewledge-v1.4.5-windows.zip` and its SHA-256 sidecar;
- `Viewledge-local-asr-small-model.zip` and its SHA-256 sidecar;
- the older `Viewledge-v1.4.3-source.zip`.

The v1.4.5 base ZIP and model extension:

- pass their recorded SHA-256 checks;
- pass `scripts/verify_release.py`;
- contain the required runtime files;
- contain no `.env`, `.git`, or `start_dev.bat` entries;
- execute the bundled FFmpeg and FFprobe version checks successfully.

An earlier normalized comparison found 112 packaged files identical to the
working tree at that time and one mismatch: `README.md` had changed after the
ZIP was built. The current ZIP predates the committed v1.4.6 changes and the
current v1.4.7 boundary tranche, so it is not a v1.4.6 or v1.4.7 artifact.
Tests are not shipped in the base ZIP. A frozen beta artifact must therefore be
rebuilt from the user-approved stable commit and verified again.

## Test baseline

The current project interpreter is Python 3.12.13. The latest full suite
reports:

```text
Ran 386 tests
OK
```

See `docs/TEST_BASELINE.md` for the current command matrix.

## Documentation truth

- `README.md` correctly identifies v1.4.5 as a private internal portable beta
  and is broadly aligned with the implementation.
- The former `docs/CURRENT_STATE.md` described `main`, v1.4.3, and 312 tests.
  It was obsolete and now redirects here.
- The former `docs/ROADMAP.md` used the older v1.2-v1.5 phase model. It was
  obsolete and now redirects to `docs/MASTER_ROADMAP.md`.
- `CHANGELOG.md`, `docs/CURRENT_TASK.md`, `docs/CODEX_HANDOFF.md`, and several
  `docs/V1_4_*` files remain useful historical records but contain older version
  or task status. They are not authoritative for current work.
- Historical license files remain present and require a separate licensing
  decision before public distribution. This audit does not delete or replace
  them.

## Freeze assessment

v1.4.5 has a technically healthy beta candidate: the full unit suite and release
verification pass, product-mode redaction is covered, and the portable artifacts
exist.

It is not yet a frozen `v1.4.5-beta.1` baseline because:

- the working tree is dirty and the candidate fixes are not committed;
- the current ZIP does not contain the latest README;
- no user-approved stable commit or tag exists for the audited state;
- a rebuilt artifact and final clean-Windows/manual product smoke check are
  still required;
- the direct CLI help succeeded but Chinese text rendered as mojibake in this
  audit shell, so clean-Windows user-visible text still needs confirmation;
- public licensing and no-source packaging are intentionally unresolved and do
  not apply to this internal source beta.

The freeze decision is therefore: **conditional candidate, not yet frozen**.

## Scope boundary

The v1.4.6 identity, duplicate, API-config, package-claim, explicit Web
duplicate-action API/UI, task-level transcript grouping, and initial
stage-aware repair units are in the working tree. The final audit has now
verified CLI recovery against an incomplete package, Web active-duplicate
decision handling, and the 15/30/60/120-second grouping selector. No browser
extension, public repository, code split, cloud account system, or paid feature
was created. User review and a stable commit are still pending.
