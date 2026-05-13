"""Unit tests for compute.scoring.beneish — Beneish M-score (PR 3e.1)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.beneish import (
    BENEISH_THRESHOLD,
    BeneishResult,
    _aqi,
    _depi,
    _dsri,
    _gmi,
    _lvgi,
    _prior_year_value,
    _safe_div,
    _sgai,
    _sgi,
    _tata,
    compute_beneish,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    """Healthy default — clean Beneish profile (M well below -2.22)."""
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 1000.0,
        "net_income": 100.0,
        "cost_of_revenue": 600.0,
        "sga_expense": 150.0,
        "depreciation_and_amortization": 50.0,
        "accounts_receivable": 100.0,
        "current_assets": 400.0,
        "current_liabilities": 200.0,
        "property_plant_equipment": 500.0,
        "total_assets": 1500.0,
        "long_term_debt": 300.0,
        "operating_cash_flow": 110.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _history(rows: list[tuple[str, float, date]] | None = None) -> pd.DataFrame:
    """Build the annual-history DataFrame shape that fetch_fundamentals_history
    emits (`metric`, `value`, `period_end`).

    Default produces a quiet year-over-year snapshot for a 2024-12-31 prior
    fiscal year — matches the _snap default period_end of 2025-12-31.
    """
    if rows is None:
        prior_end = date(2024, 12, 31)
        rows = [
            ("revenue", 900.0, prior_end),
            ("cost_of_revenue", 540.0, prior_end),
            ("sga_expense", 140.0, prior_end),
            ("depreciation_and_amortization", 45.0, prior_end),
            ("accounts_receivable", 95.0, prior_end),
            ("current_assets", 380.0, prior_end),
            ("current_liabilities", 195.0, prior_end),
            ("property_plant_equipment", 480.0, prior_end),
            ("total_assets", 1450.0, prior_end),
            ("long_term_debt", 290.0, prior_end),
        ]
    return pd.DataFrame(
        [{"metric": m, "value": v, "period_end": pe} for m, v, pe in rows]
    )


# -- Section A: _safe_div + _prior_year_value ------------------------------


def test_A1_safe_div_returns_none_on_zero_denominator():
    assert _safe_div(1.0, 0.0) is None


def test_A2_safe_div_returns_none_on_nan():
    assert _safe_div(float("nan"), 1.0) is None
    assert _safe_div(1.0, float("inf")) is None


def test_A3_safe_div_handles_none():
    assert _safe_div(None, 1.0) is None
    assert _safe_div(1.0, None) is None


def test_A4_prior_year_value_returns_none_for_empty_history():
    assert _prior_year_value(None, "revenue", date(2025, 12, 31)) is None
    assert _prior_year_value(pd.DataFrame(), "revenue", date(2025, 12, 31)) is None


def test_A5_prior_year_value_returns_none_without_period():
    hist = _history()
    assert _prior_year_value(hist, "revenue", None) is None


def test_A6_prior_year_value_picks_closest_to_target():
    rows = [
        ("revenue", 800.0, date(2023, 12, 31)),
        ("revenue", 900.0, date(2024, 12, 31)),
        ("revenue", 1000.0, date(2025, 6, 30)),  # within 180-day cutoff window
    ]
    hist = _history(rows)
    # target = 2025-12-31 - 365 = 2024-12-31; cutoff = 2025-12-31 - 180 = 2025-07-04
    # The 2024-12-31 row is on-target and behind cutoff → wins
    assert _prior_year_value(hist, "revenue", date(2025, 12, 31)) == 900.0


def test_A7_prior_year_value_skips_too_recent_rows():
    rows = [
        ("revenue", 999.0, date(2025, 11, 30)),  # within 180-day window → skip
    ]
    hist = _history(rows)
    # No row behind the 180-day cutoff → None
    assert _prior_year_value(hist, "revenue", date(2025, 12, 31)) is None


# -- Section B: per-ratio --------------------------------------------------


def test_B1_dsri_equal_to_one_when_unchanged():
    snap = _snap(revenue=1000.0, accounts_receivable=100.0)
    # prior AR/Rev = 100/1000 = 0.1 = current → ratio = 1.0
    assert _dsri(snap, prior_ar=100.0, prior_rev=1000.0) == 1.0


def test_B2_dsri_high_when_ar_jumps_relative_to_revenue():
    snap = _snap(revenue=1000.0, accounts_receivable=200.0)
    # current = 200/1000 = 0.2; prior = 100/1000 = 0.1 → ratio = 2.0
    assert _dsri(snap, prior_ar=100.0, prior_rev=1000.0) == 2.0


def test_B3_dsri_none_when_revenue_missing():
    snap = _snap(revenue=None)
    assert _dsri(snap, prior_ar=100.0, prior_rev=1000.0) is None


def test_B4_gmi_equal_to_one_when_unchanged():
    snap = _snap(revenue=1000.0, cost_of_revenue=600.0)
    # current GM = 400/1000 = 0.4; prior GM = 0.4 → ratio = 1.0
    assert _gmi(snap, prior_rev=1000.0, prior_cogs=600.0) == 1.0


def test_B5_gmi_high_when_gross_margin_compresses():
    # margin shrunk (suspicious)
    snap = _snap(revenue=1000.0, cost_of_revenue=800.0)
    # current GM = 200/1000 = 0.2; prior GM = 0.4 → GMI = 0.4 / 0.2 = 2.0
    assert _gmi(snap, prior_rev=1000.0, prior_cogs=600.0) == 2.0


def test_B6_aqi_returns_none_without_ppe():
    snap = _snap(property_plant_equipment=None)
    assert _aqi(snap, prior_ca=380.0, prior_ppe=480.0, prior_ta=1450.0) is None


def test_B7_aqi_equal_to_one_when_unchanged():
    snap = _snap(
        current_assets=400.0, property_plant_equipment=500.0, total_assets=1500.0
    )
    # cur = 1 - (400+500)/1500 = 1 - 0.6 = 0.4
    # pri = 1 - (380+480)/1450 = 1 - ~0.593 = 0.407
    # ratio ≈ 0.984
    r = _aqi(snap, prior_ca=380.0, prior_ppe=480.0, prior_ta=1450.0)
    assert r is not None
    assert 0.95 < r < 1.05


def test_B8_sgi_above_one_when_revenue_grows():
    snap = _snap(revenue=1100.0)
    assert _sgi(snap, prior_rev=1000.0) == 1.1


def test_B9_sgi_returns_none_when_prior_revenue_missing():
    snap = _snap(revenue=1100.0)
    assert _sgi(snap, prior_rev=None) is None


def test_B10_depi_returns_none_without_ppe():
    snap = _snap(property_plant_equipment=None)
    assert _depi(snap, prior_da=45.0, prior_ppe=480.0) is None


def test_B11_depi_equal_to_one_when_unchanged():
    snap = _snap(depreciation_and_amortization=50.0, property_plant_equipment=500.0)
    r = _depi(snap, prior_da=50.0, prior_ppe=500.0)
    assert r == 1.0


def test_B12_sgai_above_one_when_sga_grows_faster_than_revenue():
    snap = _snap(revenue=1000.0, sga_expense=200.0)
    # current = 200/1000 = 0.2; prior = 140/900 = 0.1556 → ratio ≈ 1.286
    r = _sgai(snap, prior_sga=140.0, prior_rev=900.0)
    assert r is not None
    assert 1.25 < r < 1.30


def test_B13_tata_high_when_ni_far_exceeds_cfo():
    # large accruals = NI >> CFO
    snap = _snap(net_income=200.0, operating_cash_flow=50.0, total_assets=1000.0)
    assert _tata(snap) == 0.15  # (200-50)/1000


def test_B14_tata_returns_none_on_zero_assets():
    snap = _snap(total_assets=0.0)
    assert _tata(snap) is None


def test_B15_lvgi_above_one_when_leverage_grows():
    snap = _snap(
        long_term_debt=500.0, current_liabilities=300.0, total_assets=1500.0
    )
    # cur = (500+300)/1500 = 0.533; pri = (290+195)/1450 = 0.334 → ratio ≈ 1.595
    r = _lvgi(snap, prior_ltd=290.0, prior_cl=195.0, prior_ta=1450.0)
    assert r is not None
    assert 1.55 < r < 1.65


# -- Section C: end-to-end compute_beneish ---------------------------------


def test_C1_quiet_snapshot_well_below_threshold():
    snap = _snap()
    result = compute_beneish(snap, _history())
    assert isinstance(result, BeneishResult)
    assert result.m_score is not None
    assert result.m_score < BENEISH_THRESHOLD
    assert result.is_high is False
    assert result.missing_ratios == ()


def test_C2_high_signal_snapshot_above_threshold():
    # Deliberately manipulated profile: AR ballooned, GM compressed,
    # SGA grew, leverage spiked, large accruals (NI >> CFO).
    snap = _snap(
        revenue=1500.0,           # SGI = 1.667
        accounts_receivable=400.0, # AR/Rev = 0.267 vs prior 0.106 → DSRI = 2.52
        cost_of_revenue=1200.0,   # GM=0.2 vs 0.4 → GMI = 2.0
        sga_expense=400.0,        # SGA/Rev = 0.267 vs 0.156 → SGAI = 1.72
        net_income=400.0,
        operating_cash_flow=50.0, # TATA = (400-50)/1500 = 0.233
        total_assets=1500.0,
        long_term_debt=500.0,
        current_liabilities=400.0, # LVGI = 0.6 / 0.334 = 1.795
    )
    result = compute_beneish(snap, _history())
    assert result.m_score is not None
    assert result.m_score > BENEISH_THRESHOLD
    assert result.is_high is True


def test_C3_none_score_when_snap_missing():
    result = compute_beneish(None, _history())
    assert result.m_score is None
    assert result.is_high is False
    assert "snap" in result.missing_ratios


def test_C4_none_score_when_history_empty():
    result = compute_beneish(_snap(), None)
    assert result.m_score is None
    assert result.is_high is False
    # All YoY ratios need history → all missing
    assert "DSRI" in result.missing_ratios
    assert "SGI" in result.missing_ratios


def test_C5_none_score_when_ppe_missing_bank_or_reit_pattern():
    # Banks/REITs/asset-light filers often report no PPE → AQI + DEPI None
    snap = _snap(property_plant_equipment=None)
    result = compute_beneish(snap, _history())
    assert result.m_score is None
    assert "AQI" in result.missing_ratios
    assert "DEPI" in result.missing_ratios


def test_C6_threshold_constant_matches_beneish_1999():
    # Beneish 1999 FAJ original cutoff
    assert BENEISH_THRESHOLD == -2.22


def test_C7_intercept_and_coefficients_round_trip():
    # Pin the formula constants — regression guard against an accidental
    # coefficient flip that would silently shift the entire score distribution.
    from compute.scoring.beneish import (
        _AQI_COEF,
        _DEPI_COEF,
        _DSRI_COEF,
        _GMI_COEF,
        _INTERCEPT,
        _LVGI_COEF,
        _SGAI_COEF,
        _SGI_COEF,
        _TATA_COEF,
    )
    assert _INTERCEPT == -4.84
    assert _DSRI_COEF == 0.92
    assert _GMI_COEF == 0.528
    assert _AQI_COEF == 0.404
    assert _SGI_COEF == 0.892
    assert _DEPI_COEF == 0.115
    assert _SGAI_COEF == -0.172
    assert _TATA_COEF == 4.679
    assert _LVGI_COEF == -0.327
