"""Tests for Issue #566 / PR #571 — pure-advisory investment-bank revenue.

Pure-advisory IBs (Moelis MC, Evercore EVR, Houlihan Lokey HLI, PJT, Lazard
LAZ) have negligible interest income and tag consolidated fee revenue under the
ASC 942 broker-dealer concept ``us-gaap:NoninterestIncome`` rather than any
``Revenues*`` concept. Without recovering it they ship with revenue=None, which
(combined with empty dimensional DEI share contexts) blocked the per-filing
XBRL shares fallback and left ``market_cap`` / fair-price null while the stock
still SCORED — the misleading-``lean_bullish``-with-no-context case for MC.

The two ASC 942 concepts are added as a **fallback-only** chain
(``_TTM_REVENUE_ADVISORY_FALLBACK_TAGS``), NOT into the MAX-of-fresh
``_TTM_REVENUE_TAGS``: ``NoninterestIncome`` is a *component* of a bank's
``RevenuesNetOfInterestExpense`` and EXCEEDS that consolidated total whenever
NetInterestIncome < 0 (interest expense > interest income). Were it in the MAX
chain it would silently inflate a net-interest-negative diversified bank's
revenue. ``_resolve_ttm_revenue`` consults the fallback ONLY when no standard
concept resolves a fresh value (methodology-scientist RATIFY-WITH-CONDITIONS).

Coverage:
- The two advisory tags are fallback-only (in the fallback list, NOT the MAX chain).
- Two-tier path: an advisory-only filer (revenue ONLY under ``NoninterestIncome``)
  resolves a non-None TTM revenue via the fallback.
- ADVERSARIAL: a net-interest-negative bank with a SMALLER consolidated
  ``RevenuesNetOfInterestExpense`` AND a LARGER ``NoninterestIncome`` still
  resolves the consolidated value (the fallback is never consulted).
- The OilAndGasRevenue "last in chain" structural invariant is preserved.
"""

from __future__ import annotations

import sys
import types
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _stub_edgar() -> None:
    """Register a minimal ``edgar`` stub so importing fundamentals does not
    require the real edgartools package at collection time (offline-first)."""
    if "edgar" in sys.modules:
        return

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

_RECENT_PE = date(2025, 12, 31)
_RECENT_FD = date(2026, 2, 15)


def _ttm_stub(value: float, pe: date = _RECENT_PE, fd: date = _RECENT_FD) -> SimpleNamespace:
    return SimpleNamespace(
        value=value,
        period_facts=[SimpleNamespace(period_end=pe, filing_date=fd)],
    )


def _make_ttm_facts(tag_responses: dict[str, float | None]) -> MagicMock:
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


def _all_revenue_tags_none() -> dict[str, float | None]:
    from compute.ingest.fundamentals import (
        _TTM_REVENUE_ADVISORY_FALLBACK_TAGS,
        _TTM_REVENUE_TAGS,
    )

    responses: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    responses.update({t: None for t in _TTM_REVENUE_ADVISORY_FALLBACK_TAGS})
    return responses


def test_advisory_revenue_tags_are_fallback_only():
    """#571 — the ASC 942 fee concepts live in the FALLBACK list, NOT the
    MAX-of-fresh ``_TTM_REVENUE_TAGS`` chain (so a present consolidated bank
    total always wins and they can't silently inflate a net-interest-negative
    bank's revenue)."""
    from compute.ingest.fundamentals import (
        _TTM_REVENUE_ADVISORY_FALLBACK_TAGS,
        _TTM_REVENUE_TAGS,
    )

    assert "us-gaap:NoninterestIncome" in _TTM_REVENUE_ADVISORY_FALLBACK_TAGS
    assert "us-gaap:BrokerageCommissionsRevenue" in _TTM_REVENUE_ADVISORY_FALLBACK_TAGS
    # Must NOT be in the MAX-of-fresh chain (the whole point of #571's carve-out).
    assert "us-gaap:NoninterestIncome" not in _TTM_REVENUE_TAGS
    assert "us-gaap:BrokerageCommissionsRevenue" not in _TTM_REVENUE_TAGS


def test_oil_gas_revenue_still_last_in_ttm_chain():
    """The standard MAX-of-fresh chain is unchanged — OilAndGasRevenue stays
    last (mirrors the invariant pinned by test_oil_gas_revenue.py)."""
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS

    assert _TTM_REVENUE_TAGS[-1] == "us-gaap:OilAndGasRevenue"


def test_advisory_only_filer_resolves_revenue_via_fallback():
    """A pure-advisory IB (Moelis-class) tagging revenue ONLY under
    ``us-gaap:NoninterestIncome`` resolves a non-None TTM revenue through the
    two-tier ``_resolve_ttm_revenue`` (standard chain empty → fallback fires)."""
    from compute.ingest.fundamentals import _resolve_ttm_revenue

    tag_responses = _all_revenue_tags_none()
    tag_responses["us-gaap:NoninterestIncome"] = 1_200_000_000.0  # MC-scale fee revenue
    facts = _make_ttm_facts(tag_responses)

    value, filed, pe = _resolve_ttm_revenue(facts, today=date(2026, 6, 1))

    assert value == pytest.approx(1_200_000_000.0), "advisory-only filer must resolve revenue"
    assert pe == _RECENT_PE
    assert filed == _RECENT_FD


def test_net_interest_negative_bank_consolidated_wins_over_larger_noninterest():
    """ADVERSARIAL pin (methodology RATIFY-WITH-CONDITIONS, #571): a
    net-interest-negative diversified bank reports a SMALLER consolidated
    ``RevenuesNetOfInterestExpense`` AND a LARGER ``NoninterestIncome`` (because
    NetInterestIncome < 0). The two-tier resolution must return the consolidated
    total — the fallback tag is NEVER consulted when a standard concept resolves,
    so MAX-of-fresh cannot pick the inflated noninterest line."""
    from compute.ingest.fundamentals import _resolve_ttm_revenue

    tag_responses = _all_revenue_tags_none()
    tag_responses["us-gaap:RevenuesNetOfInterestExpense"] = 30_000_000_000.0  # net total
    tag_responses["us-gaap:NoninterestIncome"] = 50_000_000_000.0  # LARGER gross fee line
    facts = _make_ttm_facts(tag_responses)

    value, _, _ = _resolve_ttm_revenue(facts, today=date(2026, 6, 1))

    assert value == pytest.approx(30_000_000_000.0), (
        "consolidated net revenue must win; the larger NoninterestIncome fallback "
        "must NOT be consulted when a standard concept resolved"
    )
