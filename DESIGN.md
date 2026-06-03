---
name: QuantRank
description: Numbers you can read like a ledger — a static US-equity ranking dashboard.
colors:
  app-bg: "#FAFAFA"
  surface: "#FFFFFF"
  surface-alt: "#F8FAFC"
  hover: "#F1F5F9"
  border: "#E2E8F0"
  ink: "#0F172A"
  ink-subdued: "#475569"
  ink-muted: "#94A3B8"
  primary: "#15803D"
  primary-hover: "#166534"
  secondary: "#64748B"
  tertiary: "#B45309"
  error: "#DC2626"
  info: "#2563EB"
  positive: "oklch(50% 0.09 155)"
  negative: "oklch(48% 0.09 18)"
typography:
  display:
    fontFamily: "Roboto Slab, ui-serif, Georgia, serif"
    fontSize: "1.875rem"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Roboto Slab, ui-serif, Georgia, serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  title:
    fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.14em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "0.875rem"
    fontWeight: 500
rounded:
  chip: "2px"
  card: "4px"
  full: "9999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "16px"
  lg: "20px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.chip}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  chip:
    backgroundColor: "{colors.surface-alt}"
    textColor: "{colors.ink-subdued}"
    rounded: "{rounded.chip}"
    padding: "2px 8px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "16px"
  table-cell:
    textColor: "{colors.ink}"
    padding: "8px 12px"
---

# Design System: QuantRank

## 1. Overview

**Creative North Star: "Numbers you can read like a ledger."**

QuantRank looks and behaves like a well-typeset financial broadsheet, not a
software dashboard. The register sits deliberately between a Bloomberg terminal
and a printed annual report: dense enough to compare hundreds of stocks at a
glance, calm enough that a careful individual investor never feels shouted at.
Surfaces are flat. Depth comes from crisp 1px borders, not drop shadows. Every
number rides a monospaced, right-aligned column so a reader can scan it the way
they'd scan a ledger. The palette is restrained to a forest-green primary, a
steel secondary, an amber warning, and a soft sage/dusty-rose semantic band —
no saturation, no alarm.

The personality is **Precise, Honest, Editorial.** Precise: exact figures,
as-of dates, tabular alignment. Honest: the product shows its own limits beside
every number — flags mark *elevated risk*, never confirmed fraud — so the visual
language must never overclaim or celebrate. Editorial: considered typography and
restraint do the work that decoration would do in a lesser tool.

This system explicitly **rejects** four aesthetics. It is not a **gamified
retail-trading app** (no confetti, no dopamine green/red, no celebratory hero
number, no "buy now" urgency). It is not a **generic SaaS-cream dashboard** (no
cream/sand/beige canvas, no icon + heading + lorem card grids, no uppercase
tracked eyebrow above every section). It is not **hype AI-marketing** (no
"supercharge/unleash/next-gen" copy, no gradient text, no decorative
glassmorphism). And it is not **Bloomberg-terminal overload** (dense is fine,
illegible is not — hierarchy must let a careful amateur navigate).

**Key Characteristics:**
- Flat surfaces; borders carry depth. No resting surface uses a shadow — the
  one live shadow in the app is the FilterDrawer overlay.
- Monospaced, right-aligned numerics in every data column (`tabular-nums`).
- One outlined-light chip pattern across the entire app — never solid-fill.
- A four-family restrained palette (forest / steel / amber / soft semantic).
- Calm by default: motion is an entrance, never a permanent flourish.
- Light and dark are first-class; every surface ships a paired `dark:` variant.

## 2. Colors

A restrained, low-saturation palette: one forest-green brand voice, a steel
neutral spine, and a soft sage/rose semantic band that signals value without
ever turning into alarm.

### Primary
- **Forest Green** (`#15803D`, emerald-700): the single brand voice. Reserved
  for the wordmark "Q" logo, the FilterDrawer "View N stocks" submit, and
  genuine positive-balance emphasis. Hover deepens to **Pine** (`#166534`,
  emerald-800). It is a CTA color, not a data color.

### Secondary
- **Steel** (`#64748B`, slate-500): secondary actions, table column headers,
  and the neutral chip body (sector / country / exchange chips). The workhorse
  that lets the data, not the chrome, own the page.

### Tertiary
- **Amber** (`#B45309`, amber-700): warnings, overdue/stale notices, and the
  high band of the manipulation index. Used sparingly, as a caution — never as
  decoration.

### Neutral
- **Canvas** (`#FAFAFA`): the body background (LedgerCraft canonical). A true
  near-white, never warm-tinted toward cream.
- **Surface** (`#FFFFFF`): cards and odd table rows. **Surface Alt** (`#F8FAFC`,
  slate-50): tile surfaces, table headers. **Hover** (`#F1F5F9`, slate-100):
  row/button hover and even table rows.
- **Border** (`#E2E8F0`, slate-200): card borders and header dividers — the
  primary depth cue.
- **Ink** (`#0F172A`, slate-900): primary text. **Ink Subdued** (`#475569`,
  slate-600): section labels. **Ink Muted** (`#94A3B8`, slate-400): captions,
  "N/A", aria-hidden glyphs.

### Semantic (the soft OKLCH band)
- **Sage** (`oklch(50% 0.09 155)`): "undervalued", positive margin-of-safety,
  positive deltas. A muted green, deliberately far from "fresh green".
- **Dusty Rose** (`oklch(48% 0.09 18)`): "overvalued", negative margin-of-safety,
  negative deltas. A muted rose, deliberately far from alarm red. OKLCH is used
  so the perceptually-uniform lightness axis prevents accidental saturation
  blowups. These soft values are applied through a `globals.css` override layer
  that remaps the Tailwind emerald/rose utility classes; the override is an
  **allowlist** (only enumerated classes are softened — `bg-rose-600` is *not*
  on it and renders raw, so a positive/negative surface must use a listed class
  or the chip family).

### Named Rules
**The Soft-Band Rule.** Positive/negative state rides the OKLCH soft band (hue
155 / hue 18, chroma ≤ 0.10). The "bright fresh green" (`text-green-500`) and
"alarm red" (`text-red-600`) intensities are forbidden for value state.

**The Tailwind-Class Rule.** Reach every color through a Tailwind utility class,
never an inline hex (`style={{ color: '#15803D' }}` is prohibited): inline hex
bypasses chip-family discipline and the `globals.css` soft-color override. The
sole carve-out is the **gauge stroke + tiny status dots** (Score / MoS donut),
which take an inline `rgb` accent on purpose — a thin 6px ring needs the
saturation, and the mid-tier amber has no soft-band token; class overrides
cannot reach an inline `stroke`/`style` anyway.

**The Four-Family Rule.** Chip and ramp surfaces use only slate / indigo / rose /
amber, plus emerald as the single recommendation-bullish exception. No other
base hues enter the system.

## 3. Typography

**Display Font:** Roboto Slab (with `ui-serif, Georgia, serif`)
**Body Font:** IBM Plex Sans (with `ui-sans-serif, system-ui, sans-serif`)
**Numeric / Mono Font:** JetBrains Mono (with `ui-monospace, monospace`)

**Character:** A slab-serif headline over a humanist-sans body reads as
"editorial finance" — the authority of a printed research note without the
stiffness of a system font. The monospaced numeric face is the load-bearing
choice: it is what makes a column of prices scan like a ledger. The root
font-size is fluid (`clamp(1rem, 0.89rem + 0.45vw, 1.125rem)`), so the whole
rem-based scale grows proportionally from phone to desktop.

### Hierarchy
- **Display** (Roboto Slab, 700, ~1.875rem/30px, line-height 1.1): the one hero
  stat — e.g. the manipulation-index number.
- **Headline** (Roboto Slab, 700, ~1.5rem/24px): page H1, large badges.
- **Title** (IBM Plex Sans, 600, ~1.125rem/18px): card titles, headline panels.
- **Body** (IBM Plex Sans, 400, ~0.875rem/14px, line-height 1.6): default body
  and table cells. Long-form prose caps at 65–75ch.
- **Label** (IBM Plex Sans, 600, ~0.75rem/12px, letter-spacing 0.14em,
  uppercase): section headers and table `thead` — the "spreadsheet column
  header" register.
- **Numeric** (JetBrains Mono, 400–600, ~0.875rem/14px): tickers, prices,
  ratios — always right-aligned with `tabular-nums`.

### Named Rules
**The Tabular-Nums Rule.** Every numeric column gets `tabular-nums` so digits
right-align across rows; without it "$3.42T" and "$19.84B" misalign by a digit
width. Non-negotiable.

**The Spreadsheet-Header Rule.** The `font-semibold uppercase tracking-[0.14em]
text-slate-600` triple is reserved for top-level section `h2`s and table
`thead`s. Micro labels inside cards stay at `font-medium tracking-wide
text-slate-500`. The weight delta between header and data is what creates the
spreadsheet feel — don't flatten it.

**The Three-Family Ceiling.** Slab display + sans body + mono numerics — three
working faces, no fourth.

## 4. Elevation

Flat by default, and more flat than most "flat" systems: depth is carried by
**1px borders**, alternating row tints, and tonal layering. After the LedgerCraft
reskin, **no resting surface uses a drop shadow** — every card, table, and the
per-stock hero is a `rounded` box with a `#E2E8F0` border and nothing else.
Shadow is reserved for one job: an element that genuinely floats *above* the
data grid.

Four shadow tiers are defined in `tailwind.config.ts` (`shadow-subtle` /
`-medium` / `-large` / `-overlay`), but only **Overlay** is currently live — on
the FilterDrawer slide-over. Subtle / Medium / Large remain a calibrated
vocabulary for a future floating surface (a popover, a sticky toast), but they
are deliberately unused on the resting page.

### Shadow Vocabulary (defined; only Overlay is in use today)
- **Overlay** (`box-shadow: 0 12px 24px -6px rgb(15 23 42 / 0.12), 0 4px 8px -4px rgb(15 23 42 / 0.06)`):
  the FilterDrawer slide-over — the one surface that sits above the grid, and the
  only shadow that renders in the shipped app.
- **Subtle / Medium / Large** (defined in `tailwind.config.ts`, currently
  unused): a graded vocabulary kept for future floating surfaces. Do not
  reintroduce them onto resting cards / tables / heroes — those are border-only.

### Named Rules
**The Borders-As-Depth Rule.** Surfaces are flat. A border, not a shadow, is the
default depth cue. Tailwind's raw `shadow-sm` / `-md` / `-lg` are forbidden;
reach only for the four formal tier names, and in practice only the Overlay tier
ever appears (above the data grid).

**The Flat-Card Rule.** A card is a 1px `#E2E8F0` border + `rounded` (4px), with
**no resting shadow**. If a card seems to need a `0 Npx` blur ≥ 16px to read as
separate, the layout is wrong, not the shadow.

## 5. Components

### Buttons
- **Shape:** sharp — 2px radius (`rounded-sm`). Never softer on a data surface.
- **Primary:** forest-green fill (`#15803D`) + white text, 8px×16px padding;
  hover deepens to `#166534`. This solid fill is the *one* place solid color is
  allowed — it is a CTA, not a chip.
- **Secondary / ghost:** steel text on a transparent or `surface-alt` ground,
  same 2px radius, no shadow.

### Chips (the canonical pattern)
- **Primitive:** the shared `Chip` component (`frontend/components/Chip.tsx`)
  owns the shell — `<Chip tone={…} size="sm" dot={…}>label</Chip>`. The
  `CHIP_BASE` / `CHIP_DOT` / `CHIP_SIZES` exports cover bespoke surfaces that
  deviate on weight/text-size (`ScoreBadge`'s numeric pill, `SectorChip`'s
  inline-rgb dot). Tone classes pass through verbatim so the `globals.css`
  soft-OKLCH allowlist still applies — never inline a hex.
- **Style:** outlined-light, always. Tinted `bg-{tone}-50` + `text-{tone}-700` +
  `ring-1 ring-inset ring-{tone}-200` + an optional `h-1.5 w-1.5 rounded-full`
  status dot (or a ↗/↘ arrow for directional values). 2px body radius; the dot
  stays fully round.
- **Used by:** sector, recommendation, score-tier, MoS, manipulation-risk,
  loss-chance, daily-price-change, and active-filter chips — one pattern across
  all of them. Numeric chips (score, price-change) carry `font-semibold
  tabular-nums`; label chips carry `font-medium`.
- **State:** selected/unselected filter chips differ by ring weight and
  background tint, never by switching to a solid fill.

### Listing chips (`ListingChips`)
- **Style:** two **neutral-steel** chips on the stock-detail hero — a country
  chip (an inline flag SVG + ISO code, e.g. US) and an exchange chip (a generic
  `Landmark` glyph + name, e.g. NASDAQ). Same body as the sector chip:
  `bg-slate-100 text-slate-600 ring-slate-200`, 2px radius, `font-medium`, paired
  `dark:`.
- **Behavior:** each chip is independently **null-safe** — it renders nothing
  until a cron populates `country` / `exchange`, so the row degrades to the bare
  `#rank` chip rather than showing an empty box.

### Attribute tiles (`HeroAttributeTiles`)
- **Style:** a 2×2 (mobile) / 1×4 (wide) grid of category tiles under the hero —
  a lucide icon over an uppercase caption over a value. Soft slate surface
  (`bg-slate-50` / `dark:bg-slate-800/40`), 1px border, 4px radius, no shadow.
  Not the reference app's black boxes (those break in light mode).
- **Reserved state:** a tile with no data yet (Dividend, Type) renders a
  **dashed** border + a dimmed icon + a "Coming soon" sub-line, so an empty tile
  reads as reserved, never broken. Info tiles, not filters.

### Cards / Containers
- **Corner Style:** 4px radius (`rounded`). Data surfaces never exceed 4px.
- **Background:** `#FFFFFF` (`dark:bg-slate-900`).
- **Shadow Strategy:** none at rest. Depth is the 1px border, not a shadow (see
  Elevation — even the per-stock hero, once the documented `shadow-large`
  exception, is now border-only).
- **Border:** 1px `#E2E8F0` (`dark:border-slate-800`).
- **Internal Padding:** 16px (`p-4`) resting; 20px (`p-5`) for hero / chart panels.

### Inputs / Fields
- **Style:** 1px border, `surface` background, 2px radius, **no shadow**.
- **Focus:** border shift to the brand/steel ring; no glow.

### Navigation
- **Style:** a left-rail sidebar (240px expanded / 64px collapsed icon rail),
  `md:sticky md:top-0 md:h-screen`. Slate-only — no accent color — so the data
  surfaces own the palette. Active route swaps to `bg-slate-100 font-medium
  text-slate-900`. Mobile collapses to a hamburger-triggered drawer with a
  `bg-slate-900/40` backdrop. Collapse state persists in `localStorage` and is
  pre-painted before hydration so the rail never flashes width on refresh.

### Icons
- **Library:** `lucide-react`, **named imports only** (`import { Landmark } from
  'lucide-react'`) — never `import * as Icons` (that pulls the 224 KB barrel and
  defeats tree-shaking). Flags via `country-flag-icons`, per-country subpath
  import (`country-flag-icons/react/3x2/US`), same discipline.
- **Weight:** `strokeWidth={1.75}` on tile/chrome icons — a hair lighter than the
  1px-border chrome so the icon reads as content, not structure.

### Signature Component: the Score / MoS gauges
- The composite-score radial gauge sweeps 0→value with a synchronized count-up
  over 800ms (`ease-in-out`) on every visit to a stock — the app's one longer
  "signature" beat. The Margin-of-Safety donut shares that motion but is
  **sign-aware**: MoS ≥ 0 sweeps clockwise (sage), MoS < 0 runs counter-clockwise
  (rose, mirrored via `-scale-x-100` with the number un-mirrored to stay
  readable). Everything else stays inside a ≤ 320ms micro-entrance budget and
  plays once per mount, never loops. The arc renders at its final value at SSR /
  under reduced motion (the sweep is enhancement, never a visibility gate).

## 6. Do's and Don'ts

### Do:
- **Do** reach colors through Tailwind utility classes (`bg-emerald-50
  text-emerald-700 ring-emerald-200`), never an inline hex (the gauge stroke +
  status dots are the one documented inline-`rgb` carve-out).
- **Do** put `tabular-nums` on every numeric column so digits right-align.
- **Do** use the one outlined-light chip pattern (tinted bg + ring + dot/arrow)
  for every chip family — including directional values like daily price change.
- **Do** ship a paired `dark:` variant on every surface; never a light-only card.
- **Do** keep radii ≤ 4px on data surfaces (2px chips/buttons, 4px cards) and
  reserve `rounded-full` for status dots.
- **Do** import icons by name (lucide) and flags per-country (country-flag-icons)
  — never a barrel or `import *`; the tree-shake depends on it.
- **Do** give every animation a `prefers-reduced-motion: reduce` static-end-state
  off-switch, and render real values at SSR (count-up is enhancement, never a gate).
- **Do** let borders carry depth; reserve shadow for the FilterDrawer-class overlay.

### Don't:
- **Don't** build a **gamified retail-trading** feel — no confetti, no dopamine
  green/red, no celebratory big-number hero, no "buy now" urgency.
- **Don't** drift toward a **generic SaaS-cream dashboard** — no cream/sand/beige
  canvas (the body is `#FAFAFA`, not warm-tinted), no icon + heading + lorem card
  grids, no tiny uppercase tracked eyebrow above every section.
- **Don't** write **hype AI-marketing** — no "supercharge / unleash /
  next-generation / seamless", no `background-clip: text` gradient text, no
  decorative glassmorphism.
- **Don't** ship **Bloomberg-terminal overload** — dense is fine, an
  undifferentiated wall of numbers a non-professional can't parse is not.
- **Don't** use `bg-emerald-600 text-white` (or any solid fill) for a chip — the
  solid-fill chip was retired; chips are outlined-light only. The one solid-fill
  exception is the primary CTA button.
- **Don't** use `text-green-500` / `text-red-600` for value state, or reach for an
  un-allowlisted shade like `bg-rose-600` expecting it to soften — use the OKLCH
  sage/rose soft band (a listed class or the chip family).
- **Don't** add `shadow-medium` / `-large` (or any resting shadow) to a card,
  table, or the hero — they are border-only; shadow is for the FilterDrawer-class
  overlay only.
- **Don't** exceed a 4px radius on cards/inputs or pick `rounded-2xl`/`32px`+ on a
  data surface, and don't use a colored `border-left`/`border-right` > 1px as a
  stripe accent.
