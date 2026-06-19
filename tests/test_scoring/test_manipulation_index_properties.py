"""P3-1: Property-based tests for manipulation_index pure functions.

Hypothesis ``@given`` tests asserting invariants that hold for ALL valid
inputs — not just the hand-picked cases in ``test_manipulation_index.py``.

Conventions match ``test_transforms_properties.py``:
- Small generated inputs so the default 200 ms deadline isn't tripped.
- No ``@settings(deadline=None)`` — slow examples are signal.
- One ``@given`` per logical invariant.

Coverage:
- M1: ``compute_adjusted_composite`` output is always in [0, 100]
      for any composite ∈ [0, 100] and index ∈ [0, 100].
- M2: ``compute_adjusted_composite`` output is always ≤ composite
      (the soft penalty can only reduce, never increase, the score).
- M3: ``compute_manipulation_index`` output is always in [0, 100]
      for any non-negative raw weight sum (clipping contract).
- M4: ``compute_adjusted_composite`` penalty is monotone in index —
      higher index → lower (or equal) adjusted score when composite
      is held fixed.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from compute.scoring.manipulation_index import (
    MAX_INDEX,
    compute_adjusted_composite,
    compute_manipulation_index,
)

# ---------------------------------------------------------------------------
# M1 — compute_adjusted_composite output ∈ [0, 100]
# ---------------------------------------------------------------------------


@given(
    composite=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    index=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_M1_adjusted_composite_bounded_0_to_100(
    composite: float, index: float
) -> None:
    """M1: For any composite ∈ [0, 100] and index ∈ [0, 100], the adjusted
    composite is clamped to [0, 100].

    This is the domain contract the downstream UI + Pydantic schema both
    depend on (``composite_score_adjusted: float | None`` — when not None
    it must be a valid score, not a negative number).
    """
    result = compute_adjusted_composite(composite, index)
    assert 0.0 <= result <= 100.0, (
        f"adjusted composite {result} out of [0, 100] for "
        f"composite={composite}, index={index}"
    )


# ---------------------------------------------------------------------------
# M2 — adjusted composite ≤ composite (penalty never increases score)
# ---------------------------------------------------------------------------


@given(
    composite=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    index=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_M2_adjusted_composite_le_composite(
    composite: float, index: float
) -> None:
    """M2: adjusted ≤ round(composite, 2) for all valid inputs.

    The manipulation-index penalty can only reduce the composite
    (SKILL.md Rule 9 — the raw composite is preserved untouched;
    adjusted is the DISPLAY value). A mutation that turns the
    subtraction into an addition would flip this invariant.

    NOTE — contract finding: ``compute_adjusted_composite`` applies
    ``round(..., 2)`` to the output for display purposes.  This means
    the adjusted value is compared against ``round(composite, 2)``,
    not the raw float — a raw composite of 1.875 produces
    ``round(1.875 - 0, 2) == 1.88`` which is > 1.875 due to IEEE 754
    banker rounding, but ≤ ``round(1.875, 2) == 1.88``.  The invariant
    holds against the ROUNDED reference, not the raw composite.  This
    rounding behavior is intentional (display precision), but callers
    that compare ``adjusted`` vs the raw ``composite_score`` must
    account for it.
    """
    result = compute_adjusted_composite(composite, index)
    # Compare against the rounded reference — both values are rounded to 2dp.
    composite_rounded = round(composite, 2)
    assert result <= composite_rounded + 1e-9, (
        f"adjusted {result} > round(composite, 2)={composite_rounded} "
        f"(raw composite={composite}, index={index}) — penalty must not increase score"
    )


# ---------------------------------------------------------------------------
# M3 — compute_manipulation_index output ∈ [0, 100]
# ---------------------------------------------------------------------------


@given(
    flags=st.lists(
        st.sampled_from(
            [
                "sloan_accruals_top_decile",
                "beneish_manipulation_veto",
                "dechow_manipulation_veto",
                "non_reliance_filing",
                "manipulation_triple_flag",
                "rem_suspect",
                "restatement_history",
                "restatement_high_confidence",
                "late_filing_notification",
                "accruals_momentum_high",
                "loss_avoidance_pattern",
                "loss_avoidance_pattern_size_invariant",
                "beneish_high",
                "dechow_high",
                "insider_sell_cluster",
                "c_suite_unusual_sell",
                "totally_new_flag_2099",  # unknown flag — forward compat
            ]
        ),
        min_size=0,
        max_size=17,
        unique=True,
    ),
)
def test_M3_manipulation_index_bounded_0_to_max(flags: list[str]) -> None:
    """M3: For any subset of known + unknown flags, the manipulation
    index is in [0, MAX_INDEX].

    The SUM of all weight-table entries exceeds 100; the clipping
    contract ensures the output is always bounded.  An accidental
    removal of the ``min(max(...))`` clip would surface here as a
    saturation failure (out-of-bounds result).
    """
    result = compute_manipulation_index(flags, [])
    assert 0.0 <= result <= MAX_INDEX, (
        f"manipulation index {result} out of [0, {MAX_INDEX}] for flags={flags}"
    )


# ---------------------------------------------------------------------------
# M4 — penalty is monotone in index (fixed composite)
# ---------------------------------------------------------------------------


@given(
    composite=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    index_lo=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    index_hi=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_M4_adjusted_composite_monotone_in_index(
    composite: float, index_lo: float, index_hi: float
) -> None:
    """M4: If index_lo ≤ index_hi then adjusted(composite, index_lo) ≥
    adjusted(composite, index_hi).

    The penalty formula is linear in index, so the adjusted score is
    anti-monotone in the index (higher risk → lower display score).
    A sign flip in the formula would invert this invariant.
    """
    lo, hi = min(index_lo, index_hi), max(index_lo, index_hi)
    adj_lo = compute_adjusted_composite(composite, lo)
    adj_hi = compute_adjusted_composite(composite, hi)
    assert adj_lo >= adj_hi - 1e-9, (
        f"monotonicity violated: adjusted({composite}, {lo})={adj_lo} < "
        f"adjusted({composite}, {hi})={adj_hi}"
    )
