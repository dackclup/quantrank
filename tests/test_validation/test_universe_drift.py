"""Tests for ``compute.validation.universe_drift``."""

from __future__ import annotations

from datetime import date

import pytest

from compute.ingest import historical_universe as hu
from compute.validation.universe_drift import (
    compute_universe_drift,
    format_drift_report,
)


@pytest.fixture(autouse=True)
def _clear_event_cache() -> None:
    hu._load_events.cache_clear()
    yield
    hu._load_events.cache_clear()


@pytest.fixture
def current_universe_sample() -> frozenset[str]:
    """Mix of always-in + added-during-window tickers."""
    return frozenset({
        "AAPL", "MSFT", "GOOGL", "NVDA", "META", "AMZN",
        "TSLA",  # added 2020-12-21
        "SMCI",  # added 2024-03-18
        "DASH",  # added 2025-09-22
        "FSLR",  # added 2023-03-15
        "PANW",  # added 2023-06-20
    })


def test_drift_report_added_since_includes_recent_additions(
    current_universe_sample: frozenset[str],
) -> None:
    """At 2022-01-01: SMCI, DASH, FSLR, PANW should be in 'added_since'."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2022, 1, 1),
        current_universe_sample,
        anchor_date=today,
    )
    # All 4 tickers added AFTER 2022-01-01 → in added_since
    assert "SMCI" in report.added_since
    assert "DASH" in report.added_since
    assert "FSLR" in report.added_since
    assert "PANW" in report.added_since
    # TSLA added 2020-12-21, BEFORE 2022-01-01 → in unchanged
    assert "TSLA" in report.unchanged
    # Always-in cohort
    assert "AAPL" in report.unchanged
    assert "MSFT" in report.unchanged


def test_drift_report_removed_since_includes_delistings(
    current_universe_sample: frozenset[str],
) -> None:
    """At 2023-03-12 (before the 2023-03-15 removal), SIVB should be in removed_since."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2023, 3, 12),
        current_universe_sample,
        anchor_date=today,
    )
    # SVB Financial (ticker SIVB) was in the S&P 500 on 2023-03-12 and was
    # removed effective 2023-03-15 (bank failure) → in removed_since. (NOT in
    # current_universe_sample, but historically WAS there.) The prior ledger's
    # "SVB" + 2023-03-13 announce-date was corrected in the Phase 7.0 PR-0 rebuild.
    assert "SIVB" in report.removed_since


def test_drift_report_anchor_date_is_zero_drift(
    current_universe_sample: frozenset[str],
) -> None:
    """as_of_date == anchor_date → no drift."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        today,
        current_universe_sample,
        anchor_date=today,
    )
    assert len(report.added_since) == 0
    assert len(report.removed_since) == 0
    assert report.unchanged == current_universe_sample
    assert report.is_complete is True


def test_drift_report_pre_coverage_is_degraded(
    current_universe_sample: frozenset[str],
) -> None:
    """Pre-EARLIEST_EVENT_DATE → is_complete=False; drift sets reflect fallback."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2010, 1, 1),
        current_universe_sample,
        anchor_date=today,
    )
    assert report.is_complete is False
    # Degraded: members_at returns current → drift symmetric-diff is empty
    assert len(report.added_since) == 0
    assert len(report.removed_since) == 0
    assert report.unchanged == current_universe_sample


def test_drift_report_future_date_raises(
    current_universe_sample: frozenset[str],
) -> None:
    """Future as_of_date propagates ValueError from members_at."""
    today = date(2026, 5, 27)
    with pytest.raises(ValueError, match="future"):
        compute_universe_drift(
            date(2027, 1, 1),
            current_universe_sample,
            anchor_date=today,
        )


def test_drift_report_set_partition_invariant(
    current_universe_sample: frozenset[str],
) -> None:
    """added + unchanged = current; removed + unchanged = historical (per members_at)."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2022, 6, 1),
        current_universe_sample,
        anchor_date=today,
    )
    # Partition invariants
    assert report.added_since | report.unchanged == current_universe_sample
    assert report.added_since & report.unchanged == frozenset()
    assert report.removed_since & report.unchanged == frozenset()
    assert report.removed_since & report.added_since == frozenset()


def test_drift_report_size_invariant(current_universe_sample: frozenset[str]) -> None:
    """current_size = added + unchanged; historical_size = removed + unchanged."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2023, 6, 1),
        current_universe_sample,
        anchor_date=today,
    )
    assert report.current_size == len(report.added_since) + len(report.unchanged)
    assert report.universe_size_at_as_of == len(report.removed_since) + len(report.unchanged)


def test_format_drift_report_renders_required_sections(
    current_universe_sample: frozenset[str],
) -> None:
    """Human-readable rendering contains the 4 key section labels."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2023, 1, 1),
        current_universe_sample,
        anchor_date=today,
    )
    text = format_drift_report(report)
    assert "Universe drift report" in text
    assert "ADDED since as_of" in text
    assert "REMOVED since as_of" in text
    assert "UNCHANGED" in text
    assert "SURVIVORSHIP-BIAS-CORRECTED cohort" in text


def test_format_drift_report_caps_listed_at_max_listed(
    current_universe_sample: frozenset[str],
) -> None:
    """When >max_listed tickers in a category, output uses '+N more' suffix."""
    today = date(2026, 5, 27)
    # Synthetic large current universe to force many 'added_since' entries
    large = frozenset(
        list(current_universe_sample) + [f"FOO{i:03d}" for i in range(50)]
    )
    report = compute_universe_drift(
        date(2024, 1, 1),
        large,
        anchor_date=today,
    )
    text = format_drift_report(report, max_listed=5)
    # 50+ synthetic tickers in added → '+N more' should appear
    if len(report.added_since) > 5:
        assert "+" in text and "more" in text


def test_universe_drift_report_dataclass_is_frozen(
    current_universe_sample: frozenset[str],
) -> None:
    """UniverseDriftReport is immutable — accidental field mutation raises."""
    today = date(2026, 5, 27)
    report = compute_universe_drift(
        date(2023, 6, 1),
        current_universe_sample,
        anchor_date=today,
    )
    with pytest.raises((AttributeError, Exception)):
        report.as_of_date = date(2020, 1, 1)  # type: ignore[misc]


def test_drift_anchor_date_defaults_to_today(
    current_universe_sample: frozenset[str],
) -> None:
    """anchor_date=None uses today UTC (smoke check)."""
    report = compute_universe_drift(
        date(2023, 6, 1),
        current_universe_sample,
        anchor_date=None,
    )
    # Just check it ran and anchor_date is set to something current-ish
    assert report.anchor_date.year >= 2025
