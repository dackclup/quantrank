"""8-K event defenses (Phase 3d Defenses #9 + #10).

Two defenses on the same module — both consume SEC Form 8-K filings via
``edgartools`` but enforce them differently per Tier-2 spec:

- **Defense #9** (Item 4.02 — "Non-Reliance on Previously Issued Financial
  Statements or a Related Audit Report or Completed Interim Review") is a
  **HARD VETO**. Joins the existing 3 vetoes (altman / sloan / NSI) at v1.0.
  Lookback window: 365 days. Schroeder 2024 SSRN finds ~50% of Item 4.02
  filings precede formal restatement within the trailing year.
- **Defense #10** (Item 4.01 — "Changes in Registrant's Certifying
  Accountant") is **annotate-only** because Reg S-K Item 304 mandates the
  same disclosure for benign reasons (audit firm restructuring, partner
  rotation), so the false-positive rate is too high for veto. Lookback
  window: 730 days.

Both defenses surface in ``StockDetail.tier2_events`` (the Pydantic field
lands in PR 3d Step 4) and the user-visible flag list. Per SKILL.md
Rule 16, neither modifies the composite score directly; the hard veto
suppresses only the ``entered_top5`` badge.

Cache strategy
--------------

The 8-K filing list per ticker is JSON-cached with a 7-day TTL under
``compute/cache/edgar_8k/<ticker>.json`` (gitignored). Cache shape::

    {
      "fetched_at": "2026-05-10T03:49:51Z",
      "lookback_days": 730,
      "filings": [
        {
          "filing_date": "2026-02-14",
          "filing_url": "https://www.sec.gov/Archives/...",
          "items": ["Item 5.02", "Item 9.01"],
          "item_text_excerpts": {"Item 5.02": "<first 500 chars>"}
        },
        ...
      ]
    }

A 7-day TTL is safe because 4.02 / 4.01 events are sticky: once filed,
they don't disappear. The worst-case staleness is a missed-by-a-week
flag for a ticker that filed in the last 7 days; Step 5's weekly
compute cadence aligns with this.

Failure semantics
-----------------

Any fetch failure (rate-limit, network error, ticker-not-found,
malformed response) returns ``None`` from ``fetch_recent_8k_filings``.
The ``check_*`` callers translate that into ``ItemFlag(fired=False, …)``
with all metadata fields ``None``. **Callers cannot distinguish
"genuinely no event" from "fetch failed" from a single ItemFlag
return** — that's why ``Metadata.tier2_coverage_pct`` (PR 3d Step 4
field) tracks fetch success rate at the population level.

References
----------
- SEC Form 8-K Items 4.01 / 4.02 — current rule text via SEC.gov
  ``Form 8-K General Instructions``.
- Reg S-K Item 304 — disclosure requirements for changes in
  registrant's certifying accountant.
- Schroeder, J. (2024) "The Information Content of Item 4.02
  Disclosures", SSRN.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from compute import config

logger = logging.getLogger(__name__)

# Item-number regexes — case-insensitive, dot-anchored on both sides so
# "Item 4.02" matches but "Item 4.020" does NOT (the latter would be a
# malformed item number anyway, but defense in depth).
_ITEM_4_02_PATTERN = re.compile(r"\bItem\s+4\.\s*02\b", re.IGNORECASE)
_ITEM_4_01_PATTERN = re.compile(r"\bItem\s+4\.\s*01\b", re.IGNORECASE)

# General "Item N.MM" extractor used by _filing_to_dict to enumerate
# items in raw 8-K HTML text. Mirrors edgartools' Strategy 3 fallback
# (_extract_items_from_text in current_report.py:51) — proven-correct
# regex extraction that bypasses hybrid_section_detector.
_ITEMS_PATTERN = re.compile(r"\bItem\s+(\d+\.\s*\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ItemFlag:
    """Return shape for ``check_non_reliance`` and ``check_auditor_change``.

    Attributes
    ----------
    fired:
        True iff at least one matching 8-K Item was found in the
        lookback window. Returns False when no matching item OR when
        the upstream fetch failed (the caller distinguishes via
        ``Metadata.tier2_coverage_pct`` at the population level —
        see module docstring).
    filing_date:
        ISO ``YYYY-MM-DD`` date of the **most recent** matching
        filing. ``None`` when ``fired=False`` or fetch failed.
    filing_url:
        Canonical SEC filing URL for the most recent matching
        filing. ``None`` when ``fired=False`` or fetch failed.
    raw_item_text:
        First :data:`config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS` of the
        matching item body, for human review on the detail page.
        ``None`` when ``fired=False`` or excerpt couldn't be
        extracted from the filing's section structure.
    """

    fired: bool
    filing_date: str | None
    filing_url: str | None
    raw_item_text: str | None


# ---------------------------------------------------------------------------
# Identity (lazy — same pattern as compute/ingest/fundamentals.py)
# ---------------------------------------------------------------------------

_IDENTITY_SET = False


def _ensure_edgar_identity() -> bool:
    """Initialize the EDGAR User-Agent if not already done.

    Returns True on success, False if the env var is unset (in which
    case caller treats it as a fetch failure → returns None / fired=False).
    Failure is non-fatal here (8-K events are a Tier-2 feature, not a
    hard requirement for the compute run to succeed) — distinct from
    the fundamentals layer which raises on missing identity.
    """
    global _IDENTITY_SET
    if _IDENTITY_SET:
        return True
    ua = os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        logger.warning(
            "EDGAR_USER_AGENT not set — Tier-2 8-K event fetch will skip "
            "all tickers. Set the env var to enable Defenses #9 + #10."
        )
        return False
    try:
        from edgar import set_identity
        set_identity(ua)
    except Exception as e:  # noqa: BLE001
        logger.warning("set_identity failed: %s", e)
        return False
    _IDENTITY_SET = True
    return True


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

def _cache_path(ticker: str) -> Path:
    config.EDGAR_8K_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ticker = re.sub(r"[^A-Za-z0-9_-]", "_", ticker)
    return config.EDGAR_8K_CACHE_DIR / f"{safe_ticker}.json"


def _cache_read(ticker: str, lookback_days: int) -> list[dict] | None:
    """Return cached filings list or None on miss / expired / corrupt."""
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("cache read failed for %s (%s) — treating as miss", ticker, e)
        return None
    fetched_at_str = payload.get("fetched_at")
    if not fetched_at_str:
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    age = datetime.now(UTC) - fetched_at
    if age > timedelta(seconds=config.EDGAR_8K_CACHE_TTL_SECONDS):
        return None
    # Cache hit must cover at least the requested lookback window.
    cached_lookback = payload.get("lookback_days", 0)
    if cached_lookback < lookback_days:
        return None
    filings = payload.get("filings")
    if not isinstance(filings, list):
        return None
    return filings


def _cache_write(ticker: str, lookback_days: int, filings: list[dict]) -> None:
    path = _cache_path(ticker)
    payload = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": lookback_days,
        "filings": filings,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("cache write failed for %s (%s) — continuing", ticker, e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def invalidate_cache(ticker: str) -> None:
    """Remove the on-disk cache entry for a ticker. Idempotent."""
    path = _cache_path(ticker)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _extract_items_and_excerpts_from_html(
    html: str,
) -> tuple[list[str], dict[str, str]]:
    """Pure regex extraction of 8-K items + excerpts from raw HTML.

    Mirrors edgartools' Strategy 3 fallback path
    (``_extract_items_from_text`` in
    ``edgar/company_reports/current_report.py:51``), which the
    upstream library uses for legacy SGML filings (1999-2001). The
    same approach gives correctness-equivalent output for modern
    filings on our use case (item-number presence + first-N-char
    excerpts) WITHOUT routing through ``HTMLParser(ParserConfig)`` →
    ``hybrid_section_detector``. Skipping the parser saves the
    dominant Tier-2 cost (~3,500 detector invocations across 502
    stocks × ~7 8-K filings each) that exceeded the 45-min workflow
    timeout in run #13.

    Items are canonicalized to ``"Item N.MM"`` (whitespace stripped
    from inside the number), deduplicated (first occurrence wins
    for excerpt). Excerpts are sliced from the match start position
    out to ``config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS``.
    """
    text = BeautifulSoup(html, "lxml").get_text(separator=" ")
    items: list[str] = []
    seen: set[str] = set()
    excerpts: dict[str, str] = {}
    excerpt_chars = config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS
    for m in _ITEMS_PATTERN.finditer(text):
        num = re.sub(r"\s+", "", m.group(1))
        canon = f"Item {num}"
        if canon in seen:
            continue
        seen.add(canon)
        items.append(canon)
        excerpts[canon] = text[m.start() : m.start() + excerpt_chars]
    return items, excerpts


def _filing_to_dict(filing: object) -> dict | None:
    """Extract the JSON-cacheable subset of an edgartools Filing.

    Uses ``filing.html()`` + BeautifulSoup raw text extraction +
    regex item detection (NOT ``filing.obj().items`` /
    ``filing.obj().sections``) to skip edgartools' parser pipeline,
    which routes through ``HTMLParser(ParserConfig(form='8-K'))`` →
    ``hybrid_section_detector`` via the ``EightK.document``
    cached_property. The detector adds substantial CPU cost across
    ~3,500 8-K filings (502 tickers × ~7 each) totaling 30+ min
    that exceeded the 45-min workflow timeout in run #13. Item
    detection mirrors edgartools' own Strategy 3 regex fallback
    (validated against legacy SGML filings).

    Returns None if the filing can't be parsed (malformed object,
    missing required fields). Caller treats as a soft skip.
    """
    try:
        filing_date = getattr(filing, "filing_date", None)
        filing_url = getattr(filing, "url", None) or getattr(filing, "filing_url", None)
        if filing_date is None or filing_url is None:
            return None
        if isinstance(filing_date, (date, datetime)):
            filing_date_str = filing_date.strftime("%Y-%m-%d")
        else:
            filing_date_str = str(filing_date)[:10]
    except Exception as e:  # noqa: BLE001
        logger.debug("_filing_to_dict header extract failed: %s", e)
        return None

    items: list[str] = []
    item_text_excerpts: dict[str, str] = {}
    try:
        html_attr = getattr(filing, "html", None)
        html_content = html_attr() if callable(html_attr) else html_attr
        if html_content:
            items, item_text_excerpts = _extract_items_and_excerpts_from_html(
                str(html_content)
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("_filing_to_dict html extract failed: %s", e)

    return {
        "filing_date": filing_date_str,
        "filing_url": str(filing_url),
        "items": items,
        "item_text_excerpts": item_text_excerpts,
    }


def fetch_recent_8k_filings(
    ticker: str,
    lookback_days: int,
) -> list[dict] | None:
    """Fetch 8-K filings via edgartools, JSON-cached for 7 days.

    Returns
    -------
    list[dict] | None
        A list (possibly empty) of normalized filing dicts on success.
        ``None`` on EDGAR rate-limit, network failure, missing identity,
        or ticker-not-found. Empty list ``[]`` means EDGAR returned
        successfully but the ticker has zero 8-Ks in the lookback
        window.

    Cache: 7-day TTL. Cache hit requires ``cached_lookback >= lookback_days``
    (so a request for 730d won't be served by a 365d cache entry).
    """
    cached = _cache_read(ticker, lookback_days)
    if cached is not None:
        return cached

    if not _ensure_edgar_identity():
        return None

    try:
        from edgar import Company
    except ImportError as e:
        logger.warning("edgartools not importable: %s", e)
        return None

    try:
        company = Company(ticker)
        end = date.today()
        start = end - timedelta(days=lookback_days)
        filings = company.get_filings(
            form="8-K",
            filing_date=(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("8-K fetch failed for %s: %s", ticker, e)
        return None

    out: list[dict] = []
    try:
        for filing in filings:
            entry = _filing_to_dict(filing)
            if entry is not None:
                out.append(entry)
    except Exception as e:  # noqa: BLE001
        logger.warning("8-K iteration failed for %s after %d entries: %s", ticker, len(out), e)
        # Partial result is OK — cache what we have.

    _cache_write(ticker, lookback_days, out)
    return out


# ---------------------------------------------------------------------------
# Item checks
# ---------------------------------------------------------------------------

def _filing_date_within(filing_date_str: str, asof: date, lookback_days: int) -> bool:
    """True iff ``filing_date_str`` is within the last ``lookback_days``
    of ``asof`` (inclusive on both ends)."""
    try:
        fd = date.fromisoformat(filing_date_str)
    except ValueError:
        return False
    if fd > asof:
        return False
    return (asof - fd).days <= lookback_days


def _check_item(
    ticker: str,
    *,
    item_pattern: re.Pattern[str],
    lookback_days: int,
    asof: date | None = None,
    filings: list[dict] | None = None,
) -> ItemFlag:
    """Shared implementation for check_non_reliance + check_auditor_change.

    ``filings`` may be passed in directly (used by tests with synthetic
    fixtures). When None, the function fetches via
    :func:`fetch_recent_8k_filings`.
    """
    asof = asof or date.today()

    if filings is None:
        filings = fetch_recent_8k_filings(ticker, lookback_days)
    if filings is None:
        return ItemFlag(fired=False, filing_date=None, filing_url=None, raw_item_text=None)

    matches: list[dict] = []
    for entry in filings:
        if not isinstance(entry, dict):
            continue
        filing_date_str = entry.get("filing_date")
        if not filing_date_str or not _filing_date_within(filing_date_str, asof, lookback_days):
            continue
        for item_name in entry.get("items") or []:
            if item_pattern.search(str(item_name)):
                matches.append({
                    "filing_date": filing_date_str,
                    "filing_url": entry.get("filing_url"),
                    "matched_item_name": item_name,
                    "raw_item_text": (entry.get("item_text_excerpts") or {}).get(item_name),
                })
                break  # one filing fires the flag once

    if not matches:
        return ItemFlag(fired=False, filing_date=None, filing_url=None, raw_item_text=None)

    # Most recent match wins.
    most_recent = max(matches, key=lambda m: m["filing_date"])
    excerpt = most_recent.get("raw_item_text")
    if excerpt is not None:
        excerpt = str(excerpt)[: config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS]
    return ItemFlag(
        fired=True,
        filing_date=most_recent["filing_date"],
        filing_url=most_recent.get("filing_url"),
        raw_item_text=excerpt,
    )


def check_non_reliance(
    ticker: str,
    *,
    asof: date | None = None,
    filings: list[dict] | None = None,
) -> ItemFlag:
    """Defense #9 — 8-K Item 4.02 hard veto.

    Lookback window: :data:`config.EIGHT_K_LOOKBACK_DAYS_VETO` (365 days).
    See module docstring for failure semantics.
    """
    return _check_item(
        ticker,
        item_pattern=_ITEM_4_02_PATTERN,
        lookback_days=config.EIGHT_K_LOOKBACK_DAYS_VETO,
        asof=asof,
        filings=filings,
    )


def check_auditor_change(
    ticker: str,
    *,
    asof: date | None = None,
    filings: list[dict] | None = None,
) -> ItemFlag:
    """Defense #10 — 8-K Item 4.01 annotate-only.

    Lookback window: :data:`config.EIGHT_K_LOOKBACK_DAYS_ANNOTATE`
    (730 days). See module docstring for failure semantics.

    Note: Per Reg S-K Item 304 both dismissal and resignation trigger
    Item 4.01 disclosure; we do not distinguish severity in this
    annotate-only flag. Callers can read ``raw_item_text`` to surface
    the underlying disclosure (e.g., "no disagreements" vs "material
    weakness identified") on the detail page.
    """
    return _check_item(
        ticker,
        item_pattern=_ITEM_4_01_PATTERN,
        lookback_days=config.EIGHT_K_LOOKBACK_DAYS_ANNOTATE,
        asof=asof,
        filings=filings,
    )


__all__ = [
    "ItemFlag",
    "check_auditor_change",
    "check_non_reliance",
    "fetch_recent_8k_filings",
    "invalidate_cache",
]
