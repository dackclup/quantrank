"""Tests for the XBRL balance-sheet context mis-pick fix (sp1500 cron, 2026-06-21).

Root cause: ``EntityFacts.get_fact(tag)`` sorts all facts for a concept by
``(filing_date, period_end)`` — a recent 8-K / S-3 / S-4 event tag can beat
the real 10-K/10-Q consolidated balance-sheet value.  Three confirmed victims
on the first sp1500 production cron:

  HASI: ``stockholders_equity`` $1,000 (S-3 tranche) instead of >$2B (10-K)
  LGIH: ``stockholders_equity`` $25.2M (duration Q-change) instead of >$2B
  GPK:  ``total_liabilities`` $10.8M (8-K event) instead of >$8B (10-K)

The fix adds ``_try_balance_tags`` (replacing the old one-liner) with a
three-tier selection:
  Tier 1 — instant + consolidated form (``_BALANCE_SHEET_FORM_TYPES``) + USD
  Tier 2 — instant + USD (drop form-type — odd-filer safety net)
  Tier 3 — raw ``get_fact()`` (original behavior, last resort)

Within each tier the primary sort key is ``period_end DESC``; ``filing_date``
is the tiebreaker only when two candidates share the same period_end.

All tests here are offline (synthetic ``get_all_facts()`` mocks).  The
``@pytest.mark.network`` regression tests at the bottom assert the corrected
values on HASI / LGIH / GPK via live SEC data and require ``EDGAR_USER_AGENT``
+ ``pytest --run-network``.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from compute.ingest.fundamentals import (
    _BALANCE_SHEET_FORM_TYPES,  # noqa: PLC2701 (private but exported for tests)
    _FINANCIAL_FACT_REQUIRED_ATTRS,  # noqa: PLC2701
    _try_balance_tags,  # noqa: PLC2701
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fact(
    *,
    concept: str,
    value: float,
    period_type: str = "instant",
    form_type: str = "10-K",
    unit: str = "USD",
    period_end: date = date(2024, 12, 31),
    filing_date: date = date(2025, 2, 15),
) -> SimpleNamespace:
    """Return a minimal FinancialFact-shaped namespace."""
    return SimpleNamespace(
        concept=concept,
        value=value,
        period_type=period_type,
        form_type=form_type,
        unit=unit,
        period_end=period_end,
        filing_date=filing_date,
    )


def _make_facts_with_all_facts(
    all_facts: list[SimpleNamespace],
    *,
    get_fact_returns: dict[str, SimpleNamespace | None] | None = None,
) -> MagicMock:
    """Return a mock EntityFacts object whose ``get_all_facts()`` yields
    ``all_facts`` and whose ``get_fact(tag)`` returns entries from
    ``get_fact_returns`` (defaults to always returning ``None`` so Tier-3
    fallback is also controllable).
    """
    facts = MagicMock()
    facts.get_all_facts.return_value = all_facts
    if get_fact_returns is not None:
        facts.get_fact.side_effect = lambda tag: get_fact_returns.get(tag)
    else:
        facts.get_fact.return_value = None
    return facts


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_balance_sheet_form_types_is_frozenset():
    """``_BALANCE_SHEET_FORM_TYPES`` must be an immutable frozenset."""
    assert isinstance(_BALANCE_SHEET_FORM_TYPES, frozenset)


def test_balance_sheet_form_types_covers_standard_filings():
    """The form-type allowlist must include the standard quarterly + annual
    filing variants (plus transition-period forms).  8-K is explicitly absent."""
    assert "10-K" in _BALANCE_SHEET_FORM_TYPES
    assert "10-Q" in _BALANCE_SHEET_FORM_TYPES
    assert "10-K/A" in _BALANCE_SHEET_FORM_TYPES
    assert "10-Q/A" in _BALANCE_SHEET_FORM_TYPES
    assert "20-F" in _BALANCE_SHEET_FORM_TYPES
    # 8-K is an event form — must NOT be in the allowlist
    assert "8-K" not in _BALANCE_SHEET_FORM_TYPES
    # S-type shelf registration — must NOT be in the allowlist
    assert "S-3" not in _BALANCE_SHEET_FORM_TYPES
    assert "S-4" not in _BALANCE_SHEET_FORM_TYPES


def test_financial_fact_required_attrs_is_non_empty_tuple():
    """``_FINANCIAL_FACT_REQUIRED_ATTRS`` must be a tuple and cover the
    core fields used by the new ``_try_balance_tags`` implementation."""
    assert isinstance(_FINANCIAL_FACT_REQUIRED_ATTRS, tuple)
    assert len(_FINANCIAL_FACT_REQUIRED_ATTRS) >= 5
    for attr in ("concept", "period_type", "form_type", "unit", "period_end", "filing_date", "value"):
        assert attr in _FINANCIAL_FACT_REQUIRED_ATTRS, f"{attr!r} missing from manifest"


# ---------------------------------------------------------------------------
# Core behavior: HASI / GPK pattern — 8-K event fact beats real 10-K value
# ---------------------------------------------------------------------------


def test_tier1_picks_10k_over_8k_event_fact_same_period_end():
    """HASI / GPK pattern: two facts for the same concept at the same period_end
    — one from a 10-K (real balance-sheet total), one from a more-recently-filed
    8-K (event tranche, tiny value).  Tier 1 must pick the 10-K fact.
    """
    tag = "us-gaap:StockholdersEquity"
    real_10k = _make_fact(
        concept=tag,
        value=2_500_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    event_8k = _make_fact(
        concept=tag,
        value=1_000.0,
        period_type="instant",
        form_type="8-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 3, 10),   # filed LATER than the 10-K
    )
    facts = _make_facts_with_all_facts([real_10k, event_8k])

    val, pe, fd = _try_balance_tags(facts, [tag])

    assert val == 2_500_000_000.0, (
        f"Expected 10-K value 2.5B, got {val} — 8-K event fact mis-picked"
    )
    assert pe == date(2024, 12, 31)
    # filing_date may be either (both have same period_end, 10-K is NOT max
    # by filing_date) — just verify it's one of the valid dates
    assert fd in {date(2025, 2, 15), date(2025, 3, 10)}


def test_tier1_picks_most_recent_period_end_among_10k_facts():
    """When two 10-K facts differ by period_end, Tier 1 must pick the one
    with the later period_end (most recent balance date), NOT the one with
    the later filing_date.
    """
    tag = "us-gaap:Liabilities"
    older_large = _make_fact(
        concept=tag,
        value=9_000_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2023, 12, 31),
        filing_date=date(2025, 2, 20),   # filed MORE recently
    )
    newer_correct = _make_fact(
        concept=tag,
        value=8_500_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),   # more recent period_end
        filing_date=date(2025, 2, 15),
    )
    facts = _make_facts_with_all_facts([older_large, newer_correct])

    val, pe, _ = _try_balance_tags(facts, [tag])

    assert pe == date(2024, 12, 31), "Should pick fact with the latest period_end"
    assert val == 8_500_000_000.0


def test_tier1_excluded_facts_include_s3_filing():
    """S-3 shelf registration facts must be excluded from Tier 1 (form not in
    ``_BALANCE_SHEET_FORM_TYPES``), leaving only the 10-K value.
    """
    tag = "us-gaap:StockholdersEquity"
    real_fact = _make_fact(
        concept=tag,
        value=2_000_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    s3_tranche = _make_fact(
        concept=tag,
        value=500.0,
        period_type="instant",
        form_type="S-3",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 4, 1),   # filed after the 10-K
    )
    facts = _make_facts_with_all_facts([real_fact, s3_tranche])

    val, _, _ = _try_balance_tags(facts, [tag])

    assert val == 2_000_000_000.0, (
        f"S-3 tranche value should be excluded from Tier 1; got {val}"
    )


# ---------------------------------------------------------------------------
# LGIH pattern — duration fact (equity change) beats instant balance fact
# ---------------------------------------------------------------------------


def test_tier1_excludes_duration_facts():
    """LGIH pattern: a 'duration' fact (one quarter's equity change) must be
    excluded from Tier 1 (which requires ``period_type=='instant'``), leaving
    only the correct instant balance-sheet value.
    """
    tag = "us-gaap:StockholdersEquity"
    duration_change = _make_fact(
        concept=tag,
        value=25_200_000.0,
        period_type="duration",   # Q change, NOT a balance-sheet snapshot
        form_type="10-Q",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 10),
    )
    instant_balance = _make_fact(
        concept=tag,
        value=2_800_000_000.0,
        period_type="instant",
        form_type="10-Q",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 10),
    )
    facts = _make_facts_with_all_facts([duration_change, instant_balance])

    val, pe, _ = _try_balance_tags(facts, [tag])

    assert val == 2_800_000_000.0, (
        f"Duration (change) fact should be excluded; got {val} instead of 2.8B"
    )
    assert pe == date(2024, 12, 31)


# ---------------------------------------------------------------------------
# Three-fact mix: instant 10-K real value + instant 8-K small value + duration
# ---------------------------------------------------------------------------


def test_selects_instant_10k_from_mixed_fact_set():
    """Core regression: given a fact list containing:
      - instant 10-K fact with the real balance (the correct answer)
      - instant 8-K fact with a tiny event value
      - duration 10-Q fact with a quarterly change value
    ``_try_balance_tags`` must return the instant 10-K value.

    This is the canonical three-fact scenario produced by the edgar-debugger
    diagnosis of the sp1500 cron failures.
    """
    tag = "us-gaap:StockholdersEquity"

    instant_10k = _make_fact(
        concept=tag,
        value=3_000_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    instant_8k = _make_fact(
        concept=tag,
        value=1_000.0,
        period_type="instant",
        form_type="8-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 3, 20),   # most recent filing_date
    )
    duration_10q = _make_fact(
        concept=tag,
        value=50_000_000.0,
        period_type="duration",
        form_type="10-Q",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 10),
    )

    facts = _make_facts_with_all_facts([instant_10k, instant_8k, duration_10q])

    val, pe, _ = _try_balance_tags(facts, [tag])

    assert val == 3_000_000_000.0, (
        f"Expected 10-K real value 3B, got {val}. "
        "The three-fact selection is not working correctly."
    )
    assert pe == date(2024, 12, 31)


# ---------------------------------------------------------------------------
# Tag chain: first tag that resolves wins
# ---------------------------------------------------------------------------


def test_returns_first_resolving_tag_in_chain():
    """When a two-tag chain is provided, the function should return the value
    from the first tag that has valid Tier-1 candidates.
    """
    tag1 = "us-gaap:StockholdersEquity"
    tag2 = "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"

    f1 = _make_fact(
        concept=tag1,
        value=2_000_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    f2 = _make_fact(
        concept=tag2,
        value=2_100_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )

    facts = _make_facts_with_all_facts([f1, f2])

    val, _, _ = _try_balance_tags(facts, [tag1, tag2])

    assert val == 2_000_000_000.0, "Should pick the first tag with valid candidates"


def test_falls_through_to_second_tag_when_first_has_no_valid_facts():
    """When the first tag has only 8-K / duration facts (excluded from all
    tiers that match), the function should fall through to the second tag.
    """
    tag1 = "us-gaap:StockholdersEquity"
    tag2 = "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"

    good_tag2 = _make_fact(
        concept=tag2,
        value=2_500_000_000.0,
        period_type="instant",
        form_type="10-K",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )

    # Tier-2 fallback: an 8-K instant USD fact for tag1 would still resolve
    # via Tier 2 (instant+USD, any form).  Use non-USD to force fall-through.
    only_8k_for_tag1_shares = _make_fact(
        concept=tag1,
        value=999.0,
        period_type="instant",
        form_type="8-K",
        unit="shares",   # NOT USD — excluded from all tiers
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 3, 1),
    )

    # Tier-3 get_fact: also returns None for tag1 so Tier 3 doesn't resolve it
    facts = _make_facts_with_all_facts(
        [only_8k_for_tag1_shares, good_tag2],
        get_fact_returns={tag1: None, tag2: None},
    )

    val, _, _ = _try_balance_tags(facts, [tag1, tag2])

    assert val == 2_500_000_000.0, (
        "Should fall through from tag1 (no USD instant facts) to tag2"
    )


# ---------------------------------------------------------------------------
# Tier 2 (instant + USD, no form-type constraint) safety net
# ---------------------------------------------------------------------------


def test_tier2_fires_when_no_consolidated_form_facts_exist():
    """An odd filer that only files balance-sheet data in a non-standard form
    (e.g., a foreign private issuer in a form not in _BALANCE_SHEET_FORM_TYPES)
    should resolve via Tier 2 (instant + USD, any form).
    """
    tag = "us-gaap:Assets"
    odd_form_fact = _make_fact(
        concept=tag,
        value=5_000_000_000.0,
        period_type="instant",
        form_type="40-F",   # Canadian FPI form — not in _BALANCE_SHEET_FORM_TYPES
        unit="USD",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 3, 1),
    )
    facts = _make_facts_with_all_facts([odd_form_fact], get_fact_returns={tag: None})

    val, pe, _ = _try_balance_tags(facts, [tag])

    assert val == 5_000_000_000.0, "Tier 2 should pick up the odd-form fact"
    assert pe == date(2024, 12, 31)


# ---------------------------------------------------------------------------
# Tier 3 fallback (raw get_fact) when get_all_facts is missing
# ---------------------------------------------------------------------------


def test_tier3_fires_when_get_all_facts_missing():
    """If ``get_all_facts`` is absent from the facts object (hypothetical
    future API change), the Tier-3 ``get_fact()`` path must still work.
    """
    tag = "us-gaap:Assets"
    fact_ns = SimpleNamespace(
        value=1_500_000_000.0,
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    facts = MagicMock(spec=["get_fact"])   # no get_all_facts on spec
    facts.get_fact.return_value = fact_ns

    val, pe, fd = _try_balance_tags(facts, [tag])

    assert val == 1_500_000_000.0
    assert pe == date(2024, 12, 31)


# ---------------------------------------------------------------------------
# Graceful degradation — missing attributes on FinancialFact objects
# ---------------------------------------------------------------------------


def test_graceful_when_fact_missing_period_type_attr():
    """If a future edgartools version omits ``period_type`` on a FinancialFact,
    ``getattr(f, 'period_type', None)`` should return ``None`` and exclude
    the fact from Tier 1/2 without raising, then fall through to Tier 3.
    """
    tag = "us-gaap:StockholdersEquity"
    # A fact with NO period_type attribute (simulates edgartools drift)
    broken_fact = SimpleNamespace(
        concept=tag,
        value=999.0,
        # no period_type here
        form_type="10-K",
        unit="USD",
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    good_tier3_fact = SimpleNamespace(
        value=2_000_000_000.0,
        period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 15),
    )
    facts = _make_facts_with_all_facts(
        [broken_fact],
        get_fact_returns={tag: good_tier3_fact},
    )

    val, _, _ = _try_balance_tags(facts, [tag])

    # Tier 1+2 excluded the broken_fact (no period_type → not 'instant').
    # Tier 3 get_fact() returns the good fact.
    assert val == 2_000_000_000.0


def test_returns_none_when_no_tag_resolves():
    """When no tag in the chain has any valid fact at any tier, the function
    should return (None, None, None) matching the original contract.
    """
    facts = _make_facts_with_all_facts([], get_fact_returns={})

    val, pe, fd = _try_balance_tags(facts, ["us-gaap:StockholdersEquity"])

    assert val is None
    assert pe is None
    assert fd is None


# ---------------------------------------------------------------------------
# @network — live SEC regression tests (HASI, LGIH, GPK)
# Require EDGAR_USER_AGENT + pytest --run-network.
# Lock the edgar-debugger-confirmed correct values against future
# edgartools API drift or cron cache state.
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_network_hasi_stockholders_equity_corrected():
    """HASI (Hannon Armstrong) — confirmed first sp1500 cron value was $1,000
    (S-3 preferred-share tranche) instead of the real ~$2-3B total equity.
    The fixed ``_try_balance_tags`` must return a value > $2B.
    """
    import os

    from edgar import Company, set_identity

    set_identity(os.environ["EDGAR_USER_AGENT"])
    company = Company("HASI")
    facts = company.get_facts()
    assert facts is not None, "EDGAR returned no facts for HASI"

    val, pe, _ = _try_balance_tags(
        facts,
        [
            "us-gaap:StockholdersEquity",
            "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
    )
    assert val is not None, "HASI stockholders_equity resolved to None — check EDGAR"
    assert val > 2e9, (
        f"HASI stockholders_equity {val:,.0f} is unexpectedly low (expected >$2B). "
        "If the S-3 tranche fact is still winning, the Tier-1 form-type filter is broken."
    )


@pytest.mark.network
def test_network_lgih_stockholders_equity_corrected():
    """LGIH (LGI Homes) — confirmed first sp1500 cron value was $25.2M
    (duration fact = one quarter's equity change) instead of the real >$2B
    cumulative stockholders_equity.
    The fixed ``_try_balance_tags`` must return a value > $2B.
    """
    import os

    from edgar import Company, set_identity

    set_identity(os.environ["EDGAR_USER_AGENT"])
    company = Company("LGIH")
    facts = company.get_facts()
    assert facts is not None, "EDGAR returned no facts for LGIH"

    val, pe, _ = _try_balance_tags(
        facts,
        [
            "us-gaap:StockholdersEquity",
            "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
    )
    assert val is not None, "LGIH stockholders_equity resolved to None — check EDGAR"
    assert val > 2e9, (
        f"LGIH stockholders_equity {val:,.0f} is unexpectedly low (expected >$2B). "
        "If a duration fact is winning, the Tier-1 period_type='instant' filter is broken."
    )


@pytest.mark.network
def test_network_gpk_total_liabilities_corrected():
    """GPK (Graphic Packaging) — confirmed first sp1500 cron value was $10.8M
    (8-K event liabilities) instead of the real >$8B consolidated balance-sheet
    total liabilities.
    The fixed ``_try_balance_tags`` must return a value > $8B.
    """
    import os

    from edgar import Company, set_identity

    set_identity(os.environ["EDGAR_USER_AGENT"])
    company = Company("GPK")
    facts = company.get_facts()
    assert facts is not None, "EDGAR returned no facts for GPK"

    val, pe, _ = _try_balance_tags(facts, ["us-gaap:Liabilities"])
    assert val is not None, "GPK total_liabilities resolved to None — check EDGAR"
    assert val > 8e9, (
        f"GPK total_liabilities {val:,.0f} is unexpectedly low (expected >$8B). "
        "If an 8-K event fact is winning, the Tier-1 form-type filter is broken."
    )
