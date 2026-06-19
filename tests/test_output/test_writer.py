"""Tests for atomic JSON writer + schema round-trip."""

from __future__ import annotations

import json
from pathlib import Path

from compute.output.schemas import (
    DataQuality,
    Metadata,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)
from compute.output.writer import (
    _PRUNE_SAFETY_FLOOR,
    atomic_write_json,
    prune_orphan_stock_files,
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


def test_write_benchmarks_json_shape_and_coverage(tmp_path):
    """Phase 7.0 PR-1 — column-major benchmark export + coverage %."""
    import pandas as pd

    from compute.output.writer import write_benchmarks_json

    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    spy = pd.DataFrame(
        {"Adj Close": [470.0, 472.5, 471.0], "Close": [469.0, 472.0, 470.5]}, index=idx
    )
    qqq = pd.DataFrame({"Close": [400.0, 401.0, 402.0]}, index=idx)  # no Adj Close
    path, coverage = write_benchmarks_json(
        {"SPY": spy, "QQQ": qqq, "DIA": None, "IWM": None}, tmp_path
    )
    assert path == tmp_path / "portfolio" / "benchmarks.json"
    assert coverage == 50.0  # 2 of 4 had data
    payload = json.loads(path.read_text())
    assert payload["dates"] == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert payload["spy"] == [470.0, 472.5, 471.0]  # Adj Close preferred
    assert payload["qqq"] == [400.0, 401.0, 402.0]  # Close fallback
    assert payload["dia"] == [None, None, None]
    assert payload["iwm"] == [None, None, None]


def test_write_benchmarks_json_union_dates_and_nan(tmp_path):
    """Union of trading dates; NaN and missing-date both serialize to null."""
    import pandas as pd

    from compute.output.writer import write_benchmarks_json

    spy = pd.DataFrame(
        {"Adj Close": [470.0, float("nan"), 471.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    qqq = pd.DataFrame(  # missing the middle date → null on the union axis
        {"Adj Close": [400.0, 402.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-04"]),
    )
    path, coverage = write_benchmarks_json({"SPY": spy, "QQQ": qqq}, tmp_path)
    payload = json.loads(path.read_text())
    assert payload["dates"] == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert payload["spy"] == [470.0, None, 471.0]  # NaN → null
    assert payload["qqq"] == [400.0, None, 402.0]  # missing date → null
    assert coverage == 100.0


def test_write_benchmarks_json_all_empty_returns_none(tmp_path):
    """No usable benchmark → (None, 0.0); the cron must continue (display-only)."""
    from compute.output.writer import write_benchmarks_json

    path, coverage = write_benchmarks_json({"SPY": None, "QQQ": None}, tmp_path)
    assert path is None
    assert coverage == 0.0


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


# -- prune_orphan_stock_files (release-hygiene: drop de-listed tickers) ------


def _seed_stock_files(data_dir, tickers) -> None:
    """Create dummy detail + history JSON for each ticker under data_dir."""
    (data_dir / "stocks").mkdir(parents=True, exist_ok=True)
    (data_dir / "stocks" / "history").mkdir(parents=True, exist_ok=True)
    for t in tickers:
        (data_dir / "stocks" / f"{t}.json").write_text("{}")
        (data_dir / "stocks" / "history" / f"{t}.json").write_text("{}")


def _big_keep() -> list[str]:
    """A keep set comfortably above _PRUNE_SAFETY_FLOOR (50)."""
    return [f"T{i:03d}" for i in range(60)]


def test_prune_orphan_stock_files_removes_dropped_ticker(tmp_path):
    """An index de-listing (EPAM) → detail + history both pruned; kept survive."""
    keep = _big_keep()
    _seed_stock_files(tmp_path, [*keep[:3], "EPAM"])  # 3 current + 1 orphan
    # Pass a generator to prove the Iterable contract (main.py passes one).
    pruned = prune_orphan_stock_files(iter(keep), tmp_path)
    assert pruned == ["EPAM"]
    assert not (tmp_path / "stocks" / "EPAM.json").exists()
    assert not (tmp_path / "stocks" / "history" / "EPAM.json").exists()
    # A retained ticker keeps BOTH files.
    assert (tmp_path / "stocks" / f"{keep[0]}.json").exists()
    assert (tmp_path / "stocks" / "history" / f"{keep[0]}.json").exists()


def test_prune_orphan_stock_files_multiple_sorted_and_history_only(tmp_path):
    """Returns sorted tickers; a history-only orphan (no detail file) is pruned too."""
    keep = _big_keep()
    _seed_stock_files(tmp_path, keep[:2])
    for t in ("ZZZ", "ABC"):  # two full orphans (detail + history)
        (tmp_path / "stocks" / f"{t}.json").write_text("{}")
        (tmp_path / "stocks" / "history" / f"{t}.json").write_text("{}")
    # Orphan that only ever wrote a history file (no detail) — still pruned.
    (tmp_path / "stocks" / "history" / "HONLY.json").write_text("{}")
    pruned = prune_orphan_stock_files(keep, tmp_path)
    assert pruned == ["ABC", "HONLY", "ZZZ"]
    assert not (tmp_path / "stocks" / "history" / "HONLY.json").exists()


def test_prune_orphan_stock_files_safety_floor_skips_small_keep(tmp_path):
    """A degraded run (keep set < floor) must NOT delete anything — even orphans."""
    _seed_stock_files(tmp_path, ["AAPL", "MSFT", "EPAM"])
    pruned = prune_orphan_stock_files(["AAPL", "MSFT"], tmp_path)  # 2 < floor 50
    assert pruned == []
    assert (tmp_path / "stocks" / "EPAM.json").exists()
    assert (tmp_path / "stocks" / "AAPL.json").exists()


def test_prune_orphan_stock_files_empty_keep_skips(tmp_path):
    """Empty keep set (degenerate run) → no-op, never wipes the directory."""
    _seed_stock_files(tmp_path, ["AAPL"])
    assert prune_orphan_stock_files([], tmp_path) == []
    assert (tmp_path / "stocks" / "AAPL.json").exists()


def test_prune_orphan_stock_files_missing_dir_no_error(tmp_path):
    """No stocks/ directory yet (fresh checkout) → returns [] without error."""
    assert prune_orphan_stock_files(_big_keep(), tmp_path) == []


def test_prune_orphan_stock_files_at_floor_boundary_prunes(tmp_path):
    """keep size == _PRUNE_SAFETY_FLOOR is NOT < floor → prune fires (pins the `<`)."""
    keep = [f"T{i:03d}" for i in range(_PRUNE_SAFETY_FLOOR)]  # exactly the floor
    _seed_stock_files(tmp_path, keep[:1])
    (tmp_path / "stocks" / "ORPHAN.json").write_text("{}")
    assert prune_orphan_stock_files(keep, tmp_path) == ["ORPHAN"]
    assert not (tmp_path / "stocks" / "ORPHAN.json").exists()


def test_prune_orphan_stock_files_below_floor_boundary_skips(tmp_path):
    """keep size == floor - 1 IS < floor → prune skipped (companion boundary; an
    `<` → `<=` mutation would wrongly prune here)."""
    keep = [f"T{i:03d}" for i in range(_PRUNE_SAFETY_FLOOR - 1)]
    (tmp_path / "stocks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "stocks" / "ORPHAN.json").write_text("{}")
    assert prune_orphan_stock_files(keep, tmp_path) == []
    assert (tmp_path / "stocks" / "ORPHAN.json").exists()


def test_write_stock_detail_pre_split_raw_field_round_trip(tmp_path):
    """P2-2: ``RawMetrics.shares_outstanding_pre_split_raw`` (#499 field) must
    survive a full write_stock_detail → read JSON round-trip with its exact
    float value intact.

    This is the audit-trail contract (SKILL.md Rule 9): the pre-correction raw
    EDGAR share count is preserved alongside the corrected value so a post-cron
    audit can compute the delta independently.  The field is ``None`` on normal
    rows (no split detected); only non-None when ``post_split_share_lag`` is in
    ``valuation_warnings``.
    """
    detail = StockDetail(
        ticker="KLAC",
        name="KLA Corporation",
        sector="Information Technology",
        industry="Semiconductor Equipment",
        current_price=750.0,
        rank=2,
        composite_score=82.1,
        raw_metrics=RawMetrics(
            revenue=10_500_000_000.0,
            shares_outstanding=260_200_000.0,  # corrected (post-split × 2)
            shares_outstanding_pre_split_raw=130_600_000.0,  # raw EDGAR before correction
            market_cap=195_150_000_000.0,
        ),
        valuation_warnings=["post_split_share_lag"],  # matches the non-None condition
    )
    out = write_stock_detail(detail, tmp_path)
    payload = json.loads(out.read_text())

    raw_metrics = payload["raw_metrics"]
    assert raw_metrics["shares_outstanding_pre_split_raw"] == 130_600_000.0, (
        "shares_outstanding_pre_split_raw must survive the JSON round-trip "
        f"unchanged; got {raw_metrics['shares_outstanding_pre_split_raw']!r}"
    )
    assert raw_metrics["shares_outstanding"] == 260_200_000.0
    assert payload["valuation_warnings"] == ["post_split_share_lag"]


def test_write_stock_detail_pre_split_raw_field_null_on_normal_row(tmp_path):
    """P2-2 complement: ``shares_outstanding_pre_split_raw`` must be ``null`` in
    the JSON for a normal (no-split) row.  This guards against the field being
    accidentally populated for every ticker when it should only appear on split-
    correction rows (SKILL.md Rule 9 audit-trail discipline).
    """
    detail = StockDetail(
        ticker="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        current_price=220.0,
        rank=1,
        composite_score=88.0,
        raw_metrics=RawMetrics(
            shares_outstanding=15_550_000_000.0,
            # shares_outstanding_pre_split_raw intentionally omitted (defaults None)
        ),
    )
    out = write_stock_detail(detail, tmp_path)
    payload = json.loads(out.read_text())

    assert payload["raw_metrics"]["shares_outstanding_pre_split_raw"] is None, (
        "shares_outstanding_pre_split_raw must be null for a normal (no-split) row"
    )


def test_prune_orphan_stock_files_ignores_non_json_files(tmp_path):
    """The glob is `*.json` — a non-JSON file in stocks/ is never an unlink target."""
    keep = _big_keep()
    _seed_stock_files(tmp_path, keep[:2])
    (tmp_path / "stocks" / "README.txt").write_text("not a stock file")
    (tmp_path / "stocks" / "ZZZ.json").write_text("{}")  # a real orphan
    assert prune_orphan_stock_files(keep, tmp_path) == ["ZZZ"]
    assert (tmp_path / "stocks" / "README.txt").exists()  # untouched
    assert not (tmp_path / "stocks" / "ZZZ.json").exists()


def test_prune_orphan_stock_files_unlink_failure_does_not_abort(tmp_path, monkeypatch):
    """One un-removable orphan must not abort the prune (the documented per-file
    try/except) — the other orphan is still pruned."""
    keep = _big_keep()
    (tmp_path / "stocks").mkdir(parents=True, exist_ok=True)
    for t in ("AAA", "ZZZ"):
        (tmp_path / "stocks" / f"{t}.json").write_text("{}")
    real_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.stem == "AAA":
            raise OSError("simulated permission error")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    pruned = prune_orphan_stock_files(keep, tmp_path)
    assert pruned == ["ZZZ"]  # the failing orphan is absent from the return
    assert (tmp_path / "stocks" / "AAA.json").exists()  # survived its OSError
    assert not (tmp_path / "stocks" / "ZZZ.json").exists()  # the other was pruned
