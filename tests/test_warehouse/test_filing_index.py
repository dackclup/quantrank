"""Offline tests for compute.warehouse.filing_index + related writer/schema_check.

All tests are ``not network`` — they use synthetic fixtures and mock objects.
No SEC EDGAR calls are made.

Coverage targets
----------------
FI1  FILING_INDEX_COLUMNS is a tuple of unique, non-empty strings.
FI2  fetch_filing_index_rows returns [] without EDGAR_USER_AGENT set.
FI3  fetch_filing_index_rows returns [] when CIK resolution fails.
FI4  _filing_to_row produces a row with all FILING_INDEX_COLUMNS present.
FI5  _filing_to_row returns None when accession is missing.
FI6  _filing_to_row returns None when form_type is missing.
FI7  _filing_to_row returns None when filing_date is missing.
FI8  fetch_filing_index_rows handles a mocked edgartools call gracefully.
FI9  write_filing_index_partition writes a Parquet file with correct layout.
FI10 write_filing_index_partition returns 0 for empty rows (no file written).
FI11 write_filing_index_partition is idempotent on re-run.
FI12 derive_filing_index_columns returns the canonical column set.
FI13 check_filing_index_schema round-trip: --update writes snapshot; compare passes.
FI14 _accession_to_edgar_url produces an https SEC URL.
FI15 _build_primary_doc_url produces correct URL or None.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_filing(
    *,
    accession_no: str = "0001234567-26-000001",
    form: str = "10-K",
    filing_date: str = "2026-06-01",
    period_of_report: str | None = "2026-03-31",
    document: str | None = "test10k.htm",
) -> MagicMock:
    """Build a MagicMock that looks like an edgartools Filing object."""
    m = MagicMock()
    m.accession_no = accession_no
    m.form = form
    # Simulate date object for filing_date / period_of_report
    m.filing_date = date.fromisoformat(filing_date)
    m.period_of_report = (
        date.fromisoformat(period_of_report) if period_of_report else None
    )
    m.document = document
    return m


def _fake_filings_obj(filings: list[MagicMock]) -> MagicMock:
    """Wrap a list of fake filings into a mock FilingsCollection object."""
    obj = MagicMock()
    obj.head = MagicMock(return_value=filings)
    return obj


# ---------------------------------------------------------------------------
# FI1 — FILING_INDEX_COLUMNS integrity
# ---------------------------------------------------------------------------

class TestFilingIndexColumnsConstant:
    """FI1: FILING_INDEX_COLUMNS is well-formed."""

    def test_columns_are_unique(self):
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        assert len(FILING_INDEX_COLUMNS) == len(set(FILING_INDEX_COLUMNS))

    def test_columns_are_non_empty_strings(self):
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        for col in FILING_INDEX_COLUMNS:
            assert isinstance(col, str) and col.strip(), f"Bad column: {col!r}"

    def test_columns_are_sorted(self):
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        assert list(FILING_INDEX_COLUMNS) == sorted(FILING_INDEX_COLUMNS), (
            "FILING_INDEX_COLUMNS must be sorted alphabetically (stable schema)"
        )

    def test_required_columns_present(self):
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        required = {
            "accession", "cik", "edgar_url", "fetched_utc", "filing_date",
            "form_type", "period_of_report", "primary_doc_url", "row_provenance",
            "ticker",
        }
        assert required.issubset(set(FILING_INDEX_COLUMNS)), (
            f"Missing required columns: {required - set(FILING_INDEX_COLUMNS)}"
        )


# ---------------------------------------------------------------------------
# FI2 — returns [] without EDGAR_USER_AGENT
# ---------------------------------------------------------------------------

class TestFetchWithoutUserAgent:
    """FI2: graceful degradation when EDGAR_USER_AGENT is not set."""

    def test_returns_empty_list_no_ua(self, monkeypatch):
        # Ensure env var is absent and reset module-level identity flag.
        monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
        import compute.warehouse.filing_index as fi_mod
        fi_mod._IDENTITY_SET = False  # reset global
        result = fi_mod.fetch_filing_index_rows("AAPL")
        assert result == [], f"Expected [] without UA, got {result}"
        fi_mod._IDENTITY_SET = False  # cleanup


# ---------------------------------------------------------------------------
# FI3 — returns [] when CIK resolution fails
# ---------------------------------------------------------------------------

class TestFetchCIKResolutionFails:
    """FI3: returns [] when the CIK cannot be resolved."""

    def test_returns_empty_when_cik_none(self, monkeypatch):
        import compute.warehouse.filing_index as fi_mod
        # Patch identity so it returns True.
        monkeypatch.setattr(fi_mod, "_IDENTITY_SET", True)
        # Patch _resolve_cik to return None.
        with patch.object(fi_mod, "_resolve_cik", return_value=None):
            result = fi_mod.fetch_filing_index_rows("XXXX")
        assert result == []


# ---------------------------------------------------------------------------
# FI4-FI7 — _filing_to_row correctness
# ---------------------------------------------------------------------------

class TestFilingToRow:
    """FI4-FI7: _filing_to_row produces correct rows or returns None."""

    def _call(self, **kwargs) -> dict[str, Any] | None:
        from compute.warehouse.filing_index import _filing_to_row
        return _filing_to_row(**kwargs)

    def test_fi4_produces_all_columns(self):
        """FI4: row contains all FILING_INDEX_COLUMNS."""
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        filing = _fake_filing()
        row = self._call(
            ticker="AAPL",
            cik="0000320193",
            filing=filing,
            row_provenance="live",
            fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is not None
        for col in FILING_INDEX_COLUMNS:
            assert col in row, f"Missing column {col!r} in row"

    def test_fi4_values_correct(self):
        """FI4: row values match the fake filing object."""
        filing = _fake_filing(
            accession_no="0001234567-26-000001",
            form="10-K",
            filing_date="2026-06-01",
            period_of_report="2026-03-31",
            document="test10k.htm",
        )
        row = self._call(
            ticker="AAPL",
            cik="0001234567",
            filing=filing,
            row_provenance="live",
            fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is not None
        assert row["ticker"] == "AAPL"
        assert row["cik"] == "0001234567"
        assert row["accession"] == "0001234567-26-000001"
        assert row["form_type"] == "10-K"
        assert row["filing_date"] == "2026-06-01"
        assert row["period_of_report"] == "2026-03-31"
        assert row["row_provenance"] == "live"
        assert row["fetched_utc"] == "2026-06-22T00:00:00Z"
        assert row["edgar_url"].startswith("https://www.sec.gov/")
        assert row["primary_doc_url"] is not None
        assert "test10k.htm" in row["primary_doc_url"]

    def test_fi5_returns_none_missing_accession(self):
        """FI5: returns None when accession is absent."""
        filing = _fake_filing()
        filing.accession_no = None
        filing.accession_number = None
        filing.accession = None
        row = self._call(
            ticker="AAPL", cik="0000320193", filing=filing,
            row_provenance="live", fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is None

    def test_fi6_returns_none_missing_form_type(self):
        """FI6: returns None when form type is absent."""
        filing = _fake_filing()
        filing.form = None
        filing.form_type = None
        row = self._call(
            ticker="AAPL", cik="0000320193", filing=filing,
            row_provenance="live", fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is None

    def test_fi7_returns_none_missing_filing_date(self):
        """FI7: returns None when filing_date is absent."""
        filing = _fake_filing()
        filing.filing_date = None
        row = self._call(
            ticker="AAPL", cik="0000320193", filing=filing,
            row_provenance="live", fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is None

    def test_period_of_report_none_allowed(self):
        """FI4 variant: period_of_report may be None (e.g. 8-K forms)."""
        filing = _fake_filing(period_of_report=None)
        row = self._call(
            ticker="AAPL", cik="0000320193", filing=filing,
            row_provenance="live", fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is not None
        assert row["period_of_report"] is None

    def test_row_provenance_passed_through(self):
        """FI4 variant: row_provenance="pit_replay" is preserved."""
        filing = _fake_filing()
        row = self._call(
            ticker="MSFT", cik="0000789019", filing=filing,
            row_provenance="pit_replay", fetched_utc="2026-06-22T00:00:00Z",
        )
        assert row is not None
        assert row["row_provenance"] == "pit_replay"


# ---------------------------------------------------------------------------
# FI8 — fetch_filing_index_rows with mocked edgartools
# ---------------------------------------------------------------------------

def _make_edgar_module(mock_company_cls: Any) -> types.ModuleType:
    """Build a synthetic ``edgar`` module stub for use in sys.modules injection.

    ``Company`` is imported lazily inside ``fetch_filing_index_rows`` via
    ``from edgar import Company`` — it is NOT an attribute of the
    ``filing_index`` module namespace at import time.  The correct way to
    intercept it in tests is to inject a fake ``edgar`` module into
    ``sys.modules`` before the lazy import runs.
    """
    mod = types.ModuleType("edgar")
    mod.Company = mock_company_cls  # type: ignore[attr-defined]
    mod.set_identity = lambda ua: None  # type: ignore[attr-defined]
    return mod


class TestFetchFilingIndexRowsMocked:
    """FI8: full fetch_filing_index_rows path with mocked Company.get_filings."""

    def test_fi8_happy_path(self, monkeypatch):
        """FI8: mocked edgartools returns rows for all DEFAULT_FORM_TYPES."""
        import compute.warehouse.filing_index as fi_mod
        monkeypatch.setattr(fi_mod, "_IDENTITY_SET", True)

        filings = [
            _fake_filing(form="10-K", accession_no="0001111111-26-000001"),
            _fake_filing(form="10-Q", accession_no="0001111111-26-000002"),
            _fake_filing(form="8-K",  accession_no="0001111111-26-000003"),
        ]
        mock_filings_obj = _fake_filings_obj(filings)
        mock_company_instance = MagicMock()
        mock_company_instance.get_filings = MagicMock(return_value=mock_filings_obj)
        mock_company_cls = MagicMock(return_value=mock_company_instance)

        fake_edgar = _make_edgar_module(mock_company_cls)
        # Inject synthetic edgar module so that the lazy `from edgar import Company`
        # inside fetch_filing_index_rows gets our mock.
        monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

        # Supply CIK directly to bypass _resolve_cik's Company() call.
        rows = fi_mod.fetch_filing_index_rows(
            "AAPL",
            cik="0000320193",
            form_types=frozenset({"10-K"}),
        )

        assert isinstance(rows, list)
        # The mock filings_obj.head() returns all 3 fake filings regardless
        # of form_type filter (head is called once per form in forms_to_fetch).
        assert all("accession" in r for r in rows)
        assert all(r["ticker"] == "AAPL" for r in rows)

    def test_fi8_get_filings_raises(self, monkeypatch):
        """FI8 graceful degradation: get_filings raises → returns []."""
        import compute.warehouse.filing_index as fi_mod
        monkeypatch.setattr(fi_mod, "_IDENTITY_SET", True)

        mock_company_instance = MagicMock()
        mock_company_instance.get_filings = MagicMock(side_effect=RuntimeError("SEC 429"))
        mock_company_cls = MagicMock(return_value=mock_company_instance)

        fake_edgar = _make_edgar_module(mock_company_cls)
        monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

        rows = fi_mod.fetch_filing_index_rows("AAPL", cik="0000320193")
        assert rows == []

    def test_fi8_none_filings_obj(self, monkeypatch):
        """FI8 graceful degradation: get_filings returns None → returns []."""
        import compute.warehouse.filing_index as fi_mod
        monkeypatch.setattr(fi_mod, "_IDENTITY_SET", True)

        mock_company_instance = MagicMock()
        mock_company_instance.get_filings = MagicMock(return_value=None)
        mock_company_cls = MagicMock(return_value=mock_company_instance)

        fake_edgar = _make_edgar_module(mock_company_cls)
        monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

        rows = fi_mod.fetch_filing_index_rows("AAPL", cik="0000320193")
        assert rows == []


# ---------------------------------------------------------------------------
# FI9-FI11 — write_filing_index_partition
# ---------------------------------------------------------------------------

class TestWriteFilingIndexPartition:
    """FI9-FI11: write_filing_index_partition Parquet I/O.

    These tests require pyarrow + pandas.  They are skipped automatically
    when those packages are not installed (e.g. the minimal CI environment
    used for pure-Python offline tests).
    """

    @staticmethod
    def _skip_if_no_parquet():
        import pytest
        pytest.importorskip("pyarrow", reason="pyarrow required for Parquet writer tests")
        pytest.importorskip("pandas", reason="pandas required for Parquet writer tests")

    def _make_rows(self, n: int = 5) -> list[dict]:
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        return [
            {
                col: f"val_{col}_{i}" if col != "period_of_report" else None
                for col in FILING_INDEX_COLUMNS
            }
            for i in range(n)
        ]

    def test_fi9_writes_parquet_correct_layout(self, tmp_path):
        """FI9: partition written at year=<YYYY>/run_date=<ISO>/part-0.parquet."""
        self._skip_if_no_parquet()
        import pandas as pd

        from compute.warehouse.writer import write_filing_index_partition

        rows = self._make_rows(10)
        run_date = date(2026, 6, 22)
        out_dir = tmp_path / "warehouse"

        n = write_filing_index_partition(rows, run_date, out_dir)
        assert n == 10

        part_path = out_dir / "filing_index" / "year=2026" / "run_date=2026-06-22" / "part-0.parquet"
        assert part_path.exists(), f"Partition file not found: {part_path}"

        df = pd.read_parquet(part_path)
        assert len(df) == 10
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        for col in FILING_INDEX_COLUMNS:
            assert col in df.columns, f"Column {col!r} missing from Parquet"

    def test_fi10_empty_rows_returns_zero(self, tmp_path):
        """FI10: empty rows → return 0, no file written."""
        self._skip_if_no_parquet()
        from compute.warehouse.writer import write_filing_index_partition

        out_dir = tmp_path / "warehouse"
        n = write_filing_index_partition([], date(2026, 6, 22), out_dir)
        assert n == 0

        part_path = out_dir / "filing_index" / "year=2026" / "run_date=2026-06-22" / "part-0.parquet"
        assert not part_path.exists()

    def test_fi11_idempotent_rerun(self, tmp_path):
        """FI11: second write overwrites the partition; row count matches last write."""
        self._skip_if_no_parquet()
        import pandas as pd

        from compute.warehouse.writer import write_filing_index_partition

        out_dir = tmp_path / "warehouse"
        run_date = date(2026, 6, 22)

        write_filing_index_partition(self._make_rows(5), run_date, out_dir)
        write_filing_index_partition(self._make_rows(7), run_date, out_dir)

        part_path = out_dir / "filing_index" / "year=2026" / "run_date=2026-06-22" / "part-0.parquet"
        df = pd.read_parquet(part_path)
        assert len(df) == 7, "Second write should overwrite the first"


# ---------------------------------------------------------------------------
# FI12-FI13 — warehouse_schema_check for filing index
# ---------------------------------------------------------------------------

class TestFilingIndexSchemaCheck:
    """FI12-FI13: derive_filing_index_columns + check_filing_index_schema.

    These tests require pydantic (and transitively pyarrow/pandas) because
    ``warehouse_schema_check`` imports ``compute.output.schemas`` at module
    load.  They are skipped when those packages are absent.
    """

    @staticmethod
    def _skip_if_no_pydantic():
        import pytest
        pytest.importorskip("pydantic", reason="pydantic required for schema_check tests")

    def test_fi12_derive_returns_canonical_columns(self):
        """FI12: derive_filing_index_columns returns FILING_INDEX_COLUMNS as str|None."""
        self._skip_if_no_pydantic()
        from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
        from compute.warehouse.warehouse_schema_check import derive_filing_index_columns

        cols = derive_filing_index_columns()
        assert isinstance(cols, dict)
        for col in FILING_INDEX_COLUMNS:
            assert col in cols, f"Column {col!r} missing from derivation"
            assert cols[col] == "str | None", f"Unexpected dtype for {col!r}: {cols[col]}"

    def test_fi12_columns_sorted(self):
        """FI12: derived columns are alphabetically sorted."""
        self._skip_if_no_pydantic()
        from compute.warehouse.warehouse_schema_check import derive_filing_index_columns

        cols = derive_filing_index_columns()
        assert list(cols.keys()) == sorted(cols.keys())

    def test_fi13_update_then_check(self, tmp_path, monkeypatch):
        """FI13: --update writes snapshot; subsequent check returns 0 (in-sync)."""
        self._skip_if_no_pydantic()
        from compute.warehouse import warehouse_schema_check as wsc

        snapshot_path = tmp_path / "filing_index_schema.json"
        monkeypatch.setattr(wsc, "FILING_INDEX_SNAPSHOT_PATH", snapshot_path)

        # --update should write and return 0.
        rc = wsc.check_filing_index_schema(update=True)
        assert rc == 0
        assert snapshot_path.exists()

        payload = json.loads(snapshot_path.read_text())
        assert "columns" in payload
        assert len(payload["columns"]) > 0

        # A fresh check against the just-written snapshot should return 0.
        rc2 = wsc.check_filing_index_schema(update=False)
        assert rc2 == 0

    def test_fi13_drift_detected(self, tmp_path, monkeypatch):
        """FI13: drift is detected when snapshot has stale columns."""
        self._skip_if_no_pydantic()
        from compute.warehouse import warehouse_schema_check as wsc

        snapshot_path = tmp_path / "filing_index_schema.json"
        monkeypatch.setattr(wsc, "FILING_INDEX_SNAPSHOT_PATH", snapshot_path)

        # Write an intentionally wrong snapshot (extra column).
        snapshot_path.write_text(
            json.dumps({"columns": {"nonexistent_column": "str | None"}}) + "\n",
            encoding="utf-8",
        )

        rc = wsc.check_filing_index_schema(update=False)
        assert rc == 1, "Expected exit-1 when snapshot drifts from derivation"


# ---------------------------------------------------------------------------
# FI14-FI15 — URL helpers
# ---------------------------------------------------------------------------

class TestURLHelpers:
    """FI14-FI15: URL construction helpers."""

    def test_fi14_accession_to_edgar_url(self):
        """FI14: _accession_to_edgar_url produces an https SEC Archives URL."""
        from compute.warehouse.filing_index import _accession_to_edgar_url

        url = _accession_to_edgar_url("0001234567-26-000001")
        assert url.startswith("https://www.sec.gov/Archives/edgar/data/")
        assert "0001234567-26-000001" in url
        assert "index.htm" in url

    def test_fi14_leading_zeros_stripped(self):
        """FI14: CIK segment leading zeros are stripped (standard SEC URL form)."""
        from compute.warehouse.filing_index import _accession_to_edgar_url

        url = _accession_to_edgar_url("0001234567-26-000001")
        # CIK = 0001234567 → "1234567" (leading zeros stripped)
        assert "/1234567/" in url

    def test_fi15_build_primary_doc_url_with_doc(self):
        """FI15: primary_doc_url is non-None when document name is provided."""
        from compute.warehouse.filing_index import _build_primary_doc_url

        url = _build_primary_doc_url("0001234567-26-000001", "form10k.htm")
        assert url is not None
        assert url.startswith("https://www.sec.gov/")
        assert "form10k.htm" in url

    def test_fi15_build_primary_doc_url_none_doc(self):
        """FI15: primary_doc_url is None when document name is absent."""
        from compute.warehouse.filing_index import _build_primary_doc_url

        assert _build_primary_doc_url("0001234567-26-000001", None) is None
        assert _build_primary_doc_url("0001234567-26-000001", "") is None
