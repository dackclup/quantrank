"""Phase 2 weekly compute orchestrator.

Pulls S&P 500 prices + 12-1 momentum (Phase 1), then SEC EDGAR fundamentals
(Phase 2). Writes ``rankings.json``, ``metadata.json``, and per-stock
``stocks/{TICKER}.json`` atomically.

Composite stays momentum-only — real pillars land in Phase 3.
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
from compute.features.momentum import momentum_12_1
from compute.ingest.fundamentals import (
    ALL_METRIC_KEYS,
    FundamentalsSnapshot,
    fetch_fundamentals,
)
from compute.ingest.prices import fetch_prices
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
    write_metadata_json,
    write_rankings_json,
    write_stock_detail,
)

logger = logging.getLogger(__name__)


def _score_one(row: pd.Series) -> dict | None:
    ticker = row["ticker"]
    prices = fetch_prices(ticker)
    if prices is None or prices.empty:
        return None

    mom = momentum_12_1(prices)
    if mom is None or (isinstance(mom, float) and math.isnan(mom)):
        return None

    close_col = "Adj Close" if "Adj Close" in prices.columns else "Close"
    last_price_series = prices[close_col].dropna()
    if last_price_series.empty:
        return None
    current_price = float(last_price_series.iloc[-1])
    if math.isnan(current_price) or current_price <= 0:
        return None

    return {
        "ticker": ticker,
        "name": row["name"],
        "sector": row["sector"],
        "industry": row.get("sub_industry"),
        "cik": row.get("cik"),
        "current_price": current_price,
        "momentum_12_1": float(mom),
    }


def _fundamentals_one(ticker: str, cik: str) -> FundamentalsSnapshot | None:
    try:
        return fetch_fundamentals(ticker, cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals raised for %s/%s: %s", ticker, cik, e)
        return None


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
    snapshot: FundamentalsSnapshot | None, today: datetime
) -> DataQuality:
    if snapshot is None:
        return DataQuality(missing_metrics=list(ALL_METRIC_KEYS))
    filing_lag: int | None = None
    if snapshot.latest_filed_date is not None:
        filing_lag = (today.date() - snapshot.latest_filed_date).days
    return DataQuality(
        missing_metrics=snapshot.missing_fields(),
        imputed_metrics=[],
        filing_lag_days=filing_lag,
        latest_period_end=str(snapshot.latest_period_end)
        if snapshot.latest_period_end
        else None,
        latest_filed_date=str(snapshot.latest_filed_date)
        if snapshot.latest_filed_date
        else None,
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

    # Phase 1 — prices + momentum
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.MAX_PARALLEL_FETCHES) as ex:
        futures = {ex.submit(_score_one, row): row["ticker"] for _, row in universe.iterrows()}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.warning("Scoring failed for %s: %s", ticker, e)
                continue
            if result is not None:
                rows.append(result)

    logger.info("Scored %d / %d tickers", len(rows), len(universe))

    if len(rows) < config.MIN_VALID_TICKERS:
        logger.error(
            "Only %d tickers scored — below minimum of %d. Aborting without writing JSON "
            "to preserve last-good data.",
            len(rows),
            config.MIN_VALID_TICKERS,
        )
        return 0

    df = pd.DataFrame(rows)
    df["composite_score"] = df["momentum_12_1"].rank(pct=True, method="average") * 100.0
    df = df.sort_values("composite_score", ascending=False, kind="mergesort").reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)

    # Phase 2 — fundamentals
    logger.info("Fetching fundamentals for %d tickers (max_workers=%d)…",
                len(df), config.EDGAR_MAX_WORKERS)
    snapshots: dict[str, FundamentalsSnapshot] = {}
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
                continue
            if snap is not None:
                snapshots[ticker] = snap

    coverage = len(snapshots) / max(len(df), 1)
    logger.info(
        "Fundamentals coverage: %d / %d (%.1f%%)",
        len(snapshots),
        len(df),
        coverage * 100,
    )
    if coverage < config.MIN_FUNDAMENTALS_COVERAGE:
        logger.error(
            "Fundamentals coverage %.1f%% below threshold %.1f%%. Aborting "
            "without writing JSON to preserve last-good data.",
            coverage * 100,
            config.MIN_FUNDAMENTALS_COVERAGE * 100,
        )
        return 0

    summaries: list[StockSummary] = [
        StockSummary(
            rank=int(r["rank"]),
            ticker=str(r["ticker"]),
            name=str(r["name"]),
            sector=str(r["sector"]),
            composite_score=round(float(r["composite_score"]), 2),
            current_price=round(float(r["current_price"]), 4),
            pillar_scores=PillarScores(momentum=round(float(r["composite_score"]), 2)),
        )
        for _, r in df.iterrows()
    ]

    now = _now_utc()

    # Per-stock detail JSON
    detail_count = 0
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        snap = snapshots.get(ticker)
        raw_metrics = _build_raw_metrics(snap, float(r["current_price"]))
        detail = StockDetail(
            ticker=ticker,
            name=str(r["name"]),
            sector=str(r["sector"]),
            industry=(r.get("industry") if pd.notna(r.get("industry")) else None),
            market_cap=raw_metrics.market_cap,
            current_price=round(float(r["current_price"]), 4),
            rank=int(r["rank"]),
            composite_score=round(float(r["composite_score"]), 2),
            pillar_scores=PillarScores(momentum=round(float(r["composite_score"]), 2)),
            raw_metrics=raw_metrics,
            data_quality=_build_data_quality(snap, now),
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
