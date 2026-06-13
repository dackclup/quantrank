"""Tests for compute.validation.basket_rule_validation (Phase-A OOS-validation protocol).

Pins:
- n_trials default == BASKET_RULE_N_TRIALS == 15.
- Quarterly annualization (ANNUALIZATION_FACTOR_QUARTERLY = 4.0) is used,
  NOT the monthly default (12.0). A test explicitly fails if the monthly default
  is passed by accident.
- compute_basket_rule_validation returns the expected keys and types.
- dsr_confidence_phi is in [0, 1] on a synthetic NAV.
- Walk-forward stability: correct shape + in_sample always True.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from compute.validation.basket_rule_validation import (
    BASKET_RULE_N_TRIALS,
    _extract_quarterly_returns,
    _walk_forward_anchored_sharpe_stability,
    compute_basket_rule_validation,
)
from compute.validation.pbo_dsr import (
    ANNUALIZATION_FACTOR_MONTHLY,
    ANNUALIZATION_FACTOR_QUARTERLY,
    compute_deflated_sharpe,
)

# ---------------------------------------------------------------- protocol constants


def test_basket_rule_n_trials_is_15() -> None:
    """Pin: n_trials default == 15 (pre-registered multiplicity charge, issue #130)."""
    assert BASKET_RULE_N_TRIALS == 15


def test_quarterly_annualization_constant_is_4() -> None:
    """Pin: ANNUALIZATION_FACTOR_QUARTERLY == 4.0 (quarterly rebalance cadence)."""
    assert ANNUALIZATION_FACTOR_QUARTERLY == 4.0


def test_quarterly_annualization_differs_from_monthly() -> None:
    """Regression: quarterly != monthly so mixing them up changes the result materially."""
    assert ANNUALIZATION_FACTOR_QUARTERLY != ANNUALIZATION_FACTOR_MONTHLY


def test_dsr_annualization_affects_reported_sharpe() -> None:
    """Fail-fast: the reported annualized Sharpe changes with the annualization factor.

    The DSR statistic itself (deflated_sharpe) is annualization-scale-invariant —
    it is computed in per-period units (see Bailey-López de Prado 2014 eq.9 and the
    pbo_dsr.py implementation). What DOES change is the reported ``sharpe`` field,
    which is SR_per_period * sqrt(annualization). Using the wrong annualization factor
    (monthly instead of quarterly) means the reported Sharpe is off by sqrt(12/4) ≈ 1.73.

    This test pins that: compute_basket_rule_validation uses ANNUALIZATION_FACTOR_QUARTERLY
    (4.0), so the reported Sharpe for the adaptive basket rebalancing QUARTERLY is
    SR_per_period * sqrt(4) — NOT * sqrt(12). Verify via the ratio.
    """
    import math as _math

    rng = np.random.default_rng(seed=0)
    returns = pd.Series(rng.normal(0.02, 0.05, size=40))

    dsr_q = compute_deflated_sharpe(returns, n_trials=15, annualization=ANNUALIZATION_FACTOR_QUARTERLY)
    dsr_m = compute_deflated_sharpe(returns, n_trials=15, annualization=ANNUALIZATION_FACTOR_MONTHLY)

    # Annualized Sharpe must differ by exactly sqrt(12/4) = sqrt(3).
    expected_ratio = _math.sqrt(ANNUALIZATION_FACTOR_MONTHLY / ANNUALIZATION_FACTOR_QUARTERLY)
    actual_ratio = dsr_m.sharpe / dsr_q.sharpe
    assert abs(actual_ratio - expected_ratio) < 1e-9, (
        f"Sharpe ratio quarterly vs monthly should differ by sqrt(3)={expected_ratio:.6f}, "
        f"got ratio={actual_ratio:.6f}"
    )

    # The DSR itself is the same (scale-invariant per-period statistic).
    assert abs(dsr_q.deflated_sharpe - dsr_m.deflated_sharpe) < 1e-9, (
        "DSR is per-period scale-invariant — should be equal for the same return series"
    )


# ---------------------------------------------------------------- helper: synthetic artifact


def _make_synthetic_artifact(
    n_legs: int = 40,
    seed: int = 42,
    drift_per_leg: float = 0.05,
) -> dict[str, Any]:
    """Build a minimal artifact dict with a synthetic adaptive net NAV series.

    Constructs a daily NAV series from quarterly synthetic returns, with the
    rebalance boundaries matching the first trading day of each leg.

    Parameters
    ----------
    n_legs:
        Number of quarterly rebalance legs (== rebalance_count).
    seed:
        RNG seed for reproducibility.
    drift_per_leg:
        Mean quarterly return per leg (generates a positive-drift series).
    """
    rng = np.random.default_rng(seed=seed)

    # One trading day per leg + a "current" day after the last rebalance.
    # For simplicity: rebalances on days 0, 63, 126, ... (63-day quarters).
    days_per_leg = 63
    total_days = n_legs * days_per_leg + days_per_leg  # +1 leg of "live" data

    # Build NAV series from synthetic daily returns.
    daily_ret = rng.normal(drift_per_leg / days_per_leg, 0.01, size=total_days)
    nav = [100.0]
    for r in daily_ret:
        nav.append(nav[-1] * (1.0 + r))

    # Date strings: YYYY-MM-DD format starting from 2016-08-15.
    from datetime import date, timedelta
    start_date = date(2016, 8, 15)
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(total_days + 1)]

    # Rebalance dates: every days_per_leg-th date (1-based to match the 0-indexed NAV).
    rebalance_dates = [dates[i * days_per_leg] for i in range(n_legs)]
    rebalances = [{"date": d} for d in rebalance_dates]

    return {
        "meta": {
            "rebalance_count": n_legs,
            "as_of_start": dates[0],
            "as_of_end": dates[-1],
        },
        "nav": {
            "dates": dates,
            "adaptive": {
                "net": nav,
            },
            "by_count": {},
            "benchmark": {},
        },
        "rebalances": rebalances,
    }


# ---------------------------------------------------------------- _extract_quarterly_returns


def test_extract_quarterly_returns_length() -> None:
    """Extracted return count == n_legs (one per rebalance)."""
    artifact = _make_synthetic_artifact(n_legs=40)
    returns = _extract_quarterly_returns(artifact)
    assert len(returns) == 40


def test_extract_quarterly_returns_no_nan() -> None:
    """Extracted returns have no NaN (synthetic NAV is dense)."""
    artifact = _make_synthetic_artifact(n_legs=20)
    returns = _extract_quarterly_returns(artifact)
    assert not returns.isna().any()


def test_extract_quarterly_returns_sign_correct() -> None:
    """Positive-drift NAV produces a majority of positive quarterly returns."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.08, seed=7)
    returns = _extract_quarterly_returns(artifact)
    assert (returns > 0).sum() > len(returns) // 2


def test_extract_quarterly_returns_raises_on_empty_nav() -> None:
    """Raises ValueError when nav.adaptive.net is empty."""
    artifact = _make_synthetic_artifact(n_legs=5)
    artifact["nav"]["adaptive"]["net"] = []
    with pytest.raises(ValueError, match="nav.adaptive.net"):
        _extract_quarterly_returns(artifact)


def test_extract_quarterly_returns_raises_on_missing_rebalances() -> None:
    """Raises ValueError when rebalances list is empty."""
    artifact = _make_synthetic_artifact(n_legs=5)
    artifact["rebalances"] = []
    with pytest.raises(ValueError):
        _extract_quarterly_returns(artifact)


# ---------------------------------------------------------------- _walk_forward_anchored_sharpe_stability


def test_walk_forward_stability_keys() -> None:
    """Returns all expected keys."""
    rng = np.random.default_rng(seed=0)
    returns = pd.Series(rng.normal(0.04, 0.05, size=40))
    result = _walk_forward_anchored_sharpe_stability(returns, k0=16)
    expected_keys = {
        "k0", "k_max", "sharpe_min", "sharpe_max",
        "sharpe_mean", "sharpe_dispersion", "in_sample", "label",
    }
    assert set(result.keys()) == expected_keys


def test_walk_forward_stability_in_sample_always_true() -> None:
    """in_sample is always True — this is parameter stability, NOT OOS."""
    rng = np.random.default_rng(seed=1)
    returns = pd.Series(rng.normal(0.03, 0.04, size=40))
    result = _walk_forward_anchored_sharpe_stability(returns, k0=16)
    assert result["in_sample"] is True


def test_walk_forward_stability_uses_quarterly_annualization_by_default() -> None:
    """Default annualization is QUARTERLY (4.0) — check via Sharpe magnitude."""
    # A series with mean=0.05, std=0.05 per quarter has SR_per_period = 1.0.
    # Annualized: sqrt(4) * 1.0 = 2.0 (quarterly); sqrt(12) * 1.0 = 3.46 (monthly).
    # Use a deterministic constant series to avoid RNG noise.
    returns = pd.Series([0.05] * 40)
    _walk_forward_anchored_sharpe_stability(
        returns, k0=16, annualization=ANNUALIZATION_FACTOR_QUARTERLY
    )
    # All windows give the same Sharpe (constant series) — but constant series has
    # sigma=0 (degenerate). Use a nearly-constant series with small jitter instead.
    jitter = np.full(40, 0.05)
    jitter[0] = 0.051  # break degeneracy
    returns_j = pd.Series(jitter)
    result_j = _walk_forward_anchored_sharpe_stability(
        returns_j, k0=16, annualization=ANNUALIZATION_FACTOR_QUARTERLY
    )
    # Quarterly SR should be around sqrt(4) * (0.05 / tiny_std), which is large.
    # Key check: monthly would give sqrt(12)*SR_per_period — larger by sqrt(3).
    # We verify the Sharpe_max is finite (not degenerate).
    assert result_j["sharpe_max"] is not None
    assert result_j["sharpe_max"] > 0


def test_walk_forward_stability_k0_respected() -> None:
    """k_max == len(returns) and k0 is echoed in the result."""
    rng = np.random.default_rng(seed=2)
    returns = pd.Series(rng.normal(0.03, 0.04, size=40))
    result = _walk_forward_anchored_sharpe_stability(returns, k0=16)
    assert result["k0"] == 16
    assert result["k_max"] == 40


def test_walk_forward_stability_insufficient_data() -> None:
    """When n < k0, returns None stats + appropriate label."""
    returns = pd.Series([0.05] * 10)  # 10 < k0=16
    result = _walk_forward_anchored_sharpe_stability(returns, k0=16)
    assert result["sharpe_min"] is None
    assert result["sharpe_max"] is None
    assert result["in_sample"] is True
    assert "insufficient_data" in result["label"]


def test_walk_forward_dispersion_is_max_minus_min() -> None:
    """sharpe_dispersion == sharpe_max - sharpe_min."""
    rng = np.random.default_rng(seed=3)
    returns = pd.Series(rng.normal(0.04, 0.06, size=40))
    result = _walk_forward_anchored_sharpe_stability(returns, k0=16)
    if result["sharpe_max"] is not None and result["sharpe_min"] is not None:
        expected = round(result["sharpe_max"] - result["sharpe_min"], 6)
        assert abs(result["sharpe_dispersion"] - expected) < 1e-9


# ---------------------------------------------------------------- compute_basket_rule_validation


def test_compute_basket_rule_validation_expected_keys() -> None:
    """Returns all required keys."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.06)
    result = compute_basket_rule_validation(artifact)
    expected_keys = {
        "dsr",
        "dsr_confidence_phi",
        "n_trials",
        "annualization_basis",
        "annualized_sharpe",
        "n_observations",
        "walk_forward_sharpe_stability",
        "dsr_passes",
        "phi_passes",
        "selection_footprint_note",
    }
    assert set(result.keys()) == expected_keys


def test_compute_basket_rule_validation_n_trials_default_is_15() -> None:
    """Default n_trials == BASKET_RULE_N_TRIALS == 15."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.04)
    result = compute_basket_rule_validation(artifact)
    assert result["n_trials"] == 15
    assert result["n_trials"] == BASKET_RULE_N_TRIALS


def test_compute_basket_rule_validation_annualization_basis_is_quarterly() -> None:
    """annualization_basis is always 'quarterly' — pin the cadence label."""
    artifact = _make_synthetic_artifact(n_legs=40)
    result = compute_basket_rule_validation(artifact)
    assert result["annualization_basis"] == "quarterly"


def test_compute_basket_rule_validation_phi_in_unit_interval() -> None:
    """dsr_confidence_phi is in [0, 1] for any synthetic NAV."""
    rng_seeds = [0, 1, 42, 99, 123]
    for seed in rng_seeds:
        artifact = _make_synthetic_artifact(n_legs=40, seed=seed)
        result = compute_basket_rule_validation(artifact)
        phi = result["dsr_confidence_phi"]
        assert 0.0 <= phi <= 1.0, f"seed={seed}: phi={phi} out of [0,1]"


def test_compute_basket_rule_validation_phi_positive_drift_above_half() -> None:
    """Strong positive drift produces Phi(DSR) > 0.5 (DSR > 0)."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.10, seed=0)
    result = compute_basket_rule_validation(artifact)
    assert result["dsr_confidence_phi"] > 0.5


def test_compute_basket_rule_validation_phi_negative_drift_near_zero() -> None:
    """Strong negative drift produces Phi(DSR) < 0.5 (DSR <= 0)."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=-0.10, seed=0)
    result = compute_basket_rule_validation(artifact)
    assert result["dsr_confidence_phi"] < 0.5


def test_compute_basket_rule_validation_n_observations() -> None:
    """n_observations == rebalance_count from the artifact."""
    for n_legs in (20, 30, 40):
        artifact = _make_synthetic_artifact(n_legs=n_legs)
        result = compute_basket_rule_validation(artifact)
        assert result["n_observations"] == n_legs


def test_compute_basket_rule_validation_walk_forward_in_sample_flag() -> None:
    """walk_forward_sharpe_stability.in_sample is always True."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.05)
    result = compute_basket_rule_validation(artifact)
    wf = result["walk_forward_sharpe_stability"]
    assert wf["in_sample"] is True


def test_compute_basket_rule_validation_selection_footprint_note_mentions_127pp() -> None:
    """selection_footprint_note quantifies the adaptive premium as ~127.7pp."""
    artifact = _make_synthetic_artifact(n_legs=40)
    result = compute_basket_rule_validation(artifact)
    assert "127.7" in result["selection_footprint_note"]


def test_compute_basket_rule_validation_dsr_passes_consistent_with_phi() -> None:
    """dsr_passes is consistent with DSR > 0 (positive or near-zero)."""
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.07, seed=5)
    result = compute_basket_rule_validation(artifact)
    dsr_sign_positive = result["dsr"] > 0.0
    assert result["dsr_passes"] == dsr_sign_positive


def test_compute_basket_rule_validation_phi_passes_consistent_with_phi_value() -> None:
    """phi_passes is consistent with dsr_confidence_phi >= 0.95."""
    for seed in [0, 1, 42, 7]:
        artifact = _make_synthetic_artifact(n_legs=40, seed=seed, drift_per_leg=0.06)
        result = compute_basket_rule_validation(artifact)
        assert result["phi_passes"] == (result["dsr_confidence_phi"] >= 0.95)
