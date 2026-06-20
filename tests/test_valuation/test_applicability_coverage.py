"""Coverage-gap tests for compute.valuation.applicability.

Targets the uncovered branches in the 2026-06-20 baseline:
  - Lines 180-183 in _finite_positive (non-castable value, NaN check)
  - Line 342 in check_multiples_ev_ebitda_applicability
    (missing_or_non_positive_peer_ev_ebitda)

These are applicability-gate contracts: each gate must correctly
suppress a valuation method when inputs are missing or corrupt rather
than silently passing them through and producing a garbage number.
"""

from __future__ import annotations

import math

from compute.valuation.applicability import (
    _finite_positive,
    check_multiples_ev_ebitda_applicability,
)

# ---------------------------------------------------------------------------
# _finite_positive edge cases (lines 180-183)
# ---------------------------------------------------------------------------

def test_finite_positive_non_castable_value_returns_false() -> None:
    """A non-castable input (e.g. a plain dict) must return False.

    Line 180-181: ``try: float(x) / except (TypeError, ValueError): return False``.
    This fires when callers pass unexpected types (e.g. a list where a
    float was expected), preventing a TypeError from propagating up to
    the applicability gate.
    """
    assert _finite_positive({}) is False, (
        "_finite_positive({}) must return False (non-castable type)"
    )
    assert _finite_positive([1.0]) is False, (
        "_finite_positive([1.0]) must return False (list is non-castable to float)"
    )


def test_finite_positive_nan_returns_false() -> None:
    """float('nan') must return False.

    Line 182-183: ``if v != v: return False`` (NaN self-inequality check).
    This is the IEEE-754 NaN identity: NaN != NaN is True.  A NaN input
    to a valuation gate must not pass — it would produce a NaN fair price.
    """
    assert _finite_positive(math.nan) is False, (
        "_finite_positive(nan) must return False (NaN guard)"
    )


def test_finite_positive_infinity_behavior() -> None:
    """Document actual behavior: _finite_positive(inf) currently returns True.

    NOTE: the docstring says "finite, strictly-positive float" but there is
    no math.isfinite() guard in the implementation — only the NaN (v != v)
    and non-positive (v <= 0) checks.  inf > 0 so it passes both.

    This test documents the CURRENT behavior so any future fix is visible.
    In the production data path (peer EV/EBITDA medians from real S&P tickers)
    inf cannot be produced, so this gap has no known production impact.
    See: _finite_positive lines 182-184 in applicability.py.
    """
    # inf passes the current implementation (no math.isfinite guard)
    assert _finite_positive(math.inf) is True  # current behavior, not ideal
    # -inf fails the v <= 0 guard
    assert _finite_positive(-math.inf) is False


def test_finite_positive_zero_returns_false() -> None:
    """Zero must return False — the gate requires strictly positive."""
    assert _finite_positive(0.0) is False
    assert _finite_positive(0) is False


def test_finite_positive_negative_returns_false() -> None:
    """Negative values must return False."""
    assert _finite_positive(-1.0) is False


def test_finite_positive_valid_returns_true() -> None:
    """Positive, finite floats and ints must return True."""
    assert _finite_positive(1.0) is True
    assert _finite_positive(1) is True
    assert _finite_positive(1_000_000.0) is True


# ---------------------------------------------------------------------------
# check_multiples_ev_ebitda_applicability: missing peer ev/ebitda (line 342)
# ---------------------------------------------------------------------------

def test_ev_ebitda_applicability_skipped_when_peer_median_missing() -> None:
    """check_multiples_ev_ebitda_applicability returns skip when
    peer_ev_ebitda_median is None.

    Line 342: ``if not _finite_positive(peer_ev_ebitda_median): return _skip(...)``
    This fires when the peer-median computation returns None (e.g., a sector
    with fewer than MIN_PEERS peers or a sector where all peers have negative EBITDA).
    Without this gate the multiples formula would try to divide by None.
    """
    result = check_multiples_ev_ebitda_applicability(
        sector="Technology",
        ebitda_ttm=50_000_000.0,
        peer_ev_ebitda_median=None,  # no peers available
        lag_status="fresh",
    )
    assert not result.applicable, (
        "ev_ebitda method must be skipped when peer_ev_ebitda_median is None"
    )
    assert result.reason == "missing_or_non_positive_peer_ev_ebitda", (
        f"Expected reason 'missing_or_non_positive_peer_ev_ebitda', "
        f"got {result.reason!r}"
    )


def test_ev_ebitda_applicability_skipped_when_peer_median_zero() -> None:
    """peer_ev_ebitda_median=0 must also trigger the skip gate.

    Zero peer median would produce a divide-by-zero or meaningless multiple.
    """
    result = check_multiples_ev_ebitda_applicability(
        sector="Technology",
        ebitda_ttm=50_000_000.0,
        peer_ev_ebitda_median=0.0,
        lag_status="fresh",
    )
    assert not result.applicable
    assert result.reason == "missing_or_non_positive_peer_ev_ebitda"


def test_ev_ebitda_applicability_skipped_when_peer_median_negative() -> None:
    """Negative peer median (sector with mostly-negative EBITDA) must skip."""
    result = check_multiples_ev_ebitda_applicability(
        sector="Technology",
        ebitda_ttm=50_000_000.0,
        peer_ev_ebitda_median=-5.0,
        lag_status="fresh",
    )
    assert not result.applicable
    assert result.reason == "missing_or_non_positive_peer_ev_ebitda"


def test_ev_ebitda_applicability_applicable_when_valid() -> None:
    """Control: with valid inputs, the method IS applicable."""
    result = check_multiples_ev_ebitda_applicability(
        sector="Technology",
        ebitda_ttm=50_000_000.0,
        peer_ev_ebitda_median=15.0,
        lag_status="fresh",
    )
    assert result.applicable, (
        "ev_ebitda must be applicable when all inputs are valid"
    )
