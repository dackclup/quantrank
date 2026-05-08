"""Phase 1 weekly compute orchestrator.

Pulls S&P 500 prices, computes 12-1 momentum, ranks stocks by cross-sectional
percentile, and writes ``rankings.json`` + ``metadata.json`` atomically.

Composite is momentum-only by design — real pillars land in Phase 3.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from compute import config
from compute.features.momentum import momentum_12_1
from compute.ingest.prices import fetch_prices
from compute.ingest.universe import get_sp500_constituents
from compute.output.schemas import Metadata, PillarScores, StockSummary
from compute.output.writer import write_metadata_json, write_rankings_json

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
        "current_price": current_price,
        "momentum_12_1": float(mom),
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_weekly_compute() -> int:
    """Run the full weekly compute. Returns the count of successfully scored tickers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger.info("Loading S&P 500 universe…")
    universe = get_sp500_constituents()
    logger.info("Universe size: %d", len(universe))

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
