# Codex Log

This file stores concise summaries of Codex work for this project.

## 2026-07-09

- Created the standard Codex documentation structure.

## 2026-08-02

- Completed the v1.4.6 stabilization audit on the uncommitted working tree.
- Verified CLI recovery from an incomplete package, Web active-duplicate
  handling, and the 15/30/60/120-second task-level transcript grouping UI.
- Re-ran 382 full tests and 196 focused v1.4.6 tests; all passed. No Git
  staging, commit, push, merge, rebase, or tag action was performed.
- Created `feat/v1.4.7-private-public-boundary` from committed `bae85c6 v1.4.6`
  after user-created branch setup.
- Added the first v1.4.7 boundary tranche: explicit public allowlist,
  implementation-independent Bridge Schema fixture, deterministic staging
  manifest, and secondary sensitive-data scan with unit coverage. No public
  repository or public artifact was created.
- Extended the v1.4.7 boundary tranche with `verify` hash/file-set validation,
  public Schema independence examples, tamper detection, a no-source packaging
  comparison, and the private release handoff checklist. A temporary dry run at
  `bae85c6` copied only the two reviewed Schema files and passed `verify`.
- Added a regression test proving `.git` metadata cannot enter allowlisted
  staging output; the full suite now passes 389 tests.
