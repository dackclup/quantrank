"""PBO + Deflated Sharpe Ratio pre-integration gate (Phase 4b §2).

Per `.claude/skills/phase-4/defense-infrastructure/PLAN.md` §2. Any
Phase 4+ candidate factor (OSAP signal, JKP theme, Qlib feature, IPCA
exposure) must pass **both**:

1. **PBO ≤ 0.5** — Bailey, Borwein, López de Prado, Zhu (2014).
   *Combinatorially Symmetric Cross-Validation* estimates the
   probability the in-sample top configuration is below-median
   out-of-sample. PBO > 0.5 = factor is more likely backtest noise
   than signal.
2. **DSR > 0** — Bailey, López de Prado (2014). Deflates the
   Sharpe ratio for multiple-testing inflation. DSR > 0 = the post-
   deflation expected Sharpe is still positive after accounting for
   the number of variants tested.

Implementation
--------------

Pure numpy (no ``scipy``, no ``pypbo``). CSCV is a partition-and-
evaluate algorithm in O(n_partitions × log(n_partitions)) pandas. DSR
uses the analytic formula in Bailey-López de Prado 2014 eq. 11 — the
normal CDF / inverse-CDF inputs are approximated via Beasley-Springer-
Moro (1990) per Joshi's *More Mathematical Finance* §3.4. We chose
custom over `pypbo` + `scipy` to:

- Avoid a 50MB+ scipy install on the CI runner (Phase 4 is already
  adding pyqlib later; install footprint matters)
- Pin behavior to the published papers (no opaque library upgrades)
- Keep the math auditable in <300 LOC

Both functions are designed to be **called from later Phase 4 PRs**
(OSAP §4h, JKP §4i, Qlib §4j, IPCA §4k) at the point where each PR's
candidate factor produces a returns time series. This module ships
the library; the integration is the caller's responsibility.

Reference paper coverage
------------------------

CSCV: Bailey, Borwein, López de Prado, Zhu (2014). "The Probability
of Backtest Overfitting." *Journal of Computational Finance* 20(4),
39-69.

DSR: Bailey, López de Prado (2014). "The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting, and Non-
Normality." *Journal of Portfolio Management* 40(5), 94-107.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime
from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from compute.ingest.historical_universe import MembershipResult

logger = logging.getLogger(__name__)

PBO_VETO_THRESHOLD: float = 0.5
DSR_VETO_THRESHOLD: float = 0.0
DEFAULT_N_PARTITIONS: int = 16
ANNUALIZATION_FACTOR_MONTHLY: float = 12.0
ANNUALIZATION_FACTOR_DAILY: float = 252.0

# Beasley-Springer-Moro coefficients (1990) for inverse normal CDF.
# Accurate to ~7 decimal places over the (0.5, 1) tail we use.
_BSM_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_BSM_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_BSM_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_BSM_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)


def _inv_norm_cdf(p: float) -> float:
    """Beasley-Springer-Moro inverse standard-normal CDF.

    Returns z such that Phi(z) = p. Accurate to ~7 decimal places over
    p ∈ (0, 1). Replaces ``scipy.stats.norm.ppf`` so we don't pull
    scipy into the dep tree.
    """
    if p <= 0 or p >= 1:
        raise ValueError(f"_inv_norm_cdf requires 0 < p < 1, got {p}")
    p_low = 0.02425
    p_high = 1 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (
            ((((_BSM_C[0] * q + _BSM_C[1]) * q + _BSM_C[2]) * q + _BSM_C[3]) * q + _BSM_C[4]) * q
            + _BSM_C[5]
        ) / ((((_BSM_D[0] * q + _BSM_D[1]) * q + _BSM_D[2]) * q + _BSM_D[3]) * q + 1)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        num = (
            ((((_BSM_A[0] * r + _BSM_A[1]) * r + _BSM_A[2]) * r + _BSM_A[3]) * r + _BSM_A[4]) * r
            + _BSM_A[5]
        ) * q
        den = (((((_BSM_B[0] * r + _BSM_B[1]) * r + _BSM_B[2]) * r + _BSM_B[3]) * r + _BSM_B[4]) * r) + 1
        return num / den
    q = math.sqrt(-2 * math.log(1 - p))
    return -(
        ((((_BSM_C[0] * q + _BSM_C[1]) * q + _BSM_C[2]) * q + _BSM_C[3]) * q + _BSM_C[4]) * q
        + _BSM_C[5]
    ) / ((((_BSM_D[0] * q + _BSM_D[1]) * q + _BSM_D[2]) * q + _BSM_D[3]) * q + 1)


@dataclass(frozen=True)
class PBOResult:
    """Result of a CSCV PBO computation."""

    pbo: float
    """Probability of Backtest Overfitting in [0, 1]. > 0.5 = veto."""

    n_partitions: int
    n_strategies: int
    n_observations: int

    def passes(self, threshold: float = PBO_VETO_THRESHOLD) -> bool:
        return self.pbo <= threshold


@dataclass(frozen=True)
class DSRResult:
    """Result of a Deflated Sharpe Ratio computation."""

    sharpe: float
    """Raw Sharpe ratio (annualized)."""

    deflated_sharpe: float
    """Bailey-López de Prado 2014 DSR. > 0 = signal survives multiple-testing correction."""

    n_trials: int
    n_observations: int
    skew: float
    kurtosis: float

    def passes(self, threshold: float = DSR_VETO_THRESHOLD) -> bool:
        return self.deflated_sharpe > threshold


def _sample_moments(x: np.ndarray) -> tuple[float, float]:
    """Return (skew, excess_kurtosis) for a 1-D numpy array.

    Skew = E[((X-μ)/σ)^3]; excess kurtosis = E[((X-μ)/σ)^4] - 3.
    Replaces scipy.stats.skew / kurtosis (`bias=True` default) so we
    avoid the scipy dep.
    """
    n = len(x)
    if n < 4:
        return 0.0, 0.0
    mu = float(np.mean(x))
    sigma = float(np.std(x, ddof=0))
    if sigma <= 0:
        return 0.0, 0.0
    z = (x - mu) / sigma
    skew = float(np.mean(z**3))
    excess_kurtosis = float(np.mean(z**4) - 3.0)
    return skew, excess_kurtosis


def compute_pbo(
    returns_matrix: pd.DataFrame,
    *,
    n_partitions: int = DEFAULT_N_PARTITIONS,
) -> PBOResult:
    """Compute the Probability of Backtest Overfitting via CSCV.

    Per Bailey-Borwein-López de Prado-Zhu (2014):

    1. Split T rows into ``n_partitions`` slices of equal size (extra
       rows truncated from tail).
    2. For each ``C(n_partitions, n_partitions//2)`` choice of half-
       partitions:
       - In-sample (IS) = the chosen halves; out-of-sample (OOS) = the
         complement
       - Pick the strategy with the highest IS Sharpe
       - Record its OOS rank (1 = best OOS, N = worst OOS)
    3. PBO = fraction of trials where the IS-top strategy lands in the
       below-median OOS half.

    Parameters
    ----------
    returns_matrix:
        DataFrame indexed by time (rows) × strategy (columns). Cell
        ``[t, s]`` = strategy s's return at time t. Must have at least
        2 strategies and ``n_partitions`` observations.
    n_partitions:
        S in the Bailey 2014 paper. Default 16 (paper recommends 16
        for stable PBO estimates; even-numbered required).

    Returns
    -------
    PBOResult
    """
    if returns_matrix.empty:
        raise ValueError("returns_matrix must be non-empty")
    if returns_matrix.shape[1] < 2:
        raise ValueError("CSCV requires ≥2 strategies (columns)")
    if n_partitions < 4 or n_partitions % 2 != 0:
        raise ValueError(f"n_partitions must be even and ≥4, got {n_partitions}")
    t = len(returns_matrix)
    if t < n_partitions:
        raise ValueError(f"need ≥{n_partitions} rows, got {t}")

    # Truncate so the partition slices are equal-length.
    rows_per_partition = t // n_partitions
    usable_t = rows_per_partition * n_partitions
    data = returns_matrix.iloc[:usable_t].to_numpy(dtype=float)
    n_strategies = data.shape[1]

    # Index slices: list of arrays of row indices per partition.
    partition_indices = [
        np.arange(i * rows_per_partition, (i + 1) * rows_per_partition)
        for i in range(n_partitions)
    ]
    half = n_partitions // 2

    n_below_median = 0
    n_trials = 0
    for chosen in combinations(range(n_partitions), half):
        is_idx = np.concatenate([partition_indices[i] for i in chosen])
        oos_idx = np.concatenate(
            [partition_indices[i] for i in range(n_partitions) if i not in chosen]
        )

        is_returns = data[is_idx]
        oos_returns = data[oos_idx]

        # Sharpe ratio per strategy on each split (constant scale factor cancels in argmax).
        is_mean = is_returns.mean(axis=0)
        is_std = is_returns.std(axis=0, ddof=0)
        is_sharpe = np.divide(
            is_mean, is_std, out=np.zeros_like(is_mean), where=(is_std > 0)
        )
        is_top = int(np.argmax(is_sharpe))

        oos_mean = oos_returns.mean(axis=0)
        oos_std = oos_returns.std(axis=0, ddof=0)
        oos_sharpe = np.divide(
            oos_mean, oos_std, out=np.zeros_like(oos_mean), where=(oos_std > 0)
        )

        # Rank of is_top in OOS (1 = best, n_strategies = worst).
        # Ties broken arbitrarily — uses argsort order.
        oos_rank = int(np.argsort(np.argsort(-oos_sharpe))[is_top] + 1)
        relative = oos_rank / (n_strategies + 1)  # ω in Bailey 2014
        # PBO = Prob(ω > 0.5) = Prob(rank below median OOS).
        if relative > 0.5:
            n_below_median += 1
        n_trials += 1

    pbo = n_below_median / n_trials if n_trials > 0 else float("nan")
    return PBOResult(
        pbo=float(pbo),
        n_partitions=n_partitions,
        n_strategies=n_strategies,
        n_observations=usable_t,
    )


def compute_deflated_sharpe(
    returns: pd.Series | np.ndarray,
    *,
    n_trials: int,
    annualization: float = ANNUALIZATION_FACTOR_MONTHLY,
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio.

    Per Bailey-López de Prado 2014 eq. 11:

        DSR = (SR_obs - SR_*) / sqrt(Var(SR_obs))

    where SR_* is the expected maximum Sharpe ratio across ``n_trials``
    independent random strategies and Var(SR_obs) accounts for skew /
    kurtosis of the observed returns.

    Parameters
    ----------
    returns:
        1-D series of strategy returns. Period (monthly / daily) sets
        the ``annualization`` factor.
    n_trials:
        Number of strategy variants searched / examined (the multiple-
        testing correction factor). For Phase 4 OSAP: the number of
        OSAP signals considered for the same pillar.
    annualization:
        Period → annual Sharpe conversion. Monthly = sqrt(12); daily
        = sqrt(252). Default monthly per OSAP / JKP cadence.

    Returns
    -------
    DSRResult
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be ≥1, got {n_trials}")
    arr = np.asarray(returns, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 4:
        raise ValueError(f"need ≥4 non-NaN observations, got {n}")

    mu = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=0))
    # Numerical-stability guard: identical-value series have sigma ≈ 0
    # but float jitter can leave a 1e-19 residual that explodes SR.
    if sigma <= 1e-12 * max(1.0, abs(mu)):
        return DSRResult(
            sharpe=0.0,
            deflated_sharpe=0.0,
            n_trials=n_trials,
            n_observations=n,
            skew=0.0,
            kurtosis=0.0,
        )
    sharpe_per_period = mu / sigma
    sharpe = sharpe_per_period * math.sqrt(annualization)
    skew, excess_kurtosis = _sample_moments(arr)

    # Bailey-López de Prado 2014 eq. 9 — Var(SR) for non-normal returns.
    # Per-period SR variance; annualization handled by scaling DSR
    # numerator AND denominator the same way (cancels out).
    var_sr = (
        1.0 - skew * sharpe_per_period + ((excess_kurtosis) / 4.0) * sharpe_per_period**2
    ) / (n - 1)
    if var_sr <= 0:
        # Numerically degenerate (very high SR with positive skew + low kurtosis).
        return DSRResult(
            sharpe=sharpe,
            deflated_sharpe=0.0,
            n_trials=n_trials,
            n_observations=n,
            skew=skew,
            kurtosis=excess_kurtosis,
        )

    # Expected max SR across n_trials independent strategies — Bailey 2014 eq. 6.
    # Mixes Φ⁻¹(1 - 1/N) (the dominant Gumbel-like term) with the
    # Euler-Mascheroni correction Φ⁻¹(1 - 1/(N·e)).
    euler_gamma = 0.5772156649015329
    if n_trials == 1:
        expected_max_sr = 0.0
    else:
        emax_per_period = (1 - euler_gamma) * _inv_norm_cdf(
            1 - 1 / n_trials
        ) + euler_gamma * _inv_norm_cdf(1 - 1 / (n_trials * math.e))
        # Scale by per-period SR variance under null (= 1/sqrt(n-1) under
        # the standard-normal null for IID returns). The result is the
        # expected max in per-period SR units.
        expected_max_sr = emax_per_period * math.sqrt(var_sr)

    dsr = (sharpe_per_period - expected_max_sr) / math.sqrt(var_sr)
    return DSRResult(
        sharpe=sharpe,
        deflated_sharpe=float(dsr),
        n_trials=n_trials,
        n_observations=n,
        skew=skew,
        kurtosis=excess_kurtosis,
    )


def factor_passes_gates(
    factor_returns: pd.Series | np.ndarray,
    returns_matrix: pd.DataFrame,
    *,
    n_trials: int,
    n_partitions: int = DEFAULT_N_PARTITIONS,
    pbo_threshold: float = PBO_VETO_THRESHOLD,
    dsr_threshold: float = DSR_VETO_THRESHOLD,
    annualization: float = ANNUALIZATION_FACTOR_MONTHLY,
    universe_provider: Callable[[_date], MembershipResult] | None = None,
    as_of_date: _date | None = None,
    current_universe: set[str] | frozenset[str] | None = None,
) -> tuple[bool, dict]:
    """Run both gates and return (passes, metrics_dict).

    Phase 4 ``osap-integration/PLAN.md`` § Validation / ``jkp-integration/
    PLAN.md`` § Validation will call this to decide whether a candidate
    factor is accepted into pillar blending.

    Phase 4.6 (Research Report v1.0 §7.4) — optional ``universe_provider``
    kwarg lets the caller pass a ``Callable[[date], MembershipResult]``
    (typically ``functools.partial(historical_universe.members_at,
    current_universe=...)``) so the diagnostic dict carries honest
    universe provenance. The function does NOT filter ``returns_matrix``
    itself — that's the caller's responsibility (the caller knows which
    column → ticker mapping the matrix carries). What this function adds
    is the **observability surface**: when ``universe_provider`` returns
    a degraded (``is_complete=False``) result for ``as_of_date``, the
    metrics dict's ``survivorship_bias_corrected`` flag flips False so
    downstream Metadata + PR reviewers see the gap.

    Backward compatibility: when all 3 new kwargs are None (default),
    behavior is identical to pre-Phase-4.6. The 3 universe-related
    metric keys are emitted but populated as ``None``.

    Parameters
    ----------
    universe_provider:
        Optional callable ``(as_of_date, current_universe, anchor_date)
        -> MembershipResult``. Typically ``historical_universe.members_at``.
        When provided alongside ``as_of_date`` AND ``current_universe``,
        the function calls the provider once and includes the result's
        ``is_complete`` flag + ticker count in the metrics dict.
    as_of_date:
        The validation as-of date (when the historical backtest is
        evaluated). Defaults to None — when None, the provider call is
        skipped even if ``universe_provider`` is set, and the metrics
        ``universe_as_of`` is ``None``.
    current_universe:
        The current S&P 500 anchor set (typically ``set(
        get_sp500_constituents().ticker)``). Required when both
        ``universe_provider`` and ``as_of_date`` are provided.

    Returns
    -------
    (passes: bool, metrics: dict)
        ``metrics`` always contains the legacy 10 keys plus 3 new keys
        (``universe_as_of``, ``universe_size``, ``survivorship_bias_corrected``)
        populated either from the provider call or as ``None``.
    """
    pbo_result = compute_pbo(returns_matrix, n_partitions=n_partitions)
    dsr_result = compute_deflated_sharpe(
        factor_returns, n_trials=n_trials, annualization=annualization
    )
    passes = pbo_result.passes(pbo_threshold) and dsr_result.passes(dsr_threshold)
    metrics = {
        "pbo": pbo_result.pbo,
        "pbo_passes": pbo_result.passes(pbo_threshold),
        "dsr": dsr_result.deflated_sharpe,
        "dsr_passes": dsr_result.passes(dsr_threshold),
        "sharpe": dsr_result.sharpe,
        "skew": dsr_result.skew,
        "kurtosis": dsr_result.kurtosis,
        "n_observations": dsr_result.n_observations,
        "n_strategies": pbo_result.n_strategies,
        "n_partitions": pbo_result.n_partitions,
        "n_trials": n_trials,
        # Phase 4.6 observability — universe provenance for this validation
        # run. Populated only when the caller passes all 3 universe kwargs;
        # otherwise all 3 stay None (back-compat with pre-Phase-4.6 callers).
        "universe_as_of": None,
        "universe_size": None,
        "survivorship_bias_corrected": None,
    }

    if universe_provider is not None and as_of_date is not None and current_universe is not None:
        try:
            membership = universe_provider(
                as_of_date,
                current_universe=current_universe,
            )
            metrics["universe_as_of"] = membership.as_of_date.isoformat()
            metrics["universe_size"] = len(membership.tickers)
            metrics["survivorship_bias_corrected"] = bool(membership.is_complete)
            if not membership.is_complete:
                logger.warning(
                    "factor_passes_gates: degraded universe for as_of=%s — "
                    "is_complete=False, note=%r. Validation result still "
                    "computed, but survivorship_bias_corrected=False signals "
                    "caller to interpret with caution.",
                    as_of_date,
                    membership.note,
                )
        except Exception as exc:  # noqa: BLE001 — graceful degradation per Rule 18
            logger.warning(
                "factor_passes_gates: universe_provider raised %s for "
                "as_of=%s — metrics universe fields stay None. Validation "
                "result still computed from the supplied returns_matrix.",
                type(exc).__name__,
                as_of_date,
            )
    elif universe_provider is not None or as_of_date is not None or current_universe is not None:
        # Partial-kwarg case: caller passed SOME of the 3 but not all.
        # Likely an integration error — warn loud, don't fall over.
        logger.warning(
            "factor_passes_gates: universe_provider/as_of_date/current_universe "
            "must be passed together (got provider=%s, as_of_date=%s, "
            "current_universe=%s). Universe metrics stay None.",
            universe_provider is not None,
            as_of_date is not None,
            current_universe is not None,
        )
    return passes, metrics


def today_utc_date() -> _date:
    """Return today's UTC date — small helper for callers wiring as_of_date."""
    return datetime.utcnow().date()


__all__ = [
    "ANNUALIZATION_FACTOR_DAILY",
    "ANNUALIZATION_FACTOR_MONTHLY",
    "DEFAULT_N_PARTITIONS",
    "DSR_VETO_THRESHOLD",
    "DSRResult",
    "PBO_VETO_THRESHOLD",
    "PBOResult",
    "compute_deflated_sharpe",
    "compute_pbo",
    "factor_passes_gates",
    "today_utc_date",
]
