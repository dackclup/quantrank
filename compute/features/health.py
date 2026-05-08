"""Financial health metrics — knowledge doc §11.3 + §6.2 (Altman Z″).

Take a ``FundamentalsSnapshot`` and return a single scalar.
"""

from __future__ import annotations

from compute.ingest.fundamentals import FundamentalsSnapshot


def _safe_div(num: float | None, den: float | None) -> float:
    if num is None or den is None or den == 0:
        return float("nan")
    return float(num) / float(den)


def current_ratio(snap: FundamentalsSnapshot) -> float:
    """Current Assets / Current Liabilities. >1.5 healthy, <1.0 squeezed."""
    return _safe_div(snap.current_assets, snap.current_liabilities)


def quick_ratio(snap: FundamentalsSnapshot) -> float:
    """(Current Assets − Inventory) / Current Liabilities."""
    if snap.current_assets is None or snap.current_liabilities in (None, 0):
        return float("nan")
    inv = snap.inventory or 0.0
    return float((snap.current_assets - inv) / snap.current_liabilities)


def debt_to_equity(snap: FundamentalsSnapshot) -> float:
    """Total Debt / Stockholders' Equity. Lower better; >2 levered."""
    debt = (snap.long_term_debt or 0.0) + (snap.short_term_debt or 0.0)
    if debt == 0 and snap.long_term_debt is None and snap.short_term_debt is None:
        return float("nan")
    return _safe_div(debt, snap.stockholders_equity)


def interest_coverage(snap: FundamentalsSnapshot) -> float:
    """EBIT / Interest Expense. >5x comfortable; <1.5x distress."""
    ebit = snap.operating_income
    if ebit is None or snap.interest_expense in (None, 0):
        return float("nan")
    return float(ebit) / float(snap.interest_expense)


def debt_to_ebitda(snap: FundamentalsSnapshot) -> float:
    """Total Debt / EBITDA. <3 healthy, >5 stressed."""
    if snap.ebitda in (None, 0):
        return float("nan")
    debt = (snap.long_term_debt or 0.0) + (snap.short_term_debt or 0.0)
    return float(debt) / float(snap.ebitda)


def altman_z_double_prime(snap: FundamentalsSnapshot) -> float:
    """Altman Z″ for non-manufacturers (knowledge doc §6.2):

        Z″ = 6.56·X₁ + 3.26·X₂ + 6.72·X₃ + 1.05·X₄

        X₁ = (Current Assets − Current Liabilities) / Total Assets
        X₂ = Retained Earnings / Total Assets
        X₃ = EBIT / Total Assets
        X₄ = Book Value of Equity / Total Liabilities

    Zones: >2.90 safe, 1.23-2.90 grey, <1.23 distress.
    """
    if snap.total_assets in (None, 0) or snap.total_liabilities in (None, 0):
        return float("nan")
    ca = snap.current_assets
    cl = snap.current_liabilities
    re = snap.retained_earnings
    ebit = snap.operating_income
    eq = snap.stockholders_equity
    if any(v is None for v in (ca, cl, re, ebit, eq)):
        return float("nan")
    x1 = (ca - cl) / snap.total_assets
    x2 = re / snap.total_assets
    x3 = ebit / snap.total_assets
    x4 = eq / snap.total_liabilities
    return float(6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4)
