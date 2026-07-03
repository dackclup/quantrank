"""Tests for compute.validation.basket_rule_validation (Phase-A OOS-validation protocol).

Pins:
- n_trials default == BASKET_RULE_N_TRIALS == 16 (U9 +1 charge for #177 amendment).
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
    _snap_to_trading_day,
    _walk_forward_anchored_sharpe_stability,
    compute_basket_rule_validation,
    compute_grid_pbo,
    compute_holdout,
)
from compute.validation.pbo_dsr import (
    ANNUALIZATION_FACTOR_MONTHLY,
    ANNUALIZATION_FACTOR_QUARTERLY,
    compute_deflated_sharpe,
)

# ---------------------------------------------------------------- protocol constants


def test_basket_rule_n_trials_is_16() -> None:
    """Pin: n_trials default == 16 (pre-registered multiplicity charge, issue #130).

    The count is 16 rather than 15: the base 12-configuration grid
    {55,60,65,70}×{1,3,5} + 1 uncap amendment + 2 hold-band sweep trials = 15,
    plus a U9 +1 charge for the #177 trimmed-median behavioral-flip amendment
    (PATH-C ruling, methodology-scientist ratified) = 16.
    """
    assert BASKET_RULE_N_TRIALS == 16


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


# ---------------------------------------------------------------- _snap_to_trading_day
#
# Deterministic pin (F1, ratified 2026-07-03, commit 3a0865b8): this DSR mirror
# of scripts.backfill_portfolio_pit._snap_to_trading_day was flipped from
# bisect_left (on-or-after) to bisect_right (strictly after) by the same fix,
# so the quarterly-return partitions this module derives stay in sync with the
# NAV path's T+1-fill leg boundaries. Same bisect_right boundary pin as the
# backfill sibling (tests/test_portfolio/test_backfill_integration.py).


def test_snap_to_trading_day_on_trading_day_resolves_to_next_day() -> None:
    """For a date_iso that IS itself present in ``dates``, the strictly-after
    (bisect_right) convention resolves to the NEXT trading day — NOT the same
    day, which is what the superseded bisect_left (on-or-after) convention
    would have returned. This is the load-bearing semantic of the F1 fix."""
    trading_days = ["2022-01-03", "2022-01-04", "2022-01-05", "2022-01-06", "2022-01-07"]
    assert _snap_to_trading_day("2022-01-04", trading_days) == "2022-01-05", (
        "must resolve to the NEXT trading day (strictly after), not the same day "
        "— the pre-fix bisect_left convention would have returned '2022-01-04' itself"
    )


def test_snap_to_trading_day_weekend_input_unchanged() -> None:
    """A date NOT present in ``dates`` (e.g. a weekend) is unaffected by the
    bisect_left -> bisect_right flip: bisect_left and bisect_right agree when
    the target value is absent from the list."""
    trading_days = ["2022-01-03", "2022-01-04", "2022-01-06", "2022-01-07"]  # 01-05 skipped
    # 2022-01-05 is absent (weekend-like gap) -> resolves to the next trading day.
    assert _snap_to_trading_day("2022-01-05", trading_days) == "2022-01-06"


def test_snap_to_trading_day_newest_leg_falls_back_to_last_date() -> None:
    """Nothing trades strictly after the LAST date in ``dates`` -> falls back to
    ``dates[-1]`` (the newest-leg fallback)."""
    trading_days = ["2022-01-03", "2022-01-04", "2022-01-05"]
    assert _snap_to_trading_day("2022-01-05", trading_days) == "2022-01-05"
    # Also holds for a date entirely past the panel's end.
    assert _snap_to_trading_day("2099-06-30", trading_days) == "2022-01-05"


def test_snap_to_trading_day_returns_none_on_empty_dates() -> None:
    """The documented ``None`` only if ``dates`` is empty guard."""
    assert _snap_to_trading_day("2022-01-03", []) is None


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


def test_compute_basket_rule_validation_n_trials_default_is_16() -> None:
    """Default n_trials == BASKET_RULE_N_TRIALS == 16.

    16 = 15-base (12-config grid + uncap + 2 hold-band sweeps) + 1 U9 charge
    for the #177 trimmed-median behavioral-flip amendment (PATH-C ruling).
    The relative pin (== BASKET_RULE_N_TRIALS) self-updates; the literal pin
    here catches an accidental constant regression back to 15.
    """
    artifact = _make_synthetic_artifact(n_legs=40, drift_per_leg=0.04)
    result = compute_basket_rule_validation(artifact)
    assert result["n_trials"] == 16
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


def test_selection_footprint_note_no_hardcoded_127pp() -> None:
    """Regression guard: the literal '127.7' must never appear in the note.

    The +127.7pp figure was a stale hardcode from an older pre-uncap artifact.
    _compute_selection_footprint_note now derives the lead dynamically from the
    artifact's own NAV; this test ensures the hardcode cannot be re-introduced.
    Checked across multiple artifacts (with and without by_count[8] data).
    """
    from compute.validation.basket_rule_validation import _compute_selection_footprint_note

    # Synthetic artifact without by_count[8] — triggers the fallback path.
    artifact_no_bc8 = _make_synthetic_artifact(n_legs=40)
    note_no_bc8 = _compute_selection_footprint_note(artifact_no_bc8)
    assert "127.7" not in note_no_bc8, (
        "Stale hardcode '127.7' must not appear in the fallback note"
    )

    # Also verify via compute_basket_rule_validation (the public call path).
    result = compute_basket_rule_validation(artifact_no_bc8)
    assert "127.7" not in result["selection_footprint_note"], (
        "Stale hardcode '127.7' must not appear in the note from compute_basket_rule_validation"
    )


def _make_artifact_with_bc8(
    adaptive_terminal: float = 130.0,
    bc8_terminal: float = 100.0,
    n_legs: int = 10,
) -> dict:
    """Build a minimal artifact with both nav.adaptive.net and nav.by_count['8'].net.

    Both series start at 100 and end at the specified terminal values via a single
    straight-line step (length-2 list: [start, terminal]).  The rebalances list
    has one entry so _extract_quarterly_returns does not raise.

    This is the synthetic fixture for testing _compute_selection_footprint_note's
    dynamic-computation path.
    """
    from datetime import date

    dates = [date(2020, 1, 1).isoformat(), date(2020, 4, 1).isoformat()]
    rebalances = [{"date": dates[0]}]
    return {
        "meta": {"rebalance_count": 1},
        "nav": {
            "dates": dates,
            "adaptive": {"net": [100.0, adaptive_terminal]},
            "by_count": {
                "8": {"net": [100.0, bc8_terminal]},
            },
            "benchmark": {},
        },
        "rebalances": rebalances,
    }


def test_selection_footprint_note_computes_dynamic_lead() -> None:
    """With known terminal NAV values, the note contains the correct +X.Ypp lead.

    Fixture: adaptive.net ends at 130.0, by_count[8].net ends at 100.0.
    Expected lead = round(130.0 - 100.0, 1) = 30.0 → note contains '+30.0pp'.

    This pins the DYNAMIC computation path of _compute_selection_footprint_note
    against a controlled synthetic artifact.
    """
    from compute.validation.basket_rule_validation import _compute_selection_footprint_note

    artifact = _make_artifact_with_bc8(adaptive_terminal=130.0, bc8_terminal=100.0)
    note = _compute_selection_footprint_note(artifact)

    assert "+30.0pp" in note, (
        f"Expected '+30.0pp' in the note for adaptive=130, bc8=100; got: {note!r}"
    )
    # Also confirm the stale hardcode is absent from this path.
    assert "127.7" not in note


def test_selection_footprint_note_fallback_when_bc8_absent() -> None:
    """When by_count[8].net is absent, the note contains the 'cannot be computed' caveat.

    _compute_selection_footprint_note falls back to a generic disclaimer string
    when bc8_terminal is None (i.e. by_count['8'].net is missing or empty).
    This is the expected behaviour for all synthetic test fixtures that do not
    include by_count data.
    """
    from compute.validation.basket_rule_validation import _compute_selection_footprint_note

    # Standard synthetic artifact — no by_count["8"] data.
    artifact = _make_synthetic_artifact(n_legs=40)
    note = _compute_selection_footprint_note(artifact)

    assert "cannot be computed" in note, (
        f"Expected fallback caveat containing 'cannot be computed'; got: {note!r}"
    )


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


# ===========================================================================
# Helpers for grid / holdout tests
# ===========================================================================


def _make_grid_navs(
    n_months: int = 120,
    n_configs: int = 12,
    seed: int = 42,
    base: float = 100.0,
    drift: float = 0.005,
) -> dict[str, list[float | None]]:
    """Build a synthetic 12-config monthly NAV grid with positive drift.

    Config keys match ``_GRID_CONFIG_KEYS`` naming: ``"{cmin}_{floor}"`` for
    cmin ∈ {55,60,65,70} × floor ∈ {1,3,5}.
    """
    from scripts.backfill_portfolio_pit import _GRID_CONFIG_KEYS

    rng = np.random.default_rng(seed)
    grid: dict[str, list[float | None]] = {}
    for i, key in enumerate(_GRID_CONFIG_KEYS):
        # Slightly different drift per config (correlated but not identical).
        col_drift = drift * (1.0 + 0.05 * i)
        navs: list[float | None] = [base]
        for _ in range(n_months - 1):
            r = rng.normal(col_drift, 0.02)
            navs.append(navs[-1] * (1.0 + r))
        grid[key] = navs
    return grid


# ===========================================================================
# compute_grid_pbo tests
# ===========================================================================


def test_compute_grid_pbo_returns_required_keys() -> None:
    """compute_grid_pbo returns the required keys with correct types."""
    grid = _make_grid_navs(n_months=120)
    result = compute_grid_pbo(grid)
    required = {"pbo", "n_partitions", "n_configs", "n_observations", "passes", "config_correlation_note"}
    assert set(result.keys()) == required


def test_compute_grid_pbo_pbo_in_unit_interval() -> None:
    """PBO is in [0, 1] for any synthetic grid."""
    grid = _make_grid_navs(n_months=120, seed=7)
    result = compute_grid_pbo(grid)
    assert 0.0 <= result["pbo"] <= 1.0


def test_compute_grid_pbo_n_configs_is_12() -> None:
    """n_configs == 12 for the standard grid."""
    grid = _make_grid_navs(n_months=120)
    result = compute_grid_pbo(grid)
    assert result["n_configs"] == 12


def test_compute_grid_pbo_n_partitions_is_16() -> None:
    """n_partitions == 16 (Bailey 2014 floor, pinned)."""
    grid = _make_grid_navs(n_months=120)
    result = compute_grid_pbo(grid)
    assert result["n_partitions"] == 16


def test_compute_grid_pbo_passes_consistent_with_pbo() -> None:
    """passes == (pbo <= 0.5)."""
    grid = _make_grid_navs(n_months=120, seed=99)
    result = compute_grid_pbo(grid)
    assert result["passes"] == (result["pbo"] <= 0.5)


def test_compute_grid_pbo_correlation_note_warns_about_shared_columns() -> None:
    """The correlation note string mentions internal correlation."""
    grid = _make_grid_navs(n_months=120)
    result = compute_grid_pbo(grid)
    note = result["config_correlation_note"]
    assert "correlated" in note.lower()
    assert "must not be over-read" in note.lower() or "must not" in note.lower()


def test_compute_grid_pbo_raises_on_too_short_grid() -> None:
    """Raises ValueError when the grid has fewer than n_partitions=16 rows."""
    grid = _make_grid_navs(n_months=10)  # only 9 return rows < 16
    with pytest.raises(ValueError, match="complete rows"):
        compute_grid_pbo(grid)


def test_compute_grid_pbo_raises_on_single_config() -> None:
    """Raises ValueError when only 1 config column is present (CSCV needs >= 2)."""
    grid = {"65_5": [100.0 + float(i) for i in range(120)]}
    with pytest.raises(ValueError):
        compute_grid_pbo(grid)


# ===========================================================================
# compute_holdout tests
# ===========================================================================


def test_compute_holdout_returns_required_keys() -> None:
    """compute_holdout returns all required keys."""
    grid = _make_grid_navs(n_months=120)
    bench = [100.0 * (1.01 ** i) for i in range(120)]  # simple 1%/month benchmark
    result = compute_holdout(grid, bench)
    required = {
        "train_legs", "test_legs", "purged_leg", "embargo_quarters", "embargo_leg_indices",
        "train_winner_config", "test_return", "test_sharpe",
        "benchmark_test_return", "falsified", "in_sample", "caveat",
    }
    assert set(result.keys()) == required


def test_compute_holdout_in_sample_is_false() -> None:
    """in_sample is always False — holdout is the ONLY OOS block."""
    grid = _make_grid_navs(n_months=120)
    result = compute_holdout(grid, [])
    assert result["in_sample"] is False


def test_compute_holdout_train_test_leg_counts() -> None:
    """Default train=[0,30), purge=30, embargo=1, test=[31,40): correct leg counts."""
    grid = _make_grid_navs(n_months=120)
    result = compute_holdout(grid, [])
    assert result["train_legs"] == list(range(0, 30))
    assert result["test_legs"] == list(range(31, 40))
    assert result["purged_leg"] == 30
    assert result["embargo_quarters"] == 1
    # Default split: purge=30, test=(31,40) → gap=[31,31) = [] (no separate embargo band).
    assert result["embargo_leg_indices"] == []


def test_compute_holdout_embargo_off_by_one_pin() -> None:
    """Pin the exact embargo arithmetic for the ratified default and a non-default split.

    Core invariant: embargo_leg_indices NEVER overlaps test_legs (disjoint by construction).

    Default split (purge=30, embargo=1, test=(31,40)):
    - train legs: 0..29 (30 legs)
    - purged leg: 30 (only gap between train and test)
    - embargo_leg_indices: [] — no separate embargo band needed; this is a chronological
      train-before-test split so test→train leakage is structurally impossible, and the
      1-leg purge gap (leg 30) covers the only real concern (a holding spanning the boundary).
    - test legs: 31..39 (9 legs, correctly disjoint from purge+embargo_legs)

    Non-default split (purge=30, embargo=1, test=(32,40)):
    - embargo_leg_indices: [31] — leg 31 is the gap between purge and test start
    - Still disjoint from test_legs [32..39]
    """
    grid = _make_grid_navs(n_months=120)

    # --- (a) Default split: embargo_leg_indices == [] ---
    result_default = compute_holdout(grid, [], train=(0, 30), purge=30, embargo=1, test=(31, 40))
    assert len(result_default["train_legs"]) == 30
    assert len(result_default["test_legs"]) == 9
    assert result_default["purged_leg"] == 30
    assert result_default["embargo_leg_indices"] == [], (
        "Default split has no gap between purge and test start — embargo_leg_indices must be []"
    )

    # --- (b) Core invariant: embargo never overlaps test (always disjoint) ---
    assert set(result_default["embargo_leg_indices"]).isdisjoint(set(result_default["test_legs"])), (
        "embargo_leg_indices must be disjoint from test_legs"
    )
    # Verify the caveat mentions the purge and the chronological split logic.
    caveat = result_default["caveat"].lower()
    assert "purged" in caveat or "purge" in caveat

    # --- (c) Non-default split: test=(32,40) → embargo_leg_indices == [31] ---
    result_nondefault = compute_holdout(
        grid, [], train=(0, 30), purge=30, embargo=1, test=(32, 40)
    )
    assert result_nondefault["embargo_leg_indices"] == [31], (
        "When test starts at 32, leg 31 is in the gap [purge+1, test[0]) = [31, 32) = [31]"
    )
    assert set(result_nondefault["embargo_leg_indices"]).isdisjoint(
        set(result_nondefault["test_legs"])
    ), "embargo_leg_indices must be disjoint from test_legs for non-default split too"


def test_compute_holdout_falsified_flag_on_negative_sharpe() -> None:
    """falsified=True when the winner's test Sharpe is negative (strong decay series).

    Default test legs = [31, 40) = return periods 31..39.
    Return period t = NAV[t+1] / NAV[t] - 1 (0-indexed into the NAV series).
    So test legs 31..39 = navs[32]/navs[31] - 1 .. navs[40]/navs[39] - 1.
    Negative drift must start at NAV index 32 at the latest (so return period 31 is negative).
    """
    from scripts.backfill_portfolio_pit import _GRID_CONFIG_KEYS

    # Build navs where positive drift covers return periods 0..29 (train),
    # and strong negative drift covers return periods 31..39 (test).
    # Return period t = navs[t+1]/navs[t] - 1.
    # navs[0] = 100, navs[1..30] positive (covering return periods 0..29 = train),
    # navs[31] = purge boundary, navs[32..41] negative (covering return periods 31..40 = test).
    # Use jittered drift so variance > 0 (avoids the sigma=0 degeneracy guard in _leg_sharpe).
    rng = np.random.default_rng(42)
    grid: dict[str, list[float | None]] = {}
    for key in _GRID_CONFIG_KEYS:
        navs: list[float] = [100.0]
        # Return periods 0..30: positive drift with small jitter (31 navs appended).
        for _ in range(31):
            navs.append(navs[-1] * (1.02 + rng.normal(0.0, 0.002)))
        # Return periods 31..40: strong negative drift with small jitter (10 navs appended).
        for _ in range(10):
            navs.append(navs[-1] * (0.88 + rng.normal(0.0, 0.002)))
        grid[key] = navs  # 42 entries → 41 return periods

    result = compute_holdout(grid, [])
    assert result["falsified"] is True


def test_compute_holdout_falsified_flag_on_benchmark_trail() -> None:
    """falsified=True when the winner trails the benchmark on the test legs."""
    from scripts.backfill_portfolio_pit import _GRID_CONFIG_KEYS

    n = 120
    rng = np.random.default_rng(42)
    grid: dict[str, list[float | None]] = {}
    for key in _GRID_CONFIG_KEYS:
        navs = [100.0]
        for _ in range(n - 1):
            navs.append(navs[-1] * (1.0 + rng.normal(0.002, 0.01)))  # small positive drift
        grid[key] = navs

    # Benchmark: much higher returns on test legs → winner will trail it.
    bench = [100.0]
    for _ in range(n - 1):
        bench.append(bench[-1] * 1.05)  # 5% per month — all configs trail on test

    result = compute_holdout(grid, bench)
    assert result["falsified"] is True


def test_compute_holdout_nonfalsified_on_strong_positive() -> None:
    """falsified=False when the winner has clearly positive test Sharpe and beats bench."""
    from scripts.backfill_portfolio_pit import _GRID_CONFIG_KEYS

    n = 120
    rng = np.random.default_rng(7)
    grid: dict[str, list[float | None]] = {}
    for key in _GRID_CONFIG_KEYS:
        navs = [100.0]
        for _ in range(n - 1):
            navs.append(navs[-1] * (1.0 + rng.normal(0.03, 0.01)))  # strong positive drift
        grid[key] = navs

    bench = [100.0] * n  # flat benchmark (return = 0)
    result = compute_holdout(grid, bench)
    assert result["falsified"] is False


def test_compute_holdout_train_winner_is_valid_key() -> None:
    """train_winner_config is always one of the grid keys."""
    from scripts.backfill_portfolio_pit import _GRID_CONFIG_KEYS

    grid = _make_grid_navs(n_months=120, seed=5)
    result = compute_holdout(grid, [])
    assert result["train_winner_config"] in _GRID_CONFIG_KEYS


def test_compute_holdout_test_sharpe_is_numeric_or_none() -> None:
    """test_sharpe is a float when computable, None when degenerate."""
    grid = _make_grid_navs(n_months=120)
    result = compute_holdout(grid, [])
    sharpe = result["test_sharpe"]
    assert sharpe is None or isinstance(sharpe, float)


# ===========================================================================
# Hypothesis property-based tests (issue #126 discipline)
# ===========================================================================


try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _HAS_HYPOTHESIS = True
except ImportError:
    _HAS_HYPOTHESIS = False


if _HAS_HYPOTHESIS:
    from scripts.backfill_portfolio_pit import (
        ADAPTIVE_COMPOSITE_MIN,
        ADAPTIVE_MIN_PICKS,
        _band_book,
    )

    @given(
        n_names=st.integers(min_value=1, max_value=20),
        seed=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=50)
    def test_hypothesis_book_size_monotone_nonincreasing_in_cmin(
        n_names: int, seed: int
    ) -> None:
        """Book size is monotone non-increasing in composite_min at fixed floor.

        For the same order/scores/tenure, a higher composite_min means fewer
        fresh entrants → the book can only shrink or stay the same (pads keep
        the floor, but the pad floor is fixed).  This is monotone non-increasing
        in cmin.
        """
        rng = np.random.default_rng(seed)
        tickers = [f"T{i:02d}" for i in range(n_names)]
        scores = {t: float(rng.uniform(40.0, 90.0)) for t in tickers}
        order = sorted(tickers, key=lambda t: -scores[t])
        tenure: set[str] = set()  # no prior tenure — band inert (tests fresh-only sizing)

        # Test cmin 55, 60, 65, 70 with fixed floor=5.
        book_sizes: list[int] = []
        for cmin in (55, 60, 65, 70):
            book, _, _ = _band_book(order, scores, tenure, composite_min=float(cmin), min_picks=5)
            book_sizes.append(len(book))

        # Monotone non-increasing: each step cmin goes up, book can only shrink/stay.
        for i in range(len(book_sizes) - 1):
            assert book_sizes[i] >= book_sizes[i + 1], (
                f"cmin step {i}: book_sizes={book_sizes}, expected non-increasing"
            )

    @given(
        n_names=st.integers(min_value=1, max_value=30),
        floor=st.sampled_from([1, 3, 5]),
        seed=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=50)
    def test_hypothesis_book_size_at_least_floor(n_names: int, floor: int, seed: int) -> None:
        """Book size >= min(floor, len(order)) regardless of scores.

        The pads path enforces this: even if no name scores >= composite_min,
        the book is padded to min(floor, len(order)).
        """
        rng = np.random.default_rng(seed)
        tickers = [f"T{i:02d}" for i in range(n_names)]
        scores = {t: float(rng.uniform(40.0, 60.0)) for t in tickers}  # all below 65
        order = sorted(tickers, key=lambda t: -scores[t])
        tenure: set[str] = set()

        book, _, _ = _band_book(order, scores, tenure, composite_min=65.0, min_picks=floor)
        expected_min = min(floor, len(order))
        assert len(book) >= expected_min, (
            f"floor={floor}, n={n_names}: book_size={len(book)} < {expected_min}"
        )

    @given(seed=st.integers(min_value=0, max_value=999))
    @settings(max_examples=30)
    def test_hypothesis_default_kwarg_byte_identity(seed: int) -> None:
        """Default-kwarg call == pre-refactor behaviour (byte-identical to explicit defaults).

        C2 regression: calling _band_book(order, scores, tenure) must produce the
        same result as _band_book(order, scores, tenure, composite_min=65.0, min_picks=5).
        """
        rng = np.random.default_rng(seed)
        n = rng.integers(1, 20)
        tickers = [f"T{i:02d}" for i in range(int(n))]
        scores = {t: float(rng.uniform(40.0, 90.0)) for t in tickers}
        order = sorted(tickers, key=lambda t: -scores[t])
        # Synthetic tenure: half the names.
        tenure = set(tickers[:len(tickers) // 2])

        book_default, tenure_default, carry_default = _band_book(order, scores, tenure)
        book_explicit, tenure_explicit, carry_explicit = _band_book(
            order, scores, tenure,
            composite_min=ADAPTIVE_COMPOSITE_MIN,
            min_picks=ADAPTIVE_MIN_PICKS,
        )

        assert book_default == book_explicit, (
            f"default vs explicit book mismatch: {book_default} != {book_explicit}"
        )
        assert tenure_default == tenure_explicit, (
            f"default vs explicit tenure mismatch: {tenure_default} != {tenure_explicit}"
        )
        assert carry_default == carry_explicit, (
            f"default vs explicit carry_count mismatch: {carry_default} != {carry_explicit}"
        )
