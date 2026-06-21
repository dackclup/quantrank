"""Research warehouse maximum-history point-in-time backfill (Slice 2).

Replays the per-run ranking snapshot back to the membership-ledger floor
(~2016-06-01) one week at a time, writing ``row_provenance="pit_replay"``
Parquet rows into the warehouse backfill directory.

Purpose
-------
Produces a deep historical panel (2016→today) for factor/IC research and
Phase-5 ML training, in the same Parquet schema as the forward Slice-1
live snapshots so a single DuckDB / Polars read covers the full panel.

PIT-honesty guarantees
-----------------------
* No look-ahead: fundamentals must have ``filing_date <= run_date`` (10-K
  only via ``pit_snapshot_fields`` from ``compute.portfolio.pit_fundamentals``).
* Survivorship-correct: ``members_at(T)`` reverses ADD/REMOVE events from the
  S&P 500 membership ledger (``data/sp500_membership_historical.csv``), so
  tickers removed after date T are present in the as-of cross-section.
* Forward-only flags are NULL (not False): flags that cannot be reconstructed
  PIT (Form-4, 8-K non-reliance, live-ADV, post-split yfinance reconciliation,
  cross-source comparison, etc.) are written as NULL in replay rows to prevent
  ML models from reading an unconfirmed absence as a confirmed negative.  The
  ``FORWARD_ONLY_FLAGS`` registry in ``compute.warehouse.flag_registry`` declares
  the complete set.  ``replay_completeness`` (fraction of flag columns that are
  non-NULL) is included in each row as a diagnostic.

Replayed vetoes (from ``backfill_portfolio_pit._VETOES_REPLAYED``)
------------------------------------------------------------------
Six accounting-based active vetoes are replayed PIT — they derive only from
the already-loaded PIT snapshot + PIT history rows (no additional EDGAR calls):
  - data_quality_input_corruption
  - altman_distress
  - sloan_accruals_top_decile
  - net_issuance_top_decile
  - beneish_manipulation_veto
  - dechow_manipulation_veto

Annotates: genuinely replayed (True/False in replay rows)
-----------------------------------------------------------
The following ``valuation_warnings`` are derived from PIT-recoverable inputs
and ARE replayed as True/False (not NULL) in pit_replay rows:
  - value_trap_risk, goodwill_heavy (from ensemble Tier-1 defenses)
  - extreme_*_estimate, extreme_estimate_majority (from ensemble)

Annotates: NOT recomputed (NULL in replay rows)
------------------------------------------------
The following ``valuation_warnings`` are PIT-recoverable in principle but are
NOT recomputed by the current backfill — written as NULL (not False) so
downstream ML models never read an unconfirmed absence as a confirmed negative.
Declared in ``BACKFILL_UNCOMPUTED_ANNOTATES`` in ``compute.warehouse.flag_registry``.
Genuine recompute is a future enhancement (Slice 3+):
  - restatement_history, restatement_high_confidence (EDGAR amendment fetches)
  - late_filing_notification (NT filing detection)
  - rem_suspect, accruals_momentum_high (main.py per-ticker loop)
  - loss_avoidance_pattern, loss_avoidance_pattern_size_invariant (main.py loop)
  - beneish_high, dechow_high (warning-band annotation; the VETO is replayed)
  - manipulation_triple_flag (depends on beneish_high + dechow_high)
  - share_count_extraction_missing (main.py writer step; RawMetrics all-None PIT)
  - valuation_output_anomalous (main.py writer step DQIC co-fire)

Forward-only flags (NULL in replay rows — no historical record exists)
-----------------------------------------------------------------------
Declared in ``FORWARD_ONLY_FLAGS`` in ``compute.warehouse.flag_registry``.
Sources: 8-K Item-4.02 feed, Form-4 insider data, live trailing-30d ADV,
live cross-source yfinance comparison, live post-split yfinance reconciliation.
See FORWARD_ONLY_FLAGS docstring for the complete list.

Honest limits (encoded here + in --help)
-----------------------------------------
1. SP500-ONLY before sp900/sp1500 go-live (no historical mid/small-cap ledger
   exists).  The backfill universe is always SP500.  sp900/sp1500 rows exist
   only in the Slice-1 live forward snapshots from their real go-live dates.
2. Forward-only flags are NULL (see above and FORWARD_ONLY_FLAGS registry).
3. Recommendation and loss_chance in replay rows derive from PIT-recoverable
   inputs only and WILL differ from any live value because forward-only flags
   are absent.  ``row_provenance="pit_replay"`` and ``replay_completeness``
   document this.
4. GICS sectors are assumed stable from today (same approximation as
   backfill_portfolio_pit.py — the historical sector parquet is a separate
   optional enrichment).
5. Fair-price hard-stale ceiling is relaxed to 455 days (same as
   BACKTEST_HARD_STALE_DAYS in backfill_portfolio_pit.py) to avoid nulling
   annual 10-K fundamentals 3 of 4 quarters.

Output layout
-------------
    <--out>/year=<YYYY>/run_date=<ISO>/part-0.parquet

This mirrors the Slice-1 snapshot layout under ``data/warehouse/snapshots/``
so the backfill directory can be combined with the live snapshots in a single
Hive-partitioned read.  The default ``--out`` is ``data/warehouse/backfill/``,
which the project's ``*.parquet`` .gitignore blanket already covers — this
directory MUST NOT be committed to git (it is an artifact, not source data).

Network requirements
--------------------
The script requires the on-disk EDGAR + yfinance caches populated by the CI
cron (``compute/cache/``).  It does NOT make live network calls itself (all
fetches use ``fetch_prices`` / ``fetch_fundamentals_history`` which read from
the warm cache).  Run under ``--run-network`` after the CI cache is warm, or
point at a CI cache artifact.

Usage
-----
    python -m scripts.backfill_warehouse \\
        [--start YYYY-MM-DD]  (default 2016-06-01, membership-ledger floor) \\
        [--end   YYYY-MM-DD]  (default today) \\
        [--cadence weekly]     (only "weekly" supported) \\
        [--out   PATH]         (default data/warehouse/backfill/) \\
        [--universe sp500]     (only "sp500" supported for backfill; see Limits)

CI/release artifact
--------------------
This script is intended to be run via ``workflow_dispatch`` on
``backfill-warehouse.yml`` (not yet written — orchestrator handles the workflow
file).  Its output is uploaded as a GitHub Actions artifact, NOT committed to
the repo.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Membership-ledger floor — same as BACKTEST_CANONICAL_START in
# backfill_portfolio_pit.py.  Anchored to the Track-B rebuild coverage start
# (data/sp500_membership_historical.csv, 2016-01-04) plus a buffer so the
# first weekly window has fundamentals + price history.
BACKFILL_DEFAULT_START: date = date(2016, 6, 1)

# Relaxed hard-stale ceiling for annual 10-K data (same as backfill_portfolio_pit.py).
# The live path uses config.FILING_STALE_HARD_DAYS (180d); for a once-a-year
# 10-K the legitimate gap is up to ~455d (SEC 75d deadline + 365d + 15d buffer).
BACKTEST_HARD_STALE_DAYS: int = 455

# The six accounting vetoes replayed PIT (see scripts/backfill_portfolio_pit.py
# _VETOES_REPLAYED for the canonical definition; reproduced here for self-containment).
# All derive from the already-loaded PIT snapshot + PIT history — no EDGAR fetching.
_VETOES_REPLAYED: tuple[str, ...] = (
    "data_quality_input_corruption",
    "altman_distress",
    "sloan_accruals_top_decile",
    "net_issuance_top_decile",
    "beneish_manipulation_veto",
    "dechow_manipulation_veto",
)

# Sigma lookback buffer for price fetch (same as backfill_portfolio_pit.py).
_SIGMA_LOOKBACK_BUFFER_DAYS: int = 185


# ---------------------------------------------------------------------------
# Weekly date generation
# ---------------------------------------------------------------------------

def _weekly_run_dates(start: date, end: date) -> list[date]:
    """Return Fridays (or nearest preceding weekday) in [start, end].

    The live cron runs Mon-Fri; for the backfill we emit one date per week
    pinned to Friday so the weekly cross-section aligns with a typical
    end-of-week settle.  If the candidate Friday is a weekend (can't happen
    since Friday is always a weekday) we would adjust, but Fridays are always
    valid trading-day candidates for the fundamentals-lag computation.

    The first date in the series is the first Friday >= ``start``.
    """
    dates: list[date] = []
    # Advance to the first Friday on or after start.
    d = start
    while d.weekday() != 4:  # 4 = Friday
        d += timedelta(days=1)
    while d <= end:
        dates.append(d)
        d += timedelta(weeks=1)
    return dates


# ---------------------------------------------------------------------------
# PIT fundamentals helpers (reused from backfill_portfolio_pit.py pattern)
# ---------------------------------------------------------------------------

def _annual_rows(history) -> list[dict]:
    """Convert a pd.DataFrame annual history to plain dicts for PIT selectors."""
    if history is None or len(history) == 0:
        return []
    rows: list[dict] = []
    for r in history.itertuples(index=False):
        fd = getattr(r, "filing_date", None)
        rows.append(
            {
                "metric": getattr(r, "metric", None),
                "fiscal_year": getattr(r, "fiscal_year", None),
                "value": getattr(r, "value", None),
                "filing_date": fd.isoformat() if hasattr(fd, "isoformat") else fd,
                "form_type": getattr(r, "form_type", None),
            }
        )
    return rows


def _pit_snapshot(ticker: str, cik: str, rows: list[dict], as_of: str):
    """Build a FundamentalsSnapshot from the PIT-filtered rows."""
    import dataclasses

    from compute.ingest.fundamentals import FundamentalsSnapshot
    from compute.portfolio.pit_fundamentals import pit_snapshot_fields
    _snapshot_fields = {f.name for f in dataclasses.fields(FundamentalsSnapshot)}
    fields = {k: v for k, v in pit_snapshot_fields(rows, as_of).items() if k in _snapshot_fields}
    return FundamentalsSnapshot(ticker=ticker, cik=cik, **fields)


def _pit_filing_lag(rows: list[dict], as_of: str, as_of_date: date) -> int | None:
    """Days from the latest 10-K filed on/before as_of (annual PIT staleness)."""
    fds = [
        r["filing_date"]
        for r in rows
        if r.get("form_type") == "10-K"
        and isinstance(r.get("filing_date"), str)
        and r["filing_date"] <= as_of
    ]
    if not fds:
        return None
    return (as_of_date - date.fromisoformat(max(fds))).days


def _price_at(prices, as_of_ts) -> float | None:
    """Close price on the latest trading day on or before as_of."""
    if prices is None or len(prices) == 0:
        return None
    col = "Adj Close" if "Adj Close" in prices.columns else "Close"
    sliced = prices.loc[:as_of_ts, col]
    if len(sliced) == 0:
        return None
    val = sliced.iloc[-1]
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 0 else None


# ---------------------------------------------------------------------------
# Backfill writer: partition layout mirrors Slice-1 snapshots
# ---------------------------------------------------------------------------

def _write_backfill_partition(
    rows: list[dict],
    run_date: date,
    out_dir: Path,
) -> int:
    """Write one run_date's rows to the backfill partition directory.

    Layout: <out_dir>/year=<YYYY>/run_date=<ISO>/part-0.parquet

    Idempotent — overwrites if the partition already exists.

    Returns the number of rows written.
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not rows:
        logger.warning("_write_backfill_partition: no rows for %s — skipping", run_date)
        return 0

    # Stable column ordering (mirrors write_run_snapshot).
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    sorted_cols = sorted(all_keys)
    for row in rows:
        for col in sorted_cols:
            row.setdefault(col, None)

    df = pd.DataFrame(rows, columns=sorted_cols)
    table = pa.Table.from_pandas(df, preserve_index=False)

    year_str = str(run_date.year)
    iso_str = run_date.isoformat()
    partition_dir = out_dir / f"year={year_str}" / f"run_date={iso_str}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    part_path = partition_dir / "part-0.parquet"
    pq.write_table(table, part_path, compression="zstd")
    logger.info(
        "backfill_warehouse: wrote %d rows → %s (%.1f KB)",
        len(rows),
        part_path,
        part_path.stat().st_size / 1024,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Core replay: one run_date → list[dict] rows
# ---------------------------------------------------------------------------

def _replay_one_date(
    run_date: date,
    *,
    current_sp500: set[str],
    cik_by_ticker: dict[str, str],
    sector_by_ticker: dict[str, str],
    rows_by_ticker: dict[str, list[dict]],
    prices_by_ticker: dict[str, pd.DataFrame],  # noqa: F821
) -> list[dict]:
    """Compute PIT cross-section for run_date and return flat Parquet rows.

    For each ticker present in the SP500 at run_date:
      1. PIT snapshot from filed<=run_date annual rows.
      2. PIT price (close on/before run_date).
      3. Re-score 8 pillars cross-sectionally.
      4. Composite score (frozen PHASE3_EFFECTIVE_WEIGHTS).
      5. Replay 6 PIT-replayable vetoes against the as-of cross-section.
      6. Compute peer medians WITHIN the as-of cohort (no look-ahead).
      7. 6-method fair-price ensemble.
      8. Derive recommendation + loss_chance from PIT inputs.
      9. Flatten via flatten_stock with null_flags=FORWARD_ONLY_FLAGS +
         row_provenance="pit_replay".
    """

    import pandas as pd

    from compute.ingest.fundamentals import FundamentalsSnapshot
    from compute.ingest.historical_universe import members_at
    from compute.main import (
        _build_historical_metrics,
        _build_peer_groupings,
        _build_universe_metrics,
    )
    from compute.output.schemas import (
        DataQuality,
        RawMetrics,
        StockDetail,
    )
    from compute.scoring.beneish import compute_beneish
    from compute.scoring.composite import (
        PHASE3_EFFECTIVE_WEIGHTS,
        compute_composite,
        neutralize_pillar_scores,
    )
    from compute.scoring.dechow_f import compute_dechow_f
    from compute.scoring.loss_chance import derive_loss_chance
    from compute.scoring.pillars import TickerInputs, compute_all_pillars
    from compute.scoring.recommendation import derive_recommendation
    from compute.scoring.risk_overlay import compute_risk_flags
    from compute.valuation.ensemble import compute_fair_price_ensemble, ensemble_result_to_dict
    from compute.warehouse.flag_registry import BACKFILL_UNCOMPUTED_ANNOTATES, FORWARD_ONLY_FLAGS
    from compute.warehouse.flatten import flatten_stock

    as_of = run_date.isoformat()
    as_of_ts = pd.Timestamp(as_of)

    # --- 1. As-of universe (survivorship-correct) ---
    membership = members_at(run_date, current_universe=current_sp500)
    as_of_tickers = sorted(membership.tickers)

    if not as_of_tickers:
        logger.warning("backfill_warehouse: empty universe at %s — skipping", run_date)
        return []

    # --- 2. PIT snapshots + prices ---
    pit_snapshots: dict[str, FundamentalsSnapshot | None] = {}
    pit_histories: dict[str, pd.DataFrame | None] = {}
    pit_prices: dict[str, pd.DataFrame | None] = {}
    current_prices: dict[str, float | None] = {}

    for ticker in as_of_tickers:
        rows = rows_by_ticker.get(ticker, [])
        prices = prices_by_ticker.get(ticker)

        # PIT snapshot
        cik = cik_by_ticker.get(ticker, "")
        if rows and cik:
            try:
                snap = _pit_snapshot(ticker, cik, rows, as_of)
            except Exception as exc:  # noqa: BLE001
                logger.warning("backfill_warehouse: snapshot failed %s at %s: %s", ticker, run_date, exc)
                snap = None
        else:
            snap = None
        pit_snapshots[ticker] = snap

        # PIT history DataFrame (filed<=run_date, for Beneish/Dechow/NSI)
        if rows:
            try:
                filtered_rows = [r for r in rows if isinstance(r.get("filing_date"), str) and r["filing_date"] <= as_of]
                if filtered_rows:
                    pit_histories[ticker] = pd.DataFrame(filtered_rows)
                else:
                    pit_histories[ticker] = None
            except Exception:  # noqa: BLE001
                pit_histories[ticker] = None
        else:
            pit_histories[ticker] = None

        # PIT price
        pit_prices[ticker] = prices
        cp = _price_at(prices, as_of_ts)
        current_prices[ticker] = cp

    # Drop tickers with no price (can't score without a current_price)
    scorable_tickers = [t for t in as_of_tickers if current_prices.get(t) is not None]
    if not scorable_tickers:
        logger.warning("backfill_warehouse: no scorable tickers at %s", run_date)
        return []

    # --- 3. Build TickerInputs for cross-sectional pillar scoring ---
    # SPY benchmark: use an empty DataFrame if not available (momentum/risk
    # pillars will degrade gracefully to NaN).
    spy_prices = prices_by_ticker.get("SPY")
    ticker_inputs: dict[str, TickerInputs] = {}
    for ticker in scorable_tickers:
        ticker_inputs[ticker] = TickerInputs(
            snapshot=pit_snapshots.get(ticker),
            prices=pit_prices.get(ticker),
            benchmark_prices=spy_prices,
            current_price=float(current_prices[ticker]),  # type: ignore[arg-type]
            sector=sector_by_ticker.get(ticker, "Unknown"),
            history=pit_histories.get(ticker),
        )

    # --- 4. Cross-sectional pillar scores + composite ---
    pillar_df = compute_all_pillars(ticker_inputs)
    if pillar_df.empty:
        logger.warning("backfill_warehouse: pillar_df empty at %s", run_date)
        return []

    pillar_df_neutralized, _imputed = neutralize_pillar_scores(pillar_df)
    composite_scores = compute_composite(pillar_df_neutralized, weights=PHASE3_EFFECTIVE_WEIGHTS)

    # --- 5. Replay the 6 PIT-replayable vetoes ---
    # Beneish + Dechow require pre-computation (see compute_risk_flags signature).
    beneish_scores: dict[str, float | None] = {}
    dechow_scores: dict[str, float | None] = {}
    for ticker in scorable_tickers:
        snap = pit_snapshots.get(ticker)
        hist_df = pit_histories.get(ticker)
        try:
            beneish_scores[ticker] = compute_beneish(snap, hist_df)
        except Exception:  # noqa: BLE001
            beneish_scores[ticker] = None
        try:
            dechow_scores[ticker] = compute_dechow_f(snap, hist_df)
        except Exception:  # noqa: BLE001
            dechow_scores[ticker] = None

    # non_reliance_by_ticker = all False (not replayed PIT — forward-only).
    nr_map = {t: False for t in scorable_tickers}
    sectors_for_risk = {t: sector_by_ticker.get(t, "Unknown") for t in scorable_tickers}
    risk_flags_by_ticker = compute_risk_flags(
        snapshots={t: pit_snapshots.get(t) for t in scorable_tickers},
        histories={t: pit_histories[t] for t in scorable_tickers if pit_histories.get(t) is not None},
        sectors=sectors_for_risk,
        today=run_date,
        non_reliance_by_ticker=nr_map,
        beneish_m_scores=beneish_scores,
        dechow_f_scores=dechow_scores,
    )

    # --- 6. Cross-sectional valuation inputs ---
    # Build a minimal DataFrame with ticker + current_price + sector so the
    # main.py universe/peer helpers work without the full live DataFrame.
    universe_df = pd.DataFrame([
        {
            "ticker": t,
            "current_price": current_prices[t],
            "sector": sector_by_ticker.get(t, "Unknown"),
            "industry": None,  # sub_industry not available in backfill
        }
        for t in scorable_tickers
    ])
    universe_metrics = _build_universe_metrics(
        {t: pit_snapshots.get(t) for t in scorable_tickers},
        universe_df,
    )
    by_sub_industry, by_sector, broad_ex_fin_util = _build_peer_groupings(universe_df)
    peer_panels = {
        "sub_industry": by_sub_industry,
        "sector": by_sector,
        "broad_ex_fin_util": {"broad_ex_fin_util": broad_ex_fin_util},
    }
    historical_metrics = _build_historical_metrics(
        {t: pit_histories[t] for t in scorable_tickers if pit_histories.get(t) is not None},
        {t: pit_snapshots.get(t) for t in scorable_tickers},
    )

    # --- 7. Per-ticker fair-price ensemble + flatten ---
    rows_out: list[dict] = []
    # Sort by composite to assign rank.
    ranked = sorted(scorable_tickers, key=lambda t: -float(composite_scores.get(t, 0.0)))

    for rank, ticker in enumerate(ranked, start=1):
        snap = pit_snapshots.get(ticker)
        if snap is None:
            # No usable fundamentals: skip (fundamentals_unavailable would
            # fire live; in the backfill we simply omit the row).
            continue

        cp = float(current_prices[ticker])  # type: ignore[arg-type]
        sector = sector_by_ticker.get(ticker, "Unknown")
        filing_lag = _pit_filing_lag(rows_by_ticker.get(ticker, []), as_of, run_date)

        # Pillar scores for this ticker.
        pillar_vals = pillar_df_neutralized.loc[ticker] if ticker in pillar_df_neutralized.index else None
        if pillar_vals is None:
            continue

        try:
            ensemble_result, ensemble_risk_flags = compute_fair_price_ensemble(
                ticker=ticker,
                snap=snap,
                sector=sector,
                sub_industry=None,
                industry=None,
                current_price=cp,
                filing_lag_days_value=filing_lag,
                peer_panels=peer_panels,
                universe_metrics=universe_metrics,
                historical_metrics=historical_metrics,
                hard_stale_days=BACKTEST_HARD_STALE_DAYS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("backfill_warehouse: ensemble failed %s at %s: %s", ticker, run_date, exc)
            from compute.valuation.ensemble import EnsembleResult
            ensemble_result = EnsembleResult(
                methods={},
                median=None,
                max=None,
                low=None,
                high=None,
                mos_pct=None,
                valuation_warnings=[],
            )
            ensemble_risk_flags = []

        # Merge risk flags (risk_overlay + ensemble).
        replay_rf = list(risk_flags_by_ticker.get(ticker, []))
        for flag in ensemble_risk_flags:
            if flag not in replay_rf:
                replay_rf.append(flag)

        # Valuation warnings from the ensemble.
        replay_vw = list(ensemble_result.valuation_warnings)

        # Recommendation + loss_chance (PIT-derived).
        composite_score = float(composite_scores.get(ticker, 0.0))
        fair_price_dict = ensemble_result_to_dict(ensemble_result)

        try:
            recommendation = derive_recommendation(
                composite_score=composite_score,
                mos_pct=ensemble_result.mos_pct,
                risk_flags=replay_rf,
                valuation_warnings=replay_vw,
            )
        except Exception:  # noqa: BLE001
            recommendation = "neutral"

        try:
            loss_chance = derive_loss_chance(
                composite_score=composite_score,
                mos_pct=ensemble_result.mos_pct,
                risk_flags=replay_rf,
                valuation_warnings=replay_vw,
            )
        except Exception:  # noqa: BLE001
            loss_chance = None

        # Build minimal DataQuality (PIT-derived; imputed_metrics unknown in backfill).
        dq = DataQuality(
            missing_metrics=[],
            imputed_metrics=[],
            filing_lag_days=filing_lag,
        )

        # Build PillarScores from the neutralized DataFrame.
        from compute.output.schemas import PillarScores as _PS
        ps_kwargs = {}
        for field_name in _PS.model_fields:
            ps_kwargs[field_name] = float(pillar_vals[field_name]) if field_name in pillar_vals.index else None
        pillar_scores = _PS(**ps_kwargs)

        # Build RawMetrics (all None in the backfill — raw metrics require the
        # full live ingest path which includes TTM derivation not available PIT).
        rm = RawMetrics(**{f: None for f in RawMetrics.model_fields})

        # Assemble StockDetail.
        detail = StockDetail(
            ticker=ticker,
            name=ticker,  # Name not available PIT; ticker used as placeholder.
            sector=sector,
            recommendation=recommendation,
            rank=rank,
            composite_score=composite_score,
            current_price=cp,
            pillar_scores=pillar_scores,
            raw_metrics=rm,
            data_quality=dq,
            risk_flags=replay_rf,
            valuation_warnings=replay_vw,
            fair_price=fair_price_dict,
            index_membership="sp500",
            index_memberships=["sp500"],
            loss_chance_pct=loss_chance,
        )

        # Flatten with ALL non-evaluated flags → NULL and pit_replay provenance.
        # null_flags = union of:
        #   FORWARD_ONLY_FLAGS            — no historical record (8-K, Form-4,
        #                                   live-ADV, cross-source, post-split)
        #   BACKFILL_UNCOMPUTED_ANNOTATES — PIT-recoverable in principle but
        #                                   not recomputed by this backfill
        # Writing NULL (not False) prevents ML models from reading an
        # unconfirmed absence as a confirmed negative.
        flat_row = flatten_stock(
            detail,
            None,  # no StockSummary in backfill
            null_flags=FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES,
            row_provenance="pit_replay",
        )
        rows_out.append(flat_row)

    logger.info(
        "backfill_warehouse: %s → %d rows (universe=%d scorable=%d)",
        run_date,
        len(rows_out),
        len(as_of_tickers),
        len(scorable_tickers),
    )
    return rows_out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_backfill(
    start: date,
    end: date,
    *,
    out_dir: Path,
    universe: str = "sp500",
) -> dict:
    """Run the full warehouse backfill from start to end.

    Parameters
    ----------
    start : date
        First weekly run_date to replay.
    end : date
        Last weekly run_date to replay (inclusive if it falls on a Friday).
    out_dir : Path
        Backfill artifact directory.  Created if absent.
    universe : str
        Must be "sp500" — the only universe with a historical membership
        ledger (SP500 Track-B, 2016-01-04→present).

    Returns
    -------
    dict
        Summary: ``{"dates_processed": N, "total_rows": M, "skipped": K}``.
    """
    import pandas as pd

    from compute.ingest.fundamentals import fetch_fundamentals_history
    from compute.ingest.prices import fetch_prices
    from compute.ingest.universe import get_sp500_constituents

    if universe != "sp500":
        raise ValueError(
            f"backfill_warehouse: universe={universe!r} is not supported.  "
            "Only 'sp500' has a historical membership ledger (data/sp500_membership_historical.csv "
            "Track-B, 2016-01-04→present).  sp900/sp1500 rows exist only in the "
            "Slice-1 live forward snapshots from their real go-live dates."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "backfill_warehouse: start=%s end=%s universe=%s out=%s",
        start, end, universe, out_dir,
    )

    # --- Load current SP500 constituents (anchor for members_at) ---
    members_df = get_sp500_constituents()
    current_sp500: set[str] = {str(r.ticker) for r in members_df.itertuples(index=False)}
    cik_by_ticker: dict[str, str] = {str(r.ticker): str(r.cik) for r in members_df.itertuples(index=False)}
    sector_by_ticker: dict[str, str] = {str(r.ticker): str(r.sector) for r in members_df.itertuples(index=False)}

    # --- Pre-fetch: load each name's caches ONCE ---
    price_floor = start - timedelta(days=_SIGMA_LOOKBACK_BUFFER_DAYS)
    logger.info("backfill_warehouse: pre-fetching %d current tickers (price floor=%s)", len(current_sp500), price_floor)

    rows_by_ticker: dict[str, list[dict]] = {}
    prices_by_ticker: dict[str, pd.DataFrame] = {}

    for ticker in sorted(current_sp500):
        try:
            hist = fetch_fundamentals_history(cik_by_ticker[ticker])
            rows_by_ticker[ticker] = _annual_rows(hist)
        except Exception as exc:  # noqa: BLE001
            logger.warning("backfill_warehouse: fundamentals load failed %s: %s", ticker, exc)
            rows_by_ticker[ticker] = []
        try:
            pf = fetch_prices(ticker, period="max", min_start=price_floor)
            if pf is not None and len(pf) > 0:
                prices_by_ticker[ticker] = pf
        except Exception as exc:  # noqa: BLE001
            logger.warning("backfill_warehouse: prices load failed %s: %s", ticker, exc)

    # Also load SPY for benchmark (momentum/risk pillars).
    try:
        spy = fetch_prices("SPY", period="max", min_start=price_floor)
        if spy is not None and len(spy) > 0:
            prices_by_ticker["SPY"] = spy
    except Exception as exc:  # noqa: BLE001
        logger.warning("backfill_warehouse: SPY prices load failed: %s", exc)

    logger.info(
        "backfill_warehouse: pre-fetch complete — %d tickers with fundamentals, %d with prices",
        sum(1 for r in rows_by_ticker.values() if r),
        len(prices_by_ticker),
    )

    # --- Weekly replay loop ---
    run_dates = _weekly_run_dates(start, end)
    logger.info("backfill_warehouse: %d weekly dates to replay", len(run_dates))

    total_rows = 0
    skipped = 0

    for run_date in run_dates:
        try:
            rows = _replay_one_date(
                run_date,
                current_sp500=current_sp500,
                cik_by_ticker=cik_by_ticker,
                sector_by_ticker=sector_by_ticker,
                rows_by_ticker=rows_by_ticker,
                prices_by_ticker=prices_by_ticker,
            )
            n = _write_backfill_partition(rows, run_date, out_dir)
            total_rows += n
            if n == 0:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("backfill_warehouse: FAILED at %s: %s — skipping", run_date, exc)
            skipped += 1

    result = {
        "dates_processed": len(run_dates) - skipped,
        "total_rows": total_rows,
        "skipped": skipped,
    }
    logger.info("backfill_warehouse: DONE — %s", result)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.backfill_warehouse",
        description=(
            "Research warehouse maximum-history PIT backfill (Slice 2). "
            "Replays the SP500 cross-section weekly from ~2016-06-01 to today "
            "and writes row_provenance='pit_replay' Parquet partitions to --out. "
            "\n\n"
            "HONEST LIMITS: "
            "(1) SP500-ONLY — no historical mid/small-cap membership ledger exists; "
            "(2) Forward-only flags (Form-4, 8-K non-reliance, live-ADV, "
            "post-split yfinance, cross-source) are written as NULL — NOT False — "
            "in replay rows; "
            "(3) GICS sectors are assumed stable from today (same approximation "
            "as backfill_portfolio_pit.py); "
            "(4) Fair-price hard-stale ceiling is relaxed to 455 days so annual "
            "10-K fundamentals are not auto-nulled 3 of 4 quarters; "
            "(5) Requires warm on-disk EDGAR + yfinance caches (compute/cache/); "
            "(6) Output written to --out (default data/warehouse/backfill/) which "
            "is gitignored — DO NOT commit this directory."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--start",
        default=BACKFILL_DEFAULT_START.isoformat(),
        help=(
            f"First replay date (default: {BACKFILL_DEFAULT_START} — membership-ledger floor). "
            "Must be >= 2016-01-01 (Track-B coverage start)."
        ),
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="Last replay date (default: today).",
    )
    parser.add_argument(
        "--cadence",
        default="weekly",
        choices=["weekly"],
        help="Replay cadence (default: weekly; only 'weekly' supported).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output directory for backfill Parquet partitions. "
            "Default: data/warehouse/backfill/ (gitignored, never committed). "
            "Mirror layout: year=<YYYY>/run_date=<ISO>/part-0.parquet."
        ),
    )
    parser.add_argument(
        "--universe",
        default="sp500",
        choices=["sp500"],
        help=(
            "Universe to replay (default: sp500). Only 'sp500' supported: "
            "the SP500 membership ledger (data/sp500_membership_historical.csv) "
            "covers 2016-01-04→present. sp900/sp1500 have no historical ledger — "
            "their rows are written by the Slice-1 live forward snapshots."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code 0=ok, 1=error."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parse_args(argv)

    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    except ValueError as exc:
        logger.error("Invalid date: %s", exc)
        return 1

    if start > end:
        logger.error("--start %s > --end %s", start, end)
        return 1

    # Resolve output directory.
    from compute import config
    out_dir: Path
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = config.PROJECT_ROOT / "data" / "warehouse" / "backfill"

    try:
        result = run_backfill(start, end, out_dir=out_dir, universe=args.universe)
        logger.info("backfill_warehouse: result=%s", result)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("backfill_warehouse: FATAL: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
