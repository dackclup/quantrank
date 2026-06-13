"""PIT GICS sector reader for the backtest.

Reads ``data/historical_sector.parquet`` (written by
``scripts/backfill_historical_sector.py``) and exposes a single pure
function that returns the GICS sector name for a ticker at a historical
rebalance date.

Graceful degradation
--------------------
When the parquet is absent the function falls back to calling
``get_sp500_constituents()`` (today's Wikipedia sector), and sets
``sector_source = "fallback"``.  This preserves the current backtest
behavior exactly — ``meta.sector_from_today`` remains ``True``.

Parquet schema
--------------
Columns written by ``scripts/backfill_historical_sector.py``:
  ticker              str  -- canonical (dot-to-dash, upper)
  sector              str  -- GICS sector NAME (e.g. "Information Technology")
                             NOTE: NEVER the proprietary 4-tier numeric code
  sub_industry        str  -- GICS sub-industry name (best-effort; may be "")
  rebalance_date      str  -- ISO "YYYY-MM-DD" quarterly rebalance date
  revision_timestamp  str  -- MediaWiki revision timestamp for audit trail
  sector_source       str  -- "wikipedia_pit" or "fallback"

License boundary
----------------
Only GICS sector **names** are stored — the proprietary 4-tier numeric
codes (sector code 10, industry group 1010, industry 101010, sub-industry
10101010) are NEVER stored.  The raw Wikipedia table contains only names;
reverse-mapping names to codes would require the MSCI/S&P GICS taxonomy
(licensed), which QuantRank does not hold.  Sector names are factual
enumerations of classification outcomes (Feist 1991) — the same legal
basis as the Wikipedia membership CSV (``historical_universe.py``).

References
----------
- Rule 18 (observability-before-wiring): ``meta.historical_sector_coverage_pct``
  + ``meta.historical_sector_fallback_count`` are emitted BEFORE the sector
  values drive composite scoring.
- CC BY-SA 4.0 provenance: MediaWiki revision-history API content is
  CC BY-SA 4.0; sector names stored as factual data (Feist 1991 basis).
  See ``THIRD_PARTY_NOTICES.md`` Wikipedia-revision-history entry.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HISTORICAL_SECTOR_PARQUET: Path = _PROJECT_ROOT / "data" / "historical_sector.parquet"

# Module-level cache: (parquet mtime, DataFrame).
_CACHE: tuple[float, object] | None = None


def _load_parquet() -> object | None:
    """Return the parquet as a DataFrame, or None when absent/unreadable."""
    global _CACHE

    if not HISTORICAL_SECTOR_PARQUET.exists():
        logger.debug(
            "historical_sector.parquet not found at %s — "
            "sector PIT disabled (graceful degradation; using today's sectors)",
            HISTORICAL_SECTOR_PARQUET,
        )
        return None

    try:
        mtime = HISTORICAL_SECTOR_PARQUET.stat().st_mtime
    except OSError as exc:
        logger.warning("historical_sector parquet stat failed: %s — using today's sectors", exc)
        return None

    if _CACHE is not None and _CACHE[0] == mtime:
        return _CACHE[1]  # type: ignore[return-value]

    try:
        import pandas as pd
        df = pd.read_parquet(HISTORICAL_SECTOR_PARQUET)
        _CACHE = (mtime, df)
        logger.info(
            "historical_sector PIT parquet loaded: %d rows from %s",
            len(df),
            HISTORICAL_SECTOR_PARQUET,
        )
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "historical_sector parquet read failed: %s — using today's sectors", exc
        )
        return None


def sector_at(ticker: str, as_of_date: date) -> str:
    """Return the GICS sector name for ``ticker`` as of ``as_of_date``.

    Looks up the closest rebalance date on or before ``as_of_date`` in the
    historical-sector parquet.  Falls back to today's Wikipedia sector when:
    - the parquet is absent,
    - the ticker/date combination has no row, or
    - any read error occurs.

    Parameters
    ----------
    ticker:
        Canonical equity ticker (dot-to-dash, uppercase).
    as_of_date:
        Point-in-time date (typically a backtest rebalance date ``T``).

    Returns
    -------
    str
        GICS sector name (e.g. ``"Information Technology"``).
        Returns ``"Unknown"`` only when both the parquet lookup AND the
        today's-sector fallback fail — which should be impossible for any
        in-universe ticker.
    """
    df = _load_parquet()

    if df is not None:
        try:
            as_of_iso = as_of_date.isoformat()
            mask = (df["ticker"] == ticker) & (df["rebalance_date"] <= as_of_iso)
            subset = df.loc[mask]
            if not subset.empty:
                # Closest prior rebalance = latest rebalance_date <= as_of_date.
                row = subset.loc[subset["rebalance_date"].idxmax()]
                return str(row["sector"])
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sector_at(%s, %s) parquet lookup failed: %s — falling back to today's sector",
                ticker,
                as_of_date,
                exc,
            )

    # Fallback: today's Wikipedia sector (current behavior).
    try:
        from compute.ingest.universe import get_sp500_constituents
        members = get_sp500_constituents()
        row = members.loc[members["ticker"] == ticker]
        if not row.empty:
            sector = str(row.iloc[0]["sector"])
            logger.debug(
                "sector_at fallback: %s @ %s -> %s (today's sector)",
                ticker,
                as_of_date,
                sector,
            )
            return sector
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "sector_at(%s, %s) today's-sector fallback failed: %s",
            ticker,
            as_of_date,
            exc,
        )

    return "Unknown"


def historical_sector_parquet_stats() -> dict:
    """Return observability counters for Rule 18 / ``meta`` fields.

    Returns a dict with:
    - ``parquet_present``: bool
    - ``row_count``: int
    - ``rebalance_dates``: list[str] — unique ISO dates covered

    All values are 0/empty/False when the parquet is absent (graceful).
    """
    df = _load_parquet()
    if df is None:
        return {"parquet_present": False, "row_count": 0, "rebalance_dates": []}
    try:
        return {
            "parquet_present": True,
            "row_count": len(df),
            "rebalance_dates": sorted(df["rebalance_date"].unique().tolist()),
        }
    except Exception:  # noqa: BLE001
        return {"parquet_present": True, "row_count": 0, "rebalance_dates": []}


__all__ = [
    "HISTORICAL_SECTOR_PARQUET",
    "historical_sector_parquet_stats",
    "sector_at",
]
