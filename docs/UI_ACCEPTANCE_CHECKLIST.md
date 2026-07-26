# Cupertino UI Acceptance Checklist

Status: v1.3.1 implementation gate

Last updated: 2026-07-24

This checklist converts the design and motion documents into verifiable release criteria. Work Unit 4 implementation and the focused v1.3.1 acceptance fixes have been completed on `feat/v1.3.1-cupertino-ui`; unchecked items below still require full manual review or release-gate confirmation.

## Work Unit 1: Audit and Specification

- [x] The repository and branch were verified before work.
- [x] The current HTML, CSS, JavaScript, Web server asset route, and frontend-related tests were read.
- [x] Page structure, components, styling, animation, responsiveness, dark mode, and accessibility were audited.
- [x] Repeated components, scattered values, undefined tokens, cascade conflicts, and mixed visual language were recorded.
- [x] Cupertino layout, hierarchy, material, typography, spacing, theme, and component direction is documented.
- [x] Emil Kowalski motion rules are incorporated into the normative motion document.
- [x] No business page, CLI, Worker, task contract, provider, export, or knowledge-package code was changed.
- [x] No frontend framework or dependency was added.

## Scope Protection for Later UI Work

- [x] API paths, request bodies, response fields, and task lifecycle meanings remain unchanged unless separately approved.
- [x] Existing knowledge-package rendering and persistence behavior remains intact.
- [x] Existing element IDs required by JavaScript/tests are preserved or migrated with tests in the same work unit.
- [x] API Keys and private paths remain absent from frontend storage and rendered payloads.
- [x] A UI refactor does not silently broaden v1.3.1 into v1.4 queue or v1.5 account/provider work.

## Architecture

- [x] One authoritative AppShell layout replaces the two competing CSS layout generations.
- [x] Wide desktop provides a usable Sidebar, primary content region, and Inspector without compressing reading surfaces.
- [x] Medium layouts disclose Sidebar and Inspector independently.
- [x] Compact layouts show one clear primary pane and use an accessible navigation control.
- [x] Split views restore saved widths safely and provide a reset action.
- [x] Source order remains logical when visual module order changes.

## Visual Tokens

- [ ] Color, typography, spacing, radius, separator, shadow, material, and motion values use semantic tokens.
- [ ] `--surface` and `--text-muted` are removed or replaced with defined semantic tokens.
- [ ] New components do not introduce unexplained literal colors or one-off radii.
- [ ] Reading content uses a solid surface and an appropriate Chinese/Latin line length.
- [ ] Capsule shapes are limited to tokens, filters, and compact statuses.
- [ ] Accent color does not overwhelm neutral information hierarchy.

## Cupertino Material and Hierarchy

- [ ] The layout reads as a macOS utility application rather than a generic dashboard.
- [ ] Settings use grouped sections and clear label/value rows inspired by iOS Settings.
- [ ] Sidebar, Toolbar, Inspector, Popover, and Sheet may use restrained material effects.
- [ ] Summary, transcript, chat text, and notes remain on clear solid surfaces.
- [ ] Every blurred surface has an opaque fallback.
- [ ] Blur is not stacked across adjacent layers and is not used as decoration.
- [ ] Material, default shadcn, Material Design, and unrelated dashboard conventions are not mixed unintentionally.

## Component Consolidation

- [x] `IconButton` covers sizes, accessible labels, pressed, disabled, hover, and focus states.
- [ ] Primary, secondary, destructive, and borderless Buttons share one state model.
- [ ] Tabs and segmented controls share keyboard and selection behavior.
- [ ] Sidebar rows and list rows share selection, status, and destructive-selection behavior.
- [ ] Settings rows, fields, selects, toggles, help text, and errors share one form contract.
- [ ] Loading, empty, warning, error, and retry states are reusable components.
- [ ] Dialog, Sheet, Popover, and Toast have distinct roles and consistent chrome.
- [ ] Provider, processing, task, and note-save status use one semantic status vocabulary.

## Dark Mode and Contrast

- [ ] All semantic colors have reviewed light and dark values.
- [ ] Native controls render correctly after enabling `color-scheme: light dark`.
- [ ] Light/dark mode covers dialogs, overlays, media controls, code/log blocks, disabled states, and focus rings.
- [ ] Normal text and interactive controls meet WCAG 2.2 AA contrast.
- [ ] Status meaning is never conveyed by color alone.
- [ ] Forced-colors/high-contrast mode retains focus, selection, error, warning, and disabled meaning.

## Motion

- [ ] No `transition: all` exists.
- [ ] No animation begins or ends at `scale(0)`.
- [ ] Ordinary UI animation remains below `300ms`.
- [ ] Entry motion uses ease-out.
- [ ] Transform and opacity are preferred over layout properties.
- [ ] Keyboard and high-frequency interactions add no animation.
- [ ] Motion can be interrupted without queued or stale visual states.
- [ ] Popovers animate from the trigger direction with a matching transform origin.
- [ ] CSS and JavaScript both support `prefers-reduced-motion`.
- [ ] Transcript following and keyboard media seeking do not smooth-scroll repeatedly.

## Accessibility

- [ ] Every control has an accessible name and explicit button type where relevant.
- [ ] Tab sets implement `tablist`, `tab`, `tabpanel`, `aria-controls`, roving `tabindex`, and Arrow-key navigation.
- [x] Sidebar and Inspector triggers expose `aria-controls` and `aria-expanded`.
- [x] Sheet/drawer focus enters predictably, is contained when modal, and returns to its trigger.
- [ ] Dialogs have programmatic names and preserve native Escape/focus behavior.
- [x] Split-view dividers support keyboard resizing and expose orientation, current value, minimum, and maximum.
- [ ] Dynamic task, save, error, and provider states are announced without excessive repetition.
- [ ] Focus indicators are visible in light, dark, and high-contrast modes.
- [ ] Touch targets are at least `44×44px` in touch layouts; compact desktop controls retain adequate separation.
- [ ] Disabled feature explanations are available without relying only on `title`.
- [ ] Zoom to 200% and browser text enlargement do not hide required actions or content.

## Responsive Visual Matrix

Manually review at minimum:

- [ ] `1440×900` light, dark, and reduced motion.
- [ ] `1280×800` light and dark.
- [ ] `1024×768` with Sidebar and Inspector disclosures.
- [ ] `768×1024` touch/tablet layout.
- [ ] `390×844` compact portrait layout.
- [ ] Long Chinese titles, long model names, empty states, errors, active processing, and dense transcript content.
- [ ] Local video, local audio, YouTube embed, Bilibili embed, and external-link fallback.

For every viewport confirm: no unintended horizontal scrolling, no clipped focus ring, no overlapping fixed layer, no inaccessible action, and no unreadable translucent content.

## Automated Verification

- [x] Existing Web UI contract tests pass.
- [x] Existing Web API tests pass.
- [ ] Full unit suite passes.
- [x] `node --check src/web_ui/app.js` passes.
- [x] `git diff --check` passes.
- [ ] Tests cover theme token presence, reduced-motion integration, forbidden motion patterns, and accessible tab contracts.
- [ ] Browser tests cover Sidebar/Sheet focus, keyboard tabs, dialog close/focus return, keyboard split resizing, and compact navigation.
- [ ] Visual regression snapshots cover the viewport/theme matrix after the visual implementation stabilizes.

Recommended commands:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_ui tests.test_web
.\.venv\Scripts\python.exe -m unittest discover
node --check src/web_ui/app.js
git diff --check
```

## Release Gate

- [ ] Manual UI review is approved by the user.
- [ ] No critical or high-severity accessibility issue remains.
- [ ] No regression exists in task creation, media playback, summary/transcript reading, chat, note persistence, export, or deletion.
- [ ] Documentation describes implemented behavior rather than planned behavior.
- [ ] Release notes identify the UI scope and any intentionally deferred items.

This checklist does not authorize commit, push, merge, tag, or Release actions.
