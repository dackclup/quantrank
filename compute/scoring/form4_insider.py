"""Form 4 insider-transaction scout (Phase 4.5e PR 1).

Scout-level fetcher + cache layer for SEC Form 4 (insider transactions).
**Production wiring intentionally NOT included** — this PR locks the
edgartools Form-4 API surface, ships the cache shape, and validates
the parser against synthetic fixtures. Two follow-up PRs land:

- **PR 2** — observability surface: ``Metadata.form4_*`` diagnostic
  fields + per-ticker fetch in ``compute/main.py``. Still no scoring
  impact. After ≥ 1 production cron, we know fetch latency, success
  rate, and the universe-level insider-count distribution.
- **PR 3** — production wiring: emit ``insider_sell_cluster`` +
  ``c_suite_unusual_sell`` annotates (per ``portable-annotate-before-
  veto``); calibrate thresholds against the PR-2 cron data;
  uncomment the reserved weight constants in
  ``compute/scoring/manipulation_index.py``.

This pattern is the ``portable-scout-then-integrate`` skill applied:
the dep + cache + parser land first under tests; the scoring impact
follows after operational confidence.

Cache shape
-----------

``compute/cache/edgar_form4/<TICKER>.json`` mirrors the
``edgar_amendments`` / ``edgar_late_filings`` siblings with a 7-day
TTL. One row per insider TRANSACTION (a single Form 4 can carry
multiple transaction rows — open-market sells, grants, exercises —
so flattening one-row-per-filing would lose granularity needed by
PR 3's cluster-detection logic).

::

    {
      "fetched_at": "2026-05-21T02:30:00Z",
      "lookback_days": 365,
      "transactions": [
        {
          "accession": "0001234567-26-000045",
          "filing_date": "2026-04-12",
          "transaction_date": "2026-04-10",
          "insider_name": "DOE JOHN A",
          "insider_cik": "0001234567",
          "is_director": false,
          "is_officer": true,
          "is_ten_percent_owner": false,
          "officer_title": "CEO",
          "transaction_code": "S",
          "shares": 12500.0,
          "price_per_share": 142.30,
          "dollar_value": 1778750.0,
          "shares_owned_following": 38200.0,
          "filing_url": "https://..."
        },
        ...
      ]
    }

Transaction codes (SEC Form 4 Table II / III mapping):

- ``S`` — open-market or private sale
- ``P`` — open-market or private purchase
- ``A`` — grant or award (compensation-tied, not opportunistic)
- ``M`` — exercise of derivative + acquisition of common
- ``F`` — payment of exercise price or tax via shares
- ``D`` — sale back to issuer

PR 3 cluster detection filters on ``transaction_code in {"S", "F"}``
— compensation-tied codes (A, M) are NOT insider-info-asymmetry
signals.

Drift detection
---------------

The ``_FORM4_REQUIRED_ATTRS`` manifest tuple locks the edgartools
Form-4 public-API surface as of this PR. A future edgartools minor
version that renames any of these attrs will fail the drift-detector
test loudly — preventing silent breakage on the weekly cron.

References
----------

- SEC Form 4 official spec — https://www.sec.gov/about/forms/form4.pdf
- Cohen-Malloy-Pomorski 2012 *J. Finance* §"Decoding Inside Information"
  — opportunistic insider trades (codes S, P) predict 1-6 month
  abnormal returns of ~10% annualized
- Cohen-Malloy-Nguyen 2020 *RFS* "Lazy Prices" — insider-cluster
  patterns predict subsequent disclosure quality + price drift
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final

from compute import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default lookback window for Form-4 fetches. **180 days** (was 365)
#: to fit the cron budget on a cold cache. The 2026-05-22 hotfix for
#: the property→method silent-drop (this PR) revealed that the post-
#: fix parser actually does the work it was claimed to do — each
#: filing iteration calls ``filing.obj()`` which triggers a SEC HTTP
#: round-trip per filing. At 365-day lookback × 502 tickers × N
#: filings/ticker, the cron exceeded the 45-min CI cap (pre-merge-
#: prod-sim run #1 on PR #210 timed out at 43m44s mid-Form-4-fetch).
#:
#: PR 3 (``insider_sell_cluster`` + ``c_suite_unusual_sell``) needs a
#: per-CEO baseline that benefits from a longer window. The proper fix
#: is per-filing caching (avoid re-fetching ``filing.obj()`` for
#: already-seen accession numbers) — tracked as a follow-up. Until
#: then, 180d still covers Cohen-Malloy-Pomorski 2012 §3.1's pattern
#: detection (their backtest used 6m-and-12m parallel windows; the
#: 180d ≈ 6m window remains literature-anchored).
FORM4_LOOKBACK_DAYS: Final[int] = 180

#: Cache TTL — mirrors the 8-K + restatement caches. Weekly cron repopulates.
CACHE_TTL_DAYS: Final[int] = 7

#: Cache subdir under ``config.CACHE_DIR``. Gitignored (parent
#: ``compute/cache/`` is gitignored).
_CACHE_SUBDIR: Final[str] = "edgar_form4"

#: Drift-detector manifest — public-API attrs we depend on from each
#: edgartools ``Filing`` instance returned by ``Company.get_filings(form="4")``.
#: A future minor-version bump that renames any of these fails the
#: ``test_edgar_form4_api_surface_locked`` test loudly so we catch the
#: drift on PR review, not on a Sunday-night cron.
#:
#: NOTE on ``"obj"``: edgartools 2.x exposed ``Filing.obj`` as a
#: property; edgartools 5.x changed it to a method (must be called as
#: ``filing.obj()``). The manifest check only verifies attribute
#: presence — the *call site* in ``_form4_to_transactions`` handles
#: both shapes via ``callable()``. A future 6.x revert to property
#: form would NOT need a code change here.
_FORM4_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "accession_no",
    "filing_date",
    "form",
    "obj",  # property in edgartools 2.x; method in 5.x — caller handles both
)

#: Drift-detector manifest — attrs on the parsed Ownership object
#: (``filing.obj`` for a Form 4 returns an ``edgar.ownership.Form4``
#: which subclasses ``Ownership``). The parser walks down this chain
#: to extract reporting-owner identity + transaction rows.
_OWNERSHIP_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "reporting_owners",       # ReportingOwners(owners: list[Owner])
    "non_derivative_table",   # NonDerivativeTable(transactions, ...)
)

#: Drift-detector manifest — fields on each ``Owner`` dataclass row
#: inside ``Ownership.reporting_owners.owners``.
_OWNER_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "cik",
    "name",
    "is_director",
    "is_officer",
    "is_ten_pct_owner",       # NOTE: edgartools uses "ten_pct", not "ten_percent"
    "officer_title",
)

#: Drift-detector manifest — fields on each ``NonDerivativeTransaction``
#: dataclass row inside ``Ownership.non_derivative_table.transactions``.
#: Note the unconventional field names — edgartools uses ``date`` (not
#: ``transaction_date``), ``price`` (not ``price_per_share``), and
#: ``remaining`` (not ``shares_owned_following``). Our cache shape
#: translates to the more descriptive QuantRank names.
_NON_DERIVATIVE_TX_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "date",
    "shares",
    "price",
    "remaining",
    "transaction_code",
    "acquired_disposed",
)


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Form4Transaction:
    """One row in a Form 4 filing's transaction table.

    Attributes mirror the cache JSON shape — see module docstring.
    """

    accession: str
    filing_date: str  # ISO YYYY-MM-DD
    transaction_date: str | None  # may differ from filing_date
    insider_name: str
    insider_cik: str  # stable key (vs name drift across filings)
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    officer_title: str | None
    transaction_code: str  # S, P, A, M, F, D
    shares: float | None
    price_per_share: float | None
    dollar_value: float | None  # shares × price; None when transaction has no price (grants)
    shares_owned_following: float | None
    filing_url: str

    @classmethod
    def from_dict(cls, d: dict) -> Form4Transaction | None:
        """Parse a cache dict back into a typed dataclass. Returns None
        if any required field is missing — caller should log + skip."""
        try:
            return cls(
                accession=str(d["accession"]),
                filing_date=str(d["filing_date"]),
                transaction_date=d.get("transaction_date"),
                insider_name=str(d["insider_name"]),
                insider_cik=str(d["insider_cik"]),
                is_director=bool(d.get("is_director", False)),
                is_officer=bool(d.get("is_officer", False)),
                is_ten_percent_owner=bool(d.get("is_ten_percent_owner", False)),
                officer_title=d.get("officer_title"),
                transaction_code=str(d["transaction_code"]),
                shares=_safe_float(d.get("shares")),
                price_per_share=_safe_float(d.get("price_per_share")),
                dollar_value=_safe_float(d.get("dollar_value")),
                shares_owned_following=_safe_float(d.get("shares_owned_following")),
                filing_url=str(d.get("filing_url", "")),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Form4Transaction.from_dict failed: %s | dict=%s", e, d)
            return None


def _safe_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# EDGAR identity (lazy — same pattern as siblings)
# ---------------------------------------------------------------------------


def _ensure_edgar_identity() -> bool:
    user_agent = os.environ.get("EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        logger.warning(
            "EDGAR_USER_AGENT is not set; skipping Form-4 fetch.",
        )
        return False
    try:
        from edgar import set_identity

        set_identity(user_agent)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to set edgar identity: %s", e)
        return False
    return True


# ---------------------------------------------------------------------------
# Cache layer (mirrors compute.scoring.eight_k_events / restatement_filings)
# ---------------------------------------------------------------------------


def _cache_path(ticker: str) -> Path:
    return config.CACHE_DIR / _CACHE_SUBDIR / f"{ticker}.json"


def _cache_read(ticker: str, lookback_days: int) -> list[dict] | None:
    p = _cache_path(ticker)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("form4 cache read failed for %s: %s", ticker, e)
        return None
    fetched_at_raw = payload.get("fetched_at")
    cached_lookback = payload.get("lookback_days")
    if not isinstance(fetched_at_raw, str) or not isinstance(cached_lookback, int):
        return None
    if cached_lookback < lookback_days:
        # Stale window — caller wants more history than the cache stored.
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if datetime.now(UTC) - fetched_at > timedelta(days=CACHE_TTL_DAYS):
        return None
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return None
    return transactions


def _cache_write(ticker: str, lookback_days: int, transactions: list[dict]) -> None:
    p = _cache_path(ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": int(lookback_days),
        "transactions": transactions,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def invalidate_cache(ticker: str) -> None:
    """Drop the Form-4 cache entry for a ticker — used in tests."""
    p = _cache_path(ticker)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Parser — duck-typed; tests inject synthetic objects without edgartools
# ---------------------------------------------------------------------------


def _form4_to_transactions(filing: object) -> list[dict]:
    """Extract one or more transaction-row dicts from a single Form 4
    filing object. Duck-typed — accepts any object exposing the
    attributes documented in ``_FORM4_REQUIRED_ATTRS`` PLUS the
    parsed-form attrs surfaced via ``filing.obj``.

    Returns an empty list when:
    - The filing has no parsed non-derivative transaction table
    - All transactions are derivative-only (Form 4 Table II)
    - The parser raises (logged at WARNING level)

    Call chain (verified against edgartools 5.31.3, 2026-05-21):

    - ``filing.obj`` → ``edgar.ownership.Form4`` (subclass of ``Ownership``)
    - ``Ownership.reporting_owners`` → ``ReportingOwners(owners: list[Owner])``
    - ``Ownership.non_derivative_table.transactions`` → iterable of
      ``NonDerivativeTransaction`` (rows via ``__getitem__`` protocol)
    - ``Owner`` fields: ``cik``, ``name``, ``is_director``, ``is_officer``,
      ``is_ten_pct_owner`` (sic — edgartools uses ``ten_pct``, NOT
      ``ten_percent``), ``officer_title``
    - ``NonDerivativeTransaction`` fields: ``date`` (NOT
      ``transaction_date``), ``shares``, ``price`` (NOT
      ``price_per_share``), ``remaining`` (NOT ``shares_owned_following``),
      ``transaction_code``, ``acquired_disposed``

    Cache JSON schema preserves the more descriptive QuantRank names
    (``transaction_date`` / ``price_per_share`` / ``shares_owned_following``
    / ``is_ten_percent_owner``) — the translation happens here at the
    boundary.

    Multi-owner Form 4s (joint filers): this scout takes ``owners[0]``
    only. Joint filers are rare; the function logs a WARNING when
    ``len(owners) > 1`` so PR 3 can audit cohort impact.
    """
    try:
        accession = str(filing.accession_no)
        filing_date_raw = filing.filing_date
        filing_date = (
            filing_date_raw.isoformat()
            if hasattr(filing_date_raw, "isoformat")
            else str(filing_date_raw)
        )
        filing_url = str(
            getattr(filing, "filing_url", "")
            or getattr(filing, "homepage_url", "")
        )
        # edgartools 5.x exposes ``Filing.obj`` as a METHOD (must be
        # called), where 2.x exposed it as a property. The 2026-05-22
        # silent-drop incident — 0/502 insider transactions across the
        # entire S&P 500 universe — traced to ``getattr(filing, "obj")``
        # returning the bound method instead of the parsed Ownership
        # object, then ``getattr(bound_method, "reporting_owners")``
        # returning ``None`` and short-circuiting ``return []`` on every
        # filing. The ``callable()`` check below handles both API
        # generations so a future 6.x reversion (or a downgrade) won't
        # re-introduce the bug; the unit-test mocks pass through the
        # attribute path because ``@dataclass`` instances are not
        # callable.
        _obj_attr = getattr(filing, "obj", None)
        parsed = _obj_attr() if callable(_obj_attr) else _obj_attr
        if parsed is None:
            return []

        # Walk the reporting_owners chain.
        reporting_owners = getattr(parsed, "reporting_owners", None)
        if reporting_owners is None:
            return []
        owners = getattr(reporting_owners, "owners", None) or []
        if not owners:
            return []
        if len(owners) > 1:
            logger.warning(
                "form4 accession=%s has %d reporting owners — scout uses owners[0] only",
                accession,
                len(owners),
            )
        owner = owners[0]
        insider_cik = str(getattr(owner, "cik", ""))
        insider_name = str(getattr(owner, "name", ""))
        if not insider_cik or not insider_name:
            return []

        # Walk the non_derivative_table chain.
        nd_table = getattr(parsed, "non_derivative_table", None)
        if nd_table is None:
            return []
        transactions_iter = getattr(nd_table, "transactions", None)
        if transactions_iter is None:
            return []
        # NonDerivativeTransactions wraps a DataFrame and implements
        # __getitem__; Python's for-loop falls back to the __getitem__
        # protocol. The `.empty` flag is the explicit no-rows signal.
        if getattr(transactions_iter, "empty", False):
            return []

        rows: list[dict] = []
        for tx in transactions_iter:
            tx_date_raw = getattr(tx, "date", None)
            tx_date = (
                tx_date_raw.isoformat()
                if hasattr(tx_date_raw, "isoformat")
                else (str(tx_date_raw) if tx_date_raw is not None else None)
            )
            shares = _safe_float(getattr(tx, "shares", None))
            price = _safe_float(getattr(tx, "price", None))
            dollar_value = (
                shares * price
                if shares is not None and price is not None
                else None
            )
            rows.append(
                {
                    "accession": accession,
                    "filing_date": filing_date,
                    "transaction_date": tx_date,
                    "insider_name": insider_name,
                    "insider_cik": insider_cik,
                    "is_director": bool(getattr(owner, "is_director", False)),
                    "is_officer": bool(getattr(owner, "is_officer", False)),
                    "is_ten_percent_owner": bool(
                        getattr(owner, "is_ten_pct_owner", False)
                    ),
                    "officer_title": getattr(owner, "officer_title", None) or None,
                    "transaction_code": str(getattr(tx, "transaction_code", "")),
                    "shares": shares,
                    "price_per_share": price,
                    "dollar_value": dollar_value,
                    "shares_owned_following": _safe_float(
                        getattr(tx, "remaining", None)
                    ),
                    "filing_url": filing_url,
                }
            )
        return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("form4_to_transactions failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Fetch entry — production callers use this
# ---------------------------------------------------------------------------


def fetch_recent_form4(
    ticker: str,
    lookback_days: int = FORM4_LOOKBACK_DAYS,
    *,
    filings_override: list[object] | None = None,
) -> list[dict] | None:
    """Fetch Form 4 filings for ``ticker`` within ``lookback_days``,
    flattened into one row per transaction.

    Returns ``None`` on EDGAR rate-limit / network failure / missing
    identity / ticker-not-found. Returns an empty list ``[]`` when
    EDGAR succeeds but the ticker has no Form-4 activity in the window
    (small caps, no recent insider trades).

    ``filings_override`` is the test inject path — pass a list of
    duck-typed filing objects to skip the live EDGAR call.

    Scout-PR note: PR 2 will wrap this call in a try/except per the
    ``portable-graceful-degradation-try-except`` skill — failures
    must not block weekly compute.
    """
    if filings_override is not None:
        rows: list[dict] = []
        for filing in filings_override:
            rows.extend(_form4_to_transactions(filing))
        # Sort by filing_date desc so most-recent transactions come first.
        rows.sort(key=lambda d: d.get("filing_date") or "", reverse=True)
        return rows

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
            form="4",
            filing_date=(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("form4 top-level fetch failed for %s: %s", ticker, e)
        return None

    rows: list[dict] = []
    try:
        for filing in filings:
            rows.extend(_form4_to_transactions(filing))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "form4 iteration failed for %s after %d rows: %s",
            ticker,
            len(rows),
            e,
        )

    rows.sort(key=lambda d: d.get("filing_date") or "", reverse=True)
    _cache_write(ticker, lookback_days, rows)
    return rows


__all__ = [
    "CACHE_TTL_DAYS",
    "FORM4_LOOKBACK_DAYS",
    "Form4Transaction",
    "fetch_recent_form4",
    "invalidate_cache",
]
