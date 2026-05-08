"""Quality metrics — knowledge doc §6.1 (Piotroski), §8.7 (MSCI 3-desc),
§8.10 (Gross Profitability), and §11.

Most quality metrics use the latest ``FundamentalsSnapshot``. Piotroski needs
year-over-year comparisons → consumes the annual-history DataFrame from
``compute.ingest.fundamentals.fetch_fundamentals_history``.
"""

from __future__ import annotations

import math

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot


def _safe_div(num: float | None, den: float | None) -> float:
    if num is None or den is None or den == 0:
        return float("nan")
    return float(num) / float(den)


def return_on_equity(snap: FundamentalsSnapshot) -> float:
    return _safe_div(snap.net_income, snap.stockholders_equity)


def return_on_invested_capital(snap: FundamentalsSnapshot) -> float:
    """ROIC = NOPAT / Invested Capital (~equity + total debt).

    NOPAT ≈ operating_income × (1 − tax rate). When tax rate is unavailable,
    fall back to operating_income directly (still a reasonable proxy).
    """
    if snap.operating_income is None:
        return float("nan")
    tax_rate = (
        snap.income_tax_expense / snap.income_before_tax
        if snap.income_tax_expense is not None
        and snap.income_before_tax not in (None, 0)
        else 0.21  # default U.S. corporate rate
    )
    nopat = snap.operating_income * (1 - max(min(tax_rate, 0.5), 0.0))
    debt = (snap.long_term_debt or 0.0) + (snap.short_term_debt or 0.0)
    invested_capital = (snap.stockholders_equity or 0.0) + debt
    if invested_capital <= 0:
        return float("nan")
    return float(nopat / invested_capital)


def gross_profitability(snap: FundamentalsSnapshot) -> float:
    """(Revenue − COGS) / Total Assets — Novy-Marx (2013). Robust quality factor."""
    if snap.total_assets in (None, 0):
        return float("nan")
    if snap.gross_profit is not None:
        return float(snap.gross_profit) / float(snap.total_assets)
    if snap.revenue is not None and snap.cost_of_revenue is not None:
        return float(snap.revenue - snap.cost_of_revenue) / float(snap.total_assets)
    return float("nan")


def msci_3descriptor(snap: FundamentalsSnapshot) -> float:
    """MSCI 3-descriptor proxy: equally-weighted z-score of {ROE, D/E (inverted), Earnings Variability}.

    Earnings variability needs annual history, which isn't on the snapshot.
    Stub: return ROE (knowledge §8.7 partial). Phase 3b composite will compute
    the full descriptor cross-sectionally when annual history is available.
    """
    return return_on_equity(snap)


def piotroski_f_score(
    snap: FundamentalsSnapshot, history: pd.DataFrame | None = None
) -> float:
    """Piotroski F-Score (0-9, integer) per knowledge doc §6.1.

    Uses the snapshot for the latest fiscal year (FY_t) and ``history`` for
    FY_{t-1}. Returns NaN if not enough history is available.

    Criteria:
        1. NI > 0
        2. ROA > 0
        3. CFO > 0
        4. CFO / TA > ROA  (quality of earnings)
        5. ΔLong-term debt ratio decreased
        6. ΔCurrent ratio increased
        7. No new shares issued
        8. ΔGross margin increased
        9. ΔAsset turnover increased
    """
    if history is None or history.empty:
        return float("nan")
    score = 0

    # 1. Positive net income
    if snap.net_income is not None and snap.net_income > 0:
        score += 1

    # 2. Positive ROA
    if snap.net_income is not None and snap.total_assets not in (None, 0):
        if snap.net_income / snap.total_assets > 0:
            score += 1

    # 3. Positive CFO
    if snap.operating_cash_flow is not None and snap.operating_cash_flow > 0:
        score += 1

    # 4. CFO/TA > ROA (quality of earnings — accruals not driving profit)
    if (
        snap.operating_cash_flow is not None
        and snap.total_assets not in (None, 0)
        and snap.net_income is not None
    ):
        cfo_ta = snap.operating_cash_flow / snap.total_assets
        roa = snap.net_income / snap.total_assets
        if cfo_ta > roa:
            score += 1

    # 5-9 require last year's values from history.
    def _hist(metric: str) -> float | None:
        rows = history[history["metric"] == metric].sort_values("fiscal_year")
        if rows.empty:
            return None
        # Take the second-most-recent (last full year before current snapshot).
        if len(rows) < 2:
            return None
        return float(rows.iloc[-2]["value"])

    rev_prev = _hist("revenue")
    ta_prev = _hist("total_assets")
    ltd_prev = _hist("long_term_debt")
    ca_prev = _hist("current_assets")
    cl_prev = _hist("current_liabilities")
    shares_prev = _hist("shares_outstanding")
    gp_prev = _hist("gross_profit")

    # 5. Long-term debt ratio decreased
    if (
        snap.long_term_debt is not None
        and snap.total_assets not in (None, 0)
        and ltd_prev is not None
        and ta_prev not in (None, 0)
    ):
        ltd_t = snap.long_term_debt / snap.total_assets
        ltd_t1 = ltd_prev / ta_prev
        if ltd_t < ltd_t1:
            score += 1

    # 6. Current ratio increased
    if (
        snap.current_assets is not None
        and snap.current_liabilities not in (None, 0)
        and ca_prev is not None
        and cl_prev not in (None, 0)
    ):
        cr_t = snap.current_assets / snap.current_liabilities
        cr_t1 = ca_prev / cl_prev
        if cr_t > cr_t1:
            score += 1

    # 7. No new shares issued
    if snap.shares_outstanding is not None and shares_prev is not None:
        if snap.shares_outstanding <= shares_prev:
            score += 1

    # 8. Gross margin increased
    if (
        snap.gross_profit is not None
        and snap.revenue not in (None, 0)
        and gp_prev is not None
        and rev_prev not in (None, 0)
    ):
        gm_t = snap.gross_profit / snap.revenue
        gm_t1 = gp_prev / rev_prev
        if gm_t > gm_t1:
            score += 1

    # 9. Asset turnover increased
    if (
        snap.revenue is not None
        and snap.total_assets not in (None, 0)
        and rev_prev is not None
        and ta_prev not in (None, 0)
    ):
        at_t = snap.revenue / snap.total_assets
        at_t1 = rev_prev / ta_prev
        if at_t > at_t1:
            score += 1

    if math.isnan(score):  # never, but defensive
        return float("nan")
    return float(score)
