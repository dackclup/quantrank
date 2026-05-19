"""Tests for compute.features.osap_replicate.

Phase 4h commit 2. Twelve offline tests covering long-short
derivation, as-of cross-section selection, cross-sectional ranking,
the universe-gap None policy, and end-to-end ``compute_osap_signals``.
No @network markers — all tests use either a hand-built synthetic
DataFrame or the shipped ``tests/fixtures/osap_returns_sample.csv``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from compute import config
from compute.features import osap_replicate

FIXTURE_CSV = Path(__file__).parent.parent / "fixtures" / "osap_returns_sample.csv"


def _make_returns(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    """Build a synthetic OSAP returns DataFrame from
    ``(signalname, port, date_str, ret)`` tuples. Adds the trailing
    ``signallag / Nlong / Nshort`` columns with neutral defaults so the
    schema matches the ingest layer's REQUIRED_COLUMNS contract."""
    df = pd.DataFrame(
        rows, columns=["signalname", "port", "date", "ret"]
    )
    df["signallag"] = 0.0
    df["Nlong"] = 50
    df["Nshort"] = 50
    return df


def test_compute_long_short_returns_basic():
    """Two signals × one date with both ports → 2 long-short rows."""
    returns = _make_returns(
        [
            ("BM", "01", "2024-01-31", 1.50),
            ("BM", "10", "2024-01-31", -0.25),
            ("Mom12m", "01", "2024-01-31", 2.10),
            ("Mom12m", "10", "2024-01-31", 0.30),
        ]
    )
    ls = osap_replicate.compute_long_short_returns(returns)

    assert set(ls.columns) == {"signalname", "date", "ls_return"}
    assert len(ls) == 2

    bm_row = ls[ls["signalname"] == "BM"].iloc[0]
    mom_row = ls[ls["signalname"] == "Mom12m"].iloc[0]
    assert bm_row["ls_return"] == pytest.approx(1.75)
    assert mom_row["ls_return"] == pytest.approx(1.80)


def test_compute_long_short_returns_missing_short_port_drops_signal():
    """A signal with port=01 only (no port=10) yields no long-short row."""
    returns = _make_returns(
        [
            ("BM", "01", "2024-01-31", 1.50),  # long only — no pair
            ("Mom12m", "01", "2024-01-31", 2.00),
            ("Mom12m", "10", "2024-01-31", 0.50),
        ]
    )
    ls = osap_replicate.compute_long_short_returns(returns)

    assert "BM" not in ls["signalname"].values
    assert "Mom12m" in ls["signalname"].values


def test_compute_long_short_returns_drops_decile_buckets():
    """Inner decile buckets (port=02..09) must NOT contribute to ls_return."""
    returns = _make_returns(
        [
            ("BM", "01", "2024-01-31", 5.0),
            ("BM", "05", "2024-01-31", 99.0),  # noise — should be ignored
            ("BM", "10", "2024-01-31", 1.0),
        ]
    )
    ls = osap_replicate.compute_long_short_returns(returns)

    assert len(ls) == 1
    assert ls.iloc[0]["ls_return"] == pytest.approx(4.0)


def test_compute_long_short_returns_handles_integer_port():
    """OSAP parquet may store ``port`` as int (1..10); normaliser must
    coerce both representations to '01'/'10'."""
    df = pd.DataFrame(
        [
            ("BM", 1, "2024-01-31", 5.0),
            ("BM", 10, "2024-01-31", 1.0),
        ],
        columns=["signalname", "port", "date", "ret"],
    )
    df["signallag"] = 0.0
    df["Nlong"] = 50
    df["Nshort"] = 50

    ls = osap_replicate.compute_long_short_returns(df)
    assert len(ls) == 1
    assert ls.iloc[0]["ls_return"] == pytest.approx(4.0)


def test_select_as_of_cross_section_picks_most_recent_per_signal():
    """For each signal, the row with the maximum date <= as_of is kept."""
    ls_returns = pd.DataFrame(
        [
            ("BM", "2023-12-31", 1.0),
            ("BM", "2024-01-31", 1.5),  # most recent for BM
            ("Mom12m", "2024-01-31", 2.0),
            ("Mom12m", "2023-11-30", 1.9),
        ],
        columns=["signalname", "date", "ls_return"],
    )
    cs = osap_replicate.select_as_of_cross_section(
        ls_returns, date(2024, 1, 31)
    )

    assert len(cs) == 2
    bm = cs[cs["signalname"] == "BM"].iloc[0]
    mom = cs[cs["signalname"] == "Mom12m"].iloc[0]
    assert bm["ls_return"] == pytest.approx(1.5)
    assert mom["ls_return"] == pytest.approx(2.0)


def test_select_as_of_cross_section_filters_future_dates():
    """Observations after ``as_of`` must be dropped before the
    most-recent-per-signal pick."""
    ls_returns = pd.DataFrame(
        [
            ("BM", "2024-01-31", 1.0),
            ("BM", "2024-06-30", 5.0),  # AFTER as_of — must not be picked
        ],
        columns=["signalname", "date", "ls_return"],
    )
    cs = osap_replicate.select_as_of_cross_section(
        ls_returns, date(2024, 2, 28)
    )

    assert len(cs) == 1
    assert cs.iloc[0]["ls_return"] == pytest.approx(1.0)


def test_select_as_of_cross_section_empty_window():
    """``as_of`` precedes all observations → empty cross-section."""
    ls_returns = pd.DataFrame(
        [
            ("BM", "2024-01-31", 1.0),
            ("Mom12m", "2024-01-31", 2.0),
        ],
        columns=["signalname", "date", "ls_return"],
    )
    cs = osap_replicate.select_as_of_cross_section(
        ls_returns, date(2020, 1, 1)
    )

    assert cs.empty
    assert list(cs.columns) == ["signalname", "date", "ls_return"]


def test_rank_signals_cross_sectional_normalises_to_unit_interval():
    """Three signals with distinct ls_return → ranks ≈ {1/3, 2/3, 1}."""
    cs = pd.DataFrame(
        [
            ("Low", "2024-01-31", 0.1),
            ("Mid", "2024-01-31", 0.5),
            ("High", "2024-01-31", 0.9),
        ],
        columns=["signalname", "date", "ls_return"],
    )
    ranks = osap_replicate.rank_signals_cross_sectional(cs)

    assert ranks["Low"] == pytest.approx(1 / 3)
    assert ranks["Mid"] == pytest.approx(2 / 3)
    assert ranks["High"] == pytest.approx(1.0)
    assert ranks.max() <= 1.0
    assert ranks.min() > 0.0


def test_rank_signals_cross_sectional_ties_get_average_rank():
    """Two signals with identical ls_return share the same average rank."""
    cs = pd.DataFrame(
        [
            ("A", "2024-01-31", 0.5),
            ("B", "2024-01-31", 0.5),
            ("C", "2024-01-31", 0.9),
        ],
        columns=["signalname", "date", "ls_return"],
    )
    ranks = osap_replicate.rank_signals_cross_sectional(cs)

    # method='average', pct=True: A and B tie at ranks 1 and 2 →
    # average rank 1.5 → pct 1.5/3 = 0.5
    assert ranks["A"] == pytest.approx(0.5)
    assert ranks["B"] == pytest.approx(0.5)
    assert ranks["C"] == pytest.approx(1.0)


def test_compute_osap_signals_full_path_proxy_mode():
    """End-to-end: synthetic 3-signal fixture × 4 tickers → every ticker
    receives the same signal map (factor-exposure proxy, locked
    2026-05-18)."""
    returns = _make_returns(
        [
            ("BM", "01", "2024-01-31", 1.5),
            ("BM", "10", "2024-01-31", -0.5),  # ls = 2.0
            ("Mom12m", "01", "2024-01-31", 0.8),
            ("Mom12m", "10", "2024-01-31", 0.6),  # ls = 0.2
            ("Beta", "01", "2024-01-31", 0.3),
            ("Beta", "10", "2024-01-31", 0.4),  # ls = -0.1
        ]
    )
    tickers = ["NVDA", "AAPL", "CF", "HST"]
    signals = ("BM", "Mom12m", "Beta")

    result = osap_replicate.compute_osap_signals(
        returns, tickers, date(2024, 2, 28), requested_signals=signals
    )

    assert set(result.keys()) == set(tickers)
    # Every ticker gets a non-None dict in the proxy version
    for ticker in tickers:
        assert result[ticker] is not None, f"{ticker} should have a signal map"
        assert set(result[ticker].keys()) == set(signals)

    # All tickers MUST share the same map (factor-exposure proxy invariant)
    assert result["NVDA"] == result["AAPL"] == result["CF"] == result["HST"]

    # Rank ordering: BM (ls=2.0) > Mom12m (ls=0.2) > Beta (ls=-0.1)
    one_map = result["NVDA"]
    assert one_map["BM"] == pytest.approx(1.0)
    assert one_map["Mom12m"] == pytest.approx(2 / 3)
    assert one_map["Beta"] == pytest.approx(1 / 3)


def test_compute_osap_signals_empty_returns_yields_none_per_ticker():
    """Empty input DataFrame → every ticker maps to None (universe gap)."""
    returns = _make_returns([])
    tickers = ["NVDA", "AAPL"]

    result = osap_replicate.compute_osap_signals(
        returns, tickers, date(2024, 1, 31)
    )

    assert result == {"NVDA": None, "AAPL": None}


def test_compute_osap_signals_universe_gap_before_coverage():
    """``as_of`` precedes OSAP coverage → every ticker maps to None.

    Distinct from pillar ``neutralize_missing`` — OSAP does NOT impute
    a neutral value; the blend layer (commit 3) interprets None as
    'no OSAP adjustment' and passes composite_score through.
    """
    returns = _make_returns(
        [
            ("BM", "01", "2024-01-31", 1.5),
            ("BM", "10", "2024-01-31", -0.5),
        ]
    )
    tickers = ["NVDA", "AAPL"]

    # as_of well before the only observation
    result = osap_replicate.compute_osap_signals(
        returns,
        tickers,
        date(2020, 1, 1),
        requested_signals=("BM",),
    )

    assert result == {"NVDA": None, "AAPL": None}


def test_compute_osap_signals_default_manifest_is_100_signals():
    """Sanity: the module's default manifest matches config.OSAP_SIGNALS_100
    and the manifest itself has the expected shape."""
    assert len(config.OSAP_SIGNALS_100) == 100
    assert len(set(config.OSAP_SIGNALS_100)) == 100, "no duplicates in manifest"

    # Theme buckets must sum to exactly 100
    theme_sum = sum(
        len(sigs) for sigs in config.OSAP_SIGNALS_BY_THEME.values()
    )
    assert theme_sum == 100


def test_compute_osap_signals_uses_shipped_fixture():
    """End-to-end with the shipped scout fixture
    ``tests/fixtures/osap_returns_sample.csv``. Anchors the test suite
    against the same file the @network live test uses, so a hand-edit
    of the fixture surfaces here too."""
    fixture = pd.read_csv(FIXTURE_CSV)
    assert {"signalname", "port", "date", "ret"}.issubset(fixture.columns)

    # Pick an as_of after the latest fixture date so all signals have
    # at least one observation visible.
    as_of_ts = pd.to_datetime(fixture["date"]).max()
    as_of_dt = as_of_ts.date()

    tickers = ["NVDA", "AAPL"]
    result = osap_replicate.compute_osap_signals(
        fixture,
        tickers,
        as_of_dt,
        requested_signals=tuple(fixture["signalname"].unique()),
    )

    # At least one ticker should have a non-None signal map (the fixture
    # carries 4 long-short pairs across 2 dates).
    non_none_count = sum(1 for v in result.values() if v is not None)
    assert non_none_count == len(tickers), (
        "shipped fixture should produce a non-None signal map for every "
        f"ticker; got {non_none_count}/{len(tickers)}"
    )


# ---------------------------------------------------------------------------
# Phase 4h.2 Part 1 — signals_in_dataframe helper (issue #116)
# ---------------------------------------------------------------------------


def test_signals_in_dataframe_empty_returns_empty_frozenset():
    """Empty DataFrame (correct schema, zero rows) → empty frozenset.
    NOT a KeyError or NaN — the manifest-vs-dataset set diff downstream
    expects a usable empty set."""
    df = pd.DataFrame(columns=["signalname", "port", "date", "ret"])
    result = osap_replicate.signals_in_dataframe(df)
    assert result == frozenset()
    assert isinstance(result, frozenset)


def test_signals_in_dataframe_no_signalname_column_returns_empty_frozenset():
    """DataFrame without the ``signalname`` column → empty frozenset
    (defensive). Caller's set diff then surfaces the full manifest as
    missing — safer than raising on a schema-drift edge case."""
    df = pd.DataFrame({"other_col": [1, 2, 3]})
    result = osap_replicate.signals_in_dataframe(df)
    assert result == frozenset()


def test_signals_in_dataframe_unique_signals_dedup():
    """Multi-row input with duplicate signalnames → frozenset dedups.
    Mirrors the real OSAP shape where each ``signalname`` appears once
    per ``(port, date)`` cell."""
    df = pd.DataFrame(
        {
            "signalname": ["Mom12m", "BM", "Mom12m", "Accruals", "BM"],
            "port": ["01", "01", "10", "01", "10"],
            "date": ["2024-01-31"] * 5,
            "ret": [0.1, 0.2, -0.05, 0.15, -0.1],
        }
    )
    assert osap_replicate.signals_in_dataframe(df) == frozenset(
        {"Mom12m", "BM", "Accruals"}
    )


def test_signals_in_dataframe_setdiff_with_manifest_simulates_silent_drop():
    """Simulates the issue-#116 silent-drop: manifest declares 5
    signals; dataset surfaces only 2. Set diff is the missing-3."""
    manifest = ("BM", "Mom12m", "AOP", "AccrualsBM", "ChEQ")
    df = pd.DataFrame(
        {
            "signalname": ["BM", "BM", "Mom12m"],
            "port": ["01", "10", "01"],
            "date": ["2024-01-31"] * 3,
            "ret": [0.1, -0.05, 0.2],
        }
    )
    present = osap_replicate.signals_in_dataframe(df)
    missing = sorted(set(manifest) - present)
    assert missing == ["AOP", "AccrualsBM", "ChEQ"]
