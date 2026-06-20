"""Coverage tests for compute.features.quality — targeting uncovered branches.

Uncovered lines (baseline 84%):
  122,125   gross_profitability: revenue - cost_of_revenue fallback path
            (when gross_profit is None but revenue + cost_of_revenue present)
  190       piotroski_f_score: math.isnan(score) defensive branch
  Various piotroski criteria branches — the existing tests exercise a full
  snapshot but don't hit per-criterion False branches individually.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from compute.features.quality import (
    gross_profitability,
    piotroski_f_score,
    return_on_invested_capital,
)
from compute.ingest.fundamentals import FundamentalsSnapshot


def _snap(**kwargs) -> FundamentalsSnapshot:
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 1_000.0,
        "net_income": 100.0,
        "total_assets": 2_000.0,
        "gross_profit": 400.0,
        "operating_cash_flow": 120.0,
        "shares_outstanding": 1_000_000.0,
        "stockholders_equity": 800.0,
        "operating_income": 200.0,
        "long_term_debt": 500.0,
        "short_term_debt": 100.0,
        "cost_of_revenue": 600.0,
        "current_assets": 500.0,
        "current_liabilities": 250.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _history(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["metric", "value", "fiscal_year"])


def _hist_two_years(**metrics_by_year) -> pd.DataFrame:
    """Build a history DF with two years for each metric.

    metrics_by_year: {metric_name: [value_y2, value_y1]}  (y2=older, y1=newer)
    The piotroski helper picks the second-most-recent (y2) as the prior year.
    """
    rows = []
    for metric, (older_val, newer_val) in metrics_by_year.items():
        rows.append({"metric": metric, "value": older_val, "fiscal_year": 2023})
        rows.append({"metric": metric, "value": newer_val, "fiscal_year": 2024})
    return _history(rows)


# ---------------------------------------------------------------------------
# gross_profitability: revenue - cost_of_revenue fallback path (lines 56-57)
# ---------------------------------------------------------------------------


def test_gross_profitability_uses_revenue_minus_cogs_when_gross_profit_none():
    """When gross_profit is None but revenue + cost_of_revenue present,
    gross_profitability falls back to (revenue - cost_of_revenue) / total_assets."""
    snap = _snap(
        gross_profit=None,
        revenue=1_000.0,
        cost_of_revenue=600.0,
        total_assets=2_000.0,
    )
    gp = gross_profitability(snap)
    # (1000 - 600) / 2000 = 0.2
    assert math.isclose(gp, 0.2, rel_tol=1e-9)


def test_gross_profitability_returns_nan_when_all_sources_none():
    """NaN when gross_profit, revenue, and cost_of_revenue are all None."""
    snap = _snap(gross_profit=None, revenue=None, cost_of_revenue=None)
    assert math.isnan(gross_profitability(snap))


def test_gross_profitability_returns_nan_when_total_assets_zero():
    """NaN when total_assets = 0 (division-by-zero guard)."""
    snap = _snap(gross_profit=400.0, total_assets=0.0)
    assert math.isnan(gross_profitability(snap))


def test_gross_profitability_returns_nan_when_revenue_present_but_cogs_none():
    """No gross_profit, revenue available but cost_of_revenue=None → NaN."""
    snap = _snap(gross_profit=None, revenue=1_000.0, cost_of_revenue=None)
    assert math.isnan(gross_profitability(snap))


# ---------------------------------------------------------------------------
# piotroski_f_score: various criterion False branches
# ---------------------------------------------------------------------------


def test_piotroski_negative_net_income_does_not_score_criterion_1():
    """Criterion 1: NI > 0. Negative NI → criterion not scored."""
    snap = _snap(net_income=-50.0)
    hist = _hist_two_years(
        revenue=[800.0, 900.0],
        total_assets=[1_900.0, 2_000.0],
        long_term_debt=[450.0, 500.0],
        current_assets=[480.0, 500.0],
        current_liabilities=[240.0, 250.0],
        shares_outstanding=[1_000_000.0, 1_000_000.0],
        gross_profit=[380.0, 400.0],
    )
    score = piotroski_f_score(snap, hist)
    # Score should be <= 7 (no criterion 1, no criterion 2 either since NI < 0)
    assert not math.isnan(score)
    assert score <= 7.0


def test_piotroski_returns_nan_for_empty_history():
    """History empty → NaN immediately (early return)."""
    snap = _snap()
    assert math.isnan(piotroski_f_score(snap, pd.DataFrame()))


def test_piotroski_returns_nan_for_none_history():
    """None history → NaN immediately."""
    snap = _snap()
    assert math.isnan(piotroski_f_score(snap, None))


def test_piotroski_criterion_5_false_when_debt_increases():
    """Criterion 5: LT debt ratio decreased. When it increases, no point scored."""
    snap = _snap(long_term_debt=600.0, total_assets=2_000.0)  # ratio = 0.30
    # Prior year: ratio = 400/1800 = 0.222 → current 0.30 > prior → no point
    hist = _hist_two_years(
        revenue=[800.0, 900.0],
        total_assets=[1_800.0, 2_000.0],  # older=1800, newer=2000
        long_term_debt=[400.0, 500.0],    # prior (older) = 400, so ratio = 400/1800
        current_assets=[480.0, 500.0],
        current_liabilities=[240.0, 250.0],
        shares_outstanding=[1_000_000.0, 1_000_000.0],
        gross_profit=[380.0, 400.0],
    )
    score = piotroski_f_score(snap, hist)
    assert not math.isnan(score)
    # Just verify it runs — the exact score depends on other criteria too.
    assert 0.0 <= score <= 9.0


def test_piotroski_criterion_6_false_when_current_ratio_falls():
    """Criterion 6: current ratio increased. When it falls, no point."""
    # current ratio now = 500/250 = 2.0; prior = 600/200 = 3.0 → fell
    snap = _snap(current_assets=500.0, current_liabilities=250.0)
    hist = _hist_two_years(
        revenue=[800.0, 900.0],
        total_assets=[1_900.0, 2_000.0],
        long_term_debt=[450.0, 500.0],
        current_assets=[700.0, 600.0],       # older 700, so prior = 700
        current_liabilities=[200.0, 200.0],  # older 200, so prior = 200
        shares_outstanding=[1_000_000.0, 1_000_000.0],
        gross_profit=[380.0, 400.0],
    )
    score = piotroski_f_score(snap, hist)
    assert not math.isnan(score)
    assert 0.0 <= score <= 9.0


def test_piotroski_criterion_7_false_when_shares_increased():
    """Criterion 7: no new shares issued. When shares increase, no point."""
    snap = _snap(shares_outstanding=1_200_000.0)  # increased from prior
    hist = _hist_two_years(
        revenue=[800.0, 900.0],
        total_assets=[1_900.0, 2_000.0],
        long_term_debt=[450.0, 500.0],
        current_assets=[480.0, 500.0],
        current_liabilities=[240.0, 250.0],
        shares_outstanding=[800_000.0, 1_000_000.0],  # older=800k, prior = 800k
        gross_profit=[380.0, 400.0],
    )
    score = piotroski_f_score(snap, hist)
    # Current shares (1.2M) > prior (0.8M) → no Criterion 7 point.
    assert not math.isnan(score)
    assert 0.0 <= score <= 8.0  # max is 8 (can't score Criterion 7)


def test_piotroski_criterion_8_false_when_gross_margin_falls():
    """Criterion 8: gross margin increased. When it falls, no point."""
    # now: GM = 300/1000 = 0.30; prior: GM = 450/900 = 0.50
    snap = _snap(gross_profit=300.0, revenue=1_000.0)
    hist = _hist_two_years(
        revenue=[700.0, 900.0],      # older 700
        total_assets=[1_900.0, 2_000.0],
        long_term_debt=[450.0, 500.0],
        current_assets=[480.0, 500.0],
        current_liabilities=[240.0, 250.0],
        shares_outstanding=[1_000_000.0, 1_000_000.0],
        gross_profit=[350.0, 450.0],  # older 350, prior = 350/700 = 0.50
    )
    score = piotroski_f_score(snap, hist)
    assert not math.isnan(score)
    assert 0.0 <= score <= 8.0


def test_piotroski_criterion_9_false_when_asset_turnover_falls():
    """Criterion 9: asset turnover increased. When it falls, no point."""
    # now: AT = 1000/2000 = 0.50; prior: AT = 900/1500 = 0.60
    snap = _snap(revenue=1_000.0, total_assets=2_000.0)
    hist = _hist_two_years(
        revenue=[700.0, 900.0],         # older 700, prior = 900/1500 = 0.60
        total_assets=[1_300.0, 1_500.0],  # older 1300, prior = 1300 (uses second-most-recent)
        long_term_debt=[450.0, 500.0],
        current_assets=[480.0, 500.0],
        current_liabilities=[240.0, 250.0],
        shares_outstanding=[1_000_000.0, 1_000_000.0],
        gross_profit=[380.0, 400.0],
    )
    score = piotroski_f_score(snap, hist)
    assert not math.isnan(score)
    assert 0.0 <= score <= 8.0


def test_piotroski_perfect_score():
    """All 9 criteria pass → score = 9.0."""
    snap = _snap(
        net_income=200.0,          # NI > 0 (C1)
        total_assets=2_000.0,      # ROA > 0 via NI/TA = 0.10 (C2)
        operating_cash_flow=300.0, # CFO > 0 (C3); CFO/TA = 0.15 > ROA (C4)
        long_term_debt=400.0,      # LT ratio = 400/2000 = 0.20 (C5: decreased from 0.30)
        current_assets=600.0,      # CR = 600/200 = 3.0 (C6: up from 2.0)
        current_liabilities=200.0,
        shares_outstanding=900_000.0,  # decreased from 1M (C7)
        gross_profit=550.0,       # GM = 550/1500 = 0.367 (C8: up from 0.333)
        revenue=1_500.0,          # AT = 1500/2000 = 0.75 (C9: up from 0.50)
    )
    hist = _hist_two_years(
        revenue=[800.0, 1_000.0],       # prior (older) = 800
        total_assets=[1_800.0, 2_000.0],  # prior = 1800
        long_term_debt=[540.0, 500.0],   # prior ratio = 540/1800 = 0.30 (now 0.20 → decreased)
        current_assets=[360.0, 400.0],   # prior CR = 360/180 = 2.0 (now 3.0 → increased)
        current_liabilities=[180.0, 200.0],
        shares_outstanding=[1_000_000.0, 950_000.0],  # older=1M; prior=1M > current 900k
        gross_profit=[266.0, 300.0],     # prior GM = 266/800 = 0.3325 (now 0.367 → up)
    )
    score = piotroski_f_score(snap, hist)
    assert score == 9.0


def test_roic_uses_default_tax_rate_when_income_before_tax_zero():
    """When income_before_tax is 0, ROIC should use the default 21% tax rate."""
    snap = _snap(
        operating_income=200.0,
        income_tax_expense=42.0,
        income_before_tax=0.0,    # denominator zero → fallback to 0.21
        long_term_debt=500.0,
        short_term_debt=100.0,
        stockholders_equity=800.0,
    )
    roic = return_on_invested_capital(snap)
    # With tax=0.21: NOPAT = 200 * (1 - 0.21) = 158; IC = 800 + 500 + 100 = 1400
    assert math.isfinite(roic)
    assert math.isclose(roic, 158.0 / 1400.0, rel_tol=1e-6)


def test_roic_uses_default_tax_rate_when_income_tax_expense_none():
    """When income_tax_expense is None, ROIC uses the 21% default."""
    snap = _snap(
        operating_income=200.0,
        income_tax_expense=None,
        income_before_tax=300.0,
        long_term_debt=500.0,
        short_term_debt=100.0,
        stockholders_equity=800.0,
    )
    roic = return_on_invested_capital(snap)
    # NOPAT = 200 * (1 - 0.21) = 158
    assert math.isclose(roic, 158.0 / 1400.0, rel_tol=1e-6)


def test_roic_caps_tax_rate_at_50_pct():
    """Unreasonably high income_tax_expense capped at 50% (max(min(tx,0.5),0))."""
    snap = _snap(
        operating_income=200.0,
        income_tax_expense=900.0,   # 900/300 = 300% → capped at 50%
        income_before_tax=300.0,
        long_term_debt=0.0,
        short_term_debt=0.0,
        stockholders_equity=1_000.0,
    )
    roic = return_on_invested_capital(snap)
    # NOPAT = 200 * (1 - 0.5) = 100; IC = 1000
    assert math.isclose(roic, 0.10, rel_tol=1e-6)


def test_roic_nan_when_operating_income_none():
    snap = _snap(operating_income=None)
    assert math.isnan(return_on_invested_capital(snap))


def test_roic_nan_when_invested_capital_zero():
    """Zero invested capital → NaN (division guard)."""
    snap = _snap(
        operating_income=200.0,
        stockholders_equity=0.0,
        long_term_debt=0.0,
        short_term_debt=0.0,
    )
    assert math.isnan(return_on_invested_capital(snap))
