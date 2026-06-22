"""Tests for Issue #566 — pure-advisory investment-bank revenue extraction.

Pure-advisory IBs (Moelis MC, Evercore EVR, Houlihan Lokey HLI, PJT, Lazard
LAZ) have negligible interest income and tag consolidated fee revenue under the
ASC 942 broker-dealer concept ``us-gaap:NoninterestIncome`` (or, less commonly,
``us-gaap:BrokerageCommissionsRevenue``) rather than any ``Revenues*`` concept.
Without these tags in ``_TTM_REVENUE_TAGS`` they ship with revenue=None, which
(combined with empty dimensional DEI share contexts) blocked the per-filing
XBRL shares fallback and left ``market_cap`` / fair-price null while the stock
still SCORED — the misleading-``lean_bullish``-with-no-context case for MC.

Coverage:
- Structural guard: the two advisory tags are present in ``_TTM_REVENUE_TAGS``.
- TTM path: an advisory-only filer (revenue ONLY under ``NoninterestIncome``)
  resolves a non-None TTM revenue.
- No regression: a diversified bank reporting BOTH ``RevenuesNetOfInterestExpense``
  (larger, consolidated) AND a smaller ``NoninterestIncome`` segment still
  resolves the LARGER consolidated value (MAX-of-fresh is order-independent).
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


def test_advisory_revenue_tags_present():
    """Structural guard: both ASC 942 broker-dealer fee-revenue concepts are in
    ``_TTM_REVENUE_TAGS`` (#566). Removing either re-breaks pure-advisory IBs."""
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS

    assert "us-gaap:NoninterestIncome" in _TTM_REVENUE_TAGS
    assert "us-gaap:BrokerageCommissionsRevenue" in _TTM_REVENUE_TAGS


def test_oil_gas_revenue_still_last_in_ttm_chain():
    """The #566 additions are inserted BEFORE ``SalesRevenueNet`` /
    ``OilAndGasRevenue``, so the documented OilAndGasRevenue-is-last invariant
    (test_oil_gas_revenue.py) must still hold."""
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS

    assert _TTM_REVENUE_TAGS[-1] == "us-gaap:OilAndGasRevenue"


def test_ttm_advisory_only_filer_resolves_revenue():
    """A pure-advisory IB (Moelis-class) that reports revenue ONLY under
    ``us-gaap:NoninterestIncome`` must resolve a non-None TTM revenue."""
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS, _try_ttm_max_fresh

    tag_responses: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    tag_responses["us-gaap:NoninterestIncome"] = 1_200_000_000.0  # MC-scale fee revenue

    facts = _make_ttm_facts(tag_responses)

    value, filed, pe = _try_ttm_max_fresh(facts, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))

    assert value is not None, "advisory-only filer must resolve a TTM revenue"
    assert value == pytest.approx(1_200_000_000.0)
    assert pe == _RECENT_PE
    assert filed == _RECENT_FD


def test_ttm_diversified_bank_consolidated_wins_over_noninterest_segment():
    """No regression: a diversified bank reporting BOTH a larger consolidated
    ``RevenuesNetOfInterestExpense`` AND a smaller ``NoninterestIncome`` segment
    resolves the LARGER consolidated value (MAX-of-fresh is order-independent),
    so adding the advisory tag cannot shrink a bank's revenue."""
    from compute.ingest.fundamentals import _TTM_REVENUE_TAGS, _try_ttm_max_fresh

    tag_responses: dict[str, float | None] = {t: None for t in _TTM_REVENUE_TAGS}
    tag_responses["us-gaap:RevenuesNetOfInterestExpense"] = 50_000_000_000.0  # GS-scale total
    tag_responses["us-gaap:NoninterestIncome"] = 30_000_000_000.0  # smaller fee segment

    facts = _make_ttm_facts(tag_responses)

    value, _, _ = _try_ttm_max_fresh(facts, _TTM_REVENUE_TAGS, today=date(2026, 6, 1))

    assert value == pytest.approx(50_000_000_000.0), (
        "MAX-of-fresh must keep the larger consolidated bank revenue"
    )
