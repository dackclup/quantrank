"""Unit tests for compute.valuation.ensemble.

Per kickoff Step 5 spec, ~23 cases:
  A. Median + max + MoS arithmetic (4)
  B. Defense #4 outlier guard (3)
  C. Defense #3 stale filing (3)
  D. Defense #2 goodwill_heavy (2)
  E. RIM value_trap_risk warning (2)
  F. EnsembleResult shape invariants (3)
  G. Edge cases (3)
  H. Integration (3)

  L. Issue #289 — Site-2 output-level ceiling retired (3)
     Regression guard against the NVR false-positive on cron #69
     (2026-05-28): `multiples_pe ≈ 22× × $458.86 ≈ $10,094` tripped
     the $10,000 absolute ceiling and nulled all 6 methods despite
     legitimate inputs. Post-fix: Site-2 trigger deleted; the per-method
     extreme_*_estimate outlier guard (Defense #4, 5×/0.2× of current
     price) is the correct layer for out-of-distribution valuations.

Most aggregation/outlier/stale tests use the private helpers
(``_aggregate_methods``, ``_classify_outliers``, ``_all_methods_skipped``)
to exercise the logic in isolation; integration tests then call the
full ``compute_fair_price_ensemble`` with synthetic snapshots.
"""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import date

import pytest

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.valuation.ensemble import (
    METHOD_NAMES,
    EnsembleResult,
    FairPriceMethodResult,
    _aggregate_methods,
    _all_methods_skipped,
    _bvps_reported,
    _classify_outliers,
    _count_applicable_non_outliers,
    _data_quality_corrupt_result,
    _has_corrupt_input,
    _net_debt,
    compute_fair_price_ensemble,
    ensemble_result_to_dict,
)


def _result(value: float | None, applicable: bool, reason: str | None = None,
            tier_used: str | None = None) -> FairPriceMethodResult:
    return FairPriceMethodResult(
        value=value, applicable=applicable, reason=reason, tier_used=tier_used
    )


def _methods_fixture(values: dict[str, float | None]) -> dict[str, FairPriceMethodResult]:
    """Build a 6-key methods dict; missing methods are skipped (not applicable)."""
    out: dict[str, FairPriceMethodResult] = {}
    for name in METHOD_NAMES:
        v = values.get(name)
        if v is None:
            out[name] = _result(None, False, "test_skipped")
        else:
            out[name] = _result(v, True, None)
    return out


# -- A. Median + max + MoS arithmetic ----------------------------------------

def test_A1_four_methods_no_outliers_aggregation():
    """Four methods with all values in the [0.2×, 5×] band of current=$200,
    so no outlier flags. Sorted [50, 117, 160, 207] → median = 138.5."""
    methods = _methods_fixture({
        "graham": 50.0,         # 0.25× — in band
        "multiples_pe": 160.0,  # 0.80× — in band
        "rim": 207.0,           # 1.035× — in band
        "dcf": 117.0,           # 0.585× — in band
    })
    aggs, warnings = _aggregate_methods(methods, current_price=200.0)
    assert aggs["median"] == pytest.approx(138.5, abs=1e-6)
    assert aggs["max"] == 207.0
    assert aggs["low"] == 50.0
    assert aggs["high"] == 207.0
    # MoS = (138.5 - 200) / 138.5 × 100 ≈ -44.40%
    assert aggs["mos_pct"] == pytest.approx(
        (138.5 - 200.0) / 138.5 * 100.0, rel=1e-6
    )
    assert warnings == []


def test_A2_single_applicable_method_aggregates_to_self():
    methods = _methods_fixture({"graham": 50.0})
    aggs, _w = _aggregate_methods(methods, current_price=40.0)
    assert aggs["median"] == 50.0
    assert aggs["max"] == 50.0
    assert aggs["low"] == 50.0
    assert aggs["high"] == 50.0
    # Mos = (50-40)/50 × 100 = +20%
    assert aggs["mos_pct"] == pytest.approx(20.0, abs=1e-9)


def test_A3_no_applicable_methods_yields_all_null():
    methods = _methods_fixture({})  # all skipped
    aggs, warnings = _aggregate_methods(methods, current_price=100.0)
    assert aggs["median"] is None
    assert aggs["max"] is None
    assert aggs["low"] is None
    assert aggs["high"] is None
    assert aggs["mos_pct"] is None
    assert warnings == []


def test_A4_mos_sign_convention_undervalued_positive():
    """Direction check: median > current → POSITIVE MoS (undervalued)."""
    methods = _methods_fixture({"graham": 100.0})
    aggs, _w = _aggregate_methods(methods, current_price=80.0)
    # (100-80)/100 = 0.20 = 20.0%, positive (NOT 25% — common sign error)
    assert aggs["mos_pct"] == pytest.approx(20.0, abs=1e-9)


# -- B. Defense #4 outlier guard ---------------------------------------------

def test_B1_outlier_above_5x_excluded_from_max_kept_in_median():
    # current=$200; DCF=$1500 (= 7.5×) → outlier; Graham=$28, RIM=$207 ok.
    methods = _methods_fixture({
        "graham": 28.0,
        "rim": 207.0,
        "dcf": 1500.0,
    })
    aggs, warnings = _aggregate_methods(methods, current_price=200.0)
    # Max excludes the 1500 outlier → max = 207 (NOT 1500).
    assert aggs["max"] == 207.0
    # Median INCLUDES the 1500 outlier (median([28, 207, 1500]) = 207).
    assert aggs["median"] == 207.0
    # Outlier warning emitted for DCF.
    assert "extreme_dcf_estimate" in warnings


def test_B2_boundary_at_0_2x_strict_inequality():
    """value=$40 with current=$200 → exactly 0.2×, NOT outlier (strict).
    value=$39.99 → < 0.2×, outlier."""
    methods_at_boundary = _methods_fixture({"graham": 40.0})
    _, w_at = _classify_outliers(methods_at_boundary, current_price=200.0)
    out_at, _ = _classify_outliers(methods_at_boundary, current_price=200.0)
    assert "graham" not in out_at
    assert w_at == []

    methods_below = _methods_fixture({"graham": 39.99})
    out_below, w_below = _classify_outliers(methods_below, current_price=200.0)
    assert "graham" in out_below
    assert w_below == ["extreme_graham_estimate"]


def test_B3_multiple_outliers_each_warning_emitted():
    # 2 methods at $1200 (5× of $240=1200; strictly > 1200×0.0001 wouldn't
    # fire — use $1300 to clear the 5× threshold strictly).
    methods = _methods_fixture({
        "graham": 100.0,                # in band
        "multiples_pe": 1300.0,         # > 5× of 240 → outlier
        "rim": 1300.0,                  # > 5× of 240 → outlier
        "dcf": 200.0,                   # in band
    })
    aggs, warnings = _aggregate_methods(methods, current_price=240.0)
    # Max excludes both outliers → max = max(100, 200) = 200.
    assert aggs["max"] == 200.0
    # Two extreme warnings, both names.
    assert "extreme_multiples_pe_estimate" in warnings
    assert "extreme_rim_estimate" in warnings
    # Median includes all 4 applicable values.
    # Sorted [100, 200, 1300, 1300] → median = 750.
    assert aggs["median"] == pytest.approx(750.0, abs=1e-9)


# -- C. Defense #3 stale filing ----------------------------------------------

def test_C1_hard_stale_short_circuits_to_all_null_plus_risk_flag():
    """Hard-stale early return: all 6 methods skip with reason
    'stale_filing_hard'; no valuation_warnings; risk_flags carries
    'stale_filing_hard' for caller to merge."""
    snap = _make_snap(stockholders_equity=100.0, shares_outstanding=10.0)
    result, risk_flags = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=200,  # > 180 → hard
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={},
    )
    assert risk_flags == ["stale_filing_hard"]
    assert result.median is None
    assert result.max is None
    assert result.low is None
    assert result.high is None
    assert result.mos_pct is None
    assert result.valuation_warnings == []
    for name in METHOD_NAMES:
        m = result.methods[name]
        assert m.value is None
        assert m.applicable is False
        assert m.reason == "stale_filing_hard"


def test_C2_soft_stale_annotates_warning_methods_compute():
    snap = _make_snap_full()
    result, risk_flags = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=130,  # > 120, ≤ 180 → soft
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.0,
                "avg_3y_roe": 0.15,
                "fcf_5y": [80.0, 90.0, 100.0, 110.0, 120.0],
            },
        },
    )
    assert risk_flags == []  # soft is NOT a risk_flag
    assert "stale_filing_soft" in result.valuation_warnings


def test_C3_fresh_filing_no_stale_warnings():
    snap = _make_snap_full()
    result, risk_flags = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,  # fresh
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.0,
                "avg_3y_roe": 0.15,
                "fcf_5y": [80.0, 90.0, 100.0, 110.0, 120.0],
            },
        },
    )
    assert risk_flags == []
    assert "stale_filing_soft" not in result.valuation_warnings
    assert "stale_filing_hard" not in result.valuation_warnings


# -- D. Defense #2 goodwill_heavy --------------------------------------------

def test_D1_goodwill_heavy_appended_when_ratio_below_threshold():
    # equity=100, goodwill=40, intangibles=20, shares=10 →
    # BVPS_reported=10, TBVPS=4, ratio=0.4 < 0.5 → flag fires.
    snap = _make_snap(
        stockholders_equity=100.0,
        goodwill=40.0,
        intangibles_net=20.0,
        shares_outstanding=10.0,
    )
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=10.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={},
    )
    assert "goodwill_heavy" in result.valuation_warnings


def test_D2_goodwill_heavy_not_appended_when_clean_balance():
    # equity=100, goodwill=10, intangibles=5, shares=10 → TBVPS=8.5,
    # ratio = 0.85 > 0.5 → flag does NOT fire.
    snap = _make_snap(
        stockholders_equity=100.0,
        goodwill=10.0,
        intangibles_net=5.0,
        shares_outstanding=10.0,
    )
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=10.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={},
    )
    assert "goodwill_heavy" not in result.valuation_warnings


# -- E. RIM value_trap_risk warning ------------------------------------------

def test_E1_rim_applicable_no_value_trap_warning():
    # ROE > Ke → RIM computes; no value_trap_risk warning.
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.0,
                "avg_3y_roe": 0.20,  # > Ke=0.10
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    assert "value_trap_risk" not in result.valuation_warnings
    # Sanity: RIM is applicable.
    assert result.methods["rim"].applicable is True


def test_E2_rim_value_trap_warning_when_roe_below_ke():
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.0,
                "avg_3y_roe": 0.05,  # < Ke=0.10 → value-trap-risk
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    assert "value_trap_risk" in result.valuation_warnings
    assert result.methods["rim"].applicable is False
    assert (
        result.methods["rim"].reason == "value_trap_risk_roe_below_cost_of_equity"
    )


def test_E3_no_value_trap_warning_when_roe_history_missing_issue_11():
    """Issue #11 regression test — a ticker with `avg_3y_roe=None`
    (missing input) must NOT get a `value_trap_risk` warning. The
    new `insufficient_history_for_roe` skip reason is the signal
    that RIM had no data; it's NOT a value-trap signal."""
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.0,
                "avg_3y_roe": None,  # missing 3y equity history
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    # Critical: the false-positive value_trap_risk warning is GONE.
    assert "value_trap_risk" not in result.valuation_warnings
    # RIM is still skipped, but under the distinct reason.
    assert result.methods["rim"].applicable is False
    assert result.methods["rim"].reason == "insufficient_history_for_roe"


# -- F. EnsembleResult shape invariants --------------------------------------

def test_F1_methods_dict_has_six_keys():
    """The 6 expected method names exactly."""
    methods = _all_methods_skipped("test_reason")
    assert set(methods.keys()) == set(METHOD_NAMES)
    assert len(METHOD_NAMES) == 6


def test_F2_fair_price_method_result_is_frozen():
    assert is_dataclass(FairPriceMethodResult)
    r = FairPriceMethodResult(value=10.0, applicable=True, reason=None, tier_used=None)
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass raises FrozenInstanceError
        r.value = 99.0  # type: ignore[misc]


def test_F3_ensemble_result_is_frozen():
    assert is_dataclass(EnsembleResult)
    er = EnsembleResult(
        methods=_all_methods_skipped("x"),
        median=None, max=None, low=None, high=None, mos_pct=None,
        valuation_warnings=[],
    )
    with pytest.raises(Exception):  # noqa: B017
        er.median = 99.0  # type: ignore[misc]


def test_F4_tier_used_none_for_non_multiples_when_applicable():
    # Build via full ensemble path: graham/rim/dcf should never carry tier_used.
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.0,
                "avg_3y_roe": 0.20,
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    for non_multiples in ("graham", "rim", "dcf"):
        assert result.methods[non_multiples].tier_used is None


# -- G. Edge cases -----------------------------------------------------------

def test_G1_zero_current_price_yields_null_mos():
    methods = _methods_fixture({"graham": 50.0})
    aggs, _w = _aggregate_methods(methods, current_price=0.0)
    assert aggs["mos_pct"] is None


def test_G2_negative_current_price_yields_null_mos():
    methods = _methods_fixture({"graham": 50.0})
    aggs, _w = _aggregate_methods(methods, current_price=-10.0)
    assert aggs["mos_pct"] is None


def test_G3_negative_method_value_treated_as_below_outlier_floor():
    """Defensive: if a method ever produces a negative value (shouldn't,
    given gates, but…), the outlier guard catches it because
    -50 < 0.2 × 200 = 40."""
    methods = _methods_fixture({"graham": 100.0})
    methods["dcf"] = _result(-50.0, applicable=True)
    out, w = _classify_outliers(methods, current_price=200.0)
    assert "dcf" in out
    assert "extreme_dcf_estimate" in w


# -- H. Integration with full ensemble ---------------------------------------

def test_H1_synthetic_it_stock_full_ensemble_path():
    """Synthetic IT stock with reasonable inputs → some methods apply."""
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},  # empty → multiples skip
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.5,
                "avg_3y_roe": 0.15,
                "fcf_5y": [80.0, 90.0, 100.0, 110.0, 120.0],
            },
        },
    )
    # With empty peer panels, multiples all skip; graham/rim/dcf compute.
    assert result.methods["graham"].applicable is True
    assert result.methods["rim"].applicable is True
    assert result.methods["dcf"].applicable is True
    # Multiples skip because peer_tier_used = INSUFFICIENT (empty panel).
    assert result.methods["multiples_pe"].applicable is False
    # At least one applicable → median/max non-None.
    assert result.median is not None
    assert result.max is not None


def test_H2_financials_sector_skips_dcf_and_ev_ebitda():
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Financials",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.5,
                "avg_3y_roe": 0.15,
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    assert result.methods["dcf"].reason == "sector_excluded_financials"
    # EV/EBITDA also excluded for Financials. Note: when peer_tier is
    # INSUFFICIENT, that reason wins over the sector reason; with empty
    # peer panel here, we expect either reason — both indicate skip.
    assert result.methods["multiples_ev_ebitda"].applicable is False


def test_H3_utilities_sector_skips_dcf_only():
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Utilities",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.5,
                "avg_3y_roe": 0.15,
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    assert result.methods["dcf"].reason == "sector_excluded_utilities"
    # Utilities still get multiples_ev_ebitda when peers exist; here
    # peer panel is empty so reason is INSUFFICIENT.
    assert result.methods["multiples_ev_ebitda"].applicable is False


# -- J. valuation_methods_applicable (Epic #150 Phase 2.1) --------------------


def test_J1_count_excludes_outliers_and_skips():
    """4 methods applicable, 1 outlier above 5×, 1 skipped → count = 3."""
    methods = _methods_fixture({
        "graham": 50.0,        # 0.25× — in band
        "multiples_pe": 100.0,  # 0.50× — in band
        "rim": 1500.0,         # 7.5× — OUTLIER
        "dcf": 117.0,          # 0.585× — in band
    })
    extreme_warnings = ["extreme_rim_estimate"]
    assert _count_applicable_non_outliers(methods, extreme_warnings) == 3


def test_J2_all_skipped_returns_zero():
    methods = _all_methods_skipped("test")
    assert _count_applicable_non_outliers(methods, []) == 0


def test_J3_all_outliers_returns_zero():
    methods = _methods_fixture({
        "graham": 10000.0,
        "dcf": 0.001,
    })
    extreme_warnings = ["extreme_graham_estimate", "extreme_dcf_estimate"]
    assert _count_applicable_non_outliers(methods, extreme_warnings) == 0


def test_J4_ensemble_result_carries_default_zero_when_unset():
    """Default value is 0 — matches the hard-stale / data-quality-null paths."""
    er = EnsembleResult(
        methods=_all_methods_skipped("x"),
        median=None, max=None, low=None, high=None, mos_pct=None,
    )
    assert er.valuation_methods_applicable == 0


def test_J5_ensemble_result_to_dict_emits_field():
    er = EnsembleResult(
        methods=_methods_fixture({"graham": 50.0, "dcf": 60.0}),
        median=55.0, max=60.0, low=50.0, high=60.0, mos_pct=10.0,
        valuation_warnings=[],
        valuation_methods_applicable=2,
    )
    d = ensemble_result_to_dict(er)
    assert d["valuation_methods_applicable"] == 2


def test_J6_full_ensemble_path_populates_field():
    """Synthetic IT stock — graham/rim/dcf compute, multiples skip on empty
    peer panel, no outliers → field equals 3."""
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.5,
                "avg_3y_roe": 0.15,
                "fcf_5y": [80.0, 90.0, 100.0, 110.0, 120.0],
            },
        },
    )
    # graham + rim + dcf applicable, no outliers, no multiples → 3.
    assert result.valuation_methods_applicable == 3


def test_J7_hard_stale_path_yields_zero():
    """Hard-stale short-circuit: every method skips → field defaults to 0."""
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=999,  # well past hard-stale threshold
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={"TST": {}},
    )
    assert result.valuation_methods_applicable == 0


# -- K. extreme_estimate_majority (issue #177) -------------------------------
#
# Annotate-only flag: fires when ≥ ``config.EXTREME_MAJORITY_THRESHOLD``
# (= 3) of the 6 methods produce ``extreme_*_estimate`` warnings — the
# Huber 1981 §1.4 breakdown-point cohort where median-on-all degrades.
# The flag is appended inside ``compute_fair_price_ensemble`` after the
# ``_aggregate_methods`` call; tests below build per-method dicts and
# invoke the threshold-comparison branch via a tiny adapter rather than
# the full per-method computation path (which would require crafting
# 6 simultaneously-extreme inputs against 3 different per-method
# gates). This keeps the threshold semantics testable in isolation.


def _emit_majority_flag(extreme_warnings: list[str]) -> bool:
    """Mirror the threshold branch in ``compute_fair_price_ensemble`` —
    keeps the test against the actual config constant so a future bump
    of EXTREME_MAJORITY_THRESHOLD flips these tests automatically."""
    return len(extreme_warnings) >= config.EXTREME_MAJORITY_THRESHOLD


def test_K1_silent_on_zero_extreme():
    assert _emit_majority_flag([]) is False


def test_K2_silent_on_one_extreme():
    assert _emit_majority_flag(["extreme_graham_estimate"]) is False


def test_K3_silent_at_breakdown_minus_one():
    """Boundary — 2 outliers is the highest count median-of-6 still
    tolerates per Huber breakdown-point math ⌊5/2⌋ = 2; flag silent."""
    assert _emit_majority_flag(
        ["extreme_graham_estimate", "extreme_rim_estimate"]
    ) is False


def test_K4_fires_at_threshold():
    """At threshold = 3 extreme methods, the flag MUST fire (the median
    has now passed its Huber breakdown point)."""
    assert _emit_majority_flag(
        [
            "extreme_graham_estimate",
            "extreme_rim_estimate",
            "extreme_dcf_estimate",
        ]
    ) is True


def test_K5_fires_at_four_extreme():
    assert _emit_majority_flag(
        [f"extreme_{n}_estimate" for n in ("graham", "rim", "dcf", "multiples_pb")]
    ) is True


def test_K6_fires_at_all_six_extreme():
    """All 6 methods extreme — flag fires (and the median is at this
    point fully past breakdown). Defensive — universe-wide this should
    be rare, but the threshold logic must not short-circuit."""
    assert _emit_majority_flag(
        [f"extreme_{n}_estimate" for n in METHOD_NAMES]
    ) is True


def test_K7_full_ensemble_emits_flag_when_three_methods_extreme():
    """Integration — synthetic snapshot + current_price chosen so ≥ 3 of
    the 6 methods produce outliers above the 5× Defense #4 ceiling. The
    full ensemble path must surface ``extreme_estimate_majority`` in
    ``valuation_warnings`` alongside the per-method extreme flags."""
    snap = _make_snap_full()
    # current_price = $2 is small relative to the snapshot's $100 BVPS,
    # $10 EPS-TTM (net_income $100 / 10 shares), and $100 FCF/yr.
    # Per-method estimates:
    #   graham:  EPS=2.5 + tbvps=$99.50 → > $10 (5× of $2)
    #   multiples_pb: bvps_reported $100 × peer 1.0 = $100 → outlier
    #   multiples_pe (peer empty): skipped, no value to flag
    #   rim: tbvps $99.50 × residual income premium → outlier
    #   dcf: 5× $100 FCF discounted → outlier
    # Expect at least 3 outlier flags AND the majority annotate.
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=2.0,
        filing_lag_days_value=30,
        peer_panels={
            "pe": {},
            "pb": {"sub_industry": ["PEER1", "PEER2", "PEER3"]},
            "ev_ebitda": {},
        },
        universe_metrics={
            "PEER1": {"pb_reported": 1.0},
            "PEER2": {"pb_reported": 1.0},
            "PEER3": {"pb_reported": 1.0},
        },
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.5,
                "avg_3y_roe": 0.15,
                "fcf_5y": [100.0] * 5,
            },
        },
    )
    extreme_flags = [
        w for w in result.valuation_warnings
        if w.startswith("extreme_") and w.endswith("_estimate")
    ]
    assert len(extreme_flags) >= config.EXTREME_MAJORITY_THRESHOLD, (
        f"Synthetic setup did not produce ≥ {config.EXTREME_MAJORITY_THRESHOLD} "
        f"extreme flags as expected; got {extreme_flags}. The K7 fixture "
        "drifted relative to one of the 6 per-method gates — re-tune "
        "current_price or peer fixture rather than weakening this assertion."
    )
    assert "extreme_estimate_majority" in result.valuation_warnings


def test_K8_full_ensemble_silent_when_one_method_extreme():
    """Counter-integration — synthetic IT stock with reasonable current
    price produces at most 1 outlier (the per-method gates land most
    methods in-band) → majority flag must NOT fire."""
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={
            "TST": {
                "eps_3y_avg": 2.5,
                "avg_3y_roe": 0.15,
                "fcf_5y": [80.0, 90.0, 100.0, 110.0, 120.0],
            },
        },
    )
    extreme_flags = [
        w for w in result.valuation_warnings
        if w.startswith("extreme_") and w.endswith("_estimate")
    ]
    assert len(extreme_flags) < config.EXTREME_MAJORITY_THRESHOLD
    assert "extreme_estimate_majority" not in result.valuation_warnings


def test_K9_hard_stale_path_silent_on_majority_flag():
    """Hard-stale early return short-circuits the entire aggregation —
    no per-method extreme flags fire so the majority annotate is also
    silent (defensive: prevents the flag from being emitted at the
    all-null path where there are no estimates to be extreme about)."""
    snap = _make_snap_full()
    result, _r = compute_fair_price_ensemble(
        ticker="TST",
        snap=snap,
        sector="Information Technology",
        sub_industry=None,
        industry=None,
        current_price=100.0,
        filing_lag_days_value=999,  # past hard-stale
        peer_panels={"pe": {}, "pb": {}, "ev_ebitda": {}},
        universe_metrics={},
        historical_metrics={"TST": {}},
    )
    assert "extreme_estimate_majority" not in result.valuation_warnings


# -- Helper invariants --------------------------------------------------------

def test_net_debt_helper():
    snap = _make_snap(long_term_debt=80.0, short_term_debt=10.0, cash=30.0)
    assert _net_debt(snap) == 60.0  # 80 + 10 - 30
    snap_all_none = _make_snap(long_term_debt=None, short_term_debt=None, cash=None)
    assert _net_debt(snap_all_none) is None
    snap_partial = _make_snap(long_term_debt=80.0, short_term_debt=None, cash=20.0)
    assert _net_debt(snap_partial) == 60.0  # 80 + 0 - 20


def test_bvps_reported_helper():
    snap = _make_snap(stockholders_equity=100.0, shares_outstanding=10.0)
    assert _bvps_reported(snap) == 10.0
    snap_no_equity = _make_snap(stockholders_equity=None, shares_outstanding=10.0)
    assert _bvps_reported(snap_no_equity) is None
    snap_no_shares = _make_snap(stockholders_equity=100.0, shares_outstanding=0.0)
    assert _bvps_reported(snap_no_shares) is None


def test_extreme_estimate_constants_sane():
    assert config.EXTREME_ESTIMATE_HIGH == 5.0
    assert config.EXTREME_ESTIMATE_LOW == 0.2


# -- I. ensemble_result_to_dict shape ----------------------------------------

def test_I1_ensemble_result_to_dict_shape_matches_ts_type():
    """Shape mirrors FairPriceEnsemble in frontend/lib/types.ts.

    Top-level keys: methods, median, max, low, high, mos_pct,
    valuation_warnings. Each method is a 4-key sub-dict (value,
    applicable, reason, tier_used).
    """
    methods = _methods_fixture({
        "graham": 50.0,
        "multiples_pe": 160.0,
        "multiples_pb": None,
        "multiples_ev_ebitda": None,
        "rim": 207.0,
        "dcf": 117.0,
    })
    methods["multiples_pe"] = _result(
        160.0, applicable=True, reason=None, tier_used="sub_industry"
    )
    result = EnsembleResult(
        methods=methods,
        median=138.5,
        max=207.0,
        low=50.0,
        high=207.0,
        mos_pct=-44.4,
        valuation_warnings=["goodwill_heavy"],
    )
    out = ensemble_result_to_dict(result)
    assert set(out.keys()) == {
        "methods", "median", "max", "low", "high", "mos_pct",
        "valuation_warnings", "valuation_methods_applicable",
    }
    assert set(out["methods"].keys()) == set(METHOD_NAMES)
    for name, sub in out["methods"].items():
        assert set(sub.keys()) == {"value", "applicable", "reason", "tier_used"}, name
    assert out["median"] == 138.5
    assert out["max"] == 207.0
    assert out["mos_pct"] == -44.4
    assert out["valuation_warnings"] == ["goodwill_heavy"]
    assert out["methods"]["multiples_pe"]["tier_used"] == "sub_industry"
    assert out["methods"]["graham"]["tier_used"] is None


def test_I2_ensemble_result_to_dict_handles_all_null():
    """When every method is skipped, dict reflects null aggregates and
    preserves the per-method skip reason."""
    methods = _all_methods_skipped("stale_filing_hard")
    result = EnsembleResult(
        methods=methods,
        median=None,
        max=None,
        low=None,
        high=None,
        mos_pct=None,
        valuation_warnings=[],
    )
    out = ensemble_result_to_dict(result)
    assert out["median"] is None
    assert out["max"] is None
    assert out["mos_pct"] is None
    assert out["valuation_warnings"] == []
    for sub in out["methods"].values():
        assert sub["value"] is None
        assert sub["applicable"] is False
        assert sub["reason"] == "stale_filing_hard"


def test_I3_ensemble_result_to_dict_warnings_is_a_copy():
    """The returned ``valuation_warnings`` list is a new list, not the
    same object — mutating it must not affect the EnsembleResult."""
    result = EnsembleResult(
        methods=_all_methods_skipped("stale_filing_hard"),
        median=None,
        max=None,
        low=None,
        high=None,
        mos_pct=None,
        valuation_warnings=["goodwill_heavy"],
    )
    out = ensemble_result_to_dict(result)
    out["valuation_warnings"].append("mutation_test")
    assert result.valuation_warnings == ["goodwill_heavy"]


# -- J. Step 7.5 data-quality sanity guard -----------------------------------

def test_data_quality_sanity_guard_triggers_on_extreme_method_value():
    """Synthetic SPG-pattern: 5 methods compute reasonable values, 1 produces
    an absurd $10,001/share (just above the $10,000 ceiling). The guard
    must null all 6 methods, surface a single warning, and return an empty
    risk_flags list (data quality is not a ranking veto)."""
    methods = {
        "graham": _result(50.0, applicable=True),
        "multiples_pe": _result(60.0, applicable=True, tier_used="sub_industry"),
        "multiples_pb": _result(10001.0, applicable=True, tier_used="sector"),
        "multiples_ev_ebitda": _result(70.0, applicable=True, tier_used="sub_industry"),
        "rim": _result(55.0, applicable=True),
        "dcf": _result(65.0, applicable=True),
    }
    assert _has_corrupt_input(methods) is True

    result = _data_quality_corrupt_result(methods)
    # Issue #262 rename (2026-05-26) — Site 2 emission renamed from
    # ``data_quality_input_corruption`` (input-level corruption,
    # exclusive to ``risk_overlay.py`` veto surface) to
    # ``valuation_output_anomalous`` (output-level anomaly,
    # semantically distinct per methodology-scientist Mode B).
    for name in METHOD_NAMES:
        m = result.methods[name]
        assert m.value is None
        assert m.applicable is False
        assert m.reason == "valuation_output_anomalous"
    # Aggregates all None.
    assert result.median is None
    assert result.max is None
    assert result.low is None
    assert result.high is None
    assert result.mos_pct is None
    # Issue #262 rename — single canonical warning identifier.
    # Single warning, no others.
    assert result.valuation_warnings == ["valuation_output_anomalous"]
    # tier_used preserved on multiples for diagnostics.
    assert result.methods["multiples_pe"].tier_used == "sub_industry"
    assert result.methods["multiples_pb"].tier_used == "sector"
    assert result.methods["multiples_ev_ebitda"].tier_used == "sub_industry"
    assert result.methods["graham"].tier_used is None


def test_data_quality_guard_boundary_exactly_at_ceiling():
    """Method value = 10000.0 exactly → does NOT trigger (strict >)."""
    methods = {
        "graham": _result(50.0, applicable=True),
        "multiples_pe": _result(60.0, applicable=True),
        "multiples_pb": _result(config.FAIR_PRICE_DATA_QUALITY_CEILING, applicable=True),
        "multiples_ev_ebitda": _result(70.0, applicable=True),
        "rim": _result(55.0, applicable=True),
        "dcf": _result(65.0, applicable=True),
    }
    assert _has_corrupt_input(methods) is False


def test_data_quality_guard_skipped_methods_dont_trigger():
    """Methods with applicable=False are pass-through. A skipped method
    can never trip the guard (its value is None or stale; only applicable
    values are checked)."""
    methods = {
        "graham": _result(None, applicable=False, reason="non_positive_eps_3y_avg"),
        "multiples_pe": _result(60.0, applicable=True),
        "multiples_pb": _result(None, applicable=False, reason="non_positive_or_missing_bvps"),
        "multiples_ev_ebitda": _result(70.0, applicable=True),
        "rim": _result(None, applicable=False, reason="value_trap_risk_roe_below_cost_of_equity"),
        "dcf": _result(65.0, applicable=True),
    }
    assert _has_corrupt_input(methods) is False


def test_site2_data_quality_guard_retired_post_issue_289():
    """Issue #289 (2026-05-28) — Site-2 (output-level) data-quality guard
    RETIRED per methodology-scientist Mode B verdict Option C. End-to-end
    regression guard: a corrupted snapshot that PRE-fix would have routed
    through `_has_corrupt_input` → `_data_quality_corrupt_result` and
    produced the all-null payload with `valuation_warnings ==
    ["valuation_output_anomalous"]` POST-fix produces the normal ensemble
    path output with `extreme_*_estimate` per-method annotates + the
    `extreme_estimate_majority` Huber-breakdown annotate (Defense #4 +
    Issue #177 = the correct ensemble-robustness layer).

    The shape change is structural:
    - Pre-fix: `valuation_warnings == ["valuation_output_anomalous"]`,
      `result.median is None`, all 6 methods nulled with reason
      `valuation_output_anomalous`
    - Post-fix: `valuation_warnings` contains `extreme_*_estimate`
      annotates for each method exceeding the 5×/0.2× Defense #4 band,
      PLUS `extreme_estimate_majority` if ≥ 3 methods are extreme;
      `valuation_output_anomalous` ABSENT from `ensemble`'s
      `valuation_warnings` (writer-parity emit in `compute/main.py`
      is the only remaining source, gated on Site-1 veto in risk_flags)

    Site-1 input-level corruption guard at
    `compute/scoring/risk_overlay.py::_data_quality_input_corruption`
    continues to fire its VETO (`data_quality_input_corruption` in
    risk_flags) — that's the canonical input-corruption defense, and
    Site-2 was the redundant downstream layer that's now retired.

    NVR's $458 EPS / $6,098 price case (the empirical false positive
    on cron #69, 2026-05-28) is covered separately under
    `test_NVR_*_no_longer_nulled_*` per the test-engineer follow-up.
    """
    # Equity $5B / 10 shares = $500M/share TBVPS — far above the $10K ceiling.
    snap = FundamentalsSnapshot(
        ticker="CORRUPT",
        cik="0000000099",
        revenue=1000.0,
        net_income=100.0,
        operating_income=200.0,
        total_assets=10_000_000_000.0,
        total_liabilities=5_000_000_000.0,
        stockholders_equity=5_000_000_000.0,
        cash=100_000_000.0,
        operating_cash_flow=300_000_000.0,
        capex=50_000_000.0,
        free_cash_flow=250_000_000.0,
        eps_basic=10_000_000.0,
        eps_diluted=10_000_000.0,
        shares_outstanding=10.0,  # corrupted — should be millions
        long_term_debt=500_000_000.0,
        short_term_debt=50_000_000.0,
        ebitda=400_000_000.0,
        goodwill=10_000_000.0,
        intangibles_net=5_000_000.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 14),
    )
    historical_metrics = {
        "CORRUPT": {
            "eps_3y_avg": 10_000_000.0,
            "avg_3y_roe": 0.20,
            "fcf_5y": [200_000_000.0] * 5,
        }
    }
    universe_metrics = {"CORRUPT": {"pe_ttm": 1.0, "pb_reported": 1.0, "ev_ebitda_ttm": 5.0}}
    peer_panels = {
        "pe": {"sub_industry": [], "industry": [], "sector": [], "broad": []},
        "pb": {"sub_industry": [], "industry": [], "sector": [], "broad": []},
        "ev_ebitda": {"sub_industry": [], "industry": [], "sector": [], "broad": []},
    }
    result, extra_flags = compute_fair_price_ensemble(
        ticker="CORRUPT",
        snap=snap,
        sector="Information Technology",
        sub_industry="Software",
        industry=None,
        current_price=100.0,
        filing_lag_days_value=30,
        peer_panels=peer_panels,
        universe_metrics=universe_metrics,
        historical_metrics=historical_metrics,
    )
    # Issue #289 retirement-guard assertions:
    # 1. Site-2 emission `valuation_output_anomalous` ABSENT from ensemble's
    #    valuation_warnings (the writer-parity emit in compute/main.py is
    #    the only remaining source, gated on Site-1 risk_flags — not
    #    exercised here since this test stays in the ensemble layer).
    assert "valuation_output_anomalous" not in result.valuation_warnings
    # 2. Defense #4 5×/0.2× per-method extreme guard fires correctly —
    #    methods producing absurd values get `extreme_<method>_estimate`
    #    annotates instead of being silently nulled. At least one method
    #    in the corrupted-snapshot synthetic case should trip the band.
    assert any(
        w.startswith("extreme_") and w.endswith("_estimate")
        for w in result.valuation_warnings
    )
    # 3. extra_flags (risk_flags appended by the ensemble path) remains
    #    empty — Site-1 (`data_quality_input_corruption` veto) is in
    #    risk_overlay.py, not in the ensemble path itself.
    assert extra_flags == []
    # 4. No method has reason `valuation_output_anomalous` post-retirement
    #    (each method either computed a value or skipped with its own
    #    applicability reason like `non_positive_eps_3y_avg`).
    for name in METHOD_NAMES:
        m = result.methods[name]
        assert m.reason != "valuation_output_anomalous", (
            f"Site-2 retired by Issue #289 — method {name!r} should NOT carry "
            f"`valuation_output_anomalous` reason from the ensemble path; "
            f"got reason={m.reason!r}"
        )


# -- Helpers ------------------------------------------------------------------

def _make_snap(**kwargs) -> FundamentalsSnapshot:
    """Minimal FundamentalsSnapshot for testing."""
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "stockholders_equity": 100.0,
        "shares_outstanding": 10.0,
        "goodwill": 0.0,
        "intangibles_net": 0.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _make_snap_full() -> FundamentalsSnapshot:
    """Snapshot with most fields populated for ensemble integration tests."""
    return FundamentalsSnapshot(
        ticker="TST",
        cik="0000000001",
        revenue=1000.0,
        net_income=100.0,
        gross_profit=500.0,
        operating_income=200.0,
        total_assets=2000.0,
        total_liabilities=1000.0,
        stockholders_equity=1000.0,
        cash=200.0,
        operating_cash_flow=150.0,
        capex=50.0,
        free_cash_flow=100.0,
        eps_basic=2.5,
        eps_diluted=2.5,
        shares_outstanding=10.0,
        retained_earnings=400.0,
        long_term_debt=300.0,
        short_term_debt=50.0,
        ebitda=220.0,
        goodwill=10.0,
        intangibles_net=5.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 14),
    )


# -- L. Issue #289 — Site-2 output-level ceiling retired ----------------------
#
# Regression guard against the NVR false-positive on cron #69 (2026-05-28).
# Pre-fix: `multiples_pe ≈ sector_PE × EPS_TTM ≈ 22× × $458.86 ≈ $10,094`
# tripped the $10,000 absolute Site-2 ceiling in ensemble.py:457-458 and
# nulled ALL 6 methods → `fair_price.median = null` + `valuation_warnings =
# ["valuation_output_anomalous"]` despite legitimate inputs and a 65% MoS
# signal. Post-fix (methodology-scientist Mode B verdict Option C, 2026-05-28):
# Site-2 trigger deleted. The per-method Defense #4 outlier guard
# (``extreme_*_estimate``, 5×/0.2× of current price) is the correct layer;
# it correctly annotates out-of-distribution estimates while leaving the
# other methods to produce a non-null ensemble median.


def _make_nvr_snap() -> FundamentalsSnapshot:
    """Synthetic NVR-shape snapshot.

    Key numbers mirroring cron #69 (2026-05-28):
      shares_outstanding = 2_700_000  (low-float homebuilder, ~2.7 M)
      net_income         = 1_238_922_000  → EPS_TTM = NI/shares ≈ $458.86
      current_price (caller-supplied) = $6,098

    With a sector PE median of ~22×:
      multiples_pe ≈ 22 × $458.86 ≈ $10,094 > old $10,000 Site-2 ceiling
      → pre-fix: ALL 6 methods nulled.
      → post-fix: Site-2 deleted; Defense #4 (5× of $6,098 = $30,490)
        does NOT flag multiples_pe as an outlier at $10,094 (< 5×), so
        the method contributes to the median normally.
    """
    return FundamentalsSnapshot(
        ticker="NVR",
        cik="0000012345",
        revenue=9_525_000_000.0,
        net_income=1_238_922_000.0,       # → EPS_TTM ≈ $458.86 / share
        operating_income=1_500_000_000.0,
        total_assets=6_000_000_000.0,
        total_liabilities=2_500_000_000.0,
        stockholders_equity=3_500_000_000.0,
        cash=1_200_000_000.0,
        operating_cash_flow=1_300_000_000.0,
        capex=50_000_000.0,
        free_cash_flow=1_250_000_000.0,
        eps_basic=458.86,
        eps_diluted=458.86,
        shares_outstanding=2_700_000.0,   # low float → high EPS_TTM
        long_term_debt=900_000_000.0,
        short_term_debt=50_000_000.0,
        ebitda=1_600_000_000.0,
        goodwill=0.0,
        intangibles_net=0.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 14),
    )


def _make_nvr_peer_panels(n_peers: int = 10) -> tuple[
    dict[str, dict[str, list[str]]],
    dict[str, dict[str, float | None]],
]:
    """Build peer panels with ``n_peers`` sector-level PE peers at 22×.

    sector median = 22.0 exactly → multiples_pe ≈ 22 × $458.86 ≈ $10,094.
    pb + ev_ebitda panels are empty so those methods skip on
    ``insufficient_peers_all_tiers`` (irrelevant to this regression).
    """
    peer_tickers = [f"HB{i}" for i in range(n_peers)]
    peer_panels: dict[str, dict[str, list[str]]] = {
        "pe": {"sector": peer_tickers},
        "pb": {},
        "ev_ebitda": {},
    }
    universe_metrics: dict[str, dict[str, float | None]] = {
        t: {"pe_ttm": 22.0, "pb_reported": None, "ev_ebitda_ttm": None}
        for t in peer_tickers
    }
    return peer_panels, universe_metrics


def test_L1_NVR_fair_price_methods_no_longer_nulled_by_output_ceiling():
    """Regression: pre-fix Site-2 ceiling (`FAIR_PRICE_DATA_QUALITY_CEILING
    = $10,000`) nulled all 6 methods for NVR because `multiples_pe ≈ $10,094`
    exceeded the absolute-dollar gate.  Post-fix (Site-2 trigger deleted per
    Issue #289 Option C): ensemble computes normally and returns a non-null
    median.

    Empirical NVR inputs (cron #69, 2026-05-28):
      current_price = $6,098 · shares ≈ 2.7 M · EPS_TTM ≈ $458.86
      sector PE median ≈ 22× → multiples_pe ≈ $10,094
    """
    snap = _make_nvr_snap()
    peer_panels, universe_metrics = _make_nvr_peer_panels(n_peers=10)

    result, risk_flags = compute_fair_price_ensemble(
        ticker="NVR",
        snap=snap,
        sector="Consumer Discretionary",
        sub_industry=None,
        industry=None,
        current_price=6098.0,
        filing_lag_days_value=30,
        peer_panels=peer_panels,
        universe_metrics=universe_metrics,
        historical_metrics={
            "NVR": {
                "eps_3y_avg": 400.0,
                "avg_3y_roe": 0.35,
                "fcf_5y": [1_000_000_000.0] * 5,
            },
        },
    )

    # Post-fix: median must be non-null — graham/rim/dcf and multiples_pe
    # all compute on this snapshot; pre-fix all 6 were blocked.
    assert result.median is not None, (
        "Site-2 ceiling regression: ensemble returned null median for NVR "
        "despite legitimate inputs.  Verify that the Site-2 trigger in "
        "ensemble.py was deleted per Issue #289."
    )

    # Post-fix: Site-2 emission must NOT appear from the ensemble layer.
    # (Writer-parity emit for Site-1 veto cohort lives in compute/main.py,
    # not here — that is not tested in this file per the hard constraint.)
    assert "valuation_output_anomalous" not in result.valuation_warnings, (
        "Site-2 ceiling regression: 'valuation_output_anomalous' surfaced "
        "from ensemble.py despite the Site-2 trigger being deleted. "
        "Verify ensemble.py:450-479 per Issue #289."
    )

    # Post-fix: at least one method must be applicable.
    applicable_methods = [
        name for name, m in result.methods.items() if m.applicable
    ]
    assert len(applicable_methods) > 0, (
        f"All 6 methods are non-applicable — same null payload as pre-fix. "
        f"Applicable: {applicable_methods}"
    )

    # Sanity: NVR has clean inputs, no risk_flags expected.
    assert risk_flags == []


def test_L2_dead_code_functions_still_callable_after_site2_deletion():
    """Dead-code retention guard (one-cycle hold per Issue #289 Option C).

    `_has_corrupt_input` and `_data_quality_corrupt_result` must remain
    importable and callable after the Site-2 call site was deleted at
    ensemble.py:457-458.  They are kept for one cycle so the reviewer can
    confirm the deletion cleanly before a follow-up PR removes them.

    If this test FAILS, one of the functions was removed too early.
    """
    import compute.valuation.ensemble as _ensemble

    assert callable(_ensemble._has_corrupt_input), (
        "_has_corrupt_input was removed prematurely — Issue #289 Option C "
        "specifies dead-code retention for one cycle before removal."
    )
    assert callable(_ensemble._data_quality_corrupt_result), (
        "_data_quality_corrupt_result was removed prematurely — Issue #289 "
        "Option C specifies dead-code retention for one cycle before removal."
    )


def test_L3_site2_ceiling_not_invoked_for_high_share_price_ticker():
    """Site-2 call-site deletion guard: a ticker with a legitimately high
    per-share price (current_price = $3,500) and a multiples_pe estimate
    of ~$10,094 that EXCEEDS the old $10,000 Site-2 ceiling but stays WITHIN
    Defense #4's 5× band ($17,500) must return a non-null median.

    Pre-fix (ensemble.py:457-458 present):
      `_has_corrupt_input` checks every applicable method value > $10,000 →
      multiples_pe ≈ $10,094 > $10,000 → all 6 methods set to null +
      `valuation_output_anomalous` emitted → `result.median = None`.
      So: assert result.median is not None  →  FAIL (RED on pre-fix).

    Post-fix (call site deleted):
      No Site-2 check; Defense #4 (5× of $3,500 = $17,500) does not flag
      $10,094; ensemble proceeds to non-null median.
      So: assert result.median is not None  →  PASS (GREEN on post-fix).

    Uses a snapshot with shares_outstanding = 2_700_000 (NVR-pattern) and
    net_income sized so that EPS_TTM × sector_PE_22 ≈ $10,094, while
    current_price = $3,500 keeps multiples_pe within 5× ($17,500 > $10,094).
    """
    # NI / shares = $458.86 → multiples_pe = 22 × $458.86 ≈ $10,094.
    # current_price = $3,500 → Defense #4 band: [$700, $17,500].
    # $10,094 is inside the band → Defense #4 does NOT flag it.
    # Pre-fix Site-2 ceiling ($10,000) WOULD have fired; post-fix it's gone.
    snap = _make_nvr_snap()
    peer_panels, universe_metrics = _make_nvr_peer_panels(n_peers=10)

    result, risk_flags = compute_fair_price_ensemble(
        ticker="NVR",
        snap=snap,
        sector="Consumer Discretionary",
        sub_industry=None,
        industry=None,
        current_price=3500.0,   # lower than cron price but above $10,094 / 5×
        filing_lag_days_value=30,
        peer_panels=peer_panels,
        universe_metrics=universe_metrics,
        historical_metrics={
            "NVR": {
                "eps_3y_avg": 400.0,
                "avg_3y_roe": 0.35,
                "fcf_5y": [1_000_000_000.0] * 5,
            },
        },
    )

    # Post-fix: the Site-2 gate is gone; median must be non-null.
    assert result.median is not None, (
        "Site-2 ceiling regression: null median on a ticker with "
        "multiples_pe ≈ $10,094 > old $10K ceiling but within 5× of "
        "current_price=$3,500.  Verify ensemble.py:450 per Issue #289."
    )

    # `valuation_output_anomalous` must not come from the ensemble layer.
    assert "valuation_output_anomalous" not in result.valuation_warnings, (
        "Site-2 ceiling regression: 'valuation_output_anomalous' appeared "
        "despite the Site-2 call site being deleted in ensemble.py."
    )

    # multiples_pe is within 5× band → Defense #4 should NOT flag it.
    assert "extreme_multiples_pe_estimate" not in result.valuation_warnings, (
        "Defense #4 false-positive: multiples_pe ≈ $10,094 is within "
        "5× of current_price=$3,500 ($17,500) — it must NOT be flagged."
    )
