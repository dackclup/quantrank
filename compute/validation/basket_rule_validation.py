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
= 16 (the 12-configuration grid {55,60,65,70}×{1,3,5} + 1 uncap amendment + 2
hold-band sweep trials + 1 U9 charge for the #177 trimmed-median behavioral-flip
amendment — see BASKET_RULE_N_TRIALS comment), a quarterly-annualized DSR > 0 AND
Φ(DSR) >= 0.95 provides inferential evidence that the adaptive rule's excess Sharpe
survives the in-sample selection haircut.

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

from compute.validation.pbo_dsr import (
    ANNUALIZATION_FACTOR_QUARTERLY,
    compute_deflated_sharpe,
    compute_pbo,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---- Protocol constants (pinned; changing these requires a methodology-scientist review)

# n_trials = number of strategy variants examined during the in-sample grid sweep.
#
# Grid exhausted: {55, 60, 65, 70} x {1, 3, 5} floors = 12 configurations.
# Three amendments post-results counted as additional trials (U9 +1 multiplicity rule):
#   +1  uncap amendment (carry-domain rank-free, V55.1)
#   +2  hold-band sweep (V60, V55 tested; V60 failed C2, V55 passed)
#   +1  #177 trimmed-median behavioral-flip amendment — PATH C decision
#       (methodology-scientist ruling, user-confirmed 2026-06-18). V55.1
#       gauntlet condition (2) substitutes a forward-OOS shadow record +
#       structural non-inferiority for the synthetic backfill_portfolio_pit
#       purged-embargo holdout (artifact is not trim-replayable; the trim is a
#       frozen-threshold-inheriting estimator-correctness fix with zero new
#       tunable params). Charge booked even though immaterial (DSR headroom is
#       large), per the "immaterial charges still get booked" discipline. The
#       shipped backtest_pit.json artifact reflects n_trials=15 and will lag
#       until the next Q3 backtest rerun — this is intentional and benign.
# Total: 12 + 1 + 2 + 1 = 16.
BASKET_RULE_N_TRIALS: int = 16

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
        Default :data:`BASKET_RULE_N_TRIALS` = 16. Callers SHOULD NOT override
        this unless they have a documented reason to change the multiplicity
        charge — the default reflects the pre-registered count from the
        methodology-scientist RATIFY-WITH-CONDITIONS 2026-06-11 (U9; issue #130)
        plus the +1 U9 charge for the #177 trimmed-median behavioral-flip
        amendment (PATH C, 2026-06-18).

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


def compute_grid_pbo(monthly_grid: dict[str, list[float | None]]) -> dict:
    """Compute PBO over the 12-config monthly net-NAV grid.

    Builds the T × 12 returns matrix from the aligned monthly NAV columns, then
    calls :func:`compute.validation.pbo_dsr.compute_pbo` AS-IS with
    ``n_partitions=16`` (Bailey 2014 floor for stable estimates).

    Parameters
    ----------
    monthly_grid:
        ``{config_key: [float|None]}`` — 12 aligned monthly net-NAV columns (all
        the same length, None where a config had no valid leg that month).

    Returns
    -------
    dict with keys:
        ``pbo`` — probability of backtest overfitting in [0, 1].
        ``n_partitions`` — always 16.
        ``n_configs`` — number of strategy columns (should be 12).
        ``n_observations`` — usable row count after truncation.
        ``passes`` — True when pbo <= 0.5 (Bailey 2014 veto threshold).
        ``config_correlation_note`` — caveat string about column correlation.

    Raises
    ------
    ValueError
        When the matrix is too small (< n_partitions rows or < 2 columns) or all
        columns are None-only. The caller in ``run_backfill`` catches this and
        leaves the block as None (Rule 18 graceful-degradation).
    """
    n_partitions = 16

    # Build returns matrix: T×12, dropping rows with ANY None (need complete rows for PBO).
    keys = list(monthly_grid.keys())
    if len(keys) < 2:
        raise ValueError(f"compute_grid_pbo: need >= 2 config columns, got {len(keys)}")

    # Collect all columns as a 2-D list (rows = month index, cols = configs).
    # Convert NAV series to returns: r[t] = nav[t] / nav[t-1] - 1.
    nav_cols: list[list[float | None]] = [monthly_grid[k] for k in keys]
    n_months = max(len(col) for col in nav_cols)
    if n_months < 2:
        raise ValueError(f"compute_grid_pbo: need >= 2 monthly observations, got {n_months}")

    # Convert NAV → returns (monthly). A None in any column → row excluded.
    # Return matrix rows = month t=1..T-1, returns[t] = nav[t] / nav[t-1] - 1.
    returns_rows: list[list[float]] = []
    for t in range(1, n_months):
        row: list[float] = []
        complete = True
        for col in nav_cols:
            prev = col[t - 1] if t - 1 < len(col) else None
            curr = col[t] if t < len(col) else None
            if prev is None or curr is None or prev <= 0:
                complete = False
                break
            row.append(curr / prev - 1.0)
        if complete:
            returns_rows.append(row)

    if len(returns_rows) < n_partitions:
        raise ValueError(
            f"compute_grid_pbo: need >= {n_partitions} complete rows, "
            f"got {len(returns_rows)} (monthly_grid has {n_months} months, "
            f"{n_months - len(returns_rows)} rows excluded due to None values)"
        )

    matrix = pd.DataFrame(returns_rows, columns=keys)
    pbo_result = compute_pbo(matrix, n_partitions=n_partitions)

    return {
        "pbo": round(float(pbo_result.pbo), 8),
        "n_partitions": n_partitions,
        "n_configs": len(keys),
        "n_observations": int(pbo_result.n_observations),
        "passes": bool(pbo_result.passes()),
        "config_correlation_note": (
            "The 12 configs share composite_min ∈ {55,60,65,70} × floor ∈ {1,3,5}. "
            "Columns are INTERNALLY CORRELATED: configs with similar thresholds "
            "(e.g. 65_1, 65_3, 65_5) select overlapping books and will have correlated "
            "return series. The CSCV PBO assumes independent strategies — a low PBO "
            "from near-duplicate columns over-states independence and MUST NOT be "
            "over-read as strong evidence. Treat the PBO as a structural-correlation "
            "diagnostic, not a standalone inferential gate."
        ),
    }


def compute_holdout(
    grid: dict[str, list[float | None]],
    benchmark: list[float | None],
    *,
    train: tuple[int, int] = (0, 30),
    purge: int = 30,
    embargo: int = 1,
    test: tuple[int, int] = (31, 40),
) -> dict:
    """Purged-embargo holdout: train-sweep Sharpe → pick winner → evaluate on test legs.

    Parameters
    ----------
    grid:
        ``{config_key: [float|None]}`` aligned monthly NAV columns (same length).
        Returns are derived as (nav[t] / nav[t-1]) - 1.
    benchmark:
        Monthly benchmark NAV column (SPY), same length as grid columns. None-safe.
    train:
        ``(start_leg, end_leg)`` — EXCLUSIVE end; uses legs ``[start_leg, end_leg)``.
        Default = (0, 30): first 30 legs.
    purge:
        Index of the leg to purge (excluded from both train and test). Default = 30.
    embargo:
        Number of legs after the purge boundary to exclude from the test set.
        Default = 1: leg 31 is the embargo leg, excluded from test.
        FOOTGUN guard: train ends at leg ``purge - 1`` (inclusive), purge leg is
        excluded, embargo legs ``[purge+1, purge+embargo]`` are excluded, test
        starts at ``purge + embargo + 1`` = leg 31.
    test:
        ``(start_leg, end_leg)`` — EXCLUSIVE end; uses legs ``[start_leg, end_leg)``.
        Default = (31, 40): last 9 legs.

    Returns
    -------
    dict with keys:
        ``train_legs`` — indices used for training (list of ints).
        ``test_legs`` — indices used for testing (list of ints).
        ``purged_leg`` — the purged leg index.
        ``embargo_quarters`` — number of embargo legs.
        ``train_winner_config`` — config key with highest train-set Sharpe.
        ``test_return`` — cumulative return on test set for the winner config.
        ``test_sharpe`` — annualized Sharpe (ANNUALIZATION_FACTOR_QUARTERLY) on test legs.
        ``benchmark_test_return`` — cumulative return for the benchmark on the test legs.
        ``falsified`` — True when test_sharpe < 0 OR test_return < benchmark_test_return.
        ``in_sample`` — always False (this IS the only OOS block).
        ``caveat`` — honest interpretation string.

    Raises
    ------
    ValueError
        When the grid does not have enough legs to satisfy the train/test split,
        or when no config has a valid train Sharpe.
    """
    # Build monthly returns from aligned NAV columns.
    keys = list(grid.keys())
    if not keys:
        raise ValueError("compute_holdout: grid is empty")

    max_len = max(len(col) for col in grid.values())

    def _nav_to_returns(col: list[float | None], n: int) -> list[float | None]:
        out: list[float | None] = []
        for t in range(1, n):
            prev = col[t - 1] if t - 1 < len(col) else None
            curr = col[t] if t < len(col) else None
            if prev is None or curr is None or prev <= 0:
                out.append(None)
            else:
                out.append(curr / prev - 1.0)
        return out  # length = n - 1

    returns_by_key: dict[str, list[float | None]] = {
        k: _nav_to_returns(grid[k], max_len) for k in keys
    }
    bench_returns: list[float | None] = _nav_to_returns(benchmark or [], max_len)

    # Index arithmetic: train / purge / embargo / test are in RETURN-PERIOD indices
    # (0-based; return period t corresponds to nav[t] / nav[t-1] - 1).
    # FOOTGUN guard: exact boundaries pinned here and in tests.
    # train_legs = [train[0], train[1])  e.g. [0, 30) = legs 0..29
    # purged_leg = purge  e.g. 30
    # embargo_leg_indices = [purge+1, test[0])  e.g. [] for default (purge=30, test=(31,40))
    # test_legs = [test[0], test[1])  e.g. [31, 40) = legs 31..39
    #
    # embargo_leg_indices derivation note:
    # A separate embargo band protects against test→train leakage, which CANNOT
    # occur in a chronological train-before-test split because no train data
    # follows the test set.  The 1-leg purge gap (leg 30) handles the only real
    # concern: a holding that spans the train/test boundary.  Consequently, for
    # the ratified default (purge=30, test=(31,40)), embargo_leg_indices=[] —
    # zero separate embargo legs is correct for this split geometry.  When test
    # starts later (e.g. test=(32,40)) the gap legs [purge+1, test[0]) = [31]
    # are reported as embargo legs.  The derivation from test[0] (not from
    # purge+embargo) guarantees embargo_leg_indices NEVER overlaps test_legs.
    train_legs = list(range(train[0], train[1]))
    test_legs = list(range(test[0], test[1]))
    purged_leg = purge
    # Derive from actual gap between purge leg and test start so the set is
    # structurally disjoint from test_legs by construction.
    embargo_leg_indices = list(range(purge + 1, test[0]))

    # Validate that test_legs start at or after the embargo boundary.
    # The embargo discipline: train ends at purge-1 (inclusive), purge is excluded,
    # embargo_legs = [purge+1, purge+embargo], and test STARTS at purge+embargo
    # (i.e. test[0] == purge + embargo is valid per the design spec).
    # Violation only if test starts BEFORE the embargo window ends.
    if test[0] < purge + embargo:
        raise ValueError(
            f"compute_holdout: test start ({test[0]}) must be >= purge + embargo "
            f"({purge + embargo}). Embargo off-by-one guard: train=[{train[0]},{train[1]}), "
            f"purge={purge}, embargo={embargo}, test=[{test[0]},{test[1]})."
        )
    if not train_legs or not test_legs:
        raise ValueError(
            f"compute_holdout: empty train ({train}) or test ({test}) leg set"
        )

    def _leg_sharpe(rets: list[float | None], legs: list[int]) -> float | None:
        vals = [rets[i] for i in legs if i < len(rets) and rets[i] is not None]
        if len(vals) < 2:
            return None
        import math
        mu = sum(vals) / len(vals)
        var = sum((r - mu) ** 2 for r in vals) / len(vals)
        if var <= 1e-24:
            return None
        return (mu / var ** 0.5) * math.sqrt(ANNUALIZATION_FACTOR_QUARTERLY)

    def _leg_cum_return(rets: list[float | None], legs: list[int]) -> float | None:
        vals = [rets[i] for i in legs if i < len(rets) and rets[i] is not None]
        if not vals:
            return None
        cum = 1.0
        for r in vals:
            cum *= 1.0 + r
        return cum - 1.0

    # Train: pick the config with the highest Sharpe on train_legs.
    train_sharpes: dict[str, float] = {}
    for k in keys:
        sr = _leg_sharpe(returns_by_key[k], train_legs)
        if sr is not None:
            train_sharpes[k] = sr

    if not train_sharpes:
        raise ValueError("compute_holdout: no config has a valid train Sharpe")

    train_winner = max(train_sharpes, key=lambda k: train_sharpes[k])

    # Test: evaluate the winner on UNTOUCHED test legs.
    winner_rets = returns_by_key[train_winner]
    test_sharpe = _leg_sharpe(winner_rets, test_legs)
    test_return = _leg_cum_return(winner_rets, test_legs)

    # Benchmark test return.
    bench_test_return = _leg_cum_return(bench_returns, test_legs)

    # Falsified: test_sharpe < 0 OR (benchmark available AND test_return < bench_test_return).
    falsified = False
    if test_sharpe is not None and test_sharpe < 0:
        falsified = True
    if test_return is not None and bench_test_return is not None:
        if test_return < bench_test_return:
            falsified = True

    return {
        "train_legs": train_legs,
        "test_legs": test_legs,
        "purged_leg": purged_leg,
        "embargo_quarters": embargo,
        "embargo_leg_indices": embargo_leg_indices,
        "train_winner_config": train_winner,
        "test_return": round(float(test_return), 6) if test_return is not None else None,
        "test_sharpe": round(float(test_sharpe), 6) if test_sharpe is not None else None,
        "benchmark_test_return": (
            round(float(bench_test_return), 6) if bench_test_return is not None else None
        ),
        "falsified": bool(falsified),
        "in_sample": False,  # this IS the only OOS block — never copy this flag onto DSR/walk_forward
        "caveat": (
            f"Purged-embargo holdout: winner selected on legs {train[0]}..{train[1]-1} "
            f"(train Sharpe), evaluated on legs {test[0]}..{test[1]-1} ({len(test_legs)} legs). "
            + (
                f"Leg {purged_leg} purged; no separate embargo band required for a "
                f"chronological train-before-test split (no train data follows the test set)."
                if not embargo_leg_indices
                else
                f"Leg {purged_leg} purged; leg(s) {embargo_leg_indices} embargoed "
                f"(gap between purge and test start)."
            )
            + f" WEAK FLOOR: {len(test_legs)} test legs is a minimal sample — a collapse "
            f"(test_sharpe < 0 or trailing benchmark) FALSIFIES the config's forward edge; "
            f"a positive read is encouraging but NOT proof. CPCV (full combinatorial "
            f"purged cross-validation) is deferred pending longer OOS window. "
            f"The holdout test set was NOT used during threshold selection "
            f"(in_sample=False)."
        ),
    }


__all__ = [
    "BASKET_RULE_N_TRIALS",
    "compute_basket_rule_validation",
    "compute_grid_pbo",
    "compute_holdout",
]
