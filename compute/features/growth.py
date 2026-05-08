"""Growth metrics — knowledge doc §11.1.

CAGRs computed from the annual-history DataFrame returned by
``compute.ingest.fundamentals.fetch_fundamentals_history``. Sustainable Growth
Rate uses the latest snapshot.
"""

from __future__ import annotations

import math

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot


def _cagr(values: list[float], n_years: int) -> float:
    """Geometric CAGR over ``n_years`` from a chronological list of values.

    Both endpoints must be positive and the list must contain at least two
    values; returns NaN otherwise. For series that include negatives we
    fall back to NaN (log CAGR isn't defined cleanly).
    """
    if not values or len(values) < 2 or n_years <= 0:
        return float("nan")
    start, end = values[0], values[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return float("nan")
    return float((end / start) ** (1 / n_years) - 1)


def _series_for(history: pd.DataFrame | None, metric: str) -> list[tuple[int, float]]:
    """Sorted (fiscal_year, value) for a given metric. Empty list if missing."""
    if history is None or history.empty:
        return []
    sub = history[history["metric"] == metric].sort_values("fiscal_year")
    return [(int(r.fiscal_year), float(r.value)) for r in sub.itertuples()]


def _cagr_from_history(
    history: pd.DataFrame | None, metric: str, years: int
) -> float:
    series = _series_for(history, metric)
    if len(series) < years + 1:
        return float("nan")
    # Use the most recent ``years + 1`` annual observations.
    window = series[-(years + 1):]
    return _cagr([v for _, v in window], n_years=years)


def revenue_cagr_3y(history: pd.DataFrame | None) -> float:
    return _cagr_from_history(history, "revenue", 3)


def revenue_cagr_5y(history: pd.DataFrame | None) -> float:
    return _cagr_from_history(history, "revenue", 5)


def eps_cagr_3y(history: pd.DataFrame | None) -> float:
    return _cagr_from_history(history, "eps_diluted", 3)


def eps_cagr_5y(history: pd.DataFrame | None) -> float:
    return _cagr_from_history(history, "eps_diluted", 5)


def fcf_cagr_3y(history: pd.DataFrame | None) -> float:
    """FCF = CFO − CapEx, computed per fiscal year from history."""
    return _cagr_from_history(_compute_fcf_series(history), "fcf", 3)


def fcf_cagr_5y(history: pd.DataFrame | None) -> float:
    return _cagr_from_history(_compute_fcf_series(history), "fcf", 5)


def _compute_fcf_series(history: pd.DataFrame | None) -> pd.DataFrame | None:
    if history is None or history.empty:
        return None
    cfo = history[history["metric"] == "operating_cash_flow"].set_index("fiscal_year")
    capex = history[history["metric"] == "capex"].set_index("fiscal_year")
    common = sorted(set(cfo.index) & set(capex.index))
    if not common:
        return None
    rows = []
    for fy in common:
        v = float(cfo.loc[fy, "value"]) - abs(float(capex.loc[fy, "value"]))
        rows.append({"fiscal_year": fy, "metric": "fcf", "value": v})
    return pd.DataFrame(rows)


def sustainable_growth_rate(snap: FundamentalsSnapshot) -> float:
    """SGR = ROE × (1 − payout ratio).

    Payout ratio = dividends_paid / net_income. When dividends or net income
    are missing, returns NaN. Knowledge doc §11.1.
    """
    if (
        snap.net_income is None
        or snap.net_income <= 0
        or snap.stockholders_equity in (None, 0)
        or snap.stockholders_equity <= 0
    ):
        return float("nan")
    roe = snap.net_income / snap.stockholders_equity
    payout = (
        (snap.dividends_paid or 0.0) / snap.net_income
        if snap.net_income > 0
        else 0.0
    )
    if math.isnan(payout) or payout < 0 or payout > 1.5:
        return float("nan")
    return float(roe * (1 - payout))
