"""Phase-A (no-rerun) OOS-validation protocol for the AI-pick adaptive backtest.

This module computes the Deflated Sharpe Ratio (DSR) gate and a walk-forward-
ANCHORED Sharpe stability report for the adaptive basket rule, using the existing
``backtest_pit.json`` artifact. It does NOT regenerate the artifact.

Scope + caveats
---------------
The adaptive thresholds (composite_min=65 / hold_band=55 / floor 5 / uncapped)
were grid-swept IN-SAMPLE on the same 40-quarter window that constitutes the
headline track record, then amended twice post-results (V55.0 -> V55.1 hold-band
carry-domain expansion; uncap amendment). The selection footprint of this in-sample
optimisation: the adaptive book's lead over the best fixed-N basket (by_count[8])
is approximately +127.7 pp, representing ~16% of total return — a tuning artifact
until OOS-confirmed.

The DSR (Bailey-López de Prado 2014) is the primary inferential gate. With n_trials
= 15 (the 12-configuration grid {55,60,65,70}×{1,3,5} + 1 uncap amendment + 2
hold-band sweep trials), a quarterly-annualized DSR > 0 AND Φ(DSR) >= 0.95 provides
inferential evidence that the adaptive rule's excess Sharpe survives the in-sample
selection haircut.

Walk-forward stability note
----------------------------
The ``walk_forward_sharpe_stability`` field is ANCHORED (grows from k0=16 legs),
NOT expanding-OOS. The threshold (composite_min=65) was chosen on all 40 legs; the
anchored Sharpe trajectory therefore measures PARAMETER STABILITY (robustness to
sample length), not out-of-sample performance. The field names use ``walk_forward``
for methodological precedent, but the embedded ``in_sample`` flag is set to True
and the field description is explicit — never re-label this as OOS.

Usage
-----
::

    import json
    from compute.validation.basket_rule_validation import compute_basket_rule_validation

    with open("frontend/public/data/portfolio/backtest_pit.json") as fh:
        artifact = json.load(fh)

    result = compute_basket_rule_validation(artifact)
    print(result)

Wire into ``meta.validation`` in :func:`scripts.backfill_portfolio_pit.run_backfill`
so future reruns carry the block without changing the current artifact.
"""

from __future__ import annotations

import bisect
import logging
import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from compute.validation.pbo_dsr import ANNUALIZATION_FACTOR_QUARTERLY, compute_deflated_sharpe

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---- Protocol constants (pinned; changing these requires a methodology-scientist review)

# n_trials = number of strategy variants examined during the in-sample grid sweep.
#
# Grid exhausted: {55, 60, 65, 70} x {1, 3, 5} floors = 12 configurations.
# Two amendments post-results counted as additional trials (U9 +1 multiplicity rule):
#   +1  uncap amendment (carry-domain rank-free, V55.1)
#   +2  hold-band sweep (V60, V55 tested; V60 failed C2, V55 passed)
# Total: 12 + 1 + 2 = 15. This is the pre-registered multiplicity charge per the
# methodology-scientist RATIFY-WITH-CONDITIONS 2026-06-11 (U9 rule; issue #130).
BASKET_RULE_N_TRIALS: int = 15

# Walk-forward anchor: start the anchored Sharpe trace at k0 legs so the estimate
# is not wildly unstable (at least k0 quarterly observations before reporting).
# Bailey 2014 recommends >= n_partitions=16 for PBO stability; we mirror that floor.
_WALK_FORWARD_K0: int = 16


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via error function (math.erf — no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _snap_to_trading_day(date_iso: str, dates: list[str]) -> str | None:
    """First trading day in ``dates`` on or after ``date_iso``.

    Falls back to the last available date when ``date_iso`` is past the end of the
    series. Returns ``None`` only when ``dates`` is empty.

    Mirrors the private ``_snap_to_trading_day`` in
    :mod:`scripts.backfill_portfolio_pit` (kept private there, duplicated here to
    avoid cross-layer import).
    """
    if not dates:
        return None
    i = bisect.bisect_left(dates, date_iso)
    return dates[i] if i < len(dates) else dates[-1]


def _extract_quarterly_returns(artifact: dict) -> pd.Series:
    """Extract per-leg quarterly returns from the adaptive net NAV series.

    The artifact's ``nav.adaptive.net`` is a daily NAV series indexed by
    ``nav.dates``. At each rebalance boundary the NAV is sampled on the snapped
    trading day (first trading day on/after the calendar rebalance date) and the
    per-leg return is computed as (NAV_end / NAV_start) - 1.

    The final leg runs from the last rebalance snap to the LAST day of the NAV
    series (the as-of date of the artifact), so the series always has exactly
    ``meta.rebalance_count`` observations — one per leg.

    Parameters
    ----------
    artifact:
        Loaded ``backtest_pit.json`` dict (full artifact).

    Returns
    -------
    pd.Series
        Per-leg quarterly returns, length == ``meta.rebalance_count``.

    Raises
    ------
    ValueError
        When the artifact is missing required keys or the adaptive NAV is empty.
    """
    nav_block = artifact.get("nav", {})
    dates: list[str] = nav_block.get("dates", [])
    adaptive_net: list[float | None] = nav_block.get("adaptive", {}).get("net", [])
    rebalances: list[dict] = artifact.get("rebalances", [])

    if not dates or not adaptive_net or not rebalances:
        raise ValueError(
            "compute_basket_rule_validation: artifact is missing nav.dates, "
            "nav.adaptive.net, or rebalances — cannot extract quarterly returns."
        )
    if len(dates) != len(adaptive_net):
        raise ValueError(
            f"compute_basket_rule_validation: nav.dates length ({len(dates)}) != "
            f"nav.adaptive.net length ({len(adaptive_net)}). Artifact is malformed."
        )

    # Snap each rebalance calendar date to the nearest trading day in the series.
    reb_dates = [r["date"] for r in rebalances]
    snap_dates: list[str] = []
    for rd in reb_dates:
        sd = _snap_to_trading_day(rd, dates)
        if sd is None:
            raise ValueError(
                f"compute_basket_rule_validation: could not snap rebalance {rd!r} "
                "to a trading day — dates list is empty."
            )
        snap_dates.append(sd)

    # Extract NAV value at each snapped rebalance date.
    date_to_idx: dict[str, int] = {d: i for i, d in enumerate(dates)}
    snap_navs: list[float] = []
    for sd in snap_dates:
        idx = date_to_idx.get(sd)
        if idx is None:
            raise ValueError(
                f"compute_basket_rule_validation: snapped date {sd!r} not in nav.dates."
            )
        val = adaptive_net[idx]
        if val is None:
            raise ValueError(
                f"compute_basket_rule_validation: adaptive net NAV is None at {sd!r}."
            )
        snap_navs.append(float(val))

    # The final leg ends at the last available NAV value (the as-of date).
    final_nav = next((v for v in reversed(adaptive_net) if v is not None), None)
    if final_nav is None:
        raise ValueError(
            "compute_basket_rule_validation: all adaptive net NAV values are None."
        )

    # Per-leg quarterly returns: (NAV[k+1] / NAV[k]) - 1.
    # Boundaries: snap_navs[0], snap_navs[1], ..., snap_navs[-1], final_nav.
    boundaries = snap_navs + [float(final_nav)]
    quarterly_returns = [
        (boundaries[i + 1] / boundaries[i]) - 1.0
        for i in range(len(snap_navs))
    ]

    n_expected = artifact.get("meta", {}).get("rebalance_count", len(rebalances))
    if len(quarterly_returns) != n_expected:
        logger.warning(
            "compute_basket_rule_validation: extracted %d quarterly returns but "
            "meta.rebalance_count=%d. Using the extracted count.",
            len(quarterly_returns),
            n_expected,
        )

    return pd.Series(quarterly_returns, dtype=float)


def _walk_forward_anchored_sharpe_stability(
    returns: pd.Series | np.ndarray,
    k0: int = _WALK_FORWARD_K0,
    annualization: float = ANNUALIZATION_FACTOR_QUARTERLY,
) -> dict:
    """Compute anchored-window Sharpe stability statistics.

    For k from k0 to len(returns), computes the frozen-rule annualized Sharpe
    on the leg series returns[0:k] (expanding anchor, not rolling). Reports
    min / max / mean / dispersion (max - min) of the resulting Sharpe trajectory.

    This is PARAMETER-STABILITY evidence, NOT out-of-sample validation. The
    adaptive threshold was chosen on the full window; the anchored trace shows
    whether the Sharpe estimate stabilised over time, not whether the rule
    generalises to new data.

    Parameters
    ----------
    returns:
        Per-leg quarterly returns (length N).
    k0:
        Minimum leg count before the first Sharpe estimate is included.
        Default 16 (mirrors Bailey 2014's PBO partition floor for stability).
    annualization:
        Annualization factor. Default ANNUALIZATION_FACTOR_QUARTERLY (= 4.0).

    Returns
    -------
    dict with keys:
        ``k0`` — first k included.
        ``k_max`` — final k (= len(returns)).
        ``sharpe_min`` — minimum anchored Sharpe across k=k0..k_max.
        ``sharpe_max`` — maximum anchored Sharpe across k=k0..k_max.
        ``sharpe_mean`` — mean anchored Sharpe.
        ``sharpe_dispersion`` — max - min (stability measure: smaller = more stable).
        ``in_sample`` — always True; marker so callers cannot mislabel this as OOS.
        ``label`` — human-readable caveat string.
    """
    arr = np.asarray(returns, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)

    if n < k0:
        return {
            "k0": k0,
            "k_max": n,
            "sharpe_min": None,
            "sharpe_max": None,
            "sharpe_mean": None,
            "sharpe_dispersion": None,
            "in_sample": True,
            "label": (
                "insufficient_data: fewer than k0 non-NaN observations "
                "(parameter-stability estimate not computable)"
            ),
        }

    sharpes: list[float] = []
    for k in range(k0, n + 1):
        sub = arr[:k]
        mu = float(np.mean(sub))
        sigma = float(np.std(sub, ddof=0))
        if sigma <= 1e-12 * max(1.0, abs(mu)):
            continue  # degenerate window — skip
        sr = (mu / sigma) * math.sqrt(annualization)
        sharpes.append(sr)

    if not sharpes:
        return {
            "k0": k0,
            "k_max": n,
            "sharpe_min": None,
            "sharpe_max": None,
            "sharpe_mean": None,
            "sharpe_dispersion": None,
            "in_sample": True,
            "label": "all_windows_degenerate",
        }

    return {
        "k0": k0,
        "k_max": n,
        "sharpe_min": round(float(min(sharpes)), 6),
        "sharpe_max": round(float(max(sharpes)), 6),
        "sharpe_mean": round(float(sum(sharpes) / len(sharpes)), 6),
        "sharpe_dispersion": round(float(max(sharpes) - min(sharpes)), 6),
        "in_sample": True,  # NEVER re-label as OOS — this is parameter-stability only
        "label": (
            "anchored_parameter_stability: anchored Sharpe trace (k=k0..k_max), "
            "NOT out-of-sample — threshold chosen on all k_max legs; "
            "dispersion measures estimate stability, not OOS predictability"
        ),
    }


def compute_basket_rule_validation(
    artifact: dict,
    *,
    n_trials: int = BASKET_RULE_N_TRIALS,
) -> dict:
    """Compute the DSR gate + walk-forward anchored stability for the adaptive basket rule.

    Uses the loaded ``backtest_pit.json`` dict (no network calls, no artifact
    regeneration). Extracts the adaptive net NAV at the 40 rebalance boundaries,
    converts to per-leg quarterly returns, and applies the existing
    :func:`compute.validation.pbo_dsr.compute_deflated_sharpe` AS-IS
    (ANNUALIZATION_FACTOR_QUARTERLY = 4.0, not the monthly default).

    Parameters
    ----------
    artifact:
        Loaded ``backtest_pit.json`` dict (full artifact, not a sub-section).
    n_trials:
        Number of strategy variants examined during the in-sample grid sweep.
        Default :data:`BASKET_RULE_N_TRIALS` = 15. Callers SHOULD NOT override
        this unless they have a documented reason to change the multiplicity
        charge — the default reflects the pre-registered count from the
        methodology-scientist RATIFY-WITH-CONDITIONS 2026-06-11 (U9; issue #130).

    Returns
    -------
    dict with keys:
        ``dsr`` — Deflated Sharpe Ratio (Bailey-López de Prado 2014).
            Positive = signal survives multiple-testing correction.
        ``dsr_confidence_phi`` — Φ(DSR): standard-normal CDF of DSR value.
            >= 0.95 is the headline inferential pass threshold.
        ``n_trials`` — multiplicity charge used for DSR (= ``n_trials`` argument).
        ``annualization_basis`` — always ``"quarterly"`` (ANNUALIZATION_FACTOR_QUARTERLY = 4.0).
        ``annualized_sharpe`` — raw (pre-deflation) annualized Sharpe of the adaptive net series.
        ``n_observations`` — number of quarterly legs included (== meta.rebalance_count).
        ``walk_forward_sharpe_stability`` — anchored-Sharpe stability dict; see
            :func:`_walk_forward_anchored_sharpe_stability`. The ``in_sample`` key is
            always True — this is PARAMETER STABILITY, not OOS.
        ``dsr_passes`` — True when DSR > 0 (the Bailey 2014 positive-DSR gate).
        ``phi_passes`` — True when Φ(DSR) >= 0.95 (the headline inferential gate).
        ``selection_footprint_note`` — disclaimer string quantifying the in-sample
            selection artifact.

    Raises
    ------
    ValueError
        When the artifact is missing required structure.
    """
    try:
        returns = _extract_quarterly_returns(artifact)
    except ValueError as exc:
        logger.error("compute_basket_rule_validation: return extraction failed: %s", exc)
        raise

    dsr_result = compute_deflated_sharpe(
        returns,
        n_trials=n_trials,
        annualization=ANNUALIZATION_FACTOR_QUARTERLY,
    )

    dsr_val = float(dsr_result.deflated_sharpe)
    phi = _norm_cdf(dsr_val)

    wf_stability = _walk_forward_anchored_sharpe_stability(
        returns,
        k0=_WALK_FORWARD_K0,
        annualization=ANNUALIZATION_FACTOR_QUARTERLY,
    )

    return {
        "dsr": round(dsr_val, 6),
        "dsr_confidence_phi": round(phi, 8),
        "n_trials": n_trials,
        "annualization_basis": "quarterly",
        "annualized_sharpe": round(float(dsr_result.sharpe), 6),
        "n_observations": int(dsr_result.n_observations),
        "walk_forward_sharpe_stability": wf_stability,
        "dsr_passes": bool(dsr_result.passes()),
        "phi_passes": bool(phi >= 0.95),
        "selection_footprint_note": (
            "The adaptive book's lead over the best fixed-N basket (by_count[8]) is "
            "approximately +127.7pp (~16% of total return). This excess is a tuning "
            "artifact from the in-sample grid sweep and is NOT out-of-sample confirmed. "
            "A positive DSR and Phi(DSR) >= 0.95 are necessary but not sufficient for "
            "OOS confirmation — the OOS-confirmation step requires a fresh live rebalance "
            "window not used during threshold selection."
        ),
    }


__all__ = [
    "BASKET_RULE_N_TRIALS",
    "compute_basket_rule_validation",
]
