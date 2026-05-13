"""Unit tests for compute.scoring.composite."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from compute.scoring.composite import (
    ACTIVE_PILLARS_PHASE3,
    PHASE3_EFFECTIVE_WEIGHTS,
    PHASE3_WEIGHTS,
    PILLAR_LABEL_MAP,
    build_sector_pillar_baselines,
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


# ---------------------------------------------------------------------------
# Issue #34 — per-sector pillar-median baseline for the stock-detail UI.
# ---------------------------------------------------------------------------


def _make_pillar_df(values: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Build a pillar_df from ``{ticker: {pillar: score}}``."""
    return pd.DataFrame.from_dict(values, orient="index")


def test_I1_baseline_built_for_each_sector_above_min_peers():
    """A 12-ticker IT sector + a 12-ticker Energy sector each emit a
    baseline with the expected label + median values."""
    pillar_df = _make_pillar_df(
        {f"IT{i}": {"quality": float(i * 10), "value": 50.0} for i in range(12)}
        | {f"EN{i}": {"quality": float(i * 5), "value": 30.0} for i in range(12)}
    )
    by_sector = {
        "Information Technology": [f"IT{i}" for i in range(12)],
        "Energy": [f"EN{i}" for i in range(12)],
    }
    out = build_sector_pillar_baselines(pillar_df, by_sector, min_peers=10)
    assert "Information Technology" in out
    assert "Energy" in out
    # IT median of [0,10,20,...,110] is 55.0
    assert out["Information Technology"]["values"]["Quality"] == 55.0
    assert out["Information Technology"]["label"] == (
        "Information Technology median (n=12)"
    )
    # Value is constant 50.0 for IT, constant 30.0 for Energy
    assert out["Information Technology"]["values"]["Value"] == 50.0
    assert out["Energy"]["values"]["Value"] == 30.0


def test_I2_sector_below_min_peers_omitted():
    """A sector with n < min_peers is absent from the result entirely,
    not emitted with null values."""
    pillar_df = _make_pillar_df(
        {f"T{i}": {"quality": 50.0} for i in range(5)}
    )
    by_sector = {"Tiny": [f"T{i}" for i in range(5)]}
    out = build_sector_pillar_baselines(pillar_df, by_sector, min_peers=10)
    assert "Tiny" not in out
    assert out == {}


def test_I3_pillar_all_null_in_sector_yields_none_value():
    """A pillar with no finite values in a sector maps to None in the
    baseline (not a synthetic 0 or 50)."""
    df = _make_pillar_df(
        {f"T{i}": {"quality": float(i * 10)} for i in range(10)}
    )
    # 'value' column is entirely missing — pandas treats it as absent
    by_sector = {"S": [f"T{i}" for i in range(10)]}
    out = build_sector_pillar_baselines(df, by_sector, min_peers=10)
    assert out["S"]["values"]["Quality"] == 45.0  # median of 0,10,...,90
    assert out["S"]["values"]["Value"] is None


def test_I4_partial_nulls_in_pillar_use_median_of_non_null():
    """Within a sector, individual nulls are dropped before the median
    (matches pillar_df.dropna() semantics)."""
    df = pd.DataFrame(
        {
            "quality": [10.0, 20.0, 30.0, float("nan"), float("nan"), 60.0,
                        70.0, 80.0, 90.0, 100.0],
        },
        index=[f"T{i}" for i in range(10)],
    )
    by_sector = {"S": [f"T{i}" for i in range(10)]}
    out = build_sector_pillar_baselines(df, by_sector, min_peers=8)
    # Non-null values: 10, 20, 30, 60, 70, 80, 90, 100 → median = 65.0
    assert out["S"]["values"]["Quality"] == 65.0


def test_I5_label_includes_peer_count_after_index_intersection():
    """A ticker listed in by_sector but absent from pillar_df is dropped
    before counting. The label's n= reflects the post-intersection
    count, not the raw by_sector length."""
    df = _make_pillar_df(
        {f"T{i}": {"quality": 50.0} for i in range(10)}
    )
    by_sector = {
        # 15 tickers in by_sector, but only 10 are in pillar_df
        "S": [f"T{i}" for i in range(15)],
    }
    out = build_sector_pillar_baselines(df, by_sector, min_peers=8)
    assert "S" in out
    assert "(n=10)" in out["S"]["label"]


def test_I6_baseline_values_keyed_by_display_label_not_snake_case():
    """The frontend component indexes by the capitalized display label;
    the compute layer must produce keys matching PillarRadarChart's
    ACTIVE_PILLARS labels, not the snake_case PillarScores fields."""
    df = _make_pillar_df(
        {f"T{i}": {col: 50.0 for col in PILLAR_LABEL_MAP} for i in range(10)}
    )
    out = build_sector_pillar_baselines(
        df, {"S": [f"T{i}" for i in range(10)]}, min_peers=10
    )
    for snake, label in PILLAR_LABEL_MAP.items():
        assert label in out["S"]["values"], (
            f"missing display label {label!r} for snake_case {snake!r}"
        )
    # And the snake_case versions are NOT present.
    for snake in PILLAR_LABEL_MAP:
        assert snake not in out["S"]["values"], (
            f"snake_case key {snake!r} leaked into baseline.values"
        )


def test_I7_rounded_to_two_decimals():
    """Match the rounding convention used by ``_pillar_scores_to_schema``
    so the baseline notch lines up with the per-stock bar exactly."""
    df = pd.DataFrame(
        {"quality": [33.333, 66.667, 50.0]},
        index=["A", "B", "C"],
    )
    out = build_sector_pillar_baselines(
        df, {"S": ["A", "B", "C"]}, min_peers=3
    )
    assert out["S"]["values"]["Quality"] == 50.0  # median


def test_I8_empty_inputs_return_empty():
    """Degenerate cases: empty pillar_df or empty by_sector yield {}."""
    assert build_sector_pillar_baselines(
        pd.DataFrame(), {}, min_peers=10
    ) == {}
    assert build_sector_pillar_baselines(
        _make_pillar_df({"T0": {"quality": 50.0}}), {}, min_peers=1
    ) == {}
