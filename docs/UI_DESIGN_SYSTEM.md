# Cupertino UI Design System

Status: v1.3.1 work unit 1 design baseline

Last audited: 2026-07-21

This document defines the visual and structural direction for the local Web UI. It is a design contract, not an implementation claim. The v1.3.1 first work unit changes documentation only and does not alter CLI, Worker, task, provider, or knowledge-package behavior.

## Product Character

The target is a calm Cupertino-inspired knowledge tool:

- a macOS-style utility workspace for long desktop sessions;
- iOS Settings-style grouping and information hierarchy for configuration;
- restrained translucency used to clarify layering, never as decoration;
- solid, high-contrast surfaces for summaries, transcripts, notes, and other reading areas;
- light material effects limited to Sidebar, Toolbar, Inspector, Popover, and Sheet layers;
- native-feeling density, direct manipulation, predictable keyboard behavior, and strong content focus.

“Cupertino-inspired” describes hierarchy, material discipline, typography, spacing, and interaction. It does not mean copying Apple product chrome, adding decorative blur everywhere, or hiding application-specific state.

## Audited Frontend

The current frontend is framework-free HTML, CSS, and JavaScript:

- `src/web_ui/index.html`: static shell, SVG icon sprite, native dialogs, and all primary landmarks;
- `src/web_ui/app.css`: global tokens, component rules, two generations of workspace layout rules, responsive behavior, and motion;
- `src/web_ui/app.js`: state, rendering, media controllers, dialogs, resizing, persistence, keyboard actions, and API calls;
- `tests/test_web_ui.py`: source-level UI contracts;
- `tests/test_web.py`: static asset and Web API regression coverage.

There is no Material, shadcn, Radix, Tailwind, Bootstrap, or other frontend component dependency. Visual conflicts come from locally accumulated patterns rather than an imported design system.

## Current Page Structure

| Layer | Current structure | Intended role |
| --- | --- | --- |
| App chrome | `workspace-header` | Unified Toolbar with navigation, current workspace title, and contextual actions |
| Navigation | reserved desktop `sidebar`/rail; compact drawer | Context navigation that never sits beneath the desktop workbench |
| Primary workspace | Resource Overview or reorderable `result`, `media`, and `collaboration` modules | Collection management followed by focused knowledge reading |
| Result module | tabs, action toolbar, status, summary/transcript reader, footer | primary solid reading surface |
| Media module | media toolbar, player, source information, highlights | media canvas plus timeline/detail content |
| Collaboration module | chat over notes | right-side Inspector on desktop; a full pane on compact layouts |
| Overlays | task, delete, export, settings, layout, image dialogs, toast | Sheets/dialogs, Popovers where appropriate, and transient status |

## Audit Findings

### What already works

- Primary application regions use semantic `header`, `nav`, `aside`, `main`, and `section` elements.
- Icon-only controls generally have accessible names.
- Native `dialog` provides a sound modal foundation.
- Unavailable features are visibly disabled rather than presented as working.
- Status is not encoded by color alone in task and processing copy.
- UI-only preferences are the only values stored in `localStorage`.
- The layout already supports pointer resizing, module ordering, a compact one-pane mode, and visible focus outlines.
- Existing CSS contains no `transition: all` and no `scale(0)` animation.
- A `prefers-reduced-motion` CSS rule exists, although JavaScript scrolling still needs integration.

### Structural and visual debt

1. `app.css` contains two layout generations. Early rules define a Sidebar/center/result grid and `979px`/`620px` breakpoints; later rules redefine the shell as a header plus reorderable three-column workbench with `1179px`/`680px` breakpoints. The cascade, rather than a single architecture, decides the result.
2. Sidebar behavior is now explicit by breakpoint: desktop reserves 264px or 56px, while compact widths use the fixed overlay drawer. Future layout work must preserve this contract instead of reintroducing overlapping desktop panes.
3. The UI is light-only: both HTML and CSS declare `color-scheme: light`, with no dark semantic tokens or dark media query.
4. Color is only partly tokenized. The stylesheet contains many one-off grays, indigos, status colors, and overlay alphas outside `:root`.
5. `--surface` and `--text-muted` are referenced but not defined. Browsers therefore fall back to inherited or initial values in affected chat states.
6. Radius values repeat as `5px`, `6px`, `7px`, `8px`, and `999px` without semantic roles. Spacing and control heights are similarly distributed as local values.
7. Reading width is inconsistent. The earlier result surface has a `1040px` maximum, while the later workbench removes it; paragraphs retain `95ch`, which is still wide for sustained Chinese reading.
8. Buttons, tabs, pills, status badges, settings rows, dialog sections, and empty states are independently styled. Equivalent states do not share one primitive contract.
9. The visual language mixes an indigo web-dashboard accent, uppercase English dialog kickers, rounded tag pills, default native controls, and neutral utility panels. None is individually wrong, but together they do not form one deliberate Cupertino hierarchy.
10. Static asset aliases use unrelated revision numbers (`app.workspace-6.css`, `app.workspace-15.js`, and a test request for `app.workspace-14.js`). The server intentionally maps any numeric alias to the same file, but the version labels do not communicate one coherent UI revision.

### Accessibility debt

- Elements with `role="tab"` lack `id`, `aria-controls`, associated `tabpanel` semantics, roving `tabindex`, and Arrow-key navigation.
- Split-view separators are focusable but only implement pointer resizing; keyboard resizing and current-value attributes are absent.
- Sidebar trigger buttons do not expose `aria-expanded` or `aria-controls`, and the non-modal drawer does not manage focus containment or return.
- Dynamic loading, note-save, and provider states are not consistently announced through dedicated live regions.
- Some form buttons rely on implicit button type; future component primitives must require explicit `type`.
- Disabled icon controls sometimes depend on `title` for explanation, which is unreliable for touch and some assistive technology.
- Focus indication exists, but it uses a hard-coded color and has not been verified in dark mode or high-contrast environments.
- Keyboard media shortcuts trigger smooth scrolling, and transcript-follow updates can repeatedly animate the viewport.

## Target Information Architecture

### Wide desktop

At `1280px` and above, use a macOS utility layout:

```text
Unified Toolbar
┌──────────── Sidebar ────────────┬──────── Content split view ────────┬──── Inspector ────┐
│ library, search, filters        │ summary / transcript + media       │ chat / notes       │
└─────────────────────────────────┴─────────────────────────────────────┴───────────────────┘
```

- Sidebar target width: `240–280px`, collapsible to an intentional compact mode when needed.
- Inspector target width: `320–400px`, hideable without losing user content.
- Reading content remains on a solid surface with a comfortable line length.
- Split-view dividers are pointer- and keyboard-operable.

### Medium window

From `960px` to `1279px`, keep the primary content visible and allow Sidebar and Inspector to become independently disclosed side layers. Do not compress all three modules below usable reading widths.

### Compact and touch layouts

Below `960px`, show one primary pane at a time. Navigation becomes a Sheet, and Summary/Media/Collaboration selection becomes an accessible segmented control or tab set. Settings use grouped, full-width rows inspired by iOS Settings rather than a dense two-column desktop form.

## Material Policy

| Surface | Material allowed | Rule |
| --- | --- | --- |
| App canvas | No blur | stable neutral background |
| Summary, transcript, notes | No blur | solid surface, maximum text contrast |
| Media player | No blur | black or near-black media canvas |
| Sidebar | Light material | subtle translucency only when content can be seen behind it |
| Unified Toolbar | Light material | thin separator; blur only if content scrolls beneath it |
| Inspector | Optional light material | use only for chrome; text editor and chat messages remain solid |
| Sheet/Popover | Light material | clear elevation and opaque fallback |
| Modal dialog | Mostly solid | translucency belongs to surrounding chrome/backdrop, not form fields |

Implementation must provide an opaque fallback before `backdrop-filter`. Blur should normally remain between `12px` and `20px`; stacking several blurred layers is prohibited.

## Semantic Tokens

Future implementation should replace literal presentation values with semantic tokens. Token names describe purpose, not a particular color.

### Color

```css
--ui-canvas
--ui-surface
--ui-surface-secondary
--ui-material
--ui-material-strong
--ui-text-primary
--ui-text-secondary
--ui-text-tertiary
--ui-separator
--ui-separator-strong
--ui-control-fill
--ui-control-fill-hover
--ui-accent
--ui-accent-hover
--ui-accent-soft
--ui-success
--ui-warning
--ui-danger
--ui-focus-ring
--ui-scrim
```

Light and dark values must be defined as one semantic pair. Components may not introduce new literal colors unless the value represents media content or a documented data visualization category.

### Typography

Use the platform system stack:

```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
```

| Role | Size | Weight | Line height |
| --- | ---: | ---: | ---: |
| Utility caption | 11px | 400–500 | 1.35 |
| Secondary label | 12px | 400–500 | 1.4 |
| Control/body | 13–14px | 400–500 | 1.5 |
| Reading body | 15–16px | 400 | 1.7–1.8 |
| Section heading | 17–20px | 600 | 1.3–1.4 |
| Page title | 24–28px | 650–700 | 1.2 |

Chinese reading content should normally target `38–48` full-width characters per line. Metadata and controls may be denser.

### Spacing, radius, and elevation

- Base spacing unit: `4px`.
- Preferred spacing steps: `4`, `8`, `12`, `16`, `20`, `24`, `32`.
- Compact control radius: `6px`.
- Standard control and row radius: `10px`.
- Grouped section and Sheet radius: `14px`.
- Large modal radius: `18px`.
- Capsule radius is reserved for tokens, filters, and compact statuses—not ordinary buttons.
- Prefer separators and surface contrast over shadows. Use one subtle shadow for floating layers and one stronger shadow for modal elevation.

## Component Vocabulary

The next implementation units should consolidate behavior and style around these primitives:

| Primitive | Responsibility |
| --- | --- |
| `AppShell` | Toolbar, Sidebar, content split view, Inspector, compact navigation |
| `Sidebar` / `SidebarRow` | library navigation, filters, selection, status, deletion mode |
| `UnifiedToolbar` / `ToolbarItem` | current context and high-frequency actions |
| `IconButton` | consistent sizes, labels, hover, pressed, disabled, and focus states |
| `Button` | primary, secondary, destructive, and borderless variants |
| `SegmentedControl` | Summary/Media/Collaboration and other mutually exclusive views |
| `SplitViewDivider` | pointer and keyboard resizing with accessible value reporting |
| `ReadingSurface` | summary, transcript, source material, and readable line length |
| `Inspector` | chat and notes chrome without making content translucent |
| `GroupedSettingsSection` / `SettingsRow` | iOS-style settings hierarchy and value disclosure |
| `Field`, `Select`, `Toggle` | labels, descriptions, errors, and disabled states |
| `StatusBadge` / `InlineStatus` | provider, processing, save, warning, and failure states |
| `EmptyState` / `ErrorState` | reusable blank, loading, unavailable, and retry states |
| `Popover` / `Sheet` / `Dialog` | directional context, responsive side layers, and modal tasks |
| `Toast` | brief confirmation; never the sole channel for a critical error |
| `Progress` / `Spinner` | determinate stages and bounded indeterminate activity |

Component extraction must preserve existing IDs and API behavior until corresponding tests are deliberately migrated.

## Theme and Contrast

- Support `prefers-color-scheme` and leave room for a future explicit `data-theme` override.
- Set `color-scheme: light dark` only after every native control and semantic token has both modes.
- Text, icons, separators, focus rings, and status colors must meet WCAG 2.2 AA contrast for their intended size.
- Dark mode is not a color inversion. Reading surfaces remain solid, media remains neutral black, and material alpha/shadows receive dedicated values.
- High-contrast and forced-colors modes must retain selection, focus, disabled, warning, and error meaning.

## Non-goals for This Work Unit

- No HTML, CSS, or JavaScript refactor.
- No new frontend framework or component library.
- No CLI, Worker, task contract, provider, export, or knowledge-package change.
- No claim that dark mode, material layers, keyboard resizing, or new components are already implemented.

Implementation acceptance is defined in `docs/UI_ACCEPTANCE_CHECKLIST.md`; motion behavior is normative in `docs/UI_MOTION_RULES.md`.
