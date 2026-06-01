# Product

## Register

product

## Users

Self-directed individual investors doing **value + quality screening** of the
S&P 500 — people who want to answer "is this name fairly valued, and what are
the red flags?" before doing deeper diligence. They are skeptical by
disposition: they read methodology, they weight model output against its stated
error rates, and they distrust a black-box "buy/sell" verdict. A second audience
is **students and researchers** learning quantitative equity analysis from a
transparent, reproducible reference.

Context of use: research and diligence on a laptop or phone, **never live
trading** — the product connects to no brokerage and never will. The primary
task on any screen is *understanding*, not transacting: read a stock's
composite rank, see the fair-price spread, and weigh the risk/defense flags.

## Product Purpose

QuantRank is a static, daily-refreshed US-equity ranking tool. A Python pipeline
combines fundamental, valuation, factor, and academic fraud/earnings-manipulation
signals into a single **0–100 composite StockRank**, a **6-method fair-price
ensemble**, and a **defense layer** of literature-anchored risk flags; a Next.js
static site renders the pre-computed JSON.

It exists to make academic-quality screening **legible to a careful individual**
— a "look harder here" risk-stratifier, explicitly **not** investment advice and
**not** a fraud guarantor (flags mark elevated risk, never confirmed fraud).
Success is when a user can see *why* a stock ranks where it does (which pillars,
which valuation methods, which flags fired) and *trust* the number because every
score ties to a git commit and a cited academic prior.

## Brand Personality

**Precise · Honest · Editorial.**

- **Precise** — tabular discipline; every numeric column right-aligns; exact
  figures and as-of dates over vibes. Comparability is a feature.
- **Honest** — the product leads with its own limits (irreducible false-positive
  / false-negative rates, frauds it structurally cannot catch, post-publication
  anomaly decay). The voice never overclaims: "elevated risk", never "fraud".
  Uncertainty sits *next to* the number, not in a footnote nobody reads.
- **Editorial** — reads like a well-typeset annual report or a financial
  broadsheet: considered type, restraint, hierarchy that guides the eye rather
  than shouts. The register sits between a Bloomberg terminal and a printed
  research note — minus the overload.

## Anti-references

What QuantRank must **not** look or feel like:

- **Gamified retail-trading apps** (Robinhood-style) — no confetti, no
  dopamine green/red, no celebratory big-number hero, no "buy now" urgency. The
  tool informs diligence; it must never nudge a trade.
- **Generic SaaS-cream dashboards** (the 2026 AI default) — no cream/sand/beige
  body canvas, no endless icon + heading + lorem card grids, no tiny uppercase
  tracked eyebrow above every section.
- **Hype AI-marketing** — no "supercharge / unleash / next-generation /
  seamless" buzzwords, no gradient text, no decorative glassmorphism. Specific
  noun + verb over slogan.
- **Bloomberg-terminal overload** — dense is fine, *illegible* is not. Never a
  wall of undifferentiated numbers that only a professional can parse; hierarchy
  must let a careful amateur navigate.

## Design Principles

1. **Honest by construction.** Show the limit next to the number. Every score
   travels with its uncertainty, its defense flags, and a methodology link.
   Never render a model output as a verdict.
2. **Legible like a ledger.** A reader should scan a column of figures and trust
   the alignment. Clarity and comparability beat decoration every time.
3. **Show the why.** The rank is explainable — pillars, fair-price methods, and
   risk flags are all surfaced, never hidden behind a single opaque score.
4. **Calm, never urgent.** This is a research surface, not a trading floor. No
   pressure, no celebration; the design earns trust by staying quiet.
5. **Reproducible & transparent.** Every number ties to a git commit and a cited
   academic prior; the UI carries that provenance (data-as-of dates, methodology
   links, the standing educational-only disclaimer).

## Accessibility & Inclusion

Target: **WCAG 2.1 AA.**

- Body text ≥ 4.5:1, large text ≥ 3:1 contrast — in **both** light and dark mode
  (the dark-surface fix on hero metrics is the standing precedent).
- `prefers-reduced-motion: reduce` is **mandatory** — every entrance/motion token
  has a static-end-state off-switch; verify under reduced-motion.
- Class-strategy dark mode (`next-themes`) with a paired `dark:` variant on every
  surface — never ship a light-only surface.
- State is never color-only: the outlined-light chip pattern always carries a
  dot/label alongside the sage/rose hue, so red/green-deficient users still parse
  positive vs negative.
- Mobile-first touch targets; `tabular-nums` on every numeric column for legible,
  right-aligned figures.
