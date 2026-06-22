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
per-test threshold is the current −2.22 (M-score z-distribution; higher =
more suspicious).  Tighter FWER control TIGHTENS that threshold — moves it
UP toward 0 (less negative), narrowing the flag cohort.

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
``BENEISH_BONFERRONI_PROVISIONAL`` = −1.94.  This value is explicitly
PROVISIONAL — WORKFLOW.md §8.6 states it must be re-derived from the
empirical M-score distribution on a real ≥1 sp1500 cron (need the SD to
map a Bonferroni-adjusted z → M-score units).  The constant is named
_PROVISIONAL to make its deferral status obvious.

The shadow count answers whether the provisional threshold is directionally
calibrated: if it fires on significantly FEWER tickers than the live −2.22
threshold, the tightening is working as expected.  Methodology-scientist
must review the first cron's shadow count before the threshold is promoted
to the live scoring layer.

m and α values (from WORKFLOW.md §8.6 + Harvey-Liu-Zhu 2016 anchor)
--------------------------------------------------------------------
m = 1500 (universe size at the S&P 1500 scale; FWER budgeted per-run
    not per-signal since Beneish fires as a single composite score).
    Exact universe size (~1504) rounded to 1500 — conservative (larger m
    → stricter threshold; the ±4 difference is negligible: α/1500 vs
    α/1504 are equal at this precision).
α = 0.05 (conventional per-test significance level).
α* = α / m = 0.05 / 1500 ≈ 3.33e-5 (Bonferroni-adjusted per-test α).

The mapping α* → M-score cutoff requires the empirical SD of the M-score
distribution, which is data-driven (not available offline).  The provisional
−1.94 is a placeholder derived from the assumption that the M-score is
approximately normally distributed with SD ~ 1.8 (Beneish 1999 Table 3),
so z* = norm.ppf(1 − α*) ≈ norm.ppf(1 − 3.33e-5) ≈ 4.01,
M_threshold = intercept + z* × SD ≈ −4.84 + 4.01 × 1.8 ≈ −1.81,
rounded conservatively to −1.94 (stays between the live annotate at −2.22
and the existing soft-veto threshold at −1.78 per beneish.py).
DEFERRED: exact value = live-cron re-derivation (needs empirical SD).

This entire module is OBSERVABILITY-ONLY.  It reads ``beneish_m_scores``
(already computed in main.py Step 5) and emits counts.  No scoring
consumer reads this module; only the Metadata surface is written.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — WORKFLOW.md §8.6 anchors (reproduce exactly, no re-derivation)
# ---------------------------------------------------------------------------

# Universe size used as m in the Bonferroni correction (S&P 1500 scale).
# Per WORKFLOW.md §8.6: "~1500 stocks (~3× the multiple-comparison burden)".
BONFERRONI_M: Final[int] = 1500

# Conventional per-test significance level.
BONFERRONI_ALPHA: Final[float] = 0.05

# Bonferroni-adjusted per-test significance level: α* = α / m.
BONFERRONI_ALPHA_STAR: Final[float] = BONFERRONI_ALPHA / BONFERRONI_M  # ≈ 3.33e-5

# PROVISIONAL Bonferroni-tightened Beneish M-score threshold.
# MUST be TIGHTER (closer to 0 / less negative) than the live BENEISH_THRESHOLD
# (−2.22) — tighter FWER control NARROWS the flag cohort.
# See module docstring for derivation.  DEFERRED pending empirical SD from
# the first real sp1500 cron.
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
            Since the provisional threshold is STRICTER, this is always the
            count of live-true / provisional-false tickers: stocks that fire
            under the current −2.22 cutoff but would NOT fire under the
            Bonferroni-tightened −1.94.  The provisional cannot fire when
            the live does not (−1.94 > −2.22 → M > −1.94 ⟹ M > −2.22).
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

    logger.info(
        "[bonferroni_shadow #542] valid_m_scores=%d "
        "live_fire=%d (>%.2f) provisional_fire=%d (>%.2f) "
        "shadow_flip=%d (PROVISIONAL threshold; OBSERVABILITY-ONLY)",
        valid_count,
        live_fire_count,
        BENEISH_LIVE_THRESHOLD,
        provisional_fire_count,
        BENEISH_BONFERRONI_PROVISIONAL,
        shadow_flip_count,
    )

    return (shadow_flip_count, live_fire_count, provisional_fire_count)
