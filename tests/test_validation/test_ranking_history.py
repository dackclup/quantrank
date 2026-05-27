"""Tests for ``compute.validation.ranking_history``.

Phase 4.6 task #2a — git-archived rankings.json time-series loader.

Tests cover the pure-function units against the real repo's git history
(rankings.json IS committed daily by the cron). For helpers that don't
need git access, synthetic data is used.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from compute.validation.ranking_history import (
    DEFAULT_COLUMNS,
    DEFAULT_RANKINGS_PATH,
    dedupe_by_date,
    list_ranking_commits,
    load_ranking_history,
    load_snapshot_at,
)

# ---------------------------------------------------------------- dedupe_by_date


def test_dedupe_by_date_keeps_latest_per_day() -> None:
    """Input sorted ascending; multiple commits same date → latest wins."""
    commits = [
        ("sha1", date(2026, 5, 26)),
        ("sha2", date(2026, 5, 26)),
        ("sha3", date(2026, 5, 26)),
        ("sha4", date(2026, 5, 27)),
    ]
    out = dedupe_by_date(commits, prefer="latest")
    assert len(out) == 2
    by_date = dict((d, sha) for sha, d in out)
    assert by_date[date(2026, 5, 26)] == "sha3"  # last in input
    assert by_date[date(2026, 5, 27)] == "sha4"


def test_dedupe_by_date_keeps_earliest_per_day() -> None:
    commits = [
        ("sha1", date(2026, 5, 26)),
        ("sha2", date(2026, 5, 26)),
        ("sha3", date(2026, 5, 27)),
    ]
    out = dedupe_by_date(commits, prefer="earliest")
    by_date = dict((d, sha) for sha, d in out)
    assert by_date[date(2026, 5, 26)] == "sha1"  # first in input


def test_dedupe_by_date_invalid_prefer_raises() -> None:
    with pytest.raises(ValueError, match="prefer"):
        dedupe_by_date([("sha1", date(2026, 5, 26))], prefer="middle")


def test_dedupe_by_date_empty_returns_empty() -> None:
    assert dedupe_by_date([]) == []


def test_dedupe_by_date_returns_sorted_ascending() -> None:
    commits = [
        ("sha3", date(2026, 5, 27)),
        ("sha1", date(2026, 5, 25)),
        ("sha2", date(2026, 5, 26)),
    ]
    out = dedupe_by_date(commits, prefer="latest")
    dates = [d for _, d in out]
    assert dates == sorted(dates)


# ---------------------------------------------------------------- list_ranking_commits (live git)


def test_list_ranking_commits_returns_real_commits() -> None:
    """Smoke test against the real repo's git history."""
    commits = list_ranking_commits()
    assert len(commits) >= 1  # rankings.json is committed daily by the cron
    # Sorted ascending
    for prev, curr in zip(commits, commits[1:], strict=False):
        assert prev[1] <= curr[1]
    # Sample row well-formed
    sha, d = commits[0]
    assert isinstance(sha, str) and len(sha) == 40
    assert isinstance(d, date)


def test_list_ranking_commits_date_filter() -> None:
    """start_date / end_date narrow the result correctly."""
    commits = list_ranking_commits(
        start_date=date(2026, 5, 22),
        end_date=date(2026, 5, 23),
    )
    for _, d in commits:
        assert date(2026, 5, 22) <= d <= date(2026, 5, 23)


def test_list_ranking_commits_empty_window() -> None:
    """Far-future window returns empty list, not error."""
    commits = list_ranking_commits(
        start_date=date(2099, 1, 1),
        end_date=date(2099, 12, 31),
    )
    assert commits == []


# ---------------------------------------------------------------- load_snapshot_at (live git)


def test_load_snapshot_at_returns_json_list() -> None:
    """Snapshot at HEAD parses cleanly + contains rankings entries."""
    snapshot = load_snapshot_at("HEAD")
    assert isinstance(snapshot, list)
    assert len(snapshot) >= 1  # rankings is non-empty
    # First row should have ticker + composite_score
    first = snapshot[0]
    assert "ticker" in first
    assert "composite_score" in first


def test_load_snapshot_at_missing_commit_returns_empty() -> None:
    """git show on a SHA that doesn't have the file → empty list, no raise."""
    # Use a known-old SHA from the project's pre-rankings.json era
    # (the very first commits before frontend/public/data existed).
    # If unable to construct a valid bad sha, use a 40-hex string that
    # is not a real commit — git show will fail, we expect empty list.
    snapshot = load_snapshot_at("0000000000000000000000000000000000000000")
    assert snapshot == []


# ---------------------------------------------------------------- load_ranking_history (live git)


def test_load_ranking_history_smoke_recent_window() -> None:
    """Load a small window of recent cron commits."""
    df = load_ranking_history(
        start_date=date(2026, 5, 22),
        end_date=date(2026, 5, 27),
    )
    assert isinstance(df, pd.DataFrame)
    # Multi-index (date, ticker)
    assert df.index.nlevels == 2
    assert df.index.names == ["date", "ticker"]
    assert "composite_score" in df.columns


def test_load_ranking_history_default_columns_is_composite_score() -> None:
    """DEFAULT_COLUMNS = composite_score only."""
    assert DEFAULT_COLUMNS == ("composite_score",)


def test_load_ranking_history_custom_columns() -> None:
    """Custom column tuple extracts multiple fields."""
    df = load_ranking_history(
        start_date=date(2026, 5, 26),
        end_date=date(2026, 5, 26),
        columns=("composite_score", "current_price"),
    )
    if not df.empty:
        assert "composite_score" in df.columns
        assert "current_price" in df.columns


def test_load_ranking_history_empty_window_returns_empty_df() -> None:
    df = load_ranking_history(
        start_date=date(2099, 1, 1),
        end_date=date(2099, 12, 31),
    )
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_load_ranking_history_dedupes_dates_by_default() -> None:
    """With dedupe_dates=True (default), each unique date appears once."""
    df = load_ranking_history(
        start_date=date(2026, 5, 26),
        end_date=date(2026, 5, 26),
    )
    if not df.empty:
        dates_in_index = df.index.get_level_values("date").unique()
        assert len(dates_in_index) == 1  # single unique date


def test_default_rankings_path_is_canonical() -> None:
    assert DEFAULT_RANKINGS_PATH == "frontend/public/data/rankings.json"


# ---------------------------------------------------------------- JSON-malformed handling


def test_load_ranking_history_handles_json_parse_error(
    tmp_path,
    monkeypatch,
) -> None:
    """If a snapshot is malformed, the loader logs + continues."""
    # Inject a fake _run_git that returns invalid JSON for one snapshot
    from compute.validation import ranking_history as rh

    call_count = {"n": 0}

    def fake_run_git(args, *, repo=None):
        if args[0] == "log":
            return "sha_bad 2026-05-25\nsha_good 2026-05-26\n"
        if args[0] == "show":
            call_count["n"] += 1
            if "sha_bad" in args[1]:
                return "{not valid json"
            if "sha_good" in args[1]:
                return json.dumps([{"ticker": "AAPL", "composite_score": 70.0}])
        return ""

    monkeypatch.setattr(rh, "_run_git", fake_run_git)
    df = rh.load_ranking_history()
    # Good snapshot parsed; bad one skipped
    assert "AAPL" in df.index.get_level_values("ticker")


def test_load_ranking_history_skips_rows_missing_columns(monkeypatch) -> None:
    """Rows missing ticker OR a requested column are silently skipped."""
    from compute.validation import ranking_history as rh

    def fake_run_git(args, *, repo=None):
        if args[0] == "log":
            return "shaA 2026-05-26\n"
        if args[0] == "show":
            return json.dumps([
                {"ticker": "AAPL", "composite_score": 70.0},  # complete
                {"ticker": "MSFT"},  # missing column
                {"composite_score": 50.0},  # missing ticker
            ])
        return ""

    monkeypatch.setattr(rh, "_run_git", fake_run_git)
    df = rh.load_ranking_history(columns=("composite_score",))
    tickers = list(df.index.get_level_values("ticker"))
    assert tickers == ["AAPL"]
