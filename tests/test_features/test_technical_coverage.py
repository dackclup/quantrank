"""Coverage tests for compute.features.technical — targeting uncovered branches.

Uncovered lines (baseline 80%):
  48    macd_signal: short history returns nan
  59    atr: missing High/Low columns returns nan
  64    atr: short history returns nan
  75    adx: missing required columns returns nan
  80    adx: short history returns nan
  100   bollinger_pct_b: short history returns nan
  107   bollinger_pct_b: band_width == 0 returns nan
  117   obv_slope: missing Volume returns nan
  121   obv_slope: short history returns nan
  127   obv_slope: non-finite y guard
  136,138  mfi: missing required columns; short history
  147   mfi: neg_sum == 0 returns 100.0 (all money flow positive)
"""

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


def _ohlcv(closes: np.ndarray | list[float]) -> pd.DataFrame:
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


def _close_only(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Adj Close": np.array(closes, dtype=float)}, index=idx)


# ---------------------------------------------------------------------------
# macd_signal: short history (line 48)
# ---------------------------------------------------------------------------


def test_macd_signal_nan_when_too_short():
    """macd needs at least slow + signal bars (26 + 9 = 35)."""
    df = _close_only(np.full(30, 100.0).tolist())
    assert math.isnan(macd_signal(df))


def test_macd_signal_negative_downtrend():
    """MACD histogram negative for a downtrending series."""
    closes = np.linspace(200.0, 100.0, 200)
    df = _close_only(closes.tolist())
    assert macd_signal(df) <= 0


# ---------------------------------------------------------------------------
# atr: missing columns (line 59); short history (line 64)
# ---------------------------------------------------------------------------


def test_atr_nan_when_high_low_missing():
    """atr needs 'High' and 'Low' columns."""
    df = _close_only(np.full(50, 100.0).tolist())
    assert math.isnan(atr(df))


def test_atr_nan_when_too_short():
    """atr needs at least period + 1 = 15 bars."""
    df = _ohlcv(np.full(5, 100.0))
    assert math.isnan(atr(df))


# ---------------------------------------------------------------------------
# adx: missing columns (line 75); short history (line 80)
# ---------------------------------------------------------------------------


def test_adx_nan_when_close_column_missing():
    """adx needs 'High', 'Low', 'Close'. A df with only 'Adj Close' fails."""
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame(
        {
            "High": np.full(n, 102.0),
            "Low": np.full(n, 98.0),
            "Adj Close": np.full(n, 100.0),
            # 'Close' missing → should return NaN
        },
        index=idx,
    )
    assert math.isnan(adx(df))


def test_adx_nan_when_missing_high_low():
    """adx needs High and Low."""
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({"Close": np.full(n, 100.0)}, index=idx)
    assert math.isnan(adx(df))


def test_adx_nan_when_too_short():
    """adx needs at least period * 2 = 28 bars by default."""
    df = _ohlcv(np.full(20, 100.0))
    assert math.isnan(adx(df))


# ---------------------------------------------------------------------------
# bollinger_pct_b: short history (line 100); zero band width (line 107)
# ---------------------------------------------------------------------------


def test_bollinger_pct_b_nan_when_too_short():
    """bollinger_pct_b needs at least `period` = 20 bars."""
    df = _close_only(np.full(10, 100.0).tolist())
    assert math.isnan(bollinger_pct_b(df))


def test_bollinger_pct_b_nan_when_band_width_zero():
    """A perfectly flat series has sd=0 → band_width=0 → NaN (no division)."""
    df = _close_only(np.full(50, 100.0).tolist())
    result = bollinger_pct_b(df)
    assert math.isnan(result)


# ---------------------------------------------------------------------------
# obv_slope: missing Volume (line 117); short history (line 121)
# ---------------------------------------------------------------------------


def test_obv_slope_nan_when_volume_missing():
    """obv_slope needs 'Volume' column."""
    df = _close_only(np.linspace(100.0, 200.0, 100).tolist())
    assert math.isnan(obv_slope(df))


def test_obv_slope_nan_when_too_short():
    """obv_slope needs at least lookback + 1 = 21 bars."""
    df = _ohlcv(np.full(10, 100.0))
    assert math.isnan(obv_slope(df))


def test_obv_slope_negative_for_downtrend():
    """Decreasing close price with steady volume → negative OBV slope."""
    closes = np.linspace(200.0, 100.0, 100)
    df = _ohlcv(closes)
    assert obv_slope(df) < 0


# ---------------------------------------------------------------------------
# mfi: missing columns (line 136); short history (line 138); neg_sum==0 (line 147)
# ---------------------------------------------------------------------------


def test_mfi_nan_when_volume_missing():
    """mfi needs 'High', 'Low', 'Close', 'Volume'."""
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame(
        {
            "High": np.full(n, 102.0),
            "Low": np.full(n, 98.0),
            "Close": np.full(n, 100.0),
            # 'Volume' missing
        },
        index=idx,
    )
    assert math.isnan(mfi(df))


def test_mfi_nan_when_too_short():
    """mfi needs at least period + 1 = 15 bars."""
    df = _ohlcv(np.full(5, 100.0))
    assert math.isnan(mfi(df))


def test_mfi_returns_100_when_all_money_flow_positive():
    """mfi returns 100.0 when neg_sum == 0 (pure uptrend with no down ticks)."""
    # Strictly increasing typical price → delta > 0 every bar → neg_flow = 0.
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = np.linspace(100.0, 200.0, n)
    df = pd.DataFrame(
        {
            "High": closes + 1.0,
            "Low": closes - 1.0,
            "Close": closes,
            "Adj Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    result = mfi(df)
    assert result == 100.0


# ---------------------------------------------------------------------------
# rsi: avg_loss == 0 → returns 100.0 (line 31)
# ---------------------------------------------------------------------------


def test_rsi_returns_100_when_no_losses():
    """RSI = 100.0 when avg_loss == 0 (pure uptrend with no down ticks)."""
    n = 50
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # Strictly increasing → no negative differences → avg_loss = 0.
    closes = np.linspace(100.0, 200.0, n)
    df = pd.DataFrame({"Adj Close": closes}, index=idx)
    result = rsi(df)
    assert result == 100.0
