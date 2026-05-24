"""Form 4 insider-transaction scout (Phase 4.5e PR 1 / 2 / 3 / 4-eq).

Scout-level fetcher + cache layer for SEC Form 4 (insider transactions).
The Phase 4.5e ladder landed in four sub-PRs:

- **PR 1 (scout)** — dep + cache shape + drift-detector manifest +
  parser against synthetic fixtures. No production wiring.
- **PR 2** — observability surface: ``Metadata.form4_*`` diagnostic
  fields + per-ticker fetch in ``compute/main.py``. Still no scoring
  impact.
- **PR 3** — production wiring: emit ``insider_sell_cluster`` +
  ``c_suite_unusual_sell`` annotates (per ``portable-annotate-before-
  veto``); thresholds calibrated against PR-2 cron data; weight
  constants uncommented in ``compute/scoring/manipulation_index.py``.
- **PR 4-eq (this revision)** — 10b5-1 contamination filter. Per-
  transaction ``is_rule_10b5_one: bool | None`` field added to the
  cache shape, resolved via ``edgar.ownership.core.detect_10b5_1_plan``
  pattern-scan on the RESOLVED footnote text (see "Footnote resolution"
  below — edgartools 5.31.5 does NOT parse the SEC structured
  ``<aff10b5One>`` XML element added in the 2023-04-01 mandate, so the
  footnote-text path is the only access surface available without
  forking the library). ``compute/scoring/form4_signals.py``
  ``_is_opportunistic_sell`` gates on NOT ``is_rule_10b5_one is True``
  so 10b5-1 scheduled trades are excluded from cluster + C-suite
  cohort counts. methodology-scientist Mode B verdict 2026-05-23
  (Jagolinzer 2009 §3.1 + §5.2 + Cohen 2008 §III + CMP 2012 §III.B/§V.A
  + SEC Release 33-11138) — APPROVED-AS-ANNOTATE.

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
          "is_rule_10b5_one": true,
          "filing_url": "https://..."
        },
        ...
      ]
    }

PR 4-eq adds the ``is_rule_10b5_one`` field. Pre-PR-4-eq caches
(missing the field) survive the 7-day TTL via
``Form4Transaction.from_dict``'s ``.get()`` fallback (the field is
``None`` on legacy rows — see "10b5-1 None-handling" below); the
weekly cron repopulates within a week. No forced cache invalidation
needed.

Footnote resolution
-------------------

The 10b5-1 plan flag is NOT in the SEC structured XML accessible via
edgartools 5.31.5. The ``<aff10b5One>`` element added by SEC Release
33-11138 (effective 2023-04-01, EDGAR schema X0609) is silently
dropped during edgartools' ``BeautifulSoup("xml")`` parse — verified
by ``edgar-debugger`` 2026-05-23 + 2026-05-24 across the full
``edgar.ownership`` module (no ``aff10b5One`` / ``rule10b5`` /
``tradingArrangement`` accessor on any parser path). The only
access path is pattern-scanning the resolved FOOTNOTE TEXT via
``edgar.ownership.core.detect_10b5_1_plan``.

Important scope caveat: ``<aff10b5One>`` is a DOCUMENT-LEVEL boolean
at ``ownershipDocument/aff10b5One`` (one boolean per Form 4 filing,
covering ALL transactions in that filing), NOT a per-transaction
attribute. The footnote-text fallback resolves per-transaction —
which is the CONSERVATIVE direction (catches filers who annotated
the specific transaction with the plan-pursuit footnote). The
architectural gap: a filer who checks ``<aff10b5One>true`` at the
document level but does NOT include the footnote text on a specific
transaction (valid — the checkbox IS the formal affirmative defense,
footnotes are supplemental) will slip past the footnote-text path
and enter the opportunistic cohort. Deferred to a follow-up PR
that parses the raw Form 4 XML directly for ``<aff10b5One>``
(edgartools doesn't expose it, so the implementation would walk the
filing text once per Ownership object). Tracked as the architectural
follow-up after PR 4-eq.

``NonDerivativeTransaction.footnotes`` carries newline-joined
footnote IDs (e.g. ``"F1\\nF2"``), NOT the resolved text. The
parsed ``Ownership`` object exposes a ``footnotes: Footnotes`` dict
that maps each ID to its resolved disclosure text. We resolve in the
parse loop by walking ``ownership.footnotes.get(fid)`` for each ID,
joining with newlines, and passing the result to
``detect_10b5_1_plan``. ``Footnotes.get(id, default)`` is the
public dict-like accessor (avoids the underscore-prefixed
``_resolve_footnotes`` private method); pinned via
``_FOOTNOTES_REQUIRED_ATTRS``.

10b5-1 None-handling: ``detect_10b5_1_plan`` returns ``None`` when
the resolved footnote text is empty or missing — typical for pre-
2023-04 filings (no mandate) AND for post-mandate filings that
simply have no disclosure text. ``_is_opportunistic_sell`` in
``form4_signals.py`` treats ``None`` as not-10b5-1 (the trade
remains opportunistic) per methodology-scientist Mode B verdict
2026-05-23 option (a) — matches the CMP 2012 + Jagolinzer 2009
empirical regime under which the cluster-detection thresholds
were calibrated.

FP caveat: ``detect_10b5_1_plan`` is a substring match on the
pattern list ``["10b5-1", "10b-5-1", "rule 10b5", "rule 10b-5",
"10b5 plan", "10b-5 plan"]``. Negated disclosures like "10b5-1
plan terminated 2022" or "no 10b5-1 plan in effect" match True.
edgar-debugger verified this on synthetic input. Tolerated for
this PR — the bias direction is conservative (over-excludes from
opportunistic cohort, never under-excludes). Q3 2026-08-19 cohort
audit gates whether to harden with a negation guard.

Transaction codes (SEC Form 4 Table II / III mapping):

- ``S`` — open-market or private sale
- ``P`` — open-market or private purchase
- ``A`` — grant or award (compensation-tied, not opportunistic)
- ``M`` — exercise of derivative + acquisition of common
- ``F`` — payment of exercise price or tax via shares
- ``D`` — sale back to issuer
- ``G`` — gift

PR 3 cluster detection (``compute/scoring/form4_signals.py``) filters
on ``transaction_code in {"S", "D"}`` — the Cohen-Malloy-Pomorski
2012 *J. Finance* §III.A "opportunistic" set. Codes ``A`` (grant),
``M`` (derivative exercise), ``F`` (tax-via-shares), ``G`` (gift)
are compensation-mechanical and explicitly excluded by CMP 2012;
including them would inflate cluster firing on benign vesting events.

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
  — canonical cluster definition (≥ 3 insiders, same direction,
  calendar-quarter) + opportunistic-code partition (``{S, D}``);
  cluster sells precede ~1.2% monthly abnormal returns
- Jeng-Metrick-Zeckhauser 2003 *RFS* §V — CFO + CEO co-sell signature
  used by ``compute/scoring/form4_signals.py`` for the narrower
  ``c_suite_unusual_sell`` annotate
- Jagolinzer 2009 *Mgmt Sci* §3.2 — signal-decay half-lives (~45d
  C-suite, ~75d broader pool) + 10b5-1 contamination evidence
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
#: to extract reporting-owner identity + transaction rows + the
#: footnote dict used for 10b5-1 plan resolution (PR 4-eq).
_OWNERSHIP_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "reporting_owners",       # ReportingOwners(owners: list[Owner])
    "non_derivative_table",   # NonDerivativeTable(transactions, ...)
    "footnotes",              # Footnotes(dict-like; id → resolved text) — PR 4-eq
)

#: Drift-detector manifest — accessor on the ``Footnotes`` dict
#: returned by ``Ownership.footnotes``. PR 4-eq uses the public
#: ``Footnotes.get(id, default)`` dict-like API to resolve a
#: transaction's footnote-ID string into the full disclosure text;
#: avoids edgartools' underscore-prefixed ``Ownership._resolve_footnotes``
#: private method. A future minor-version bump that renames ``get``
#: would fail the drift-detector test loudly.
_FOOTNOTES_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "get",
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
#: translates to the more descriptive QuantRank names. ``footnotes``
#: (PR 4-eq) is the newline-joined footnote-ID string used by the
#: 10b5-1 plan resolver — see module docstring §"Footnote resolution"
#: for the resolution path.
_NON_DERIVATIVE_TX_REQUIRED_ATTRS: Final[tuple[str, ...]] = (
    "date",
    "shares",
    "price",
    "remaining",
    "transaction_code",
    "acquired_disposed",
    "footnotes",
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
    is_rule_10b5_one: bool | None  # PR 4-eq; see module docstring §"Footnote resolution"
    filing_url: str

    @classmethod
    def from_dict(cls, d: dict) -> Form4Transaction | None:
        """Parse a cache dict back into a typed dataclass. Returns None
        if any required field is missing — caller should log + skip.

        ``is_rule_10b5_one`` (PR 4-eq) is read with a None default for
        backward compatibility with pre-PR-4-eq cache rows. Pre-PR-4-eq
        rows are treated as "no 10b5-1 disclosure detected" (option (a)
        from methodology-scientist Mode B 2026-05-23) — the trade
        remains in the opportunistic cohort, matching the empirical
        regime under which the cluster-detection thresholds were
        calibrated.
        """
        try:
            raw_10b5 = d.get("is_rule_10b5_one")
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
                is_rule_10b5_one=bool(raw_10b5) if raw_10b5 is not None else None,
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


def _detect_10b5_1_on_transaction(
    tx: object, footnotes_dict: object | None
) -> bool | None:
    """Return ``True`` / ``False`` / ``None`` for the 10b5-1 plan flag
    on a single ``NonDerivativeTransaction`` row (PR 4-eq).

    ``tx.footnotes`` carries newline-joined footnote IDs (e.g.
    ``"F1\\nF2"``); ``footnotes_dict`` (the parsed ``Ownership.footnotes``
    object) resolves each ID to disclosure text via its public
    ``.get(id, default)`` accessor. The joined text is then pattern-
    scanned by ``edgar.ownership.core.detect_10b5_1_plan``.

    Returns:
        ``True`` — footnote text matches a 10b5-1 disclosure pattern
        ``False`` — footnote text exists but no pattern matches
        ``None`` — no footnotes / no footnote text resolvable / parse
                  failure / edgartools detector unimportable

    Duck-typed for tests: any object exposing ``footnotes: str`` works
    for ``tx``, and any object exposing ``.get(key, default) -> str``
    works for ``footnotes_dict``.
    """
    raw_ids = getattr(tx, "footnotes", "") or ""
    if not raw_ids or footnotes_dict is None:
        return None
    try:
        from edgar.ownership.core import detect_10b5_1_plan
    except ImportError:
        # edgartools not installed or sub-module path drifted; fail
        # quietly — the cluster flag remains a (slightly noisier)
        # detector without the 10b5-1 filter rather than crashing.
        logger.debug(
            "edgar.ownership.core.detect_10b5_1_plan not importable; "
            "is_rule_10b5_one will be None for this filing."
        )
        return None
    try:
        ids = [fid for fid in str(raw_ids).split("\n") if fid]
        if not ids:
            return None
        resolved_parts: list[str] = []
        for fid in ids:
            text = footnotes_dict.get(fid, "")
            if text:
                resolved_parts.append(str(text))
        if not resolved_parts:
            return None
        return detect_10b5_1_plan("\n".join(resolved_parts))
    except Exception as e:  # noqa: BLE001 — defensive; parser is best-effort
        logger.warning("10b5-1 detection failed for a transaction: %s", e)
        return None


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

        # PR 4-eq — bind the Footnotes dict once per filing for 10b5-1
        # resolution. See module docstring §"Footnote resolution" for
        # why this path is needed (edgartools 5.31.5 does not parse
        # the SEC structured <aff10b5One> XML element).
        footnotes_dict = getattr(parsed, "footnotes", None)

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
            is_rule_10b5_one = _detect_10b5_1_on_transaction(tx, footnotes_dict)
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
                    "is_rule_10b5_one": is_rule_10b5_one,
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
