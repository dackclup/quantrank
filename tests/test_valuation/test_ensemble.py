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
        "methods", "median", "max", "low", "high", "mos_pct", "valuation_warnings"
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
