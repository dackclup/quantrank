"""Universe drift diagnostics — Phase 4.6 honest re-validation scaffolding.

Phase 4.6 task #2 first unit. Closes the gap between PR #276 (writer
wiring populates ``Metadata.universe_membership_as_of`` going forward)
and the eventual full historical re-validation of pillars +
``manipulation_index`` per Research Report v1.0 §7.4.

This module answers the foundational question every honest re-validation
must answer FIRST: **what's the universe drift between today and any
historical as-of date?** Without this answer, IC / PBO / DSR re-runs are
just numbers — you can't tell if the delta vs the published baseline is
from (a) survivorship bias correction, (b) scoring drift, or (c) real
factor decay.

The module is pure-functional: takes a date and a current-universe set,
returns a ``UniverseDriftReport``. No I/O beyond reading the historical
CSV (handled by ``compute.ingest.historical_universe``).

Future PRs (out of this scope) will layer on:
- IC time-series per pillar at historical as-of dates
- PBO / DSR re-runs using the universe_provider kwarg landed in PR #275
- Honest baseline comparison vs published Phase 4.5f numbers

API:
    >>> from datetime import date
    >>> from compute.validation.universe_drift import compute_universe_drift
    >>> current = frozenset({"AAPL", "MSFT", "TSLA", "SMCI"})
    >>> report = compute_universe_drift(date(2023, 1, 1), current)
    >>> report.added_since   # tickers added between 2023-01-01 and today
    frozenset({"SMCI"})
    >>> report.removed_since  # tickers removed between 2023-01-01 and today
    frozenset()  # (depends on CSV coverage)
    >>> report.universe_size_at_as_of
    3
    >>> report.is_complete
    True
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date

from compute.ingest.historical_universe import MembershipResult, members_at

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UniverseDriftReport:
    """Result of ``compute_universe_drift(as_of_date, current_universe)``.

    Attributes:
        as_of_date: the historical date queried.
        anchor_date: the date the current_universe snapshot was taken
            (typically today).
        current_size: ``len(current_universe)`` for downstream sanity.
        universe_size_at_as_of: ``len(historical_universe)`` per the
            CSV reversal walk.
        added_since: tickers in CURRENT that were NOT in historical
            (i.e., ADDED to S&P 500 between as_of_date and today).
        removed_since: tickers in HISTORICAL that are NOT in current
            (i.e., REMOVED from S&P 500 between as_of_date and today —
            the survivorship-bias-corrected cohort that current-only
            views silently exclude).
        unchanged: tickers in BOTH (the always-in cohort over the
            window).
        is_complete: passes through ``MembershipResult.is_complete``
            from the underlying members_at() call.
        events_applied: number of reverse events the underlying walk
            applied.
        note: passes through ``MembershipResult.note``.
    """

    as_of_date: _date
    anchor_date: _date
    current_size: int
    universe_size_at_as_of: int
    added_since: frozenset[str]
    removed_since: frozenset[str]
    unchanged: frozenset[str]
    is_complete: bool
    events_applied: int
    note: str


def compute_universe_drift(
    as_of_date: _date,
    current_universe: set[str] | frozenset[str],
    anchor_date: _date | None = None,
) -> UniverseDriftReport:
    """Return the add/remove drift between today and ``as_of_date``.

    Wraps ``compute.ingest.historical_universe.members_at()`` and
    produces the symmetric-difference partitions that downstream
    honest-re-validation work consumes.

    Args:
        as_of_date: the historical date to query.
        current_universe: today's S&P 500 anchor set.
        anchor_date: defaults to None → members_at uses today UTC.

    Returns:
        UniverseDriftReport with added / removed / unchanged sets +
        size + completeness flag.

    Raises:
        ValueError: if ``as_of_date`` is in the future (propagates
            from members_at).
    """
    membership: MembershipResult = members_at(
        as_of_date=as_of_date,
        current_universe=current_universe,
        anchor_date=anchor_date,
    )

    current_set = frozenset(current_universe)
    historical_set = membership.tickers

    added = current_set - historical_set
    removed = historical_set - current_set
    unchanged = current_set & historical_set

    if not membership.is_complete:
        logger.warning(
            "compute_universe_drift: degraded report for as_of=%s — "
            "is_complete=False, note=%r. Added/removed sets reflect "
            "current-only fallback, NOT honest historical reversal.",
            as_of_date,
            membership.note,
        )

    return UniverseDriftReport(
        as_of_date=as_of_date,
        anchor_date=membership.anchor_date,
        current_size=len(current_set),
        universe_size_at_as_of=len(historical_set),
        added_since=added,
        removed_since=removed,
        unchanged=unchanged,
        is_complete=membership.is_complete,
        events_applied=membership.events_applied,
        note=membership.note,
    )


def format_drift_report(report: UniverseDriftReport, *, max_listed: int = 20) -> str:
    """Render a UniverseDriftReport as a human-readable text block.

    Used by the CLI in ``scripts/historical_pillar_revalidate.py``.
    Caps listed tickers at ``max_listed`` per category to keep output
    scannable in terminal.
    """
    lines = []
    lines.append(f"Universe drift report — as_of={report.as_of_date}")
    lines.append(f"  anchor date         : {report.anchor_date}")
    lines.append(f"  current universe    : {report.current_size} tickers")
    lines.append(f"  historical universe : {report.universe_size_at_as_of} tickers")
    lines.append(f"  events applied      : {report.events_applied}")
    lines.append(f"  is_complete         : {report.is_complete}")
    if report.note:
        lines.append(f"  note                : {report.note}")
    lines.append("")
    lines.append(f"  ADDED since as_of   : {len(report.added_since)} tickers")
    if report.added_since:
        sample = sorted(report.added_since)[:max_listed]
        extra = "" if len(sample) == len(report.added_since) else f" (+{len(report.added_since) - len(sample)} more)"
        lines.append(f"    {', '.join(sample)}{extra}")
    lines.append(f"  REMOVED since as_of : {len(report.removed_since)} tickers")
    if report.removed_since:
        sample = sorted(report.removed_since)[:max_listed]
        extra = "" if len(sample) == len(report.removed_since) else f" (+{len(report.removed_since) - len(sample)} more)"
        lines.append(f"    {', '.join(sample)}{extra}")
        lines.append("    ↑ this is the SURVIVORSHIP-BIAS-CORRECTED cohort —")
        lines.append("      current-universe-only views silently EXCLUDE these")
    lines.append(f"  UNCHANGED           : {len(report.unchanged)} tickers (always-in cohort)")
    return "\n".join(lines)


__all__ = [
    "UniverseDriftReport",
    "compute_universe_drift",
    "format_drift_report",
]
