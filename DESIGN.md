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
- Flat surfaces; borders carry depth, shadows are reserved for overlays.
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
  and the neutral chip body. The workhorse that lets the data, not the chrome,
  own the page.

### Tertiary
- **Amber** (`#B45309`, amber-700): warnings, overdue/stale notices, and the
  high band of the manipulation index. Used sparingly, as a caution — never as
  decoration.

### Neutral
- **Canvas** (`#FAFAFA`): the body background (LedgerCraft canonical). A true
  near-white, never warm-tinted toward cream.
- **Surface** (`#FFFFFF`): cards and odd table rows. **Surface Alt** (`#F8FAFC`,
  slate-50): even table rows. **Hover** (`#F1F5F9`, slate-100): row/button hover.
- **Border** (`#E2E8F0`, slate-200): card borders and header dividers — the
  primary depth cue.
- **Ink** (`#0F172A`, slate-900): primary text. **Ink Subdued** (`#475569`,
  slate-600): section labels. **Ink Muted** (`#94A3B8`, slate-400): captions,
  "N/A", aria-hidden glyphs.

### Semantic (the soft OKLCH band)
- **Sage** (`oklch(50% 0.09 155)`): "undervalued", positive margin-of-safety,
  positive deltas. A muted green, deliberately far from "fresh green".
- **Dusty Rose** (`oklch(48% 0.09 18)`): "overvalued", negative margin-of-safety.
  A muted rose, deliberately far from alarm red. OKLCH is used so the
  perceptually-uniform lightness axis prevents accidental saturation blowups.

### Named Rules
**The Soft-Band Rule.** Positive/negative state rides the OKLCH soft band (hue
155 / hue 18, chroma ≤ 0.10). The "bright fresh green" (`text-green-500`) and
"alarm red" (`text-red-600`) intensities are forbidden for value state.

**The Tailwind-Class Rule.** Reach every color through a Tailwind utility class,
never an inline hex (`style={{ color: '#15803D' }}` is prohibited). Inline hex
bypasses chip-family discipline and is invisible to the purge.

**The Four-Family Rule.** Chip and ramp surfaces use only slate / indigo / rose /
amber, plus emerald as the single recommendation-bullish exception. No other
base hues enter the system.

## 3. Typography

**Display Font:** Roboto Slab (with `ui-serif, Georgia, serif`)
**Body Font:** IBM Plex Sans (with `ui-sans-serif, system-ui, sans-serif`)
**Numeric / Mono Font:** JetBrains Mono (with `ui-monospace, monospace`)
**Editorial accent:** Instrument Serif — marquee headlines only, used sparingly.

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

**The Three-Family Ceiling.** Slab display + sans body + mono numerics. Instrument
Serif is a rare editorial accent, not a fourth working face.

## 4. Elevation

Flat by default. Depth is carried by **1px borders**, alternating row tints, and
tonal layering — not by shadow. Shadows are a response to *layering above the
data grid*, never a resting decoration. Four formal tiers exist, calibrated for
slate-on-white with gentle vertical depth.

### Shadow Vocabulary
- **Subtle** (`box-shadow: 0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 1px -1px rgb(15 23 42 / 0.02)`):
  table-row hover, badge surface, the method-list `<ul>`.
- **Medium** (`box-shadow: 0 1px 3px 0 rgb(15 23 42 / 0.06), 0 1px 2px -1px rgb(15 23 42 / 0.04)`):
  card resting state — RankingTable, PillarRadarChart, RawMetricsTable.
- **Large** (`box-shadow: 0 4px 8px -2px rgb(15 23 42 / 0.08), 0 2px 4px -2px rgb(15 23 42 / 0.04)`):
  section emphasis — the per-stock hero card only.
- **Overlay** (`box-shadow: 0 12px 24px -6px rgb(15 23 42 / 0.12), 0 4px 8px -4px rgb(15 23 42 / 0.06)`):
  modal / drawer / popover — the FilterDrawer.

### Named Rules
**The Borders-As-Depth Rule.** Surfaces are flat. A border, not a shadow, is the
default depth cue. Tailwind's `shadow-sm` / `shadow-md` / `shadow-lg` are
forbidden — reach only for the four formal tier names, and only the Overlay tier
appears above the data grid.

**The Flat-Card Rule.** A card is a 1px `#E2E8F0` border + `shadow-medium`, never
a heavy drop shadow. If a card needs a `0 Npx` shadow with blur ≥ 16px to read
as separate, the layout is wrong, not the shadow.

## 5. Components

### Buttons
- **Shape:** sharp — 2px radius (`rounded-sm`). Never softer on a data surface.
- **Primary:** forest-green fill (`#15803D`) + white text, 8px×16px padding;
  hover deepens to `#166534`. This solid fill is the *one* place solid color is
  allowed — it is a CTA, not a chip.
- **Secondary / ghost:** steel text on a transparent or `surface-alt` ground,
  same 2px radius, no shadow.

### Chips (the canonical pattern)
- **Style:** outlined-light, always. Tinted `bg-{tone}-50` + `text-{tone}-700` +
  `ring-1 ring-inset ring-{tone}-200` + an optional `h-1.5 w-1.5 rounded-full`
  status dot. 2px body radius; the dot stays fully round.
- **Used by:** sector, recommendation, score-tier, MoS, manipulation-risk, and
  active-filter chips — one pattern across all of them. The sector chip body is
  neutral steel; only its dot carries sector identity.
- **State:** selected/unselected filter chips differ by ring weight and
  background tint, never by switching to a solid fill.

### Cards / Containers
- **Corner Style:** 4px radius (`rounded`). Data surfaces never exceed 4px.
- **Background:** `#FFFFFF` (`dark:bg-slate-900`).
- **Shadow Strategy:** `shadow-medium` at rest; the per-stock hero card is the
  single `shadow-large` exception.
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
  `bg-slate-900/40` backdrop. Collapse state persists in `localStorage`.

### Signature Component: the Score / MoS gauges
- The composite-score radial gauge sweeps 0→value with a synchronized count-up
  over 800ms on every visit to a stock — the app's one longer "signature" beat.
  The Margin-of-Safety donut shares that motion but is **sign-aware**: MoS ≥ 0
  sweeps clockwise (emerald), MoS < 0 runs counter-clockwise (rose). Everything
  else stays inside a ≤ 320ms micro-entrance budget and plays once per mount,
  never loops.

## 6. Do's and Don'ts

### Do:
- **Do** reach colors through Tailwind utility classes (`bg-emerald-50
  text-emerald-700 ring-emerald-200`), never an inline hex.
- **Do** put `tabular-nums` on every numeric column so digits right-align.
- **Do** use the one outlined-light chip pattern (tinted bg + ring + dot) for
  every chip family.
- **Do** ship a paired `dark:` variant on every surface; never a light-only card.
- **Do** keep radii ≤ 4px on data surfaces (2px chips/buttons, 4px cards) and
  reserve `rounded-full` for status dots.
- **Do** give every animation a `prefers-reduced-motion: reduce` static-end-state
  off-switch, and render real values at SSR (count-up is enhancement, never a gate).
- **Do** let borders carry depth; reserve shadow for overlays.

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
- **Don't** use `text-green-500` / `text-red-600` for value state — those ramps
  are too saturated; use the OKLCH sage/rose soft band.
- **Don't** exceed a 4px radius on cards/inputs or pick `rounded-2xl`/`32px`+ on a
  data surface.
- **Don't** use a colored `border-left`/`border-right` > 1px as a stripe accent.
