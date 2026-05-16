"""Beneish M-score — Tier-3 earnings manipulation indicator (Beneish 1999 FAJ).

Eight-ratio composite measuring the likelihood of earnings manipulation::

    M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
        + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

Threshold: M > -2.22 flags ``beneish_high`` (Beneish 1999 cutoff).

ANNOTATE-only — never enters the composite score or triggers Top-5
suppression. Rationale (WORKFLOW.md §PR 3e):

1. Sloan accruals (an active veto) already encodes much of TATA;
   adding Beneish as a hard veto would double-jeopardy the same signal.
2. Beneish 2022 confirms FP rate ~30% in broad market — too noisy
   for a rank action without sector adjustment.
3. Sector relativity matters: tech / biotech inflate DSRI + SGI
   organically through growth; flagging them as "high" without
   sector-aware thresholds would over-fire.

The boolean flag lands in ``valuation_warnings`` (informational); the
numeric M-score is exposed on ``StockDetail.beneish_m_score`` for
transparency.

Any missing input ratio yields ``m_score=None``. Stocks without a
``property_plant_equipment`` line (banks / REITs / asset-light filers)
will fail AQI + DEPI and skip the flag entirely — a deliberate
conservative default vs. a partial M-score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot

_DSRI_COEF: Final[float] = 0.92
_GMI_COEF: Final[float] = 0.528
_AQI_COEF: Final[float] = 0.404
_SGI_COEF: Final[float] = 0.892
_DEPI_COEF: Final[float] = 0.115
_SGAI_COEF: Final[float] = -0.172
_TATA_COEF: Final[float] = 4.679
_LVGI_COEF: Final[float] = -0.327
_INTERCEPT: Final[float] = -4.84

# Beneish 1999 manipulation threshold (Type-I ~17%, Type-II ~24%).
BENEISH_THRESHOLD: Final[float] = -2.22

# PR 4.5a.2 — soft-veto threshold for promoting Beneish from annotate
# to active veto. Beneish 1999 *FAJ* original cutoff is M > −2.22 (the
# `beneish_high` annotate above). For Top-5 suppression we use a
# STRICTER threshold (M > −1.78) so only high-confidence manipulation
# candidates lose `entered_top5`. The −2.22 to −1.78 band keeps
# annotate-only treatment.
#
# Why −1.78 specifically: Beneish 1999 paper Table 4 shows that at
# M > −1.78 the model's positive-predictive-value crosses ~60% on the
# original 74-manipulator sample. Below that, precision drops into
# FP-heavy territory (Table 3 Type-II error rate). The stricter cutoff
# mirrors the precision/recall trade-off PR 3d locked for the
# `non_reliance_filing` veto — high precision, narrower recall, won't
# dilute Top-5 with marginal annotators.
BENEISH_VETO_THRESHOLD: Final[float] = -1.78


@dataclass(frozen=True)
class BeneishResult:
    """Per-stock Beneish output. ``missing_ratios`` lists which ratios
    couldn't be computed (used by tests + ops triage)."""

    m_score: float | None
    is_high: bool
    missing_ratios: tuple[str, ...] = field(default_factory=tuple)


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
    """Return annual value for ``metric`` ~12 months before ``snap_period_end``.

    Mirrors the lookback shape of ``risk_overlay._shares_at_lookback``: take
    the row with ``period_end`` closest to ``snap_period_end - 365d`` and
    at least 180 days behind ``snap_period_end`` (so we never compare a
    same-period annual against the snapshot's TTM).
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


def _dsri(snap: FundamentalsSnapshot, prior_ar: float | None, prior_rev: float | None) -> float | None:
    return _safe_div(
        _safe_div(snap.accounts_receivable, snap.revenue),
        _safe_div(prior_ar, prior_rev),
    )


def _gmi(snap: FundamentalsSnapshot, prior_rev: float | None, prior_cogs: float | None) -> float | None:
    if snap.revenue is None or snap.cost_of_revenue is None:
        return None
    cur_gm = _safe_div(snap.revenue - snap.cost_of_revenue, snap.revenue)
    if prior_rev is None or prior_cogs is None:
        return None
    pri_gm = _safe_div(prior_rev - prior_cogs, prior_rev)
    return _safe_div(pri_gm, cur_gm)


def _aqi(
    snap: FundamentalsSnapshot,
    prior_ca: float | None,
    prior_ppe: float | None,
    prior_ta: float | None,
) -> float | None:
    if (
        snap.current_assets is None
        or snap.property_plant_equipment is None
        or snap.total_assets is None
        or snap.total_assets == 0
    ):
        return None
    cur = 1 - (snap.current_assets + snap.property_plant_equipment) / snap.total_assets
    if prior_ca is None or prior_ppe is None or prior_ta is None or prior_ta == 0:
        return None
    pri = 1 - (prior_ca + prior_ppe) / prior_ta
    return _safe_div(cur, pri)


def _sgi(snap: FundamentalsSnapshot, prior_rev: float | None) -> float | None:
    return _safe_div(snap.revenue, prior_rev)


def _depi(
    snap: FundamentalsSnapshot,
    prior_da: float | None,
    prior_ppe: float | None,
) -> float | None:
    if snap.depreciation_and_amortization is None or snap.property_plant_equipment is None:
        return None
    cur_share = _safe_div(
        snap.depreciation_and_amortization,
        snap.depreciation_and_amortization + snap.property_plant_equipment,
    )
    if prior_da is None or prior_ppe is None:
        return None
    pri_share = _safe_div(prior_da, prior_da + prior_ppe)
    return _safe_div(pri_share, cur_share)


def _sgai(snap: FundamentalsSnapshot, prior_sga: float | None, prior_rev: float | None) -> float | None:
    return _safe_div(
        _safe_div(snap.sga_expense, snap.revenue),
        _safe_div(prior_sga, prior_rev),
    )


def _tata(snap: FundamentalsSnapshot) -> float | None:
    if snap.net_income is None or snap.operating_cash_flow is None or snap.total_assets is None:
        return None
    if snap.total_assets == 0:
        return None
    return (snap.net_income - snap.operating_cash_flow) / snap.total_assets


def _lvgi(
    snap: FundamentalsSnapshot,
    prior_ltd: float | None,
    prior_cl: float | None,
    prior_ta: float | None,
) -> float | None:
    if (
        snap.long_term_debt is None
        or snap.current_liabilities is None
        or snap.total_assets is None
        or snap.total_assets == 0
    ):
        return None
    cur = (snap.long_term_debt + snap.current_liabilities) / snap.total_assets
    if prior_ltd is None or prior_cl is None or prior_ta is None or prior_ta == 0:
        return None
    pri = (prior_ltd + prior_cl) / prior_ta
    return _safe_div(cur, pri)


def compute_beneish(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
) -> BeneishResult:
    """Compute the Beneish M-score for one stock. None on any missing ratio."""
    if snap is None:
        return BeneishResult(m_score=None, is_high=False, missing_ratios=("snap",))

    period = snap.latest_period_end
    prior_rev = _prior_year_value(history, "revenue", period)
    prior_ar = _prior_year_value(history, "accounts_receivable", period)
    prior_cogs = _prior_year_value(history, "cost_of_revenue", period)
    prior_ca = _prior_year_value(history, "current_assets", period)
    prior_ppe = _prior_year_value(history, "property_plant_equipment", period)
    prior_ta = _prior_year_value(history, "total_assets", period)
    prior_da = _prior_year_value(history, "depreciation_and_amortization", period)
    prior_sga = _prior_year_value(history, "sga_expense", period)
    prior_ltd = _prior_year_value(history, "long_term_debt", period)
    prior_cl = _prior_year_value(history, "current_liabilities", period)

    ratios = {
        "DSRI": _dsri(snap, prior_ar, prior_rev),
        "GMI": _gmi(snap, prior_rev, prior_cogs),
        "AQI": _aqi(snap, prior_ca, prior_ppe, prior_ta),
        "SGI": _sgi(snap, prior_rev),
        "DEPI": _depi(snap, prior_da, prior_ppe),
        "SGAI": _sgai(snap, prior_sga, prior_rev),
        "TATA": _tata(snap),
        "LVGI": _lvgi(snap, prior_ltd, prior_cl, prior_ta),
    }

    missing = tuple(k for k, v in ratios.items() if v is None)
    if missing:
        return BeneishResult(m_score=None, is_high=False, missing_ratios=missing)

    m = (
        _INTERCEPT
        + _DSRI_COEF * ratios["DSRI"]
        + _GMI_COEF * ratios["GMI"]
        + _AQI_COEF * ratios["AQI"]
        + _SGI_COEF * ratios["SGI"]
        + _DEPI_COEF * ratios["DEPI"]
        + _SGAI_COEF * ratios["SGAI"]
        + _TATA_COEF * ratios["TATA"]
        + _LVGI_COEF * ratios["LVGI"]
    )
    return BeneishResult(m_score=m, is_high=m > BENEISH_THRESHOLD)
