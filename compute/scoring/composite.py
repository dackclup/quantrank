"""10-pillar weighted composite score.

Phase 3 composite weights per ``PHASE_STATUS.md``. ``sentiment`` and ``ml``
remain null in Phase 3 — their combined 0.20 weight is redistributed
pro-rata across the active pillars (effective weights divided by 0.80).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Authoritative weights — sum to 1.00. Keep in sync with PHASE_STATUS.md
# "Phase 3 composite weights" table.
PHASE3_WEIGHTS: dict[str, float] = {
    "quality": 0.22,
    "value": 0.18,
    "growth": 0.10,
    "momentum": 0.10,
    "health": 0.08,
    "profitability": 0.05,
    "technical": 0.04,
    "risk": 0.03,
    "sentiment": 0.10,
    "ml": 0.10,
}

ACTIVE_PILLARS_PHASE3 = (
    "quality",
    "value",
    "growth",
    "momentum",
    "health",
    "profitability",
    "technical",
    "risk",
)
INACTIVE_PILLARS_PHASE3 = ("sentiment", "ml")

# Sanity check at import time — weights must sum to 1.0 within float epsilon.
_W_SUM = sum(PHASE3_WEIGHTS.values())
if abs(_W_SUM - 1.0) > 1e-9:
    raise ValueError(f"PHASE3_WEIGHTS must sum to 1.0, got {_W_SUM}")

# Pre-compute the redistributed Phase-3 weights (active pillars only,
# normalized to sum to 1.0).
_ACTIVE_WEIGHT_SUM = sum(PHASE3_WEIGHTS[p] for p in ACTIVE_PILLARS_PHASE3)
PHASE3_EFFECTIVE_WEIGHTS: dict[str, float] = {
    p: PHASE3_WEIGHTS[p] / _ACTIVE_WEIGHT_SUM for p in ACTIVE_PILLARS_PHASE3
}


def compute_composite(
    pillar_scores: pd.DataFrame,
    *,
    weights: dict[str, float] | None = None,
    neutralize_missing: bool = True,
) -> pd.Series:
    """Compute weighted composite score per ticker.

    Parameters
    ----------
    pillar_scores : DataFrame indexed by ticker, with at least the active
        Phase-3 pillar columns. Pillars not present in `weights` are ignored.
    weights : pillar → weight mapping. Must sum to 1.0. Defaults to
        ``PHASE3_EFFECTIVE_WEIGHTS`` (active pillars only, redistributed).
    neutralize_missing : if True, NaN pillar scores are imputed to 50.0
        (neutral) before weighting. Per SKILL.md Rule 7.
    """
    if pillar_scores.empty:
        return pd.Series(dtype=float)

    w = dict(weights) if weights is not None else dict(PHASE3_EFFECTIVE_WEIGHTS)
    s = sum(w.values())
    if abs(s - 1.0) > 1e-9:
        raise ValueError(f"weights must sum to 1.0, got {s}")

    cols = [p for p in w if p in pillar_scores.columns]
    if not cols:
        raise ValueError("none of the requested pillar columns are present")

    df = pillar_scores[cols].copy()
    if neutralize_missing:
        df = df.fillna(50.0)

    weight_vec = np.array([w[p] for p in cols], dtype=float)
    weight_vec /= weight_vec.sum()  # safety renorm if cols subset weights
    composite = (df.to_numpy() * weight_vec).sum(axis=1)
    return pd.Series(composite, index=df.index, dtype=float).clip(lower=0.0, upper=100.0)


def neutralize_pillar_scores(
    pillar_scores: pd.DataFrame, *, neutral: float = 50.0
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Replace NaN pillar values with `neutral` and report which pillars
    were imputed per ticker.
    """
    out = pillar_scores.copy()
    imputed: dict[str, list[str]] = {}
    for ticker in out.index:
        missing = [c for c in out.columns if isinstance(out.at[ticker, c], float) and math.isnan(out.at[ticker, c])]
        if missing:
            imputed[str(ticker)] = missing
            for c in missing:
                out.at[ticker, c] = neutral
    return out, imputed
