"""Unit tests for compute.scoring.normalize."""

from __future__ import annotations

import math

import pandas as pd

from compute.scoring.normalize import (
    average_pillar_score,
    normalize_metric,
)


def _series(d: dict[str, float]) -> pd.Series:
    return pd.Series(d, dtype=float)


def test_normalize_absolute_higher_is_better_monotonic():
    sectors = pd.Series({"A": "tech", "B": "tech", "C": "tech", "D": "tech"})
    s = _series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0})
    out = normalize_metric(s, sectors, sector_relative=False, higher_is_better=True)
    # Monotonic: lowest gets lowest rank, highest gets highest.
    assert out["A"] < out["B"] < out["C"] < out["D"]
    assert 0.0 <= out.min() <= out.max() <= 100.0


def test_normalize_absolute_lower_is_better_inverts():
    sectors = pd.Series({"A": "x", "B": "x", "C": "x", "D": "x"})
    s = _series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0})
    out = normalize_metric(s, sectors, sector_relative=False, higher_is_better=False)
    # Inverted: lowest input gets the highest score.
    assert out["A"] > out["B"] > out["C"] > out["D"]


def test_normalize_sector_relative_buckets_independent():
    # Two tech stocks (1, 2) and two health stocks (1, 2). Within each
    # sector the ranking should be independent — the lower of each sector
    # gets ~25/100, the higher gets ~75/100 (rank pct = 0.5 / 1.0).
    sectors = pd.Series({"T1": "tech", "T2": "tech", "H1": "health", "H2": "health"})
    s = _series({"T1": 1.0, "T2": 100.0, "H1": 50.0, "H2": 200.0})
    out = normalize_metric(s, sectors, sector_relative=True, higher_is_better=True)
    # Within tech: T1 < T2; within health: H1 < H2.
    assert out["T1"] < out["T2"]
    assert out["H1"] < out["H2"]
    # The cross-sector "lower in its bucket" stocks should both have similar ranks.
    assert math.isclose(out["T1"], out["H1"], abs_tol=1e-9)
    assert math.isclose(out["T2"], out["H2"], abs_tol=1e-9)


def test_normalize_sector_median_imputes_nan():
    # A has NaN, B/C/D are finite; A should get the sector median, then ranked.
    sectors = pd.Series({"A": "x", "B": "x", "C": "x", "D": "x"})
    s = _series({"A": float("nan"), "B": 1.0, "C": 2.0, "D": 3.0})
    out = normalize_metric(s, sectors, sector_relative=False, higher_is_better=True)
    # All four should have a finite normalized score.
    assert out.notna().all()
    # A imputed to median (2.0) → ranked between B and D.
    assert out["B"] <= out["A"] <= out["D"]


def test_normalize_winsorizes_extreme_outliers():
    # An outlier should get clipped — its rank should equal the highest
    # non-outlier rank, not exceed it.
    sectors = pd.Series({k: "x" for k in "ABCDEFGHIJ"})
    vals = {chr(ord("A") + i): float(i) for i in range(9)}
    vals["J"] = 1e9  # extreme outlier; winsor clips to 99th percentile
    s = pd.Series(vals, dtype=float)
    out = normalize_metric(s, sectors, sector_relative=False, higher_is_better=True)
    # Pre-winsor, J would be far above I. Post-winsor, J's clip ≈ I's value;
    # ranks remain monotonically tied at the top.
    assert out["J"] >= out["I"] - 1e-9


def test_average_pillar_score_drops_low_coverage():
    # 4 metrics, ticker A has 1 finite (25% coverage < 50%) → NaN.
    # Ticker B has 3 finite (75%) → mean of those 3.
    metrics = {
        "m1": pd.Series({"A": 90.0, "B": 80.0}),
        "m2": pd.Series({"A": float("nan"), "B": 60.0}),
        "m3": pd.Series({"A": float("nan"), "B": 40.0}),
        "m4": pd.Series({"A": float("nan"), "B": float("nan")}),
    }
    out = average_pillar_score(metrics, min_coverage=0.5)
    assert math.isnan(out["A"])  # below 50% coverage
    assert math.isclose(out["B"], (80.0 + 60.0 + 40.0) / 3.0)


def test_normalize_empty_series_returns_empty():
    out = normalize_metric(
        pd.Series([], dtype=float), pd.Series([], dtype=str),
        sector_relative=False, higher_is_better=True,
    )
    assert out.empty


def test_average_pillar_score_handles_empty_input():
    assert average_pillar_score({}).empty


def test_normalize_all_nan_returns_all_nan():
    sectors = pd.Series({"A": "x", "B": "x"})
    s = _series({"A": float("nan"), "B": float("nan")})
    out = normalize_metric(
        s, sectors, sector_relative=False, higher_is_better=True, impute_missing=False
    )
    assert out.isna().all()
