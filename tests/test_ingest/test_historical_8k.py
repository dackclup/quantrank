"""Tests for ``compute.ingest.historical_8k``.

All tests are offline — no network calls, no real parquet on disk.
The parquet is mocked in-memory using ``unittest.mock.patch``.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from compute.ingest.historical_8k import (
    item402_filings_for,
    item402_parquet_row_count,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_parquet_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal in-memory DataFrame matching the parquet schema."""
    return pd.DataFrame(rows, columns=["ticker", "cik", "accession_number", "filing_date"])


@pytest.fixture(autouse=True)
def _reset_module_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the module-level mtime cache between tests."""
    import compute.ingest.historical_8k as mod
    monkeypatch.setattr(mod, "_CACHE", None)


# ---------------------------------------------------------------------------
# item402_filings_for — parquet absent
# ---------------------------------------------------------------------------

def test_item402_filings_for_parquet_absent_returns_empty() -> None:
    """When the parquet file does not exist, return [] (graceful degradation)."""
    import compute.ingest.historical_8k as mod

    with patch.object(mod, "_load_parquet", return_value=None):
        result = item402_filings_for("AAPL", before_date=date(2022, 6, 30))
    assert result == []


def test_item402_parquet_row_count_absent_returns_zero() -> None:
    import compute.ingest.historical_8k as mod

    with patch.object(mod, "_load_parquet", return_value=None):
        assert item402_parquet_row_count() == 0


# ---------------------------------------------------------------------------
# item402_filings_for — PIT filter (filing_date <= before_date)
# ---------------------------------------------------------------------------

_SAMPLE_ROWS = [
    {
        "ticker": "GE",
        "cik": "0000040554",
        "accession_number": "0000040554-22-000001",
        "filing_date": "2022-03-15",
    },
    {
        "ticker": "GE",
        "cik": "0000040554",
        "accession_number": "0000040554-23-000002",
        "filing_date": "2023-07-01",
    },
    {
        "ticker": "AAPL",
        "cik": "0000320193",
        "accession_number": "0000320193-21-000005",
        "filing_date": "2021-12-01",
    },
]


def _patch_load_parquet(rows: list[dict]):
    """Context manager: monkey-patch ``_load_parquet`` to return ``rows``."""
    import compute.ingest.historical_8k as mod
    df = _make_parquet_df(rows)
    return patch.object(mod, "_load_parquet", return_value=df)


def test_pit_filter_returns_only_on_or_before_date() -> None:
    """Filings with filing_date > before_date are excluded."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        result = item402_filings_for("GE", before_date=date(2022, 12, 31))
    # The 2022-03-15 filing is <= 2022-12-31 → included
    # The 2023-07-01 filing is > 2022-12-31 → excluded
    assert len(result) == 1
    assert result[0]["filing_date"] == "2022-03-15"
    assert result[0]["items"] == ["Item 4.02"]
    assert "item_text_excerpts" in result[0]


def test_pit_filter_includes_filing_on_exact_cutoff_date() -> None:
    """Boundary: filing_date == before_date is included."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        result = item402_filings_for("GE", before_date=date(2022, 3, 15))
    assert len(result) == 1
    assert result[0]["filing_date"] == "2022-03-15"


def test_pit_filter_all_after_cutoff_returns_empty() -> None:
    """When all filings are after before_date, return []."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        result = item402_filings_for("GE", before_date=date(2020, 1, 1))
    assert result == []


def test_pit_filter_wrong_ticker_returns_empty() -> None:
    """Ticker not in the parquet returns []."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        result = item402_filings_for("MSFT", before_date=date(2023, 12, 31))
    assert result == []


def test_pit_filter_multiple_filings_all_before_cutoff() -> None:
    """When multiple filings exist before cutoff, all are returned."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        result = item402_filings_for("GE", before_date=date(2024, 1, 1))
    assert len(result) == 2
    dates = [r["filing_date"] for r in result]
    assert "2022-03-15" in dates
    assert "2023-07-01" in dates


def test_pit_filter_correct_ticker_isolation() -> None:
    """Results for one ticker do not bleed into another."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        aapl = item402_filings_for("AAPL", before_date=date(2024, 1, 1))
        ge = item402_filings_for("GE", before_date=date(2024, 1, 1))
    assert all(r["filing_date"] == "2021-12-01" for r in aapl)
    assert all("2022" in r["filing_date"] or "2023" in r["filing_date"] for r in ge)


def test_filing_dict_shape() -> None:
    """Each returned dict matches the shape check_non_reliance's _check_item expects."""
    with _patch_load_parquet(_SAMPLE_ROWS):
        result = item402_filings_for("AAPL", before_date=date(2022, 1, 1))
    assert len(result) == 1
    row = result[0]
    assert "filing_date" in row
    assert "filing_url" in row
    assert "items" in row
    assert "item_text_excerpts" in row
    assert row["items"] == ["Item 4.02"]
    assert isinstance(row["item_text_excerpts"], dict)


# ---------------------------------------------------------------------------
# item402_parquet_row_count
# ---------------------------------------------------------------------------

def test_parquet_row_count_when_present() -> None:
    import compute.ingest.historical_8k as mod
    df = _make_parquet_df(_SAMPLE_ROWS)
    with patch.object(mod, "_load_parquet", return_value=df):
        assert item402_parquet_row_count() == len(_SAMPLE_ROWS)


def test_parquet_row_count_none_returns_zero() -> None:
    import compute.ingest.historical_8k as mod
    with patch.object(mod, "_load_parquet", return_value=None):
        assert item402_parquet_row_count() == 0


# ---------------------------------------------------------------------------
# Graceful degradation: _load_parquet raises unexpectedly
# ---------------------------------------------------------------------------

def test_item402_filings_for_exception_in_load_returns_empty() -> None:
    """If the underlying DataFrame raises during filtering, return [] not crash."""
    import compute.ingest.historical_8k as mod

    class BadDF:
        """A fake DataFrame that raises on any column access."""
        def __len__(self) -> int:
            return 1

    with patch.object(mod, "_load_parquet", return_value=BadDF()):
        result = item402_filings_for("AAPL", before_date=date(2022, 1, 1))
    # Should return [] and not raise
    assert result == []
