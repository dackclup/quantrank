"""yfinance stock-split event fetcher with 24h on-disk cache.

Used exclusively by the ``post_split_share_lag`` defense
(``compute/scoring/risk_overlay.py``) to detect recent material splits
where EDGAR ``shares_outstanding`` has not yet caught up with the
post-split share count.

Cache strategy
--------------

Modelled on ``compute/ingest/cross_source.py``'s yfinance_info 24h-TTL
cache.  Split events are date-stamped and stable — once a split fires
it never un-fires — so a 24h TTL is conservative and correct.  The
cache lives at ``compute/cache/yfinance_splits/<TICKER>.json`` (the
directory is gitignored along with the rest of ``compute/cache/``).

Unlike the ``prices.py`` freshness gate (issue #498 last-bar-date
recency), ``.splits`` is event-data rather than a continuous price
series, so file-mtime TTL is the correct freshness mechanism here.
A cache entry older than 24h is re-fetched live; within 24h the
cached payload is returned as-is.  This avoids a new GHA mtime
regression because the cache is in the SLOW-TEXT bundle (run-id key,
always saves) — the mtime is never reset to "now" on a fresh checkout
in the same way the fast (quarter-key) bundle is.

Graceful degradation
--------------------

On any fetch failure (network error, yfinance API change, cache
corruption, or unexpected exception) the function returns ``None``.
Callers treat ``None`` as "no split detected" — the flag silently
doesn't fire rather than blocking the cron.  This is deliberate:
a missed split correction is preferable to a cron abort.

``QR_SKIP_SPLITS`` escape hatch
---------------------------------

Set ``QR_SKIP_SPLITS=1`` to skip live fetches and rely on cache-only
reads (same pattern as ``QR_SKIP_CROSS_SOURCE`` in cross_source.py).
Used by CI pre-merge-prod-sim to avoid adding a new serial yfinance
loop to the sim budget.

Cache payload format
--------------------

``{"splits": [{"date": "2026-06-12", "ratio": 10.0}, ...]}``

Dates are ISO strings (YYYY-MM-DD).  The list is sorted descending by
date (most-recent first).  An empty list means the ticker had no splits
in the yfinance history.

References
----------

- CRSP CFACSHR adjustment factor, CRSP Survivor-Bias-Free US Stock
  Database §4.3.
- Damodaran 2019 *Investment Valuation*, 3rd ed., Ch. 16 (share-count
  adjustments after corporate actions).
- Methodology-scientist ruling 2026-06-18 (frozen pre-registration for
  ``POST_SPLIT_WINDOW_DAYS``, ``POST_SPLIT_MIN_RATIO``,
  ``POST_SPLIT_RATIO_TOLERANCE``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from compute import config

logger = logging.getLogger(__name__)

# Cache TTL reuses the yfinance_info 24h constant — split events are at most
# daily in frequency (corporate-action effective dates), so 24h is safe.
_CACHE_TTL_SECONDS: float = config.YFINANCE_INFO_CACHE_MAX_AGE_HOURS * 3600

_SPLITS_CACHE_DIR: Path = config.CACHE_DIR / "yfinance_splits"


@dataclass(frozen=True)
class SplitEvent:
    """A single stock-split event from yfinance ``.splits``."""

    split_date: date
    """The effective date of the split."""

    ratio: float
    """Split multiplier (e.g. 10.0 for a 10:1 split; always ≥ 1.0 for forward
    splits; values < 1.0 indicate reverse splits and are treated as
    ``ratio < POST_SPLIT_MIN_RATIO`` so the flag never fires on them)."""


def _cache_path(ticker: str) -> Path:
    _SPLITS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ticker = re.sub(r"[^A-Za-z0-9_-]", "_", ticker)
    return _SPLITS_CACHE_DIR / f"{safe_ticker}.json"


def _cache_read(ticker: str) -> list[SplitEvent] | None:
    """Return cached split events, or ``None`` on miss / expired / corrupt."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("splits cache read failed for %s: %s", ticker, exc)
        return None
    raw = payload.get("splits")
    if not isinstance(raw, list):
        return None
    events: list[SplitEvent] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            d = date.fromisoformat(str(entry["date"]))
            r = float(entry["ratio"])
        except (KeyError, ValueError, TypeError):
            continue
        events.append(SplitEvent(split_date=d, ratio=r))
    return events


def _cache_write(ticker: str, events: list[SplitEvent]) -> None:
    """Atomically write split events to the cache file."""
    path = _cache_path(ticker)
    payload = {
        "splits": [
            {"date": e.split_date.isoformat(), "ratio": e.ratio}
            for e in events
        ]
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("splits cache write failed for %s: %s", ticker, exc)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _yf_fetch_splits(ticker: str) -> list[SplitEvent]:
    """Fetch ``.splits`` from yfinance.  Raises on persistent network error."""
    splits_series = yf.Ticker(ticker).splits
    if splits_series is None or splits_series.empty:
        return []
    events: list[SplitEvent] = []
    for ts, ratio in splits_series.items():
        # yfinance returns a pandas Timestamp index; extract date.
        try:
            if hasattr(ts, "date"):
                d = ts.date()
            else:
                d = datetime.fromisoformat(str(ts)).date()
            r = float(ratio)
        except (ValueError, TypeError, AttributeError):
            continue
        events.append(SplitEvent(split_date=d, ratio=r))
    # Sort descending by date so callers can short-circuit on the first
    # recent split without scanning the entire history.
    return sorted(events, key=lambda e: e.split_date, reverse=True)


def fetch_splits(ticker: str) -> list[SplitEvent] | None:
    """Return a list of historical stock-split events for ``ticker``.

    Hits the 24h disk cache first.  On a cache miss (or stale entry),
    fetches from yfinance with tenacity retry.  Returns ``None`` on
    persistent failure — callers treat ``None`` as "no split detected"
    (graceful-degradation contract: the post-split defense never fires
    when data is unavailable, preferring a missed correction to a
    cron abort).

    When ``QR_SKIP_SPLITS=1`` is set:
    - A stale-but-present cache entry is returned as-is (tolerates the
      GHA mtime reset).
    - A genuinely cold cache → ``None`` returned; no live fetch.

    The returned list is sorted descending by ``split_date`` (most-recent
    first).  An empty list means no splits found (not the same as ``None``
    — empty list = successful fetch that found no events; ``None`` =
    fetch error).
    """
    if os.environ.get("QR_SKIP_SPLITS"):
        # Stale-cache-tolerant path: bypass the 24h TTL by reading raw JSON.
        cache_file = _cache_path(ticker)
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                raw = payload.get("splits", [])
                events: list[SplitEvent] = []
                for entry in raw:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        d = date.fromisoformat(str(entry["date"]))
                        r = float(entry["ratio"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    events.append(SplitEvent(split_date=d, ratio=r))
                logger.debug(
                    "splits FORCE-HIT (QR_SKIP_SPLITS=1) for %s "
                    "(stale-tolerant, %d events)",
                    ticker,
                    len(events),
                )
                return events
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_SPLITS stale-read failed for %s: %s — "
                    "returning None (no split detected)",
                    ticker,
                    exc,
                )
                return None
        return None

    cached = _cache_read(ticker)
    if cached is not None:
        return cached

    try:
        events = _yf_fetch_splits(ticker)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "splits fetch failed for %s (non-fatal, post_split_share_lag "
            "flag will not fire): %s",
            ticker,
            exc,
        )
        return None

    _cache_write(ticker, events)
    return events
