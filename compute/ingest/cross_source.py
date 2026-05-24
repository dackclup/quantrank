"""Cross-source market-cap validator (Phase 4b §1).

Compares two independent estimates of a stock's market cap:

1. **SEC-derived**: ``shares_outstanding`` (from the XBRL TTM snapshot
   in :mod:`compute.ingest.fundamentals`) × ``current_price`` (from the
   yfinance OHLCV history in :mod:`compute.ingest.prices`).
2. **yfinance-reported**: ``yfinance.Ticker(ticker).info["marketCap"]``
   — pulled from yfinance's metadata API surface (distinct from the
   OHLCV history).

If ``|delta| / sec_mc > CROSS_SOURCE_MARKET_CAP_TOLERANCE`` (default
5%), the ticker is flagged with ``cross_source_disagreement`` in
``StockDetail.valuation_warnings``.

This is **annotate-only** (no Top-N veto). It joins the existing
annotate group with ``beneish_high`` / ``dechow_high``: surfaces a
"verify before trusting" badge without changing the composite.

Mode rationale
--------------

The check catches yfinance scraper drift — the most common Phase 1
fragility. Examples:

- yfinance's cached share count is from a pre-split snapshot (post-split
  it drifts ~2-3× until yfinance refreshes — sometimes weeks)
- yfinance's marketCap field is computed from a different price snapshot
  than the current OHLCV close (intraday vs. EOD)
- yfinance's ticker→company mapping rotated (M&A) and the new entity's
  marketCap doesn't match the old ticker's shares

Per ``defense-infrastructure/PLAN.md`` §1, this catches ~80% of
documented drift cases. The other 20% (yfinance returns None /
errors out / matches but both wrong) require deeper Phase 5+ work.

Cache strategy
--------------

The ``yfinance.Ticker.info`` call is rate-limited more aggressively
than ``yf.download()`` (it hits the metadata API, not the historical
data CDN). We cache responses to
``compute/cache/yfinance_info/<ticker>.json`` with a 24-hour TTL —
same cadence as ``compute/cache/prices/`` per
``config.YFINANCE_INFO_CACHE_MAX_AGE_HOURS``.

Failure semantics
-----------------

Returns ``False`` (no disagreement flag) on:

- yfinance API error / rate limit / network failure
- yfinance returns ``marketCap`` of None / 0 / negative
- ``snap.shares_outstanding`` is None / 0 / negative
- ``current_price`` is None / 0 / negative

Quiet-failure is deliberate: we'd rather miss a yfinance-drift case
than emit a noisy false positive when the underlying data is itself
missing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = config.YFINANCE_INFO_CACHE_MAX_AGE_HOURS * 3600


def _cache_path(ticker: str) -> Path:
    config.YFINANCE_INFO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ticker = re.sub(r"[^A-Za-z0-9_-]", "_", ticker)
    return config.YFINANCE_INFO_CACHE_DIR / f"{safe_ticker}.json"


def _cache_read(ticker: str) -> float | None:
    """Return cached market_cap or None on miss / expired / corrupt."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("yfinance_info cache read failed for %s: %s", ticker, e)
        return None
    val = payload.get("market_cap")
    if not isinstance(val, (int, float)) or val <= 0:
        return None
    return float(val)


def _cache_write(ticker: str, market_cap: float) -> None:
    path = _cache_path(ticker)
    payload = {"market_cap": float(market_cap)}
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("yfinance_info cache write failed for %s: %s", ticker, e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _yf_info_market_cap(ticker: str) -> float | None:
    """Pull marketCap from yfinance .info. Raises on persistent network errors."""
    info = yf.Ticker(ticker).info
    val = info.get("marketCap") if isinstance(info, dict) else None
    if not isinstance(val, (int, float)) or val <= 0:
        return None
    return float(val)


def fetch_yfinance_market_cap(ticker: str) -> float | None:
    """Return yfinance-reported market cap for ``ticker``, or ``None``.

    Hits 24h disk cache first. On miss, fetches via ``Ticker.info`` with
    tenacity retry. Returns ``None`` on persistent failure rather than
    raising — the caller treats absence as "no validation possible"
    (same semantics as the going-concern Tier-2 quiet-skip).

    ``QR_SKIP_CROSS_SOURCE=1`` escape hatch (PR #230 Part 6, 2026-05-24
    — the 5th external-data loop): when set, the 24h freshness gate in
    ``_cache_read`` is bypassed for stale-but-present entries; if cache
    is genuinely empty (cold-runner / first-cron-since-eviction), the
    live yfinance fetch is skipped entirely and ``None`` is returned.
    Used by ``.github/workflows/pre-merge-prod-sim.yml`` to skip the
    502-ticker serial loop ``yf.Ticker(ticker).info`` (2-8s per ticker
    cold = 17-67m) that filled the simulate budget on PR #230 / #238 /
    #241 despite the four prior skip vars (FORM4_FETCH_SKIP +
    QR_SKIP_TIER2 + QR_SKIP_FUNDAMENTALS + QR_SKIP_OSAP) being in
    place. Returning ``None`` means the downstream
    ``validate_market_cap`` cross-check is skipped — semantically
    identical to a cold-cache-fetch-failure, which the call site
    already handles per the existing graceful-degradation pattern.
    Weekly cron does NOT set this — full live fetch runs there.
    """
    if os.environ.get("QR_SKIP_CROSS_SOURCE"):
        # Stale-cache-tolerant path: bypass the 24h TTL in _cache_read
        # by reading the JSON directly when it exists.
        cache_file = _cache_path(ticker)
        if cache_file.exists():
            try:
                with cache_file.open() as f:
                    payload = json.load(f)
                cached = float(payload.get("market_cap"))
                logger.debug(
                    "yfinance_info FORCE-HIT (QR_SKIP_CROSS_SOURCE=1) "
                    "for %s (stale-tolerant)", ticker,
                )
                return cached
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_CROSS_SOURCE stale-read failed for %s: %s — "
                    "skipping validation", ticker, e,
                )
                return None
        # No cache file at all → skip live fetch entirely; cross-check
        # is treated as "no validation possible" (existing semantic).
        return None

    cached = _cache_read(ticker)
    if cached is not None:
        return cached

    try:
        market_cap = _yf_info_market_cap(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance info fetch failed for %s: %s", ticker, e)
        return None

    if market_cap is None:
        return None

    _cache_write(ticker, market_cap)
    return market_cap


def validate_market_cap(
    ticker: str,
    snap: FundamentalsSnapshot | None,
    current_price: float | None,
    *,
    yf_market_cap: float | None = None,
    tolerance: float = config.CROSS_SOURCE_MARKET_CAP_TOLERANCE,
) -> bool:
    """Return True if SEC-derived market cap disagrees with yfinance > tolerance.

    Parameters
    ----------
    ticker:
        Stock ticker. Used only for cache lookup if ``yf_market_cap`` is
        not supplied.
    snap:
        Fundamentals snapshot. Source of ``shares_outstanding``.
    current_price:
        Current price from yfinance OHLCV history. Source of the SEC-
        derived market-cap "price" leg.
    yf_market_cap:
        Optional pre-fetched yfinance market cap (e.g., from a
        cross-source batch fetch). If None, ``fetch_yfinance_market_cap``
        is called inside.
    tolerance:
        Relative delta threshold. Default 5% per
        ``config.CROSS_SOURCE_MARKET_CAP_TOLERANCE``.

    Returns
    -------
    bool
        True iff the two market-cap estimates disagree by more than
        ``tolerance``. False on any missing input (quiet-skip).
    """
    if snap is None or snap.shares_outstanding is None:
        return False
    if snap.shares_outstanding <= 0:
        return False
    if current_price is None or current_price <= 0:
        return False

    sec_mc = float(snap.shares_outstanding) * float(current_price)
    if sec_mc <= 0:
        return False

    if yf_market_cap is None:
        yf_market_cap = fetch_yfinance_market_cap(ticker)
    if yf_market_cap is None or yf_market_cap <= 0:
        return False

    delta = abs(sec_mc - yf_market_cap) / sec_mc
    return delta > tolerance


__all__ = [
    "fetch_yfinance_market_cap",
    "validate_market_cap",
]
