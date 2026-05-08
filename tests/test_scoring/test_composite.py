"""Unit tests for compute.scoring.composite."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from compute.scoring.composite import (
    ACTIVE_PILLARS_PHASE3,
    PHASE3_EFFECTIVE_WEIGHTS,
    PHASE3_WEIGHTS,
    compute_composite,
    neutralize_pillar_scores,
)


def test_phase3_weights_sum_to_one():
    assert math.isclose(sum(PHASE3_WEIGHTS.values()), 1.0)


def test_phase3_effective_weights_sum_to_one():
    # Pro-rata redistributed weights (active pillars only) must sum to 1.0.
    assert math.isclose(sum(PHASE3_EFFECTIVE_WEIGHTS.values()), 1.0)


def test_phase3_effective_weights_keep_relative_ratios():
    # Quality is 0.22 / 0.18 = 1.222... times Value in the original. The
    # ratio must survive redistribution unchanged.
    orig_ratio = PHASE3_WEIGHTS["quality"] / PHASE3_WEIGHTS["value"]
    eff_ratio = PHASE3_EFFECTIVE_WEIGHTS["quality"] / PHASE3_EFFECTIVE_WEIGHTS["value"]
    assert math.isclose(orig_ratio, eff_ratio)


def test_compute_composite_all_50_returns_50():
    # If every active pillar = 50, composite = 50 (regardless of weights).
    df = pd.DataFrame(
        {p: [50.0, 50.0] for p in ACTIVE_PILLARS_PHASE3}, index=["A", "B"]
    )
    out = compute_composite(df)
    assert math.isclose(out["A"], 50.0)
    assert math.isclose(out["B"], 50.0)


def test_compute_composite_weighted_mean_arithmetic():
    # Hand-computed: quality=100, value=0, others=50.
    pillar_values = {p: [50.0] for p in ACTIVE_PILLARS_PHASE3}
    pillar_values["quality"] = [100.0]
    pillar_values["value"] = [0.0]
    df = pd.DataFrame(pillar_values, index=["X"])
    out = compute_composite(df)
    expected = (
        100.0 * PHASE3_EFFECTIVE_WEIGHTS["quality"]
        + 0.0 * PHASE3_EFFECTIVE_WEIGHTS["value"]
        + 50.0
        * sum(
            PHASE3_EFFECTIVE_WEIGHTS[p]
            for p in ACTIVE_PILLARS_PHASE3
            if p not in ("quality", "value")
        )
    )
    assert math.isclose(out["X"], expected, abs_tol=1e-9)


def test_compute_composite_clips_to_0_100():
    # Even pathological inputs (>100) get clipped to [0, 100].
    df = pd.DataFrame({p: [150.0] for p in ACTIVE_PILLARS_PHASE3}, index=["A"])
    out = compute_composite(df)
    assert out["A"] == 100.0


def test_compute_composite_neutralizes_nan_to_50():
    # All active pillars NaN → composite = 50 with neutralize_missing=True.
    df = pd.DataFrame(
        {p: [float("nan")] for p in ACTIVE_PILLARS_PHASE3}, index=["A"]
    )
    out = compute_composite(df, neutralize_missing=True)
    assert math.isclose(out["A"], 50.0)


def test_compute_composite_rejects_bad_weights():
    df = pd.DataFrame({p: [50.0] for p in ACTIVE_PILLARS_PHASE3}, index=["A"])
    with pytest.raises(ValueError):
        compute_composite(df, weights={"quality": 0.5})  # sum != 1


def test_neutralize_pillar_scores_records_imputations():
    df = pd.DataFrame(
        {
            "quality": [80.0, float("nan")],
            "value": [float("nan"), 60.0],
            "growth": [70.0, 70.0],
        },
        index=["A", "B"],
    )
    out, imputed = neutralize_pillar_scores(df)
    assert math.isclose(out.at["A", "value"], 50.0)
    assert math.isclose(out.at["B", "quality"], 50.0)
    assert imputed["A"] == ["value"]
    assert imputed["B"] == ["quality"]


def test_phase3_inactive_pillars_excluded_from_effective_weights():
    # sentiment and ml must NOT appear in PHASE3_EFFECTIVE_WEIGHTS.
    assert "sentiment" not in PHASE3_EFFECTIVE_WEIGHTS
    assert "ml" not in PHASE3_EFFECTIVE_WEIGHTS
