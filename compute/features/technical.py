"""Technical indicators — knowledge doc §7.

All take a price DataFrame (OHLCV) and return a single scalar (latest value).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_COL = "Adj Close"


def _close(prices: pd.DataFrame) -> pd.Series:
    col = PRICE_COL if PRICE_COL in prices.columns else "Close"
    return prices[col].dropna()


def rsi(prices: pd.DataFrame, period: int = 14) -> float:
    """Wilder's RSI on closing prices (0-100). >70 overbought, <30 oversold."""
    s = _close(prices)
    if len(s) < period + 1:
        return float("nan")
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing: EMA with alpha=1/period.
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    if avg_loss.iloc[-1] == 0:
        return 100.0
    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
    return float(100 - (100 / (1 + rs)))


def macd_signal(
    prices: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> float:
    """MACD histogram (MACD - signal line) at the most recent bar.

    Positive = bullish trend strength.
    """
    s = _close(prices)
    if len(s) < slow + signal:
        return float("nan")
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    return float((macd - sig).iloc[-1])


def mad_scalefree(prices: pd.DataFrame, short: int = 21, long: int = 200) -> float:
    """Scale-free moving-average distance (MAD) at the latest bar:
    ``(SMA_short − SMA_long) / SMA_long``.

    LITERATURE-ANCHORED (issue #441): Avramov-Kaplanski-Subrahmanyam 2021
    *Rev.Fin.Econ.* 39(2) — MAD (short-SMA minus long-SMA, price-normalized) predicts the
    cross-section of equity returns (~9% annualized VW alpha, incremental beyond momentum /
    52-week-high / profitability); Han-Zhou-Zhu 2016 *JFE* 122(2) — MA-trend factor (windows
    up to 200d) at >2× momentum Sharpe, incremental to momentum. Positive = short-run average
    above the long-run trend = bullish.

    Windows are LOAD-BEARING for the sign: the long 21/200 windows are the regime the ~9%
    alpha was measured on. The standard 12/26 MACD windows sit in Ko-Wang-Yang 2025 *FAJ*'s
    short-window OVERREACTION regime where the cross-sectional sign INVERTS — do NOT shorten
    these windows without re-validating the sign (this is why MAD is a SEPARATE function, not
    a reparametrized ``macd_signal``). The ``/ SMA_long`` normalization makes it scale-free so
    the pillar's cross-sectional percentile-rank is not price-level-biased ($500 vs $20 stock).
    ``NaN`` when fewer than ``long`` bars.
    """
    s = _close(prices)
    if len(s) < long:
        return float("nan")
    sma_short = float(s.tail(short).mean())
    sma_long = float(s.tail(long).mean())
    if not np.isfinite(sma_long) or sma_long <= 0:
        return float("nan")
    return (sma_short - sma_long) / sma_long


def mad_diagnostics(
    mad_by_ticker: dict[str, float],
    mom12_by_ticker: dict[str, float],
    mom3_by_ticker: dict[str, float],
    universe_size: int,
) -> tuple[float | None, float | None, float | None]:
    """Cross-sectional MAD observability diagnostics (issue #441 PR-1, Rule 18).

    Returns ``(mad_coverage_pct, mad_mom12_corr, mad_mom3_corr)`` — all three
    fields used by ``Metadata`` for the PR-2 blending gate.

    ``mad_coverage_pct`` — % of the pillar-stage universe (denominator =
    ``universe_size``, matching ``alpha158_coverage_pct`` which uses
    ``len(pillar_df.index)``) with a finite ``mad_scalefree`` value.
    The PR-2 gate requires ≥ 90.

    ``mad_mom12_corr`` / ``mad_mom3_corr`` — cross-sectional Spearman ρ between
    MAD and ``mom_12_1`` / ``mom_3_1`` across tickers where BOTH are finite.
    Implemented as rank-then-Pearson (``pd.Series.rank`` + ``pd.Series.corr``
    with ``method="pearson"``) — no scipy dep.
    Returns ``None`` (not NaN) when < 3 overlapping finite pairs or when
    either rank series is constant (zero variance → undefined ρ). JSON carries
    ``None``, never NaN.

    ``universe_size`` must be > 0; callers should guard.
    """
    # Coverage: finite MAD values / total pillar-stage universe.
    finite_mad = {t: v for t, v in mad_by_ticker.items() if np.isfinite(v)}
    if universe_size > 0:
        cov = round(100.0 * len(finite_mad) / universe_size, 2)
    else:
        cov = None

    def _spearman_corr(
        a: dict[str, float], b: dict[str, float]
    ) -> float | None:
        """Spearman ρ between two ticker→float maps; returns None when undefined.

        Implemented as rank-then-Pearson (no scipy dep).  Ranks are average
        ranks for ties (``method="average"``), consistent with classical
        Spearman ρ. Returns ``None`` (never NaN) when < 3 overlapping pairs or
        when either rank series is constant (zero variance → undefined ρ).
        """
        common = sorted(
            t for t in a if t in b and np.isfinite(a[t]) and np.isfinite(b[t])
        )
        if len(common) < 3:
            return None
        s_a = pd.Series([a[t] for t in common], dtype=float)
        s_b = pd.Series([b[t] for t in common], dtype=float)
        # Rank-then-Pearson: Spearman ρ = Pearson ρ of the ranks.
        r_a = s_a.rank(method="average")
        r_b = s_b.rank(method="average")
        if r_a.std(ddof=0) == 0 or r_b.std(ddof=0) == 0:
            return None
        rho = r_a.corr(r_b, method="pearson")
        if rho is None or not np.isfinite(float(rho)):
            return None
        return round(float(rho), 4)

    corr12 = _spearman_corr(finite_mad, mom12_by_ticker)
    corr3 = _spearman_corr(finite_mad, mom3_by_ticker)
    return cov, corr12, corr3


def atr(prices: pd.DataFrame, period: int = 14) -> float:
    """Average True Range over ``period`` days (Wilder's smoothing)."""
    if not {"High", "Low"}.issubset(prices.columns):
        return float("nan")
    high = prices["High"]
    low = prices["Low"]
    close = _close(prices)
    if len(close) < period + 1:
        return float("nan")
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def adx(prices: pd.DataFrame, period: int = 14) -> float:
    """Wilder's Average Directional Index. >25 trending, <20 choppy."""
    if not {"High", "Low", "Close"}.issubset(prices.columns):
        return float("nan")
    high = prices["High"]
    low = prices["Low"]
    close = prices["Close"]
    if len(close) < period * 2:
        return float("nan")
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr_s = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return float(dx.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def bollinger_pct_b(prices: pd.DataFrame, period: int = 20, n_std: float = 2.0) -> float:
    """Bollinger %B = (price − lower) / (upper − lower). 0=lower band, 1=upper band."""
    s = _close(prices)
    if len(s) < period:
        return float("nan")
    sma = s.rolling(period).mean()
    sd = s.rolling(period).std(ddof=0)
    upper = sma + n_std * sd
    lower = sma - n_std * sd
    band_width = float((upper - lower).iloc[-1])
    if band_width == 0 or np.isnan(band_width):
        return float("nan")
    return float((s.iloc[-1] - lower.iloc[-1]) / band_width)


def obv_slope(prices: pd.DataFrame, lookback: int = 20) -> float:
    """OLS slope of OBV over the last ``lookback`` bars (per-day units).

    Positive slope = accumulation; negative = distribution.
    """
    if "Volume" not in prices.columns:
        return float("nan")
    close = _close(prices)
    vol = prices["Volume"].reindex(close.index).fillna(0)
    if len(close) < lookback + 1:
        return float("nan")
    direction = np.sign(close.diff().fillna(0))
    obv = (direction * vol).cumsum()
    y = obv.tail(lookback).to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    if not np.isfinite(y).all() or len(y) < 2:
        return float("nan")
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def mfi(prices: pd.DataFrame, period: int = 14) -> float:
    """Money Flow Index (0-100). Volume-weighted RSI-like indicator."""
    needed = {"High", "Low", "Close", "Volume"}
    if not needed.issubset(prices.columns):
        return float("nan")
    if len(prices) < period + 1:
        return float("nan")
    typ = (prices["High"] + prices["Low"] + prices["Close"]) / 3
    raw_money_flow = typ * prices["Volume"]
    delta = typ.diff()
    pos_flow = raw_money_flow.where(delta > 0, 0.0)
    neg_flow = raw_money_flow.where(delta < 0, 0.0)
    pos_sum = pos_flow.rolling(period).sum().iloc[-1]
    neg_sum = neg_flow.rolling(period).sum().iloc[-1]
    if neg_sum == 0:
        return 100.0
    ratio = pos_sum / neg_sum
    return float(100 - (100 / (1 + ratio)))
