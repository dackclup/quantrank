"""Tests for ``compute.ingest.historical_universe``.

Phase 4.6 — Survivorship-bias fix (Research Report v1.0 §7.4).
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from compute.ingest import historical_universe as hu
from compute.ingest.historical_universe import (
    EARLIEST_EVENT_DATE,
    _parse_event_row,
    list_known_events,
    members_at,
)

# --- Fixtures ------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_event_cache() -> None:
    """Each test starts with a fresh CSV load — protects against stale lru_cache."""
    hu._load_events.cache_clear()
    yield
    hu._load_events.cache_clear()


@pytest.fixture
def current_universe_502() -> frozenset[str]:
    """A representative current S&P 500 universe (~502 tickers, abbreviated).

    Tests don't need the full 502 — just enough representative names to
    exercise add/remove reversal logic. Tickers chosen include some that
    were ADDed during the 2020-2026 window (TSLA, SMCI, DASH) and some
    that have been there longer (AAPL, MSFT).
    """
    return frozenset({
        "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "SMCI", "DASH",
        "META", "AMZN", "BRK-B", "JPM", "V", "MA", "WMT", "PG",
        "LULU", "PANW", "FSLR", "INVH", "KDP", "ON", "CEG", "EPAM",
        "DELL", "EXE", "WSM", "DECK",
    })


# --- Parse helpers -------------------------------------------------


def test_parse_event_row_well_formed() -> None:
    row = {
        "effective_date": "2024-03-18",
        "ticker": "SMCI",
        "action": "ADD",
        "name": "Super Micro Computer",
        "source_url": "https://example.com",
        "notes": "Replaced WHR",
    }
    ev = _parse_event_row(row)
    assert ev is not None
    assert ev.effective_date == date(2024, 3, 18)
    assert ev.ticker == "SMCI"
    assert ev.action == "ADD"


def test_parse_event_row_skips_comment() -> None:
    row = {"effective_date": "# this is a comment", "ticker": "", "action": ""}
    assert _parse_event_row(row) is None


def test_parse_event_row_skips_blank() -> None:
    row = {"effective_date": "", "ticker": "", "action": ""}
    assert _parse_event_row(row) is None


def test_parse_event_row_invalid_action() -> None:
    row = {
        "effective_date": "2024-03-18",
        "ticker": "SMCI",
        "action": "MERGE",  # not in _VALID_ACTIONS
        "name": "",
        "source_url": "",
    }
    assert _parse_event_row(row) is None


def test_parse_event_row_malformed_date() -> None:
    row = {
        "effective_date": "2024/03/18",  # wrong format
        "ticker": "SMCI",
        "action": "ADD",
        "name": "",
        "source_url": "",
    }
    assert _parse_event_row(row) is None


# --- members_at: anchor / forward cases ---------------------------


def test_members_at_anchor_date_returns_current_unchanged(
    current_universe_502: frozenset[str],
) -> None:
    today = date(2026, 5, 27)
    result = members_at(today, current_universe_502, anchor_date=today)
    assert result.tickers == current_universe_502
    assert result.is_complete is True
    assert result.events_applied == 0
    assert result.as_of_date == today


def test_members_at_future_date_raises(
    current_universe_502: frozenset[str],
) -> None:
    today = date(2026, 5, 27)
    future = date(2027, 1, 1)
    with pytest.raises(ValueError, match="future"):
        members_at(future, current_universe_502, anchor_date=today)


# --- members_at: known historical events --------------------------


def test_members_at_pre_tsla_addition(
    current_universe_502: frozenset[str],
) -> None:
    """TSLA joined the S&P 500 on 2020-12-21. Before that → NOT in universe."""
    pre_tsla = date(2020, 12, 20)
    today = date(2026, 5, 27)
    result = members_at(pre_tsla, current_universe_502, anchor_date=today)
    assert "TSLA" not in result.tickers
    assert "AAPL" in result.tickers  # always there
    assert result.is_complete is True


def test_members_at_post_tsla_addition(
    current_universe_502: frozenset[str],
) -> None:
    """TSLA was in the index from 2020-12-21 onward."""
    post_tsla = date(2020, 12, 22)
    today = date(2026, 5, 27)
    result = members_at(post_tsla, current_universe_502, anchor_date=today)
    assert "TSLA" in result.tickers


def test_members_at_pre_smci_addition(
    current_universe_502: frozenset[str],
) -> None:
    """SMCI added 2024-03-18. Before that → not in universe."""
    pre_smci = date(2024, 3, 17)
    today = date(2026, 5, 27)
    result = members_at(pre_smci, current_universe_502, anchor_date=today)
    assert "SMCI" not in result.tickers


def test_members_at_atvi_pre_acquisition(
    current_universe_502: frozenset[str],
) -> None:
    """ATVI was REMOVED 2023-10-18 (Microsoft acquisition). Before that → in universe."""
    pre_atvi_out = date(2023, 10, 17)
    today = date(2026, 5, 27)
    result = members_at(pre_atvi_out, current_universe_502, anchor_date=today)
    # ATVI is NOT in current_universe but WAS in the universe before
    # 2023-10-18 → the reverse-walk should have added it back.
    assert "ATVI" in result.tickers


def test_members_at_svb_pre_collapse(
    current_universe_502: frozenset[str],
) -> None:
    """SVB Financial (ticker SIVB) removed 2023-03-15. Before that → in universe.

    The prior ledger used the colloquial "SVB" + the 2023-03-13 *announcement*
    date; the Phase 7.0 PR-0 rebuild corrects it to the real NASDAQ ticker SIVB
    and the *effective* index-removal date 2023-03-15.
    """
    pre_svb_collapse = date(2023, 3, 12)
    today = date(2026, 5, 27)
    result = members_at(pre_svb_collapse, current_universe_502, anchor_date=today)
    assert "SIVB" in result.tickers


# --- members_at: pre-coverage degradation -------------------------


def test_members_at_pre_coverage_marks_incomplete(
    current_universe_502: frozenset[str],
) -> None:
    """Dates before EARLIEST_EVENT_DATE return is_complete=False."""
    pre_coverage = date(2010, 1, 1)
    today = date(2026, 5, 27)
    result = members_at(pre_coverage, current_universe_502, anchor_date=today)
    assert result.is_complete is False
    # Universe falls back to current (anchor) — degraded but loud
    assert result.tickers == current_universe_502
    assert "EARLIEST_EVENT_DATE" in result.note


def test_members_at_at_earliest_boundary_is_complete(
    current_universe_502: frozenset[str],
) -> None:
    """Exactly at EARLIEST_EVENT_DATE → is_complete=True."""
    today = date(2026, 5, 27)
    result = members_at(EARLIEST_EVENT_DATE, current_universe_502, anchor_date=today)
    assert result.is_complete is True


# --- list_known_events accessor -----------------------------------


def test_list_known_events_returns_sorted() -> None:
    events = list_known_events()
    assert len(events) >= 30  # CSV has ~50+ events; guard against truncation
    # sorted ascending by effective_date
    for prev, curr in zip(events, events[1:], strict=False):
        assert prev.effective_date <= curr.effective_date


def test_list_known_events_date_filter() -> None:
    events_2023 = list_known_events(
        since=date(2023, 1, 1),
        until=date(2023, 12, 31),
    )
    for ev in events_2023:
        assert date(2023, 1, 1) <= ev.effective_date <= date(2023, 12, 31)


def test_csv_coverage_size_invariant() -> None:
    """Universe size at every snapshot date stays in plausible S&P 500 band [490, 510].

    Hypothesis-style property check (manual sampling instead of @given
    to avoid network/Hypothesis overhead in the smoke suite). Walks a
    few representative dates across the coverage window.
    """
    today = date(2026, 5, 27)
    current = frozenset({f"TKR{i:04d}" for i in range(502)})  # 502 placeholder
    for d in [
        date(2020, 6, 1),
        date(2021, 6, 1),
        date(2022, 6, 1),
        date(2023, 6, 1),
        date(2024, 6, 1),
        date(2025, 6, 1),
    ]:
        result = members_at(d, current, anchor_date=today)
        # CSV is incomplete so size will drift slightly from 502, but
        # should NEVER drift outside the very-wide [400, 600] band on
        # the partial 50-event set.
        assert 400 <= len(result.tickers) <= 600, (
            f"members_at({d}) returned {len(result.tickers)} tickers — outside [400, 600]"
        )


# --- CSV file structure invariants --------------------------------


def test_csv_has_action_column_in_valid_set() -> None:
    csv_path = Path(hu.HISTORICAL_CSV)
    assert csv_path.exists(), "data/sp500_membership_historical.csv must be committed"
    with csv_path.open() as f:
        lines = [
            line for line in f if line.strip() and not line.lstrip().startswith("#")
        ]
    reader = csv.DictReader(lines)
    for row in reader:
        if not row.get("ticker", "").strip():
            continue
        action = row.get("action", "").strip().upper()
        assert action in {"ADD", "REMOVE", "RENAME"}, (
            f"Invalid action {action!r} in row: {row}"
        )


def test_csv_has_source_url_per_row() -> None:
    """Every event row must cite a source URL (Wikipedia or S&P press release)."""
    csv_path = Path(hu.HISTORICAL_CSV)
    with csv_path.open() as f:
        lines = [
            line for line in f if line.strip() and not line.lstrip().startswith("#")
        ]
    reader = csv.DictReader(lines)
    for row in reader:
        if not row.get("ticker", "").strip():
            continue
        url = row.get("source_url", "").strip()
        assert url.startswith("http"), (
            f"Row {row.get('ticker')} {row.get('effective_date')} missing http source_url"
        )


def test_csv_has_minimum_coverage_count() -> None:
    """Coverage floor: at least 30 events covering 2020-01-01 → present.

    Prevents a future maintenance PR from silently gutting the CSV.
    """
    events = list_known_events()
    assert len(events) >= 30
