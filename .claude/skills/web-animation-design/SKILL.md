---
name: web-animation-design
description: >-
  TRIGGER when designing, reviewing, or fixing a web animation in `frontend/` —
  choosing easing (ease-out vs ease-in-out vs ease), a duration, or a spring;
  diagnosing "feels janky" / "make it smooth"; entrance / exit / hover / modal /
  drawer / tooltip / stagger motion; animation performance (transform/opacity-
  only, will-change, GPU); or prefers-reduced-motion + touch-hover
  accessibility. Pairs with `docs/design.md` §Motion (the project's 5 motion
  rules) and `frontend/lib/useMotion.ts`. Do NOT auto-fire on incidental
  transform/opacity/transition in unrelated layout/CSS work, or on backend
  Python.
---

# Web Animation Design

A decision guide for adding motion that feels intentional rather than
decorative. The principles below are standard front-end practice (easing
families, duration bands, the transform/opacity GPU rule, the
`prefers-reduced-motion` contract); this skill curates them for QuantRank
and ties each one back to the motion system already in the repo. See the
**Attribution** section at the bottom for the references this distills.

This skill is the *general* animation reference. The *binding* project
rules live in [`docs/design.md`](../../../docs/design.md) §Motion (5
non-negotiables) and the hooks in
[`frontend/lib/useMotion.ts`](../../../frontend/lib/useMotion.ts)
(`useCountUp`, `usePlayOnMount`). When the two disagree, `docs/design.md`
wins — it is the contract; this skill is the rationale.

## First question: should this animate at all?

Motion is a cost (attention, CPU, accessibility surface). Spend it only
where it buys spatial continuity or feedback.

- **Frequency gate** — if a user triggers the interaction dozens of times
  a session, do NOT animate it (or make it near-instant). In QuantRank
  this is why the 502-row ranking table cells render static server-side and
  only the `ScoreBadge` `lg` variant (one per stock-detail page) gets the
  signature gauge sweep. A reveal you see once per page-open earns a beat;
  a sort you click ten times in a row does not.
- **Animate** entrances/exits (spatial continuity), state changes that
  benefit from continuity, and direct responses to a user action
  (feedback).
- **Don't animate** keyboard-driven actions, hover on high-frequency
  controls, or anything where raw speed beats smoothness.

## Easing — pick by what the element is doing

| Situation | Easing | Why |
|---|---|---|
| Element entering or leaving the screen (dropdown, modal, toast, card reveal) | **ease-out** | Fast start = instant, responsive; settles into place |
| Element already on screen that moves/resizes/morphs | **ease-in-out** | Accelerate then brake — reads as natural motion |
| Hover state / color transition | **ease** (or a short ease-out) | Gentle, symmetric enough for small changes |
| Continuous motion (marquee, ticker, determinate progress) | **linear** | Constant speed is correct here; everywhere else it feels robotic |
| (almost never) | **ease-in** | Slow start delays feedback — feels sluggish; avoid for UI |

Decision shortcut: *entering/exiting → ease-out · moving on screen →
ease-in-out · hover → ease · constant → linear · default → ease-out.*

Reusable `cubic-bezier` values (public easing constants, see Attribution):

```css
/* ease-out family, weak → strong */
--ease-out-quad:  cubic-bezier(0.25, 0.46, 0.45, 0.94);
--ease-out-cubic: cubic-bezier(0.215, 0.61, 0.355, 1);
--ease-out-quart: cubic-bezier(0.165, 0.84, 0.44, 1);
--ease-out-quint: cubic-bezier(0.23, 1, 0.32, 1);
--ease-out-expo:  cubic-bezier(0.19, 1, 0.22, 1);
/* ease-in-out family, weak → strong */
--ease-in-out-cubic: cubic-bezier(0.645, 0.045, 0.355, 1);
--ease-in-out-quart: cubic-bezier(0.77, 0, 0.175, 1);
```

QuantRank already uses `cubic-bezier(0.22, 1, 0.36, 1)` (an ease-out-quint
relative) for the gauge sweep and `rise-in` entrance — match it for new
entrances so the app's motion feels like one hand.

**Paired-element rule.** Anything that moves as a unit shares one easing
AND one duration — modal + its overlay, drawer + its backdrop, tooltip +
its arrow. If they drift apart in timing the unit falls apart visually.

## Duration

| Element | Duration |
|---|---|
| Micro-interaction (button press, toggle, icon) | 100–150 ms |
| Standard UI (tooltip, dropdown, chip) | 150–250 ms |
| Modal / drawer / large panel | 200–300 ms |
| Signature moment (rare, one-per-view) | up to ~800 ms |

Rules of thumb: keep functional UI under ~300 ms; larger or
farther-traveling elements animate a touch slower; an exit can run ~20%
faster than the matching entrance; match duration to distance. QuantRank's
fast entrances sit at 260–320 ms (`chip-pop`, `rise-in`); the one
deliberate long beat is the 800 ms composite-score gauge sweep — that is
the headline number, so it earns the extra time, and it plays once per
detail-page visit, never on a loop.

## Springs

Springs feel organic because they model physics instead of a fixed
duration, and — unlike CSS keyframes — they keep velocity when
interrupted. Reach for them for **drag / gesture** interactions that a
user might reverse mid-motion, or elements meant to feel alive.

- Prefer the duration-and-bounce mental model
  (`{ duration: 0.5, bounce: 0.2 }`) over raw mass/stiffness/damping.
- Keep **bounce subtle (0.1–0.3)** and only where playfulness is wanted
  (drag-to-dismiss). Most product UI wants no bounce.
- QuantRank ships **CSS/Tailwind motion only — no framer-motion / spring
  library** (see `docs/design.md` §Motion). So springs here are a
  *concept for future gesture work*, not a current dependency. Don't add a
  spring runtime without an explicit PR + design sign-off.

## Performance — the one hard rule

**Only animate `transform` and `opacity`.** They skip layout + paint and
run on the GPU compositor. Everything else risks dropped frames.

- Avoid animating `width` / `height` / `margin` / `padding` / `top` /
  `left` (force layout) and large `blur` filters (> ~20px, expensive,
  worst on Safari).
- `will-change: transform` can promote an element to its own layer for a
  janky animation — use sparingly and remove it after; a permanent
  `will-change` wastes memory.
- **CSS vs JS**: CSS animations run off the main thread (smoother under
  load) — prefer them for simple, predetermined motion. Use JS
  (`requestAnimationFrame`) only when the motion is dynamic or
  interruptible; if you drive it from React, update via refs, not
  per-frame state, or every frame re-renders.

QuantRank precedent: `rise-in` / `chip-pop` / `flag-pulse` are
transform+opacity-only by design (an early `flag-pulse` draft animated
`box-shadow` and was dropped for violating this rule). The gauge sweep
animates `stroke-dashoffset` via a CSS `@keyframes` (not a transition —
a transition needed two committed paint frames Chromium batched away, so
it was silently invisible until a 2026-05-29 audit caught it; the keyframe
plays reliably on class-add).

## Accessibility — non-negotiable

Every animated surface needs a `prefers-reduced-motion: reduce` escape
that snaps to the end state:

```css
@media (prefers-reduced-motion: reduce) {
  .my-entrance { animation: none; }   /* no !important needed */
}
```

- One reduced-motion guard per animated element (or one shared block, as
  in `frontend/app/globals.css`). No exceptions for "just opacity."
- Gate the motion in JS too, not only in CSS — QuantRank's `usePlayOnMount`
  returns `false` under reduced motion so the animate class is never even
  added (the end-state renders directly). Never gate *content visibility*
  on the animation: the page must be fully usable if the motion no-ops.
- **Touch-hover guard** — hover effects fire on tap on touch devices.
  Wrap pointer-only hover motion (a pattern for new authors — not yet
  wired in the current `frontend/`):
  ```css
  @media (hover: hover) and (pointer: fine) {
    .row:hover { transform: translateY(-1px); }
  }
  ```

## Review format

When reviewing animation code, present findings as a **single markdown
table with `Before` / `After` columns** (one row per issue), not as prose
pairs. It makes the delta scannable. Example:

| Before | After |
|---|---|
| `transform: scale(0)` (pops from nothing) | `transform: scale(0.95)` (settles in) |
| `400ms ease-in` (sluggish) | `200ms ease-out` (responsive) |
| no reduced-motion guard | `@media (prefers-reduced-motion: reduce) { … }` |
| animating `height` | animate `transform: scaleY()` or `max-height` swap |

## Quick fixes

| Symptom | Fix |
|---|---|
| Button feels dead on press | `transform: scale(0.97)` on `:active` |
| Element "pops" from nowhere | start from `scale(0.95)`, not `scale(0)` |
| Shaky / sub-pixel jitter | promote with `will-change: transform` (then remove) |
| Hover flicker | animate a child, not the element that holds the `:hover` |
| Popover grows from the wrong corner | set `transform-origin` to the trigger |
| Sequential tooltips feel slow | skip the entrance after the first in a group |
| Hover motion fires on mobile tap | `@media (hover: hover) and (pointer: fine)` |
| Entrance double-plays on a static export | add the animate class client-side after mount (see `usePlayOnMount`), never bake it into prerendered HTML |

## Attribution

The principles here are standard front-end animation practice. This skill
is **QuantRank-original prose** — no third-party text is copied. It
distills widely-published knowledge and is **inspired by Emil Kowalski's
"Animations on the Web"** course (<https://animations.dev/>); the
`cubic-bezier` constants are the public easing values catalogued at
<https://easings.net/>. Consult those sources directly for depth. The
binding project rules remain `docs/design.md` §Motion.
