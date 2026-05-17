"""Earnings-quality time-series defenses — Phase 4.5d.

Two annotate-only flags derived from the per-ticker fundamentals
history (annual XBRL via ``compute/ingest/fundamentals.py``):

- **`accruals_momentum_high`** — Δ(TATA) > +0.05 over trailing 3
  fiscal years. TATA = (NetIncome − OperatingCashFlow) / TotalAssets,
  the Sloan 1996 / Beneish 1999 accruals backbone. A sudden 3-year
  rise indicates manipulation gathering steam — the snapshot-only
  Sloan + Beneish flags miss this trajectory because they read
  current values without history. PR #86 plan §4.5d called this
  ``m_score_deteriorating`` (Δ(Beneish M) > +0.5); we use TATA
  momentum as a practical equivalent — TATA is the only Beneish
  component that's a level (not a ratio of ratios) and Sloan 1996
  established it as the standalone accruals signal. Avoids the
  bookkeeping cost of building 3 historical 8-ratio Beneish
  snapshots from XBRL history that often has gaps for prior years.

- **`loss_avoidance_pattern`** — Burgstahler-Dichev 1997 *JAE* kink
  at zero. Firms reporting *tiny-positive* NetIncome (in
  ``[$0, $5M]``) OR tiny-positive EPS (in ``[$0.00, $0.05]``) for
  **3+ consecutive fiscal years** are over-represented above zero
  vs the smooth distribution below — the empirical signature of
  managers shading reported earnings just enough to clear the
  loss/loss-threshold.

Both flags are **ANNOTATE-only** — sector-agnostic, both ideas have
moderate base rates and high precision when the cohort is right.
Mirrors the 4.5b posture (no veto without sector adjustment).

References
----------

- Sloan, R. (1996). "Do stock prices fully reflect information in
  accruals and cash flows about future earnings?"
  *The Accounting Review* 71(3), 289-315.
- Burgstahler, D., & Dichev, I. (1997). "Earnings management to
  avoid earnings decreases and losses."
  *Journal of Accounting and Economics* 24(1), 99-126.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot

logger = logging.getLogger(__name__)


# Accruals-momentum threshold — Δ(TATA) over 3y. +0.05 ≈ 5
# percentage points of "TATA worsening" in 3 years. Calibrated to
# match Beneish 1999 Δ(M-score) > +0.5 threshold via the TATA
# coefficient in the Beneish 8-ratio (β_TATA = 4.679 → ΔM ≈ 4.679 ×
# ΔTATA, so ΔM > 0.5 ⇔ ΔTATA > 0.107; we use 0.05 as a more
# sensitive threshold since TATA momentum alone captures less than
# the full 8-ratio signal — the lower bar is the standard practitioner
# adaptation when shortening to one ratio).
ACCRUALS_MOMENTUM_THRESHOLD: Final[float] = 0.05

# Lookback window — exactly 3 fiscal years matches Roychowdhury 2006
# + Burgstahler-Dichev 1997 cohort window. Looking back ~3*365d from
# the snapshot's latest_period_end.
LOOKBACK_YEARS: Final[int] = 3

# Loss-avoidance NI band — Burgstahler-Dichev 1997 Table 2 "small
# positive earnings" cohort. Both the absolute floor ($5M) and the
# per-share floor ($0.05) are practitioner adaptations for the
# modern S&P 500 size (1997 thresholds in inflation-adjusted dollars
# would be ~$8M / $0.08; we use the more sensitive originals).
LOSS_AVOID_NI_FLOOR: Final[float] = 0.0
LOSS_AVOID_NI_CEILING: Final[float] = 5_000_000.0
LOSS_AVOID_EPS_FLOOR: Final[float] = 0.0
LOSS_AVOID_EPS_CEILING: Final[float] = 0.05

# Minimum consecutive years in the tiny-positive band before
# `loss_avoidance_pattern` fires. 3 matches Burgstahler-Dichev 1997
# §4 (persistent earnings-management signature, not just one-year noise).
LOSS_AVOID_MIN_CONSECUTIVE_YEARS: Final[int] = 3


@dataclass(frozen=True)
class AccrualsMomentumResult:
    """`accruals_momentum_high` flag output."""

    fired: bool
    delta_tata: float | None
    """TATA_now − TATA_3y_ago. None when either endpoint is missing."""
    tata_now: float | None
    tata_then: float | None


@dataclass(frozen=True)
class LossAvoidanceResult:
    """`loss_avoidance_pattern` flag output."""

    fired: bool
    consecutive_years: int
    """How many trailing fiscal years sat in the tiny-positive band.
    Could exceed ``LOSS_AVOID_MIN_CONSECUTIVE_YEARS`` for very
    consistent loss-avoiders. 0 when no eligible history found."""


# ---------------------------------------------------------------------------
# History walk helpers
# ---------------------------------------------------------------------------


def _annual_values(
    history: pd.DataFrame | None,
    metric: str,
) -> list[tuple[date, float]]:
    """Return (period_end, value) pairs for ``metric``, sorted ascending
    by period_end. Skips non-finite values + malformed rows."""
    if history is None or len(history) == 0:
        return []
    if "metric" not in history.columns or "period_end" not in history.columns:
        return []
    rows = history[history["metric"] == metric]
    if rows.empty:
        return []
    out: list[tuple[date, float]] = []
    for _, row in rows.iterrows():
        try:
            pe = pd.to_datetime(row["period_end"]).date()
            v = float(row["value"])
        except (TypeError, ValueError, AttributeError):
            continue
        if not math.isfinite(v):
            continue
        out.append((pe, v))
    out.sort(key=lambda p: p[0])
    return out


def _value_at_year(
    series: list[tuple[date, float]],
    target: date,
    *,
    tolerance_days: int = 180,
) -> float | None:
    """Return value whose period_end is closest to ``target`` and
    within ``tolerance_days``. None when no row is close enough."""
    if not series:
        return None
    best: tuple[date, float] | None = None
    best_dist = tolerance_days + 1
    for pe, v in series:
        dist = abs((pe - target).days)
        if dist <= tolerance_days and dist < best_dist:
            best = (pe, v)
            best_dist = dist
    return best[1] if best is not None else None


# ---------------------------------------------------------------------------
# accruals_momentum_high
# ---------------------------------------------------------------------------


def check_accruals_momentum(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
) -> AccrualsMomentumResult:
    """TATA momentum — Δ(TATA) over trailing 3 fiscal years."""
    if snap is None or snap.latest_period_end is None:
        return AccrualsMomentumResult(False, None, None, None)

    # Current TATA from the snapshot.
    if (
        snap.net_income is None
        or snap.operating_cash_flow is None
        or snap.total_assets is None
        or snap.total_assets == 0
    ):
        return AccrualsMomentumResult(False, None, None, None)
    tata_now = (snap.net_income - snap.operating_cash_flow) / snap.total_assets
    if not math.isfinite(tata_now):
        return AccrualsMomentumResult(False, None, None, None)

    # TATA 3y ago from history.
    target = snap.latest_period_end - timedelta(days=365 * LOOKBACK_YEARS)
    ni_series = _annual_values(history, "net_income")
    cfo_series = _annual_values(history, "operating_cash_flow")
    ta_series = _annual_values(history, "total_assets")
    ni_then = _value_at_year(ni_series, target)
    cfo_then = _value_at_year(cfo_series, target)
    ta_then = _value_at_year(ta_series, target)
    if (
        ni_then is None
        or cfo_then is None
        or ta_then is None
        or ta_then == 0
    ):
        return AccrualsMomentumResult(False, None, tata_now, None)
    tata_then = (ni_then - cfo_then) / ta_then
    if not math.isfinite(tata_then):
        return AccrualsMomentumResult(False, None, tata_now, None)

    delta = tata_now - tata_then
    fired = delta > ACCRUALS_MOMENTUM_THRESHOLD
    return AccrualsMomentumResult(
        fired=fired,
        delta_tata=delta,
        tata_now=tata_now,
        tata_then=tata_then,
    )


# ---------------------------------------------------------------------------
# loss_avoidance_pattern
# ---------------------------------------------------------------------------


def _in_tiny_positive_band(
    ni: float | None,
    shares: float | None,
) -> bool:
    """A fiscal-year observation is "tiny positive" when either the
    absolute-NI threshold OR the per-share EPS threshold fires."""
    if ni is None or not math.isfinite(ni):
        return False
    if LOSS_AVOID_NI_FLOOR <= ni <= LOSS_AVOID_NI_CEILING:
        return True
    # EPS check requires shares.
    if shares is None or not math.isfinite(shares) or shares <= 0:
        return False
    eps = ni / shares
    return LOSS_AVOID_EPS_FLOOR <= eps <= LOSS_AVOID_EPS_CEILING


def check_loss_avoidance(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
) -> LossAvoidanceResult:
    """Detect ``LOSS_AVOID_MIN_CONSECUTIVE_YEARS`` or more consecutive
    fiscal years of tiny-positive earnings (Burgstahler-Dichev 1997
    signature). Walks history newest → oldest, stopping at the first
    year that doesn't qualify.
    """
    if snap is None:
        return LossAvoidanceResult(False, 0)

    # Build a chronological list (oldest → newest) of (period_end, NI)
    # from history, plus the current snapshot as the newest entry.
    ni_series = _annual_values(history, "net_income")
    shares_series = _annual_values(history, "shares_outstanding")

    # Pair NI with shares at the same period_end (or nearest within
    # 180d). Walk newest → oldest, counting consecutive years in band.
    if snap.latest_period_end is not None and snap.net_income is not None:
        # Snapshot becomes the most recent entry. Use current
        # shares_outstanding for EPS calc.
        snap_shares = snap.shares_outstanding
        chronological = [
            (snap.latest_period_end, float(snap.net_income), snap_shares),
        ]
        for pe, ni in ni_series:
            if pe >= snap.latest_period_end:
                # Skip same-period (already covered by snap) and any
                # future-dated history rows.
                continue
            sh = _value_at_year(shares_series, pe)
            chronological.append((pe, ni, sh))
    else:
        chronological = [
            (pe, ni, _value_at_year(shares_series, pe)) for pe, ni in ni_series
        ]

    # Sort newest first.
    chronological.sort(key=lambda t: t[0], reverse=True)

    consecutive = 0
    for _, ni, sh in chronological:
        if _in_tiny_positive_band(ni, sh):
            consecutive += 1
        else:
            break

    fired = consecutive >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS
    return LossAvoidanceResult(fired=fired, consecutive_years=consecutive)


__all__ = [
    "ACCRUALS_MOMENTUM_THRESHOLD",
    "AccrualsMomentumResult",
    "LOOKBACK_YEARS",
    "LOSS_AVOID_EPS_CEILING",
    "LOSS_AVOID_EPS_FLOOR",
    "LOSS_AVOID_MIN_CONSECUTIVE_YEARS",
    "LOSS_AVOID_NI_CEILING",
    "LOSS_AVOID_NI_FLOOR",
    "LossAvoidanceResult",
    "check_accruals_momentum",
    "check_loss_avoidance",
]
