"""Loss Chance % heuristic derivation (PR 4e, Phase 4 UX trio §2).

Combines the already-computed composite score, risk-overlay flags,
valuation warnings, and Margin of Safety into a single 5-95% chip that
answers "if I buy this at the current price, what's my heuristic chance
of loss?" **No new modeling, no ML, no backtest** — purely a tunable
linear combiner over existing outputs.

Per the locked decision in `.claude/skills/phase-4/loss-chance/PLAN.md`
+ `phase-4-kickoff-checklist/PLAN.md` §1 (Option D, 2026-05-14): use
the literal "Loss Chance %" label + small italic "heuristic"
qualifier. Internal value is just a 0-100 number with [5, 95] clipping.

Calibration (locked 2026-05-14 post-simulation against live S&P 500):
- Baseline 40 (NOT 50) — S&P 500 has median MoS −25% so a symmetric
  50% baseline pushes the universe median up to ~60-64. Baseline 40
  shifts the universe median to ~49, on target.
- Asymmetric MoS contribution: undervalued (positive MoS) gets a
  stronger push DOWN (cap 35 pp) than overvalued gets push UP (cap 20
  pp). Captures the rare-deep-value vs common-moderate-overvalue
  shape of the universe.
- Composite signal stronger (`/2.0` vs PLAN's `/5`) so top-composite
  stocks land in the green band even when MoS is moderate.
- Flag penalties proportionally lower than PLAN draft (`dq` 20→15,
  `altman` 15→12, `gc` 10→8) so the universe median doesn't drift
  above 50 from flag stacking alone.

The threshold knobs are exposed as module constants; downstream
re-tuning happens by editing them, not by rewriting the rubric.

⚠️ This is a **heuristic**, not a backtested probability. The
LossChanceBadge component must render a small italic "heuristic"
qualifier next to the number. The global Disclaimer banner on every
page covers the legal posture. For a backtest-calibrated interval,
see Phase 5+ Triple-Barrier + Conformal Prediction work.
"""

from __future__ import annotations

# Baseline starts BELOW 50 because S&P 500 median MoS is negative
# (universe median MoS −25% in 2026-05-14 production data); a 50
# baseline drifts universe median up to ~60. Baseline 40 + the
# MoS / composite shifters below land the universe median ≈ 49.
BASELINE_PCT: float = 40.0

# MoS contribution shape:
# - mos_signal = -mos_pct * MOS_SCALE
# - clipped to [-MOS_NEG_CAP, +MOS_POS_CAP]
# Positive MoS (stock undervalued) → mos_signal negative → push LC down.
# Negative MoS (overvalued) → mos_signal positive → push LC up.
# Asymmetric caps reflect that S&P 500's left tail (deep overvalue)
# is heavier than its right tail (deep undervalue) — we don't want
# every overvalued stock pinned at 95.
MOS_SCALE: float = 0.35
MOS_NEG_CAP: float = 35.0  # max push DOWN from MoS (undervalued stocks)
MOS_POS_CAP: float = 20.0  # max push UP from MoS (overvalued stocks)

# Composite contribution: (50 - composite) / COMPOSITE_SCALE.
# composite=70 → -10 pp; composite=30 → +10 pp.
COMPOSITE_SCALE: float = 2.0

# Risk-flag penalties — heaviest weight to broken-input vetoes since
# they invalidate the entire downstream signal stack.
DATA_QUALITY_PENALTY: float = 15.0
ALTMAN_PENALTY: float = 12.0
GOING_CONCERN_PENALTY: float = 8.0
SLOAN_NSI_PENALTY: float = 3.0  # applied per flag (Sloan + NSI both fire = +6)

# Valuation-warning penalties — lighter touch.
BENEISH_DECHOW_PENALTY: float = 3.0  # per flag
VALUE_TRAP_PENALTY: float = 2.0
GOODWILL_HEAVY_PENALTY: float = 1.0
STALE_FILING_SOFT_PENALTY: float = 2.0
EXTREME_ESTIMATE_PER_FLAG: float = 1.0  # per `extreme_*_estimate` flag
EXTREME_ESTIMATE_CAP: float = 5.0       # max cumulative

# Honest 5-95% clip — the chip surface should never claim 0% or 100%
# certainty because a heuristic combiner can't justify either.
MIN_PCT: float = 5.0
MAX_PCT: float = 95.0


def derive_loss_chance(
    *,
    composite_score: float | None,
    risk_flags: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    valuation_warnings: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    mos_pct: float | None,
) -> float | None:
    """Return a heuristic Loss Chance % in [MIN_PCT, MAX_PCT], or None
    when MoS is missing (the dominant signal — without it we don't have
    enough information to fake a probability).

    Parameters mirror the StockSummary / StockDetail fields rather than
    taking the full Pydantic object — keeps the function pure-data and
    trivially unit-testable.

    Returns
    -------
    float | None
        Loss Chance percentage, clipped to [MIN_PCT, MAX_PCT]. None
        propagates when ``mos_pct`` is None — the badge component
        renders an em-dash placeholder in that case.

    Notes
    -----
    The function is **pure**: same inputs always yield the same
    output. No reads from disk, env, or global mutable state.
    """
    if mos_pct is None:
        return None

    base = BASELINE_PCT

    # MoS contribution (asymmetric caps).
    mos_signal = -mos_pct * MOS_SCALE
    if mos_signal < 0:
        mos_signal = max(-MOS_NEG_CAP, mos_signal)
    else:
        mos_signal = min(MOS_POS_CAP, mos_signal)
    base += mos_signal

    # Composite contribution.
    if composite_score is not None:
        base += (50.0 - composite_score) / COMPOSITE_SCALE

    # Risk-flag penalties.
    rf: set[str] = set(risk_flags or ())
    if "data_quality_input_corruption" in rf:
        base += DATA_QUALITY_PENALTY
    if "altman_distress" in rf:
        base += ALTMAN_PENALTY
    if "going_concern_disclosure" in rf:
        base += GOING_CONCERN_PENALTY
    if "sloan_accruals_top_decile" in rf:
        base += SLOAN_NSI_PENALTY
    if "net_issuance_top_decile" in rf:
        base += SLOAN_NSI_PENALTY

    # Valuation-warning penalties.
    vw: set[str] = set(valuation_warnings or ())
    if "beneish_high" in vw:
        base += BENEISH_DECHOW_PENALTY
    if "dechow_high" in vw:
        base += BENEISH_DECHOW_PENALTY
    if "value_trap_risk" in vw:
        base += VALUE_TRAP_PENALTY
    if "goodwill_heavy" in vw:
        base += GOODWILL_HEAVY_PENALTY
    if "stale_filing_soft" in vw:
        base += STALE_FILING_SOFT_PENALTY
    extreme_count = sum(
        1 for w in vw if w.startswith("extreme_") and w.endswith("_estimate")
    )
    base += min(EXTREME_ESTIMATE_CAP, extreme_count * EXTREME_ESTIMATE_PER_FLAG)

    # Honest clip.
    return max(MIN_PCT, min(MAX_PCT, base))


__all__ = [
    "ALTMAN_PENALTY",
    "BASELINE_PCT",
    "BENEISH_DECHOW_PENALTY",
    "COMPOSITE_SCALE",
    "DATA_QUALITY_PENALTY",
    "EXTREME_ESTIMATE_CAP",
    "EXTREME_ESTIMATE_PER_FLAG",
    "GOING_CONCERN_PENALTY",
    "GOODWILL_HEAVY_PENALTY",
    "MAX_PCT",
    "MIN_PCT",
    "MOS_NEG_CAP",
    "MOS_POS_CAP",
    "MOS_SCALE",
    "SLOAN_NSI_PENALTY",
    "STALE_FILING_SOFT_PENALTY",
    "VALUE_TRAP_PENALTY",
    "derive_loss_chance",
]
