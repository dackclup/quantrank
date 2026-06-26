"""Proposal A #605 extension tests for compute.validation.ic_decay.

Covers the two new behaviors added in the Proposal A consolidation:

- C12: walk_ic_history C5 graceful degradation — any internal failure
       returns empty (entries=[], panels={}, n_dates=0), never raises.
- C13: build_decay_report injection-equivalence — the injected-panels
       path and the self-walk path agree when fed the same panel data.
       AND backward-compat: build_decay_report() with no args still
       self-walks (existing behavior unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import patch

import pytest

from compute.validation.ic_decay import (
    build_decay_report,
    pillar_entries_to_monthly_panel,
    walk_ic_history,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeEntry:
    """Minimal stand-in for PillarICEntry (avoids git/network dep)."""
    date: date
    pillar: str
    ic: float
    n_tickers: int


class _FakeHistoricalICReport:
    """Minimal stand-in for HistoricalICReport (avoids git dep)."""
    def __init__(self, entries: list, n_dates_with_ic: int = 0) -> None:
        self.entries = entries
        self.n_dates_with_ic = n_dates_with_ic
        self.n_dates_walked = 0


def _make_stable_entries(pillars: list[str], n_months: int = 24) -> list[_FakeEntry]:
    """Build n_months of stable IC=0.04 entries for each pillar."""
    entries = []
    for month in range(n_months):
        yr = 2022 + month // 12
        mo = (month % 12) + 1
        for p in pillars:
            entries.append(_FakeEntry(date=date(yr, mo, 15), pillar=p, ic=0.04, n_tickers=400))
    return entries


# ---------------------------------------------------------------------------
# C12 — walk_ic_history C5 graceful degradation
# ---------------------------------------------------------------------------

def test_C12_walk_ic_history_returns_empty_when_internal_raises():
    """walk_ic_history never raises when compute_historical_ic_report fails.

    C5 binding condition: any git/data failure → entries=[], panels={},
    n_dates_with_ic=0. The cron is never blocked.
    """
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        side_effect=RuntimeError("simulated git failure"),
    ):
        result = walk_ic_history()

    assert result.entries == [], (
        "walk_ic_history must return [] entries on git failure"
    )
    assert result.panels == {}, (
        "walk_ic_history must return {} panels on git failure"
    )
    assert result.n_dates_with_ic == 0, (
        "walk_ic_history must return 0 n_dates on git failure"
    )


def test_C12_walk_ic_history_returns_empty_when_historical_ic_import_fails():
    """walk_ic_history degrades cleanly when compute_historical_ic_report raises
    an ImportError or any other exception — not just RuntimeError.
    """
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        side_effect=ImportError("hypothetical missing dep"),
    ):
        result = walk_ic_history()

    assert result.entries == []
    assert result.panels == {}
    assert result.n_dates_with_ic == 0


def test_C12_walk_ic_history_does_not_raise():
    """walk_ic_history is unconditionally non-raising per the C5 contract."""
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        side_effect=Exception("any exception"),
    ):
        try:
            _ = walk_ic_history()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"walk_ic_history raised unexpectedly: {exc}")


def test_C12_walk_ic_history_returns_correct_data_on_success():
    """walk_ic_history returns the panels/entries/n_dates from a successful walk."""
    from compute.validation.historical_ic import DEFAULT_PILLARS
    entries = _make_stable_entries(list(DEFAULT_PILLARS[:2]), n_months=3)

    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=_FakeHistoricalICReport(entries=entries, n_dates_with_ic=3),
    ):
        result = walk_ic_history()

    assert result.n_dates_with_ic == 3
    assert len(result.entries) == len(entries)
    # panels should be non-empty (resampled from entries)
    assert len(result.panels) > 0


# ---------------------------------------------------------------------------
# C13 — build_decay_report injection-equivalence + backward-compat
# ---------------------------------------------------------------------------

def test_C13_injected_panels_path_agrees_with_self_walk_path():
    """build_decay_report(panels=P, entries=E, n_dates_with_ic=N) returns the
    SAME reports as build_decay_report() when the self-walk would produce
    the same panel P.

    Both the self-walk path and the injected-panels path should converge on
    identical ICDecayReport values for the same underlying monthly IC data.
    """
    from compute.validation.historical_ic import DEFAULT_PILLARS
    entries = _make_stable_entries(list(DEFAULT_PILLARS), n_months=24)
    fake_report = _FakeHistoricalICReport(entries=entries, n_dates_with_ic=24)

    # Build the panels the same way both paths would
    panels = pillar_entries_to_monthly_panel(entries)
    n_dates = 24

    # Self-walk path (mocked to return same data)
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=fake_report,
    ):
        self_reports, self_status, self_n = build_decay_report()

    # Injected-panels path (no git-walk at all)
    inj_reports, inj_status, inj_n = build_decay_report(
        panels=panels,
        entries=entries,
        n_dates_with_ic=n_dates,
    )

    # Both paths should agree on status and n_dates
    assert inj_status == self_status, (
        f"Status mismatch: injected={inj_status}, self-walk={self_status}"
    )
    assert inj_n == self_n, (
        f"n_dates mismatch: injected={inj_n}, self-walk={self_n}"
    )

    # Both paths should agree on per-pillar preliminary / alert flags
    inj_by_pillar = {r.pillar: r for r in inj_reports}
    self_by_pillar = {r.pillar: r for r in self_reports}

    for pillar in DEFAULT_PILLARS:
        inj_r = inj_by_pillar.get(pillar)
        self_r = self_by_pillar.get(pillar)
        assert inj_r is not None and self_r is not None, (
            f"Pillar {pillar} missing from one of the result sets"
        )
        assert inj_r.preliminary == self_r.preliminary, (
            f"Pillar {pillar}: preliminary mismatch — "
            f"injected={inj_r.preliminary}, self-walk={self_r.preliminary}"
        )
        assert inj_r.alert == self_r.alert, (
            f"Pillar {pillar}: alert mismatch — "
            f"injected={inj_r.alert}, self-walk={self_r.alert}"
        )


def test_C13_backward_compat_no_args_still_self_walks():
    """build_decay_report() with no injected panels still performs a self-walk.

    This is the critical backward-compat test: existing callers that pass
    no panels= argument must behave exactly as before Proposal A #605.
    We verify the self-walk is triggered (mock is called).
    """
    fake_report = _FakeHistoricalICReport(entries=[], n_dates_with_ic=0)

    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=fake_report,
    ) as mock_walk:
        reports, status, n_dates = build_decay_report()

    # The self-walk must have been called (backward-compat)
    mock_walk.assert_called_once()
    # Degraded result: no IC → insufficient_history
    assert status == "insufficient_history"
    assert n_dates == 0
    # Still returns all 10 canonical pillars
    assert len(reports) == 10
    assert all(r.preliminary for r in reports)


def test_C13_injected_empty_panels_returns_all_preliminary():
    """Injecting empty panels (as from a degraded walk_ic_history) yields
    all-preliminary, all-no-alert — same as the pre-#605 degraded path.
    """
    reports, status, n_dates = build_decay_report(
        panels={},
        entries=[],
        n_dates_with_ic=0,
    )
    assert status == "insufficient_history"
    assert n_dates == 0
    assert all(r.preliminary for r in reports)
    assert all(not r.alert for r in reports)


def test_C13_injected_path_skips_git_walk():
    """When panels= is supplied, compute_historical_ic_report is NEVER called.

    This is the efficiency guarantee: the injected path avoids the second
    git-walk that existed pre-#605.
    """
    from compute.validation.historical_ic import DEFAULT_PILLARS
    entries = _make_stable_entries(list(DEFAULT_PILLARS[:2]), n_months=3)
    panels = pillar_entries_to_monthly_panel(entries)

    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
    ) as mock_walk:
        build_decay_report(panels=panels, entries=entries, n_dates_with_ic=3)

    mock_walk.assert_not_called(), (
        "With panels= injected, compute_historical_ic_report must NOT be called "
        "(no duplicate git-walk)."
    )
