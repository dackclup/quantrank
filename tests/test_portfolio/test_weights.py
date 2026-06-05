"""Tests for the Phase 7.0 AI-pick selection + inverse-vol weighting engine.

Pure functions → fully offline (no network, no @network marker, no I/O).
"""
from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from compute.portfolio.weights import (
    MAX_PICKS,
    MAX_WEIGHT,
    PickCandidate,
    inverse_vol_weights,
    is_eligible,
    select_picks,
    trailing_return_sigma,
)


def _cand(ticker, score, sector="Tech", flags=(), adjusted=None):
    return PickCandidate(
        ticker=ticker,
        composite_score=score,
        sector=sector,
        risk_flags=tuple(flags),
        composite_score_adjusted=adjusted,
    )


# --- is_eligible -------------------------------------------------------------


def test_is_eligible_clean():
    assert is_eligible([]) is True
    assert is_eligible(["going_concern_disclosure"]) is True  # annotate-only → eligible


def test_is_eligible_vetoed():
    assert is_eligible(["altman_distress"]) is False
    assert is_eligible(["foo", "beneish_manipulation_veto"]) is False


# --- select_picks ------------------------------------------------------------


def test_select_picks_orders_by_composite_desc():
    cands = [_cand("A", 50), _cand("B", 90), _cand("C", 70)]
    assert select_picks(cands, 3) == ["B", "C", "A"]


def test_select_picks_excludes_active_vetoes():
    cands = [
        _cand("VETO", 99, flags=["sloan_accruals_top_decile"]),
        _cand("OK1", 80),
        _cand("OK2", 70),
    ]
    assert select_picks(cands, 2) == ["OK1", "OK2"]
    assert "VETO" not in select_picks(cands, 10)


def test_select_picks_count_clamped():
    cands = [_cand(f"T{i}", 100 - i) for i in range(20)]
    assert len(select_picks(cands, 0)) == 1  # clamp up to MIN_PICKS
    assert len(select_picks(cands, 99)) == MAX_PICKS  # clamp down to MAX_PICKS


def test_select_picks_sector_cap_binds_at_count_5():
    # 6 Tech names; with the 2-per-sector cap at count>=5 only 2 Tech survive,
    # then the cap leaves us short (no other sectors) → backfill honors COUNT.
    cands = [_cand(f"T{i}", 100 - i, sector="Tech") for i in range(6)]
    cands += [_cand("E0", 50, sector="Energy"), _cand("H0", 40, sector="Health")]
    picks = select_picks(cands, 5)
    assert len(picks) == 5
    # top-2 Tech (T0, T1) kept; T2.. capped out in favor of other sectors first
    assert picks[:2] == ["T0", "T1"]
    assert "E0" in picks and "H0" in picks


def test_select_picks_no_sector_cap_below_count_5():
    # count=4 (< MIN_COUNT_FOR_SECTOR_CAP) → all-Tech basket allowed.
    cands = [_cand(f"T{i}", 100 - i, sector="Tech") for i in range(6)]
    assert select_picks(cands, 4) == ["T0", "T1", "T2", "T3"]


def test_select_picks_tiebreak_adjusted_then_ticker():
    # equal composite → higher composite_score_adjusted wins; then ticker asc.
    cands = [
        _cand("Z", 80, adjusted=70),
        _cand("A", 80, adjusted=70),
        _cand("M", 80, adjusted=75),
    ]
    assert select_picks(cands, 3) == ["M", "A", "Z"]


# --- inverse_vol_weights -----------------------------------------------------


def test_inverse_vol_weights_sum_to_one():
    w = inverse_vol_weights({"A": 0.2, "B": 0.1, "C": 0.4})
    assert math.isclose(sum(w.values()), 1.0, abs_tol=1e-9)


def test_inverse_vol_lower_sigma_gets_more_weight():
    # 4 names with a modest spread so the cap doesn't bind → pure inverse-vol
    # ordering. (At N=2 the 35% cap is infeasible and degrades to equal weight,
    # which is intended — see test_inverse_vol_infeasible_cap_degrades_to_equal.)
    w = inverse_vol_weights({"LOW": 0.20, "B": 0.25, "C": 0.30, "HIGH": 0.35})
    assert w["LOW"] > w["B"] > w["C"] > w["HIGH"]


def test_inverse_vol_respects_cap():
    # One ultra-low-vol name would dominate; the cap pins it at MAX_WEIGHT.
    w = inverse_vol_weights({"DOM": 0.001, "B": 0.3, "C": 0.3, "D": 0.3})
    assert w["DOM"] <= MAX_WEIGHT + 1e-9
    assert math.isclose(sum(w.values()), 1.0, abs_tol=1e-9)


def test_inverse_vol_infeasible_cap_degrades_to_equal():
    # N=2, cap 0.35 → N*cap=0.7 < 1 infeasible → equal weight 0.5/0.5.
    w = inverse_vol_weights({"A": 0.1, "B": 0.4})
    assert math.isclose(w["A"], 0.5) and math.isclose(w["B"], 0.5)


def test_inverse_vol_drops_bad_sigma():
    w = inverse_vol_weights({"A": 0.2, "BAD": 0.0, "NEG": -0.1, "NAN": float("nan")})
    assert set(w) == {"A"}
    assert math.isclose(w["A"], 1.0)


def test_inverse_vol_empty():
    assert inverse_vol_weights({}) == {}
    assert inverse_vol_weights({"A": 0.0}) == {}


@given(
    st.dictionaries(
        st.text(min_size=1, max_size=4),
        st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    )
)
def test_inverse_vol_property_sum_one_and_capped(sigmas):
    w = inverse_vol_weights(sigmas)
    assert math.isclose(sum(w.values()), 1.0, abs_tol=1e-9)
    # cap holds whenever it is feasible (N*cap >= 1)
    if len(w) * MAX_WEIGHT >= 1.0:
        assert all(v <= MAX_WEIGHT + 1e-9 for v in w.values())
    assert all(v > 0 for v in w.values())


# --- trailing_return_sigma ---------------------------------------------------


def test_trailing_return_sigma_known_series():
    sig = trailing_return_sigma([100.0, 110.0, 99.0, 108.9])
    assert sig is not None and sig > 0


def test_trailing_return_sigma_too_short():
    assert trailing_return_sigma([100.0]) is None
    assert trailing_return_sigma([100.0, 101.0]) is None  # only 1 return


def test_trailing_return_sigma_drops_nulls():
    # nulls / non-positive prices removed before the return calc
    sig = trailing_return_sigma([100.0, None, 110.0, 0.0, 105.0, 107.0])
    assert sig is not None


def test_trailing_return_sigma_zero_variance():
    # flat series → zero stdev (defined, not None)
    assert trailing_return_sigma([100.0, 100.0, 100.0, 100.0]) == 0.0
