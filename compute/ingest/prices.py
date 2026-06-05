"""Daily OHLCV prices via yfinance, with disk caching and tenacity retry.

Returns ``None`` on persistent failure or empty response so the orchestrator
can skip the ticker without crashing the whole run.
"""

from __future__ import annotations

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


def fetch_prices(ticker: str, period: str = config.PRICES_PERIOD) -> pd.DataFrame | None:
    """Return a daily OHLCV DataFrame for ``ticker``, or ``None`` on failure."""
    cache_dir = config.PRICES_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{ticker}.parquet"

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < config.PRICES_CACHE_MAX_AGE_HOURS:
            try:
                return pd.read_parquet(cache_path)
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

    try:
        df.to_parquet(cache_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache write failed for %s: %s", ticker, e)

    return df
