"""Offline coverage for ``compute.ingest.historical_sector``.

The PIT GICS-sector reader degrades gracefully when its parquet is absent
(falls back to today's Wikipedia sector). The PRESENT-parquet read / mtime
cache / corrupt-file branches (``_load_parquet`` body) and the parquet-hit /
fallback paths in ``sector_at`` were uncovered because the data file does not
ship. These tests point the module path constant at a ``tmp_path`` parquet and
stub the Wikipedia fallback so every branch runs offline.

All offline: no network, no real ``data/`` file touched.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from compute.ingest import historical_sector as mod

_COLUMNS = ["ticker", "sector", "sub_industry", "rebalance_date", "revision_timestamp", "sector_source"]


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows, columns=_COLUMNS)
    df.to_parquet(path)
    return path


def _row(ticker: str, sector: str, rebalance_date: str) -> dict:
    return {
        "ticker": ticker,
        "sector": sector,
        "sub_industry": "",
        "rebalance_date": rebalance_date,
        "revision_timestamp": "2024-01-01T00:00:00Z",
        "sector_source": "wikipedia_pit",
    }


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_CACHE", None)


# ---------------------------------------------------------------------------
# _load_parquet — present / cache-hit / absent / corrupt
# ---------------------------------------------------------------------------


def test_load_parquet_present_and_cache_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pq = _write_parquet(tmp_path / "sector.parquet", [_row("AAPL", "Information Technology", "2024-03-01")])
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", pq)

    first = mod._load_parquet()
    assert first is not None and len(first) == 1
    second = mod._load_parquet()
    assert first is second  # mtime cache hit returns the same object


def test_load_parquet_absent_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", tmp_path / "absent.parquet")
    assert mod._load_parquet() is None


def test_load_parquet_corrupt_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corrupt = tmp_path / "corrupt.parquet"
    corrupt.write_bytes(b"not a parquet")
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", corrupt)
    assert mod._load_parquet() is None


# ---------------------------------------------------------------------------
# sector_at — parquet hit / closest-prior / fallback
# ---------------------------------------------------------------------------


def test_sector_at_parquet_hit_returns_closest_prior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The latest rebalance_date on/before as_of_date wins."""
    pq = _write_parquet(
        tmp_path / "sector.parquet",
        [
            _row("MSFT", "Information Technology", "2023-01-01"),
            _row("MSFT", "Financials", "2024-06-01"),  # closest prior to 2024-09
            _row("MSFT", "Energy", "2025-01-01"),  # after as_of — excluded
        ],
    )
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", pq)

    assert mod.sector_at("MSFT", date(2024, 9, 1)) == "Financials"


def test_sector_at_parquet_no_prior_row_uses_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present parquet without a prior-dated row for the ticker → today's-sector fallback."""
    pq = _write_parquet(
        tmp_path / "sector.parquet",
        [_row("NVDA", "Information Technology", "2025-12-31")],  # only AFTER as_of
    )
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", pq)

    fake_members = pd.DataFrame({"ticker": ["NVDA"], "sector": ["Technology Fallback"]})
    monkeypatch.setattr(
        "compute.ingest.universe.get_sp500_constituents", lambda: fake_members
    )

    assert mod.sector_at("NVDA", date(2024, 1, 1)) == "Technology Fallback"


def test_sector_at_absent_parquet_uses_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", tmp_path / "absent.parquet")
    fake_members = pd.DataFrame({"ticker": ["KO"], "sector": ["Consumer Staples"]})
    monkeypatch.setattr(
        "compute.ingest.universe.get_sp500_constituents", lambda: fake_members
    )
    assert mod.sector_at("KO", date(2024, 1, 1)) == "Consumer Staples"


def test_sector_at_fallback_ticker_missing_returns_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both the parquet AND the today's-sector fallback miss → 'Unknown'."""
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", tmp_path / "absent.parquet")
    empty_members = pd.DataFrame({"ticker": [], "sector": []})
    monkeypatch.setattr(
        "compute.ingest.universe.get_sp500_constituents", lambda: empty_members
    )
    assert mod.sector_at("ZZZZ", date(2024, 1, 1)) == "Unknown"


def test_sector_at_fallback_raises_returns_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising fallback is swallowed → 'Unknown' (never propagates)."""
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", tmp_path / "absent.parquet")

    def _boom() -> pd.DataFrame:
        raise RuntimeError("wikipedia down")

    monkeypatch.setattr("compute.ingest.universe.get_sp500_constituents", _boom)
    assert mod.sector_at("ANY", date(2024, 1, 1)) == "Unknown"


# ---------------------------------------------------------------------------
# historical_sector_parquet_stats
# ---------------------------------------------------------------------------


def test_stats_present_reports_rows_and_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pq = _write_parquet(
        tmp_path / "sector.parquet",
        [
            _row("A", "Energy", "2024-01-01"),
            _row("B", "Energy", "2024-04-01"),
            _row("C", "Utilities", "2024-01-01"),
        ],
    )
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", pq)

    stats = mod.historical_sector_parquet_stats()
    assert stats["parquet_present"] is True
    assert stats["row_count"] == 3
    assert stats["rebalance_dates"] == ["2024-01-01", "2024-04-01"]


def test_stats_absent_reports_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "HISTORICAL_SECTOR_PARQUET", tmp_path / "absent.parquet")
    assert mod.historical_sector_parquet_stats() == {
        "parquet_present": False,
        "row_count": 0,
        "rebalance_dates": [],
    }
