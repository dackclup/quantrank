"""Latest 10-K filing text fetch with on-disk JSON cache (Phase 3d Step 5).

Adds the 10-K text-retrieval surface that Defense #8
(:func:`compute.scoring.going_concern.scan_going_concern`) consumes.
The XBRL-only ingest in :mod:`compute.ingest.fundamentals` doesn't carry
narrative text — going-concern detection needs the prose body of MD&A
(Item 7) where the LM-dictionary phrases live.

Cache strategy
--------------

JSON-on-disk at ``compute/cache/edgar_10k_text/<ticker>.json`` with a
90-day TTL. Cache shape::

    {
      "fetched_at": "2026-05-10T03:49:51Z",
      "filing_date": "2025-11-01",
      "filing_url": "https://www.sec.gov/Archives/...",
      "text": "<narrative body>"
    }

Why 90 days: 10-K filings are annual. A given ticker's "most recent 10-K"
only changes once per fiscal year, so an 89-day stale cache hit returns
the same filing we'd fetch fresh.

Failure semantics
-----------------

Returns ``None`` on:
- Missing ``EDGAR_USER_AGENT`` env var
- EDGAR rate-limit / network error / ticker-not-found
- No 10-K filed in the trailing
  ``config.GOING_CONCERN_FILING_LOOKBACK_DAYS`` window

The going-concern caller then treats a None as "no signal" (same as
"phrase not present"). Population-level coverage shows up in
``Metadata.tier2_coverage_pct``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from compute import config

logger = logging.getLogger(__name__)

_IDENTITY_SET = False


def _ensure_edgar_identity() -> bool:
    """Initialize the EDGAR User-Agent if not already done.

    Same lazy non-fatal pattern as
    :func:`compute.scoring.eight_k_events._ensure_edgar_identity` —
    Tier-2 features are non-blocking, unlike fundamentals.
    """
    global _IDENTITY_SET
    if _IDENTITY_SET:
        return True
    ua = os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        logger.warning(
            "EDGAR_USER_AGENT not set — Tier-2 10-K text fetch will skip all "
            "tickers. Set the env var to enable Defense #8."
        )
        return False
    try:
        from edgar import set_identity
        set_identity(ua)
    except Exception as e:  # noqa: BLE001
        logger.warning("set_identity failed: %s", e)
        return False
    _IDENTITY_SET = True
    return True


def _cache_path(ticker: str) -> Path:
    config.EDGAR_10K_TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ticker = re.sub(r"[^A-Za-z0-9_-]", "_", ticker)
    return config.EDGAR_10K_TEXT_CACHE_DIR / f"{safe_ticker}.json"


def _cache_read(ticker: str) -> dict | None:
    """Return cached payload or None on miss / expired / corrupt."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("10-K cache read failed for %s (%s)", ticker, e)
        return None
    fetched_at_str = payload.get("fetched_at")
    if not fetched_at_str:
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if datetime.now(UTC) - fetched_at > timedelta(
        seconds=config.EDGAR_10K_TEXT_CACHE_TTL_SECONDS
    ):
        return None
    if not isinstance(payload.get("text"), str):
        return None
    return payload


def _cache_write(ticker: str, *, filing_date: str, filing_url: str, text: str) -> None:
    path = _cache_path(ticker)
    payload = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filing_date": filing_date,
        "filing_url": filing_url,
        "text": text,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("10-K cache write failed for %s (%s)", ticker, e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def invalidate_cache(ticker: str) -> None:
    """Remove the on-disk cache entry for a ticker. Idempotent."""
    path = _cache_path(ticker)
    if path.exists():
        path.unlink()


def fetch_latest_10k_text(ticker: str) -> str | None:
    """Fetch the narrative text of the most recent 10-K (or None on failure).

    Uses ``filing.html()`` + BeautifulSoup raw text extraction (NOT
    ``filing.text()``) to skip edgartools' section-detection parser,
    which adds ~5-10s per filing for section structure we don't need.
    The going-concern phrase scan operates on raw text via
    ``\\b``-anchored regex with ``[\\s\\-]+`` whitespace flex, so the
    flat output of ``BeautifulSoup.get_text(separator=" ")`` matches
    correctness-equivalently to ``rich_to_text``-formatted text. The
    section detector's ~19,000-call CPU cost on a 502-stock universe
    blew past the 45-min workflow timeout in the first
    ``workflow_dispatch`` run; this path keeps cold-cache time around
    25-30 min instead.

    Parameters
    ----------
    ticker:
        Stock ticker symbol (case-insensitive — passed through to
        edgartools' ``Company`` constructor which handles case).

    Returns
    -------
    str | None
        Concatenated 10-K body text on success. ``None`` on:

        - Missing ``EDGAR_USER_AGENT`` env var
        - EDGAR network error / rate-limit / ticker-not-found
        - No 10-K filed within
          ``config.GOING_CONCERN_FILING_LOOKBACK_DAYS`` (default 400d)
        - 10-K HTML payload empty / unparseable

    Cache: 90-day TTL. See module docstring.
    """
    cached = _cache_read(ticker)
    if cached is not None:
        return cached["text"]

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
        start = end - timedelta(days=config.GOING_CONCERN_FILING_LOOKBACK_DAYS)
        filings = company.get_filings(
            form="10-K",
            filing_date=(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("10-K fetch failed for %s: %s", ticker, e)
        return None

    # Pick the most recent filing in the window. edgartools' iterables
    # often yield in newest-first order, but we don't rely on that.
    most_recent = None
    most_recent_date: date | None = None
    try:
        for filing in filings:
            fd = getattr(filing, "filing_date", None)
            if isinstance(fd, datetime):
                fd_date = fd.date()
            elif isinstance(fd, date):
                fd_date = fd
            else:
                try:
                    fd_date = date.fromisoformat(str(fd)[:10])
                except ValueError:
                    continue
            if most_recent_date is None or fd_date > most_recent_date:
                most_recent = filing
                most_recent_date = fd_date
    except Exception as e:  # noqa: BLE001
        logger.warning("10-K iteration failed for %s: %s", ticker, e)

    if most_recent is None or most_recent_date is None:
        return None

    # Pull the raw HTML and strip tags ourselves. We deliberately skip
    # ``filing.text()`` because that path runs ``HTMLParser(ParserConfig)``
    # → ``rich_to_text`` → ``hybrid_section_detector`` for every paragraph
    # (~5-10s per filing × 502 tickers blew the 45-min workflow timeout
    # on the first cold-cache run). Going-concern detection only needs
    # the prose body, not section structure, so BS get_text gives
    # correctness-equivalent input to ``scan_going_concern``.
    text: str | None = None
    try:
        html_attr = getattr(most_recent, "html", None)
        html_content = html_attr() if callable(html_attr) else html_attr
        if not html_content:
            logger.warning(
                "10-K HTML fetch returned empty for %s (filing_date %s)",
                ticker,
                most_recent_date,
            )
            return None
        text = BeautifulSoup(str(html_content), "lxml").get_text(separator=" ")
    except Exception as e:  # noqa: BLE001
        logger.warning("10-K text extract failed for %s: %s", ticker, e)
        text = None

    if not text:
        return None

    filing_url = (
        getattr(most_recent, "url", None)
        or getattr(most_recent, "filing_url", None)
        or ""
    )
    _cache_write(
        ticker,
        filing_date=most_recent_date.strftime("%Y-%m-%d"),
        filing_url=str(filing_url),
        text=text,
    )
    return text


__all__ = [
    "fetch_latest_10k_text",
    "invalidate_cache",
]
