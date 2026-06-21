"""Coverage-gap tests for compute.valuation.graham.

Targets the single uncovered block in the 2026-06-20 baseline (~89%):

    Lines 110-117 — the post-gate product sanity guard:
        if product <= 0 or not math.isfinite(product):
            return (None, MethodApplicability(False, reason=<constant>))

The normal applicability gate (check_graham_applicability) uses _finite_positive
which rejects None / non-positive / NaN inputs but does NOT guard against
infinity (confirmed: _finite_positive(math.inf) is True — see
test_applicability_coverage.py).  So the only viable OFFLINE path to exercise
this branch is via inf / float-overflow inputs that legitimately pass the gate
but produce a non-finite product.

No network calls.  All tests are pure-function, deterministic, offline.
"""

from __future__ import annotations

import math
import sys

from compute.valuation.graham import (
    _GRAHAM_MULTIPLIER,
    _POST_GATE_PRODUCT_NON_POSITIVE,
    graham_fair_price,
)

# ---------------------------------------------------------------------------
# Module-level constant contracts
# ---------------------------------------------------------------------------


def test_graham_multiplier_is_22_point_5() -> None:
    """The Graham multiplier MUST be 22.5 (canonical max-PE × max-PB).

    This constant is methodologically load-bearing — changing it would silently
    alter every fair-price output.  Locking it here ensures any accidental edit
    breaks a test rather than silently distorting outputs.
    Reference: Graham (1949) §15; Damodaran practitioner default.
    """
    assert _GRAHAM_MULTIPLIER == 22.5, (
        f"Graham multiplier changed from canonical 22.5 to {_GRAHAM_MULTIPLIER!r}; "
        "this is a methodology-breaking change — escalate to methodology-scientist"
    )


def test_post_gate_reason_constant_string() -> None:
    """The post-gate skip reason string must be stable.

    Step 5 ensemble and internal logs key on this string to distinguish a
    regression in the gate logic from a normal applicability skip.  Renaming
    it without updating downstream consumers would produce a silent mis-
    classification.
    """
    assert _POST_GATE_PRODUCT_NON_POSITIVE == "graham_product_non_positive_post_gate", (
        f"Post-gate skip reason identifier changed: {_POST_GATE_PRODUCT_NON_POSITIVE!r}"
    )


# ---------------------------------------------------------------------------
# Post-gate safety guard — product non-finite (lines 110-117)
# ---------------------------------------------------------------------------
# Context: _finite_positive(math.inf) returns True (no math.isfinite guard
# in _finite_positive — see test_applicability_coverage.py).  So math.inf
# passes check_graham_applicability but 22.5 * inf * finite = inf which is
# NOT math.isfinite, triggering the post-gate return.


def test_graham_infinite_eps_triggers_post_gate_guard() -> None:
    """eps_3y_avg=inf passes the applicability gate but fails the product guard.

    _finite_positive(inf) is True (inf > 0, not NaN, castable).
    22.5 * inf * 10.0 = inf → not math.isfinite(inf) → post-gate fires.
    Result must be (None, MethodApplicability(applicable=False,
    reason='graham_product_non_positive_post_gate')).
    """
    fair, app = graham_fair_price(
        eps_3y_avg=math.inf,
        tangible_book_value_per_share=10.0,
        lag_status="fresh",
    )
    assert fair is None, (
        "graham_fair_price must return None for eps_3y_avg=inf"
    )
    assert app.applicable is False, (
        "method must be NOT applicable when product is non-finite"
    )
    assert app.reason == _POST_GATE_PRODUCT_NON_POSITIVE, (
        f"expected reason {_POST_GATE_PRODUCT_NON_POSITIVE!r}, got {app.reason!r}"
    )


def test_graham_infinite_tbvps_triggers_post_gate_guard() -> None:
    """tangible_book_value_per_share=inf passes the gate but fails product guard.

    Mirrors the eps=inf case — ensures both input positions exercise the
    post-gate branch, not just one.
    """
    fair, app = graham_fair_price(
        eps_3y_avg=5.0,
        tangible_book_value_per_share=math.inf,
        lag_status="fresh",
    )
    assert fair is None, (
        "graham_fair_price must return None for tangible_book_value_per_share=inf"
    )
    assert app.applicable is False
    assert app.reason == _POST_GATE_PRODUCT_NON_POSITIVE, (
        f"expected reason {_POST_GATE_PRODUCT_NON_POSITIVE!r}, got {app.reason!r}"
    )


def test_graham_both_infinite_inputs_trigger_post_gate_guard() -> None:
    """Both inputs inf → product inf → post-gate fires.

    Exercises the compound case where both operands are infinite.
    """
    fair, app = graham_fair_price(
        eps_3y_avg=math.inf,
        tangible_book_value_per_share=math.inf,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == _POST_GATE_PRODUCT_NON_POSITIVE


def test_graham_float_overflow_triggers_post_gate_guard() -> None:
    """Float overflow (sys.float_info.max × sys.float_info.max) → inf product → post-gate.

    sys.float_info.max ≈ 1.8e308.  22.5 × max × max overflows IEEE-754 double
    to inf.  Both inputs pass _finite_positive (finite, positive) so the
    applicability gate passes, but the product guard catches the overflow.
    """
    huge = sys.float_info.max
    fair, app = graham_fair_price(
        eps_3y_avg=huge,
        tangible_book_value_per_share=huge,
        lag_status="fresh",
    )
    assert fair is None, (
        f"graham_fair_price must return None when product overflows to inf "
        f"(eps={huge}, tbvps={huge})"
    )
    assert app.applicable is False
    assert app.reason == _POST_GATE_PRODUCT_NON_POSITIVE


def test_graham_float_underflow_product_zero_triggers_post_gate_guard() -> None:
    """Float underflow: subnormal × subnormal → product underflows to 0.0 → product <= 0 fires.

    The minimum positive subnormal (~5e-324) passes _finite_positive (> 0.0).
    22.5 × subnormal × subnormal = 0.0 due to IEEE-754 underflow.
    product <= 0 branch fires (the other arm of the OR condition on line 110).

    This exercises the ``product <= 0`` branch of the guard, complementing
    the ``not math.isfinite(product)`` branch tested by the inf/overflow cases.
    """
    # sys.float_info.min is the minimum NORMAL positive double (~2.2e-308).
    # The minimum subnormal is float_info.min * float_info.epsilon ≈ 5e-324,
    # accessible as the smallest nonzero float.
    tiny = sys.float_info.min * sys.float_info.epsilon  # ≈ 5e-324
    # Sanity: confirm tiny itself is > 0 (passes _finite_positive gate)
    assert tiny > 0.0, "test precondition: tiny must be > 0"
    # And the product must be 0.0 (underflow)
    expected_product = 22.5 * tiny * tiny
    assert expected_product == 0.0, (
        f"test precondition failed: product {expected_product} is not 0.0 — "
        "Python's float may have changed underflow behavior"
    )

    fair, app = graham_fair_price(
        eps_3y_avg=tiny,
        tangible_book_value_per_share=tiny,
        lag_status="fresh",
    )
    assert fair is None, (
        "graham_fair_price must return None when product underflows to 0.0"
    )
    assert app.applicable is False
    assert app.reason == _POST_GATE_PRODUCT_NON_POSITIVE


# ---------------------------------------------------------------------------
# Post-gate guard does NOT fire for valid inputs (regression guard)
# ---------------------------------------------------------------------------


def test_graham_post_gate_does_not_fire_on_valid_inputs() -> None:
    """Confirm the post-gate branch is NOT reached for typical positive inputs.

    The branch comment says it is "mathematically unreachable" via normal gate
    logic.  This test locks that claim: valid finite positive inputs must
    produce a computable fair_value, not the post-gate None return.
    Contrasts directly with the inf / overflow cases above.
    """
    fair, app = graham_fair_price(
        eps_3y_avg=3.0,
        tangible_book_value_per_share=15.0,
        lag_status="fresh",
    )
    assert fair is not None, (
        "post-gate guard must NOT fire for normal finite positive inputs"
    )
    assert app.applicable is True
    assert app.reason is None
    # Internal consistency
    assert math.isclose(fair * fair, 22.5 * 3.0 * 15.0, rel_tol=1e-9)


def test_graham_post_gate_does_not_fire_under_soft_lag_with_inf_rejected_by_gate() -> None:
    """Soft lag + valid finite inputs → normal result, gate does not fire.

    Combined boundary test: lag_status='soft' is permissive (tests 10/11 in
    sibling test_graham.py cover this), and valid finite inputs must not
    trigger the post-gate branch.
    """
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=10.0,
        lag_status="soft",
    )
    assert app.applicable is True
    assert fair is not None
    assert math.isclose(fair * fair, 22.5 * 2.0 * 10.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Interaction: inf input + hard lag_status
# ---------------------------------------------------------------------------


def test_graham_hard_lag_takes_precedence_over_inf_eps() -> None:
    """hard lag_status triggers the applicability gate BEFORE the product guard.

    check_graham_applicability checks lag_status='hard' only AFTER both input
    guards (eps, tbvps).  With eps=inf and tbvps=10.0, _finite_positive(inf)
    returns True, _finite_positive(10.0) returns True, and then lag='hard'
    triggers stale_filing_hard — so the applicability gate returns BEFORE the
    post-gate product check.

    This ensures the two code paths are correctly ordered and the stale-filing
    reason surfaces, not the post-gate reason.
    """
    fair, app = graham_fair_price(
        eps_3y_avg=math.inf,
        tangible_book_value_per_share=10.0,
        lag_status="hard",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "stale_filing_hard", (
        f"hard lag must surface stale_filing_hard, not {app.reason!r}"
    )
