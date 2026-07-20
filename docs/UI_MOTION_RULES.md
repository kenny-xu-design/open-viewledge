# UI Motion Rules

Status: normative for v1.3.1 Cupertino UI work

Last audited: 2026-07-21

These rules incorporate the interaction principles requested from Emil Kowalski’s motion guidance and adapt them to a local, keyboard-heavy video knowledge tool.

## Core Rules

1. High-frequency actions and keyboard operations do not add animation.
2. UI entry motion uses ease-out so the interface responds immediately and settles gently.
3. Ordinary UI motion should finish in under `300ms`.
4. Never animate from or to `scale(0)`.
5. Never use `transition: all`.
6. Prefer `transform` and `opacity`; avoid layout-triggering animation.
7. Motion must be interruptible and must resolve to the latest application state.
8. Respect `prefers-reduced-motion` in CSS and JavaScript.
9. A Popover expands from the direction of its trigger and uses a matching `transform-origin`.
10. Motion communicates hierarchy or state change. Decorative motion that does not explain either is omitted.

## Duration and Easing Tokens

```css
--motion-instant: 0ms;
--motion-fast: 120ms;
--motion-standard: 180ms;
--motion-slow: 260ms;
--ease-out-ui: cubic-bezier(.16, 1, .3, 1);
--ease-in-ui: cubic-bezier(.7, 0, .84, 0);
--ease-standard-ui: cubic-bezier(.2, 0, 0, 1);
```

- Hover, press, focus, and selection feedback: `0–120ms`.
- Disclosure, Toast, and small Popover: `120–180ms`.
- Sidebar, Inspector, Sheet, and modal entry: `180–260ms`.
- Ordinary transitions above `300ms` require an explicit documented exception.
- Continuous progress indicators may have a longer loop, but they stop immediately when work stops and become static under reduced motion.

Entry uses `--ease-out-ui`. Exit may use a shorter ease-in. Reversing state during a transition must reverse or retarget the same transition; it must not queue a second animation.

## Property Rules

Preferred:

- `transform: translate…` for spatial entry and exit;
- `opacity` for layering and visibility;
- color/background/border-color for immediate interaction feedback;
- a determinate progress indicator may update `width` without decorative easing.

Avoid:

- animated `width`, `height`, `top`, `left`, margin, padding, or grid definitions for general layout;
- animating from `height: 0` to `height: auto`;
- large blur animation;
- bouncing or spring overshoot in routine productivity flows;
- parallax, cursor-following effects, and animated gradients;
- transforms that make text visibly resample or blur.

Direct split-view resizing follows the pointer with no transition. Persisted width restoration also has no transition.

## Interaction Matrix

| Interaction | Motion |
| --- | --- |
| Keyboard seek, playback, tab navigation, search typing | none |
| Pointer hover/press | immediate or `≤120ms` color/opacity feedback |
| Disclosure chevron | `120–160ms` rotation; content appears without a staged delay |
| Sidebar/Inspector/Sheet | `180–220ms` directional translation plus scrim opacity |
| Dialog | `160–220ms` opacity plus `4–8px` translation; never `scale(0)` |
| Popover | `120–180ms` opacity plus `4–6px` translation from trigger side |
| Toast | `160–180ms` opacity plus small vertical translation |
| Segmented selection | immediate state update; optional `≤160ms` indicator translation |
| Loading spinner | continuous rotation only while genuinely busy |
| Determinate progress | bounded update up to `250ms`; no false completion animation |
| Auto-follow transcript | no smooth animation for repeated updates; keep the active item visible directly |

## Popover Direction

A Popover’s entry direction follows its placement relative to the trigger:

```css
[data-side="bottom"] { transform-origin: top center; }
[data-side="top"]    { transform-origin: bottom center; }
[data-side="right"]  { transform-origin: left center; }
[data-side="left"]   { transform-origin: right center; }
```

- Bottom Popover begins `4–6px` toward the trigger and moves downward into place.
- Top Popover begins `4–6px` toward the trigger and moves upward into place.
- Left/right Popovers follow the equivalent horizontal rule.
- Collision handling may change `data-side`; motion origin must update in the same frame.
- The trigger remains visually anchored; it does not scale or jump.

## Interruptibility

- Prefer class- or attribute-driven CSS transitions over chains of `setTimeout` calls.
- Opening a different Sheet closes or retargets the current one immediately.
- Repeated clicks cannot enqueue duplicate entry animations.
- Removing an item during motion must leave no invisible focusable element.
- `transitionend` may be used for cleanup, but correctness must not depend on the event firing.
- Network completion updates state immediately; motion never delays success, error, or cancellation reporting.

## Reduced Motion

CSS must disable nonessential movement:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

JavaScript must also consult `matchMedia("(prefers-reduced-motion: reduce)")`:

- replace `scrollIntoView({ behavior: "smooth" })` with instant scrolling;
- avoid focus delays that exist only to wait for animation;
- do not animate transcript-follow, keyboard seek, or “back to top” actions;
- replace rotating activity with a static busy affordance when practical;
- preserve all state changes and focus movement.

Reduced motion is a product mode, not merely a shortened duration.

## Current Motion Audit

Existing strengths:

- no `transition: all`;
- no `scale(0)`;
- ordinary CSS transitions are currently `150–250ms`;
- Sidebar and Toast already use `transform` and/or `opacity`;
- a reduced-motion media query is present.

Required later corrections:

1. Replace generic `ease` on drawer/disclosure motion with the entry/exit easing tokens.
2. Consolidate the duplicate Sidebar transition definitions.
3. Add a shared JavaScript reduced-motion helper.
4. Remove smooth scrolling from keyboard seek, repeated transcript-follow updates, and other high-frequency actions.
5. Make “back to top,” chat focus, and Sidebar search focus select instant behavior when reduced motion is requested.
6. Avoid relying on the current `80ms`, `200ms`, `450ms`, and `700ms` timing delays for correctness or focus.
7. Keep progress changes semantic; do not animate guessed percentages as if they were measured work.

## Review Commands

The implementation review should include:

```powershell
rg -n "transition\s*:\s*all|scale\(0" src/web_ui
rg -n "transition|animation|@keyframes|behavior:\s*\"smooth\"" src/web_ui
rg -n "prefers-reduced-motion|matchMedia" src/web_ui
```

Any exception must be listed in the pull request with the interaction, duration, property, reason, and reduced-motion behavior.
