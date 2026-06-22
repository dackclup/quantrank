"""Bonferroni multi-test shadow counter — OBSERVABILITY-ONLY (Rule 18).

Issue #542 · Slice 8 · WORKFLOW.md §8.6 — "Bonferroni adjustments documented
and applied" acceptance criterion.

Background
----------
When the scoring universe grows from ~500 (S&P 500) to ~1500 (S&P 1500),
the multiple-comparison burden grows ~3×.  For a fixed per-test α = 0.05 the
family-wise error rate (FWER = 1 − (1 − α)^m) grows correspondingly —
meaning we accept far more false positives at scale without adjustment.

The control target is **FWER via Bonferroni**, NOT FDR (Benjamini-Hochberg).
Bonferroni: adjusted α* = α / m.  For the Beneish M-Score specifically the
per-test threshold is the current −2.22 (M-score; higher = more suspicious).
Tighter FWER control TIGHTENS that threshold — moves it UP toward 0 (less
negative), narrowing the flag cohort.

This module computes a **shadow count only** — it does NOT change the live
threshold, the live flags, the composite score, or any veto.  It answers:
"how many tickers WOULD flip from ``beneish_high=False`` to
``beneish_high=True`` under the Bonferroni-tightened threshold?"  (None
will; it answers how many would be REMOVED from the live fire set.)

SIGN CORRECTION (WORKFLOW.md §8.6, 2026-06-19)
-----------------------------------------------
The original Slice-3 draft had the direction backwards: −2.50 < −2.22 is
LOOSER (flags a superset, MORE names) — that is the wrong direction for
tighter FWER control.  Tighter control means a HIGHER cutoff (closer to 0).

The provisional Bonferroni-tightened threshold implemented here is
``BENEISH_BONFERRONI_PROVISIONAL`` = −1.94.  This value is an ARBITRARY
PLACEHOLDER chosen to fall strictly between the live annotate threshold
(−2.22) and the soft-veto threshold (−1.78) in ``beneish.py``.  It is NOT
derived from a formula — the correct derivation requires the empirical
standard deviation of the M-score distribution on a real sp1500 cron run,
which is not yet available.  The exact value is EXPLICITLY DEFERRED to
re-derivation once the first real sp1500 cron produces the empirical
M-score SD.  Cite: Beneish 1999 (FAJ); Bonferroni FWER correction.

The shadow count answers whether the provisional threshold is directionally
calibrated: if it fires on significantly FEWER tickers than the live −2.22
threshold, the tightening is working as expected.  Methodology-scientist
must review the first cron's shadow count before the threshold is promoted
to the live scoring layer.

m and α (data-driven, NOT universe-size constant)
-------------------------------------------------
``m`` is the number of hypothesis TESTS in this family — the number of
tickers with a valid (non-None) Beneish M-score on this cron run.  This
controls the per-ticker family-wise false-flag rate across the N valid
Beneish M-score decisions for THIS run (distinct from Harvey-Liu-Zhu 2016
multi-SIGNAL control, which uses a different ``m`` concept across signals,
not tickers).

Concretely: ``m = valid_count`` (non-None M-scores); ``α* = 0.05 / m``.
This makes the correction data-driven rather than frozen at an assumed
universe size.  On a warm sp1500 cron ``m ≈ 1400-1500``; on sp500-only
runs ``m ≈ 450-500``.  The FWER being controlled is: "across the m binary
flag decisions on THIS run, at most 5% chance of at least one false positive
flag due to M-score threshold alone".

The computed ``alpha_star`` is logged for each run and deferred to the
methodology-scientist for threshold re-derivation.  It is NOT stored in
Metadata (the 3 Metadata fields are the flip/live/provisional counts).

Edge cases: ``valid_count == 0`` → returns (0, 0, 0) gracefully, no
division by zero.

This entire module is OBSERVABILITY-ONLY.  It reads ``beneish_m_scores``
(already computed in main.py Step 5) and emits counts.  No scoring
consumer reads this module; only the Metadata surface is written.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Conventional per-test significance level.
BONFERRONI_ALPHA: Final[float] = 0.05

# PROVISIONAL Beneish M-score threshold for the Bonferroni shadow counter.
#
# This is an ARBITRARY PLACEHOLDER chosen to sit strictly between:
#   - the live annotate threshold: BENEISH_LIVE_THRESHOLD = −2.22 (beneish.py)
#   - the soft-veto threshold:     −1.78 (beneish.py)
# so that ``provisional ⊆ live`` and the flip count (live_fire − provisional_fire)
# is well-defined.
#
# The threshold is LESS NEGATIVE than the live −2.22 (closer to 0 = stricter
# FWER control, narrower flag cohort).
#
# DEFERRED: the exact value requires re-derivation from the empirical sp1500
# M-score standard deviation on a real cron run (WORKFLOW.md §8.6).  Do NOT
# dress this in a formula that has not been verified on real data.
# Named _PROVISIONAL to make its deferral status obvious in call sites.
BENEISH_BONFERRONI_PROVISIONAL: Final[float] = -1.94

# Live Beneish threshold — mirrored here so the comparison is self-contained.
# Keep in sync with compute/scoring/beneish.py::BENEISH_THRESHOLD = -2.22.
BENEISH_LIVE_THRESHOLD: Final[float] = -2.22


def compute_bonferroni_shadow(
    beneish_m_scores: dict[str, float | None],
) -> tuple[int, int, int]:
    """Count tickers that change flag state under the Bonferroni threshold.

    This function is SHADOW-ONLY.  It does NOT modify any flag, score, or
    veto.  All returned values are diagnostic counters for Metadata only.

    ``m`` for the Bonferroni correction is the number of tickers with a
    valid (non-None) M-score on THIS run — the number of hypothesis tests
    actually performed.  ``α* = 0.05 / valid_count`` is computed
    data-driven.  This controls the per-ticker family-wise false-flag rate
    across the N valid Beneish M-score decisions for this cron
    (distinct from Harvey-Liu-Zhu multi-SIGNAL FWER, which uses a
    different m).  Cite: Beneish 1999; Bonferroni FWER.

    Parameters
    ----------
    beneish_m_scores:
        ``{ticker: m_score}`` from the main.py Beneish pre-compute pass
        (``beneish_m_scores`` dict, populated in Step 5 before risk_flags).
        ``None`` values (missing ratios — stock had incomplete fundamentals)
        are excluded from all counts.

    Returns
    -------
    tuple[int, int, int]
        ``(shadow_flip_count, live_fire_count, provisional_fire_count)``

        shadow_flip_count
            Tickers where the flag state DIFFERS between the two thresholds.
            Since the provisional threshold is STRICTER (−1.94 > −2.22),
            this is always the count of live-true / provisional-false
            tickers: stocks that fire under the current −2.22 cutoff but
            would NOT fire under the Bonferroni-tightened −1.94.
            The provisional cannot fire when the live does not
            (−1.94 > −2.22 → M > −1.94 ⟹ M > −2.22).
            A larger value indicates more false positives the tighter
            threshold would suppress.

        live_fire_count
            Tickers with M-score > BENEISH_LIVE_THRESHOLD (−2.22) on this
            run.  Corresponds to the existing ``beneish_high`` annotate.
            Surfaced here so the shadow report is self-contained.

        provisional_fire_count
            Tickers with M-score > BENEISH_BONFERRONI_PROVISIONAL (−1.94).
            Always ≤ live_fire_count (provisional is stricter).
            live_fire_count − provisional_fire_count = shadow_flip_count.
    """
    live_fire_count: int = 0
    provisional_fire_count: int = 0
    shadow_flip_count: int = 0
    valid_count: int = 0

    for _ticker, m_score in beneish_m_scores.items():
        if m_score is None:
            continue
        valid_count += 1
        live_fires = m_score > BENEISH_LIVE_THRESHOLD
        provisional_fires = m_score > BENEISH_BONFERRONI_PROVISIONAL
        if live_fires:
            live_fire_count += 1
        if provisional_fires:
            provisional_fire_count += 1
        # Flip: live and provisional disagree.
        # Structurally: provisional_fires implies live_fires (stricter),
        # so flips are always live_fires=True / provisional_fires=False.
        if live_fires != provisional_fires:
            shadow_flip_count += 1

    # m = valid_count (hypothesis tests actually performed this run).
    # α* = 0.05 / valid_count (data-driven Bonferroni correction).
    # Edge case: valid_count == 0 → α* undefined; log 0 counts and return.
    if valid_count > 0:
        alpha_star = BONFERRONI_ALPHA / valid_count
        logger.info(
            "[bonferroni_shadow #542] valid_m_scores=%d "
            "m=%d alpha_star=%.6e "
            "live_fire=%d (>%.2f) provisional_fire=%d (>%.2f) "
            "shadow_flip=%d "
            "(FWER-controlled per-ticker flag rate; PROVISIONAL threshold; "
            "OBSERVABILITY-ONLY; threshold re-derivation DEFERRED to "
            "empirical sp1500 cron SD)",
            valid_count,
            valid_count,
            alpha_star,
            live_fire_count,
            BENEISH_LIVE_THRESHOLD,
            provisional_fire_count,
            BENEISH_BONFERRONI_PROVISIONAL,
            shadow_flip_count,
        )
    else:
        logger.info(
            "[bonferroni_shadow #542] valid_m_scores=0 — no valid Beneish "
            "M-scores; returning (0, 0, 0) (OBSERVABILITY-ONLY)",
        )

    return (shadow_flip_count, live_fire_count, provisional_fire_count)
