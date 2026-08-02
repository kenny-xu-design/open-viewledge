# Test Baseline

Last verified: 2026-08-02

This baseline applies to committed v1.4.6 identity, duplicate, API-config,
package-claim, recovery, and task-level transcript grouping work plus the
uncommitted v1.4.7 public-boundary tranche on
`feat/v1.4.7-private-public-boundary`.

## Environment

- Project interpreter: Python 3.12.13 from `.venv`.
- Node.js is available for JavaScript syntax validation.
- Tests use repository fixtures and mocks; passing unit tests do not substitute
  for clean-Windows product smoke checks or live third-party service tests.

## Required command matrix

```powershell
.\.venv\Scripts\python.exe -m unittest discover
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m src.main --help
.\.venv\Scripts\python.exe -m src.web --help
node --check src/web_ui/app.js
git diff --check
```

Latest verification:

| Check | Result |
|---|---|
| Full unit suite | PASS, 389 tests |
| v1.4.6 affected suite | PASS, 196 tests |
| v1.4.7 boundary suite | PASS, 7 tests |
| Default `compileall src` | PASS |
| `compileall src` with `PYTHONPYCACHEPREFIX=.local/codex_pycache` | PASS |
| CLI help | PASS |
| Web help | PASS |
| Frontend JavaScript syntax | PASS |
| Git whitespace/error check | PASS |

Focused v1.4.6 command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_knowledge_identity.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_package_claim.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_pipeline_claim.py"
.\.venv\Scripts\python.exe -m unittest tests.test_cli_contract tests.test_job_store tests.test_main tests.test_web tests.test_provider_config
```

Equivalent focused-module command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_knowledge_identity tests.test_package_claim tests.test_pipeline_claim tests.test_pipeline_repair tests.test_cli_contract tests.test_job_store tests.test_main tests.test_web tests.test_web_ui tests.test_provider_config tests.test_transcripts
```

Result: PASS, 196 tests.

v1.4.7 boundary command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_public_boundary
```

Result: PASS, 7 tests. The generator and `verify` command were exercised with a
temporary staging directory at source revision `bae85c6`; they copied the two
allowlisted Schema files, verified both hashes, and passed the secondary scan.

Coverage includes stable identity, request fingerprints, duplicate decisions,
package claim/stale recovery, stale-owner overwrite prevention, Pipeline claim
blocking/release, CLI/Web identity persistence, Web active duplicate rejection,
explicit completed-duplicate reuse, recoverable-duplicate resume,
stage-aware source/transcript repair for incomplete packages,
stable/legacy knowledge-package lookup, Web duplicate decision controls,
API-config session-key test reuse, and task-level transcript grouping with
30-second default, 15-second minimum validation, Web selection, CLI propagation,
and request-fingerprint differentiation.

Runtime audit evidence on 2026-08-02:

- CLI `resume` completed against a deliberately incomplete package while
  reusing the existing source, metadata, and raw transcript artifacts; the
  manifest recorded cache hits for `resolve_source`, `collect_metadata`, and
  `acquire_transcript`.
- In-app Web smoke showed the task-level grouping selector with default `30`
  and options `15/30/60/120`; submitting `15` propagated
  `--transcript-group-seconds 15` to the CLI command.
- A second identical Web request during an active task rendered the duplicate
  decision panel and its `取消` action hid the panel without creating a second
  task.

Full-suite command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Result: PASS, 389 tests.

The default and prefixed `compileall src` checks both pass in the latest run.

## Release artifact verification

Release ZIPs belong to the v1.4.5 beta line. Rebuilding or redistributing them
is a separate task and must be done only from the intended stable source state.

## Failure handling

- Do not lower test counts by excluding failures.
- Do not rewrite historical packages to make inspection pass.
- Treat flaky, timeout, environment, and external-service failures separately.
- A release verifier pass does not authorize public distribution of a
  source-containing ZIP.
