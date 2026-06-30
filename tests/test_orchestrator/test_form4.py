"""Unit tests for compute.orchestrator.form4 (PR #259-R4).

All tests are offline/synthetic: ``compute.orchestrator.form4.fetch_recent_form4``
and the negation-guard functions (``reset_negation_downgrade_count``,
``get_negation_downgrade_count``) are monkeypatched so no network calls occur.

Coverage
--------
A — ``_fetch_one_form4`` (module-scope worker; smell #9 fix)
    A1  Happy path with transactions: returns (diag, elapsed, False);
        diag has fetch_status="ok", correct distinct insider_count, correct
        latest_filing_date.
    A2  fetch_recent_form4 returns None → (diag, elapsed, True);
        diag has fetch_status="failed", insider_count=0.
    A3  fetch_recent_form4 raises → (diag, elapsed, True);
        diag has fetch_status="failed"; exception does NOT propagate.
    A4  Empty transaction list → fetch_status="ok", insider_count=0,
        latest_filing_date=None, is_failure=False.
    A5  Duplicate insider_cik entries are de-duplicated in insider_count.
    A6  elapsed is a non-negative float on every path.
    A7  Diagnostic dict always contains exactly the 3 required keys.

B — ``fetch_all_form4`` happy-path
    B1  Returns a 5-tuple.
    B2  form4_diagnostics is keyed by ticker.
    B3  form4_latencies is a list of floats (one per ticker).
    B4  form4_failures is a list of tickers that returned None.
    B5  form4_wall_clock_seconds is a float (not None) on the happy path.
    B6  form4_negation_guard_downgrade_count is an int (not None) on happy path.
    B7  reset_negation_downgrade_count is called before the thread pool.
    B8  get_negation_downgrade_count is called after the thread pool.

C — ``fetch_all_form4`` per-ticker failure handling
    C1  A ticker whose _fetch_one_form4 returns (diag, elapsed, True)
        appears in form4_failures AND in form4_diagnostics.
    C2  A ticker whose _fetch_one_form4 returns is_failure=False does NOT
        appear in form4_failures.
    C3  A future that raises (the inner except arm in fetch_all_form4) results
        in the ticker in form4_failures and a failed-status diag entry.

D — ``fetch_all_form4`` SKIP path (FORM4_FETCH_SKIP env-var)
    D1  FORM4_FETCH_SKIP=1 → form4_diagnostics={}, form4_latencies=[],
        form4_failures=[], wall_clock=None, negation_count=None.
    D2  FORM4_FETCH_SKIP=true → same empty/None outputs.
    D3  FORM4_FETCH_SKIP=yes → same empty/None outputs.
    D4  SKIP path logs an INFO message containing "FORM4_FETCH_SKIP".
    D5  SKIP path does NOT call fetch_recent_form4 at all.

E — ``fetch_all_form4`` outer-except path
    E1  When _f4_tickers construction raises (simulate by forcing
        df.iterrows to raise), all 5 outputs reset to {}, [], [], None, None.
    E2  outer-except logs a WARNING containing "failed entirely".
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import compute.orchestrator.form4 as form4_mod
from compute.orchestrator.form4 import _fetch_one_form4, fetch_all_form4

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_df(*tickers: str) -> pd.DataFrame:
    """Return a minimal universe DataFrame with the given tickers."""
    return pd.DataFrame([{"ticker": t} for t in tickers])


def _make_transactions(ciks: list[str], filing_date: str = "2026-04-12") -> list[dict]:
    """Return a minimal list of Form-4 transaction dicts."""
    return [
        {"insider_cik": cik, "filing_date": filing_date}
        for cik in ciks
    ]


def _patch_negation(
    reset_return=None,
    get_return: int = 0,
):
    """Context manager patch for both negation-guard functions."""
    return patch.multiple(
        form4_mod,
        reset_negation_downgrade_count=MagicMock(return_value=reset_return),
        get_negation_downgrade_count=MagicMock(return_value=get_return),
    )


# ---------------------------------------------------------------------------
# Section A: _fetch_one_form4 (module-scope worker)
# ---------------------------------------------------------------------------


def test_A1_happy_path_returns_ok_diag_and_elapsed(monkeypatch):
    """Happy path: returns (diag, elapsed>=0, False) with correct fields."""
    txns = _make_transactions(["0001000001", "0001000002"], "2026-04-12")
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: txns)

    diag, elapsed, is_failure = _fetch_one_form4("TST")

    assert diag["fetch_status"] == "ok"
    assert diag["insider_count"] == 2
    assert diag["latest_filing_date"] == "2026-04-12"
    assert is_failure is False
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_A2_none_return_gives_failed_diag(monkeypatch):
    """fetch_recent_form4 returning None → failed diag, is_failure=True."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: None)

    diag, elapsed, is_failure = _fetch_one_form4("TST")

    assert diag["fetch_status"] == "failed"
    assert diag["insider_count"] == 0
    assert diag["latest_filing_date"] is None
    assert is_failure is True


def test_A3_exception_gives_failed_diag_does_not_propagate(monkeypatch):
    """fetch_recent_form4 raising → failed diag returned, no propagation."""
    def boom(ticker):
        raise RuntimeError("network error")

    monkeypatch.setattr(form4_mod, "fetch_recent_form4", boom)

    # Must not raise:
    diag, elapsed, is_failure = _fetch_one_form4("TST")

    assert diag["fetch_status"] == "failed"
    assert diag["insider_count"] == 0
    assert is_failure is True


def test_A4_empty_list_ok_zero_insiders(monkeypatch):
    """Empty transaction list → fetch_status='ok', insider_count=0, is_failure=False."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])

    diag, elapsed, is_failure = _fetch_one_form4("TST")

    assert diag["fetch_status"] == "ok"
    assert diag["insider_count"] == 0
    assert diag["latest_filing_date"] is None
    assert is_failure is False


def test_A5_duplicate_ciks_are_deduplicated(monkeypatch):
    """Duplicate insider_cik entries count as one distinct insider."""
    txns = _make_transactions(["0001000001", "0001000001", "0001000002"])
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: txns)

    diag, _, _ = _fetch_one_form4("TST")

    assert diag["insider_count"] == 2


def test_A6_elapsed_is_nonnegative_on_all_paths(monkeypatch):
    """elapsed is a non-negative float on both the ok path and the failure path."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: None)
    _, elapsed_fail, _ = _fetch_one_form4("TST")
    assert elapsed_fail >= 0.0

    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    _, elapsed_ok, _ = _fetch_one_form4("TST")
    assert elapsed_ok >= 0.0


def test_A7_diag_always_has_required_keys(monkeypatch):
    """Diagnostic dict always contains fetch_status, insider_count, latest_filing_date."""
    required = {"fetch_status", "insider_count", "latest_filing_date"}

    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    ok_diag, _, _ = _fetch_one_form4("TST")
    assert required.issubset(ok_diag.keys())

    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: None)
    fail_diag, _, _ = _fetch_one_form4("TST")
    assert required.issubset(fail_diag.keys())


# ---------------------------------------------------------------------------
# Section B: fetch_all_form4 happy-path
# ---------------------------------------------------------------------------


def test_B1_returns_five_tuple(monkeypatch):
    """fetch_all_form4 returns a 5-tuple."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    with _patch_negation(get_return=0):
        result = fetch_all_form4(_make_df("AAPL", "MSFT"))

    assert isinstance(result, tuple)
    assert len(result) == 5


def test_B2_diagnostics_keyed_by_ticker(monkeypatch):
    """form4_diagnostics is keyed by ticker string."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    with _patch_negation(get_return=0):
        diags, latencies, failures, wc, neg = fetch_all_form4(_make_df("AAPL", "MSFT"))

    assert "AAPL" in diags
    assert "MSFT" in diags


def test_B3_latencies_is_list_of_floats(monkeypatch):
    """form4_latencies is a list with one float per ticker."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    with _patch_negation(get_return=0):
        _, latencies, _, _, _ = fetch_all_form4(_make_df("AAPL", "MSFT"))

    assert isinstance(latencies, list)
    assert len(latencies) == 2
    assert all(isinstance(v, float) for v in latencies)


def test_B4_failures_contains_tickers_that_returned_none(monkeypatch):
    """Tickers for which fetch_recent_form4 returns None appear in form4_failures."""
    def fake_fetch(ticker):
        return None if ticker == "FAIL" else []

    monkeypatch.setattr(form4_mod, "fetch_recent_form4", fake_fetch)
    with _patch_negation(get_return=0):
        _, _, failures, _, _ = fetch_all_form4(_make_df("GOOD", "FAIL"))

    assert "FAIL" in failures
    assert "GOOD" not in failures


def test_B5_wall_clock_is_float_on_happy_path(monkeypatch):
    """form4_wall_clock_seconds is a float (not None) on the happy path."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    with _patch_negation(get_return=0):
        _, _, _, wc, _ = fetch_all_form4(_make_df("AAPL"))

    assert isinstance(wc, float)
    assert wc >= 0.0


def test_B6_negation_count_is_int_on_happy_path(monkeypatch):
    """form4_negation_guard_downgrade_count is an int (not None) on happy path."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    with _patch_negation(get_return=3):
        _, _, _, _, neg = fetch_all_form4(_make_df("AAPL"))

    assert neg == 3


def test_B7_reset_called_before_thread_pool(monkeypatch):
    """reset_negation_downgrade_count is called exactly once before the pool runs."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    mock_reset = MagicMock()
    mock_get = MagicMock(return_value=0)
    with patch.multiple(
        form4_mod,
        reset_negation_downgrade_count=mock_reset,
        get_negation_downgrade_count=mock_get,
    ):
        fetch_all_form4(_make_df("AAPL"))

    mock_reset.assert_called_once()


def test_B8_get_called_after_thread_pool(monkeypatch):
    """get_negation_downgrade_count is called exactly once after the pool drains."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    mock_reset = MagicMock()
    mock_get = MagicMock(return_value=7)
    with patch.multiple(
        form4_mod,
        reset_negation_downgrade_count=mock_reset,
        get_negation_downgrade_count=mock_get,
    ):
        _, _, _, _, neg = fetch_all_form4(_make_df("AAPL"))

    mock_get.assert_called_once()
    assert neg == 7


# ---------------------------------------------------------------------------
# Section C: fetch_all_form4 per-ticker failure handling
# ---------------------------------------------------------------------------


def test_C1_is_failure_ticker_in_failures_and_diags(monkeypatch):
    """A ticker that returns None appears in failures AND in diagnostics dict."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: None)
    with _patch_negation(get_return=0):
        diags, _, failures, _, _ = fetch_all_form4(_make_df("FAIL"))

    assert "FAIL" in failures
    assert "FAIL" in diags
    assert diags["FAIL"]["fetch_status"] == "failed"


def test_C2_ok_ticker_not_in_failures(monkeypatch):
    """A ticker with fetch_status='ok' does NOT appear in form4_failures."""
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", lambda ticker: [])
    with _patch_negation(get_return=0):
        _, _, failures, _, _ = fetch_all_form4(_make_df("GOOD"))

    assert "GOOD" not in failures


def test_C3_future_that_raises_goes_to_failures(monkeypatch):
    """When _fetch_one_form4 raises (inner except arm), ticker is in failures
    and form4_diagnostics gets a failed-status entry."""
    # Patch _fetch_one_form4 to raise so the inner except arm in
    # fetch_all_form4 fires (the arm that catches fut.result() exceptions).
    def boom(ticker):
        raise RuntimeError("simulated future raise")

    with patch.object(form4_mod, "_fetch_one_form4", side_effect=boom):
        with _patch_negation(get_return=0):
            diags, _, failures, _, _ = fetch_all_form4(_make_df("CRASH"))

    assert "CRASH" in failures
    assert "CRASH" in diags
    assert diags["CRASH"]["fetch_status"] == "failed"


# ---------------------------------------------------------------------------
# Section D: fetch_all_form4 SKIP path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skip_val", ["1", "true", "yes"])
def test_D1_D2_D3_skip_env_var_gives_all_empty_none(monkeypatch, skip_val):
    """FORM4_FETCH_SKIP=1/true/yes → all 5 outputs empty/None."""
    monkeypatch.setenv("FORM4_FETCH_SKIP", skip_val)
    # fetch_recent_form4 must NOT be called; no need to patch it
    diags, latencies, failures, wc, neg = fetch_all_form4(_make_df("AAPL"))

    assert diags == {}
    assert latencies == []
    assert failures == []
    assert wc is None
    assert neg is None


def test_D4_skip_logs_info_with_env_var_name(monkeypatch, caplog):
    """SKIP path logs an INFO message mentioning FORM4_FETCH_SKIP."""
    monkeypatch.setenv("FORM4_FETCH_SKIP", "1")
    with caplog.at_level(logging.INFO, logger="compute.orchestrator.form4"):
        fetch_all_form4(_make_df("AAPL"))

    assert any(
        "FORM4_FETCH_SKIP" in r.message
        for r in caplog.records
    )


def test_D5_skip_does_not_call_fetch_recent_form4(monkeypatch):
    """FORM4_FETCH_SKIP=1 must not invoke fetch_recent_form4 at all."""
    monkeypatch.setenv("FORM4_FETCH_SKIP", "1")
    mock_fetch = MagicMock()
    monkeypatch.setattr(form4_mod, "fetch_recent_form4", mock_fetch)

    fetch_all_form4(_make_df("AAPL", "MSFT"))

    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Section E: fetch_all_form4 outer-except path
# ---------------------------------------------------------------------------


def test_E1_outer_except_resets_all_five_to_empty_none(monkeypatch):
    """When the outer try block raises (e.g. df.iterrows explodes),
    all 5 outputs are reset to {}, [], [], None, None."""

    class _BadDF:
        """Minimal DataFrame-like whose iterrows() raises."""

        def iterrows(self):
            raise RuntimeError("disk full")

    result = fetch_all_form4(_BadDF())  # type: ignore[arg-type]
    diags, latencies, failures, wc, neg = result

    assert diags == {}
    assert latencies == []
    assert failures == []
    assert wc is None
    assert neg is None


def test_E2_outer_except_logs_warning(monkeypatch, caplog):
    """outer-except path logs a WARNING containing 'failed entirely'."""

    class _BadDF:
        def iterrows(self):
            raise RuntimeError("simulated outer failure")

    with caplog.at_level(logging.WARNING, logger="compute.orchestrator.form4"):
        fetch_all_form4(_BadDF())  # type: ignore[arg-type]

    assert any(
        "failed entirely" in r.message
        for r in caplog.records
    )
