"""Historical S&P 500 membership for survivorship-bias-free validation.

Phase 4.6 — Research Report v1.0 §7.4 closer. Without this module, every
backtest / IC / PBO / DSR computation that uses pre-today dates is
silently survivorship-biased: stocks that delisted or got dropped from
the index are excluded from the historical view of the universe.

The weekly cron's FORWARD compute is unaffected — current S&P 500
membership is correct for forward-looking ranking.

References (per Research Report v1.0):
- Hou, Xue, Zhang (2020). "Replicating Anomalies." Review of Financial
  Studies 33(5):2019-2133. Replication crisis evidence emphasizing
  survivorship as PRIMARY failure mode in factor-zoo work.
- McLean, Pontiff (2016). "Does Academic Research Destroy Stock Return
  Predictability?" Journal of Finance 71(1):5-32. 32% post-publication
  decay; survivorship correction is the first-order honest-estimate
  adjustment.

Data source (`data/sp500_membership_historical.csv`):
- Wikipedia "List of S&P 500 companies" change-history table
- S&P Dow Jones Indices press releases
- Factual lists (uncopyrightable per Feist 1991); CSV compilation is
  original work under project MIT license; per-row citation included.

Scope (Phase 4.6 v1): events 2020-01-01 → present. ~50 well-known
ADD/REMOVE events. NOT a complete historical index. Pre-2020 lookups
return ``is_complete = False`` with the closest-available anchor.

API:
    >>> from datetime import date
    >>> from compute.ingest.historical_universe import members_at
    >>> result = members_at(date(2020, 12, 21), current_universe={"AAPL", "TSLA", ...})
    >>> result.tickers
    {"AAPL", "MSFT", ...}  # universe as it existed on 2020-12-21
    >>> result.is_complete
    True
    >>> result.anchor_date
    datetime.date(2026, 5, 27)
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_CSV: Path = PROJECT_ROOT / "data" / "sp500_membership_historical.csv"

# Coverage boundary: events older than this are NOT in the CSV. Extended back to
# 2016-01 (Track B 10Y rebuild — full ledger re-derived from the fja05680
# historical-components snapshot-diff, 2016-01-04 .. 2026-06-02). Lookups before
# this date return is_complete=False with a warning logged.
EARLIEST_EVENT_DATE: date = date(2016, 1, 1)

# Action codes in the CSV. RENAME events are non-membership-changing
# (ticker rename only) — handled by the alias map, not the add/remove walk.
_ACTION_ADD = "ADD"
_ACTION_REMOVE = "REMOVE"
_ACTION_RENAME = "RENAME"
_VALID_ACTIONS = frozenset({_ACTION_ADD, _ACTION_REMOVE, _ACTION_RENAME})


class MissingMembershipError(RuntimeError):
    """Raised when the historical CSV cannot answer for a given date."""


@dataclass(frozen=True)
class MembershipEvent:
    effective_date: date
    ticker: str
    action: str
    name: str
    source_url: str
    notes: str = ""


@dataclass(frozen=True)
class MembershipResult:
    """Return shape for ``members_at(as_of_date)``.

    Attributes:
        tickers: the set of S&P 500 constituents on ``as_of_date``.
        as_of_date: echoed input date for downstream Metadata wiring.
        anchor_date: the date the current-universe snapshot was taken
            (today) — events between ``as_of_date`` and ``anchor_date``
            were reversed to compute ``tickers``.
        is_complete: True when ``as_of_date >= EARLIEST_EVENT_DATE``
            AND the CSV walk covered every reversal cleanly. False
            when the lookup degraded to a partial / anchor-only result.
        events_applied: number of reverse events applied — useful for
            verify-helper acceptance checks.
    """

    tickers: frozenset[str]
    as_of_date: date
    anchor_date: date
    is_complete: bool
    events_applied: int = 0
    note: str = ""


def _parse_event_row(row: dict[str, str]) -> MembershipEvent | None:
    """Parse a CSV row to a MembershipEvent; return None for blank/comment rows."""
    eff = row.get("effective_date", "").strip()
    if not eff or eff.startswith("#"):
        return None
    ticker = row.get("ticker", "").strip().upper()
    action = row.get("action", "").strip().upper()
    if not ticker or action not in _VALID_ACTIONS:
        return None
    try:
        eff_date = datetime.strptime(eff, "%Y-%m-%d").date()
    except ValueError:
        logger.warning("Skipping CSV row with malformed date: %r", eff)
        return None
    return MembershipEvent(
        effective_date=eff_date,
        ticker=ticker,
        action=action,
        name=row.get("name", "").strip(),
        source_url=row.get("source_url", "").strip(),
        notes=row.get("notes", "").strip(),
    )


@lru_cache(maxsize=1)
def _load_events(csv_path_str: str | None = None) -> tuple[MembershipEvent, ...]:
    """Load + parse the historical membership CSV. Cached after first call."""
    csv_path = Path(csv_path_str) if csv_path_str else HISTORICAL_CSV
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Historical membership CSV missing at {csv_path}. "
            "Run Phase 4.6 PR to populate."
        )
    events: list[MembershipEvent] = []
    with csv_path.open() as f:
        # Skip comment lines (#) before passing to DictReader. We re-parse
        # the header line manually because csv.DictReader doesn't honor
        # comment-prefix skipping natively.
        lines = [line for line in f if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return ()
    reader = csv.DictReader(lines)
    for row in reader:
        ev = _parse_event_row(row)
        if ev is not None:
            events.append(ev)
    events.sort(key=lambda e: e.effective_date)
    logger.info("Loaded %d historical S&P 500 membership events from %s", len(events), csv_path)
    return tuple(events)


def members_at(
    as_of_date: date,
    current_universe: set[str] | frozenset[str],
    anchor_date: date | None = None,
) -> MembershipResult:
    """Return the S&P 500 membership snapshot for ``as_of_date``.

    Reverses ADD/REMOVE events with ``effective_date > as_of_date``:
    - Forward ADD on date D > as_of_date → REVERSE: ticker was NOT in
      the universe at as_of_date → REMOVE from the working set.
    - Forward REMOVE on date D > as_of_date → REVERSE: ticker WAS in
      the universe at as_of_date → ADD to the working set.

    RENAME events do not change membership; the alias map is used only
    for downstream ticker-resolution (out of scope for membership query).

    Args:
        as_of_date: the historical date to query. Must be in the past
            or equal to today; future dates raise ValueError.
        current_universe: set of tickers currently in the S&P 500 — the
            anchor. Typically ``set(get_sp500_constituents().ticker)``.
        anchor_date: the date the current_universe snapshot was taken.
            Defaults to today (UTC date).

    Returns:
        MembershipResult with the historical universe, is_complete flag,
        and event-count diagnostic.

    Raises:
        ValueError: if ``as_of_date`` is in the future.
        MissingMembershipError: never raised directly here; the result
            is degraded with ``is_complete = False`` instead. The
            exception is a public API surface for future tightening.
    """
    if anchor_date is None:
        anchor_date = datetime.utcnow().date()
    if as_of_date > anchor_date:
        raise ValueError(
            f"as_of_date {as_of_date} is in the future relative to anchor "
            f"{anchor_date}. Use current_universe directly for forward dates."
        )

    # Same-day or future = no reversal needed
    if as_of_date == anchor_date:
        return MembershipResult(
            tickers=frozenset(current_universe),
            as_of_date=as_of_date,
            anchor_date=anchor_date,
            is_complete=True,
            events_applied=0,
            note="anchor-date snapshot",
        )

    # Pre-coverage = degraded
    if as_of_date < EARLIEST_EVENT_DATE:
        logger.warning(
            "members_at(%s) before EARLIEST_EVENT_DATE=%s — returning anchor "
            "snapshot with is_complete=False. Coverage extension is tracked "
            "as a follow-up PR.",
            as_of_date,
            EARLIEST_EVENT_DATE,
        )
        return MembershipResult(
            tickers=frozenset(current_universe),
            as_of_date=as_of_date,
            anchor_date=anchor_date,
            is_complete=False,
            events_applied=0,
            note=f"date < EARLIEST_EVENT_DATE={EARLIEST_EVENT_DATE.isoformat()}",
        )

    working: set[str] = set(current_universe)
    events = _load_events()
    applied = 0

    # Walk events from MOST RECENT to OLDEST, reversing those that
    # post-date ``as_of_date``. Stop when we cross ``as_of_date`` — any
    # event with eff_date <= as_of_date is already reflected in the
    # current universe state.
    for ev in reversed(events):
        if ev.effective_date <= as_of_date:
            break
        if ev.action == _ACTION_ADD:
            # Forward ADD post-as_of → ticker was NOT in universe at as_of
            working.discard(ev.ticker)
            applied += 1
        elif ev.action == _ACTION_REMOVE:
            # Forward REMOVE post-as_of → ticker WAS in universe at as_of
            working.add(ev.ticker)
            applied += 1
        # RENAME: no-op for membership; alias-map use is downstream

    return MembershipResult(
        tickers=frozenset(working),
        as_of_date=as_of_date,
        anchor_date=anchor_date,
        is_complete=True,
        events_applied=applied,
        note=f"reversed {applied} post-as_of events",
    )


def list_known_events(
    since: date | None = None,
    until: date | None = None,
) -> tuple[MembershipEvent, ...]:
    """Return events from the CSV optionally filtered by date range.

    Pure read accessor — used by tests + verify-helper. Returns the
    cached event tuple; safe to call repeatedly.
    """
    events = _load_events()
    if since is None and until is None:
        return events
    out = []
    for ev in events:
        if since is not None and ev.effective_date < since:
            continue
        if until is not None and ev.effective_date > until:
            continue
        out.append(ev)
    return tuple(out)
