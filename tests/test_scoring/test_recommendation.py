"""Tests for compute.scoring.recommendation (PR 4d).

Anchors the 4-tier decision rubric (Option B: Bullish / Lean Bullish /
Neutral / Cautious). Tests cover:

- Each tier triggered by its canonical input pattern
- Cautious overrides (distress / corruption / very low composite / -30% MoS)
- Bullish disqualifications (Sloan / NSI / Beneish / Dechow / MoS < 20%)
- Lean Bullish boundary (composite=60, MoS=0, 1 risk flag)
- Neutral default fallback
- Tolerant input shapes (None, set, list, tuple, frozenset)
"""

from __future__ import annotations

import pytest

from compute.scoring.recommendation import (
    BULLISH_COMPOSITE_MIN,
    BULLISH_MOS_MIN_PCT,
    CAUTIOUS_COMPOSITE_MAX,
    CAUTIOUS_MOS_MAX_PCT,
    LEAN_BULLISH_COMPOSITE_MIN,
    LEAN_BULLISH_MAX_RISK_FLAGS,
    LEAN_BULLISH_MOS_MIN_PCT,
    derive_recommendation,
)

# -- Bullish -----------------------------------------------------------------

def test_bullish_canonical_case():
    """Top-decile + clean + cheap → bullish."""
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=25.0,
        )
        == "bullish"
    )


def test_bullish_with_none_mos_passes():
    """Missing MoS shouldn't downgrade a clean high-composite stock."""
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=None,
        )
        == "bullish"
    )


def test_bullish_blocked_by_sloan_flag():
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=["sloan_accruals_top_decile"],
            valuation_warnings=[],
            mos_pct=25.0,
        )
        == "lean_bullish"  # falls through to LB tier
    )


def test_bullish_blocked_by_nsi_flag():
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=["net_issuance_top_decile"],
            valuation_warnings=[],
            mos_pct=25.0,
        )
        == "lean_bullish"
    )


def test_bullish_blocked_by_beneish_high():
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=[],
            valuation_warnings=["beneish_high"],
            mos_pct=25.0,
        )
        == "lean_bullish"
    )


def test_bullish_blocked_by_dechow_high():
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=[],
            valuation_warnings=["dechow_high"],
            mos_pct=25.0,
        )
        == "lean_bullish"
    )


def test_bullish_blocked_by_low_mos():
    """Composite ≥ BULLISH_MIN + 0 flags, but MoS just below
    BULLISH_MOS_MIN_PCT → falls through to lean_bullish (not bullish).
    Threshold-relative so the test survives future calibration.
    """
    assert (
        derive_recommendation(
            composite_score=BULLISH_COMPOSITE_MIN + 5.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=BULLISH_MOS_MIN_PCT - 1.0,
        )
        == "lean_bullish"
    )


def test_bullish_composite_boundary_inclusive():
    """composite == BULLISH_COMPOSITE_MIN (70) qualifies."""
    assert (
        derive_recommendation(
            composite_score=BULLISH_COMPOSITE_MIN,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=BULLISH_MOS_MIN_PCT,
        )
        == "bullish"
    )


# -- Lean Bullish ------------------------------------------------------------

def test_lean_bullish_canonical_case():
    """Top-quartile composite + a Bullish-disqualifying flag + positive
    MoS → falls through to lean_bullish. Use Sloan (which IS in the
    Bullish disqualifier set) so the test exercises the actual
    Bullish→Lean fall-through path regardless of future tuning.
    """
    assert (
        derive_recommendation(
            composite_score=LEAN_BULLISH_COMPOSITE_MIN + 5.0,
            risk_flags=["sloan_accruals_top_decile"],
            valuation_warnings=[],
            mos_pct=5.0,
        )
        == "lean_bullish"
    )


def test_lean_bullish_composite_boundary_inclusive():
    assert (
        derive_recommendation(
            composite_score=LEAN_BULLISH_COMPOSITE_MIN,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=LEAN_BULLISH_MOS_MIN_PCT,
        )
        == "lean_bullish"
    )


def test_lean_bullish_blocked_by_excess_risk_flags():
    """More than LEAN_BULLISH_MAX_RISK_FLAGS flags → neutral.
    Construct N+1 distinct flags to exceed the cap regardless of value.
    """
    excess_flags = [
        "sloan_accruals_top_decile",
        "net_issuance_top_decile",
        "goodwill_heavy",
        "stale_filing_soft",
        "extreme_graham_estimate",
    ][: LEAN_BULLISH_MAX_RISK_FLAGS + 1]
    assert (
        derive_recommendation(
            composite_score=LEAN_BULLISH_COMPOSITE_MIN + 5.0,
            risk_flags=excess_flags,
            valuation_warnings=[],
            mos_pct=5.0,
        )
        == "neutral"
    )


def test_lean_bullish_blocked_by_negative_mos():
    """MoS just below LEAN_BULLISH_MOS_MIN_PCT but above CAUTIOUS_MOS_MAX_PCT
    → neutral (Lean Bullish needs ≥ threshold; not deep enough for Sell).
    """
    assert (
        derive_recommendation(
            composite_score=LEAN_BULLISH_COMPOSITE_MIN + 5.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=LEAN_BULLISH_MOS_MIN_PCT - 1.0,
        )
        == "neutral"
    )


# -- Cautious ----------------------------------------------------------------

def test_cautious_on_data_quality_corruption():
    """data_quality_input_corruption forces cautious regardless of composite."""
    assert (
        derive_recommendation(
            composite_score=80.0,
            risk_flags=["data_quality_input_corruption"],
            valuation_warnings=[],
            mos_pct=50.0,
        )
        == "cautious"
    )


def test_cautious_on_altman_distress():
    assert (
        derive_recommendation(
            composite_score=80.0,
            risk_flags=["altman_distress"],
            valuation_warnings=[],
            mos_pct=50.0,
        )
        == "cautious"
    )


def test_cautious_on_very_low_composite():
    """composite < CAUTIOUS_COMPOSITE_MAX (35) → cautious."""
    assert (
        derive_recommendation(
            composite_score=CAUTIOUS_COMPOSITE_MAX - 0.01,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=10.0,
        )
        == "cautious"
    )


def test_cautious_on_deep_overvaluation():
    """MoS < CAUTIOUS_MOS_MAX_PCT (−30%) → cautious."""
    assert (
        derive_recommendation(
            composite_score=70.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=CAUTIOUS_MOS_MAX_PCT - 0.01,
        )
        == "cautious"
    )


# -- Neutral fallback --------------------------------------------------------

def test_neutral_default_for_middling_composite():
    """Composite just below LEAN_BULLISH_COMPOSITE_MIN + above
    CAUTIOUS_COMPOSITE_MAX → neutral (no positive tier qualifies, no
    cautious trigger).
    """
    assert (
        derive_recommendation(
            composite_score=LEAN_BULLISH_COMPOSITE_MIN - 1.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=0.0,
        )
        == "neutral"
    )


def test_neutral_when_composite_in_lean_band_but_too_flagged():
    """Composite in Lean Bullish band but with > LEAN_BULLISH_MAX_RISK_FLAGS
    distinct flags → neutral. Five flag candidates ensure we always
    exceed the cap regardless of future tuning.
    """
    excess_flags = [
        "sloan_accruals_top_decile",
        "net_issuance_top_decile",
        "goodwill_heavy",
        "stale_filing_soft",
        "extreme_graham_estimate",
    ][: LEAN_BULLISH_MAX_RISK_FLAGS + 1]
    assert (
        derive_recommendation(
            composite_score=LEAN_BULLISH_COMPOSITE_MIN + 2.0,
            risk_flags=excess_flags,
            valuation_warnings=[],
            mos_pct=0.0,
        )
        == "neutral"
    )


# -- Input tolerance ---------------------------------------------------------

@pytest.mark.parametrize(
    "rf",
    [
        None,
        [],
        (),
        set(),
        frozenset(),
    ],
)
def test_accepts_various_empty_risk_flag_shapes(rf):
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=rf,
            valuation_warnings=None,
            mos_pct=25.0,
        )
        == "bullish"
    )


def test_accepts_set_input():
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags={"data_quality_input_corruption"},
            valuation_warnings={"beneish_high"},
            mos_pct=25.0,
        )
        == "cautious"
    )
