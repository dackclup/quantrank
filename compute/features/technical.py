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
