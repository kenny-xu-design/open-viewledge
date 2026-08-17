# Test Baseline

Last verified: 2026-08-17

This baseline applies to the committed private source baseline `3854828` and
the v1.5.0 release-freeze edits on `release/v1.5.0`. It consolidates v1.4.6
identity/recovery, the v1.4.7 public boundary, and the v1.5.0 Intake,
collections, projects, resource overview, global search, page ingestion, and
resource-governance slices.

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

In this checkout, the generated `src/__pycache__` entries are read-only. The
reproducible equivalent for validation is:

```powershell
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\viewledge-pyc"
\.venv\Scripts\python.exe -m compileall -q src
```

Latest verification:

| Check | Result |
|---|---|
| Full unit suite (latest complete run) | PASS, 483 tests |
| Current discovered test cases | PASS, 483 cases discovered |
| Package and release-builder version | `1.5.0` |
| v1.5.0 runtime smoke | PASS, `/api/runtime` reports `1.5.0`; local global search returns the shared collection index |
| v1.5.0 private page/Bridge smoke | PASS, `scripts/smoke_v15.py` |
| Public boundary staging | PASS, allowlist build and verify with fresh-history requirement |
| v1.5.0 Windows base ZIP | PASS, `scripts/verify_release.py`; SHA-256 `6b3cac06edb409154da54d2baa02080957434c2e17e9805a03f74427a5b9568` |
| v1.4.6 affected suite | PASS, 196 tests |
| v1.4.7 boundary suite | PASS, 10 tests |
| v1.5.0 Intake/inbox suite | PASS, 11 tests |
| Bilibili series/knowledge-set suite | PASS, 5 focused tests |
| v1.5.1 Bridge/Web/Side Panel slice | PASS, focused Bridge/client boundary tests plus loopback and browser UI smoke; Side Panel UTF-8 display contract covered |
| Web UI contract suite | PASS, 59 tests |
| Global search endpoint/UI contracts | PASS, 3 focused tests |
| `compileall src` with temporary `PYTHONPYCACHEPREFIX` | PASS |
| `compileall src` with `PYTHONPYCACHEPREFIX=.local/codex_pycache` | Historical PASS |
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

Historical result: PASS, 461 tests in 13.774 seconds, with temporary external state and
cache roots. The cache-root fix prevents repository-permission stalls in
portable/read-only executions.

v1.5.1 runtime smoke on 2026-08-12:

- `GET /v1/knowledge/resolve` matched the current Bilibili part-1 package,
  including the user-style URL without an explicit `p=1` query.
- `GET /v1/knowledge/{knowledge_id}/transcript` returned the sanitized Bridge
  envelope and ordered transcript groups without a local path.
- The local Web UI loaded the “原文细读” tab and rendered subtitle groups with
  copy, clip, highlight, and receive actions. The only browser console error
  was the optional `/favicon.ico` 404; it does not block the transcript view.
- The boundary client accepts only loopback Bridge bases (`localhost`,
  `127.0.0.1`, `[::1]`) and rejects remote hosts, credentials, paths, and query
  parameters before issuing a request. The focused boundary/Web/UI/page/clip
  suite passed 159 tests after this change.
- The official Windows launchers default `VIEWLEDGE_STATE_ROOT` to
  `%LOCALAPPDATA%\Viewledge\state`, allowing a read-only extracted project to
  keep mutable Web state outside the private checkout.
- A subprocess-level test confirms that `VIEWLEDGE_STATE_ROOT` changes the
  Python Web process's actual `LOCAL_STATE_ROOT`, not just launcher text.
- The allowlisted Side Panel staging output was rebuilt and passed
  `scripts/public_boundary.py verify`; the staging manifest contains only the
  reviewed client and schema files.
- Side Panel contract tests cover Manifest file references, UTF-8-safe markup,
  selection memory, separate highlight/clip actions, loopback-only Bridge
  validation, bounded notes, render-stable idempotency keys, and absence of
  private pipeline identifiers.
- The focused Side Panel/Bridge/Web/page/clip/intake regression now passes 168
  tests; unmatched pages and Bridge failures are checked for sanitized public
  messaging and an explicit Retry action.
- The subsequent Web UI + boundary + Bridge regression passes 165 tests and
  covers content-aware idempotency for transcript clip, highlight, and Intake
  actions.
- With `VIEWLEDGE_STATE_ROOT`, `VIEWLEDGE_CACHE_ROOT`, and
  `VIEWLEDGE_OUTPUT_ROOT` pointed at temporary writable directories, the
  complete discovery run passes 461 tests in 13.774 seconds. The cache-root fix
  prevents repository-permission stalls in portable/read-only executions.
- The Side Panel contract remains allowlist-only and is covered by static
  behavior assertions for Retry, sanitized errors, loopback-only Bridge bases,
  selection memory, content-aware idempotency, and no private identifiers.
- Side Panel action failures now retain action-specific public fallbacks, so a
  clip/highlight/inbox error cannot be mislabeled as subtitle-read failure.
- Clipboard permission failures now use the same sanitized public status path
  instead of failing silently from the subtitle card.
- Local Bridge validation errors now remain distinguishable from transcript
  read failures while exposing only a fixed public message.
- The boundary Bridge client now validates the public response envelope version
  and mutual exclusivity of `data`/`error` before consuming any endpoint data.
- `scripts/test_bridge_client.mjs` executes the exported envelope validator in a
  zero-dependency Node runtime, covering valid data and malformed/version/error
  response cases rather than relying only on static source assertions.
- Boundary documentation and behavior now agree that web-page groups alone
  expose Inbox capture; video groups expose timestamp seeking instead.
- The Side Panel service worker now registers `openPanelOnActionClick` on both
  extension install and browser profile startup, so the icon behavior does not
  depend on a one-time install event. The boundary test asserts both lifecycle
  listeners and the worker passes Node syntax checking.
- The MV3 Manifest now declares all three supported loopback Bridge hosts,
  including `http://[::1]:5188/*`; the boundary regression asserts that the
  client allowlist and browser host permissions stay aligned.
- The MV3 Manifest also declares the narrow `tabs` permission required for
  the Side Panel to follow active-tab changes after it is already open; the
  client uses it only for tab URL/title metadata and never for page body,
  cookies, or scripts.
- The candidate Side Panel declares `minimum_chrome_version: 114`, matching
  the Side Panel API baseline and making unsupported-browser failure explicit.
- Page transcript Bridge groups now expose `contentKind: "web_page"`, a
  one-based position, and null media times; the contract regression rejects
  fabricated page timestamps while preserving video seconds.
- Video transcript Bridge groups now expose the explicit `contentKind:
  "video_subtitle"` field, and the disposable smoke verifies it alongside
  real subtitle start/end seconds.
- The disposable v1.5 smoke and Web regression now cover both accepted
  extension CORS preflight and rejected arbitrary-extension preflight, not
  only the response header on a completed request.
- `compileall`, CLI/Web help, both JavaScript syntax checks, and `git diff
  --check` pass when `PYTHONPYCACHEPREFIX` points to a temporary directory;
  the default in-checkout `compileall src` remains unsuitable for the existing
  read-only repository `__pycache__` artifacts.
- Timestamp seeking rechecks the active tab URL before navigation, preventing
  a stale Side Panel record from changing a newly selected page.
- Side Panel reloads resolve the active page through the same playback-position
  normalization after a seek, preventing `t`/`start` URL changes from losing the
  matched knowledge record.
- The Side Panel Intake handler now enforces `source.kind === "web_page"` in
  addition to hiding the action for video groups; the boundary regression checks
  both defenses.
- The active-page check ignores only playback-position parameters, so repeated
  seeks on the same video remain usable after the first `t` update.
- Side Panel tab activation and active-tab URL changes now trigger a fresh
  sanitized local lookup rather than leaving stale subtitle groups visible.
- Concurrent Side Panel lookups are sequence-guarded, so a slower response for
  an older tab cannot overwrite the newest page's subtitle groups.
- Tab and URL events are debounced briefly to avoid duplicate Bridge lookups
  during a browser navigation burst.
- The Side Panel refresh button is disabled only during an active lookup, then
  becomes available again for explicit retry or refresh.
- Closing or suspending the Side Panel clears its pending reload timer and
  invalidates in-flight results.
- URL-change events from background tabs are ignored; only the active tab can
  trigger a Side Panel lookup.
- Web UI regression coverage asserts that only child folder-set cards are
  draggable, video rows remain fixed, and reordering is limited to siblings.
- The Side Panel also exposes a user-triggered focus-reading mode; its larger
  subtitle cards remain inside the extension surface and do not inject text
  into the host webpage.
- The Web task source validator now leaves an inline status after inspection:
  ordinary paths auto-select tutorial/complete/30-second settings, collections
  remain explicit knowledge-set decisions, and validation failures stay visible
  until the source type changes.
- The knowledge inbox now keeps load failures actionable with an inline Retry
  button; retry reuses the same inbox refresh contract and never exposes
  captured page text.
- On 2026-08-14, the private Web `/v1/` client was unified behind one Bridge
  envelope validator/unwrapper. The focused Web/Inbox/clip regression passed
  161 tests, the full discovery suite passed 461 tests, and both v1.5 runtime
  smoke and credential-free Bridge client checks passed.
- On 2026-08-14, browser acceptance of the source validator reproduced the
  local-folder branch that remained in a "checking" state after the user
  declined immediate set creation. The UI now reports successful validation;
  the focused regression and subsequent 461-test discovery run passed.
- The same runtime audit confirmed that the launcher refuses a read-only
  output root instead of mutating an existing source checkout. A disposable
  writable state/output/cache root was used for the live Web smoke; no user
  package or credential was copied.
- `python scripts/smoke_v15.py` now provides a disposable-process smoke for
  page Intake create/replay/start, local page package readiness, source resolve,
  transcript read, clip replay, exact CORS opt-in, and arbitrary-origin denial.
- Latest disposable smoke result: PASS; it created a temporary page knowledge
  record and one idempotent clip, verified the page source/content-kind and
  null media-time contract, plus a minimal video subtitle package with real
  media start/end values (`video_subtitle_kind=video`), then removed the
  temporary process/state.
- The public Bridge client enforces credential-free fetches after options are
  merged; the focused boundary test, Node syntax check, and private runtime
  request test cover this privacy invariant, URL normalization, and loopback
  rejection.
- The actual allowlisted `side_panel.js` now also runs inside a disposable local
  browser DOM smoke (`scripts/smoke_side_panel_dom.html`). The 2026-08-14 run
  passed loading, search, focus reading, timestamp seek, a simulated lost
  response followed by an idempotent clip replay with the same key, cross-record
  note/search cleanup, fragment removal, and sanitized unsupported-page Retry.
- The Bridge client Node smoke rejects active-page URLs with embedded
  credentials and confirms fragments are removed before local lookup.
- Bridge runtime coverage also asserts that caller headers are reduced to the
  public `Accept`/`Content-Type`/`Idempotency-Key` allowlist.

The current checkout contains read-only generated files under `src/__pycache__`;
therefore the authoritative compile check uses a temporary
`PYTHONPYCACHEPREFIX` and does not mutate the repository. This is an execution
environment constraint, not a Python syntax failure.

## Release artifact verification

Historical ZIPs belong to the v1.4.5 beta line. The v1.5.0 internal ZIP must be
rebuilt from `release/v1.5.0`, pass `scripts/verify_release.py`, and remain a
private trusted-tester artifact; verification does not authorize publication.

## Failure handling

- Do not lower test counts by excluding failures.
- Do not rewrite historical packages to make inspection pass.
- Treat flaky, timeout, environment, and external-service failures separately.
- A release verifier pass does not authorize public distribution of a
  source-containing ZIP.

## 2026-08-16 资源治理改造验证

- `python -m unittest discover`: 469 tests passed。
- `python -m compileall -q src`、`src.main --help`、`src.web --help`、`node --check src/web_ui/app.js`：通过。
- 资源治理专项覆盖 CPU 线程档位、跨进程锁路径/释放、Web FIFO 调度和既有 ASR/GPU 回退链路。

## 2026-08-16 资源、产出与项目分区验证

- `python -m unittest discover`: 478 tests passed。
- 项目专项覆盖幂等创建、重命名、删除、单项目归属、跨项目移动、失效引用过滤及知识包不变性。
- Web/API 专项覆盖集合归属标记、项目 CRUD、成员移动，以及删除项目不删除知识包。
- 浏览器在 1440px 桌面视口验证资源集合排除、产出集合成员视图、记录三点菜单、折叠图标栏和浮窗；在 800px 视口验证移动端仍使用抽屉且图标栏不可见。
- 本机 30 次项目列表请求平均 15.8ms、P95 17.9ms；轻量 manifest ID 索引替代重复完整知识包扫描后，优化前平均约 205.6ms。

## 2026-08-16 资源总览与桌面占位验证

- `python -m unittest discover`: 479 tests passed；`tests.test_web_ui`: 58 tests passed。
- `node --check src/web_ui/app.js` 与相关文件 `git diff --check`：通过。
- 浏览器验证 `#/resources`、知识详情往返入口、状态/来源/搜索组合、收件箱主面板及三点菜单独立点击。
- 1280px 桌面实测展开工作区左边界为 264px、折叠为 56px；330px 浮窗打开前后工作区宽度均为 1224px。
- 390px 窄屏实测继续使用抽屉，资源总览使用卡片布局并隐藏知识详情模块。
