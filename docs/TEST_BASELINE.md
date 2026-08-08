# Test Baseline

Last verified: 2026-08-07

This baseline applies to committed v1.4.6 identity, duplicate, API-config,
package-claim, recovery, and task-level transcript grouping work plus the
v1.4.7 public-boundary tranche and the uncommitted v1.5.0 local Intake and
Bilibili knowledge-set slices on
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
| Full unit suite | PASS, 409 tests |
| v1.4.6 affected suite | PASS, 196 tests |
| v1.4.7 boundary suite | PASS, 7 tests |
| v1.5.0 Intake/inbox suite | PASS, 11 tests |
| Bilibili series/knowledge-set suite | PASS, 5 focused tests |
| Web UI contract suite | PASS, 48 tests |
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

v1.5.0 Intake/inbox command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_intake_store tests.test_web.WebApiTests.test_bridge_intake_is_idempotent_and_exposes_inbox_state tests.test_web.WebApiTests.test_bridge_intake_requires_idempotency_key tests.test_web.WebApiTests.test_bridge_intake_action_hands_off_to_local_job_once tests.test_web.WebApiTests.test_bridge_intake_action_failure_enters_attention_and_retry_can_recover tests.test_web.WebApiTests.test_bridge_intake_action_rejects_duplicate_intake tests.test_web.WebApiTests.test_bridge_intake_can_be_cancelled_before_handoff
```

Result: PASS, 11 tests. Coverage includes durable replay-safe Intake creation,
URL normalization, page/video identity, active duplicate and source revision
states, captured-text redaction, cursor validation, local Bridge envelope
endpoints, start handoff, retry after needs-attention, duplicate rejection,
pre-handoff cancellation, and action idempotency.

The Bilibili collection command is:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_bilibili_series tests.test_web.WebApiTests.test_bilibili_collection_inspect_create_set_and_analyze_item tests.test_web_ui.WebUiContractTests.test_bilibili_series_detection_offers_knowledge_set_or_current_video
```

Result: PASS, 5 tests. Coverage includes metadata-only multi-P inspection,
playlist ordering, idempotent set creation, per-item reconciliation, private
Web endpoints, and the UI decision panel.

Full-suite command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Result: PASS, 409 tests.

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
