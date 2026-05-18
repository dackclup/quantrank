"""Tests for ``compute/scoring/osap_blend.py`` (Phase 4h commit 3).

Path-b blend math + universe-gap pass-through invariant. The blend
layer is observability-only this phase (Top-5 still ranked by raw
composite_score per SKILL.md Rule 16), so test focus is on the formula
correctness and the None/NaN universe-gap policy that downstream
``compute/main.py`` (commit 5) relies on.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from compute.scoring.osap_blend import (
    OSAP_BLEND_WEIGHT_DEFAULT,
    aggregate_osap_signals,
    apply_osap_blend,
)

# ---------------------------------------------------------------------------
# aggregate_osap_signals
# ---------------------------------------------------------------------------


def test_aggregate_osap_signals_mean_of_ranks_scaled_to_0_100() -> None:
    """Mean of rank values × 100 — basic 3-ticker happy path.

    Each ticker has the same proxy-mode signal map per commit 2 design,
    but the helper is shape-agnostic so the test uses distinct maps to
    isolate the math.
    """
    signal_map: dict[str, dict[str, float] | None] = {
        "AAPL": {"Mom1m": 0.8, "Accruals": 0.4, "BM": 0.6},  # mean=0.6 → 60.0
        "MSFT": {"Mom1m": 1.0, "Accruals": 0.2, "BM": 0.5},  # mean≈0.566 → 56.66
        "NVDA": {"Mom1m": 0.1, "Accruals": 0.1, "BM": 0.1},  # mean=0.1 → 10.0
    }

    result = aggregate_osap_signals(signal_map)

    assert result.name == "osap_signal_aggregate"
    assert set(result.index) == {"AAPL", "MSFT", "NVDA"}
    assert result["AAPL"] == pytest.approx(60.0)
    assert result["MSFT"] == pytest.approx(100.0 * (1.0 + 0.2 + 0.5) / 3)
    assert result["NVDA"] == pytest.approx(10.0)


def test_aggregate_osap_signals_none_ticker_yields_nan() -> None:
    """Universe-gap ticker (None map) → NaN aggregate, NOT zero."""
    signal_map: dict[str, dict[str, float] | None] = {
        "AAPL": {"Mom1m": 0.5},
        "DELISTED": None,
    }

    result = aggregate_osap_signals(signal_map)

    assert result["AAPL"] == pytest.approx(50.0)
    assert math.isnan(result["DELISTED"])


def test_aggregate_osap_signals_empty_inner_dict_yields_nan() -> None:
    """Empty {} signal dict treated identically to None (no signals fired)."""
    signal_map: dict[str, dict[str, float] | None] = {
        "AAPL": {},
    }

    result = aggregate_osap_signals(signal_map)

    assert math.isnan(result["AAPL"])


def test_aggregate_osap_signals_empty_map_returns_empty_series() -> None:
    """Empty input → empty Series, not error."""
    result = aggregate_osap_signals({})

    assert result.empty
    assert result.dtype == float
    assert result.name == "osap_signal_aggregate"


# ---------------------------------------------------------------------------
# apply_osap_blend
# ---------------------------------------------------------------------------


def test_apply_osap_blend_basic_50_50() -> None:
    """50/50 default — blended = mean(composite, osap)."""
    composite = pd.Series({"AAPL": 80.0, "MSFT": 60.0, "NVDA": 40.0})
    osap = pd.Series({"AAPL": 40.0, "MSFT": 70.0, "NVDA": 100.0})

    result = apply_osap_blend(composite, osap)

    assert result.name == "composite_score_osap_adjusted"
    assert result["AAPL"] == pytest.approx(60.0)  # (80 + 40) / 2
    assert result["MSFT"] == pytest.approx(65.0)  # (60 + 70) / 2
    assert result["NVDA"] == pytest.approx(70.0)  # (40 + 100) / 2


def test_apply_osap_blend_weight_zero_returns_composite_unchanged() -> None:
    """weight=0 → pure pass-through (no OSAP influence)."""
    composite = pd.Series({"AAPL": 80.0, "MSFT": 60.0})
    osap = pd.Series({"AAPL": 10.0, "MSFT": 90.0})

    result = apply_osap_blend(composite, osap, weight=0.0)

    pd.testing.assert_series_equal(
        result.astype(float),
        composite.astype(float),
        check_names=False,
    )


def test_apply_osap_blend_weight_one_returns_osap_where_covered() -> None:
    """weight=1 → pure OSAP for covered tickers; pass-through for NaN."""
    composite = pd.Series({"AAPL": 80.0, "GAP": 60.0})
    osap = pd.Series({"AAPL": 25.0, "GAP": float("nan")})

    result = apply_osap_blend(composite, osap, weight=1.0)

    assert result["AAPL"] == pytest.approx(25.0)
    # NaN OSAP → composite passes through even at weight=1
    assert result["GAP"] == pytest.approx(60.0)


def test_apply_osap_blend_nan_osap_falls_back_to_composite() -> None:
    """Universe-gap policy: NaN OSAP → composite unchanged."""
    composite = pd.Series({"AAPL": 80.0, "GAP": 50.0, "MSFT": 60.0})
    osap = pd.Series({"AAPL": 20.0, "GAP": float("nan"), "MSFT": 100.0})

    result = apply_osap_blend(composite, osap, weight=0.5)

    assert result["AAPL"] == pytest.approx(50.0)  # (80 + 20) / 2
    assert result["GAP"] == pytest.approx(50.0)  # NaN → pass-through
    assert result["MSFT"] == pytest.approx(80.0)  # (60 + 100) / 2


def test_apply_osap_blend_empty_composite_returns_empty_series() -> None:
    """Empty composite → empty output, no error."""
    result = apply_osap_blend(
        pd.Series(dtype=float),
        pd.Series({"AAPL": 50.0}),
    )

    assert result.empty
    assert result.name == "composite_score_osap_adjusted"


def test_apply_osap_blend_clips_to_0_100() -> None:
    """Output is clipped to [0, 100] to match composite-score domain."""
    # Edge: composite=100, osap=100 → 100 (no clip needed).
    # Edge: composite=0, osap=0 → 0 (no clip needed).
    # Construct a degenerate case where naive math could exceed bounds
    # if caller passes out-of-domain inputs.
    composite = pd.Series({"HIGH": 100.0, "LOW": 0.0, "OOB": 150.0})
    osap = pd.Series({"HIGH": 100.0, "LOW": 0.0, "OOB": 200.0})

    result = apply_osap_blend(composite, osap, weight=0.5)

    assert result["HIGH"] == pytest.approx(100.0)
    assert result["LOW"] == pytest.approx(0.0)
    # 0.5 * 150 + 0.5 * 200 = 175 → clipped to 100
    assert result["OOB"] == pytest.approx(100.0)


def test_apply_osap_blend_invalid_weight_below_zero_raises() -> None:
    composite = pd.Series({"AAPL": 50.0})
    osap = pd.Series({"AAPL": 50.0})

    with pytest.raises(ValueError, match=r"weight must be in \[0, 1\]"):
        apply_osap_blend(composite, osap, weight=-0.1)


def test_apply_osap_blend_invalid_weight_above_one_raises() -> None:
    composite = pd.Series({"AAPL": 50.0})
    osap = pd.Series({"AAPL": 50.0})

    with pytest.raises(ValueError, match=r"weight must be in \[0, 1\]"):
        apply_osap_blend(composite, osap, weight=1.5)


def test_apply_osap_blend_extra_osap_tickers_dropped_via_reindex() -> None:
    """Tickers in OSAP but not composite are silently dropped — output
    index matches composite_scores.index exactly."""
    composite = pd.Series({"AAPL": 60.0, "MSFT": 70.0})
    osap = pd.Series({"AAPL": 80.0, "MSFT": 50.0, "EXTRA": 99.0})

    result = apply_osap_blend(composite, osap, weight=0.5)

    assert list(result.index) == ["AAPL", "MSFT"]
    assert "EXTRA" not in result.index


def test_apply_osap_blend_missing_osap_ticker_becomes_passthrough() -> None:
    """Composite ticker absent from OSAP series → reindex to NaN →
    pass-through (universe-gap path)."""
    composite = pd.Series({"AAPL": 60.0, "ABSENT": 75.0})
    osap = pd.Series({"AAPL": 20.0})  # ABSENT not in OSAP

    result = apply_osap_blend(composite, osap, weight=0.5)

    assert result["AAPL"] == pytest.approx(40.0)  # (60 + 20) / 2
    assert result["ABSENT"] == pytest.approx(75.0)  # pass-through


def test_apply_osap_blend_default_weight_matches_constant() -> None:
    """No explicit weight → uses OSAP_BLEND_WEIGHT_DEFAULT (0.5 lock)."""
    composite = pd.Series({"AAPL": 80.0})
    osap = pd.Series({"AAPL": 40.0})

    result_default = apply_osap_blend(composite, osap)
    result_explicit = apply_osap_blend(
        composite, osap, weight=OSAP_BLEND_WEIGHT_DEFAULT
    )

    pd.testing.assert_series_equal(result_default, result_explicit)
    # Sanity: the locked default is 0.5 per osap-integration/PLAN.md L168-170
    assert OSAP_BLEND_WEIGHT_DEFAULT == 0.5


# ---------------------------------------------------------------------------
# Cross-module integration sanity (commit 2 → commit 3)
# ---------------------------------------------------------------------------


def test_aggregate_then_blend_round_trip_with_compute_osap_signals_shape() -> None:
    """End-to-end shape: ``compute_osap_signals`` output → aggregate →
    apply_osap_blend works without manual conversion."""
    # Simulate compute_osap_signals output directly (avoid importing the
    # full pipeline here — that's commit 5's integration test concern).
    osap_signal_map: dict[str, dict[str, float] | None] = {
        "AAPL": {"Mom1m": 0.9, "Accruals": 0.3, "BM": 0.6},
        "MSFT": {"Mom1m": 0.5, "Accruals": 0.5, "BM": 0.5},
        "GAP": None,  # Universe gap
    }
    composite = pd.Series({"AAPL": 80.0, "MSFT": 60.0, "GAP": 70.0})

    aggregate = aggregate_osap_signals(osap_signal_map)
    blended = apply_osap_blend(composite, aggregate)

    # AAPL: (0.9 + 0.3 + 0.6) / 3 × 100 = 60 → (80 + 60) / 2 = 70
    assert blended["AAPL"] == pytest.approx(70.0)
    # MSFT: mean=0.5 → 50 → (60 + 50) / 2 = 55
    assert blended["MSFT"] == pytest.approx(55.0)
    # GAP: None → NaN → pass-through 70
    assert blended["GAP"] == pytest.approx(70.0)


def test_apply_osap_blend_preserves_dtype_float() -> None:
    """Output dtype is float (matches composite_score in StockSummary)."""
    composite = pd.Series({"AAPL": 80, "MSFT": 60}, dtype=int)  # int input
    osap = pd.Series({"AAPL": 40.0, "MSFT": 70.0})

    result = apply_osap_blend(composite, osap)

    assert result.dtype == np.float64
