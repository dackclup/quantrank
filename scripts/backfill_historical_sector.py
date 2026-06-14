"""Build ``data/historical_sector.parquet`` via the MediaWiki revision API.

For each quarterly rebalance date in the backtest window, fetches the
Wikipedia "List of S&P 500 companies" revision that was the most-recent
edit on or before that date, parses the GICS Sector column via the same
BeautifulSoup/lxml path used in ``compute/ingest/universe.py``, and writes
a parquet with one row per (ticker, rebalance_date):

    ticker              str  -- canonical (dot-to-dash, upper)
    sector              str  -- GICS sector NAME only (no numeric codes)
    sub_industry        str  -- GICS sub-industry name (best-effort)
    rebalance_date      str  -- ISO "YYYY-MM-DD"
    revision_timestamp  str  -- MediaWiki revid/timestamp for audit trail
    sector_source       str  -- "wikipedia_pit" or "fallback"

**License boundary**: only GICS sector and sub-industry NAMES are stored —
never the proprietary 4-tier numeric codes.  Sector names are factual
enumerations (Feist 1991 — same basis as the membership CSV).  CC BY-SA 4.0
provenance documented in ``THIRD_PARTY_NOTICES.md``.

**Rate limit**: 1 req/s to Wikipedia (Wikimedia API etiquette).

Usage
-----
    python -m scripts.backfill_historical_sector

Options
-------
--start     First rebalance date (default 2016-06-01, BACKTEST_CANONICAL_START).
--end       Last rebalance date (default today).
--out       Output parquet path (default data/historical_sector.parquet).
--lag-days  Quarter-end lag (default 45, same as the backfill).
--user-agent
            User-Agent for the MediaWiki API (default "QuantRank/1.0 <dack30@gmail.com>").

Idempotent: re-running merges with any existing parquet and deduplicates on
(ticker, rebalance_date).

Pre-2017 header variants
------------------------
Wikipedia has used at least two column name variants:
  - "GICS Sector" (current; post-~2016)
  - "Sector" (older revisions; pre-~2016)
  - "GICS Sector\n" / whitespace-stripped variants

Pre-2018, "Telecommunication Services" appears as the sector for what is now
"Communication Services" — stored as-is (factual record of that time).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUT = _PROJECT_ROOT / "data" / "historical_sector.parquet"
_DEFAULT_START = date(2016, 6, 1)  # BACKTEST_CANONICAL_START
_FILING_LAG_DAYS = 45  # matches compute.portfolio.backtest.DEFAULT_FILING_LAG_DAYS

# Wikipedia MediaWiki API endpoint
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_TITLE = "List of S%26P 500 companies"

# Rate limit: 1 req/s (Wikimedia API etiquette)
_INTER_REQUEST_SLEEP = 1.0

# Recognized GICS Sector column name variants across Wikipedia revision history.
_SECTOR_COLUMN_CANDIDATES = [
    "GICS Sector",
    "Sector",
    "GICS sector",
    "GICSSector",
]

_TICKER_OVERRIDES: dict[str, str] = {
    "FISV": "FI",
}


# ---------------------------------------------------------------------------
# MediaWiki API fetch
# ---------------------------------------------------------------------------

def _wiki_session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s


def _fetch_revision_before(
    session: requests.Session,
    as_of_date: date,
) -> tuple[str, str] | None:
    """Return (wikitext_content, revision_timestamp) for the revision
    that was the most-recent edit on or before ``as_of_date``.

    Uses ``rvdir=older`` + ``rvstart=<date+1>T00:00:00Z`` so the first
    result is the last revision prior to the day boundary.
    Returns None on any error.
    """
    # rvstart is exclusive-upper-bound when rvdir=older, so we pass T+1.
    rvstart = (as_of_date + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": "List of S&P 500 companies",
        "rvprop": "ids|timestamp|content",
        "rvstart": rvstart,
        "rvlimit": "1",
        "rvdir": "older",
        "format": "json",
        "formatversion": "2",
    }
    try:
        r = session.get(_WIKI_API, params=params, timeout=30)
        r.raise_for_status()
        time.sleep(_INTER_REQUEST_SLEEP)
        data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("MediaWiki API failed for %s: %s", as_of_date, e)
        return None

    try:
        pages = data["query"]["pages"]
        if not pages:
            return None
        page = pages[0]
        revisions = page.get("revisions")
        if not revisions:
            logger.warning("No revision found before %s", as_of_date)
            return None
        rev = revisions[0]
        content = rev.get("content") or rev.get("*") or ""
        timestamp = rev.get("timestamp", "")
        return content, timestamp
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("Revision parse failed for %s: %s", as_of_date, e)
        return None


# ---------------------------------------------------------------------------
# Wikitext / HTML table parsing
# ---------------------------------------------------------------------------

def _wikitext_to_html(wikitext: str, session: requests.Session) -> str | None:
    """Parse wikitext to HTML via the MediaWiki parse API (action=parse).

    This is the same content the reader sees; the BeautifulSoup + lxml path
    in universe.py operates on rendered HTML, so we use the same path here.
    """
    params = {
        "action": "parse",
        "text": wikitext,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
    }
    try:
        r = session.post(_WIKI_API, data=params, timeout=60)
        r.raise_for_status()
        time.sleep(_INTER_REQUEST_SLEEP)
        return r.json()["parse"]["text"]
    except Exception as e:  # noqa: BLE001
        logger.warning("MediaWiki parse API failed: %s", e)
        return None


def _parse_sector_table(html: str) -> object | None:
    """Extract ticker + sector + sub_industry from the Wikipedia HTML table.

    Reuses the BeautifulSoup/lxml path from ``compute.ingest.universe``.
    Handles column name variants: "GICS Sector" / "Sector" / stripped.

    Returns a DataFrame with columns [ticker, sector, sub_industry], or
    None if the table cannot be found or parsed.
    """
    import pandas as pd

    from compute.ingest.universe import TICKER_OVERRIDES, _normalize_ticker

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"class": "wikitable"})
    if table is None:
        logger.warning("No wikitable found in parsed HTML")
        return None

    try:
        df = pd.read_html(StringIO(str(table)))[0]
    except Exception as e:  # noqa: BLE001
        logger.warning("pd.read_html failed: %s", e)
        return None

    # Strip whitespace from all column names
    df.columns = [str(c).strip() for c in df.columns]

    # Resolve Symbol column
    if "Symbol" in df.columns:
        df["wiki_ticker"] = df["Symbol"].astype(str)
    elif "Ticker" in df.columns:
        df["wiki_ticker"] = df["Ticker"].astype(str)
    elif "Ticker symbol" in df.columns:
        df["wiki_ticker"] = df["Ticker symbol"].astype(str)
    else:
        logger.warning("No ticker column found; available: %s", list(df.columns))
        return None

    df["ticker"] = df["wiki_ticker"].map(_normalize_ticker)
    df["ticker"] = df["ticker"].map(lambda t: TICKER_OVERRIDES.get(t, t))

    # Resolve GICS Sector column — try known variants
    sector_col: str | None = None
    for cand in _SECTOR_COLUMN_CANDIDATES:
        if cand in df.columns:
            sector_col = cand
            break
    if sector_col is None:
        # Last-resort: case-insensitive search
        for col in df.columns:
            if "sector" in col.lower():
                sector_col = col
                break
    if sector_col is None:
        logger.warning("No sector column found; available: %s", list(df.columns))
        return None

    df["sector"] = df[sector_col].astype(str).str.strip()

    # Resolve Sub-Industry column (best-effort; may not exist in old revisions)
    sub_col: str | None = None
    for cand in ("GICS Sub-Industry", "Sub-Industry", "GICS Sub Industry"):
        if cand in df.columns:
            sub_col = cand
            break
    if sub_col:
        df["sub_industry"] = df[sub_col].astype(str).str.strip()
    else:
        df["sub_industry"] = ""

    df = df[["ticker", "sector", "sub_industry"]].drop_duplicates("ticker").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Rebalance date generation (mirrors backfill_portfolio_pit.py logic)
# ---------------------------------------------------------------------------

def _rebalance_dates(start: date, end: date, lag_days: int = _FILING_LAG_DAYS) -> list[date]:
    """Generate quarterly rebalance dates (quarter-end + lag_days).

    Mirrors ``compute.portfolio.backtest.quarterly_rebalance_dates``
    without importing it (script layering — scripts import compute, not
    the reverse).
    """
    out: list[date] = []
    year = start.year
    while year <= end.year:
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qend = date(year, m, d)
            asof = qend + timedelta(days=lag_days)
            if start <= asof <= end:
                out.append(asof)
        year += 1
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build data/historical_sector.parquet via MediaWiki revision API.",
    )
    p.add_argument(
        "--start",
        default=_DEFAULT_START.isoformat(),
        help="First rebalance date (default BACKTEST_CANONICAL_START 2016-06-01)",
    )
    p.add_argument("--end", default=date.today().isoformat(), help="Last rebalance date")
    p.add_argument("--out", default=str(_DEFAULT_OUT), help="Output parquet path")
    p.add_argument(
        "--lag-days",
        type=int,
        default=_FILING_LAG_DAYS,
        help="Quarter-end lag in days (default 45)",
    )
    p.add_argument(
        "--user-agent",
        default="QuantRank/1.0 (dack30@gmail.com; historical sector backfill)",
        help="User-Agent for the MediaWiki API",
    )
    return p.parse_args(argv)


def run(
    start: date,
    end: date,
    out: Path,
    *,
    lag_days: int = _FILING_LAG_DAYS,
    user_agent: str = "QuantRank/1.0 (dack30@gmail.com; historical sector backfill)",
) -> None:
    """Fetch per-rebalance sector snapshots and write parquet.

    Idempotent: merges new rows with existing parquet and deduplicates on
    (ticker, rebalance_date).
    """
    import pandas as pd

    session = _wiki_session(user_agent)
    dates = _rebalance_dates(start, end, lag_days)
    logger.info(
        "Historical sector backfill: %d rebalance dates (%s … %s)",
        len(dates),
        dates[0].isoformat() if dates else "none",
        dates[-1].isoformat() if dates else "none",
    )

    rows: list[dict] = []

    for T in dates:
        logger.info("Fetching revision before %s …", T.isoformat())
        result = _fetch_revision_before(session, T)
        if result is None:
            logger.warning("Could not fetch revision for %s — skipping", T.isoformat())
            continue

        wikitext, revision_timestamp = result
        logger.debug("Revision timestamp: %s (length %d chars)", revision_timestamp, len(wikitext))

        html = _wikitext_to_html(wikitext, session)
        if html is None:
            logger.warning("Could not parse wikitext for %s — skipping", T.isoformat())
            continue

        df = _parse_sector_table(html)
        if df is None or df.empty:
            logger.warning("Could not extract sector table for %s — skipping", T.isoformat())
            continue

        logger.info(
            "Rebalance %s: %d tickers parsed (revision %s)",
            T.isoformat(),
            len(df),
            revision_timestamp,
        )

        for row in df.itertuples(index=False):
            rows.append(
                {
                    "ticker": str(row.ticker),
                    "sector": str(row.sector),
                    "sub_industry": str(row.sub_industry),
                    "rebalance_date": T.isoformat(),
                    "revision_timestamp": revision_timestamp,
                    "sector_source": "wikipedia_pit",
                }
            )

    if not rows:
        logger.warning("No rows collected — parquet will not be written")
        return

    new_df = pd.DataFrame(rows)

    # Idempotent merge
    out_path = Path(out)
    if out_path.exists():
        try:
            existing = pd.read_parquet(out_path)
            new_df = pd.concat([existing, new_df], ignore_index=True)
            logger.info("Merged with existing parquet (%d rows)", len(existing))
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not read existing parquet: %s — overwriting", e)

    new_df = (
        new_df
        .drop_duplicates(subset=["ticker", "rebalance_date"])
        .sort_values(["rebalance_date", "ticker"])
        .reset_index(drop=True)
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_df.to_parquet(out_path, index=False)
    logger.info(
        "Wrote %d rows (%d rebalance dates) to %s",
        len(new_df),
        new_df["rebalance_date"].nunique(),
        out_path,
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    args = _parse_args(argv)
    run(
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        out=Path(args.out),
        lag_days=args.lag_days,
        user_agent=args.user_agent,
    )


if __name__ == "__main__":
    main()
