"""Shrinkage-composite weight blending — Proposal A.

Background
----------
QuantRank's Phase-3 composite uses a fixed ``PHASE3_EFFECTIVE_WEIGHTS`` vector
derived from subjective + literature-informed priors.  Proposal A adds a
data-adaptive shrinkage layer: each epoch we have an IC estimate
``rolling_12m_ic`` per pillar (from the IC-decay monitor); we use it to
*nudge* the weight vector toward the IC-implied weight vector
``w_IC`` while retaining the prior ``w0`` as a shrinkage target.

The formula follows Timmermann (2006) "Forecast Combinations" §3 (Handbook
of Economic Forecasting) — shrink toward the prior (``w0``) and let the data
only move weights insofar as the evidence is reliable:

    λ_p = 1/(1 + n_p / τ)      ← shrinkage factor for pillar p
    w_p = λ_p · w0_p + (1 − λ_p) · w_IC_p

where ``n_p`` is the months of IC history available for pillar ``p`` and
``τ`` (``SHRINKAGE_TAU_MONTHS``) is the prior-persistence half-life.

The IC-implied weight component ``w_IC`` follows the signal-weighting
principle from Grinold and Kahn (2000) "Active Portfolio Management"
Ch. 4 (IR = IC × √breadth): weight more heavily the factors whose
realized IC is highest.

Ledoit-Wolf (2004) "A well-conditioned estimator for large-dimensional
covariance matrices" (*Journal of Multivariate Analysis* 88(2)) is
cited here as the **shrinkage principle only** — the idea that shrinking
an empirical estimate toward a structured prior (the identity / prior w0)
reduces estimation noise.  This module does NOT implement a
covariance-shrinkage operator; the application is to the 1-D weight vector,
not a covariance matrix.

Identity-at-launch (safety property)
--------------------------------------
With ``SHRINKAGE_LAMBDA_PIN = 1.0`` AND every pillar currently preliminary
(thin IC history — ``ICDecayReport.preliminary == True`` for all pillars),
the blend returns ``w0`` via two independent guards:

1. **Pin guard** — ``blend_weights`` forces λ_p = 1.0 for all pillars in
   ``preliminary_mask``, so w_p = w0_p regardless of ``w_IC``.
2. **Degenerate guard** — ``build_ic_weights`` sets ``w_IC := w0`` when all
   raw IC signals are zero (``Σraw == 0``), so the blend trivially returns
   ``w0`` even without the pin guard.

Both guards must hold simultaneously before this composite is byte-identical.
Neither guard is removed without the pin-lift gate below.

``SHRINKAGE_TAU_MONTHS`` calibration note (C2 binding condition)
----------------------------------------------------------------
``SHRINKAGE_TAU_MONTHS = 24.0`` is a **Tier-2/3 gut-feel calibration**.
The parameter is inert-at-launch: while the pin is 1.0 OR every pillar is
preliminary, ``n_p`` is either 0 or irrelevant (λ_p forced to 1.0), so
``τ`` never touches the blended weight.  It only bites once:

  (a) a pillar clears ``MIN_HISTORY_MONTHS`` (12) in the decay monitor, AND
  (b) ``SHRINKAGE_LAMBDA_PIN`` is set to ``None`` (pin lifted).

The Proposal-F (#604 merged) ``build_pillar_half_lives`` output will supply
``τ_p`` per-pillar via the empirical half-life curve.  That follow-up (the
``τ_p`` re-derivation) supersedes this scalar gut-feel constant once
sufficient IC history is available (≥ 24 months per active pillar, A3-i
gate below).

Pre-registered pin-lift gate (A3-i / A3-ii)
---------------------------------------------
These conditions MUST ALL be met before setting ``SHRINKAGE_LAMBDA_PIN = None``:

Gate conditions from §5 of the Proposal-A design brief:
  - ≥ 1 full cron of observation at the new weight vector (shadow comparison).
  - Methodology-scientist RATIFY-PROCEED on the blended IC distribution.
  - Defense-layer-auditor confirms BYTE-IDENTICAL canary holds on ≥ 2 crons.
  - Data-scientist OOS horse-race passes (A3-ii below).

PLUS:

**A3-i** — Minimum n floor: ≥ 24 monthly IC observations per active pillar.
  (n = 12 clears the preliminary label but is too thin to move weight reliably.)

**A3-ii** — Timmermann OOS horse-race: compute blended IC vs fixed-w0 IC on
  the existing purged-embargo holdout (``meta.validation`` ``in_sample=false``
  block).  Lift the pin ONLY when:
      blended_IC > fixed_w0_IC  by > 1 SE of the IC difference
  If this condition is not met, keep ``SHRINKAGE_LAMBDA_PIN = 1.0``
  permanently and ship the 1/N prior instead.

  Rationale: Timmermann (2006) §5 shows that forecast-combination gains over
  the best individual model are most reliable when the combination strictly
  beats the benchmark OOS.  Equal-weighting (1/N) is the fallback per the
  same literature when no combination gains emerge on held-out data.

References
----------
- Timmermann, A. (2006). Forecast combinations. In G. Elliott, C. W. J.
  Granger, & A. Timmermann (Eds.), *Handbook of Economic Forecasting* (Vol. 1,
  §3, pp. 135–196). Elsevier.
- Grinold, R. C., & Kahn, R. N. (2000). *Active Portfolio Management* (2nd ed.,
  Ch. 4). McGraw-Hill.
- Ledoit, O., & Wolf, M. (2004). A well-conditioned estimator for
  large-dimensional covariance matrices. *Journal of Multivariate Analysis*,
  88(2), 365–411.  [Cited as the shrinkage PRINCIPLE only — not a covariance
  port.]
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (C2 binding condition: docstring above explains Tier-2/3 status)
# ---------------------------------------------------------------------------

SHRINKAGE_TAU_MONTHS: float = 24.0
"""Prior-persistence half-life in months.

Tier-2/3 gut-feel calibration — inert-at-launch (see module docstring §C2).
τ only bites once a pillar clears MIN_HISTORY_MONTHS=12 AND the pin is lifted.
The Proposal-F follow-up will supply per-pillar τ_p from build_pillar_half_lives.
"""

SHRINKAGE_LAMBDA_PIN: float = 1.0
"""Identity pin for obs-first safety.

Set to 1.0 (identity) at launch — means every pillar's blend weight equals w0
regardless of IC evidence.  The pin is NEVER lifted without all A3-i/A3-ii gates.
Set to None to engage the schedule; this requires a full methodology-scientist
RATIFY-PROCEED + data-scientist OOS horse-race pass (see module docstring).
"""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def compute_shrinkage_lambda(n_months: float, tau: float = SHRINKAGE_TAU_MONTHS) -> float:
    """Compute per-pillar shrinkage factor λ = 1 / (1 + n / τ).

    Parameters
    ----------
    n_months:
        Number of months of IC history available for the pillar.  Must be ≥ 0.
        Values ≤ 0 (no history) return 1.0 (full prior — do not move weight).
    tau:
        Prior-persistence half-life in months.  Default is
        ``SHRINKAGE_TAU_MONTHS = 24.0``.

    Returns
    -------
    float in [0.0, 1.0].
        - 1.0 when n_months ≤ 0 (full prior — no evidence yet).
        - Approaches 0.0 as n_months → ∞ (full IC-implied weight).
        - 0.5 at n_months == tau (equal blend of prior and IC-implied).

    Examples
    --------
    >>> compute_shrinkage_lambda(0)
    1.0
    >>> compute_shrinkage_lambda(24)  # n == τ → 0.5
    0.5
    >>> compute_shrinkage_lambda(72)  # n == 3τ → 0.25
    0.25
    """
    if n_months <= 0:
        return 1.0
    lam = 1.0 / (1.0 + n_months / tau)
    # Clamp to [0, 1] as a safety net (both terms are non-negative so this
    # is numerically guaranteed, but explicit clamping guards against
    # floating-point edge cases).
    return float(min(1.0, max(0.0, lam)))


def build_ic_weights(
    decay_reports: list,
    w0: dict[str, float],
    active_pillars: tuple[str, ...],
) -> tuple[dict[str, float], frozenset[str], bool]:
    """Build the IC-implied weight vector from per-pillar decay reports.

    Reads ``ICDecayReport.preliminary`` (C1 binding condition: never
    inline ``n < 12``).  Preliminary pillars are zeroed in the raw IC
    signal and added to the ``preliminary_mask`` so ``blend_weights``
    can force λ_p = 1.0 for them.

    Parameters
    ----------
    decay_reports:
        List of ``ICDecayReport`` objects (from
        ``compute.validation.ic_decay.build_decay_report``).  Only
        reports whose ``.pillar`` is in ``active_pillars`` are used.
    w0:
        Prior weight dict (e.g. ``PHASE3_EFFECTIVE_WEIGHTS``).  Keys =
        active pillar names; values = weights that sum to 1.0.
    active_pillars:
        Tuple of pillar names to include.  Pillars absent from both
        ``decay_reports`` and ``w0`` are silently ignored.

    Returns
    -------
    w_ic : dict[str, float]
        IC-implied weight vector.  When ``degenerate=True``, this equals
        ``w0`` (the caller must pass the prior into ``blend_weights``
        unmodified).
    preliminary_mask : frozenset[str]
        Pillar names whose ``ICDecayReport.preliminary == True``.
        ``blend_weights`` forces λ_p = 1.0 for every pillar in this set
        so the blend returns w0_p for those pillars regardless of λ or w_ic.
    degenerate : bool
        ``True`` when the IC-implied weight vector cannot be meaningfully
        constructed (all positive-IC signals are zero or all pillars are
        preliminary).  When ``True``, ``w_ic`` is returned as ``w0`` so the
        upstream caller never divides by zero or reads a NaN weight.
    """
    # Build a lookup: pillar → ICDecayReport.
    report_by_pillar: dict[str, object] = {}
    for r in decay_reports:
        try:
            report_by_pillar[r.pillar] = r
        except AttributeError:
            continue

    preliminary_mask_list: list[str] = []
    raw: dict[str, float] = {}

    for p in active_pillars:
        report = report_by_pillar.get(p)
        if report is None:
            # No report for this pillar → treat as preliminary (C1: read the
            # `preliminary` field; absence == preliminary by definition).
            preliminary_mask_list.append(p)
            raw[p] = 0.0
            continue

        # C1: read the field — never inline n < 12.
        if report.preliminary:
            preliminary_mask_list.append(p)
            raw[p] = 0.0
        else:
            # raw_p = max(rolling_12m_ic, 0) — negative IC gets zero weight.
            raw[p] = max(float(report.rolling_12m_ic), 0.0)

    preliminary_mask = frozenset(preliminary_mask_list)

    # Normalize over non-preliminary positive-IC pillars.
    raw_sum = sum(v for p, v in raw.items() if p not in preliminary_mask)

    if raw_sum <= 0.0:
        # Degenerate: all non-preliminary IC is zero or negative.
        # Return w0 as the IC-implied vector so blend_weights returns w0.
        logger.debug(
            "build_ic_weights: Σraw=%.4f ≤ 0 (all IC ≤ 0 or all preliminary) — "
            "degenerate=True, w_ic := w0",
            raw_sum,
        )
        return dict(w0), preliminary_mask, True

    w_ic: dict[str, float] = {}
    for p in active_pillars:
        if p in preliminary_mask:
            # Preliminary pillars get zero IC-implied weight (they're pinned
            # to w0 via the mask anyway, but this makes w_ic internally consistent).
            w_ic[p] = 0.0
        else:
            w_ic[p] = raw[p] / raw_sum

    return w_ic, preliminary_mask, False


def blend_weights(
    w0: dict[str, float],
    w_ic: dict[str, float],
    lam: float,
    preliminary_mask: frozenset[str],
    lambda_pin: float | None = SHRINKAGE_LAMBDA_PIN,
) -> dict[str, float]:
    """Blend the prior ``w0`` with the IC-implied ``w_ic`` per pillar.

    For each pillar ``p``:

        if p ∈ preliminary_mask:
            λ_p = 1.0   (full prior — not enough IC history)
        elif lambda_pin is not None:
            λ_p = lambda_pin   (obs-first identity pin)
        else:
            λ_p = lam   (use the schedule)

        w_p = λ_p * w0[p] + (1 - λ_p) * w_ic[p]

    After blending, the weight vector is renormalized to sum exactly to 1.0.

    Parameters
    ----------
    w0:
        Prior weight dict.  Must cover every key in ``w_ic``.
    w_ic:
        IC-implied weight dict.  Must cover every key in ``w0``.
    lam:
        Schedule-derived shrinkage factor (from ``compute_shrinkage_lambda``).
        Only used when ``lambda_pin is None`` and ``p ∉ preliminary_mask``.
    preliminary_mask:
        Pillars whose λ_p is forced to 1.0 (full prior) regardless of
        ``lambda_pin`` or ``lam``.  From ``build_ic_weights``.
    lambda_pin:
        If not None, every non-preliminary pillar uses this fixed λ_p instead
        of the schedule ``lam``.  Default is ``SHRINKAGE_LAMBDA_PIN = 1.0``
        (identity at launch).

    Returns
    -------
    dict[str, float]
        Blended weight vector, renormalized to sum to exactly 1.0 within 1e-9.

    Raises
    ------
    ValueError
        When the blended vector cannot be renormalized (sum ≤ 0 — structurally
        impossible when w0 sums to 1.0 and λ ∈ [0,1], but guarded explicitly).
    """
    pillars = list(w0.keys())
    blended: dict[str, float] = {}

    for p in pillars:
        w0_p = float(w0.get(p, 0.0))
        w_ic_p = float(w_ic.get(p, 0.0))

        if p in preliminary_mask:
            lam_p = 1.0
        elif lambda_pin is not None:
            lam_p = float(lambda_pin)
        else:
            lam_p = float(lam)

        blended[p] = lam_p * w0_p + (1.0 - lam_p) * w_ic_p

    # Renormalize to 1.0.
    total = sum(blended.values())
    if total <= 0.0:
        raise ValueError(
            f"blend_weights: blended sum={total:.6f} ≤ 0 — cannot renormalize. "
            "This should be structurally impossible when w0 sums to 1.0 and "
            "λ ∈ [0, 1]."
        )

    renormed: dict[str, float] = {p: v / total for p, v in blended.items()}

    # C-canary: assert sum to 1.0 within 1e-9 BEFORE returning.
    actual_sum = sum(renormed.values())
    if abs(actual_sum - 1.0) > 1e-9:
        raise ValueError(
            f"blend_weights: renormalized sum={actual_sum:.15f} deviates "
            "from 1.0 by more than 1e-9 — floating-point error exceeded tolerance."
        )

    return renormed


__all__ = [
    "SHRINKAGE_LAMBDA_PIN",
    "SHRINKAGE_TAU_MONTHS",
    "blend_weights",
    "build_ic_weights",
    "compute_shrinkage_lambda",
]
