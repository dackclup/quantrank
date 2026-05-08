"""Risk overlay flags — annotate-only.

Per the user's PR-3b scope decision (2026-05-08): flagged stocks keep their
honest composite score; the veto is enforced one layer up at Top-5 rotation
(``compute.main``) — a flagged stock cannot earn the ``entered_top5`` badge
even if its composite would qualify.

Phase 3 ships two flags:

- ``altman_distress`` — Altman Z″ < 1.1 (financial distress zone)
- ``sloan_accruals_top_decile`` — Sloan accruals = (NI − CFO) / TotalAssets,
  flagged if this stock sits in the cross-sectional top decile (highest
  accruals relative to assets are associated with future negative returns,
  Sloan 1996)

The Beneish M-score flag (``beneish_manipulation``) is documented in
``SKILL.md`` but deferred to Phase 4 — its 8-ratio composite needs inputs
not yet in ``FundamentalsSnapshot`` (sales-receivables variation requires
prior-period balance items, which Phase 2 only persists for the latest
fiscal period).
"""

from __future__ import annotations

import math

import pandas as pd

from compute.features import health
from compute.ingest.fundamentals import FundamentalsSnapshot

ALTMAN_DISTRESS_THRESHOLD = 1.1
SLOAN_TOP_DECILE = 0.90
# Minimum sample size before Sloan accruals deciles are statistically
# meaningful. Below this, we skip the Sloan flag entirely (a 1-ticker
# universe trivially makes that ticker its own 90th percentile).
SLOAN_MIN_POPULATION = 10


def _altman_distress(snap: FundamentalsSnapshot | None) -> bool:
    if snap is None:
        return False
    z = health.altman_z_double_prime(snap)
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return False
    return float(z) < ALTMAN_DISTRESS_THRESHOLD


def _sloan_accruals(snap: FundamentalsSnapshot | None) -> float:
    """Compute Sloan accruals = (Net Income − Operating Cash Flow) / Total Assets.

    Returns NaN when any input is missing/zero.
    """
    if snap is None:
        return math.nan
    ni = snap.net_income
    cfo = snap.operating_cash_flow
    ta = snap.total_assets
    if ni is None or cfo is None or ta is None:
        return math.nan
    if ta == 0:
        return math.nan
    return (ni - cfo) / ta


def compute_risk_flags(
    snapshots: dict[str, FundamentalsSnapshot | None],
) -> dict[str, list[str]]:
    """Compute the risk-flag list per ticker.

    Top-decile cutoff for Sloan accruals is computed cross-sectionally over
    the universe; tickers with NaN accruals are excluded from the decile
    population (and don't receive the Sloan flag).
    """
    if not snapshots:
        return {}

    accruals = pd.Series(
        {t: _sloan_accruals(s) for t, s in snapshots.items()}, dtype=float
    )
    finite = accruals.dropna()
    sloan_enabled = len(finite) >= SLOAN_MIN_POPULATION
    sloan_threshold = (
        float(finite.quantile(SLOAN_TOP_DECILE)) if sloan_enabled else math.nan
    )

    out: dict[str, list[str]] = {}
    for ticker, snap in snapshots.items():
        flags: list[str] = []
        if _altman_distress(snap):
            flags.append("altman_distress")
        accrual_val = accruals.get(ticker)
        if (
            sloan_enabled
            and accrual_val is not None
            and isinstance(accrual_val, float)
            and math.isfinite(accrual_val)
            and accrual_val >= sloan_threshold
        ):
            flags.append("sloan_accruals_top_decile")
        out[ticker] = flags
    return out
