"""Tests for ``compute.scoring.multi_class_shares``.

The CIK-collision detector is a universe-level function (Issue #261)
that returns the set of tickers firing the
``multi_class_aggregate_shares_suspected`` annotate. Trigger:

1. Ticker's CIK appears on ≥ 2 tickers in the universe.
2. Ticker's market_cap > ``MARKET_CAP_FLOOR_RATIO × universe-median``.

Both conditions must hold. Tests pin the trigger semantics + edge
cases (None data / single-ticker universe / threshold boundary).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from compute.scoring.multi_class_shares import (
    MARKET_CAP_FLOOR_RATIO,
    detect_multi_class_aggregate_shares_suspected,
)


def test_market_cap_floor_ratio_pin():
    """Issue #261 — pin the 10% × universe median floor. Methodology-
    scientist Mode B 2026-05-26 verdict: 10% catches all six known
    S&P 500 multi-class tickers while excluding micro-class artifacts.
    Recalibration target for Q3 2026-08-19 quarterly audit."""
    assert MARKET_CAP_FLOOR_RATIO == 0.10


def test_empty_universe_returns_empty_set():
    assert detect_multi_class_aggregate_shares_suspected({}, {}) == set()


def test_no_cik_collision_returns_empty_set():
    """Single-CIK-per-ticker universe never fires regardless of
    market_cap (no multi-class signature present)."""
    cik_by_ticker = {"AAPL": "0000320193", "MSFT": "0000789019"}
    mc_by_ticker = {"AAPL": 3_000_000_000_000.0, "MSFT": 3_200_000_000_000.0}
    assert (
        detect_multi_class_aggregate_shares_suspected(
            cik_by_ticker, mc_by_ticker
        )
        == set()
    )


def test_goog_googl_collision_above_floor_fires_both():
    """Canonical Issue #261 case: GOOG + GOOGL share Alphabet's CIK
    `0001652044`; both market caps are well above 10% × median."""
    cik_by_ticker = {
        "GOOG": "0001652044",
        "GOOGL": "0001652044",
        "AAPL": "0000320193",
    }
    # Synthetic universe with median market_cap = $500B; floor = $50B.
    # GOOG/GOOGL at $4.6T each (overcount artifact) trivially exceeds.
    mc_by_ticker = {
        "GOOG": 4_600_000_000_000.0,
        "GOOGL": 4_640_000_000_000.0,
        "AAPL": 500_000_000_000.0,
    }
    flagged = detect_multi_class_aggregate_shares_suspected(
        cik_by_ticker, mc_by_ticker
    )
    assert flagged == {"GOOG", "GOOGL"}


def test_collision_below_floor_does_not_fire():
    """Two tickers share a CIK but both have market_cap < 10% ×
    median — micro-class artifact, do NOT fire."""
    cik_by_ticker = {
        "TINY_A": "0000111111",
        "TINY_B": "0000111111",
        "BIG1": "0000222222",
        "BIG2": "0000333333",
    }
    # Median market_cap = $500B; floor = $50B. TINY_A/B at $1B are well
    # below the floor (micro-class artifact).
    mc_by_ticker = {
        "TINY_A": 1_000_000_000.0,
        "TINY_B": 1_000_000_000.0,
        "BIG1": 500_000_000_000.0,
        "BIG2": 600_000_000_000.0,
    }
    assert (
        detect_multi_class_aggregate_shares_suspected(
            cik_by_ticker, mc_by_ticker
        )
        == set()
    )


def test_partial_above_floor_only_fires_above():
    """One collision-pair member above floor, one below — only the
    above-floor ticker fires (the below-floor sibling is not user-
    visible at S&P 500 scale)."""
    cik_by_ticker = {
        "PARENT_A": "0000999999",
        "PARENT_C": "0000999999",
        "PEER1": "0000111111",
        "PEER2": "0000222222",
    }
    # Median market_cap = ~$200B; floor = $20B. Parent A above; C below.
    mc_by_ticker = {
        "PARENT_A": 500_000_000_000.0,
        "PARENT_C": 5_000_000_000.0,
        "PEER1": 200_000_000_000.0,
        "PEER2": 250_000_000_000.0,
    }
    flagged = detect_multi_class_aggregate_shares_suspected(
        cik_by_ticker, mc_by_ticker
    )
    assert flagged == {"PARENT_A"}


def test_none_cik_excluded_from_collision_detection():
    """Snapshot failures (CIK = None) cannot collide on missing data —
    excluded from the cik_to_tickers map."""
    cik_by_ticker = {"FOO": None, "BAR": None, "BAZ": "0000111111"}
    mc_by_ticker = {
        "FOO": 100_000_000_000.0,
        "BAR": 100_000_000_000.0,
        "BAZ": 100_000_000_000.0,
    }
    assert (
        detect_multi_class_aggregate_shares_suspected(
            cik_by_ticker, mc_by_ticker
        )
        == set()
    )


def test_none_market_cap_does_not_fire():
    """A ticker with None market_cap (missing shares / price) cannot
    exceed any floor — excluded from the firing set even when its
    CIK collides."""
    cik_by_ticker = {
        "TICKER_A": "0001234567",
        "TICKER_B": "0001234567",
        "PEER": "0007654321",
    }
    mc_by_ticker = {
        "TICKER_A": None,
        "TICKER_B": 1_000_000_000_000.0,
        "PEER": 500_000_000_000.0,
    }
    flagged = detect_multi_class_aggregate_shares_suspected(
        cik_by_ticker, mc_by_ticker
    )
    # TICKER_B fires (above floor + colliding CIK); TICKER_A excluded
    # because its market_cap is None — cannot evaluate the floor test.
    assert flagged == {"TICKER_B"}


def test_all_market_caps_none_returns_empty_set():
    """Universe with no observable market caps cannot compute a
    median → returns empty set without dividing by zero."""
    cik_by_ticker = {"A": "0001", "B": "0001", "C": "0002"}
    mc_by_ticker = {"A": None, "B": None, "C": None}
    assert (
        detect_multi_class_aggregate_shares_suspected(
            cik_by_ticker, mc_by_ticker
        )
        == set()
    )


def test_three_way_collision_all_above_floor_fires_all():
    """Three tickers sharing one CIK (e.g., hypothetical NWS-style
    three-class structure) all fire when each clears the floor."""
    cik_by_ticker = {
        "A": "0000999999",
        "B": "0000999999",
        "C": "0000999999",
        "PEER": "0000111111",
    }
    mc_by_ticker = {
        "A": 200_000_000_000.0,
        "B": 200_000_000_000.0,
        "C": 200_000_000_000.0,
        "PEER": 100_000_000_000.0,
    }
    flagged = detect_multi_class_aggregate_shares_suspected(
        cik_by_ticker, mc_by_ticker
    )
    assert flagged == {"A", "B", "C"}


def test_threshold_boundary_strict_inequality():
    """Floor uses strict `>` — a ticker at exactly the floor does NOT
    fire. Documents the boundary semantic so a future refactor doesn't
    silently change inclusion/exclusion at the edge.

    Universe construction: 5 peers at $50B → median = $50B → floor =
    $5B. EDGE_A pinned exactly to $5B (at the floor); EDGE_B at $6B
    (above). Both share CIK; only EDGE_B fires.
    """
    cik_by_ticker = {
        "EDGE_A": "0001000000",
        "EDGE_B": "0001000000",
        "P1": "0002000000",
        "P2": "0003000000",
        "P3": "0004000000",
        "P4": "0005000000",
        "P5": "0006000000",
    }
    # All 7 market_caps: [5B, 6B, 50B, 50B, 50B, 50B, 50B] → median = 50B
    # → floor = 5B (strict `>` excludes EDGE_A at exactly 5B).
    mc_by_ticker = {
        "EDGE_A": 5_000_000_000.0,
        "EDGE_B": 6_000_000_000.0,
        "P1": 50_000_000_000.0,
        "P2": 50_000_000_000.0,
        "P3": 50_000_000_000.0,
        "P4": 50_000_000_000.0,
        "P5": 50_000_000_000.0,
    }
    flagged = detect_multi_class_aggregate_shares_suspected(
        cik_by_ticker, mc_by_ticker
    )
    # EDGE_A at the floor itself is excluded by strict `>`; EDGE_B fires.
    assert flagged == {"EDGE_B"}


@given(
    n_collisions=st.integers(min_value=0, max_value=5),
    median_mc=st.floats(
        min_value=1e9, max_value=1e12, allow_nan=False, allow_infinity=False
    ),
)
def test_firing_set_subset_of_collision_set_property(
    n_collisions: int, median_mc: float
):
    """Property: the flagged set is always a SUBSET of the colliding-
    CIK ticker set. Floor never adds tickers; it only filters them
    OUT. Catches regressions where a refactor accidentally lets a
    non-colliding ticker into the firing set."""
    # Build a universe with n_collisions ticker pairs sharing CIKs
    # plus 10 single-CIK peers, all at ~median market_cap.
    cik_by_ticker: dict[str, str | None] = {}
    mc_by_ticker: dict[str, float | None] = {}
    colliding_tickers: set[str] = set()
    for i in range(n_collisions):
        for cls in ("A", "B"):
            ticker = f"COLL{i}_{cls}"
            cik_by_ticker[ticker] = f"COLLCIK_{i}"
            mc_by_ticker[ticker] = median_mc * 2  # well above floor
            colliding_tickers.add(ticker)
    for i in range(10):
        ticker = f"PEER{i}"
        cik_by_ticker[ticker] = f"PEERCIK_{i}"
        mc_by_ticker[ticker] = median_mc
    flagged = detect_multi_class_aggregate_shares_suspected(
        cik_by_ticker, mc_by_ticker
    )
    assert flagged <= colliding_tickers
