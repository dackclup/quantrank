"""Technical indicator tests (knowledge doc §7). Synthetic data, offline."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from compute.features.technical import (
    adx,
    atr,
    bollinger_pct_b,
    macd_signal,
    mfi,
    obv_slope,
    rsi,
)


def _ohlcv(closes: list[float] | np.ndarray) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.02,
            "Low": closes * 0.98,
            "Close": closes,
            "Adj Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def test_rsi_range():
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0, 1, 200))
    df = _ohlcv(closes)
    val = rsi(df)
    assert 0 <= val <= 100


def test_rsi_uptrend_above_50():
    closes = np.linspace(100, 200, 100)
    df = _ohlcv(closes)
    assert rsi(df) > 60


def test_rsi_downtrend_below_50():
    closes = np.linspace(200, 100, 100)
    df = _ohlcv(closes)
    assert rsi(df) < 40


def test_macd_signal_positive_uptrend():
    closes = np.linspace(100, 200, 200)
    df = _ohlcv(closes)
    assert macd_signal(df) >= 0


def test_atr_positive_for_volatile_series():
    rng = np.random.default_rng(11)
    closes = 100 + np.cumsum(rng.normal(0, 1, 200))
    df = _ohlcv(closes)
    assert atr(df) > 0


def test_adx_returns_finite_for_trending_series():
    closes = np.linspace(100, 200, 200)
    df = _ohlcv(closes)
    val = adx(df)
    assert not math.isnan(val)
    assert val > 0


def test_bollinger_pct_b_within_reasonable_range():
    rng = np.random.default_rng(31)
    closes = 100 + np.cumsum(rng.normal(0, 1, 200))
    df = _ohlcv(closes)
    val = bollinger_pct_b(df)
    assert -1 <= val <= 2  # excursions outside [0,1] are normal


def test_obv_slope_positive_for_uptrend_with_steady_volume():
    closes = np.linspace(100, 200, 100)
    df = _ohlcv(closes)
    assert obv_slope(df) > 0


def test_mfi_within_0_100():
    rng = np.random.default_rng(41)
    closes = 100 + np.cumsum(rng.normal(0, 1, 200))
    df = _ohlcv(closes)
    val = mfi(df)
    assert 0 <= val <= 100


def test_rsi_short_history_returns_nan():
    df = _ohlcv(np.full(5, 100.0))
    assert math.isnan(rsi(df))
