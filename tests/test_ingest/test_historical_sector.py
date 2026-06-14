"""Tests for ``compute.ingest.historical_sector`` and
``scripts.backfill_historical_sector``.

All tests are offline — no network calls, no real parquet on disk.
The parquet is mocked in-memory using ``unittest.mock.patch``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from compute.ingest.historical_sector import (
    historical_sector_parquet_stats,
    sector_at,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_sector_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal in-memory DataFrame matching the parquet schema."""
    return pd.DataFrame(
        rows,
        columns=["ticker", "sector", "sub_industry", "rebalance_date", "revision_timestamp", "sector_source"],
    )


@pytest.fixture(autouse=True)
def _reset_module_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the module-level mtime cache between tests."""
    import compute.ingest.historical_sector as mod
    monkeypatch.setattr(mod, "_CACHE", None)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _patch_load_parquet(rows: list[dict] | None):
    """Context manager: monkey-patch ``_load_parquet`` to return rows or None."""
    import compute.ingest.historical_sector as mod
    df = _make_sector_df(rows) if rows is not None else None
    return patch.object(mod, "_load_parquet", return_value=df)


# ---------------------------------------------------------------------------
# Parquet absent — fallback to today's sector
# ---------------------------------------------------------------------------

def test_sector_at_parquet_absent_returns_fallback() -> None:
    """When the parquet is absent, sector_at falls back to today's Wikipedia sector."""
    fake_members = pd.DataFrame([{"ticker": "AAPL", "sector": "Information Technology"}])
    with _patch_load_parquet(None):
        with patch("compute.ingest.universe.get_sp500_constituents", return_value=fake_members):
            result = sector_at("AAPL", as_of_date=date(2018, 3, 15))
    assert result == "Information Technology"


def test_sector_at_parquet_absent_unknown_ticker_returns_unknown() -> None:
    """Unknown ticker not in today's universe returns 'Unknown'."""
    empty_members = pd.DataFrame(columns=["ticker", "sector"])
    with _patch_load_parquet(None):
        with patch("compute.ingest.universe.get_sp500_constituents", return_value=empty_members):
            result = sector_at("ZZZZ", as_of_date=date(2020, 1, 1))
    assert result == "Unknown"


# ---------------------------------------------------------------------------
# Parquet present — closest-prior rebalance date lookup
# ---------------------------------------------------------------------------

_SAMPLE_SECTOR_ROWS = [
    {
        "ticker": "T",
        "sector": "Telecommunication Services",  # pre-2018 name
        "sub_industry": "Integrated Telecommunication Services",
        "rebalance_date": "2017-02-15",
        "revision_timestamp": "2017-02-14T10:00:00Z",
        "sector_source": "wikipedia_pit",
    },
    {
        "ticker": "T",
        "sector": "Communication Services",  # post-2018 rename
        "sub_industry": "Integrated Telecommunication Services",
        "rebalance_date": "2019-05-14",
        "revision_timestamp": "2019-05-13T10:00:00Z",
        "sector_source": "wikipedia_pit",
    },
    {
        "ticker": "AAPL",
        "sector": "Information Technology",
        "sub_industry": "Technology Hardware",
        "rebalance_date": "2017-02-15",
        "revision_timestamp": "2017-02-14T10:00:00Z",
        "sector_source": "wikipedia_pit",
    },
    {
        "ticker": "AAPL",
        "sector": "Information Technology",
        "sub_industry": "Technology Hardware",
        "rebalance_date": "2019-05-14",
        "revision_timestamp": "2019-05-13T10:00:00Z",
        "sector_source": "wikipedia_pit",
    },
]


def test_sector_at_returns_closest_prior_rebalance() -> None:
    """sector_at picks the rebalance_date closest to (and <= ) as_of_date."""
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        # as_of_date is between the two rebalance dates — should pick 2017-02-15
        result = sector_at("T", as_of_date=date(2018, 6, 1))
    assert result == "Telecommunication Services"


def test_sector_at_returns_later_rebalance_after_it() -> None:
    """After the 2019 rebalance date, the newer sector is used."""
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        result = sector_at("T", as_of_date=date(2020, 1, 1))
    assert result == "Communication Services"


def test_sector_at_exact_rebalance_date_match() -> None:
    """Boundary: as_of_date == rebalance_date returns that rebalance's sector."""
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        result = sector_at("T", as_of_date=date(2019, 5, 14))
    assert result == "Communication Services"


def test_sector_at_before_any_rebalance_falls_back() -> None:
    """When as_of_date is before all rebalance dates in the parquet, fall back."""
    fake_members = pd.DataFrame([{"ticker": "T", "sector": "Telecommunication Services"}])
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        with patch("compute.ingest.universe.get_sp500_constituents", return_value=fake_members):
            result = sector_at("T", as_of_date=date(2015, 1, 1))
    # No rows before 2015 in our sample data → falls back to today's sector
    assert result == "Telecommunication Services"


def test_sector_at_ticker_not_in_parquet_falls_back() -> None:
    """Ticker with no rows in the parquet uses today's-sector fallback."""
    fake_members = pd.DataFrame([{"ticker": "MSFT", "sector": "Information Technology"}])
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        with patch("compute.ingest.universe.get_sp500_constituents", return_value=fake_members):
            result = sector_at("MSFT", as_of_date=date(2020, 1, 1))
    assert result == "Information Technology"


def test_sector_at_pre_2018_name_stored_as_is() -> None:
    """'Telecommunication Services' is stored as-is (not renamed to 'Communication Services')."""
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        result = sector_at("T", as_of_date=date(2017, 6, 1))
    assert result == "Telecommunication Services"


def test_sector_at_multiple_tickers_isolation() -> None:
    """Sector lookup for one ticker does not bleed into another."""
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        aapl = sector_at("AAPL", as_of_date=date(2017, 6, 1))
        att = sector_at("T", as_of_date=date(2017, 6, 1))
    assert aapl == "Information Technology"
    assert att == "Telecommunication Services"


# ---------------------------------------------------------------------------
# historical_sector_parquet_stats
# ---------------------------------------------------------------------------

def test_parquet_stats_when_absent() -> None:
    with _patch_load_parquet(None):
        stats = historical_sector_parquet_stats()
    assert stats["parquet_present"] is False
    assert stats["row_count"] == 0
    assert stats["rebalance_dates"] == []


def test_parquet_stats_when_present() -> None:
    with _patch_load_parquet(_SAMPLE_SECTOR_ROWS):
        stats = historical_sector_parquet_stats()
    assert stats["parquet_present"] is True
    assert stats["row_count"] == len(_SAMPLE_SECTOR_ROWS)
    assert "2017-02-15" in stats["rebalance_dates"]
    assert "2019-05-14" in stats["rebalance_dates"]


# ---------------------------------------------------------------------------
# Parser robustness: wikitext header variants
# ---------------------------------------------------------------------------

def test_parse_sector_table_gics_sector_header() -> None:
    """Standard 'GICS Sector' column header is parsed correctly."""
    from scripts.backfill_historical_sector import _parse_sector_table

    html = """
    <table class="wikitable">
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>
          <th>GICS Sub-Industry</th></tr>
      <tr><td>AAPL</td><td>Apple Inc.</td><td>Information Technology</td>
          <td>Technology Hardware</td></tr>
      <tr><td>JPM</td><td>JPMorgan Chase</td><td>Financials</td>
          <td>Diversified Banks</td></tr>
    </table>
    """
    df = _parse_sector_table(html)
    assert df is not None
    assert len(df) == 2
    aapl = df.loc[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["sector"] == "Information Technology"
    assert aapl["sub_industry"] == "Technology Hardware"


def test_parse_sector_table_bare_sector_header() -> None:
    """Older revisions used 'Sector' instead of 'GICS Sector'."""
    from scripts.backfill_historical_sector import _parse_sector_table

    html = """
    <table class="wikitable">
      <tr><th>Symbol</th><th>Security</th><th>Sector</th></tr>
      <tr><td>T</td><td>AT&amp;T</td><td>Telecommunication Services</td></tr>
    </table>
    """
    df = _parse_sector_table(html)
    assert df is not None
    att = df.loc[df["ticker"] == "T"].iloc[0]
    assert att["sector"] == "Telecommunication Services"
    # No sub-industry column → empty string
    assert att["sub_industry"] == ""


def test_parse_sector_table_no_wikitable_returns_none() -> None:
    """HTML with no .wikitable table returns None gracefully."""
    from scripts.backfill_historical_sector import _parse_sector_table

    html = "<html><body><p>No table here.</p></body></html>"
    result = _parse_sector_table(html)
    assert result is None


def test_parse_sector_table_brk_b_ticker_normalization() -> None:
    """BRK.B ticker is normalized to BRK-B."""
    from scripts.backfill_historical_sector import _parse_sector_table

    html = """
    <table class="wikitable">
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>
      <tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td></tr>
    </table>
    """
    df = _parse_sector_table(html)
    assert df is not None
    assert "BRK-B" in df["ticker"].values


def test_parse_sector_table_deduplicates_tickers() -> None:
    """Duplicate ticker rows (e.g. BRK.A + BRK.B mapped to same symbol) keep first."""
    from scripts.backfill_historical_sector import _parse_sector_table

    html = """
    <table class="wikitable">
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>
      <tr><td>AAPL</td><td>Apple Inc.</td><td>Information Technology</td></tr>
      <tr><td>AAPL</td><td>Apple Inc. (dupe)</td><td>Information Technology</td></tr>
    </table>
    """
    df = _parse_sector_table(html)
    assert df is not None
    assert len(df[df["ticker"] == "AAPL"]) == 1


# ---------------------------------------------------------------------------
# backfill_historical_sector.run() — revision-absent path (no crash contract)
# ---------------------------------------------------------------------------
#
# Requirement from the PIT-backfill task (2026-06-13): when the MediaWiki
# API returns an empty revisions list for a given rebalance date, run() must
# skip that date gracefully — no crash, no partial rows, no parquet written.
# This pins the graceful-degradation contract at the run() level.
#
# Mock boundary: _fetch_revision_before (replaces the network call).
# ---------------------------------------------------------------------------

def _make_wiki_session_mock() -> MagicMock:
    """Return a MagicMock that stands in for a requests.Session."""
    return MagicMock()


def test_run_empty_revisions_no_crash_no_parquet(tmp_path: Path) -> None:
    """When _fetch_revision_before returns None (empty revisions), run() must
    not crash and must produce no parquet output for that date.

    This tests the path: _fetch_revision_before → None → date skipped.
    The None return is what _fetch_revision_before emits when the MediaWiki
    API revisions list is empty (see the ``if not revisions`` guard in
    backfill_historical_sector.py).
    """
    from scripts.backfill_historical_sector import run

    out = tmp_path / "sector.parquet"
    # Single rebalance date — one call to _fetch_revision_before → None.
    start = date(2024, 5, 14)   # 2024-Q1-end + 45 days
    end = date(2024, 5, 14)

    with patch("scripts.backfill_historical_sector._fetch_revision_before", return_value=None):
        # Must not raise
        run(start=start, end=end, out=out)

    # No rows collected → parquet must NOT exist
    assert not out.exists(), (
        "parquet must not be written when all rebalance dates return empty revisions"
    )


def test_run_revision_absent_multiple_dates_all_skipped(tmp_path: Path) -> None:
    """All rebalance dates returning None → run() skips every date, no parquet.

    Ensures the no-op path is stable with more than one date in the window.
    """
    from scripts.backfill_historical_sector import run

    out = tmp_path / "sector.parquet"
    # Two-quarter window that generates at least 2 rebalance dates
    start = date(2024, 2, 13)   # 2023-Q4-end (2023-12-31) + 45d = 2024-02-14
    end = date(2024, 5, 15)     # 2024-Q1-end (2024-03-31) + 45d = 2024-05-15

    with patch("scripts.backfill_historical_sector._fetch_revision_before", return_value=None):
        run(start=start, end=end, out=out)

    assert not out.exists(), (
        "parquet must not be written when all rebalance dates have no revision"
    )


def test_run_partial_revision_absent_only_good_date_written(tmp_path: Path) -> None:
    """When one date fails (None) and one succeeds, only the successful date is written.

    This pins the per-date skip contract — a single bad date must not prevent
    data from good dates from being written.
    """
    from scripts.backfill_historical_sector import run

    good_html = """
    <table class="wikitable">
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>
      <tr><td>AAPL</td><td>Apple Inc.</td><td>Information Technology</td></tr>
    </table>
    """
    out = tmp_path / "sector.parquet"
    # Two rebalance dates in a two-quarter window
    start = date(2024, 2, 13)
    end = date(2024, 5, 15)

    # First call → None (empty revisions); second call → (wikitext, timestamp).
    def _fake_fetch(session, as_of_date):  # noqa: ARG001
        if as_of_date.month < 5:
            return None  # first date: no revision
        return ("fake wikitext", "2024-05-14T00:00:00Z")

    with (
        patch("scripts.backfill_historical_sector._fetch_revision_before", side_effect=_fake_fetch),
        patch(
            "scripts.backfill_historical_sector._wikitext_to_html",
            return_value=good_html,
        ),
    ):
        run(start=start, end=end, out=out)

    assert out.exists(), "parquet must be written for the one date that returned a revision"
    df = pd.read_parquet(out)
    assert len(df) >= 1, f"expected at least 1 row, got {len(df)}"
    assert "AAPL" in df["ticker"].values
