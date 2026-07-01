"""Unit tests for compute.orchestrator.tier2 (PR #259-R5).

All tests are offline/synthetic: ``compute.orchestrator.tier2.fetch_tier2_for_ticker``
is monkeypatched (or a stub used directly) so no network calls occur.

This module is a simpler extraction than R4's Form-4 loop — no inner
module-scope helper worker (the per-ticker work is a single call straight
to ``fetch_tier2_for_ticker`` imported from ``compute.scoring.tier2``), no
env-var SKIP path, and no auxiliary counter (just the results dict + the
wall-clock float). ``fetch_all_tier2`` returns a 2-tuple:
``(tier2_results, tier2_wall_clock_seconds)``.

Coverage
--------
A — ``fetch_all_tier2`` happy path
    A1  Returns a 2-tuple.
    A2  tier2_results is keyed by ticker and holds the returned Tier2Result
        objects unchanged.
    A3  tier2_wall_clock_seconds is a non-negative float (not None) on the
        happy path.
    A4  Every requested ticker appears in tier2_results when the fetch
        succeeds for all of them.

B — ``fetch_all_tier2`` per-ticker failure handling
    B1  A future that raises (fut.result() raising inside the inner
        try/except) is caught + warned + skipped — that ticker does NOT
        appear in tier2_results, but tier2_wall_clock_seconds is still
        populated and OTHER tickers are still collected normally.
    B2  The skip does not raise out of fetch_all_tier2.
    B3  A per-ticker raise logs a WARNING containing "Tier-2 task raised".

C — ``fetch_all_tier2`` outer-except path
    C1  When df.iterrows() raises (interpreter-level failure before the
        executor block completes), tier2_results is the empty dict (no
        entries were ever populated) and tier2_wall_clock_seconds is None.
    C2  outer-except logs a WARNING containing "failed entirely".

D — max_workers plumbing
    D1  max_workers defaults to config.EDGAR_MAX_WORKERS when not passed.
    D2  A custom max_workers is honoured (ThreadPoolExecutor constructed
        with the passed value) — verified via a spy on ThreadPoolExecutor.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pandas as pd

import compute.orchestrator.tier2 as tier2_mod
from compute import config
from compute.orchestrator.tier2 import fetch_all_tier2
from compute.scoring.eight_k_events import ItemFlag
from compute.scoring.tier2 import Tier2Result

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_df(*tickers: str) -> pd.DataFrame:
    """Return a minimal universe DataFrame with the given tickers."""
    return pd.DataFrame([{"ticker": t} for t in tickers])


_EMPTY_ITEM_FLAG = ItemFlag(
    fired=False, filing_date=None, filing_url=None, raw_item_text=None
)


def _make_tier2_result(
    *,
    going_concern: bool = False,
    fetch_succeeded: bool = True,
) -> Tier2Result:
    """Return a minimal synthetic Tier2Result, matching the fixture shape
    used elsewhere in the test suite (tests/test_main.py::_MINIMAL_TIER2_STEP4,
    tests/test_output/test_wall_clock_schema.py::_MINIMAL_TIER2)."""
    return Tier2Result(
        going_concern_disclosure=going_concern,
        non_reliance_flag=_EMPTY_ITEM_FLAG,
        auditor_change_flag=_EMPTY_ITEM_FLAG,
        fetch_succeeded=fetch_succeeded,
    )


# ---------------------------------------------------------------------------
# Section A: fetch_all_tier2 happy path
# ---------------------------------------------------------------------------


def test_A1_returns_two_tuple(monkeypatch):
    """fetch_all_tier2 returns a 2-tuple."""
    monkeypatch.setattr(
        tier2_mod, "fetch_tier2_for_ticker", lambda ticker: _make_tier2_result()
    )
    result = fetch_all_tier2(_make_df("AAPL", "MSFT"))

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_A2_results_keyed_by_ticker_holds_result_unchanged(monkeypatch):
    """tier2_results is keyed by ticker and holds the Tier2Result object
    returned by fetch_tier2_for_ticker, unaltered."""
    aapl_result = _make_tier2_result(going_concern=True)
    msft_result = _make_tier2_result(going_concern=False)

    def fake_fetch(ticker):
        return aapl_result if ticker == "AAPL" else msft_result

    monkeypatch.setattr(tier2_mod, "fetch_tier2_for_ticker", fake_fetch)
    results, _ = fetch_all_tier2(_make_df("AAPL", "MSFT"))

    assert results["AAPL"] is aapl_result
    assert results["MSFT"] is msft_result
    assert results["AAPL"].going_concern_disclosure is True
    assert results["MSFT"].going_concern_disclosure is False


def test_A3_wall_clock_is_nonnegative_float_on_happy_path(monkeypatch):
    """tier2_wall_clock_seconds is a float (not None) on the happy path."""
    monkeypatch.setattr(
        tier2_mod, "fetch_tier2_for_ticker", lambda ticker: _make_tier2_result()
    )
    _, wc = fetch_all_tier2(_make_df("AAPL"))

    assert isinstance(wc, float)
    assert wc >= 0.0


def test_A4_all_tickers_present_when_all_succeed(monkeypatch):
    """Every requested ticker appears in tier2_results when the fetch
    succeeds for all of them."""
    monkeypatch.setattr(
        tier2_mod, "fetch_tier2_for_ticker", lambda ticker: _make_tier2_result()
    )
    results, _ = fetch_all_tier2(_make_df("AAPL", "MSFT", "GOOG"))

    assert set(results.keys()) == {"AAPL", "MSFT", "GOOG"}


# ---------------------------------------------------------------------------
# Section B: fetch_all_tier2 per-ticker failure handling
# ---------------------------------------------------------------------------


def test_B1_raising_ticker_skipped_others_still_collected(monkeypatch):
    """A ticker whose fetch_tier2_for_ticker raises is skipped (does not
    appear in tier2_results); the wall-clock is still populated and other
    tickers are still collected normally."""

    def fake_fetch(ticker):
        if ticker == "CRASH":
            raise RuntimeError("simulated EDGAR failure")
        return _make_tier2_result()

    monkeypatch.setattr(tier2_mod, "fetch_tier2_for_ticker", fake_fetch)
    results, wc = fetch_all_tier2(_make_df("GOOD", "CRASH"))

    assert "CRASH" not in results
    assert "GOOD" in results
    assert isinstance(wc, float)
    assert wc >= 0.0


def test_B2_per_ticker_raise_does_not_propagate(monkeypatch):
    """A per-ticker raise inside the executor must not propagate out of
    fetch_all_tier2 — the outer function call itself must not raise."""

    def boom(ticker):
        raise RuntimeError("simulated future raise")

    monkeypatch.setattr(tier2_mod, "fetch_tier2_for_ticker", boom)

    # Must not raise:
    results, wc = fetch_all_tier2(_make_df("CRASH"))

    assert results == {}
    assert isinstance(wc, float)


def test_B3_per_ticker_raise_logs_warning(monkeypatch, caplog):
    """A per-ticker raise logs a WARNING containing 'Tier-2 task raised'."""

    def boom(ticker):
        raise RuntimeError("simulated future raise")

    monkeypatch.setattr(tier2_mod, "fetch_tier2_for_ticker", boom)

    with caplog.at_level(logging.WARNING, logger="compute.orchestrator.tier2"):
        fetch_all_tier2(_make_df("CRASH"))

    assert any("Tier-2 task raised" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Section C: fetch_all_tier2 outer-except path
# ---------------------------------------------------------------------------


def test_C1_outer_except_leaves_empty_results_and_none_wall_clock(monkeypatch):
    """When df.iterrows() raises (interpreter-level failure before the
    executor block completes), tier2_results is empty and
    tier2_wall_clock_seconds is None.

    Note: the initial ``logger.info(..., len(df))`` call sits OUTSIDE the
    try block (matches the original inline block byte-for-byte), so the
    stub must support ``len()`` while still raising from ``iterrows()``.
    """

    class _BadDF:
        """Minimal DataFrame-like that supports len() but whose
        iterrows() raises."""

        def __len__(self):
            return 1

        def iterrows(self):
            raise RuntimeError("disk full")

    results, wc = fetch_all_tier2(_BadDF())  # type: ignore[arg-type]

    assert results == {}
    assert wc is None


def test_C2_outer_except_logs_warning(monkeypatch, caplog):
    """outer-except path logs a WARNING containing 'failed entirely'."""

    class _BadDF:
        def __len__(self):
            return 1

        def iterrows(self):
            raise RuntimeError("simulated outer failure")

    with caplog.at_level(logging.WARNING, logger="compute.orchestrator.tier2"):
        fetch_all_tier2(_BadDF())  # type: ignore[arg-type]

    assert any("failed entirely" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Section D: max_workers plumbing
# ---------------------------------------------------------------------------


def test_D1_max_workers_defaults_to_config_edgar_max_workers(monkeypatch):
    """max_workers defaults to config.EDGAR_MAX_WORKERS when the caller
    does not pass an explicit value — verified via a spy on
    ThreadPoolExecutor's constructor args."""
    captured_kwargs: list[dict] = []
    real_executor_cls = tier2_mod.ThreadPoolExecutor

    class _SpyExecutor(real_executor_cls):
        def __init__(self, *args, **kwargs):
            captured_kwargs.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        tier2_mod, "fetch_tier2_for_ticker", lambda ticker: _make_tier2_result()
    )
    with patch.object(tier2_mod, "ThreadPoolExecutor", _SpyExecutor):
        fetch_all_tier2(_make_df("AAPL"))

    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["max_workers"] == config.EDGAR_MAX_WORKERS


def test_D2_custom_max_workers_is_honoured(monkeypatch):
    """A custom max_workers value passed by the caller reaches
    ThreadPoolExecutor unchanged."""
    captured_kwargs: list[dict] = []
    real_executor_cls = tier2_mod.ThreadPoolExecutor

    class _SpyExecutor(real_executor_cls):
        def __init__(self, *args, **kwargs):
            captured_kwargs.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        tier2_mod, "fetch_tier2_for_ticker", lambda ticker: _make_tier2_result()
    )
    with patch.object(tier2_mod, "ThreadPoolExecutor", _SpyExecutor):
        fetch_all_tier2(_make_df("AAPL"), max_workers=3)

    assert captured_kwargs[0]["max_workers"] == 3
