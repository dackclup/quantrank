"""Property-based tests for the Issue #177 PR-A shadow trimmed-median invariants.

Two invariants are tested for all randomly-generated method-value inputs:

1. ``median_trimmed``, when not None (not majority-collapse), is within
   ``[min(applicable_values), max(applicable_values)]`` — the trimmed
   estimate cannot escape the range of the methods that produced it.

2. ``methods_excluded_from_median`` is always a SUBSET of the applicable
   method names — the trim can only exclude methods that actually ran.

The trim is symmetric (extreme-HIGH and extreme-LOW are flagged equally by
``_classify_outliers``), but testing the numerical direction of symmetry is
handled by the deterministic tests in ``test_ensemble.py``
(``test_shadow_trimmed_symmetry_high``). These properties focus on the
structural / domain invariants that must hold for ALL inputs.

Style: one ``@given`` per invariant, Hypothesis strategies matching production
input ranges, default deadline (no ``@settings(deadline=None)``).
"""

from __future__ import annotations

import math

from hypothesis import assume, given
from hypothesis import strategies as st

from compute.valuation.ensemble import METHOD_NAMES, FairPriceMethodResult, _aggregate_methods

# ---------------------------------------------------------------------------
# Strategy: build a methods dict with arbitrary applicable values
# ---------------------------------------------------------------------------

def _build_methods(
    values: list[float],
    current_price: float,
) -> dict[str, FairPriceMethodResult]:
    """Build a methods dict using the first len(values) METHOD_NAMES.

    Methods not in values are marked as not applicable (skipped).  At least
    one value is supplied by construction (assumed by the callers).
    """
    out: dict[str, FairPriceMethodResult] = {}
    for i, name in enumerate(METHOD_NAMES):
        if i < len(values):
            out[name] = FairPriceMethodResult(
                value=values[i],
                applicable=True,
                reason=None,
                tier_used=None,
            )
        else:
            out[name] = FairPriceMethodResult(
                value=None,
                applicable=False,
                reason="test_skipped",
                tier_used=None,
            )
    return out


# ---------------------------------------------------------------------------
# Property 1 — median_trimmed, when not None, is within [min, max] of
# all applicable method values (not just the survivors).
# ---------------------------------------------------------------------------

@given(
    current_price=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False,
                            allow_infinity=False),
    values=st.lists(
        st.floats(min_value=0.01, max_value=100_000.0, allow_nan=False,
                  allow_infinity=False),
        min_size=1,
        max_size=6,
    ),
)
def test_median_trimmed_within_applicable_range(
    current_price: float, values: list[float]
) -> None:
    """median_trimmed is always in [min(applicable), max(applicable)] when
    not None.

    The shadow trimmed median is the median of a subset of the applicable
    values (those not flagged as outliers).  A subset's median cannot exceed
    the full set's max or fall below the full set's min.  This is the
    domain-containment invariant.
    """
    assume(math.isfinite(current_price) and current_price > 0)
    assume(all(math.isfinite(v) and v > 0 for v in values))

    methods = _build_methods(values, current_price)
    _aggs, _warnings, median_trimmed, _excluded = _aggregate_methods(
        methods, current_price=current_price
    )

    if median_trimmed is None:
        # Majority collapse — no bound to check.
        return

    lo = min(values)
    hi = max(values)
    assert lo <= median_trimmed <= hi + 1e-9, (
        f"median_trimmed={median_trimmed} outside applicable range [{lo}, {hi}] "
        f"with current_price={current_price}, values={values}"
    )


# ---------------------------------------------------------------------------
# Property 2 — methods_excluded_from_median is a subset of applicable names.
# ---------------------------------------------------------------------------

@given(
    current_price=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False,
                            allow_infinity=False),
    values=st.lists(
        st.floats(min_value=0.01, max_value=100_000.0, allow_nan=False,
                  allow_infinity=False),
        min_size=1,
        max_size=6,
    ),
)
def test_methods_excluded_is_subset_of_applicable_names(
    current_price: float, values: list[float]
) -> None:
    """methods_excluded_from_median contains only names of applicable methods.

    The trim can only exclude methods that ran (applicable=True, value not
    None).  It must never invent or re-reference skipped method names.
    """
    assume(math.isfinite(current_price) and current_price > 0)
    assume(all(math.isfinite(v) and v > 0 for v in values))

    methods = _build_methods(values, current_price)
    applicable_names = {
        name for name, r in methods.items()
        if r.applicable and r.value is not None
    }

    _aggs, _warnings, _median_trimmed, methods_excluded = _aggregate_methods(
        methods, current_price=current_price
    )

    assert set(methods_excluded) <= applicable_names, (
        f"methods_excluded={methods_excluded} contains names not in "
        f"applicable_names={applicable_names}.  "
        "The trim must only reference methods that ran."
    )
