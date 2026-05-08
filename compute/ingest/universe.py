"""S&P 500 constituents from Wikipedia.

Cached to ``compute/cache/universe.parquet`` (gitignored). Re-fetched after
``UNIVERSE_CACHE_MAX_AGE_DAYS`` days unless ``force_refresh=True``.
"""

from __future__ import annotations

import logging
import time
from io import StringIO

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
