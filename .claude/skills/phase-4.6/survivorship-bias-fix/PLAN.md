# Phase 4.6 — Survivorship-Bias Fix (PLAN)

> **Priority**: P0 per Research Report v1.0 §7.4 (highest credibility ROI for top-1% claim)
> **Status**: PLAN — execution begins on `claude/phase-4.6-survivorship-bias-fix` branch

## Goal

Replace `compute/ingest/universe.py` "current S&P 500" assumption with
**historical point-in-time membership** for any backtest or validation
that uses dates pre-today. Without this fix, every Sharpe/IC/PBO/DSR
computation has survivorship bias: stocks that delisted or got dropped
from the index are silently excluded.

The cron's **forward** scoring uses current S&P 500 (correct) — this
fix is for **validation suite + IC backtest + PBO/DSR gates**.

## Files changed

- `data/sp500_membership_historical.csv` (NEW) — static CSV of (effective_date, ticker, action, source) tuples covering 2000-01-01 → present. Sourced from Wikipedia "List of S&P 500 companies" revision history + WSJ archives + S&P press releases. Each row carries `source_url` citation.
- `compute/ingest/historical_universe.py` (NEW) — `members_at(as_of_date: date) -> set[str]` returning the index membership on that date. Pure function, no I/O beyond loading the CSV once.
- `compute/validation/pbo_dsr.py` (MODIFY) — accept `universe_provider: Callable[[date], set[str]] | None = None` kwarg; default to current universe; pass historical provider when validating backtests.
- `compute/output/schemas.py` (MODIFY) — `Metadata.universe_membership_as_of: str | None` (ISO date) + `Metadata.survivorship_bias_corrected: bool` (informational flag, default True for forward cron / False+warning for stale runs).
- `frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json` (MODIFY) — triple lockstep.
- `tests/test_ingest/test_historical_universe.py` (NEW) — 12+ unit tests including known events (e.g., FTI added 2019-03-20, BLL removed 2024-08-30, etc.).

## Schema delta

PATCH bump: `0.10.5-phase4.5e` → `0.10.6-phase4.6`. Two additive optional
`Metadata` fields — no breaking change to consumers.

## Defense mode

N/A — not a defense flag. Validation-infrastructure fix.

## Tests

- Unit (12+): known add/remove events; date-range boundary; ticker-rename handling (e.g., `FB → META`); empty universe at pre-1957 date.
- Hypothesis property: for any date D in [2000-01-01, today], `len(members_at(D))` ∈ [490, 510] (S&P 500 always ~500 ±10 transitions).
- Golden value: NVDA membership history verified (joined SOX index 2000, S&P 500 2001-11-30); AAPL (always-in since 1982); SVB (in 2004-12-01 until 2023-03-13 collapse — must show OUT after that date); TSLA (in 2020-12-21 onward).
- @network smoke (1 test): hit Wikipedia revision-history API for sanity (skipped if no internet).

## Production verification

- `Metadata.universe_membership_as_of` matches today's date in forward cron
- `Metadata.survivorship_bias_corrected = True` for forward cron
- Backtest harness (when used) emits `Metadata.survivorship_bias_corrected = True` AND a non-current `universe_membership_as_of`
- Section A-L verify-helper passes (new Section M for membership consistency?)

## Fallback triggers

- If Wikipedia revision history scrape impractical (sandbox no internet OR API throttles): commit static CSV constructed from primary sources (S&P press releases dated 2000-present). User-pipeline explicitly authorizes this fallback.
- If CSV has gaps for date D: `members_at(D)` raises `MissingMembershipError` with the specific date. Loud failure, not silent fallback.

## Acceptance checklist

- [ ] `data/sp500_membership_historical.csv` committed with ≥ 600 (add/remove) events and source citations
- [ ] `compute/ingest/historical_universe.py` pure function; no side effects
- [ ] `compute/validation/pbo_dsr.factor_passes_gates()` accepts optional `universe_provider` and threads through; default = current
- [ ] Schema bump `0.10.5 → 0.10.6-phase4.6` atomic across Pydantic + TS + snapshot
- [ ] 12+ unit tests pass offline; suite count goes UP
- [ ] `ruff check .` clean
- [ ] `python -m compute.output.schema_check` clean
- [ ] Draft PR opened on `claude/phase-4.6-survivorship-bias-fix`
- [ ] Methodology citation: Hou-Xue-Zhang 2020 §"Replicating Anomalies" + McLean-Pontiff 2016 in module docstring

## License posture

- Wikipedia revision history: CC BY-SA 4.0 (data extracted, no copying of prose)
- WSJ / S&P press releases: factual list (uncopyrightable per Feist 1991) — citation only
- Static CSV: original compilation = our work, BSD-3 compatible per project license

## Methodology citation (anchor)

- Hou-Xue-Zhang 2020 RFS 33(5):2019-2133 — replication crisis evidence emphasizing survivorship as PRIMARY failure mode
- McLean-Pontiff 2016 JF 71(1):5-32 — 32% post-publication decay budget; survivorship correction is the first-order honest-estimate adjustment
