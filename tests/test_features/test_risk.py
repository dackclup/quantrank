"""Risk metrics tests (knowledge doc §9). All synthetic, offline."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from compute.features.risk import (
    TRADING_DAYS_PER_YEAR,
    beta,
    calmar,
    max_drawdown,
    sharpe,
    sortino,
    vol_252,
)


def _flat_series(n: int = 300, start: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({"Adj Close": np.full(n, start)}, index=idx)


def _ramp_series(n: int = 300, start: float = 100.0, daily_return: float = 0.001) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = start * (1 + daily_return) ** np.arange(n)
    return pd.DataFrame({"Adj Close": closes}, index=idx)


def test_vol_252_zero_for_flat_series():
    df = _flat_series()
    assert vol_252(df) == 0.0


def test_vol_252_positive_for_volatile_series():
    rng = np.random.default_rng(42)
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    daily = rng.normal(0, 0.02, n)
    closes = 100 * np.cumprod(1 + daily)
    df = pd.DataFrame({"Adj Close": closes}, index=idx)
    v = vol_252(df)
    assert 0.20 < v < 0.50  # ballpark 30% annualized


def test_vol_252_returns_nan_for_short_history():
    df = _flat_series(n=10)
    assert math.isnan(vol_252(df))


def test_beta_one_when_stock_mirrors_market():
    market = _ramp_series(daily_return=0.001)
    stock = _ramp_series(daily_return=0.001)
    # Identical returns → β should be 1.0 (variance ratio of 1).
    assert math.isclose(beta(stock, market), 1.0, rel_tol=1e-6, abs_tol=1e-6)


def test_beta_two_when_stock_doubles_market_returns():
    rng = np.random.default_rng(123)
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    market_daily = rng.normal(0, 0.01, n)
    stock_daily = 2 * market_daily  # exact 2x
    market_close = 100 * np.cumprod(1 + market_daily)
    stock_close = 100 * np.cumprod(1 + stock_daily)
    market = pd.DataFrame({"Adj Close": market_close}, index=idx)
    stock = pd.DataFrame({"Adj Close": stock_close}, index=idx)
    b = beta(stock, market)
    assert 1.95 < b < 2.05


def test_sharpe_positive_for_uptrending_series():
    df = _ramp_series(daily_return=0.001)
    assert sharpe(df) > 0


def test_sortino_handles_no_downside():
    """Strict uptrend has no negative returns → Sortino is NaN by definition."""
    df = _ramp_series(daily_return=0.001)
    s = sortino(df)
    assert math.isnan(s)


def test_max_drawdown_negative_after_peak_to_trough():
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = np.concatenate(
        [
            np.linspace(100, 200, n // 2),  # up to 200
            np.linspace(200, 80, n - n // 2),  # crash to 80
        ]
    )
    df = pd.DataFrame({"Adj Close": closes}, index=idx)
    mdd = max_drawdown(df)
    # MDD = (80 − 200) / 200 = −0.60
    assert math.isclose(mdd, -0.60, rel_tol=1e-6, abs_tol=1e-6)


def test_max_drawdown_5y_window_invariant_to_extra_history():
    """max_drawdown is 5y-capped (2026-06-08): extending the price series beyond 5y
    (PRICES_PERIOD 5y→10y) must NOT change it — only the trailing 5y counts, so the
    LIVE risk pillar is invariant to PRICES_PERIOD. Without the cap this would shift
    live composite ranks (the regression quantrank-reviewer caught)."""
    rng = np.random.default_rng(7)
    n10 = TRADING_DAYS_PER_YEAR * 10
    idx = pd.date_range("2016-01-01", periods=n10, freq="B")
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, n10)))
    df10 = pd.DataFrame({"Adj Close": closes}, index=idx)
    df5 = df10.tail(TRADING_DAYS_PER_YEAR * 5)
    assert math.isclose(max_drawdown(df10), max_drawdown(df5), rel_tol=1e-9, abs_tol=1e-9)


def test_max_drawdown_ignores_crash_older_than_5y():
    """A catastrophic crash >5y ago is OUTSIDE the 5y window and must not count — pins
    that the trailing-5y cap (not the full history) bounds the live metric."""
    n = TRADING_DAYS_PER_YEAR * 8  # 8y of bars
    idx = pd.date_range("2016-01-01", periods=n, freq="B")
    closes = np.full(n, 100.0)
    closes[5] = 5.0  # −95% crash ~8y ago, recovers next bar (outside the trailing 5y)
    df = pd.DataFrame({"Adj Close": closes}, index=idx)
    # the trailing 5y is flat 100 → ~0 drawdown; the old crash is windowed out
    assert max_drawdown(df) > -0.001


def test_calmar_returns_nan_when_drawdown_zero():
    df = _flat_series()
    assert math.isnan(calmar(df))
