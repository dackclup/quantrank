"""Offline coverage for ``compute.ingest.historical_8k._load_parquet`` and friends.

The PIT Item 4.02 reader degrades gracefully when its parquet is absent
(returns ``[]`` / ``0``) — the absent path is exercised by the broader suite,
but the PRESENT-parquet read / mtime-cache / corrupt-file branches
(``_load_parquet`` body, lines ~74-95) were uncovered because the data file
does not ship in the repo. These tests point the module path constant at a
``tmp_path`` parquet and reset the module cache so the real read path runs.

All offline: no network, no SEC, no real ``data/`` file touched.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from compute.ingest import historical_8k as mod

_COLUMNS = ["ticker", "cik", "accession_number", "filing_date"]


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    """Write a synthetic item402-history parquet at *path*."""
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df.to_parquet(path)
    return path


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean module cache."""
    monkeypatch.setattr(mod, "_CACHE", None)


# ---------------------------------------------------------------------------
# _load_parquet — present / cache-hit / corrupt
# ---------------------------------------------------------------------------


def test_load_parquet_present_returns_dataframe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present, readable parquet is loaded into a DataFrame and cached."""
    pq = _write_parquet(
        tmp_path / "pit.parquet",
        [{"ticker": "BRK-B", "cik": "0000000123", "accession_number": "0001234567-24-000001", "filing_date": "2024-03-01"}],
    )
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", pq)

    df = mod._load_parquet()

    assert df is not None
    assert len(df) == 1
    assert list(df.columns) == _COLUMNS
    # The mtime cache must now be primed.
    assert mod._CACHE is not None
    assert mod._CACHE[0] == pq.stat().st_mtime


def test_load_parquet_cache_hit_skips_reread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second call with an unchanged mtime returns the cached frame object."""
    pq = _write_parquet(
        tmp_path / "pit.parquet",
        [{"ticker": "AAA", "cik": "0000000001", "accession_number": "0000000001-24-000001", "filing_date": "2024-01-01"}],
    )
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", pq)

    first = mod._load_parquet()
    second = mod._load_parquet()

    assert first is second, "cache hit must return the SAME DataFrame object, not a re-read"


def test_load_parquet_absent_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent parquet returns None (graceful degradation, no raise)."""
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", tmp_path / "does_not_exist.parquet")
    assert mod._load_parquet() is None


def test_load_parquet_corrupt_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present-but-corrupt parquet is swallowed → None (no raise)."""
    corrupt = tmp_path / "corrupt.parquet"
    corrupt.write_bytes(b"this is not a parquet file")
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", corrupt)

    assert mod._load_parquet() is None


# ---------------------------------------------------------------------------
# item402_filings_for — present-parquet filtering + shape
# ---------------------------------------------------------------------------


def test_item402_filings_for_filters_and_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filtering by ticker + before_date returns ascending, correctly-shaped dicts."""
    pq = _write_parquet(
        tmp_path / "pit.parquet",
        [
            {"ticker": "XYZ", "cik": "0000000999", "accession_number": "0000000999-23-000002", "filing_date": "2023-06-15"},
            {"ticker": "XYZ", "cik": "0000000999", "accession_number": "0000000999-22-000001", "filing_date": "2022-01-10"},
            {"ticker": "XYZ", "cik": "0000000999", "accession_number": "0000000999-25-000003", "filing_date": "2025-09-09"},
            {"ticker": "OTHER", "cik": "0000000111", "accession_number": "0000000111-23-000001", "filing_date": "2023-01-01"},
        ],
    )
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", pq)

    result = mod.item402_filings_for("XYZ", date(2024, 1, 1))

    # Only the two XYZ filings on/before 2024-01-01, ascending by date.
    assert [r["filing_date"] for r in result] == ["2022-01-10", "2023-06-15"]
    for r in result:
        assert r["items"] == ["Item 4.02"]
        assert r["item_text_excerpts"] == {}
        assert r["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/")


def test_item402_filings_for_absent_parquet_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", tmp_path / "absent.parquet")
    assert mod.item402_filings_for("XYZ", date(2024, 1, 1)) == []


# ---------------------------------------------------------------------------
# item402_parquet_row_count
# ---------------------------------------------------------------------------


def test_row_count_present_and_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pq = _write_parquet(
        tmp_path / "pit.parquet",
        [
            {"ticker": "A", "cik": "0000000001", "accession_number": "0000000001-24-000001", "filing_date": "2024-01-01"},
            {"ticker": "B", "cik": "0000000002", "accession_number": "0000000002-24-000001", "filing_date": "2024-02-02"},
        ],
    )
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", pq)
    assert mod.item402_parquet_row_count() == 2

    monkeypatch.setattr(mod, "_CACHE", None)
    monkeypatch.setattr(mod, "PIT_ITEM402_PARQUET", tmp_path / "absent.parquet")
    assert mod.item402_parquet_row_count() == 0


# ---------------------------------------------------------------------------
# _accession_to_url — pure helper
# ---------------------------------------------------------------------------


def test_accession_to_url_strips_leading_zeros() -> None:
    url = mod._accession_to_url("0001234567-24-000001")
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/1234567/"
        "000123456724000001/0001234567-24-000001-index.htm"
    )


def test_accession_to_url_all_zero_cik_segment() -> None:
    # A degenerate all-zero CIK segment must not produce an empty path segment.
    url = mod._accession_to_url("0000000000-24-000001")
    assert "/data/0/" in url
