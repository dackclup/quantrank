"""Phase 4h commit 3 — composite × OSAP signal-aggregate blend (Path-b).

Stays OUTSIDE :func:`compute.scoring.composite.compute_composite` so the
``PHASE3_WEIGHTS`` sum-to-1.0 invariant at ``compute/scoring/composite.py:
43-45`` is not extended. Adding a 9th slot to ``PHASE3_WEIGHTS`` for OSAP
would either fail the invariant or force a redistribution of the eight
active pillars — both of which alter Phase 3 composite math
retroactively. Path-b applies the OSAP correction *after* the pillar
composite is computed, leaving the composite layer untouched.

Formula (osap-integration/PLAN.md:168-170, locked 2026-05-18 plan
audit)::

    blended = (1 - weight) * composite_score + weight * osap_signal_aggregate

where ``osap_signal_aggregate`` is a 0-100 per-ticker aggregate of the
accepted OSAP signal map produced by
:func:`compute.features.osap_replicate.compute_osap_signals` (cross-
sectional rank of the long-short return at ``as_of``, mean-pooled per
ticker, scaled to ``[0, 100]``).

**Universe-gap policy** — tickers with ``None`` signal map (or NaN
aggregate) **pass composite_score through unchanged**. No impute,
distinct from pillar ``compute_composite(neutralize_missing=True)``.
Rationale: in Phase 4h, an OSAP-blank ticker is genuinely "no
information added" rather than "no information available" — imputing
50.0 would silently shrink the composite toward neutral and bias
Top-5 against OSAP-covered names.

**Observability-only this phase** — :func:`apply_osap_blend` writes
``composite_score_osap_adjusted`` into ``StockDetail.osap_blended_score``
but Top-5 ranking still uses raw ``composite_score`` per SKILL.md
Rule 16. Phase 5 ML meta-learner is where 50/50 may be retuned and the
cutover authorized.

No I/O, no tenacity, no network access — pure pandas / numpy.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Locked 50/50 default per osap-integration/PLAN.md:168-170. Phase 5
# ML meta-learner is the next layer where this can move.
OSAP_BLEND_WEIGHT_DEFAULT: float = 0.5


def aggregate_osap_signals(
    signal_map: dict[str, dict[str, float] | None],
) -> pd.Series:
    """Mean-pool a ticker's OSAP signal ranks into a single 0-100 score.

    Each ticker's inner map is ``{signalname: rank}`` where rank is the
    cross-sectional ``(0, 1]`` rank from
    :func:`compute.features.osap_replicate.rank_signals_cross_sectional`.
    Aggregation is the arithmetic mean × 100.

    Args:
        signal_map: ``{ticker: {signalname: rank} | None}`` — exactly the
            shape returned by ``compute_osap_signals``.

    Returns:
        Series indexed by ticker, dtype float, name
        ``osap_signal_aggregate``. NaN for tickers whose inner map is
        ``None`` or empty (universe gap). Empty Series when the input
        dict has no entries.
    """
    if not signal_map:
        return pd.Series(dtype=float, name="osap_signal_aggregate")

    out: dict[str, float] = {}
    for ticker, sigs in signal_map.items():
        if sigs is None or len(sigs) == 0:
            out[ticker] = float("nan")
            continue
        mean_rank = float(np.mean(list(sigs.values())))
        out[ticker] = 100.0 * mean_rank

    return pd.Series(out, dtype=float, name="osap_signal_aggregate")


def apply_osap_blend(
    composite_scores: pd.Series,
    osap_signal_aggregate: pd.Series,
    weight: float = OSAP_BLEND_WEIGHT_DEFAULT,
) -> pd.Series:
    """Blend pillar composite × OSAP aggregate per ticker (Phase 4h Path-b).

    Formula::

        blended = (1 - weight) * composite_score + weight * osap_signal_aggregate

    Tickers whose ``osap_signal_aggregate`` is NaN (after reindex to the
    composite index) pass their raw ``composite_score`` through
    unchanged. The result is clipped to ``[0, 100]`` to match the
    composite-score domain (the writer / Pydantic schema both expect
    ``[0, 100]``).

    Args:
        composite_scores: Series indexed by ticker, values nominally in
            ``[0, 100]``. The output index mirrors this index.
        osap_signal_aggregate: Series indexed by ticker, values in
            ``[0, 100]`` or NaN. Tickers present here but not in
            ``composite_scores`` are silently dropped during reindex.
        weight: blend weight in ``[0, 1]``. Default
            :data:`OSAP_BLEND_WEIGHT_DEFAULT` (0.5) per
            osap-integration/PLAN.md:168-170.

    Returns:
        Series indexed by ``composite_scores.index``, dtype float, name
        ``composite_score_osap_adjusted``. Clipped to ``[0, 100]``.

    Raises:
        ValueError: if ``weight`` is outside ``[0, 1]``.
    """
    if not (0.0 <= weight <= 1.0):
        raise ValueError(f"OSAP blend weight must be in [0, 1], got {weight}")

    if composite_scores.empty:
        return pd.Series(dtype=float, name="composite_score_osap_adjusted")

    # Align OSAP aggregate to composite index; missing tickers become NaN.
    aligned_osap = osap_signal_aggregate.reindex(composite_scores.index)

    # NaN-safe Path-b blend. ``raw_blend`` will be NaN wherever OSAP is
    # NaN, but ``.where(cond, other)`` keeps ``composite_scores`` at those
    # positions — yielding the documented universe-gap pass-through.
    raw_blend = (1.0 - weight) * composite_scores + weight * aligned_osap
    blended = raw_blend.where(~aligned_osap.isna(), composite_scores)

    blended = blended.clip(lower=0.0, upper=100.0)
    blended.name = "composite_score_osap_adjusted"

    coverage = int((~aligned_osap.isna()).sum())
    logger.info(
        "OSAP blend applied: weight=%.2f, %d/%d tickers OSAP-covered, "
        "%d passed-through (universe gap)",
        weight,
        coverage,
        len(composite_scores),
        len(composite_scores) - coverage,
    )
    return blended
