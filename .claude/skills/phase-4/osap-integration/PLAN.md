# OSAP Integration (Phase 4 planning stub)

**Status**: Planning. Closes P0 audit gap (2026-05-14): WORKFLOW.md §4.2 lists OSAP integration as a Phase 4 deliverable but no focused PLAN existed.

## Purpose

Wire Chen-Zimmermann **Open Source Asset Pricing** (openassetpricing.com) portfolio signals into the QuantRank composite. OSAP is the canonical academic factor library — 319 signals replicated from peer-reviewed papers with full transparency on construction.

This PLAN is the focused implementation spec for what WORKFLOW.md §4.2 + RESEARCH_FINDINGS.md §2.1 describe at high level.

## Why OSAP, not DIY

QuantRank's Phase 0-3 factor work is small (~50 LOC per pillar). OSAP delivers 319 academically-validated signals already. Replacing handful-of-pillars DIY with a 100-signal subset of OSAP:
- +0.5-1% alpha lift (per RESEARCH_FINDINGS.md §1)
- Removes "did we implement Sloan correctly?" class of bugs
- Defensible methodology — every signal has a peer-reviewed paper citation

Phase 4 doesn't replace the DIY pillars — it **blends** them via the pillar aggregation step (§Mapping below).

## License

| Component | License | Phase 4 use |
|---|---|---|
| `openassetpricing` Python package | MIT (Chen-Zimmermann + collaborators) | ✅ free |
| Portfolio returns CSV (long-short factor returns by month) | Public domain — freely downloadable | ✅ use directly |
| Stock-level signal recompute | Requires WRDS subscription | ❌ skip — use returns CSV only |

Decision locked: **CSV-only path**. No WRDS subscription. Phase 4 consumes monthly long-short returns per signal; stock-level cross-sectional ranks must be derived from QuantRank's own inputs (mirroring published signal construction in `compute/features/osap_replicate.py` for the subset we need).

## Architecture

```
compute/ingest/osap.py            # CSV download + cache
compute/features/osap_replicate.py # Reproduce stock-level signal values (subset)
compute/scoring/osap_blend.py     # Blend OSAP signal ranks into existing pillars
```

### Step 1: Ingest (`compute/ingest/osap.py`)

```python
OSAP_RETURNS_URL = "https://www.openassetpricing.com/wp-content/uploads/<release>/SignalReturns.csv"
CACHE_PATH = Path("compute/cache/osap/returns.parquet")
FRESHNESS_DAYS = 31  # OSAP releases monthly

def fetch_osap_returns() -> pd.DataFrame:
    """Download + cache OSAP long-short portfolio returns.
    Schema: signal_name, year_month, ls_return, n_stocks
    """
    if _is_fresh(CACHE_PATH, FRESHNESS_DAYS):
        return pd.read_parquet(CACHE_PATH)
    df = pd.read_csv(OSAP_RETURNS_URL)
    df.to_parquet(CACHE_PATH, index=False)
    return df
```

Cache key: `osap-returns-<year-month>` (bumped monthly via GitHub Actions cache key includes `date +%Y-%m`).

### Step 2: Signal replication (`compute/features/osap_replicate.py`)

For each of the ~100 signals we want to use, port the SAS / Stata replication code from `OpenAP/Code` (GitHub: OpenSourceAP/CrossSection) into pure pandas.

Phase 4 in-scope signal subset (target 100 of 319; locked list):

| Theme | Signals | Source |
|---|---|---|
| Value | bm, ep, sp, cfp, dy, debt2tang, ... (~15) | OSAP `Value` category |
| Quality / profitability | roeacc, gpa, opln, ato, accruals_total, ... (~15) | `Profitability` + `Accruals` |
| Momentum | mom12m, mom6m, mom36m, str, ind_mom, ... (~12) | `Momentum` |
| Investment / issuance | cei, totinv, growthnoa, ... (~8) | `Investment` |
| Risk / volatility | maxret, std_turn, beta, idiovol, ... (~10) | `Risk` |
| Earnings news | sue, ear, exfin, ... (~8) | `EarningsNews` |
| Trading frictions | turnover, illiq, amihud, ... (~7) | `Trading` |
| Other | (~25 covering Lev, Trad, etc.) | Misc OSAP categories |

Validation gate (§Validation below): each replicated signal's **monthly cross-section** must correlate ≥0.85 with the OSAP-published long-short return for that signal in our backtest window (2018-present). If <0.85 → signal excluded from blending.

### Step 3: Pillar blending (`compute/scoring/osap_blend.py`)

```python
PILLAR_OSAP_MAP = {
    "value":          ["bm", "ep", "sp", "cfp", ...],
    "quality":        ["roeacc", "gpa", "opln", "ato", ...],
    "growth":         ["sgr", "asset_growth_neg", ...],
    "momentum":       ["mom12m", "mom6m", "str", ...],
    "health":         ["debt2tang", "lev", "intan", ...],
    "profitability":  ["roa", "roe", "gpa", ...],
    "technical":      ["maxret", "idiovol", "amihud", ...],
    "risk":           ["std_turn", "beta", "exfin", ...],
}

OSAP_WEIGHT = 0.5  # 50/50 blend with DIY pillar ranks; tunable

def blend_pillar(diy_rank: pd.Series, osap_signal_ranks: list[pd.Series]) -> pd.Series:
    """Z-blend each pillar: 50% DIY rank + 50% mean of OSAP signal ranks
    for that pillar."""
    osap_combined = pd.concat(osap_signal_ranks, axis=1).mean(axis=1).rank(pct=True)
    return OSAP_WEIGHT * osap_combined + (1 - OSAP_WEIGHT) * diy_rank
```

50/50 weight is the Phase 4 default. Phase 5 backtest infrastructure can tune this per-pillar.

## Compute time impact

| Step | Cold cache | Warm cache |
|---|---|---|
| OSAP returns CSV download | 5 sec | <1 sec |
| Signal replication (100 signals × 500 stocks) | 3-5 min | unchanged (recomputed per run since point-in-time-correct) |
| Blending | <30 sec | unchanged |
| **Phase 4 OSAP cost** | **+5 min** | **+3 min** |

Stays within the 60-min weekly compute budget.

## Validation

| Test | Threshold | Action on fail |
|---|---|---|
| Signal replication correlation (vs OSAP-published L/S returns 2018-) | ≥0.85 | Exclude that signal from blending |
| IC walk-forward per signal | |IC| > 0.01 | Exclude from blending |
| Coverage | ≥80 of 100 target signals pass both gates | If <80 → Phase 4 OSAP partial-ship; document in PHASE_STATUS |
| Combined pillar IC after blending | ≥ DIY-only IC | If worse → revert that pillar to DIY-only |

## Schema impact

Additive only (per `v1-to-v1-1-migration/PLAN.md`):

```python
class StockDetail(BaseModel):
    ...
    osap_signals: dict[str, float] | None = None   # signal_name → cross-sectional rank
    osap_blended_pillars: dict[str, float] | None = None  # pillar → blended rank
```

Schema bump: `1.0.x` → `1.1.0-phase4` when this ships (per `schema-versioning/PLAN.md`).

## Effort estimate

| Step | LOC | Days |
|---|---|---|
| Ingest + caching | ~80 | 1 |
| Signal replication (100 signals × pandas porting) | ~600 | 4-5 |
| Blending | ~80 | 0.5 |
| Validation harness (correlation + IC gate) | ~120 | 1 |
| Tests (synthetic + golden) | ~200 | 1.5 |
| Schema additions + writer wiring | ~50 | 0.5 |
| Documentation + RESEARCH_FINDINGS cross-ref | ~30 | 0.25 |
| **Total** | **~1,160 LOC** | **~9 days** |

Larger than the rough estimate in `docs/PHASE_4_8_EFFORT_BACKFILL.md` (which only counted infra). Signal porting is the long tail.

## Dependencies

- `workflow-cache-improvements/PLAN.md` should land first (cache discipline before adding parquet downloads)
- `defense-infrastructure/PLAN.md` should land first (PBO + DSR + IC-decay gates are how we validate each OSAP signal)
- `backtest-infrastructure/PLAN.md` (Phase 5 foundational) is a stronger gate — full walk-forward validation needs it. Phase 4 can ship with simpler rolling-IC validation, but Phase 5 should re-validate.

Decision locked: Phase 4 ships with simpler rolling-12m-IC validation. Full walk-forward + DSR + PBO comes in Phase 5.

## What this PLAN doesn't cover

- **WRDS-required signals** — skipped entirely (would need paid subscription)
- **Real-time OSAP updates** — monthly cadence sufficient; static-site doesn't need hourly refresh
- **Custom signal authoring** — out of scope; this PLAN consumes OSAP only
- **JKP integration** — sister PLAN at `jkp-integration/PLAN.md`

## Open questions (closed by decisions above)

1. ~~WRDS vs CSV path?~~ → **CSV only locked**
2. ~~Full 319 signals vs subset?~~ → **100-signal subset locked** (signal list above)
3. ~~Blend weight?~~ → **50/50 default locked**; per-pillar tuning deferred to Phase 5

## References

- Chen, Andrew Y., and Tom Zimmermann (2022). "Open Source Cross-Sectional Asset Pricing." *Critical Finance Review*.
- Code: github.com/OpenSourceAP/CrossSection
- Returns CSV: openassetpricing.com (no WRDS needed for the L/S returns CSV)
