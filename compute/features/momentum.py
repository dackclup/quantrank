"""Momentum factor (knowledge doc §8.8).

12-1 momentum = cumulative return from month t-12 to month t-1, skipping the
most recent month to mitigate short-term reversal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_COLUMN = "Adj Close"


def _resolve_price_column(prices: pd.DataFrame) -> str:
    if PRICE_COLUMN in prices.columns:
        return PRICE_COLUMN
    if "Close" in prices.columns:
        return "Close"
    raise KeyError(f"prices DataFrame is missing both {PRICE_COLUMN!r} and 'Close' columns")


def _bar_at_or_before(prices: pd.DataFrame, anchor: pd.Timestamp, col: str) -> float | None:
    candidates = prices.loc[prices.index <= anchor, col].dropna()
    if candidates.empty:
        return None
    return float(candidates.iloc[-1])


def _momentum_window(
    prices: pd.DataFrame, months_back: int, skip_months: int, today: pd.Timestamp | None
) -> float:
    """Generic n-1 momentum: cumulative return from t-N months ago to t-skip months ago."""
    if prices is None or prices.empty:
        return float("nan")
    col = _resolve_price_column(prices)
    if today is None:
        today = pd.Timestamp(prices.index[-1])
    p_recent = _bar_at_or_before(prices, today - pd.DateOffset(months=skip_months), col)
    p_old = _bar_at_or_before(prices, today - pd.DateOffset(months=months_back), col)
    if (
        p_recent is None
        or p_old is None
        or p_old == 0
        or np.isnan(p_recent)
        or np.isnan(p_old)
    ):
        return float("nan")
    return p_recent / p_old - 1.0


def momentum_12_1(prices: pd.DataFrame, today: pd.Timestamp | None = None) -> float:
    """Cumulative total return from t-12m to t-1m. Returns NaN if history is short."""
    return _momentum_window(prices, months_back=12, skip_months=1, today=today)


def momentum_6_1(prices: pd.DataFrame, today: pd.Timestamp | None = None) -> float:
    """Cumulative total return from t-6m to t-1m."""
    return _momentum_window(prices, months_back=6, skip_months=1, today=today)


def momentum_3_1(prices: pd.DataFrame, today: pd.Timestamp | None = None) -> float:
    """Cumulative total return from t-3m to t-1m."""
    return _momentum_window(prices, months_back=3, skip_months=1, today=today)


def distance_from_52w_high(
    prices: pd.DataFrame, today: pd.Timestamp | None = None
) -> float:
    """Current price / 52-week high. 1.0 = at high; lower = further below.

    Knowledge doc §8.8: 52-week-high proximity factor.
    """
    if prices is None or prices.empty:
        return float("nan")
    col = _resolve_price_column(prices)
    if today is None:
        today = pd.Timestamp(prices.index[-1])

    last_year = prices.loc[prices.index >= today - pd.DateOffset(weeks=52), col].dropna()
    if last_year.empty:
        return float("nan")
    high = float(last_year.max())
    current = _bar_at_or_before(prices, today, col)
    if current is None or high == 0 or np.isnan(current):
        return float("nan")
    return current / high
