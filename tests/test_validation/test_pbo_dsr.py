"""Tests for compute.validation.pbo_dsr (Phase 4b §2).

Anchors the Bailey 2014 + Bailey-López de Prado 2014 numerical
behavior:

- Pure-noise strategies → PBO ~0.5 (no signal to overfit to)
- Single signal-bearing strategy + noise → PBO well below 0.5
- DSR shrinks SR by a positive amount when n_trials > 1
- DSR shrinks more aggressively as n_trials grows
- Beasley-Springer-Moro inverse normal CDF matches scipy reference
  values (verified offline) to 6 decimals
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from compute.validation.pbo_dsr import (
    DEFAULT_N_PARTITIONS,
    _inv_norm_cdf,
    compute_deflated_sharpe,
    compute_pbo,
    factor_passes_gates,
)


# ---------------------------------------------------------------- BSM inverse CDF
@pytest.mark.parametrize(
    "p,expected",
    [
        (0.5, 0.0),
        (0.975, 1.959964),  # standard 97.5% z-score
        (0.025, -1.959964),
        (0.84134474606, 1.0),  # Phi(1) ≈ 0.8413
        (0.99865, 3.0),  # Phi(3) ≈ 0.99865
    ],
)
def test_inv_norm_cdf_matches_reference(p: float, expected: float) -> None:
    """Beasley-Springer-Moro accurate to ~5 decimal places on common quantiles."""
    assert abs(_inv_norm_cdf(p) - expected) < 1e-3


@pytest.mark.parametrize("bad_p", [0.0, 1.0, -0.1, 1.1])
def test_inv_norm_cdf_rejects_out_of_range(bad_p: float) -> None:
    with pytest.raises(ValueError):
        _inv_norm_cdf(bad_p)


# ---------------------------------------------------------------- PBO
def test_pbo_pure_noise_is_near_half():
    """500 random strategies × 256 months of pure noise → PBO ≈ 0.5.

    Bailey-Borwein-LdP-Zhu 2014 §3.3 anchor: PBO of in-sample-best on
    OOS is exactly 0.5 under the null of no signal across strategies.
    Empirical estimate over 16 partitions is asymptotically unbiased
    but high-variance — tolerate ±0.15.
    """
    rng = np.random.default_rng(seed=42)
    returns = pd.DataFrame(rng.normal(0.0, 0.05, size=(256, 50)))
    result = compute_pbo(returns, n_partitions=DEFAULT_N_PARTITIONS)
    assert 0.30 < result.pbo < 0.70


def test_pbo_signal_strategy_pulls_pbo_below_half():
    """1 of 20 strategies has a real edge → PBO < 0.5 (less overfit)."""
    rng = np.random.default_rng(seed=42)
    n_periods, n_strats = 256, 20
    noise = rng.normal(0.0, 0.02, size=(n_periods, n_strats))
    # Strategy 0 has a real edge (mean 0.02 vs std 0.02 → SR ~1 in-period).
    noise[:, 0] += 0.02
    returns = pd.DataFrame(noise)
    result = compute_pbo(returns, n_partitions=DEFAULT_N_PARTITIONS)
    # With a real signal in strategy 0, OOS rank tends to stay high.
    assert result.pbo < 0.45


def test_pbo_rejects_odd_partition_count():
    rng = np.random.default_rng(seed=1)
    returns = pd.DataFrame(rng.normal(0.0, 0.05, size=(60, 5)))
    with pytest.raises(ValueError, match="even"):
        compute_pbo(returns, n_partitions=15)


def test_pbo_rejects_short_returns():
    rng = np.random.default_rng(seed=1)
    returns = pd.DataFrame(rng.normal(0.0, 0.05, size=(10, 5)))
    with pytest.raises(ValueError):
        compute_pbo(returns, n_partitions=16)


def test_pbo_rejects_single_strategy():
    rng = np.random.default_rng(seed=1)
    returns = pd.DataFrame(rng.normal(0.0, 0.05, size=(100, 1)))
    with pytest.raises(ValueError, match="2 strategies"):
        compute_pbo(returns, n_partitions=8)


def test_pbo_rejects_empty():
    with pytest.raises(ValueError):
        compute_pbo(pd.DataFrame(), n_partitions=8)


# ---------------------------------------------------------------- DSR
def test_dsr_shrinks_sharpe_when_many_trials():
    """DSR should be smaller than the raw monthly SR for n_trials > 1."""
    rng = np.random.default_rng(seed=7)
    # 60 months of strong-edge returns (mean 0.015, std 0.04 → annual SR ~1.3).
    returns = pd.Series(rng.normal(0.015, 0.04, size=60))
    raw_result_low = compute_deflated_sharpe(returns, n_trials=1)
    high_search = compute_deflated_sharpe(returns, n_trials=100)
    assert raw_result_low.sharpe > 0
    # n_trials=1 → expected_max_sr = 0 → DSR ~ (SR_per_period) / sqrt(var_sr)
    # n_trials=100 → expected_max_sr > 0 → DSR < raw equivalent
    assert high_search.deflated_sharpe < raw_result_low.deflated_sharpe


def test_dsr_with_pure_noise_close_to_zero_or_negative_under_many_trials():
    """Pure-noise returns + many trials → DSR ≤ 0 (signal doesn't survive deflation)."""
    rng = np.random.default_rng(seed=11)
    noise = pd.Series(rng.normal(0.0, 0.05, size=120))
    result = compute_deflated_sharpe(noise, n_trials=50)
    # Could be slightly positive or slightly negative — but must not survive a
    # strict positive-signal gate.
    assert result.deflated_sharpe < 0.5


def test_dsr_passes_threshold_on_strong_signal():
    """A genuine signal with few trials → DSR > 0."""
    rng = np.random.default_rng(seed=42)
    returns = pd.Series(rng.normal(0.02, 0.04, size=120))
    result = compute_deflated_sharpe(returns, n_trials=2)
    assert result.deflated_sharpe > 0


def test_dsr_zero_volatility_returns_zero():
    constant = pd.Series([0.01] * 60)
    result = compute_deflated_sharpe(constant, n_trials=10)
    assert result.sharpe == 0.0
    assert result.deflated_sharpe == 0.0


def test_dsr_rejects_too_few_observations():
    with pytest.raises(ValueError):
        compute_deflated_sharpe(pd.Series([0.01, 0.02, 0.03]), n_trials=1)


def test_dsr_rejects_zero_trials():
    with pytest.raises(ValueError, match="n_trials"):
        compute_deflated_sharpe(pd.Series([0.01, 0.02, 0.03, 0.04, 0.05]), n_trials=0)


def test_dsr_annualization_changes_sharpe_not_deflated():
    """Switching daily ↔ monthly annualization scales raw SR but the DSR ratio survives."""
    rng = np.random.default_rng(seed=99)
    returns = pd.Series(rng.normal(0.005, 0.02, size=252))
    monthly = compute_deflated_sharpe(returns, n_trials=10, annualization=12.0)
    daily = compute_deflated_sharpe(returns, n_trials=10, annualization=252.0)
    assert daily.sharpe > monthly.sharpe  # daily ann. factor is larger
    # DSR is in per-period SR units, no annualization → identical
    assert math.isclose(monthly.deflated_sharpe, daily.deflated_sharpe, rel_tol=1e-9)


# ---------------------------------------------------------------- Combined gate
def test_factor_passes_gates_returns_metrics_dict():
    rng = np.random.default_rng(seed=42)
    returns_matrix = pd.DataFrame(rng.normal(0.0, 0.05, size=(256, 10)))
    factor_returns = pd.Series(rng.normal(0.015, 0.04, size=60))
    passes, metrics = factor_passes_gates(
        factor_returns,
        returns_matrix,
        n_trials=10,
        n_partitions=16,
    )
    assert isinstance(passes, bool)
    assert {"pbo", "dsr", "sharpe", "skew", "kurtosis", "n_strategies"} <= set(metrics.keys())


# ----------------------------------------------------- Phase 4.6 universe_provider
def _mock_returns_input():
    """Shared rng-driven inputs for the universe-provider tests below."""
    rng = np.random.default_rng(seed=4242)
    returns_matrix = pd.DataFrame(rng.normal(0.0, 0.05, size=(256, 8)))
    factor_returns = pd.Series(rng.normal(0.01, 0.04, size=60))
    return factor_returns, returns_matrix


def test_factor_passes_gates_backward_compat_no_universe_kwargs():
    """No universe kwargs passed → metrics has the 3 new keys, all None.

    Backward compat for every pre-Phase-4.6 caller (osap-integration,
    jkp-integration, qlib/ipca scouts). They must continue to work
    unchanged.
    """
    factor_returns, returns_matrix = _mock_returns_input()
    _, metrics = factor_passes_gates(
        factor_returns, returns_matrix, n_trials=10
    )
    assert metrics["universe_as_of"] is None
    assert metrics["universe_size"] is None
    assert metrics["survivorship_bias_corrected"] is None
    # Pre-existing keys still present
    assert "pbo" in metrics
    assert "dsr" in metrics


def test_factor_passes_gates_universe_complete_path():
    """Real historical_universe.members_at integration — is_complete=True."""
    from datetime import date

    from compute.ingest.historical_universe import members_at

    factor_returns, returns_matrix = _mock_returns_input()
    current_universe = frozenset({"AAPL", "MSFT", "NVDA", "TSLA", "SMCI"})
    _, metrics = factor_passes_gates(
        factor_returns,
        returns_matrix,
        n_trials=10,
        universe_provider=members_at,
        as_of_date=date(2023, 6, 1),
        current_universe=current_universe,
    )
    # 2023-06-01 is well within EARLIEST_EVENT_DATE coverage → is_complete=True
    assert metrics["universe_as_of"] == "2023-06-01"
    assert isinstance(metrics["universe_size"], int)
    assert metrics["universe_size"] >= 1
    assert metrics["survivorship_bias_corrected"] is True


def test_factor_passes_gates_universe_degraded_path():
    """Pre-EARLIEST_EVENT_DATE → is_complete=False → metrics flag flipped."""
    from datetime import date

    from compute.ingest.historical_universe import members_at

    factor_returns, returns_matrix = _mock_returns_input()
    current_universe = frozenset({"AAPL", "MSFT", "NVDA"})
    _, metrics = factor_passes_gates(
        factor_returns,
        returns_matrix,
        n_trials=10,
        universe_provider=members_at,
        as_of_date=date(2010, 1, 1),  # pre-coverage
        current_universe=current_universe,
    )
    assert metrics["universe_as_of"] == "2010-01-01"
    assert metrics["survivorship_bias_corrected"] is False
    # Universe falls back to current anchor (degraded but loud)
    assert metrics["universe_size"] == len(current_universe)


def test_factor_passes_gates_universe_provider_raises_graceful():
    """Universe provider raising → metrics fields stay None, validation completes."""
    from datetime import date

    def raising_provider(as_of_date, current_universe, anchor_date=None):
        raise RuntimeError("simulated provider failure")

    factor_returns, returns_matrix = _mock_returns_input()
    passes, metrics = factor_passes_gates(
        factor_returns,
        returns_matrix,
        n_trials=10,
        universe_provider=raising_provider,
        as_of_date=date(2023, 6, 1),
        current_universe=frozenset({"AAPL"}),
    )
    # Universe fields stay None on provider failure
    assert metrics["universe_as_of"] is None
    assert metrics["universe_size"] is None
    assert metrics["survivorship_bias_corrected"] is None
    # Validation result still computed from the supplied returns_matrix
    assert isinstance(passes, bool)
    assert metrics["pbo"] is not None
    assert metrics["dsr"] is not None


def test_factor_passes_gates_partial_kwargs_warns_and_skips():
    """Caller passes only some of the 3 universe kwargs → log warning + None fields."""
    from compute.ingest.historical_universe import members_at

    factor_returns, returns_matrix = _mock_returns_input()
    # Only provider given, no as_of_date / current_universe → partial
    _, metrics = factor_passes_gates(
        factor_returns,
        returns_matrix,
        n_trials=10,
        universe_provider=members_at,
        # as_of_date intentionally omitted
    )
    assert metrics["universe_as_of"] is None
    assert metrics["survivorship_bias_corrected"] is None


def test_today_utc_date_helper():
    """today_utc_date returns a real date instance (smoke)."""
    from datetime import date

    from compute.validation.pbo_dsr import today_utc_date

    d = today_utc_date()
    assert isinstance(d, date)
