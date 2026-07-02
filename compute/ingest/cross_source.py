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

# yfinance `fast_info.exchange` returns a terse MIC-ish code, not the
# human exchange name. Map the codes that appear on the S&P 500 universe to
# a display name. Unknown codes pass through verbatim (forward-safe — better
# to show the raw code than to drop the field). Sourced from the Yahoo
# Finance exchange-code set: NMS/NGM/NCM = the three NASDAQ tiers (Global
# Select / Global Market / Capital Market), NYQ = NYSE, PCX = NYSE Arca,
# ASE = NYSE American, BATS/BTS = Cboe BZX.
#
# ``BTS`` (2026-06-02 post-cron stock-detail audit) — Cboe Global Markets
# (ticker CBOE) self-lists on its own Cboe BZX Exchange; Yahoo emits the
# terse ``BTS`` code for it, DISTINCT from the ``BATS`` code already mapped.
# Before this entry, ``BTS`` passed through raw as the exchange name AND —
# because it was absent from ``_US_EXCHANGE_CODES`` (derived from these keys)
# — ``country_for_exchange("BTS")`` returned None, so CBOE rendered a raw
# "BTS" chip with no country flag. Adding it here fixes BOTH (exchange display
# + the US country tag in one line, since the country set derives from these
# keys).
_EXCHANGE_NAME_BY_CODE: dict[str, str] = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NyseArca": "NYSE Arca",
    "PCX": "NYSE Arca",
    "NYQ": "NYSE",
    "ASE": "NYSE American",
    "BATS": "Cboe BZX",
    "BTS": "Cboe BZX",
}

# Every venue above is a US listing. The S&P 500 is a US-large-cap index, so
# country is "US" for the whole universe today; deriving it from the exchange
# (rather than hardcoding) keeps the field correct if a non-US ADR's primary
# venue ever surfaces a foreign code — that code would simply not be in this
# set and country would fall back to None (display layer treats None as "—").
_US_EXCHANGE_CODES: frozenset[str] = frozenset(_EXCHANGE_NAME_BY_CODE)


# yfinance `fast_info.quote_type` returns uppercase instrument-type codes.
# Map the codes that appear on the S&P 1500 universe to human display labels.
# Unknown codes pass through verbatim (forward-safe — same philosophy as the
# exchange-code map; better to show the raw code than drop the field so the
# frontend always has something to display).
#
# Known codes observed on the S&P 1500 + broad US-equity universe:
#   EQUITY     → domestic common stock (the overwhelming majority)
#   ETF        → exchange-traded fund
#   MUTUALFUND → open-end mutual fund (rare on S&P 1500; included for safety)
#   INDEX      → index tracking product
#   FUTURE     → futures contract
#   CURRENCY   → currency pair (unexpected here but forward-safe passthrough)
#
# ADR note: yfinance returns ``EQUITY`` for most ADRs because Yahoo Finance
# treats them as regular equities from the perspective of ``fast_info``.
# The SEC-side ADR refinement (20-F document type OR EDGAR ``entityType``
# = "foreign private issuer") is a TODO(#541 PR-1b) — wiring it cleanly
# requires a new SEC submissions-JSON fetch that has no existing cache
# surface in this layer.  PR-1 ships the yfinance ``quote_type`` as the
# primary signal; the ADR override will be added in PR-1b once the SEC
# entityType cache is available without introducing a new network round-trip.
_QUOTE_TYPE_LABEL: dict[str, str] = {
    "EQUITY": "Common stock",
    "ETF": "ETF",
    "MUTUALFUND": "Fund",
    "INDEX": "Index",
    "FUTURE": "Future",
    "CURRENCY": "Currency",
}


def security_type_label(quote_type: str | None) -> str | None:
    """Map a yfinance ``fast_info.quote_type`` code to a display label.

    Unknown codes pass through verbatim (forward-safe) so new instrument
    types surface as-is rather than being silently dropped.
    """
    if not quote_type:
        return None
    return _QUOTE_TYPE_LABEL.get(quote_type.upper(), quote_type)


# yfinance `.info["sector"]` returns its own 11-sector vocabulary, which is
# a near-but-not-exact match for GICS sector names — 5 are verbatim, 6 are
# renamed. Phase 9.4 PR-1 (sector-resolution coverage canary, observability
# only — see the module-level Rule-18 note on ``fetch_yfinance_sector``).
#
# The 11 target (mapped-to) keys MUST exactly match the keys of
# ``compute.scoring.cost_of_equity.SECTOR_COST_OF_EQUITY`` — a test pins
# this equality so the two vocabularies can never silently drift apart.
#
# yfinance's own category vocabulary HAS drifted before elsewhere in this
# codebase (dividend_yield_pct format-reversion #533, payout_ratio
# format-reversion #554) — treat an unmapped raw sector string as the
# drift TELL this canary exists to surface, not a bug to silently patch
# around. Unmapped / missing / None → None (stays "Unknown" downstream;
# this PR does NOT wire the mapped value into any scored field — see
# ``compute/main.py``'s Phase 9.4 PR-1 canary comment).
_YF_SECTOR_TO_GICS: dict[str, str] = {
    # Verbatim (5).
    "Communication Services": "Communication Services",
    "Energy": "Energy",
    "Industrials": "Industrials",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
    # Renamed (6).
    "Basic Materials": "Materials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Healthcare": "Health Care",
    "Technology": "Information Technology",
}


def map_yfinance_sector_to_gics(raw_sector: str | None) -> str | None:
    """Map a RAW yfinance ``.info["sector"]`` string to the 11-key GICS
    vocabulary used by ``SECTOR_COST_OF_EQUITY`` (Damodaran 2019/2025
    sector-Ke table), or ``None`` if unmapped / absent.

    Diagnostic-only helper for the Phase 9.4 PR-1 sector-resolution
    coverage canary (``Metadata.broad_universe_sector_resolved_pct``).
    NEVER used to set a scored ticker's ``sector`` field this PR — that
    is explicitly out of scope (observability-before-wiring, Rule 18);
    see the ``compute/main.py`` canary comment + CLAUDE.md §Gotchas.
    """
    if not raw_sector:
        return None
    return _YF_SECTOR_TO_GICS.get(raw_sector)


def exchange_name(code: str | None) -> str | None:
    """Map a yfinance exchange code to a display name (passthrough on unknown)."""
    if not code:
        return None
    return _EXCHANGE_NAME_BY_CODE.get(code, code)


def country_for_exchange(code: str | None) -> str | None:
    """Derive ISO-ish country tag from the exchange code. US-only universe today."""
    if not code:
        return None
    return "US" if code in _US_EXCHANGE_CODES else None


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


def _shares_outstanding_cache_read(ticker: str) -> float | None:
    """Return cached sharesOutstanding or None on miss / expired / corrupt.

    Reuses the same ``yfinance_info/<ticker>.json`` file as the market-cap
    cache.  Backward-compatible: entries written before this field existed
    simply have no ``shares_outstanding`` key and return None.
    """
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("yfinance_info shares cache read failed for %s: %s", ticker, e)
        return None
    val = payload.get("shares_outstanding")
    if not isinstance(val, (int, float)) or val <= 0:
        return None
    return float(val)


def _dividend_cache_read(ticker: str) -> tuple[float | None, float | None]:
    """Return cached (dividend_yield_pct, payout_ratio) or (None, None).

    Reuses the same ``yfinance_info/<ticker>.json`` file as the market-cap
    cache.  ``dividend_yield_pct`` is stored as a PERCENT (e.g. 2.0 for 2%)
    as returned directly by yfinance (no conversion needed since yfinance now
    returns percent, not a fraction).  ``payout_ratio`` is the raw yfinance
    fraction (0-1).

    Backward-compatible: cache entries written before this field existed
    simply have no ``dividend_yield_pct`` / ``payout_ratio`` keys and
    return (None, None).
    """
    path = _cache_path(ticker)
    if not path.exists():
        return (None, None)
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return (None, None)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("yfinance_info dividend cache read failed for %s: %s", ticker, e)
        return (None, None)
    dy_val = payload.get("dividend_yield_pct")
    pr_val = payload.get("payout_ratio")
    dividend_yield_pct = (
        float(dy_val) if isinstance(dy_val, (int, float)) and dy_val >= 0 else None
    )
    # Defensive >100 clamp at the cache-read boundary: a stale cache file written
    # by the pre-#533 ×100 code (e.g. KO 267.0) must never surface a 100× inflated
    # value on a pure warm-cache hit. Mirrors the live-path guard in _yf_info_fetch.
    if dividend_yield_pct is not None and dividend_yield_pct > 100.0:
        logger.warning(
            "cached dividend_yield_pct %.4f > 100 for %s — discarding as implausible"
            " (pre-#533 ×100 stale cache?)",
            dividend_yield_pct,
            ticker,
        )
        dividend_yield_pct = None
    payout_ratio = (
        float(pr_val) if isinstance(pr_val, (int, float)) and pr_val >= 0 else None
    )
    # Defensive >20 clamp at the cache-read boundary: a stale cache file written
    # when yfinance returned a percent-format payout_ratio (e.g. SLG=153.75)
    # must never surface an implausible value on a warm-cache hit.
    # Mirrors the dividend_yield_pct >100 clamp added in the #533 follow-up.
    if payout_ratio is not None and payout_ratio > 20.0:
        logger.warning(
            "cached payout_ratio %.4f > 20 for %s — discarding as implausible"
            " (stale cache written with percent-format payout_ratio?)",
            payout_ratio,
            ticker,
        )
        payout_ratio = None
    return (dividend_yield_pct, payout_ratio)


def _sector_cache_read(ticker: str) -> tuple[str | None, str | None]:
    """Return cached (sector, industry) RAW yfinance strings, or (None, None).

    Phase 9.4 PR-1 sector-resolution coverage canary.  Reuses the same
    ``yfinance_info/<ticker>.json`` file as the market-cap cache — the
    ``.info["sector"]`` / ``.info["industry"]`` values are written to the
    cache as a zero-cost side-channel during the live ``_yf_info_fetch``
    call that already fetches ``marketCap`` + ``sharesOutstanding``.

    Backward-compatible: cache entries written before this field existed
    simply have no ``sector`` / ``industry`` keys and return (None, None).
    """
    path = _cache_path(ticker)
    if not path.exists():
        return (None, None)
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return (None, None)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("yfinance_info sector cache read failed for %s: %s", ticker, e)
        return (None, None)
    sector_val = payload.get("sector")
    industry_val = payload.get("industry")
    sector = sector_val if isinstance(sector_val, str) and sector_val else None
    industry = industry_val if isinstance(industry_val, str) and industry_val else None
    return (sector, industry)


def _cache_write(
    ticker: str,
    market_cap: float,
    shares_outstanding: float | None = None,
    dividend_yield_pct: float | None = None,
    payout_ratio: float | None = None,
    sector: str | None = None,
    industry: str | None = None,
) -> None:
    """Merge-write market_cap (and optionally other fields) into the cache.

    Reads the existing JSON file first so that a subsequent exchange-code
    write (``_exchange_cache_write``) does not clobber freshly written
    values.  The merge pattern keeps the file as the single source of
    truth for all yfinance_info fields.

    ``dividend_yield_pct`` is stored as a PERCENT (e.g. 2.0 for 2%).
    yfinance now returns ``dividendYield`` already in percent, so no
    ×100 conversion is needed by the caller.  ``payout_ratio`` is the
    raw 0-1 fraction from yfinance.

    ``sector`` / ``industry`` (Phase 9.4 PR-1) are the RAW yfinance
    ``.info`` strings — stored verbatim, un-mapped.  Diagnostic-only.
    """
    path = _cache_path(ticker)
    payload: dict[str, object] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload["market_cap"] = float(market_cap)
    if shares_outstanding is not None and shares_outstanding > 0:
        payload["shares_outstanding"] = float(shares_outstanding)
    # Dividend fields: store only when the ingest yielded a positive value.
    # Zero dividend_yield_pct is valid (non-dividend payer detected) and is
    # also stored so pays_dividend can be derived correctly on cache reads.
    if dividend_yield_pct is not None and dividend_yield_pct >= 0:
        payload["dividend_yield_pct"] = float(dividend_yield_pct)
    if payout_ratio is not None and payout_ratio >= 0:
        payload["payout_ratio"] = float(payout_ratio)
    if sector is not None and isinstance(sector, str) and sector:
        payload["sector"] = sector
    if industry is not None and isinstance(industry, str) and industry:
        payload["industry"] = industry
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
def _yf_info_fetch(
    ticker: str,
) -> tuple[
    float | None, float | None, float | None, float | None, str | None, str | None
]:
    """Pull marketCap + sharesOutstanding + dividendYield + payoutRatio +
    sector + industry in one call.

    Returns ``(market_cap, shares_outstanding, dividend_yield_pct,
    payout_ratio, sector, industry)``. Any element may be None when the
    field is absent or invalid.  Raises on persistent network errors
    (tenacity retries the caller).

    ``dividend_yield_pct`` is returned as a PERCENT.  yfinance now returns
    ``dividendYield`` already in percent (e.g. 2.67 = 2.67%) — no ×100
    conversion is applied.  Values > 100 are discarded as implausible
    (format-reversion guard).  ``payout_ratio`` is returned as-is (0-1 fraction).

    ``sector`` / ``industry`` (Phase 9.4 PR-1, sector-resolution coverage
    canary) are the RAW yfinance ``.info["sector"]`` / ``.info["industry"]``
    strings — un-mapped, whatever vocabulary yfinance happens to use this
    week (its category names have drifted before — see the dividend #533 /
    payout-ratio #554 format-reversion precedents — so treat these two as
    display/diagnostic-only, never as a scoring input).  ``None`` when the
    key is absent, empty, or not a string (e.g. yfinance's ``"Industrials"``
    placeholder is real data; a missing key on a delisted/thin ticker is
    the common failure mode).
    """
    info = yf.Ticker(ticker).info
    mc_val = info.get("marketCap") if isinstance(info, dict) else None
    so_val = info.get("sharesOutstanding") if isinstance(info, dict) else None
    dy_val = info.get("dividendYield") if isinstance(info, dict) else None
    pr_val = info.get("payoutRatio") if isinstance(info, dict) else None
    sector_val = info.get("sector") if isinstance(info, dict) else None
    industry_val = info.get("industry") if isinstance(info, dict) else None
    market_cap = float(mc_val) if isinstance(mc_val, (int, float)) and mc_val > 0 else None
    shares_out = float(so_val) if isinstance(so_val, (int, float)) and so_val > 0 else None
    # dividendYield was a fraction pre-2025; yfinance now returns percent directly
    # (e.g. 2.67 = 2.67%).  No ×100 conversion needed.
    dividend_yield_pct = (
        float(dy_val)
        if isinstance(dy_val, (int, float)) and dy_val >= 0
        else None
    )
    if dividend_yield_pct is not None and dividend_yield_pct > 100.0:
        # Implausible yield — yfinance format may have reverted to a fraction;
        # discard rather than emit a 100× inflated value.
        logger.warning(
            "dividend_yield_pct %.4f > 100 for %s — discarding as implausible"
            " (yfinance format drift?)",
            dividend_yield_pct,
            ticker,
        )
        dividend_yield_pct = None
    payout_ratio = (
        float(pr_val) if isinstance(pr_val, (int, float)) and pr_val >= 0 else None
    )
    # payout_ratio is a 0-1 fraction; yfinance occasionally returns a PERCENT-
    # format value for companies with negative/near-zero earnings (observed:
    # SLG=153.75 on the first sp1500 cron, meaning 15375% payout). A legitimate
    # high-but-real ratio (e.g. a REIT at 1.5 = 150%) stays; only garbage > 20
    # (>2000%) is discarded as implausible. Same pattern as the
    # dividend_yield_pct > 100 guard added in #533.
    if payout_ratio is not None and payout_ratio > 20.0:
        logger.warning(
            "payout_ratio %.4f > 20 for %s — discarding as implausible"
            " (yfinance returning percent-format instead of 0-1 fraction?)",
            payout_ratio,
            ticker,
        )
        payout_ratio = None
    sector = sector_val if isinstance(sector_val, str) and sector_val else None
    industry = industry_val if isinstance(industry_val, str) and industry_val else None
    return (market_cap, shares_out, dividend_yield_pct, payout_ratio, sector, industry)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _yf_info_market_cap(ticker: str) -> float | None:
    """Pull marketCap from yfinance .info. Raises on persistent network errors.

    .. deprecated::
        Kept for backward-compatibility with any call sites that mock this
        private function in tests.  New production code uses ``_yf_info_fetch``
        so the single Ticker round-trip populates both market_cap and
        shares_outstanding into the cache.
    """
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
        (
            market_cap,
            shares_outstanding,
            dividend_yield_pct,
            payout_ratio,
            sector,
            industry,
        ) = _yf_info_fetch(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance info fetch failed for %s: %s", ticker, e)
        return None

    if market_cap is None:
        return None

    # Populate all fields in a single cache write so subsequent calls to
    # fetch_yfinance_shares_outstanding, fetch_yfinance_dividend, and
    # fetch_yfinance_sector hit the cache without a second Ticker.info
    # round-trip.
    _cache_write(
        ticker,
        market_cap,
        shares_outstanding,
        dividend_yield_pct=dividend_yield_pct,
        payout_ratio=payout_ratio,
        sector=sector,
        industry=industry,
    )
    return market_cap


def fetch_yfinance_shares_outstanding(ticker: str) -> float | None:
    """Return yfinance-reported ``sharesOutstanding`` for ``ticker``, or ``None``.

    Used by ``compute/main.py`` Step 3b to supply the
    ``yf_shares_outstanding_override`` to ``check_post_split_share_lag``
    — a direct share count avoids the cache-timing trap where
    ``yf_market_cap / current_price`` gives a wrong implied-share count
    when the price and market-cap caches straddle a split date.

    Cache contract (identical to ``fetch_yfinance_market_cap``)
    -----------------------------------------------------------
    • Reads ``yfinance_info/<ticker>.json`` (same file, ``shares_outstanding``
      key written as a side-effect of ``fetch_yfinance_market_cap`` from
      ``_yf_info_fetch``).
    • 24h TTL on live runs; stale-cache-tolerant read on
      ``QR_SKIP_CROSS_SOURCE=1`` (pre-merge-prod-sim escape hatch — same
      semantics as for market_cap: warm cache → return stale value, cold
      cache → return None, never crash, never live-fetch).
    • On a warm market_cap cache (common case) the ``shares_outstanding``
      field was already written during the same Ticker.info call, so this
      function is a pure cache read at zero network cost.
    • On a cold cache (first cron / cache eviction) this function does NOT
      trigger a live fetch on its own — it returns None and lets the caller
      fall back to the existing market_cap/price path.  The live fetch is
      owned by ``fetch_yfinance_market_cap`` which is called first in the
      Step 3b loop, ensuring the cache is populated before this function
      is called.
    """
    if os.environ.get("QR_SKIP_CROSS_SOURCE"):
        # Stale-cache-tolerant path: same pattern as fetch_yfinance_market_cap.
        cache_file = _cache_path(ticker)
        if cache_file.exists():
            try:
                with cache_file.open() as f:
                    payload = json.load(f)
                val = payload.get("shares_outstanding")
                if not isinstance(val, (int, float)) or val <= 0:
                    return None
                logger.debug(
                    "yfinance_info shares FORCE-HIT (QR_SKIP_CROSS_SOURCE=1) "
                    "for %s (stale-tolerant)", ticker,
                )
                return float(val)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_CROSS_SOURCE shares stale-read failed for %s: %s — "
                    "skipping override", ticker, e,
                )
                return None
        return None

    # Normal path: TTL-gated cache read only.  No live fetch here — the
    # market_cap call (earlier in the same loop iteration) already did the
    # Ticker.info round-trip and populated the cache.
    return _shares_outstanding_cache_read(ticker)


def fetch_yfinance_dividend(
    ticker: str,
) -> tuple[float | None, bool | None, float | None]:
    """Return ``(dividend_yield_pct, pays_dividend, payout_ratio)`` for ``ticker``.

    Dividend signal PR-1 (roadmap item #5 / 7a — observability-first,
    Rule 18).  This is a PURE CACHE-READ off the existing
    ``yfinance_info/<ticker>.json`` cache file populated by
    ``fetch_yfinance_market_cap`` during the Step-8 cross-source loop.
    No new network round-trip is introduced; the dividend fields are
    written to the cache as a zero-cost side-channel during the live
    ``_yf_info_fetch`` call that already fetches ``marketCap`` +
    ``sharesOutstanding``.

    Parameters
    ----------
    ticker:
        Stock ticker symbol.

    Returns
    -------
    tuple[float | None, bool | None, float | None]
        ``(dividend_yield_pct, pays_dividend, payout_ratio)`` where:

        - ``dividend_yield_pct``: annualised dividend yield expressed as
          a PERCENT (e.g. 2.0 for 2%).  yfinance now returns
          ``dividendYield`` already in percent (no ×100 conversion).
          Zero means the ticker actively pays no dividend (confirmed by
          yfinance); ``None`` means the data was unavailable.
        - ``pays_dividend``: ``True`` iff ``dividend_yield_pct > 0``;
          ``False`` iff ``dividend_yield_pct == 0``; ``None`` when
          ``dividend_yield_pct`` is ``None``.
        - ``payout_ratio``: raw 0-1 fraction from yfinance
          ``payoutRatio``, or ``None``.

    Failure semantics
    -----------------
    Returns ``(None, None, None)`` on:

    - No cache entry exists (cold cache / first run before
      ``fetch_yfinance_market_cap`` has been called for this ticker).
    - Cache entry is stale / corrupt.
    - Dividend fields were absent from the yfinance ``.info`` dict
      (e.g. a ticker with no dividend history).

    This function NEVER triggers a live yfinance fetch.  Callers that
    need live data must call ``fetch_yfinance_market_cap`` first (which
    populates all fields in one round-trip), then call this function.
    In practice the Step-8 loop already calls ``fetch_yfinance_market_cap``
    earlier in the same ticker iteration, so the cache is warm by the
    time this function is called.

    QR_SKIP_CROSS_SOURCE
    ---------------------
    When ``QR_SKIP_CROSS_SOURCE=1`` is set (pre-merge-prod-sim escape
    hatch), reads the cache with the same stale-tolerant path as
    ``fetch_yfinance_shares_outstanding``: warm cache → return values;
    cold cache → ``(None, None, None)`` (no live fetch).
    """
    if os.environ.get("QR_SKIP_CROSS_SOURCE"):
        cache_file = _cache_path(ticker)
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                dy_val = payload.get("dividend_yield_pct")
                pr_val = payload.get("payout_ratio")
                dividend_yield_pct = (
                    float(dy_val)
                    if isinstance(dy_val, (int, float)) and dy_val >= 0
                    else None
                )
                # Same >100 stale-cache clamp as _dividend_cache_read (a pre-#533
                # ×100 cache file must not surface a 100× inflated value here).
                if dividend_yield_pct is not None and dividend_yield_pct > 100.0:
                    logger.warning(
                        "cached dividend_yield_pct %.4f > 100 for %s (QR_SKIP) —"
                        " discarding as implausible (pre-#533 ×100 stale cache?)",
                        dividend_yield_pct,
                        ticker,
                    )
                    dividend_yield_pct = None
                payout_ratio = (
                    float(pr_val)
                    if isinstance(pr_val, (int, float)) and pr_val >= 0
                    else None
                )
                # Same >20 stale-cache clamp as _dividend_cache_read: a cache file
                # written when yfinance returned a percent-format payout_ratio
                # (e.g. SLG=153.75) must not surface an implausible value here.
                if payout_ratio is not None and payout_ratio > 20.0:
                    logger.warning(
                        "cached payout_ratio %.4f > 20 for %s (QR_SKIP) —"
                        " discarding as implausible (stale cache with percent-format?)",
                        payout_ratio,
                        ticker,
                    )
                    payout_ratio = None
                pays_dividend = (
                    dividend_yield_pct > 0 if dividend_yield_pct is not None else None
                )
                logger.debug(
                    "yfinance_info dividend FORCE-HIT (QR_SKIP_CROSS_SOURCE=1) "
                    "for %s (stale-tolerant)",
                    ticker,
                )
                return (dividend_yield_pct, pays_dividend, payout_ratio)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_CROSS_SOURCE dividend stale-read failed for %s: %s — "
                    "returning (None, None, None)",
                    ticker,
                    e,
                )
                return (None, None, None)
        return (None, None, None)

    # Normal path: TTL-gated cache read only. No live fetch here — the
    # market_cap call (earlier in the same loop iteration) already did the
    # Ticker.info round-trip and populated all fields into the cache.
    dividend_yield_pct, payout_ratio = _dividend_cache_read(ticker)
    pays_dividend = (
        dividend_yield_pct > 0 if dividend_yield_pct is not None else None
    )
    return (dividend_yield_pct, pays_dividend, payout_ratio)


def _security_type_cache_read(ticker: str) -> str | None:
    """Return cached raw ``quote_type`` code, or None on miss / expired / corrupt.

    Reuses the same ``yfinance_info/<ticker>.json`` file.  The ``quote_type``
    key is written as a side-channel during ``fetch_yfinance_exchange``'s live
    ``_yf_fast_exchange`` call (zero extra round-trips).  Backward-compatible:
    pre-existing cache entries without the ``quote_type`` key return None.
    """
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("yfinance_info security_type cache read failed for %s: %s", ticker, e)
        return None
    val = payload.get("quote_type")
    return val if isinstance(val, str) and val else None


def _exchange_cache_read(ticker: str) -> str | None:
    """Return cached raw exchange code, or None on miss / expired / corrupt.

    Reuses the same `yfinance_info/<ticker>.json` file as the market-cap
    cache (one Ticker round-trip populates both). Backward-compatible: a
    pre-existing cache entry written before this field existed simply has no
    `exchange` key and returns None (a later fetch re-populates it).
    """
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > _CACHE_TTL_SECONDS:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("yfinance_info exchange cache read failed for %s: %s", ticker, e)
        return None
    val = payload.get("exchange")
    return val if isinstance(val, str) and val else None


def _exchange_cache_write(
    ticker: str,
    exchange_code: str,
    quote_type: str | None = None,
) -> None:
    """Merge the exchange code (and optionally quote_type) into the cache file.

    Security-type signal PR-1 (0.10.30-phase8pilot): ``quote_type`` is now
    captured in the same ``fast_info`` call as ``exchange`` and stored in the
    same cache file under the ``"quote_type"`` key.  A subsequent call to
    ``_security_type_cache_read`` retrieves it at zero extra network cost.
    Pre-existing callers that omit ``quote_type`` are unaffected (the key is
    simply not written if ``None``).
    """
    path = _cache_path(ticker)
    payload: dict[str, object] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload["exchange"] = exchange_code
    if quote_type is not None and isinstance(quote_type, str) and quote_type:
        payload["quote_type"] = quote_type
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("yfinance_info exchange cache write failed for %s: %s", ticker, e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _yf_fast_exchange(ticker: str) -> tuple[str | None, str | None]:
    """Pull the raw exchange code + quote_type from yfinance ``fast_info``.

    Returns ``(exchange_code, quote_type)`` — either element may be None when
    the field is absent or the scraper returns nothing.  Raises on persistent
    network errors (tenacity retries the caller).

    Uses ``fast_info`` (the lightweight scraper) rather than ``.info`` —
    exchange and quote_type are both native ``fast_info`` attributes.
    Capturing both in one call means ``fetch_yfinance_security_type`` costs
    zero extra network round-trips: ``quote_type`` is stored as a side-channel
    in the same ``yfinance_info/<ticker>.json`` cache file that ``exchange``
    already writes to.

    Security-type signal PR-1 (0.10.30-phase8pilot): return type changed from
    ``str | None`` to ``tuple[str | None, str | None]`` to carry quote_type.
    The only caller is ``fetch_yfinance_exchange`` (below) — updated in this
    same PR to unpack the 2-tuple.
    """
    fi = yf.Ticker(ticker).fast_info
    # ``exchange`` key is camelCase in fast_info.keys() and also an attribute.
    # ``quoteType`` is the camelCase key (maps to snake_case ``quote_type`` attr).
    # Primary path: fast_info.get() (camelCase-aware mapping, available in
    # yfinance >= 0.2).  Fallback: getattr uses snake_case attribute names
    # (``quote_type`` not ``quoteType`` — fast_info stores them as properties).
    code = fi.get("exchange") if hasattr(fi, "get") else getattr(fi, "exchange", None)
    qt = (
        fi.get("quoteType")
        if hasattr(fi, "get")
        else getattr(fi, "quote_type", None)
    )
    exchange_code = code if isinstance(code, str) and code else None
    quote_type = qt if isinstance(qt, str) and qt else None
    return (exchange_code, quote_type)


def fetch_yfinance_exchange(ticker: str) -> str | None:
    """Return the raw yfinance exchange code for ``ticker`` (display-mapped by
    `exchange_name`), or ``None``.

    Same graceful-degradation contract as `fetch_yfinance_market_cap`: 24h
    disk cache first, then a tenacity-retried live fetch, returning ``None``
    on persistent failure rather than raising (the caller treats absence as
    "no exchange shown"). Honors the same ``QR_SKIP_CROSS_SOURCE=1`` escape
    hatch — stale-cache-tolerant read when set, no live fetch on a cold miss.

    Security-type signal PR-1 (0.10.30-phase8pilot): on a live fetch,
    ``quote_type`` is captured from the same ``fast_info`` call (zero extra
    round-trips) and written to the cache alongside ``exchange`` via the
    updated ``_exchange_cache_write``.  A subsequent call to
    ``fetch_yfinance_security_type`` finds it in the warm cache.
    """
    if os.environ.get("QR_SKIP_CROSS_SOURCE"):
        path = _cache_path(ticker)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                val = payload.get("exchange")
                return val if isinstance(val, str) and val else None
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_CROSS_SOURCE exchange stale-read failed for %s: %s",
                    ticker, e,
                )
                return None
        return None

    cached = _exchange_cache_read(ticker)
    if cached is not None:
        return cached

    try:
        code, quote_type = _yf_fast_exchange(ticker)
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance exchange fetch failed for %s: %s", ticker, e)
        return None

    if code is None:
        # Don't cache when the exchange code is absent: an empty-exchange key
        # would poison the cache, and the missing exchange is already handled by
        # the None passthrough. A quote_type seen without an exchange is dropped
        # here and re-resolves on the next fetch that returns a valid exchange.
        return None

    _exchange_cache_write(ticker, code, quote_type=quote_type)
    return code


def fetch_yfinance_security_type(ticker: str) -> str | None:
    """Return the mapped security-type label for ``ticker``, or ``None``.

    Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.30-phase8pilot,
    Rule 18 observability-first).  This is a PURE CACHE-READ off the existing
    ``yfinance_info/<ticker>.json`` cache file.  The ``quote_type`` field is
    written to the cache as a zero-cost side-channel during the live
    ``_yf_fast_exchange`` call inside ``fetch_yfinance_exchange`` — which is
    called earlier in the same Step-8 loop iteration, so the cache is warm
    by the time this function is called.

    Returns the display label (e.g. ``"Common stock"`` for ``EQUITY``,
    ``"ETF"`` for ``ETF``); unknown yfinance codes pass through verbatim
    (forward-safe).  Returns ``None`` on cold cache, corrupt cache, or absent
    ``quote_type`` field.

    This function NEVER triggers a live yfinance fetch.  Callers that need
    live data must call ``fetch_yfinance_exchange`` first (which populates
    both fields in one round-trip), then call this function.  In practice
    the Step-8 loop already calls ``fetch_yfinance_exchange`` earlier in the
    same ticker iteration.

    QR_SKIP_CROSS_SOURCE
    --------------------
    When ``QR_SKIP_CROSS_SOURCE=1`` is set (pre-merge-prod-sim escape hatch),
    reads the cache with the same stale-tolerant path as
    ``fetch_yfinance_shares_outstanding``: warm cache → return label;
    cold cache → ``None`` (no live fetch).

    **DESCRIPTIVE METADATA ONLY** — NOT a scoring input, NOT a defense flag.
    Does NOT influence composite score, risk_flags, recommendation, or Top-5.
    """
    if os.environ.get("QR_SKIP_CROSS_SOURCE"):
        path = _cache_path(ticker)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                qt = payload.get("quote_type")
                if not isinstance(qt, str) or not qt:
                    return None
                logger.debug(
                    "yfinance_info security_type FORCE-HIT (QR_SKIP_CROSS_SOURCE=1) "
                    "for %s (stale-tolerant)",
                    ticker,
                )
                return security_type_label(qt)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_CROSS_SOURCE security_type stale-read failed for %s: %s — "
                    "returning None",
                    ticker,
                    e,
                )
                return None
        return None

    # Normal path: TTL-gated cache read only.  No live fetch here — the
    # exchange call (earlier in the same loop iteration) already did the
    # fast_info round-trip and populated both exchange + quote_type into cache.
    raw = _security_type_cache_read(ticker)
    return security_type_label(raw)


def fetch_yfinance_sector(ticker: str) -> str | None:
    """Return the RAW yfinance ``.info["sector"]`` string for ``ticker``, or
    ``None``.

    Phase 9.4 PR-1 (sector-resolution coverage canary — OBSERVABILITY ONLY,
    Rule 18).  This is a PURE CACHE-READ off the existing
    ``yfinance_info/<ticker>.json`` cache file populated by
    ``fetch_yfinance_market_cap`` during the Step-8 cross-source loop.  No
    new network round-trip is introduced; ``sector`` (and ``industry``) are
    written to the cache as a zero-cost side-channel during the live
    ``_yf_info_fetch`` call that already fetches ``marketCap`` +
    ``sharesOutstanding`` + the dividend fields.

    Returns the RAW, UN-MAPPED yfinance string (e.g. ``"Technology"``, not
    the GICS-renamed ``"Information Technology"``) — callers that need the
    GICS-mapped 11-key vocabulary call ``map_yfinance_sector_to_gics()``
    separately.  ``None`` on cold cache, corrupt cache, or an absent
    ``sector`` key (both are common failure modes: a cold cache before
    ``fetch_yfinance_market_cap`` has run for this ticker this cycle, or a
    thinly-covered / delisted ticker yfinance has no sector data for).

    This function NEVER triggers a live yfinance fetch.  Callers that need
    live data must call ``fetch_yfinance_market_cap`` first (which
    populates all fields in one round-trip), then call this function.  In
    practice the Step-8 loop already calls ``fetch_yfinance_market_cap``
    earlier in the same ticker iteration, so the cache is warm by the time
    this function is called.

    QR_SKIP_CROSS_SOURCE
    ---------------------
    When ``QR_SKIP_CROSS_SOURCE=1`` is set (pre-merge-prod-sim escape
    hatch), reads the cache with the same stale-tolerant path as
    ``fetch_yfinance_shares_outstanding`` / ``fetch_yfinance_dividend``:
    warm cache → return value; cold cache → ``None`` (no live fetch).

    **DIAGNOSTIC / OBSERVABILITY-ONLY** — NOT a scoring input, NOT a
    defense flag, and NOT wired into any scored ticker's ``sector`` field
    this PR.  Does NOT influence composite score, risk_flags, fair-price,
    peer-medians, or ``select_picks``. See the Phase 9.4 PR-1 canary
    comment in ``compute/main.py`` for the full Rule-18 constraint.
    """
    if os.environ.get("QR_SKIP_CROSS_SOURCE"):
        cache_file = _cache_path(ticker)
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                sector_val = payload.get("sector")
                if not isinstance(sector_val, str) or not sector_val:
                    return None
                logger.debug(
                    "yfinance_info sector FORCE-HIT (QR_SKIP_CROSS_SOURCE=1) "
                    "for %s (stale-tolerant)",
                    ticker,
                )
                return sector_val
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "QR_SKIP_CROSS_SOURCE sector stale-read failed for %s: %s — "
                    "returning None",
                    ticker,
                    e,
                )
                return None
        return None

    # Normal path: TTL-gated cache read only.  No live fetch here — the
    # market_cap call (earlier in the same loop iteration) already did the
    # Ticker.info round-trip and populated sector + industry into cache.
    sector, _industry = _sector_cache_read(ticker)
    return sector


def validate_market_cap(
    ticker: str,
    snap: FundamentalsSnapshot | None,
    current_price: float | None,
    *,
    yf_market_cap: float | None = None,
    tolerance: float = config.CROSS_SOURCE_MARKET_CAP_TOLERANCE,
) -> tuple[bool, float | None]:
    """Return ``(disagreement_above_tolerance, delta_fraction_or_None)``.

    Issue #248 PR2a (2026-05-25, schema 0.10.3) — signature changed from
    ``-> bool`` to ``-> tuple[bool, float | None]`` so downstream
    observability (``Metadata.cross_source_delta_histogram`` +
    ``StockDetail.cross_source_delta``) can use the computed delta
    instead of recomputing or hiding it. The methodology-scientist Mode B
    verdict (2026-05-25) confirms the existing 5% tolerance + annotate
    semantics are unchanged; only the second-tuple-element is new. The
    second element is None when the inputs are insufficient to compute
    a delta (missing snapshot, missing price, yfinance returned None,
    or any value non-positive); the first element is False in all those
    cases.

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
    tuple[bool, float | None]
        ``(disagreement, delta)`` where ``disagreement`` is True iff the
        two market-cap estimates disagree by more than ``tolerance``, and
        ``delta`` is the absolute relative delta
        ``|sec_mc - yf_mc| / sec_mc`` (a fraction in ``[0, +inf)``, not
        a percentage). ``delta`` is None on any missing input — the same
        quiet-skip conditions that produce ``disagreement = False``.
    """
    if snap is None or snap.shares_outstanding is None:
        return (False, None)
    if snap.shares_outstanding <= 0:
        return (False, None)
    if current_price is None or current_price <= 0:
        return (False, None)

    sec_mc = float(snap.shares_outstanding) * float(current_price)
    if sec_mc <= 0:
        return (False, None)

    if yf_market_cap is None:
        yf_market_cap = fetch_yfinance_market_cap(ticker)
    if yf_market_cap is None or yf_market_cap <= 0:
        return (False, None)

    delta = abs(sec_mc - yf_market_cap) / sec_mc
    return (delta > tolerance, delta)


def bucket_delta(delta: float | None) -> str:
    """Classify a cross-source delta into the observability histogram bucket.

    Issue #248 PR2a (2026-05-25, schema 0.10.3) — used by main.py to
    populate ``Metadata.cross_source_delta_histogram``. 9 buckets total
    with boundaries at 5/25/50/75/100/150/200 % (relative deltas
    expressed as fractions). Buckets are half-open intervals
    ``[lower, upper)`` — an exact-floor value belongs to the next bucket.

    Symmetric resolution around the 100% boundary is intentional per
    methodology-scientist Mode B verdict 2026-05-25: PR2b's severe-
    threshold decision (75 vs 100 vs 150%) will be calibrated from
    histogram tail mass on the first 0.10.3 cron rather than gut-feel.
    The ``"unavailable"`` bucket counts validator-skip cases (missing
    snapshot, missing price, yfinance returned None).
    """
    if delta is None:
        return "unavailable"
    pct = delta * 100.0
    if pct < 5.0:
        return "<5"
    if pct < 25.0:
        return "5-25"
    if pct < 50.0:
        return "25-50"
    if pct < 75.0:
        return "50-75"
    if pct < 100.0:
        return "75-100"
    if pct < 150.0:
        return "100-150"
    if pct < 200.0:
        return "150-200"
    return ">200"


# Drift detector — schema-snapshot guard pins these keys so a bucket-
# boundary rename / addition / deletion forces a coordinated PR2b
# decision. If you change BUCKET_KEYS, also update bucket_delta() above,
# the schema docstring in compute/output/schemas.py, and any consumer
# (verify-production-output helper, audit comparisons).
BUCKET_KEYS: tuple[str, ...] = (
    "<5",
    "5-25",
    "25-50",
    "50-75",
    "75-100",
    "100-150",
    "150-200",
    ">200",
    "unavailable",
)


__all__ = [
    "fetch_yfinance_market_cap",
    "fetch_yfinance_shares_outstanding",
    "fetch_yfinance_dividend",
    "fetch_yfinance_security_type",
    "security_type_label",
    "validate_market_cap",
    "bucket_delta",
    "BUCKET_KEYS",
]
