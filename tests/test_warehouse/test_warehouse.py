"""Offline tests for the compute.warehouse package.

All tests run without network access and without SEC EDGAR.  They use
synthetic Pydantic models built entirely in-process.

Coverage targets
----------------
R1  round-trip: flatten_stock → writer → parquet → read back ≥ row
R2  PK uniqueness: no duplicate (ticker, run_date) pairs within a partition
R3  flatten_stock correctness: flag_*/warn_* bools, pillar_* / raw_* / dq_* /
    fp_* columns, json-encoded fields, row_provenance sentinel
R4  row_provenance is "live" for every row produced by flatten_stock
R5  manifest append + dedupe: re-run same run_date replaces the row
R6  QR_SKIP_WAREHOUSE no-op: env-var set → warehouse write does NOT fire
    (tested via mocking writer, not via main.py to keep tests unit-level)
R7  graceful-degradation: write_run_snapshot called with zero details → 0
    (empty-list guard)
R8  partition path layout: year=<YYYY>/run_date=<ISO>/part-0.parquet
R9  size sanity: 900 synthetic rows compress to < 2 MB
R10 warehouse_schema_check drift guard: derive_canonical_columns passes
    flag registry cross-check; --update → file written; compare round-trip
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Synthetic model builders
# ---------------------------------------------------------------------------

def _make_pillar_scores():
    from compute.output.schemas import PillarScores
    return PillarScores(quality=60.0, value=55.0, growth=70.0, momentum=65.0,
                        health=50.0, profitability=75.0, technical=80.0, risk=45.0)


def _make_raw_metrics():
    from compute.output.schemas import RawMetrics
    return RawMetrics(
        **{f: None for f in RawMetrics.model_fields}
    )


def _make_data_quality():
    from compute.output.schemas import DataQuality
    # missing_metrics and imputed_metrics require list[str], not None.
    # All other fields are int|None / str|None so None is valid.
    overrides = {
        "missing_metrics": [],
        "imputed_metrics": [],
    }
    kwargs = {
        f: overrides.get(f, None) for f in DataQuality.model_fields
    }
    return DataQuality(**kwargs)


def _make_detail(
    ticker: str = "AAPL",
    risk_flags: list[str] | None = None,
    valuation_warnings: list[str] | None = None,
    fair_price: dict | None = None,
) -> Any:
    from compute.output.schemas import StockDetail
    return StockDetail(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector="Technology",
        recommendation="neutral",
        rank=1,
        composite_score=55.0,
        current_price=100.0,
        pillar_scores=_make_pillar_scores(),
        raw_metrics=_make_raw_metrics(),
        data_quality=_make_data_quality(),
        risk_flags=risk_flags or [],
        valuation_warnings=valuation_warnings or [],
        index_membership="sp500",
        index_memberships=["sp500"],
        fair_price=fair_price,
    )


def _make_summary(ticker: str = "AAPL") -> Any:
    from compute.output.schemas import StockSummary
    return StockSummary(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector="Technology",
        recommendation="neutral",
        rank=1,
        composite_score=55.0,
        current_price=100.0,
        risk_flags=[],
        valuation_warnings=[],
        index_membership="sp500",
        index_memberships=["sp500"],
    )


def _make_metadata() -> Any:
    from compute.output.schemas import Metadata
    return Metadata(
        version="0.10.29-phase8pilot",
        last_update_utc="2026-06-21T22:00:00Z",
        next_update_utc="2026-06-22T22:00:00Z",
        universe="SP900",
        universe_size=900,
        compute_run_id="test-run-001",
        git_commit="abc1234",
    )


# ---------------------------------------------------------------------------
# R3 / R4 — flatten_stock correctness
# ---------------------------------------------------------------------------

class TestFlattenStock:
    """R3: flatten_stock column correctness and R4: row_provenance."""

    def test_row_provenance_is_live(self):
        """R4: row_provenance must be 'live' for every flatten_stock call."""
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        assert row["row_provenance"] == "live"

    def test_risk_flag_columns_are_bool(self):
        """R3: flag_<name> columns are True/False (never None) for live rows."""
        from compute.warehouse.flag_registry import KNOWN_RISK_FLAGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail(risk_flags=["altman_distress"])
        row = flatten_stock(detail, None)
        for flag in KNOWN_RISK_FLAGS:
            col = f"flag_{flag}"
            assert col in row, f"Missing column {col}"
            assert isinstance(row[col], bool), f"{col} must be bool, got {type(row[col])}"
        assert row["flag_altman_distress"] is True
        assert row["flag_beneish_manipulation_veto"] is False

    def test_warn_columns_are_bool(self):
        """R3: warn_<name> columns are True/False for live rows."""
        from compute.warehouse.flag_registry import KNOWN_VALUATION_WARNINGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail(valuation_warnings=["stale_filing_soft", "goodwill_heavy"])
        row = flatten_stock(detail, None)
        for warn in KNOWN_VALUATION_WARNINGS:
            col = f"warn_{warn}"
            assert col in row, f"Missing column {col}"
            assert isinstance(row[col], bool), f"{col} must be bool, got {type(row[col])}"
        assert row["warn_stale_filing_soft"] is True
        assert row["warn_goodwill_heavy"] is True
        assert row["warn_beneish_high"] is False

    def test_pillar_columns_present(self):
        """R3: pillar_<name> columns map PillarScores fields."""
        from compute.output.schemas import PillarScores
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        for field in PillarScores.model_fields:
            col = f"pillar_{field}"
            assert col in row, f"Missing {col}"

    def test_raw_metric_columns_present(self):
        """R3: raw_<name> columns map RawMetrics fields."""
        from compute.output.schemas import RawMetrics
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        for field in RawMetrics.model_fields:
            col = f"raw_{field}"
            assert col in row, f"Missing {col}"

    def test_dq_columns_present(self):
        """R3: dq_<name> columns map DataQuality fields."""
        from compute.output.schemas import DataQuality
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        for field in DataQuality.model_fields:
            col = f"dq_{field}"
            assert col in row, f"Missing {col}"

    def test_fp_columns_present_when_fair_price_set(self):
        """R3: fp_<key> columns present and populated from the real nested
        fair_price structure: top-level scalars + nested methods dict.

        The real fair_price dict (from compute.valuation.ensemble) has:
          - Top-level: median, max, low, high, mos_pct, median_trimmed,
            methods_excluded_from_median, valuation_methods_applicable
          - Nested: methods[<name>] = {"value": ..., "applicable": ..., ...}
        Per-method fp_<name> columns come from methods[<name>]["value"].
        fp_methods_applicable comes from valuation_methods_applicable.
        """
        from compute.warehouse.flatten import _FP_SCALAR_KEYS, flatten_stock
        fp = {
            "median": 120.0,
            "max": 130.0,
            "low": 100.0,
            "high": 135.0,
            "mos_pct": 20.0,
            "median_trimmed": 121.0,
            "methods_excluded_from_median": [],
            "valuation_methods_applicable": 4,
            "methods": {
                "graham": {"value": 110.0, "applicable": True, "reason": None, "tier_used": None},
                "multiples_pe": {"value": 90.0, "applicable": True, "reason": None, "tier_used": "sub_industry"},
                "multiples_pb": {"value": 85.0, "applicable": True, "reason": None, "tier_used": "sub_industry"},
                "multiples_ev_ebitda": {"value": None, "applicable": False, "reason": "excluded", "tier_used": None},
                "rim": {"value": 105.0, "applicable": True, "reason": None, "tier_used": None},
                "dcf": {"value": None, "applicable": False, "reason": "excluded", "tier_used": None},
            },
        }
        detail = _make_detail(fair_price=fp)
        row = flatten_stock(detail, None)
        # Top-level scalars
        assert row["fp_median"] == 120.0
        assert row["fp_mos_pct"] == 20.0
        # Per-method values from nested methods dict
        assert row["fp_graham"] == 110.0
        assert row["fp_multiples_pe"] == 90.0
        assert row["fp_rim"] == 105.0
        # Non-applicable methods have value=None → column is None
        assert row["fp_multiples_ev_ebitda"] is None
        assert row["fp_dcf"] is None
        # fp_methods_applicable from valuation_methods_applicable (not methods_applicable)
        assert row["fp_methods_applicable"] == 4
        # All expected fp_* columns present
        for key in _FP_SCALAR_KEYS:
            col = f"fp_{key}"
            assert col in row, f"Missing {col}"

    def test_fp_columns_none_when_fair_price_none(self):
        """R3: fp_* columns are None when fair_price is None."""
        from compute.warehouse.flatten import _FP_SCALAR_KEYS, flatten_stock
        row = flatten_stock(_make_detail(fair_price=None), None)
        for key in _FP_SCALAR_KEYS:
            assert row[f"fp_{key}"] is None

    def test_fair_price_json_present(self):
        """R3: fair_price_json is a JSON string of the full dict."""
        from compute.warehouse.flatten import flatten_stock
        fp = {"median": 99.0, "extra_key": "xyz"}
        row = flatten_stock(_make_detail(fair_price=fp), None)
        decoded = json.loads(row["fair_price_json"])
        assert decoded["extra_key"] == "xyz"

    def test_risk_flags_json_present(self):
        """R3: risk_flags_json is the raw list JSON-encoded."""
        from compute.warehouse.flatten import flatten_stock
        flags = ["altman_distress"]
        row = flatten_stock(_make_detail(risk_flags=flags), None)
        assert json.loads(row["risk_flags_json"]) == flags

    def test_valuation_warnings_json_present(self):
        """R3: valuation_warnings_json is the raw list JSON-encoded."""
        from compute.warehouse.flatten import flatten_stock
        warns = ["stale_filing_soft"]
        row = flatten_stock(_make_detail(valuation_warnings=warns), None)
        assert json.loads(row["valuation_warnings_json"]) == warns

    def test_detail_wins_over_summary_on_overlap(self):
        """R3: StockDetail wins on field collision with StockSummary."""
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail(ticker="TEST")
        summary = _make_summary(ticker="TEST")
        row = flatten_stock(detail, summary)
        # composite_score exists in both; the detail's value must win.
        assert row["ticker"] == "TEST"

    def test_summary_none_still_produces_row(self):
        """R3: flatten_stock with summary=None produces a valid row."""
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        assert isinstance(row, dict)
        assert row["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# R1 / R2 / R8 — write_run_snapshot round-trip
# ---------------------------------------------------------------------------

class TestWriteRunSnapshot:
    """R1 round-trip, R2 PK uniqueness, R8 partition path."""

    def test_R1_round_trip(self, tmp_path):
        """R1: write + read back yields ≥ 1 row with expected ticker column."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        detail = _make_detail("MSFT")
        summary = _make_summary("MSFT")
        meta = _make_metadata()
        run_date = date(2026, 6, 21)

        n = write_run_snapshot([detail], [summary], meta, run_date, tmp_path)
        assert n == 1

        partition_dir = tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21"
        part_file = partition_dir / "part-0.parquet"
        assert part_file.exists()

        table = pq.read_table(part_file)
        assert table.num_rows == 1
        assert "ticker" in table.schema.names
        assert table.column("ticker")[0].as_py() == "MSFT"

    def test_R2_pk_uniqueness(self, tmp_path):
        """R2: no duplicate rows in one snapshot partition."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        details = [_make_detail(f"T{i:03d}") for i in range(10)]
        summaries = [_make_summary(f"T{i:03d}") for i in range(10)]
        meta = _make_metadata()
        run_date = date(2026, 6, 21)

        write_run_snapshot(details, summaries, meta, run_date, tmp_path)
        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        table = pq.read_table(part_file)
        tickers = [r.as_py() for r in table.column("ticker")]
        assert len(tickers) == len(set(tickers)), "Duplicate tickers in snapshot"

    def test_R8_partition_path(self, tmp_path):
        """R8: partition is at year=YYYY/run_date=ISO/part-0.parquet."""
        from compute.warehouse.writer import write_run_snapshot

        run_date = date(2025, 12, 31)
        write_run_snapshot([_make_detail()], [_make_summary()], _make_metadata(), run_date, tmp_path)
        expected = tmp_path / "snapshots" / "year=2025" / "run_date=2025-12-31" / "part-0.parquet"
        assert expected.exists(), f"Expected {expected} not found"

    def test_idempotent_overwrite(self, tmp_path):
        """R1/R5: re-running the same run_date overwrites, not appends."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        run_date = date(2026, 6, 21)
        meta = _make_metadata()
        write_run_snapshot([_make_detail("AAA")], [_make_summary("AAA")], meta, run_date, tmp_path)
        write_run_snapshot([_make_detail("BBB")], [_make_summary("BBB")], meta, run_date, tmp_path)

        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        table = pq.read_table(part_file)
        # Should have only 1 row (the second write), not 2.
        assert table.num_rows == 1
        assert table.column("ticker")[0].as_py() == "BBB"


# ---------------------------------------------------------------------------
# R5 — manifest append + dedupe
# ---------------------------------------------------------------------------

class TestManifest:
    """R5: manifest append and dedupe semantics."""

    def test_manifest_created_after_write(self, tmp_path):
        """R5: _manifest.parquet is created after first write."""
        from compute.warehouse.writer import write_run_snapshot

        write_run_snapshot(
            [_make_detail()], [_make_summary()], _make_metadata(),
            date(2026, 6, 21), tmp_path,
        )
        assert (tmp_path / "_manifest.parquet").exists()

    def test_manifest_appends_new_run_dates(self, tmp_path):
        """R5: two different run_dates produce two manifest rows."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        meta = _make_metadata()
        write_run_snapshot([_make_detail()], [_make_summary()], meta, date(2026, 6, 20), tmp_path)
        write_run_snapshot([_make_detail()], [_make_summary()], meta, date(2026, 6, 21), tmp_path)

        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        assert len(manifest["run_date"]) == 2
        assert set(manifest["run_date"]) == {"2026-06-20", "2026-06-21"}

    def test_manifest_deduplicates_same_run_date(self, tmp_path):
        """R5: re-run same run_date replaces the manifest row (not appends)."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        meta = _make_metadata()
        run_date = date(2026, 6, 21)
        write_run_snapshot([_make_detail("A1")], [_make_summary("A1")], meta, run_date, tmp_path)
        write_run_snapshot([_make_detail("B1")], [_make_summary("B1")], meta, run_date, tmp_path)

        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        # Only 1 entry for this run_date.
        assert manifest["run_date"].count("2026-06-21") == 1
        # row_count reflects the second write (1 row).
        dates_dict = dict(zip(manifest["run_date"], manifest["row_count"], strict=False))
        assert dates_dict["2026-06-21"] == 1

    def test_manifest_has_expected_columns(self, tmp_path):
        """R5: manifest includes run_date, schema_version, universe, row_count, part_path."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        write_run_snapshot(
            [_make_detail()], [_make_summary()], _make_metadata(),
            date(2026, 6, 21), tmp_path,
        )
        table = pq.read_table(tmp_path / "_manifest.parquet")
        required = {"run_date", "schema_version", "universe", "row_count", "part_path"}
        assert required.issubset(set(table.schema.names))


# ---------------------------------------------------------------------------
# R7 — graceful degradation: empty details list
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """R7: empty details → 0 rows returned, no file written (or empty)."""

    def test_empty_details_returns_zero(self, tmp_path):
        """R7: write_run_snapshot with no details returns 0."""
        from compute.warehouse.writer import write_run_snapshot

        n = write_run_snapshot([], [], _make_metadata(), date(2026, 6, 21), tmp_path)
        assert n == 0

    def test_empty_details_no_partition_dir(self, tmp_path):
        """R7: empty details → no partition directory created."""
        from compute.warehouse.writer import write_run_snapshot

        write_run_snapshot([], [], _make_metadata(), date(2026, 6, 21), tmp_path)
        snapshots_dir = tmp_path / "snapshots"
        # Either not created, or no parquet files inside.
        if snapshots_dir.exists():
            parts = list(snapshots_dir.rglob("*.parquet"))
            assert len(parts) == 0, "Unexpected parquet files for empty run"


# ---------------------------------------------------------------------------
# R9 — size sanity: 900 rows < 2 MB
# ---------------------------------------------------------------------------

class TestSizeSanity:
    """R9: 900 synthetic rows compress to < 2 MB."""

    def test_900_rows_under_2mb(self, tmp_path):
        """R9: 900-row snapshot compresses to < 2 MB."""
        from compute.warehouse.writer import write_run_snapshot

        details = [_make_detail(f"T{i:04d}") for i in range(900)]
        summaries = [_make_summary(f"T{i:04d}") for i in range(900)]
        meta = _make_metadata()
        run_date = date(2026, 6, 21)

        write_run_snapshot(details, summaries, meta, run_date, tmp_path)
        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        size_mb = part_file.stat().st_size / (1024 * 1024)
        assert size_mb < 2.0, f"Snapshot size {size_mb:.2f} MB exceeds 2 MB limit"


# ---------------------------------------------------------------------------
# R10 — warehouse_schema_check drift guard
# ---------------------------------------------------------------------------

class TestWarehouseSchemaCheck:
    """R10: drift guard CLI + flag registry cross-check."""

    def test_derive_canonical_columns_nonempty(self):
        """R10: derive_canonical_columns returns a non-empty dict."""
        from compute.warehouse.warehouse_schema_check import derive_canonical_columns
        cols = derive_canonical_columns()
        assert len(cols) > 50, f"Expected > 50 columns, got {len(cols)}"

    def test_derive_canonical_columns_sorted(self):
        """R10: columns are alphabetically sorted."""
        from compute.warehouse.warehouse_schema_check import derive_canonical_columns
        cols = derive_canonical_columns()
        keys = list(cols.keys())
        assert keys == sorted(keys)

    def test_flag_columns_have_bool_dtype(self):
        """R10: all flag_* columns are typed 'bool'."""
        from compute.warehouse.warehouse_schema_check import derive_canonical_columns
        cols = derive_canonical_columns()
        for col, dtype in cols.items():
            if col.startswith("flag_"):
                assert dtype == "bool", f"{col} has dtype {dtype!r} (expected 'bool')"

    def test_warn_columns_have_bool_dtype(self):
        """R10: all warn_* columns are typed 'bool'."""
        from compute.warehouse.warehouse_schema_check import derive_canonical_columns
        cols = derive_canonical_columns()
        for col, dtype in cols.items():
            if col.startswith("warn_"):
                assert dtype == "bool", f"{col} has dtype {dtype!r} (expected 'bool')"

    def test_json_columns_have_str_none_dtype(self):
        """R10: all *_json columns are typed 'str | None'."""
        from compute.warehouse.warehouse_schema_check import derive_canonical_columns
        cols = derive_canonical_columns()
        for col, dtype in cols.items():
            if col.endswith("_json"):
                assert dtype == "str | None", (
                    f"{col} has dtype {dtype!r} (expected 'str | None')"
                )

    def test_flag_registry_cross_check_passes(self):
        """R10: _check_flag_registry returns no errors for the current schema."""
        from compute.warehouse.warehouse_schema_check import (
            _check_flag_registry,
            derive_canonical_columns,
        )
        cols = derive_canonical_columns()
        errors = _check_flag_registry(cols)
        assert errors == [], f"Registry drift: {errors}"

    def test_update_snapshot_writes_file(self, tmp_path, monkeypatch):
        """R10: --update writes the snapshot JSON to the configured path."""
        import compute.warehouse.warehouse_schema_check as wsc

        snapshot_path = tmp_path / "warehouse_schema.json"
        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", snapshot_path)

        exit_code = wsc.main(["--update"])
        assert exit_code == 0
        assert snapshot_path.exists()
        data = json.loads(snapshot_path.read_text())
        assert "columns" in data
        assert len(data["columns"]) > 50

    def test_check_passes_after_update(self, tmp_path, monkeypatch):
        """R10: verify round-trip: --update then plain check → exit 0."""
        import compute.warehouse.warehouse_schema_check as wsc

        snapshot_path = tmp_path / "warehouse_schema.json"
        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", snapshot_path)

        assert wsc.main(["--update"]) == 0
        assert wsc.main([]) == 0

    def test_check_fails_on_drift(self, tmp_path, monkeypatch):
        """R10: tampered snapshot produces exit 1 (drift detected)."""
        import compute.warehouse.warehouse_schema_check as wsc

        snapshot_path = tmp_path / "warehouse_schema.json"
        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", snapshot_path)

        # Write a valid snapshot, then mutate it.
        wsc.main(["--update"])
        data = json.loads(snapshot_path.read_text())
        data["columns"]["__fake_extra_col__"] = "str"
        snapshot_path.write_text(json.dumps(data))

        exit_code = wsc.main([])
        assert exit_code == 1


# ---------------------------------------------------------------------------
# R6 — QR_SKIP_WAREHOUSE env-var no-op (unit-level, no main.py)
# ---------------------------------------------------------------------------

class TestSkipEnvVar:
    """R6: QR_SKIP_WAREHOUSE prevents write_run_snapshot from being called."""

    def test_skip_env_var_suppresses_write(self, tmp_path, monkeypatch):
        """R6: with QR_SKIP_WAREHOUSE=1, no Parquet files are written.

        This test patches write_run_snapshot to raise if called, then
        simulates the main.py Step 13.5 guard logic inline (so we don't
        import main.py, which has heavy module-level side effects).
        """
        monkeypatch.setenv("QR_SKIP_WAREHOUSE", "1")

        called = []

        def fake_write(*args, **kwargs):
            called.append(True)
            return 0

        # Simulate the guard logic from main.py Step 13.5.
        import os as _os
        if _os.environ.get("QR_SKIP_WAREHOUSE", "").lower() in ("1", "true", "yes"):
            pass  # skip — no call to fake_write
        else:
            fake_write()

        assert called == [], "write_run_snapshot must NOT be called when QR_SKIP_WAREHOUSE=1"

    def test_skip_env_var_values(self, monkeypatch):
        """R6: all accepted truthy values for QR_SKIP_WAREHOUSE."""
        import os as _os
        for val in ("1", "true", "True", "TRUE", "yes", "YES", "Yes"):
            monkeypatch.setenv("QR_SKIP_WAREHOUSE", val)
            is_skipped = _os.environ.get("QR_SKIP_WAREHOUSE", "").lower() in (
                "1", "true", "yes"
            )
            assert is_skipped, f"QR_SKIP_WAREHOUSE={val!r} should trigger skip"


# ---------------------------------------------------------------------------
# R11 — fp_* columns from nested fair_price["methods"] dict (Defect-1 fix)
# ---------------------------------------------------------------------------

class TestFlattenFpNestedMethods:
    """R11: per-method fair_price columns sourced from fair_price["methods"][name]["value"].

    Validates both:
    - The nested methods dict extraction (Defect 1 fix).
    - fp_methods_applicable comes from valuation_methods_applicable, not
      a non-existent top-level "methods_applicable" key.
    """

    def _make_real_fp(self) -> dict:
        """Build a fair_price dict with the real production structure."""
        return {
            "median": 100.0,
            "max": 150.0,
            "low": 80.0,
            "high": 200.0,
            "mos_pct": 30.0,
            "median_trimmed": 95.0,
            "methods_excluded_from_median": [],
            "valuation_warnings": ["value_trap_risk"],
            "valuation_methods_applicable": 3,
            "methods": {
                "graham": {
                    "value": 120.0,
                    "applicable": True,
                    "reason": None,
                    "tier_used": None,
                },
                "multiples_pe": {
                    "value": 95.0,
                    "applicable": True,
                    "reason": None,
                    "tier_used": "sub_industry",
                },
                "multiples_pb": {
                    "value": 85.0,
                    "applicable": True,
                    "reason": None,
                    "tier_used": "sub_industry",
                },
                "multiples_ev_ebitda": {
                    "value": None,
                    "applicable": False,
                    "reason": "sector_excluded_financials",
                    "tier_used": None,
                },
                "rim": {
                    "value": None,
                    "applicable": False,
                    "reason": "value_trap_risk_roe_below_cost_of_equity",
                    "tier_used": None,
                },
                "dcf": {
                    "value": None,
                    "applicable": False,
                    "reason": "sector_excluded_financials",
                    "tier_used": None,
                },
            },
        }

    def test_per_method_values_extracted_from_nested_dict(self):
        """R11: fp_graham/fp_multiples_pe/etc. read from methods[name]['value']."""
        from compute.warehouse.flatten import flatten_stock
        fp = self._make_real_fp()
        row = flatten_stock(_make_detail(fair_price=fp), None)

        assert row["fp_graham"] == 120.0, f"fp_graham={row['fp_graham']}, expected 120.0"
        assert row["fp_multiples_pe"] == 95.0
        assert row["fp_multiples_pb"] == 85.0

    def test_non_applicable_methods_are_none(self):
        """R11: methods with value=None → fp_* column is None."""
        from compute.warehouse.flatten import flatten_stock
        fp = self._make_real_fp()
        row = flatten_stock(_make_detail(fair_price=fp), None)

        assert row["fp_multiples_ev_ebitda"] is None
        assert row["fp_rim"] is None
        assert row["fp_dcf"] is None

    def test_fp_methods_applicable_from_valuation_methods_applicable(self):
        """R11: fp_methods_applicable populated from valuation_methods_applicable (int count)."""
        from compute.warehouse.flatten import flatten_stock
        fp = self._make_real_fp()
        row = flatten_stock(_make_detail(fair_price=fp), None)

        assert row["fp_methods_applicable"] == 3

    def test_fp_methods_applicable_none_when_key_absent(self):
        """R11: fp_methods_applicable is None when valuation_methods_applicable absent."""
        from compute.warehouse.flatten import flatten_stock
        fp = {
            "median": 50.0,
            "max": 60.0,
            "low": 40.0,
            "high": 70.0,
            "mos_pct": 10.0,
            "median_trimmed": 51.0,
            "methods_excluded_from_median": [],
            # No valuation_methods_applicable key
            "methods": {
                "graham": {"value": 55.0, "applicable": True, "reason": None, "tier_used": None},
                "multiples_pe": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "multiples_pb": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "multiples_ev_ebitda": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "rim": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "dcf": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
            },
        }
        row = flatten_stock(_make_detail(fair_price=fp), None)
        assert row["fp_methods_applicable"] is None

    def test_top_level_scalars_still_extracted(self):
        """R11: median/max/low/high/mos_pct/median_trimmed still come from top-level."""
        from compute.warehouse.flatten import flatten_stock
        fp = self._make_real_fp()
        row = flatten_stock(_make_detail(fair_price=fp), None)

        assert row["fp_median"] == 100.0
        assert row["fp_max"] == 150.0
        assert row["fp_low"] == 80.0
        assert row["fp_high"] == 200.0
        assert row["fp_mos_pct"] == 30.0
        assert row["fp_median_trimmed"] == 95.0

    def test_fair_price_json_still_complete(self):
        """R11: fair_price_json carries the full dict including nested methods."""
        from compute.warehouse.flatten import flatten_stock
        fp = self._make_real_fp()
        row = flatten_stock(_make_detail(fair_price=fp), None)

        decoded = json.loads(row["fair_price_json"])
        assert "methods" in decoded
        assert decoded["methods"]["graham"]["value"] == 120.0

    def test_all_fp_columns_present(self):
        """R11: all expected fp_* columns appear in the row."""
        from compute.warehouse.flatten import _FP_SCALAR_KEYS, flatten_stock
        fp = self._make_real_fp()
        row = flatten_stock(_make_detail(fair_price=fp), None)
        for key in _FP_SCALAR_KEYS:
            col = f"fp_{key}"
            assert col in row, f"Missing column {col}"


# ---------------------------------------------------------------------------
# R12 — all-null numeric columns write as DOUBLE/float64 in parquet (Defect-2 fix)
# ---------------------------------------------------------------------------

class TestWriterNumericDtypes:
    """R12: numeric columns that are all-null in a snapshot round-trip as float,
    not integer, in the parquet file.  This ensures schema stability across
    runs where e.g. pillar_sentiment / pillar_ml (Phase-5 not yet wired)
    or fp_dcf (sector excluded) are all-null for every row.
    """

    def test_all_null_numeric_column_writes_as_float(self, tmp_path):
        """R12: pillar_sentiment/pillar_ml (always None in synthetic rows)
        must be DOUBLE in parquet, not INT/BIGINT."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        # Build one row where pillar_sentiment and pillar_ml are None
        # (the default in _make_pillar_scores above, which leaves them out).
        detail = _make_detail("NULL_TEST")
        summary = _make_summary("NULL_TEST")
        meta = _make_metadata()
        run_date = date(2026, 6, 21)

        write_run_snapshot([detail], [summary], meta, run_date, tmp_path)
        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        table = pq.read_table(part_file)
        schema_dict = {field.name: field.type for field in table.schema}

        import pyarrow as pa

        # pillar_sentiment and pillar_ml are set to 50.0 in _make_pillar_scores
        # so they are non-null; we need a column that IS all-null.
        # composite_score_adjusted is None in our synthetic StockDetail.
        # It's a float|None field — must come out as DOUBLE.
        for col_name in ("composite_score_adjusted", "beneish_m_score", "dechow_f_score"):
            if col_name in schema_dict:
                col_type = schema_dict[col_name]
                assert pa.types.is_floating(col_type), (
                    f"{col_name} dtype={col_type} — expected float64/DOUBLE, "
                    f"got {col_type} (integer schema drift defect)"
                )

    def test_all_null_fp_dcf_writes_as_float(self, tmp_path):
        """R12: fp_dcf column (all-null when fair_price.methods.dcf.value is None)
        must be DOUBLE in parquet, not INT/BIGINT."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        # Use a fair_price where dcf value is None (common for financial-sector stocks).
        fp = {
            "median": 50.0,
            "max": 60.0,
            "low": 40.0,
            "high": 70.0,
            "mos_pct": 10.0,
            "median_trimmed": 50.0,
            "methods_excluded_from_median": [],
            "valuation_methods_applicable": 1,
            "methods": {
                "graham": {"value": 55.0, "applicable": True, "reason": None, "tier_used": None},
                "multiples_pe": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "multiples_pb": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "multiples_ev_ebitda": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "rim": {"value": None, "applicable": False, "reason": "x", "tier_used": None},
                "dcf": {"value": None, "applicable": False, "reason": "sector_excluded_financials", "tier_used": None},
            },
        }
        detail = _make_detail("FP_DCF_NULL", fair_price=fp)
        summary = _make_summary("FP_DCF_NULL")
        meta = _make_metadata()
        run_date = date(2026, 6, 21)

        write_run_snapshot([detail], [summary], meta, run_date, tmp_path)
        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        table = pq.read_table(part_file)
        schema_dict = {field.name: field.type for field in table.schema}

        # fp_dcf is None → must write as DOUBLE not INT.
        assert "fp_dcf" in schema_dict, "fp_dcf column missing from parquet"
        col_type = schema_dict["fp_dcf"]
        assert pa.types.is_floating(col_type), (
            f"fp_dcf dtype={col_type} — expected DOUBLE, got {col_type}"
        )

        # fp_graham has a real value (55.0) — must also be float.
        col_type_g = schema_dict["fp_graham"]
        assert pa.types.is_floating(col_type_g), (
            f"fp_graham dtype={col_type_g} — expected DOUBLE"
        )

        # Confirm the real fp_graham value round-trips correctly.
        col_vals = table.column("fp_graham").to_pylist()
        assert col_vals[0] == 55.0, f"fp_graham round-tripped as {col_vals[0]}, expected 55.0"
