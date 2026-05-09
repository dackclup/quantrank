"""Phase 3b weekly compute orchestrator.

Pipeline:
1. Universe (S&P 500 from Wikipedia, cached)
2. Prices (yfinance, parallel) + SPY benchmark for beta
3. Fundamentals snapshot (SEC EDGAR, parallel)
4. Annual fundamentals history (SEC EDGAR, parallel) — feeds growth CAGRs
5. 8-pillar scoring via ``compute.scoring.pillars``
6. NaN pillar imputation (50.0 = neutral) per SKILL.md Rule 7
7. 10-pillar weighted composite (sentiment+ml redistributed pro-rata)
8. Risk overlay flags (annotate-only)
9. Sort by composite, assign rank
10. Top-5 rotation: compare to previous rankings.json; flagged stocks
    cannot earn ``entered_top5`` even if their rank ≤ 5
11. Atomic writes: rankings.json, metadata.json, stocks/{TICKER}.json
"""

from __future__ import annotations

import logging
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from compute import config
from compute.ingest.fundamentals import (
    ALL_METRIC_KEYS,
    FundamentalsSnapshot,
    fetch_fundamentals,
    fetch_fundamentals_history,
)
from compute.ingest.prices import fetch_prices, fetch_spy_benchmark
from compute.ingest.universe import get_sp500_constituents
from compute.output.schemas import (
    DataQuality,
    Metadata,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)
from compute.output.writer import (
    read_previous_top5,
    write_metadata_json,
    write_rankings_json,
    write_stock_detail,
)
from compute.scoring.composite import compute_composite, neutralize_pillar_scores
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.risk_overlay import compute_risk_flags

logger = logging.getLogger(__name__)


def _resolve_close_column(prices: pd.DataFrame) -> str | None:
    if "Adj Close" in prices.columns:
        return "Adj Close"
    if "Close" in prices.columns:
        return "Close"
    return None


def _fetch_prices_one(row: pd.Series) -> dict | None:
    """Fetch prices + extract last close for one ticker."""
    ticker = row["ticker"]
    prices = fetch_prices(ticker)
    if prices is None or prices.empty:
        return None
    col = _resolve_close_column(prices)
    if col is None:
        return None
    last = prices[col].dropna()
    if last.empty:
        return None
    current = float(last.iloc[-1])
    if math.isnan(current) or current <= 0:
        return None
    return {
        "ticker": ticker,
        "name": row["name"],
        "sector": row["sector"],
        "industry": row.get("sub_industry"),
        "cik": row.get("cik"),
        "current_price": current,
        "_prices": prices,
    }


def _fundamentals_one(ticker: str, cik: str) -> FundamentalsSnapshot | None:
    try:
        return fetch_fundamentals(ticker, cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals raised for %s/%s: %s", ticker, cik, e)
        return None


def _history_one(cik: str) -> pd.DataFrame:
    if not cik:
        return pd.DataFrame()
    try:
        return fetch_fundamentals_history(cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals_history raised for cik=%s: %s", cik, e)
        return pd.DataFrame()


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_raw_metrics(
    snapshot: FundamentalsSnapshot | None, current_price: float
) -> RawMetrics:
    if snapshot is None:
        return RawMetrics()
    market_cap = (
        current_price * snapshot.shares_outstanding
        if snapshot.shares_outstanding is not None
        else None
    )
    pe_ttm = (
        current_price / snapshot.eps_diluted
        if snapshot.eps_diluted is not None and snapshot.eps_diluted > 0
        else None
    )
    return RawMetrics(
        revenue=snapshot.revenue,
        net_income=snapshot.net_income,
        total_assets=snapshot.total_assets,
        total_liabilities=snapshot.total_liabilities,
        stockholders_equity=snapshot.stockholders_equity,
        cash=snapshot.cash,
        operating_cash_flow=snapshot.operating_cash_flow,
        capex=snapshot.capex,
        free_cash_flow=snapshot.free_cash_flow,
        eps_basic=snapshot.eps_basic,
        eps_diluted=snapshot.eps_diluted,
        shares_outstanding=snapshot.shares_outstanding,
        market_cap=market_cap,
        pe_ratio_ttm=pe_ttm,
    )


def _build_data_quality(
    snapshot: FundamentalsSnapshot | None,
    today: datetime,
    imputed_pillars: list[str],
) -> DataQuality:
    if snapshot is None:
        return DataQuality(
            missing_metrics=list(ALL_METRIC_KEYS),
            imputed_metrics=imputed_pillars,
        )
    filing_lag: int | None = None
    if snapshot.latest_filed_date is not None:
        filing_lag = (today.date() - snapshot.latest_filed_date).days
    return DataQuality(
        missing_metrics=snapshot.missing_fields(),
        imputed_metrics=imputed_pillars,
        filing_lag_days=filing_lag,
        latest_period_end=str(snapshot.latest_period_end)
        if snapshot.latest_period_end
        else None,
        latest_filed_date=str(snapshot.latest_filed_date)
        if snapshot.latest_filed_date
        else None,
    )


def _pillar_scores_to_schema(row: pd.Series) -> PillarScores:
    """Convert a one-ticker pillar score row into a PillarScores model.

    Rounds to 2 decimals; null pillars (sentiment, ml) stay None.
    """
    def r(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return round(float(v), 2)

    return PillarScores(
        quality=r(row.get("quality")),
        value=r(row.get("value")),
        growth=r(row.get("growth")),
        momentum=r(row.get("momentum")),
        health=r(row.get("health")),
        profitability=r(row.get("profitability")),
        technical=r(row.get("technical")),
        risk=r(row.get("risk")),
        sentiment=None,
        ml=None,
    )


def run_weekly_compute() -> int:
    """Run the full weekly compute. Returns the count of successfully scored tickers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger.info("Loading S&P 500 universe…")
    universe = get_sp500_constituents()
    logger.info("Universe size: %d", len(universe))

    logger.info("Fetching SPY benchmark for beta…")
    benchmark = fetch_spy_benchmark()
    if benchmark is None or benchmark.empty:
        logger.warning("SPY benchmark unavailable — beta will be NaN for all tickers")
        benchmark = None

    # Step 1 — prices in parallel.
    rows: list[dict] = []
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=config.MAX_PARALLEL_FETCHES) as ex:
        futures = {
            ex.submit(_fetch_prices_one, row): row["ticker"]
            for _, row in universe.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.warning("Price fetch failed for %s: %s", ticker, e)
                continue
            if result is not None:
                prices_by_ticker[ticker] = result.pop("_prices")
                rows.append(result)

    logger.info("Fetched prices for %d / %d tickers", len(rows), len(universe))
    if len(rows) < config.MIN_VALID_TICKERS:
        logger.error(
            "Only %d tickers priced — below minimum of %d. Aborting without writing JSON "
            "to preserve last-good data.",
            len(rows),
            config.MIN_VALID_TICKERS,
        )
        return 0

    df = pd.DataFrame(rows)
    df = df.set_index("ticker", drop=False)

    # Step 2 — fundamentals snapshot in parallel.
    logger.info(
        "Fetching fundamentals for %d tickers (max_workers=%d)…",
        len(df),
        config.EDGAR_MAX_WORKERS,
    )
    snapshots: dict[str, FundamentalsSnapshot | None] = {}
    with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as ex:
        futures = {
            ex.submit(_fundamentals_one, r["ticker"], str(r.get("cik") or "")): r["ticker"]
            for _, r in df.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                snap = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.warning("Fundamentals task raised for %s: %s", ticker, e)
                snap = None
            snapshots[ticker] = snap

    coverage = sum(1 for v in snapshots.values() if v is not None) / max(len(df), 1)
    logger.info(
        "Fundamentals coverage: %d / %d (%.1f%%)",
        sum(1 for v in snapshots.values() if v is not None),
        len(df),
        coverage * 100,
    )
    if coverage < config.MIN_FUNDAMENTALS_COVERAGE:
        logger.error(
            "Fundamentals coverage %.1f%% below threshold %.1f%%. Aborting.",
            coverage * 100,
            config.MIN_FUNDAMENTALS_COVERAGE * 100,
        )
        return 0

    # Step 3 — annual history in parallel (feeds growth CAGRs).
    logger.info("Fetching annual fundamentals history…")
    histories: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as ex:
        futures = {
            ex.submit(_history_one, str(r.get("cik") or "")): r["ticker"]
            for _, r in df.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                histories[ticker] = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.warning("History task raised for %s: %s", ticker, e)
                histories[ticker] = pd.DataFrame()

    # Step 4 — assemble TickerInputs and compute all pillars.
    inputs: dict[str, TickerInputs] = {}
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        inputs[ticker] = TickerInputs(
            snapshot=snapshots.get(ticker),
            prices=prices_by_ticker.get(ticker),
            benchmark_prices=benchmark,
            current_price=float(r["current_price"]),
            sector=str(r["sector"]),
            history=histories.get(ticker),
        )

    logger.info("Computing pillar scores for %d tickers…", len(inputs))
    pillar_df = compute_all_pillars(inputs)
    pillar_df, imputed_by_ticker = neutralize_pillar_scores(pillar_df)

    # Step 5 — composite + risk flags. NSI flag (Defense Playbook §PR 3c §1)
    # requires per-ticker history + sector to compute within-sector top-decile
    # threshold, so we pass both into compute_risk_flags. Top-5 rotation below
    # already iterates risk_flags.get(ticker) → no change needed there for NSI
    # to enter the existing flagged-skip path (annotate-and-veto-Top-N pattern,
    # SKILL.md Rule 16).
    composite = compute_composite(pillar_df)
    sectors_dict = {t: inp.sector for t, inp in inputs.items()}
    risk_flags = compute_risk_flags(
        snapshots,
        histories=histories,
        sectors=sectors_dict,
    )

    # Step 6 — assemble ranking DataFrame.
    df = df.assign(composite_score=composite.reindex(df.index).fillna(0.0))
    df = df.sort_values(
        "composite_score", ascending=False, kind="mergesort"
    ).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)

    # Step 7 — Top-5 rotation. Flagged stocks never earn entered_top5
    # regardless of rank (per PR-3b veto enforcement decision 2026-05-08).
    previous_top5 = read_previous_top5(config.DATA_DIR)
    current_top5: list[str] = []
    for _, r in df.iterrows():
        if len(current_top5) >= 5:
            break
        ticker = str(r["ticker"])
        if risk_flags.get(ticker):
            continue  # skip flagged stocks even if they'd qualify
        current_top5.append(ticker)
    current_top5_set = set(current_top5)
    entered = current_top5_set - previous_top5
    exited = previous_top5 - current_top5_set
    logger.info(
        "Top-5 rotation: entered=%s exited=%s (flagged-skipped count=%d)",
        sorted(entered),
        sorted(exited),
        sum(1 for f in risk_flags.values() if f),
    )

    # Step 8 — assemble StockSummary list.
    summaries: list[StockSummary] = []
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        pillar_row = pillar_df.loc[ticker] if ticker in pillar_df.index else pd.Series(dtype=float)
        summaries.append(
            StockSummary(
                rank=int(r["rank"]),
                ticker=ticker,
                name=str(r["name"]),
                sector=str(r["sector"]),
                composite_score=round(float(r["composite_score"]), 2),
                current_price=round(float(r["current_price"]), 4),
                pillar_scores=_pillar_scores_to_schema(pillar_row),
                risk_flags=risk_flags.get(ticker, []),
                entered_top5=ticker in entered,
                exited_top5=ticker in exited,
            )
        )

    now = _now_utc()

    # Step 9 — per-stock detail JSON.
    detail_count = 0
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        snap = snapshots.get(ticker)
        raw_metrics = _build_raw_metrics(snap, float(r["current_price"]))
        imputed = imputed_by_ticker.get(ticker, [])
        pillar_row = pillar_df.loc[ticker] if ticker in pillar_df.index else pd.Series(dtype=float)
        detail = StockDetail(
            ticker=ticker,
            name=str(r["name"]),
            sector=str(r["sector"]),
            industry=(r.get("industry") if pd.notna(r.get("industry")) else None),
            market_cap=raw_metrics.market_cap,
            current_price=round(float(r["current_price"]), 4),
            rank=int(r["rank"]),
            composite_score=round(float(r["composite_score"]), 2),
            pillar_scores=_pillar_scores_to_schema(pillar_row),
            raw_metrics=raw_metrics,
            data_quality=_build_data_quality(snap, now, imputed),
            risk_flags=risk_flags.get(ticker, []),
            entered_top5=ticker in entered,
            exited_top5=ticker in exited,
        )
        write_stock_detail(detail, config.DATA_DIR)
        detail_count += 1
    logger.info("Wrote %d stock detail JSON files", detail_count)

    meta = Metadata(
        version=config.SCHEMA_VERSION,
        last_update_utc=_iso(now),
        next_update_utc=_iso(now + timedelta(days=7)),
        universe=config.UNIVERSE,
        universe_size=len(summaries),
        compute_run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        git_commit=(os.environ.get("GITHUB_SHA") or "unknown")[:40],
    )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_rankings_json(summaries, config.DATA_DIR)
    write_metadata_json(meta, config.DATA_DIR)
    logger.info("Wrote rankings.json (%d rows) and metadata.json", len(summaries))
    return len(summaries)


if __name__ == "__main__":
    sys.exit(0 if run_weekly_compute() > 0 else 1)
