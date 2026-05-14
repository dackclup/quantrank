# JKP Factor Integration (Phase 4 planning stub)

**Status**: Planning. Closes P0 audit gap (2026-05-14): WORKFLOW.md §4.3 lists JKP integration but no focused PLAN existed.

## Purpose

Wire **Jensen-Kelly-Pedersen** 153-factor library (jkpfactors.com) into the QuantRank composite via theme-cluster aggregation. JKP is the Kelly-Pruitt-Su Lab's complement to OSAP — global coverage, longer history, 13 theme clusters that mitigate collinearity.

This PLAN is the focused implementation spec for WORKFLOW.md §4.3 + RESEARCH_FINDINGS.md §2.2.

## Why JKP, in addition to OSAP

OSAP and JKP overlap on ~40% of signals but differ on:
- **Theme clustering** — JKP's 13 themes (Quality, Value, Investment, Profitability, Profit Growth, Momentum, Leverage, Trading Frictions, Skewness, Low Risk, Size, Accruals, Seasonality) collapse 153 collinear signals into 13 quasi-orthogonal axes. OSAP does NOT provide this.
- **Global coverage** — JKP includes international stocks; QuantRank universe is US-only currently but this preserves Phase 8 universe-expand-sp1500 → global option
- **Long history** — JKP covers 1972-present; OSAP starts later

Decision locked: **Theme-cluster path only**. Phase 4 consumes the 13 theme cluster returns, NOT all 153 individual signal returns. This:
1. Avoids LightGBM double-counting collinear signals (the original motivation in RESEARCH_FINDINGS.md §2.2)
2. Reduces compute cost
3. Aligns with JKP's authors' published recommendation for downstream users

## License ⚠️

| Component | License | Phase 4 use |
|---|---|---|
| JKP code (`bkelly-lab/jkp-data`) | MIT | ✅ free |
| Factor returns CSV (the 13 themes + 153 signals at monthly granularity) | **CC BY-NC 4.0** (non-commercial) | ✅ educational static-site OK; ⚠️ commercial use forbidden |
| Stock-level signals | Requires WRDS | ❌ skip |

**Re-verify at Phase 4 entry**: confirm jkpfactors.com terms STILL show CC BY-NC 4.0 (no change since 2026-05-09 last verification). If terms change to commercial-only → fallback to OSAP-only.

**QuantRank's status**: Open-source static-site educational project. CC BY-NC 4.0 ALLOWED. If the project ever commercializes (consulting, paid API, etc.) → JKP must be removed or commercial license obtained from Kelly Lab.

This is documented as a v1.1 commitment. README's "License" section gets a JKP attribution line when this PLAN ships.

## Architecture

```
compute/ingest/jkp.py            # CSV download + cache (theme cluster returns)
compute/scoring/jkp_blend.py     # Blend theme cluster returns into existing pillars
```

NOT building `compute/features/jkp_replicate.py` — Phase 4 doesn't recompute stock-level signals. The cluster L/S returns are consumed directly.

### Step 1: Ingest (`compute/ingest/jkp.py`)

```python
JKP_THEME_RETURNS_URL = (
    "https://jkpfactors.com/data/factors_<release>.csv"
)
CACHE_PATH = Path("compute/cache/jkp/themes.parquet")
FRESHNESS_DAYS = 31

THEME_NAMES = [
    "quality", "value", "investment", "profitability",
    "profit_growth", "momentum", "leverage", "trading_frictions",
    "skewness", "low_risk", "size", "accruals", "seasonality",
]

def fetch_jkp_themes() -> pd.DataFrame:
    """Download + cache JKP 13 theme cluster long-short returns.
    Schema: theme, year_month, ls_return, region (us / dev / em / global)
    """
    if _is_fresh(CACHE_PATH, FRESHNESS_DAYS):
        return pd.read_parquet(CACHE_PATH)
    df = pd.read_csv(JKP_THEME_RETURNS_URL)
    df = df[df["region"] == "us"]  # US universe only for QuantRank
    df.to_parquet(CACHE_PATH, index=False)
    return df
```

### Step 2: Pillar blending (`compute/scoring/jkp_blend.py`)

JKP themes map onto QuantRank's 8 pillars as follows (locked mapping):

| QuantRank pillar | JKP theme(s) | Weight |
|---|---|---|
| Quality | `quality` | 1.0 |
| Value | `value` | 1.0 |
| Growth | `profit_growth` + `investment` (negative) | 0.5 / -0.5 |
| Momentum | `momentum` + `seasonality` | 0.7 / 0.3 |
| Health | `leverage` (negative) + `accruals` (negative) | -0.5 / -0.5 |
| Profitability | `profitability` | 1.0 |
| Technical | `low_risk` + `trading_frictions` (negative) | 0.5 / -0.5 |
| Risk | `skewness` (negative) | -1.0 |

(Negative weights = "high X is bad for this pillar".)

Blending pattern same as OSAP — 50/50 DIY-vs-academic for each pillar by default.

**Important**: JKP returns are *long-short portfolio returns over time*, not stock-level signal values. The blend works by computing each stock's exposure to the JKP factor (regression slope on the theme's L/S return over rolling 36 months) and using that exposure as the cross-sectional rank.

```python
def stock_theme_exposure(stock_returns: pd.Series, theme_returns: pd.Series) -> float:
    """Rolling 36-month regression slope. NaN if <24 months overlap."""
    aligned = pd.concat([stock_returns, theme_returns], axis=1).dropna()
    if len(aligned) < 24:
        return float("nan")
    cov = aligned.cov().iloc[0, 1]
    var = aligned.iloc[:, 1].var()
    return cov / var if var > 0 else float("nan")
```

This is the published JKP-prescribed approach for downstream users without WRDS access.

## Compute time impact

| Step | Cold cache | Warm cache |
|---|---|---|
| JKP CSV download | 5 sec | <1 sec |
| Stock-theme exposure (500 stocks × 13 themes × 36-month regression) | 1-2 min | unchanged |
| Blending | <30 sec | unchanged |
| **Phase 4 JKP cost** | **+2 min** | **+1-2 min** |

Combined with OSAP (~5 min): Phase 4 adds ~7 min to weekly compute. Within budget.

## Validation

| Test | Threshold | Action on fail |
|---|---|---|
| Theme L/S returns published t-stat replication (against jkpfactors.com tables) | ≥0.90 correlation with published series | Exclude that theme from blending |
| Stock-theme exposure IC (walk-forward) | |IC| > 0.01 per theme | Exclude theme from that pillar |
| Combined pillar IC after blending | ≥ DIY-only IC | Revert that pillar to DIY-only |
| Coverage | ≥10 of 13 themes pass IC gate | If <10 → partial-ship, document |

## Schema impact

Additive (per `v1-to-v1-1-migration/PLAN.md`):

```python
class StockDetail(BaseModel):
    ...
    jkp_theme_exposures: dict[str, float] | None = None   # theme_name → 36-month exposure beta
    jkp_blended_pillars: dict[str, float] | None = None   # pillar → blended rank
```

Schema bump: `1.1.0-phase4` (joint with OSAP).

## Effort estimate

| Step | LOC | Days |
|---|---|---|
| Ingest + caching | ~80 | 1 |
| Theme-exposure regression engine | ~120 | 1.5 |
| Blending | ~80 | 0.5 |
| Validation harness (replication QC + IC gate) | ~100 | 1 |
| Tests (synthetic + golden) | ~150 | 1 |
| Schema additions + writer wiring | ~50 | 0.5 |
| Documentation + license attribution in README | ~30 | 0.25 |
| **Total** | **~610 LOC** | **~6 days** |

## Dependencies

- `workflow-cache-improvements/PLAN.md` should land first (parquet cache discipline)
- `defense-infrastructure/PLAN.md` should land first (IC-decay gate per theme)
- `osap-integration/PLAN.md` should land first or in parallel — the blending pattern is shared (`compute/scoring/<library>_blend.py`)

## Phase 4 ship order (per `v1-to-v1-1-migration/PLAN.md`)

JKP lands at **PR 4g** or **4h** alongside OSAP:
- 4g: OSAP integration (~9 days)
- 4h: JKP integration (~6 days)
- 4i: Qlib Alpha158 (~4 days, per `alpha158-fit/PLAN.md`)
- 4j: IPCA (~4 days, per `ipca-factor-fit/PLAN.md`)

OSAP first (denser signal coverage); JKP second (theme orthogonalization on top).

## What this PLAN doesn't cover

- **All 153 individual JKP signals** — out of scope; we use the 13 themes only
- **Stock-level JKP signal replication** — needs WRDS, skipped
- **Global / international expansion** — Phase 8; this PLAN filters to US returns
- **OSAP integration** — sister PLAN at `osap-integration/PLAN.md`

## Open questions (closed by decisions above)

1. ~~13 themes vs 153 signals?~~ → **13 themes locked**
2. ~~Exposure window length?~~ → **36 months locked** (matches Kelly Lab examples)
3. ~~License?~~ → **CC BY-NC 4.0 acceptable for static-site educational use**; re-verify at Phase 4 entry

## References

- Jensen, Theis I., Bryan Kelly, and Lasse H. Pedersen (2023). "Is There a Replication Crisis in Finance?" *Journal of Finance* 78(5).
- Code: github.com/bkelly-lab/jkp-data
- Factor returns CSV: jkpfactors.com
- License terms: CC BY-NC 4.0 (creativecommons.org/licenses/by-nc/4.0/)
