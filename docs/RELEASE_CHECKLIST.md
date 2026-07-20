# Release Checklist

Run this checklist for every version.

## Automated

- [ ] Version metadata and CHANGELOG agree.
- [ ] README and CURRENT_STATE describe the implemented code.
- [ ] Full unit test suite passes.
- [ ] `python -m compileall src` passes.
- [ ] Every public CLI command exposes `--json`.
- [ ] Long commands expose valid JSONL events with clean stdout.
- [ ] Legacy CLI compatibility tests pass.
- [ ] `doctor --json` detects expected missing dependencies without exposing secrets.
- [ ] `node --check src/web_ui/app.js` passes.

## v1.3 acceptance

- [ ] A real local video completes through `analyze --jsonl`.
- [ ] The resulting package passes `inspect --json`.
- [ ] A failed task can be restored through `resume`.
- [ ] Agent Skill uses only public CLI commands.
- [ ] stdout and stderr separation is manually verified.

## Release actions

- [ ] Human acceptance completed.
- [ ] Feature branch merged to `main`.
- [ ] `main` pushed and clean.
- [ ] Formal annotated tag created and pushed.
- [ ] No later version begins before all preceding gates pass.
