"""Regression tests for Issue #288 — ``us-gaap:CommonStockSharesOutstanding``
missing from the XBRL fallback concept tuple in
``_fetch_shares_from_per_filing_xbrl``.

Bug: Prior to the fix (2026-05-28), the per-filing XBRL fallback only queried:

    ("dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesIssued")

Alphabet (GOOG / GOOGL) files per-class share counts ONLY under the
``us-gaap:CommonStockSharesOutstanding`` concept, NOT under the DEI cover-page
concept.  With the concept absent from the tuple, filter-mode lookups always
returned an empty DataFrame → function returned None → per_class_override
counter remained 0 → the aggregate share count (inflated 2×) was used for
market-cap display.

Fix: ``"us-gaap:CommonStockSharesOutstanding"`` inserted between the two
existing concepts (matching the primary path at ``fundamentals.py:125-134``).

These tests exercise ``_fetch_shares_from_per_filing_xbrl`` internals
directly via synthetic XBRL fixtures — they do NOT mock the function itself.
That gap in the prior test suite is exactly why the bug survived to production.

All tests are offline — no ``@pytest.mark.network``.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

# ---------------------------------------------------------------------------
# Synthetic XBRL fixture builders
# ---------------------------------------------------------------------------

# Alphabet share counts from the 2026-05-28 edgar-debugger live probe:
_GOOGL_CLASS_A_SHARES = 5_822_000_000  # us-gaap:CommonClassAMember
_GOOG_CLASS_C_SHARES = 5_429_000_000   # goog:CapitalClassCMember
_CLASS_B_SHARES = 837_000_000          # us-gaap:CommonClassBMember (not traded)

# Context refs (arbitrary stable IDs mirroring real XBRL context naming)
_CTX_CLASS_A = "FY2024_ClassA"
_CTX_CLASS_C = "FY2024_ClassC"
_CTX_CLASS_B = "FY2024_ClassB"


class _FakeContext:
    """Minimal context object with a .dimensions dict."""

    def __init__(self, class_member: str) -> None:
        self.dimensions = {"us-gaap:StatementClassOfStockAxis": class_member}


class _FakeFactsView:
    """Synthetic XBRL facts view.

    Mimics edgartools' ``XBRLFacts.get_facts_by_concept`` return shape.

    - ``us-gaap:CommonStockSharesOutstanding`` → 3 dimensional rows (Class A,
      Class C, Class B) with ``numeric_value``, ``period_instant``, and
      ``context_ref`` columns.
    - ``dei:EntityCommonStockSharesOutstanding`` → empty DataFrame (Alphabet
      files this concept only non-dimensionally, so aggregate is wrong; in
      the synthetic fixture we simply return empty to model the zero-hit case).
    - ``us-gaap:CommonStockSharesIssued`` → empty DataFrame.
    - Any other concept → empty DataFrame.
    """

    _PERIOD = date(2025, 12, 31)

    def get_facts_by_concept(self, concept_name: str) -> pd.DataFrame:
        if concept_name == "us-gaap:CommonStockSharesOutstanding":
            return pd.DataFrame(
                [
                    {
                        "numeric_value": float(_GOOGL_CLASS_A_SHARES),
                        "period_instant": self._PERIOD,
                        "context_ref": _CTX_CLASS_A,
                    },
                    {
                        "numeric_value": float(_GOOG_CLASS_C_SHARES),
                        "period_instant": self._PERIOD,
                        "context_ref": _CTX_CLASS_C,
                    },
                    {
                        "numeric_value": float(_CLASS_B_SHARES),
                        "period_instant": self._PERIOD,
                        "context_ref": _CTX_CLASS_B,
                    },
                ]
            )
        # DEI cover-page concept + CommonStockSharesIssued both return empty
        # for Alphabet (modelling the real filing shape where only the
        # us-gaap balance-sheet concept carries dimensional rows).
        return pd.DataFrame()


class _FakeXBRL:
    """Minimal XBRL object wiring facts + contexts together."""

    def __init__(self) -> None:
        self.facts = _FakeFactsView()
        self.contexts = {
            _CTX_CLASS_A: _FakeContext("us-gaap:CommonClassAMember"),
            _CTX_CLASS_C: _FakeContext("goog:CapitalClassCMember"),
            _CTX_CLASS_B: _FakeContext("us-gaap:CommonClassBMember"),
        }


def _make_fake_filing(xbrl_obj: _FakeXBRL) -> MagicMock:
    """Return a filing mock whose .xbrl() returns the provided fixture."""
    filing = MagicMock()
    filing.xbrl.return_value = xbrl_obj
    filing.form = "10-K"
    filing.filing_date = date(2026, 2, 4)
    return filing


def _make_company_with_xbrl(xbrl_obj: _FakeXBRL) -> MagicMock:
    """Return a company mock that exposes the XBRL fixture via get_filings."""
    filing = _make_fake_filing(xbrl_obj)

    filings_stub = MagicMock()
    filings_stub.head.return_value = [filing]

    company = MagicMock()
    company.get_filings.return_value = filings_stub
    return company


# ---------------------------------------------------------------------------
# Test 1 — GOOG Class C filter-mode (the regression case)
#
# Pre-fix: concept tuple was ("dei:...", "us-gaap:CommonStockSharesIssued")
# → get_facts_by_concept never returned dimensional rows → function returned None.
# Post-fix: "us-gaap:CommonStockSharesOutstanding" is in the tuple → rows found
# → filter matches goog:CapitalClassCMember → returns 5_429_000_000.
# ---------------------------------------------------------------------------


def test_xbrl_fallback_filter_mode_returns_GOOG_class_C_shares():
    """Issue #288 regression: GOOG Class C shares recoverable via XBRL fallback.

    FAILS on pre-fix code (concept missing → empty result → None returned).
    PASSES on post-fix code (concept present → filter match → 5_429_000_000).
    """
    from compute.ingest.fundamentals import _fetch_shares_from_per_filing_xbrl

    xbrl = _FakeXBRL()
    company = _make_company_with_xbrl(xbrl)

    result = _fetch_shares_from_per_filing_xbrl(
        company,
        ticker="GOOG",
        target_class_member="goog:CapitalClassCMember",
    )

    assert result == float(_GOOG_CLASS_C_SHARES), (
        f"Expected {_GOOG_CLASS_C_SHARES:,} (GOOG Class C), got {result}. "
        "This failure indicates 'us-gaap:CommonStockSharesOutstanding' is missing "
        "from the XBRL fallback concept tuple (Issue #288 regression)."
    )


# ---------------------------------------------------------------------------
# Test 2 — GOOGL Class A filter-mode
#
# Same structural path as GOOG but using the standard us-gaap namespace member.
# ---------------------------------------------------------------------------


def test_xbrl_fallback_filter_mode_returns_GOOGL_class_A_shares():
    """Issue #288 regression: GOOGL Class A shares recoverable via XBRL fallback.

    FAILS on pre-fix code (concept missing → None).
    PASSES on post-fix code (filter match on us-gaap:CommonClassAMember → 5_822_000_000).
    """
    from compute.ingest.fundamentals import _fetch_shares_from_per_filing_xbrl

    xbrl = _FakeXBRL()
    company = _make_company_with_xbrl(xbrl)

    result = _fetch_shares_from_per_filing_xbrl(
        company,
        ticker="GOOGL",
        target_class_member="us-gaap:CommonClassAMember",
    )

    assert result == float(_GOOGL_CLASS_A_SHARES), (
        f"Expected {_GOOGL_CLASS_A_SHARES:,} (GOOGL Class A), got {result}. "
        "This failure indicates 'us-gaap:CommonStockSharesOutstanding' is missing "
        "from the XBRL fallback concept tuple (Issue #288 regression)."
    )


# ---------------------------------------------------------------------------
# Test 3 — Concept tuple pin (explicit regression guard against re-omission)
#
# The tuple at fundamentals.py:746-760 must contain all 3 concepts in
# the same order as the primary path (fundamentals.py:125-134).
# ---------------------------------------------------------------------------


def test_xbrl_fallback_concept_tuple_includes_us_gaap_outstanding():
    """Drift-detector: the XBRL fallback concept tuple must include all 3 concepts.

    This test introspects the production code's concept loop by observing
    which concept names are passed to get_facts_by_concept during a call.
    It asserts that at least:
        - "dei:EntityCommonStockSharesOutstanding"
        - "us-gaap:CommonStockSharesOutstanding"
        - "us-gaap:CommonStockSharesIssued"
    are all queried — the exact order and superset are acceptable.

    FAILS on pre-fix code ("us-gaap:CommonStockSharesOutstanding" was absent).
    PASSES on post-fix code (all 3 concepts present in the tuple).
    """
    from compute.ingest.fundamentals import _fetch_shares_from_per_filing_xbrl

    queried_concepts: list[str] = []

    class _TrackingFactsView(_FakeFactsView):
        def get_facts_by_concept(self, concept_name: str) -> pd.DataFrame:
            queried_concepts.append(concept_name)
            return pd.DataFrame()  # always empty — we only care about what's queried

    xbrl = _FakeXBRL()
    xbrl.facts = _TrackingFactsView()
    company = _make_company_with_xbrl(xbrl)

    # Run in sum-all mode (no target_class_member) so the loop exhausts all concepts
    _fetch_shares_from_per_filing_xbrl(company, ticker="TEST")

    required = {
        "dei:EntityCommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesIssued",
    }
    missing = required - set(queried_concepts)
    assert not missing, (
        f"Concept(s) missing from XBRL fallback tuple: {missing}. "
        "The tuple must match the primary path at fundamentals.py:125-134. "
        "This is the Issue #288 regression guard — do not remove concepts."
    )


# ---------------------------------------------------------------------------
# Test 4 — per_class_attempt counter increments on Branch 3 entry
#
# Pre-fix: _FALLBACK_STATS did NOT include "per_class_attempt" as a key
# (it was added in the same commit that fixed the concept tuple).
# A KeyError on get_fallback_stats()["per_class_attempt"] signals pre-fix.
#
# Post-fix: Branch 3 increments per_class_attempt BEFORE the XBRL call,
# so attempt==1 even when XBRL returns None; override==1 when XBRL succeeds.
# ---------------------------------------------------------------------------


def test_per_class_attempt_increments_on_branch_3_entry():
    """Issue #288: per_class_attempt counter increments when Branch 3 is entered.

    Two sub-assertions:
      (a) per_class_attempt == 1 after one Branch-3 entry (regardless of XBRL result)
      (b) per_class_override == 1 when XBRL succeeds and per_class < primary

    Pre-fix failure mode: KeyError on get_fallback_stats()["per_class_attempt"]
    (key did not exist in _FALLBACK_STATS before Issue #288 fix).
    Post-fix: both counters increment correctly.
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 12_120_000_000.0    # Alphabet aggregate (triggers Branch 3 for GOOG)
    per_class = _GOOG_CLASS_C_SHARES  # 5.43B < primary → override fires

    # Use the existing _make_facts_stub + _make_company_stub helpers from the
    # sibling test module rather than re-implementing them here, to keep the
    # fixture surface lean. We import them from the module-level namespace by
    # re-reading from the package rather than cross-importing from a test file.
    from tests.test_ingest.test_fundamentals import (
        _make_company_stub,
        _make_facts_stub,
    )

    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=float(per_class),
        ),
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    stats = get_fallback_stats()

    # (a) Attempt counter — key must exist (pre-fix: KeyError here)
    assert "per_class_attempt" in stats, (
        "per_class_attempt key missing from _FALLBACK_STATS — "
        "Issue #288 pre-fix state detected."
    )
    assert stats["per_class_attempt"] == 1, (
        f"Expected per_class_attempt=1, got {stats['per_class_attempt']}. "
        "Branch 3 was not entered or counter not wired."
    )

    # (b) Override counter — XBRL succeeded and per_class < primary
    assert stats["per_class_override"] == 1, (
        f"Expected per_class_override=1, got {stats['per_class_override']}."
    )

    # (c) Snapshot reflects the per-class value, not the aggregate
    assert snapshot.shares_outstanding == float(per_class)
