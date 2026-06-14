"""S&P 500, S&P 400, and S&P 900 (combined) constituents from Wikipedia.

SP500 cached to ``compute/cache/universe-v2.parquet`` (gitignored).
SP400 cached to ``compute/cache/universe_sp400-v1.parquet`` (gitignored).
SP900 (combined, de-duped) cached to ``compute/cache/universe_sp900-v1.parquet``.

Re-fetched after the respective ``*_CACHE_MAX_AGE_DAYS`` unless
``force_refresh=True``. Phase 8 pilot adds the SP400 + SP900 paths
(PR 1 — observability-first; ranked output stays SP500-only until PR 3).
"""

from __future__ import annotations

import logging
import time
from io import StringIO
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from compute import config

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = ("ticker", "name", "sector", "sub_industry", "cik")

# Wikipedia is sometimes slow to update post-rename. Map stale symbols here.
# Keys are normalized (dot-to-dash, uppercase). Values are the live ticker.
TICKER_OVERRIDES: dict[str, str] = {
    "FISV": "FI",  # Fiserv renamed in 2024
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
def _fetch_wikipedia_html(url: str = config.WIKIPEDIA_SP500_URL) -> str:
    resp = requests.get(url, headers={"User-Agent": config.HTTP_USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def _normalize_ticker(t: str) -> str:
    return t.strip().replace(".", "-").upper()


# Wikipedia stores some company names with a parenthetical "The" suffix or
# similar quirks ("Hartford (The)", "Lilly (Eli)") that read awkwardly in
# the UI. PR 4c.2 normalizes these to the human-readable form. Add new
# entries here as Wikipedia surfaces more — the function is the single
# transform applied after `df["name"]` is populated.
_NAME_OVERRIDES: dict[str, str] = {
    # Inverted-prefix oddity: "Lilly (Eli)" → "Eli Lilly".
    "Lilly (Eli)": "Eli Lilly",
}


def _normalize_company_name(name: str) -> str:
    """Clean Wikipedia formatting quirks in company names.

    Two pattern types:

    1. ``"X (The)"`` → ``"The X"`` — Wikipedia sorts alphabetically by
       primary noun, so "The Hartford" / "The Walt Disney Company" land
       under H/W with "(The)" suffixed. We restore the natural form.
    2. Explicit overrides in ``_NAME_OVERRIDES`` for one-off cases
       (currently just "Lilly (Eli)" → "Eli Lilly").

    Returns the input unchanged if no rule matches. Affects 13 of 502
    S&P 500 constituents at the 2026-05-14 baseline.
    """
    if name in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[name]
    if name.endswith(" (The)"):
        return "The " + name[: -len(" (The)")]
    return name


def parse_sp500_html(html: str) -> pd.DataFrame:
    """Parse the S&P 500 Wikipedia page HTML into a DataFrame.

    Pulled out so it can be unit-tested with a fixture HTML payload.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"class": "wikitable"})
    if table is None:
        raise ValueError("Could not find S&P 500 constituents table on Wikipedia page.")

    df = pd.read_html(StringIO(str(table)))[0]

    rename_map = {
        "Symbol": "wiki_ticker",
        "Security": "name",
        "GICS Sector": "sector",
        "GICS Sub-Industry": "sub_industry",
        "CIK": "cik",
    }
    missing = [k for k in rename_map if k not in df.columns]
    if missing:
        raise ValueError(f"Wikipedia table is missing expected columns: {missing}")
    df = df.rename(columns=rename_map)
    df["wiki_ticker"] = df["wiki_ticker"].astype(str)
    df["ticker"] = df["wiki_ticker"].map(_normalize_ticker)
    df["ticker"] = df["ticker"].map(lambda t: TICKER_OVERRIDES.get(t, t))
    df["name"] = df["name"].astype(str).map(_normalize_company_name)
    df["cik"] = df["cik"].astype(str).str.zfill(10)
    df = df[["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"]]
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    return df


def get_sp500_constituents(force_refresh: bool = False) -> pd.DataFrame:
    """Return the S&P 500 constituents DataFrame, hitting the disk cache when fresh."""
    cache = config.UNIVERSE_CACHE
    if not force_refresh and cache.exists():
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        if age_days < config.UNIVERSE_CACHE_MAX_AGE_DAYS:
            logger.info("Universe cache hit (age=%.1f days)", age_days)
            return pd.read_parquet(cache)

    logger.info("Fetching S&P 500 constituents from Wikipedia")
    html = _fetch_wikipedia_html()
    df = parse_sp500_html(html)

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    logger.info("Cached %d constituents to %s", len(df), cache)
    return df


# ---------------------------------------------------------------------------
# Phase 8 pilot — S&P 400 (mid-cap) constituents
# ---------------------------------------------------------------------------

def _parse_sp400_html(html: str) -> pd.DataFrame:
    """Parse the S&P 400 Wikipedia page into a DataFrame.

    The S&P 400 page uses the same wikitable structure as the S&P 500 page.
    Column names differ slightly ("Ticker" vs "Symbol"); we normalise both.
    The CIK column may be absent on this page — we tolerate that gracefully
    and leave it None (resolved at scoring time via ``Company(ticker).cik``).

    ADRs are NOT in the S&P 400 (domestic mid-cap index). No 20-F/6-K
    filtering is needed here.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", {"class": "wikitable"})
    if not tables:
        raise ValueError("Could not find any wikitable on the S&P 400 Wikipedia page.")

    df: pd.DataFrame | None = None
    for table in tables:
        try:
            candidate = pd.read_html(StringIO(str(table)))[0]
        except Exception:  # noqa: BLE001
            continue
        cols_lower = {str(c).lower().strip(): c for c in candidate.columns}
        if "symbol" in cols_lower or "ticker" in cols_lower:
            df = candidate
            break

    if df is None:
        raise ValueError(
            "Could not find S&P 400 constituents table on Wikipedia page. "
            "Expected a wikitable with a 'Symbol' or 'Ticker' column."
        )

    # Normalise column names — the S&P 400 page uses "Ticker" (vs "Symbol"
    # on the S&P 500 page), so we map both.
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = str(col).lower().strip()
        if cl in ("symbol", "ticker"):
            col_map[col] = "wiki_ticker"
        elif cl in ("security", "company"):
            col_map[col] = "name"
        elif "sector" in cl and "sub" not in cl:
            col_map[col] = "sector"
        elif "sub" in cl and "industry" in cl:
            col_map[col] = "sub_industry"
        elif cl == "cik":
            col_map[col] = "cik"

    df = df.rename(columns=col_map)

    if "wiki_ticker" not in df.columns:
        raise ValueError(
            f"S&P 400 Wikipedia table has no ticker column. Columns: {list(df.columns)}"
        )

    df["wiki_ticker"] = df["wiki_ticker"].astype(str)
    df["ticker"] = df["wiki_ticker"].map(_normalize_ticker)

    if "name" not in df.columns:
        df["name"] = df["ticker"]
    else:
        df["name"] = df["name"].astype(str)

    if "sector" not in df.columns:
        df["sector"] = "Unknown"
    else:
        df["sector"] = df["sector"].astype(str).fillna("Unknown")

    if "sub_industry" not in df.columns:
        df["sub_industry"] = None

    # CIK: zero-pad to 10 digits when present; otherwise leave None.
    # Scoring time resolves missing CIKs via Company(ticker).cik.
    if "cik" not in df.columns:
        df["cik"] = None
    else:
        def _safe_cik(v: Any) -> str | None:  # noqa: ANN001
            if pd.isna(v) or str(v).strip() in ("", "nan"):
                return None
            try:
                return str(int(float(str(v)))).zfill(10)
            except (ValueError, TypeError):
                return None
        df["cik"] = df["cik"].map(_safe_cik)

    df = df[["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"]]
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    return df


def fetch_sp400_constituents(force_refresh: bool = False) -> pd.DataFrame:
    """Return the S&P 400 mid-cap constituents, hitting the disk cache when fresh.

    Mirrors the ``get_sp500_constituents`` caching pattern.  Cache file:
    ``compute/cache/universe_sp400-v1.parquet`` (gitignored).

    The returned DataFrame has the same columns as ``get_sp500_constituents``
    (ticker, name, sector, sub_industry, cik, wiki_ticker).  The ``cik``
    column may be None for tickers whose CIK was not on the Wikipedia page;
    ``get_sp900_constituents`` resolves those via edgartools before returning.
    """
    cache = config.SP400_UNIVERSE_CACHE
    if not force_refresh and cache.exists():
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        if age_days < config.SP400_CACHE_MAX_AGE_DAYS:
            logger.info("SP400 universe cache hit (age=%.1f days)", age_days)
            return pd.read_parquet(cache)

    logger.info("Fetching S&P 400 constituents from Wikipedia (%s)", config.WIKIPEDIA_SP400_URL)
    html = _fetch_wikipedia_html(config.WIKIPEDIA_SP400_URL)
    df = _parse_sp400_html(html)

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    logger.info("Cached %d S&P 400 constituents to %s", len(df), cache)
    return df


def _resolve_cik_for_midcap(ticker: str) -> str | None:
    """Resolve CIK for a mid-cap ticker via edgartools Company(ticker).

    Returns the 10-digit zero-padded CIK string, or None on failure.
    This is a best-effort lookup — graceful degradation: a ticker with no
    CIK will be logged and skipped in the probe loop, not crash the run.

    GOTCHA (docs/GOTCHAS.md): ``Company("")`` resolves to an arbitrary
    company — always pass the actual ticker string.

    Rate-limit note: NO tenacity retry or inter-call sleep is needed here.
    ``Company(ticker).__init__`` resolves the ticker to a CIK via
    ``find_cik()`` → ``get_company_cik_lookup()``, which is an in-memory
    dict built once from edgartools' BUNDLED ``company_tickers.parquet``
    (shipped with the package, ~10 k rows).  The dict is populated by
    ``_get_company_tickers_raw()`` decorated with ``@lru_cache(maxsize=1)``;
    every subsequent call — including all ~400 calls in the resolution loop
    in ``get_sp900_constituents`` — hits the cache with ZERO per-call HTTP.
    Verified empirically: intercepting httpx.Client.send during 400 back-to-
    back ``Company(ticker).cik`` lookups records 0 network requests.
    The ``co.cik`` attribute is set eagerly in ``__init__`` (``self._cik =
    cik``), so it never triggers the lazy ``data`` property that DOES make
    an HTTP call (``get_entity_submissions``).  Therefore ``midcap_cik_
    resolution_pct`` is trustworthy on the first sp900 run; no burst risk.
    """
    try:
        from edgar import Company as _Company  # noqa: PLC0415
        co = _Company(ticker)
        raw_cik = getattr(co, "cik", None)
        if raw_cik is None:
            return None
        return str(int(str(raw_cik))).zfill(10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[sp900] CIK resolution failed for %s: %s", ticker, exc)
        return None


def get_sp900_constituents(force_refresh: bool = False) -> pd.DataFrame:
    """Return the S&P 900 = S&P 500 ∪ S&P 400 constituents DataFrame.

    Phase 8 pilot — observability-first (PR 1). The returned DataFrame is
    used ONLY for the diagnostic coverage probe; the ranked output stays
    500-only until PR 3.

    Construction:
      1. Fetch SP500 (``get_sp500_constituents``).
      2. Fetch SP400 (``fetch_sp400_constituents``).
      3. Concatenate; add a ``cohort`` column ("sp500" | "sp400").
      4. De-duplicate on ticker: sp500 wins on transient index overlap
         (a ticker in both lists keeps only the sp500 row).
      5. For sp400 rows with a None CIK: attempt CIK resolution via
         ``Company(ticker).cik``. Failures are logged + the CIK stays None
         (the probe counts them under ``midcap_null_rate_pct``).

    Cache: ``compute/cache/universe_sp900-v1.parquet`` (gitignored).
    Re-built whenever either constituent list re-fetches (or force_refresh).
    On the default ``sp500`` path, this function is never called.
    """
    cache = config.SP900_UNIVERSE_CACHE

    # The SP900 cache is only valid if both constituent caches are fresh.
    sp500_cache_age = (
        (time.time() - config.UNIVERSE_CACHE.stat().st_mtime) / 86400
        if config.UNIVERSE_CACHE.exists()
        else float("inf")
    )
    sp400_cache_age = (
        (time.time() - config.SP400_UNIVERSE_CACHE.stat().st_mtime) / 86400
        if config.SP400_UNIVERSE_CACHE.exists()
        else float("inf")
    )
    constituent_caches_fresh = (
        sp500_cache_age < config.UNIVERSE_CACHE_MAX_AGE_DAYS
        and sp400_cache_age < config.SP400_CACHE_MAX_AGE_DAYS
    )

    if not force_refresh and cache.exists() and constituent_caches_fresh:
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        if age_days < config.UNIVERSE_CACHE_MAX_AGE_DAYS:
            logger.info("SP900 universe cache hit (age=%.1f days)", age_days)
            return pd.read_parquet(cache)

    logger.info("Building S&P 900 universe (500 + 400 mid-cap, de-duped)…")
    sp500_df = get_sp500_constituents(force_refresh=force_refresh)
    sp400_df = fetch_sp400_constituents(force_refresh=force_refresh)

    # Tag cohort before concat
    sp500_tagged = sp500_df.copy()
    sp500_tagged["cohort"] = "sp500"

    sp400_tagged = sp400_df.copy()
    sp400_tagged["cohort"] = "sp400"

    combined = pd.concat([sp500_tagged, sp400_tagged], ignore_index=True)

    # De-duplicate: sp500 rows come first, so drop_duplicates(keep="first")
    # keeps the sp500 row when a ticker appears in both lists.
    before = len(combined)
    combined = combined.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)
    n_deduped = before - len(combined)
    if n_deduped > 0:
        logger.info(
            "[sp900] De-duplicated %d tickers present in both SP500 and SP400 (sp500 rows kept)",
            n_deduped,
        )

    # Resolve missing CIKs for sp400 rows
    midcap_mask = combined["cohort"] == "sp400"
    missing_cik_mask = midcap_mask & combined["cik"].isna()
    n_missing = int(missing_cik_mask.sum())
    if n_missing > 0:
        logger.info(
            "[sp900] Resolving CIKs for %d sp400 tickers with null CIK (via edgartools)…",
            n_missing,
        )
        resolved = 0
        for idx in combined[missing_cik_mask].index:
            ticker = str(combined.at[idx, "ticker"])
            cik = _resolve_cik_for_midcap(ticker)
            if cik:
                combined.at[idx, "cik"] = cik
                resolved += 1
            else:
                logger.warning("[sp900] Could not resolve CIK for %s — skipping", ticker)
        logger.info(
            "[sp900] CIK resolution: %d / %d resolved; %d remain None (excluded from EDGAR probe)",
            resolved,
            n_missing,
            n_missing - resolved,
        )

    cache.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(cache, index=False)
    logger.info(
        "SP900 universe: %d total (%d sp500 + %d sp400 after dedup); cached to %s",
        len(combined),
        int((combined["cohort"] == "sp500").sum()),
        int((combined["cohort"] == "sp400").sum()),
        cache,
    )
    return combined
