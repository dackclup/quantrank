"""Tests for atomic JSON writer + schema round-trip."""

from __future__ import annotations

import json

from compute.output.schemas import Metadata, PillarScores, StockSummary
from compute.output.writer import (
    atomic_write_json,
    write_metadata_json,
    write_rankings_json,
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
        version="0.2.0-phase1",
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
    assert payload["version"] == "0.2.0-phase1"
