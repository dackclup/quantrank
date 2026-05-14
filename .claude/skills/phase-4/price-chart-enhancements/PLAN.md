# Price Chart Enhancements (Phase 4 planning stub)

**Status**: Planning. Not yet a loaded skill — promote to top-level
`.claude/skills/price-chart-enhancements/SKILL.md` when implementation
begins. Pairs with `recommendation-badge/PLAN.md` (sibling stub).

## Spec (user request, 2026-05-14, with Jitta-style reference)

Three enhancements to the per-stock price chart on the detail page
(`frontend/app/stock/[ticker]/page.tsx` + `StockHistoryChart.tsx` or
similar):

### 1. Time-period selector

Toggle buttons above the chart: **`1D` `5D` `1M` `6M` `YTD` `1Y` `5Y`**

Default: `1Y` (matches current behavior).

### 2. Target price line (Bullish / Lean Bullish only)

For tickers whose `recommendation` field (added in
[`recommendation-badge/PLAN.md`](../recommendation-badge/PLAN.md), Option B
locked per `phase-4-kickoff-checklist/PLAN.md` §1) is
`bullish` or `lean_bullish`:

- **Black solid horizontal line** across the chart at the target-price
  level
- **Black numeric label** at the right edge showing the target value
  (e.g., `$XXX.XX`)

Skip rendering for `neutral` and `cautious` (no target line, no label) —
showing a target price below current price would be confusing UX.

### 3. Fair price line (Jitta-style, all tickers)

For all tickers regardless of recommendation:

- **Gray dashed horizontal line** at `fair_price.median` value
- Visually similar to Jitta Line — light-gray (`#94a3b8` or
  Tailwind `slate-400`), dash pattern `5 3` (5px on, 3px off)
- Numeric label at right edge in matching gray, smaller font than
  target-price label

If `fair_price.median` is null (e.g., applicability gates failed for
all 6 methods, or `data_quality_input_corruption` veto fired) → omit
the line entirely.

## Mapping QuantRank fields → chart elements

QuantRank's existing fair-price ensemble already produces the values
needed — no new modeling:

| Chart element | Source field | Notes |
|---|---|---|
| Black solid (target price) | `StockDetail.fair_price.max` | **LOCKED** per `phase-4-kickoff-checklist/PLAN.md` §1. Upper bound across the 6 methods (excludes outliers per the `_classify_outliers` rule). Represents "if the optimistic methods are right, this is where it could go". Conservative vs `fair_price.high` (which includes outliers) |
| Gray dashed (fair price) | `StockDetail.fair_price.median` | Robust central tendency across all applicable methods. Same value used for `MoS%` calculation |
| Numeric labels | rounded to 2 decimals | Match the `current_price` formatting elsewhere |

## Time-period data requirements

| Period | Data granularity needed | Currently available? |
|---|---|---|
| `1D` | minute-level intraday | ❌ NOT in ingest |
| `5D` | minute or hourly | ❌ NOT in ingest |
| `1M` | daily | ✅ in `frontend/public/data/stocks/history/<TICKER>.json` |
| `6M` | daily | ✅ slice of existing 1Y |
| `YTD` | daily | ✅ slice |
| `1Y` | daily | ✅ current default |
| `5Y` | daily or weekly | ❌ only 1Y currently — need ingest extension |

**Two ingest extensions required** to fully support the request:

| Extension | Source | Effort |
|---|---|---|
| 5Y daily history | yfinance `period="5y"` parameter | Trivial — change one parameter in `compute/ingest/prices.py` |
| Intraday (1D / 5D) | yfinance `period="5d", interval="1m"` OR a separate intraday data source (Polygon, Alpaca) | Moderate — yfinance intraday is rate-limited and unreliable; Polygon free tier covers but adds API key surface |

**Phased rollout** suggested:

| Phase | Periods supported | When |
|---|---|---|
| 4.1 | `1M`, `6M`, `YTD`, `1Y` (slice existing data) + fair-price + target lines | Immediately implementable |
| 4.2 | + `5Y` (extend ingest to 5Y daily) | Small ingest PR — 1 day work |
| 4.3 | + `1D`, `5D` intraday | Bigger architecture decision — separate data source + cache strategy |

The user-visible toggle UI should ship all 7 buttons in Phase 4.1, with
4.2 / 4.3 ones disabled (greyed-out + tooltip "coming in v1.X") until
backed by data. This avoids breaking the design intent.

## Why horizontal lines (Phase 4) vs Jitta-style time-series (Phase 5+)

Jitta's gray dashed line evolves over time because their "Jitta Line"
recomputes intrinsic value at each historical timestamp. To replicate
that for QuantRank we'd need:

- Historical EPS / book value / equity / cash flow at each prior
  quarter (already partially in `_ANNUAL_TAGS` history)
- Re-run the 6-method fair-price ensemble at each historical timestamp
  using point-in-time inputs
- Cache the resulting time-series alongside the price history JSON
- ~200-400 LOC of new compute layer + ~5-10× the per-ticker compute
  time (re-running ensemble 20+ times for a 5y monthly cadence)

**Phased rollout**:

| Phase | Fair-price line | When |
|---|---|---|
| 4 | Single horizontal line (current `fair_price.median`) | Immediate — no compute change |
| 5+ | Time-series fair-price line (Jitta-equivalent) | Major compute extension — needs Phase 5+ ML/factor work to land first since point-in-time historical inputs overlap with backtest infrastructure |

This PLAN ships **Phase 4 horizontal-line only**. Time-series fair-price
gets its own future PLAN under Phase 5 or 6.

## Architecture changes

| Layer | Change |
|---|---|
| `compute/output/schemas.py` | No new fields needed — `fair_price.median` and `fair_price.max` already exist on `FairPriceEnsemble` |
| `compute/ingest/prices.py` | Phase 4.2: add 5Y daily fetch alongside existing 1Y |
| `compute/output/writer.py` | Phase 4.2: persist 5Y price slice in `<TICKER>.json` (or separate `<TICKER>-5y.json` to keep current 1Y file lean) |
| `frontend/lib/types.ts` | No type changes for Phase 4.1; add `prices_5y` field for Phase 4.2 |
| `frontend/components/StockHistoryChart.tsx` (or current chart component) | Add: time-period state, fair-price horizontal line, target-price horizontal line (conditional on recommendation), labels |
| `frontend/components/PriceTimePeriodSelector.tsx` (new) | 7-button toggle group; uncovered periods disabled with tooltip |

LOC estimate: **~180 LOC** for Phase 4.1 (chart + selector + lines), **~50 LOC** more for Phase 4.2 (5Y ingest + writer + slice).

## Visual spec details

```tsx
// Recharts ReferenceLine config (proposal)
<ReferenceLine
  y={fairPriceMedian}
  stroke="#94a3b8"           // slate-400
  strokeDasharray="5 3"
  label={{
    value: `Fair: $${fairPriceMedian.toFixed(2)}`,
    position: "right",
    fill: "#64748b",         // slate-500
    fontSize: 11,
  }}
/>

{recommendation === "bullish" || recommendation === "lean_bullish" ? (
  <ReferenceLine
    y={fairPriceMax}
    stroke="#0f172a"          // slate-900 (near-black, not pure black for readability)
    strokeWidth={1.5}
    label={{
      value: `Target: $${fairPriceMax.toFixed(2)}`,
      position: "right",
      fill: "#0f172a",
      fontSize: 12,
      fontWeight: 600,
    }}
  />
) : null}
```

Soft-palette rule from prior design reviews: avoid pure `#000000` or
`#ef4444`-saturated colors. Use `slate-900` for "black" and the
existing soft-red/soft-green from the page header.

## Test plan

- [ ] Time-period toggle: clicking each button updates chart x-axis
  range without remounting
- [ ] Disabled periods (`1D`, `5D`, `5Y` in Phase 4.1) show tooltip
  "available in v1.X" on hover
- [ ] Recommendation badge → target-price line rendering:
  - `bullish` / `lean_bullish` → black line + label visible
  - `neutral` / `cautious` → no black line
  - `recommendation` field missing (legacy data) → no black line
- [ ] Fair price line:
  - Renders for all tickers with non-null `fair_price.median`
  - Skipped for tickers with null `fair_price` (banks excluded by
    sector rule, or `data_quality_input_corruption` vetoed)
- [ ] Light + dark mode: lines + labels remain legible in both
- [ ] Mobile: labels don't overflow chart bounds; toggle buttons wrap
  cleanly at narrow viewports
- [ ] Distribution sanity: target-price line is ABOVE current price for
  Bullish / Lean Bullish tickers (else the rubric in
  `recommendation-badge/PLAN.md` is broken)

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| 1. PriceTimePeriodSelector component | ~50 | 1-2 hr |
| 2. Chart enhancements (lines + labels + period state) | ~80 | 3-4 hr |
| 3. Frontend tests | ~50 | 1-2 hr |
| 4. Verification ladder | n/a | 1 hr |
| **Phase 4.1 total** | **~180 LOC** | **~6-9 hr** |
| Phase 4.2 (5Y ingest extension) | ~50 LOC | 1-2 hr |
| Phase 4.3 (intraday data source) | ~150-300 LOC | major decision — defer |

Fits as **one PR for Phase 4.1**, separate PRs for 4.2 / 4.3.

## Dependencies

- **Hard dependency**: `recommendation-badge/PLAN.md` must ship first
  (the chart's target-price-line conditional reads
  `StockDetail.recommendation`)
- **Soft dependency**: design palette decision from
  `recommendation-badge/PLAN.md` Option A/B/C/D — the chart's color
  story should align (soft-palette + "almost-black" not pure black)

## Decisions (formerly open questions — locked 2026-05-14)

1. ~~Target line source?~~ → **`fair_price.max` locked** (per `phase-4-kickoff-checklist/PLAN.md` §1). Conservative; excludes outliers
2. ~~5Y data source?~~ → **yfinance `period="5y"` locked** for Phase 4.2; defer alternative-source decision to Phase 6+ if yfinance reliability degrades further. Existing `yfinance==0.2.55` pin protects ingest
3. ~~Intraday support (1D / 5D)?~~ → **Defer entirely** locked for Phase 4. Phase 4.3 (intraday) is a separate architecture decision; Phase 4 ships 4.1 + 4.2 only. Phase 4.1 disables `1D` / `5D` buttons with "available in v1.X" tooltip
4. ~~Fair-price line for `cautious` tickers?~~ → **Show it** locked. Transparent to user (they see overvaluation explicitly); matches the "honest model output" framing
