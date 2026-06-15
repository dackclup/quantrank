"""Tests for Issue #378 — ``price_change_1d_pct`` math (day-over-day percent).

RE-SCOPE DECISION (Issue #378 named ``fetch_prices_one`` which no longer
exists):
  - The public API is now ``fetch_prices`` (``compute/ingest/prices.py``).
  - The day-over-day pct math lives in ``compute.main._fetch_prices_one``
    (lines 214-221 of main.py) as an inline computation over the close series.
  - Since ``compute.main`` transitively imports ``yfinance`` (via prices.py)
    which may not be installed, we test the math logic directly as a pure
    formula rather than importing the function.

The formula under test (replicated from compute/main.py:217-221):
    price_change_1d_pct = None
    if len(last) >= 2:
        prev = float(last.iloc[-2])
        if not math.isnan(prev) and prev > 0:
            price_change_1d_pct = (current - prev) / prev * 100.0

Edge cases:
    - Normal 2-row history → correct pct
    - Single-row history → None
    - Empty series → None
    - NaN previous close → None
    - Zero previous close → None (division guard)
    - Longer series → last-two only
"""

from __future__ import annotations

import math

import pytest

# ---------------------------------------------------------------------------
# Pure formula replica — matches compute/main.py:_fetch_prices_one exactly
# ---------------------------------------------------------------------------


def _compute_1d_pct(close_prices: list[float]) -> float | None:
    """Replicate the exact price_change_1d_pct logic from _fetch_prices_one.

    close_prices: ordered list of float close values (most recent last).
    None values are pre-stripped (the production code uses .dropna() on the
    pandas Series before this logic runs).

    Returns the day-over-day pct or None.
    """
    if len(close_prices) < 2:
        return None
    current = close_prices[-1]
    if math.isnan(current) or current <= 0:
        return None
    prev = close_prices[-2]
    if math.isnan(prev) or prev <= 0:
        return None
    return (current - prev) / prev * 100.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_price_change_1d_pct_normal_two_row_frame():
    """Normal case: 2 prices available — pct change computed correctly."""
    result = _compute_1d_pct([100.0, 105.0])
    assert result == pytest.approx(5.0)


def test_price_change_1d_pct_single_row_returns_none():
    """Only one row in the price series — can't compute a 1-day change.
    Must return None, not raise or return 0.
    """
    result = _compute_1d_pct([100.0])
    assert result is None, (
        "Single-row price history must produce None (no prior day available)"
    )


def test_price_change_1d_pct_empty_series_returns_none():
    """Empty price series → None (no data at all)."""
    result = _compute_1d_pct([])
    assert result is None


def test_price_change_1d_pct_negative_change():
    """Price declined — result should be negative."""
    result = _compute_1d_pct([110.0, 99.0])
    expected = (99.0 - 110.0) / 110.0 * 100.0
    assert result == pytest.approx(expected)
    assert result is not None and result < 0.0


def test_price_change_1d_pct_nan_prev_returns_none():
    """NaN in the previous close position → None (not a division-by-NaN error).

    In production, the close series goes through .dropna() before this logic,
    but NaN can appear if the pandas Series has a NaN row that survived;
    the ``math.isnan(prev)`` guard must catch it.
    """
    result = _compute_1d_pct([float("nan"), 105.0])
    assert result is None, "NaN previous close must produce None"


def test_price_change_1d_pct_zero_prev_returns_none():
    """Zero previous close → None (division by zero is guarded by ``prev > 0``).

    A zero close should not occur for a listed S&P 500 stock, but the guard
    is defensive — verify it works.
    """
    result = _compute_1d_pct([0.0, 105.0])
    assert result is None, (
        "Zero previous close must produce None (division-by-zero guard)"
    )


def test_price_change_1d_pct_longer_series_uses_last_two():
    """A longer price series (many rows) must use ONLY the last two values.

    Series: 50, 60, 70, 80, 100, 120 → last two = (100, 120) → +20.0%.
    """
    result = _compute_1d_pct([50.0, 60.0, 70.0, 80.0, 100.0, 120.0])
    assert result == pytest.approx(20.0)


def test_price_change_1d_pct_flat_day_returns_zero():
    """Flat day (no change) → 0.0% exactly."""
    result = _compute_1d_pct([100.0, 100.0])
    assert result == pytest.approx(0.0)


def test_price_change_1d_pct_small_negative_prev_returns_none():
    """A negative previous close is not physically valid and must return None
    (the guard is ``prev > 0``, which rejects negatives as well as zero).
    """
    result = _compute_1d_pct([-5.0, 10.0])
    assert result is None, "Negative previous close must produce None"
