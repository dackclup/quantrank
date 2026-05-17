"""Manipulation Index 0-100 composite (PR 4.5f).

Pure-function rollup of the Phase 4.5a-d earnings-manipulation defense
cluster into a single 0-100 risk index, plus a 10-point soft penalty
that derives ``composite_score_adjusted`` from the original
``composite_score``.

Per the locked design in ``WORKFLOW.md`` §"PHASE 4.5 → 4.5f":

- Per-flag additive weights summed and clipped to ``[0, 100]``. The
  weight table leaves headroom for the 4.5e Form-4 flags
  (``insider_sell_cluster`` + ``c_suite_unusual_sell``) so a follow-up
  PR can plug them in additively without re-calibrating the existing
  index distribution.
- ``composite_score_adjusted = composite_score − 0.5 ×
  (manipulation_index / 100) × 20``. Max penalty at index = 100 is
  **10 composite points**. The original ``composite_score`` is
  preserved untouched per SKILL.md Rule 9 (audit trail).
- **Rank source stays the raw composite** per SKILL.md Rule 16
  ("composite rank unchanged"). The adjusted score is informational —
  surfaced as the headline number on the detail-page Manipulation
  Risk card, but ``StockSummary.rank`` is still computed from the raw
  composite. Re-evaluate in Phase 5 once walk-forward backtest
  evidence is available.

Weight calibration: active vetoes (high PPV) get 15-20 pts each,
soft annotates 3-8 pts. A worst-case stock firing all currently-active
4.5a-d flags lands near the cap; a stock with only the lightest
Tier-3 soft flag lands at 3 — well below the penalty floor where the
``composite_score_adjusted`` deduction starts mattering (penalty at
index=3 is 0.3 composite points, rounding noise).

References: Sloan 1996 *TAR*, Beneish 1999 *FAJ*, Dechow et al. 2011
*CAR*, Roychowdhury 2006 *JAE*, Burgstahler-Dichev 1997 *JAE*,
Hennes-Leone-Miller 2008 *TAR*, Bartov-Lai-Yeung 2002 *JAR*,
Schroeder 2024 SSRN.
"""

from __future__ import annotations

from typing import Final

# --- Weight table ----------------------------------------------------------
#
# Each entry maps a flag identifier (as it appears in ``StockSummary.
# risk_flags`` or ``valuation_warnings``) to the points it contributes
# to the manipulation index. Sum of all currently-active 4.5a-d flag
# weights = 132; clipping at 100 means a worst-case stock saturates
# before all flags are required (intentional — 5+ flags is already a
# strong signal). Phase 4.5e adds two reserved-slot weights.

# Active vetoes — high-PPV signals already suppressing entered_top5.
SLOAN_WEIGHT: Final[float] = 20.0
BENEISH_VETO_WEIGHT: Final[float] = 20.0
DECHOW_VETO_WEIGHT: Final[float] = 20.0
NON_RELIANCE_WEIGHT: Final[float] = 15.0

# Joint gate — Sloan + Beneish-high + Dechow-high co-fire.
TRIPLE_FLAG_WEIGHT: Final[float] = 10.0

# Annotates — medium-confidence forensic / disclosure signals.
REM_SUSPECT_WEIGHT: Final[float] = 8.0
RESTATEMENT_HISTORY_WEIGHT: Final[float] = 5.0
LATE_FILING_WEIGHT: Final[float] = 5.0
ACCRUALS_MOMENTUM_WEIGHT: Final[float] = 5.0
LOSS_AVOIDANCE_WEIGHT: Final[float] = 5.0

# Tier-3 soft annotates — Beneish/Dechow in the warning band (M ∈
# [−2.22, −1.78] or F ∈ [2.45, 3.0]) but below the active-veto threshold.
BENEISH_HIGH_WEIGHT: Final[float] = 3.0
DECHOW_HIGH_WEIGHT: Final[float] = 3.0

# Reserved 4.5e slots — uncomment when those flags land. Listed here so
# the 4.5e follow-up PR is a one-line uncomment + a new entry in
# FLAG_WEIGHTS, no calibration cascade.
INSIDER_SELL_CLUSTER_WEIGHT_RESERVED: Final[float] = 10.0
C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED: Final[float] = 5.0

#: Authoritative flag → weight mapping. Iteration order is intentional:
#: heavier weights first so a debug-printed dict reads top-down by
#: severity. Lookups are O(1) — order doesn't affect computation.
FLAG_WEIGHTS: Final[dict[str, float]] = {
    "sloan_accruals_top_decile": SLOAN_WEIGHT,
    "beneish_manipulation_veto": BENEISH_VETO_WEIGHT,
    "dechow_manipulation_veto": DECHOW_VETO_WEIGHT,
    "non_reliance_filing": NON_RELIANCE_WEIGHT,
    "manipulation_triple_flag": TRIPLE_FLAG_WEIGHT,
    "rem_suspect": REM_SUSPECT_WEIGHT,
    "restatement_history": RESTATEMENT_HISTORY_WEIGHT,
    "late_filing_notification": LATE_FILING_WEIGHT,
    "accruals_momentum_high": ACCRUALS_MOMENTUM_WEIGHT,
    "loss_avoidance_pattern": LOSS_AVOIDANCE_WEIGHT,
    "beneish_high": BENEISH_HIGH_WEIGHT,
    "dechow_high": DECHOW_HIGH_WEIGHT,
    # "insider_sell_cluster": INSIDER_SELL_CLUSTER_WEIGHT_RESERVED,
    # "c_suite_unusual_sell": C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED,
}

#: Hard ceiling on the rolled-up index — Roychowdhury-style
#: saturation. A stock firing 5+ flags is already maximally suspect;
#: no need to differentiate 5-flag from 6-flag at the headline level.
MAX_INDEX: Final[float] = 100.0

#: Penalty multiplier — see module docstring. Penalty at full
#: saturation (index=100) = ``PENALTY_MULTIPLIER × MAX_INDEX / 100 ×
#: PENALTY_BUDGET`` = ``0.5 × 1.0 × 20`` = **10 composite points**.
PENALTY_MULTIPLIER: Final[float] = 0.5
PENALTY_BUDGET: Final[float] = 20.0


def compute_manipulation_index(
    risk_flags: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    valuation_warnings: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
) -> float:
    """Roll up flag membership into a 0-100 manipulation index.

    Iterates the union of ``risk_flags`` and ``valuation_warnings``,
    summing each flag's weight from :data:`FLAG_WEIGHTS`. Unknown
    flag identifiers contribute 0 (forward compatibility — new flags
    don't need to update this module before they can ship). Result is
    clipped to ``[0, MAX_INDEX]`` and rounded to two decimals.

    Inputs are tolerant of any iterable / None / set shape so callers
    don't need to coerce. Duplicates within a single input collection
    are deduped via union — a flag in both ``risk_flags`` and
    ``valuation_warnings`` (which shouldn't happen in practice) counts
    once.

    Returns
    -------
    float
        Index in ``[0.0, MAX_INDEX]``. **Always returns a number** —
        never None — because zero is a meaningful answer ("no
        manipulation signals fired") whereas None would force the
        frontend into a "missing data" branch for the common case.
    """
    rf: set[str] = set(risk_flags or ())
    vw: set[str] = set(valuation_warnings or ())
    fired = rf | vw

    raw = sum(FLAG_WEIGHTS.get(flag, 0.0) for flag in fired)
    clipped = min(max(raw, 0.0), MAX_INDEX)
    return round(clipped, 2)


def compute_adjusted_composite(
    composite_score: float,
    manipulation_index: float,
) -> float:
    """Apply the manipulation-index soft penalty to a raw composite.

    Formula
    -------

    ``adjusted = composite − PENALTY_MULTIPLIER × (index / 100) × PENALTY_BUDGET``

    With the locked defaults (``0.5``, ``20``), the deduction range is
    ``[0, 10]`` composite points across the ``[0, 100]`` index range.

    Result is clamped to ``[0, 100]`` to honor the composite range
    contract (some unlucky stock with composite=2 and index=100 would
    otherwise drop to −8, which downstream UI / sorting can't reason
    about).
    """
    penalty = PENALTY_MULTIPLIER * (manipulation_index / MAX_INDEX) * PENALTY_BUDGET
    adjusted = composite_score - penalty
    clamped = min(max(adjusted, 0.0), 100.0)
    return round(clamped, 2)


def manipulation_components(
    risk_flags: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    valuation_warnings: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
) -> dict[str, bool]:
    """Per-flag boolean breakdown for the UI drill-down.

    Returns a dict keyed by every flag identifier in
    :data:`FLAG_WEIGHTS` (stable ordering — matches the weight
    table). Each value is ``True`` when that flag fired on this
    ticker, ``False`` otherwise. The frontend uses this to render
    the Manipulation Risk card's component list without having to
    re-derive flag membership from the raw arrays.

    Stable key set is important: the UI assumes every key is
    present so it can render a sorted-by-weight component grid.
    Adding a new flag to :data:`FLAG_WEIGHTS` automatically adds it
    to the output here.
    """
    rf: set[str] = set(risk_flags or ())
    vw: set[str] = set(valuation_warnings or ())
    fired = rf | vw
    return {flag: (flag in fired) for flag in FLAG_WEIGHTS}


__all__ = [
    "ACCRUALS_MOMENTUM_WEIGHT",
    "BENEISH_HIGH_WEIGHT",
    "BENEISH_VETO_WEIGHT",
    "C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED",
    "DECHOW_HIGH_WEIGHT",
    "DECHOW_VETO_WEIGHT",
    "FLAG_WEIGHTS",
    "INSIDER_SELL_CLUSTER_WEIGHT_RESERVED",
    "LATE_FILING_WEIGHT",
    "LOSS_AVOIDANCE_WEIGHT",
    "MAX_INDEX",
    "NON_RELIANCE_WEIGHT",
    "PENALTY_BUDGET",
    "PENALTY_MULTIPLIER",
    "REM_SUSPECT_WEIGHT",
    "RESTATEMENT_HISTORY_WEIGHT",
    "SLOAN_WEIGHT",
    "TRIPLE_FLAG_WEIGHT",
    "compute_adjusted_composite",
    "compute_manipulation_index",
    "manipulation_components",
]
