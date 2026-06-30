"""Unit tests for compute.orchestrator.fundamentals (PR #259-R3).

All tests are offline/synthetic: ``compute.orchestrator.fundamentals._fundamentals_one``
and ``compute.orchestrator.fundamentals.fetch_fundamentals`` are monkeypatched
so no network calls occur.

Coverage
--------
A — ``_fundamentals_one``
    A1  Happy path returns (snapshot, elapsed>=0) 2-tuple.
    A2  Exception in fetch_fundamentals → (None, elapsed>=0); never raises.
    A3  Returns the exact snapshot object from fetch_fundamentals on success.

B — ``fetch_all_fundamentals`` happy-path aggregation
    B1  Returns (snapshots, fundamentals_latency) 2-tuple for 2 tickers.
    B2  snapshots is keyed by ticker with the snapshot as value.
    B3  fundamentals_latency is keyed by ticker with a float elapsed value.
    B4  A None snapshot is preserved in the dict (graceful degrade path).

C — ``fetch_all_fundamentals`` timeout handling
    C1  concurrent.futures.TimeoutError → snap=None, elapsed=float(timeout).
    C2  TimeoutError logs a warning containing the ticker name.
    C3  TimeoutError for one ticker does not prevent other tickers collecting.

D — ``fetch_all_fundamentals`` exception handling
    D1  A task raising a generic Exception → snap=None, elapsed=0.0.
    D2  Exception for one ticker does not prevent other tickers collecting.
    D3  Exception logs a warning containing the ticker name.
    D4  All tickers failing → empty snapshots/latency dicts (no crash).
"""

from __future__ import annotations

import concurrent.futures
import logging
from unittest.mock import patch

import pandas as pd
import pytest

import compute.orchestrator.fundamentals as fund_mod
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.orchestrator.fundamentals import _fundamentals_one, fetch_all_fundamentals

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_snapshot(ticker: str = "TST") -> FundamentalsSnapshot:
    """Return a minimal FundamentalsSnapshot for offline tests.

    Uses only fields declared on FundamentalsSnapshot (mirroring the
    ``_snap`` helper in ``tests/test_main.py``).
    """
    return FundamentalsSnapshot(
        ticker=ticker,
        cik="0000000001",
        net_income=50.0,
        stockholders_equity=100.0,
        shares_outstanding=10.0,
        eps_diluted=5.0,
        ebitda=50.0,
        long_term_debt=20.0,
        short_term_debt=5.0,
        cash=10.0,
        goodwill=0.0,
        intangibles_net=0.0,
    )


def _make_df(*tickers: str) -> pd.DataFrame:
    """Return a minimal universe DataFrame with the given tickers."""
    rows = [
        {
            "ticker": t,
            "cik": f"000{i:07d}",
        }
        for i, t in enumerate(tickers, start=1)
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Section A: _fundamentals_one
# ---------------------------------------------------------------------------


def test_A1_happy_path_returns_tuple(monkeypatch):
    """_fundamentals_one returns (snapshot, elapsed>=0.0) on success."""
    snap = _make_snapshot()
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda ticker, cik: snap)

    result_snap, elapsed = _fundamentals_one("TST", "0000000001")

    assert result_snap is snap
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_A2_exception_returns_none_and_elapsed(monkeypatch):
    """Exception in fetch_fundamentals → (None, elapsed>=0); never raises."""
    def boom(ticker, cik):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(fund_mod, "fetch_fundamentals", boom)

    result_snap, elapsed = _fundamentals_one("TST", "0000000001")

    assert result_snap is None
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_A3_returns_exact_snapshot_object(monkeypatch):
    """The snapshot object returned by fetch_fundamentals is propagated unchanged."""
    sentinel = _make_snapshot("SENTINEL")
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t, c: sentinel)

    result_snap, _ = _fundamentals_one("SENTINEL", "0000000001")

    assert result_snap is sentinel


# ---------------------------------------------------------------------------
# Section B: fetch_all_fundamentals happy-path aggregation
# ---------------------------------------------------------------------------


def test_B1_returns_two_tuple_for_two_tickers(monkeypatch):
    """fetch_all_fundamentals returns (snapshots, fundamentals_latency) for 2 tickers."""
    snap = _make_snapshot()
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t, c: snap)

    df = _make_df("AAPL", "MSFT")
    result = fetch_all_fundamentals(df, max_workers=2)

    assert isinstance(result, tuple)
    assert len(result) == 2
    snapshots, latency = result
    assert isinstance(snapshots, dict)
    assert isinstance(latency, dict)


def test_B2_snapshots_keyed_by_ticker(monkeypatch):
    """snapshots dict is keyed by ticker with the FundamentalsSnapshot as value."""
    snap = _make_snapshot()
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t, c: snap)

    df = _make_df("AAPL", "MSFT")
    snapshots, _ = fetch_all_fundamentals(df, max_workers=2)

    assert "AAPL" in snapshots
    assert "MSFT" in snapshots
    assert snapshots["AAPL"] is snap
    assert snapshots["MSFT"] is snap


def test_B3_latency_keyed_by_ticker_with_float(monkeypatch):
    """fundamentals_latency dict is keyed by ticker with a float elapsed value."""
    snap = _make_snapshot()
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t, c: snap)

    df = _make_df("AAPL", "MSFT")
    _, latency = fetch_all_fundamentals(df, max_workers=2)

    assert "AAPL" in latency
    assert "MSFT" in latency
    assert isinstance(latency["AAPL"], float)
    assert isinstance(latency["MSFT"], float)
    assert latency["AAPL"] >= 0.0
    assert latency["MSFT"] >= 0.0


def test_B4_none_snapshot_preserved_in_dict(monkeypatch):
    """A None result from _fundamentals_one is preserved in snapshots dict."""
    # Patch _fundamentals_one directly to return None snapshot
    with patch.object(fund_mod, "_fundamentals_one", return_value=(None, 1.23)):
        df = _make_df("FAIL")
        snapshots, latency = fetch_all_fundamentals(df, max_workers=1)

    assert "FAIL" in snapshots
    assert snapshots["FAIL"] is None
    assert latency["FAIL"] == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# Section C: fetch_all_fundamentals timeout handling
# ---------------------------------------------------------------------------


def test_C1_timeout_error_yields_none_snap_and_float_timeout(monkeypatch):
    """concurrent.futures.TimeoutError → snap=None, elapsed=float(timeout)."""
    timeout_val = 45

    def raise_timeout(ticker, cik):
        raise concurrent.futures.TimeoutError()

    # Patch _fundamentals_one so it raises TimeoutError inside the future.
    # We need the future itself to raise TimeoutError on .result() — we do this
    # by patching _fundamentals_one at the module level so the submitted callable
    # raises before returning. The ThreadPoolExecutor propagates the exception
    # to fut.result(), triggering the TimeoutError arm only when we call
    # fut.result(timeout=...) and the future raises TimeoutError.
    #
    # A cleaner approach: patch the future's .result() directly via a custom
    # _fundamentals_one that makes fut.result() raise TimeoutError. We achieve
    # this by injecting a side_effect on _fundamentals_one that raises
    # concurrent.futures.TimeoutError (which is what fut.result(timeout=T)
    # raises when T expires, but here we simulate it synchronously via a
    # thread-raised TimeoutError that fetch_all_fundamentals catches in its
    # except concurrent.futures.TimeoutError arm).
    with patch.object(fund_mod, "_fundamentals_one", side_effect=raise_timeout):
        df = _make_df("SLOW")
        snapshots, latency = fetch_all_fundamentals(df, max_workers=1, timeout=timeout_val)

    assert "SLOW" in snapshots
    assert snapshots["SLOW"] is None
    assert latency["SLOW"] == pytest.approx(float(timeout_val))


def test_C2_timeout_logs_warning(monkeypatch, caplog):
    """TimeoutError logs a warning containing the ticker name."""
    timeout_val = 30

    with patch.object(
        fund_mod,
        "_fundamentals_one",
        side_effect=concurrent.futures.TimeoutError(),
    ):
        with caplog.at_level(logging.WARNING, logger="compute.orchestrator.fundamentals"):
            df = _make_df("SLOW")
            fetch_all_fundamentals(df, max_workers=1, timeout=timeout_val)

    assert any(
        "SLOW" in r.message and "timed out" in r.message.lower()
        for r in caplog.records
    )


def test_C3_timeout_for_one_ticker_does_not_block_others(monkeypatch):
    """TimeoutError for SLOW does not prevent GOOD ticker from being collected."""
    good_snap = _make_snapshot("GOOD")

    def side_effect(ticker, cik):
        if ticker == "SLOW":
            raise concurrent.futures.TimeoutError()
        return good_snap, 0.1

    with patch.object(fund_mod, "_fundamentals_one", side_effect=side_effect):
        df = _make_df("GOOD", "SLOW")
        snapshots, latency = fetch_all_fundamentals(df, max_workers=2, timeout=45)

    assert "GOOD" in snapshots
    assert snapshots["GOOD"] is good_snap
    assert "SLOW" in snapshots
    assert snapshots["SLOW"] is None


# ---------------------------------------------------------------------------
# Section D: fetch_all_fundamentals exception handling
# ---------------------------------------------------------------------------


def test_D1_generic_exception_yields_none_snap_and_zero_elapsed(monkeypatch):
    """A task raising a generic Exception → snap=None, elapsed=0.0."""
    with patch.object(
        fund_mod,
        "_fundamentals_one",
        side_effect=RuntimeError("synthetic"),
    ):
        df = _make_df("FAIL")
        snapshots, latency = fetch_all_fundamentals(df, max_workers=1)

    assert "FAIL" in snapshots
    assert snapshots["FAIL"] is None
    assert latency["FAIL"] == pytest.approx(0.0)


def test_D2_exception_for_one_ticker_does_not_block_others(monkeypatch):
    """Exception for FAIL does not prevent GOOD ticker from being collected."""
    good_snap = _make_snapshot("GOOD")

    def side_effect(ticker, cik):
        if ticker == "FAIL":
            raise RuntimeError("simulated failure")
        return good_snap, 0.5

    with patch.object(fund_mod, "_fundamentals_one", side_effect=side_effect):
        df = _make_df("GOOD", "FAIL")
        snapshots, latency = fetch_all_fundamentals(df, max_workers=2)

    assert "GOOD" in snapshots
    assert snapshots["GOOD"] is good_snap
    assert latency["GOOD"] == pytest.approx(0.5)
    assert "FAIL" in snapshots
    assert snapshots["FAIL"] is None


def test_D3_exception_logs_warning(monkeypatch, caplog):
    """Exception logs a warning containing the ticker name."""
    with patch.object(
        fund_mod,
        "_fundamentals_one",
        side_effect=RuntimeError("boom"),
    ):
        with caplog.at_level(logging.WARNING, logger="compute.orchestrator.fundamentals"):
            df = _make_df("FAIL")
            fetch_all_fundamentals(df, max_workers=1)

    assert any(
        "FAIL" in r.message
        for r in caplog.records
    )


def test_D4_all_tickers_failing_returns_populated_dicts_with_none_snaps(monkeypatch):
    """When every ticker raises, snapshots has None values and latency has 0.0 values."""
    with patch.object(
        fund_mod,
        "_fundamentals_one",
        side_effect=RuntimeError("all fail"),
    ):
        df = _make_df("BAD1", "BAD2", "BAD3")
        snapshots, latency = fetch_all_fundamentals(df, max_workers=2)

    # All three are present with None snapshot and 0.0 latency (generic exc arm).
    assert set(snapshots.keys()) == {"BAD1", "BAD2", "BAD3"}
    assert all(v is None for v in snapshots.values())
    assert set(latency.keys()) == {"BAD1", "BAD2", "BAD3"}
    assert all(v == pytest.approx(0.0) for v in latency.values())
