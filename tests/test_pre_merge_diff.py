"""Offline tests for tools/pre_merge_diff.py — Epic #125 Item 3 PR 2.

Pure-Python; no compute, no network, no fixtures from frontend/public/data.
Synthesizes tiny rankings.json + metadata.json pairs in tmp_path so the
diff logic is exercised end-to-end without a 502-ticker corpus.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.pre_merge_diff import (
    baseline_age_days,
    compute_movers,
    load_metadata,
    load_rankings,
    render_markdown,
)
from tools.pre_merge_diff import (
    main as cli_main,
)


def _write_rankings(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows))


def _write_metadata(path: Path, meta: dict) -> None:
    path.write_text(json.dumps(meta))


def test_baseline_age_days_recent():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    baseline = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    age = baseline_age_days({"last_update_utc": baseline}, now=now)
    assert age == pytest.approx(2.0, abs=0.01)


def test_baseline_age_days_stale():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    baseline = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    age = baseline_age_days({"last_update_utc": baseline}, now=now)
    assert age is not None and age > 7


def test_baseline_age_days_invalid():
    assert baseline_age_days({"last_update_utc": "not-a-timestamp"}) is None


def test_baseline_age_days_missing():
    assert baseline_age_days({}) is None


def test_compute_movers_basic_ordering():
    pr = {
        "AAA": {"rank": 1, "composite_score": 80.0},
        "BBB": {"rank": 2, "composite_score": 70.0},
        "CCC": {"rank": 3, "composite_score": 60.0},
    }
    main = {
        "AAA": {"rank": 1, "composite_score": 79.0},  # Δ +1.0
        "BBB": {"rank": 2, "composite_score": 65.0},  # Δ +5.0  ← largest |Δ|
        "CCC": {"rank": 3, "composite_score": 62.0},  # Δ -2.0
    }
    movers = compute_movers(pr, main, top_n=3)
    assert [m["ticker"] for m in movers] == ["BBB", "CCC", "AAA"]
    assert movers[0]["delta_score"] == pytest.approx(5.0)


def test_compute_movers_tiebreaker_by_ticker():
    pr = {
        "ZZZ": {"rank": 1, "composite_score": 75.0},
        "AAA": {"rank": 2, "composite_score": 75.0},
    }
    main = {
        "ZZZ": {"rank": 1, "composite_score": 70.0},
        "AAA": {"rank": 2, "composite_score": 70.0},
    }
    movers = compute_movers(pr, main)
    assert [m["ticker"] for m in movers] == ["AAA", "ZZZ"]


def test_compute_movers_excludes_unshared():
    pr = {
        "AAA": {"rank": 1, "composite_score": 80.0},
        "NEW": {"rank": 2, "composite_score": 100.0},  # PR-only
    }
    main = {
        "AAA": {"rank": 1, "composite_score": 79.0},
        "OLD": {"rank": 2, "composite_score": 99.0},  # main-only
    }
    movers = compute_movers(pr, main)
    assert {m["ticker"] for m in movers} == {"AAA"}


def test_compute_movers_top_n_cap():
    pr = {f"T{i:03d}": {"rank": i, "composite_score": 100 - i} for i in range(20)}
    main = {f"T{i:03d}": {"rank": i, "composite_score": 100 - i - 0.1 * i} for i in range(20)}
    movers = compute_movers(pr, main, top_n=5)
    assert len(movers) == 5


def test_render_markdown_universe_delta():
    pr_meta = {"universe_size": 503, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 502, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    out = render_markdown(pr_meta, main_meta, [], [], [], age_days=1.0)
    assert "| Universe size | 502 | 503 | +1 |" in out


def test_render_markdown_schema_bump_warning():
    pr_meta = {"universe_size": 502, "version": "0.9.3", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 502, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    out = render_markdown(pr_meta, main_meta, [], [], [], age_days=0.5)
    assert "⚠️ bumped" in out


def test_render_markdown_stale_baseline_warning():
    pr_meta = {"universe_size": 502, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 502, "version": "0.9.2", "last_update_utc": "2026-05-10T00:00:00Z"}
    out = render_markdown(pr_meta, main_meta, [], [], [], age_days=10.0)
    assert "days stale" in out
    assert "market drift" in out


def test_render_markdown_fresh_baseline_no_warning():
    pr_meta = {"universe_size": 502, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 502, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    out = render_markdown(pr_meta, main_meta, [], [], [], age_days=1.0)
    assert "days stale" not in out
    assert "1.0 days old" in out


def test_render_markdown_movers_table_format():
    pr_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    movers = [
        {
            "ticker": "AAPL",
            "pr_rank": 5,
            "main_rank": 12,
            "delta_rank": 7,
            "pr_score": 65.42,
            "main_score": 58.10,
            "delta_score": 7.32,
        }
    ]
    out = render_markdown(pr_meta, main_meta, movers, [], [], age_days=1.0)
    assert "| AAPL | 5 | 12 | +7 | 65.42 | 58.10 | +7.32 |" in out
    assert "Top-1 movers" in out


def test_render_markdown_negative_deltas_signed():
    pr_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    movers = [
        {
            "ticker": "NVDA",
            "pr_rank": 8,
            "main_rank": 3,
            "delta_rank": -5,
            "pr_score": 60.10,
            "main_score": 70.42,
            "delta_score": -10.32,
        }
    ]
    out = render_markdown(pr_meta, main_meta, movers, [], [], age_days=1.0)
    assert "-5" in out
    assert "-10.32" in out


def test_render_markdown_no_movers():
    pr_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    out = render_markdown(pr_meta, main_meta, [], [], [], age_days=1.0)
    assert "universe shifted entirely" in out


def test_render_markdown_movers_carry_provenance_caveat():
    """Issue #669 — the movers table must carry the cold-fetch-vs-warm-cache
    provenance caveat so reviewers don't misread benign provenance movers as
    code regressions on rank-neutral PRs."""
    pr_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    movers = [
        {
            "ticker": "KLAC",
            "pr_rank": 5,
            "main_rank": 129,
            "delta_rank": 124,
            "pr_score": 73.37,
            "main_score": 63.13,
            "delta_score": 10.24,
        }
    ]
    out = render_markdown(pr_meta, main_meta, movers, [], [], age_days=0.2)
    assert "cold-fetch (PR) vs warm-cache" in out
    assert "compute/scoring/**" in out
    assert "#669" in out


def test_render_markdown_no_movers_omits_provenance_caveat():
    """The caveat rides with the movers table — when there are no shared
    movers there is nothing to caveat, so it must not appear."""
    pr_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    out = render_markdown(pr_meta, main_meta, [], [], [], age_days=1.0)
    assert "cold-fetch (PR) vs warm-cache" not in out


def test_render_markdown_universe_additions_truncated(tmp_path):
    pr_meta = {"universe_size": 15, "version": "0.9.2", "last_update_utc": "2026-05-20T00:00:00Z"}
    main_meta = {"universe_size": 1, "version": "0.9.2", "last_update_utc": "2026-05-19T00:00:00Z"}
    added = [f"T{i:03d}" for i in range(15)]
    out = render_markdown(pr_meta, main_meta, [], added, [], age_days=1.0)
    assert "Tickers in PR only (15)" in out
    assert "5 more" in out


def test_cli_writes_output_file(tmp_path):
    pr_rankings = tmp_path / "pr_rankings.json"
    pr_metadata = tmp_path / "pr_meta.json"
    main_rankings = tmp_path / "main_rankings.json"
    main_metadata = tmp_path / "main_meta.json"
    out_path = tmp_path / "diff.md"

    _write_rankings(
        pr_rankings,
        [
            {"rank": 1, "ticker": "AAA", "composite_score": 80.0},
            {"rank": 2, "ticker": "BBB", "composite_score": 70.0},
        ],
    )
    _write_rankings(
        main_rankings,
        [
            {"rank": 1, "ticker": "AAA", "composite_score": 78.0},
            {"rank": 2, "ticker": "BBB", "composite_score": 70.5},
        ],
    )
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _write_metadata(
        pr_metadata,
        {"universe_size": 2, "version": "0.9.3", "last_update_utc": now_iso},
    )
    _write_metadata(
        main_metadata,
        {"universe_size": 2, "version": "0.9.2", "last_update_utc": now_iso},
    )

    exit_code = cli_main(
        [
            "--pr-rankings",
            str(pr_rankings),
            "--pr-metadata",
            str(pr_metadata),
            "--main-rankings",
            str(main_rankings),
            "--main-metadata",
            str(main_metadata),
            "--output",
            str(out_path),
        ]
    )

    assert exit_code == 0
    body = out_path.read_text()
    assert "## Diff vs main" in body
    assert "| AAA |" in body
    assert "⚠️ bumped" in body


def test_load_rankings_and_metadata_roundtrip(tmp_path):
    rankings_path = tmp_path / "rankings.json"
    metadata_path = tmp_path / "metadata.json"
    _write_rankings(
        rankings_path,
        [{"rank": 1, "ticker": "AAA", "composite_score": 80.0}],
    )
    _write_metadata(
        metadata_path,
        {"universe_size": 1, "version": "0.9.2"},
    )

    ranks = load_rankings(rankings_path)
    meta = load_metadata(metadata_path)

    assert ranks == {"AAA": {"rank": 1, "composite_score": 80.0}}
    assert meta["universe_size"] == 1
