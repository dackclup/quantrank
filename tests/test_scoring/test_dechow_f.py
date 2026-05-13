"""Unit tests for compute.scoring.dechow_f — Dechow F-score (PR 3e.2)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.dechow_f import (
    DECHOW_HIGH_THRESHOLD,
    DechowResult,
    _avg_ta,
    _delta_cash_sales,
    _delta_inv,
    _delta_recv,
    _delta_roa,
    _issuance_dummy,
    _prior_year_value,
    _rsst_simplified,
    _safe_div,
    _soft_assets,
    compute_dechow_f,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    """Healthy default — clean Dechow profile (F well below 2.45)."""
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 1000.0,
        "net_income": 100.0,
        "operating_cash_flow": 110.0,
        "accounts_receivable": 100.0,
        "inventory": 80.0,
        "cash": 100.0,
        "property_plant_equipment": 500.0,
        "total_assets": 1500.0,
        "shares_outstanding": 1_000_000.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _history(rows: list[tuple[str, float, date]] | None = None) -> pd.DataFrame:
    if rows is None:
        prior_end = date(2024, 12, 31)
        rows = [
            ("total_assets", 1450.0, prior_end),
            ("accounts_receivable", 95.0, prior_end),
            ("inventory", 78.0, prior_end),
            ("revenue", 950.0, prior_end),
            ("net_income", 95.0, prior_end),
            ("shares_outstanding", 1_000_000.0, prior_end),
        ]
    return pd.DataFrame(
        [{"metric": m, "value": v, "period_end": pe} for m, v, pe in rows]
    )


# -- Section A: helpers ----------------------------------------------------


def test_A1_safe_div_zero_denom():
    assert _safe_div(1.0, 0.0) is None


def test_A2_safe_div_none_inputs():
    assert _safe_div(None, 1.0) is None
    assert _safe_div(1.0, None) is None


def test_A3_safe_div_nan():
    assert _safe_div(float("nan"), 1.0) is None


def test_A4_prior_year_value_empty_history():
    assert _prior_year_value(None, "revenue", date(2025, 12, 31)) is None
    assert _prior_year_value(pd.DataFrame(), "revenue", date(2025, 12, 31)) is None


def test_A5_prior_year_value_missing_period():
    assert _prior_year_value(_history(), "revenue", None) is None


def test_A6_prior_year_value_picks_closest():
    rows = [
        ("revenue", 800.0, date(2023, 12, 31)),
        ("revenue", 950.0, date(2024, 12, 31)),
    ]
    hist = _history(rows)
    assert _prior_year_value(hist, "revenue", date(2025, 12, 31)) == 950.0


def test_A7_avg_ta():
    snap = _snap(total_assets=1500.0)
    assert _avg_ta(snap, prior_ta=1450.0) == 1475.0


def test_A8_avg_ta_none_when_negative_avg():
    snap = _snap(total_assets=-100.0)
    assert _avg_ta(snap, prior_ta=50.0) is None


# -- Section B: per-variable -----------------------------------------------


def test_B1_rsst_simplified_zero_when_ni_equals_cfo():
    snap = _snap(net_income=100.0, operating_cash_flow=100.0)
    assert _rsst_simplified(snap, avg_ta=1500.0) == 0.0


def test_B2_rsst_simplified_high_when_ni_far_exceeds_cfo():
    snap = _snap(net_income=300.0, operating_cash_flow=50.0)
    # (300 - 50) / 1500 = 0.1667
    r = _rsst_simplified(snap, avg_ta=1500.0)
    assert r is not None
    assert 0.16 < r < 0.17


def test_B3_delta_recv_zero_when_ar_unchanged():
    snap = _snap(accounts_receivable=100.0)
    assert _delta_recv(snap, prior_ar=100.0, avg_ta=1500.0) == 0.0


def test_B4_delta_recv_positive_when_ar_grows():
    snap = _snap(accounts_receivable=150.0)
    # (150 - 100) / 1500 = 0.0333
    r = _delta_recv(snap, prior_ar=100.0, avg_ta=1500.0)
    assert r is not None
    assert 0.030 < r < 0.040


def test_B5_delta_inv_positive_when_inventory_grows():
    snap = _snap(inventory=150.0)
    r = _delta_inv(snap, prior_inv=80.0, avg_ta=1500.0)
    assert r is not None
    assert 0.04 < r < 0.05


def test_B6_soft_assets_returns_none_without_ppe():
    snap = _snap(property_plant_equipment=None)
    assert _soft_assets(snap) is None


def test_B7_soft_assets_lower_when_more_ppe_and_cash():
    snap = _snap(
        total_assets=1500.0, property_plant_equipment=900.0, cash=300.0
    )
    # (1500 - 900 - 300) / 1500 = 0.2 → low softness (asset-heavy)
    r = _soft_assets(snap)
    assert r is not None
    assert abs(r - 0.2) < 0.001


def test_B8_soft_assets_higher_when_intangible_heavy():
    snap = _snap(
        total_assets=1500.0, property_plant_equipment=100.0, cash=50.0
    )
    # (1500 - 100 - 50) / 1500 = 0.9 → high softness (asset-light)
    r = _soft_assets(snap)
    assert r is not None
    assert abs(r - 0.9) < 0.001


def test_B9_delta_cash_sales_positive_when_revenue_grows():
    snap = _snap(revenue=1100.0)
    # (1100 - 1000) / 1000 = 0.10
    assert _delta_cash_sales(snap, prior_rev=1000.0) == 0.1


def test_B10_delta_cash_sales_none_on_zero_prior():
    snap = _snap(revenue=1000.0)
    assert _delta_cash_sales(snap, prior_rev=0.0) is None


def test_B11_delta_roa_positive_when_profitability_improves():
    snap = _snap(net_income=200.0, total_assets=1500.0)
    # 200/1500 - 100/1500 = 0.0667
    r = _delta_roa(snap, prior_ni=100.0, prior_ta=1500.0)
    assert r is not None
    assert 0.06 < r < 0.07


def test_B12_delta_roa_negative_when_profitability_declines():
    snap = _snap(net_income=50.0, total_assets=1500.0)
    r = _delta_roa(snap, prior_ni=100.0, prior_ta=1500.0)
    assert r is not None
    assert r < 0


def test_B13_issuance_dummy_one_when_shares_grow_more_than_1pct():
    snap = _snap(shares_outstanding=1_020_000.0)  # +2%
    assert _issuance_dummy(snap, prior_shares=1_000_000.0) == 1.0


def test_B14_issuance_dummy_zero_when_shares_stable():
    snap = _snap(shares_outstanding=1_005_000.0)  # +0.5% < 1% threshold
    assert _issuance_dummy(snap, prior_shares=1_000_000.0) == 0.0


def test_B15_issuance_dummy_zero_when_shares_buyback():
    snap = _snap(shares_outstanding=950_000.0)  # -5%
    assert _issuance_dummy(snap, prior_shares=1_000_000.0) == 0.0


# -- Section C: end-to-end -------------------------------------------------


def test_C1_quiet_snapshot_below_threshold():
    result = compute_dechow_f(_snap(), _history())
    assert isinstance(result, DechowResult)
    assert result.f_score is not None
    assert result.f_score < DECHOW_HIGH_THRESHOLD
    assert result.is_high is False
    assert result.missing_inputs == ()


def test_C2_high_signal_snapshot_above_threshold():
    # Deliberately manipulated profile:
    # - large accruals (NI >> CFO)
    # - AR ballooning
    # - inventory ballooning
    # - high soft-assets ratio (intangible-heavy)
    # - revenue acceleration
    # - share issuance
    snap = _snap(
        net_income=300.0,
        operating_cash_flow=50.0,
        accounts_receivable=300.0,
        inventory=200.0,
        revenue=1400.0,
        cash=50.0,
        property_plant_equipment=100.0,
        shares_outstanding=1_050_000.0,
    )
    result = compute_dechow_f(snap, _history())
    assert result.f_score is not None
    assert result.f_score > DECHOW_HIGH_THRESHOLD
    assert result.is_high is True


def test_C3_none_score_when_snap_missing():
    result = compute_dechow_f(None, _history())
    assert result.f_score is None
    assert "snap" in result.missing_inputs


def test_C4_none_score_when_history_empty():
    result = compute_dechow_f(_snap(), None)
    assert result.f_score is None
    # All YoY-dependent variables → all missing
    assert "RSST" in result.missing_inputs
    assert "Δrecv" in result.missing_inputs


def test_C5_none_score_when_ppe_missing_asset_light_pattern():
    # Banks / REITs / asset-light filers without PPE → soft_assets None
    snap = _snap(property_plant_equipment=None)
    result = compute_dechow_f(snap, _history())
    assert result.f_score is None
    assert "soft_assets" in result.missing_inputs


def test_C6_threshold_constant_matches_dechow_2011():
    assert DECHOW_HIGH_THRESHOLD == 2.45


def test_C7_intercept_and_coefficients_round_trip():
    from compute.scoring.dechow_f import (
        _DCASH_COEF,
        _DINV_COEF,
        _DRECV_COEF,
        _DROA_COEF,
        _INTERCEPT,
        _ISSUE_COEF,
        _RSST_COEF,
        _SOFT_COEF,
    )
    assert _INTERCEPT == -7.893
    assert _RSST_COEF == 0.790
    assert _DRECV_COEF == 2.518
    assert _DINV_COEF == 1.191
    assert _SOFT_COEF == 1.979
    assert _DCASH_COEF == 0.171
    assert _DROA_COEF == -0.932
    assert _ISSUE_COEF == 1.029


def test_C8_baseline_is_dechow_2011_unconditional_rate():
    from compute.scoring.dechow_f import _BASELINE
    # 0.37% AAER misstatement base rate in Dechow's training sample
    assert _BASELINE == 0.0037
