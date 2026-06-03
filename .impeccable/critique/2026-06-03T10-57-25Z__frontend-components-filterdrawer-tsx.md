---
target: filter UI (FilterDrawer + toolbar, all breakpoints/platforms)
total_score: 34
p0_count: 0
p1_count: 3
timestamp: 2026-06-03T10-57-25Z
slug: frontend-components-filterdrawer-tsx
---
# Critique — Filter surface (FilterDrawer + RankingTable toolbar + DualRange + chips)

Scope: the full filter experience across breakpoints/platforms — the `Filters` toolbar
button + active-filter chip row (RankingTable.tsx), the slide-in `FilterDrawer.tsx`
(search · composite-score dual-range · score-tier · recommendation · valuation · sectors),
`DualRange.tsx`, and the shared chip tokens (visual.ts). Evidence: source review + two
user-supplied Android-Chrome mobile screenshots + impeccable detector. Desktop/tablet
reasoned from Tailwind breakpoint classes (no browser pass — node_modules absent).

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 4 | Live count in header + footer CTA + active-chip row + button badge; instant. |
| 2 | Match System / Real World | 3 | "MoS ≥ +10%" / "Composite score" assume domain knowledge; defined inline but tersely. |
| 3 | User Control and Freedom | 3 | Esc/backdrop/X/Clear-all/per-chip remove — but on full-width MOBILE drawer there is no backdrop and the only cancel (X) sits top-right, outside the thumb zone. |
| 4 | Consistency and Standards | 4 | One outlined-light chip vocabulary shared app-wide; rounded-sm, tabular-nums, mirrored active chips. |
| 5 | Error Prevention | 4 | "View" disabled at 0 results; compare disabled <2; lo<hi clamp on the slider. |
| 6 | Recognition Rather Than Recall | 3 | On DESKTOP all filters hidden behind a button (recall they exist); default all-gray chips kill pre-attentive color grouping. |
| 7 | Flexibility and Efficiency | 3 | Live + URL-shareable + persisted; but no presets, no "select all/none" per group, no group-level clear. |
| 8 | Aesthetic and Minimalist Design | 3 | Six visually identical gray label+pill sections; ragged flex-wrap right edge; mobile pills look inflated (44px min-h around 12px text). |
| 9 | Error Recovery | 4 | Empty state is genuinely good: SearchX glyph + human heading + "Try a wider score range" + Clear-all CTA. |
| 10 | Help and Documentation | 3 | Inline range hints exist but render at `text-[0.625rem] opacity-60` — too small/low-contrast to be reliable help. |
| **Total** | | **34/40** | **Good — solid, consistent, accessible-by-construction; judgment-level polish gaps, no structural breakage.** |

## Anti-Patterns Verdict

**LLM assessment:** Does NOT read as AI slop. It reads as a deliberately restrained financial
tool — neutral steel chips, 2px radius, mono tabular numerics, one forest-green CTA. On-brand
("Numbers you can read like a ledger"). The risk here is the opposite of slop: it is so
uniformly gray that the filter has almost no visual hierarchy between its six sections, and the
chip wrap is ragged rather than ledger-tidy, which slightly undercuts the "precise/editorial"
personality the rest of the app earns.

**Deterministic scan:** `detect.mjs --json` on FilterDrawer/DualRange/RankingTable/Chip/SectorChip
returned `[]` (exit 0). No gradient text, no side-stripe borders, no >=32px card radius, no
ghost-card (1px border + >=16px shadow), no glassmorphism, no repeating-gradient stripes. The
mechanical-slop surface is clean; every finding below is judgment-level.

**Visual overlays:** Not available — node_modules absent, no install/build/live-server run.
Mobile evidence is the two user screenshots; desktop/tablet reasoned from Tailwind classes.

## Overall Impression

A well-engineered, accessible filter that is doing the brand proud on discipline (focus-trap,
focus-visible ring, reduced-motion guard, 44px targets, live status, excellent empty state) but
is leaving aesthetic and IA points on the table. Biggest single opportunity: the **desktop
experience hides the screener's primary task (filtering 502 names) behind a button + a 448px
modal drawer**, on a layout that already has a left sidebar rail and acres of horizontal room.

## What's Working

1. **Status legibility.** The live `filtered / total stocks` count (header + footer + button
   badge) means the user always knows the consequence of a toggle before committing. The footer
   `View N stocks` is pinned and thumb-reachable; `No matching stocks` disables it so a bright
   CTA never points at a 0-result screen. This is the brand's "honest by construction" done right.
2. **One chip vocabulary, app-wide.** Toggles reuse the exact outlined-light tone tokens
   (TIERS / MOS_BUCKETS / RECOMMENDATION_CHIP_TONES / sectorStyle) the table and badges use, so a
   selected "Undervalued" chip in the drawer is visually identical to its table cell. Consistency
   is a feature here and it is honored.
3. **Accessibility baked in.** Focus trap + restore-focus-on-close, Esc, body-scroll-lock,
   global `:focus-visible` indigo ring, comprehensive `prefers-reduced-motion` guard, aria-labels
   on the dual-range handles, 44px touch targets (`lg:min-h-0` relaxes only on desktop). Sam
   (screen-reader/keyboard) can drive this.

## Priority Issues

### [P1] Desktop filtering lives in a modal drawer, not on the surface
- **Why it matters:** The product register's own rule is "Modal as first thought is usually
  laziness; exhaust inline/progressive alternatives first." Filtering IS the primary task of a
  502-row screener. On a 1440px desktop the user clicks `Filters`, a 448px panel slides over a
  dimmed table, they toggle, then dismiss to see results — a back-and-forth that a persistent
  left filter rail (the app already ships a left Sidebar) or an inline filter bar would remove.
  Best-in-class screeners (Bloomberg, Linear/Notion list filters) keep filters resident on wide
  viewports. The drawer is right for mobile; it is a cognitive tax on desktop.
- **Fix:** Above `lg`, render the same FilterState/FilterSetters in a persistent left rail or a
  collapsible inline panel; keep the drawer only below `lg`. The state layer already supports it
  (the drawer is a pure controlled view of RankingTable state).
- **Suggested command:** `$impeccable adapt`

### [P1] Inline help + selected-chip labels flirt with the WCAG AA floor the brand promises
- **Why it matters:** Accessibility target is stated as WCAG 2.1 AA (body >=4.5:1). Three places
  are at/over the line: (a) the chip range/help text renders at `text-[0.625rem] opacity-60` —
  10px AND 40%-faded, which fails 4.5:1 on both the gray and tinted chip backgrounds; (b) the
  selected positive/negative chip label is the softened `--c-pos-medium` oklch(56% 0.12 152) on
  `--c-pos-bg` oklch(97%…), which measures close to ~3.5:1 for the 12px medium label — at risk;
  (c) the light-mode search placeholder sets NO `placeholder-*` color (only `dark:placeholder-slate-500`),
  so it falls to the UA default and is unverified. For a tool whose whole pitch is "trust the
  number," text you cannot read is the worst failure mode.
- **Fix:** Drop `opacity-60` on the help text; use a solid `text-slate-500`/tonal-700 at >=11px.
  Measure the selected-chip label contrast and bump `--c-pos-medium`/`--c-neg-medium` toward
  `*-strong` if it misses 4.5:1. Add `placeholder-slate-500` to both search inputs to match the
  dark side and guarantee AA.
- **Suggested command:** `$impeccable colorize` (then `$impeccable audit` to verify ratios)

### [P2] The filter is six identical gray sections — flat hierarchy, ragged wrap
- **Why it matters:** Every group is `uppercase tracking-wider 11px slate-700` label + a row of
  `bg-slate-100` pills. Nothing signals that SECTORS (11 options, ~6 wrapped rows on mobile) is
  heavier than VALUATION (3). Combined with variable-width chips left-packed into a ragged right
  edge, the drawer reads as a long monotonous scroll rather than the crafted, precise surface the
  detail page and table achieve. This is the gap between "not slop" and "designed."
- **Fix:** Give the long SECTORS group its own rhythm — a tidy 2-column checklist or an `auto-fit`
  grid so the right edge is straight and the 11 options scan as a block; add a subtle section
  divider or vary label weight/spacing so the eye chunks the six groups. Consider grouping the
  redundant Composite-score slider + Score-tier chips under one "Score" heading.
- **Suggested command:** `$impeccable layout`

### [P2] Mobile cancel is stranded at the top; full-width drawer kills the backdrop exit
- **Why it matters:** On phones the drawer is `w-full`, so there is no visible backdrop to tap —
  the documented "backdrop click closes" exit is desktop-only. The remaining non-apply exit is the
  `X` at top-right, the hardest spot to reach one-handed on a tall phone (Casey). The happy path
  (`View N stocks`, bottom) is fine; the "back out without changing my mind" path is not. Filters
  also apply live, so there is no true revert.
- **Fix:** Add a bottom-row dismiss affordance on mobile (e.g. make `Clear all` share the footer
  with a `Done`/close, or add a drag-down-to-close grabber), or keep a thin tappable backdrop gutter.
- **Suggested command:** `$impeccable adapt`

### [P3] Inflated mobile pills + neutral slider fill miss small craft beats
- **Why it matters:** The 44px touch-target floor (correct for a11y) wraps 12px text in a pill
  with ~14px of vertical dead space, so chips read slightly "blown up." Separately, the
  composite-score active range is `bg-slate-900` (neutral) where the product register allows the
  brand accent for a current selection — a missed, on-brand emerald beat.
- **Fix:** Let the pill height read as intentional by aligning chips to a grid (P2 fix helps);
  optionally tint the slider's active segment with `--c-pos`/emerald to mark it as the selection.
- **Suggested command:** `$impeccable polish`

## Persona Red Flags

**Casey (Distracted Mobile User):** Full-width drawer → no backdrop tap-to-dismiss; the only
cancel is the top-right `X`, unreachable one-handed on a tall phone. The long SECTORS block forces
multi-screen scrolling to reach the last sector. Happy path (bottom `View N stocks`) is good, and
state persists across tab-switch (sessionStorage + URL) — that part respects her.

**Sam (Accessibility-Dependent):** Strong overall — focus trap, focus-visible ring, aria-labels,
reduced-motion. BUT the `opacity-60` 10px range hints and the unset light-mode placeholder will
fail her 4.5:1 needs, and the selected-chip label is borderline. Color is never the ONLY signal
(every chip has a dot + label), which is correct.

**Margaret (project persona — Skeptical Value Screener):** Wants to slice 502 names fast and
distrusts black boxes. She is annoyed that on her desktop the filters hide behind a button instead
of sitting beside the table, that "Composite score" (slider) and "Score tier" (chips) are two
controls for one metric with no explanation of how they interact, and that the help text telling
her what MoS means is the least-readable text on the panel. She trusts the live count, though.

## Minor Observations

- Search appears twice (page toolbar + drawer) bound to one state — fine (sync), mildly redundant.
- `View N stocks` is really "Close" (filtering is already live); label is friendly but not literal.
- DualRange: when lo and hi converge, the top-painted (max) thumb steals the grab; standard native
  two-thumb limitation — consider z-swapping by proximity (Riley).
- `type="search"` shows a native clear `x` on some platforms, duplicating app affordances; on iOS
  Safari the search/range inputs may pick up native chrome since `appearance` isn't reset on the box.
- Count is shown three times (header ratio, toolbar ratio, footer CTA) — useful, but a lot of "N / 502".

## Questions to Consider

- What would the desktop screener look like if the filters never left the screen?
- Do the composite-score slider AND the score-tier chips both need to exist, or is one the honest control?
- If the help text is worth showing, why is it the hardest thing on the panel to read?
- Could the eleven sectors scan as a tidy block instead of a ragged wrap?

## Addendum — Dark + Light mode theme audit (2026-06-03)

Token-level pass over every filter color pair across both themes (`:root` light band
oklch 56%/97% vs `.dark` band oklch 66%/22%) plus the resolution path of the
`globals.css` soft-color `!important` override layer. No browser pass (node_modules
absent) — ratios marked `~` are hand-derived from the OKLCH→sRGB tokens and should be
confirmed in-browser; direction (pass/fail) is confident.

### Per-element light vs dark

| Element (filter) | Light | Dark | Verdict |
|---|---|---|---|
| Section labels `slate-700/300` | OK ~8:1 | OK ~7:1 | pass both |
| Unselected chip TEXT `slate-600/400` | OK ~7:1 | OK ~5.5:1 | pass both |
| Unselected chip FILL vs panel | OK `slate-100` on white | FAIL `slate-900` chip on `slate-900` panel (ring-only) | dark affordance loss |
| Selected chip label (pos/neg) | FAIL ~3.4:1 (`--c-*-medium` on 97% tint) | OK (light text on 22% tint) | light fail |
| Chip help/range text `opacity-60` 10px | FAIL ~1.9:1 | FAIL ~3.7:1 | fail both |
| Search placeholder | FAIL unset (UA default) | OK `slate-500` | light gap |
| DualRange track/fill/thumb | OK | OK | pass both |
| Primary CTA "View N" (white on green) | OK `emerald-700` ~5.8:1 | FAIL `emerald-600` ~3.5:1 | dark fail |
| Backdrop scrim `slate-900/40` | OK dims light page | WEAK under-dims (≈ `slate-950`) | dark weak (desktop) |
| Count / footer / borders | OK | OK | pass both |

### Theme strengths

- **Zero light-only leak** — every filter surface ships a `dark:` pair (panel/border/label/
  count/input/track/thumb/footer/CTA/all chip families). Honors PRODUCT.md "never ship a
  light-only surface."
- DualRange inverts correctly (fill `slate-900`→`slate-100`, thumb border+bg swap); semantic
  tokens flip cleanly through `:root`/`.dark` with hue held constant (152/18) so warmth does not
  shift between themes.

### Theme-specific issues

#### [P1] Dark-mode primary CTA fails AA — and the soft-override never reaches `dark:` variants
- **Mechanism:** the override layer keys on the LITERAL utility class (`.bg-emerald-600 { … !important }`).
  The dark CTA uses `dark:bg-emerald-600`, a different class token, so the override does NOT apply —
  it renders raw Tailwind `emerald-600` (#059669); white label on it ~3.5:1, under the 4.5:1 the
  brand promises for 14px text. Light uses `bg-emerald-700` (#15803D) ~5.8:1, safe.
- **Wider implication (audit beyond filter):** EVERY `dark:bg-emerald-*` / `dark:bg-rose-*`
  SOLID-FILL surface app-wide bypasses the "soft" system and renders at full Tailwind saturation in
  dark. In the filter the only victim is the CTA; this is the dark-side blind spot of the §Gotchas
  "soft-color overrides are an ALLOWLIST" rule.
- **Fix:** dark CTA → `dark:bg-emerald-700` (white reads), or add a `.dark .dark\:bg-emerald-600`
  override mapping to `--c-pos-strong`; cleanest is to drive the CTA from `--c-pos-strong` directly.

#### [P1] Help/range `opacity-60` text fails in BOTH modes
- Light ~1.9:1 (hard fail), dark ~3.7:1 (still under) — 10px AND 40%-faded loses both ways
  ("70-100", "MoS ≥ +10%", "±10% MoS"). Fix: drop `opacity-60`, use solid `text-slate-500
  dark:text-slate-400` at >=11px. (Same finding as the main report's P1(a), now confirmed both-mode.)

#### [P2] Selected chip label ~3.4:1 in LIGHT only (dark passes)
- `--c-pos-medium` oklch(56%) / `--c-neg-medium` oklch(54%) on the 97% tint ~3.4:1 for the 12px
  medium label (both hues). Dark = light text oklch(66%) on dark tint oklch(22%), comfortable.
  Fix: in light, push selected chip text to `--c-pos-strong` / `text-emerald-800` (~4.5:1+).

#### [P2] Unselected toggle chips disappear into the panel in dark
- Toggle chip `dark:bg-slate-900` == drawer panel `dark:bg-slate-900` → no fill contrast, only the
  `slate-700` ring delineates. Light shows them filled (`slate-100` on white). So the chip
  affordance differs by mode (filled in light, outline-only in dark), AND it is inconsistent with
  the drawer's own active-summary chips, which use `dark:bg-slate-800` (filled) in the same panel.
  Fix: unselected toggle chip → `dark:bg-slate-800` (match summary chips), or drop the panel to
  `slate-950` so `slate-900` chips lift off it.

#### [P2] Light-mode search placeholder color unset (dark handled)
- Only `dark:placeholder-slate-500` is declared; light falls to the UA default (browser-dependent,
  ~4.5:1 borderline). Fix: add `placeholder-slate-500` to both search inputs.

#### [P3] Backdrop scrim is not theme-aware — under-dims in dark
- `bg-slate-900/40` over the dark page (`slate-950`) is a near-invisible dim → weak modal separation
  on DESKTOP dark (mobile unaffected; the full-width drawer covers everything). Fix: `bg-black/50`
  or a dark-aware higher opacity.

### Theme verdict

Structure is sound (complete pairing, no leak), but contrast splits three ways: DARK is hit by the
white-on-green CTA (P1), chip-fill loss (P2), and weak scrim (P3); LIGHT is hit by the selected-chip
label (P2) and unset placeholder (P2); BOTH modes are hit by the `opacity-60` help text (P1). The
most systemically interesting finding is that the soft-override allowlist does not reach `dark:`
solid-fill utilities — worth an app-wide audit, not just the filter.
