"""Tests for compute.scoring.loss_chance (PR 4e).

Threshold-relative — uses the module's exposed constants so future
re-calibration doesn't silently break tests. Same pattern PR 4d
adopted after its first iteration broke 5 tests on calibration change.

Coverage:
- 5-band gradient triggered by canonical inputs
- MoS=None returns None (dominant signal missing)
- Composite=None falls back gracefully
- Clipping floor (MIN_PCT) + ceiling (MAX_PCT)
- Flag penalties stack additively
- Tolerant input shapes (None, set, list, tuple, frozenset)
"""

from __future__ import annotations

import pytest

from compute.scoring.loss_chance import (
    ALTMAN_PENALTY,
    BASELINE_PCT,
    DATA_QUALITY_PENALTY,
    MAX_PCT,
    MIN_PCT,
    MOS_NEG_CAP,
    MOS_POS_CAP,
    MOS_SCALE,
    derive_loss_chance,
)

# -- Missing inputs ----------------------------------------------------------

def test_returns_none_when_mos_missing():
    """MoS is the dominant signal — without it we don't fake a probability."""
    assert (
        derive_loss_chance(
            composite_score=70.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=None,
        )
        is None
    )


def test_composite_none_does_not_break():
    """Composite=None should skip the composite contribution but still
    return a value (MoS alone suffices)."""
    result = derive_loss_chance(
        composite_score=None,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=0.0,
    )
    assert result is not None
    assert MIN_PCT <= result <= MAX_PCT


# -- Band gradient -----------------------------------------------------------

def test_deep_undervalue_clean_lands_in_low_band():
    """Composite 80 + clean + MoS +50% should land in the <25 band."""
    result = derive_loss_chance(
        composite_score=80.0,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=50.0,
    )
    assert result is not None
    assert result < 25.0


def test_neutral_inputs_land_near_baseline():
    """Composite 50 + clean + MoS 0% sits at baseline (no shifts)."""
    result = derive_loss_chance(
        composite_score=50.0,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=0.0,
    )
    assert result == BASELINE_PCT


def test_deep_overvalue_with_flags_lands_in_high_band():
    """Composite 30 + altman_distress + MoS −80% lands in the >80 band."""
    result = derive_loss_chance(
        composite_score=30.0,
        risk_flags=["altman_distress"],
        valuation_warnings=[],
        mos_pct=-80.0,
    )
    assert result is not None
    assert result > 80.0


# -- Clipping ----------------------------------------------------------------

def test_clips_to_floor_on_extreme_undervalue():
    """Extreme positive MoS + top composite + no flags doesn't go below MIN_PCT."""
    result = derive_loss_chance(
        composite_score=100.0,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=500.0,  # absurd MoS — should saturate via MOS_NEG_CAP
    )
    assert result == MIN_PCT


def test_clips_to_ceiling_on_extreme_overvalue_with_all_flags():
    """Deep negative MoS + every flag stacked → ceiling at MAX_PCT."""
    result = derive_loss_chance(
        composite_score=0.0,
        risk_flags=[
            "data_quality_input_corruption",
            "altman_distress",
            "going_concern_disclosure",
            "sloan_accruals_top_decile",
            "net_issuance_top_decile",
        ],
        valuation_warnings=[
            "beneish_high",
            "dechow_high",
            "value_trap_risk",
            "goodwill_heavy",
            "stale_filing_soft",
            "extreme_graham_estimate",
            "extreme_rim_estimate",
            "extreme_dcf_estimate",
            "extreme_multiples_pe_estimate",
            "extreme_multiples_pb_estimate",
        ],
        mos_pct=-500.0,
    )
    assert result == MAX_PCT


# -- MoS scaling -------------------------------------------------------------

def test_positive_mos_pushes_lc_down():
    """Positive MoS (undervalued) reduces loss chance vs baseline."""
    neutral = derive_loss_chance(
        composite_score=50.0, risk_flags=[], valuation_warnings=[], mos_pct=0.0
    )
    undervalued = derive_loss_chance(
        composite_score=50.0, risk_flags=[], valuation_warnings=[], mos_pct=30.0
    )
    assert undervalued < neutral


def test_negative_mos_pushes_lc_up():
    """Negative MoS (overvalued) raises loss chance vs baseline."""
    neutral = derive_loss_chance(
        composite_score=50.0, risk_flags=[], valuation_warnings=[], mos_pct=0.0
    )
    overvalued = derive_loss_chance(
        composite_score=50.0, risk_flags=[], valuation_warnings=[], mos_pct=-30.0
    )
    assert overvalued > neutral


def test_mos_asymmetric_caps():
    """Positive MoS can push down up to MOS_NEG_CAP; negative MoS can push
    up to MOS_POS_CAP. Verify both via threshold-relative math."""
    # Positive MoS large enough to saturate: contribution = +MOS_NEG_CAP
    # pushed onto baseline = BASELINE_PCT - MOS_NEG_CAP.
    pos_saturated = derive_loss_chance(
        composite_score=50.0,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=MOS_NEG_CAP / MOS_SCALE + 100.0,  # well past saturation
    )
    assert pos_saturated == max(MIN_PCT, BASELINE_PCT - MOS_NEG_CAP)

    # Negative MoS large enough to saturate the positive cap.
    neg_saturated = derive_loss_chance(
        composite_score=50.0,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=-(MOS_POS_CAP / MOS_SCALE + 100.0),
    )
    assert neg_saturated == min(MAX_PCT, BASELINE_PCT + MOS_POS_CAP)


# -- Flag penalty additivity -------------------------------------------------

def test_data_quality_flag_adds_dq_penalty():
    """Cleanly isolating one flag — penalty is exactly DATA_QUALITY_PENALTY."""
    clean = derive_loss_chance(
        composite_score=50.0, risk_flags=[], valuation_warnings=[], mos_pct=0.0
    )
    flagged = derive_loss_chance(
        composite_score=50.0,
        risk_flags=["data_quality_input_corruption"],
        valuation_warnings=[],
        mos_pct=0.0,
    )
    assert flagged == min(MAX_PCT, clean + DATA_QUALITY_PENALTY)


def test_altman_flag_adds_altman_penalty():
    clean = derive_loss_chance(
        composite_score=50.0, risk_flags=[], valuation_warnings=[], mos_pct=0.0
    )
    flagged = derive_loss_chance(
        composite_score=50.0,
        risk_flags=["altman_distress"],
        valuation_warnings=[],
        mos_pct=0.0,
    )
    assert flagged == min(MAX_PCT, clean + ALTMAN_PENALTY)


def test_extreme_estimates_capped():
    """5 extreme_*_estimate flags hit the EXTREME_ESTIMATE_CAP — adding a
    6th doesn't increase loss chance further."""
    five = derive_loss_chance(
        composite_score=50.0,
        risk_flags=[],
        valuation_warnings=[
            "extreme_graham_estimate",
            "extreme_rim_estimate",
            "extreme_dcf_estimate",
            "extreme_multiples_pe_estimate",
            "extreme_multiples_pb_estimate",
        ],
        mos_pct=0.0,
    )
    six = derive_loss_chance(
        composite_score=50.0,
        risk_flags=[],
        valuation_warnings=[
            "extreme_graham_estimate",
            "extreme_rim_estimate",
            "extreme_dcf_estimate",
            "extreme_multiples_pe_estimate",
            "extreme_multiples_pb_estimate",
            "extreme_multiples_ev_ebitda_estimate",
        ],
        mos_pct=0.0,
    )
    assert five == six


# -- Tier-aligned expectations -----------------------------------------------

def test_bullish_profile_lands_in_low_band():
    """A canonical Bullish stock (top composite + no flags + +20% MoS)
    should produce a Loss Chance in the lower half of the gradient."""
    result = derive_loss_chance(
        composite_score=72.0,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=20.0,
    )
    assert result is not None
    assert result < 40.0  # in <25 or 25-40 band


def test_cautious_profile_lands_in_high_band():
    """A canonical Cautious stock (low composite + Altman + −50% MoS)
    should produce a Loss Chance well above the midpoint."""
    result = derive_loss_chance(
        composite_score=40.0,
        risk_flags=["altman_distress"],
        valuation_warnings=[],
        mos_pct=-50.0,
    )
    assert result is not None
    assert result > 60.0


# -- Input shape tolerance ---------------------------------------------------

@pytest.mark.parametrize(
    "rf",
    [None, [], (), set(), frozenset()],
)
def test_accepts_various_empty_risk_flag_shapes(rf):
    """None / list / tuple / set / frozenset all treated as 'no flags'."""
    result = derive_loss_chance(
        composite_score=50.0,
        risk_flags=rf,
        valuation_warnings=None,
        mos_pct=0.0,
    )
    assert result == BASELINE_PCT


def test_accepts_set_inputs_for_risk_and_warnings():
    """The Set form should produce the same result as the List form."""
    list_form = derive_loss_chance(
        composite_score=50.0,
        risk_flags=["altman_distress"],
        valuation_warnings=["beneish_high"],
        mos_pct=0.0,
    )
    set_form = derive_loss_chance(
        composite_score=50.0,
        risk_flags={"altman_distress"},
        valuation_warnings={"beneish_high"},
        mos_pct=0.0,
    )
    assert list_form == set_form
