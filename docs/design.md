# QuantRank Design System

_Static-site US-equity ranking — visual spec, last updated 2026-05-22._

A design specification in the spirit of
[LedgerCraft](https://designmd.ai/chef/ledgercraft). LedgerCraft was
adopted as the visual anchor across three PRs:

- **Phase 1** (PR #211, 2026-05-22) — Roboto Slab + 4-tier shadow tokens
- **Phase 2** (PR #212, 2026-05-22) — token propagation to per-stock detail pages
- **Phase 3a** (PR #213, 2026-05-22) — spreadsheet polish on section h2s + table theads

The values below are the canonical reference for any new UI surface.
The companion enforcement rules live in
[`.claude/skills/frontend-design-system/SKILL.md`](../.claude/skills/frontend-design-system/SKILL.md).

---

## Vibe

> **"Numbers you can read like a ledger."**

A financial-analyst spreadsheet feel — flat surfaces, crisp borders,
tabular numerics, dense data presentation, restrained palette. The
register sits between Bloomberg terminal and a well-typeset annual
report. Editorial without being decorative; precise without being
sterile.

Three governing instincts:

1. **Tabular discipline** — every numeric column uses `tabular-nums`
   so digits right-align. No exceptions.
2. **Soft palette, no saturation** — semantic green / red are muted
   sage + dusty rose, not "bright fresh green" or alarm red.
3. **One chip pattern** — outlined-light chips with a dot for
   hierarchy, never solid-fill (the solid-fill variant was retired
   in PR #68).

---

## Color palette

### Base

| Role | Token | Value | Purpose |
|---|---|---|---|
| App background | `neutral-50` | `#FAFAFA` | Body canvas (LedgerCraft canonical) |
| Surface | `white` | `#FFFFFF` | Cards, table rows (odd) |
| Surface (alt) | `slate-50` | `#F8FAFC` | Table rows (even) — alternating-row pattern |
| Hover | `slate-100` | `#F1F5F9` | Table row hover, button hover |
| Border | `slate-200` | `#E2E8F0` | Card borders, table dividers (header) |
| Divider | `slate-100` | `#F1F5F9` | Table body row dividers |
| Body text | `slate-900` | `rgb(15 23 42)` | Primary content |
| Subdued text | `slate-600` / `slate-500` | — | Section labels (600) / micro labels (500) |
| Muted text | `slate-400` | — | Captions, "N/A", aria-hidden glyphs |

### LedgerCraft canonical accents (Phase 3b)

QuantRank's brand palette aligns to the LedgerCraft spec. The hex
values below are the canonical truth; the Tailwind classes are the
single approved way to reach them in code (no inline hex per Rule 0).

| Role | LedgerCraft hex | Tailwind class | Use |
|---|---|---|---|
| **Primary** (forest green) | `#15803D` | `emerald-700` | CTAs, wordmark Q logo, "View N stocks" submit, positive balance |
| **Primary hover** | `#166534` | `emerald-800` | Primary button hover |
| **Secondary** (steel) | `#64748B` | `slate-500` | Secondary actions, column headers |
| **Tertiary** (amber) | `#B45309` | `amber-700` | Alerts, overdue notices, warning chip text |
| **Neutral** (gray) | `#9CA3AF` | ≈ `slate-400` | Borders, disabled states, placeholders |
| **Error** | `#DC2626` | `red-600` | Hard errors, rejected entries (rare — `rose-*` preferred for "overvalued") |
| **Info** | `#2563EB` | `blue-600` | Help links, informational notes |

The primary CTA chip family (`bg-emerald-700` + white text) is the
LedgerCraft "Primary button" pattern. Used for the FilterDrawer
"View N stocks" submit + the sidebar wordmark Q logo. NOT used for
chips / data surfaces — those follow the outlined-light pattern per
Rule 2.

### Semantic (OKLCH, soft band)

OKLCH was chosen over HSL because the perceptually-uniform lightness
axis prevents accidental saturation blowups — see `globals.css:55-75`.
Hue 155 (sage / muted green) for positive, hue 18 (dusty rose) for
negative. Both kept far from the "alarm" intensity.

| Role | CSS var | OKLCH | Purpose |
|---|---|---|---|
| Positive (strong) | `--c-pos-strong` | `oklch(50% 0.09 155)` | "Undervalued" text, MoS positive |
| Positive (medium) | `--c-pos-medium` | `oklch(56% 0.09 155)` | Bar fills, mid-emphasis |
| Positive (bg) | `--c-pos-bg` | `oklch(97% 0.025 155)` | Chip backgrounds |
| Positive (ring) | `--c-pos-ring` | `oklch(86% 0.06 155)` | Chip rings |
| Positive (dot) | `--c-pos-dot` | `oklch(60% 0.10 155)` | Chip dot |
| Negative (strong) | `--c-neg-strong` | `oklch(48% 0.09 18)` | "Overvalued" text, MoS negative |
| Negative (medium) | `--c-neg-medium` | `oklch(54% 0.09 18)` | Bar fills, mid-emphasis |
| Negative (bg) | `--c-neg-bg` | `oklch(97% 0.025 18)` | Chip backgrounds |
| Negative (ring) | `--c-neg-ring` | `oklch(86% 0.06 18)` | Chip rings |
| Negative (dot) | `--c-neg-dot` | `oklch(60% 0.10 18)` | Chip dot |

### Tailwind accent ramps

Where the OKLCH semantic colors don't fit (chip families, sector
palette, recommendation badges), the design uses the **slate / indigo
/ rose / amber** four-family Tailwind ramp. No other base hues — see
[Rule 0](#do-and-dont) below.

| Family | Use |
|---|---|
| `slate` | Neutral, default state, dividers |
| `indigo` | Info, links, secondary CTAs |
| `rose` | Strong negative state (rare; OKLCH preferred) |
| `amber` | Warnings, "Overdue / Pending" surfaces, manipulation index high |
| `emerald` | Recommendation chip "bullish" / "lean_bullish" (the only `emerald` exception) |

### Dark mode mapping (Phase 3b)

Every light surface ships with a paired `dark:` variant. The
canonical conversions:

| Light | Dark | Use |
|---|---|---|
| `bg-white` | `dark:bg-slate-900` | Card surface |
| `bg-slate-50` | `dark:bg-slate-900/50` or `dark:bg-slate-900/60` | Table thead, alternating row |
| `bg-slate-100` | `dark:bg-slate-800` | Hover, neutral chip bg |
| `border-slate-200` | `dark:border-slate-800` | Card border |
| `border-slate-100` | `dark:border-slate-800/60` | Divider |
| `text-slate-900` | `dark:text-slate-100` | Primary text |
| `text-slate-700` | `dark:text-slate-300` | Body text |
| `text-slate-600` | `dark:text-slate-400` | Section labels |
| `text-slate-500` | `dark:text-slate-400` | Sub-labels (mid) |
| `text-slate-400` | `dark:text-slate-500` | Captions, "N/A" |
| `text-slate-300` | `dark:text-slate-600` | Placeholder, em-dash |
| `hover:bg-slate-50` | `dark:hover:bg-slate-800/50` | Card hover |
| `hover:bg-slate-100` | `dark:hover:bg-slate-800` | Stronger hover |
| `bg-{tone}-50` | `dark:bg-{tone}-900/30` | Chip background |
| `text-{tone}-700` | `dark:text-{tone}-300` | Chip text (mid) |
| `text-{tone}-900` | `dark:text-{tone}-100` | Chip text (strong) |
| `ring-{tone}-200` | `dark:ring-{tone}-800` | Chip ring |
| `bg-{tone}-500` (dot) | `dark:bg-{tone}-400` | Chip dot |

---

## Typography

Four self-hosted faces via `@fontsource`. Each face is loaded as
woff2 + `@font-face` declarations in `globals.css`.

| Role | Family | Tailwind class | Use |
|---|---|---|---|
| Body | **IBM Plex Sans** | default (`font-sans`) | Paragraphs, labels, body text |
| Tabular numerics | **JetBrains Mono** | `font-mono` | Numeric columns, ticker codes |
| Editorial display | **Instrument Serif** | `font-serif` | Marquee headlines (sparingly) |
| Ledger headline | **Roboto Slab** | `font-slab` | h1/h2 hero surfaces, wordmark |

### Scale

| Token | Tailwind | px | Weight | Family | Use |
|---|---|---|---|---|---|
| Display | `text-3xl` | 30 | 700 | Roboto Slab | Hero stat (manipulation index) |
| Headline | `text-2xl` | 24 | 700 | Roboto Slab | Page H1, large badge |
| Subhead | `text-lg` | 18 | 600 | IBM Plex Sans | Card titles, headline panels |
| Body large | `text-base` | 16 | 400 | IBM Plex Sans | Long-form paragraphs |
| Body | `text-sm` | 14 | 400 | IBM Plex Sans | Default body, table cells |
| Body small | `text-xs` | 12 | 400 | IBM Plex Sans | Sub-labels, hints |
| Caption | `text-[11px]` | 11 | 500 | IBM Plex Sans | Disclaimers, fine print |
| Overline | `text-[10px]` | 10 | 500-600 | IBM Plex Sans | Micro labels (uppercase) |
| Code / numeric | `text-sm font-mono` | 14 | 400-600 | JetBrains Mono | Tickers, prices, ratios |

### Section header pattern (Phase 3a)

The canonical spreadsheet-style header — applied to every top-level
section `h2` AND every table `thead`:

```html
<h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600">
  Fair price check
</h2>
```

- **Weight**: `font-semibold` (600) — heavier than body
- **Tracking**: `tracking-[0.14em]` — wider than `tracking-wide` (0.025em)
- **Color**: `text-slate-600` — darker than micro labels at `slate-500`
- **Case**: `uppercase`

That triple is the "Excel / Numbers column header" register. Reserved
for top-level sections; micro labels inside cards stay at
`font-medium tracking-wide text-slate-500`.

---

## Spacing

Tailwind default 4px base. All paddings, gaps, and margins step in
multiples of 4px. The most-used increments:

| Token | px | Use |
|---|---|---|
| `gap-1.5` / `p-1.5` | 6 | Chip internals, tight icon gaps |
| `gap-2` / `p-2` | 8 | Chip group gaps, inline button padding |
| `px-3 py-2` | 12 / 8 | Table cell, button default |
| `p-4` | 16 | Card resting padding |
| `p-5` | 20 | Hero card, FairPriceBarChart |
| `gap-4` | 16 | Form rows, KPI grid gaps |
| `mb-4` | 16 | Section spacing |
| `space-y-2` | 8 | List rows |

Tables use compact `px-3 py-2` (12 × 8). Cards use `p-4` to `p-5`.
No surface uses ad-hoc pixel values.

---

## Elevation

Four formal shadow tokens, calibrated for slate-on-white. The names
mirror LedgerCraft's documented elevation system. Defined in
`tailwind.config.ts:25-34`.

| Tier | Tailwind | CSS | Use |
|---|---|---|---|
| **Subtle** | `shadow-subtle` | `0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 1px -1px rgb(15 23 42 / 0.02)` | Table row hover, badge surface, method-list `<ul>` |
| **Medium** | `shadow-medium` | `0 1px 3px 0 rgb(15 23 42 / 0.06), 0 1px 2px -1px rgb(15 23 42 / 0.04)` | Card resting — RankingTable, PillarRadarChart, RawMetricsTable, FairPriceBarChart headline |
| **Large** | `shadow-large` | `0 4px 8px -2px rgb(15 23 42 / 0.08), 0 2px 4px -2px rgb(15 23 42 / 0.04)` | Section emphasis — per-stock hero card |
| **Overlay** | `shadow-overlay` | `0 12px 24px -6px rgb(15 23 42 / 0.12), 0 4px 8px -4px rgb(15 23 42 / 0.06)` | Modal / drawer / popover — FilterDrawer |

`shadow-sm` / `shadow-md` / `shadow-lg` from Tailwind defaults are NOT
used. Use the formal tier names.

---

## Motion (Phase 4 tasteful-motion, 2026-05-29)

LedgerCraft stays **flat** — motion is the **entrance**, never a permanent
flourish. The bar is "tasteful, not playful" (Stripe / Linear, not a game
UI): motion guides attention and rewards arrival without ever undermining
the trust a finance tool needs. No animation library — pure CSS/Tailwind
keyframes + Recharts' built-in chart animation. Tokens in
`tailwind.config.ts`; keyframe bodies + utilities in `app/globals.css`;
JS hooks in `lib/useMotion.ts`.

### Tokens

| Token | What | Timing | Use |
|---|---|---|---|
| `animate-rise-in` | fade + 8px upward settle | 320ms `cubic-bezier(.22,1,.36,1)` | card / row / list-item entrance |
| `animate-chip-pop` | scale 0.85→1.04→1 overshoot | 260ms `cubic-bezier(.34,1.56,.64,1)` | verdict chips (recommendation / score-tier) |
| `animate-flag-pulse` | rise + scale settle (8px rise, 0.99→1.012→1) | 900ms ease-out, **single iteration** | risk-veto list items (attention beat, not blink) |
| `.gauge-arc` | `stroke-dashoffset` ease | 800ms `cubic-bezier(.22,1,.36,1)` | **signature** — ScoreBadge composite-score sweep |
| `.hover-lift` | `translateY(-1px)` | 160ms ease-out | table row / card hover (pairs with slate hover-bg) |
| `.stagger-1..12` | `animation-delay` 40–480ms | — | cascade a row/list group (capped at 12 steps) |
| `animate-shimmer` / `animate-fade-in` | (pre-existing) skeleton + mount | 1.5s / 200ms | async-loading placeholder |

### Five non-negotiable rules

1. **transform + opacity only** — never animate width/height/top/left (no
   layout reflow; the compositor handles transform/opacity on the GPU).
2. **Play on every visit, never loop.** Entrances fire once per mount via
   `usePlayOnMount` (`lib/useMotion.ts`) — each time the user arrives at a
   surface (open a stock, return to home) the entrance replays, so the app
   feels alive on every navigation. What's forbidden is *looping* /
   permanent motion (an animation that runs continuously after arrival) and
   *re-firing on in-page interaction* (sort/filter must not re-stagger — the
   RankingTable `interacted` latch enforces this within a mount). The **one
   signature** beat (gauge) is the only > 320ms animation.
3. **Reduced-motion is mandatory.** Every token has a
   `prefers-reduced-motion: reduce` off-switch in `globals.css` that snaps
   to the static end-state. Verify with Playwright `reducedMotion: 'reduce'`.
4. **Never gate content on JS.** Numbers/values render correct at SSR /
   pre-hydration / no-JS (`useCountUp` inits at the target; count-up is
   progressive enhancement). The static export must show real data, never
   a stuck `0.0`.
5. **Static-export rule: add animate classes CLIENT-SIDE, never in SSR
   markup.** Baking an entrance class into the prerendered HTML
   hydration-mismatches the client gate (rows stuck mid-fade). Effect-based
   `usePlayOnMount` returns false on first paint, flips true after mount —
   one imperceptible frame later.

### Signature moment

The composite-score radial gauge (`ScoreGauge.tsx`, the detail-page
`ScoreBadge size="lg"`) sweeps 0→value with a synchronized count-up over
800ms on first view this session. It is the app's headline number, so it
earns the one longer beat. Everything else stays in the ≤ 320ms micro
budget.

---

## Components

### Recommendation chip (canonical chip pattern)

The single chip shape used across the entire app. Outlined-light:
tinted background + ring + dot.

```html
<span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5
                 text-xs ring-1 ring-inset
                 bg-emerald-50 text-emerald-700 ring-emerald-200">
  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
  Lean bullish
</span>
```

| Recommendation | Background | Text | Ring | Dot |
|---|---|---|---|---|
| Bullish | `bg-emerald-50` | `text-emerald-900` | `ring-emerald-300` | `bg-emerald-700` |
| Lean bullish | `bg-emerald-50` | `text-emerald-700` | `ring-emerald-200` | `bg-emerald-500` |
| Neutral | `bg-slate-100` | `text-slate-700` | `ring-slate-300` | `bg-slate-500` |
| Lean cautious | `bg-amber-50` | `text-amber-700` | `ring-amber-200` | `bg-amber-500` |
| Cautious | `bg-rose-50` | `text-rose-700` | `ring-rose-300` | `bg-rose-600` |

### Sector chip

Same chip shape, sector-keyed palette. 11 sectors, all in the
4-family ramp (slate / indigo / rose / amber + emerald exception).
See `frontend/components/SectorChip.tsx`.

### Score badge

Tier-based composite-score badge. Five tiers — Strong / Above / Mid /
Below / Weak — each with its own background / text / ring triple.
`ScoreBadge.tsx` exposes `size="xs" | "sm" | "md"` variants.

### Table

```html
<div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-medium">
  <table className="min-w-full divide-y divide-slate-200 text-sm">
    <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
      <tr>
        <th className="px-3 py-2 text-left">Metric</th>
        <th className="px-3 py-2 text-right">Value</th>
      </tr>
    </thead>
    <tbody className="divide-y divide-slate-100">
      <tr className="odd:bg-white even:bg-slate-50 hover:bg-slate-100">
        <td className="px-3 py-2 text-slate-700">Market cap</td>
        <td className="px-3 py-2 text-right tabular-nums text-slate-900">$3.42T</td>
      </tr>
    </tbody>
  </table>
</div>
```

Three conventions:

1. **Alternating rows** — `odd:bg-white even:bg-slate-50 hover:bg-slate-100`
2. **Numeric columns** — `text-right tabular-nums` mandatory
3. **Header treatment** — Phase 3a spreadsheet style (`font-semibold tracking-[0.14em] text-slate-600`)

### Card

```html
<section className="rounded-lg border border-slate-200 bg-white p-4 shadow-medium">
  <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600">
    Section title
  </h2>
  ...
</section>
```

The hero card on the per-stock detail page uses `shadow-large`
instead of `shadow-medium` — the only section-emphasis exception.

### Drawer / modal

```html
<div className="fixed inset-y-0 right-0 w-full max-w-sm bg-white shadow-overlay">
  ...
</div>
```

`shadow-overlay` is the modal / drawer / popover-only tier.

### App shell (Phase 3c)

Layout shell is a left-rail sidebar + flex main column.

```
+--------+-----------------------------+
| Side   |  Slim header (mobile toggle) |
| bar    +-----------------------------+
| 240px  |  Disclaimer                  |
|        +-----------------------------+
| - Nav  |                              |
| - Rsrc |  <main>                      |
|        |                              |
|        +-----------------------------+
|        |  Footer                      |
+--------+-----------------------------+
```

| Surface | Pattern |
|---|---|
| Desktop sidebar | `md:sticky md:top-0 md:h-screen md:w-60` (240px default) / `md:w-16` collapsed (64px icon rail) |
| Collapse state | Persisted in `localStorage["quantrank.sidebar.collapsed"]` ("0" / "1") |
| Mobile drawer | Hidden by default (`-translate-x-full`), slides in via hamburger; backdrop `bg-slate-900/40` |
| Active route | `usePathname()` — both `/` and `/stock/<ticker>/` highlight the "Rankings" item |
| Sticky header | `sticky top-0 z-20 backdrop-blur bg-white/95` — only the mobile hamburger + status caption |

Sidebar item structure:

```html
<li>
  <Link className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm
                   text-slate-600 hover:bg-slate-50 hover:text-slate-900">
    <svg ... />
    <span>Rankings</span>
  </Link>
</li>
```

Active item swaps `text-slate-600` + `hover:bg-slate-50` for
`bg-slate-100 font-medium text-slate-900`. No accent color (slate
only) — keeps the sidebar neutral so the data surfaces own the
palette.

---

## Do's and Don'ts

### Rule 0 — Tailwind utility classes, no inline hex

**Do:** `className="bg-emerald-50 text-emerald-700 ring-emerald-200"`

**Don't:** `style={{ backgroundColor: '#ecfdf5' }}`

Inline hex bypasses the chip-family discipline and accumulates as
"design debt" that's invisible to Tailwind's purge.

### Rule 1 — Soft palette, no saturation

The semantic green / red ride the OKLCH soft band (hue 155 / hue 18,
chroma ≤ 0.10). The "bright fresh green" and alarm-red intensities
were explicitly rejected during design review.

**Do:** `style={{ color: 'var(--c-pos-strong)' }}` for "undervalued"

**Don't:** `text-green-500` or `text-red-600` for positive / negative
state (those Tailwind ramps are too saturated)

### Rule 2 — One chip pattern, no solid-fill

Every chip — sector, recommendation, score-tier, MoS, manipulation
risk, filter active state — uses the outlined-light pattern: tinted
`bg-X-50` + `text-X-700` + `ring-X-200` + optional dot.

**Do:** `bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200`

**Don't:** `bg-emerald-600 text-white` (solid-fill — retired PR #68)

### Rule 3 — Tabular numerics required

Every numeric column gets `tabular-nums` so the digits right-align
across rows. Without it, "$3.42T" and "$19.84B" mis-align by a digit
width.

### Rule 4 — Dark mode is class-strategy (Phase 3b shipped)

Dark mode toggles via `next-themes` adding `class="dark"` to
`<html>`. Tailwind `darkMode: 'class'` activates paired `dark:`
variants. Three states cycle in the toggle: system → light →
dark → system. The system default respects OS preference but
defers to an explicit user choice.

When adding a new surface, ALWAYS pair the light variant with a
`dark:` variant per the mapping table in §Components — never ship
a light-only surface. The build won't fail without `dark:`, but
the eye will: missing variants leave white cards on a slate-950
body.

### Rule 5 — Header treatment is reserved

The Phase 3a `font-semibold uppercase tracking-[0.14em] text-slate-600`
triple is for top-level section `h2`s and table `thead`s only. Micro
labels inside cards (`text-xs` `<dt>` elements, `text-[10px]`
overlines) stay at `font-medium tracking-wide text-slate-500`.

Promoting micro labels to the header treatment would over-darken
inline-with-data surfaces — the spreadsheet feel works because the
weight delta between header and data is visible.

---

## Phase roadmap

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Roboto Slab + 4-tier shadow tokens (PR #211) | ✅ merged 2026-05-22 |
| Phase 2 | Token propagation to detail page (PR #212) | ✅ merged 2026-05-22 |
| Phase 3a | Spreadsheet polish on section h2s + table theads (PR #213) | ✅ merged 2026-05-22 |
| Phase 3c | Sidebar pattern — left-rail nav + collapsible + mobile drawer (PR #215) | ✅ merged 2026-05-22 |
| Phase 3b | Dark-mode toggle — next-themes + OKLCH dark band + paired `dark:` variants | ✅ shipped this PR |
| Phase 3d | LedgerCraft canonical palette alignment — `#FAFAFA` body bg + emerald-700 brand primary + OKLCH hue 155 → 152 + border-radius normalization (rounded-2xl/xl → rounded-lg) | ✅ shipped this PR (folded into Phase 3b) |

---

## Cross-references

- **Internal enforcement** (Claude Code rules): [`.claude/skills/frontend-design-system/SKILL.md`](../.claude/skills/frontend-design-system/SKILL.md)
- **Reference template**: https://designmd.ai/chef/ledgercraft
- **Stack** (font + lib versions): [`CLAUDE.md`](../CLAUDE.md) §Stack
- **Tailwind config**: [`frontend/tailwind.config.ts`](../frontend/tailwind.config.ts)
- **OKLCH variables**: [`frontend/app/globals.css`](../frontend/app/globals.css)
