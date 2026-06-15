"""Tests for Issue #385 — OilAndGasRevenue extraction in both the TTM
and annual tag chains.

Coverage:
- TTM path (``_try_ttm_max_fresh``): O&G-only filer resolves a non-None revenue.
- Annual path (``_build_annual_history`` / ``_ANNUAL_TAGS``): O&G-only filer
  resolves a non-None revenue row for the correct fiscal year.
- Co-reporting edge cases:
  - Annual path: standard tag fires first (``break``), OilAndGasRevenue never
    reached — safe by design because standard concept is listed earlier.
  - TTM path: MAX-of-fresh heuristic — when BOTH a standard tag AND
    ``OilAndGasRevenue`` are fresh, the LARGER value wins.  This means a
    hypothetical co-filer where ``OilAndGasRevenue`` > standard-revenue WOULD
    see OilAndGasRevenue win.  The comment in the production code says "placed
    LAST so standard filers' existing concepts win", but this is only safe when
    the O&G value is NOT larger than the standard value.

FINDING (#385 TTM-selection):
    The TTM path uses MAX-of-fresh semantics (``max(candidates, key=lambda c: c[0])``
    at line 665 of fundamentals.py).  OilAndGasRevenue being "last" in
    ``_TTM_REVENUE_TAGS`` provides NO ordering protection — every fresh candidate
    is collected and the largest wins.  If an O&G filer also tags revenue under
    a standard concept (e.g., ``us-gaap:Revenues``) AND the OilAndGasRevenue
    value is larger, OilAndGasRevenue wins.  If both values are equal, either
    wins (comparison is stable within candidates, but which is "max" when equal
    is undefined).  In practice this is correct for O&G filers — both concepts
    should represent the same consolidated total — but it is NOT correct to claim
    ordering provides safety.  The test ``test_ttm_co_reporter_max_wins``
    documents this real behavior explicitly.

All tests are offline (no live SEC fetch).  The ``fundamentals`` module has a
top-level ``from edgar import Company, set_identity`` — since ``edgar`` is an
optional dependency (edgartools), we stub it in ``sys.modules`` at module load
time so this file collects even when the package is absent.  The functions under
test (``_try_ttm_max_fresh``, ``_build_annual_history``, ``_ANNUAL_TAGS``,
``_TTM_REVENUE_TAGS``) do not actually call ``edgar.Company`` in the offline
path — the stubs only need to be importable.
"""

from __future__ import annotations

import sys
import types
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# edgar stub — allows fundamentals.py to be imported without edgartools
# ---------------------------------------------------------------------------


def _stub_edgar():
    """Register a minimal edgar stub in sys.modules so that
    ``from edgar import Company, set_identity`` succeeds in fundamentals.py.

    Idempotent: if edgar is already installed, the real module wins.
    """
    if "edgar" in sys.modules:
        return  # real edgar (or prior stub) already registered

    edgar_stub = types.ModuleType("edgar")

    class _Company:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def get_facts(self):
            return None

    def _set_identity(user_agent: str) -> None:  # noqa: ARG001
        pass

    edgar_stub.Company = _Company
    edgar_stub.set_identity = _set_identity
    sys.modules["edgar"] = edgar_stub


_stub_edgar()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RECENT_PE = date(2025, 12, 31)
_RECENT_FD = date(2026, 2, 15)


def _ttm_stub(value: float, pe: date = _RECENT_PE, fd: date = _RECENT_FD) -> SimpleNamespace:
    """TTM stub with a single period_fact so freshness check passes."""
    return SimpleNamespace(
        value=value,
        period_facts=[SimpleNamespace(period_end=pe, filing_date=fd)],
    )


def _annual_fact_stub(value: float, fy: int) -> SimpleNamespace:
    """Annual fact stub for ``_build_annual_history`` / ``get_annual_fact``."""
    return SimpleNamespace(
        value=value,
        period_end=date(fy, 12, 31),
        filing_date=date(fy + 1, 2, 15),
        form_type="10-K",
    )


def _make_ttm_facts(tag_responses: dict[str, float | None]) -> MagicMock:
    """Build a facts mock whose ``get_ttm`` answers per ``tag_responses``.

    ``tag_responses`` maps tag string → float value (fresh) or None (not filed).
    Tags absent from the dict also return None.
    """
    def get_ttm(tag: str):
        val = tag_responses.get(tag)
        if val is None:
            return None
        return _ttm_stub(val)

    m = MagicMock()
    m.get_ttm.side_effect = get_ttm
    m.get_fact.return_value = None
    m.get_concept.return_value = None
    m._suppress_warnings = False
    return m


def _make_annual_facts(annual_tag_responses: dict[str, dict[int, float | None]]) -> MagicMock:
    """Build a facts mock whose ``get_annual_fact(tag, fiscal_year=fy)``
    answers per ``annual_tag_responses``.

    annual_tag_responses: {tag: {fiscal_year: value | None}}
    """
    def get_annual_fact(tag: str, *, fiscal_year: int):
        tag_map = annual_tag_responses.get(tag, {})
        val = tag_map.get(fiscal_year)
        if val is None:
            return None
        return _annual_fact_stub(val, fiscal_year)

    m = MagicMock()
    m.get_annual_fact.side_effect = get_annual_fact
    m._suppress_warnings = False
    return m


# ---------------------------------------------------------------------------
# Structural guards — can run without importing edgar internals
# ---------------------------------------------------------------------------


def test_annual_oil_gas_revenue_is_last_in_chain():
    """Structural guard: ``us-gaap:OilAndGasRevenue`` must be the LAST entry
    in the ``_ANNUAL_TAGS["revenue"]`` list.  Being last is what makes the
    annual first-non-null break safe for standard filers.
    """
    from compute.ingest.fundamentals import _ANNUAL_TAGS

    revenue_tags = _ANNUAL_TAGS["revenue"]
    assert revenue_tags[-1] == "us-gaap:OilAndGasRevenue", (
        "OilAndGasRevenue must be last in _ANNUAL_TAGS['revenue'] for "
        "break-on-first-non-null safety"
    )


def test_ttm_oil_gas_revenue_is_last_in_ttm_chain():
    """Structural guard: ``us-gaap:OilAndGasRevenue`` is the last entry
    in ``_TTM_REVENUE_TAGS``.  While order does NOT protect standard filers
    on the TTM path (MAX-of-fresh wins regardless), being last is the
    documented intent; removing or reordering it should surface here.
    """
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS

    assert _TTM_REVENUE_TAGS[-1] == "us-gaap:OilAndGasRevenue", (
        "OilAndGasRevenue must be last in _TTM_REVENUE_TAGS (documented intent)"
    )


# ---------------------------------------------------------------------------
# TTM path — OilAndGasRevenue-only filer
# ---------------------------------------------------------------------------


def test_ttm_oil_gas_only_filer_resolves_revenue():
    """An E&P filer that reports revenue ONLY under ``us-gaap:OilAndGasRevenue``
    (no ``Revenues`` / ``RevenueFromContractWithCustomer*`` / etc.) must resolve
    a non-None TTM revenue via ``_try_ttm_max_fresh``.
    """
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS, _try_ttm_max_fresh

    # Only OilAndGasRevenue is populated; all other standard tags return None.
    tag_responses: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    tag_responses["us-gaap:OilAndGasRevenue"] = 8_500_000_000.0  # APA-scale

    facts = _make_ttm_facts(tag_responses)

    value, filed, pe = _try_ttm_max_fresh(facts, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))

    assert value is not None, "OilAndGasRevenue-only filer must resolve a TTM revenue"
    assert value == pytest.approx(8_500_000_000.0)
    assert pe == _RECENT_PE
    assert filed == _RECENT_FD


def test_ttm_oil_gas_only_filer_stale_returns_none():
    """A stale OilAndGasRevenue fact (period_end > 540 days ago) must be
    rejected by the freshness gate, returning (None, None, None).
    """
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS, _try_ttm_max_fresh

    STALE_PE = date(2022, 6, 30)   # > 540 days before 2026-06-01

    def get_ttm(tag: str):
        if tag == "us-gaap:OilAndGasRevenue":
            return SimpleNamespace(
                value=5_000_000_000.0,
                period_facts=[SimpleNamespace(period_end=STALE_PE, filing_date=date(2022, 9, 1))],
            )
        return None

    m = MagicMock()
    m.get_ttm.side_effect = get_ttm
    m.get_fact.return_value = None
    m.get_concept.return_value = None
    m._suppress_warnings = False

    value, filed, pe = _try_ttm_max_fresh(m, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))
    assert value is None
    assert pe is None


# ---------------------------------------------------------------------------
# TTM path — co-reporter: MAX-of-fresh heuristic behavior
# ---------------------------------------------------------------------------


def test_ttm_co_reporter_max_wins():
    """FINDING — documenting real MAX-of-fresh behavior for co-reporters.

    When a filer reports BOTH a standard tag (``us-gaap:Revenues``) AND
    ``us-gaap:OilAndGasRevenue``, the TTM path collects ALL fresh candidates
    and returns the one with the LARGEST value.  Ordering in _TTM_REVENUE_TAGS
    provides NO protection here.

    This test asserts the actual behavior:
    - If OilAndGasRevenue > standard: OilAndGasRevenue wins (even though it's last)
    - If standard > OilAndGasRevenue: standard wins

    For O&G filers that truly co-report under multiple concepts (both summing to
    the same consolidated total), this is safe.  It is NOT safe if a filer tags
    a subset value under OilAndGasRevenue and a consolidated total under Revenues —
    the higher value (Revenues) correctly wins in that case.
    """
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS, _try_ttm_max_fresh

    # Scenario A: OilAndGasRevenue > standard → O&G wins (MAX selection)
    tag_responses_a: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    tag_responses_a["us-gaap:Revenues"] = 10_000_000_000.0
    tag_responses_a["us-gaap:OilAndGasRevenue"] = 12_000_000_000.0  # larger

    facts_a = _make_ttm_facts(tag_responses_a)
    value_a, _, _ = _try_ttm_max_fresh(facts_a, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))
    # MAX-of-fresh: the 12B OilAndGasRevenue wins
    assert value_a == pytest.approx(12_000_000_000.0), (
        "TTM MAX-of-fresh: OilAndGasRevenue (12B) must win over Revenues (10B)"
    )

    # Scenario B: standard > OilAndGasRevenue → standard wins
    tag_responses_b: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    tag_responses_b["us-gaap:Revenues"] = 15_000_000_000.0
    tag_responses_b["us-gaap:OilAndGasRevenue"] = 12_000_000_000.0  # smaller

    facts_b = _make_ttm_facts(tag_responses_b)
    value_b, _, _ = _try_ttm_max_fresh(facts_b, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))
    # MAX-of-fresh: the 15B Revenues wins
    assert value_b == pytest.approx(15_000_000_000.0), (
        "TTM MAX-of-fresh: Revenues (15B) must win over OilAndGasRevenue (12B)"
    )


def test_ttm_standard_filer_no_oil_gas_tag_unaffected():
    """Standard (non-O&G) filer that reports only ``us-gaap:Revenues`` is
    completely unaffected by the OilAndGasRevenue addition — the tag is simply
    absent from the SEC companyfacts and get_ttm returns None for it.
    """
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS, _try_ttm_max_fresh

    tag_responses: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    tag_responses["us-gaap:Revenues"] = 50_000_000_000.0  # AAPL-scale
    # OilAndGasRevenue remains None (not filed)

    facts = _make_ttm_facts(tag_responses)
    value, _, _ = _try_ttm_max_fresh(facts, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))

    assert value == pytest.approx(50_000_000_000.0)


# ---------------------------------------------------------------------------
# Annual path — OilAndGasRevenue-only filer
# ---------------------------------------------------------------------------


def test_annual_oil_gas_only_filer_resolves_revenue():
    """An E&P filer that ONLY files under ``us-gaap:OilAndGasRevenue`` must
    produce a non-empty DataFrame row for the revenue metric in
    ``_build_annual_history``.

    The annual path uses first-non-null break semantics: ``OilAndGasRevenue``
    is last in the chain, so it is only reached when ALL earlier standard tags
    return None.
    """
    from unittest.mock import patch

    from compute.ingest.fundamentals import _ANNUAL_TAGS, _build_annual_history

    # Build annual fact stubs: only OilAndGasRevenue is populated for FY 2024.
    fy = 2024

    # All standard revenue tags return None; only OilAndGasRevenue fires.
    annual_responses: dict[str, dict[int, float | None]] = {}
    for tag in _ANNUAL_TAGS["revenue"]:
        annual_responses[tag] = {fy: None}
    annual_responses["us-gaap:OilAndGasRevenue"][fy] = 9_000_000_000.0

    # Non-revenue tags return None for all years (simplification).
    for metric, tags in _ANNUAL_TAGS.items():
        if metric == "revenue":
            continue
        for tag in tags:
            annual_responses.setdefault(tag, {})[fy] = None

    facts = _make_annual_facts(annual_responses)
    company = MagicMock()
    company.get_facts.return_value = facts

    with patch("compute.ingest.fundamentals.Company", return_value=company):
        df = _build_annual_history("0000000001", years=1)

    assert not df.empty, "O&G-only annual filer must resolve at least one row"
    revenue_rows = df[df["metric"] == "revenue"]
    assert not revenue_rows.empty, "revenue row must be present for O&G-only annual filer"
    rev_row = revenue_rows[revenue_rows["fiscal_year"] == fy]
    assert not rev_row.empty, f"revenue row for FY {fy} must be present"
    assert rev_row.iloc[0]["value"] == pytest.approx(9_000_000_000.0)


def test_annual_co_reporter_standard_tag_wins_via_break():
    """Annual co-reporter: a filer that reports BOTH ``us-gaap:Revenues``
    (standard, listed FIRST) AND ``us-gaap:OilAndGasRevenue`` (listed LAST)
    must resolve to the standard Revenues value because the annual loop uses
    ``break`` on first-non-null.  OilAndGasRevenue is never reached.
    """
    from unittest.mock import patch

    from compute.ingest.fundamentals import _ANNUAL_TAGS, _build_annual_history

    fy = 2024

    annual_responses: dict[str, dict[int, float | None]] = {}
    for _metric, tags in _ANNUAL_TAGS.items():
        for tag in tags:
            annual_responses.setdefault(tag, {})[fy] = None

    # Standard Revenues fires (first in chain)
    annual_responses["us-gaap:Revenues"][fy] = 100_000_000_000.0  # Exxon-scale
    # OilAndGasRevenue also populated (should NOT win — break fires first)
    annual_responses["us-gaap:OilAndGasRevenue"][fy] = 80_000_000_000.0

    facts = _make_annual_facts(annual_responses)
    company = MagicMock()
    company.get_facts.return_value = facts

    with patch("compute.ingest.fundamentals.Company", return_value=company):
        df = _build_annual_history("0000000001", years=1)

    revenue_rows = df[(df["metric"] == "revenue") & (df["fiscal_year"] == fy)]
    assert not revenue_rows.empty
    # The 100B Revenues (first-non-null) must win; OilAndGasRevenue (80B) is skipped.
    assert revenue_rows.iloc[0]["value"] == pytest.approx(100_000_000_000.0), (
        "Annual path break-on-first-non-null: Revenues (100B) must win; "
        "OilAndGasRevenue (80B) never reached"
    )
