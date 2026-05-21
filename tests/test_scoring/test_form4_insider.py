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
    CACHE_TTL_DAYS,
    FORM4_LOOKBACK_DAYS,
    Form4Transaction,
    fetch_recent_form4,
    invalidate_cache,
)

# ---------------------------------------------------------------------------
# Synthetic duck-typed Form 4 fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeTxRow:
    transaction_date: str
    transaction_code: str
    shares: float
    price_per_share: float | None
    shares_owned_following: float


@dataclass
class _FakeOwnershipObj:
    reporting_owner_name: str
    reporting_owner_cik: str
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    officer_title: str | None
    non_derivative_transactions: list[_FakeTxRow]


@dataclass
class _FakeFiling:
    accession_no: str
    filing_date: str
    form: str
    obj: _FakeOwnershipObj | None
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
        obj=_FakeOwnershipObj(
            reporting_owner_name=name,
            reporting_owner_cik=cik,
            is_director=False,
            is_officer=True,
            is_ten_percent_owner=False,
            officer_title=title,
            non_derivative_transactions=[
                _FakeTxRow(
                    transaction_date=transaction_date,
                    transaction_code="S",
                    shares=shares,
                    price_per_share=price,
                    shares_owned_following=38200.0,
                )
            ],
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
        obj=_FakeOwnershipObj(
            reporting_owner_name="DOE JOHN A",
            reporting_owner_cik="0001000001",
            is_director=False,
            is_officer=True,
            is_ten_percent_owner=False,
            officer_title="CEO",
            non_derivative_transactions=[
                _FakeTxRow(
                    transaction_date="2026-04-10",
                    transaction_code="A",  # grant
                    shares=5000.0,
                    price_per_share=None,  # grants typically have no price
                    shares_owned_following=43200.0,
                ),
                _FakeTxRow(
                    transaction_date="2026-04-10",
                    transaction_code="M",  # option exercise
                    shares=2000.0,
                    price_per_share=85.0,
                    shares_owned_following=45200.0,
                ),
            ],
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


def test_D1_edgar_form4_api_surface_locked():
    """Catch silent API drift on edgartools minor-version bumps.

    Scout-PR contract: every attribute in ``_FORM4_REQUIRED_ATTRS``
    must be either (a) a constructor parameter on ``Filing`` (most are
    instance attrs assigned in ``__init__``, NOT class-level
    attributes — so ``hasattr(Filing, '<attr>')`` returns False) or
    (b) a property / cached_property defined on the class.

    If a future edgartools bump renames any of them, this test fails
    LOUDLY on PR review — preventing a Sunday-night cron breakage.

    Skips when edgartools isn't installed (e.g., minimal CI environments).
    """
    try:
        from edgar import Filing
    except ImportError:
        pytest.skip("edgartools not installed")

    import inspect

    init_params = set(inspect.signature(Filing.__init__).parameters)
    class_attrs = set(dir(Filing))
    accepted = init_params | class_attrs

    for attr_name in _FORM4_REQUIRED_ATTRS:
        assert attr_name in accepted, (
            f"edgartools Filing class is missing expected attr '{attr_name}' — "
            f"either the public API drifted (edgartools bump) or our manifest "
            f"is wrong. Update _FORM4_REQUIRED_ATTRS in form4_insider.py. "
            f"Init params: {sorted(init_params)}. "
            f"Class attrs (first 20): {sorted(class_attrs)[:20]}"
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


def test_E2_lookback_constant_is_365():
    """Pin the lookback constant — PR 3's cluster detection needs ≥1y
    of history for the per-CEO baseline. Don't drop below 365 without
    re-checking the cold-start path."""
    assert FORM4_LOOKBACK_DAYS == 365
