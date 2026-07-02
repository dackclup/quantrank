"""Unit tests for compute.orchestrator.history (Phase 9.3 precache-split
prerequisite extraction).

All tests are offline/synthetic: ``compute.orchestrator.history._history_one``
and ``compute.orchestrator.history.fetch_fundamentals_history`` are
monkeypatched so no network calls occur.

This module mirrors ``tests/test_orchestrator/test_fundamentals.py``
section-for-section (the R3 precedent this extraction was told to match
exactly), adapted for ``fetch_all_history``'s single-dict return shape
(vs. ``fetch_all_fundamentals``'s 2-tuple).

Coverage
--------
A — ``_history_one``
    A1  Happy path returns (history_df, elapsed>=0) 2-tuple.
    A2  Missing CIK ("") → (empty DataFrame, 0.0) without calling the fetcher.
    A3  Exception in fetch_fundamentals_history → (empty DataFrame, elapsed>=0);
        never raises.
    A4  Returns the exact DataFrame object from fetch_fundamentals_history
        on success.

B — ``fetch_all_history`` happy-path aggregation
    B1  Returns a plain dict (not a tuple) for 2 tickers.
    B2  histories is keyed by ticker with the DataFrame as value.
    B3  Every row of the input df gets an entry — no ticker silently
        dropped on success.
    B4  An empty-DataFrame result from ``_history_one`` is preserved in the
        dict (graceful-degrade path — missing CIK / failed fetch).

C — ``fetch_all_history`` timeout handling
    C1  concurrent.futures.TimeoutError → histories[ticker] is an empty
        DataFrame.
    C2  TimeoutError logs a warning containing the ticker name.
    C3  TimeoutError for one ticker does not prevent other tickers
        collecting.

D — ``fetch_all_history`` exception handling
    D1  A task raising a generic Exception → histories[ticker] is an empty
        DataFrame.
    D2  Exception for one ticker does not prevent other tickers collecting.
    D3  Exception logs a warning containing the ticker name.
    D4  All tickers failing → populated dict of empty DataFrames (no crash).

E — Behaviour-preservation regression guards (Phase 9.3 extraction)
    E1  ``compute.main`` no longer defines ``_history_one`` (fully moved,
        not duplicated).
    E2  ``compute.main`` no longer imports ``fetch_fundamentals_history``
        directly (the only caller — ``_history_one`` — moved with it).
    E3  ``fetch_all_history``'s default ``timeout`` (45) matches
        ``compute.main._FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS`` — the value
        the extraction's sole caller passes explicitly; a silent default
        drift here would NOT be caught by the byte-identical-call-site
        assertion alone since the caller always passes timeout explicitly,
        so this pins the numeric constant independently.
    E4  ``fetch_all_history`` and ``fetch_all_fundamentals`` default to the
        SAME ``max_workers`` (``config.EDGAR_MAX_WORKERS``) — both loops
        share the EDGAR 10 req/s ceiling.
"""

from __future__ import annotations

import concurrent.futures
import logging
from unittest.mock import patch

import pandas as pd

import compute.orchestrator.history as history_mod
from compute.orchestrator.history import _history_one, fetch_all_history

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_history_df(*, fiscal_year: int = 2025) -> pd.DataFrame:
    """Return a minimal non-empty annual-history DataFrame for offline tests."""
    return pd.DataFrame(
        [
            {"metric": "net_income", "fiscal_year": fiscal_year, "value": 100.0},
            {"metric": "revenue", "fiscal_year": fiscal_year, "value": 500.0},
        ]
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
# Section A: _history_one
# ---------------------------------------------------------------------------


def test_A1_happy_path_returns_tuple(monkeypatch):
    """_history_one returns (history_df, elapsed>=0.0) on success."""
    hist = _make_history_df()
    monkeypatch.setattr(history_mod, "fetch_fundamentals_history", lambda cik: hist)

    result_df, elapsed = _history_one("TST", "0000000001")

    assert result_df is hist
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_A2_missing_cik_returns_empty_zero_elapsed_without_calling_fetcher(
    monkeypatch,
):
    """No CIK ('') → empty DataFrame + zero elapsed; fetcher never called."""
    called = []
    monkeypatch.setattr(
        history_mod, "fetch_fundamentals_history", lambda cik: called.append(cik)
    )

    df, elapsed = _history_one("TST", "")

    assert df.empty
    assert elapsed == 0.0
    assert called == [], "fetch_fundamentals_history must not be called for a missing CIK"


def test_A3_exception_returns_empty_df_and_elapsed(monkeypatch):
    """Exception in fetch_fundamentals_history → (empty DataFrame, elapsed>=0); never raises."""

    def boom(cik):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(history_mod, "fetch_fundamentals_history", boom)

    result_df, elapsed = _history_one("TST", "0000000001")

    assert result_df.empty
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_A4_returns_exact_dataframe_object(monkeypatch):
    """The DataFrame object returned by fetch_fundamentals_history is propagated unchanged."""
    sentinel = _make_history_df(fiscal_year=1999)
    monkeypatch.setattr(history_mod, "fetch_fundamentals_history", lambda cik: sentinel)

    result_df, _ = _history_one("SENTINEL", "0000000001")

    assert result_df is sentinel


# ---------------------------------------------------------------------------
# Section B: fetch_all_history happy-path aggregation
# ---------------------------------------------------------------------------


def test_B1_returns_plain_dict_not_tuple(monkeypatch):
    """fetch_all_history returns a plain dict (not a 2-tuple like fetch_all_fundamentals)."""
    hist = _make_history_df()
    monkeypatch.setattr(history_mod, "fetch_fundamentals_history", lambda cik: hist)

    df = _make_df("AAPL", "MSFT")
    result = fetch_all_history(df, max_workers=2)

    assert isinstance(result, dict)
    assert not isinstance(result, tuple)


def test_B2_histories_keyed_by_ticker(monkeypatch):
    """histories dict is keyed by ticker with the history DataFrame as value."""
    hist = _make_history_df()
    monkeypatch.setattr(history_mod, "fetch_fundamentals_history", lambda cik: hist)

    df = _make_df("AAPL", "MSFT")
    histories = fetch_all_history(df, max_workers=2)

    assert "AAPL" in histories
    assert "MSFT" in histories
    assert histories["AAPL"] is hist
    assert histories["MSFT"] is hist


def test_B3_every_row_gets_an_entry(monkeypatch):
    """Every row of the input df gets a histories entry — no ticker silently dropped."""
    hist = _make_history_df()
    monkeypatch.setattr(history_mod, "fetch_fundamentals_history", lambda cik: hist)

    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    df = _make_df(*tickers)
    histories = fetch_all_history(df, max_workers=2)

    assert set(histories.keys()) == set(tickers)


def test_B4_empty_dataframe_result_preserved_in_dict(monkeypatch):
    """An empty-DataFrame result from _history_one is preserved in histories dict."""
    with patch.object(
        history_mod, "_history_one", return_value=(pd.DataFrame(), 0.0)
    ):
        df = _make_df("NOCIK")
        histories = fetch_all_history(df, max_workers=1)

    assert "NOCIK" in histories
    assert histories["NOCIK"].empty


# ---------------------------------------------------------------------------
# Section C: fetch_all_history timeout handling
# ---------------------------------------------------------------------------


def test_C1_timeout_error_yields_empty_dataframe(monkeypatch):
    """concurrent.futures.TimeoutError → histories[ticker] is an empty DataFrame."""
    timeout_val = 45

    def raise_timeout(ticker, cik):
        raise concurrent.futures.TimeoutError()

    with patch.object(history_mod, "_history_one", side_effect=raise_timeout):
        df = _make_df("SLOW")
        histories = fetch_all_history(df, max_workers=1, timeout=timeout_val)

    assert "SLOW" in histories
    assert isinstance(histories["SLOW"], pd.DataFrame)
    assert histories["SLOW"].empty


def test_C2_timeout_logs_warning(monkeypatch, caplog):
    """TimeoutError logs a warning containing the ticker name."""
    timeout_val = 30

    with patch.object(
        history_mod,
        "_history_one",
        side_effect=concurrent.futures.TimeoutError(),
    ):
        with caplog.at_level(logging.WARNING, logger="compute.orchestrator.history"):
            df = _make_df("SLOW")
            fetch_all_history(df, max_workers=1, timeout=timeout_val)

    assert any(
        "SLOW" in r.message and "timed out" in r.message.lower() for r in caplog.records
    )


def test_C3_timeout_for_one_ticker_does_not_block_others(monkeypatch):
    """TimeoutError for SLOW does not prevent GOOD ticker from being collected."""
    good_hist = _make_history_df()

    def side_effect(ticker, cik):
        if ticker == "SLOW":
            raise concurrent.futures.TimeoutError()
        return good_hist, 0.1

    with patch.object(history_mod, "_history_one", side_effect=side_effect):
        df = _make_df("GOOD", "SLOW")
        histories = fetch_all_history(df, max_workers=2, timeout=45)

    assert histories["GOOD"] is good_hist
    assert histories["SLOW"].empty


# ---------------------------------------------------------------------------
# Section D: fetch_all_history exception handling
# ---------------------------------------------------------------------------


def test_D1_generic_exception_yields_empty_dataframe(monkeypatch):
    """A task raising a generic Exception → histories[ticker] is an empty DataFrame."""
    with patch.object(
        history_mod,
        "_history_one",
        side_effect=RuntimeError("synthetic"),
    ):
        df = _make_df("FAIL")
        histories = fetch_all_history(df, max_workers=1)

    assert "FAIL" in histories
    assert histories["FAIL"].empty


def test_D2_exception_for_one_ticker_does_not_block_others(monkeypatch):
    """Exception for FAIL does not prevent GOOD ticker from being collected."""
    good_hist = _make_history_df()

    def side_effect(ticker, cik):
        if ticker == "FAIL":
            raise RuntimeError("simulated failure")
        return good_hist, 0.5

    with patch.object(history_mod, "_history_one", side_effect=side_effect):
        df = _make_df("GOOD", "FAIL")
        histories = fetch_all_history(df, max_workers=2)

    assert histories["GOOD"] is good_hist
    assert histories["FAIL"].empty


def test_D3_exception_logs_warning(monkeypatch, caplog):
    """Exception logs a warning containing the ticker name."""
    with patch.object(
        history_mod,
        "_history_one",
        side_effect=RuntimeError("boom"),
    ):
        with caplog.at_level(logging.WARNING, logger="compute.orchestrator.history"):
            df = _make_df("FAIL")
            fetch_all_history(df, max_workers=1)

    assert any("FAIL" in r.message for r in caplog.records)


def test_D4_all_tickers_failing_returns_populated_dict_of_empty_frames(monkeypatch):
    """When every ticker raises, histories has an empty DataFrame for each."""
    with patch.object(
        history_mod,
        "_history_one",
        side_effect=RuntimeError("all fail"),
    ):
        df = _make_df("BAD1", "BAD2", "BAD3")
        histories = fetch_all_history(df, max_workers=2)

    assert set(histories.keys()) == {"BAD1", "BAD2", "BAD3"}
    assert all(v.empty for v in histories.values())


# ---------------------------------------------------------------------------
# Section E: behaviour-preservation regression guards (Phase 9.3 extraction)
# ---------------------------------------------------------------------------


def test_E1_history_one_fully_removed_from_compute_main():
    """compute.main no longer defines _history_one — it was MOVED, not copied.

    Locks the extraction: a future edit that re-adds an inline
    ``_history_one`` to ``compute.main`` (e.g. a bad merge) would silently
    reintroduce the un-independently-callable Step-3 loop this PR exists to
    eliminate. If this test ever needs updating because ``compute.main``
    legitimately needs its own local helper of that name again, that is a
    deliberate design change, not an accidental regression.
    """
    import compute.main as main_mod

    assert not hasattr(main_mod, "_history_one"), (
        "_history_one must live ONLY in compute.orchestrator.history after "
        "the Phase 9.3 precache-split extraction — found a definition on "
        "compute.main too."
    )


def test_E2_fetch_fundamentals_history_no_longer_imported_by_compute_main():
    """compute.main no longer imports fetch_fundamentals_history directly.

    Its only caller (_history_one) moved to compute.orchestrator.history;
    compute.main now reaches annual history exclusively through
    fetch_all_history.
    """
    import compute.main as main_mod

    assert not hasattr(main_mod, "fetch_fundamentals_history"), (
        "compute.main should no longer import fetch_fundamentals_history "
        "directly — Step 3 now goes through "
        "compute.orchestrator.history.fetch_all_history exclusively."
    )


def test_E3_default_timeout_matches_compute_main_constant():
    """fetch_all_history's default timeout (45) matches
    compute.main._FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS — the value the sole
    call site passes explicitly today. Pinning this independently means a
    future refactor that (accidentally) drops the explicit
    ``timeout=...`` kwarg at the call site still gets the correct value,
    rather than silently falling back to a drifted default.
    """
    import inspect

    import compute.main as main_mod

    sig = inspect.signature(fetch_all_history)
    assert sig.parameters["timeout"].default == main_mod._FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS


def test_E4_max_workers_default_matches_fundamentals_sibling():
    """fetch_all_history and fetch_all_fundamentals share the same
    max_workers default (config.EDGAR_MAX_WORKERS) — both loops are bound
    by the same EDGAR 10 req/s ceiling.
    """
    import inspect

    from compute import config
    from compute.orchestrator.fundamentals import fetch_all_fundamentals

    history_sig = inspect.signature(fetch_all_history)
    fundamentals_sig = inspect.signature(fetch_all_fundamentals)

    assert history_sig.parameters["max_workers"].default == config.EDGAR_MAX_WORKERS
    assert (
        history_sig.parameters["max_workers"].default
        == fundamentals_sig.parameters["max_workers"].default
    )
