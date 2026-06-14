"""Offline coverage for Issue #471 Design-B filing-precheck (fetch_fundamentals).

Tests the new middle path in ``fetch_fundamentals``:

    if cached is not None and cik and cached.latest_filed_date is not None:
        latest = _latest_filing_date(cik)
        if latest is not None and latest <= cached.latest_filed_date:
            # skip heavy get_facts() — no new filing
            <increment skip counter>
            return cached
        # else (latest None, or latest > cached) → fall through to _build_snapshot

Also tests the two new public helpers:
    - ``_latest_filing_date(cik)``
    - ``reset_filing_precheck_skip_count()`` / ``get_filing_precheck_skip_count()``

All tests are offline — no live SEC, no ``@pytest.mark.network``.

Style mirrors ``test_fundamentals.py`` in this module: ``unittest.mock.patch`` on
fully-qualified names; ``SimpleNamespace``-based stubs; no deep mock hierarchies.
``_build_snapshot`` is patched throughout (import-time; the real implementation
requires edgartools which is not installed in this sandbox).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

_TICKER = "FAKE"
_CIK = "0000000001"

# A "stale" date that will be old enough to make _is_fresh return False.
# _is_fresh: (today - latest_filed_date) < FUNDAMENTALS_REFETCH_DAYS
# We use a date 200 days in the past with today=2026-06-13 (fixed reference).
_TODAY = date(2026, 6, 13)
# FUNDAMENTALS_REFETCH_DAYS is typically 30 or 45; 200 days is safely stale.
_STALE_FILED_DATE = date(2026, 6, 13) - timedelta(days=200)
# A "fresh" date: filed 5 days ago — well within any FUNDAMENTALS_REFETCH_DAYS.
_FRESH_FILED_DATE = date(2026, 6, 13) - timedelta(days=5)


# ---------------------------------------------------------------------------
# Helpers — synthetic FundamentalsSnapshot constructor
# ---------------------------------------------------------------------------

def _make_snapshot(
    *,
    latest_filed_date: date | None = _STALE_FILED_DATE,
    ticker: str = _TICKER,
    cik: str = _CIK,
) -> object:
    """Return a minimal ``FundamentalsSnapshot`` suitable for cache injection.

    Uses the real dataclass so isinstance checks in fetch_fundamentals hold.
    All metric fields default to None — only latest_filed_date matters for
    the precheck / freshness gate tests.
    """
    from compute.ingest.fundamentals import FundamentalsSnapshot

    return FundamentalsSnapshot(
        ticker=ticker,
        cik=cik,
        latest_filed_date=latest_filed_date,
    )


# ---------------------------------------------------------------------------
# Stub factory for _build_snapshot (returns a minimal live snapshot)
# ---------------------------------------------------------------------------

def _make_live_snapshot(*, ticker: str = _TICKER, cik: str = _CIK) -> object:
    """Minimal snapshot that _build_snapshot would return on a live call."""
    from compute.ingest.fundamentals import FundamentalsSnapshot

    return FundamentalsSnapshot(
        ticker=ticker,
        cik=cik,
        latest_filed_date=_TODAY,
    )


# ---------------------------------------------------------------------------
# 1.  Stale + no new filing → SKIP (equal date)
# ---------------------------------------------------------------------------


def test_stale_cached_equal_filing_date_skips_build_snapshot():
    """Stale cache + _latest_filing_date == cached.latest_filed_date → precheck SKIP.

    _build_snapshot must NOT be called; skip counter increments by 1.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            return_value=_STALE_FILED_DATE,  # equal → <=  → skip
        ),
        patch("compute.ingest.fundamentals._build_snapshot") as mock_build,
    ):
        result = fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_not_called()
    assert result is cached
    assert get_filing_precheck_skip_count() == 1


def test_stale_cached_older_filing_date_skips_build_snapshot():
    """_latest_filing_date returns a date < cached.latest_filed_date → STILL skips.

    The gate is ``latest <= cached.latest_filed_date``; strictly older also satisfies.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)
    older = _STALE_FILED_DATE - timedelta(days=30)

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            return_value=older,  # older than cached → <=  → skip
        ),
        patch("compute.ingest.fundamentals._build_snapshot") as mock_build,
    ):
        result = fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_not_called()
    assert result is cached
    assert get_filing_precheck_skip_count() == 1


# ---------------------------------------------------------------------------
# 2.  Stale + new filing → FALL THROUGH to _build_snapshot
# ---------------------------------------------------------------------------


def test_stale_cached_newer_filing_calls_build_snapshot():
    """_latest_filing_date > cached.latest_filed_date → new filing → fall through.

    _build_snapshot IS called; skip counter stays 0.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)
    newer = _STALE_FILED_DATE + timedelta(days=90)  # new 10-Q appeared
    live_snap = _make_live_snapshot()

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            return_value=newer,
        ),
        patch(
            "compute.ingest.fundamentals._build_snapshot",
            return_value=live_snap,
        ) as mock_build,
        patch("compute.ingest.fundamentals._save_cached"),
    ):
        result = fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_called_once_with(_TICKER, _CIK)
    assert result is live_snap
    assert get_filing_precheck_skip_count() == 0


# ---------------------------------------------------------------------------
# 3.  Fresh cache → warm-hit short-circuit (precheck NOT reached)
# ---------------------------------------------------------------------------


def _sentinel_latest_filing_date_fail(*_args, **_kwargs):
    """Sentinel: raises if called — used to assert _latest_filing_date is NEVER invoked."""
    raise AssertionError(
        "_latest_filing_date should not be called when cache is fresh "
        "(warm-hit returns before the precheck block)."
    )


def test_fresh_cache_returns_without_calling_latest_filing_date():
    """Fresh cache (within FUNDAMENTALS_REFETCH_DAYS) → returns immediately.

    _latest_filing_date must NOT be called; skip counter stays 0.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    # _FRESH_FILED_DATE is 5 days old — always within FUNDAMENTALS_REFETCH_DAYS.
    cached = _make_snapshot(latest_filed_date=_FRESH_FILED_DATE)

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            side_effect=_sentinel_latest_filing_date_fail,
        ),
        patch("compute.ingest.fundamentals._build_snapshot") as mock_build,
    ):
        result = fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_not_called()
    assert result is cached
    assert get_filing_precheck_skip_count() == 0


# ---------------------------------------------------------------------------
# 4.  Precheck guard misses → FALL THROUGH to _build_snapshot
# ---------------------------------------------------------------------------


def test_no_cache_calls_build_snapshot():
    """cached is None → precheck block not entered; _build_snapshot called."""
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    live_snap = _make_live_snapshot()

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=None),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            side_effect=_sentinel_latest_filing_date_fail,
        ),
        patch(
            "compute.ingest.fundamentals._build_snapshot",
            return_value=live_snap,
        ) as mock_build,
        patch("compute.ingest.fundamentals._save_cached"),
    ):
        fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_called_once()
    assert get_filing_precheck_skip_count() == 0


def test_empty_cik_calls_build_snapshot():
    """cik='' → _load_cached returns None (conditional), precheck skipped.

    fetch_fundamentals calls ``_load_cached(cik) if cik else None``.
    An empty string is falsy; _load_cached is not called → cached=None →
    precheck block not entered; _build_snapshot called.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    live_snap = _make_live_snapshot()

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached") as mock_load,
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            side_effect=_sentinel_latest_filing_date_fail,
        ),
        patch(
            "compute.ingest.fundamentals._build_snapshot",
            return_value=live_snap,
        ) as mock_build,
        patch("compute.ingest.fundamentals._save_cached"),
    ):
        # cik="" is falsy → _load_cached must NOT be called → cached=None
        fetch_fundamentals(_TICKER, "", today=_TODAY)

    # _load_cached should not be called when cik is empty
    mock_load.assert_not_called()
    mock_build.assert_called_once()
    assert get_filing_precheck_skip_count() == 0


def test_cached_with_none_filed_date_calls_build_snapshot():
    """cached.latest_filed_date is None → precheck guard fails; _build_snapshot called."""
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    # Snapshot with no filing date — guard condition ``cached.latest_filed_date is not None``
    # is False → precheck block not entered.
    cached = _make_snapshot(latest_filed_date=None)
    live_snap = _make_live_snapshot()

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            side_effect=_sentinel_latest_filing_date_fail,
        ),
        patch(
            "compute.ingest.fundamentals._build_snapshot",
            return_value=live_snap,
        ) as mock_build,
        patch("compute.ingest.fundamentals._save_cached"),
    ):
        fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_called_once()
    assert get_filing_precheck_skip_count() == 0


# ---------------------------------------------------------------------------
# 5.  Helper returns None (graceful) → FALL THROUGH
# ---------------------------------------------------------------------------


def test_latest_filing_date_returns_none_calls_build_snapshot():
    """_latest_filing_date returns None (network error / edgartools drift) → fall through.

    _build_snapshot IS called; skip counter NOT incremented.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)
    live_snap = _make_live_snapshot()

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            return_value=None,  # failure path
        ),
        patch(
            "compute.ingest.fundamentals._build_snapshot",
            return_value=live_snap,
        ) as mock_build,
        patch("compute.ingest.fundamentals._save_cached"),
    ):
        result = fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_build.assert_called_once()
    assert result is live_snap
    assert get_filing_precheck_skip_count() == 0


# ---------------------------------------------------------------------------
# 6.  Counter lifecycle: reset → skip → reset
# ---------------------------------------------------------------------------


def test_counter_reset_and_increment_lifecycle():
    """reset zeroes counter; one skip path raises it to 1; second reset zeroes again."""
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    # Start clean.
    reset_filing_precheck_skip_count()
    assert get_filing_precheck_skip_count() == 0

    # Drive one precheck skip.
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)
    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            return_value=_STALE_FILED_DATE,
        ),
        patch("compute.ingest.fundamentals._build_snapshot"),
    ):
        fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    assert get_filing_precheck_skip_count() == 1

    # Reset again → back to zero.
    reset_filing_precheck_skip_count()
    assert get_filing_precheck_skip_count() == 0


# ---------------------------------------------------------------------------
# 7.  QR_SKIP_FUNDAMENTALS=1 → escape-hatch path: precheck NOT called
# ---------------------------------------------------------------------------


def test_qr_skip_fundamentals_returns_cache_without_precheck(monkeypatch):
    """QR_SKIP_FUNDAMENTALS=1 with cached snapshot → returned immediately.

    The escape-hatch branch runs before _require_identity; _latest_filing_date
    must NOT be called; skip counter stays 0.
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    reset_filing_precheck_skip_count()
    monkeypatch.setenv("QR_SKIP_FUNDAMENTALS", "1")
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)

    with (
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            side_effect=_sentinel_latest_filing_date_fail,
        ),
        patch("compute.ingest.fundamentals._require_identity") as mock_ident,
        patch("compute.ingest.fundamentals._build_snapshot") as mock_build,
    ):
        result = fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    mock_ident.assert_not_called()
    mock_build.assert_not_called()
    assert result is cached
    assert get_filing_precheck_skip_count() == 0


# ---------------------------------------------------------------------------
# 8.  Thread-safety: concurrent skip-path invocations
# ---------------------------------------------------------------------------


def test_skip_counter_is_thread_safe():
    """Concurrent skip-path invocations (50 threads) → final count == 50.

    Verifies that the threading.Lock around ``_FILING_PRECHECK_SKIP_COUNT``
    prevents lost increments under concurrent access.

    Patches are applied ONCE at the test-body level (single-threaded
    __enter__/__exit__) so they are visible to all threads without racing.
    unittest.mock.patch is not thread-safe — placing patch context managers
    inside per-thread workers causes concurrent __enter__/__exit__ on the same
    module attributes, which leaks MagicMocks into sibling tests (PR #471 flaky
    root cause, reproduced ~30% of runs on main).
    """
    from compute.ingest.fundamentals import (
        fetch_fundamentals,
        get_filing_precheck_skip_count,
        reset_filing_precheck_skip_count,
    )

    N_THREADS = 50
    reset_filing_precheck_skip_count()
    cached = _make_snapshot(latest_filed_date=_STALE_FILED_DATE)

    def run_one(_n: int) -> None:
        # No patch machinery here — patches are already active at the test-body
        # level, so all threads share the same (already-applied) stubs.
        fetch_fundamentals(_TICKER, _CIK, today=_TODAY)

    with (
        patch("compute.ingest.fundamentals._require_identity"),
        patch("compute.ingest.fundamentals._load_cached", return_value=cached),
        patch(
            "compute.ingest.fundamentals._latest_filing_date",
            return_value=_STALE_FILED_DATE,
        ),
        patch("compute.ingest.fundamentals._build_snapshot"),
    ):
        with ThreadPoolExecutor(max_workers=N_THREADS) as pool:
            futures = [pool.submit(run_one, i) for i in range(N_THREADS)]
            for f in as_completed(futures):
                f.result()  # re-raise any thread exception immediately

    assert get_filing_precheck_skip_count() == N_THREADS


# ---------------------------------------------------------------------------
# 9.  _latest_filing_date unit tests (mock Company directly)
# ---------------------------------------------------------------------------


def _make_filing_stub(filing_date: date | datetime) -> SimpleNamespace:
    """Minimal filing object with a .filing_date attribute."""
    return SimpleNamespace(filing_date=filing_date)


class _FakeFiling:
    """Minimal filing iterable with .head(n) support."""

    def __init__(self, filings: list) -> None:
        self._filings = filings

    def head(self, n: int) -> list:
        return self._filings[:n]

    def __len__(self) -> int:
        return len(self._filings)

    def __getitem__(self, idx):
        return self._filings[idx]


def test_latest_filing_date_returns_max_across_10k_and_10q():
    """_latest_filing_date returns the MAX filing date across 10-K and 10-Q sets."""
    from compute.ingest.fundamentals import _latest_filing_date

    date_10k = date(2026, 2, 15)
    date_10q = date(2026, 5, 10)  # newer

    mock_company = MagicMock()
    mock_company.get_filings.side_effect = lambda form: (
        _FakeFiling([_make_filing_stub(date_10k)])
        if form == "10-K"
        else _FakeFiling([_make_filing_stub(date_10q)])
    )

    with patch("compute.ingest.fundamentals.Company", return_value=mock_company):
        result = _latest_filing_date(_CIK)

    assert result == date_10q


def test_latest_filing_date_normalises_datetime_to_date():
    """A filing_date given as a datetime is normalised to a plain date."""
    from compute.ingest.fundamentals import _latest_filing_date

    dt_value = datetime(2026, 3, 15, 12, 30, 0)  # datetime, not date
    mock_company = MagicMock()
    mock_company.get_filings.side_effect = lambda form: (
        _FakeFiling([_make_filing_stub(dt_value)])
        if form == "10-K"
        else _FakeFiling([])
    )

    with patch("compute.ingest.fundamentals.Company", return_value=mock_company):
        result = _latest_filing_date(_CIK)

    assert result == date(2026, 3, 15)
    assert isinstance(result, date) and not isinstance(result, datetime)


def test_latest_filing_date_returns_none_on_company_exception():
    """Company() or get_filings() raising → returns None (graceful degradation)."""
    from compute.ingest.fundamentals import _latest_filing_date

    with patch(
        "compute.ingest.fundamentals.Company",
        side_effect=RuntimeError("edgartools drift"),
    ):
        result = _latest_filing_date(_CIK)

    assert result is None


def test_latest_filing_date_returns_none_when_no_filings():
    """Empty filing sets for both 10-K and 10-Q → returns None."""
    from compute.ingest.fundamentals import _latest_filing_date

    mock_company = MagicMock()
    mock_company.get_filings.return_value = _FakeFiling([])

    with patch("compute.ingest.fundamentals.Company", return_value=mock_company):
        result = _latest_filing_date(_CIK)

    assert result is None


def test_latest_filing_date_returns_none_when_head_raises():
    """get_filings().head(1) raising for all form types → returns None gracefully."""
    from compute.ingest.fundamentals import _latest_filing_date

    class _RaisingFiling:
        def head(self, _n):
            raise OSError("network blip")

    mock_company = MagicMock()
    mock_company.get_filings.return_value = _RaisingFiling()

    with patch("compute.ingest.fundamentals.Company", return_value=mock_company):
        result = _latest_filing_date(_CIK)

    assert result is None


def test_latest_filing_date_uses_10q_when_no_10k():
    """When 10-K set is empty, the 10-Q date is returned."""
    from compute.ingest.fundamentals import _latest_filing_date

    date_10q = date(2026, 4, 30)
    mock_company = MagicMock()
    mock_company.get_filings.side_effect = lambda form: (
        _FakeFiling([])
        if form == "10-K"
        else _FakeFiling([_make_filing_stub(date_10q)])
    )

    with patch("compute.ingest.fundamentals.Company", return_value=mock_company):
        result = _latest_filing_date(_CIK)

    assert result == date_10q
