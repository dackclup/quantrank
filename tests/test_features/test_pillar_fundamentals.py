"""Tests for the fundamental pillar feature modules: profitability, health,
quality, value, growth.

All tests use synthetic ``FundamentalsSnapshot`` instances so they're
deterministic and offline.
"""

from __future__ import annotations

import math

import pandas as pd

from compute.features import growth, health, profitability, quality, value
from compute.ingest.fundamentals import FundamentalsSnapshot


def _snap(**overrides) -> FundamentalsSnapshot:
    base = dict(
        ticker="TEST",
        cik="0000001234",
        revenue=100_000.0,
        net_income=10_000.0,
        total_assets=200_000.0,
        total_liabilities=80_000.0,
        stockholders_equity=120_000.0,
        cash=20_000.0,
        operating_cash_flow=15_000.0,
        capex=3_000.0,
        free_cash_flow=12_000.0,
        eps_basic=2.0,
        eps_diluted=2.0,
        shares_outstanding=10_000.0,
        gross_profit=40_000.0,
        operating_income=20_000.0,
        cost_of_revenue=60_000.0,
        research_and_development=5_000.0,
        sga_expense=10_000.0,
        depreciation_and_amortization=4_000.0,
        interest_expense=1_000.0,
        income_tax_expense=2_000.0,
        income_before_tax=12_000.0,
        dividends_paid=2_000.0,
        current_assets=60_000.0,
        current_liabilities=30_000.0,
        inventory=10_000.0,
        accounts_receivable=12_000.0,
        accounts_payable=8_000.0,
        long_term_debt=40_000.0,
        short_term_debt=5_000.0,
        retained_earnings=50_000.0,
        ebitda=24_000.0,
    )
    base.update(overrides)
    return FundamentalsSnapshot(**base)


# -- Profitability ---------------------------------------------------------

def test_gross_margin_uses_gross_profit():
    snap = _snap()
    assert math.isclose(profitability.gross_margin(snap), 0.40)


def test_operating_margin():
    snap = _snap()
    assert math.isclose(profitability.operating_margin(snap), 0.20)


def test_net_margin():
    snap = _snap()
    assert math.isclose(profitability.net_margin(snap), 0.10)


def test_roa():
    assert math.isclose(profitability.return_on_assets(_snap()), 0.05)


def test_asset_turnover():
    assert math.isclose(profitability.asset_turnover(_snap()), 0.5)


def test_cash_conversion_cycle_components():
    """DSO + DIO − DPO with our synthetic numbers:
        DSO = 12000 / (100000 / 365) ≈ 43.8
        DIO = 10000 / (60000 / 365)  ≈ 60.83
        DPO =  8000 / (60000 / 365)  ≈ 48.67
        CCC ≈ 43.8 + 60.83 − 48.67 ≈ 55.97
    """
    val = profitability.cash_conversion_cycle(_snap())
    assert 50 < val < 60


def test_gross_profitability_novy_marx():
    snap = _snap()
    # 40000 / 200000 = 0.2
    assert math.isclose(profitability.gross_profitability(snap), 0.2)


# -- Health ----------------------------------------------------------------

def test_current_ratio():
    assert math.isclose(health.current_ratio(_snap()), 2.0)


def test_quick_ratio_excludes_inventory():
    snap = _snap()
    # (60000 - 10000) / 30000 ≈ 1.667
    assert math.isclose(health.quick_ratio(snap), 50_000 / 30_000)


def test_debt_to_equity():
    snap = _snap()
    # (40000 + 5000) / 120000 = 0.375
    assert math.isclose(health.debt_to_equity(snap), 0.375)


def test_interest_coverage():
    # EBIT (operating_income) / interest_expense = 20000 / 1000 = 20
    assert math.isclose(health.interest_coverage(_snap()), 20.0)


def test_debt_to_ebitda():
    # 45000 / 24000 = 1.875
    assert math.isclose(health.debt_to_ebitda(_snap()), 45000 / 24000)


def test_altman_z_double_prime_safe_zone():
    """Healthy synthetic balance sheet should land in safe zone (>2.9)."""
    z = health.altman_z_double_prime(_snap())
    assert z > 2.9


def test_altman_z_returns_nan_when_inputs_missing():
    snap = _snap(retained_earnings=None)
    assert math.isnan(health.altman_z_double_prime(snap))


# -- Quality ---------------------------------------------------------------

def test_roe():
    # 10000 / 120000 ≈ 0.0833
    assert math.isclose(quality.return_on_equity(_snap()), 10_000 / 120_000)


def test_roic_basic():
    """NOPAT = OI × (1 − tax_rate); IC = equity + debt."""
    snap = _snap()
    # tax_rate = 2000 / 12000 = 0.1667 → NOPAT = 20000 × 0.8333 ≈ 16666.67
    # IC = 120000 + 45000 = 165000
    # ROIC ≈ 16666.67 / 165000 ≈ 0.10101
    val = quality.return_on_invested_capital(snap)
    assert 0.09 < val < 0.12


def test_quality_gross_profitability():
    assert math.isclose(quality.gross_profitability(_snap()), 0.2)


def test_piotroski_returns_nan_without_history():
    assert math.isnan(quality.piotroski_f_score(_snap()))


def test_piotroski_with_synthetic_history():
    """Build a minimal 2-year history showing improvement on every dimension."""
    snap = _snap()
    history = pd.DataFrame(
        [
            {"fiscal_year": 2023, "metric": "revenue", "value": 80_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "revenue", "value": 100_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "total_assets", "value": 220_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "total_assets", "value": 200_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "long_term_debt", "value": 50_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "long_term_debt", "value": 40_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "current_assets", "value": 50_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "current_assets", "value": 60_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "current_liabilities", "value": 35_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "current_liabilities", "value": 30_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "shares_outstanding", "value": 10_500.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "shares_outstanding", "value": 10_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "gross_profit", "value": 25_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "gross_profit", "value": 40_000.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
        ]
    )
    score = quality.piotroski_f_score(snap, history=history)
    # All 9 criteria should fire with these constructed inputs.
    assert score == 9


# -- Value -----------------------------------------------------------------

def test_pe_ratio():
    # Audit #6: pe_ratio now derives TTM EPS from NI_TTM / shares_outstanding
    # instead of the single-period snap.eps_diluted. Fixture: NI=10k, shares=10k
    # → TTM EPS = 1.0; price=40 → PE = 40.
    assert math.isclose(value.pe_ratio(_snap(), current_price=40.0), 40.0)


def test_pe_returns_nan_for_negative_earnings():
    # Negative NI → NaN PE (the eps_diluted field is now ignored).
    snap = _snap(net_income=-5_000.0)
    assert math.isnan(value.pe_ratio(snap, current_price=40.0))


def test_pe_returns_nan_when_inputs_missing():
    # NI=None or shares=None or shares<=0 → NaN.
    assert math.isnan(value.pe_ratio(_snap(net_income=None), current_price=40.0))
    assert math.isnan(value.pe_ratio(_snap(shares_outstanding=None), current_price=40.0))
    assert math.isnan(value.pe_ratio(_snap(shares_outstanding=0), current_price=40.0))


def test_pb_ratio():
    snap = _snap()
    # BVPS = 120000 / 10000 = 12; P/B = 24 / 12 = 2.0
    assert math.isclose(value.pb_ratio(snap, current_price=24.0), 2.0)


def test_market_cap_and_ps():
    snap = _snap()
    # cap = 40 × 10000 = 400000; P/S = 400000 / 100000 = 4.0
    assert math.isclose(value.market_cap(snap, 40.0), 400_000.0)
    assert math.isclose(value.ps_ratio(snap, current_price=40.0), 4.0)


def test_enterprise_value():
    snap = _snap()
    # EV = 400000 + 45000 − 20000 = 425000
    assert math.isclose(value.enterprise_value(snap, 40.0), 425_000.0)


def test_ev_to_ebitda():
    # 425000 / 24000 ≈ 17.708
    assert math.isclose(value.ev_to_ebitda(_snap(), 40.0), 425_000 / 24_000)


def test_ev_to_fcf():
    # 425000 / 12000 ≈ 35.4
    assert math.isclose(value.ev_to_fcf(_snap(), 40.0), 425_000 / 12_000)


def test_earnings_yield_greenblatt():
    # OI / EV = 20000 / 425000 ≈ 0.047
    assert math.isclose(
        value.earnings_yield_greenblatt(_snap(), 40.0), 20_000 / 425_000
    )


def test_graham_number():
    # Audit #6: graham_number now derives TTM EPS from NI_TTM / shares.
    # Fixture: NI=10k, shares=10k → TTM EPS=1.0; equity=120k, shares=10k → BVPS=12.
    # √(22.5 × 1.0 × 12) = √270 ≈ 16.43.
    snap = _snap()
    g = value.graham_number(snap)
    assert 16 < g < 17


def test_tobins_q():
    # Q = (cap + liabilities) / TA = (400000 + 80000) / 200000 = 2.4
    assert math.isclose(value.tobins_q(_snap(), 40.0), 2.4)


# -- Growth ----------------------------------------------------------------

def _growth_history() -> pd.DataFrame:
    """6-year revenue and EPS series with steady 10% growth."""
    rows = []
    for i, fy in enumerate(range(2019, 2025)):
        rev = 100.0 * (1.10 ** i)
        eps = 1.0 * (1.10 ** i)
        rows.extend(
            [
                {"fiscal_year": fy, "metric": "revenue", "value": rev,
                 "period_end": None, "filing_date": None, "form_type": "10-K"},
                {"fiscal_year": fy, "metric": "eps_diluted", "value": eps,
                 "period_end": None, "filing_date": None, "form_type": "10-K"},
                {"fiscal_year": fy, "metric": "operating_cash_flow", "value": rev * 0.2,
                 "period_end": None, "filing_date": None, "form_type": "10-K"},
                {"fiscal_year": fy, "metric": "capex", "value": rev * 0.05,
                 "period_end": None, "filing_date": None, "form_type": "10-K"},
            ]
        )
    return pd.DataFrame(rows)


def test_revenue_cagr_3y_matches_synthetic_growth():
    h = _growth_history()
    # CAGR over 3 years of 10%/year compounding = 0.10
    val = growth.revenue_cagr_3y(h)
    assert math.isclose(val, 0.10, rel_tol=1e-9, abs_tol=1e-9)


def test_revenue_cagr_5y_matches():
    h = _growth_history()
    assert math.isclose(growth.revenue_cagr_5y(h), 0.10, rel_tol=1e-9, abs_tol=1e-9)


def test_eps_cagr_3y():
    assert math.isclose(growth.eps_cagr_3y(_growth_history()), 0.10, rel_tol=1e-9, abs_tol=1e-9)


def test_fcf_cagr_3y():
    """FCF = CFO − CapEx with a 0.15 × revenue underlying → grows 10% per year."""
    assert math.isclose(growth.fcf_cagr_3y(_growth_history()), 0.10, rel_tol=1e-9, abs_tol=1e-9)


def test_sustainable_growth_rate():
    snap = _snap()
    # ROE = 10000 / 120000 = 0.0833; payout = 2000 / 10000 = 0.20
    # SGR = 0.0833 × 0.80 = 0.0667
    val = growth.sustainable_growth_rate(snap)
    assert math.isclose(val, (10_000 / 120_000) * 0.80)


def test_growth_returns_nan_when_history_too_short():
    short = pd.DataFrame(
        [
            {"fiscal_year": 2023, "metric": "revenue", "value": 100.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2024, "metric": "revenue", "value": 110.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
        ]
    )
    assert math.isnan(growth.revenue_cagr_3y(short))


def test_growth_returns_nan_when_history_none():
    assert math.isnan(growth.revenue_cagr_3y(None))


def test_growth_returns_nan_when_endpoint_negative():
    history = pd.DataFrame(
        [
            {"fiscal_year": 2020, "metric": "revenue", "value": 100.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2021, "metric": "revenue", "value": 90.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2022, "metric": "revenue", "value": 80.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
            {"fiscal_year": 2023, "metric": "revenue", "value": -10.0,
             "period_end": None, "filing_date": None, "form_type": "10-K"},
        ]
    )
    assert math.isnan(growth.revenue_cagr_3y(history))


# -- Momentum extensions --------------------------------------------------

def test_momentum_helpers_return_nan_for_short_input():
    """Smoke test that the new momentum helpers degrade cleanly."""
    from compute.features import momentum
    df = pd.DataFrame()
    assert math.isnan(momentum.momentum_6_1(df))
    assert math.isnan(momentum.momentum_3_1(df))
    assert math.isnan(momentum.distance_from_52w_high(df))
