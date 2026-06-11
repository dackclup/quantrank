"""RATIFY-B coverage tests — Issue #374 share-count fix.

RATIFY-B revert (2026-06-11): ``FundamentalsSnapshot.shares_outstanding``
now holds the SEC companyfacts COMPANY-TOTAL aggregate (class-invariant)
instead of the listed ticker's per-class count.  The per-class value moved
to the new additive field ``shares_outstanding_listed_class`` on both
``FundamentalsSnapshot`` (ingest) and ``RawMetrics`` (output schema).

Series-consistency: NSI (_net_stock_issuance) and the Dechow issuance
dummy read share-count history that is ALSO the companyfacts aggregate, so
the revert eliminates the spurious ln(5.4B / 12.1B) ≈ −0.80 collapse signal
that GOOG/GOOGL triggered pre-fix.

All tests are offline — no ``@pytest.mark.network``.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from compute import config

# ---------------------------------------------------------------------------
# Fixtures / helpers (re-use the builder pattern from test_fundamentals.py)
# ---------------------------------------------------------------------------

def _make_facts_stub(
    *,
    shares_outstanding: float | None,
    revenue: float = 5_000_000_000.0,
    total_assets: float = 10_000_000_000.0,
) -> MagicMock:
    """Minimal EntityFacts stub sufficient to drive _build_snapshot into
    the Branch-3 per-class path.  Mirrors _make_facts_stub in
    test_fundamentals.py — kept local to avoid cross-test-module import
    coupling (the sibling is not a public fixture module)."""
    from datetime import date as _date

    def make_fact(value, period_end=_date(2025, 12, 31), filing_date=_date(2026, 2, 15)):
        return SimpleNamespace(value=value, period_end=period_end, filing_date=filing_date)

    def get_fact(tag):
        if tag == "us-gaap:Assets":
            return make_fact(total_assets)
        if tag in (
            "dei:EntityCommonStockSharesOutstanding",
            "us-gaap:CommonStockSharesOutstanding",
            "us-gaap:CommonStockSharesIssued",
            "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
            "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
        ):
            return make_fact(shares_outstanding) if shares_outstanding is not None else None
        return None

    def get_ttm(tag):
        from datetime import date as _date
        recent_pe = _date(2025, 12, 31)
        recent_fd = _date(2026, 2, 15)
        if "Revenue" in tag or "SalesRevenue" in tag or "RevenueFrom" in tag:
            pf = SimpleNamespace(period_end=recent_pe, filing_date=recent_fd)
            return SimpleNamespace(value=revenue, period_facts=[pf])
        if "NetCash" in tag:
            pf = SimpleNamespace(period_end=recent_pe, filing_date=recent_fd)
            return SimpleNamespace(value=1_000_000_000.0, period_facts=[pf])
        return None

    facts = MagicMock()
    facts.get_fact.side_effect = get_fact
    facts.get_ttm.side_effect = get_ttm
    facts.get_concept.return_value = None
    facts._suppress_warnings = False
    return facts


def _make_company_stub(facts_stub: MagicMock) -> MagicMock:
    company = MagicMock()
    company.get_facts.return_value = facts_stub
    return company


# ---------------------------------------------------------------------------
# Task B.1 — GOOG cold path: aggregate retained, per_class captured
# ---------------------------------------------------------------------------


def test_ratifyb_goog_aggregate_retained_in_shares_outstanding():
    """GOOG cold path: primary=12.12B aggregate, per-class filter returns
    5.43B (Class C).  RATIFY-B contract:
    - ``shares_outstanding`` == 12.12B (company-total, class-invariant)
    - ``shares_outstanding_listed_class`` == 5.43B (Class C per-class)
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "GOOG" in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST

    reset_fallback_stats()
    primary = 12_120_000_000.0   # Alphabet aggregate (3-class sum)
    per_class_c = 5_429_000_000.0  # Class C (GOOG)
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=per_class_c,
        ),
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    # Aggregate is class-invariant and must not be replaced by per-class
    assert snapshot.shares_outstanding == primary
    # Per-class value captured in the new additive field
    assert snapshot.shares_outstanding_listed_class == per_class_c
    # Branch-3 fired
    assert get_fallback_stats()["per_class_override"] == 1


# ---------------------------------------------------------------------------
# Task B.2 — GOOGL cold path: aggregate retained, per_class A captured
# ---------------------------------------------------------------------------


def test_ratifyb_googl_aggregate_retained_in_shares_outstanding():
    """GOOGL cold path: primary=12.12B aggregate, per-class filter returns
    5.82B (Class A standard namespace).  RATIFY-B contract:
    - ``shares_outstanding`` == 12.12B (company-total, class-invariant)
    - ``shares_outstanding_listed_class`` == 5.82B (Class A per-class)
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "GOOGL" in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST

    reset_fallback_stats()
    primary = 12_120_000_000.0
    per_class_a = 5_822_000_000.0  # Class A (GOOGL)
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=per_class_a,
        ),
    ):
        snapshot = _build_snapshot("GOOGL", "0001652044")

    assert snapshot.shares_outstanding == primary
    assert snapshot.shares_outstanding_listed_class == per_class_a
    assert get_fallback_stats()["per_class_override"] == 1


# ---------------------------------------------------------------------------
# Task B.3 — Non-allowlist ticker: listed_class stays None
# ---------------------------------------------------------------------------


def test_ratifyb_non_allowlist_ticker_listed_class_is_none():
    """Regression guard: AAPL is not in MULTI_CLASS_OVERCOUNT_ALLOWLIST,
    so Branch 3 must NOT be entered.  ``shares_outstanding_listed_class``
    must be None (the field's zero-value for non-MULTI_CLASS tickers).
    ``shares_outstanding`` passes through unchanged from primary.
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "AAPL" not in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST

    reset_fallback_stats()
    primary = 15_204_000_000.0
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("AAPL", "0000320193")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == primary
    # The new additive field must be None for non-allowlist tickers
    assert snapshot.shares_outstanding_listed_class is None
    assert get_fallback_stats()["per_class_override"] == 0


def test_ratifyb_non_allowlist_ticker_listed_class_none_msft():
    """Second non-allowlist case (MSFT) — guards against accidental
    allowlist expansion widening the branch to single-class stocks."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        reset_fallback_stats,
    )

    assert "MSFT" not in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST

    reset_fallback_stats()
    primary = 7_400_000_000.0
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("MSFT", "0000789019")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == primary
    assert snapshot.shares_outstanding_listed_class is None


# ---------------------------------------------------------------------------
# Task B.4 — _build_raw_metrics wiring: listed_class propagates to RawMetrics
# ---------------------------------------------------------------------------


def test_ratifyb_build_raw_metrics_passes_listed_class_through():
    """``_build_raw_metrics`` must wire ``snapshot.shares_outstanding_listed_class``
    into the produced ``RawMetrics.shares_outstanding_listed_class`` field.
    This is the plumbing test: compute/main.py line 386.
    """
    from compute.ingest.fundamentals import FundamentalsSnapshot
    from compute.main import _build_raw_metrics

    snap = FundamentalsSnapshot(
        ticker="GOOG",
        cik="0001652044",
        shares_outstanding=12_120_000_000.0,       # company-total aggregate
        shares_outstanding_listed_class=5_429_000_000.0,  # Class C per-class
        net_income=80_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 15),
    )

    rm = _build_raw_metrics(snap, current_price=175.0)

    assert rm.shares_outstanding == 12_120_000_000.0
    assert rm.shares_outstanding_listed_class == 5_429_000_000.0


def test_ratifyb_build_raw_metrics_listed_class_none_for_non_allowlist():
    """For a non-MULTI_CLASS ticker the snapshot carries ``shares_outstanding_listed_class=None``
    (never entered Branch 3), and ``_build_raw_metrics`` must propagate None."""
    from compute.ingest.fundamentals import FundamentalsSnapshot
    from compute.main import _build_raw_metrics

    snap = FundamentalsSnapshot(
        ticker="AAPL",
        cik="0000320193",
        shares_outstanding=15_204_000_000.0,
        shares_outstanding_listed_class=None,    # non-allowlist — stays None
        net_income=94_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 15),
    )

    rm = _build_raw_metrics(snap, current_price=220.0)

    assert rm.shares_outstanding == 15_204_000_000.0
    assert rm.shares_outstanding_listed_class is None


# ---------------------------------------------------------------------------
# Task B.5 — Series-consistency: NSI uses aggregate, no spurious spike
# ---------------------------------------------------------------------------


_NSI_TODAY = date(2026, 5, 9)  # deterministic clock, mirrors test_risk_overlay.py


def _history_with_shares(prior_shares: float, *, years_ago: int = 1) -> pd.DataFrame:
    """Build a minimal annual history DataFrame with one shares_outstanding row.
    The history metric 'shares_outstanding' represents the SEC companyfacts
    aggregate (same basis as snapshot.shares_outstanding after RATIFY-B)."""
    period_end = _NSI_TODAY - timedelta(days=365 * years_ago)
    return pd.DataFrame(
        [
            {
                "fiscal_year": _NSI_TODAY.year - years_ago,
                "metric": "shares_outstanding",
                "value": prior_shares,
                "period_end": period_end,
                "filing_date": period_end + timedelta(days=60),
                "form_type": "10-K",
            }
        ]
    )


def test_ratifyb_nsi_uses_aggregate_no_spurious_spike():
    """Series-consistency invariant (Issue #374 RATIFY-B).

    Pre-fix: snapshot.shares_outstanding = per_class (~5.4B) while history
    contains the companyfacts aggregate (~12.1B).  NSI = ln(5.4B/12.1B)
    ≈ −0.80 — a spurious share-buyback/collapse signal that can trigger the
    NSI veto on GOOG/GOOGL.

    Post-fix: snapshot.shares_outstanding = aggregate (12.1B).  NSI compares
    aggregate_t / aggregate_{t-1}, eliminating the cross-basis mismatch.
    When Alphabet's true share count was approximately stable year-over-year,
    NSI should be close to 0.0 (within ±0.15 for modest organic changes),
    NOT near −0.80.

    This test constructs a GOOG-like scenario where the company had
    12.0B aggregate shares a year ago and 12.12B today (≈+1% — realistic
    slow dilution).  Expected NSI ≈ ln(12.12B / 12.0B) ≈ 0.010; the
    spurious pre-fix value of ln(5.4B / 12.0B) ≈ −0.80 must NOT appear.
    """
    from compute.ingest.fundamentals import FundamentalsSnapshot
    from compute.scoring.risk_overlay import _net_stock_issuance

    aggregate_now = 12_120_000_000.0
    aggregate_prior = 12_000_000_000.0  # ~1% growth year-over-year
    per_class_c = 5_429_000_000.0        # Class C — what pre-fix put in shares_outstanding

    # RATIFY-B snapshot: shares_outstanding = aggregate (class-invariant)
    snap = FundamentalsSnapshot(
        ticker="GOOG",
        cik="0001652044",
        shares_outstanding=aggregate_now,              # post-fix: aggregate
        shares_outstanding_listed_class=per_class_c,   # additive field only
        net_income=80_000_000_000.0,
        revenue=300_000_000_000.0,
        total_assets=400_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 15),
    )

    # History contains the aggregate as well (companyfacts aggregate path)
    history = _history_with_shares(aggregate_prior)

    nsi = _net_stock_issuance(snap, history, today=_NSI_TODAY)

    # Post-fix: NSI ≈ ln(12.12B / 12.0B) ≈ 0.010 — near-zero, correct
    expected_nsi = math.log(aggregate_now / aggregate_prior)
    assert nsi == pytest.approx(expected_nsi, rel=1e-6)

    # Regression guard: the pre-fix spurious spike is nowhere near the result
    spurious_pre_fix_nsi = math.log(per_class_c / aggregate_prior)  # ≈ −0.80
    # The correct NSI must differ from the spurious one by at least 0.5
    assert abs(nsi - spurious_pre_fix_nsi) > 0.5, (
        f"NSI {nsi:.4f} is suspiciously close to the pre-fix spurious value "
        f"{spurious_pre_fix_nsi:.4f}; check that shares_outstanding = aggregate."
    )
