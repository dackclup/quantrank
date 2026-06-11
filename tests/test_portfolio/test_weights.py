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


# --- C1: default gate is veto_only (reconciled for PR-2) ----------------------


def test_C1_default_gate_is_veto_only_hc_fields_do_not_filter():
    """PR-2 reconcile: the DEFAULT gate ('veto_only') does NOT apply the
    high-conviction filter.  A candidate with recommendation='neutral' (fails
    is_high_conviction) but no active veto MUST appear in the result when
    called with the default gate — whether the caller passes gate='veto_only'
    explicitly or relies on the default.  Pins that the default is unchanged
    by PR-2's addition of gate='high_conviction'."""
    # Fails is_high_conviction (neutral recommendation) but has no active veto.
    non_hc_but_eligible = _cand("CLEAN", 85.0, recommendation="neutral",
                                mos_pct=None, loss_chance_pct=None)
    other = _cand("OTHER", 70.0)

    # Both the bare call (default) and the explicit veto_only must be identical
    # and must include the non-HC candidate.
    result_default = select_picks([non_hc_but_eligible, other], 2)
    result_explicit = select_picks([non_hc_but_eligible, other], 2, gate="veto_only")
    assert result_default == result_explicit, (
        "select_picks() and select_picks(gate='veto_only') must be identical"
    )
    assert "CLEAN" in result_default, (
        "default gate should include non-high-conviction eligible candidates "
        "(veto_only does not apply is_high_conviction)"
    )


# --- Phase 7 PR-2: gate='high_conviction' tests --------------------------------


def test_hc_gate_filters_out_non_bullish_and_overvalued():
    """gate='high_conviction' excludes neutral + overvalued candidates even
    when they rank higher by composite than the gate-passing names.

    Fixture:
      HI1  bullish    MoS=15  comp=90  LC=30  → passes gate
      HOLD neutral    MoS=20  comp=95  LC=25  → fails (recommendation)
      OVER bullish    MoS=-2  comp=85  LC=20  → fails (MoS≤0)
      HI2  lean_b.   MoS=5   comp=80  LC=40  → passes gate
      HI3  bullish   MoS=20  comp=70  LC=20  → passes gate

    With count=10 only [HI1, HI2, HI3] appear; HOLD and OVER are absent.
    """
    cands = [
        _cand("HI1",  90.0, recommendation="bullish",      mos_pct=15.0, loss_chance_pct=30.0),
        _cand("HOLD", 95.0, recommendation="neutral",      mos_pct=20.0, loss_chance_pct=25.0),
        _cand("OVER", 85.0, recommendation="bullish",      mos_pct=-2.0, loss_chance_pct=20.0),
        _cand("HI2",  80.0, recommendation="lean_bullish", mos_pct=5.0,  loss_chance_pct=40.0),
        _cand("HI3",  70.0, recommendation="bullish",      mos_pct=20.0, loss_chance_pct=20.0),
    ]
    result = select_picks(cands, 10, gate="high_conviction")
    assert result == ["HI1", "HI2", "HI3"]
    assert "HOLD" not in result
    assert "OVER" not in result


def test_hc_gate_orders_by_composite_desc_among_eligible():
    """gate='high_conviction' still sorts eligible names by composite desc."""
    cands = [
        _cand("LOW",  55.0, recommendation="bullish",      mos_pct=10.0, loss_chance_pct=30.0),
        _cand("MID",  70.0, recommendation="lean_bullish", mos_pct=8.0,  loss_chance_pct=35.0),
        _cand("HIGH", 88.0, recommendation="bullish",      mos_pct=25.0, loss_chance_pct=20.0),
    ]
    result = select_picks(cands, 3, gate="high_conviction")
    assert result == ["HIGH", "MID", "LOW"]


def test_hc_gate_top_n_respected():
    """gate='high_conviction' returns at most count eligible candidates."""
    cands = [
        _cand(f"HC{i}", float(90 - i), recommendation="bullish",
              mos_pct=10.0, loss_chance_pct=20.0)
        for i in range(8)
    ]
    result = select_picks(cands, 3, gate="high_conviction")
    assert len(result) == 3
    assert result == ["HC0", "HC1", "HC2"]


def test_hc_gate_empty_when_no_candidate_passes():
    """When NO candidate clears the gate (all neutral / all overvalued), the
    result is an empty list — the selection correctly shrinks to zero eligible
    rather than falling back to veto_only behavior."""
    cands = [
        _cand("N1", 90.0, recommendation="neutral",  mos_pct=10.0, loss_chance_pct=20.0),
        _cand("N2", 80.0, recommendation="cautious", mos_pct=5.0,  loss_chance_pct=15.0),
        _cand("N3", 75.0, recommendation="bullish",  mos_pct=-5.0, loss_chance_pct=30.0),  # MoS≤0
    ]
    result = select_picks(cands, 5, gate="high_conviction")
    assert result == []


def test_hc_gate_dual_class_both_passing_canonicalizes():
    """GOOG + GOOGL both clear the high-conviction gate → canonicalized to GOOGL
    (one issuer slot, stable class), same as veto_only.  The gate×canonicalize
    interaction must not double-count or omit the issuer."""
    cands = [
        _cand("GOOG",  92.0, recommendation="bullish", mos_pct=12.0, loss_chance_pct=25.0),
        _cand("GOOGL", 91.0, recommendation="bullish", mos_pct=10.0, loss_chance_pct=28.0),
        _cand("AAA",   80.0, recommendation="lean_bullish", mos_pct=8.0, loss_chance_pct=30.0),
    ]
    result = select_picks(cands, 3, gate="high_conviction")
    assert "GOOG" not in result          # canonicalized away
    assert "GOOGL" in result             # canonical class present
    assert "AAA" in result               # next distinct issuer fills the freed slot
    assert len(result) == 2             # only 2 distinct issuers exist


def test_hc_gate_dual_class_canonical_ineligible_fallback_to_sibling():
    """If GOOGL does NOT pass the gate (MoS≤0) but GOOG does, the issuer is
    represented by GOOG — the select_picks fallback path applies under the gate
    the same way it applies for veto_only (the 'if key in eligible_tickers'
    fallback in select_picks emits c.ticker instead of key)."""
    cands = [
        _cand("GOOG",  90.0, recommendation="bullish",  mos_pct=15.0, loss_chance_pct=20.0),
        _cand("GOOGL", 88.0, recommendation="bullish",  mos_pct=-3.0, loss_chance_pct=20.0),  # MoS≤0
        _cand("AAA",   75.0, recommendation="lean_bullish", mos_pct=5.0, loss_chance_pct=30.0),
    ]
    result = select_picks(cands, 3, gate="high_conviction")
    assert "GOOGL" not in result         # MoS≤0 → not gate-eligible
    assert "GOOG" in result              # sibling fallback for the Alphabet slot
    assert "AAA" in result


@given(
    st.lists(
        st.fixed_dictionaries({
            "ticker": st.text(min_size=1, max_size=6).filter(
                lambda t: t not in {"GOOG", "GOOGL", "FOX", "FOXA", "NWS", "NWSA"}
            ),
            "composite_score": st.floats(min_value=0.0, max_value=100.0,
                                          allow_nan=False, allow_infinity=False),
            "recommendation": st.sampled_from(
                ["bullish", "lean_bullish", "neutral", "cautious", None]
            ),
            "mos_pct": st.one_of(st.none(),
                                 st.floats(min_value=-50.0, max_value=100.0,
                                           allow_nan=False, allow_infinity=False)),
            "loss_chance_pct": st.one_of(st.none(),
                                         st.floats(min_value=0.0, max_value=100.0,
                                                   allow_nan=False, allow_infinity=False)),
            "flags": st.lists(st.sampled_from([
                "altman_distress", "beneish_manipulation_veto",
                "going_concern_disclosure", "sloan_accruals_top_decile",
            ]), max_size=2),
        }),
        min_size=0,
        max_size=15,
    ),
    st.integers(min_value=1, max_value=20),
)
def test_hc_gate_subset_of_veto_only_property(raw_cands, count):
    """Property: every ticker returned by gate='high_conviction' is veto-eligible.

    HC is a strictly tighter gate than veto_only: it adds recommendation,
    MoS, composite, and loss-chance filters ON TOP OF the 7-veto eligibility
    check.  The invariant is therefore a GATE-LEVEL one — not a top-N
    selection one.

    With count=N the veto_only top-N can be occupied entirely by veto-eligible
    but HC-ineligible names (e.g. neutral recommendations).  In that case
    hc_picks and veto_only_picks are DISJOINT even though every hc pick IS
    veto-eligible.  Asserting hc_picks ⊆ veto_only_top_N was wrong.

    Correct invariants for any candidate list:
      set(hc_picks) ⊆ {c.ticker for c in candidates if is_eligible(c.risk_flags)}
      len(hc_picks) ≤ count
      len(hc_picks) ≤ |veto-eligible candidates|
    """
    # Deduplicate tickers so the fixture has no repeated tickers
    seen: set[str] = set()
    cands: list[PickCandidate] = []
    for d in raw_cands:
        if d["ticker"] in seen:
            continue
        seen.add(d["ticker"])
        cands.append(PickCandidate(
            ticker=d["ticker"],
            composite_score=d["composite_score"],
            sector="Tech",
            risk_flags=tuple(d["flags"]),
            recommendation=d["recommendation"],
            mos_pct=d["mos_pct"],
            loss_chance_pct=d["loss_chance_pct"],
        ))

    hc_picks = select_picks(cands, count, gate="high_conviction")

    # Gate-level subset invariant: every HC pick must carry no active veto.
    # Derive the eligible set directly from the candidates fixture — this is
    # independent of the veto_only top-N selection, which can be occupied by
    # veto-eligible-but-not-HC names and therefore does NOT bound hc_picks.
    veto_eligible_tickers = {c.ticker for c in cands if is_eligible(c.risk_flags)}
    assert set(hc_picks) <= veto_eligible_tickers, (
        f"HC picks {hc_picks} contain a veto-ineligible ticker; "
        f"veto-eligible set: {veto_eligible_tickers}"
    )
    # Length invariants
    assert len(hc_picks) <= count
    assert len(hc_picks) <= len(veto_eligible_tickers)


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


# ---------------------------------------------------------------------------
# Uncap coverage pins — methodology conditions U1/U2/U3/U4 (2026-06-11).
#
# U1: select_picks(count=None) returns ALL eligible deduped names (no clamp).
# U2: dual-class dedup holds at count=None — one canonical slot per issuer.
# U3: regression guard — int count still clamps (no regression from uncap).
# U4: _adaptive_count with full 25-element pool scores all >= 65 → raw == 25.
#
# Fixture style: plain _cand() / _hc() builders (no mocks); matches every
# existing test in this file.  All tests are fully offline.
# ---------------------------------------------------------------------------


def test_select_picks_count_none_returns_all_eligible():
    """U1 pin: select_picks(count=None) returns ALL eligible deduped names,
    more than MAX_PICKS when the eligible pool exceeds MAX_PICKS.

    Fixture forces:
      - 25 eligible candidates (composite 100-down, no flags, no dual-class)
        plus 1 vetoed candidate with composite 999.
      - count=None → no [MIN_PICKS, MAX_PICKS] clamp.

    Expected:
      - Result length == 25 (all eligible, > MAX_PICKS=20).
      - The vetoed name is absent.
      - Ordering is composite-desc.
      - All 25 eligible tickers present.
    """
    vetoed = _cand("VETO", 999.0, flags=["altman_distress"])
    eligible = [_cand(f"E{i:02d}", float(100 - i)) for i in range(25)]
    cands = [vetoed] + eligible

    result = select_picks(cands, count=None)

    assert len(result) == 25, (
        f"Expected 25 names with count=None (all eligible, > MAX_PICKS={MAX_PICKS}); "
        f"got {len(result)}"
    )
    assert "VETO" not in result, "Vetoed ticker must be excluded even with count=None"
    # Correct composite-desc order.
    assert result == [f"E{i:02d}" for i in range(25)], (
        f"Expected composite-desc order; got {result}"
    )


def test_select_picks_count_none_composite_desc_order():
    """U1 pin: composite-desc ordering is preserved across the full uncapped domain.

    Fixture forces a 3-element unordered input so the sort is exercised without
    relying on insertion order.
    """
    cands = [_cand("LOW", 55.0), _cand("HIGH", 90.0), _cand("MID", 70.0)]
    result = select_picks(cands, count=None)
    assert result == ["HIGH", "MID", "LOW"], (
        f"Expected composite-desc order with count=None; got {result}"
    )


def test_select_picks_count_none_dual_class_u2_one_slot_canonical():
    """U2 pin: dual-class dedup holds with count=None — both classes eligible,
    ONE canonical slot emitted (GOOGL), sibling (GOOG) dropped.

    Fixture forces:
      - GOOG=95, GOOGL=94, AAA=90, BBB=88 — all eligible, no vetoes.
      - count=None → uncapped.

    Expected:
      - 'GOOG' absent (canonicalized to GOOGL slot).
      - 'GOOGL' present.
      - Full composite-desc order: GOOGL, AAA, BBB (3 distinct issuers, not 4).
    """
    cands = [
        _cand("GOOG", 95.0),
        _cand("GOOGL", 94.0),
        _cand("AAA", 90.0),
        _cand("BBB", 88.0),
    ]
    result = select_picks(cands, count=None)

    assert "GOOG" not in result, (
        "GOOG must be canonicalized to GOOGL slot even with count=None"
    )
    assert "GOOGL" in result, "GOOGL (canonical class) must appear in result"
    assert result == ["GOOGL", "AAA", "BBB"], (
        f"Expected ['GOOGL','AAA','BBB'] (one slot per dual-class issuer); got {result}"
    )


def test_select_picks_count_none_all_dual_class_pairs_dedup():
    """U2 pin: all three known dual-class pairs (Alphabet, Fox, News Corp) each
    collapse to one canonical slot with count=None.

    Fixture forces all 6 dual-class tickers eligible (no vetoes).
    Expected: 3 canonical tickers only (GOOGL, FOXA, NWSA).
    """
    cands = [
        _cand("GOOGL", 90.0), _cand("GOOG", 89.0),
        _cand("FOXA", 80.0), _cand("FOX", 79.0),
        _cand("NWSA", 70.0), _cand("NWS", 69.0),
    ]
    result = select_picks(cands, count=None)

    assert result == ["GOOGL", "FOXA", "NWSA"], (
        f"All dual-class siblings must be deduped with count=None; got {result}"
    )
    for non_canonical in ("GOOG", "FOX", "NWS"):
        assert non_canonical not in result, (
            f"{non_canonical} must be canonicalized away even with count=None"
        )


def test_select_picks_int_count_regression_guard():
    """U3 regression guard: integer count still clamps to [MIN_PICKS, MAX_PICKS].

    The uncap change (count=None) must not affect the existing int-count path.
    This test is a direct regression pin: 25 eligible candidates + count=5
    must return exactly 5 (the top 5 by composite), same as before the uncap.
    """
    eligible = [_cand(f"E{i:02d}", float(100 - i)) for i in range(25)]

    result = select_picks(eligible, count=5)

    assert len(result) == 5, (
        f"int count=5 must still return exactly 5 (clamp unchanged); got {len(result)}"
    )
    assert result == ["E00", "E01", "E02", "E03", "E04"], (
        f"Must return top-5 by composite with int count; got {result}"
    )


def test_select_picks_int_count_max_clamp_regression():
    """U3 regression guard: count > MAX_PICKS is still clamped to MAX_PICKS.

    Fixture: 25 eligible candidates, count=99.  Result must be exactly MAX_PICKS names.
    """
    eligible = [_cand(f"E{i:02d}", float(100 - i)) for i in range(25)]
    result = select_picks(eligible, count=99)

    assert len(result) == MAX_PICKS, (
        f"count=99 must clamp to MAX_PICKS={MAX_PICKS} (regression guard); "
        f"got {len(result)}"
    )
    assert result == [f"E{i:02d}" for i in range(MAX_PICKS)], (
        "Clamped result must be the top-MAX_PICKS by composite"
    )


def test_adaptive_count_raw_uncensored_25_element_pool_u4():
    """U4 pin: _adaptive_count with 25 scores all >= ADAPTIVE_COMPOSITE_MIN
    returns raw == 25 (the uncensored full-pool count, not clamped to MAX_PICKS).

    The uncap change (2026-06-11) removed the MAX_PICKS ceiling from the raw
    count.  This test freezes the contract: raw is counted over the FULL deduped
    pool, not just the first MAX_PICKS names.

    Fixture forces:
      - 25 scores, all 65.0 (exactly at entry threshold — inclusive boundary).
      - available_counts = list(range(1, MAX_PICKS + 1)) — the real wbc key range.

    Expected:
      - raw == 25 (full pool counted).
      - final is clamped to max(available_counts) = MAX_PICKS = 20 (since
        raw=25 > MAX_PICKS=20 and the largest available key is 20).
    """
    from scripts.backfill_portfolio_pit import ADAPTIVE_COMPOSITE_MIN, _adaptive_count

    scores = [ADAPTIVE_COMPOSITE_MIN] * 25
    available = list(range(1, MAX_PICKS + 1))

    raw, final = _adaptive_count(scores, available)

    assert raw == 25, (
        f"Expected raw=25 (uncensored full-pool count); got raw={raw}. "
        "The MAX_PICKS ceiling must be removed from the raw count (U4 uncap)."
    )
    # final clamps to MAX_PICKS (largest available <= 25 → that's MAX_PICKS=20).
    assert final == MAX_PICKS, (
        f"Expected final={MAX_PICKS} (clamped to largest available); got final={final}"
    )
