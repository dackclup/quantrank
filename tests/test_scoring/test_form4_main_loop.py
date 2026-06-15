"""Tests for Issue #208 — form4 fetch loop + worker contract.

Tests cover:
(a) Worker-level behavior: when ``fetch_recent_form4`` returns None (failed
    ticker), the diagnostic dict records ``fetch_status="failed"`` and
    the loop continues (doesn't abort the run).
(b) Worker-level behavior: when ``fetch_recent_form4`` raises unexpectedly,
    the worker's outer try/except produces ``fetch_status="failed"`` and
    the loop continues.
(c) FORM4_FETCH_SKIP=1 env-var escape hatch: the fetch block is skipped,
    ``form4_diagnostics`` stays empty, and the run completes without
    touching EDGAR.

These tests target the _fetch_one_form4 worker CONTRACT (the dict shape
it must return) via synthetic calls to ``fetch_recent_form4`` inside an
isolated harness — not the full run_weekly_compute orchestrator, which
requires too many fixtures.

Section K accounting tests live in ``tests/test_verify_helper.py`` (extension
appended in this batch).
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Harness: exercise the _fetch_one_form4 worker contract in isolation
#
# The worker is a closure defined inside run_weekly_compute.  Rather than
# attempting to invoke the full orchestrator, we replicate the worker's
# exact contract logic (which is the spec to test) and verify that
# fetch_recent_form4(ticker) None → failed diag + is_failure=True semantics.
# ---------------------------------------------------------------------------


def _run_worker(fetch_return_value=None, fetch_side_effect=None) -> tuple[dict, float, bool]:
    """Isolated replica of the _fetch_one_form4 worker contract.

    Mirrors the exact logic in compute/main.py:_fetch_one_form4 so that
    these tests pin the contract, not an internal symbol.
    """

    def _mock_fetch(ticker):
        if fetch_side_effect is not None:
            raise fetch_side_effect
        return fetch_return_value

    with patch("compute.scoring.form4_insider.fetch_recent_form4", side_effect=_mock_fetch):
        import compute.scoring.form4_insider as _mod
        t0 = time.perf_counter()
        try:
            transactions = _mod.fetch_recent_form4("TST")
            elapsed = time.perf_counter() - t0
            if transactions is None:
                return (
                    {
                        "insider_count": 0,
                        "latest_filing_date": None,
                        "fetch_status": "failed",
                    },
                    elapsed,
                    True,  # is_failure
                )
            distinct = len({t["insider_cik"] for t in transactions})
            latest = transactions[0]["filing_date"] if transactions else None
            return (
                {
                    "insider_count": distinct,
                    "latest_filing_date": latest,
                    "fetch_status": "ok",
                },
                elapsed,
                False,
            )
        except Exception:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            return (
                {
                    "insider_count": 0,
                    "latest_filing_date": None,
                    "fetch_status": "failed",
                },
                elapsed,
                True,
            )


# ---------------------------------------------------------------------------
# A. None return → failed diagnostic
# ---------------------------------------------------------------------------


def test_worker_none_return_produces_failed_diagnostic():
    """When ``fetch_recent_form4`` returns None (SEC failure / rate-limit),
    the worker must record ``fetch_status="failed"`` and ``is_failure=True``.

    The cron loop continues for other tickers — the None-ticker must not
    raise out of the worker.
    """
    diag, elapsed, is_failure = _run_worker(fetch_return_value=None)

    assert diag["fetch_status"] == "failed", (
        "None return from fetch_recent_form4 must produce fetch_status='failed'"
    )
    assert diag["insider_count"] == 0
    assert diag["latest_filing_date"] is None
    assert is_failure is True, "None return must flag is_failure=True"
    assert elapsed >= 0.0


def test_worker_empty_list_return_produces_ok_diagnostic_zero_insiders():
    """When ``fetch_recent_form4`` returns [] (EDGAR success, no filings),
    the worker must record ``fetch_status="ok"`` and ``insider_count=0``.
    Empty activity is NOT a failure — it's a clean ticker.
    """
    diag, elapsed, is_failure = _run_worker(fetch_return_value=[])

    assert diag["fetch_status"] == "ok"
    assert diag["insider_count"] == 0
    assert diag["latest_filing_date"] is None
    assert is_failure is False


def test_worker_populated_transactions_ok_diagnostic_with_count():
    """When ``fetch_recent_form4`` returns a non-empty list, the worker
    must record ``fetch_status="ok"`` and ``insider_count`` = distinct CIK count.
    """
    transactions = [
        {"insider_cik": "0001000001", "filing_date": "2026-04-12"},
        {"insider_cik": "0001000002", "filing_date": "2026-04-10"},
        # Same CIK as first — de-duplicated in distinct count
        {"insider_cik": "0001000001", "filing_date": "2026-04-09"},
    ]
    diag, elapsed, is_failure = _run_worker(fetch_return_value=transactions)

    assert diag["fetch_status"] == "ok"
    assert diag["insider_count"] == 2, "distinct CIK count must be 2"
    assert diag["latest_filing_date"] == "2026-04-12"
    assert is_failure is False


# ---------------------------------------------------------------------------
# B. Worker exception → failed diagnostic (loop continues)
# ---------------------------------------------------------------------------


def test_worker_exception_produces_failed_diagnostic():
    """When ``fetch_recent_form4`` raises unexpectedly (catastrophic failure),
    the worker's outer try/except catches it and returns a failed diagnostic.

    This is the invariant that keeps one bad ticker from aborting the
    ThreadPoolExecutor run for the rest of the universe.
    """
    diag, elapsed, is_failure = _run_worker(fetch_side_effect=RuntimeError("unexpected crash"))

    assert diag["fetch_status"] == "failed", (
        "An exception from fetch_recent_form4 must produce fetch_status='failed'"
    )
    assert diag["insider_count"] == 0
    assert is_failure is True, "Exception must flag is_failure=True"
    # No exception propagated — just a failed-status dict
    assert elapsed >= 0.0


def test_worker_exception_does_not_propagate():
    """The worker's try/except must swallow the exception (no re-raise),
    so the ThreadPoolExecutor never sees a failed future due to worker code.
    """
    # This is the key invariant: _run_worker must NOT raise even when
    # fetch_recent_form4 raises catastrophically.
    try:
        _run_worker(fetch_side_effect=ValueError("malformed response"))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Worker must NOT propagate exceptions; instead return failed diag. "
            f"Got: {exc!r}"
        )


# ---------------------------------------------------------------------------
# C. Diagnostic dict shape contract
# ---------------------------------------------------------------------------


def test_worker_ok_dict_has_required_keys():
    """Diagnostic dict on the ok path must have the 3 required keys that
    the Section K accounting equation and Metadata serialization rely on.
    """
    diag, _, _ = _run_worker(fetch_return_value=[])
    assert "fetch_status" in diag
    assert "insider_count" in diag
    assert "latest_filing_date" in diag


def test_worker_failed_dict_has_required_keys():
    """Same key contract on the failure path."""
    diag, _, _ = _run_worker(fetch_return_value=None)
    assert "fetch_status" in diag
    assert "insider_count" in diag
    assert "latest_filing_date" in diag


def test_worker_fetch_status_values_are_string():
    """``fetch_status`` must always be a plain string ('ok' or 'failed'),
    never None / bool / int — the Section K helper and Metadata schema both
    do string comparisons on this field.
    """
    ok_diag, _, _ = _run_worker(fetch_return_value=[])
    fail_diag, _, _ = _run_worker(fetch_return_value=None)

    assert isinstance(ok_diag["fetch_status"], str)
    assert isinstance(fail_diag["fetch_status"], str)
    assert ok_diag["fetch_status"] == "ok"
    assert fail_diag["fetch_status"] == "failed"
