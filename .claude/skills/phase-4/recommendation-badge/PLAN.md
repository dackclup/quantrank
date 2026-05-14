# Recommendation Badge (Phase 4 planning stub)

**Status**: Planning. Not yet a loaded skill — promote to top-level
`.claude/skills/recommendation-badge/SKILL.md` when implementation
begins.

## Spec (user request, 2026-05-14)

Add a 4-tier recommendation indicator next to every stock's ticker
symbol in both the overview ranking table and the per-stock detail
page, plus a filter control in the existing filter panel.

### 4 tiers + colors

| Tier | Color | Tailwind class (proposed) |
|---|---|---|
| **Strong Buy** | dark green | `bg-emerald-700 text-white` |
| **Buy** | light green | `bg-emerald-300 text-emerald-900` |
| **Hold** | black / neutral | `bg-slate-700 text-white` (dark) / `bg-slate-200 text-slate-900` (light) |
| **Sell** | red | `bg-red-600 text-white` |

Soft-palette rule from prior sessions: avoid pure saturated red/green
(per the 2026-05 design review). Use `emerald-700` not `green-600`,
`red-600` not `red-700`. Light mode + dark mode variants both needed.

### Display location

1. **Overview / Ranking table** (`frontend/components/RankingTable.tsx`):
   - Place to the right of the ticker symbol, before the company name
   - Compact badge — short text only (`SB` / `B` / `H` / `S`) OR full
     text with smaller font; decide during implementation by visual
     density
2. **Stock detail page** (`frontend/app/stock/[ticker]/page.tsx`):
   - Place to the right of the ticker symbol in the header row
   - Use full text variant (more space available)

### Filter

Add to existing filter panel in `frontend/components/FilterBar.tsx`
(or wherever sector / search filter currently lives):

- Multi-select chips: `[Strong Buy] [Buy] [Hold] [Sell]`
- Default = all selected (show everything)
- Persists in URL query param: `?rec=strong_buy,buy`

## Methodology (proposed rubric)

The rating is derived from existing compute-layer outputs — **no new
modeling**. Pure thresholding on composite score + risk overlay +
fair-price MoS:

```
def derive_recommendation(detail: StockDetail) -> Literal["strong_buy", "buy", "hold", "sell"]:
    risk_flags = set(detail.risk_flags or [])
    warnings = set(detail.valuation_warnings or [])
    mos = detail.fair_price.mos_pct if detail.fair_price else None

    # SELL — overrides composite
    if (
        "data_quality_input_corruption" in risk_flags
        or "altman_distress" in risk_flags
        or detail.composite_score < 35
        or (mos is not None and mos < -30)
    ):
        return "sell"

    # STRONG BUY — top decile + clean + cheap
    if (
        detail.composite_score >= 70
        and not (risk_flags & {"sloan_accruals_top_decile", "net_issuance_top_decile"})
        and "beneish_high" not in warnings
        and "dechow_high" not in warnings
        and (mos is None or mos >= 20)
    ):
        return "strong_buy"

    # BUY — top quartile, not flagged
    if (
        detail.composite_score >= 60
        and len(risk_flags) <= 1
        and (mos is None or mos >= 0)
    ):
        return "buy"

    return "hold"
```

**Thresholds are tunable** — surface as `config.RECOMMENDATION_*`
constants. Default tuning targets:
- ~5-10% of universe at Strong Buy
- ~25-35% at Buy
- ~40-50% at Hold
- ~10-25% at Sell

Validate by running the rubric against the latest production
`rankings.json` before merging — counts shouldn't be wildly skewed.

## Architecture changes

| Layer | Change |
|---|---|
| `compute/scoring/recommendation.py` (new) | `derive_recommendation(detail)` function — pure derivation, no new feature inputs |
| `compute/output/schemas.py` | Add `recommendation: Literal["strong_buy", "buy", "hold", "sell"]` to both `StockSummary` and `StockDetail` |
| `compute/main.py` | Call `derive_recommendation()` in the per-ticker loop after `risk_flags` + `fair_price` are computed |
| `frontend/lib/types.ts` | Mirror the literal-union field |
| `frontend/lib/schema-snapshot.json` | Regenerate |
| `frontend/components/RecommendationBadge.tsx` (new) | Reusable badge component — accepts `recommendation: Recommendation`, returns `<span>` with Tailwind classes |
| `frontend/components/RankingTable.tsx` | Insert `<RecommendationBadge />` after ticker, before name |
| `frontend/app/stock/[ticker]/page.tsx` | Insert `<RecommendationBadge size="lg" />` next to ticker in header |
| `frontend/components/FilterBar.tsx` (or wherever filters live) | Add 4-chip multi-select control with URL param sync |
| `frontend/app/page.tsx` filter state | Add `rec` query param parsing + apply filter to rankings before rendering |

LOC estimate: ~150 LOC across 8 files.

## Legal / disclaimer considerations ⚠️

The README's existing Disclaimer + Honest Limitations section
explicitly says:

> "Nothing here is investment advice, a recommendation, or an offer to
> buy or sell securities."

> "QuantRank is a risk-stratifier and screener, not a fraud guarantor"

Adding **literal "Strong Buy / Buy / Hold / Sell"** labels — which is
the standard sell-side analyst terminology — directly contradicts that
positioning and may carry regulatory implications (FINRA / SEC view of
"investment advice" definitions).

**Mitigation options** (decide before implementation):

| Option | Tradeoff |
|---|---|
| **A. Keep terminology, add prominent disclaimer near each badge** | Most direct user request; legal exposure highest |
| **B. Rename to neutral terms**: `Top Tier / Favorable / Neutral / Cautious`, or `Bullish / Lean Bullish / Neutral / Bearish` | Same UX, lower legal exposure |
| **C. Color-coded percentile only, no text labels** | Loses the "instant readable" UX intent |
| **D. Composite-percentile labels**: `Top 5% / Top 25% / Median / Bottom 25%` | Most defensible academically; least intuitive for casual users |

**Recommended**: **Option B** ("Bullish / Lean Bullish / Neutral / Cautious")
gives the same instant-read color affordance without using regulated
terminology. README disclaimer update can stay minimal.

If user insists on **Option A** (literal "Strong Buy / Buy / Hold /
Sell"): add the disclaimer text:

> "Ratings shown are derived from QuantRank's open-source composite
> + defense layer + fair-price ensemble. They are NOT investment advice
> from a licensed adviser. See [Honest Limitations](#honest-limitations)."

…directly under every badge (`<small>` text on detail page, tooltip
on ranking table).

## Test plan

- [ ] Unit test `derive_recommendation()` with synthetic StockDetail
  inputs covering all 4 tiers + edge cases:
  - data_quality_input_corruption → sell (overrides high composite)
  - mos < -30 → sell
  - composite 35 boundary → strict comparison
  - mos = None → hold (defensive)
- [ ] Distribution test against latest `rankings.json`:
  - Strong Buy count ≤ 15%
  - Sell count ≥ 5%, ≤ 30%
  - No tier > 60% of universe (rubric isn't broken)
- [ ] Snapshot regen — schema_check passes
- [ ] TypeScript: union type narrowing works in `RecommendationBadge`
- [ ] Frontend visual: badge renders both light + dark mode
- [ ] Filter: URL param round-trips, default = all selected

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| 1. Backend (recommendation.py + schema + wire-up) | ~50 | 2-3 hr |
| 2. Tests (8-12 unit tests + distribution test) | ~80 | 2 hr |
| 3. Frontend badge component + 2 placement sites | ~50 | 2-3 hr |
| 4. Filter UI + URL sync | ~40 | 2-3 hr |
| 5. Disclaimer + Honest Limitations update | ~10 | 0.5 hr |
| 6. Verification ladder + iteration | n/a | 2-3 hr |
| **Total** | **~230 LOC** | **~10-15 hr** |

Fits as one focused PR (`feat(ui): recommendation badge with filter`).

## When to ship

Not a v1.0 blocker. Land any time after v1.0 tag stabilizes. Suggested
placement: **post-v1.0 minor feature** (`v1.1` or early Phase 4 chore).

## Open questions for implementer

1. Confirm terminology (Option A / B / C / D from "Mitigation options")
2. Confirm if Strong Buy count should be sector-relative or
   absolute-universe — sector-relative makes "every sector has its own
   top picks", absolute-universe means tech might dominate
3. Confirm if recommendation should be wholly derived (deterministic from
   composite + flags) or partially editable / overridable
4. Confirm filter persistence: URL query param vs. localStorage
