"""Tests for atomic JSON writer + schema round-trip."""

from __future__ import annotations

import json

from compute.output.schemas import (
    DataQuality,
    Metadata,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)
from compute.output.writer import (
    atomic_write_json,
    write_metadata_json,
    write_rankings_json,
    write_stock_detail,
)


def test_atomic_write_json_replaces_existing_file(tmp_path):
    target = tmp_path / "file.json"
    target.write_text("OLD")

    atomic_write_json(target, {"hello": "world"})

    assert json.loads(target.read_text()) == {"hello": "world"}
    assert not (tmp_path / "file.json.tmp").exists()


def test_atomic_write_json_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "deep" / "out.json"
    atomic_write_json(target, [1, 2, 3])
    assert json.loads(target.read_text()) == [1, 2, 3]


def test_write_rankings_json_round_trip(tmp_path):
    rows = [
        StockSummary(
            rank=1,
            ticker="AAPL",
            name="Apple Inc.",
            sector="Information Technology",
            composite_score=87.4,
            current_price=220.15,
            pillar_scores=PillarScores(momentum=87.4),
        ),
        StockSummary(
            rank=2,
            ticker="MSFT",
            name="Microsoft",
            sector="Information Technology",
            composite_score=85.0,
            current_price=410.50,
            pillar_scores=PillarScores(momentum=85.0),
        ),
    ]
    out = write_rankings_json(rows, tmp_path)
    payload = json.loads(out.read_text())
    assert payload[0]["ticker"] == "AAPL"
    assert payload[0]["pillar_scores"]["momentum"] == 87.4
    assert payload[0]["pillar_scores"]["quality"] is None
    assert payload[1]["composite_score"] == 85.0


def test_write_metadata_json_round_trip(tmp_path):
    meta = Metadata(
        version="0.3.0-phase2",
        last_update_utc="2026-05-08T22:00:00Z",
        next_update_utc="2026-05-15T22:00:00Z",
        universe="SP500",
        universe_size=503,
        compute_run_id="run-123",
        git_commit="abc123",
    )
    out = write_metadata_json(meta, tmp_path)
    payload = json.loads(out.read_text())
    assert payload["universe_size"] == 503
    assert payload["version"] == "0.3.0-phase2"


def test_write_stock_detail_round_trip(tmp_path):
    detail = StockDetail(
        ticker="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        industry="Technology Hardware, Storage and Peripherals",
        market_cap=3.4e12,
        current_price=220.15,
        rank=1,
        composite_score=87.4,
        pillar_scores=PillarScores(momentum=87.4),
        raw_metrics=RawMetrics(
            revenue=391_035_000_000.0,
            net_income=93_736_000_000.0,
            total_assets=364_980_000_000.0,
            eps_diluted=6.05,
            shares_outstanding=15_000_000_000.0,
            market_cap=3.4e12,
            pe_ratio_ttm=36.4,
        ),
        data_quality=DataQuality(
            missing_metrics=["capex"],
            imputed_metrics=[],
            filing_lag_days=38,
            latest_filed_date="2024-11-01",
            latest_period_end="2024-09-28",
        ),
    )
    out = write_stock_detail(detail, tmp_path)
    assert out == tmp_path / "stocks" / "AAPL.json"
    payload = json.loads(out.read_text())
    assert payload["ticker"] == "AAPL"
    assert payload["raw_metrics"]["revenue"] == 391_035_000_000.0
    assert payload["pillar_scores"]["momentum"] == 87.4
    assert payload["pillar_scores"]["quality"] is None
    assert payload["data_quality"]["filing_lag_days"] == 38
    assert payload["fair_price"] is None
    assert payload["top5_factors"] == []
