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

E — run_per_ticker_loop (PR #259-R7b)
    Mostly-REAL exercise of the Step-8 per-ticker loop: a tiny 2-3 ticker
    synthetic universe with real ``FundamentalsSnapshot`` / ``BeneishResult``
    / ``DechowResult`` instances, real ``_filing_lag`` / ``_build_raw_metrics``
    injected from ``compute.main`` (the actual production wiring), and the
    real (pure, no-network) scoring/valuation/recommendation functions. Only
    the network-touching cross-source + EDGAR-filing lookups are
    monkeypatched (deterministic no-fire stand-ins) and ``config.DATA_DIR``
    is redirected to ``tmp_path`` so the real ``write_stock_detail`` /
    ``write_stock_history`` calls land on disk safely.

    E1  Result is a ``PerTickerLoopResult`` whose field set matches
        ``dataclasses.fields`` exactly (28 fields) — the return-contract
        shape lock.
    E2  ``summaries`` / ``all_details`` have one entry per ticker, in
        ``StockSummary`` / ``StockDetail`` instances, and both stock-detail
        + stock-history JSON files are actually written to ``tmp_path``.
    E3  ``fundamentals_unavailable_count == 1`` for the one ticker with
        ``snap=None``.
    E4  ``low_liquidity_annotate_count == 1`` for the one ticker whose
        ``adv_by_ticker`` value sits below ``config.ADV_FLOOR_USD`` — and
        the ``"low_liquidity"`` annotate lands in that ticker's
        ``valuation_warnings`` (rank-neutral: no ``risk_flags`` change).
    E5  ``multi_class_aggregate_shares_suspected_count == 1`` for the one
        ticker in the injected ``multi_class_flagged_tickers`` set, and the
        matching annotate lands in ``valuation_warnings``.
    E6  The injected ``filing_lag_fn`` / ``build_raw_metrics_fn`` callables
        (the real ``compute.main._filing_lag`` / ``_build_raw_metrics``) are
        actually invoked (call-count > 0 via a counting wrapper) — locks the
        injection contract described in the module docstring.
    E7  Degenerate empty-universe call (``df`` with zero rows) returns a
        ``PerTickerLoopResult`` with empty ``summaries`` / ``all_details``
        and every counter at its zero/empty init value — no exception.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.main import _build_raw_metrics, _filing_lag
from compute.orchestrator import per_ticker
from compute.orchestrator.per_ticker import (
    PerTickerLoopResult,
    build_ticker_membership_maps,
    run_per_ticker_loop,
)
from compute.output.schemas import StockDetail, StockSummary
from compute.scoring.beneish import BeneishResult
from compute.scoring.dechow_f import DechowResult
from compute.scoring.restatement_filings import (
    LateFilingResult,
    RestatementHistoryResult,
)

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


# ---------------------------------------------------------------------------
# Section E: run_per_ticker_loop (PR #259-R7b)
# ---------------------------------------------------------------------------
#
# Mostly-REAL exercise: only the network-touching cross-source + EDGAR-filing
# lookups are monkeypatched (deterministic no-fire stand-ins bound directly
# on the `per_ticker` module namespace, since they were imported there via
# `from X import Y`). Everything else — the fair-price ensemble, the earnings
# -quality checks, recommendation/loss-chance/manipulation-index, the RIM
# applicability dual-count, and the real `write_stock_detail` /
# `write_stock_history` I/O against `tmp_path` — runs for real.


ASOF_DATE = date(2026, 6, 30)
NOW = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def _snap(**overrides) -> FundamentalsSnapshot:
    """A minimal-but-real FundamentalsSnapshot (mirrors tests/test_main.py's
    own ``_snap()`` fixture) — real dataclass, not a stand-in, so every real
    (non-network) function the loop calls on it behaves exactly as in
    production."""
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "net_income": 50.0,
        "stockholders_equity": 100.0,
        "shares_outstanding": 10.0,
        "eps_diluted": 5.0,
        "revenue": 500.0,
        "total_assets": 400.0,
        "ebitda": 50.0,
        "long_term_debt": 20.0,
        "short_term_debt": 5.0,
        "cash": 10.0,
        "goodwill": 0.0,
        "intangibles_net": 0.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 5, 1),
    }
    defaults.update(overrides)
    return FundamentalsSnapshot(**defaults)


def _valid_prices_df() -> pd.DataFrame:
    """A minimal-but-real OHLCV DataFrame satisfying write_stock_history's
    required-column + DatetimeIndex contract."""
    idx = pd.date_range("2026-06-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "Open": [10.0, 10.1, 10.2, 10.3, 10.4],
            "High": [10.5, 10.6, 10.7, 10.8, 10.9],
            "Low": [9.5, 9.6, 9.7, 9.8, 9.9],
            "Close": [10.2, 10.3, 10.4, 10.5, 10.6],
            "Volume": [1_000_000, 1_100_000, 1_200_000, 1_300_000, 1_400_000],
        },
        index=idx,
    )


def _patch_network_and_edgar_calls(monkeypatch, *, call_counts: dict | None = None):
    """Monkeypatch every network/EDGAR-touching name the loop calls, bound
    directly on ``compute.orchestrator.per_ticker`` (the module namespace
    they were imported into). All stand-ins are deterministic non-firing
    defaults — no annotate should fire from these paths in the test universe
    (the annotates under test — low_liquidity, multi_class — come from
    pure-Python threshold checks, not these patched fetchers).

    ``call_counts``, if supplied, is incremented per call under each key so
    a test can assert the patched paths were actually exercised.
    """
    counts = call_counts if call_counts is not None else {}

    def _bump(key: str):
        counts[key] = counts.get(key, 0) + 1

    def _fake_validate_market_cap(*, ticker, snap, current_price):
        _bump("cross_source_validate_market_cap")
        return False, None

    def _fake_yf_market_cap(ticker):
        _bump("fetch_yfinance_market_cap")
        return None

    def _fake_yf_shares_outstanding(ticker):
        _bump("fetch_yfinance_shares_outstanding")
        return None

    def _fake_yf_exchange(ticker):
        _bump("fetch_yfinance_exchange")
        return None

    def _fake_yf_dividend(ticker):
        _bump("fetch_yfinance_dividend")
        return None, None, None

    def _fake_yf_security_type(ticker):
        _bump("fetch_yfinance_security_type")
        return None

    def _fake_check_restatement_history(ticker, *, asof=None):
        _bump("check_restatement_history")
        return RestatementHistoryResult(
            fired=False, count=0, latest_filing_date=None, latest_filing_url=None
        )

    def _fake_check_late_filing(ticker, *, asof=None):
        _bump("check_late_filing")
        return LateFilingResult(
            fired=False,
            count=0,
            latest_filing_date=None,
            latest_filing_url=None,
            latest_form=None,
        )

    def _fake_get_amendment_filing_dates(ticker, *, asof=None):
        _bump("get_amendment_filing_dates")
        return ()

    def _fake_get_non_reliance_filing_dates(ticker, *, asof=None):
        _bump("get_non_reliance_filing_dates")
        return ()

    monkeypatch.setattr(per_ticker, "cross_source_validate_market_cap", _fake_validate_market_cap)
    monkeypatch.setattr(per_ticker, "fetch_yfinance_market_cap", _fake_yf_market_cap)
    monkeypatch.setattr(
        per_ticker, "fetch_yfinance_shares_outstanding", _fake_yf_shares_outstanding
    )
    monkeypatch.setattr(per_ticker, "fetch_yfinance_exchange", _fake_yf_exchange)
    monkeypatch.setattr(per_ticker, "fetch_yfinance_dividend", _fake_yf_dividend)
    monkeypatch.setattr(per_ticker, "fetch_yfinance_security_type", _fake_yf_security_type)
    monkeypatch.setattr(
        per_ticker, "check_restatement_history", _fake_check_restatement_history
    )
    monkeypatch.setattr(per_ticker, "check_late_filing", _fake_check_late_filing)
    monkeypatch.setattr(
        per_ticker, "get_amendment_filing_dates", _fake_get_amendment_filing_dates
    )
    monkeypatch.setattr(
        per_ticker, "get_non_reliance_filing_dates", _fake_get_non_reliance_filing_dates
    )
    return counts


def _run_loop_kwargs(*, df, snapshots, tickers, tmp_path, monkeypatch, call_counts=None):
    """Assemble the full keyword-argument set for run_per_ticker_loop from a
    3-ticker (or fewer) synthetic universe, with every other pillar-5b /
    Step-4b/4.5e input at its safe "nothing fired yet" default (empty dict /
    ``.get()``-safe — none of these are direct-indexed except
    beneish_results/dechow_results, which this helper populates for every
    ticker key)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(per_ticker.config, "DATA_DIR", tmp_path)
    _patch_network_and_edgar_calls(monkeypatch, call_counts=call_counts)

    beneish_results = {t: BeneishResult(m_score=None, is_high=False) for t in tickers}
    dechow_results = {t: DechowResult(f_score=None, is_high=False) for t in tickers}

    return dict(
        df=df,
        snapshots=snapshots,
        pillar_df=pd.DataFrame(),
        risk_flags={t: [] for t in tickers},
        beneish_results=beneish_results,
        dechow_results=dechow_results,
        rem_results={},
        post_split_results={},
        tier2_results={},
        histories={},
        historical_metrics={},
        universe_metrics={},
        by_sector={},
        by_sub_industry={},
        broad_ex_fin_util=[],
        adv_by_ticker={},
        prices_by_ticker={},
        imputed_by_ticker={},
        sector_pillar_baselines={},
        form4_diagnostics={},
        osap_signal_map={},
        composite_osap_adjusted=pd.Series(dtype=float),
        cohort_by_ticker={t: "sp500" for t in tickers},
        memberships_by_ticker={t: ["sp500"] for t in tickers},
        multi_class_flagged_tickers=set(),
        entered=set(),
        exited=set(),
        asof_date=ASOF_DATE,
        now=NOW,
        filing_lag_fn=_filing_lag,
        build_raw_metrics_fn=_build_raw_metrics,
    )


def test_E1_result_field_set_matches_dataclass_shape(tmp_path, monkeypatch):
    """PerTickerLoopResult's actual field set (28 fields) is exactly what
    dataclasses.fields() reports — the return-contract shape lock."""
    tickers = ["GOOD"]
    df = _make_df(
        [
            {
                "ticker": "GOOD",
                "name": "Good Corp",
                "current_price": 100.0,
                "sector": "Technology",
                "composite_score": 75.0,
                "rank": 1,
            }
        ]
    )
    snapshots = {"GOOD": _snap(ticker="GOOD")}
    kwargs = _run_loop_kwargs(
        df=df, snapshots=snapshots, tickers=tickers, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    result = run_per_ticker_loop(**kwargs)

    assert isinstance(result, PerTickerLoopResult)
    field_names = {f.name for f in dataclasses.fields(PerTickerLoopResult)}
    assert len(field_names) == 28
    for name in field_names:
        # every declared field is actually set (dataclass would have raised
        # in __init__ already if not, but this locks the attribute-access
        # contract callers rely on, e.g. result.summaries).
        assert hasattr(result, name)


def test_E2_three_ticker_universe_wiring_and_disk_writes(tmp_path, monkeypatch):
    """The main integration exercise: 3 tickers covering the happy path
    (GOOD), the fundamentals_unavailable path (NOSNAP, snap=None), and a
    combined low_liquidity + multi_class_aggregate_shares_suspected path
    (LOWLIQ, also no price history). Asserts summaries/all_details shape,
    the 3 targeted counters, has_history per ticker, and real JSON writes to
    tmp_path (write_stock_detail / write_stock_history are NOT mocked)."""
    tickers = ["GOOD", "NOSNAP", "LOWLIQ"]
    df = _make_df(
        [
            {
                "ticker": "GOOD",
                "name": "Good Corp",
                "current_price": 100.0,
                "sector": "Technology",
                "composite_score": 75.0,
                "rank": 1,
            },
            {
                "ticker": "NOSNAP",
                "name": "No Snapshot Inc",
                "current_price": 50.0,
                "sector": "Health Care",
                "composite_score": 40.0,
                "rank": 2,
            },
            {
                "ticker": "LOWLIQ",
                "name": "Low Liquidity Co",
                "current_price": 20.0,
                "sector": "Industrials",
                "composite_score": 30.0,
                "rank": 3,
            },
        ]
    )
    snapshots = {
        "GOOD": _snap(ticker="GOOD", cik="1"),
        "NOSNAP": None,
        "LOWLIQ": _snap(ticker="LOWLIQ", cik="2"),
    }
    call_counts: dict = {}
    kwargs = _run_loop_kwargs(
        df=df,
        snapshots=snapshots,
        tickers=tickers,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        call_counts=call_counts,
    )
    # ADV: GOOD clears the $5M floor comfortably; LOWLIQ sits below it.
    kwargs["adv_by_ticker"] = {
        "GOOD": 10_000_000.0,
        "NOSNAP": 10_000_000.0,
        "LOWLIQ": 1_000_000.0,
    }
    assert kwargs["adv_by_ticker"]["LOWLIQ"] < config.ADV_FLOOR_USD
    # Prices: GOOD + NOSNAP get real history; LOWLIQ has none (has_history=False).
    kwargs["prices_by_ticker"] = {
        "GOOD": _valid_prices_df(),
        "NOSNAP": _valid_prices_df(),
    }
    # CIK-collision set (from build_ticker_membership_maps in production) —
    # inject LOWLIQ directly to exercise the annotate + counter.
    kwargs["multi_class_flagged_tickers"] = {"LOWLIQ"}

    result = run_per_ticker_loop(**kwargs)

    # E2 — shape.
    assert len(result.summaries) == 3
    assert len(result.all_details) == 3
    assert all(isinstance(s, StockSummary) for s in result.summaries)
    assert all(isinstance(d, StockDetail) for d in result.all_details)
    by_ticker_detail = {d.ticker: d for d in result.all_details}
    assert by_ticker_detail["GOOD"].has_history is True
    assert by_ticker_detail["NOSNAP"].has_history is True
    assert by_ticker_detail["LOWLIQ"].has_history is False

    # Real disk writes — write_stock_detail runs for every ticker;
    # write_stock_history only for GOOD/NOSNAP (LOWLIQ has no price frame).
    for t in tickers:
        assert (tmp_path / "stocks" / f"{t}.json").exists()
    assert (tmp_path / "stocks" / "history" / "GOOD.json").exists()
    assert (tmp_path / "stocks" / "history" / "NOSNAP.json").exists()
    assert not (tmp_path / "stocks" / "history" / "LOWLIQ.json").exists()

    # E3 — fundamentals_unavailable_count: exactly NOSNAP (snap=None).
    assert result.fundamentals_unavailable_count == 1

    # E4 — low_liquidity_annotate_count: exactly LOWLIQ (below ADV floor).
    assert result.low_liquidity_annotate_count == 1
    assert "low_liquidity" in by_ticker_detail["LOWLIQ"].valuation_warnings
    assert "low_liquidity" not in by_ticker_detail["GOOD"].valuation_warnings
    # Rank-neutral per Rule 16 — never in risk_flags, never forces `cautious`.
    assert "low_liquidity" not in by_ticker_detail["LOWLIQ"].risk_flags

    # E5 — multi_class_aggregate_shares_suspected_count: exactly LOWLIQ.
    assert result.multi_class_aggregate_shares_suspected_count == 1
    assert (
        "multi_class_aggregate_shares_suspected"
        in by_ticker_detail["LOWLIQ"].valuation_warnings
    )
    assert (
        "multi_class_aggregate_shares_suspected"
        not in by_ticker_detail["GOOD"].valuation_warnings
    )

    # cross_source_wall_clock_seconds is a real (non-negative) measurement.
    assert result.cross_source_wall_clock_seconds is not None
    assert result.cross_source_wall_clock_seconds >= 0.0

    # The patched network/EDGAR stand-ins were actually reached (sanity that
    # this is exercising the real call sites, not silently skipping them).
    assert call_counts.get("check_restatement_history", 0) == 3
    assert call_counts.get("fetch_yfinance_exchange", 0) == 3


def test_E6_injected_filing_lag_and_raw_metrics_callables_are_invoked(tmp_path, monkeypatch):
    """filing_lag_fn / build_raw_metrics_fn — the two compute.main helpers
    injected as callables (see the module docstring's R7b section) — are
    each invoked at least once per ticker with a non-None snapshot."""
    tickers = ["GOOD"]
    df = _make_df(
        [
            {
                "ticker": "GOOD",
                "name": "Good Corp",
                "current_price": 100.0,
                "sector": "Technology",
                "composite_score": 75.0,
                "rank": 1,
            }
        ]
    )
    snapshots = {"GOOD": _snap(ticker="GOOD")}
    kwargs = _run_loop_kwargs(
        df=df, snapshots=snapshots, tickers=tickers, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    lag_calls = {"n": 0}
    raw_metrics_calls = {"n": 0}

    def _counting_filing_lag(snap, asof):
        lag_calls["n"] += 1
        return _filing_lag(snap, asof)

    def _counting_build_raw_metrics(*args, **kw):
        raw_metrics_calls["n"] += 1
        return _build_raw_metrics(*args, **kw)

    kwargs["filing_lag_fn"] = _counting_filing_lag
    kwargs["build_raw_metrics_fn"] = _counting_build_raw_metrics

    result = run_per_ticker_loop(**kwargs)

    # _filing_lag is called twice per non-None-snapshot ticker (once for the
    # ensemble's filing_lag_days_value, once for the issue #67 dual RIM count).
    assert lag_calls["n"] == 2
    # _build_raw_metrics is called once per ticker (StockDetail.raw_metrics).
    assert raw_metrics_calls["n"] == 1
    assert len(result.summaries) == 1


def test_E7_empty_universe_returns_empty_result_no_exception(tmp_path, monkeypatch):
    """Zero-row df -> PerTickerLoopResult with empty summaries/all_details
    and every counter at its zero/empty init value. No exception, no
    KeyError on the direct beneish_results[ticker] / dechow_results[ticker]
    indexing (loop body never executes)."""
    df = _make_df([])
    kwargs = _run_loop_kwargs(
        df=df, snapshots={}, tickers=[], tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    result = run_per_ticker_loop(**kwargs)

    assert result.summaries == []
    assert result.all_details == []
    assert result.fundamentals_unavailable_count == 0
    assert result.low_liquidity_annotate_count == 0
    assert result.multi_class_aggregate_shares_suspected_count == 0
    assert result.cross_source_delta_by_ticker == {}
    assert result.cross_source_wall_clock_seconds is not None
