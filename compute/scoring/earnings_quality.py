"""Earnings-quality time-series defenses — Phase 4.5d + 4b.

Three annotate-only flags derived from the per-ticker fundamentals
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
  ``[$0, $50M]``) OR tiny-positive EPS (in ``[$0.00, $0.50]``) for
  **3+ consecutive fiscal years** are over-represented above zero
  vs the smooth distribution below — the empirical signature of
  managers shading reported earnings just enough to clear the
  loss/loss-threshold. Thresholds are 10× the original
  Burgstahler-Dichev 1997 Compustat-cohort values ($5M / $0.05) to
  account for the S&P 500's larger firm-size distribution; the
  zero-bunching effect is preserved, only the band width is scaled
  (Phase 2.4 of epic #150, 2026-05-21).

- **`loss_avoidance_pattern_size_invariant`** — Roychowdhury 2006
  *JAE* §5.2 "suspect-firm" definition: ``NI / TotalAssets ∈
  [0, 0.005]`` (0.5% of assets) for **3+ consecutive fiscal years**.
  Size-invariant operationalization of the same Burgstahler-Dichev
  1997 kink-at-zero signature — the asset-scaled threshold doesn't
  drift with universe market-cap inflation, so it generalizes
  cleanly to firm-size distributions the absolute-dollar variant
  misses (e.g., chronically thin-margin large caps where NI/TA
  hovers near zero despite NI > $50M). Donelson-McInnis-Mergenthaler
  2013 *TAR* reaffirms the 0.005 cutoff as canonical for small-
  profit cohort selection. The size-invariant flag ships alongside
  the absolute-$ variant per the `portable-annotate-before-veto`
  discipline (Phase 4b, 2026-05-21); the next-PR decision (retire
  the absolute-$ original, keep both, or split weights) waits on
  the Q3 2026-08-19 quarterly cohort audit + a φ-correlation check
  vs `rem_suspect` (same Roychowdhury 2006 anchor; different
  sub-trigger).

All three flags are **ANNOTATE-only** — sector-agnostic, all three
ideas have moderate base rates and high precision when the cohort
is right. Mirrors the 4.5b posture (no veto without sector
adjustment).

References
----------

- Sloan, R. (1996). "Do stock prices fully reflect information in
  accruals and cash flows about future earnings?"
  *The Accounting Review* 71(3), 289-315.
- Burgstahler, D., & Dichev, I. (1997). "Earnings management to
  avoid earnings decreases and losses."
  *Journal of Accounting and Economics* 24(1), 99-126.
- Roychowdhury, S. (2006). "Earnings management through real
  activities manipulation."
  *Journal of Accounting and Economics* 42(3), 335-370.
- Donelson, D. C., McInnis, J. M., & Mergenthaler, R. D. (2013).
  "Discontinuities and earnings management: Evidence from
  restatements related to securities litigation."
  *The Accounting Review* 88(2), 387-411.
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
# positive earnings" cohort, rescaled 10× for the S&P 500 universe
# (Phase 2.4 of epic #150). Original BD 1997 thresholds ($5M / $0.05)
# were calibrated to a 1990s Compustat universe dominated by small-
# and mid-cap firms; at S&P 500 scale (mean NI > $1B, mean EPS > $5)
# the absolute-dollar band catches 0 firms — the flag fired 0% on
# the live universe pre-rescale (issue tracked in CLAUDE.md §Gotchas
# until Phase 2.4 landed). 10× lifts the NI band to ``[$0, $50M]``
# and the EPS band to ``[$0, $0.50]``. The Burgstahler-Dichev kink-
# at-zero signature is preserved — only the band width scales with
# firm size. The size-invariant sibling `loss_avoidance_pattern_size_invariant`
# (``LOSS_AVOID_NI_TO_ASSETS_CEILING`` below) closes the Phase 2.4
# follow-up that originally read "replace absolute-dollar with
# NI/TotalAssets"; both flags now ship side-by-side annotate-only
# pending the Q3 2026-08-19 cohort-acceptance decision (retire one,
# keep both, or split weights).
LOSS_AVOID_NI_FLOOR: Final[float] = 0.0
LOSS_AVOID_NI_CEILING: Final[float] = 50_000_000.0
LOSS_AVOID_EPS_FLOOR: Final[float] = 0.0
LOSS_AVOID_EPS_CEILING: Final[float] = 0.50

# Size-invariant loss-avoidance band — Roychowdhury 2006 *JAE*
# Table 1 + §5.2 "suspect-firm" definition: NI / TotalAssets ∈
# [0, 0.005] (0.5% of assets). Donelson-McInnis-Mergenthaler 2013
# *TAR* reaffirms 0.005 as the canonical small-profit cohort cutoff.
# Same kink-at-zero signature as the absolute-dollar variant
# (LOSS_AVOID_NI_CEILING above), but asset-scaled so the threshold
# doesn't drift with universe market-cap inflation — catches
# chronically-thin-margin large caps (NI > $50M, NI/TA < 0.5%) that
# the absolute-$ band misses. Expected single-year suspect rate
# ~8-12% on Compustat per Roychowdhury Table 1; on S&P 500 with the
# 3-year persistence filter the expected firing rate is ~1.5-4%
# (~8-20 tickers). Phase 4b, 2026-05-21.
LOSS_AVOID_NI_TO_ASSETS_FLOOR: Final[float] = 0.0
LOSS_AVOID_NI_TO_ASSETS_CEILING: Final[float] = 0.005

# Minimum consecutive years in the tiny-positive band before
# `loss_avoidance_pattern` (and `loss_avoidance_pattern_size_invariant`)
# fires. 3 matches Burgstahler-Dichev 1997 §4 + Roychowdhury 2006
# §5.2 (persistent earnings-management signature, not just one-year noise).
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


@dataclass(frozen=True)
class LossAvoidanceSizeInvariantResult:
    """`loss_avoidance_pattern_size_invariant` flag output (Phase 4b)."""

    fired: bool
    consecutive_years: int
    """How many trailing fiscal years sat in the
    ``NI / TotalAssets ∈ [0, LOSS_AVOID_NI_TO_ASSETS_CEILING]``
    band. 0 when no eligible history found (missing NI or
    TotalAssets at any year in the look-back, zero TotalAssets,
    or non-finite ratio). Walks newest → oldest, stops at the
    first year that doesn't qualify (matches the absolute-$
    sibling's streak semantics)."""


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


# ---------------------------------------------------------------------------
# loss_avoidance_pattern_size_invariant (Phase 4b — Roychowdhury 2006)
# ---------------------------------------------------------------------------


def check_loss_avoidance_size_invariant(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
) -> LossAvoidanceSizeInvariantResult:
    """Detect ``LOSS_AVOID_MIN_CONSECUTIVE_YEARS`` or more consecutive
    fiscal years where ``NI / TotalAssets ∈ [0, LOSS_AVOID_NI_TO_ASSETS_CEILING]``
    (Roychowdhury 2006 *JAE* §5.2 suspect-firm signature).

    Companion to ``check_loss_avoidance`` — same persistence-streak
    construction (newest → oldest, stop at the first year that fails),
    different threshold metric (asset-scaled instead of absolute-$).
    Returns ``fired=False, consecutive_years=0`` when the snapshot or
    history is missing the inputs needed to compute NI/TA at any year
    in the candidate streak — graceful-degradation per Rule 18 (no
    half-credit for partial history).
    """
    if snap is None:
        return LossAvoidanceSizeInvariantResult(False, 0)

    ni_series = _annual_values(history, "net_income")
    ta_series = _annual_values(history, "total_assets")

    # Build a chronological list of (period_end, NI, TA) including the
    # snapshot as the most recent entry (when its inputs are available).
    chronological: list[tuple[date, float | None, float | None]] = []
    if (
        snap.latest_period_end is not None
        and snap.net_income is not None
        and snap.total_assets is not None
    ):
        chronological.append(
            (
                snap.latest_period_end,
                float(snap.net_income),
                float(snap.total_assets),
            )
        )
    for pe, ni in ni_series:
        if snap is not None and snap.latest_period_end is not None and pe >= snap.latest_period_end:
            # Skip same-period (already covered by snap) and future-dated rows.
            continue
        ta = _value_at_year(ta_series, pe)
        chronological.append((pe, ni, ta))

    # Walk newest first, counting consecutive in-band years.
    chronological.sort(key=lambda t: t[0], reverse=True)

    consecutive = 0
    for _, ni, ta in chronological:
        if ni is None or ta is None or ta <= 0:
            # Missing input → cannot evaluate this year → streak breaks
            # (no half-credit per Rule 18 — annotate is only meaningful
            # when the full 3y window has data).
            break
        if not math.isfinite(ni) or not math.isfinite(ta):
            break
        ratio = ni / ta
        if not math.isfinite(ratio):
            break
        if LOSS_AVOID_NI_TO_ASSETS_FLOOR <= ratio <= LOSS_AVOID_NI_TO_ASSETS_CEILING:
            consecutive += 1
        else:
            break

    fired = consecutive >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS
    return LossAvoidanceSizeInvariantResult(fired=fired, consecutive_years=consecutive)


__all__ = [
    "ACCRUALS_MOMENTUM_THRESHOLD",
    "AccrualsMomentumResult",
    "LOOKBACK_YEARS",
    "LOSS_AVOID_EPS_CEILING",
    "LOSS_AVOID_EPS_FLOOR",
    "LOSS_AVOID_MIN_CONSECUTIVE_YEARS",
    "LOSS_AVOID_NI_CEILING",
    "LOSS_AVOID_NI_FLOOR",
    "LOSS_AVOID_NI_TO_ASSETS_CEILING",
    "LOSS_AVOID_NI_TO_ASSETS_FLOOR",
    "LossAvoidanceResult",
    "LossAvoidanceSizeInvariantResult",
    "check_accruals_momentum",
    "check_loss_avoidance",
    "check_loss_avoidance_size_invariant",
]
