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


def momentum_12_1(prices: pd.DataFrame, today: pd.Timestamp | None = None) -> float:
    """Cumulative total return from t-12m to t-1m. Returns NaN if history is short."""
    if prices is None or prices.empty:
        return float("nan")

    col = _resolve_price_column(prices)
    if today is None:
        today = pd.Timestamp(prices.index[-1])

    t_minus_1 = today - pd.DateOffset(months=1)
    t_minus_12 = today - pd.DateOffset(months=12)

    p_recent = _bar_at_or_before(prices, t_minus_1, col)
    p_old = _bar_at_or_before(prices, t_minus_12, col)

    if p_recent is None or p_old is None or p_old == 0 or np.isnan(p_recent) or np.isnan(p_old):
        return float("nan")

    return p_recent / p_old - 1.0
