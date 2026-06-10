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
    mad_diagnostics,
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


# ---------------------------------------------------------------------------
# mad_diagnostics — issue #441 PR-1 observability pins
# ---------------------------------------------------------------------------


def test_mad_diagnostics_perfect_positive_correlation():
    """MAD values == mom12 values yields r12 == 1.0, coverage == 100%.

    When the two series are identical (same ranks), Spearman rho = 1.0.
    universe_size == len(inputs) so coverage == 100.0.
    """
    tickers = [f"T{i:02d}" for i in range(10)]
    mad = {t: float(i + 1) for i, t in enumerate(tickers)}
    mom12 = dict(mad)  # identical → perfect positive rank alignment
    mom3 = {t: float(10 - i) for i, t in enumerate(tickers)}  # anticorrelated

    cov, r12, r3 = mad_diagnostics(mad, mom12, mom3, universe_size=10)

    assert cov == 100.0
    assert r12 is not None
    assert math.isclose(r12, 1.0, abs_tol=1e-4), f"expected r12≈1.0, got {r12}"


def test_mad_diagnostics_perfect_negative_correlation():
    """MAD == inverse ranking of mom3 yields r3 == -1.0.

    When the ranks are perfectly reversed, Spearman rho = -1.0.
    """
    tickers = [f"T{i:02d}" for i in range(10)]
    mad = {t: float(i + 1) for i, t in enumerate(tickers)}
    mom12 = {t: float(i + 1) for i, t in enumerate(tickers)}  # same order
    mom3 = {t: float(10 - i) for i, t in enumerate(tickers)}  # reversed

    _cov, _r12, r3 = mad_diagnostics(mad, mom12, mom3, universe_size=10)

    assert r3 is not None
    assert math.isclose(r3, -1.0, abs_tol=1e-4), f"expected r3≈-1.0, got {r3}"


def test_mad_diagnostics_fewer_than_3_finite_pairs_returns_none():
    """Fewer than 3 overlapping finite pairs yields both corrs None.

    Only 2 tickers have finite values in both MAD and mom12/mom3,
    which is below the < 3 pair guard. Both correlations must be None
    (not NaN, not a float).
    """
    # Only 2 tickers overlap finitely between mad and mom12/mom3.
    mad = {"A": 1.0, "B": 2.0, "C": float("nan")}
    mom12 = {"A": 1.0, "B": 2.0, "D": 3.0}  # C missing, D not in mad
    mom3 = {"A": 1.0, "B": 2.0}

    _cov, r12, r3 = mad_diagnostics(mad, mom12, mom3, universe_size=3)

    assert r12 is None, f"expected r12=None with 2 pairs, got {r12}"
    assert r3 is None, f"expected r3=None with 2 pairs, got {r3}"


def test_mad_diagnostics_constant_mad_returns_none_corrs():
    """Constant MAD (zero variance in the rank series) yields both corrs None.

    When all MAD values are identical, all ranks are tied at the same
    average rank — the rank series has zero standard deviation, making
    Spearman rho undefined. The implementation must return None (not NaN,
    not raise ZeroDivisionError).
    """
    tickers = [f"T{i:02d}" for i in range(5)]
    mad = {t: 1.0 for t in tickers}  # constant — zero variance
    mom12 = {t: float(i + 1) for i, t in enumerate(tickers)}
    mom3 = {t: float(i + 1) for i, t in enumerate(tickers)}

    _cov, r12, r3 = mad_diagnostics(mad, mom12, mom3, universe_size=5)

    assert r12 is None, f"constant MAD must yield r12=None, got {r12}"
    assert r3 is None, f"constant MAD must yield r3=None, got {r3}"


def test_mad_diagnostics_empty_inputs_returns_zero_coverage_none_corrs():
    """Empty input dicts yield cov == 0.0, both corrs None.

    universe_size > 0, but no tickers have finite MAD; coverage numerator
    is 0 so cov == 0.0. With 0 overlapping pairs, both corrs are None.
    """
    cov, r12, r3 = mad_diagnostics({}, {}, {}, universe_size=10)

    assert cov == 0.0, f"empty MAD dict must yield cov=0.0, got {cov}"
    assert r12 is None
    assert r3 is None


def test_mad_diagnostics_universe_size_zero_returns_coverage_none():
    """universe_size == 0 yields cov == None (no ZeroDivisionError).

    The implementation guards universe_size > 0; zero triggers the
    else branch and returns None without dividing by zero.
    """
    mad = {"A": 1.0, "B": 2.0}
    mom12 = {"A": 1.0, "B": 2.0}
    mom3 = {"A": 1.0, "B": 2.0}

    cov, _r12, _r3 = mad_diagnostics(mad, mom12, mom3, universe_size=0)

    assert cov is None, f"universe_size=0 must yield cov=None, got {cov}"


def test_mad_diagnostics_nan_values_excluded_from_coverage_and_corr():
    """NaN entries excluded from coverage numerator AND correlation pairs.

    3 tickers have finite MAD; 2 have NaN. Coverage = 3/5 * 100 = 60.0.
    The NaN tickers are dropped from correlation pairs, so only 3 pairs
    contribute to the correlation — enough for a finite result.
    """
    mad = {"A": 1.0, "B": 2.0, "C": 3.0, "D": float("nan"), "E": float("nan")}
    mom12 = {t: float(i + 1) for i, t in enumerate(["A", "B", "C", "D", "E"])}
    mom3 = {t: float(i + 1) for i, t in enumerate(["A", "B", "C", "D", "E"])}

    cov, r12, r3 = mad_diagnostics(mad, mom12, mom3, universe_size=5)

    assert math.isclose(cov, 60.0, abs_tol=0.01), f"expected cov=60.0, got {cov}"
    # Correlation uses the 3 finite-MAD tickers only — still >= 3 pairs,
    # so both corrs should be finite (not None).
    assert r12 is not None, "3 finite pairs should yield a finite r12"
    assert r3 is not None, "3 finite pairs should yield a finite r3"
    assert -1.0 <= r12 <= 1.0, f"r12={r12} out of [-1, 1]"
    assert -1.0 <= r3 <= 1.0, f"r3={r3} out of [-1, 1]"


def test_mad_diagnostics_ties_exercise_average_rank_no_crash():
    """Duplicate values on mom12 side exercise rank(method='average').

    Tied values on both sides should produce a finite rho in [-1, 1]
    without raising any exception (the average-rank tie-breaking is the
    classical Spearman definition per Kendall 1938 §3.1 for tied pairs).
    """
    # Ties on the mom12 side: two tickers share value 2.0.
    mad = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}
    mom12 = {"A": 1.0, "B": 2.0, "C": 2.0, "D": 4.0, "E": 5.0}  # B and C tied
    mom3 = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}

    cov, r12, r3 = mad_diagnostics(mad, mom12, mom3, universe_size=5)

    assert cov == 100.0
    assert r12 is not None, "tied mom12 must still yield a finite r12"
    assert -1.0 <= r12 <= 1.0, f"r12={r12} out of [-1, 1]"
    assert r3 is not None, "r3 must be finite"
    assert math.isclose(r3, -1.0, abs_tol=1e-4), f"expected r3≈-1.0, got {r3}"
