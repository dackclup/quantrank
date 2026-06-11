"""Dechow F-score — Tier-3 fraud probability (Dechow et al. 2011 CAR).

Complementary to Beneish M-score: uses different inputs (RSST-style accruals
+ non-financial proxies). Average sensitivity 73%, type-II 27% in the
original 2,190-firm AAER sample. Both flags surface as ANNOTATE-only on
``valuation_warnings``; the UI displays them side-by-side.

Formula (Model 1 — financial-statement-only)::

    P = -7.893 + 0.790*RSST + 2.518*Δrecv + 1.191*Δinv
        + 1.979*soft_assets + 0.171*Δcash_sales - 0.932*Δroa + 1.029*issuance

    F = (exp(P) / (1 + exp(P))) / 0.0037

Where 0.0037 is the unconditional probability of misstatement in the
Dechow training sample. F > 1 = above-baseline risk; **F > 2.45** = top-
decile high risk → flag ``dechow_high``.

Simplifications vs. the strict Dechow 2011 formula:

1. **RSST accruals → (NI − CFO) / avg_TA** (TATA pattern). Dechow paper
   footnote 13: "Total accruals (NI − CFO) is a valid proxy for RSST
   accruals when balance sheet decomposition is unavailable." Strict RSST
   needs 5+ extra ingest fields (taxes_payable, investments, preferred
   stock) that have spotty XBRL coverage on S&P 500. Consistent with
   the Beneish TATA simplification merged in PR 3e.1.

2. **Δcash_sales → (Rev_t − Rev_{t−1}) / Rev_{t−1}** instead of the
   AR-adjusted version. Coefficient 0.171 is the smallest in the formula,
   and AR-relative manipulation is already caught by Beneish DSRI
   (coefficient 0.92).

ANNOTATE-only (same rationale as Beneish, WORKFLOW.md §PR 3e):
- Sloan accruals already covers the RSST overlap → double-jeopardy risk
- Dechow FP rate ~27% in broad market (sensitivity 73%)
- Sector relativity matters for soft_assets (tech / pharma run high
  organically)

Any missing ratio yields ``f_score=None`` (no flag).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot

_RSST_COEF: Final[float] = 0.790
_DRECV_COEF: Final[float] = 2.518
_DINV_COEF: Final[float] = 1.191
_SOFT_COEF: Final[float] = 1.979
_DCASH_COEF: Final[float] = 0.171
_DROA_COEF: Final[float] = -0.932
_ISSUE_COEF: Final[float] = 1.029
_INTERCEPT: Final[float] = -7.893

# Dechow 2011 unconditional base rate of AAER misstatement in sample.
_BASELINE: Final[float] = 0.0037

# Top-decile cutoff per Dechow 2011 Table 7: "high risk" classification.
DECHOW_HIGH_THRESHOLD: Final[float] = 2.45

# PR 4.5a.3 — soft-veto threshold for promoting Dechow from annotate
# to active veto. Dechow 2011 *CAR* Table 7 "high risk" cutoff is F >
# 2.45 (the `dechow_high` annotate above). For Top-5 suppression we
# use a STRICTER threshold (F > 3.0) so only high-confidence
# manipulation candidates lose `entered_top5`. The 2.45 to 3.0 band
# keeps annotate-only treatment.
#
# Why 3.0 specifically: Dechow 2011 Table 7 shows that at F > 3.0 the
# AAER hit rate exceeds 4× the baseline (vs ~2× at F > 2.45). The
# stricter cutoff matches the precision/recall trade-off PR 4.5a.2
# locked for Beneish (high precision, narrower recall) and PR 3d
# locked for `non_reliance_filing`.
DECHOW_VETO_THRESHOLD: Final[float] = 3.0

# Share-issuance dummy threshold — 1%+ year-over-year growth in
# shares_outstanding flips the dummy.
_ISSUANCE_THRESHOLD: Final[float] = 0.01


@dataclass(frozen=True)
class DechowResult:
    f_score: float | None
    is_high: bool
    missing_inputs: tuple[str, ...] = field(default_factory=tuple)


def _safe_div(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None:
        return None
    if not math.isfinite(num) or not math.isfinite(denom):
        return None
    if denom == 0:
        return None
    return num / denom


def _prior_year_value(
    history: pd.DataFrame | None,
    metric: str,
    snap_period_end: date | None,
) -> float | None:
    """Return annual value for ``metric`` ~12m before ``snap_period_end``.

    Same shape as ``compute.scoring.beneish._prior_year_value``. Picks the
    row with ``period_end`` closest to ``snap_period_end − 365d`` and
    behind a 180-day cutoff so we never compare same-period TTM to an
    annual-row of the same fiscal year.
    """
    if history is None or len(history) == 0:
        return None
    if snap_period_end is None:
        return None
    if "metric" not in history.columns or "period_end" not in history.columns:
        return None
    rows = history[history["metric"] == metric]
    if rows.empty:
        return None
    rows = rows.copy()
    rows["_period_end"] = pd.to_datetime(rows["period_end"]).dt.date
    target = snap_period_end - timedelta(days=365)
    cutoff = snap_period_end - timedelta(days=180)
    candidates = rows[rows["_period_end"] <= cutoff]
    if candidates.empty:
        return None
    candidates = candidates.assign(
        _dist=candidates["_period_end"].apply(lambda d: abs((d - target).days))
    )
    best = candidates.sort_values("_dist", kind="mergesort").iloc[0]
    val = best["value"]
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def _avg_ta(snap: FundamentalsSnapshot, prior_ta: float | None) -> float | None:
    if snap.total_assets is None or prior_ta is None:
        return None
    avg = (snap.total_assets + prior_ta) / 2
    if avg <= 0:
        return None
    return avg


def _rsst_simplified(snap: FundamentalsSnapshot, avg_ta: float | None) -> float | None:
    """Total-accruals proxy = (NI − CFO) / avg_TA."""
    if snap.net_income is None or snap.operating_cash_flow is None:
        return None
    return _safe_div(snap.net_income - snap.operating_cash_flow, avg_ta)


def _delta_recv(
    snap: FundamentalsSnapshot, prior_ar: float | None, avg_ta: float | None
) -> float | None:
    if snap.accounts_receivable is None or prior_ar is None:
        return None
    return _safe_div(snap.accounts_receivable - prior_ar, avg_ta)


def _delta_inv(
    snap: FundamentalsSnapshot, prior_inv: float | None, avg_ta: float | None
) -> float | None:
    if snap.inventory is None or prior_inv is None:
        return None
    return _safe_div(snap.inventory - prior_inv, avg_ta)


def _soft_assets(snap: FundamentalsSnapshot) -> float | None:
    """Soft assets = (TA − PPE − Cash) / TA. Higher = more book-value softness."""
    if (
        snap.total_assets is None
        or snap.total_assets <= 0
        or snap.property_plant_equipment is None
        or snap.cash is None
    ):
        return None
    return (snap.total_assets - snap.property_plant_equipment - snap.cash) / snap.total_assets


def _delta_cash_sales(snap: FundamentalsSnapshot, prior_rev: float | None) -> float | None:
    """Simplified — % change in revenue. Strict version subtracts ΔAR, but
    AR-channel-stuffing is already encoded by Beneish DSRI and the Δrecv
    term in this formula. Coefficient 0.171 is the smallest weight."""
    if snap.revenue is None or prior_rev is None or prior_rev <= 0:
        return None
    return (snap.revenue - prior_rev) / prior_rev


def _delta_roa(
    snap: FundamentalsSnapshot,
    prior_ni: float | None,
    prior_ta: float | None,
) -> float | None:
    if (
        snap.net_income is None
        or snap.total_assets is None
        or snap.total_assets <= 0
        or prior_ni is None
        or prior_ta is None
        or prior_ta <= 0
    ):
        return None
    return snap.net_income / snap.total_assets - prior_ni / prior_ta


def _issuance_dummy(
    snap: FundamentalsSnapshot, prior_shares: float | None
) -> float | None:
    # Series-consistency invariant (Issue #374, RATIFY-B, 2026-06-11):
    # ``snap.shares_outstanding`` is the SEC companyfacts AGGREGATE (company-total
    # across all classes); ``prior_shares`` is from ``_ANNUAL_TAGS``
    # (us-gaap:CommonStockSharesOutstanding via the same aggregate path). Both
    # are on the same basis post-RATIFY-B revert — no fabricated YoY spike.
    if (
        snap.shares_outstanding is None
        or snap.shares_outstanding <= 0
        or prior_shares is None
        or prior_shares <= 0
    ):
        return None
    growth = snap.shares_outstanding / prior_shares - 1
    return 1.0 if growth >= _ISSUANCE_THRESHOLD else 0.0


def compute_dechow_f(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
) -> DechowResult:
    """Compute the Dechow F-score for one stock. None on any missing input."""
    if snap is None:
        return DechowResult(f_score=None, is_high=False, missing_inputs=("snap",))

    period = snap.latest_period_end
    prior_ta = _prior_year_value(history, "total_assets", period)
    prior_ar = _prior_year_value(history, "accounts_receivable", period)
    prior_inv = _prior_year_value(history, "inventory", period)
    prior_rev = _prior_year_value(history, "revenue", period)
    prior_ni = _prior_year_value(history, "net_income", period)
    prior_shares = _prior_year_value(history, "shares_outstanding", period)

    avg_ta = _avg_ta(snap, prior_ta)
    variables = {
        "RSST": _rsst_simplified(snap, avg_ta),
        "Δrecv": _delta_recv(snap, prior_ar, avg_ta),
        "Δinv": _delta_inv(snap, prior_inv, avg_ta),
        "soft_assets": _soft_assets(snap),
        "Δcash_sales": _delta_cash_sales(snap, prior_rev),
        "Δroa": _delta_roa(snap, prior_ni, prior_ta),
        "issuance": _issuance_dummy(snap, prior_shares),
    }

    missing = tuple(k for k, v in variables.items() if v is None)
    if missing:
        return DechowResult(f_score=None, is_high=False, missing_inputs=missing)

    p = (
        _INTERCEPT
        + _RSST_COEF * variables["RSST"]
        + _DRECV_COEF * variables["Δrecv"]
        + _DINV_COEF * variables["Δinv"]
        + _SOFT_COEF * variables["soft_assets"]
        + _DCASH_COEF * variables["Δcash_sales"]
        + _DROA_COEF * variables["Δroa"]
        + _ISSUE_COEF * variables["issuance"]
    )
    # Logistic transform → probability of misstatement → scaled by base rate.
    try:
        prob = math.exp(p) / (1 + math.exp(p))
    except OverflowError:
        # When P is large positive, exp(P) overflows but prob → 1.0 in the limit.
        prob = 1.0
    f = prob / _BASELINE
    return DechowResult(f_score=f, is_high=f > DECHOW_HIGH_THRESHOLD)
