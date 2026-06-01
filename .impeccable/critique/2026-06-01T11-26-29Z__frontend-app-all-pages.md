---
target: frontend/app (all pages)
total_score: 27
p0_count: 0
p1_count: 2
timestamp: 2026-06-01T11-26-29Z
slug: frontend-app-all-pages
---
# QuantRank — Audit + Critique (all pages)

Combined `$impeccable audit` (technical /20) + `$impeccable critique` (Nielsen /40), synthesized from two independent assessments — A (design-director review) + B (real-browser persona pass, both themes, mobile+desktop) — plus the bundled detector. Scope: `/` (rankings) and `/stock/[ticker]` (detail) + their states.

## Design Health Score (Nielsen, /40)

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | No "data as-of" date on the detail hero; compute-pending box has no ETA/retry |
| 2 | Match System / Real World | 3 | `sm` score pill shows "64.0" with no tier word; "Rank gates" is jargon |
| 3 | User Control & Freedom | 3 | No undo on clear-filters; no breadcrumb for deep-linked detail arrivals |
| 4 | Consistency & Standards | 4 | Standout — one chip grammar across 5 families, uniform headers, full dark parity |
| 5 | Error Prevention | 2 | Score range can drag to 0–0 → silently empty table; "View 0 stocks" still closes |
| 6 | Recognition Rather Than Recall | 3 | `[flag]` schema keys shown with no tooltip |
| 7 | Flexibility & Efficiency | 2 | No URL-encoded filter state (can't share a view), no keyboard shortcuts, fixed 50/page |
| 8 | Aesthetic & Minimalist | 3 | Two "Coming soon" placeholder tiles occupy 50% of the hero attribute grid |
| 9 | Error Recovery | 2 | `FairPriceBarChart` returns null with no fallback label (silent section gap) |
| 10 | Help & Documentation | 2 | No inline "what is this?" on Composite Score / MoS / Loss Chance; help lives off-app |
| **Total** | | **27/40** | **Good — solid foundation, address the weak dimensions (5, 7, 9, 10)** |

## Audit Health Score (technical, /20)

| # | Dimension | Score | Key finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 3 | Strong contrast + semantics + ARIA; gaps: FilterDrawer focus-trap, sub-44px touch targets, 2 missing aria-labels, chart has no SR summary |
| 2 | Performance | 4 | FCP 308ms, CLS 0.059 (Good), 0 console errors, no jank on sort/theme/filter |
| 3 | Responsive | 3 | No overflow 320–1280, container-query hero works; sub-44px touch targets + filter drawer 256px on a 390px viewport |
| 4 | Theming | 3 | Excellent OKLCH token system + full dark parity; `dark:text-red-300` not in the soft-override allowlist (loss-chance high band renders raw pink-salmon in dark); latent `bg-rose-600` gap |
| 5 | Anti-Patterns | 3 | No gradient/glass/over-round/numbered-markers; cautions: placeholder tiles in prod, eyebrow-on-every-section flat hierarchy, the `w-1` verdict side-stripe on FairPriceBarChart |
| **Total** | | **16/20** | **Good — address the weak dimensions** |

## Anti-Patterns Verdict — does it look AI-made?

**Largely no.** The chip-family discipline, the OKLCH soft-override palette, the sign-aware MoS gauge, the pre-paint sidebar, and the "plain-English fair-price verdict" are all opinionated, engineering-derived decisions an AI template doesn't produce. Two cautions: (1) the **two "Coming soon" placeholder tiles** that render on every detail page read as "work in progress" (NOTE: this was a *deliberate* user decision in PR #344 — reserved tiles, not an accident); (2) **eyebrow-on-every-section** — the `uppercase tracking-[0.14em]` h2 treatment on 8+ detail-page sections flattens hierarchy so a fired risk-veto card weighs the same as the raw-data table.

**Detector:** 5 findings, **all false positives** on inspection — the em-dashes (110/8/5) are in CSS/JS *comments*, not user copy; "flat type hierarchy" is one badge's size *props* (12/14/16px); "numbered markers 03-08" matched the `.stagger-3…8` animation-delay utilities. No real AI tells from the deterministic scan.

## What's Working
- **Chip-family discipline + OKLCH soft-override** — the single strongest differentiator from a generic dashboard; consistency scored 4/4.
- **Motion system** — one `ease-in-out` curve, the keyframe gauge-sweep, sign-aware MoS, stagger-with-interaction-latch, full reduced-motion coverage.
- **Defensive rendering** — uniform `== null` + graceful em-dash/empty fallbacks; B logged 0 console errors across 30 phases and every displayed value matched the JSON.

## Priority Issues

**[P1] FilterDrawer doesn't trap focus** (`FilterDrawer.tsx`). Both A + B agree: Esc works + body-scroll is locked, but Tab escapes the open modal to the page behind the backdrop (B's "two search inputs in the tab order" was the symptom). WCAG 2.4.3. Fix: trap focus to the `<aside>` on open, restore to the trigger on close. → `$impeccable harden`

**[P1] Mobile touch targets systemically < 44px** (`Sidebar` nav 32px · `Filters` button 38px · `PriceTimePeriodSelector` 24px-tall · score sliders 20px · search 38px). B measured 16/17 interactive elements below 44px at 390px; the 20–24px ones are borderline on WCAG 2.2 SC 2.5.8 (24px AA) and miss PRODUCT.md's "mobile-first touch targets" goal. → `$impeccable adapt`

**[P2] Two different MoS percentages on one detail page, unlabeled** — `FairPriceBarChart` "−X% vs today" = `(median−price)/price`; `FairPriceCard` "Margin of safety" = `(median−price)/median`. NVDA shows −64% vs −172% with no label saying they use different anchors (documented-intentional, but reads as a contradiction). Fix: label each ("vs market price" / "vs fair value"). → `$impeccable clarify`

**[P2] Flat hierarchy on the dense stock-detail page** — 8+ sections share one eyebrow header treatment, so warning cards (Tier2 / RiskSummary) don't outweigh the raw-data table. A's cognitive-load FAILs cluster here (single-focus, hierarchy, one-thing-at-a-time, working-memory all fail on detail). Fix: give the active warning-group headings the rose tone the card ring already uses. → `$impeccable layout`

**[P2] "Coming soon" placeholder tiles render in production** (`HeroAttributeTiles.tsx`) — they take 50% of the hero grid and signal incompleteness. **This was an explicit user choice (PR #344); confirm intent** — keep as reserved, or hide until Dividend/Type data lands (`grid-cols-2` with only filled tiles). → `$impeccable distill`

**[P3] Price chart inaccessible to screen readers** — `PriceHistoryChart` Recharts SVG has no `aria-label` / SR summary. Add `aria-label="Price history for <T>"` + an sr-only "5y range $lo–$hi, latest $close". → `$impeccable harden`

**[P3] Missing ARIA + small a11y polish** — period buttons need `aria-pressed`; score sliders need `aria-label` (min/max); `Disclaimer` should be `role="note"` not `role="alert"` (it's persistent) + the "more" toggle needs `aria-expanded` + an aria-label.

**[P3] Dark-mode loss-chance high band renders raw pink-salmon** — `dark:text-red-300` isn't in the `globals.css` soft-override allowlist, so the ≥60% loss-chance value skips the terracotta token in dark mode. → `$impeccable colorize`

## Persona Red Flags
- **Sam (keyboard / SR):** FilterDrawer focus escape; price chart is silent to a screen reader; period selector + score sliders unnamed. (Resolved non-issues: loss-chance band *is* in the badge aria-label; StockLogo is correctly `alt="" aria-hidden`.)
- **Casey (mobile):** sub-44px targets across nav/filters/period/sliders; filter drawer 256px on a 390px screen feels cramped. (Good: back-nav preserves filter/search state.)
- **Alex (power user):** no shareable filter URL, no keyboard shortcuts, fixed 50/page; first click on the already-descending Score header has no visible effect.
- **Riley (edge):** clean — empty state clear, long names truncate, MoS `<−99` clamp correct, refresh/back-nav preserve state.

## Minor Observations
- `FairPriceCard` uses `<dl>` with each `<dt>`/`<dd>` wrapped in its own `<div>` — visually fine, semantically malformed dl pairing.
- `FilterDrawer` close "×" is missing `type="button"` (every other button has it).
- Sort: clicking the already-default-sorted (Score desc) header gives no visible feedback on the first click.
- Build `out/` is 145MB on disk (502 stock JSONs dominate) — fine gzipped on the CDN; route JS chunk ~389KB is Recharts.
- Doc note (not UI): data is schema `0.10.12-phase4.6` while CLAUDE.md §Phase status still reads `0.10.11` — doc drift, JSON is authoritative.

## Questions to Consider
- Is the stock-detail page a *reading* experience or a *decision* experience? A clean stock still scrolls past where the (collapsed) warning cards would be.
- Should the Composite Score carry a persistent "what is this?" affordance, given it's the product's primary differentiator and its only definition lives in a footnote?
- When non-US stocks/ADRs enter, does the rank-row metadata (country + exchange + future security-type chips) have a deliberate crowded-state layout?
