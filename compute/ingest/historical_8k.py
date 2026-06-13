"""PIT Item 4.02 filing history reader for the backtest veto replay.

Reads ``data/pit_item402_history.parquet`` (written by
``scripts/backfill_item402_history.py``) and exposes a single pure
function that the backfill's veto-replay path can pass as the ``filings``
override to ``check_non_reliance``.

Graceful degradation
--------------------
When the parquet is absent the function returns ``[]``, which causes
``check_non_reliance(filings=[])`` to fire no veto — backtest output is
byte-identical to the current behavior. No exception is raised; a
DEBUG-level log is emitted once per process.

Parquet schema
--------------
Columns written by ``scripts/backfill_item402_history.py``:
  ticker            str   -- canonical (dot-to-dash, upper)
  cik               str   -- 10-digit zero-padded CIK
  accession_number  str   -- SEC accession number (dashes form)
  filing_date       str   -- ISO "YYYY-MM-DD"

The function returns a list of dicts in the shape that
``compute.scoring.eight_k_events._check_item`` already expects for the
``filings`` argument:

  [{"filing_date": "YYYY-MM-DD",
    "filing_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&...",
    "items": ["Item 4.02"],
    "item_text_excerpts": {}}]

``items`` always contains ``"Item 4.02"`` so the ``_ITEM_4_02_PATTERN``
inside ``_check_item`` matches without re-fetching the filing HTML.

References
----------
- SEC EDGAR Full-Text Search (EFTS):
  https://efts.sec.gov/LATEST/search-index (public API, SEC public domain)
- Rule 18 (observability-before-wiring): the observable parquet presence
  flag is emitted in ``meta.item402_pit_rows`` on the backfill artifact
  before the veto replay logic reads a single row.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical path — relative to project root so the module can be imported
# from any CWD. Resolved once at import time.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PIT_ITEM402_PARQUET: Path = _PROJECT_ROOT / "data" / "pit_item402_history.parquet"

# Module-level cache: (parquet mtime, DataFrame). Avoids re-reading the
# parquet on every call within a single process run.
_CACHE: tuple[float, object] | None = None  # (mtime, pd.DataFrame)


def _load_parquet() -> object | None:
    """Return the parquet as a DataFrame, or None when absent/unreadable."""
    global _CACHE

    if not PIT_ITEM402_PARQUET.exists():
        logger.debug(
            "pit_item402_history.parquet not found at %s — "
            "item402 PIT replay disabled (graceful degradation)",
            PIT_ITEM402_PARQUET,
        )
        return None

    try:
        mtime = PIT_ITEM402_PARQUET.stat().st_mtime
    except OSError as exc:
        logger.warning("item402 parquet stat failed: %s — skipping PIT replay", exc)
        return None

    if _CACHE is not None and _CACHE[0] == mtime:
        return _CACHE[1]  # type: ignore[return-value]

    try:
        import pandas as pd
        df = pd.read_parquet(PIT_ITEM402_PARQUET)
        _CACHE = (mtime, df)
        logger.info(
            "item402 PIT parquet loaded: %d rows from %s",
            len(df),
            PIT_ITEM402_PARQUET,
        )
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning("item402 parquet read failed: %s — skipping PIT replay", exc)
        return None


def _accession_to_url(accession_number: str) -> str:
    """Build a best-effort SEC filing URL from a dashes-form accession number.

    Format: ``https://www.sec.gov/Archives/edgar/full-index/<YYYY>/<QQ>/
    company.idx`` is the canonical index, but the human-facing permalink is
    ``https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&
    filenum=<accession_number>&type=8-K``. We use the simpler direct-link:
    ``https://www.sec.gov/Archives/edgar/<accession_no_dashes>/``.

    E.g. ``0001234567-24-000001`` →
    ``https://www.sec.gov/Archives/edgar/data/1234567/0001234567-24-000001-index.htm``
    (rough; the exact path varies by CIK). Fall back to the EFTS search link
    when the CIK cannot be extracted.
    """
    # Accession numbers are always ``XXXXXXXXXX-YY-ZZZZZZ`` (10+2+6 digits).
    no_dashes = accession_number.replace("-", "")
    cik_segment = no_dashes[:10].lstrip("0") or "0"
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_segment}/"
        f"{no_dashes}/{accession_number}-index.htm"
    )


def item402_filings_for(
    ticker: str,
    before_date: date,
) -> list[dict]:
    """Return Item 4.02 filings for ``ticker`` filed on or before ``before_date``.

    Parameters
    ----------
    ticker:
        Canonical equity ticker (dot-to-dash, uppercase, e.g. ``"BRK-B"``).
    before_date:
        Point-in-time cutoff — only filings with ``filing_date <= before_date``
        are returned. This is the backtest rebalance date ``T``.

    Returns
    -------
    list[dict]
        A list of dicts in the shape ``check_non_reliance``'s ``filings``
        parameter expects:

        .. code-block:: python

            [
                {
                    "filing_date": "YYYY-MM-DD",
                    "filing_url": "https://...",
                    "items": ["Item 4.02"],
                    "item_text_excerpts": {},
                }
            ]

        Returns ``[]`` when:
        - The parquet is absent (graceful degradation).
        - The ticker has no Item 4.02 filings before ``before_date``.

    Notes
    -----
    The returned list is ordered ascending by ``filing_date``; the caller
    (``_check_item``) selects the most-recent match within the lookback
    window independently of this ordering.
    """
    df = _load_parquet()
    if df is None:
        return []

    try:
        before_iso = before_date.isoformat()
        mask = (df["ticker"] == ticker) & (df["filing_date"] <= before_iso)
        subset = df.loc[mask].sort_values("filing_date")
        result: list[dict] = []
        for row in subset.itertuples(index=False):
            fd = str(row.filing_date)[:10]
            accession = str(row.accession_number)
            result.append(
                {
                    "filing_date": fd,
                    "filing_url": _accession_to_url(accession),
                    "items": ["Item 4.02"],
                    "item_text_excerpts": {},
                }
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "item402_filings_for(%s, %s) failed: %s — returning []",
            ticker,
            before_date,
            exc,
        )
        return []


def item402_parquet_row_count() -> int:
    """Return the number of rows in the parquet, or 0 when absent.

    Used by ``scripts/backfill_portfolio_pit.py`` to populate
    ``meta.item402_pit_rows`` (Rule 18 observability).
    """
    df = _load_parquet()
    if df is None:
        return 0
    try:
        return len(df)
    except Exception:  # noqa: BLE001
        return 0


__all__ = [
    "PIT_ITEM402_PARQUET",
    "item402_filings_for",
    "item402_parquet_row_count",
]
