# Viewledge Project State

Last verified: 2026-08-17

This is the canonical current-state document. Git state, current code, and
reproducible commands take precedence over older notes.

## Repository baseline

- Repository role: private Viewledge core.
- Current release branch: `release/v1.5.0`.
- Source baseline: `3854828 chore: freeze v1.5.0-beta.1 private baseline`.
- Package version: `1.5.0`, defined by `src/__init__.py` and enforced by the
  release builder.
- No release tag was created during this audit.
- v1.4.6 identity/recovery and v1.4.7 repository-boundary work is committed and
  consolidated into this v1.5.0 baseline; neither remains a separate release
  target.
- The current release-freeze edits are not committed, pushed, merged, rebased,
  or tagged.

## Historical v1.4.5 implemented baseline

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

## v1.4.6 identity, duplicate, and claim baseline absorbed into v1.5.0

The committed compatibility baseline provides:

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

## v1.4.7 boundary milestone absorbed into v1.5.0

The committed boundary tranche provides:

- `public_boundary/allowlist.json` with explicit source-to-destination entries;
- an implementation-independent Bridge API 1.0 Schema fixture and public note;
- `scripts/public_boundary.py build`, which stages only allowlisted files into a
  clean directory outside this repository and emits deterministic hashes;
- `scripts/public_boundary.py scan`, which blocks sensitive values, private path
  components, and private implementation references.
- `scripts/public_boundary.py verify`, which checks the generated file set and
  SHA-256 hashes before any handoff.
- The desktop navigation now reserves a real 264px sidebar column or a 56px
  collapsed rail so workbench content cannot render underneath it; narrow
  screens retain the drawer interaction and accessibility state.
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

## v1.5.0 Browser Intake and knowledge inbox — first slice

The first private-core slice is now implemented on top of the v1.4.7 boundary
milestone:

- local Bridge endpoints `POST /v1/intakes`, `GET /v1/intakes/{intake_id}`,
  and `GET /v1/inbox`;
- required `Idempotency-Key` handling with replay-safe responses;
- URL normalization and source-kind validation for video/page captures;
- stable opaque `knowledge_id` and request fingerprint generation through the
  v1.4.6 identity contract;
- active-exact and same-source revision duplicate states in the inbox;
- durable local intake registry under private local state, with captured text
  excluded from public response payloads;
- explicit `start`, `retry`, and pre-handoff `cancel` actions;
- queued video Intake handoff to the existing local task API, with
  `processing`/`ready`/`failed` reconciliation and sanitized
  `needs_attention` recovery;
- Bilibili series/P-part metadata inspection without media download;
- a private local knowledge-set registry that preserves ordered items,
  partitions, source URLs, and per-item state;
- a Web decision panel that asks whether to analyze the current video or first
  create the set, followed by on-demand analysis for individual items;
- collapsible knowledge-set cards that preserve the separate knowledge-record
  list;
- completed set items display linked package duration and analysis date in a
  compact metadata column;
- the set and library use the same stable `knowledge_id`, so a completed set
  item opens the corresponding knowledge record rather than a duplicate shell;
- Bridge responses use the independent public `1.0` envelope and sanitized
  product data;
- the private Web client now validates and unwraps `/v1/` envelopes in one
  shared `api()` boundary, so Inbox, clip, highlight, and Intake actions all
  consume the same payload shape as the public Side Panel client.
- a private loopback `GET /api/search` endpoint and compact global-search dialog
  covering records, collections, and projects; fast search is local metadata
  and summary based, while subtitle/page-body matching is an explicit deep mode
  with bounded sanitized snippets.

The Bilibili set slice is intentionally local and metadata-first: creating a
set does not start analysis or ASR. A user can later choose one item from the
sidebar and hand only that item to the existing task pipeline. Playlist/P-part
inspection is capped at 200 items and keeps the extractor behind the private
core boundary.

### v1.5.0 release-candidate acceptance evidence

- The real Bilibili series URL used for acceptance returns `bilibili_series`,
  97 ordered items, and `p=1`/`p=2` source URLs without media download.
- The live local registry contains the 97-item set; set items 1 and 2 are
  `ready` and resolve to completed library records with the same stable
  `knowledge_id`.
- Automated Web tests verify that replaying an item action with the same
  `Idempotency-Key` starts no second task, a different key is rejected while
  processing, and a failed item can be retried with a new key.
- The 2026-08-14 live check used the historical `1.4.5` package identity. The
  release branch now reports `1.5.0`; a fresh-service runtime check and the
  duration/date plus collapse/expand browser acceptance belong to the v1.5.0
  freeze gate. Real Chrome unpacked-extension acceptance belongs to v1.5.1.
- Browser acceptance also found and fixed the folder-path validation branch
  where declining immediate knowledge-set creation left the inline status stuck
  on "checking". It now reports successful validation while keeping the
  folder-set decision explicit.
- The formal Windows launcher keeps mutable state and knowledge output outside
  the checkout. If those external directories are not writable for the current
  account, startup correctly stops with a writable-directory error; select a
  user-writable `VIEWLEDGE_STATE_ROOT` and `VIEWLEDGE_OUTPUT_ROOT` before
  launching. Read-only package directories inside a source checkout are not
  silently used as a write target.

Page captures now use the private local page-ingestion adapter after the user
explicitly starts them from the Inbox. The adapter stores the bounded capture
locally, can skip Provider upload when consent is disabled, and never fetches
the supplied URL. The public client never receives local job IDs, subprocess
logs, Provider routes, or local paths.

## Local-only development launcher

`start_dev.bat` exists locally and is excluded by the repository-local
`.git/info/exclude` rule `/start_dev.bat`. It is not tracked, is not reported as
an untracked file, and is absent from the audited release ZIP.

## Release artifacts

The ignored `release/` directory currently contains the historical v1.4.5
artifacts and the rebuilt v1.5.0 base artifact:

- `Viewledge-v1.5.0-windows.zip` and its SHA-256 sidecar;
- `Viewledge-v1.4.5-windows.zip` and its SHA-256 sidecar;
- `Viewledge-local-asr-small-model.zip` and its SHA-256 sidecar;
- the older `Viewledge-v1.4.3-source.zip`.

The v1.5.0 base ZIP:

- pass their recorded SHA-256 checks;
- pass `scripts/verify_release.py`;
- contain the required runtime files;
- contain no `.env`, `.git`, or `start_dev.bat` entries;
- execute the bundled FFmpeg and FFprobe version checks successfully.

The v1.5.0 base ZIP was rebuilt from `release/v1.5.0` after the version and
documentation alignment. Its SHA-256 is
`6b3cac06edb409154da54d2baa02080957434c2e17e9805a03f74427a5b9568`.
Tests are not shipped in the base ZIP. The existing v1.4.5 ZIP remains a
historical internal artifact and is not a v1.5.0 release.

## Test baseline

The current project interpreter is Python 3.12.13. The latest complete
release-freeze run reports:

```text
Ran 483 tests
OK
```

The current discovery run finds 483 test cases. It used temporary writable
`VIEWLEDGE_STATE_ROOT`, `VIEWLEDGE_CACHE_ROOT`, and `VIEWLEDGE_OUTPUT_ROOT`
directories and completed successfully in 13.986 seconds. This is the
authoritative v1.5.0 release-freeze baseline.

See `docs/TEST_BASELINE.md` for the current command matrix.

## Documentation truth

- `README.md` identifies v1.5.0 as the private internal portable beta and is
  aligned with `src/__init__.py`, the CLI/Web runtime, and the release builder.
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

v1.5.0 is technically ready for the final internal freeze gate: the source
baseline is committed, the visible version is aligned, 483 tests pass, the
local Bridge/page smoke passes, the allowlisted public staging verifies, and
the rebuilt base ZIP passes hash, file, secret, and FFmpeg checks.

The remaining freeze conditions are user-facing manual checks: clean-Windows
launch, new-user API configuration, real Bilibili series and local-folder
acceptance, page Intake/search/restart behavior, and confirmation that the
internal ZIP is distributed only to trusted testers. No public release or tag
is implied by these checks.

## Scope boundary

The current v1.5.0 working slice also includes local folder collections: a
validated local directory can be registered as a private three-level tree,
child folder sets can be reordered, and video items can be analyzed on demand
or in batch. Absolute paths are stored only in private local state and are not
returned by the public folder-set envelope. Validation and registration accept
the quoted Windows paths commonly copied from Explorer, while empty paths are
rejected before the current working directory can be inspected accidentally.
Folder-set video rows reuse the knowledge-set duration and analysis-date column
when a completed package is available. Batch analysis now walks the selected
folder subtree, and task-start failures are recorded as retryable item failures
instead of leaving a stale processing state.
The same validated configuration persistence now applies to Bilibili knowledge
sets: collection creation stores analysis profile, processing profile, and
subtitle grouping, and item analysis reuses those values. Older set files use
tutorial/complete/30-second compatibility defaults.

The loopback Bridge also exposes a sanitized read-only transcript contract at
`GET /v1/knowledge/{knowledge_id}/transcript`. It is intended as the server
foundation for the future public Side Panel; no browser extension repository or
private-core code has been published.

The v1.5.1 target is therefore “类 vcaption” in product behavior: a browser
Side Panel will read the current page's matched subtitle groups without
exposing private package paths. The current private Web UI already provides the
same reading surface and user actions, and the Bridge contract is smoke-tested;
the independent `viewledge-clipper` browser extension itself has not yet been
created. A boundary-only MV3 Side Panel prototype now exists under
`public_boundary/client/`; it is allowlisted but not published. Cross-origin
Bridge use requires the local operator to set the exact extension origin in
`VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN`, so the default local server remains
same-origin and closed to arbitrary extensions.

The candidate Side Panel labels matched video records as subtitle groups and
matched web-page records as ordered page-text blocks, including source-aware
search, empty-state, and copy wording. Web-page blocks retain null media
timestamps and are never presented as `00:00` subtitles.

The client-side Bridge base is also constrained to loopback hosts (`localhost`,
`127.0.0.1`, or `[::1]`); a remote base cannot receive transcript, clip, or
Intake payloads from the prototype.

For read-only or portable project directories, the local Web service accepts
`VIEWLEDGE_STATE_ROOT` as an operator-selected writable state directory. This
keeps jobs, Intake, folder-set, knowledge-set, and clip state out of the core
checkout. The official `start_web.bat` and `start_web.ps1` launchers default it
to `%LOCALAPPDATA%\Viewledge\state`; direct module launches retain `.local`
when the variable is unset.

The prototype also exposes explicit “收件”: it creates a page Intake with
selected text, upload consent disabled, and no automatic processing handoff.

The Bridge now also exposes `GET /v1/knowledge/resolve?source_url=...` for a
Side Panel that knows the current page URL but not the local opaque ID. It only
normalizes and compares URLs against the local package index; it never fetches
the supplied URL or returns local paths.

The first v1.5.1 clipping foundation is now present locally: idempotent
`POST /v1/clips` plus read/list routes persist explicit user selections with
source URL and optional media range. The private Web transcript reader now
renders a user-triggered clip action for each subtitle/page group and sends
bounded context plus media range through that Bridge. This is a Bridge
contract and local validation slice, not the public browser extension itself.
The action now prefers user-selected text inside a transcript group and falls
back to the full group when no selection is present. The transcript reader
also accepts an optional bounded note and renders it in the saved-clips list.
The selection is also remembered in front-end memory until the action is
submitted, preventing a browser click from silently widening it to the whole
subtitle group.
Clip provenance now reuses the v1.4.6 source-URL normalization rules, so
tracking parameters and fragments do not create divergent saved sources.
The transcript reader now exposes a separate “高亮” action backed by the same
bounded Clip Bridge record with `kind=highlight`; saved highlights are visibly
distinguished without introducing another persistence path.
Each transcript/page group now also offers an explicit “收件” action. It sends
the selected text (or the full group when no selection is present) to the local
page Intake contract with upload consent disabled, refreshes the knowledge
inbox, and leaves starting analysis to the user.
The boundary Side Panel now hides this page-Intake action for video subtitle
groups, preventing a video subtitle selection from being mislabeled as a web
page capture.

The v1.4.6 identity, duplicate, API-config, package-claim, explicit Web
duplicate-action API/UI, task-level transcript grouping, and initial
stage-aware repair units are committed in the v1.5.0 baseline. The final audit has now
verified CLI recovery against an incomplete package, Web active-duplicate
decision handling, and the 15/30/60/120-second grouping selector. No browser
extension repository, public repository, history migration, cloud account
system, or paid feature was created.

Latest v1.5.1 boundary evidence: the allowlisted `public_boundary/client/`
directory passes clean staging and verification. Its MV3 Manifest points to
existing service-worker and Side Panel files. The Side Panel exposes copy,
clip, highlight, and inbox actions, remembers the latest in-group selection,
and uses independent idempotency keys for clip and highlight. The remaining
gate is manual Chrome unpacked-extension smoke with an exact
`VIEWLEDGE_BRIDGE_EXTENSION_ORIGIN`.
The Side Panel also exposes an optional 500-character bounded note for clip and
highlight actions.
Video subtitle groups now expose an explicit seek action. It updates only the
current tab URL with the selected start time; it does not crawl or upload page
content.
It now includes an explicit focus-reading mode: the user can enlarge subtitle
cards and hide Bridge configuration while reading. Subtitle text remains inside
the extension Side Panel; it is not injected into the host webpage DOM.
The focus-reading preference is persisted only as a boolean in extension-local
storage; subtitle text and page contents are not persisted by the client.
Its clip/highlight idempotency keys now survive search re-renders within the
same loaded knowledge record and are cleared when a different record is loaded.
Unmatched pages and Bridge failures now render a sanitized public error rather
than raw backend messages, with an explicit Retry action that re-runs the local
lookup without exposing cookies, filesystem paths, provider details, or the
current page contents.
The private transcript reader and boundary Side Panel now use content-aware
session idempotency: a lost response can be retried with the same key, while a
changed selection or bounded note receives a new key; switching records clears
the action memory.
The cache root now follows `VIEWLEDGE_STATE_ROOT` (or explicit
`VIEWLEDGE_CACHE_ROOT`) so portable/read-only checkouts do not attempt to write
mutable cache artifacts into the private project directory.
The candidate MV3 Side Panel Manifest now declares the same three loopback
Bridge hosts accepted by the client (`localhost`, `127.0.0.1`, and `[::1]`),
including the IPv6 host permission needed by Chrome.
It also declares the narrow Chrome `tabs` permission so an already-open Side
Panel can follow active-tab changes; the client only reads URL/title metadata.
The manifest declares Chrome 114 as the minimum supported browser version so
older browsers fail clearly instead of appearing to load a nonfunctional panel.
The Side Panel service worker also reapplies the icon-to-panel behavior on
browser startup, not only on extension installation. Automated validation covers
this lifecycle registration; real Chrome unpacked-extension interaction remains
the final manual gate.
After video timestamp seeking, the Side Panel keeps the live URL for provenance
but resolves the knowledge record against a URL with only playback-position
parameters removed, so repeated seeks do not break subtitle lookup.
The page-Intake action also checks the matched source kind at call time, not only
at render time, preventing a video subtitle from becoming a page capture after a
future UI change.
The full discovery baseline is now green at 483 tests when the launcher/runtime
uses external writable state, cache, and output roots; the previous
repository-cache stall is no longer a product blocker.
The repository now also includes `scripts/smoke_v15.py`, which runs the page
Intake-to-knowledge-package and clip Bridge path in a disposable process/state
root without API keys or generated artifacts in the checkout.

The public Bridge client now enforces `credentials: "omit"` after merging
request options, so a future Side Panel caller cannot accidentally opt into
cookies or HTTP authentication by overriding the default request options. The
boundary regression covers this ordering and the Node runtime envelope check
continues to pass.

The candidate client now also rejects active-page URLs containing embedded
username/password credentials and removes URL fragments before local lookup.
When navigation resolves to a different opaque knowledge record, it clears the
previous record's search text and optional clip note while retaining only the
explicit boolean focus-reading preference. A browser DOM smoke fixture executes
the actual `side_panel.js` with disposable mocked Bridge responses and verifies
loading, filtering, focus reading, timestamp seeking, lost-response idempotent
clip retry, cross-record state cleanup, and sanitized unsupported-page recovery.
This strengthens automated acceptance but does not replace the final Chrome
unpacked-extension/CORS-origin smoke.

The disposable v1.5 smoke now also asserts that a page transcript resolves as
`source.kind=web_page`, that groups carry `contentKind=web_page`, and that page
groups expose null media times rather than fabricated subtitle timestamps.
It also creates a minimal platform-subtitle package without media or Provider
calls and verifies the video Side Panel contract retains `source.kind=video`
and real subtitle start/end seconds.
Video transcript groups now also carry the explicit public
`contentKind=video_subtitle` field, matching the Side Panel Schema rather than
requiring the client to infer it solely from `source.kind`.
The public group schema now rejects undeclared fields and requires the
video/page-specific timestamp shape: video subtitles carry numeric seconds;
web-page blocks carry null media times and a one-based position.

The local-path validation endpoint now shares the same quoted-path normalizer
as folder-set creation, including single-quoted Explorer-style paths, so the
validation click and subsequent folder registration cannot disagree about the
source type.

Folder-set registration now persists the validated analysis profile, processing
profile, and subtitle grouping target. The path-validation flow explicitly
initializes tutorial/complete/30-second defaults for a detected folder, and
later child-item or subtree batch analysis reuses the persisted settings rather
than silently reverting to hard-coded defaults. Existing folder-set state files
remain compatible through those defaults.

The same validation click behavior now applies to detected Bilibili
collections: series/P-part inspection initializes tutorial/complete/30-second
settings before the user chooses knowledge-set creation or current-video
analysis.

Knowledge-set and local-folder collection views now poll while any item is
processing. Each poll refreshes both the collection registry and the library,
so a completed item appears as an openable knowledge record without a manual
page refresh; polling stops when no processing items remain.

The public Bridge request layer now filters caller-supplied headers to the
contract allowlist (`Accept`, `Content-Type`, and `Idempotency-Key`) before
fetching. Authorization, Cookie, and arbitrary custom headers cannot cross the
public client boundary; the Node runtime test covers both read and write
requests.

## 2026-08-16 运行资源治理

新增 `responsive`、`balanced`、`performance` 三档计算资源策略。默认流畅档
通过跨进程运行时锁串行化 GPU、CPU ASR 与 FFmpeg 重计算，限制 CPU ASR
线程数、FFmpeg 线程数，并让 Web 计算子进程使用低于正常优先级。Web 任务
现在先进入 FIFO 队列，任务状态可报告队列原因和实际资源；服务重启会保留
排队任务，并将失去子进程的运行任务标记为中断。既有共享知识包目录不参与
资源锁或迁移写入。

## 2026-08-16 侧边栏资源、产出与项目分区

- 资源库筛选现在只显示不属于视频系列或本地文件夹集合的独立记录。
- 视频系列知识集和本地文件夹集合统一进入产出库索引，点击后在记录栏保留原有成员状态与分析动作。
- 原知识集区域改为可新建、重命名、删除和选择的项目区；记录三点菜单仅提供移入、新建并移入、移出项目。
- 项目关系独立保存在共享输出根的 `projects/registry.json`，不迁移或改写既有知识包、知识集及文件夹集合文件。
- 桌面折叠状态保留图标栏与点击浮窗，移动端继续使用抽屉式侧边栏。

## 2026-08-16 资源总览与桌面导航占位

- 资源库成为单一位置入口，点击进入 `#/resources`；搜索、来源、处理中、已完成和收件箱筛选集中在正式主面板。
- 独立记录在桌面使用管理表格、在窄屏使用卡片，三点菜单继续仅处理项目编组；点击记录保留 `#/knowledge/{id}` 深链接。
- 桌面展开侧栏与折叠图标栏分别永久占用 264px 和 56px，浮窗仍临时覆盖且不推动工作面板；移动端继续使用抽屉。
- 总览复用现有只读列表、收件箱和项目接口，没有新增后端存储，也没有迁移或重写共享知识包及集合注册表。
