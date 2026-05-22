"""Unit + drift-detector tests for compute.scoring.form4_insider
(Phase 4.5e PR 1 — Scout).

All tests offline. Synthetic duck-typed filing fixtures bypass the
live SEC fetch path. The drift-detector test (Section D) imports
edgartools at module load to lock the public-API surface our parser
depends on; it skips cleanly when edgartools isn't installed.

Network smoke tests live under the ``@pytest.mark.network`` marker
and are deferred to a Phase 4.5e PR 2 follow-up (the
``portable-observability-before-wiring`` cron will be the first
live integration).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from compute import config
from compute.scoring import form4_insider
from compute.scoring.form4_insider import (
    _FORM4_REQUIRED_ATTRS,
    _NON_DERIVATIVE_TX_REQUIRED_ATTRS,
    _OWNER_REQUIRED_ATTRS,
    _OWNERSHIP_REQUIRED_ATTRS,
    CACHE_TTL_DAYS,
    FORM4_LOOKBACK_DAYS,
    Form4Transaction,
    fetch_recent_form4,
    invalidate_cache,
)

# ---------------------------------------------------------------------------
# Synthetic duck-typed Form 4 fixtures
# ---------------------------------------------------------------------------


# Synthetic fixtures mirror the verified edgartools API (2026-05-21):
# Filing → .obj (Ownership) → .reporting_owners.owners[0] (Owner)
#                          → .non_derivative_table.transactions (rows)


@dataclass
class _FakeTx:
    """Mirrors edgartools NonDerivativeTransaction field names."""

    date: str
    transaction_code: str
    shares: float
    price: float | None
    remaining: float
    acquired_disposed: str = "D"


@dataclass
class _FakeNonDerivativeTransactions:
    """Mirrors edgartools NonDerivativeTransactions — DataHolder with
    .empty + __getitem__ protocol for iteration."""

    _rows: list[_FakeTx]

    @property
    def empty(self) -> bool:
        return not self._rows

    def __getitem__(self, idx: int) -> _FakeTx:
        return self._rows[idx]

    def __len__(self) -> int:
        return len(self._rows)


@dataclass
class _FakeNonDerivativeTable:
    transactions: _FakeNonDerivativeTransactions


@dataclass
class _FakeOwner:
    """Mirrors edgartools Owner dataclass field names exactly."""

    cik: str
    name: str
    is_director: bool
    is_officer: bool
    is_ten_pct_owner: bool  # note: edgartools spells it ten_pct, not ten_percent
    officer_title: str | None


@dataclass
class _FakeReportingOwners:
    owners: list[_FakeOwner]


@dataclass
class _FakeOwnership:
    """Mirrors edgartools Ownership/Form4."""

    reporting_owners: _FakeReportingOwners
    non_derivative_table: _FakeNonDerivativeTable


@dataclass
class _FakeFiling:
    accession_no: str
    filing_date: str
    form: str
    obj: _FakeOwnership | None
    filing_url: str = "https://www.sec.gov/Archives/edgar/data/0/test.htm"


def _ceo_sell(
    accession: str = "0001234567-26-000001",
    filing_date: str = "2026-04-12",
    transaction_date: str = "2026-04-10",
    shares: float = 12500.0,
    price: float = 142.30,
    name: str = "DOE JOHN A",
    cik: str = "0001000001",
    title: str = "CEO",
) -> _FakeFiling:
    return _FakeFiling(
        accession_no=accession,
        filing_date=filing_date,
        form="4",
        obj=_FakeOwnership(
            reporting_owners=_FakeReportingOwners(
                owners=[
                    _FakeOwner(
                        cik=cik,
                        name=name,
                        is_director=False,
                        is_officer=True,
                        is_ten_pct_owner=False,
                        officer_title=title,
                    ),
                ],
            ),
            non_derivative_table=_FakeNonDerivativeTable(
                transactions=_FakeNonDerivativeTransactions(
                    _rows=[
                        _FakeTx(
                            date=transaction_date,
                            transaction_code="S",
                            shares=shares,
                            price=price,
                            remaining=38200.0,
                        )
                    ]
                )
            ),
        ),
    )


# ---------------------------------------------------------------------------
# A. Cohort smoke tests — synthetic fixtures
# ---------------------------------------------------------------------------


def test_A1_single_ceo_sell_parses_one_transaction_row():
    """One Form 4, one open-market sell (code S), $1.78M dollar_value —
    expect one Form4Transaction with insider_role=officer + transaction_code=S."""
    out = fetch_recent_form4("TST", filings_override=[_ceo_sell()])
    assert out is not None and len(out) == 1
    tx = out[0]
    assert tx["insider_name"] == "DOE JOHN A"
    assert tx["insider_cik"] == "0001000001"
    assert tx["is_officer"] is True
    assert tx["officer_title"] == "CEO"
    assert tx["transaction_code"] == "S"
    assert tx["shares"] == 12500.0
    assert tx["price_per_share"] == 142.30
    assert tx["dollar_value"] == pytest.approx(12500.0 * 142.30)
    assert tx["filing_date"] == "2026-04-12"


def test_A2_multi_insider_cluster_returns_four_distinct_ciks():
    """Four separate Form 4 filings within 30 days from 4 distinct CIKs
    (CEO + CFO + 2 directors), all transaction_code=S. The parser
    should return 4 transactions across 4 distinct insider_cik values
    (PR 3's cluster-detection logic will use CIK as the unique key)."""
    filings = [
        _ceo_sell(accession="a1", filing_date="2026-04-12", name="DOE JOHN A", cik="0001000001"),
        _ceo_sell(accession="a2", filing_date="2026-04-15", name="ROE JANE B", cik="0001000002", title="CFO"),
        _ceo_sell(accession="a3", filing_date="2026-04-20", name="SMITH ALICE", cik="0001000003", title=None),
        _ceo_sell(accession="a4", filing_date="2026-04-25", name="JONES BOB", cik="0001000004", title=None),
    ]
    out = fetch_recent_form4("TST", filings_override=filings)
    assert out is not None and len(out) == 4
    distinct_ciks = {row["insider_cik"] for row in out}
    assert distinct_ciks == {"0001000001", "0001000002", "0001000003", "0001000004"}


def test_A3_grants_and_exercises_preserved_with_distinct_codes():
    """A single Form 4 with two transaction rows: grant (code A) + option
    exercise (code M). Parser preserves BOTH with their original codes;
    PR 3's cluster-detection logic filters on code ∈ {"S", "F"} but the
    cache layer holds the full data for audit."""
    filing = _FakeFiling(
        accession_no="grant_and_exercise",
        filing_date="2026-04-12",
        form="4",
        obj=_FakeOwnership(
            reporting_owners=_FakeReportingOwners(
                owners=[
                    _FakeOwner(
                        cik="0001000001",
                        name="DOE JOHN A",
                        is_director=False,
                        is_officer=True,
                        is_ten_pct_owner=False,
                        officer_title="CEO",
                    ),
                ],
            ),
            non_derivative_table=_FakeNonDerivativeTable(
                transactions=_FakeNonDerivativeTransactions(
                    _rows=[
                        _FakeTx(
                            date="2026-04-10",
                            transaction_code="A",  # grant
                            shares=5000.0,
                            price=None,  # grants typically have no price
                            remaining=43200.0,
                            acquired_disposed="A",
                        ),
                        _FakeTx(
                            date="2026-04-10",
                            transaction_code="M",  # option exercise
                            shares=2000.0,
                            price=85.0,
                            remaining=45200.0,
                            acquired_disposed="A",
                        ),
                    ]
                )
            ),
        ),
    )
    out = fetch_recent_form4("TST", filings_override=[filing])
    assert out is not None and len(out) == 2
    codes = {row["transaction_code"] for row in out}
    assert codes == {"A", "M"}
    # Grant has no price → dollar_value is None
    grant_row = next(r for r in out if r["transaction_code"] == "A")
    assert grant_row["price_per_share"] is None
    assert grant_row["dollar_value"] is None
    # Exercise has price → dollar_value computed
    exercise_row = next(r for r in out if r["transaction_code"] == "M")
    assert exercise_row["dollar_value"] == pytest.approx(2000.0 * 85.0)


def test_A4_filing_with_no_parsed_obj_returns_empty():
    """Defense — when edgartools fails to parse the Form 4 (obj=None),
    the row is dropped silently rather than raising."""
    filing = _FakeFiling(
        accession_no="unparseable",
        filing_date="2026-04-12",
        form="4",
        obj=None,
    )
    out = fetch_recent_form4("TST", filings_override=[filing])
    assert out == []


def test_A5_results_sorted_by_filing_date_desc():
    """Newest filing first in the output — required by PR 3's 30-day
    cluster-window logic + UI surface."""
    filings = [
        _ceo_sell(accession="old", filing_date="2026-01-01", cik="0001"),
        _ceo_sell(accession="new", filing_date="2026-05-01", cik="0002"),
        _ceo_sell(accession="mid", filing_date="2026-03-15", cik="0003"),
    ]
    out = fetch_recent_form4("TST", filings_override=filings)
    assert out is not None
    dates = [row["filing_date"] for row in out]
    assert dates == ["2026-05-01", "2026-03-15", "2026-01-01"]


# ---------------------------------------------------------------------------
# B. Form4Transaction dataclass round-trip
# ---------------------------------------------------------------------------


def test_B1_from_dict_round_trip():
    out = fetch_recent_form4("TST", filings_override=[_ceo_sell()])
    assert out and len(out) == 1
    tx = Form4Transaction.from_dict(out[0])
    assert tx is not None
    assert tx.insider_name == "DOE JOHN A"
    assert tx.is_officer is True
    assert tx.officer_title == "CEO"
    assert tx.transaction_code == "S"


def test_B2_from_dict_missing_required_field_returns_none():
    """Defensive — corrupted cache entries should not crash callers."""
    bad = {"accession": "x", "filing_date": "2026-04-12"}  # missing insider_name etc
    assert Form4Transaction.from_dict(bad) is None


def test_B3_from_dict_handles_none_price_and_shares():
    """Grants have shares but no price; some legacy cache rows may have
    both None. Round-trip must preserve the None."""
    tx = Form4Transaction.from_dict({
        "accession": "x",
        "filing_date": "2026-04-12",
        "insider_name": "DOE JOHN A",
        "insider_cik": "0001",
        "transaction_code": "A",
        "shares": 5000.0,
        "price_per_share": None,
        "dollar_value": None,
    })
    assert tx is not None
    assert tx.price_per_share is None
    assert tx.dollar_value is None


# ---------------------------------------------------------------------------
# C. Cache layer
# ---------------------------------------------------------------------------


def test_C1_cache_write_then_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    invalidate_cache("TST")  # ensure clean slate
    transactions = [
        {"accession": "a", "filing_date": "2026-04-12", "insider_cik": "0001"},
    ]
    form4_insider._cache_write("TST", FORM4_LOOKBACK_DAYS, transactions)
    cached = form4_insider._cache_read("TST", FORM4_LOOKBACK_DAYS)
    assert cached == transactions


def test_C2_cache_stale_after_ttl(tmp_path, monkeypatch):
    """Manually rewrite the cache with an old fetched_at — read should
    return None (treated as stale)."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    p = form4_insider._cache_path("TST")
    p.parent.mkdir(parents=True, exist_ok=True)
    stale_time = datetime.now(UTC) - timedelta(days=CACHE_TTL_DAYS + 1)
    import json as _json
    p.write_text(
        _json.dumps({
            "fetched_at": stale_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lookback_days": FORM4_LOOKBACK_DAYS,
            "transactions": [],
        }),
        encoding="utf-8",
    )
    assert form4_insider._cache_read("TST", FORM4_LOOKBACK_DAYS) is None


def test_C3_cache_invalidate_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    form4_insider._cache_write("TST", FORM4_LOOKBACK_DAYS, [])
    assert form4_insider._cache_path("TST").exists()
    invalidate_cache("TST")
    assert not form4_insider._cache_path("TST").exists()


# ---------------------------------------------------------------------------
# D. Drift detector — locks edgartools Form-4 public-API surface
# ---------------------------------------------------------------------------


def _attrs_of_class(cls) -> set[str]:
    """Return the union of ctor parameters + class-level attrs for a
    class. Dataclass fields show up via dir(cls) at the class level
    once the class is defined; ctor params cover __init__-assigned
    instance attrs that may not show on dir(cls)."""
    import inspect

    params: set[str] = set()
    try:
        params = set(inspect.signature(cls.__init__).parameters)
    except (TypeError, ValueError):
        pass
    return params | set(dir(cls))


def test_D1_edgar_form4_api_surface_locked():
    """Catch silent API drift on edgartools minor-version bumps.

    Walks the full parser chain (Filing → obj → Ownership →
    reporting_owners/non_derivative_table → Owner/NonDerivativeTransaction)
    against the four manifest tuples. Any rename on the upstream
    package fails this test loudly on PR review — preventing the
    silent-empty-output failure mode where the parser returns ``[]``
    for every live ticker and we discover it only after a PR-2 cron
    cycle.

    Skips when edgartools isn't installed (e.g., minimal CI environments).
    """
    try:
        from edgar import Filing
        from edgar.ownership import NonDerivativeTransaction, Ownership
        from edgar.ownership.ownershipforms import Owner
    except ImportError:
        pytest.skip("edgartools not installed")

    chain = [
        (Filing, _FORM4_REQUIRED_ATTRS),
        (Ownership, _OWNERSHIP_REQUIRED_ATTRS),
        (Owner, _OWNER_REQUIRED_ATTRS),
        (NonDerivativeTransaction, _NON_DERIVATIVE_TX_REQUIRED_ATTRS),
    ]
    for cls, manifest in chain:
        accepted = _attrs_of_class(cls)
        for attr_name in manifest:
            assert attr_name in accepted, (
                f"edgartools {cls.__name__} is missing expected attr "
                f"'{attr_name}' — either the public API drifted (edgartools "
                f"bump) or our manifest is wrong. Update the corresponding "
                f"_*_REQUIRED_ATTRS in form4_insider.py. "
                f"Available (first 25): {sorted(accepted)[:25]}"
            )


def test_D2_required_attrs_manifest_is_non_empty_and_tupled():
    """Internal invariant — the manifest must be a tuple (immutable) and
    cover at least the core (accession/date/form) trio."""
    assert isinstance(_FORM4_REQUIRED_ATTRS, tuple)
    assert len(_FORM4_REQUIRED_ATTRS) >= 3
    assert "accession_no" in _FORM4_REQUIRED_ATTRS
    assert "filing_date" in _FORM4_REQUIRED_ATTRS
    assert "form" in _FORM4_REQUIRED_ATTRS


# ---------------------------------------------------------------------------
# E. fetch_recent_form4 fallthrough paths
# ---------------------------------------------------------------------------


def test_E1_empty_override_returns_empty_list():
    """No filings in window → empty list (NOT None — None signals
    fetch failure)."""
    out = fetch_recent_form4("TST", filings_override=[])
    assert out == []


def test_E2_lookback_constant_is_180():
    """Pin the lookback constant. 2026-05-22 hotfix dropped from 365
    to 180 to fit the 45-min cron budget after the property→method
    parser fix made the per-filing ``obj()`` call actually do its
    HTTP round-trip (vs the pre-fix silent-fast-failure that "fit"
    in 18 min). Cohen-Malloy-Pomorski 2012 §3.1 used parallel 6m / 12m
    windows in their backtest, so 180d (≈ 6m) remains literature-
    anchored. Don't drop below 90 without re-checking the cold-start
    path."""
    assert FORM4_LOOKBACK_DAYS == 180


# ---------------------------------------------------------------------------
# F. edgartools 5.x property-→-method drift coverage (2026-05-22 hotfix)
# ---------------------------------------------------------------------------
#
# The first post-PR-#205 cron landed 0/502 insider transactions across
# the entire S&P 500 universe. Root cause: edgartools 5.x reclassified
# ``Filing.obj`` from a property to a method, so ``getattr(filing,
# "obj", None)`` returned the bound method (truthy) instead of the
# parsed Ownership object; the downstream ``getattr(parsed,
# "reporting_owners", None)`` on a bound method always returns ``None``
# and short-circuited ``return []`` on every filing.
#
# The existing A-E test suite used ``@dataclass`` ``_FakeFiling`` mocks
# with ``obj`` as a regular attribute — they exercise only the
# property-shape path. Tests below cover both:
#   F1 — synthetic callable-obj mock to lock the method-shape path
#   F2 — @network live-AAPL fetch that would have caught the bug on PR
#        review instead of after the first cron.


def test_F1_callable_obj_attribute_is_invoked_in_parser():
    """Mimic edgartools 5.x where ``filing.obj`` is a method that
    must be called. The parser must call it and use the returned
    Ownership view. Locks the ``callable()`` branch added in the
    2026-05-22 hotfix."""

    fake_ownership = _FakeOwnership(
        reporting_owners=_FakeReportingOwners(
            owners=[
                _FakeOwner(
                    cik="0001000099",
                    name="CALLABLE INSIDER",
                    is_director=False,
                    is_officer=True,
                    is_ten_pct_owner=False,
                    officer_title="CEO",
                )
            ]
        ),
        non_derivative_table=_FakeNonDerivativeTable(
            transactions=_FakeNonDerivativeTransactions(
                _rows=[
                    _FakeTx(
                        date="2026-04-10",
                        shares=5000.0,
                        price=100.0,
                        remaining=10000.0,
                        transaction_code="S",
                        acquired_disposed="D",
                    )
                ]
            )
        ),
    )

    class _CallableObjFiling:
        """Mimic edgartools 5.x ``Filing`` — ``obj`` is a method, not
        a property/attribute. ``callable(filing.obj)`` is True, and the
        parser must invoke it to reach the Ownership view."""

        accession_no = "callable-obj-test"
        filing_date = "2026-04-10"
        form = "4"
        filing_url = "https://www.sec.gov/test"

        def obj(self):
            return fake_ownership

    out = fetch_recent_form4("TST", filings_override=[_CallableObjFiling()])
    assert len(out) == 1, (
        "Parser silently dropped a Form 4 whose .obj is a method "
        "(edgartools 5.x shape). The 2026-05-22 hotfix added a "
        "callable() branch in _form4_to_transactions — this test "
        "locks it against regression."
    )
    # fetch_recent_form4 returns list[dict] (cache JSON shape);
    # Form4Transaction.from_dict() is the dataclass adapter.
    assert out[0]["insider_cik"] == "0001000099"
    assert out[0]["insider_name"] == "CALLABLE INSIDER"


@pytest.mark.network
def test_F2_live_aapl_returns_non_empty_insider_activity():
    """Live SEC EDGAR fetch — AAPL has hundreds of Form-4 insider
    transactions per year (officers + directors + 10% holders). A 365d
    window MUST return ≥ 1 transaction. This test would have caught
    the 2026-05-22 silent-drop incident on PR review.

    Requires ``EDGAR_USER_AGENT`` env var. Skips cleanly when offline
    via the ``@pytest.mark.network`` marker gate.
    """
    out = fetch_recent_form4("AAPL")
    assert out is not None, (
        "fetch_recent_form4 returned None for AAPL — fetch failed "
        "(EDGAR_USER_AGENT missing? 429 throttle? identity mis-set?)."
    )
    assert len(out) > 0, (
        f"fetch_recent_form4('AAPL') returned 0 transactions over 365d. "
        f"AAPL files dozens of Form 4s per year — this is the 2026-05-22 "
        f"silent-drop signature. Check whether edgartools released a "
        f"new major version that changed Filing.obj or get_filings() "
        f"semantics. Got: {out!r}"
    )
