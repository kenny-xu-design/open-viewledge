# Viewledge Working Rules

## Repository role

- This repository is the private Viewledge core.
- Keep pipeline orchestration, source adapters, subtitle/ASR implementation,
  Provider integration, prompts, analysis and research algorithms, knowledge
  packages, private build logic, and tests private.
- Never make this repository public, publish its Git history, or use it as the
  history seed of a public repository.
- Public repositories must be created separately with new Git histories and
  populated by an explicit allowlist. See `docs/REPO_BOUNDARY.md`.

## Start-of-task checks

- Read `AGENTS.md`, `PROJECT_GUIDE.md` when present, and `README.md`.
- Run `git status --short --branch` before editing.
- Treat code, Git state, and reproducible runtime results as authoritative when
  older documentation disagrees.
- Record durable current-state, roadmap, contract, boundary, test, and decision
  changes in the corresponding files under `docs/`.

## Change control

- Make the smallest change that satisfies the requested task.
- Do not create a worktree, switch or create branches, move the repository, or
  raise the project major version unless explicitly requested.
- Do not run `git add`, `commit`, `push`, `merge`, `rebase`, or `tag` unless the
  user explicitly authorizes that exact action.
- Preserve unrelated user changes in a dirty worktree.
- Do not modify the stable ASR Worker, GPU-to-CPU fallback, or v1.4.5 portable
  release loop without a reproducible blocking defect and focused tests.

## Security and privacy

- Never commit or expose API keys, cookies, authorization headers, credentials,
  prompt bodies, internal model routing, user media, generated knowledge
  packages, local models, machine-specific absolute paths, or developer-machine
  details.
- Formal cloud credentials must live only in server-side secret storage. Desktop
  and browser clients may hold user-provided local credentials or short-lived,
  least-privilege session tokens, never a shared production cloud key.
- Product-mode API responses must redact implementation details in the backend;
  frontend-only hiding is insufficient.
- Internal source ZIPs are not public release artifacts.

## Documentation

- `docs/PROJECT_STATE.md` is the canonical current-state document.
- `docs/MASTER_ROADMAP.md` is the canonical forward roadmap.
- `docs/REPO_BOUNDARY.md` defines private/public ownership.
- `docs/API_CONTRACTS.md` defines integration contracts; public contracts must
  not depend on private implementation names or internals.
- `docs/TEST_BASELINE.md` records reproducible validation.
- `docs/DECISIONS.md` records durable decisions.
- `docs/NEXT_TASK.md` contains only the single approved next work unit.
- Store conversation summaries in `docs/codex-log.md`; never place full chat
  transcripts in the repository.
- Keep logs and decision notes out of business source directories such as
  `src/`.

## Validation and handoff

- After changes, run the tests proportionate to the risk. For a release baseline,
  run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m src.main --help
.\.venv\Scripts\python.exe -m src.web --help
node --check src/web_ui/app.js
git diff --check
```

- Report modified files, commands, pass/fail results, remaining risks, final
  `git diff --stat`, and final `git status --short --branch`.
- Stop after the requested scope. Do not begin the next roadmap version
  implicitly.
