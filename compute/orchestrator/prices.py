"""Step-1 parallel prices fetch helper for the weekly compute orchestrator.

Extracted from ``compute.main`` as part of PR #259-R2 (incremental refactor
of ``run_weekly_compute``).  The logic here is a PURE CODE MOVE — no
behaviour change, no reordering of effects, same exception handling, same
dict keys.  Output is byte-identical to the inline loop it replaces.

Public surface
--------------
``fetch_all_prices(universe, *, max_workers)``
    Run the parallelised Step-1 loop and return
    ``(rows, prices_by_ticker, adv_by_ticker)``.

Private helpers (moved verbatim from compute.main)
----------------------------------------------------
``_resolve_close_column(prices)``  — pick the best close column name.
``_fetch_prices_one(row)``         — fetch + package one ticker's data.

Thread-safety
-------------
``fetch_all_prices`` spawns a ``ThreadPoolExecutor`` with ``max_workers``
threads; the per-ticker results are accumulated on the main thread after each
future completes, exactly as the original inline loop did.  No new shared
state is introduced.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from compute import config
from compute.ingest.prices import compute_average_dollar_volume, fetch_prices

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helpers (moved verbatim from compute.main — DO NOT alter logic)
# ---------------------------------------------------------------------------


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
    # PR 4f follow-up — 1-day percent change for the ranking-table
    # quote line. Computed here so the per-stock JSON has the value
    # ready (no frontend fetch of 502 history files).
    price_change_1d_pct: float | None = None
    if len(last) >= 2:
        prev = float(last.iloc[-2])
        if not math.isnan(prev) and prev > 0:
            price_change_1d_pct = (current - prev) / prev * 100.0
    # S&P 1500 Slice 4 — compute ADV while we already hold the OHLCV
    # DataFrame.  No extra network round-trip; uses the already-cached frame.
    # Graceful degradation: compute_average_dollar_volume never raises.
    adv = compute_average_dollar_volume(prices, config.ADV_LOOKBACK_DAYS)
    return {
        "ticker": ticker,
        "name": row["name"],
        "sector": row["sector"],
        "industry": row.get("sub_industry"),
        "cik": row.get("cik"),
        # Phase 8 pilot PR 3a — carry cohort so index_membership propagates
        # into StockSummary / StockDetail without a second universe lookup.
        # "sp500" default keeps the sp500 path byte-identical.
        "cohort": row.get("cohort", "sp500"),
        "current_price": current,
        "price_change_1d_pct": price_change_1d_pct,
        "_prices": prices,
        # Slice 4 ADV (None when volume data unavailable — graceful degradation).
        "_adv": adv,
    }


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def fetch_all_prices(
    universe: pd.DataFrame,
    *,
    max_workers: int = config.MAX_PARALLEL_FETCHES,
) -> tuple[list[dict], dict[str, pd.DataFrame], dict[str, float | None]]:
    """Run the Step-1 parallel prices fetch loop over *universe*.

    Submits one ``_fetch_prices_one`` task per row using a
    ``ThreadPoolExecutor``.  Results are accumulated as each future
    completes (``as_completed``).  A per-future try/except logs a warning
    and skips the ticker on failure — exactly as the original inline loop.

    Parameters
    ----------
    universe:
        DataFrame with at least columns ``ticker``, ``name``, ``sector``.
        Must include ``cohort`` when running the sp900/sp1500 path
        (``row.get("cohort", "sp500")`` provides a safe default for the
        sp500 path).
    max_workers:
        Thread-pool size.  Defaults to ``config.MAX_PARALLEL_FETCHES``
        (currently 8, the empirical sweet-spot for the 10 req/s EDGAR
        ceiling — see ``compute/config.py``).

    Returns
    -------
    rows : list[dict]
        One dict per successfully priced ticker, with ``_prices`` and
        ``_adv`` already popped (they live in the two companion dicts).
    prices_by_ticker : dict[str, pd.DataFrame]
        Keyed by ticker; value is the OHLCV DataFrame from ``fetch_prices``.
    adv_by_ticker : dict[str, float | None]
        Keyed by ticker; value is the trailing-ADV-lookback-day mean dollar
        volume, or ``None`` when the price frame lacked volume data.
    """
    rows: list[dict] = []
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    # S&P 1500 Slice 4 — ADV dict built alongside prices (zero extra I/O).
    # Keyed by ticker; value is trailing-30-day mean dollar volume in USD,
    # or None when the price DataFrame was unavailable / missing columns.
    adv_by_ticker: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
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
                # Use .pop with default so test mocks that don't include
                # "_adv" (pre-Slice-4 fixtures) degrade gracefully to None
                # rather than raising KeyError.
                adv_by_ticker[ticker] = result.pop("_adv", None)
                rows.append(result)
    return rows, prices_by_ticker, adv_by_ticker
