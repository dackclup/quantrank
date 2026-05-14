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
        # Phase 3 fields — synthetic but plausible for AAPL FY2024.
        gross_profit=180_000_000_000.0,
        operating_income=120_000_000_000.0,
        cost_of_revenue=210_000_000_000.0,
        research_and_development=30_000_000_000.0,
        sga_expense=25_000_000_000.0,
        depreciation_and_amortization=12_000_000_000.0,
        interest_expense=4_000_000_000.0,
        income_tax_expense=15_000_000_000.0,
        income_before_tax=108_000_000_000.0,
        dividends_paid=15_000_000_000.0,
        current_assets=140_000_000_000.0,
        current_liabilities=130_000_000_000.0,
        inventory=7_000_000_000.0,
        accounts_receivable=30_000_000_000.0,
        accounts_payable=60_000_000_000.0,
        long_term_debt=80_000_000_000.0,
        short_term_debt=10_000_000_000.0,
        retained_earnings=20_000_000_000.0,
        ebitda=132_000_000_000.0,
        # Phase 3c fields — feed Tangible BVPS (Defense Playbook §PR 3c §2).
        # AAPL FY2024 actuals from EDGAR: goodwill ≈ $5.89B; intangibles ≈ $25.80B.
        goodwill=5_890_000_000.0,
        intangibles_net=25_800_000_000.0,
        # Phase 3e.1 — PPE net (Beneish M-score AQI + DEPI input).
        # AAPL FY2024 actual from EDGAR: PP&E net ≈ $45.68B.
        property_plant_equipment=45_680_000_000.0,
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


def test_annual_tags_have_legacy_fallback_coverage():
    """Regression guard against the 5.6%-coverage incident: the Beneish /
    Dechow prior-year tags must include legacy XBRL aliases still in heavy
    use by industrial / retail / energy filers. Without these, Beneish
    M-score populated for only 28 / 502 S&P 500 tickers on the first
    Phase 3e production run.
    """
    from compute.ingest.fundamentals import _ANNUAL_TAGS

    # cost_of_revenue must accept the legacy CostOfGoodsSold tag (~40% of
    # S&P 500 filers as of 2025 — biggest single gap).
    assert "us-gaap:CostOfGoodsSold" in _ANNUAL_TAGS["cost_of_revenue"]
    # accounts_receivable must accept ReceivablesNetCurrent (~10% filers).
    assert "us-gaap:ReceivablesNetCurrent" in _ANNUAL_TAGS["accounts_receivable"]
    # sga_expense must accept OperatingExpenses as last-resort proxy when
    # tech filers split S/M and G/A into separate lines.
    assert "us-gaap:OperatingExpenses" in _ANNUAL_TAGS["sga_expense"]
    # depreciation_and_amortization must accept the Depreciation-only tag
    # used by filers that report amortization separately.
    assert "us-gaap:Depreciation" in _ANNUAL_TAGS["depreciation_and_amortization"]


def test_ttm_flow_tags_replace_normalized_latest_for_income_statement():
    """Regression guard for audit #6 (deep clean, pre-v1.0): income-
    statement flow items must be fetched via `_TTM_FLOW_TAGS` (TTM-aware)
    NOT via `_NORMALIZED_LATEST` (single-period, broken for ~88% of
    tickers).

    Pre-fix bug: snap.eps_diluted came from normalized API and ranged
    from a single quarter (TSLA 0.13) to YTD (AAPL 4.85) to full annual
    (NVDA 4.90) depending on filer cadence. Same single-period problem
    for op_income, gross_profit, COGS, SGA, D&A, interest_expense, etc.
    """
    from compute.ingest.fundamentals import _NORMALIZED_LATEST, _TTM_FLOW_TAGS

    # Income-statement flow items MUST be in _TTM_FLOW_TAGS (NOT in
    # _NORMALIZED_LATEST anymore).
    flow_items_required_ttm = (
        "operating_income",
        "gross_profit",
        "cost_of_revenue",
        "sga_expense",
        "depreciation_and_amortization",
        "interest_expense",
        "income_tax_expense",
        "research_and_development",
        "income_before_tax",
        "dividends_paid",
    )
    for key in flow_items_required_ttm:
        assert key in _TTM_FLOW_TAGS, f"{key} must be in _TTM_FLOW_TAGS (TTM-aware)"
        assert key not in _NORMALIZED_LATEST, (
            f"{key} must NOT be in _NORMALIZED_LATEST anymore (single-period bug)"
        )

    # _NORMALIZED_LATEST should only contain EPS items (per-share, no
    # clean TTM-via-tag substitute).
    assert set(_NORMALIZED_LATEST.keys()) == {"eps_basic", "eps_diluted"}

    # interest_expense must include the modern operating/nonoperating
    # variants because the legacy `us-gaap:InterestExpense` froze post-
    # 2024 for many filers (AAPL, MSFT, JPM, TSLA all probed stale).
    assert "us-gaap:InterestExpenseOperating" in _TTM_FLOW_TAGS["interest_expense"]
    assert "us-gaap:InterestExpenseNonoperating" in _TTM_FLOW_TAGS["interest_expense"]


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


# -- Phase 3c: goodwill + intangibles fallback-chain coverage probe ----------
#
# Verifies the new _BALANCE_TAGS entries land non-null values via SEC EDGAR
# for a curated 5-ticker reference set spanning hardware (AAPL), consumer
# staples (KO, PG), bank (JPM), and financial conglomerate (BRK-B). The
# fallback chain for intangibles_net is intentionally probed: AAPL+PG tag
# under us-gaap:IntangibleAssetsNetExcludingGoodwill (primary); KO+JPM+BRK-B
# typically don't, so the fallback to us-gaap:OtherIntangibleAssetsNet must
# fire. We require ≥3/5 non-null on intangibles_net (vs the 2/5 seen with
# the primary tag alone) to assert the fallback chain actually improves
# coverage. Goodwill is uniformly tagged → all 5 must be non-null.

GOODWILL_INTANGIBLES_PROBE = {
    # ticker: (cik, sector_label)
    "AAPL":  ("0000320193", "hardware"),
    "KO":    ("0000021344", "staples"),
    "PG":    ("0000080424", "staples"),
    "JPM":   ("0000019617", "bank"),
    "BRK-B": ("0001067983", "financial_conglomerate"),
}


@pytest.mark.network
def test_goodwill_intangibles_fallback_chain():
    """Verify _BALANCE_TAGS goodwill + intangibles_net fallback hits SEC EDGAR.

    Probe rationale documented in PR-3c kickoff §D3 / §E2 — goodwill at 100%
    coverage, intangibles_net targeting ≥60% with the 3-tag fallback chain.
    """
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    set_identity(os.environ["EDGAR_USER_AGENT"])

    snapshots: dict[str, fundamentals_mod.FundamentalsSnapshot] = {}
    for ticker, (cik, _label) in GOODWILL_INTANGIBLES_PROBE.items():
        snap = fundamentals_mod._build_snapshot(ticker, cik)
        snapshots[ticker] = snap

    # 1. Goodwill: 5/5 non-null and economically plausible (each company has
    #    > $1B goodwill on book).
    goodwill_non_null = [t for t, s in snapshots.items() if s.goodwill is not None]
    assert len(goodwill_non_null) == 5, (
        f"Expected goodwill non-null for all 5 reference tickers; "
        f"got {goodwill_non_null}. Missing: "
        f"{[t for t in GOODWILL_INTANGIBLES_PROBE if t not in goodwill_non_null]}"
    )
    for ticker, snap in snapshots.items():
        assert snap.goodwill > 1e9, (
            f"{ticker} goodwill {snap.goodwill:,.0f} below $1B sanity floor"
        )

    # 2. Intangibles net (excluding goodwill): fallback chain must yield
    #    ≥3/5 non-null. Without the fallback chain only AAPL + PG would
    #    populate (2/5); the chain should add at least one more.
    intangibles_non_null = [
        t for t, s in snapshots.items() if s.intangibles_net is not None
    ]
    assert len(intangibles_non_null) >= 3, (
        f"Fallback chain coverage too low: only {len(intangibles_non_null)}/5 "
        f"tickers have non-null intangibles_net. Got: {intangibles_non_null}. "
        f"Expected at least AAPL + PG + 1 fallback hit."
    )
    for ticker in intangibles_non_null:
        assert snapshots[ticker].intangibles_net > 0, (
            f"{ticker} intangibles_net non-positive: {snapshots[ticker].intangibles_net}"
        )

    # 3. AAPL spot check (anchor against the E2 probe values within ±20%):
    #    goodwill ≈ $5.89B; intangibles_net ≈ $25.80B.
    aapl = snapshots["AAPL"]
    assert 4.5e9 <= aapl.goodwill <= 8.0e9, (
        f"AAPL goodwill {aapl.goodwill:,.0f} outside [4.5B, 8.0B] sanity band"
    )
    assert aapl.intangibles_net is not None and 20e9 <= aapl.intangibles_net <= 35e9, (
        f"AAPL intangibles_net {aapl.intangibles_net} outside [20B, 35B]"
    )
