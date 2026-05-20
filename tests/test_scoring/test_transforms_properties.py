"""Property-based tests for scoring transforms — composite + OSAP blend.

Process Hygiene Item #1 (issue #126). Covers two pure-numeric
transforms whose output domains are contract-locked by downstream
schemas:

- ``compute/scoring/composite.py::compute_composite`` — output Series
  must be in [0, 100] per the writer/Pydantic contract; the
  ``PHASE3_WEIGHTS`` sum-to-1 invariant is asserted at module load.
- ``compute/scoring/osap_blend.py::apply_osap_blend`` — output Series
  must also be in [0, 100]; NaN-OSAP entries pass the raw composite
  through.

Test conventions match ``test_osap_replicate_properties.py``: small
generated DataFrames so the default 200 ms deadline isn't tripped,
no ``@settings(deadline=None)``, no Hypothesis stateful machines
(out of scope for Item #1 per issue #126).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from compute.scoring import composite as composite_mod
from compute.scoring import osap_blend as osap_blend_mod

# ---------------------------------------------------------------------------
# Property A — compute_composite output is clipped to [0, 100]
# ---------------------------------------------------------------------------


_PILLAR_COLS: tuple[str, ...] = (
    "quality",
    "value",
    "growth",
    "momentum",
    "health",
    "profitability",
    "technical",
    "risk",
)


@given(
    n_tickers=st.integers(min_value=1, max_value=12),
    pillar_values=st.lists(
        st.floats(
            min_value=0.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=8,
        max_size=8,
    ),
)
def test_compute_composite_output_bounded_0_to_100(
    n_tickers: int, pillar_values: list[float]
) -> None:
    """For any pillar_scores input where each pillar ∈ [0, 100], the
    composite output is in [0, 100]. This is the domain contract the
    writer + Pydantic schema both depend on (composite_score: float,
    Field constraint at write time)."""
    # Replicate the same pillar value across every ticker — this isolates
    # the bounding property from cross-ticker interactions.
    df = pd.DataFrame(
        {col: [pillar_values[i]] * n_tickers for i, col in enumerate(_PILLAR_COLS)},
        index=[f"TKR_{i:02d}" for i in range(n_tickers)],
    )
    composite = composite_mod.compute_composite(df, neutralize_missing=True)
    assert (composite >= 0.0).all()
    assert (composite <= 100.0).all()
    assert len(composite) == n_tickers


# ---------------------------------------------------------------------------
# Property B — all-neutral input collapses to composite == 50.0
# ---------------------------------------------------------------------------


@given(n_tickers=st.integers(min_value=1, max_value=15))
def test_compute_composite_all_50_inputs_yield_composite_50(n_tickers: int) -> None:
    """For any universe size, if every pillar score == 50.0 (the
    neutral imputation value per SKILL.md Rule 7), the weighted
    composite == 50.0. Catches accidental weight-vector drift —
    weights sum to 1.0, so 50.0 × sum(weights) == 50.0."""
    df = pd.DataFrame(
        {col: [50.0] * n_tickers for col in _PILLAR_COLS},
        index=[f"TKR_{i:02d}" for i in range(n_tickers)],
    )
    composite = composite_mod.compute_composite(df, neutralize_missing=False)
    for ticker in composite.index:
        assert composite[ticker] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Property C — NaN inputs are imputed to 50.0 when neutralize_missing=True
# ---------------------------------------------------------------------------


@given(
    n_tickers=st.integers(min_value=1, max_value=10),
    nan_mask=st.lists(st.booleans(), min_size=8, max_size=8),
)
def test_compute_composite_neutralize_missing_imputes_nan_to_50(
    n_tickers: int, nan_mask: list[bool]
) -> None:
    """With neutralize_missing=True, any NaN pillar is replaced by
    50.0 before weighting. So if ALL pillars are NaN, the result must
    be 50.0; if SOME pillars are NaN, the result still satisfies
    bound checks. Catches a regression where the NaN-imputation path
    silently produces NaN composite or out-of-bound values."""
    # Build a frame where each pillar column is either fully NaN or
    # fully 50.0 based on the mask.
    cols: dict[str, list[float]] = {}
    for i, col in enumerate(_PILLAR_COLS):
        if nan_mask[i]:
            cols[col] = [float("nan")] * n_tickers
        else:
            cols[col] = [50.0] * n_tickers

    df = pd.DataFrame(
        cols, index=[f"TKR_{i:02d}" for i in range(n_tickers)]
    )
    composite = composite_mod.compute_composite(df, neutralize_missing=True)

    # All-NaN → all imputed to 50.0 → composite == 50.0.
    # Otherwise, composite ∈ [0, 100] and is non-NaN.
    for ticker in composite.index:
        val = composite[ticker]
        assert not math.isnan(val), (
            f"composite for {ticker} is NaN despite neutralize_missing=True"
        )
        assert 0.0 <= val <= 100.0
        if all(nan_mask):
            assert val == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Property D — apply_osap_blend output bounded + NaN-OSAP passthrough
# ---------------------------------------------------------------------------


@given(
    composite_vals=st.lists(
        st.floats(
            min_value=0.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=10,
    ),
    osap_vals=st.lists(
        st.one_of(
            st.floats(
                min_value=0.0,
                max_value=100.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            st.just(float("nan")),
        ),
        min_size=1,
        max_size=10,
    ),
    weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_apply_osap_blend_output_bounded_and_nan_passthrough(
    composite_vals: list[float],
    osap_vals: list[float],
    weight: float,
) -> None:
    """For any (composite, osap, weight) triple with composite ∈ [0, 100],
    osap ∈ [0, 100] ∪ {NaN}, weight ∈ [0, 1]:

    1. Blend output is in [0, 100] (post-clip contract)
    2. For tickers where OSAP is NaN, blended[ticker] == composite[ticker]
       (the universe-gap pass-through contract)
    3. For tickers where OSAP is finite, blended[ticker] is between
       composite[ticker] and osap[ticker] (interior-point property)
    """
    n = min(len(composite_vals), len(osap_vals))
    tickers = [f"TKR_{i:02d}" for i in range(n)]
    composite = pd.Series(composite_vals[:n], index=tickers, dtype=float)
    osap = pd.Series(osap_vals[:n], index=tickers, dtype=float)

    blended = osap_blend_mod.apply_osap_blend(composite, osap, weight=weight)

    # Bound check (post-clip).
    assert (blended >= 0.0).all()
    assert (blended <= 100.0).all()
    assert list(blended.index) == tickers

    for t in tickers:
        if math.isnan(osap[t]):
            # Universe-gap pass-through.
            assert blended[t] == pytest.approx(composite[t])
        else:
            # Interior-point: with weight ∈ [0, 1], the blend is the
            # convex combination of composite[t] and osap[t]. Both inputs
            # are in [0, 100], so the convex combination is too; therefore
            # the clip is a no-op AND the value lies between the two
            # endpoints (inclusive).
            lo = min(composite[t], osap[t])
            hi = max(composite[t], osap[t])
            assert lo - 1e-9 <= blended[t] <= hi + 1e-9, (
                f"blend[{t}] = {blended[t]} outside interior "
                f"[{lo}, {hi}] (composite={composite[t]}, osap={osap[t]}, "
                f"weight={weight})"
            )


# ---------------------------------------------------------------------------
# Property E — module-load weight-sum invariant (PHASE3_WEIGHTS sum=1.0)
# ---------------------------------------------------------------------------


@given(
    n_tickers=st.integers(min_value=1, max_value=8),
    pillar_value=st.floats(
        min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
    ),
)
def test_compute_composite_constant_input_equals_input(
    n_tickers: int, pillar_value: float
) -> None:
    """Constant-pillar input → composite == that constant.
    This is the weight-sum-equals-1.0 invariant expressed as a
    property: weighted_sum(constant) == constant × sum(weights) ==
    constant × 1.0 == constant. Drift in any PHASE3_WEIGHTS value
    surfaces here as a constant-input mismatch."""
    # Restrict to active Phase-3 pillars (the redistributed
    # PHASE3_EFFECTIVE_WEIGHTS sums to 1.0 over those 8 columns).
    df = pd.DataFrame(
        {col: [pillar_value] * n_tickers for col in _PILLAR_COLS},
        index=[f"TKR_{i:02d}" for i in range(n_tickers)],
    )
    composite = composite_mod.compute_composite(df, neutralize_missing=False)
    for ticker in composite.index:
        assert composite[ticker] == pytest.approx(pillar_value)


# ---------------------------------------------------------------------------
# Property F — aggregate_osap_signals output in [0, 100] (or NaN for gaps)
# ---------------------------------------------------------------------------


@given(
    n_tickers=st.integers(min_value=1, max_value=10),
    n_signals=st.integers(min_value=0, max_value=8),
    nan_universe_fraction=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False
    ),
)
def test_aggregate_osap_signals_finite_values_in_0_to_100(
    n_tickers: int, n_signals: int, nan_universe_fraction: float
) -> None:
    """For any signal_map drawn from random universe + signal-count
    shape, the aggregate output value for any ticker is either NaN
    (universe gap) OR in [0, 100]. Catches accidental [0, 1] /
    [0, 100] confusion (the rank → percent multiplication at
    osap_blend.py:82)."""
    rng = np.random.RandomState(42)
    signal_names = [f"SIG_{i}" for i in range(n_signals)]
    signal_map: dict[str, dict[str, float] | None] = {}
    for t_i in range(n_tickers):
        ticker = f"TKR_{t_i:02d}"
        # Some tickers get None (universe gap), others get a rank dict.
        if rng.random() < nan_universe_fraction or not signal_names:
            signal_map[ticker] = None
        else:
            signal_map[ticker] = {
                s: float(rng.random()) for s in signal_names  # rank ∈ [0, 1)
            }

    aggregate = osap_blend_mod.aggregate_osap_signals(signal_map)
    for t in aggregate.index:
        val = aggregate[t]
        if math.isnan(val):
            # NaN is allowed (universe gap).
            continue
        assert 0.0 <= val <= 100.0, (
            f"aggregate[{t}] = {val} outside [0, 100]"
        )


# ---------------------------------------------------------------------------
# Property G — apply_osap_blend with weight=0 is identity-on-composite
# ---------------------------------------------------------------------------


@given(
    composite_vals=st.lists(
        st.floats(
            min_value=0.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=10,
    ),
    osap_vals=st.lists(
        st.floats(
            min_value=0.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=10,
    ),
)
def test_apply_osap_blend_weight_zero_is_identity_on_composite(
    composite_vals: list[float], osap_vals: list[float]
) -> None:
    """``weight=0.0`` MUST produce ``composite_scores`` unchanged.
    Catches a regression where the blend layer accidentally injects
    OSAP signal even when configured to be ``observability-only``
    (Phase 4h commit-3 design property — Top-5 still ranks raw
    composite per Rule 16)."""
    # Filter out NaN — we want both populated here so we test the
    # interior-blend path, not the NaN-passthrough path.
    assume(len(composite_vals) == len(osap_vals))
    n = len(composite_vals)
    tickers = [f"TKR_{i:02d}" for i in range(n)]
    composite = pd.Series(composite_vals, index=tickers, dtype=float)
    osap = pd.Series(osap_vals, index=tickers, dtype=float)

    blended = osap_blend_mod.apply_osap_blend(composite, osap, weight=0.0)
    for t in tickers:
        assert blended[t] == pytest.approx(composite[t])
