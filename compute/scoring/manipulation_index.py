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

Weight provenance (Epic #150 Phase 2.5, 2026-05-20)
---------------------------------------------------

Each weight below carries one of three provenance tiers:

- **literature-anchored** — magnitude derived from a published PPV /
  hit-rate / effect-size figure. Cited inline per constant.
- **gut-feel calibration** — engineering choice (e.g., "half the
  weight of the active-veto sibling because confidence is roughly
  half"). Labeled as such per constant so a future calibration PR
  knows which weights have empirical defense vs which are coarse
  defaults.
- **reserved** — Phase 4.5e slot, no production fire yet; weight is
  a placeholder pending the integration PR's replication study.

Replacing a gut-feel weight requires either (a) production-data
evidence (≥ 1 quarter of cohort firings against an outcome series),
or (b) a peer-reviewed replication study citing the specific weight
class. Tighter-bound weights are not better in absolute terms —
overweighting a low-PPV flag drives false-positive penalties.

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

# --- Active vetoes — high-PPV signals already suppressing entered_top5 -------

#: Sloan 1996 *TAR* §"Accrual anomaly": top-decile accruals stocks
#: earn ~-10.4 %/yr abnormal returns vs bottom-decile. Replicated
#: across 25+ studies (e.g., Bernard-Stober 1989, Xie 2001, Hirshleifer
#: et al. 2012). Provenance: **literature-anchored** — magnitude
#: matched to the highest-PPV peer veto (Beneish, Dechow).
SLOAN_WEIGHT: Final[float] = 20.0

#: Beneish 1999 *FAJ* §"The Detection of Earnings Manipulation":
#: M-Score > -1.78 catches 76% of manipulators with 17.5% FP rate in
#: the original 74-firm sample. Replicated by Beneish-Lee-Nichols 2013
#: *FAJ* against post-2000 manipulator sample (similar PPV).
#: Provenance: **literature-anchored** — magnitude matches Sloan
#: (both are top-of-veto-tier).
BENEISH_VETO_WEIGHT: Final[float] = 20.0

#: Dechow et al. 2011 *CAR* §"Predicting Material Accounting
#: Misstatements": F-Score > 3.0 catches ~50% of AAER restatements
#: with ~10% FP on a Compustat panel. Sample includes both fraud
#: cases (AAER) and large material restatements. Provenance:
#: **literature-anchored** — magnitude matches Beneish veto; both
#: derive PPV from AAER ground truth.
DECHOW_VETO_WEIGHT: Final[float] = 20.0

#: Schroeder 2024 SSRN §"The Information Content of Item 4.02
#: Non-Reliance Filings": 8-K Item 4.02 = explicit management-or-auditor
#: admission of prior-period non-reliance. PPV near-100% (literal
#: disclosure); base rate ~0.5-1.5% on S&P 500. Slightly below the
#: 20-pt veto cluster because the disclosure is rare AND already
#: triggers a hard composite veto — the index weight is the
#: *additional* signal the disclosure adds beyond the veto itself.
#: Provenance: **literature-anchored** — weight reflects the
#: rare-but-unambiguous information content; gut-feel on the
#: relative 15 vs 20 split.
NON_RELIANCE_WEIGHT: Final[float] = 15.0

# --- Joint-gate bonus --------------------------------------------------------

#: Co-fire bonus when Sloan + Beneish-high + Dechow-high all fire on
#: the same ticker. Engineering choice — the 3 quant defenses are
#: correlated (all anchor on accruals / discretionary items), so the
#: bonus prevents underweighting the multi-signal regime once any
#: single 20-pt veto already saturates 1/5 of the cap. Provenance:
#: **gut-feel calibration** — no academic source prescribes joint-gate
#: weight; tuned to push 3-flag stocks well past the 60-pt mid-band
#: so the penalty (~6 composite points) is meaningfully separated
#: from single-veto stocks (~4 points).
TRIPLE_FLAG_WEIGHT: Final[float] = 10.0

# --- Annotates — medium-confidence forensic / disclosure signals -------------

#: Roychowdhury 2006 *JAE* §"Earnings Management Through Real
#: Activities Manipulation": REM-suspect = abnormal CFO + production
#: + discretionary expenses (z-score composite). PPV ~40% per
#: Cohen-Dey-Lys 2008 *TAR* replication (post-SOX REM shifted from
#: accruals to real activities). Lower than Sloan/Beneish/Dechow
#: because the signal is harder to ground-truth (REM is legal but
#: value-destroying — not a fraud signal). Provenance:
#: **literature-anchored** — weight reflects the ~2× PPV gap vs
#: active vetoes.
REM_SUSPECT_WEIGHT: Final[float] = 8.0

#: Hennes-Leone-Miller 2008 *TAR* §"The Importance of Distinguishing
#: Errors from Irregularities": restatements split ~80/20 between
#: clerical errors (non-malicious) and irregularities (fraud). The
#: current ``restatement_history`` flag fires on ANY amendment in the
#: lookback window — so the effective material-restatement PPV is
#: closer to ~30%. Provenance: **literature-anchored on the cite,
#: gut-feel on the weight** — Phase 2.2 (epic #150) plans a
#: recalibration to "amendment + Item 4.02 within 90d" which would
#: lift PPV ~70% and warrant a weight bump.
RESTATEMENT_HISTORY_WEIGHT: Final[float] = 5.0

#: Bartov-Lai-Yeung 2002 *JAR* §"Late Filings Around Earnings
#: Surprises": NT-10K / NT-10Q filings correlate with subsequent
#: material restatements (~2× base rate). Effect size lower than
#: amendment-based signals. Provenance: **gut-feel calibration** —
#: no direct PPV figure replicated in QuantRank's universe; weight
#: matches the restatement-history sibling on the assumption that
#: "late filing" is a weaker leading indicator of "restatement
#: filing." Re-evaluate post a production-data audit.
LATE_FILING_WEIGHT: Final[float] = 5.0

#: ``accruals_momentum_high`` — proprietary composite (no single peer-
#: reviewed cite). Captures sustained-high-accruals stocks (Sloan
#: anomaly extended over 4 quarters). Theoretical motivation: Sloan
#: + Xie 2001 *TAR* §"The Mispricing of Abnormal Accruals" suggests
#: persistence amplifies the anomaly. Provenance: **gut-feel
#: calibration** — weight matches the annotate-tier siblings on the
#: assumption that "momentum-on-Sloan" is a secondary signal worth a
#: modest annotate. Empirical PPV not yet measured against the
#: QuantRank universe.
ACCRUALS_MOMENTUM_WEIGHT: Final[float] = 5.0

#: Burgstahler-Dichev 1997 *JAE* §"Earnings Management to Avoid
#: Earnings Decreases and Losses": disproportionate bunching of
#: just-positive earnings (NI ≤ $5M, EPS ≤ $0.05) → loss-avoidance
#: pattern. Original Compustat cohort PPV ~60% but those thresholds
#: are scaled to a 1990s small-cap universe. On S&P 500 the current
#: thresholds fire 0% (issue tracked in CLAUDE.md §Gotchas) — the
#: weight is the magnitude the flag SHOULD carry once Phase 2.4
#: (epic #150) rescales thresholds 10× to S&P 500 market caps.
#: Provenance: **literature-anchored on magnitude, dead on
#: production** — re-evaluate after Phase 2.4.
LOSS_AVOIDANCE_WEIGHT: Final[float] = 5.0

# --- Tier-3 soft annotates — Beneish/Dechow warning band ---------------------

#: Beneish M-Score ∈ [-2.22, -1.78] — warning band below the active-
#: veto threshold (-1.78). Beneish-Lee-Nichols 2013 *FAJ* reports the
#: warning-band PPV at ~35-40% vs ~75% above the active threshold.
#: Provenance: **literature-anchored** — weight is the half-PPV
#: derivative of the 20-pt active veto (≈ 3 pts), validated by the
#: empirical band-PPV ratio.
BENEISH_HIGH_WEIGHT: Final[float] = 3.0

#: Dechow F-Score ∈ [2.45, 3.0] — warning band below the active-veto
#: threshold (3.0). Dechow et al. 2011 *CAR* Table 9 reports the
#: warning-band PPV at ~25-30% vs ~50% above the active threshold.
#: Provenance: **literature-anchored** — weight matches the Beneish-
#: high sibling for calibration symmetry across the two M+F warning
#: bands (both Tier-3, both half-PPV of their veto counterparts).
DECHOW_HIGH_WEIGHT: Final[float] = 3.0

# --- Reserved 4.5e slots — uncomment when those flags land -------------------

#: Form-4 insider-sell-cluster flag from Phase 4.5e. Cohen-Malloy-
#: Nguyen 2020 *RFS* §"Lazy Prices" + Cohen 2008 *J. Finance* on
#: opportunistic insider trading suggest cluster patterns predict
#: 1-6 month negative returns. Provenance: **reserved** — replication
#: study lands with the Phase 4.5e integration PR; weight may move
#: after the cohort calibration.
INSIDER_SELL_CLUSTER_WEIGHT_RESERVED: Final[float] = 10.0

#: Form-4 C-suite-unusual-sell flag from Phase 4.5e. Same Cohen
#: family of references; sub-signal of the cluster flag (CEO/CFO
#: specifically, vs all named insiders). Provenance: **reserved** —
#: gut-feel weight ahead of Phase 4.5e replication; expected to land
#: at half the cluster weight given it's a narrower trigger.
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
