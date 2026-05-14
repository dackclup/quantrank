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
    """Composite 75 + 0 flags but only 10% MoS → lean_bullish (not bullish)."""
    assert (
        derive_recommendation(
            composite_score=75.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=10.0,
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
    """Top quartile, 1 risk flag, MoS positive → lean_bullish."""
    assert (
        derive_recommendation(
            composite_score=65.0,
            risk_flags=["goodwill_heavy"],  # generic flag
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


def test_lean_bullish_blocked_by_two_risk_flags():
    """Two flags → over LEAN_BULLISH_MAX_RISK_FLAGS=1 → neutral."""
    assert (
        derive_recommendation(
            composite_score=65.0,
            risk_flags=["sloan_accruals_top_decile", "net_issuance_top_decile"],
            valuation_warnings=[],
            mos_pct=5.0,
        )
        == "neutral"
    )


def test_lean_bullish_blocked_by_negative_mos():
    """Composite 65 + clean but MoS −5% → drops to neutral."""
    assert (
        derive_recommendation(
            composite_score=65.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=-5.0,
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
    assert (
        derive_recommendation(
            composite_score=50.0,
            risk_flags=[],
            valuation_warnings=[],
            mos_pct=0.0,
        )
        == "neutral"
    )


def test_neutral_when_composite_in_lean_band_but_too_flagged():
    assert (
        derive_recommendation(
            composite_score=62.0,
            risk_flags=["sloan_accruals_top_decile", "net_issuance_top_decile"],
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
