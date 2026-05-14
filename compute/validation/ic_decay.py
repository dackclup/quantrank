"""IC-decay monitor (Phase 4b §3).

Per `.claude/skills/phase-4/defense-infrastructure/PLAN.md` §3.
McLean-Pontiff (2016) "Does Academic Research Destroy Stock Return
Predictability?" found that, across 97 published anomalies, the average
**out-of-sample IC decay** is **26%** and the average **post-
publication decay** is an additional **32%** on top of that.

For each QuantRank pillar (DIY + OSAP-blended + JKP-blended once those
ship), we maintain a rolling monthly IC time series. When a pillar's
rolling 12-month IC drops below 50% of its historical mean for 6+
consecutive months, the pillar is flagged as **decayed** and surfaced
in ``frontend/public/data/decay_report.json`` for human review.

Action policy
-------------

This module is **monitor + recommendation**, not auto-veto. Per the
PLAN's graduated response:

- **First detection (alert month 6)** — log to PHASE_STATUS.md; no
  composite change
- **Sustained alert (month 9)** — consider re-tuning that pillar's
  blend weight (e.g., 50/50 OSAP/DIY → 30/70)
- **Sustained alert (month 12)** — exclude the pillar from composite
  (zero its weight) and redistribute to other pillars

The composite change is **manual**, gated through WORKFLOW.md's "When
to Add a Defense" governance gate (the same gate, applied recursively
for removing a decayed defense).

Implementation
--------------

Pure pandas. No new dependencies. The pillar-IC time series is
expected to be supplied by the caller — Phase 5 backtest infrastructure
will accumulate it during walk-forward training; until then, this
module ships as a callable library that the user (or a future Phase
5+ harness) feeds with historical IC data.

Reference paper
---------------

McLean, Pontiff (2016). "Does Academic Research Destroy Stock Return
Predictability?" *Journal of Finance* 71(1), 5-32.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

IC_DECAY_THRESHOLD: float = 0.5  # 50% of historical mean
IC_DECAY_DURATION_MONTHS: int = 6  # consecutive months below threshold = alert
ROLLING_12M_MONTHS: int = 12
ROLLING_36M_MONTHS: int = 36


@dataclass
class ICDecayReport:
    """Per-pillar decay status snapshot.

    The ``alert`` flag is the canonical "this pillar is decayed" signal.
    When ``alert=True``, the caller should:
    1. Log to PHASE_STATUS.md
    2. Consider blend-weight retune (if alert persists 9+ months)
    3. Consider composite-weight zero (if alert persists 12+ months)
    """

    pillar: str
    rolling_12m_ic: float
    rolling_36m_ic: float
    historical_mean_ic: float
    decay_ratio: float
    """rolling_12m_ic / historical_mean_ic. < IC_DECAY_THRESHOLD = degraded."""

    months_below_threshold: int
    """Consecutive trailing months where monthly_ic < THRESHOLD × historical_mean."""

    alert: bool
    n_observations: int


def check_pillar_decay(
    pillar_history: pd.DataFrame,
    *,
    threshold: float = IC_DECAY_THRESHOLD,
    duration_months: int = IC_DECAY_DURATION_MONTHS,
) -> ICDecayReport:
    """Compute a decay status for a single pillar.

    Parameters
    ----------
    pillar_history:
        DataFrame with columns:

        - ``pillar`` (str) — pillar name (e.g., "value", "quality"). Used
          only to populate the returned report.
        - ``year_month`` (date or str) — month-end identifier. Rows
          should be sorted ascending by date but the function re-sorts
          defensively.
        - ``monthly_ic`` (float) — that month's cross-sectional IC.
        - ``n_stocks`` (int, optional) — sample size. Not used by the
          decay computation but preserved for downstream reporting.

    threshold:
        Decay threshold as a fraction of historical mean. Default 0.5
        per PLAN.

    duration_months:
        Number of consecutive trailing months that must be below
        ``threshold × historical_mean`` for ``alert`` to fire. Default
        6 per PLAN.

    Returns
    -------
    ICDecayReport
    """
    required_columns = {"pillar", "year_month", "monthly_ic"}
    missing = required_columns - set(pillar_history.columns)
    if missing:
        raise ValueError(f"pillar_history missing columns: {missing}")
    if pillar_history.empty:
        raise ValueError("pillar_history must be non-empty")

    df = pillar_history.copy()
    df["year_month"] = pd.to_datetime(df["year_month"])
    df = df.sort_values("year_month", kind="mergesort").reset_index(drop=True)

    pillar = str(df["pillar"].iloc[0])
    n = len(df)
    historical_mean = float(df["monthly_ic"].mean())
    rolling_12m = float(df.tail(ROLLING_12M_MONTHS)["monthly_ic"].mean())
    rolling_36m = float(df.tail(ROLLING_36M_MONTHS)["monthly_ic"].mean())

    # Decay ratio computed against historical mean. If historical mean
    # is <= 0 (the pillar never had positive IC to begin with), the
    # decay metric is meaningless — return 0.0 ratio + alert=False.
    if not math.isfinite(historical_mean) or historical_mean <= 0:
        return ICDecayReport(
            pillar=pillar,
            rolling_12m_ic=rolling_12m,
            rolling_36m_ic=rolling_36m,
            historical_mean_ic=historical_mean,
            decay_ratio=0.0,
            months_below_threshold=0,
            alert=False,
            n_observations=n,
        )

    decay_ratio = rolling_12m / historical_mean
    breach_threshold = threshold * historical_mean

    # Count consecutive trailing months below the breach threshold.
    consecutive_below = 0
    for ic in df["monthly_ic"].iloc[::-1]:
        if math.isfinite(ic) and ic < breach_threshold:
            consecutive_below += 1
        else:
            break

    return ICDecayReport(
        pillar=pillar,
        rolling_12m_ic=rolling_12m,
        rolling_36m_ic=rolling_36m,
        historical_mean_ic=historical_mean,
        decay_ratio=decay_ratio,
        months_below_threshold=consecutive_below,
        alert=consecutive_below >= duration_months,
        n_observations=n,
    )


def check_all_pillars(
    pillar_histories: dict[str, pd.DataFrame],
    *,
    threshold: float = IC_DECAY_THRESHOLD,
    duration_months: int = IC_DECAY_DURATION_MONTHS,
) -> list[ICDecayReport]:
    """Run :func:`check_pillar_decay` on every pillar.

    Each entry of ``pillar_histories`` is one pillar's monthly history.
    The dict key is overlaid as the ``pillar`` column when the history
    DataFrame lacks one (convenience for callers that index by pillar
    name).
    """
    reports: list[ICDecayReport] = []
    for pillar_name, hist in pillar_histories.items():
        if "pillar" not in hist.columns:
            hist = hist.assign(pillar=pillar_name)
        try:
            reports.append(
                check_pillar_decay(
                    hist, threshold=threshold, duration_months=duration_months
                )
            )
        except ValueError as e:
            logger.warning("Skipping pillar=%s for decay check: %s", pillar_name, e)
    return reports


def emit_decay_report(
    reports: list[ICDecayReport],
    out_path: Path,
    *,
    threshold: float = IC_DECAY_THRESHOLD,
    duration_months: int = IC_DECAY_DURATION_MONTHS,
) -> None:
    """Write ``frontend/public/data/decay_report.json`` with the per-pillar
    status + list of alerted pillars.

    The frontend may surface "X pillars decaying" badge on the about /
    methodology page in a future PR — schema is intentionally simple.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "threshold": float(threshold),
        "duration_months": int(duration_months),
        "pillars": [asdict(r) for r in reports],
        "anomalies_alerted": [r.pillar for r in reports if r.alert],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


__all__ = [
    "IC_DECAY_DURATION_MONTHS",
    "IC_DECAY_THRESHOLD",
    "ICDecayReport",
    "check_all_pillars",
    "check_pillar_decay",
    "emit_decay_report",
]
