"""Tests for the Phase 7.0 AI-pick selection + inverse-vol weighting engine.

Pure functions → fully offline (no network, no @network marker, no I/O).
"""
from __future__ import annotations

import math
from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from compute.portfolio.weights import (
    HIGH_CONVICTION_COMPOSITE_MIN,
    HIGH_CONVICTION_LOSS_CHANCE_MAX,
    HIGH_CONVICTION_RECOMMENDATIONS,
    MAX_PICKS,
    MAX_WEIGHT,
    PickCandidate,
    inverse_vol_weights,
    is_eligible,
    is_high_conviction,
    select_picks,
    trailing_return_sigma,
)


def _cand(ticker, score, sector="Tech", flags=(), adjusted=None,
          recommendation=None, mos_pct=None, loss_chance_pct=None):
    return PickCandidate(
        ticker=ticker,
        composite_score=score,
        sector=sector,
        risk_flags=tuple(flags),
        composite_score_adjusted=adjusted,
        recommendation=recommendation,
        mos_pct=mos_pct,
        loss_chance_pct=loss_chance_pct,
    )


def _hc(ticker="TST", score=72.0, flags=(), recommendation="bullish",
        mos_pct=15.0, loss_chance_pct=30.0):
    """Builder for a fully high-conviction candidate (all gates pass)."""
    return _cand(ticker, score, flags=flags, recommendation=recommendation,
                 mos_pct=mos_pct, loss_chance_pct=loss_chance_pct)


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


def test_select_picks_no_sector_cap_pure_composite():
    # No sector cap (removed 2026-06-06): the basket is the top-N by composite
    # regardless of sector. A 6-Tech cohort fills all 5 slots even though Energy
    # + Health names are present — they simply rank lower on composite.
    cands = [_cand(f"T{i}", 100 - i, sector="Tech") for i in range(6)]
    cands += [_cand("E0", 50, sector="Energy"), _cand("H0", 40, sector="Health")]
    assert select_picks(cands, 5) == ["T0", "T1", "T2", "T3", "T4"]
    # a lower count is likewise sector-blind
    assert select_picks(cands, 4) == ["T0", "T1", "T2", "T3"]


def test_select_picks_tiebreak_adjusted_then_ticker():
    # equal composite → higher composite_score_adjusted wins; then ticker asc.
    cands = [
        _cand("Z", 80, adjusted=70),
        _cand("A", 80, adjusted=70),
        _cand("M", 80, adjusted=75),
    ]
    assert select_picks(cands, 3) == ["M", "A", "Z"]


def test_select_picks_dedup_dual_class_keeps_higher_composite():
    """GOOG + GOOGL are the SAME issuer — never both picked. Keep the
    higher-composite class; fill the freed slot with the next distinct issuer."""
    cands = [
        _cand("GOOGL", 95.0),  # Alphabet Class A — higher composite
        _cand("GOOG", 94.0),   # Alphabet Class C — sibling, must be skipped
        _cand("AAA", 90.0),
        _cand("BBB", 88.0),
    ]
    # count=2 → GOOGL (kept) + AAA (next DISTINCT issuer), NOT GOOG.
    assert select_picks(cands, 2) == ["GOOGL", "AAA"]
    # GOOG never appears even at a large count — its issuer slot is GOOGL's.
    picks = select_picks(cands, 10)
    assert "GOOG" not in picks
    assert picks == ["GOOGL", "AAA", "BBB"]


def test_select_picks_dedup_canonicalizes_to_fixed_class_no_churn():
    """Even when GOOG (Class C) ranks ABOVE GOOGL this quarter, the basket shows
    the CANONICAL class (GOOGL). This stops the issuer churning GOOG<->GOOGL
    quarter-to-quarter when the two near-equal composites flip which ranks higher
    (the rotation-history spurious-turnover bug)."""
    cands = [
        _cand("GOOG", 95.0),   # Class C ranks higher THIS quarter
        _cand("GOOGL", 94.0),  # Class A — the canonical (must be the one shown)
        _cand("AAA", 90.0),
    ]
    picks = select_picks(cands, 2)
    assert "GOOG" not in picks        # canonicalized away despite ranking higher
    assert picks == ["GOOGL", "AAA"]  # stable canonical class -> no cross-quarter churn


def test_select_picks_dedup_all_three_dual_class_pairs():
    """FOX/FOXA + NWS/NWSA collapse to one issuer each (not only Alphabet)."""
    cands = [
        _cand("FOXA", 80.0), _cand("FOX", 79.0),
        _cand("NWSA", 78.0), _cand("NWS", 77.0),
    ]
    # one class per issuer, the higher-composite one kept.
    assert select_picks(cands, 10) == ["FOXA", "NWSA"]


def test_select_picks_dedup_vetoed_higher_class_keeps_clean_sibling():
    """If the higher-composite dual-class is VETOED, the clean sibling represents
    the issuer (is_eligible filters BEFORE dedup) — the issuer isn't lost. Pins
    the veto×dedup interaction for a future PR-2c veto-replay backtest."""
    cands = [
        _cand("GOOGL", 95.0, flags=["sloan_accruals_top_decile"]),  # higher but VETOED
        _cand("GOOG", 94.0),  # clean sibling — kept as Alphabet's representative
        _cand("AAA", 90.0),
    ]
    picks = select_picks(cands, 2)
    assert "GOOGL" not in picks  # vetoed out of the eligible pool
    assert picks == ["GOOG", "AAA"]


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


# --- Phase 7 PR-1: is_high_conviction + constants ----------------------------


def test_hc_constants_pinned():
    """Methodology-scientist ratified values — pin them explicitly so a future
    threshold change shows up as a deliberate, test-visible commit."""
    assert HIGH_CONVICTION_RECOMMENDATIONS == frozenset({"bullish", "lean_bullish"})
    assert HIGH_CONVICTION_COMPOSITE_MIN == 50.0
    assert HIGH_CONVICTION_LOSS_CHANCE_MAX == 45.0


def test_hc_positive_bullish():
    """Canonical positive case: bullish + MoS=15 + composite=72 + LC=30 + no veto."""
    assert is_high_conviction(_hc(recommendation="bullish")) is True


def test_hc_positive_lean_bullish():
    """lean_bullish is in the approved set — must also produce True."""
    assert is_high_conviction(_hc(recommendation="lean_bullish")) is True


def test_hc_mos_strict_greater_than_zero_boundary():
    """MoS gate is STRICT >0: exactly 0.0 fails; 0.1 passes."""
    assert is_high_conviction(_hc(mos_pct=0.0)) is False
    assert is_high_conviction(_hc(mos_pct=0.1)) is True


def test_hc_composite_floor_boundary():
    """composite_score gate: 49.9 fails; exactly 50.0 passes (>= not >)."""
    assert is_high_conviction(_hc(score=49.9)) is False
    assert is_high_conviction(_hc(score=50.0)) is True


def test_hc_loss_chance_ceiling_boundary():
    """LC gate: exactly 45.0 passes; 45.1 fails (strict >)."""
    assert is_high_conviction(_hc(loss_chance_pct=45.0)) is True
    assert is_high_conviction(_hc(loss_chance_pct=45.1)) is False


def test_hc_recommendation_gate_neutral_cautious():
    """Non-approved recommendations always fail the gate."""
    assert is_high_conviction(_hc(recommendation="neutral")) is False
    assert is_high_conviction(_hc(recommendation="cautious")) is False


def test_hc_fail_closed_recommendation_none():
    """None recommendation is FAIL-CLOSED — cannot be high-conviction."""
    assert is_high_conviction(_hc(recommendation=None)) is False


def test_hc_fail_closed_mos_none():
    """None mos_pct is FAIL-CLOSED — cannot be high-conviction."""
    assert is_high_conviction(_hc(mos_pct=None)) is False


def test_hc_fail_closed_loss_chance_none():
    """None loss_chance_pct is FAIL-CLOSED — cannot be high-conviction."""
    assert is_high_conviction(_hc(loss_chance_pct=None)) is False


def test_hc_active_veto_blocks_even_when_all_else_passes():
    """An active rank-gate veto (altman_distress) disqualifies regardless of
    recommendation, MoS, composite, and loss-chance — veto check is first."""
    vetoed = _hc(flags=("altman_distress",))
    assert is_high_conviction(vetoed) is False


# --- C1: select_picks-unchanged pin ------------------------------------------


def test_C1_select_picks_unchanged_pr1_gate_does_not_affect_selection():
    """PR-1 observability gate: is_high_conviction FAILING (recommendation='neutral')
    must NOT affect whether select_picks returns the candidate — selection still
    gates on is_eligible only. This pin makes PR-2's wiring a deliberate,
    test-visible change (the test would need to be updated when selection
    is gated on is_high_conviction)."""
    # Candidate fails is_high_conviction (neutral recommendation) but has no veto.
    non_hc_but_eligible = _cand("CLEAN", 85.0, recommendation="neutral",
                                mos_pct=None, loss_chance_pct=None)
    other = _cand("OTHER", 70.0)
    result = select_picks([non_hc_but_eligible, other], 2)
    assert "CLEAN" in result, (
        "select_picks should include non-high-conviction eligible candidates "
        "(PR-1 is observability-only; PR-2 wires the gate into selection)"
    )


# --- Phase 7 PR-1: _pit_filing_lag -------------------------------------------


def _row(form_type: str, filing_date: str) -> dict:
    return {"form_type": form_type, "filing_date": filing_date, "metric": "revenue",
            "value": 100.0, "fiscal_year": None}


def test_pit_filing_lag_latest_10k_only():
    """Latest 10-K on/before as_of determines the lag."""
    from scripts.backfill_portfolio_pit import _pit_filing_lag
    rows = [
        _row("10-K", "2024-02-15"),
        _row("10-K", "2023-02-20"),   # older — should not win
        _row("10-Q", "2024-05-01"),   # quarterly — excluded
    ]
    as_of = "2025-01-01"
    result = _pit_filing_lag(rows, as_of, date(2025, 1, 1))
    # 2025-01-01 − 2024-02-15 = 320 days
    assert result == (date(2025, 1, 1) - date(2024, 2, 15)).days


def test_pit_filing_lag_future_dated_excluded():
    """A 10-K filed AFTER as_of must not count — future filings violate PIT."""
    from scripts.backfill_portfolio_pit import _pit_filing_lag
    rows = [
        _row("10-K", "2025-03-01"),   # future relative to as_of 2025-01-01
        _row("10-K", "2024-02-15"),   # eligible
    ]
    as_of = "2025-01-01"
    result = _pit_filing_lag(rows, as_of, date(2025, 1, 1))
    assert result == (date(2025, 1, 1) - date(2024, 2, 15)).days


def test_pit_filing_lag_10q_excluded():
    """10-Q rows must never contribute to the annual staleness lag."""
    from scripts.backfill_portfolio_pit import _pit_filing_lag
    rows = [
        _row("10-Q", "2024-11-01"),
        _row("10-Q", "2024-08-01"),
    ]
    result = _pit_filing_lag(rows, "2025-01-01", date(2025, 1, 1))
    assert result is None


def test_pit_filing_lag_empty_rows_returns_none():
    """No rows at all → None (ensemble treats as 'unknown', not hard-stale)."""
    from scripts.backfill_portfolio_pit import _pit_filing_lag
    assert _pit_filing_lag([], "2025-01-01", date(2025, 1, 1)) is None
