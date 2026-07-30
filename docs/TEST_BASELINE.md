# Test Baseline

Last verified: 2026-07-30

This baseline applies to the uncommitted v1.4.5 candidate on
`feat/v1.4.5-portable-release`. A future commit or rebuilt artifact must rerun
the same matrix.

## Environment

- Project interpreter: Python 3.12.13 from `.venv`.
- The current shell does not expose a system `python` command on `PATH`.
- Node.js is available for JavaScript syntax validation.
- Tests use repository fixtures and mocks; passing unit tests do not substitute
  for a clean-Windows product smoke check or live third-party service tests.

## Required command matrix

Use the project interpreter when `python` is not on `PATH`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m src.main --help
.\.venv\Scripts\python.exe -m src.web --help
node --check src/web_ui/app.js
git diff --check
```

Verified result:

| Check | Result |
|---|---|
| Full unit suite | PASS — 345 tests |
| `compileall src` | PASS |
| CLI help | PASS |
| Web help | PASS |
| Frontend JavaScript syntax | PASS |
| Git whitespace/error check | PASS |

The current baseline is 345 tests. Older documentation mentioning 312 tests and
the handoff clue mentioning 342 tests are superseded by this run.

The CLI help command returned exit code 0, but the current PowerShell capture
rendered its Chinese help text as mojibake. This is a console-encoding
observation, not a unit-test failure; the clean-Windows launcher smoke test
should confirm user-visible text independently.

## Release artifact verification

Command:

```powershell
.\.venv\Scripts\python.exe scripts\verify_release.py
```

Result: PASS.

The verifier confirms:

- base ZIP SHA-256 matches its sidecar;
- required base files are present;
- forbidden release content scan passes;
- product launcher tokens are present;
- package version is 1.4.5;
- bundled FFmpeg and FFprobe execute;
- model extension SHA-256 matches its sidecar;
- required local ASR model files are present;
- model download cache metadata is absent.

Additional read-only inspection confirms the base and model ZIPs contain no
`.env`, `.git`, or `start_dev.bat` entries.

## Freeze gates not covered by unit tests

Before declaring `v1.4.5-beta.1` frozen:

- user reviews and commits the intended stable baseline;
- rebuild both applicable release artifacts from that exact commit;
- verify artifact hashes and package-to-commit provenance;
- run the complete matrix again from a clean checkout;
- run a clean-Windows first-launch test with no pre-existing `.venv`;
- verify the default product UI reveals no private paths, raw process logs,
  Provider/model routing, or credentials;
- verify local knowledge data is written only to the intended user-writable
  directory;
- verify base-only behavior and model-extension installation separately;
- document any live Provider or platform checks as separate, credential-free
  acceptance evidence.

## Failure handling

- Do not lower test counts by excluding failures.
- Do not rewrite historical packages to make inspection pass.
- Treat flaky, timeout, environment, and external-service failures separately.
- A release verifier pass does not authorize public distribution of the current
  source-containing ZIP.
