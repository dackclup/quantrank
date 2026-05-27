"""Tests for ``compute.validation.manipulation_distribution``.

Phase 4.6 task #2e — manipulation-index distribution shift report.
"""

from __future__ import annotations

from datetime import date

from compute.validation import manipulation_distribution as md
from compute.validation.manipulation_distribution import (
    LOW_UPPER,
    MODERATE_UPPER,
    DistributionSummary,
    ShiftReport,
    compute_manipulation_distribution_shift,
    format_shift_report,
)

# ---------------------------------------------------------------- Band constants


def test_band_boundaries_match_ui_card() -> None:
    """LOW < 20 ≤ MODERATE < 50 ≤ HIGH per ManipulationRiskCard 3-band chip."""
    assert LOW_UPPER == 20.0
    assert MODERATE_UPPER == 50.0


# ---------------------------------------------------------------- _summarize_one_date


def test_summarize_one_date_partitions_bands_correctly() -> None:
    """Values across 3 bands → correct band counts."""
    import pandas as pd

    # 5 LOW (< 20), 3 MODERATE (20-50), 2 HIGH (>= 50)
    series = pd.Series(
        [1.0, 5.0, 10.0, 15.0, 19.99,   # LOW
         20.0, 30.0, 45.0,               # MODERATE
         50.0, 84.0],                    # HIGH
        index=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
    )
    summary = md._summarize_one_date(date(2026, 5, 1), series)
    assert summary.low_count == 5
    assert summary.moderate_count == 3
    assert summary.high_count == 2
    assert summary.n_non_null == 10


def test_summarize_one_date_empty_series_returns_zero() -> None:
    """All-NaN input → all zeros, no division error."""
    import numpy as np
    import pandas as pd

    series = pd.Series([np.nan, np.nan], index=["X", "Y"])
    summary = md._summarize_one_date(date(2026, 5, 1), series)
    assert summary.n_non_null == 0
    assert summary.mean == 0.0
    assert summary.high_count == 0


def test_summarize_one_date_top_3_descending() -> None:
    """top_3_tickers sorted by manipulation_index descending."""
    import pandas as pd

    series = pd.Series(
        [84.0, 10.0, 30.0, 50.0, 15.0],
        index=["SMCI", "AAPL", "NVDA", "WAT", "MSFT"],
    )
    summary = md._summarize_one_date(date(2026, 5, 1), series)
    top = summary.top_3_tickers
    assert len(top) == 3
    # Highest first
    assert top[0] == ("SMCI", 84.0)
    assert top[1] == ("WAT", 50.0)
    assert top[2] == ("NVDA", 30.0)


# ---------------------------------------------------------------- empty / degenerate


def test_compute_shift_empty_window_returns_empty_report(monkeypatch) -> None:
    """No commits in window → empty per_date_summary, deltas None."""

    def empty_loader(*args, **kwargs):
        import pandas as pd
        return pd.DataFrame(columns=["manipulation_index"]).set_index(
            pd.MultiIndex.from_tuples([], names=["date", "ticker"])
        )

    monkeypatch.setattr(md, "load_ranking_history", empty_loader)
    report = compute_manipulation_distribution_shift(
        start_date=date(2099, 1, 1), end_date=date(2099, 12, 31),
    )
    assert report.per_date_summary == {}
    assert report.mean_delta is None
    assert "empty window" in report.note


def test_compute_shift_all_null_window_handled(monkeypatch) -> None:
    """All-None manipulation_index → empty report with explicit note."""
    import pandas as pd

    def null_loader(*args, **kwargs):
        idx = pd.MultiIndex.from_tuples(
            [(date(2024, 1, 1), "AAPL")], names=["date", "ticker"],
        )
        return pd.DataFrame({"manipulation_index": [None]}, index=idx)

    monkeypatch.setattr(md, "load_ranking_history", null_loader)
    report = compute_manipulation_distribution_shift()
    assert report.per_date_summary == {}
    assert "pre-phase4.5f" in report.note


def test_compute_shift_single_date_window(monkeypatch) -> None:
    """Single date → 1 summary, delta fields None with explicit note."""
    import pandas as pd

    def one_date_loader(*args, **kwargs):
        idx = pd.MultiIndex.from_tuples(
            [(date(2024, 1, 1), "AAPL"), (date(2024, 1, 1), "NVDA")],
            names=["date", "ticker"],
        )
        return pd.DataFrame(
            {"manipulation_index": [10.0, 50.0]}, index=idx,
        )

    monkeypatch.setattr(md, "load_ranking_history", one_date_loader)
    report = compute_manipulation_distribution_shift()
    assert len(report.per_date_summary) == 1
    assert report.mean_delta is None
    assert "single date" in report.note


# ---------------------------------------------------------------- happy path


def test_compute_shift_two_date_window_computes_deltas(monkeypatch) -> None:
    """2 dates → deltas populated; high_count delta correct."""
    import pandas as pd

    def two_date_loader(*args, **kwargs):
        idx = pd.MultiIndex.from_tuples(
            [
                (date(2024, 1, 1), "AAPL"),    # mi=5 (LOW)
                (date(2024, 1, 1), "NVDA"),    # mi=10 (LOW)
                (date(2024, 1, 1), "SMCI"),    # mi=50 (HIGH)
                (date(2024, 6, 1), "AAPL"),    # mi=15 (LOW)
                (date(2024, 6, 1), "NVDA"),    # mi=60 (HIGH)
                (date(2024, 6, 1), "SMCI"),    # mi=80 (HIGH)
            ],
            names=["date", "ticker"],
        )
        return pd.DataFrame(
            {"manipulation_index": [5.0, 10.0, 50.0, 15.0, 60.0, 80.0]},
            index=idx,
        )

    monkeypatch.setattr(md, "load_ranking_history", two_date_loader)
    report = compute_manipulation_distribution_shift()
    assert len(report.per_date_summary) == 2
    # Mean shifted up: first=21.67, last=51.67
    assert report.mean_delta is not None
    assert report.mean_delta > 0
    # HIGH count went 1 → 2
    assert report.high_count_first == 1
    assert report.high_count_last == 2
    assert report.high_count_delta == 1


# ---------------------------------------------------------------- format_shift_report


def test_format_shift_report_renders_header_and_columns(monkeypatch) -> None:
    """Text rendering contains header + per-date columns + Δ section when 2+ dates."""
    import pandas as pd

    def two_date_loader(*args, **kwargs):
        idx = pd.MultiIndex.from_tuples(
            [
                (date(2024, 1, 1), "AAPL"),
                (date(2024, 6, 1), "AAPL"),
            ],
            names=["date", "ticker"],
        )
        return pd.DataFrame(
            {"manipulation_index": [5.0, 15.0]}, index=idx,
        )

    monkeypatch.setattr(md, "load_ranking_history", two_date_loader)
    report = compute_manipulation_distribution_shift()
    text = format_shift_report(report)
    assert "Manipulation-index distribution shift report" in text
    assert "window" in text
    assert "Window-end deltas" in text
    assert "Per-date summary" in text


def test_format_shift_report_caps_long_windows() -> None:
    """When dates > max_dates, output uses '... (truncated; ...) ...'."""
    from compute.validation.manipulation_distribution import format_shift_report

    # Synthetic ShiftReport with 30 dates
    summaries = {
        date(2024, 1, d): DistributionSummary(
            n_tickers=10, n_non_null=10,
            mean=10.0, std=5.0, median=8.0,
            q25=3.0, q75=15.0, q95=25.0, max_value=30.0,
            low_count=5, moderate_count=3, high_count=2,
            top_3_tickers=(("AAA", 30.0),),
        )
        for d in range(1, 31)
    }
    report = ShiftReport(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 30),
        n_dates=30,
        n_unique_tickers=10,
        per_date_summary=summaries,
        mean_delta=0.0,
        std_delta=0.0,
        high_count_delta=0,
        high_count_first=2,
        high_count_last=2,
        note="synthetic",
    )
    text = format_shift_report(report, max_dates=10)
    assert "truncated" in text


# ---------------------------------------------------------------- live-git smoke


def test_compute_shift_live_repo_recent_window() -> None:
    """Smoke test against the real repo's recent cron commits."""
    report = compute_manipulation_distribution_shift(
        start_date=date(2026, 5, 22),
        end_date=date(2026, 5, 27),
    )
    # rankings.json is post-0.8.0-phase4.5f → manipulation_index present
    assert report.n_dates >= 1
    if report.n_dates >= 1:
        first_summary = next(iter(report.per_date_summary.values()))
        # Universe-scale: ~500 tickers per date
        assert first_summary.n_non_null > 100
        # Mean manipulation_index should be in [0, 100] band
        assert 0.0 <= first_summary.mean <= 100.0
