"""Unit tests for the per-filing XBRL share-count fallback (issue #176).

The fallback in ``compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl``
recovers ``shares_outstanding`` for filers (e.g., STZ / Constellation
Brands) whose share-count facts are dimensional (Class A / Class B) and
therefore filtered out by the SEC companyfacts aggregate API.

These tests exercise the function via a synthetic mock of the
``Company -> Filings -> Filing.xbrl().facts.get_facts_by_concept()``
chain — no live SEC network. The companion ``@network`` live test (if
ever added) would target STZ to lock the actual fact-name + dimensional
behavior against edgartools API drift.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from compute.ingest.fundamentals import _fetch_shares_from_per_filing_xbrl


def _make_company(facts_by_concept: dict[str, pd.DataFrame | None]) -> MagicMock:
    """Build a mock ``Company`` whose filings chain returns a single 10-K
    filing whose ``xbrl().facts.get_facts_by_concept(concept)`` returns
    the supplied DataFrame for each concept name.

    A concept absent from ``facts_by_concept`` returns ``None``. A
    concept whose value is ``None`` also returns ``None`` (covers
    "edgartools returned nothing" path).
    """
    def get_facts_by_concept(concept: str) -> pd.DataFrame | None:
        return facts_by_concept.get(concept)

    facts_view = SimpleNamespace(get_facts_by_concept=get_facts_by_concept)
    xbrl = SimpleNamespace(facts=facts_view)
    filing = SimpleNamespace(xbrl=lambda: xbrl)

    class _Filings:
        def __init__(self, rows: list) -> None:
            self._rows = rows

        def __len__(self) -> int:
            return len(self._rows)

        def head(self, n: int) -> list:
            return self._rows[:n]

        def __iter__(self):
            return iter(self._rows)

        def __getitem__(self, idx):
            return self._rows[idx]

    filings_10k = _Filings([filing])
    filings_10q = _Filings([])

    def get_filings(form: str) -> _Filings:
        if form == "10-K":
            return filings_10k
        if form == "10-Q":
            return filings_10q
        return _Filings([])

    return MagicMock(spec=["get_filings"], get_filings=get_filings)


def _stz_dei_df(
    period_instant: str = "2025-11-30",
    class_a: float = 173_384_625.0,
    class_b: float = 26_197.0,
) -> pd.DataFrame:
    """Reproduce the STZ 10-Q dimensional shape: 2 rows at one
    ``period_instant`` (share-count facts are instant-type, not
    flow-type), one row per share class. The real STZ 2026-01-08
    filing produced exactly these numbers in the live SEC probe
    documented on issue #176."""
    return pd.DataFrame(
        [
            {
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "numeric_value": class_a,
                "period_instant": period_instant,
                "is_dimensioned": True,
                "context_ref": "c-2",
            },
            {
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "numeric_value": class_b,
                "period_instant": period_instant,
                "is_dimensioned": True,
                "context_ref": "c-3",
            },
        ]
    )


def test_per_filing_fallback_sums_dimensional_share_classes():
    """STZ signature: 2 rows at the same ``period_instant``, one Class A
    + one Class B — total = sum."""
    df = _stz_dei_df()
    company = _make_company(
        {"dei:EntityCommonStockSharesOutstanding": df}
    )
    result = _fetch_shares_from_per_filing_xbrl(company)
    assert result == 173_384_625.0 + 26_197.0


def test_per_filing_fallback_picks_most_recent_period_instant_only():
    """Multiple ``period_instant`` values across rows — only the
    most-recent ``period_instant``'s rows participate in the sum so
    historic share counts don't leak into the present-day total."""
    df = pd.concat(
        [
            _stz_dei_df(period_instant="2024-11-30", class_a=170_000_000.0, class_b=26_000.0),
            _stz_dei_df(period_instant="2025-11-30", class_a=173_384_625.0, class_b=26_197.0),
        ],
        ignore_index=True,
    )
    company = _make_company(
        {"dei:EntityCommonStockSharesOutstanding": df}
    )
    result = _fetch_shares_from_per_filing_xbrl(company)
    assert result == 173_384_625.0 + 26_197.0


def test_per_filing_fallback_falls_back_to_us_gaap_common_stock_issued():
    """``dei`` concept absent → try ``us-gaap:CommonStockSharesIssued`` next
    (some filers tag only one or the other)."""
    issued_df = pd.DataFrame(
        [
            {
                "concept": "us-gaap:CommonStockSharesIssued",
                "numeric_value": 212_698_298.0,
                "period_instant": "2025-11-30",
                "is_dimensioned": True,
                "context_ref": "c-7",
            },
            {
                "concept": "us-gaap:CommonStockSharesIssued",
                "numeric_value": 27_037.0,
                "period_instant": "2025-11-30",
                "is_dimensioned": True,
                "context_ref": "c-296",
            },
        ]
    )
    company = _make_company(
        {
            "dei:EntityCommonStockSharesOutstanding": None,
            "us-gaap:CommonStockSharesIssued": issued_df,
        }
    )
    result = _fetch_shares_from_per_filing_xbrl(company)
    assert result == 212_698_298.0 + 27_037.0


def test_per_filing_fallback_returns_none_when_no_concepts_match():
    """Neither concept returns data → ``None`` (caller keeps the upstream
    ``share_count_extraction_missing`` annotate firing)."""
    company = _make_company(
        {
            "dei:EntityCommonStockSharesOutstanding": None,
            "us-gaap:CommonStockSharesIssued": None,
        }
    )
    assert _fetch_shares_from_per_filing_xbrl(company) is None


def test_per_filing_fallback_returns_none_on_empty_dataframe():
    """Concept returns an empty DataFrame (no rows match after edgartools
    filtering) → ``None``, same path as the "concept missing" case."""
    empty = pd.DataFrame(columns=["concept", "numeric_value", "period_instant"])
    company = _make_company(
        {
            "dei:EntityCommonStockSharesOutstanding": empty,
            "us-gaap:CommonStockSharesIssued": empty,
        }
    )
    assert _fetch_shares_from_per_filing_xbrl(company) is None


def test_per_filing_fallback_returns_none_on_zero_total():
    """All numeric_values sum to 0 (defensive — would only happen on a
    badly-tagged filing) → ``None`` so the upstream annotate keeps
    firing rather than recording ``shares_outstanding == 0``."""
    zero_df = pd.DataFrame(
        [
            {
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "numeric_value": 0.0,
                "period_instant": "2025-11-30",
                "is_dimensioned": False,
            }
        ]
    )
    company = _make_company(
        {"dei:EntityCommonStockSharesOutstanding": zero_df}
    )
    assert _fetch_shares_from_per_filing_xbrl(company) is None


def test_per_filing_fallback_returns_none_on_get_filings_exception():
    """edgartools (or the underlying SEC HTTP layer) raises → graceful
    degradation per ``portable-graceful-degradation-try-except``."""
    company = MagicMock()
    company.get_filings.side_effect = RuntimeError("simulated SEC outage")
    assert _fetch_shares_from_per_filing_xbrl(company) is None


def test_per_filing_fallback_returns_none_when_no_filings_on_file():
    """A pre-IPO or recently-listed company may have neither 10-K nor 10-Q
    on file. Defensive — shouldn't happen on the S&P 500, but cheap to
    guard so the fallback never throws into the snapshot construction."""

    class _Empty:
        def __len__(self) -> int:
            return 0

        def head(self, _n: int) -> list:
            return []

    company = MagicMock()
    company.get_filings.return_value = _Empty()
    assert _fetch_shares_from_per_filing_xbrl(company) is None


def test_per_filing_fallback_returns_none_when_xbrl_missing():
    """Filing exists but ``.xbrl()`` returns ``None`` (filing is text-only
    or pre-XBRL-mandate vintage). Don't crash."""
    filing = SimpleNamespace(xbrl=lambda: None)

    class _OneFiling:
        def __len__(self) -> int:
            return 1

        def head(self, _n: int) -> list:
            return [filing]

    company = MagicMock()
    company.get_filings.return_value = _OneFiling()
    assert _fetch_shares_from_per_filing_xbrl(company) is None


# ---------------------------------------------------------------------------
# Bug 2 fix (issue #220) — outer-except logger.warning makes the silent
# fallback miss observable. The 2026-05-23 cron #3 STZ regression
# (recovery worked in a 2026-05-21 live probe but returned None two days
# later under cron load) was invisible because the bare `except: return
# None` swallowed the failure entirely. Pin the warning emission so a
# future refactor doesn't accidentally restore the silent-drop path.


def test_per_filing_fallback_emits_warning_on_outer_except(caplog):
    """When the SEC-bound call raises (e.g., a 429, a connection reset),
    the bare `except Exception` returns None — but now also logs a
    WARNING line so the operator can distinguish 'transient SEC 429' from
    'structural XBRL shape drift' without re-running a live probe."""
    import logging

    company = MagicMock()
    company.get_filings.side_effect = RuntimeError("simulated SEC 429")

    with caplog.at_level(logging.WARNING, logger="compute.ingest.fundamentals"):
        result = _fetch_shares_from_per_filing_xbrl(company, ticker="STZ")

    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"expected 1 WARNING, got {len(warnings)}: {warnings}"
    msg = warnings[0].getMessage()
    assert "shares_outstanding fallback FAILED" in msg
    assert "STZ" in msg
    assert "RuntimeError" in msg
    assert "simulated SEC 429" in msg
    # The annotate safety-net note is included so the operator knows the
    # universe-wide impact is still surfaced via share_count_extraction_missing.
    assert "share_count_extraction_missing" in msg


def test_per_filing_fallback_ticker_arg_optional_for_back_compat(caplog):
    """The `ticker` kwarg is optional — existing call sites that pass
    only `company` (8 of the offline tests above) must still work. The
    failure-path WARNING will show '?' as the ticker, which is correct
    for the back-compat path."""
    import logging

    company = MagicMock()
    company.get_filings.side_effect = RuntimeError("any error")

    with caplog.at_level(logging.WARNING, logger="compute.ingest.fundamentals"):
        result = _fetch_shares_from_per_filing_xbrl(company)

    assert result is None
    assert any(
        "? — RuntimeError" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


# ---------------------------------------------------------------------------
# @network — live SEC verification for issue #176 root cause.
#
# Locks the actual STZ fact-name + dimensional-aggregation behavior
# against future edgartools API drift. Without this test, an upstream
# rename of the `period_instant` column or `get_facts_by_concept` would
# silently regress the fallback into "always returns None" — which would
# look like a healthy production cron (no exceptions) while quietly
# dropping STZ's market_cap to null again.
#
# Run with: `pytest --run-network tests/test_ingest/test_fundamentals_xbrl_fallback.py`
# (requires EDGAR_USER_AGENT env var). Skipped by default in offline runs.
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_per_filing_fallback_live_stz_recovers_shares():
    """Live SEC probe — STZ must recover ~170-180M shares total (Class A
    + Class B). The exact number drifts as STZ repurchases shares; lock
    against an order-of-magnitude range rather than an exact match."""
    import os

    from edgar import Company, set_identity

    set_identity(os.environ["EDGAR_USER_AGENT"])
    result = _fetch_shares_from_per_filing_xbrl(Company("STZ"))
    assert result is not None, (
        "Live STZ fallback returned None — edgartools `get_facts_by_concept` "
        "may have drifted (period_instant column rename, dei concept rename, "
        "etc.). Re-probe with the script documented on issue #176."
    )
    # STZ outstanding is ~170-180M in the 2025-2026 era; widen the band
    # so this test doesn't flap on a buyback / stock split.
    assert 100_000_000 < result < 500_000_000, (
        f"STZ share-count from live fallback {result:,.0f} outside the "
        "100M-500M expected band — possible duplicate-counting bug or "
        "STZ corporate action."
    )
