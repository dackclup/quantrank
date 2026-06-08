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
    mad_scalefree,
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


# ---------------------------------------------------------------------------
# mad_scalefree — issue #441 PR-1 construct pins
# ---------------------------------------------------------------------------


def test_mad_scalefree_scale_invariant():
    """THE load-bearing scale-freedom pin.

    Two uptrends with IDENTICAL % path but 10× different price levels must
    yield the same MAD value.  Proves the ``/ SMA_long`` normalization removes
    price-level bias — a naive raw-distance implementation would fail this.
    Uses 250 bars so the 200-window is satisfied.
    """
    closes_hi = np.linspace(100.0, 200.0, 250)
    closes_lo = closes_hi / 10.0  # identical shape, 10× cheaper stock
    df_hi = _ohlcv(closes_hi)
    df_lo = _ohlcv(closes_lo)
    val_hi = mad_scalefree(df_hi)
    val_lo = mad_scalefree(df_lo)
    assert not math.isnan(val_hi)
    assert not math.isnan(val_lo)
    assert math.isclose(val_hi, val_lo, rel_tol=1e-9)


def test_mad_scalefree_sign_at_long_windows():
    """Pin the sign convention at the LITERATURE-ANCHORED 21/200 windows.

    Literature anchor: Avramov 2021 / Han-Zhou-Zhu 2016 — the ~9% annualized
    alpha was measured on the LONG-window regime (21/200).  Ko-Wang-Yang 2025
    shows the cross-sectional sign INVERTS at short windows (12/26); this test
    would trip if someone accidentally reparametrized to short windows.

    - Steady uptrend   → positive MAD (short avg above long trend)
    - Steady downtrend → negative MAD
    - Flat series      → ≈ 0 (abs < 1e-9)
    """
    up_df = _ohlcv(np.linspace(100.0, 200.0, 250))
    assert mad_scalefree(up_df) > 0, "uptrend must yield positive MAD at 21/200"

    down_df = _ohlcv(np.linspace(200.0, 100.0, 250))
    assert mad_scalefree(down_df) < 0, "downtrend must yield negative MAD at 21/200"

    flat_df = _ohlcv(np.full(250, 100.0))
    assert abs(mad_scalefree(flat_df)) < 1e-9, "flat series must yield ≈ 0 MAD"


def test_mad_scalefree_nan_below_long_window():
    """Mirrors test_rsi_short_history_returns_nan style.

    Fewer than ``long`` (200) bars must return NaN; exactly 200 bars must
    return a finite value (the 200-window is just satisfied at that boundary).
    """
    df_short = _ohlcv(np.linspace(100.0, 200.0, 199))  # 1 bar short
    assert math.isnan(mad_scalefree(df_short)), "199 bars must return NaN"

    df_exact = _ohlcv(np.linspace(100.0, 200.0, 200))  # exactly 200
    val = mad_scalefree(df_exact)
    assert not math.isnan(val), "exactly 200 bars must return a finite value"
    assert math.isfinite(val)
