"""Profitability metrics — knowledge doc §11.2 + §8.10.

All take a ``FundamentalsSnapshot`` and return a single scalar.
"""

from __future__ import annotations

import math

from compute.ingest.fundamentals import FundamentalsSnapshot


def _safe_div(num: float | None, den: float | None) -> float:
    if num is None or den is None or den == 0:
        return float("nan")
    return float(num) / float(den)


def gross_margin(snap: FundamentalsSnapshot) -> float:
    """Gross profit / Revenue."""
    if snap.gross_profit is not None and snap.revenue not in (None, 0):
        return _safe_div(snap.gross_profit, snap.revenue)
    if snap.cost_of_revenue is not None and snap.revenue not in (None, 0):
        return _safe_div(snap.revenue - snap.cost_of_revenue, snap.revenue)
    return float("nan")


def operating_margin(snap: FundamentalsSnapshot) -> float:
    return _safe_div(snap.operating_income, snap.revenue)


def net_margin(snap: FundamentalsSnapshot) -> float:
    return _safe_div(snap.net_income, snap.revenue)


def return_on_assets(snap: FundamentalsSnapshot) -> float:
    """ROA = Net Income / Total Assets."""
    return _safe_div(snap.net_income, snap.total_assets)


def asset_turnover(snap: FundamentalsSnapshot) -> float:
    """Revenue / Total Assets. Excludes Financials per WORKFLOW.md §3.2."""
    return _safe_div(snap.revenue, snap.total_assets)


def cash_conversion_cycle(snap: FundamentalsSnapshot) -> float:
    """CCC = DSO + DIO − DPO. Lower is better.

    Approximated:
      DSO = receivables / (revenue / 365)
      DIO = inventory   / (cost_of_revenue / 365)  (fall back to revenue if COGS missing)
      DPO = payables    / (cost_of_revenue / 365)
    """
    if snap.revenue in (None, 0):
        return float("nan")
    cogs = snap.cost_of_revenue if snap.cost_of_revenue not in (None, 0) else snap.revenue
    daily_revenue = snap.revenue / 365
    if not daily_revenue:
        # revenue so small it underflows to 0.0 (e.g. 5e-324 / 365) — not computable
        return float("nan")
    daily_cogs = cogs / 365
    if not daily_cogs:
        # cogs (or revenue fallback) underflows to 0.0 — not computable
        return float("nan")
    dso = (
        snap.accounts_receivable / daily_revenue
        if snap.accounts_receivable is not None
        else None
    )
    dio = (
        snap.inventory / daily_cogs
        if snap.inventory is not None
        else None
    )
    dpo = (
        snap.accounts_payable / daily_cogs
        if snap.accounts_payable is not None
        else None
    )
    parts = [p for p in (dso, dio, dpo) if p is not None]
    if not parts:
        return float("nan")
    # CCC = DSO + DIO − DPO. Treat missing components as zero so partial data
    # still produces a useful (even if biased) number.
    return float((dso or 0) + (dio or 0) - (dpo or 0))


def gross_profitability(snap: FundamentalsSnapshot) -> float:
    """Novy-Marx 2013: (Revenue − COGS) / Total Assets — most robust profitability factor."""
    if (
        snap.gross_profit is not None
        and snap.total_assets not in (None, 0)
    ):
        return _safe_div(snap.gross_profit, snap.total_assets)
    if (
        snap.revenue is not None
        and snap.cost_of_revenue is not None
        and snap.total_assets not in (None, 0)
    ):
        return _safe_div(snap.revenue - snap.cost_of_revenue, snap.total_assets)
    return float("nan")


def is_finite(x: float) -> bool:
    return x is not None and not math.isnan(x) and math.isfinite(x)
