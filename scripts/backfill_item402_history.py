"""Build ``data/pit_item402_history.parquet`` via SEC EDGAR Full-Text Search.

Queries the EFTS endpoint for all 8-K filings that mention "Item 4.02" between
2016-01-01 and today, paginates the results (100 per page), joins entity_id
(zero-padded CIK) to the live universe to get ticker symbols, optionally
verifies each filing HTML with the existing ``_ITEM_4_02_PATTERN`` regex, and
writes a parquet with columns:

    ticker            str   -- canonical (dot-to-dash, upper)
    cik               str   -- 10-digit zero-padded CIK
    accession_number  str   -- SEC accession number (dashes form)
    filing_date       str   -- ISO "YYYY-MM-DD"

**Run this script once to build the parquet; the backtest wiring reads it.**

    python -m scripts.backfill_item402_history

Options
-------
--start         First date to query (default 2016-01-01).
--end           Last date to query (default today).
--out           Output path (default data/pit_item402_history.parquet).
--no-html-verify
                Skip the HTML confirmation pass (faster but more false
                positives for old filings where "Item 4.02" appears only in
                body text, not a section heading).
--user-agent    EDGAR User-Agent string (overrides EDGAR_USER_AGENT env var).

Expected output
---------------
~150-300 rows covering S&P 500 / historical S&P 500 tickers from 2016.
The parquet is idempotent: re-running merges and de-duplicates on
(cik, accession_number) so partial runs can be resumed safely.

EDGAR rate limit
----------------
EFTS is a public search endpoint; we cap at 10 req/s (same ceiling as
the main EDGAR 10 req/s limit documented in config.py). A 0.11s inter-
request sleep enforces this. The filing HTML verification pass fetches
individual filing documents via direct SEC URLs — same ceiling applies.

License
-------
SEC EDGAR content is US government public domain (17 U.S.C. §105).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUT = _PROJECT_ROOT / "data" / "pit_item402_history.parquet"
_DEFAULT_START = "2016-01-01"

# EFTS Full-Text Search endpoint.  ``&from=N`` paginates in steps of 100.
_EFTS_BASE = (
    "https://efts.sec.gov/LATEST/search-index"
    "?q=%22Item+4.02%22"
    "&forms=8-K"
    "&dateRange=custom"
    "&startdt={start}"
    "&enddt={end}"
    "&from={offset}"
)
_PAGE_SIZE = 100  # EFTS max per page

# Reuse the compiled pattern from eight_k_events — item-number boundary-anchored,
# case-insensitive.  Prevents counting a bare "4.02" appearing in body text.
_ITEM_4_02_PATTERN = re.compile(r"\bItem\s+4\.\s*02\b", re.IGNORECASE)

# EDGAR requires a well-formed User-Agent: "<name> <email>" or similar.
# Defaults to the env var used by the rest of the codebase.
_UA_ENV = "EDGAR_USER_AGENT"
_INTER_REQUEST_SLEEP = 0.11  # s — stays under 10 req/s ceiling


# ---------------------------------------------------------------------------
# EFTS pagination
# ---------------------------------------------------------------------------

def _efts_session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
    return s


def _fetch_efts_page(
    session: requests.Session,
    start: str,
    end: str,
    offset: int,
    *,
    max_retries: int = 3,
) -> dict:
    """Return one page of EFTS results (raw JSON dict)."""
    url = _EFTS_BASE.format(start=start, end=end, offset=offset)
    for attempt in range(max_retries):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            time.sleep(_INTER_REQUEST_SLEEP)
            return r.json()
        except requests.exceptions.HTTPError:
            status = getattr(r, "status_code", None)
            # EFTS returns sporadic 429 (rate limit) AND 5xx (flaky backend —
            # the same query often succeeds on retry). Back off + retry both;
            # only the final attempt re-raises.
            if status == 429 or (status is not None and 500 <= status < 600):
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 2)
                    logger.warning(
                        "EFTS %s — sleeping %ds (attempt %d/%d)",
                        status, wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
                else:
                    raise
            else:
                raise
        except Exception:  # noqa: BLE001
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return {}


def _iter_efts_hits(
    session: requests.Session,
    start: str,
    end: str,
) -> Iterator[dict]:
    """Yield every hit dict from EFTS for the given date range."""
    offset = 0
    total: int | None = None
    while True:
        data = _fetch_efts_page(session, start, end, offset)
        hits = data.get("hits", {})
        if total is None:
            total = hits.get("total", {}).get("value", 0)
            logger.info("EFTS: total=%d hits for %s..%s", total, start, end)
        yield from hits.get("hits") or []
        fetched_this_page = len(hits.get("hits") or [])
        offset += fetched_this_page
        if fetched_this_page < _PAGE_SIZE or offset >= (total or 0):
            break
        logger.debug("EFTS: fetched %d / %d", offset, total)


# ---------------------------------------------------------------------------
# HTML verification (optional)
# ---------------------------------------------------------------------------

def _verify_filing_html(session: requests.Session, accession_number: str, cik: str) -> bool:
    """Return True iff the filing HTML contains ``_ITEM_4_02_PATTERN``.

    Fetches the filing index page, then the first .htm document linked.
    Falls back to True (no rejection) on any fetch / parse error so we
    don't silently drop filings when SEC CDN is slow.
    """
    no_dashes = accession_number.replace("-", "")
    cik_int = str(int(cik))  # strip leading zeros for the path
    # Fetch the plain-text filing document from the known EDGAR path pattern.
    doc_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{no_dashes}/{no_dashes}.txt"
    )
    try:
        r = session.get(doc_url, timeout=20)
        time.sleep(_INTER_REQUEST_SLEEP)
        if not r.ok:
            logger.debug("HTML verify: non-200 for %s — accepting", accession_number)
            return True
        text = r.text[:50_000]  # only need the header / section list
        return bool(_ITEM_4_02_PATTERN.search(text))
    except Exception as e:  # noqa: BLE001
        logger.debug("HTML verify: fetch failed for %s (%s) — accepting", accession_number, e)
        return True  # fail-open


# ---------------------------------------------------------------------------
# Build CIK → ticker map
# ---------------------------------------------------------------------------

def _build_cik_map() -> dict[str, str]:
    """Return a dict mapping zero-padded 10-digit CIK → canonical ticker.

    Built from the live universe (``get_sp500_constituents``).  Includes
    today's ~502 constituents; historically-removed tickers are NOT in this
    map, so their 8-K hits will be dropped from the output (they are NOT
    replayed in the backtest since their CIK resolution is done lazily
    per-rebalance in the backfill script itself).
    """
    try:
        from compute.ingest.universe import get_sp500_constituents
        members = get_sp500_constituents()
        return {str(r.cik).zfill(10): str(r.ticker) for r in members.itertuples(index=False)}
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not load universe CIK map: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build data/pit_item402_history.parquet from EFTS.",
    )
    p.add_argument("--start", default=_DEFAULT_START, help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default=date.today().isoformat(), help="End date (YYYY-MM-DD)")
    p.add_argument("--out", default=str(_DEFAULT_OUT), help="Output parquet path")
    p.add_argument(
        "--no-html-verify",
        action="store_true",
        help="Skip HTML verification pass (faster, more FP)",
    )
    p.add_argument("--user-agent", default=None, help="EDGAR User-Agent string")
    return p.parse_args(argv)


def run(
    start: str,
    end: str,
    out: Path,
    *,
    html_verify: bool = True,
    user_agent: str | None = None,
) -> None:
    """Fetch EFTS results, optionally verify HTML, write parquet.

    Idempotent: merges new rows with any existing parquet and deduplicates
    on (cik, accession_number).
    """
    import pandas as pd

    ua = user_agent or os.environ.get(_UA_ENV)
    if not ua:
        logger.error(
            "EDGAR_USER_AGENT env var not set and --user-agent not provided. "
            "SEC requires a valid User-Agent; aborting."
        )
        sys.exit(1)

    session = _efts_session(ua)
    cik_map = _build_cik_map()
    logger.info("CIK map built: %d tickers", len(cik_map))

    rows: list[dict] = []
    for hit in _iter_efts_hits(session, start, end):
        src = hit.get("_source") or {}
        # EFTS _source carries `ciks` (list of 10-digit zero-padded CIK strings),
        # `adsh` (the accession number, dashed), `items` (the 8-K item codes the
        # filing actually contains), and `file_date`. There is NO `entity_id` or
        # `file_num`-as-accession field — reading those silently drops EVERY hit
        # (verified against a live EFTS response 2026-06-13: 68 hits -> 0 rows).
        ciks = src.get("ciks") or []
        ticker = None
        matched_cik = ""
        for c in ciks:
            c10 = str(c).strip().zfill(10)
            if c10 in cik_map:
                ticker = cik_map[c10]
                matched_cik = c10
                break
        if ticker is None:
            logger.debug("No S&P-500 CIK among %s — skipping", ciks)
            continue

        # Accession: prefer `adsh`; fall back to the `_id` prefix
        # ("<accession>:<filename>").
        accession = str(src.get("adsh") or hit.get("_id", "").split(":")[0]).strip()
        if not accession or len(accession) < 10:
            logger.debug("Skipping %s — unparseable accession '%s'", ticker, accession)
            continue

        filing_date = str(src.get("file_date") or src.get("period_of_report") or "")[:10]
        if not filing_date or len(filing_date) < 10:
            logger.debug("Skipping hit with no filing_date: %s", hit.get("_id"))
            continue

        # Item-4.02 confirmation. EFTS indexes the filing's actual item codes in
        # `items`; this is authoritative and avoids an HTML fetch per hit. The
        # q="Item 4.02" query matches full TEXT, so a hit may merely MENTION 4.02
        # — the items field distinguishes a real Item 4.02 SECTION from a body
        # mention. Fall back to the HTML verifier only when items is absent.
        items = [str(it).strip() for it in (src.get("items") or [])]
        if items and not any(it in ("4.02", "4.2") for it in items):
            logger.debug("%s / %s — items=%s lacks 4.02, skipping", ticker, accession, items)
            continue
        if not items and html_verify and not _verify_filing_html(session, accession, matched_cik):
            logger.debug(
                "HTML verify rejected %s / %s — Item 4.02 not found in text",
                ticker, accession,
            )
            continue

        rows.append(
            {
                "ticker": ticker,
                "cik": matched_cik,
                "accession_number": accession,
                "filing_date": filing_date,
            }
        )
        logger.info("Accepted: %s  %s  %s", ticker, filing_date, accession)

    if not rows:
        logger.warning("No rows collected — parquet will not be written")
        return

    new_df = pd.DataFrame(rows)

    # Idempotent merge: if the parquet already exists, combine and dedup.
    out_path = Path(out)
    if out_path.exists():
        try:
            existing = pd.read_parquet(out_path)
            new_df = pd.concat([existing, new_df], ignore_index=True)
            logger.info("Merged with existing parquet (%d rows)", len(existing))
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not read existing parquet: %s — overwriting", e)

    new_df = new_df.drop_duplicates(subset=["cik", "accession_number"]).reset_index(drop=True)
    new_df = new_df.sort_values(["ticker", "filing_date"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_df.to_parquet(out_path, index=False)
    logger.info(
        "Wrote %d rows to %s",
        len(new_df),
        out_path,
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    args = _parse_args(argv)
    run(
        start=args.start,
        end=args.end,
        out=Path(args.out),
        html_verify=not args.no_html_verify,
        user_agent=args.user_agent,
    )


if __name__ == "__main__":
    main()
