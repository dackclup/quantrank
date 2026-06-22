"""SEC filing pointer index for the research warehouse (Slice 1).

Enumerates a ticker's recent SEC filings and returns one row-dict per filing.
This is WRITE-ONLY observability foundation work (Rule 18): the static site
never reads ``data/warehouse/`` and this module has no read path.

Scope
-----
- ``DEFAULT_FORM_TYPES`` defines which forms are fetched by default.  The set
  is intentionally narrow — {10-K, 10-Q, 8-K} — and easy to widen later.
- Each row contains: ticker · cik · accession · form_type · filing_date ·
  period_of_report · primary_doc_url · edgar_url · row_provenance · fetched_utc.
- The entire function degrades gracefully on any EDGAR error: ``[]`` is
  returned, never an exception.

EDGAR identity
--------------
Relies on the project's lazy ``_ensure_edgar_identity()`` pattern from
``compute.ingest.filing_text`` (non-fatal variant).  The EDGAR User-Agent
must be set via ``EDGAR_USER_AGENT`` env-var; without it every call returns
``[]`` with a warning log (same as the Tier-2 non-fatal paths).

Rate-limiting
-------------
The caller (``scripts/backfill_filing_index.py``) parallelises across
``config.EDGAR_MAX_WORKERS`` (8 workers, ~1 req/s sustained — well under
the 10 req/s EDGAR ceiling).  This module does NOT start its own pool.

Empty-CIK gotcha
----------------
``Company("")`` resolves to an arbitrary company without raising.  Always
resolve a real CIK via ``Company(ticker).cik`` before any history/filings
fetch (per CLAUDE.md §Gotchas "edgartools `Company("")` resolves...").
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Default set of SEC form types to enumerate.  Add "DEF 14A", "S-3", etc.
# here or pass ``form_types=None`` to the fetch function to get all forms.
DEFAULT_FORM_TYPES: frozenset[str] = frozenset({"10-K", "10-Q", "8-K"})

# Row column names (stable, sorted) so downstream consumers can rely on
# column order without reading the Parquet schema.
FILING_INDEX_COLUMNS: tuple[str, ...] = (
    "accession",
    "cik",
    "edgar_url",
    "fetched_utc",
    "filing_date",
    "form_type",
    "period_of_report",
    "primary_doc_url",
    "row_provenance",
    "ticker",
)

# How many filings to request per form type.  For 10-K/10-Q this is
# effectively "all recent filings"; for 8-K the limit avoids pulling
# thousands of trivial 8-Ks for very active filers.
_FILINGS_LIMIT_PER_FORM: int = 50

# Module-level identity-set flag (mirrors filing_text.py pattern).
_IDENTITY_SET = False


# ---------------------------------------------------------------------------
# EDGAR identity helpers
# ---------------------------------------------------------------------------

def _ensure_edgar_identity() -> bool:
    """Initialize the EDGAR User-Agent if not already done.

    Non-fatal variant — returns False when the env-var is absent and logs a
    warning.  Mirrors ``compute.ingest.filing_text._ensure_edgar_identity``.
    """
    global _IDENTITY_SET
    if _IDENTITY_SET:
        return True
    ua = os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        logger.warning(
            "EDGAR_USER_AGENT not set — filing-index fetch will skip all "
            "tickers.  Set the env var to enable filing index enumeration."
        )
        return False
    try:
        from edgar import set_identity
        set_identity(ua)
    except Exception as exc:  # noqa: BLE001
        logger.warning("set_identity failed: %s", exc)
        return False
    _IDENTITY_SET = True
    return True


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _accession_to_edgar_url(accession: str) -> str:
    """Return the SEC Archives index URL for a dashes-form accession number.

    Mirrors ``compute.ingest.historical_8k._accession_to_url``:
        ``0001234567-24-000001`` →
        ``https://www.sec.gov/Archives/edgar/data/1234567/
          000123456724000001/0001234567-24-000001-index.htm``
    """
    no_dashes = accession.replace("-", "")
    cik_segment = no_dashes[:10].lstrip("0") or "0"
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_segment}/"
        f"{no_dashes}/{accession}-index.htm"
    )


def _build_primary_doc_url(accession: str, primary_doc: str | None) -> str | None:
    """Construct the absolute URL for the primary document of a filing.

    When edgartools provides the primary document filename we build the
    direct URL; otherwise return None and let the caller fall back to
    the index URL.
    """
    if not primary_doc:
        return None
    no_dashes = accession.replace("-", "")
    cik_segment = no_dashes[:10].lstrip("0") or "0"
    safe_doc = primary_doc.lstrip("/")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_segment}/"
        f"{no_dashes}/{safe_doc}"
    )


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

def _resolve_cik(ticker: str, hint_cik: str | None) -> str | None:
    """Return a numeric CIK string for ticker, or None on failure.

    Prefers the caller-supplied ``hint_cik`` to avoid an extra round-trip.
    Falls back to ``Company(ticker).cik`` when the hint is absent or blank.
    Guards against the empty-CIK gotcha by rejecting blank strings.
    """
    if hint_cik and hint_cik.strip():
        return hint_cik.strip()
    try:
        from edgar import Company
        cik = str(Company(ticker).cik or "").strip()
        return cik if cik else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("CIK resolution failed for %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Core fetch: one ticker → list of row-dicts
# ---------------------------------------------------------------------------

def fetch_filing_index_rows(
    ticker: str,
    *,
    cik: str | None = None,
    form_types: frozenset[str] | None = DEFAULT_FORM_TYPES,
    row_provenance: str = "live",
) -> list[dict[str, Any]]:
    """Enumerate recent SEC filings for ``ticker`` and return one row per filing.

    Parameters
    ----------
    ticker:
        Stock ticker symbol (upper-case recommended; edgartools is
        case-insensitive for ``Company`` construction).
    cik:
        Optional pre-resolved CIK string.  When supplied and non-blank,
        avoids the extra ``Company(ticker).cik`` resolution round-trip.
        Passing a blank string is the same as ``None`` (triggers resolution).
    form_types:
        Set of SEC form type strings to enumerate.  Defaults to
        ``DEFAULT_FORM_TYPES = {"10-K", "10-Q", "8-K"}``.  Pass ``None`` to
        enumerate ALL forms (may produce a very large result for active
        filers).
    row_provenance:
        Provenance sentinel written to every row.  ``"live"`` for real-time
        enumeration; ``"pit_replay"`` for historical backfill runs.
        Defaults to ``"live"``.

    Returns
    -------
    list[dict]
        One dict per filing.  Keys: ``FILING_INDEX_COLUMNS``.  Returns ``[]``
        on any EDGAR error, missing User-Agent, or empty result — never raises.

    Graceful degradation
    --------------------
    Every EDGAR call is wrapped in a broad ``except Exception`` (per the
    ``portable-graceful-degradation-try-except`` skill).  A warning is logged
    on failure; an empty list is returned.
    """
    if not _ensure_edgar_identity():
        return []

    resolved_cik = _resolve_cik(ticker, cik)
    if resolved_cik is None:
        logger.warning("filing_index: could not resolve CIK for %s — skipping", ticker)
        return []

    try:
        from edgar import Company
    except ImportError as exc:
        logger.warning("edgartools not importable: %s — returning []", exc)
        return []

    fetched_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict[str, Any]] = []

    # Determine which forms to enumerate.
    forms_to_fetch: list[str | None]
    if form_types is None:
        # None means "all forms" — fetch without a form filter.
        forms_to_fetch = [None]
    else:
        forms_to_fetch = list(form_types)

    for form in forms_to_fetch:
        try:
            company = Company(resolved_cik)
            if form is not None:
                filings_obj = company.get_filings(form=form)
            else:
                filings_obj = company.get_filings()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "filing_index: get_filings(%r) failed for %s/%s: %s",
                form, ticker, resolved_cik, exc,
            )
            continue

        if filings_obj is None:
            continue

        # Pull a limited head() to avoid giant in-memory loads for active filers.
        try:
            head = filings_obj.head(_FILINGS_LIMIT_PER_FORM)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "filing_index: filings.head() failed for %s form=%r: %s",
                ticker, form, exc,
            )
            continue

        if head is None:
            continue

        for filing in head:
            try:
                row = _filing_to_row(
                    ticker=ticker,
                    cik=resolved_cik,
                    filing=filing,
                    row_provenance=row_provenance,
                    fetched_utc=fetched_utc,
                )
                if row is not None:
                    rows.append(row)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "filing_index: row extraction failed for %s filing=%r: %s",
                    ticker, filing, exc,
                )

    logger.debug(
        "filing_index: %s/%s fetched %d rows (%s forms)",
        ticker, resolved_cik, len(rows),
        "all" if form_types is None else str(sorted(form_types)),
    )
    return rows


def _filing_to_row(
    *,
    ticker: str,
    cik: str,
    filing: Any,
    row_provenance: str,
    fetched_utc: str,
) -> dict[str, Any] | None:
    """Convert one edgartools filing object to a flat row dict.

    Returns None if the filing lacks a required field (accession number,
    filing date, form type) so callers can filter those out cleanly.

    edgartools filing attributes used:
    - ``filing.accession_no``     — SEC accession number (dashes form)
    - ``filing.form``             — form type string (e.g. "10-K")
    - ``filing.filing_date``      — date or datetime of filing acceptance
    - ``filing.period_of_report`` — reporting period end date (may be None)
    - ``filing.document``         — primary document filename (may be None)

    All attributes are accessed via ``getattr(..., default)`` to tolerate
    edgartools version variance.
    """
    # --- accession number (required) ---
    accession = (
        getattr(filing, "accession_no", None)
        or getattr(filing, "accession_number", None)
        or getattr(filing, "accession", None)
    )
    if not accession:
        return None
    accession = str(accession).strip()

    # --- form type (required) ---
    form_type = (
        getattr(filing, "form", None)
        or getattr(filing, "form_type", None)
    )
    if not form_type:
        return None
    form_type = str(form_type).strip()

    # --- filing date (required) ---
    filing_date_raw = getattr(filing, "filing_date", None)
    if filing_date_raw is None:
        return None
    # Normalise to ISO date string; edgartools may return date or datetime.
    try:
        if hasattr(filing_date_raw, "isoformat"):
            # date or datetime object
            filing_date = filing_date_raw.isoformat()[:10]
        else:
            # Already a string — strip to YYYY-MM-DD.
            filing_date = str(filing_date_raw)[:10]
    except Exception:  # noqa: BLE001
        return None

    # --- period of report (optional) ---
    period_of_report_raw = getattr(filing, "period_of_report", None)
    period_of_report: str | None = None
    if period_of_report_raw is not None:
        try:
            if hasattr(period_of_report_raw, "isoformat"):
                period_of_report = period_of_report_raw.isoformat()[:10]
            else:
                period_of_report = str(period_of_report_raw)[:10]
        except Exception:  # noqa: BLE001
            period_of_report = None

    # --- primary document filename (optional) ---
    primary_doc: str | None = None
    doc_raw = getattr(filing, "document", None)
    if doc_raw is None:
        # Some edgartools versions expose the primary_doc differently.
        doc_raw = getattr(filing, "primary_doc", None)
    if doc_raw is not None:
        try:
            primary_doc = str(doc_raw).strip() or None
        except Exception:  # noqa: BLE001
            primary_doc = None

    # --- URLs ---
    edgar_url = _accession_to_edgar_url(accession)
    primary_doc_url = _build_primary_doc_url(accession, primary_doc)

    return {
        "accession": accession,
        "cik": cik,
        "edgar_url": edgar_url,
        "fetched_utc": fetched_utc,
        "filing_date": filing_date,
        "form_type": form_type,
        "period_of_report": period_of_report,
        "primary_doc_url": primary_doc_url,
        "row_provenance": row_provenance,
        "ticker": ticker,
    }
