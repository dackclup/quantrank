"""Fundamentals fetcher tests.

Two layers:

1. Offline tests covering caching, freshness, and the snapshot helpers — fast,
   deterministic, run on every CI.
2. ``@pytest.mark.network`` golden-value tests for 5 reference tickers
   (AAPL/MSFT/GOOGL/JPM/XOM). Skipped in CI by default; run on demand via
   ``pytest --run-network``.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from compute import config
from compute.ingest import fundamentals as fundamentals_mod
from compute.ingest.fundamentals import (
    ALL_METRIC_KEYS,
    FundamentalsSnapshot,
    _is_fresh,
    _load_cached,
    _require_identity,
    _save_cached,
)


def _snapshot(latest: date, **overrides) -> FundamentalsSnapshot:
    base = dict(
        ticker="AAPL",
        cik="0000320193",
        revenue=391_000_000_000.0,
        net_income=93_000_000_000.0,
        total_assets=365_000_000_000.0,
        total_liabilities=290_000_000_000.0,
        stockholders_equity=75_000_000_000.0,
        cash=29_000_000_000.0,
        operating_cash_flow=120_000_000_000.0,
        capex=10_000_000_000.0,
        free_cash_flow=110_000_000_000.0,
        eps_basic=6.10,
        eps_diluted=6.05,
        shares_outstanding=15_000_000_000.0,
        latest_filed_date=latest,
        latest_period_end=date(latest.year, 9, 28),
    )
    base.update(overrides)
    return FundamentalsSnapshot(**base)


def test_is_fresh_within_45_days():
    snap = _snapshot(latest=date(2026, 5, 1))
    assert _is_fresh(snap, today=date(2026, 6, 1)) is True


def test_is_fresh_outside_45_days():
    snap = _snapshot(latest=date(2026, 1, 1))
    assert _is_fresh(snap, today=date(2026, 6, 1)) is False


def test_is_fresh_handles_missing_filed_date():
    snap = _snapshot(latest=date(2026, 5, 1), latest_filed_date=None)
    assert _is_fresh(snap, today=date(2026, 6, 1)) is False


def test_missing_fields_for_fully_populated_snapshot():
    snap = _snapshot(latest=date(2026, 5, 1))
    assert snap.missing_fields() == []


def test_missing_fields_marks_nones():
    snap = _snapshot(latest=date(2026, 5, 1), revenue=None, capex=None)
    missing = snap.missing_fields()
    assert "revenue" in missing
    assert "capex" in missing
    assert "net_income" not in missing


def test_all_metric_keys_match_snapshot_fields():
    """Make sure the public ALL_METRIC_KEYS tuple stays in sync with the dataclass."""
    snap = _snapshot(latest=date(2026, 5, 1))
    record = snap.to_record()
    for key in ALL_METRIC_KEYS:
        assert key in record, f"ALL_METRIC_KEYS lists {key!r} but it's not on the snapshot"


def test_cache_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    snap = _snapshot(latest=date(2026, 5, 1))
    _save_cached(snap)
    loaded = _load_cached(snap.cik)
    assert loaded is not None
    assert loaded.revenue == snap.revenue
    assert loaded.latest_filed_date == snap.latest_filed_date
    assert loaded.eps_diluted == snap.eps_diluted


def test_cache_load_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    assert _load_cached("9999999999") is None


def test_require_identity_rejects_missing(monkeypatch):
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="EDGAR_USER_AGENT"):
        _require_identity()


def test_fetch_fundamentals_uses_cache(monkeypatch, tmp_path):
    """Fresh-cache hit must NOT call ``_build_snapshot``."""
    monkeypatch.setattr(config, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    monkeypatch.setenv("EDGAR_USER_AGENT", "test test@example.com")
    monkeypatch.setattr(fundamentals_mod, "set_identity", lambda *a, **kw: None)

    snap = _snapshot(latest=date.today() - timedelta(days=10))  # fresh
    _save_cached(snap)

    def boom(*args, **kwargs):
        raise AssertionError("EDGAR fetch should not be called when cache is fresh")

    monkeypatch.setattr(fundamentals_mod, "_build_snapshot", boom)
    out = fundamentals_mod.fetch_fundamentals("AAPL", snap.cik)
    assert out is not None
    assert out.revenue == snap.revenue


def test_fetch_fundamentals_skips_stale_cache(monkeypatch, tmp_path):
    """Stale-cache miss MUST trigger a fresh ``_build_snapshot`` call."""
    monkeypatch.setattr(config, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    monkeypatch.setenv("EDGAR_USER_AGENT", "test test@example.com")
    monkeypatch.setattr(fundamentals_mod, "set_identity", lambda *a, **kw: None)

    # Stale: filed >100 days ago; refetch threshold is 45.
    stale = _snapshot(latest=date.today() - timedelta(days=120))
    _save_cached(stale)

    fresh = _snapshot(
        latest=date.today() - timedelta(days=5),
        revenue=stale.revenue + 1_000_000_000,
    )
    monkeypatch.setattr(fundamentals_mod, "_build_snapshot", lambda *a, **kw: fresh)

    out = fundamentals_mod.fetch_fundamentals("AAPL", stale.cik)
    assert out is not None
    assert out.revenue == fresh.revenue


# -- @network golden-value tests --------------------------------------------

GOLDEN_FY2024_REVENUE = {
    # ticker: (cik, expected_revenue_USD, tolerance_pct)
    "AAPL":  ("0000320193", 391_035_000_000, 0.01),
    "MSFT":  ("0000789019", 245_122_000_000, 0.02),
    "GOOGL": ("0001652044", 350_018_000_000, 0.02),
    "JPM":   ("0000019617", 177_421_000_000, 0.05),  # JPM revenue calc varies more across taxonomies
    "XOM":   ("0000034088", 339_247_000_000, 0.02),
}


@pytest.mark.network
@pytest.mark.parametrize("ticker", list(GOLDEN_FY2024_REVENUE.keys()))
def test_fy2024_revenue_within_tolerance(ticker):
    """Verify EDGAR returns the expected FY2024 revenue for reference tickers."""
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import Company, set_identity
    set_identity(os.environ["EDGAR_USER_AGENT"])

    cik, expected, tol = GOLDEN_FY2024_REVENUE[ticker]
    facts = Company(cik).get_facts()

    # Try the most common revenue tags in priority order.
    candidate_tags = [
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
    ]
    fact = None
    for tag in candidate_tags:
        f = facts.get_annual_fact(tag, fiscal_year=2024)
        if f is not None and f.value is not None:
            fact = f
            break
    assert fact is not None, f"No FY2024 revenue fact for {ticker}"
    diff = abs(float(fact.value) - expected) / expected
    assert diff < tol, (
        f"{ticker} FY2024 revenue {fact.value:,.0f} differs from expected "
        f"{expected:,.0f} by {diff*100:.2f}% (tolerance {tol*100:.0f}%)"
    )
