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
# _FALLBACK_STATS lifecycle — reset + copy-not-reference (Issue #246 PR2a)
# ---------------------------------------------------------------------------


def test_reset_fallback_stats_zeros_counters():
    """reset_fallback_stats() must drive both counters to zero regardless of
    any prior state. Exercises the threading.Lock-guarded write path.
    """
    from compute.ingest.fundamentals import (
        _FALLBACK_STATS,
        _FALLBACK_STATS_LOCK,
        get_fallback_stats,
        reset_fallback_stats,
    )

    # Put the module-level dict into a non-zero state to make the reset
    # meaningful (avoids a trivially-passing test when counters happen to
    # already be 0 from a previous test run in the same process).
    with _FALLBACK_STATS_LOCK:
        _FALLBACK_STATS["triggered"] = 7
        _FALLBACK_STATS["too_low"] = 3
        _FALLBACK_STATS["dimensional_override"] = 2
        _FALLBACK_STATS["per_class_override"] = 4
        _FALLBACK_STATS["mc_reconcile_failure"] = 1
        _FALLBACK_STATS["per_class_attempt"] = 5

    reset_fallback_stats()
    assert get_fallback_stats() == {
        "triggered": 0,
        "too_low": 0,
        "dimensional_override": 0,
        "per_class_override": 0,
        "mc_reconcile_failure": 0,
        "per_class_attempt": 0,
    }


def test_get_fallback_stats_returns_copy_not_reference():
    """Mutating the dict returned by get_fallback_stats() must NOT affect the
    internal module-level counter. get_fallback_stats() returns a shallow copy
    (``dict(_FALLBACK_STATS)``), not the live dict.
    """
    from compute.ingest.fundamentals import get_fallback_stats, reset_fallback_stats

    reset_fallback_stats()

    first = get_fallback_stats()
    first["triggered"] = 9999  # mutate the returned copy

    second = get_fallback_stats()
    # Internal state must be unaffected — still 0 from the reset above.
    assert second == {
        "triggered": 0,
        "too_low": 0,
        "dimensional_override": 0,
        "per_class_override": 0,
        "mc_reconcile_failure": 0,
        "per_class_attempt": 0,
    }
    # And the two dicts are distinct objects.
    assert first is not second


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


# ---------------------------------------------------------------------------
# Issue #248 PR2b — multi-class dimensional override branch
# Tests the new ``elif`` in ``_build_snapshot`` that fires when:
#   ticker in MULTI_CLASS_SHARE_ALLOWLIST AND primary_shares is not None
#   AND not primary_too_low AND revenue > 0 AND total_assets > 0
# and replaces primary with the dimensional sum when sum > primary.
# ---------------------------------------------------------------------------


def test_v_class_dimensional_override_fires():
    """V (Visa) — primary=469M (plausible); XBRL sum=5.4B (Class A+B+C).

    The dimensional override branch must replace shares_outstanding with
    the summed value and increment _FALLBACK_STATS["dimensional_override"].
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    facts = _make_facts_stub(shares_outstanding=469_000_000.0)
    company = _make_company_stub(facts)
    summed = 5_400_000_000.0  # Class A + B + C

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=summed,
        ),
    ):
        snapshot = _build_snapshot("V", "0001403161")

    assert snapshot.shares_outstanding == summed
    assert get_fallback_stats()["dimensional_override"] == 1
    # Primary fallback counter must not have incremented (primary was plausible).
    assert get_fallback_stats()["triggered"] == 0


def test_brk_b_dimensional_override_fires_with_naive_sum():
    """BRK-B — primary=1.46M (Class A direct); XBRL naive sum=2.14B.

    The naive sum (Class A 1.46M + Class B 2.14B) is definitionally > primary,
    so the override fires.  The 1500x economic-weighting caveat is deferred to
    the Q3 2026-08-19 cohort audit; for now any positive delta wins per
    Damodaran 2019 Ch. 16 (TSO = sum across all classes).
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 1_460_000.0  # Class A only from companyfacts aggregate
    summed = 2_140_000_000.0  # naive Class A + Class B sum (no 1500x weighting)

    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=summed,
        ),
    ):
        snapshot = _build_snapshot("BRK-B", "0001067983")

    assert snapshot.shares_outstanding == summed
    assert get_fallback_stats()["dimensional_override"] == 1


def test_multi_class_summed_equals_primary_with_tiny_delta_overrides():
    """STZ-like: primary=172.17M; XBRL sum=172.20M (Class A + Class B).

    delta = +0.02% which is > 0, so the ``summed > primary`` condition is
    True and the override fires.  Any positive delta is the truth per
    Damodaran 2019 Ch. 16; no epsilon threshold suppresses it.
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 172_170_000.0
    summed = 172_200_000.0  # +30K Class B on top of Class A primary

    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=summed,
        ),
    ):
        snapshot = _build_snapshot("STZ", "0000016160")

    assert snapshot.shares_outstanding == summed
    assert get_fallback_stats()["dimensional_override"] == 1


def test_allowlist_excludes_non_multi_class_ticker():
    """AAPL is NOT in MULTI_CLASS_SHARE_ALLOWLIST; per-filing XBRL must NOT be called.

    The dimensional override elif only fires for tickers in the allowlist.
    A plausible primary (15B shares) for a non-allowlist ticker must leave
    shares_outstanding unchanged and never call _fetch_shares_from_per_filing_xbrl.
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "AAPL" not in config.MULTI_CLASS_SHARE_ALLOWLIST

    reset_fallback_stats()
    primary = 15_000_000_000.0  # ~15B, plausible for AAPL
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
    assert get_fallback_stats()["dimensional_override"] == 0


def test_summed_less_than_primary_does_not_override():
    """Defensive guard: if XBRL sum < primary, the override must NOT fire.

    Bad XBRL data (e.g., partial dimensional parse) must not downgrade a
    correct primary value.  balance_values["shares_outstanding"] stays at
    primary; dimensional_override counter stays at 0.
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 469_000_000.0
    summed = 200_000_000.0  # lower than primary — bad XBRL data

    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=summed,
        ),
    ):
        snapshot = _build_snapshot("V", "0001403161")

    # Override must NOT have fired; primary value preserved.
    assert snapshot.shares_outstanding == primary
    assert get_fallback_stats()["dimensional_override"] == 0


def test_too_low_primary_does_not_fire_dimensional_branch():
    """ERIE pattern (primary=2541): the EXISTING None/too_low branch fires,
    NOT the new dimensional override elif.

    The two branches are mutually exclusive (if/elif).  When primary_too_low
    is True, the first ``if`` fires; the elif is skipped.  Counter:
    ``too_low`` increments, ``dimensional_override`` stays at 0.
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    # 2541 < MIN_PLAUSIBLE_SHARE_COUNT — triggers too_low path.
    # ERIE is NOT in MULTI_CLASS_SHARE_ALLOWLIST anyway, but even if it
    # were, the if/elif guarantees the dimensional branch is unreachable
    # when primary_too_low is True.
    primary = 2_541.0
    fallback_return = 57_000_000.0

    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=fallback_return,
        ),
    ):
        snapshot = _build_snapshot("ERIE", "0000049697")

    # too_low branch fired → snapshot updated to fallback value
    assert snapshot.shares_outstanding == fallback_return
    stats = get_fallback_stats()
    assert stats["too_low"] == 1
    assert stats["triggered"] == 1
    assert stats["dimensional_override"] == 0


def test_get_fallback_stats_returns_six_keys_after_dimensional_path():
    """Lifecycle sanity: reset → run dimensional override → inspect all six keys.

    After reset_fallback_stats(): all six counters are 0
    (Issue #261 PR-B added ``per_class_override`` + ``mc_reconcile_failure``
    alongside the existing 3; Issue #288 added ``per_class_attempt`` as the
    Rule-18 disambiguator on the per-class XBRL override path).
    After one dimensional override fires: only dimensional_override == 1;
    the other five counters remain 0 (each belongs to a distinct path).
    """
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    assert get_fallback_stats() == {
        "triggered": 0,
        "too_low": 0,
        "dimensional_override": 0,
        "per_class_override": 0,
        "mc_reconcile_failure": 0,
        "per_class_attempt": 0,
    }

    facts = _make_facts_stub(shares_outstanding=469_000_000.0)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=5_400_000_000.0,
        ),
    ):
        _build_snapshot("V", "0001403161")

    stats = get_fallback_stats()
    assert stats == {
        "triggered": 0,
        "too_low": 0,
        "dimensional_override": 1,
        "per_class_override": 0,
        "mc_reconcile_failure": 0,
        "per_class_attempt": 0,
    }


# ---------------------------------------------------------------------------
# Config constant drift-detector: MULTI_CLASS_SHARE_ALLOWLIST
# ---------------------------------------------------------------------------


def test_config_multi_class_share_allowlist_pinned():
    """Drift-detector: MULTI_CLASS_SHARE_ALLOWLIST must contain exactly the
    7 tickers verified 2026-05-25 via EPS cross-check (edgar-debugger).

    Expansion requires: (a) edgar-debugger EPS cross-check confirmation,
    (b) methodology-scientist Mode B sign-off, (c) Q3 2026-08-19 cohort
    audit gate if the expansion is > 2 new tickers.
    """
    expected = frozenset({"V", "NWS", "NWSA", "STZ", "FOX", "FOXA", "BRK-B"})
    assert config.MULTI_CLASS_SHARE_ALLOWLIST == expected


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


# ---------------------------------------------------------------------------
# Issue #261 PR-B: per-class XBRL extraction (OVERCOUNT path, GOOG/GOOGL)
#
# The new elif branch fires when:
#   ticker in MULTI_CLASS_OVERCOUNT_ALLOWLIST AND primary is plausible AND
#   QR_SKIP_FUNDAMENTALS not set
# It calls _fetch_shares_from_per_filing_xbrl(target_class_member=...) and
# OVERRIDES primary IFF per_class < primary (the per-class subset must be
# SMALLER than the aggregate — opposite of the PR #257 sum-all path).
# ---------------------------------------------------------------------------


def test_per_class_override_fires_for_goog_with_filer_namespace_member():
    """GOOG case: primary=12.12B (Alphabet aggregate), per-class filter
    returns 5.43B (Class C). The override fires; shares_outstanding ends
    at 5.43B; ``per_class_override`` counter increments."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "GOOG" in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST
    assert (
        config.MULTI_CLASS_OVERCOUNT_ALLOWLIST["GOOG"] == "goog:CapitalClassCMember"
    )

    reset_fallback_stats()
    primary = 12_120_000_000.0  # Alphabet aggregate (3-class sum)
    per_class = 5_429_000_000.0  # Class C (GOOG) per the live probe
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=per_class,
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    mock_fallback.assert_called_once()
    # Confirm the filter mode kwarg was passed correctly
    _, kwargs = mock_fallback.call_args
    assert kwargs.get("target_class_member") == "goog:CapitalClassCMember"
    assert snapshot.shares_outstanding == per_class
    assert get_fallback_stats()["per_class_override"] == 1
    assert get_fallback_stats()["mc_reconcile_failure"] == 0


def test_per_class_override_fires_for_googl_with_standard_namespace_member():
    """GOOGL case: primary=12.12B aggregate, per-class returns 5.82B
    (Class A standard namespace). Override fires."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "GOOGL" in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST
    assert (
        config.MULTI_CLASS_OVERCOUNT_ALLOWLIST["GOOGL"]
        == "us-gaap:CommonClassAMember"
    )

    reset_fallback_stats()
    primary = 12_120_000_000.0
    per_class = 5_822_000_000.0  # Class A (GOOGL) per the live probe
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=per_class,
        ),
    ):
        snapshot = _build_snapshot("GOOGL", "0001652044")

    assert snapshot.shares_outstanding == per_class
    assert get_fallback_stats()["per_class_override"] == 1


def test_per_class_override_does_not_fire_for_non_allowlist_ticker():
    """AAPL is NOT in MULTI_CLASS_OVERCOUNT_ALLOWLIST; the per-class
    fallback must NOT be called even with a plausible primary."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    assert "AAPL" not in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST

    reset_fallback_stats()
    primary = 15_000_000_000.0
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
    assert get_fallback_stats()["per_class_override"] == 0


def test_per_class_skipped_when_qr_skip_fundamentals_set(monkeypatch):
    """``QR_SKIP_FUNDAMENTALS=1`` escape-hatch must skip the per-class
    HTTP probe even when ticker is on the allowlist. Matches PR #257
    elif behavior."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    monkeypatch.setenv("QR_SKIP_FUNDAMENTALS", "1")
    primary = 12_120_000_000.0
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
        ) as mock_fallback,
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    mock_fallback.assert_not_called()
    assert snapshot.shares_outstanding == primary
    assert get_fallback_stats()["per_class_override"] == 0


def test_per_class_override_skipped_when_per_class_gte_primary():
    """Defensive sanity: if the filter returns >= primary, override is
    SKIPPED and ``mc_reconcile_failure`` increments. Could mean stale
    allowlist member, XBRL shape drift, or wrong-member pick."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 5_000_000_000.0
    per_class = 5_500_000_000.0  # > primary; sanity fail
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=per_class,
        ),
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    # Override SKIPPED; primary preserved; reconcile failure recorded.
    assert snapshot.shares_outstanding == primary
    assert get_fallback_stats()["per_class_override"] == 0
    assert get_fallback_stats()["mc_reconcile_failure"] == 1


def test_per_class_override_mc_reconcile_warning_on_fraction_below_5pct():
    """When per_class < primary BUT per_class / primary < 5%, the
    override fires (primary > per_class so per-class IS the better
    value) AND the reconcile-failure counter increments to flag
    the unexpected ratio for cohort-audit review."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 12_120_000_000.0
    per_class = 100_000_000.0  # < 1% of primary; suspicious
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=per_class,
        ),
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    # Override DID fire (per_class < primary)
    assert snapshot.shares_outstanding == per_class
    assert get_fallback_stats()["per_class_override"] == 1
    # AND reconcile counter incremented (fraction outside 5-95% band)
    assert get_fallback_stats()["mc_reconcile_failure"] == 1


def test_per_class_override_skipped_when_per_class_returns_none():
    """If the filter mode returns None (allowlist member missing from
    XBRL, shape drift, etc.), override is silently skipped (no counter
    increments). Primary preserved."""
    from compute.ingest.fundamentals import (
        _build_snapshot,
        get_fallback_stats,
        reset_fallback_stats,
    )

    reset_fallback_stats()
    primary = 12_120_000_000.0
    facts = _make_facts_stub(shares_outstanding=primary)
    company = _make_company_stub(facts)

    with (
        patch("compute.ingest.fundamentals.Company", return_value=company),
        patch(
            "compute.ingest.fundamentals._fetch_shares_from_per_filing_xbrl",
            return_value=None,
        ),
    ):
        snapshot = _build_snapshot("GOOG", "0001652044")

    assert snapshot.shares_outstanding == primary
    assert get_fallback_stats()["per_class_override"] == 0
    assert get_fallback_stats()["mc_reconcile_failure"] == 0
