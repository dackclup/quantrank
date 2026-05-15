# FRED Macro Regime (Phase 9 planning stub)

**Status**: Planning. First Phase 9 stub. Adds macro-regime context to
the per-stock view so a high composite during an inverted yield curve
isn't blindly recommended.

## Purpose

QuantRank's current composite + defense layer is **bottom-up** (per
stock fundamentals + price). It misses macro tailwind / headwind
context. A "Strong Buy" on a cyclical stock during a recession start
is a different recommendation than the same stock during recovery.

Phase 9 §1: bolt on a **macro regime indicator** sourced from FRED
(Federal Reserve Economic Data — fully free public API). Render as a
single chip on the homepage header.

## Free data source

[FRED API](https://fred.stlouisfed.org/docs/api/fred/) — free, no API
key required for basic series, no rate limit for reasonable use.

Series consumed (~6 indicators):

| Series ID | Description | Regime contribution |
|---|---|---|
| `T10Y2Y` | 10y-2y yield curve spread | Inverted (< 0) → recession risk |
| `UNRATE` | Civilian unemployment rate | Rising → late cycle |
| `CPIAUCSL` | CPI YoY change | Surprise > consensus → Fed hike pressure |
| `FEDFUNDS` | Effective Fed Funds rate | Tightening cycle indicator |
| `DGS10` | 10-year Treasury yield | Discount rate input for fair-price |
| `VIXCLS` | VIX volatility index | Risk-off > 25 |

## Architecture

```
compute/ingest/fred.py          # download + cache 6 series
compute/scoring/macro_regime.py # classify into 4 regimes
compute/output/schemas.py       # add Metadata.macro_regime
frontend/components/MacroRegimeChip.tsx  # display + tooltip
```

### Regime classifier (4 states, deterministic)

```python
def classify_regime(t10y2y, unrate, vixcls, cpi_yoy) -> Literal["expansion","late_cycle","recession","recovery"]:
    if t10y2y < 0 and unrate_rising:
        return "recession"
    if unrate_rising_but_yc_positive:
        return "late_cycle"
    if unrate_falling_and_yc_positive:
        return "expansion"
    return "recovery"
```

Threshold knobs tunable; defaults from Hamilton 1989 + Estrella-Mishkin
1998 NBER recession-predictor canon.

### UI display (beginner-friendly)

Chip in the page header:
- **Expansion** — emerald-50 / text-emerald-800 + dot bg-emerald-700
  "Macro tailwind"
- **Late cycle** — amber-50 / text-amber-800 + dot bg-amber-600
  "Cycle late stage"
- **Recession** — red-50 / text-red-800 + dot bg-red-700
  "Recession signal"
- **Recovery** — sky-50 / text-sky-800 + dot bg-sky-700
  "Recovery"

Tooltip: 2-3 sentence explanation of which FRED indicators triggered.

## Effort

| Step | LOC | Days |
|---|---|---|
| FRED ingest + cache | ~80 | 0.5 |
| Macro-regime classifier + tests | ~120 | 1 |
| Schema + writer wire-up | ~30 | 0.25 |
| MacroRegimeChip component | ~80 | 0.5 |
| Header layout integration | ~30 | 0.25 |
| Beginner-tooltip explanation | ~50 | 0.5 |
| **Total** | **~390 LOC** | **~3 days** |

## When this matters

A user looking at NVDA in 2026-05 sees the recommendation but doesn't
know the macro context. The chip adds one extra signal — high-composite
stocks should be trusted MORE in an expansion regime, LESS in a
late-cycle regime.

## Decisions (locked)

1. ~~FRED vs Bloomberg macro feed?~~ → **FRED locked** (free, fully
   public, no API key)
2. ~~Regime granularity?~~ → **4 states** (per Hamilton 1989 +
   Estrella-Mishkin 1998 standard)
3. ~~Threshold tuning?~~ → **Defaults from academic canon**;
   re-tunable as module constants

## Dependencies

- Phase 5 backtest infra (PR 4b) — for validating that macro regime
  signal adds IC > 0.01 over baseline
- Phase 5 conformal prediction — for calibrated regime probability
  intervals (vs deterministic 4-state classification)

## Out of scope (deferred to later phases)

- Per-sector regime adjustment (e.g., utilities favor late cycle)
- Continuous regime probability via HMM (that's Phase 7 work)
- International regime decoupling (Phase 8+ universe expansion)
