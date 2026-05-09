"""Unit tests for compute.scoring.sanity.

The function under test is a sanity *smoke* test — not a backtest — so
the tests here lock the math (Spearman rank-corr semantics), the
sample-size threshold, the skip rules (None mos / data-quality
corruption / insufficient prices), and the defensive None-returning
edge cases.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from compute.output.schemas import StockSummary
from compute.scoring.sanity import (
    DEFAULT_LOOKBACK_DAYS,
    MIN_SAMPLE,
    compute_mos_trailing_ic,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summary(
    ticker: str,
    *,
    mos_pct: float | None,
    valuation_warnings: list[str] | None = None,
    rank: int = 1,
    composite_score: float = 50.0,
    sector: str = "Information Technology",
    current_price: float = 100.0,
) -> StockSummary:
    """Build a StockSummary with just the fields compute_mos_trailing_ic reads."""
    return StockSummary(
        rank=rank,
        ticker=ticker,
        name=ticker,
        sector=sector,
        composite_score=composite_score,
        current_price=current_price,
        margin_of_safety_pct=mos_pct,
        valuation_warnings=list(valuation_warnings or []),
    )


def _prices_with_return(
    *,
    end_date: date = date(2026, 5, 1),
    days: int = DEFAULT_LOOKBACK_DAYS + 10,
    return_pct: float = 0.10,
    start_price: float = 100.0,
) -> pd.DataFrame:
    """Synthetic OHLCV with a deterministic linear close path so trailing
    return = ``return_pct``. Indexed at business-day frequency ending on
    ``end_date`` so the most-recent ``DEFAULT_LOOKBACK_DAYS``-th row's
    close is exactly ``start_price`` and the final close is
    ``start_price * (1 + return_pct)``.
    """
    n = days
    idx = pd.date_range(end=pd.Timestamp(end_date), periods=n, freq="B")
    end_price = start_price * (1.0 + return_pct)
    closes = np.linspace(start_price * 0.5, end_price, n)
    # Force the lookback-anchor row to equal start_price exactly so the
    # 1y return inside compute_mos_trailing_ic equals return_pct. Only
    # applies when we have at least lookback_days rows; the D1 test
    # intentionally builds shorter histories that the function under
    # test must skip.
    if n >= DEFAULT_LOOKBACK_DAYS:
        closes[-DEFAULT_LOOKBACK_DAYS] = start_price
    closes[-1] = end_price
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Adj Close": closes,
            "Volume": np.full(n, 1_000_000),
        },
        index=idx,
    )


def _build_universe(
    n: int,
    *,
    pairs: list[tuple[float, float]] | None = None,
    perfect_correlation: bool = False,
    perfect_inverse: bool = False,
    seed: int | None = None,
) -> tuple[list[StockSummary], dict[str, pd.DataFrame]]:
    """Build ``n`` (StockSummary, prices) pairs.

    Three modes:
    - ``pairs`` provided: use as the (mos, return) pairs verbatim.
    - ``perfect_correlation``: mos and return both ascending (Spearman = 1.0).
    - ``perfect_inverse``: mos ascending, return descending (Spearman = -1.0).
    - else random with ``seed``.
    """
    rng = np.random.default_rng(seed if seed is not None else 0)
    if pairs is None:
        if perfect_correlation:
            mos_vals = list(np.linspace(-50, 200, n))
            ret_vals = list(np.linspace(-0.3, 0.5, n))
        elif perfect_inverse:
            mos_vals = list(np.linspace(-50, 200, n))
            ret_vals = list(np.linspace(0.5, -0.3, n))
        else:
            mos_vals = list(rng.uniform(-100, 300, n))
            ret_vals = list(rng.uniform(-0.5, 0.8, n))
        pairs = list(zip(mos_vals, ret_vals, strict=False))

    summaries: list[StockSummary] = []
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    for i, (mos, ret) in enumerate(pairs):
        ticker = f"T{i:03d}"
        summaries.append(_summary(ticker, mos_pct=mos, rank=i + 1))
        prices_by_ticker[ticker] = _prices_with_return(return_pct=ret)
    return summaries, prices_by_ticker


# ---------------------------------------------------------------------------
# A. Math correctness
# ---------------------------------------------------------------------------

def test_A1_perfect_rank_correlation_is_one():
    summaries, prices = _build_universe(50, perfect_correlation=True)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is not None
    assert coef == pytest.approx(1.0, abs=1e-9)


def test_A2_perfect_inverse_rank_correlation_is_minus_one():
    summaries, prices = _build_universe(50, perfect_inverse=True)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is not None
    assert coef == pytest.approx(-1.0, abs=1e-9)


def test_A3_random_pairs_within_bounds():
    summaries, prices = _build_universe(50, seed=42)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is not None
    assert -1.0 <= coef <= 1.0


# ---------------------------------------------------------------------------
# B. Sample size
# ---------------------------------------------------------------------------

def test_B1_below_min_sample_returns_none():
    summaries, prices = _build_universe(MIN_SAMPLE - 1, perfect_correlation=True)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


def test_B2_at_min_sample_boundary_returns_float():
    summaries, prices = _build_universe(MIN_SAMPLE, perfect_correlation=True)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is not None
    assert isinstance(coef, float)


def test_B3_large_sample_returns_float():
    summaries, prices = _build_universe(100, perfect_correlation=True)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is not None
    assert coef == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# C. Edge cases
# ---------------------------------------------------------------------------

def test_C1_all_mos_identical_returns_none():
    pairs = [(50.0, 0.05 + 0.01 * i) for i in range(40)]
    summaries, prices = _build_universe(40, pairs=pairs)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


def test_C2_all_returns_identical_returns_none():
    pairs = [(50.0 + 5 * i, 0.10) for i in range(40)]
    summaries, prices = _build_universe(40, pairs=pairs)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


def test_C3_none_mos_filtered_out():
    """Stocks with mos_pct=None are skipped; if the survivors fall below
    MIN_SAMPLE the function returns None."""
    summaries, prices = _build_universe(40, perfect_correlation=True)
    # Null out the first 20 stocks' mos → 20 remain → below MIN_SAMPLE=30.
    for s in summaries[:20]:
        # Re-build with mos_pct=None (StockSummary is a pydantic model — we
        # build a new one keyed on ticker so prices stay in sync).
        idx = summaries.index(s)
        summaries[idx] = _summary(s.ticker, mos_pct=None, rank=s.rank)
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


def test_C4_data_quality_corruption_skipped():
    """Stocks tagged with the Step 7.5 sanity-guard warning are skipped
    even if their mos_pct is somehow set. Behaviour matches Phase 3c spec."""
    summaries, prices = _build_universe(40, perfect_correlation=True)
    # Tag the first 20 with the warning. Their mos_pct is still set, but
    # the function must skip them. With 20 valid pairs left → below MIN_SAMPLE.
    for i, s in enumerate(summaries[:20]):
        summaries[i] = _summary(
            s.ticker,
            mos_pct=s.margin_of_safety_pct,
            valuation_warnings=["data_quality_input_corruption"],
            rank=s.rank,
        )
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


# ---------------------------------------------------------------------------
# D. Insufficient prices
# ---------------------------------------------------------------------------

def test_D1_short_price_history_skipped():
    """Stock with len(prices) < lookback_days is skipped."""
    summaries, prices = _build_universe(40, perfect_correlation=True)
    short_df = _prices_with_return(days=DEFAULT_LOOKBACK_DAYS - 5, return_pct=0.10)
    # Replace the first 20 tickers' prices with too-short series → only 20
    # valid pairs left → below MIN_SAMPLE → returns None.
    for s in summaries[:20]:
        prices[s.ticker] = short_df
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


def test_D2_missing_prices_skipped():
    """Stock missing from prices_by_ticker is skipped."""
    summaries, prices = _build_universe(40, perfect_correlation=True)
    for s in summaries[:20]:
        del prices[s.ticker]
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


# ---------------------------------------------------------------------------
# E. Negative price defensive
# ---------------------------------------------------------------------------

def test_E1_zero_or_negative_lookback_close_skipped():
    """If the lookback anchor close is non-positive, the stock is skipped.
    Synthetic edge — wouldn't happen with real yfinance data, but the
    function should be robust."""
    summaries, prices = _build_universe(40, perfect_correlation=True)
    # Force lookback anchor close to 0 for the first 20 tickers → skipped.
    for s in summaries[:20]:
        df = prices[s.ticker].copy()
        df.iloc[-DEFAULT_LOOKBACK_DAYS, df.columns.get_loc("Close")] = 0.0
        df.iloc[-DEFAULT_LOOKBACK_DAYS, df.columns.get_loc("Adj Close")] = 0.0
        prices[s.ticker] = df
    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is None


# ---------------------------------------------------------------------------
# F. Integration
# ---------------------------------------------------------------------------

def test_F1_realistic_universe_finite_in_bounds():
    """Synthetic 50 stocks with realistic distribution:
    - 5 with corruption warning (skip)
    - 5 with mos_pct=None (skip)
    - 40 valid pairs → returns finite Spearman in [-1, 1]."""
    summaries, prices = _build_universe(50, seed=7)

    for i in range(5):
        s = summaries[i]
        summaries[i] = _summary(
            s.ticker,
            mos_pct=s.margin_of_safety_pct,
            valuation_warnings=["data_quality_input_corruption"],
            rank=s.rank,
        )
    for i in range(5, 10):
        s = summaries[i]
        summaries[i] = _summary(s.ticker, mos_pct=None, rank=s.rank)

    coef = compute_mos_trailing_ic(rankings=summaries, prices_by_ticker=prices)
    assert coef is not None
    assert math.isfinite(coef)
    assert -1.0 <= coef <= 1.0


# ---------------------------------------------------------------------------
# Module-level constants regression
# ---------------------------------------------------------------------------

def test_default_lookback_is_one_trading_year():
    assert DEFAULT_LOOKBACK_DAYS == 252


def test_min_sample_threshold_is_30():
    assert MIN_SAMPLE == 30
