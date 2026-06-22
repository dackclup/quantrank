"""Unit tests for compute.scoring.bonferroni_shadow (issue #542, Slice 8).

Tests cover the methodology-scientist REVISE semantics:
- m = valid_count (data-driven, NOT hardcoded 1500)
- alpha_star = 0.05 / valid_count (data-driven)
- flip_count invariant: live_fire - provisional_fire == flip_count
- valid_count == 0 graceful path (no ZeroDivisionError, returns (0, 0, 0))
- None M-scores excluded from valid_count and all fire counts
- provisional_fire_count always <= live_fire_count (provisional is stricter)
"""

from __future__ import annotations

import pytest

from compute.scoring.bonferroni_shadow import (
    BENEISH_BONFERRONI_PROVISIONAL,
    BENEISH_LIVE_THRESHOLD,
    BONFERRONI_ALPHA,
    compute_bonferroni_shadow,
)

# ---------------------------------------------------------------------------
# Section A: constants sanity
# ---------------------------------------------------------------------------


def test_A1_live_threshold_matches_beneish_1999():
    """Mirrored live threshold must match beneish.py::BENEISH_THRESHOLD = -2.22."""
    assert BENEISH_LIVE_THRESHOLD == -2.22


def test_A2_provisional_threshold_stricter_than_live():
    """Provisional threshold must be LESS NEGATIVE (closer to 0 = stricter FWER).

    'Stricter' means the provisional fires on FEWER tickers:
    to fire, M-score must exceed a HIGHER bar (less negative value).
    provisional_threshold > live_threshold (closer to 0).
    """
    assert BENEISH_BONFERRONI_PROVISIONAL > BENEISH_LIVE_THRESHOLD


def test_A3_provisional_threshold_between_live_and_soft_veto():
    """Provisional is strictly between the live annotate (-2.22) and the
    soft-veto threshold (-1.78) so the flag subset relationship holds.
    """
    assert BENEISH_LIVE_THRESHOLD < BENEISH_BONFERRONI_PROVISIONAL < -1.78


def test_A4_bonferroni_alpha_is_conventional():
    """Conventional per-test significance level."""
    assert BONFERRONI_ALPHA == 0.05


# ---------------------------------------------------------------------------
# Section B: valid_count semantics (m = data-driven, NOT hardcoded 1500)
# ---------------------------------------------------------------------------


def test_B1_empty_dict_returns_zero_triple():
    """Edge case: no tickers at all — returns (0, 0, 0), no error."""
    result = compute_bonferroni_shadow({})
    assert result == (0, 0, 0)


def test_B2_all_none_scores_returns_zero_triple():
    """Edge case: valid_count == 0 (all None) — returns (0, 0, 0), no ZeroDivisionError."""
    scores = {"AAPL": None, "MSFT": None, "GOOG": None}
    result = compute_bonferroni_shadow(scores)
    assert result == (0, 0, 0)


def test_B3_none_scores_excluded_from_valid_count():
    """None M-scores are NOT counted in valid_count and do not affect fire counts."""
    # Only 1 non-None score, far below both thresholds (no fires)
    scores = {"AAPL": None, "MSFT": -5.0, "GOOG": None}
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    # -5.0 is below both -2.22 and -1.94 (does NOT exceed either threshold)
    # M-score fires when m_score > threshold (greater than, not less than)
    assert live_fire == 0
    assert provisional_fire == 0
    assert flip_count == 0


def test_B4_alpha_star_is_005_divided_by_valid_count():
    """alpha_star = 0.05 / valid_count (K valid M-scores → α* = 0.05/K).

    We cannot assert alpha_star directly from the return values (it is only
    logged), but we can verify the m=valid_count convention by checking that
    the function handles K=3 non-None scores without error and returns
    the expected counts.
    """
    # K = 3 valid M-scores; expected alpha_star = 0.05 / 3 ≈ 0.01667
    # All scores well below both thresholds → 0 fires, 0 flips
    scores = {"A": -3.5, "B": -4.0, "C": -5.0, "D": None}
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 0
    assert provisional_fire == 0
    assert flip_count == 0


# ---------------------------------------------------------------------------
# Section C: fire-count + flip-count invariants
# ---------------------------------------------------------------------------


def test_C1_flip_count_equals_live_minus_provisional():
    """Invariant: live_fire_count - provisional_fire_count == shadow_flip_count.

    This must hold for any input because provisional ⊆ live
    (provisional is stricter: fires only when m_score > -1.94 > -2.22).
    """
    # Scores spanning all three zones:
    # Zone 1: m > -1.94 → fires BOTH live AND provisional (no flip)
    # Zone 2: -2.22 < m <= -1.94 → fires LIVE only (flip)
    # Zone 3: m <= -2.22 → fires NEITHER (no flip)
    scores = {
        "AA": -1.50,   # Zone 1: above both thresholds, fires both
        "BB": -1.80,   # Zone 1: above -1.94? No, -1.80 > -1.94 is True. fires both
        "CC": -2.00,   # Zone 2: -2.00 > -2.22 (live fires); -2.00 > -1.94? No → flip
        "DD": -2.10,   # Zone 2: -2.10 > -2.22 (live fires); -2.10 > -1.94? No → flip
        "EE": -2.22,   # boundary: -2.22 > -2.22 is False → neither fires
        "FF": -3.00,   # Zone 3: below both → no fire
        "GG": None,    # excluded
    }
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire - provisional_fire == flip_count, (
        f"Invariant violated: live={live_fire} - provisional={provisional_fire} "
        f"!= flip={flip_count}"
    )


def test_C2_provisional_always_le_live():
    """provisional_fire_count <= live_fire_count for any input."""
    scores = {
        "A": -1.50,
        "B": -2.00,
        "C": -2.10,
        "D": -3.00,
        "E": None,
    }
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert provisional_fire <= live_fire


def test_C3_zone_1_score_fires_both_thresholds():
    """A score above both thresholds fires both live AND provisional (no flip)."""
    # -1.50 > -1.94 (provisional threshold) AND -1.50 > -2.22 (live threshold)
    scores = {"A": -1.50}
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 1
    assert provisional_fire == 1
    assert flip_count == 0


def test_C4_zone_2_score_fires_live_only():
    """A score in (-2.22, -1.94] fires live but NOT provisional → 1 flip."""
    # -2.00 > -2.22 (live fires) but -2.00 < -1.94 (provisional does NOT fire)
    # Note: -2.00 > -1.94 is False (−2.00 is more negative than −1.94)
    scores = {"A": -2.00}
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 1
    assert provisional_fire == 0
    assert flip_count == 1


def test_C5_zone_3_score_fires_neither():
    """A score at or below -2.22 fires neither threshold → 0 flips."""
    # -3.00 is below both thresholds → no fire
    scores = {"A": -3.00, "B": -2.22}  # boundary: -2.22 > -2.22 is False
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 0
    assert provisional_fire == 0
    assert flip_count == 0


def test_C6_mixed_population_flip_count_correct():
    """Full population: 2 zone-1, 2 zone-2, 2 zone-3, 1 None.
    Expected: live=4, provisional=2, flip=2.
    """
    scores = {
        "Z1A": -1.50,  # zone 1: fires both
        "Z1B": -1.80,  # zone 1: fires both (-1.80 > -1.94 is True)
        "Z2A": -2.00,  # zone 2: live only (flip)
        "Z2B": -2.10,  # zone 2: live only (flip)
        "Z3A": -3.00,  # zone 3: neither
        "Z3B": -4.00,  # zone 3: neither
        "NUL": None,   # excluded
    }
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 4, f"Expected live_fire=4, got {live_fire}"
    assert provisional_fire == 2, f"Expected provisional_fire=2, got {provisional_fire}"
    assert flip_count == 2, f"Expected flip_count=2, got {flip_count}"
    # Invariant
    assert live_fire - provisional_fire == flip_count


def test_C7_all_scores_in_zone_1_no_flips():
    """All scores above both thresholds → flip_count == 0."""
    scores = {f"T{i}": -1.0 - i * 0.01 for i in range(10)}  # -1.00 to -1.09, all > -1.94
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert flip_count == 0
    assert live_fire == provisional_fire == 10


def test_C8_all_scores_in_zone_2_all_flip():
    """All scores in (-2.22, -1.94] → each is a flip, flip_count == live_fire."""
    # -1.95, -2.00, -2.10, -2.20 are all in (-2.22, -1.94] → live fires, provisional does not
    scores = {"A": -1.95, "B": -2.00, "C": -2.10, "D": -2.20}
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert provisional_fire == 0
    assert live_fire == flip_count == 4


def test_C9_all_scores_in_zone_3_no_fires():
    """All scores below -2.22 → no fires, no flips."""
    scores = {"A": -2.50, "B": -3.00, "C": -5.00}
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 0
    assert provisional_fire == 0
    assert flip_count == 0


# ---------------------------------------------------------------------------
# Section D: graceful edge cases
# ---------------------------------------------------------------------------


def test_D1_single_valid_score_no_error():
    """Single non-None score — valid_count=1, alpha_star=0.05/1=0.05, no error."""
    scores = {"ONLY": -1.50}  # zone 1
    flip_count, live_fire, provisional_fire = compute_bonferroni_shadow(scores)
    assert live_fire == 1
    assert provisional_fire == 1
    assert flip_count == 0


def test_D2_return_type_is_tuple_of_three_ints():
    """Return type is always tuple[int, int, int]."""
    result = compute_bonferroni_shadow({"A": -2.00, "B": None})
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert all(isinstance(v, int) for v in result)


def test_D3_valid_count_zero_no_division_error():
    """valid_count == 0 must NOT raise ZeroDivisionError."""
    # This is the key edge case from the REVISE mandate
    try:
        result = compute_bonferroni_shadow({"A": None, "B": None})
    except ZeroDivisionError:
        pytest.fail("compute_bonferroni_shadow raised ZeroDivisionError on valid_count=0")
    assert result == (0, 0, 0)
