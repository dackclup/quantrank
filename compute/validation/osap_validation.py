"""Phase 4h commit 4 — PBO/DSR hard gate for OSAP signal acceptance.

Wraps :func:`compute.validation.pbo_dsr.factor_passes_gates` (PR #60,
shipped in PR #60) per signal. No PBO or DSR math is reimplemented
here — this module only handles the *cohort framing* (wide pivot,
NaN policy, per-signal partitioning) needed to feed the existing
gate primitives correctly.

The gate is the linchpin of Phase 4h: 100 candidate OSAP signals
enter, only those passing PBO ≤ 0.5 AND DSR > 0 are blended into
``composite_score_osap_adjusted`` by commit 3's
:func:`compute.scoring.osap_blend.apply_osap_blend`. Signals rejected
here are surfaced via :data:`Metadata.osap_excluded_signals` so the
filter is fully auditable.

NaN policy — LOCKED 2026-05-18 post-source-audit of pbo_dsr.py
==============================================================

The two underlying primitives have asymmetric NaN tolerance:

- :func:`compute.validation.pbo_dsr.compute_pbo` (the cohort gate)
  is **NaN-UNSAFE**. Internally
  (``compute/validation/pbo_dsr.py:234``) it converts the cohort
  matrix to ``float`` numpy via ``.to_numpy(dtype=float)``, then
  computes ``.mean(axis=0)`` / ``.std(axis=0)`` (L256-257) and
  ``np.argmax`` (L261). Any NaN cell silently corrupts the argmax
  selection.
- :func:`compute.validation.pbo_dsr.compute_deflated_sharpe` (the
  per-signal gate) is **NaN-SAFE**. L323 strips NaN before computing
  Sharpe / skew / kurtosis: ``arr = arr[~np.isnan(arr)]``.

Because :func:`factor_passes_gates` takes the per-signal
``factor_returns`` and the cohort ``returns_matrix`` independently,
this wrapper feeds them **different NaN treatments**:

1. ``factor_returns`` ← ``wide[sig].dropna()`` — DSR's internal strip
   handles it. No information lost.
2. ``returns_matrix`` ← ``wide.fillna(0.0)`` — zero-fill, NOT
   mean-fill, NOT ``dropna(how='any')``.

Why **zero-fill** the cohort (rejecting the two competing options):

- ``dropna(how='any')`` decimates a 100-signal × monthly matrix
  below ``n_partitions=16`` rows once any earnings-event-only signal
  is included. The Bailey 2014 multiple-testing correction
  ``n_trials = cohort_size`` collapses.
- ``fillna(column_mean)`` deflates per-signal variance, inflates
  Sharpe, biases PBO toward false acceptance — and silently
  rewards sparse signals for low coverage.
- ``fillna(0.0)`` is the honest OSAP-semantic interpretation:
  absence-of-coverage for ``(signal, month)`` means "no portfolio
  formed / no information generated that month" — zero return is
  the right proxy. Bailey 2014 PBO is rank-based across strategies
  *within* each period; zero-imputation symmetrically pushes
  coverage-gap rows toward indeterminate cross-sectional rank,
  which honestly reflects "no information added".

Trade-off acknowledged: sparse-coverage signals (e.g., earnings-event-
only) see their Sharpe shrunk toward zero by the zero-fill, raising
their DSR rejection probability. This is cohort-fair but penalizes
legitimate event-only signals. Phase 4h scope accepts this — the
Phase 5 backtest harness (``defense-infrastructure/PLAN.md:270``)
runs full walk-forward CV per signal and replaces this gate when it
ships.

Standalone module
=================

Does NOT import from :mod:`compute.features.osap_replicate` (commit
2), :mod:`compute.scoring.osap_blend` (commit 3), or
:mod:`compute.main`. Validation runs on the long-short returns
DataFrame contract only (columns: ``signalname``, ``date``,
``ls_return``). This keeps the gate testable without the feature /
blend stack and lets commit 5's ``compute/main.py`` wire the three
layers independently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import pandas as pd

from compute.validation.pbo_dsr import (
    ANNUALIZATION_FACTOR_MONTHLY,
    DEFAULT_N_PARTITIONS,
    DSR_VETO_THRESHOLD,
    PBO_VETO_THRESHOLD,
    factor_passes_gates,
)

logger = logging.getLogger(__name__)

# Rolling-IC observability window (lag-1 Spearman over last 12 months).
# OBSERVABILITY ONLY — never gates acceptance. See module docstring.
ROLLING_IC_WINDOW_MONTHS: Final[int] = 12

# Per-signal observation floor before PBO/DSR is even attempted. Mirrors
# DEFAULT_N_PARTITIONS so that any signal with fewer non-NaN obs than
# PBO's partition requirement short-circuits to ``insufficient_data``.
MIN_OBS_PER_SIGNAL: Final[int] = DEFAULT_N_PARTITIONS


@dataclass(frozen=True)
class GateResult:
    """Per-signal verdict + metrics from the PBO/DSR gate.

    All three of ``pbo`` / ``dsr`` / ``sharpe`` are ``None`` when the
    signal short-circuited on ``insufficient_data`` — no PBO/DSR call
    was made. ``n_observations`` reports the count of non-NaN inputs
    that *would have been* used (informational; matches commit-5's
    coverage logging needs).

    ``rejection_reason`` is ``None`` when ``accepted=True``. Otherwise
    one of:

    - ``'high_pbo'`` — PBO exceeded the threshold (overfit risk)
    - ``'low_dsr'`` — Deflated Sharpe failed the threshold
    - ``'gate_failed'`` — both PBO and DSR failed (rare; surfaced as
      a distinct category for diagnostic clarity)
    - ``'insufficient_data'`` — per-signal obs < ``MIN_OBS_PER_SIGNAL``
      or cohort size < 2
    """

    accepted: bool
    pbo: float | None
    dsr: float | None
    sharpe: float | None
    n_observations: int
    rejection_reason: str | None


def _pivot_to_wide(
    long_short: pd.DataFrame,
    requested: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Coerce commit-2's long-format DF to a wide (date × signal) matrix.

    Commit 2's ``compute_long_short_returns`` (see
    ``compute/features/osap_replicate.py:140``) emits the ``date``
    column as ``object`` (string from the OSAP parquet pivot). We
    explicitly coerce to ``pd.Timestamp`` here so chronological
    ordering is reliable for the cohort matrix.

    Args:
        long_short: DataFrame with columns
            ``{signalname, date, ls_return}``.
        requested: optional restriction to a subset of signals. When
            ``None`` (default), all signals present in the input DF
            are kept.

    Returns:
        Wide DataFrame indexed by ``pd.Timestamp`` (sorted), columns =
        signalname, values = ls_return. Cells where a signal had no
        ``ls_return`` for a given date are NaN — caller decides the
        NaN policy (this function never fills).
    """
    if long_short.empty:
        return pd.DataFrame()

    df = long_short.copy()
    df["date"] = pd.to_datetime(df["date"])
    if requested is not None:
        df = df[df["signalname"].isin(set(requested))]
        if df.empty:
            return pd.DataFrame()

    wide = df.pivot_table(
        index="date",
        columns="signalname",
        values="ls_return",
        aggfunc="first",
    )
    return wide.sort_index()


def gate_osap_signals(
    long_short_returns: pd.DataFrame,
    requested_signals: tuple[str, ...] | None = None,
    pbo_threshold: float = PBO_VETO_THRESHOLD,
    dsr_threshold: float = DSR_VETO_THRESHOLD,
    n_partitions: int = DEFAULT_N_PARTITIONS,
) -> dict[str, GateResult]:
    """Apply the PBO/DSR hard gate per signal.

    Cohort framing follows Bailey 2014: ``n_trials = wide.shape[1]``
    (the count of candidate signals) so DSR's multiple-testing
    correction reflects the full screen. PBO operates on the
    zero-filled cohort matrix (see module docstring §NaN policy).

    Args:
        long_short_returns: commit-2 output. DataFrame with columns
            ``{signalname, date, ls_return}``.
        requested_signals: optional subset of signal names to gate.
            ``None`` (default) gates every signal present in the input.
        pbo_threshold: PBO must satisfy ``≤ pbo_threshold`` to pass.
            Default :data:`PBO_VETO_THRESHOLD` (= 0.5).
        dsr_threshold: DSR must satisfy ``> dsr_threshold`` to pass.
            Default :data:`DSR_VETO_THRESHOLD` (= 0.0).
        n_partitions: PBO partition count. Default
            :data:`DEFAULT_N_PARTITIONS` (= 16).

    Returns:
        ``{signalname: GateResult}``. Keys cover every signal that
        appeared in the (possibly ``requested_signals``-filtered)
        input. Empty dict when the input is empty or no requested
        signal exists in the input.
    """
    wide = _pivot_to_wide(long_short_returns, requested_signals)

    if wide.empty:
        logger.warning(
            "OSAP gate input empty after pivot — no signals to gate"
        )
        return {}

    cohort_size = wide.shape[1]
    n_dates = len(wide)

    # Cohort-level precondition: PBO needs at least ``n_partitions`` rows
    # and 2 strategy columns. If either fails, every signal short-
    # circuits to insufficient_data.
    cohort_too_small = cohort_size < 2 or n_dates < n_partitions

    # Zero-fill ONCE for the cohort matrix passed to PBO. See module
    # docstring §NaN policy for the rationale. The per-signal
    # ``factor_returns`` argument still uses dropna() (DSR strips NaN
    # internally, no information lost).
    cohort_matrix = wide.fillna(0.0)

    results: dict[str, GateResult] = {}

    for sig in wide.columns:
        signal_series = wide[sig]
        non_nan_obs = int(signal_series.notna().sum())

        if cohort_too_small or non_nan_obs < MIN_OBS_PER_SIGNAL:
            results[str(sig)] = GateResult(
                accepted=False,
                pbo=None,
                dsr=None,
                sharpe=None,
                n_observations=non_nan_obs,
                rejection_reason="insufficient_data",
            )
            continue

        passes, metrics = factor_passes_gates(
            factor_returns=signal_series.dropna(),
            returns_matrix=cohort_matrix,
            n_trials=cohort_size,
            n_partitions=n_partitions,
            pbo_threshold=pbo_threshold,
            dsr_threshold=dsr_threshold,
            annualization=ANNUALIZATION_FACTOR_MONTHLY,
        )

        if passes:
            reason: str | None = None
        elif not metrics["pbo_passes"] and not metrics["dsr_passes"]:
            reason = "gate_failed"
        elif not metrics["pbo_passes"]:
            reason = "high_pbo"
        elif not metrics["dsr_passes"]:
            reason = "low_dsr"
        else:
            # Defensive — passes=False but both sub-passes=True should be
            # impossible per the and-conjunction in factor_passes_gates.
            reason = "gate_failed"

        results[str(sig)] = GateResult(
            accepted=bool(passes),
            pbo=float(metrics["pbo"]),
            dsr=float(metrics["dsr"]),
            sharpe=float(metrics["sharpe"]),
            n_observations=int(metrics["n_observations"]),
            rejection_reason=reason,
        )

    n_accepted = sum(1 for r in results.values() if r.accepted)
    logger.info(
        "OSAP PBO/DSR gate: %d of %d signals accepted (cohort_size=%d, "
        "n_dates=%d, pbo_threshold=%.2f, dsr_threshold=%.2f)",
        n_accepted,
        len(results),
        cohort_size,
        n_dates,
        pbo_threshold,
        dsr_threshold,
    )
    return results


def compute_rolling_ic_12m(
    long_short_returns: pd.DataFrame,
    signalname: str,
) -> float | None:
    """Spearman rank correlation between LS return at ``t`` and ``t+1``.

    Observability metric only — :func:`gate_osap_signals` does not
    consult this. Surfaced via :data:`Metadata.osap_signals_ic_12m`
    for the UI / debug audit; the full walk-forward + purged +
    embargoed CV that would replace it is Phase 5 work per
    ``defense-infrastructure/PLAN.md:270``.

    Pure pandas — no scipy dependency. Matches the
    ``pbo_dsr.py`` precedent (Beasley-Springer-Moro inverse normal CDF
    is hand-rolled there to avoid scipy).

    Args:
        long_short_returns: commit-2 output. DataFrame with columns
            ``{signalname, date, ls_return}``.
        signalname: target signal to compute IC for.

    Returns:
        Spearman lag-1 IC over the most recent
        :data:`ROLLING_IC_WINDOW_MONTHS` observations, as ``float``.
        ``None`` when the signal has fewer than 12 valid
        ``(t, t+1)`` pairs (insufficient history).
    """
    df = long_short_returns[
        long_short_returns["signalname"] == signalname
    ].copy()
    if df.empty:
        return None

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").tail(ROLLING_IC_WINDOW_MONTHS + 1)

    if len(df) < ROLLING_IC_WINDOW_MONTHS + 1:
        return None

    ret = df["ls_return"].astype(float).reset_index(drop=True)
    lead = ret.shift(-1)
    valid = ret.notna() & lead.notna()

    if int(valid.sum()) < ROLLING_IC_WINDOW_MONTHS:
        return None

    ranks_t = ret[valid].rank(method="average")
    ranks_t1 = lead[valid].rank(method="average")
    corr = ranks_t.corr(ranks_t1)
    if pd.isna(corr):
        return None
    return float(corr)


def filter_accepted_signals(
    gate_results: dict[str, GateResult],
) -> tuple[list[str], list[str]]:
    """Split gate verdicts into (accepted, excluded) sorted lists.

    Feeds :data:`Metadata.osap_signals_used` /
    :data:`Metadata.osap_excluded_signals` in commit 5's
    ``compute/main.py`` wiring. Sorting is alphabetical for
    deterministic JSON output.

    Args:
        gate_results: ``{signalname: GateResult}`` from
            :func:`gate_osap_signals`.

    Returns:
        ``(accepted_sorted, excluded_sorted)``. Union of the two
        lists equals ``sorted(gate_results.keys())``.
    """
    accepted = sorted(s for s, r in gate_results.items() if r.accepted)
    excluded = sorted(s for s, r in gate_results.items() if not r.accepted)
    return accepted, excluded


__all__ = [
    "GateResult",
    "MIN_OBS_PER_SIGNAL",
    "ROLLING_IC_WINDOW_MONTHS",
    "compute_rolling_ic_12m",
    "filter_accepted_signals",
    "gate_osap_signals",
]
