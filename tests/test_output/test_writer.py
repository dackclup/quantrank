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
    # Phase 1.6 (issue #155) — `tier2_enabled` defaults True and is
    # always serialized so the verify-helper can read the explicit
    # state rather than inferring from `tier2_coverage_pct`.
    assert payload["tier2_enabled"] is True


def test_write_metadata_json_tier2_disabled_round_trip(tmp_path):
    meta = Metadata(
        version="0.9.3-phase4h.3",
        last_update_utc="2026-05-20T22:00:00Z",
        next_update_utc="2026-05-27T22:00:00Z",
        universe="SP500",
        universe_size=502,
        compute_run_id="run-456",
        git_commit="def456",
        tier2_enabled=False,
    )
    out = write_metadata_json(meta, tmp_path)
    payload = json.loads(out.read_text())
    assert payload["tier2_enabled"] is False


def test_write_metadata_json_universe_provenance_round_trip(tmp_path):
    """Phase 4.6 — `universe_membership_as_of` + `survivorship_bias_corrected`
    survive the Pydantic → JSON round trip and stay accessible to the
    verify-helper + downstream backtest consumers."""
    meta = Metadata(
        version="0.10.7-phase4.6",
        last_update_utc="2026-05-27T22:00:00Z",
        next_update_utc="2026-05-28T22:00:00Z",
        universe="SP500",
        universe_size=502,
        compute_run_id="run-789",
        git_commit="abc789",
        universe_membership_as_of="2026-05-27",
        survivorship_bias_corrected=True,
    )
    out = write_metadata_json(meta, tmp_path)
    payload = json.loads(out.read_text())
    assert payload["universe_membership_as_of"] == "2026-05-27"
    assert payload["survivorship_bias_corrected"] is True


def test_write_metadata_json_universe_provenance_legacy_snapshot(tmp_path):
    """Pre-0.10.7 metadata.json shapes (no universe-provenance fields)
    still serialize cleanly — the two new fields default to None and the
    payload contains them as null."""
    meta = Metadata(
        version="0.10.6-phase4.5e",
        last_update_utc="2026-05-26T22:00:00Z",
        next_update_utc="2026-05-27T22:00:00Z",
        universe="SP500",
        universe_size=502,
        compute_run_id="run-legacy",
        git_commit="legacy0",
        # universe_membership_as_of / survivorship_bias_corrected omitted
    )
    out = write_metadata_json(meta, tmp_path)
    payload = json.loads(out.read_text())
    assert payload["universe_membership_as_of"] is None
    assert payload["survivorship_bias_corrected"] is None


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


# -- write_stock_history (Phase 3c Step 5.2) ---------------------------------

import math  # noqa: E402

import pandas as pd  # noqa: E402

from compute.output.writer import write_stock_history  # noqa: E402


def _ohlcv_df(n_rows: int) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame with a date index."""
    idx = pd.date_range(end="2026-05-01", periods=n_rows, freq="B")
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n_rows)],
            "High": [101.0 + i for i in range(n_rows)],
            "Low": [99.0 + i for i in range(n_rows)],
            "Close": [100.5 + i for i in range(n_rows)],
            "Adj Close": [100.5 + i for i in range(n_rows)],
            "Volume": [1_000_000 + i * 1000 for i in range(n_rows)],
        },
        index=idx,
    )


def test_write_stock_history_slices_to_tail_days_when_input_longer(tmp_path):
    """Inputs longer than HISTORY_TAIL_DAYS get sliced to the last tail."""
    from compute.output.writer import HISTORY_TAIL_DAYS

    df = _ohlcv_df(HISTORY_TAIL_DAYS + 50)
    ok = write_stock_history(ticker="AAPL", prices_df=df, output_dir=tmp_path)
    assert ok is True
    out = tmp_path / "stocks" / "history" / "AAPL.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["ticker"] == "AAPL"
    assert len(payload["dates"]) == HISTORY_TAIL_DAYS
    assert len(payload["closes"]) == HISTORY_TAIL_DAYS
    # Last date is row (N-1); index ends at the configured `end=` date.
    assert payload["dates"][-1] == "2026-05-01"


def test_write_stock_history_uses_full_input_when_shorter_than_tail(tmp_path):
    """Inputs shorter than the tail are written verbatim — no padding."""
    df = _ohlcv_df(100)
    ok = write_stock_history(ticker="NEW", prices_df=df, output_dir=tmp_path)
    assert ok is True
    payload = json.loads((tmp_path / "stocks" / "history" / "NEW.json").read_text())
    assert len(payload["dates"]) == 100
    assert len(payload["closes"]) == 100


def test_write_stock_history_returns_false_for_empty_df(tmp_path):
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    ok = write_stock_history(ticker="EMPTY", prices_df=empty, output_dir=tmp_path)
    assert ok is False
    out = tmp_path / "stocks" / "history" / "EMPTY.json"
    assert not out.exists()


def test_write_stock_history_returns_false_for_none_input(tmp_path):
    assert write_stock_history(ticker="X", prices_df=None, output_dir=tmp_path) is False  # type: ignore[arg-type]


def test_write_stock_history_returns_false_when_columns_missing(tmp_path):
    df = pd.DataFrame({"WrongCol": [1, 2, 3]},
                      index=pd.date_range(end="2026-05-01", periods=3, freq="B"))
    ok = write_stock_history(ticker="BAD", prices_df=df, output_dir=tmp_path)
    assert ok is False


def test_write_stock_history_serializes_nan_as_none(tmp_path):
    df = _ohlcv_df(5)
    df.loc[df.index[2], "Close"] = math.nan
    df.loc[df.index[2], "Adj Close"] = math.nan
    ok = write_stock_history(ticker="NAN", prices_df=df, output_dir=tmp_path)
    assert ok is True
    payload = json.loads((tmp_path / "stocks" / "history" / "NAN.json").read_text())
    assert payload["closes"][2] is None
    # Surrounding rows still numeric.
    assert payload["closes"][0] is not None
    assert payload["closes"][1] is not None


def test_write_stock_history_payload_schema_keys(tmp_path):
    df = _ohlcv_df(10)
    write_stock_history(ticker="SCH", prices_df=df, output_dir=tmp_path)
    payload = json.loads((tmp_path / "stocks" / "history" / "SCH.json").read_text())
    assert set(payload.keys()) == {
        "ticker", "dates", "opens", "highs", "lows", "closes", "volumes",
    }
    assert all(isinstance(d, str) for d in payload["dates"])
