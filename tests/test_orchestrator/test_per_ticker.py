"""Unit tests for compute.orchestrator.per_ticker (PR #259-R7a).

All tests are offline/synthetic: a tiny hand-built universe DataFrame plus
simple snapshot stand-ins (a minimal ``_FakeSnapshot`` with just ``cik`` +
``shares_outstanding`` — the only two attributes
``build_ticker_membership_maps`` reads off a snapshot) are fed directly to
``build_ticker_membership_maps``. No network calls, no real
``FundamentalsSnapshot`` construction required.

Coverage
--------
A — cohort_by_ticker
    A1  Built for every ticker in df, defaulting to "sp500" when the
        "cohort" column/value is absent.
    A2  Reads an explicit "cohort" value (e.g. "sp400") when present.

B — memberships_by_ticker
    B1  A dow30 ticker with a known positive market cap gets
        ["sp500", "dow30", "russell1000"] (cohort first, then dow30, then
        russell1000 proxy — ndx absent for this ticker).
    B2  A ndx ticker gets "ndx" appended.
    B3  A ticker with snap=None (no market cap) does NOT get the
        "russell1000" tag, but cohort_by_ticker / memberships_by_ticker
        keys are still present (graceful degradation, not a KeyError).
    B4  A ticker with a present snapshot but shares_outstanding=None also
        does not get "russell1000" (market_cap resolves to None).
    B5  A sp600-cohort ticker with a positive known market cap does NOT
        get "russell1000" (the small-cap suppression guard).
    B6  Every ticker key present in cohort_by_ticker has a corresponding
        key in memberships_by_ticker (built from the same dict).

C — multi_class_flagged_tickers (CIK-collision + market-cap-floor detector)
    C1  Two tickers sharing the same CIK, both above the market-cap floor,
        both fire.
    C2  A lone ticker (no CIK collision) never fires even with a huge cap.
    C3  A ticker with snap=None is excluded from collision detection
        (its CIK contributes nothing) and never fires.
    C4  Below-floor market cap on a colliding pair does not fire.

D — return shape / snapshot isolation
    D1  Returns exactly a 3-tuple: (set, dict, dict).
    D2  market_cap_by_ticker / cik_by_ticker are NOT part of the return
        value (internal only) — return tuple has exactly 3 elements and
        none of them is a mapping keyed the same way with float|None cap
        values under an unexpected 4th slot.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from compute.orchestrator.per_ticker import build_ticker_membership_maps

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeSnapshot:
    """Minimal snapshot stand-in — only the 2 attributes
    ``build_ticker_membership_maps`` reads: ``cik`` and
    ``shares_outstanding``. Decoupled from the real ``FundamentalsSnapshot``
    dataclass (which requires no extra fields to construct, but this stand-in
    keeps the test hermetic and readable)."""

    cik: str
    shares_outstanding: float | None = None


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal universe DataFrame.

    Each row dict should have at least ``ticker`` and ``current_price``;
    ``cohort`` is optional (mirrors the real df where the column is always
    present on the sp500/sp900/sp1500 paths, but the code path also
    defends against a missing column via ``r.get("cohort", "sp500")``).
    """
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Section A: cohort_by_ticker
# ---------------------------------------------------------------------------


def test_A1_cohort_defaults_to_sp500_when_column_absent():
    """No 'cohort' column at all -> every ticker defaults to 'sp500'."""
    df = _make_df(
        [
            {"ticker": "AAA", "current_price": 10.0},
            {"ticker": "BBB", "current_price": 20.0},
        ]
    )
    snapshots = {"AAA": _FakeSnapshot(cik="1"), "BBB": _FakeSnapshot(cik="2")}

    _, cohort_by_ticker, _ = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert cohort_by_ticker == {"AAA": "sp500", "BBB": "sp500"}


def test_A2_cohort_reads_explicit_value():
    """An explicit 'cohort' value (e.g. 'sp400') is read as-is."""
    df = _make_df(
        [
            {"ticker": "MID", "current_price": 15.0, "cohort": "sp400"},
        ]
    )
    snapshots = {"MID": _FakeSnapshot(cik="9")}

    _, cohort_by_ticker, _ = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert cohort_by_ticker == {"MID": "sp400"}


# ---------------------------------------------------------------------------
# Section B: memberships_by_ticker
# ---------------------------------------------------------------------------


def test_B1_dow30_ticker_gets_dow30_and_russell1000():
    """A dow30 ticker with a known positive market cap: cohort first, then
    dow30, then russell1000 (ndx absent for this ticker)."""
    df = _make_df(
        [{"ticker": "DOW", "current_price": 100.0, "cohort": "sp500"}]
    )
    snapshots = {"DOW": _FakeSnapshot(cik="1", shares_outstanding=1_000_000.0)}

    _, _, memberships_by_ticker = build_ticker_membership_maps(
        df, snapshots, dow30={"DOW"}, ndx=set()
    )

    assert memberships_by_ticker["DOW"] == ["sp500", "dow30", "russell1000"]


def test_B2_ndx_ticker_gets_ndx_appended():
    """A ndx ticker gets 'ndx' appended after cohort/dow30."""
    df = _make_df(
        [{"ticker": "NDXT", "current_price": 50.0, "cohort": "sp500"}]
    )
    snapshots = {"NDXT": _FakeSnapshot(cik="2", shares_outstanding=500_000.0)}

    _, _, memberships_by_ticker = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx={"NDXT"}
    )

    assert memberships_by_ticker["NDXT"] == ["sp500", "ndx", "russell1000"]


def test_B3_snap_none_still_present_no_russell1000():
    """snap=None -> no market cap -> no 'russell1000' tag, but the ticker
    still gets a cohort_by_ticker / memberships_by_ticker entry (graceful
    degradation, never a KeyError)."""
    df = _make_df(
        [{"ticker": "NOSNAP", "current_price": 30.0, "cohort": "sp500"}]
    )
    snapshots: dict[str, _FakeSnapshot | None] = {"NOSNAP": None}

    multi_class_flagged, cohort_by_ticker, memberships_by_ticker = (
        build_ticker_membership_maps(df, snapshots, dow30=set(), ndx=set())
    )

    assert cohort_by_ticker["NOSNAP"] == "sp500"
    assert memberships_by_ticker["NOSNAP"] == ["sp500"]
    assert "NOSNAP" not in multi_class_flagged


def test_B4_shares_outstanding_none_gives_no_russell1000():
    """A present snapshot with shares_outstanding=None -> market_cap
    resolves to None -> no 'russell1000' tag."""
    df = _make_df(
        [{"ticker": "NOSHR", "current_price": 40.0, "cohort": "sp500"}]
    )
    snapshots = {"NOSHR": _FakeSnapshot(cik="3", shares_outstanding=None)}

    _, _, memberships_by_ticker = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert memberships_by_ticker["NOSHR"] == ["sp500"]


def test_B5_sp600_cohort_suppresses_russell1000():
    """A sp600-cohort ticker with a positive known market cap does NOT
    get 'russell1000' — the small-cap suppression guard in
    derive_index_memberships."""
    df = _make_df(
        [{"ticker": "SMALL", "current_price": 20.0, "cohort": "sp600"}]
    )
    snapshots = {"SMALL": _FakeSnapshot(cik="4", shares_outstanding=100_000.0)}

    _, _, memberships_by_ticker = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert memberships_by_ticker["SMALL"] == ["sp600"]


def test_B6_every_cohort_key_has_a_membership_key():
    """memberships_by_ticker is built from cohort_by_ticker.items() —
    every key in one must be present in the other."""
    df = _make_df(
        [
            {"ticker": "X1", "current_price": 10.0, "cohort": "sp500"},
            {"ticker": "X2", "current_price": 20.0, "cohort": "sp400"},
            {"ticker": "X3", "current_price": 30.0, "cohort": "sp600"},
        ]
    )
    snapshots = {
        "X1": _FakeSnapshot(cik="1", shares_outstanding=1.0),
        "X2": None,
        "X3": _FakeSnapshot(cik="3", shares_outstanding=None),
    }

    _, cohort_by_ticker, memberships_by_ticker = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert set(cohort_by_ticker.keys()) == set(memberships_by_ticker.keys())


# ---------------------------------------------------------------------------
# Section C: multi_class_flagged_tickers
# ---------------------------------------------------------------------------


def test_C1_cik_collision_above_floor_fires_both():
    """Two tickers sharing the same CIK, both with a market cap above the
    10% x universe-median floor, both fire."""
    df = _make_df(
        [
            {"ticker": "CLASSA", "current_price": 100.0, "cohort": "sp500"},
            {"ticker": "CLASSB", "current_price": 100.0, "cohort": "sp500"},
            # A third, unrelated ticker to establish a lower median so both
            # CLASSA/CLASSB clear the 10% floor comfortably.
            {"ticker": "OTHER", "current_price": 1.0, "cohort": "sp500"},
        ]
    )
    snapshots = {
        "CLASSA": _FakeSnapshot(cik="SAME", shares_outstanding=1_000_000.0),
        "CLASSB": _FakeSnapshot(cik="SAME", shares_outstanding=1_000_000.0),
        "OTHER": _FakeSnapshot(cik="OTHERCIK", shares_outstanding=1_000.0),
    }

    multi_class_flagged, _, _ = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert "CLASSA" in multi_class_flagged
    assert "CLASSB" in multi_class_flagged
    assert "OTHER" not in multi_class_flagged


def test_C2_lone_ticker_never_fires_even_with_huge_cap():
    """A ticker with a unique CIK never fires, regardless of market cap
    size (no collision possible)."""
    df = _make_df(
        [{"ticker": "LONE", "current_price": 1_000_000.0, "cohort": "sp500"}]
    )
    snapshots = {"LONE": _FakeSnapshot(cik="UNIQUE", shares_outstanding=1_000.0)}

    multi_class_flagged, _, _ = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert multi_class_flagged == set()


def test_C3_snap_none_excluded_from_collision_detection():
    """A ticker with snap=None contributes no CIK to the collision map and
    can never fire, even if another ticker happens to share a CIK
    string coincidentally with something else."""
    df = _make_df(
        [
            {"ticker": "NOSNAP1", "current_price": 50.0, "cohort": "sp500"},
            {"ticker": "NOSNAP2", "current_price": 50.0, "cohort": "sp500"},
        ]
    )
    snapshots: dict[str, _FakeSnapshot | None] = {
        "NOSNAP1": None,
        "NOSNAP2": None,
    }

    multi_class_flagged, _, _ = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert multi_class_flagged == set()


def test_C4_below_floor_collision_does_not_fire():
    """Two tickers share a CIK, but neither's market cap exceeds the 10%
    x universe-median floor -> neither fires.

    ``statistics.median`` of an even-length list averages the two middle
    values, so two additional large-cap tickers (HUGE1/HUGE2, both far
    above SMALLA/SMALLB) pull the universe median up to a point where
    10% of it still exceeds SMALLA/SMALLB's own market cap.
    """
    df = _make_df(
        [
            {"ticker": "SMALLA", "current_price": 10.0, "cohort": "sp500"},
            {"ticker": "SMALLB", "current_price": 10.0, "cohort": "sp500"},
            {"ticker": "HUGE1", "current_price": 1_000_000.0, "cohort": "sp500"},
            {"ticker": "HUGE2", "current_price": 1_000_000.0, "cohort": "sp500"},
        ]
    )
    snapshots = {
        "SMALLA": _FakeSnapshot(cik="SHARED", shares_outstanding=1.0),
        "SMALLB": _FakeSnapshot(cik="SHARED", shares_outstanding=1.0),
        "HUGE1": _FakeSnapshot(cik="HUGECIK1", shares_outstanding=1_000_000.0),
        "HUGE2": _FakeSnapshot(cik="HUGECIK2", shares_outstanding=1_000_000.0),
    }
    # Sanity-check the fixture's own arithmetic so the test's intent is
    # self-documenting and can't silently drift if MARKET_CAP_FLOOR_RATIO
    # or the detector's formula ever changes:
    #   market caps = [10, 10, 1e12, 1e12] -> median = (10 + 1e12) / 2
    #   floor = 0.10 * median >> 10 (SMALLA/SMALLB's own cap)
    from statistics import median

    from compute.scoring.multi_class_shares import MARKET_CAP_FLOOR_RATIO

    caps = [10.0, 10.0, 1_000_000.0 * 1_000_000.0, 1_000_000.0 * 1_000_000.0]
    assert MARKET_CAP_FLOOR_RATIO * median(caps) > 10.0

    multi_class_flagged, _, _ = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert multi_class_flagged == set()


# ---------------------------------------------------------------------------
# Section D: return shape / snapshot isolation
# ---------------------------------------------------------------------------


def test_D1_returns_exactly_a_3_tuple():
    """build_ticker_membership_maps returns exactly (set, dict, dict)."""
    df = _make_df([{"ticker": "T", "current_price": 1.0, "cohort": "sp500"}])
    snapshots = {"T": _FakeSnapshot(cik="1", shares_outstanding=1.0)}

    result = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    assert isinstance(result, tuple)
    assert len(result) == 3
    multi_class_flagged, cohort_by_ticker, memberships_by_ticker = result
    assert isinstance(multi_class_flagged, set)
    assert isinstance(cohort_by_ticker, dict)
    assert isinstance(memberships_by_ticker, dict)


def test_D2_internal_maps_not_leaked_into_return_value():
    """cik_by_ticker / market_cap_by_ticker are internal-only: the 3
    returned values are exactly (flagged-set, cohort-dict[str,str],
    memberships-dict[str,list[str]]) — no 4th slot, and the 2nd/3rd dict
    values are never raw market-cap floats or CIK strings."""
    df = _make_df([{"ticker": "T", "current_price": 1.0, "cohort": "sp500"}])
    snapshots = {"T": _FakeSnapshot(cik="1", shares_outstanding=1.0)}

    _, cohort_by_ticker, memberships_by_ticker = build_ticker_membership_maps(
        df, snapshots, dow30=set(), ndx=set()
    )

    # cohort_by_ticker values are cohort strings ("sp500"/"sp400"/"sp600"),
    # never a CIK or a market-cap float.
    assert cohort_by_ticker["T"] == "sp500"
    assert isinstance(cohort_by_ticker["T"], str)
    # memberships_by_ticker values are lists of membership code strings.
    assert isinstance(memberships_by_ticker["T"], list)
    assert all(isinstance(code, str) for code in memberships_by_ticker["T"])
