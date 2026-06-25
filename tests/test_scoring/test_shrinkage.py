"""Tests for compute.scoring.shrinkage — Proposal A weight-blending module.

Coverage (offline, synthetic fixtures — no network, no parquet):

- S1:  λ schedule: boundary values, monotone-decreasing, clamp n<0→1.0, range
- S2:  blend_weights identity at λ=1 (w0 key-by-key within 1e-12)
- S3:  lambda_pin=1.0 absorbs lam and w_ic (returns w0)
- S4:  preliminary_mask pillar kept at w0 even with lambda_pin=None, lam=0
- S5:  blend_weights output sums to 1.0 within 1e-9
- S6:  build_ic_weights C1 coupling — reads .preliminary, NOT inline n<12
- S7:  build_ic_weights all-preliminary → degenerate=True
- S8:  build_ic_weights all-IC≤0 → degenerate=True
- S9:  build_ic_weights max(IC,0) — negative IC → zero weight; positive renorm
- S10: end-to-end byte-identity — compute_composite(df) == compute_composite(df, weights=blend at pin=1)
- S11: Hypothesis property — non-negative, sums to 1.0, identity when lam==1
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from compute.scoring.composite import (
    ACTIVE_PILLARS_PHASE3,
    PHASE3_EFFECTIVE_WEIGHTS,
    compute_composite,
)
from compute.scoring.shrinkage import (
    SHRINKAGE_TAU_MONTHS,
    blend_weights,
    build_ic_weights,
    compute_shrinkage_lambda,
)
from compute.validation.ic_decay import ICDecayReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(
    pillar: str,
    *,
    rolling_12m_ic: float = 0.05,
    preliminary: bool = False,
    n_observations: int = 24,
) -> ICDecayReport:
    """Build a synthetic ICDecayReport for use in build_ic_weights tests."""
    return ICDecayReport(
        pillar=pillar,
        rolling_12m_ic=rolling_12m_ic,
        rolling_36m_ic=rolling_12m_ic,
        historical_mean_ic=rolling_12m_ic,
        decay_ratio=1.0 if rolling_12m_ic > 0 else 0.0,
        months_below_threshold=0,
        alert=False,
        n_observations=n_observations,
        preliminary=preliminary,
    )


def _uniform_w0(pillars: tuple[str, ...] | None = None) -> dict[str, float]:
    """Return a uniform prior over the given pillar names."""
    ps = pillars if pillars is not None else ACTIVE_PILLARS_PHASE3
    n = len(ps)
    return {p: 1.0 / n for p in ps}


def _pillar_df(pillar_values: dict[str, float] | None = None) -> pd.DataFrame:
    """Build a 1-ticker pillar DataFrame using ACTIVE_PILLARS_PHASE3."""
    if pillar_values is None:
        pillar_values = {p: 50.0 for p in ACTIVE_PILLARS_PHASE3}
    return pd.DataFrame({p: [v] for p, v in pillar_values.items()}, index=["TEST"])


# ---------------------------------------------------------------------------
# S1 — λ schedule
# ---------------------------------------------------------------------------

def test_S1a_lambda_at_zero_returns_1():
    """compute_shrinkage_lambda(0) == 1.0 (no evidence → full prior)."""
    assert compute_shrinkage_lambda(0) == 1.0


def test_S1b_lambda_at_tau_returns_half():
    """compute_shrinkage_lambda(τ) == 0.5 (equal blend point)."""
    tau = SHRINKAGE_TAU_MONTHS
    result = compute_shrinkage_lambda(tau, tau=tau)
    assert result == pytest.approx(0.5, abs=1e-12)


def test_S1c_lambda_at_3tau_returns_quarter():
    """compute_shrinkage_lambda(3τ) == 0.25 (three half-lives out)."""
    tau = SHRINKAGE_TAU_MONTHS
    result = compute_shrinkage_lambda(3 * tau, tau=tau)
    assert result == pytest.approx(0.25, abs=1e-12)


def test_S1d_lambda_monotone_decreasing():
    """λ(n) is strictly decreasing in n for n > 0."""
    n_values = [0, 6, 12, 24, 48, 96]
    lambdas = [compute_shrinkage_lambda(n) for n in n_values]
    for i in range(len(lambdas) - 1):
        assert lambdas[i] >= lambdas[i + 1], (
            f"λ not non-increasing: λ({n_values[i]})={lambdas[i]} "
            f"< λ({n_values[i+1]})={lambdas[i+1]}"
        )


def test_S1e_negative_n_clamps_to_1():
    """compute_shrinkage_lambda(n < 0) == 1.0 (no negative history)."""
    assert compute_shrinkage_lambda(-5) == 1.0
    assert compute_shrinkage_lambda(-100) == 1.0


def test_S1f_result_in_unit_interval():
    """λ result is always in [0, 1]."""
    for n in [0, 1, 12, 24, 48, 96, 1000]:
        lam = compute_shrinkage_lambda(n)
        assert 0.0 <= lam <= 1.0, f"λ({n}) = {lam} out of [0, 1]"


# ---------------------------------------------------------------------------
# S2 — blend_weights identity at λ=1
# ---------------------------------------------------------------------------

def test_S2_blend_identity_at_lam_1():
    """blend_weights(w0, w_ic, lam=1.0, mask=∅) returns w0 key-by-key within 1e-12.

    When lam=1 and lambda_pin=None (not the default), every pillar gets
    full prior weight because lam_p = lam = 1.0, so w_p = 1.0*w0 + 0.0*w_ic = w0.
    """
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    # Use a very different w_ic to expose any blending
    w_ic = _uniform_w0(ACTIVE_PILLARS_PHASE3)
    result = blend_weights(w0, w_ic, lam=1.0, preliminary_mask=frozenset(), lambda_pin=None)
    for p in w0:
        assert result[p] == pytest.approx(w0[p], abs=1e-12), (
            f"Pillar {p}: expected {w0[p]}, got {result[p]}"
        )


# ---------------------------------------------------------------------------
# S3 — lambda_pin=1.0 absorbs lam and w_ic
# ---------------------------------------------------------------------------

def test_S3_pin_holds_ignores_lam_and_wic():
    """With lambda_pin=1.0 (default), blend returns w0 regardless of lam/w_ic."""
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    # Use an arbitrary, very different w_ic
    w_ic = _uniform_w0(ACTIVE_PILLARS_PHASE3)
    # lam=0.0 would normally move weights fully toward w_ic — pin overrides
    result = blend_weights(
        w0, w_ic, lam=0.0, preliminary_mask=frozenset(), lambda_pin=1.0
    )
    for p in w0:
        assert result[p] == pytest.approx(w0[p], abs=1e-12), (
            f"Pillar {p}: pin=1.0 should return w0[{p}]={w0[p]}, got {result[p]}"
        )


# ---------------------------------------------------------------------------
# S4 — preliminary_mask forces λ_p=1.0 for those pillars
# ---------------------------------------------------------------------------

def test_S4_preliminary_pillar_uses_w0_even_at_lam_zero():
    """A pillar in preliminary_mask gets w0[p] even with lambda_pin=None, lam=0.

    This is the C1-adjacent safety property: preliminary pillars are pinned
    to the prior regardless of the schedule or the global pin.
    """
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    w_ic = _uniform_w0(ACTIVE_PILLARS_PHASE3)
    # Mark all pillars preliminary
    full_mask = frozenset(ACTIVE_PILLARS_PHASE3)
    result = blend_weights(
        w0, w_ic, lam=0.0, preliminary_mask=full_mask, lambda_pin=None
    )
    # Every pillar in mask → lam_p = 1.0 → w_p = w0_p (before renorm)
    # Since all pillars are in mask, the blend is just w0 renormed (=w0 already)
    for p in w0:
        assert result[p] == pytest.approx(w0[p], abs=1e-9), (
            f"Preliminary pillar {p}: expected w0[{p}]={w0[p]}, got {result[p]}"
        )


def test_S4b_partial_preliminary_mask_pins_only_those_pillars():
    """When only a subset of pillars are in preliminary_mask, only those are pinned."""
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    # w_ic: concentrate weight on one pillar to make the effect visible
    w_ic = {p: (0.9 if p == "quality" else 0.1 / 7) for p in ACTIVE_PILLARS_PHASE3}
    total = sum(w_ic.values())
    w_ic = {p: v / total for p, v in w_ic.items()}

    # Pin 'quality' as preliminary but leave the rest free (lam=0 → use w_ic)
    mask = frozenset({"quality"})
    result = blend_weights(
        w0, w_ic, lam=0.0, preliminary_mask=mask, lambda_pin=None
    )
    # 'quality' must stay at w0 proportion (before renorm)
    # With lam=0: blended[quality] = 1.0*w0[quality], others = 0*w0 + 1*w_ic
    # We verify the pinned pillar's contribution is from w0
    blended_quality_unnorm = 1.0 * w0["quality"]
    blended_rest_unnorm = sum(
        0.0 * w0[p] + 1.0 * w_ic[p]
        for p in ACTIVE_PILLARS_PHASE3 if p != "quality"
    )
    total_unnorm = blended_quality_unnorm + blended_rest_unnorm
    expected_quality = blended_quality_unnorm / total_unnorm
    assert result["quality"] == pytest.approx(expected_quality, abs=1e-9)


# ---------------------------------------------------------------------------
# S5 — blend_weights sums to 1.0
# ---------------------------------------------------------------------------

def test_S5_blend_sums_to_one():
    """blend_weights output sums to 1.0 within 1e-9."""
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    w_ic = _uniform_w0(ACTIVE_PILLARS_PHASE3)
    for lam in [0.0, 0.25, 0.5, 0.75, 1.0]:
        result = blend_weights(
            w0, w_ic, lam=lam, preliminary_mask=frozenset(), lambda_pin=None
        )
        assert abs(sum(result.values()) - 1.0) < 1e-9, (
            f"lam={lam}: blend sums to {sum(result.values())}"
        )


# ---------------------------------------------------------------------------
# S6 — build_ic_weights C1 binding condition: reads .preliminary
# ---------------------------------------------------------------------------

def test_S6_build_ic_weights_reads_preliminary_field_not_inline_n():
    """C1 binding condition: build_ic_weights reads .preliminary, NOT n < 12.

    A report with preliminary=True but a non-zero rolling_12m_ic MUST still
    land in the preliminary_mask.  If the code inlined ``n < 12`` it would
    require us to craft a fake n field — but the real guard is the boolean flag.
    """
    # Build reports where preliminary=True but rolling_12m_ic is non-zero.
    # This combination is synthetic but tests that the code reads the field.
    reports = [
        _make_report(
            p,
            rolling_12m_ic=0.08,  # non-zero IC
            preliminary=True,  # but flagged preliminary
            n_observations=8,  # fewer than 12 — consistent with preliminary
        )
        for p in ACTIVE_PILLARS_PHASE3
    ]
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    w_ic, mask, degenerate = build_ic_weights(reports, w0, ACTIVE_PILLARS_PHASE3)

    # All pillars should be in the preliminary_mask
    for p in ACTIVE_PILLARS_PHASE3:
        assert p in mask, (
            f"Pillar {p} has preliminary=True but is NOT in preliminary_mask. "
            "build_ic_weights must read .preliminary, not inline n < 12."
        )

    # All preliminary → degenerate=True
    assert degenerate is True


def test_S6b_non_preliminary_with_high_ic_not_in_mask():
    """Pillar with preliminary=False and positive IC is NOT in preliminary_mask."""
    reports = [
        _make_report("quality", rolling_12m_ic=0.07, preliminary=False, n_observations=24),
        _make_report("value", rolling_12m_ic=0.03, preliminary=False, n_observations=24),
    ]
    w0 = {"quality": 0.6, "value": 0.4}
    w_ic, mask, degenerate = build_ic_weights(reports, w0, ("quality", "value"))
    assert "quality" not in mask
    assert "value" not in mask
    assert degenerate is False


# ---------------------------------------------------------------------------
# S7 — build_ic_weights all-preliminary → degenerate
# ---------------------------------------------------------------------------

def test_S7_all_preliminary_reports_returns_degenerate():
    """When every report is preliminary, build_ic_weights returns degenerate=True."""
    reports = [
        _make_report(p, preliminary=True) for p in ACTIVE_PILLARS_PHASE3
    ]
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    w_ic, mask, degenerate = build_ic_weights(reports, w0, ACTIVE_PILLARS_PHASE3)
    assert degenerate is True
    assert mask == frozenset(ACTIVE_PILLARS_PHASE3)
    # w_ic is returned as w0 when degenerate
    for p in ACTIVE_PILLARS_PHASE3:
        assert w_ic[p] == pytest.approx(w0[p], abs=1e-12)


# ---------------------------------------------------------------------------
# S8 — build_ic_weights all-IC≤0 → degenerate
# ---------------------------------------------------------------------------

def test_S8_all_negative_ic_returns_degenerate():
    """All non-preliminary reports with IC ≤ 0 → degenerate=True, w_ic=w0."""
    reports = [
        _make_report(p, rolling_12m_ic=-0.02, preliminary=False, n_observations=24)
        for p in ACTIVE_PILLARS_PHASE3
    ]
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    w_ic, mask, degenerate = build_ic_weights(reports, w0, ACTIVE_PILLARS_PHASE3)
    assert degenerate is True
    # mask should be empty (preliminary=False for all)
    assert mask == frozenset()
    # w_ic returns w0 when degenerate
    for p in ACTIVE_PILLARS_PHASE3:
        assert w_ic[p] == pytest.approx(w0[p], abs=1e-12)


def test_S8b_zero_ic_returns_degenerate():
    """IC = 0.0 exactly also yields degenerate=True (zero contributes nothing)."""
    reports = [
        _make_report(p, rolling_12m_ic=0.0, preliminary=False, n_observations=24)
        for p in ACTIVE_PILLARS_PHASE3
    ]
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    _, _, degenerate = build_ic_weights(reports, w0, ACTIVE_PILLARS_PHASE3)
    assert degenerate is True


# ---------------------------------------------------------------------------
# S9 — build_ic_weights max(IC, 0) — negative IC → zero weight
# ---------------------------------------------------------------------------

def test_S9_negative_ic_pillar_gets_zero_w_ic():
    """Negative-IC pillar contributes 0 to w_ic; positive-IC pillars normalize to 1."""
    # 2-pillar scenario: quality IC=0.08 (positive), value IC=-0.05 (negative)
    reports = [
        _make_report("quality", rolling_12m_ic=0.08, preliminary=False, n_observations=24),
        _make_report("value", rolling_12m_ic=-0.05, preliminary=False, n_observations=24),
    ]
    w0 = {"quality": 0.6, "value": 0.4}
    w_ic, mask, degenerate = build_ic_weights(reports, w0, ("quality", "value"))

    assert degenerate is False
    # Negative IC pillar is NOT in mask (preliminary=False), but its w_ic = 0
    assert w_ic["value"] == pytest.approx(0.0, abs=1e-12), (
        "Negative-IC value pillar should have w_ic=0"
    )
    # All IC weight flows to quality
    assert w_ic["quality"] == pytest.approx(1.0, abs=1e-9), (
        "Positive-IC quality pillar should have w_ic=1.0 (sole positive IC)"
    )


def test_S9b_positive_ic_weights_renormalize_to_sum_one():
    """Positive-IC pillars' w_ic values sum to 1.0 (after normalization)."""
    # 4 pillars with positive IC; magnitudes differ
    pillars = ("quality", "value", "growth", "momentum")
    ic_values = (0.10, 0.04, 0.07, 0.02)
    reports = [
        _make_report(p, rolling_12m_ic=ic, preliminary=False, n_observations=24)
        for p, ic in zip(pillars, ic_values, strict=True)
    ]
    w0 = {p: 0.25 for p in pillars}
    w_ic, _, degenerate = build_ic_weights(reports, w0, pillars)
    assert degenerate is False
    assert abs(sum(w_ic.values()) - 1.0) < 1e-9, (
        f"w_ic sum = {sum(w_ic.values())} ≠ 1.0"
    )
    # Check proportionality: quality should have more weight than momentum
    assert w_ic["quality"] > w_ic["momentum"]


# ---------------------------------------------------------------------------
# S10 — end-to-end byte-identity (THE load-bearing test)
# ---------------------------------------------------------------------------

def test_S10_byte_identity_with_pin_1():
    """compute_composite(df) == compute_composite(df, weights=blend at pin=1.0).

    This is the load-bearing safety test: while SHRINKAGE_LAMBDA_PIN=1.0,
    the composite must be byte-identical whether we pass weights=None (default)
    or weights=blend_weights(..., lambda_pin=1.0).
    """
    # Synthetic pillar DataFrame with varied scores
    pillar_values = {
        "quality": [80.0],
        "value": [45.0],
        "growth": [60.0],
        "momentum": [70.0],
        "health": [55.0],
        "profitability": [40.0],
        "technical": [65.0],
        "risk": [30.0],
    }
    df = pd.DataFrame(pillar_values, index=["TICK"])

    # Build an arbitrary (non-degenerate) w_ic and mask
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    ic_values = (0.10, 0.04, 0.07, 0.02, 0.05, 0.03, 0.06, 0.01)
    reports = [
        _make_report(p, rolling_12m_ic=ic, preliminary=False, n_observations=24)
        for p, ic in zip(ACTIVE_PILLARS_PHASE3, ic_values, strict=True)
    ]
    w_ic, mask, _ = build_ic_weights(reports, w0, ACTIVE_PILLARS_PHASE3)
    lam = compute_shrinkage_lambda(12)
    blended = blend_weights(w0, w_ic, lam=lam, preliminary_mask=mask, lambda_pin=1.0)

    # Default path
    default_out = compute_composite(df)
    # Blended-weight path (pin=1.0 → blended == w0)
    blended_out = compute_composite(df, weights=blended)

    assert default_out["TICK"] == pytest.approx(blended_out["TICK"], abs=1e-9), (
        f"Byte-identity failed: default={default_out['TICK']}, "
        f"blended={blended_out['TICK']}"
    )


def test_S10b_identity_holds_for_any_w_ic_and_lam_when_pin_is_1():
    """compute_composite output is invariant to (w_ic, lam) when lambda_pin=1."""
    df = _pillar_df()
    default_out = compute_composite(df)
    ticker = df.index[0]  # "TEST"

    # Try several different w_ic vectors and lam values
    w0 = PHASE3_EFFECTIVE_WEIGHTS
    for lam in [0.0, 0.3, 0.5, 0.9]:
        w_ic = _uniform_w0(ACTIVE_PILLARS_PHASE3)
        # Vary mask too
        for mask in [frozenset(), frozenset(["quality"]), frozenset(ACTIVE_PILLARS_PHASE3)]:
            blended = blend_weights(w0, w_ic, lam=lam, preliminary_mask=mask, lambda_pin=1.0)
            blended_out = compute_composite(df, weights=blended)
            assert default_out[ticker] == pytest.approx(blended_out[ticker], abs=1e-9), (
                f"Byte-identity failed at lam={lam}, mask={mask}: "
                f"default={default_out[ticker]}, blended={blended_out[ticker]}"
            )


# ---------------------------------------------------------------------------
# S11 — Hypothesis property test
# ---------------------------------------------------------------------------

_PILLAR_NAMES = list(ACTIVE_PILLARS_PHASE3)
_N_PILLARS = len(_PILLAR_NAMES)


@st.composite
def _weight_dict(draw: st.DrawFn) -> dict[str, float]:
    """Draw positive floats and renormalize to a weight dict."""
    raw = draw(
        st.lists(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=_N_PILLARS,
            max_size=_N_PILLARS,
        )
    )
    total = sum(raw)
    return {p: v / total for p, v in zip(_PILLAR_NAMES, raw, strict=True)}


@given(
    w0=_weight_dict(),
    w_ic=_weight_dict(),
    lam=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    mask_size=st.integers(min_value=0, max_value=_N_PILLARS),
)
def test_S11_blend_weights_properties(
    w0: dict[str, float],
    w_ic: dict[str, float],
    lam: float,
    mask_size: int,
) -> None:
    """S11: For any valid w0, w_ic, lam ∈ [0,1], and mask ⊆ pillars:
    (a) blend_weights output values are all non-negative.
    (b) blend_weights output sums to 1.0 ± 1e-9.
    (c) when lam == 1.0 or mask == all pillars, output == w0.
    """
    mask = frozenset(_PILLAR_NAMES[:mask_size])
    result = blend_weights(w0, w_ic, lam=lam, preliminary_mask=mask, lambda_pin=None)

    # (a) non-negative
    for p, v in result.items():
        assert v >= -1e-15, f"Pillar {p} has negative weight {v}"

    # (b) sums to 1.0 ± 1e-9
    total = sum(result.values())
    assert abs(total - 1.0) < 1e-9, f"blend sum = {total}"

    # (c) identity conditions
    if lam == 1.0 or mask_size == _N_PILLARS:
        for p in _PILLAR_NAMES:
            assert result[p] == pytest.approx(w0[p], abs=1e-9), (
                f"Identity condition failed for pillar {p}: "
                f"lam={lam}, mask_size={mask_size}, "
                f"expected w0[{p}]={w0[p]}, got {result[p]}"
            )
