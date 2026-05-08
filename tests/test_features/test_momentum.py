"""Golden-value and edge-case tests for momentum_12_1."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from compute.features.momentum import momentum_12_1


def _series(index, values, col="Adj Close"):
    return pd.DataFrame({col: values}, index=pd.DatetimeIndex(index))


def test_momentum_12_1_known_value():
    """Expected anchors: t-12m = 2025-04-30, t-1m = 2026-03-30."""
    today = pd.Timestamp("2026-04-30")
    dates = pd.date_range("2025-01-01", today, freq="B")
    df = pd.DataFrame({"Adj Close": np.full(len(dates), np.nan)}, index=dates)
    df.loc[pd.Timestamp("2025-04-30"), "Adj Close"] = 100.0
    df.loc[pd.Timestamp("2026-03-30"), "Adj Close"] = 121.0

    out = momentum_12_1(df, today=today)
    assert math.isclose(out, 0.21, rel_tol=1e-9, abs_tol=1e-9)


def test_momentum_12_1_uses_close_when_adj_close_missing():
    today = pd.Timestamp("2026-04-30")
    dates = pd.date_range("2025-01-01", today, freq="B")
    df = pd.DataFrame({"Close": np.full(len(dates), np.nan)}, index=dates)
    df.loc[pd.Timestamp("2025-04-30"), "Close"] = 50.0
    df.loc[pd.Timestamp("2026-03-30"), "Close"] = 60.0
    out = momentum_12_1(df, today=today)
    assert math.isclose(out, 0.20, rel_tol=1e-9, abs_tol=1e-9)


def test_momentum_12_1_uses_last_bar_at_or_before_anchor():
    """If the anchor date itself isn't a trading day, use the most recent prior bar."""
    today = pd.Timestamp("2026-04-30")
    # Two prices: one a few days BEFORE t-12m anchor, one a few days BEFORE t-1m anchor.
    df = _series(
        ["2025-04-25", "2026-03-27"],
        [200.0, 250.0],
    )
    out = momentum_12_1(df, today=today)
    assert math.isclose(out, 0.25, rel_tol=1e-9, abs_tol=1e-9)


def test_momentum_12_1_returns_nan_for_too_short_history():
    today = pd.Timestamp("2026-04-30")
    df = _series(["2026-04-01", "2026-04-15"], [100.0, 105.0])
    out = momentum_12_1(df, today=today)
    assert math.isnan(out)


def test_momentum_12_1_returns_nan_for_empty_input():
    out = momentum_12_1(pd.DataFrame(columns=["Adj Close"]))
    assert math.isnan(out)


def test_momentum_12_1_handles_zero_baseline():
    today = pd.Timestamp("2026-04-30")
    df = _series(["2025-04-30", "2026-03-31"], [0.0, 100.0])
    out = momentum_12_1(df, today=today)
    assert math.isnan(out)


def test_momentum_12_1_raises_on_missing_columns():
    today = pd.Timestamp("2026-04-30")
    df = _series(["2025-04-30", "2026-03-31"], [100.0, 110.0], col="Open")
    with pytest.raises(KeyError):
        momentum_12_1(df, today=today)
