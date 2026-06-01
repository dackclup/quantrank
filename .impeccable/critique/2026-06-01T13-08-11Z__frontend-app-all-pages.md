---
target: frontend/app (all pages)
total_score: 27
p0_count: 0
p1_count: 3
timestamp: 2026-06-01T13-08-11Z
slug: frontend-app-all-pages
---
# QuantRank — Re-critique (all pages, post-#355)

Combined `$impeccable critique` re-run after the #355 a11y + clarity punch-down. Two independent, unanchored assessments — **A** (design-director, source review) + **B** (real-browser persona pass: build + serve `out/`, headless Chromium, both themes, mobile 390px + desktop 1280px, on-screen-vs-JSON cross-check) — plus the bundled detector. Scope: `/` (rankings) + `/stock/[ticker]` (detail) + states. Baseline to delta against: prior run **27/40 Nielsen + 16/20 audit** (2026-06-01T11-26-29Z).

## Headline delta

The #355 **P1 blockers are CLOSED and confirmed in a real browser**: FilterDrawer now traps focus (15 Tab presses, 0 escapes, Shift+Tab reverse-traps, Esc restores focus to the trigger) and the systemic sub-44px touch targets are fixed on **every primary control** (Filters / search / pagination / period selector / back-link / theme toggle / sidebar nav all measure 44px). Data integrity is perfect: **21/21 on-screen values matched the raw JSON**, **0 real console errors** across 5 routes, 0 horizontal overflow 320→1280px, reduced-motion fully suppresses the gauge/stagger.

The score **plateaus at 27/40** because Nielsen's ceiling here is set by information-architecture + help + power-user flexibility — none of which an a11y pass touches. What remains: one structural **P1** (detail-page hierarchy), two **residual a11y gaps the #355 sweep didn't reach** (in-drawer filter chips + the mobile "more" button), and one **newly-surfaced dark-mode contrast item that needs a focused re-measure** before any token change.

## Design Health Score (Nielsen, /40)

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Price chart has no skeleton during async fetch — blank `h-64` box for 500ms+ on cold edge (it's the 2nd section, first scroll target) |
| 2 | Match System / Real World | 3 | "Margin of safety / pillar / rank gate / manipulation index" are unexplained domain terms; the plain-English fair-price narrative is a good compensator |
| 3 | User Control & Freedom | 3 | Focus-trap + Esc + back-nav state-restore confirmed working; no undo on Clear-all, no shareable filter URL |
| 4 | Consistency & Standards | 4 | Standout — 5 chip families, one anatomy token, uniform headers, full dark parity, `tabular-nums` throughout (confirmed in browser) |
| 5 | Error Prevention | 2 | Clear-all fires with one tap, no confirm/undo; score range can drag to 0–0 → silently empty table; "View 0 stocks" still closes |
| 6 | Recognition Rather Than Recall | 3 | MoS donut center silently clamps to `<−99` / `>+99`; raw manipulation-index number has no 0–100 scale anchor |
| 7 | Flexibility & Efficiency | 2 | No URL-encoded filter state (can't bookmark/share a screen), no keyboard shortcuts, fixed 50/page |
| 8 | Aesthetic & Minimalist | 3 | Detail page = 11 same-weight sections; the decision cluster and the audit appendix read at identical hierarchy |
| 9 | Error Recovery | 2 | `FairPriceBarChart` returns `null` (heading vanishes); chart "Failed to load" is bare text in a white box, no retry |
| 10 | Help & Documentation | 2 | No inline "what is this?" on Composite Score / MoS / Loss Chance / pillars; definitions live in bottom-of-card footnotes |
| **Total** | | **27/40** | **Acceptable (top of band) — solid foundation; the ceiling is IA + help + flexibility, not a11y** |

## Technical / audit delta (/20, from B's real-browser evidence)

| # | Dimension | Score | Movement since prior |
|---|-----------|-------|----------------------|
| 1 | Accessibility | 3 | Focus-trap P1 **resolved** ✓ · primary touch targets **resolved** ✓ · residual: in-drawer chips 24px, "more" 36×24, 2 ARIA gaps (Loss-Chance `aria-sort`, 1D/5D `aria-disabled`), dark-contrast flag |
| 2 | Performance | 4 | Unchanged — 0 console errors, no jank on sort/theme/filter, no overflow |
| 3 | Responsive | 3 | Big sub-44px sweep fixed; holdout = FilterDrawer chips at 24px on 390px |
| 4 | Theming | 3 | Prior pink-salmon false-positive confirmed non-issue; **new** dark secondary-text contrast flag (see P1 below — needs re-measure) |
| 5 | Anti-Patterns | 3 | Detector 5/5 false positives; cautions hold: flat eyebrow hierarchy, intentional placeholder tiles |
| **Total** | | **16/20** | Composition shifted (focus-trap win offset by the dark-contrast flag); headline flat |

## Anti-Patterns Verdict — does it look AI-made?

**Largely no.** The chip-family discipline, the OKLCH soft-override palette, the sign-aware MoS gauge, the pre-paint sidebar, and the plain-English fair-price verdict are opinionated engineering decisions a template doesn't produce. The one real tell is **section-header homogeneity on the detail page**: 11 consecutive sections share the identical `uppercase tracking-[0.14em] text-slate-600` eyebrow, so a fired risk-veto card carries the same visual weight as the raw-data appendix. #355's `headingTone` rose/amber tinting helps but keeps the same size/weight/case, so the tonal shift lands too softly to re-rank the hierarchy.

**Detector:** 5 findings, **all false positives** — em-dashes (110/8/5) are in CSS + TSX *comments*; "numbered markers 03–08" matched the `.stagger-3…8` animation-delay utilities; "flat hierarchy 12/14/16px" is `RecommendationBadge`'s sm/md/lg size *props* (and 1.3:1 actually clears the ≥1.25 bar). No real tells from the deterministic scan.

**Visual overlays:** none injected — Assessment B drove its own persona browser; the impeccable `detect.js` overlay path was not used this run (browser evidence came from the persona missions + measured assertions instead).

## What's Working

- **Chip-family discipline + OKLCH soft-override** — consistency scored 4/4 in both assessments; the single strongest differentiator from a generic dashboard. `RECOMMENDATION_CHIP_TONES` shared across the badge and drawer surfaces; no "seven slightly different pills" drift.
- **The gauge + count-up hero is a genuine signature moment** — two same-family donuts, sign-aware CCW-for-negative MoS, 800ms ease-in-out sweep + count-up, reduced-motion fallback, SSR-safe. NVDA vs CF get visibly different arc lengths/colors before the number finishes.
- **Data integrity + defensive rendering** — B's cross-check passed **21/21** (composite, price, fair-price median, MoS, loss-chance, recommendation mapping, risk_flags) against raw JSON, 0 console errors across 5 routes, clean stocks correctly null-collapse their warning sections.

## Priority Issues

**[P1] Detail page has no hierarchy between the "decision" cluster and the "reference/audit" cluster** (`app/stock/[ticker]/page.tsx`). 11 card-sections render at identical visual weight; `RiskSummaryCard` (a critical signal) has the same chrome as `RawMetricsTable` (a data appendix). A's cognitive-load checklist FAILs 5/8 here (single-focus, grouping, hierarchy, working-memory, progressive-disclosure). *(A rated this P0; reclassified P1 — B's screener still completed the mission, so it's major-friction, not blocking.)* **Fix:** insert one visual zone-break before the audit cluster (raw metrics + data quality + disclaimer) with a non-eyebrow `<h2>` ("Supporting data") + rule; optionally collapse Zone 2 on mobile. → `$impeccable distill` (then `layout`)

**[P1] Mobile FilterDrawer chips are 24px tall — 23 of 26 below the 44px target** (`FilterDrawer.tsx`). #355 fixed the drawer's buttons/search but not the score-tier / recommendation / sector selection chips themselves. B measured 24×24 on a 390px viewport. WCAG 2.5.8. **Fix:** `min-h-[44px] items-center` on the chip wrapper (or `py-2.5`). → `$impeccable adapt`

**[P1 — VERIFY FIRST] Dark-mode secondary-text contrast** (B flagged MAJOR; needs re-measure before fixing). B reports ~4.2:1 on ~40 dark-mode secondary labels (pillar descriptions, "Coming soon" tiles, section eyebrows) and names the token `slate-400`. **Caveat (synthesis):** `slate-400` on `slate-900`/`slate-800` actually computes to ~5.7–7:1 (passes); a genuine ~3.1–3.8:1 fail would be `slate-500` on a dark surface — so B's reported token + ratio are internally inconsistent. The finding is *plausible* but the exact failing element/token is unconfirmed. **Fix:** a scoped audit that measures the specific failing nodes, then bump only those (likely `dark:text-slate-500` → `dark:text-slate-400`/`-300` on small labels). → `$impeccable audit` (verify) → `$impeccable colorize` (fix)

**[P2] No chart skeleton during async price fetch** (`PriceHistoryChart.tsx`). `loading` state exists but renders a blank `h-64` box, no shimmer/spinner. The `shimmer` keyframe already exists in `globals.css`. **Fix:** render `<div className="h-64 animate-shimmer rounded border …">` while `loading`. → `$impeccable harden`

**[P2] Filter state is not URL-serialized** (`RankingTable.tsx`). sessionStorage survives back-nav but not tab-close or sharing; a power user can't bookmark "Financials + Strong + Lean Bullish." **Fix:** mirror active filters into `useSearchParams` (client-side only, static-export safe); prefer URL over sessionStorage on mount. → `$impeccable harden`

**[P3] Loss-chance band/rounding boundary** (`RankingTable.tsx` / `LossChanceBadge.tsx`). The label displays `Math.round(pct)` but the band/color is computed from the raw `pct`, so a 59.x value shows "**60% · Neutral**" (60 reads as the start of Moderate-high). *Not re-hit this pass — B's 3 tickers (NVDA 55 / EIX 32 / CF 26) weren't at a boundary; carried from last session's screenshot of MNST.* **Fix:** derive the band from the same rounded integer used for display. → `$impeccable clarify` (+ a 1-line code change)

**[P3] Small ARIA + target nits** (B, measured): Loss-Chance `<th>` has `aria-sort=null` (should be `"none"` like Score); 1D/5D period buttons lack `aria-disabled="true"`; the mobile "more" disclaimer button is 36×24px; the default-sorted Score header reads `aria-sort="none"` on load though rows are already sorted. → `$impeccable harden`

## Persona Red Flags

- **Alex (power user / analyst):** no shareable filter URL (sessionStorage dies on tab-close); the Card-A-vs-Card-B MoS-formula caveat is buried at the bottom of Card B, not next to the two diverging figures; manipulation-index number has no visual 0–100 scale.
- **Sam (keyboard / SR):** *wins* — focus-trap confirmed, table headers keyboard-operable, price-chart `sr-only` summary present. *Gaps* — `FairPriceBarChart` per-method verdict badges have no `aria-label` tying verdict→method; Loss-Chance column not announced as sortable; 1D/5D not announced as disabled.
- **Casey (mobile):** *wins* — hero is thumb-friendly, back-nav preserves filter state, no overflow. *Friction* — 24px FilterDrawer chips; `RawMetricsTable` is always fully expanded (~616px of balance-sheet on a clean stock the user didn't come to read); the back-link's only tap feedback is `hover:opacity-70` (invisible on touch).

## Minor Observations

- `formatLargeNumber` is shared across share-count and currency contexts — "1.50K" reads fine for shares, ambiguous for `market_cap` ($1.5K vs $1,500).
- `PillarRadarChart` bar fills + legend use raw `rgb()` (alarm-red `rgb(225 29 72)` for "Poor") that bypass the OKLCH soft-override — documented-by-design, but visibly more saturated than the chips directly above them.
- Desktop ranking table omits a MoS column (only in mobile cards) — arguably the 2nd-most-important screening signal lives one click away on desktop.
- `FairPriceCard` uses `<dl>` with each `<dt>`/`<dd>` wrapped in its own `<div>` — visually fine, semantically loose pairing.
- The "Risk" pillar bar renders green when high (= low risk); the label + color convention can read backwards ("Risk: 75" + green) — consider "Risk resilience" / "Safety".

## Questions to Consider

- Is the stock-detail page a *reading* experience or a *decision* experience? The audit appendix (raw metrics + data quality) sits in the same scroll plane as the decision signals.
- Should the Composite Score carry a persistent "what is this?" affordance, given it's the product's primary differentiator and its only definition lives in a footnote?
- Do Card A + Card B need to be two separate cards, or could the formula caveat become a tooltip on Card B's MoS figure, collapsing both into one?
