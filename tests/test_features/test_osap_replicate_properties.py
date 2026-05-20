"""Property-based tests for ``compute/features/osap_replicate.py``.

Process Hygiene Item #1 (issue #126). Hypothesis generates random
inputs covering data-shape regions that example-based tests miss — the
class of bug that hid the quintile / tercile silent-drop in
``OSAP_SIGNALS_100`` from PR #112's CI until production cron
diagnostics caught it 2026-05-19 (fixed in PR #124, Phase 4h.2 Part 2).

Pattern conventions in this file:

- All ``@given`` strategies bound their integer ranges (small DataFrames)
  so the per-example wall-clock stays under the default 200 ms deadline.
  We deliberately do NOT use ``@settings(deadline=None)`` — a sudden
  multi-second example signals an algorithmic slow path that's worth
  surfacing.
- Inputs are constructed as pure ``pd.DataFrame`` literals (no fixture
  files) so the test stays self-contained and the failing-example
  shrinking output is human-readable.
- All tests run offline (``pytest -m "not network"``).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from compute.features import osap_replicate

# ---------------------------------------------------------------------------
# Helper — build a synthetic OSAP returns DataFrame with the full schema
# ---------------------------------------------------------------------------


def _make_returns_df(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    """Construct a returns DataFrame with the schema the ingest contract
    promises (``signalname, port, date, ret`` + trailing
    ``signallag, Nlong, Nshort``)."""
    df = pd.DataFrame(rows, columns=["signalname", "port", "date", "ret"])
    df["signallag"] = 0.0
    df["Nlong"] = 50
    df["Nshort"] = 50
    return df


# ---------------------------------------------------------------------------
# Property 1 — compute_long_short_returns shape invariance over port count
# ---------------------------------------------------------------------------


@given(
    port_count=st.integers(min_value=2, max_value=10),
    n_dates=st.integers(min_value=1, max_value=12),
)
def test_compute_long_short_returns_handles_any_port_cardinality(
    port_count: int, n_dates: int
) -> None:
    """For any port cardinality ∈ [2, 10] (binary → decile) and any
    n_dates ∈ [1, 12], the multi-port adapter produces exactly one
    long-short row per date with ``ls_return = ret[port=min] -
    ret[port=max]``.

    This is the property test that would have caught the quintile /
    tercile silent-drop bug fixed in Phase 4h.2 Part 2 — the old
    hardcoded ``port=10`` filter would fail this for any
    ``port_count ∈ {2, 3, 4, 5, 6, 7, 8, 9}``.
    """
    rows = []
    for date_i in range(n_dates):
        for port_i in range(1, port_count + 1):
            # Deterministic per-port return: port_count for port=01
            # decreasing to 1 for port=port_count. Long-short =
            # ret[1] - ret[port_count] = port_count - 1.
            rows.append(
                (
                    "PropSig",
                    str(port_i).zfill(2),
                    f"2024-{date_i + 1:02d}-28",
                    float(port_count - port_i + 1),
                )
            )
    df = _make_returns_df(rows)
    ls = osap_replicate.compute_long_short_returns(df)

    assert set(ls.columns) == {"signalname", "date", "ls_return"}
    assert len(ls) == n_dates
    # ret[port=01] = port_count, ret[port=port_count] = 1 →
    # ls_return = port_count - 1.
    expected = float(port_count - 1)
    for actual in ls["ls_return"]:
        assert actual == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Property 2 — signals_dropped_no_long_short returns sorted unique list
# ---------------------------------------------------------------------------


@given(
    one_port_signals=st.lists(
        st.text(
            alphabet=st.characters(min_codepoint=ord("A"), max_codepoint=ord("Z")),
            min_size=2,
            max_size=8,
        ),
        min_size=0,
        max_size=10,
        unique=True,
    ),
    two_port_signals=st.lists(
        st.text(
            alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
            min_size=2,
            max_size=8,
        ),
        min_size=0,
        max_size=10,
        unique=True,
    ),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_signals_dropped_no_long_short_returns_sorted_unique(
    one_port_signals: list[str], two_port_signals: list[str]
) -> None:
    """For any mixture of single-port and two-port signals, the helper
    returns the single-port set as a sorted (alphabetical) list of
    unique strings. Catches accidental drift from sorted + de-duped
    output (the contract the Metadata field consumer depends on)."""
    rows: list[tuple[str, str, str, float]] = []
    for sig in one_port_signals:
        # Duplicate the row at two different dates — same port → still
        # single-port from nunique()'s perspective.
        rows.append((sig, "01", "2024-01-31", 1.0))
        rows.append((sig, "01", "2024-02-29", 2.0))
    for sig in two_port_signals:
        rows.append((sig, "01", "2024-01-31", 3.0))
        rows.append((sig, "10", "2024-01-31", 1.0))
    if not rows:
        df = pd.DataFrame(columns=["signalname", "port", "date", "ret"])
    else:
        df = _make_returns_df(rows)

    dropped = osap_replicate.signals_dropped_no_long_short(df)

    # Sortedness — strict ascending order.
    assert dropped == sorted(dropped), (
        f"signals_dropped_no_long_short must return a sorted list; got {dropped}"
    )
    # Uniqueness — no duplicates.
    assert len(dropped) == len(set(dropped))
    # Membership invariant — single-port signals are the ones that
    # should appear; two-port signals must NOT appear; signals NOT in
    # the input must NOT appear.
    expected_dropped = set(one_port_signals) - set(two_port_signals)
    assert set(dropped) == expected_dropped


# ---------------------------------------------------------------------------
# Property 3 — _normalize_port_label round-trips int / str / categorical
# ---------------------------------------------------------------------------


@given(
    port_ints=st.lists(
        st.integers(min_value=1, max_value=10), min_size=1, max_size=10
    )
)
def test_normalize_port_label_int_input_yields_2char_zfill(
    port_ints: list[int],
) -> None:
    """For any list of integer port labels ∈ [1, 10], the normalizer
    produces 2-char zero-padded strings ('1' → '01', '10' stays '10')."""
    series = pd.Series(port_ints)
    result = osap_replicate._normalize_port_label(series)
    assert all(len(s) == 2 for s in result)
    assert all(s.isdigit() for s in result)
    # Idempotence — applying it again should be a no-op.
    again = osap_replicate._normalize_port_label(result)
    assert list(again) == list(result)


@given(
    port_strs=st.lists(
        st.sampled_from(["1", "01", "2", "02", "10"]),
        min_size=1,
        max_size=10,
    )
)
def test_normalize_port_label_str_input_yields_2char_zfill(
    port_strs: list[str],
) -> None:
    """Mixed-width string ports ('1' / '01' / '10') normalize to a
    uniform 2-char width — the property the pivot column-name lookup
    depends on."""
    series = pd.Series(port_strs)
    result = osap_replicate._normalize_port_label(series)
    assert all(len(s) == 2 for s in result)
    # Specifically: '1' → '01', '10' stays '10'.
    by_pos = list(zip(port_strs, result, strict=True))
    for src, normalized in by_pos:
        if src in ("1", "01"):
            assert normalized == "01"
        elif src in ("2", "02"):
            assert normalized == "02"
        elif src == "10":
            assert normalized == "10"


# ---------------------------------------------------------------------------
# Property 4 — Part 2 accounting invariant under random manifest partitions
# ---------------------------------------------------------------------------


@st.composite
def _three_disjoint_sets(
    draw: st.DrawFn,
) -> tuple[list[str], list[str], list[str]]:
    """Draw three disjoint sets of unique uppercase signal names.

    Returns ``(missing, dropped, gated)`` — each a sorted list, the
    three together partition the same underlying pool.
    """
    pool = draw(
        st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=ord("A"), max_codepoint=ord("Z")),
                min_size=2,
                max_size=6,
            ),
            min_size=0,
            max_size=15,
            unique=True,
        )
    )
    if not pool:
        return [], [], []
    # Partition the pool into three buckets via per-element label.
    labels = draw(
        st.lists(
            st.sampled_from(["missing", "dropped", "gated"]),
            min_size=len(pool),
            max_size=len(pool),
        )
    )
    missing = sorted(s for s, lbl in zip(pool, labels, strict=True) if lbl == "missing")
    dropped = sorted(s for s, lbl in zip(pool, labels, strict=True) if lbl == "dropped")
    gated = sorted(s for s, lbl in zip(pool, labels, strict=True) if lbl == "gated")
    return missing, dropped, gated


@given(partition=_three_disjoint_sets())
def test_part2_accounting_invariant_under_random_partition(
    partition: tuple[list[str], list[str], list[str]],
) -> None:
    """For any 3-way partition of a synthetic manifest into
    {missing-from-dataset, dropped-no-LS, gated} buckets, the accounting
    equation holds:

        len(manifest) == len(missing) + len(dropped) + len(gated)

    This is the property version of
    ``test_part2_accounting_invariant_against_synthetic_manifest`` in
    ``test_osap_replicate.py`` — generalises the single example into
    a coverage band that catches accidental double-counting (e.g., a
    signal in BOTH missing and dropped) on any partition shape.
    """
    missing, dropped, gated = partition
    manifest = sorted(set(missing) | set(dropped) | set(gated))

    # Build the synthetic returns DataFrame: dropped signals have 1
    # port; gated signals have 2 ports; missing signals have 0 rows.
    rows: list[tuple[str, str, str, float]] = []
    for sig in dropped:
        rows.append((sig, "01", "2024-06-28", 1.0))
    for sig in gated:
        rows.append((sig, "01", "2024-06-28", 1.5))
        rows.append((sig, "10", "2024-06-28", 0.5))
    if not rows:
        df = pd.DataFrame(columns=["signalname", "port", "date", "ret"])
    else:
        df = _make_returns_df(rows)

    observed_present = osap_replicate.signals_in_dataframe(df)
    observed_missing = sorted(set(manifest) - observed_present)
    observed_dropped = [
        s for s in osap_replicate.signals_dropped_no_long_short(df) if s in set(manifest)
    ]
    observed_gated_signals = (
        set(osap_replicate.compute_long_short_returns(df)["signalname"])
        if not df.empty
        else set()
    )
    observed_gated = sorted(observed_gated_signals & set(manifest))

    # Three-bucket equality (each signal in EXACTLY one bucket).
    assert observed_missing == missing
    assert observed_dropped == dropped
    assert observed_gated == gated

    # Headline invariant.
    assert (
        len(observed_missing) + len(observed_dropped) + len(observed_gated)
        == len(manifest)
    )

    # Disjointness — no signal appears in more than one bucket.
    assert not (set(observed_missing) & set(observed_dropped))
    assert not (set(observed_missing) & set(observed_gated))
    assert not (set(observed_dropped) & set(observed_gated))


# ---------------------------------------------------------------------------
# Property 5 — coverage_by_signal values are in [0, 100]
# ---------------------------------------------------------------------------


@given(
    n_tickers=st.integers(min_value=1, max_value=15),
    n_signals=st.integers(min_value=0, max_value=5),
    drop_some_inner=st.booleans(),
)
def test_coverage_by_signal_returns_pct_in_0_to_100(
    n_tickers: int, n_signals: int, drop_some_inner: bool
) -> None:
    """For any signal_map drawn from random universe shape, the
    per-signal coverage value lives in [0, 100] (percent). Catches
    accidental [0, 1] / [0, 100] confusion."""
    rng = np.random.RandomState(42)
    signal_names = [f"SIG_{i}" for i in range(n_signals)]
    signal_map: dict[str, dict[str, float] | None] = {}
    for t_i in range(n_tickers):
        ticker = f"TKR_{t_i:02d}"
        if drop_some_inner and t_i % 3 == 0 and signal_names:
            # Drop random subset of signals for this ticker.
            drop_mask = rng.random(len(signal_names)) > 0.5
            inner = {
                s: float(rng.random())
                for s, drop in zip(signal_names, drop_mask, strict=True)
                if not drop
            }
            signal_map[ticker] = inner if inner else None
        else:
            if not signal_names:
                signal_map[ticker] = None
                continue
            signal_map[ticker] = {s: float(rng.random()) for s in signal_names}

    coverage = osap_replicate.coverage_by_signal(signal_map)
    for sig, pct in coverage.items():
        assert 0.0 <= pct <= 100.0, (
            f"coverage_by_signal[{sig}] = {pct} outside [0, 100]"
        )


# ---------------------------------------------------------------------------
# Property 6 — rank_signals_cross_sectional returns values in (0, 1]
# ---------------------------------------------------------------------------


@given(
    ls_returns=st.lists(
        st.floats(
            min_value=-100.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=12,
    )
)
def test_rank_signals_cross_sectional_returns_unit_interval(
    ls_returns: list[float],
) -> None:
    """For any non-empty cross-section of long-short returns, the
    percentile-ranked output lives in (0, 1]. Domain contract the
    blend layer depends on (rank as proxy for cross-sectional
    exposure)."""
    cs = pd.DataFrame(
        {
            "signalname": [f"SIG_{i}" for i in range(len(ls_returns))],
            "date": ["2024-01-31"] * len(ls_returns),
            "ls_return": ls_returns,
        }
    )
    ranks = osap_replicate.rank_signals_cross_sectional(cs)
    # Empty input → empty Series (handled separately upstream).
    if ranks.empty:
        return
    for sig, rank in ranks.items():
        assert 0.0 < float(rank) <= 1.0, (
            f"rank[{sig}] = {rank} outside (0, 1]"
        )
