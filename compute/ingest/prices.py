"""Daily OHLCV prices via yfinance, with disk caching and tenacity retry.

Returns ``None`` on persistent failure or empty response so the orchestrator
can skip the ticker without crashing the whole run.
"""

from __future__ import annotations

import datetime
import logging
import time

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from compute import config

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _yf_download(ticker: str, period: str) -> pd.DataFrame:
    df = yf.download(
        ticker,
        period=period,
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


SPY_TICKER: str = "SPY"


def fetch_spy_benchmark(period: str = config.PRICES_PERIOD) -> pd.DataFrame | None:
    """Fetch SPY OHLCV for use as the β benchmark + market-return baseline."""
    return fetch_prices(SPY_TICKER, period=period)


# Phase 7.0 PR-1 — index-proxy ETFs exported for the portfolio-backtest
# benchmark selector. SPY = S&P 500 (also the β baseline above); QQQ =
# Nasdaq-100; DIA = Dow Jones Industrial Average; IWM = Russell 2000.
# Display-only — no scoring / ranking / veto impact; the home page lets the
# user compare the AI-pick basket against the chosen index. SPY shares
# fetch_prices' on-disk cache with fetch_spy_benchmark (no double download).
BENCHMARK_TICKERS: tuple[str, ...] = ("SPY", "QQQ", "DIA", "IWM")


def fetch_benchmarks(
    period: str = config.PRICES_PERIOD,
) -> dict[str, pd.DataFrame | None]:
    """Fetch OHLCV for each ``BENCHMARK_TICKERS`` symbol, degrading per symbol.

    Returns a dict keyed by ticker; the value is ``None`` when that symbol's
    fetch failed (network / empty response). Never raises — a single benchmark
    failure must not block the weekly cron (graceful-degradation pattern); the
    caller surfaces the success rate as ``Metadata.benchmark_coverage_pct``.
    """
    out: dict[str, pd.DataFrame | None] = {}
    for sym in BENCHMARK_TICKERS:
        try:
            out[sym] = fetch_prices(sym, period=period)
        except Exception as e:  # noqa: BLE001
            logger.warning("benchmark fetch failed for %s: %s", sym, e)
            out[sym] = None
    return out


def fetch_prices(
    ticker: str,
    period: str = config.PRICES_PERIOD,
    min_start: datetime.date | None = None,
) -> pd.DataFrame | None:
    """Return a daily OHLCV DataFrame for ``ticker``, or ``None`` on failure.

    Parameters
    ----------
    ticker:
        Exchange symbol to fetch.
    period:
        yfinance period string (e.g. ``"10y"``, ``"max"``). Used both for
        fresh downloads and for cache-miss refetches triggered by ``min_start``.
    min_start:
        Optional earliest-date floor for depth-sensitive callers.  The cache is
        period-blind (keyed by ticker, not by period), so a cached frame may be
        shallower than required for a long backtest window.  When ``min_start``
        is provided and a fresh cache hit's earliest index date is AFTER
        ``min_start``, the cached frame is treated as a depth miss: the function
        refetches once with the given ``period`` (typically ``"max"``), writes
        the deeper frame to the cache, and returns it.  The refetch happens AT
        MOST ONCE per call — if the newly fetched frame still starts after
        ``min_start`` that IS the full history available (e.g. a recently-listed
        ticker), and the result is cached and returned without looping.
        Default ``None`` = byte-identical current behaviour (the live weekly
        compute path never passes this argument).
    """
    cache_dir = config.PRICES_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{ticker}.parquet"

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < config.PRICES_CACHE_MAX_AGE_HOURS:
            try:
                cached = pd.read_parquet(cache_path)
                # Depth check: if min_start is set and the cached frame is
                # shallower than required, fall through to a fresh download.
                if min_start is None or _frame_covers(cached, min_start):
                    return cached
                logger.info(
                    "fetch_prices(%s): cache shallow (earliest %s > floor %s) — refetching",
                    ticker,
                    _earliest_date(cached),
                    min_start,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Cache read failed for %s: %s", ticker, e)

    try:
        df = _yf_download(ticker, period)
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance download failed for %s: %s", ticker, e)
        return None

    if df is None or df.empty:
        logger.warning("Empty price response for %s", ticker)
        return None

    # If the freshly downloaded frame is still shallower than min_start, that
    # IS the full history for this ticker (new listing).  Cache and return it —
    # no retry loop.
    if min_start is not None and not _frame_covers(df, min_start):
        logger.info(
            "fetch_prices(%s): max-depth frame still starts at %s (after floor %s) "
            "— new listing or data unavailable; caching as-is",
            ticker,
            _earliest_date(df),
            min_start,
        )

    try:
        df.to_parquet(cache_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache write failed for %s: %s", ticker, e)

    return df


def _earliest_date(df: pd.DataFrame) -> datetime.date | None:
    """Return the earliest index date of a price DataFrame, or ``None`` if empty."""
    if df is None or df.empty:
        return None
    idx = df.index
    first = idx[0]
    if hasattr(first, "date"):
        return first.date()
    if isinstance(first, datetime.date):
        return first
    return None


def _frame_covers(df: pd.DataFrame, floor: datetime.date) -> bool:
    """Return True when ``df``'s earliest row is on or before ``floor``."""
    earliest = _earliest_date(df)
    if earliest is None:
        return False
    return earliest <= floor
