"""Disclosure-driven manipulation defenses — Phase 4.5b.

Two annotate-only flags surfaced from the SEC EDGAR filing list:

- **`restatement_history`** — count of 10-K/A or 10-Q/A (amendment)
  filings per CIK in the trailing 5 years. Recurrence is a strong
  predictor of future misstatement (Hennes-Leone-Miller 2008 *TAR*:
  restating firms see −9% abnormal return on announcement; recurrent
  restaters compound the effect). Lookback window:
  ``config.RESTATEMENT_HISTORY_LOOKBACK_DAYS = 1825`` (5 × 365 + 1
  leap-day buffer).
- **`late_filing_notification`** — SEC Form 12b-25 (NT 10-K / NT 10-Q)
  within the trailing 365 days. Bartov-Lai-Yeung 2002 *JAR*: late
  filers see −5-7% abnormal returns. Lookback window:
  ``config.LATE_FILING_LOOKBACK_DAYS = 365``.

Both flags are **ANNOTATE-only** — they land in
``StockDetail.valuation_warnings`` (not the active veto layer). The
disclosure-driven signal is sector-agnostic and well-attested in the
accounting-research literature, but base rates are too low to justify
an active veto without sector adjustment.

Cache strategy
--------------

Per-ticker JSON cache with 7-day TTL under
``compute/cache/edgar_amendments/<ticker>.json`` and
``compute/cache/edgar_late_filings/<ticker>.json`` respectively.
Cache shape mirrors :mod:`compute.scoring.eight_k_events`::

    {
      "fetched_at": "2026-05-16T17:00:00Z",
      "lookback_days": 1825,
      "filings": [
        {
          "accession": "0001234567-25-000123",
          "form": "10-K/A",
          "filing_date": "2024-03-15",
          "filing_url": "https://www.sec.gov/..."
        },
        ...
      ]
    }

References
----------

- Hennes, Leone, Miller (2008). "The importance of distinguishing
  errors from irregularities in restatement research."
  *The Accounting Review* 83(6), 1487-1519.
- Bartov, Lai, Yeung (2002). "Late filing notifications, NT 10-K and
  NT 10-Q, and earnings management." *Journal of Accounting Research*
  40(2), 477-516.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final

from compute import config

logger = logging.getLogger(__name__)


CACHE_TTL_DAYS: Final[int] = 7
_AMENDMENT_FORMS: Final[tuple[str, ...]] = ("10-K/A", "10-Q/A")
_LATE_FILING_FORMS: Final[tuple[str, ...]] = ("NT 10-K", "NT 10-Q")


@dataclass(frozen=True)
class RestatementHistoryResult:
    """`restatement_history` flag output.

    ``fired = True`` when at least one 10-K/A or 10-Q/A landed in the
    lookback window. Recurrent restaters (count >= 2) get the same flag
    treatment but `count` is exposed for UI use.
    """

    fired: bool
    count: int
    latest_filing_date: str | None
    latest_filing_url: str | None


@dataclass(frozen=True)
class LateFilingResult:
    """`late_filing_notification` flag output."""

    fired: bool
    count: int
    latest_filing_date: str | None
    latest_filing_url: str | None
    latest_form: str | None


# ---------------------------------------------------------------------------
# Cache layer (mirrors compute.scoring.eight_k_events)
# ---------------------------------------------------------------------------


def _ensure_edgar_identity() -> bool:
    """Set the EDGAR user agent from the env var. Same precondition as
    the 8-K + 10-K text scanners."""
    user_agent = os.environ.get("EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        logger.warning(
            "EDGAR_USER_AGENT is not set; skipping restatement / late-filing scan."
        )
        return False
    try:
        from edgar import set_identity

        set_identity(user_agent)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to set edgar identity: %s", e)
        return False
    return True


def _cache_path(cache_subdir: str, ticker: str) -> Path:
    return config.CACHE_DIR / cache_subdir / f"{ticker}.json"


def _cache_read(
    cache_subdir: str,
    ticker: str,
    lookback_days: int,
) -> list[dict] | None:
    p = _cache_path(cache_subdir, ticker)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("%s cache read failed for %s: %s", cache_subdir, ticker, e)
        return None
    fetched_at_raw = payload.get("fetched_at")
    cached_lookback = payload.get("lookback_days")
    if not isinstance(fetched_at_raw, str) or not isinstance(cached_lookback, int):
        return None
    if cached_lookback < lookback_days:
        # Stale window — caller wants more history than the cache stored.
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if datetime.now(UTC) - fetched_at > timedelta(days=CACHE_TTL_DAYS):
        return None
    filings = payload.get("filings")
    if not isinstance(filings, list):
        return None
    return filings


def _cache_write(
    cache_subdir: str,
    ticker: str,
    lookback_days: int,
    filings: list[dict],
) -> None:
    p = _cache_path(cache_subdir, ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": int(lookback_days),
        "filings": filings,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def invalidate_cache(ticker: str) -> None:
    """Drop both cache entries for a ticker — used in tests."""
    for sub in ("edgar_amendments", "edgar_late_filings"):
        p = _cache_path(sub, ticker)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------


def _filing_to_dict(filing: object) -> dict | None:
    """Normalize an edgartools `Filing` into a minimal dict.

    We only need the form, filing date, and URL — no body parse (unlike
    8-K Item-detection). Returns None on missing required fields.
    """
    try:
        accession = getattr(filing, "accession_no", None) or getattr(filing, "accession_number", None)
        form = getattr(filing, "form", None)
        filing_date = getattr(filing, "filing_date", None)
        filing_url = getattr(filing, "filing_url", None) or getattr(filing, "homepage_url", None) or ""
        if accession is None or form is None or filing_date is None:
            return None
        if hasattr(filing_date, "isoformat"):
            filing_date_str = filing_date.isoformat()
        else:
            filing_date_str = str(filing_date)
        return {
            "accession": str(accession),
            "form": str(form),
            "filing_date": filing_date_str,
            "filing_url": str(filing_url),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("filing_to_dict failed: %s", e)
        return None


def _fetch_filings(
    ticker: str,
    forms: tuple[str, ...],
    lookback_days: int,
    cache_subdir: str,
) -> list[dict] | None:
    """Shared fetcher — 10-K/A or NT 10-K depending on `forms` arg.

    Returns
    -------
    list[dict] | None
        Normalized filing dicts. ``None`` on EDGAR rate-limit, network
        failure, missing identity, or ticker-not-found. Empty list ``[]``
        means EDGAR returned successfully but the ticker has zero matching
        filings in the lookback window.
    """
    cached = _cache_read(cache_subdir, ticker, lookback_days)
    if cached is not None:
        return cached

    if not _ensure_edgar_identity():
        return None

    try:
        from edgar import Company
    except ImportError as e:
        logger.warning("edgartools not importable: %s", e)
        return None

    try:
        company = Company(ticker)
        end = date.today()
        start = end - timedelta(days=lookback_days)
        # edgartools accepts a list of forms via repeat-fetch; we merge
        # results client-side to keep the cache shape simple.
        merged: list[dict] = []
        for form in forms:
            try:
                filings = company.get_filings(
                    form=form,
                    filing_date=(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "form %s fetch failed for %s: %s", form, ticker, e
                )
                continue
            try:
                for filing in filings:
                    entry = _filing_to_dict(filing)
                    if entry is not None:
                        merged.append(entry)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "form %s iteration failed for %s after %d entries: %s",
                    form,
                    ticker,
                    len(merged),
                    e,
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("filings fetch top-level failed for %s: %s", ticker, e)
        return None

    # Sort by filing_date desc so "latest" is always merged[0]
    merged.sort(key=lambda d: d.get("filing_date") or "", reverse=True)
    _cache_write(cache_subdir, ticker, lookback_days, merged)
    return merged


def fetch_amendments(
    ticker: str,
    lookback_days: int | None = None,
) -> list[dict] | None:
    """Fetch 10-K/A + 10-Q/A filings via edgartools, JSON-cached for 7 days.

    Lookback defaults to :data:`config.RESTATEMENT_HISTORY_LOOKBACK_DAYS`.
    """
    if lookback_days is None:
        lookback_days = config.RESTATEMENT_HISTORY_LOOKBACK_DAYS
    return _fetch_filings(
        ticker=ticker,
        forms=_AMENDMENT_FORMS,
        lookback_days=lookback_days,
        cache_subdir="edgar_amendments",
    )


def fetch_late_filings(
    ticker: str,
    lookback_days: int | None = None,
) -> list[dict] | None:
    """Fetch NT 10-K + NT 10-Q (Form 12b-25) filings, JSON-cached 7d.

    Lookback defaults to :data:`config.LATE_FILING_LOOKBACK_DAYS`.
    """
    if lookback_days is None:
        lookback_days = config.LATE_FILING_LOOKBACK_DAYS
    return _fetch_filings(
        ticker=ticker,
        forms=_LATE_FILING_FORMS,
        lookback_days=lookback_days,
        cache_subdir="edgar_late_filings",
    )


# ---------------------------------------------------------------------------
# Flag checks
# ---------------------------------------------------------------------------


def _filing_date_within(
    filing_date_str: str,
    asof: date,
    lookback_days: int,
) -> bool:
    """True iff ``filing_date_str`` is within the trailing ``lookback_days``
    of ``asof`` (inclusive on both ends)."""
    try:
        fd = date.fromisoformat(filing_date_str)
    except ValueError:
        return False
    return (asof - fd).days <= lookback_days and fd <= asof


def check_restatement_history(
    ticker: str,
    *,
    asof: date | None = None,
    lookback_days: int | None = None,
    filings_override: list[dict] | None = None,
) -> RestatementHistoryResult:
    """Count 10-K/A + 10-Q/A filings for ``ticker`` in the lookback window.

    ``filings_override`` is the inject path for tests (bypasses the EDGAR
    fetch). Returns ``RestatementHistoryResult(fired=False, count=0, ...)``
    on EDGAR failure or zero filings.
    """
    if asof is None:
        asof = date.today()
    if lookback_days is None:
        lookback_days = config.RESTATEMENT_HISTORY_LOOKBACK_DAYS

    filings = (
        filings_override
        if filings_override is not None
        else fetch_amendments(ticker, lookback_days=lookback_days)
    )
    if filings is None:
        return RestatementHistoryResult(
            fired=False, count=0, latest_filing_date=None, latest_filing_url=None
        )

    matching = [
        f
        for f in filings
        if _filing_date_within(
            f.get("filing_date", ""), asof, lookback_days
        )
    ]
    if not matching:
        return RestatementHistoryResult(
            fired=False, count=0, latest_filing_date=None, latest_filing_url=None
        )

    # Filings are sorted desc by filing_date in the cache writer, so [0] is latest.
    latest = matching[0]
    return RestatementHistoryResult(
        fired=True,
        count=len(matching),
        latest_filing_date=latest.get("filing_date"),
        latest_filing_url=latest.get("filing_url"),
    )


def check_late_filing(
    ticker: str,
    *,
    asof: date | None = None,
    lookback_days: int | None = None,
    filings_override: list[dict] | None = None,
) -> LateFilingResult:
    """Detect NT 10-K / NT 10-Q (Form 12b-25) filings in the lookback window."""
    if asof is None:
        asof = date.today()
    if lookback_days is None:
        lookback_days = config.LATE_FILING_LOOKBACK_DAYS

    filings = (
        filings_override
        if filings_override is not None
        else fetch_late_filings(ticker, lookback_days=lookback_days)
    )
    if filings is None:
        return LateFilingResult(
            fired=False,
            count=0,
            latest_filing_date=None,
            latest_filing_url=None,
            latest_form=None,
        )

    matching = [
        f
        for f in filings
        if _filing_date_within(
            f.get("filing_date", ""), asof, lookback_days
        )
    ]
    if not matching:
        return LateFilingResult(
            fired=False,
            count=0,
            latest_filing_date=None,
            latest_filing_url=None,
            latest_form=None,
        )

    latest = matching[0]
    return LateFilingResult(
        fired=True,
        count=len(matching),
        latest_filing_date=latest.get("filing_date"),
        latest_filing_url=latest.get("filing_url"),
        latest_form=latest.get("form"),
    )
