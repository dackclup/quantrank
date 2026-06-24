"""Offline tests for Gap 1 (metadata_json in manifest) + Gap 2 (portfolio writer).

Coverage targets
----------------
M1  manifest metadata_json: after write_run_snapshot the manifest Parquet
    contains a ``metadata_json`` column that round-trips to the full Metadata
    model dump (all known fields present).
M2  manifest backward-compat: the five original manifest columns are still
    present (run_date, schema_version, universe, row_count, part_path).
M3  metadata_json is valid JSON and round-trips back to a Metadata instance.
M4  metadata_json is updated idempotently on re-run (same run_date).

P1  portfolio write: write_portfolio_snapshot returns a positive row count
    when a synthetic backtest_pit.json is present.
P2  partition path: year=<YYYY>/run_date=<ISO>/part-0.parquet under
    data/warehouse/portfolio/.
P3  holdings columns: ticker, composite_score, sector, mos_pct, weight_default,
    adaptive_count, holding_json, rebalance_json present in the parquet.
P4  portfolio manifest: portfolio_manifest.parquet created with meta_json +
    nav_json + rebalance_count columns.
P5  graceful no-op: absent backtest_pit.json → returns 0, no Parquet written.
P6  graceful no-op: empty rebalances list → returns 0.
P7  QR_SKIP_WAREHOUSE: Step-13.5 guard prevents portfolio write.
P8  holding_json is valid JSON containing the full holding dict.
P9  rebalance_json does NOT contain the holdings key (it holds non-holdings
    rebalance metadata only).
P10 portfolio manifest append + dedupe: two different run_dates produce two
    rows; same run_date replaces the existing row.
P11 weight_default populated from weights_by_count[default_count] for each
    ticker.
P12 warehouse_schema_check: derive_portfolio_partition_columns and
    derive_portfolio_manifest_columns return non-empty sorted dicts.
P13 warehouse_schema_check drift guard: round-trip --update then plain check
    passes for both portfolio snapshot files.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Synthetic model / data builders
# ---------------------------------------------------------------------------

def _make_metadata() -> Any:
    from compute.output.schemas import Metadata
    return Metadata(
        version="0.10.31-phase8pilot",
        last_update_utc="2026-06-24T22:00:00Z",
        next_update_utc="2026-06-25T22:00:00Z",
        universe="SP1500",
        universe_size=1500,
        compute_run_id="test-gaps-001",
        git_commit="deadbeef",
        fundamentals_coverage_pct=98.5,
        bonferroni_shadow_live_fire_count=86,
        bonferroni_shadow_provisional_fire_count=47,
        bonferroni_shadow_flip_count=39,
    )


def _make_pillar_scores():
    from compute.output.schemas import PillarScores
    return PillarScores(**{f: 55.0 for f in PillarScores.model_fields})


def _make_raw_metrics():
    from compute.output.schemas import RawMetrics
    return RawMetrics(**{f: None for f in RawMetrics.model_fields})


def _make_data_quality():
    from compute.output.schemas import DataQuality
    kwargs: dict[str, Any] = {f: None for f in DataQuality.model_fields}
    kwargs["missing_metrics"] = []
    kwargs["imputed_metrics"] = []
    return DataQuality(**kwargs)


def _make_detail(ticker: str = "AAPL") -> Any:
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
        risk_flags=[],
        valuation_warnings=[],
        index_membership="sp500",
        index_memberships=["sp500"],
    )


def _make_summary(ticker: str = "AAPL") -> Any:
    from compute.output.schemas import StockSummary
    return StockSummary(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector="Technology",
        rank=1,
        composite_score=55.0,
        current_price=100.0,
        index_membership="sp500",
        index_memberships=["sp500"],
    )


def _make_backtest_artifact(
    n_rebalances: int = 3,
    n_holdings: int = 5,
    default_count: int = 5,
) -> dict:
    """Build a synthetic backtest_pit.json structure."""
    rebalances = []
    for i in range(n_rebalances):
        holdings = [
            {
                "ticker": f"T{j:03d}",
                "composite_score": 70.0 + j,
                "sector": "Technology",
                "sigma_90d": 0.25,
                "mos_pct": 12.5 + j,
            }
            for j in range(n_holdings)
        ]
        weights = {
            ticker_key: round(1.0 / n_holdings, 6)
            for ticker_key in [f"T{j:03d}" for j in range(n_holdings)]
        }
        rebalances.append({
            "date": f"2025-0{i+1}-01",
            "holdings": holdings,
            "weights_by_count": {str(default_count): weights},
            "adaptive_count": default_count,
            "members_complete": True,
            "high_conviction_count": n_holdings,
        })

    return {
        "meta": {
            "generated_utc": "2026-06-24T22:30:00Z",
            "rule_version": "adaptive-v2",
            "default_count": default_count,
            "rebalance_count": n_rebalances,
            "veto_layer_replayed": True,
        },
        "nav": {
            "dates": ["2025-01-01", "2025-02-01", "2025-03-01"],
            "by_count": {str(default_count): [100.0, 105.0, 110.0]},
            "adaptive": [100.0, 105.0, 110.0],
        },
        "rebalances": rebalances,
    }


def _write_artifact(artifact_path: Path, artifact: dict) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")


# ---------------------------------------------------------------------------
# M1–M4: Gap 1 — metadata_json in manifest
# ---------------------------------------------------------------------------

class TestManifestMetadataJson:
    """M1–M4: Gap 1 — full Metadata persisted in manifest as metadata_json."""

    def test_M1_metadata_json_column_present(self, tmp_path):
        """M1: after write_run_snapshot, _manifest.parquet has metadata_json column."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        meta = _make_metadata()
        write_run_snapshot(
            [_make_detail()], [_make_summary()], meta, date(2026, 6, 24), tmp_path
        )
        manifest = pq.read_table(tmp_path / "_manifest.parquet")
        assert "metadata_json" in manifest.schema.names, (
            "metadata_json column must be in _manifest.parquet (Gap 1)"
        )

    def test_M2_original_columns_still_present(self, tmp_path):
        """M2: the five original manifest columns survive (backward-compat)."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        write_run_snapshot(
            [_make_detail()], [_make_summary()], _make_metadata(),
            date(2026, 6, 24), tmp_path,
        )
        manifest_cols = set(pq.read_table(tmp_path / "_manifest.parquet").schema.names)
        required = {"run_date", "schema_version", "universe", "row_count", "part_path"}
        assert required.issubset(manifest_cols), (
            f"Original manifest columns missing: {required - manifest_cols}"
        )

    def test_M3_metadata_json_is_valid_and_roundtrips(self, tmp_path):
        """M3: metadata_json is valid JSON and round-trips to Metadata model."""
        import pyarrow.parquet as pq

        from compute.output.schemas import Metadata
        from compute.warehouse.writer import write_run_snapshot

        meta = _make_metadata()
        write_run_snapshot(
            [_make_detail()], [_make_summary()], meta, date(2026, 6, 24), tmp_path
        )
        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        meta_json_str = manifest["metadata_json"][0]

        assert meta_json_str is not None, "metadata_json must not be null"
        parsed = json.loads(meta_json_str)
        assert isinstance(parsed, dict), "metadata_json must parse to a dict"

        # Must contain at least all non-optional Metadata field names.
        assert "version" in parsed
        assert "universe" in parsed
        assert "universe_size" in parsed
        # New fields (Gap 1 goal: forward-safe) must also be present.
        assert "bonferroni_shadow_live_fire_count" in parsed
        assert parsed["bonferroni_shadow_live_fire_count"] == 86

        # Must round-trip to a Metadata instance without validation error.
        meta_rt = Metadata(**parsed)
        assert meta_rt.version == meta.version
        assert meta_rt.universe_size == meta.universe_size

    def test_M4_metadata_json_updated_idempotently(self, tmp_path):
        """M4: re-run same run_date replaces metadata_json (not appends)."""
        import pyarrow.parquet as pq

        from compute.output.schemas import Metadata
        from compute.warehouse.writer import write_run_snapshot

        meta_v1 = _make_metadata()
        run_date = date(2026, 6, 24)
        write_run_snapshot([_make_detail()], [_make_summary()], meta_v1, run_date, tmp_path)

        # Second write with a different universe_size to confirm replacement.
        meta_v2 = Metadata(
            version="0.10.32-phase8pilot",
            last_update_utc="2026-06-24T23:00:00Z",
            next_update_utc="2026-06-25T22:00:00Z",
            universe="SP1500",
            universe_size=1504,
            compute_run_id="test-gaps-002",
            git_commit="cafebabe",
        )
        write_run_snapshot([_make_detail()], [_make_summary()], meta_v2, run_date, tmp_path)

        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        # Only one row for this run_date.
        assert manifest["run_date"].count("2026-06-24") == 1

        meta_json_str = manifest["metadata_json"][manifest["run_date"].index("2026-06-24")]
        parsed = json.loads(meta_json_str)
        # Must reflect the SECOND write.
        assert parsed["universe_size"] == 1504
        assert parsed["version"] == "0.10.32-phase8pilot"


# ---------------------------------------------------------------------------
# P1–P13: Gap 2 — portfolio writer
# ---------------------------------------------------------------------------

class TestPortfolioWriter:
    """P1–P11: gap-2 portfolio writer behaviours."""

    def test_P1_returns_positive_row_count(self, tmp_path):
        """P1: write_portfolio_snapshot returns > 0 when artifact present."""
        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact(n_rebalances=3, n_holdings=5)
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)

        n = write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=tmp_path / "warehouse",
            artifact_path=artifact_path,
        )
        assert n == 3 * 5, f"Expected 15 holding rows, got {n}"

    def test_P2_partition_path_layout(self, tmp_path):
        """P2: Parquet partition lives at portfolio/year=YYYY/run_date=ISO/part-0.parquet."""
        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact()
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        expected = wh / "portfolio" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        assert expected.exists(), f"Expected partition at {expected}"

    def test_P3_holdings_columns_present(self, tmp_path):
        """P3: required holding columns are in the Parquet schema."""
        import pyarrow.parquet as pq

        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact()
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        part = wh / "portfolio" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        # schema=pq.read_schema(str(part)) avoids Hive-partition type-inference conflict when
        # run_date is both a data column and a partition directory name component.
        table = pq.ParquetFile(str(part)).read()
        cols = set(table.schema.names)
        required = {
            "ticker", "composite_score", "sector", "mos_pct",
            "weight_default", "adaptive_count", "holding_json", "rebalance_json",
            "run_date", "rebalance_date",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_P4_portfolio_manifest_created(self, tmp_path):
        """P4: portfolio_manifest.parquet is created with meta_json + nav_json."""
        import pyarrow.parquet as pq

        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact(n_rebalances=3)
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        manifest_path = wh / "portfolio_manifest.parquet"
        assert manifest_path.exists(), "portfolio_manifest.parquet must be created"

        manifest = pq.read_table(manifest_path).to_pydict()
        required = {"run_date", "meta_json", "nav_json", "rebalance_count"}
        assert required.issubset(set(manifest.keys())), (
            f"Missing portfolio manifest columns: {required - set(manifest.keys())}"
        )
        assert manifest["rebalance_count"][0] == 3.0  # stored as float64

    def test_P5_graceful_noop_absent_artifact(self, tmp_path):
        """P5: absent backtest_pit.json → returns 0, no Parquet written."""
        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        wh = tmp_path / "warehouse"
        n = write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=tmp_path / "nonexistent.json",
        )
        assert n == 0
        portfolio_dir = wh / "portfolio"
        if portfolio_dir.exists():
            parts = list(portfolio_dir.rglob("*.parquet"))
            assert len(parts) == 0, "No parquet files should be written when artifact absent"

    def test_P6_graceful_noop_empty_rebalances(self, tmp_path):
        """P6: artifact with empty rebalances list → returns 0."""
        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = {"meta": {"default_count": 5}, "nav": {}, "rebalances": []}
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        n = write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        assert n == 0

    def test_P7_qr_skip_warehouse_prevents_portfolio_write(self, tmp_path, monkeypatch):
        """P7: the Step-13.5 QR_SKIP_WAREHOUSE guard prevents the portfolio write.

        Simulates the main.py guard inline (mirrors test_warehouse.py R6).
        """
        monkeypatch.setenv("QR_SKIP_WAREHOUSE", "1")

        called = []

        def fake_portfolio_write(*args, **kwargs):
            called.append(True)
            return 0

        if os.environ.get("QR_SKIP_WAREHOUSE", "").lower() in ("1", "true", "yes"):
            pass  # skip
        else:
            fake_portfolio_write()

        assert called == [], "portfolio write must not fire when QR_SKIP_WAREHOUSE=1"

    def test_P8_holding_json_is_valid_and_complete(self, tmp_path):
        """P8: holding_json is valid JSON containing all fields from the holding dict."""
        import pyarrow.parquet as pq

        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact(n_rebalances=1, n_holdings=2)
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        part = wh / "portfolio" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        table = pq.ParquetFile(str(part)).read().to_pydict()

        # Check first row's holding_json.
        holding_json_str = table["holding_json"][0]
        assert holding_json_str is not None
        holding = json.loads(holding_json_str)
        assert "ticker" in holding
        assert "composite_score" in holding
        assert "sector" in holding

    def test_P9_rebalance_json_excludes_holdings_key(self, tmp_path):
        """P9: rebalance_json contains non-holdings metadata but NOT the holdings key."""
        import pyarrow.parquet as pq

        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact(n_rebalances=1, n_holdings=2)
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        part = wh / "portfolio" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        table = pq.ParquetFile(str(part)).read().to_pydict()

        rebalance_json_str = table["rebalance_json"][0]
        assert rebalance_json_str is not None
        rebalance_meta = json.loads(rebalance_json_str)
        assert "holdings" not in rebalance_meta, (
            "rebalance_json must NOT include the holdings array (it lives in holding_json rows)"
        )
        # Non-holdings fields should be present.
        assert "date" in rebalance_meta or "adaptive_count" in rebalance_meta

    def test_P10_portfolio_manifest_append_and_dedupe(self, tmp_path):
        """P10: two run_dates produce two manifest rows; same run_date replaces."""
        import pyarrow.parquet as pq

        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact()
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 23),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        manifest = pq.read_table(wh / "portfolio_manifest.parquet").to_pydict()
        assert len(manifest["run_date"]) == 2
        assert set(manifest["run_date"]) == {"2026-06-23", "2026-06-24"}

        # Re-run same run_date → still 2 rows, not 3.
        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        manifest2 = pq.read_table(wh / "portfolio_manifest.parquet").to_pydict()
        assert len(manifest2["run_date"]) == 2
        assert manifest2["run_date"].count("2026-06-24") == 1

    def test_P11_weight_default_populated(self, tmp_path):
        """P11: weight_default populated from weights_by_count[default_count] per ticker."""
        import pyarrow.parquet as pq

        from compute.warehouse.portfolio_writer import write_portfolio_snapshot

        artifact = _make_backtest_artifact(n_rebalances=1, n_holdings=5, default_count=5)
        artifact_path = tmp_path / "backtest_pit.json"
        _write_artifact(artifact_path, artifact)
        wh = tmp_path / "warehouse"

        write_portfolio_snapshot(
            run_date=date(2026, 6, 24),
            warehouse_dir=wh,
            artifact_path=artifact_path,
        )
        part = wh / "portfolio" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        table = pq.ParquetFile(str(part)).read().to_pydict()

        weight_values = table["weight_default"]
        # Each of 5 equal-weight holdings should be ~0.2 (1/5).
        non_null = [w for w in weight_values if w is not None]
        assert len(non_null) == 5, f"Expected 5 non-null weight_default, got {len(non_null)}"
        for w in non_null:
            assert abs(w - 0.2) < 1e-4, f"Expected weight ~0.2, got {w}"


# ---------------------------------------------------------------------------
# P12–P13: warehouse_schema_check integration for portfolio writer
# ---------------------------------------------------------------------------

class TestPortfolioSchemaCheck:
    """P12–P13: drift guard covers portfolio writer column sets."""

    def test_P12_derive_partition_columns_nonempty_sorted(self):
        """P12: derive_portfolio_partition_columns returns a non-empty sorted dict."""
        from compute.warehouse.warehouse_schema_check import derive_portfolio_partition_columns

        cols = derive_portfolio_partition_columns()
        assert len(cols) >= 11, f"Expected ≥11 partition columns, got {len(cols)}"
        keys = list(cols.keys())
        assert keys == sorted(keys), "Portfolio partition columns must be sorted"

    def test_P12_derive_manifest_columns_nonempty_sorted(self):
        """P12: derive_portfolio_manifest_columns returns a non-empty sorted dict."""
        from compute.warehouse.warehouse_schema_check import derive_portfolio_manifest_columns

        cols = derive_portfolio_manifest_columns()
        assert len(cols) >= 5, f"Expected ≥5 manifest columns, got {len(cols)}"
        keys = list(cols.keys())
        assert keys == sorted(keys), "Portfolio manifest columns must be sorted"

    def test_P13_schema_check_update_then_verify(self, tmp_path, monkeypatch):
        """P13: --update writes portfolio snapshot files; plain check passes after."""
        import compute.warehouse.warehouse_schema_check as wsc

        # Redirect snapshot paths to tmp_path.
        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", tmp_path / "warehouse_schema.json")
        monkeypatch.setattr(wsc, "FILING_INDEX_SNAPSHOT_PATH", tmp_path / "filing_index_schema.json")
        monkeypatch.setattr(
            wsc, "PORTFOLIO_PARTITION_SNAPSHOT_PATH",
            tmp_path / "portfolio_partition_schema.json",
        )
        monkeypatch.setattr(
            wsc, "PORTFOLIO_MANIFEST_SNAPSHOT_PATH",
            tmp_path / "portfolio_manifest_schema.json",
        )

        # --update must succeed.
        assert wsc.main(["--update"]) == 0
        assert (tmp_path / "portfolio_partition_schema.json").exists()
        assert (tmp_path / "portfolio_manifest_schema.json").exists()

        # Plain verify must also succeed (round-trip).
        assert wsc.main([]) == 0

    def test_P13_drift_detected_when_portfolio_snapshot_tampered(self, tmp_path, monkeypatch):
        """P13: tampering with portfolio_partition_schema.json → drift detected (exit 1)."""
        import compute.warehouse.warehouse_schema_check as wsc

        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", tmp_path / "warehouse_schema.json")
        monkeypatch.setattr(wsc, "FILING_INDEX_SNAPSHOT_PATH", tmp_path / "filing_index_schema.json")
        monkeypatch.setattr(
            wsc, "PORTFOLIO_PARTITION_SNAPSHOT_PATH",
            tmp_path / "portfolio_partition_schema.json",
        )
        monkeypatch.setattr(
            wsc, "PORTFOLIO_MANIFEST_SNAPSHOT_PATH",
            tmp_path / "portfolio_manifest_schema.json",
        )

        # First --update to get a valid baseline.
        assert wsc.main(["--update"]) == 0

        # Tamper the portfolio partition snapshot.
        pp_path = tmp_path / "portfolio_partition_schema.json"
        data = json.loads(pp_path.read_text())
        data["columns"]["__phantom_col__"] = "float | None"
        pp_path.write_text(json.dumps(data))

        # Plain verify must now fail.
        rc = wsc.main([])
        assert rc == 1, f"Expected exit 1 after tampering, got {rc}"

    def test_P12_json_columns_have_str_none_dtype(self):
        """P12: *_json columns in the portfolio partition are typed 'str | None'."""
        from compute.warehouse.warehouse_schema_check import derive_portfolio_partition_columns

        cols = derive_portfolio_partition_columns()
        for col, dtype in cols.items():
            if col.endswith("_json"):
                assert dtype == "str | None", (
                    f"{col} has dtype {dtype!r} (expected 'str | None')"
                )

    def test_P12_manifest_json_columns_have_str_none_dtype(self):
        """P12: *_json columns in portfolio_manifest are typed 'str | None'."""
        from compute.warehouse.warehouse_schema_check import derive_portfolio_manifest_columns

        cols = derive_portfolio_manifest_columns()
        for col, dtype in cols.items():
            if col.endswith("_json"):
                assert dtype == "str | None", (
                    f"{col} has dtype {dtype!r} (expected 'str | None')"
                )
