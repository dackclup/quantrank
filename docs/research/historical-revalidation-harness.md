# Historical Re-validation Harness

**Status**: Phase 4.6 first unit (scaffolding) — shipped 2026-05-27. Future PRs layer IC / PBO / DSR baselines on top.

## What this harness IS

A pure-function module + CLI that answers the first foundational question of honest re-validation: **what's the universe drift between today and any historical as-of date?**

- `compute/validation/universe_drift.py` — `compute_universe_drift(as_of_date, current_universe) -> UniverseDriftReport` returning the 3-way partition (`added_since`, `removed_since`, `unchanged`)
- `scripts/historical_pillar_revalidate.py` — CLI wrapper that prints the report (text or JSON)
- 11 tests in `tests/test_validation/test_universe_drift.py`

## What this harness is NOT (yet)

This first unit ships the **universe-drift** half of honest re-validation. The other half — per-pillar IC / PBO / DSR baselines at historical dates — depends on:

1. **Git-archived `rankings.json` snapshots** — daily cron commits exist (`chore: update rankings YYYY-MM-DD`), but a separate fetcher needs to checkout historical SHAs + load composite_score time series per ticker
2. **Forward realized returns** — requires the gitignored `compute/cache/prices/` cache (5Y daily OHLCV per stock)
3. **Pillar computation at historical dates** — requires `compute/scoring/pillars.py` pure functions to run on historical fundamentals (already pure; needs a wrapper that loads the right historical snapshot)

Each of those is a separate PR sized at 1-2 days each. This PR ships the first leg cleanly.

## How to use the CLI

```bash
# Real universe (fetches Wikipedia)
python -m scripts.historical_pillar_revalidate --as-of 2024-06-01

# Smoke mode (offline; uses 7-ticker hardcoded universe)
python -m scripts.historical_pillar_revalidate --as-of 2023-06-01 --no-fetch-universe

# JSON output for downstream tooling
python -m scripts.historical_pillar_revalidate --as-of 2023-06-01 --json

# Pre-coverage degraded mode (exit code 1, loud warning)
python -m scripts.historical_pillar_revalidate --as-of 2010-01-01
```

### Sample output (smoke mode, 2023-06-01)

```
Universe drift report — as_of=2023-06-01
  anchor date         : 2026-05-27
  current universe    : 7 tickers
  historical universe : 15 tickers
  events applied      : 19
  is_complete         : True
  note                : reversed 19 post-as_of events

  ADDED since as_of   : 1 tickers
    SMCI
  REMOVED since as_of : 9 tickers
    AAP, ATVI, BIO, BLL, DISH, ETSY, LNC, WHR, ZION
    ↑ this is the SURVIVORSHIP-BIAS-CORRECTED cohort —
      current-universe-only views silently EXCLUDE these
  UNCHANGED           : 6 tickers (always-in cohort)
```

The 9 REMOVED tickers (AAP/ATVI/BIO/BLL/DISH/ETSY/LNC/WHR/ZION) are exactly the cohort an honest backtest at as-of 2023-06-01 must include. A current-universe-only view silently excludes them → systematically biased Sharpe / IC estimates per Hou-Xue-Zhang (2020) RFS.

## Methodology anchors

- **Hou, Xue, Zhang (2020)**. "Replicating Anomalies." *Review of Financial Studies* 33(5):2019-2133.
- **McLean, Pontiff (2016)**. "Does Academic Research Destroy Stock Return Predictability?" *Journal of Finance* 71(1):5-32.
- License posture: `data/sp500_membership_historical.csv` is uncopyrightable factual data per Feist v. Rural Tel. Service Co. (1991).

## Acceptance criteria for next PRs in the chain

- [ ] Per-pillar IC re-baseline (load `rankings.json` history via git, compute IC against realized 6/12-month returns from `compute/cache/prices/`)
- [ ] Per-pillar PBO/DSR re-run using PR #275's `universe_provider` kwarg
- [ ] `manipulation_index` distribution comparison: forward (current universe) vs honest (historical-universe-corrected at quarterly anchor dates)
- [ ] Honest-correction report `docs/research/honest-baseline-2026-05-27.md` documenting the delta vs Phase 4.5f published numbers (expected DOWN 5-15% per Research Report v1.0 §1.1 decay budget)

## Caveats

- **CSV coverage starts 2020-01-01** — pre-coverage queries return `is_complete=False` and degrade to current-universe fallback. Subsequent PRs may extend coverage backward.
- **Only ADD/REMOVE events** — RENAME events (e.g., FB→META) don't affect membership and are excluded from drift analysis.
- **Drift report is symmetric-difference only** — corporate actions like stock splits, dividends, and sector reclassifications are out of scope.
- **No price/return data here** — `removed_since` is the cohort of tickers that EXISTED in the historical universe but no longer trade. Computing their realized returns from delisting requires CRSP or equivalent (paid) — this harness identifies the cohort, doesn't price it.

## Future-work TODO list

| # | Item | Effort | Blocker |
|---|---|---|---|
| 1 | Git-archived `rankings.json` time-series loader | 1d | — |
| 2 | Forward-return computation per ticker from `compute/cache/prices/` | 0.5d | gitignored cache; needs warm CI run |
| 3 | Per-pillar IC at historical dates | 1d | needs #1 + #2 |
| 4 | PBO/DSR re-baseline via `factor_passes_gates(universe_provider=members_at, ...)` | 1d | needs #3 |
| 5 | `manipulation_index` distribution shift report | 0.5d | needs #1 |
| 6 | `docs/research/honest-baseline-2026-05-27.md` with revised PBO/DSR numbers | 0.5d | needs #4 |

**Total to honest-baseline report**: ~4-5 days focused dev across a sequence of PRs.
