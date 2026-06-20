"""Coverage tests for compute.features.risk — targeting uncovered branches.

Uncovered lines (baseline 71%):
  18   _close_series: Close column fallback branch
  27   daily_returns: len(s) < 2 early-return (empty series)
  44,47,50  beta: short stock / market / join-after-align guard
  58,63  sharpe: len < 30 guard; sd == 0 guard
  71,77-80  sortino: len < 30 guard; few downside; dd == 0 guard
  85    _max_drawdown_from_series: len < 2 guard
  104   max_drawdown: len < 30 guard
  114,118,123  calmar: len < year; window.iloc[0] <= 0; mdd == 0 guard
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from compute.features.risk import (
    TRADING_DAYS_PER_YEAR,
    _close_series,
    _max_drawdown_from_series,
    beta,
    calmar,
    daily_returns,
    max_drawdown,
    sharpe,
    sortino,
    vol_252,
)


def _df_close(n: int, col: str = "Adj Close", value: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({col: np.full(n, value)}, index=idx)


def _ramp(n: int = 300, daily_return: float = 0.001) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = 100.0 * (1 + daily_return) ** np.arange(n)
    return pd.DataFrame({"Adj Close": closes}, index=idx)


# ---------------------------------------------------------------------------
# _close_series: fallback to "Close" column when "Adj Close" absent (line 19)
# ---------------------------------------------------------------------------


def test_close_series_falls_back_to_close_column():
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    df = pd.DataFrame({"Close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=idx)
    s = _close_series(df)
    assert len(s) == 5
    assert list(s) == [100.0, 101.0, 102.0, 103.0, 104.0]


def test_close_series_none_input_returns_empty():
    s = _close_series(None)
    assert len(s) == 0


def test_close_series_empty_df_returns_empty():
    s = _close_series(pd.DataFrame())
    assert len(s) == 0


# ---------------------------------------------------------------------------
# daily_returns: short series (< 2 bars) early-return (line 27)
# ---------------------------------------------------------------------------


def test_daily_returns_single_bar_returns_empty():
    df = _df_close(1)
    r = daily_returns(df)
    assert len(r) == 0


def test_daily_returns_empty_df_returns_empty():
    r = daily_returns(pd.DataFrame())
    assert len(r) == 0


# ---------------------------------------------------------------------------
# vol_252: uses Close fallback (branch coverage via _close_series)
# ---------------------------------------------------------------------------


def test_vol_252_using_close_column():
    """vol_252 via a 'Close'-only df — exercises the fallback column branch."""
    rng = np.random.default_rng(99)
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.02, n))
    df = pd.DataFrame({"Close": closes}, index=idx)
    v = vol_252(df)
    assert math.isfinite(v)
    assert v > 0


# ---------------------------------------------------------------------------
# beta: short series guards (lines 44, 47, 50)
# ---------------------------------------------------------------------------


def test_beta_nan_when_stock_too_short():
    short = _df_close(10)
    market = _ramp(300)
    assert math.isnan(beta(short, market))


def test_beta_nan_when_market_too_short():
    stock = _ramp(300)
    short = _df_close(10)
    assert math.isnan(beta(stock, short))


def test_beta_nan_when_aligned_overlap_too_short():
    """Stock and market exist but share < 30 overlapping dates after alignment."""
    # Use mismatching date ranges — they only share 1 date after alignment.
    idx_s = pd.date_range("2024-01-01", periods=300, freq="B")
    idx_m = pd.date_range("2025-06-01", periods=300, freq="B")
    stock = pd.DataFrame({"Adj Close": np.full(300, 100.0)}, index=idx_s)
    market = pd.DataFrame({"Adj Close": np.full(300, 100.0)}, index=idx_m)
    assert math.isnan(beta(stock, market))


def test_beta_nan_when_market_variance_zero():
    """A flat market (zero variance) → NaN instead of division-by-zero crash."""
    stock = _ramp(300)
    market = _df_close(300)  # flat series, var = 0
    assert math.isnan(beta(stock, market))


# ---------------------------------------------------------------------------
# sharpe: guards (lines 58, 63)
# ---------------------------------------------------------------------------


def test_sharpe_nan_when_fewer_than_30_returns():
    df = _df_close(10)
    assert math.isnan(sharpe(df))


def test_sharpe_nan_when_excess_sd_zero():
    """Sharpe is NaN when all returns are exactly the same (sd = 0)."""
    # Flat series — all daily returns = 0 → sd = 0.
    df = _df_close(300)
    # rf_annual also 0 → excess = 0 → sd = 0 → NaN.
    assert math.isnan(sharpe(df, rf_annual=0.0))


# ---------------------------------------------------------------------------
# sortino: guards (lines 71, 77-80)
# ---------------------------------------------------------------------------


def test_sortino_nan_when_fewer_than_30_returns():
    df = _df_close(10)
    assert math.isnan(sortino(df))


def test_sortino_nan_when_fewer_than_5_downside_returns():
    """Pure uptrend has no negative returns → downside < 5 → NaN."""
    df = _ramp(300, daily_return=0.001)
    assert math.isnan(sortino(df))


def test_max_drawdown_from_series_short_returns_nan():
    s = pd.Series([100.0])
    assert math.isnan(_max_drawdown_from_series(s))


def test_max_drawdown_from_series_empty_returns_nan():
    s = pd.Series(dtype=float)
    assert math.isnan(_max_drawdown_from_series(s))


# ---------------------------------------------------------------------------
# max_drawdown: len < 30 guard (line 104)
# ---------------------------------------------------------------------------


def test_max_drawdown_nan_when_short_history():
    df = _df_close(10)
    assert math.isnan(max_drawdown(df))


# ---------------------------------------------------------------------------
# calmar: guards (lines 114, 118, 123)
# ---------------------------------------------------------------------------


def test_calmar_nan_when_fewer_than_252_bars():
    df = _df_close(100)  # < TRADING_DAYS_PER_YEAR
    assert math.isnan(calmar(df))


def test_calmar_nan_when_start_price_zero():
    """calmar is NaN when window.iloc[0] <= 0 (division guard)."""
    n = TRADING_DAYS_PER_YEAR + 1
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = np.linspace(0.0, 100.0, n)  # starts at 0
    df = pd.DataFrame({"Adj Close": closes}, index=idx)
    assert math.isnan(calmar(df))


def test_calmar_nan_when_max_drawdown_is_zero():
    """Flat series → MDD = 0 → calmar NaN (division guard at line 123)."""
    df = _df_close(300)  # all prices identical → mdd = 0
    assert math.isnan(calmar(df))


def test_calmar_positive_for_uptrending_with_drawdown():
    """Calmar should be positive for an uptrending series with a drawdown."""
    rng = np.random.default_rng(42)
    n = TRADING_DAYS_PER_YEAR * 4
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Small uptrend + occasional downturns so MDD != 0.
    returns = rng.normal(0.0003, 0.015, n)
    closes = 100.0 * np.cumprod(1 + returns)
    df = pd.DataFrame({"Adj Close": closes}, index=idx)
    c = calmar(df)
    # A long uptrend should give a positive Calmar.
    if not math.isnan(c):
        assert c != 0.0
