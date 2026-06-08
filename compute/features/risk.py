"""Risk metrics — knowledge doc §9.

All take a price DataFrame and return a single scalar. Use 252 trading days
per year. Annualization √252 where applicable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_COL = "Adj Close"
TRADING_DAYS_PER_YEAR = 252


def _close_series(prices: pd.DataFrame) -> pd.Series:
    if prices is None or prices.empty:
        return pd.Series(dtype=float)
    col = PRICE_COL if PRICE_COL in prices.columns else "Close"
    return prices[col].dropna()


def daily_returns(prices: pd.DataFrame) -> pd.Series:
    """Simple daily returns from adjusted close."""
    s = _close_series(prices)
    if len(s) < 2:
        return pd.Series(dtype=float)
    return s.pct_change().dropna()


def vol_252(prices: pd.DataFrame) -> float:
    """Annualized 1-yr realized volatility (σ × √252)."""
    r = daily_returns(prices).tail(TRADING_DAYS_PER_YEAR)
    if len(r) < 30:
        return float("nan")
    return float(r.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def beta(prices: pd.DataFrame, benchmark: pd.DataFrame) -> float:
    """β = cov(stock, market) / var(market) over the last 252 trading days."""
    r_s = daily_returns(prices).tail(TRADING_DAYS_PER_YEAR)
    r_m = daily_returns(benchmark).tail(TRADING_DAYS_PER_YEAR)
    if len(r_s) < 30 or len(r_m) < 30:
        return float("nan")
    df = pd.concat([r_s.rename("s"), r_m.rename("m")], axis=1).dropna()
    if len(df) < 30:
        return float("nan")
    var_m = float(df["m"].var(ddof=1))
    if var_m == 0:
        return float("nan")
    return float(df["s"].cov(df["m"]) / var_m)


def sharpe(prices: pd.DataFrame, rf_annual: float = 0.0) -> float:
    """Annualized Sharpe ratio = (μ − r_f) / σ × √252."""
    r = daily_returns(prices).tail(TRADING_DAYS_PER_YEAR)
    if len(r) < 30:
        return float("nan")
    rf_daily = rf_annual / TRADING_DAYS_PER_YEAR
    excess = r - rf_daily
    sd = float(excess.std(ddof=1))
    if sd == 0:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino(prices: pd.DataFrame, rf_annual: float = 0.0) -> float:
    """Annualized Sortino: divides excess return by downside-only stdev."""
    r = daily_returns(prices).tail(TRADING_DAYS_PER_YEAR)
    if len(r) < 30:
        return float("nan")
    rf_daily = rf_annual / TRADING_DAYS_PER_YEAR
    excess = r - rf_daily
    downside = excess[excess < 0]
    if len(downside) < 5:
        return float("nan")
    dd = float(downside.std(ddof=1))
    if dd == 0:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown_from_series(s: pd.Series) -> float:
    if len(s) < 2:
        return float("nan")
    running_max = s.cummax()
    dd = (s - running_max) / running_max
    return float(dd.min())


def max_drawdown(prices: pd.DataFrame) -> float:
    """Maximum peak-to-trough drawdown over the trailing ~5y (negative number).

    Window-CAPPED at ``TRADING_DAYS_PER_YEAR * 5`` so this LIVE risk-pillar metric is
    invariant to ``config.PRICES_PERIOD`` (which went 5y→10y on 2026-06-08 for the
    decade-long AI-pick backtest). Without the cap, a 10y price series would capture
    deeper troughs (2020 COVID, 2018-Q4) and silently shift the cross-sectionally-
    normalized risk pillar → live composite ranks (a retroactive-score change Rule 16
    forbids). The 5y cap preserves the prior full-5y-history semantics. (calmar below
    is likewise capped — at 3y — so both window-sensitive drawdown metrics are
    PRICES_PERIOD-invariant; do NOT remove either cap.)"""
    s = _close_series(prices)
    if len(s) < 30:
        return float("nan")
    window = s.tail(TRADING_DAYS_PER_YEAR * 5) if len(s) > TRADING_DAYS_PER_YEAR * 5 else s
    return _max_drawdown_from_series(window)


def calmar(prices: pd.DataFrame) -> float:
    """Calmar = annualized return / |MaxDD|. Uses the trailing 3 years (the 3y cap is
    load-bearing now that PRICES_PERIOD=10y > 3y — keeps this PRICES_PERIOD-invariant)."""
    s = _close_series(prices)
    if len(s) < TRADING_DAYS_PER_YEAR:
        return float("nan")
    window = s.tail(TRADING_DAYS_PER_YEAR * 3) if len(s) > TRADING_DAYS_PER_YEAR * 3 else s
    n_years = len(window) / TRADING_DAYS_PER_YEAR
    if window.iloc[0] <= 0 or n_years == 0:
        return float("nan")
    cagr = (window.iloc[-1] / window.iloc[0]) ** (1 / n_years) - 1
    mdd = _max_drawdown_from_series(window)
    if mdd is None or np.isnan(mdd) or mdd == 0:
        return float("nan")
    return float(cagr / abs(mdd))
