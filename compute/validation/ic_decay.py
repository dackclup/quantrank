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

Preliminary guard
-----------------

When fewer than ``MIN_HISTORY_MONTHS`` (12) monthly observations exist
for a pillar, the report is marked ``preliminary=True`` and ``alert``
is FORCED to ``False``. This is the honest labeling requirement: a
6-month alert triggered on only 7 months of history is statistically
meaningless. Alerts are suppressed until ≥12 months have accumulated.

Wiring (Rule 18 observability-before-wiring)
--------------------------------------------

Issue #75 §3 — the orchestration entry-point is :func:`build_decay_report`,
which calls :func:`compute_historical_ic_report` over a bounded window,
resamples per-commit IC entries to a monthly panel via
:func:`pillar_entries_to_monthly_panel`, and then runs
:func:`check_all_pillars`. The written artifact is the canonical
``frontend/public/data/decay_report.json``.

With the current ~1 week of git history and a 6-month forward-return
horizon, ``compute_historical_ic_report`` will return zero dated IC
entries — this is the EXPECTED honest outcome (``status="insufficient_history"``,
all pillars ``preliminary=True``, ``n_dates_with_ic=0``). The report
self-densifies over weeks/months of cron accumulation.

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
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import date as _date
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

IC_DECAY_THRESHOLD: float = 0.5  # 50% of historical mean
IC_DECAY_DURATION_MONTHS: int = 6  # consecutive months below threshold = alert
ROLLING_12M_MONTHS: int = 12
ROLLING_36M_MONTHS: int = 36

# Issue #75 §3 — minimum monthly observations before a pillar can alert.
# Below this, alert is FORCED False (honest suppression on thin history).
MIN_HISTORY_MONTHS: int = 12

# Issue #75 §3 — forward-return horizon in months (must match historical_ic.py).
IC_HORIZON_MONTHS: int = 6

# Issue #75 §3 — bounded look-back for the cron call: 39 months so the
# 36-month rolling window is fully populated while capping compute cost.
IC_LOOKBACK_MONTHS: int = 39

# Proposal F — IC half-life fitting.
# Minimum observations required before attempting a curve fit.  Mirrors
# MIN_HISTORY_MONTHS so the preliminary gate semantics are identical: when
# n < MIN_HALF_LIFE_FIT_MONTHS the returned half-life is None.
# Provenance: Di Mascio (2022) SSRN Working Paper 4023689 §4 fits alpha-decay
# curves on panels of ≥ 12 monthly IC observations; we adopt the same floor so
# the fit is not attempted on thin history.  Tier-3 citation: this module
# (compute/validation/ic_decay.py), first added Proposal F 2026-06-24.
MIN_HALF_LIFE_FIT_MONTHS: int = 12


class PillarHalfLife(NamedTuple):
    """Result of a per-pillar IC half-life fit.

    Attributes
    ----------
    half_life_months:
        Fitted half-life in months.  ``None`` when the pillar has fewer than
        ``MIN_HALF_LIFE_FIT_MONTHS`` (12) observations (preliminary — never
        fit on thin history; reuses the existing preliminary gate semantics).
        Also ``None`` when both curve fits fail to converge or produce a
        physically-meaningless result (e.g. negative half-life).
    fit_model:
        Which decay model produced the winning fit — ``"exponential"`` or
        ``"power"`` — based on the higher R² value.  ``None`` when
        ``half_life_months`` is ``None``.
    r_squared:
        R² of the winning fit.  ``None`` when ``half_life_months`` is
        ``None``.
    preliminary:
        ``True`` when fewer than ``MIN_HALF_LIFE_FIT_MONTHS`` monthly
        observations exist.  In that state ``half_life_months`` is always
        ``None`` — the honest label when history is too thin.
    """

    half_life_months: float | None
    fit_model: str | None
    r_squared: float | None
    preliminary: bool


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of determination R² (pure numpy, no scipy dependency).

    Returns the fraction of variance in ``y_true`` explained by ``y_pred``.
    Returns ``0.0`` when the total variance is zero (constant signal).
    """
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0.0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def _fit_exponential_half_life(
    t: np.ndarray, abs_ic: np.ndarray
) -> tuple[float | None, float | None]:
    """Fit |IC(t)| = A * exp(−λt) via log-linearisation and return
    (half_life_months, r_squared).

    The exponential model ``|IC| = A exp(−λt)`` is log-linearised to
    ``ln(|IC|) = ln(A) − λt`` and solved by least-squares.

    Provenance: McLean-Pontiff (2016) JF §3 characterises anomaly decay as
    roughly exponential OOS and post-publication; Di Mascio (2022) SSRN
    4023689 §4 also uses an exponential as the baseline model.

    Returns ``(None, None)`` when:
    - fewer than 2 valid points exist after filtering non-positive |IC|.
    - the design matrix is ill-conditioned (near-zero denominator).
    - the fitted λ ≤ 0 (growing signal — no decay half-life).
    """
    mask = abs_ic > 0
    if mask.sum() < 2:
        return None, None

    t_ok = t[mask].astype(float)
    y_ok = np.log(abs_ic[mask].astype(float))

    # OLS: [ln(A), −λ] = (XᵀX)⁻¹ Xᵀy where X = [1, t].
    n = len(t_ok)
    sum_t = float(np.sum(t_ok))
    sum_t2 = float(np.sum(t_ok ** 2))
    sum_y = float(np.sum(y_ok))
    sum_ty = float(np.sum(t_ok * y_ok))
    denom = n * sum_t2 - sum_t ** 2
    if abs(denom) < 1e-10:
        return None, None

    slope = (n * sum_ty - sum_t * sum_y) / denom  # = −λ
    lam = -slope
    if lam <= 0:
        return None, None

    half_life = math.log(2.0) / lam
    intercept = (sum_y - slope * sum_t) / n  # = ln(A)
    a = math.exp(intercept)

    y_pred = a * np.exp(-lam * t[mask].astype(float))
    r2 = _r_squared(abs_ic[mask].astype(float), y_pred)
    return half_life, r2


def _fit_power_half_life(
    t: np.ndarray, abs_ic: np.ndarray
) -> tuple[float | None, float | None]:
    """Fit |IC(t)| = A * t^(−β) via log-linearisation and return
    (half_life_months, r_squared).

    The power-law model ``|IC| = A t^(−β)`` is log-linearised to
    ``ln(|IC|) = ln(A) − β ln(t)`` and solved by least-squares over
    ``t ≥ 1`` (month index starting from 1 so ln(t) is defined).

    Provenance: Di Mascio (2022) SSRN Working Paper 4023689 §4 reports
    power-law fits explain alpha-decay slightly better than exponential
    (median adj-R² 0.48 vs 0.43 in their 80-factor panel).

    Half-life is defined implicitly as the t* where |IC(t*)| = |IC(1)| / 2:
        A * t*^(−β) = A / 2  →  t* = 2^(1/β).

    Returns ``(None, None)`` when:
    - fewer than 2 valid points exist after filtering t ≤ 0 and |IC| ≤ 0.
    - the design matrix is ill-conditioned.
    - β ≤ 0 (growing/flat signal — no decay half-life under power law).
    """
    # Shift t to 1-based so ln(t) is always defined for the first month.
    t_shifted = t.astype(float) + 1.0
    mask = (t_shifted > 0) & (abs_ic > 0)
    if mask.sum() < 2:
        return None, None

    ln_t = np.log(t_shifted[mask])
    ln_y = np.log(abs_ic[mask].astype(float))

    n = len(ln_t)
    sum_x = float(np.sum(ln_t))
    sum_x2 = float(np.sum(ln_t ** 2))
    sum_y = float(np.sum(ln_y))
    sum_xy = float(np.sum(ln_t * ln_y))
    denom = n * sum_x2 - sum_x ** 2
    if abs(denom) < 1e-10:
        return None, None

    slope = (n * sum_xy - sum_x * sum_y) / denom  # = −β
    beta = -slope
    if beta <= 0:
        return None, None

    half_life = 2.0 ** (1.0 / beta)
    intercept = (sum_y - slope * sum_x) / n
    a = math.exp(intercept)

    y_pred = a * t_shifted[mask] ** (-beta)
    r2 = _r_squared(abs_ic[mask].astype(float), y_pred)
    return half_life, r2


def fit_pillar_half_life(pillar_history: pd.DataFrame) -> PillarHalfLife:
    """Fit an IC decay half-life for a single pillar.

    Given a pillar's monthly IC panel (same DataFrame shape as
    :func:`check_pillar_decay` consumes: columns ``pillar``,
    ``year_month``, ``monthly_ic``), fit BOTH an exponential decay model
    AND a power-law decay model on the ``|IC|`` time series.  Return the
    half-life from whichever has the higher R².

    Di Mascio (2022) SSRN Working Paper 4023689 §4 found the power-law
    fits alpha decay slightly better than exponential (median adj-R² 0.48
    vs 0.43 across an 80-factor panel).  We evaluate both and pick the
    winner empirically per-pillar.

    **Preliminary gate**: when the pillar has fewer than
    ``MIN_HALF_LIFE_FIT_MONTHS`` (12) observations, returns
    ``PillarHalfLife(half_life_months=None, …, preliminary=True)``.
    This is the honest expected outcome with ~1 week of git IC history
    (``preliminary=True``, ``half_life_months=None``).

    **Graceful degradation**: if both fits fail (non-positive half-life,
    ill-conditioned matrix, or any exception), returns None half-life with
    ``preliminary=False`` (enough data existed, but the fit failed).

    Parameters
    ----------
    pillar_history:
        DataFrame with columns ``pillar``, ``year_month``, ``monthly_ic``.
        ``n_stocks`` is optional.

    Returns
    -------
    PillarHalfLife
    """
    required_columns = {"pillar", "year_month", "monthly_ic"}
    missing = required_columns - set(pillar_history.columns)
    if missing:
        return PillarHalfLife(
            half_life_months=None,
            fit_model=None,
            r_squared=None,
            preliminary=True,
        )

    df = pillar_history.copy()
    df["year_month"] = pd.to_datetime(df["year_month"])
    df = df.sort_values("year_month", kind="mergesort").reset_index(drop=True)
    n = len(df)

    if n < MIN_HALF_LIFE_FIT_MONTHS:
        return PillarHalfLife(
            half_life_months=None,
            fit_model=None,
            r_squared=None,
            preliminary=True,
        )

    abs_ic = df["monthly_ic"].abs().to_numpy(dtype=float)
    t = np.arange(n, dtype=float)

    try:
        exp_hl, exp_r2 = _fit_exponential_half_life(t, abs_ic)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Exponential half-life fit failed for pillar: %s", exc)
        exp_hl, exp_r2 = None, None

    try:
        pow_hl, pow_r2 = _fit_power_half_life(t, abs_ic)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Power-law half-life fit failed for pillar: %s", exc)
        pow_hl, pow_r2 = None, None

    # Select the winning model by R².  On a tie (e.g. both None), neither wins.
    if exp_r2 is not None and (pow_r2 is None or exp_r2 >= pow_r2):
        return PillarHalfLife(
            half_life_months=exp_hl,
            fit_model="exponential" if exp_hl is not None else None,
            r_squared=exp_r2 if exp_hl is not None else None,
            preliminary=False,
        )
    if pow_r2 is not None and pow_hl is not None:
        return PillarHalfLife(
            half_life_months=pow_hl,
            fit_model="power",
            r_squared=pow_r2,
            preliminary=False,
        )

    # Both fits failed or neither produced a valid half-life.
    return PillarHalfLife(
        half_life_months=None,
        fit_model=None,
        r_squared=None,
        preliminary=False,
    )


def build_pillar_half_lives(
    pillar_histories: dict[str, pd.DataFrame],
) -> dict[str, PillarHalfLife]:
    """Run :func:`fit_pillar_half_life` on every pillar.

    Pure function — no I/O.  The caller supplies the per-pillar monthly
    panel (same shape produced by :func:`pillar_entries_to_monthly_panel`).

    Returns a dict mapping pillar name → :class:`PillarHalfLife`.  Missing
    pillars (not in ``pillar_histories``) are absent from the result.
    Never raises — any per-pillar exception is caught and logged; the
    result for that pillar will have ``half_life_months=None``.
    """
    results: dict[str, PillarHalfLife] = {}
    for pillar_name, hist in pillar_histories.items():
        if "pillar" not in hist.columns:
            hist = hist.assign(pillar=pillar_name)
        try:
            results[pillar_name] = fit_pillar_half_life(hist)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Half-life fit failed for pillar=%s (non-fatal): %s",
                pillar_name,
                exc,
            )
            results[pillar_name] = PillarHalfLife(
                half_life_months=None,
                fit_model=None,
                r_squared=None,
                preliminary=False,
            )
    return results


@dataclass
class ICDecayReport:
    """Per-pillar decay status snapshot.

    The ``alert`` flag is the canonical "this pillar is decayed" signal.
    When ``alert=True``, the caller should:
    1. Log to PHASE_STATUS.md
    2. Consider blend-weight retune (if alert persists 9+ months)
    3. Consider composite-weight zero (if alert persists 12+ months)

    ``preliminary=True`` means fewer than ``MIN_HISTORY_MONTHS`` monthly
    observations have accumulated — ``alert`` is always ``False`` in this
    state regardless of individual IC values (honest suppression).
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
    preliminary: bool = field(default=False)
    """True when n_observations < MIN_HISTORY_MONTHS; alert is suppressed."""


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
            preliminary=n < MIN_HISTORY_MONTHS,
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

    # Honest suppression: never alert on thin history (< MIN_HISTORY_MONTHS).
    is_preliminary = n < MIN_HISTORY_MONTHS
    fires = (consecutive_below >= duration_months) and not is_preliminary

    return ICDecayReport(
        pillar=pillar,
        rolling_12m_ic=rolling_12m,
        rolling_36m_ic=rolling_36m,
        historical_mean_ic=historical_mean,
        decay_ratio=decay_ratio,
        months_below_threshold=consecutive_below,
        alert=fires,
        n_observations=n,
        preliminary=is_preliminary,
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
    horizon_months: int = IC_HORIZON_MONTHS,
    min_history_months: int = MIN_HISTORY_MONTHS,
    status: str = "insufficient_history",
    n_dates_with_ic: int = 0,
) -> None:
    """Write ``frontend/public/data/decay_report.json`` with the per-pillar
    status + list of alerted pillars.

    The frontend may surface "X pillars decaying" badge on the about /
    methodology page in a future PR — schema is intentionally simple.

    Issue #75 §3 additive fields (backward-compatible — old keys unchanged):
    - ``horizon_months``: forward-return horizon used for IC computation.
    - ``min_history_months``: threshold below which a pillar is ``preliminary``.
    - ``status``: top-level gating result ("insufficient_history" |
      "monitoring" | "alert").
    - ``n_dates_with_ic``: number of distinct dates that produced at least
      one pillar IC value in the historical window.
    Per-pillar additive field: ``preliminary`` (bool) — already a field on
    ICDecayReport; surfaces via asdict(r) without any extra code.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_months": int(horizon_months),
        "threshold": float(threshold),
        "duration_months": int(duration_months),
        "min_history_months": int(min_history_months),
        "status": status,
        "n_dates_with_ic": int(n_dates_with_ic),
        "pillars": [asdict(r) for r in reports],
        "anomalies_alerted": [r.pillar for r in reports if r.alert],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Issue #75 §3 — per-commit → monthly panel adapter
# ---------------------------------------------------------------------------

def pillar_entries_to_monthly_panel(
    entries: Sequence,
) -> dict[str, pd.DataFrame]:
    """Resample per-commit PillarICEntry objects to a monthly panel.

    Takes the ``.entries`` list of a :class:`~compute.validation.historical_ic.HistoricalICReport`
    (or any sequence of objects with ``.date``, ``.pillar``, ``.ic``,
    ``.n_tickers`` attributes) and groups by (pillar, calendar month).

    For each (pillar, month):
    - ``monthly_ic`` = mean IC across all commits in that month.
    - ``n_stocks`` = mean n_tickers across commits in that month (rounded
      to int; for the common case of one commit per month it equals n_tickers
      exactly).

    Returns a dict mapping ``pillar_name → DataFrame`` with columns
    ``(pillar, year_month, monthly_ic, n_stocks)``.  Empty sequences
    or pillars with no entries return an empty dict (caller downstream
    handles via :func:`check_all_pillars` graceful skip).
    """
    if not entries:
        return {}

    rows = []
    for e in entries:
        try:
            rows.append({
                "pillar": str(e.pillar),
                "date": e.date,
                "ic": float(e.ic),
                "n_tickers": int(e.n_tickers),
            })
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed entry in pillar_entries_to_monthly_panel: %s", exc)
            continue

    if not rows:
        return {}

    df = pd.DataFrame(rows)
    # Convert to month-end period for stable grouping.
    df["year_month"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp("M")

    pillar_panels: dict[str, pd.DataFrame] = {}
    for pillar_name, group in df.groupby("pillar"):
        monthly = (
            group.groupby("year_month")
            .agg(monthly_ic=("ic", "mean"), n_stocks=("n_tickers", "mean"))
            .reset_index()
        )
        monthly["n_stocks"] = monthly["n_stocks"].round().astype(int)
        monthly["pillar"] = str(pillar_name)
        monthly = monthly.sort_values("year_month", kind="mergesort").reset_index(drop=True)
        pillar_panels[str(pillar_name)] = monthly

    return pillar_panels


# ---------------------------------------------------------------------------
# Issue #75 §3 / Proposal A #605 — shared IC git-walk helper
# ---------------------------------------------------------------------------

class _WalkICResult:
    """Internal value object from :func:`walk_ic_history`."""

    __slots__ = ("entries", "panels", "n_dates_with_ic")

    def __init__(
        self,
        entries: list,
        panels: dict[str, pd.DataFrame],
        n_dates_with_ic: int,
    ) -> None:
        self.entries = entries
        self.panels = panels
        self.n_dates_with_ic = n_dates_with_ic


def walk_ic_history(
    *,
    end_date: _date | None = None,
    lookback_months: int = IC_LOOKBACK_MONTHS,
    horizon_months: int = IC_HORIZON_MONTHS,
) -> _WalkICResult:
    """Walk the git IC history ONCE and return entries + monthly panels.

    Proposal A #605 consolidation: both the IC-decay monitor and the IC
    half-life monitor previously called ``compute_historical_ic_report``
    independently, performing TWO git-walks over the same window.  This
    helper performs ONE walk and returns the shared result so both can
    consume it without re-reading git.

    Additionally consumed by Proposal A's ``build_ic_weights`` (the
    ``preliminary`` state of each :class:`ICDecayReport` is the gate for
    the shrinkage weight).

    This function NEVER raises — any failure in the historical-IC walk
    (git, network, data) is caught and logged; the degraded result is
    ``entries=[], panels={}, n_dates_with_ic=0``.  The caller's
    downstream behaviour is byte-identical to the pre-#605 degraded path.

    C5 binding condition: the wrapping try/except here guarantees that a
    git failure → ``entries = []`` → ``build_ic_weights`` returns
    ``degenerate=True`` → ``blend_weights`` returns ``w0`` → composite
    is byte-identical.  The cron is NEVER blocked.

    Parameters
    ----------
    end_date:
        Last date for the IC window.  Defaults to today (UTC).
    lookback_months:
        Window size in months.  Default ``IC_LOOKBACK_MONTHS`` (39).
    horizon_months:
        Forward-return horizon in months.  Default ``IC_HORIZON_MONTHS`` (6).

    Returns
    -------
    _WalkICResult
        ``.entries`` — flat list of :class:`~compute.validation.historical_ic.PillarICEntry`.
        ``.panels`` — per-pillar monthly panel dicts (same shape as
        :func:`pillar_entries_to_monthly_panel` output).
        ``.n_dates_with_ic`` — number of distinct dates that produced IC.
    """
    from compute.validation.historical_ic import (
        DEFAULT_PILLARS,
        compute_historical_ic_report,
    )

    if end_date is None:
        end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=int(lookback_months * 30.5))

    entries: list = []
    n_dates_with_ic: int = 0

    # C5: try/except → degrade to empty on ANY git/network/data failure.
    try:
        report = compute_historical_ic_report(
            start_date=start_date,
            end_date=end_date,
            horizon_months=horizon_months,
            pillars=DEFAULT_PILLARS,
        )
        entries = report.entries
        n_dates_with_ic = report.n_dates_with_ic
        logger.info(
            "walk_ic_history: walked %d commits, %d dates with IC",
            report.n_dates_walked,
            n_dates_with_ic,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "walk_ic_history: compute_historical_ic_report failed — "
            "degrading to empty entries. Error: %s",
            exc,
        )
        entries = []
        n_dates_with_ic = 0

    # Resample to monthly panel.
    panels: dict[str, pd.DataFrame] = {}
    try:
        panels = pillar_entries_to_monthly_panel(entries)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "walk_ic_history: pillar_entries_to_monthly_panel failed — "
            "degrading to empty panels. Error: %s",
            exc,
        )
        panels = {}

    return _WalkICResult(entries=entries, panels=panels, n_dates_with_ic=n_dates_with_ic)


# ---------------------------------------------------------------------------
# Issue #75 §3 — high-level cron entry-point
# ---------------------------------------------------------------------------

def build_decay_report(
    *,
    end_date: _date | None = None,
    lookback_months: int = IC_LOOKBACK_MONTHS,
    horizon_months: int = IC_HORIZON_MONTHS,
    threshold: float = IC_DECAY_THRESHOLD,
    duration_months: int = IC_DECAY_DURATION_MONTHS,
    min_history_months: int = MIN_HISTORY_MONTHS,
    # Proposal A #605 — backward-compatible injected-panels path.
    # When ``panels`` is not None, the git-walk is SKIPPED and the
    # caller-supplied monthly panel is used directly.  This allows the
    # cron to call ``walk_ic_history`` ONCE and inject the result into
    # both ``build_decay_report`` AND ``build_pillar_half_lives``,
    # eliminating the duplicate git-walk that existed pre-#605.
    # ALL existing callers pass panels=None (the default), so this is
    # backward-compatible: existing behaviour is byte-identical.
    panels: dict[str, pd.DataFrame] | None = None,
    entries: list | None = None,
    n_dates_with_ic: int | None = None,
) -> tuple[list[ICDecayReport], str, int]:
    """Compute IC-decay reports for all 10 canonical pillars.

    Calls :func:`compute_historical_ic_report` over a bounded window
    (end=today, start=today − ``lookback_months``), resamples per-commit
    entries to a monthly panel via :func:`pillar_entries_to_monthly_panel`,
    and runs :func:`check_all_pillars`.

    Returns ``(reports, status, n_dates_with_ic)`` where:

    - ``reports``: one :class:`ICDecayReport` per canonical pillar, even
      when history is empty (n_observations=0, preliminary=True, alert=False).
      Always 10 entries — the frontend always renders a complete table.
    - ``status``: top-level string:
      - ``"insufficient_history"`` — every pillar has fewer than
        ``duration_months`` observations, OR no pillar produced any IC.
      - ``"alert"`` — at least one non-preliminary pillar has ``alert=True``.
      - ``"monitoring"`` — at least one non-preliminary pillar has
        sufficient history and no alert has fired.
    - ``n_dates_with_ic``: total commit-dates that produced any IC value.

    This function NEVER raises — any failure in the historical_ic walk
    (git, network, data) is caught and logged; the honest degraded result
    (all pillars empty/preliminary) is returned.

    Proposal A #605 backward-compatible injection path
    ---------------------------------------------------
    Pass ``panels=``, ``entries=``, ``n_dates_with_ic=`` from a prior
    :func:`walk_ic_history` call to reuse the git-walk result (NO second
    walk).  When any of these are ``None`` (the default), the function
    self-walks exactly as before — existing callers and tests are
    byte-identical.
    """
    from compute.validation.historical_ic import (
        DEFAULT_PILLARS,
        compute_historical_ic_report,
    )

    # --- Determine panels / n_dates_with_ic ---------------------------------
    # If the caller injected pre-computed panels (Proposal A #605 path),
    # use them directly and skip the git-walk.  Otherwise self-walk.
    if panels is not None:
        # Injected-panels path: caller already walked; use as-is.
        _panels: dict[str, pd.DataFrame] = panels
        _n_dates: int = n_dates_with_ic if n_dates_with_ic is not None else 0
        # Compute n_dates from entries if supplied and n_dates_with_ic not.
        if n_dates_with_ic is None and entries is not None:
            try:
                _n_dates = len({e.date for e in entries})
            except Exception:  # noqa: BLE001
                _n_dates = 0
    else:
        # Self-walk path (legacy / existing callers).
        if end_date is None:
            end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=int(lookback_months * 30.5))

        # Attempt the git-walk + forward-return computation.
        try:
            report = compute_historical_ic_report(
                start_date=start_date,
                end_date=end_date,
                horizon_months=horizon_months,
                pillars=DEFAULT_PILLARS,
            )
            _entries = report.entries
            _n_dates = report.n_dates_with_ic
            logger.info(
                "IC-decay build: walked %d commits, %d dates with IC",
                report.n_dates_walked,
                _n_dates,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "IC-decay build: compute_historical_ic_report failed — "
                "degrading to empty panel. Error: %s",
                exc,
            )
            _entries = []
            _n_dates = 0

        # Resample to monthly panel.
        try:
            _panels = pillar_entries_to_monthly_panel(_entries)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "IC-decay build: pillar_entries_to_monthly_panel failed — "
                "degrading to empty panel. Error: %s",
                exc,
            )
            _panels = {}

    panels = _panels
    n_dates_with_ic_actual = _n_dates  # rename to avoid shadowing param

    # Run check_all_pillars over whatever panel we have.
    try:
        found_reports = check_all_pillars(
            panels,
            threshold=threshold,
            duration_months=duration_months,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "IC-decay build: check_all_pillars failed — degrading to empty reports. Error: %s",
            exc,
        )
        found_reports = []

    # Build a by-pillar index of whatever came back.
    by_pillar = {r.pillar: r for r in found_reports}

    # Ensure ALL 10 canonical pillars appear, even with no history.
    all_reports: list[ICDecayReport] = []
    for pillar_name in DEFAULT_PILLARS:
        if pillar_name in by_pillar:
            all_reports.append(by_pillar[pillar_name])
        else:
            # Empty history → preliminary=True, alert=False.
            all_reports.append(
                ICDecayReport(
                    pillar=pillar_name,
                    rolling_12m_ic=0.0,
                    rolling_36m_ic=0.0,
                    historical_mean_ic=0.0,
                    decay_ratio=0.0,
                    months_below_threshold=0,
                    alert=False,
                    n_observations=0,
                    preliminary=True,
                )
            )

    # Compute top-level status.
    non_preliminary = [r for r in all_reports if not r.preliminary]
    if not non_preliminary or n_dates_with_ic_actual == 0:
        status = "insufficient_history"
    elif any(r.alert for r in non_preliminary):
        status = "alert"
    else:
        # Any non-preliminary pillar already cleared the preliminary gate
        # (n_observations >= MIN_HISTORY_MONTHS = 12 >= duration_months), so a
        # non-preliminary, non-alerting pillar is a live, healthy monitor.
        status = "monitoring"

    logger.info(
        "IC-decay status=%s, n_dates_with_ic=%d, alerted_pillars=%s",
        status,
        n_dates_with_ic_actual,
        [r.pillar for r in all_reports if r.alert],
    )
    return all_reports, status, n_dates_with_ic_actual


__all__ = [
    "IC_DECAY_DURATION_MONTHS",
    "IC_DECAY_THRESHOLD",
    "IC_HORIZON_MONTHS",
    "IC_LOOKBACK_MONTHS",
    "MIN_HALF_LIFE_FIT_MONTHS",
    "MIN_HISTORY_MONTHS",
    "ICDecayReport",
    "PillarHalfLife",
    "build_decay_report",
    "build_pillar_half_lives",
    "check_all_pillars",
    "check_pillar_decay",
    "emit_decay_report",
    "fit_pillar_half_life",
    "pillar_entries_to_monthly_panel",
    "walk_ic_history",
]
