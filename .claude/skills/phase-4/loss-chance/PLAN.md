# Loss Chance % (Phase 4 planning stub)

**Status**: Planning. Not yet a loaded skill — promote to top-level
`.claude/skills/loss-chance/SKILL.md` when implementation begins.
Companion stub to `recommendation-badge/PLAN.md` and
`price-chart-enhancements/PLAN.md`.

## Spec (user request, 2026-05-14)

Add a **Loss Chance %** indicator next to the existing Margin of Safety
display, on both the overview ranking table and the per-stock detail
page. Loss Chance represents the model's estimated probability that
buying at the current price results in a loss, derived purely from the
existing compute-layer outputs (composite + risk overlay + valuation
warnings + fair-price MoS).

### Display location

1. **Overview / Ranking table** (`frontend/components/RankingTable.tsx`):
   - Right after Margin of Safety, same row or directly below
   - Format: `LossChance NN%` with a colored chip OR a compact
     horizontal bar (mirror MoS visual style)

2. **Detail page** (`frontend/app/stock/[ticker]/page.tsx`):
   - Header card row: `PRICE` · `MARGIN OF SAFETY` · `LOSS CHANCE` ←
     adds a third column
   - Use the same visual chip style as MoS

## Methodology (proposed rubric — heuristic, not backtested)

Pure deterministic derivation from existing outputs. **No new
modeling, no ML, no backtest** — purely combines signals already
exposed:

```python
def derive_loss_chance(detail: StockDetail) -> float | None:
    """Return loss probability (0-100) at current price. None if inputs
    insufficient.

    Components (weights heuristic, tuned to match academic literature
    base rates rather than backtested):

      1. MoS signal — dominant
         +50% MoS → -20 pp (low loss chance, undervalued)
           0% MoS → baseline
         -50% MoS → +20 pp (high loss chance, overvalued)
        -100% MoS → +25 pp (saturating cap)

      2. Composite signal — secondary
         100 → -10 pp
          50 → 0
           0 → +10 pp

      3. Risk-flag penalties — each fires independently
         data_quality_input_corruption: +20 pp  (compute unreliable)
         altman_distress:               +15 pp  (Altman 2017 type-I FP)
         going_concern_disclosure:      +10 pp  (Mayew 2015)
         sloan_accruals_top_decile:      +5 pp  (Sloan 1996)
         net_issuance_top_decile:        +5 pp  (Pontiff-Woodgate 2008)

      4. Valuation-warning penalties — lighter touch
         beneish_high:                   +5 pp
         dechow_high:                    +5 pp
         value_trap_risk:                +3 pp
         goodwill_heavy:                 +2 pp
         extreme_*_estimate:             +1 pp  (per flag, cap +5)
         stale_filing_soft:              +2 pp

    Baseline = 50%. Sum components. Clip to [5, 95] to avoid the
    misleading certainty of 0% / 100% claims.
    """
    if detail.fair_price is None or detail.fair_price.mos_pct is None:
        return None

    base = 50.0
    mos = detail.fair_price.mos_pct
    # Inverse-linear MoS contribution, capped
    mos_signal = max(-25.0, min(25.0, -mos * 0.4))
    base += mos_signal

    if detail.composite_score is not None:
        base += (50 - detail.composite_score) / 5.0

    risk = set(detail.risk_flags or [])
    if "data_quality_input_corruption" in risk: base += 20
    if "altman_distress" in risk: base += 15
    if "going_concern_disclosure" in risk: base += 10
    if "sloan_accruals_top_decile" in risk: base += 5
    if "net_issuance_top_decile" in risk: base += 5

    warn = set(detail.valuation_warnings or [])
    if "beneish_high" in warn: base += 5
    if "dechow_high" in warn: base += 5
    if "value_trap_risk" in warn: base += 3
    if "goodwill_heavy" in warn: base += 2
    if "stale_filing_soft" in warn: base += 2
    extreme_count = sum(1 for w in warn if w.startswith("extreme_") and w.endswith("_estimate"))
    base += min(5, extreme_count)

    return max(5.0, min(95.0, base))
```

**Why these weights**:
- `data_quality_input_corruption` carries the heaviest penalty (+20) —
  this veto means the computed MoS / composite is *based on broken
  inputs*, so the model has no idea of loss probability at all.
- `altman_distress` matches Altman's published Type-I rate (~5-10%)
  multiplied by severity.
- Going concern weight (+10) aligns with Mayew 2015 (~30% subsequent
  underperformance vs market for flagged firms).
- Sloan / NSI lighter (+5) since they're statistical-momentum signals,
  not distress signals.

**Calibration target distributions** (validate against latest
`rankings.json` before merging):

| Recommendation tier (Option B locked, per `phase-4-kickoff-checklist/PLAN.md` §1) | Expected Loss Chance band |
|---|---|
| Bullish | 10-25% |
| Lean Bullish | 25-40% |
| Neutral | 40-60% |
| Cautious | 60-90% |

Counts shouldn't be wildly skewed (e.g., > 70% of universe in 50-60
band, or > 20% pinned at the 95 ceiling).

## Architecture changes

| Layer | Change |
|---|---|
| `compute/scoring/loss_chance.py` (new) | `derive_loss_chance(detail)` function — pure derivation, no new inputs |
| `compute/output/schemas.py` | Add `loss_chance_pct: float \| None = None` to both `StockSummary` and `StockDetail` |
| `compute/main.py` | Call `derive_loss_chance()` in the per-ticker loop after `risk_flags` + `fair_price` are populated, before constructing summary / detail |
| `frontend/lib/types.ts` | Mirror field |
| `frontend/lib/schema-snapshot.json` | Regenerate |
| `frontend/components/LossChanceBadge.tsx` (new) | Reusable chip/bar component — accepts `lossChancePct: number \| null`, returns colored chip + numeric label. Reuses MoS visual conventions |
| `frontend/components/RankingTable.tsx` | Add column / row after MoS |
| `frontend/app/stock/[ticker]/page.tsx` | Add third metric column in header card |

LOC estimate: **~150 LOC** across 7 files.

## Visual spec

Color gradient — soft palette (matches the existing MoS bar +
recommendation-badge proposal):

| Loss Chance band | Color | Tailwind |
|---|---|---|
| 5-25% | dark green | `bg-emerald-700 text-white` |
| 25-40% | light green | `bg-emerald-300 text-emerald-900` |
| 40-60% | neutral / slate | `bg-slate-200 text-slate-700` |
| 60-80% | soft red | `bg-red-300 text-red-900` |
| 80-95% | dark red | `bg-red-700 text-white` |

```tsx
// LossChanceBadge component (proposal)
export function LossChanceBadge({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) {
    return <span className="text-slate-400 text-sm">—</span>;
  }
  const tone =
    pct < 25 ? "bg-emerald-700 text-white"
    : pct < 40 ? "bg-emerald-300 text-emerald-900"
    : pct < 60 ? "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200"
    : pct < 80 ? "bg-red-300 text-red-900"
    : "bg-red-700 text-white";
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-md text-sm font-medium ${tone}`}>
      {pct.toFixed(0)}%
    </span>
  );
}
```

## ⚠️ Naming / disclaimer considerations

Calling this **"Loss Chance %"** carries the same legal risk surface as
the recommendation-badge labels — implying a real probability without
backtest validation.

**DECISION LOCKED (2026-05-14)**: **Option D** — `Loss Chance %` user-facing label + small-text "heuristic" qualifier + tooltip linking to Honest Limitations. Per `phase-4-kickoff-checklist/PLAN.md` §1.

Required tooltip / footnote text:

> "Loss Chance combines composite, defense flags, and Margin of Safety
> into a heuristic 5-95% range. NOT a backtested probability. See
> [Honest Limitations](#honest-limitations) for caveats."

Visual treatment:
- On overview ranking table: chip shows `LossChance NN%`; on hover → tooltip text above
- On detail page: chip in header card; small italic footer text immediately under chip says "heuristic — see disclaimer"

For full backtest-calibrated probability → Phase 5+ ML work (Triple-Barrier + conformal prediction can yield calibrated intervals).

Historical alternatives (archival reference only — NOT implemented):

| Option | Disposition |
|---|---|
| A. "Loss Chance %" + small footnote | ❌ Rejected — footnote too easy to miss |
| B. "Downside Risk %" | ❌ Rejected — loses user-requested intuition |
| C. "Risk Score" 0-100 unitless | ❌ Rejected — loses probability framing entirely |
| **D. "Loss Chance %" + tooltip + small italic qualifier** | ✅ **LOCKED** |

## Test plan

- [ ] Unit test `derive_loss_chance()` with synthetic StockDetail inputs:
  - `fair_price.mos_pct = +50, no flags, composite = 80` → ~25% loss
  - `fair_price.mos_pct = -80, altman + going_concern, composite = 20`
    → 95% (ceiling)
  - `fair_price = None` → None propagates
  - Clipping floor 5% / ceiling 95% never exceeded
- [ ] Distribution test on latest `rankings.json`:
  - Median loss chance falls in 45-55 (universe roughly balanced)
  - At least 5 tickers in each color band (sanity)
  - Bullish tier (when recommendation-badge ships) lands in 10-25
    band ≥ 70% of the time
- [ ] Snapshot regen — `schema_check` passes
- [ ] TypeScript: `lossChancePct: number | null` matches Pydantic
- [ ] Frontend visual: 5 color bands render correctly in light + dark
  mode
- [ ] Ordering verification: chip sits to the right of MoS on both
  views (table row + detail header)

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| 1. Backend (`loss_chance.py` + schema + wire-up) | ~50 | 2-3 hr |
| 2. Unit + distribution tests | ~70 | 2 hr |
| 3. `LossChanceBadge` component + 2 placement sites | ~50 | 2 hr |
| 4. Disclaimer addition (Honest Limitations + tooltip) | ~10 | 0.5 hr |
| 5. Verification ladder | n/a | 1 hr |
| **Total** | **~180 LOC** | **~8-10 hr** |

Fits as one focused PR (`feat(ui): loss-chance metric with chip badge`).

## When to ship

Not a v1.0 blocker. Land as part of the Phase 4 UX trio:

1. `recommendation-badge` (independent)
2. `loss-chance` (independent, can ship before badge)
3. `price-chart-enhancements` (depends on `recommendation` field from #1)

Suggested order: **#1 → #2 → #3** (badge first so the chart's
target-line conditional has a field to read; loss-chance any time).

## Decisions (formerly open questions — locked 2026-05-14)

1. ~~Terminology?~~ → **Option D locked** (`Loss Chance %` + tooltip + small italic qualifier) — per `phase-4-kickoff-checklist/PLAN.md` §1
2. ~~Display format?~~ → **Same row as MoS** locked. Side-by-side chip layout; stacked is too vertical on mobile
3. ~~Color band cutoffs?~~ → **Symmetric around 50 locked** (5-25 / 25-40 / 40-60 / 60-80 / 80-95). Validate post-merge against universe distribution; bandwidth tunable in v1.2 if skewed
4. ~~Sector-relative vs absolute?~~ → **Absolute-universe locked**. Matches MoS computation (cross-sector). Sector-relative is a separate v1.2+ feature
5. ~~Schema field naming?~~ → **`loss_chance_pct` (snake_case) locked**. Consistent with `RawMetrics` + Pydantic naming convention
