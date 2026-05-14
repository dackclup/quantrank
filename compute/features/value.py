"""Value metrics — knowledge doc §8.6 (Magic Formula), §10 (Graham, Tobin's Q).

Most metrics need ``current_price`` in addition to the snapshot. All return a
single scalar.
"""

from __future__ import annotations

import math

from compute.ingest.fundamentals import FundamentalsSnapshot


def _safe_div(num: float | None, den: float | None) -> float:
    if num is None or den is None or den == 0:
        return float("nan")
    return float(num) / float(den)


def market_cap(snap: FundamentalsSnapshot, current_price: float) -> float:
    if snap.shares_outstanding is None or current_price is None or current_price <= 0:
        return float("nan")
    return float(current_price * snap.shares_outstanding)


def pe_ratio(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Price / Trailing-Twelve-Months EPS. Lower is cheaper. Negative or
    missing TTM earnings → NaN.

    Computes TTM EPS from ``net_income / shares_outstanding`` rather than
    using ``snap.eps_diluted`` directly. Audit #6 (pre-v1.0 deep clean)
    found that ``snap.eps_diluted`` comes from edgartools' normalized
    snake_case API, which returns the latest single-period EPS — a value
    that can be Q1, H1 YTD, Q3 YTD, or FY annual depending on each filer's
    reporting cadence. The ratio ``eps_diluted / TTM_EPS`` had median 0.29
    across the S&P 500 (88.6% of tickers had PE wrong by > 30%); TSLA was
    8× off, ABBV 5× off, GOOGL 2.6× off.

    Using ``net_income / shares_outstanding`` is consistent across filers
    because ``net_income`` is fetched as a true TTM via the freshness-aware
    MAX helper in ``compute.ingest.fundamentals._try_ttm_max_fresh``.
    """
    if (
        snap.net_income is None
        or snap.shares_outstanding is None
        or snap.shares_outstanding <= 0
        or snap.net_income <= 0
    ):
        return float("nan")
    ttm_eps = snap.net_income / snap.shares_outstanding
    if ttm_eps <= 0:
        return float("nan")
    return float(current_price) / ttm_eps


def pb_ratio(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Price / Book. Uses book value per share = equity / shares."""
    if (
        snap.stockholders_equity is None
        or snap.shares_outstanding in (None, 0)
        or snap.stockholders_equity <= 0
    ):
        return float("nan")
    bvps = snap.stockholders_equity / snap.shares_outstanding
    if bvps <= 0:
        return float("nan")
    return float(current_price) / float(bvps)


def ps_ratio(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Price / Sales (TTM)."""
    cap = market_cap(snap, current_price)
    if math.isnan(cap) or snap.revenue in (None, 0):
        return float("nan")
    return float(cap) / float(snap.revenue)


def enterprise_value(snap: FundamentalsSnapshot, current_price: float) -> float:
    """EV = Market Cap + Total Debt − Cash."""
    cap = market_cap(snap, current_price)
    if math.isnan(cap):
        return float("nan")
    debt = (snap.long_term_debt or 0.0) + (snap.short_term_debt or 0.0)
    cash = snap.cash or 0.0
    return float(cap + debt - cash)


def ev_to_ebitda(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Enterprise Value / EBITDA. Lower = cheaper."""
    if snap.ebitda in (None, 0):
        return float("nan")
    ev = enterprise_value(snap, current_price)
    if math.isnan(ev):
        return float("nan")
    return float(ev) / float(snap.ebitda)


def ev_to_fcf(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Enterprise Value / Free Cash Flow."""
    if snap.free_cash_flow in (None, 0) or snap.free_cash_flow < 0:
        return float("nan")
    ev = enterprise_value(snap, current_price)
    if math.isnan(ev):
        return float("nan")
    return float(ev) / float(snap.free_cash_flow)


def earnings_yield_greenblatt(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Greenblatt's earnings yield = EBIT / Enterprise Value (knowledge §8.6).

    Higher yield = cheaper. Excludes financials/utilities at the screener
    level (handled by sector_rules in PR 3b).
    """
    if snap.operating_income is None or snap.operating_income <= 0:
        return float("nan")
    ev = enterprise_value(snap, current_price)
    if math.isnan(ev) or ev <= 0:
        return float("nan")
    return float(snap.operating_income) / float(ev)


def graham_number(snap: FundamentalsSnapshot) -> float:
    """Graham Number = √(22.5 × EPS_TTM × BVPS_reported). Conservative fair-value proxy.

    Defined only for positive EPS and BVPS. Compare to current price.

    EPS_TTM is derived from ``net_income / shares_outstanding`` (audit #6)
    rather than ``snap.eps_diluted`` (single-period). For the **fair-price
    ensemble** (Phase 3c onward), use the tangible-book-aware variant in
    ``compute.valuation.graham`` — ``graham_fair_price`` uses 3y-avg EPS
    and TBVPS for a more conservative valuation anchor. This pillar
    function intentionally retains TTM EPS + reported BVPS for cross-
    sectional ranking responsiveness (kickoff §B4 "intentional dual
    implementation").
    """
    if (
        snap.net_income is None
        or snap.shares_outstanding is None
        or snap.shares_outstanding <= 0
        or snap.net_income <= 0
    ):
        return float("nan")
    ttm_eps = snap.net_income / snap.shares_outstanding
    if ttm_eps <= 0:
        return float("nan")
    if (
        snap.stockholders_equity is None
        or snap.shares_outstanding in (None, 0)
        or snap.stockholders_equity <= 0
    ):
        return float("nan")
    bvps = snap.stockholders_equity / snap.shares_outstanding
    if bvps <= 0:
        return float("nan")
    return float(math.sqrt(22.5 * ttm_eps * bvps))


def tobins_q(snap: FundamentalsSnapshot, current_price: float) -> float:
    """Tobin's Q ≈ (Market Cap + Liabilities) / Total Assets.

    Q > 1 suggests market values assets above replacement cost; Q < 1
    suggests undervaluation.
    """
    cap = market_cap(snap, current_price)
    if math.isnan(cap) or snap.total_assets in (None, 0):
        return float("nan")
    liabilities = snap.total_liabilities or 0.0
    return float((cap + liabilities) / snap.total_assets)
