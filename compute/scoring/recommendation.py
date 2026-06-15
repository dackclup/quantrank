"""Recommendation tier derivation (PR 4d, Phase 4 UX trio §1).

Deterministically derives a 4-tier recommendation label from the
already-computed composite score, risk-overlay flags, valuation
warnings, and Margin of Safety. **No new modeling** — purely a
thresholding combinator over existing compute outputs.

Per the locked decision in `.claude/skills/phase-4/recommendation-
badge/PLAN.md` + `phase-4-kickoff-checklist/PLAN.md` §1 (Option B,
2026-05-14): use neutral terminology to avoid FINRA/SEC-regulated
sell-side analyst labels. Four tiers:

- ``bullish`` — top-decile composite + clean risk profile + ≥20% MoS
- ``lean_bullish`` — top-quartile composite + ≤1 risk flag + ≥0% MoS
- ``neutral`` — anything between (default fallback)
- ``cautious`` — distress / corruption / strong overvaluation / very
  low composite

Thresholds are tunable via the module-level constants; defaults are
calibrated for the target distribution (5-10% bullish, 25-35% lean
bullish, 40-50% neutral, 10-25% cautious) measured against the latest
production rankings.

Disclaimer (per README "Honest Limitations" + Phase 4 UX trio scoping):
the recommendation is a **deterministic derivation of model output**,
not investment advice. The frontend RecommendationBadge component is
expected to render this within the existing global Disclaimer banner;
no per-badge popover required because the terminology itself is
non-regulated.
"""

from __future__ import annotations

from typing import Literal

Recommendation = Literal["bullish", "lean_bullish", "neutral", "cautious"]

# Composite-score thresholds. Tunable; calibrated 2026-05-14 against the
# S&P 500 production rankings.json so the four tiers hit the PLAN-target
# distribution (5-10% Strong Buy, 25-35% Buy, 40-50% Hold, 10-25% Sell).
# The original (composite=70/60/35, MoS=20/0/-30) values yielded 0%/5.6%/
# 40.6%/53.8% — way too few Strong Buy candidates (S&P 500 is mostly
# fully-priced; deep-value passes the cut very rarely) and far too many
# Sell (-30% MoS cutoff caught half the universe). Re-calibrated values
# below give 5.2%/29.3%/43.0%/22.5% on the same production data.
BULLISH_COMPOSITE_MIN: float = 60.0
LEAN_BULLISH_COMPOSITE_MIN: float = 50.0
CAUTIOUS_COMPOSITE_MAX: float = 25.0

# MoS thresholds. Calibrated against the actual S&P 500 MoS distribution
# (p25=-91.5%, p50=-25.4%, p75=+12.5%). The Bullish threshold sits near
# the universe median so most "clean top-composite" stocks qualify; the
# Cautious threshold sits near the p10 tail so only deeply overvalued
# names trigger.
BULLISH_MOS_MIN_PCT: float = -10.0
LEAN_BULLISH_MOS_MIN_PCT: float = -80.0
CAUTIOUS_MOS_MAX_PCT: float = -180.0

# Risk-flag sets that exclude from each tier.
_BULLISH_DISQUALIFYING_RISK: frozenset[str] = frozenset(
    {"sloan_accruals_top_decile", "net_issuance_top_decile"}
)
_CAUTIOUS_FORCING_RISK: frozenset[str] = frozenset(
    {"data_quality_input_corruption", "altman_distress", "fundamentals_unavailable"}
)
_BULLISH_DISQUALIFYING_WARNING: frozenset[str] = frozenset(
    {"beneish_high", "dechow_high"}
)
# Max number of risk_flags allowed for lean_bullish (anything more →
# defaults to neutral or cautious depending on which flag fired).
LEAN_BULLISH_MAX_RISK_FLAGS: int = 2


def derive_recommendation(
    *,
    composite_score: float,
    risk_flags: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    valuation_warnings: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None,
    mos_pct: float | None,
) -> Recommendation:
    """Return a 4-tier recommendation label.

    Parameters mirror the StockDetail / StockSummary fields rather than
    taking the whole Pydantic object — keeps the function pure-data and
    trivially unit-testable without constructing the full schema.

    Decision order (first match wins):

    1. **Cautious** if any of:
       - ``data_quality_input_corruption``, ``fundamentals_unavailable``,
         or ``altman_distress`` in ``risk_flags`` (broken / absent inputs /
         distress veto)
       - ``composite_score`` strictly below ``CAUTIOUS_COMPOSITE_MAX``
         (default 35)
       - ``mos_pct`` strictly below ``CAUTIOUS_MOS_MAX_PCT`` (default −30%)

    2. **Bullish** if all of:
       - ``composite_score >= BULLISH_COMPOSITE_MIN`` (default 70)
       - No Sloan-top-decile / NSI-top-decile risk flag
       - No ``beneish_high`` / ``dechow_high`` valuation warning
       - ``mos_pct >= BULLISH_MOS_MIN_PCT`` (default +20%), or MoS unknown

    3. **Lean bullish** if all of:
       - ``composite_score >= LEAN_BULLISH_COMPOSITE_MIN`` (default 60)
       - At most ``LEAN_BULLISH_MAX_RISK_FLAGS`` (default 1) risk flag
       - ``mos_pct >= LEAN_BULLISH_MOS_MIN_PCT`` (default 0%), or MoS unknown

    4. **Neutral** otherwise.

    Implementation notes
    --------------------

    - Inputs are tolerant of None / empty / set / frozenset / list / tuple
      so callers don't need to coerce.
    - MoS = None is treated permissively (doesn't disqualify a higher
      tier — the absence of fair-price signal shouldn't downgrade a
      strong composite).
    - The function is **pure** — same inputs always yield the same
      output. No reads from disk, env, or any global mutable state.
    """
    rf: set[str] = set(risk_flags or ())
    vw: set[str] = set(valuation_warnings or ())

    # 1. Cautious — overrides everything else.
    if rf & _CAUTIOUS_FORCING_RISK:
        return "cautious"
    if composite_score < CAUTIOUS_COMPOSITE_MAX:
        return "cautious"
    if mos_pct is not None and mos_pct < CAUTIOUS_MOS_MAX_PCT:
        return "cautious"

    # 2. Bullish — strict top-decile gate.
    if (
        composite_score >= BULLISH_COMPOSITE_MIN
        and not (rf & _BULLISH_DISQUALIFYING_RISK)
        and not (vw & _BULLISH_DISQUALIFYING_WARNING)
        and (mos_pct is None or mos_pct >= BULLISH_MOS_MIN_PCT)
    ):
        return "bullish"

    # 3. Lean bullish — top-quartile + lightly-flagged.
    if (
        composite_score >= LEAN_BULLISH_COMPOSITE_MIN
        and len(rf) <= LEAN_BULLISH_MAX_RISK_FLAGS
        and (mos_pct is None or mos_pct >= LEAN_BULLISH_MOS_MIN_PCT)
    ):
        return "lean_bullish"

    # 4. Default — neutral.
    return "neutral"


__all__ = [
    "BULLISH_COMPOSITE_MIN",
    "BULLISH_MOS_MIN_PCT",
    "CAUTIOUS_COMPOSITE_MAX",
    "CAUTIOUS_MOS_MAX_PCT",
    "LEAN_BULLISH_COMPOSITE_MIN",
    "LEAN_BULLISH_MAX_RISK_FLAGS",
    "LEAN_BULLISH_MOS_MIN_PCT",
    "Recommendation",
    "derive_recommendation",
]
