"""Tests for Issue #207 — form4 retry policy in ``_fetch_form4_filings_with_retry``.

Covers:
- (a) The retry function retries then succeeds when the first attempt raises.
      Tenacity's ``stop_after_attempt(2)`` means it tries AT MOST 2 times total
      (attempt 1 + 1 retry).  With ``reraise=True`` a second failure re-raises
      instead of wrapping in RetryError.
- (b) ``fetch_recent_form4`` returns None (graceful degrade) when the fetch
      terminally fails after retries.
- (c) 429-throttle log branch is reachable — when the exception message contains
      "429", the ``logger.warning`` branch with "429" / "throttle" path fires.

All tests are offline (no live SEC fetch).

``_fetch_form4_filings_with_retry`` uses a lazy ``from edgar import Company``
inside the function body, so it doesn't need edgar at import time.  We register
a minimal edgar stub in sys.modules so the lazy import in
``_fetch_form4_filings_with_retry`` finds a real (mocked) Company class.

``_ensure_edgar_identity`` uses ``from edgar import set_identity`` — same stub
covers it.

The retry decorator uses ``stop_after_delay(30)`` which would cause actual
wall-clock waits in tests.  We bypass the live network call by patching the
``Company`` constructor inside ``_fetch_form4_filings_with_retry`` directly,
but the ``wait_exponential`` in the decorator would still cause real waits.
We therefore test ``_fetch_form4_filings_with_retry`` through its DIRECT call,
not through the retry decorator timing — call it directly so we can count
Company() invocations, then separately verify ``fetch_recent_form4`` graceful
degrade by patching ``_fetch_form4_filings_with_retry`` itself (bypassing the
decorator altogether for the fetch_recent_form4 degradation tests).
"""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# edgar stub — so lazy imports in form4_insider.py don't fail at collection
# ---------------------------------------------------------------------------


def _stub_edgar():
    if "edgar" in sys.modules:
        return

    edgar_stub = types.ModuleType("edgar")

    class _Company:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def get_filings(self, *, form, filing_date):
            return iter([])

    def _set_identity(user_agent: str) -> None:  # noqa: ARG001
        pass

    edgar_stub.Company = _Company
    edgar_stub.set_identity = _set_identity
    sys.modules["edgar"] = edgar_stub


_stub_edgar()


# ---------------------------------------------------------------------------
# Helper: minimal filings stub
# ---------------------------------------------------------------------------


class _EmptyFilings:
    """Stub for Company.get_filings() return — empty, iterable."""

    def __iter__(self):
        return iter([])


# ---------------------------------------------------------------------------
# A. _fetch_form4_filings_with_retry: retry then succeed
#
# We call the underlying Company directly rather than going through tenacity's
# wait_exponential (which would cause real delays) by patching what Company()
# returns — the retry decorator still controls how many times the function body
# runs; we count Company() instantiations to verify.
# ---------------------------------------------------------------------------


def test_form4_retry_succeeds_on_second_attempt():
    """_fetch_form4_filings_with_retry retries once and succeeds.

    Policy: stop_after_attempt(2).  We inject a side_effect that raises on
    the first call and returns on the second.  The function under test should
    succeed, consuming exactly 2 Company() instantiations.

    NOTE: wait_exponential(min=2, max=8) would sleep between attempts in
    production; in this test the retry is fast because we only need to confirm
    the ATTEMPT COUNT semantics — the wall-clock wait is irrelevant.
    We monkeypatch ``tenacity.nap.time.sleep`` to avoid actual delays.

    ``_fetch_form4_filings_with_retry`` uses ``from edgar import Company``
    as a lazy local import — so we must patch ``edgar.Company`` (the module
    attribute) rather than ``compute.scoring.form4_insider.Company``
    (which doesn't exist at module scope).
    """
    from compute.scoring.form4_insider import _fetch_form4_filings_with_retry

    _state_a = {"call_count": 0}

    class _FlakyCompany:
        def __init__(self, ticker: str) -> None:
            _state_a["call_count"] += 1
            self._ticker = ticker
            self._call_n = _state_a["call_count"]

        def get_filings(self, **kwargs):
            if self._call_n == 1:
                raise RuntimeError("transient SEC error")
            return _EmptyFilings()

    # Patch at the edgar module level (where the lazy import resolves).
    with (
        patch.object(sys.modules["edgar"], "Company", _FlakyCompany),
        patch("tenacity.nap.time.sleep"),  # suppress exponential wait
    ):
        result = _fetch_form4_filings_with_retry("TST", "2025-01-01", "2025-12-31")

    # Two Company() instantiations: first raises, second returns.
    assert _state_a["call_count"] == 2, (
        f"Expected 2 Company() calls (1 fail + 1 success); got {_state_a['call_count']}"
    )
    # Result is the filings object from the second attempt.
    assert result is not None


def test_form4_retry_reraises_after_max_attempts():
    """When both attempts fail, reraise=True means the original exception
    propagates out of _fetch_form4_filings_with_retry.

    Policy: stop_after_attempt(2) + reraise=True.  Two failures → exception
    raised.  We assert the function raises (NOT RetryError).
    """
    from compute.scoring.form4_insider import _fetch_form4_filings_with_retry

    _state_b = {"call_count": 0}

    class _AlwaysFailCompany:
        def __init__(self, ticker: str) -> None:
            _state_b["call_count"] += 1

        def get_filings(self, **kwargs):
            raise RuntimeError("persistent failure")

    with (
        patch.object(sys.modules["edgar"], "Company", _AlwaysFailCompany),
        patch("tenacity.nap.time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="persistent failure"):
            _fetch_form4_filings_with_retry("TST", "2025-01-01", "2025-12-31")

    assert _state_b["call_count"] == 2, (
        f"Expected exactly 2 Company() calls (stop_after_attempt(2)); got {_state_b['call_count']}"
    )


def test_form4_retry_max_attempts_is_two():
    """Policy pin: stop_after_attempt(2) means exactly 2 total attempts max.

    Even if a third call would succeed, it must NOT be made — the retry cap
    is 2 total (1 original + 1 retry).
    """
    from compute.scoring.form4_insider import _fetch_form4_filings_with_retry

    _state = {"call_count": 0, "would_have_succeeded": 0}

    class _CounterCompany:
        def __init__(self, ticker: str) -> None:
            _state["call_count"] += 1
            self._n = _state["call_count"]

        def get_filings(self, **kwargs):
            if self._n <= 2:
                raise RuntimeError("fail")
            # This branch must NEVER be reached.
            _state["would_have_succeeded"] += 1
            return _EmptyFilings()

    with (
        patch.object(sys.modules["edgar"], "Company", _CounterCompany),
        patch("tenacity.nap.time.sleep"),
    ):
        with pytest.raises(RuntimeError):
            _fetch_form4_filings_with_retry("TST", "2025-01-01", "2025-12-31")

    assert _state["call_count"] == 2, (
        f"stop_after_attempt(2) must limit to 2 calls; got {_state['call_count']}"
    )
    assert _state["would_have_succeeded"] == 0, "3rd+ attempt must NOT fire"


# ---------------------------------------------------------------------------
# B. Graceful degrade: fetch_recent_form4 returns None on terminal failure
#
# We patch _fetch_form4_filings_with_retry directly to bypass the actual
# retry decorator and focus on the outer fetch_recent_form4 error handling.
# We also patch _ensure_edgar_identity to return True (simulate identity set).
# ---------------------------------------------------------------------------


def test_fetch_recent_form4_returns_none_on_terminal_failure(caplog):
    """When _fetch_form4_filings_with_retry raises terminally after retries,
    ``fetch_recent_form4`` must catch the exception and return None (graceful
    degradation per the cron design — no ticker failure blocks the whole run).
    """
    from compute.scoring.form4_insider import fetch_recent_form4

    with (
        patch("compute.scoring.form4_insider._ensure_edgar_identity", return_value=True),
        patch(
            "compute.scoring.form4_insider._cache_read",
            return_value=None,  # no cache
        ),
        patch(
            "compute.scoring.form4_insider._fetch_form4_filings_with_retry",
            side_effect=RuntimeError("final failure after retries"),
        ),
    ):
        result = fetch_recent_form4("FAIL_TST")

    assert result is None, (
        "fetch_recent_form4 must return None (graceful degrade) when "
        "_fetch_form4_filings_with_retry raises terminally"
    )


def test_fetch_recent_form4_429_branch_logs_throttle_warning(caplog):
    """The 429/throttle branch in ``fetch_recent_form4`` logs a
    'form4 SEC throttle' warning when the exception message contains '429'.

    Asserts the branch is reachable and produces the expected log output
    (rate-limit observability per Rule 18).
    """
    from compute.scoring.form4_insider import fetch_recent_form4

    throttle_error = RuntimeError("HTTP 429 Too Many Requests")

    with (
        patch("compute.scoring.form4_insider._ensure_edgar_identity", return_value=True),
        patch("compute.scoring.form4_insider._cache_read", return_value=None),
        patch(
            "compute.scoring.form4_insider._fetch_form4_filings_with_retry",
            side_effect=throttle_error,
        ),
    ):
        with caplog.at_level(logging.WARNING, logger="compute.scoring.form4_insider"):
            result = fetch_recent_form4("RATE_TST")

    assert result is None, "Must return None on 429 throttle"
    warning_messages = [r.message for r in caplog.records]
    # One of the log records must mention "throttle" (or "429")
    assert any(
        "throttle" in m.lower() or "429" in m
        for m in warning_messages
    ), (
        f"Expected a 'throttle' or '429' warning log record; got: {warning_messages}"
    )


def test_fetch_recent_form4_generic_failure_logs_warning(caplog):
    """The non-429 failure branch in ``fetch_recent_form4`` also logs a
    warning (the else branch uses a different message template).
    """
    from compute.scoring.form4_insider import fetch_recent_form4

    with (
        patch("compute.scoring.form4_insider._ensure_edgar_identity", return_value=True),
        patch("compute.scoring.form4_insider._cache_read", return_value=None),
        patch(
            "compute.scoring.form4_insider._fetch_form4_filings_with_retry",
            side_effect=ConnectionError("generic network failure"),
        ),
    ):
        with caplog.at_level(logging.WARNING, logger="compute.scoring.form4_insider"):
            result = fetch_recent_form4("GEN_TST")

    assert result is None
    assert any(
        "form4" in r.message.lower() and "failed" in r.message.lower()
        for r in caplog.records
    ), (
        f"Expected a form4 fetch-failed warning record for generic failures; "
        f"got: {[r.message for r in caplog.records]}"
    )
