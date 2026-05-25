"""Tests for the Issue #246 ERIE fix in compute.ingest.fundamentals.

Exercises the extended fallback trigger in ``_build_snapshot`` that fires
when the primary ``shares_outstanding`` value is implausibly low (below
``config.MIN_PLAUSIBLE_SHARE_COUNT = 100_000``), in addition to the
original PR #182 trigger when the primary value is ``None``.

ERIE pattern: SEC ``companyfacts`` aggregate API filtered out dimensional
Class A facts (54.9M shares) and returned only Class B (2,541 shares),
producing ``primary_shares = 2_542``.  The old strict ``is None`` guard
did NOT fire; the new ``< MIN_PLAUSIBLE_SHARE_COUNT`` branch catches it.

All tests are offline (no live SEC fetch).  The ``@pytest.mark.network``
live drift-detector for ERIE is at the bottom of the file.

Mocking pattern: ``unittest.mock.patch`` on the fully-qualified names
``compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl`` and
``compute.ingest.fundamentals.Company``, matching the existing style in
``test_fundamentals_xbrl_fallback.py`` (which patches Company at the same
module scope) and ``test_cross_source.py`` (which uses unittest.mock.patch
throughout).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from compute import config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_facts_stub(
    *,
    shares_outstanding: float | None,
    revenue: float = 5_000_000_000.0,
    total_assets: float = 10_000_000_000.0,
) -> MagicMock:
    """Return a minimal ``EntityFacts`` stub whose ``get_fact`` + ``get_ttm`` +
    ``get_concept`` calls answer with values that make ``_build_snapshot``
    reach the fallback decision block.

    Only the fields that the fallback trigger gate inspects are rigorously
    controlled (revenue, total_assets, shares_outstanding).  All other
    concepts return ``None`` so the snapshot fields are None except for
    the three above — this is fine because we assert only on
    ``snapshot.shares_outstanding``.
    """
    from datetime import date as _date

    def make_fact(value, period_end=_date(2025, 12, 31), filing_date=_date(2026, 2, 15)):
        f = SimpleNamespace(
            value=value,
            period_end=period_end,
            filing_date=filing_date,
        )
        return f

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
            if shares_outstanding is None:
                return None
            return make_fact(shares_outstanding)
        return None

    def get_ttm(tag):
        # Revenue lives here (via _try_ttm_max_fresh which calls get_ttm
        # for the tag chain).  Return a simple TTM stub with period_facts.
        # ``_try_ttm_max_fresh`` inspects pf.period_end for staleness gating
        # (cutoff = today - 540d) and pf.filing_date for snapshot_dates.
        # Both must be present and recent so the revenue value is accepted.
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

    def get_concept(concept, return_metadata=False):
        return None

    facts = MagicMock()
    facts.get_fact.side_effect = get_fact
    facts.get_ttm.side_effect = get_ttm
    facts.get_concept.side_effect = get_concept
    # Suppress edgartools warning suppression attribute (non-fatal)
    facts._suppress_warnings = False
    return facts


def _make_company_stub(facts_stub: MagicMock) -> MagicMock:
    """Wrap ``facts_stub`` in a Company-shaped mock."""
    company = MagicMock()
    company.get_facts.return_value = facts_stub
    return company


# ---------------------------------------------------------------------------
# Branch coverage: fallback fires on implausibly-low primary (ERIE shape)
# ---------------------------------------------------------------------------


def test_fallback_fires_when_primary_returns_implausibly_low_count():
    """ERIE shape: primary=2542 (Class B only, dimensional-filter artifact).

    The fallback fires because 2542 < MIN_PLAUSIBLE_SHARE_COUNT (100_000),
    and the fallback function returns the real ~57M total.
    ``snapshot.shares_outstanding`` must equal the fallback value.
    """
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(shares_outstanding=2_542.0)
    company = _make_company_stub(facts)
    fallback_return = 57_000_000.0

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=fallback_return,
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("ERIE", "0000049697")

    mock_fallback.assert_called_once()
    assert snapshot.shares_outstanding == fallback_return


def test_fallback_does_not_fire_when_primary_returns_plausible_count():
    """Normal S&P 500 ticker with a plausible share count (100M >> 100_000).

    The fallback path must NOT be invoked — backward-compat for the bulk
    of the universe where the primary extraction works correctly.
    """
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(shares_outstanding=100_000_000.0)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("AAPL", "0000320193")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == 100_000_000.0


def test_fallback_fires_when_primary_returns_none():
    """Backward-compat with the PR #182 STZ path: primary=None triggers fallback.

    Ensures the original None-trigger still works after the ERIE extension.
    """
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(shares_outstanding=None)
    company = _make_company_stub(facts)
    fallback_return = 172_000_000.0

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=fallback_return,
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("STZ", "0000016160")

    mock_fallback.assert_called_once()
    assert snapshot.shares_outstanding == fallback_return


# ---------------------------------------------------------------------------
# Boundary tests: exact threshold semantics (strict < not <=)
# ---------------------------------------------------------------------------


def test_fallback_boundary_at_99999_fires():
    """primary=99_999: one below the threshold → fallback fires."""
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(shares_outstanding=99_999.0)
    company = _make_company_stub(facts)
    fallback_return = 50_000_000.0

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=fallback_return,
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("FAKE", "0000000001")

    mock_fallback.assert_called_once()
    assert snapshot.shares_outstanding == fallback_return


def test_fallback_boundary_at_100000_does_not_fire():
    """primary=100_000: exactly at threshold → fallback does NOT fire.

    Trigger is strict ``<``, not ``<=``.  100_000 is the safe floor,
    not itself implausible.
    """
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(shares_outstanding=100_000.0)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("FAKE", "0000000001")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == 100_000.0


def test_fallback_boundary_at_100001_does_not_fire():
    """primary=100_001: one above the threshold → fallback does NOT fire."""
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(shares_outstanding=100_001.0)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("FAKE", "0000000001")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == 100_001.0


# ---------------------------------------------------------------------------
# Gate interaction: revenue + total_assets must be positive (PR #182 invariants)
# ---------------------------------------------------------------------------


def test_fallback_does_not_fire_when_too_low_but_revenue_zero():
    """primary=2542 (below floor) but revenue=0 → gate blocks fallback.

    The condition is: (primary is None OR too_low) AND revenue>0 AND assets>0.
    When revenue=0 the gate is False; no fallback call.
    """
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(
        shares_outstanding=2_542.0,
        revenue=0.0,
        total_assets=10_000_000_000.0,
    )
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("FAKE", "0000000001")

    mock_fallback.assert_not_called()
    # snapshot.shares_outstanding remains the raw (implausibly low) primary value
    assert snapshot.shares_outstanding == 2_542.0


def test_fallback_does_not_fire_when_too_low_but_assets_zero():
    """primary=2542 (below floor) but total_assets=0 → gate blocks fallback."""
    from compute.ingest.fundamentals import _build_snapshot

    facts = _make_facts_stub(
        shares_outstanding=2_542.0,
        revenue=5_000_000_000.0,
        total_assets=0.0,
    )
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("FAKE", "0000000001")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == 2_542.0


# ---------------------------------------------------------------------------
# Logging discipline: log message distinguishes None vs too-low primary
# ---------------------------------------------------------------------------


def test_log_message_distinguishes_none_vs_too_low_primary(caplog):
    """When primary=None, log shows ``primary=None``.
    When primary=2542, log shows ``primary=2542``.

    This lets the operator distinguish the two trigger paths in production
    logs without re-running a live probe.
    """
    from compute.ingest.fundamentals import _build_snapshot

    fallback_return = 57_000_000.0

    # --- primary=None path ---
    facts_none = _make_facts_stub(shares_outstanding=None)
    company_none = _make_company_stub(facts_none)
    with (
        patch("compute.ingest.fundamentals.Company", return_value=company_none),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=fallback_return,
        ),
        caplog.at_level(logging.INFO, logger="compute.ingest.fundamentals"),
    ):
        _build_snapshot("STZ", "0000016160")

    none_msgs = [r.getMessage() for r in caplog.records if "fallback fired" in r.getMessage()]
    assert len(none_msgs) == 1, f"expected 1 fallback INFO, got: {none_msgs}"
    assert "primary=None" in none_msgs[0]
    caplog.clear()

    # --- primary=2542 path (ERIE shape) ---
    facts_low = _make_facts_stub(shares_outstanding=2_542.0)
    company_low = _make_company_stub(facts_low)
    with (
        patch("compute.ingest.fundamentals.Company", return_value=company_low),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=fallback_return,
        ),
        caplog.at_level(logging.INFO, logger="compute.ingest.fundamentals"),
    ):
        _build_snapshot("ERIE", "0000049697")

    low_msgs = [r.getMessage() for r in caplog.records if "fallback fired" in r.getMessage()]
    assert len(low_msgs) == 1, f"expected 1 fallback INFO, got: {low_msgs}"
    assert "primary=2542" in low_msgs[0]


# ---------------------------------------------------------------------------
# Hypothesis property: fallback fires iff primary is None or < threshold
# ---------------------------------------------------------------------------


@given(
    primary=st.one_of(st.none(), st.integers(min_value=0, max_value=10_000_000))
)
@settings(max_examples=200)
def test_property_fallback_fires_iff_primary_below_threshold_or_none(primary):
    """For any primary value in [0, 10M] or None, assert:
    fallback invoked <=> (primary is None) OR (primary < MIN_PLAUSIBLE_SHARE_COUNT).

    Uses a pure mock — no live EDGAR, no @settings(deadline=None).
    Exercises the trigger predicate exhaustively across the interesting range.
    """
    from compute.ingest.fundamentals import _build_snapshot

    primary_float = None if primary is None else float(primary)
    facts = _make_facts_stub(
        shares_outstanding=primary_float,
        revenue=5_000_000_000.0,
        total_assets=10_000_000_000.0,
    )
    company = _make_company_stub(facts)

    should_fire = primary is None or primary < config.MIN_PLAUSIBLE_SHARE_COUNT

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=200_000_000.0,
        ) as mock_fallback,
    ):
        _build_snapshot("FAKE", "0000000001")

    if should_fire:
        mock_fallback.assert_called_once()
    else:
        mock_fallback.assert_not_called()


# ---------------------------------------------------------------------------
# Config constant drift-detector
# ---------------------------------------------------------------------------


def test_config_min_plausible_share_count_pinned():
    """Drift-detector: MIN_PLAUSIBLE_SHARE_COUNT must equal 100_000.

    The 30× safety margin vs ~3M plausible S&P 500 floor and the
    docstring rationale in config.py are built around this specific value.
    Any change requires a fresh methodology-scientist review.
    """
    assert config.MIN_PLAUSIBLE_SHARE_COUNT == 100_000


# ---------------------------------------------------------------------------
# @network drift-detector: live ERIE share-count recovery
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_erie_fallback_recovers_correct_share_count():
    """Live SEC probe — ERIE must recover ~50-65M shares total (Class A + Class B).

    ERIE (Erie Indemnity Company) files Class A (~54.9M) + Class B (~2,541)
    with share-class dimensions.  The companyfacts aggregate returns only the
    undimensioned Class B (~2,542), which is below MIN_PLAUSIBLE_SHARE_COUNT.
    The per-filing XBRL fallback should aggregate both classes and return
    the correct total.

    Mirrors the STZ + AAPL + WMT @network pins documented in PR #182.
    Run with: ``pytest --run-network tests/test_ingest/test_fundamentals.py``
    """
    import os

    from edgar import Company, set_identity

    from compute.ingest.fundamentals import _fetch_shares_from_per_filing_xbrl

    set_identity(os.environ["EDGAR_USER_AGENT"])
    result = _fetch_shares_from_per_filing_xbrl(Company("ERIE"))
    assert result is not None, (
        "Live ERIE fallback returned None — _fetch_shares_from_per_filing_xbrl "
        "may be hitting the dimensional-filter pattern without recovering it.  "
        "Re-probe with the script documented on issue #246."
    )
    # ERIE outstanding is ~54.9M Class A + ~2.5K Class B ≈ 57M total.
    # Widen band for buybacks / corporate actions.
    assert 50_000_000 < result < 65_000_000, (
        f"ERIE share-count from live fallback {result:,.0f} outside the "
        "50M-65M expected band — possible duplicate-counting bug or ERIE "
        "corporate action (Class A: ~54.9M, Class B: ~2.5K)."
    )
