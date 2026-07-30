# Viewledge Project State

Last verified: 2026-07-30

This is the canonical current-state document. Git state, current code, and
reproducible commands take precedence over older notes.

## Repository baseline

- Repository role: private Viewledge core.
- Current branch: `feat/v1.4.5-portable-release`.
- Upstream: `origin/feat/v1.4.5-portable-release`.
- Current HEAD: `289354a feat(release): prepare Viewledge v1.4.5 portable Windows beta`.
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

## Working-tree baseline at audit start

Pre-existing modified tracked files:

- `README.md`
- `src/analysis/schemas.py`
- `src/analysis/service.py`
- `src/web.py`
- `start_web.bat`
- `tests/test_analysis.py`
- `tests/test_web.py`

Pre-existing untracked file:

- `docs/PRODUCT_RELEASE_STRATEGY.md`

The code changes clamp model-produced timestamps to the known transcript range,
preserve external player embed fields after product redaction, harden the
Windows launcher, and add focused regression tests. These changes are part of
the current candidate state but are not yet committed.

This audit adds or updates project-governance documents only. It does not change
the v1.4.5 processing implementation.

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

A normalized comparison found 112 packaged files identical to the current
working tree and one mismatch: `README.md` changed after the ZIP was built.
Tests are not shipped in the base ZIP. A frozen beta artifact must therefore be
rebuilt from the user-approved stable commit and verified again.

## Test baseline

The current project interpreter is Python 3.12.13. The full suite reports:

```text
Ran 345 tests
OK
```

See `docs/TEST_BASELINE.md` for the complete command matrix. The historical
figures of 312 or 342 tests are not the current baseline.

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

No v1.4.6 implementation, browser extension, public repository, code split,
cloud account system, or paid feature was created during this audit.
