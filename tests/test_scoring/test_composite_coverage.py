"""Coverage tests for compute.scoring.composite — targeting uncovered branches.

Uncovered lines (baseline 88%):
  49    PHASE3_WEIGHTS sum guard (import-time check) — not directly exercisable
        but we lock the constant via a value test
  77    compute_composite: empty pillar_scores → empty Series
  86    compute_composite: no requested pillars in df → ValueError
  89->92 compute_composite: neutralize_missing=False path
  108->106  neutralize_pillar_scores: no NaN present → no imputation
  181   build_sector_pillar_baselines: col not in sub.columns → None in values
        (already covered in composite test; re-lock via explicit case)
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from compute.scoring.composite import (
    ACTIVE_PILLARS_PHASE3,
    PHASE3_WEIGHTS,
    build_sector_pillar_baselines,
    compute_composite,
    neutralize_pillar_scores,
)

# ---------------------------------------------------------------------------
# compute_composite: empty DataFrame → empty Series (line 77)
# ---------------------------------------------------------------------------


def test_compute_composite_empty_dataframe_returns_empty_series():
    out = compute_composite(pd.DataFrame())
    assert isinstance(out, pd.Series)
    assert len(out) == 0


# ---------------------------------------------------------------------------
# compute_composite: no requested pillars in df → ValueError (line 86)
# ---------------------------------------------------------------------------


def test_compute_composite_raises_when_no_matching_columns():
    df = pd.DataFrame({"some_unknown_pillar": [50.0]}, index=["A"])
    with pytest.raises(ValueError, match="none of the requested pillar columns"):
        compute_composite(df, weights={"quality": 0.5, "value": 0.5})


# ---------------------------------------------------------------------------
# compute_composite: neutralize_missing=False path (lines 89-92 branch)
# ---------------------------------------------------------------------------


def test_compute_composite_without_neutralize_missing_keeps_nan():
    """With neutralize_missing=False, NaN pillar values propagate to the composite."""
    df = pd.DataFrame(
        {p: [50.0] for p in ACTIVE_PILLARS_PHASE3},
        index=["A"],
    )
    # Set one pillar to NaN; without neutralize, the weighted sum sees a NaN.
    df.at["A", "quality"] = float("nan")
    out = compute_composite(df, neutralize_missing=False)
    # NaN propagates through the weighted sum.
    assert math.isnan(out["A"])


def test_compute_composite_subset_of_weights_renorms():
    """When weights only cover a subset of columns present in df, the
    safety renorm (line 93) ensures the weighted sum still sums to 1."""
    df = pd.DataFrame(
        {"quality": [100.0], "value": [0.0], "extra_col": [999.0]},
        index=["A"],
    )
    # weights only cover 2 columns (renorm: quality=0.6, value=0.4)
    weights = {"quality": 0.6, "value": 0.4}
    out = compute_composite(df, weights=weights)
    # 100*0.6 + 0*0.4 = 60
    assert math.isclose(out["A"], 60.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# neutralize_pillar_scores: no NaN → no imputation (line 108 branch)
# ---------------------------------------------------------------------------


def test_neutralize_pillar_scores_no_nan_no_imputation():
    """When all values are finite, imputed dict is empty and values unchanged."""
    df = pd.DataFrame(
        {"quality": [80.0, 90.0], "value": [60.0, 70.0]},
        index=["A", "B"],
    )
    out, imputed = neutralize_pillar_scores(df)
    assert imputed == {}
    assert out.at["A", "quality"] == 80.0
    assert out.at["B", "value"] == 70.0


# ---------------------------------------------------------------------------
# neutralize_pillar_scores: custom neutral value
# ---------------------------------------------------------------------------


def test_neutralize_pillar_scores_custom_neutral():
    """Custom neutral=0 replaces NaN with 0 instead of 50."""
    df = pd.DataFrame({"quality": [float("nan")]}, index=["A"])
    out, imputed = neutralize_pillar_scores(df, neutral=0.0)
    assert out.at["A", "quality"] == 0.0
    assert imputed["A"] == ["quality"]


# ---------------------------------------------------------------------------
# build_sector_pillar_baselines: missing column → None (line 181)
# ---------------------------------------------------------------------------


def test_build_sector_pillar_baselines_pillar_column_absent_yields_none():
    """When a pillar from PILLAR_LABEL_MAP is not a column in sub,
    the baseline value for that pillar label is None."""
    # Only 'quality' column present; all other pillars from PILLAR_LABEL_MAP absent.
    df = pd.DataFrame(
        {f"T{i}": {"quality": float(i * 10)} for i in range(10)},
        dtype=float,
    ).T
    by_sector = {"S": [f"T{i}" for i in range(10)]}
    out = build_sector_pillar_baselines(df, by_sector, min_peers=10)
    # 'Quality' should have a value; all other labels should be None.
    assert out["S"]["values"]["Quality"] is not None
    assert out["S"]["values"]["Value"] is None
    assert out["S"]["values"]["Growth"] is None


# ---------------------------------------------------------------------------
# Edge cases for PHASE3_WEIGHTS constant integrity
# ---------------------------------------------------------------------------


def test_phase3_weights_active_inactive_partition_covers_all():
    """All pillar names in PHASE3_WEIGHTS are covered by ACTIVE + INACTIVE."""
    from compute.scoring.composite import INACTIVE_PILLARS_PHASE3

    all_pillars = set(ACTIVE_PILLARS_PHASE3) | set(INACTIVE_PILLARS_PHASE3)
    assert all_pillars == set(PHASE3_WEIGHTS.keys())
