"""SEC EDGAR fundamentals via edgartools.

Returns latest TTM flow items (revenue, net_income, operating_cash_flow, capex)
and latest point-in-time balance items (assets, liabilities, equity, cash,
shares_outstanding) for one ticker. Both ``period_end`` and ``filed_date`` are
preserved on every fact (Rule 5 — anti look-ahead bias).

Per-ticker disk cache lives at ``compute/cache/fundamentals/{cik}.parquet``.
A cached row is considered fresh if its newest ``filed_date`` is within
``FUNDAMENTALS_REFETCH_DAYS`` of today.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from edgar import Company, set_identity
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential

from compute import config

logger = logging.getLogger(__name__)


# Initialize EDGAR identity at module import. Failure is fatal — Phase 2
# compute hard-requires it; running without a real UA will get rejected by
# SEC with 403s and give the operator zero coverage.
def _require_identity() -> None:
    ua = os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "EDGAR_USER_AGENT environment variable is required for Phase 2 compute. "
            'Set it to "Your Name your@email.com" — SEC EDGAR rejects requests '
            "without a real contact string. In CI: add EDGAR_USER_AGENT to "
            "GitHub Actions secrets and reference via env: in compute-rankings.yml."
        )
    set_identity(ua)


# US-GAAP tag preference order per metric. First non-null wins.
_BALANCE_TAGS: dict[str, list[str]] = {
    "total_assets": ["us-gaap:Assets"],
    "total_liabilities": ["us-gaap:Liabilities"],
    "stockholders_equity": [
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "us-gaap:Cash",
    ],
    "shares_outstanding": [
        # DEI cover-page tag — most current for many filers (e.g., WMT,
        # ACN, MA). Audit #6 found WMT's `us-gaap:CommonStockSharesOutstanding`
        # held a stale pre-split value (3.42B vs ~8B post-Feb-2024 split).
        # DEI cover-page facts are filed every quarter with as-of date
        # close to the filing date, so they reflect splits / buybacks
        # faster than the balance-sheet concept.
        "dei:EntityCommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesIssued",
        # META, BRK-B and ~25 other S&P 500 filers don't tag
        # CommonStockSharesOutstanding at all — falls back to the
        # weighted-average diluted figure used in their EPS denominator.
        # This is a slight under-count vs point-in-time outstanding
        # (the diluted average lags buybacks / issuance within a quarter),
        # but it's far better than the None we shipped pre-audit-#6.
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "current_assets": ["us-gaap:AssetsCurrent"],
    "current_liabilities": ["us-gaap:LiabilitiesCurrent"],
    "inventory": ["us-gaap:InventoryNet"],
    "accounts_receivable": ["us-gaap:AccountsReceivableNetCurrent"],
    "accounts_payable": ["us-gaap:AccountsPayableCurrent"],
    "long_term_debt": ["us-gaap:LongTermDebt", "us-gaap:LongTermDebtNoncurrent"],
    "short_term_debt": [
        "us-gaap:DebtCurrent",
        "us-gaap:LongTermDebtCurrent",
        "us-gaap:ShortTermBorrowings",
    ],
    "retained_earnings": ["us-gaap:RetainedEarningsAccumulatedDeficit"],
    # Phase 3c additions — feed Tangible BVPS (full intangibles netting) per
    # docs/RESEARCH_FINDINGS.md "Defense Playbook §PR 3c §2 Tangible BVPS".
    # Goodwill is uniformly tagged (5/5 hit on AAPL/KO/PG/JPM/BRK-B probe);
    # intangibles_net needs a fallback chain because ~60% of filers use the
    # us-gaap:OtherIntangibleAssetsNet tag rather than the Excluding-Goodwill
    # variant. Coverage probe results in PR-3c kickoff D3 / E2.
    "goodwill": ["us-gaap:Goodwill"],
    "intangibles_net": [
        "us-gaap:IntangibleAssetsNetExcludingGoodwill",
        "us-gaap:OtherIntangibleAssetsNet",
        "us-gaap:FiniteLivedIntangibleAssetsNet",
    ],
    # PR 3e.1 — Beneish M-score needs PPE net for AQI + DEPI ratios.
    # PropertyPlantAndEquipmentNet is the standard tag for filers with
    # tangible operating assets; banks / REITs / asset-light tech may
    # report None, in which case Beneish drops to None and skips the flag.
    "property_plant_equipment": ["us-gaap:PropertyPlantAndEquipmentNet"],
}

# Concepts queried via the normalized snake_case API for latest values.
# Income-statement flow items (gross_profit, operating_income, ...) were
# REMOVED from this dict in audit #6 (deep clean, pre-v1.0) — they now
# flow through `_TTM_FLOW_TAGS` + `_try_ttm_max_fresh` to guarantee
# trailing-12-month aggregation. Only EPS items remain here because EPS
# is a per-share figure that the FASB stack reports as a single value
# per filing period; consumers (pe_ratio) should derive TTM EPS from
# NI_TTM / shares_outstanding instead.
_NORMALIZED_LATEST: dict[str, str] = {
    "eps_basic": "earnings_per_share_basic",
    "eps_diluted": "earnings_per_share_diluted",
}

# US-GAAP tags for TTM flow items.
_TTM_TAGS: dict[str, list[str]] = {
    "operating_cash_flow": ["us-gaap:NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
    ],
}

# US-GAAP tag chains for income-statement flow items previously fetched via
# the normalized snake_case API in `_NORMALIZED_LATEST`. Audit #6 (deep
# clean, pre-v1.0) showed that `facts.get_concept('operating_income')`
# returns the latest single-period value — which can be Q1, H1 YTD, or FY
# annual depending on filer cadence. Probed 4 tickers in May 2026:
# TSLA's `operating_income` came back as $941M (single quarter Q1-2026)
# while TTM is $4.9B — 5× error that compresses TSLA's profitability and
# health pillar scores universe-wide.
#
# Walking these through `_try_ttm_max_fresh` ensures every snapshot field
# represents a consistent trailing-12-month aggregation, comparable across
# tickers regardless of fiscal calendar.
#
# Fallback ordering for each metric: most-general / modern concept FIRST
# (so the MAX-of-fresh heuristic picks the consolidated total), with
# legacy + sector-specific fallbacks last.
_TTM_FLOW_TAGS: dict[str, list[str]] = {
    "operating_income": ["us-gaap:OperatingIncomeLoss"],
    "gross_profit": ["us-gaap:GrossProfit"],
    "cost_of_revenue": [
        "us-gaap:CostOfRevenue",
        "us-gaap:CostOfGoodsAndServicesSold",
        "us-gaap:CostOfGoodsSold",
        "us-gaap:CostOfServices",
    ],
    "sga_expense": [
        "us-gaap:SellingGeneralAndAdministrativeExpense",
        "us-gaap:GeneralAndAdministrativeExpense",
    ],
    "depreciation_and_amortization": [
        "us-gaap:DepreciationDepletionAndAmortization",
        "us-gaap:DepreciationAndAmortization",
        "us-gaap:Depreciation",
    ],
    "interest_expense": [
        # Newest concepts first — `us-gaap:InterestExpense` frozen post-2024
        # for many filers (AAPL, MSFT, JPM, TSLA all probed stale).
        "us-gaap:InterestExpenseOperating",
        "us-gaap:InterestExpenseNonoperating",
        "us-gaap:InterestExpense",
        "us-gaap:InterestExpenseDebt",
    ],
    "income_tax_expense": ["us-gaap:IncomeTaxExpenseBenefit"],
    "research_and_development": ["us-gaap:ResearchAndDevelopmentExpense"],
    "income_before_tax": [
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "dividends_paid": [
        "us-gaap:PaymentsOfDividendsCommonStock",
        "us-gaap:PaymentsOfDividends",
    ],
}

# Annual history concepts for CAGR + Piotroski. Tuple of (snapshot_key,
# US-GAAP tag list, fallback lookup). Pulled per fiscal year for the last
# ``ANNUAL_HISTORY_YEARS`` years.
ANNUAL_HISTORY_YEARS: int = 5

_ANNUAL_TAGS: dict[str, list[str]] = {
    "revenue": [
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
    ],
    "net_income": ["us-gaap:NetIncomeLoss"],
    "operating_cash_flow": ["us-gaap:NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"],
    "eps_diluted": ["us-gaap:EarningsPerShareDiluted"],
    "total_assets": ["us-gaap:Assets"],
    "long_term_debt": ["us-gaap:LongTermDebt", "us-gaap:LongTermDebtNoncurrent"],
    "current_assets": ["us-gaap:AssetsCurrent"],
    "current_liabilities": ["us-gaap:LiabilitiesCurrent"],
    "shares_outstanding": ["us-gaap:CommonStockSharesOutstanding"],
    "gross_profit": ["us-gaap:GrossProfit"],
    # PR 3e.1 — Beneish M-score year-over-year inputs (prior-year denominators
    # for DSRI / GMI / AQI / SGI / DEPI / SGAI / LVGI).
    # PR 3e.x — fallback chains expanded post-3e.2 production run, which found
    # Beneish coverage at 5.6% on S&P 500 because legacy XBRL tags (still in
    # heavy use by industrial / retail / energy filers) were missing from the
    # chains. Rationale per tag below.
    "cost_of_revenue": [
        # Modern post-2015 tags (~55% of S&P 500 filers).
        "us-gaap:CostOfGoodsAndServicesSold",
        "us-gaap:CostOfRevenue",
        # Legacy tag still dominant in manufacturers / retailers / staples
        # (~40% of filers — single biggest pre-3e.x coverage gap).
        "us-gaap:CostOfGoodsSold",
        # Pure-service filers (banks, consultancies) use this split.
        "us-gaap:CostOfServices",
    ],
    "accounts_receivable": [
        "us-gaap:AccountsReceivableNetCurrent",
        # Some healthcare / financial-services filers tag receivables under
        # the broader "Receivables" or "AccountsAndOtherReceivables" concept.
        "us-gaap:ReceivablesNetCurrent",
        "us-gaap:AccountsAndOtherReceivablesNetCurrent",
    ],
    "sga_expense": [
        "us-gaap:SellingGeneralAndAdministrativeExpense",
        "us-gaap:GeneralAndAdministrativeExpense",
        # Tech filers commonly split S/M and G/A into separate lines — when
        # the SGA-combined concept isn't filed, OperatingExpenses (excluding
        # COGS + R&D) is the closest single-line proxy. Caveat: this
        # over-counts vs. strict S+G+A.
        "us-gaap:OperatingExpenses",
    ],
    "depreciation_and_amortization": [
        "us-gaap:DepreciationAndAmortization",
        "us-gaap:DepreciationDepletionAndAmortization",
        # Many filers (esp. tech / IP-heavy) tag depreciation separately
        # from amortization. Falling back to Depreciation alone under-counts
        # vs. strict D&A by the amortization-of-intangibles portion, but it
        # preserves the year-over-year ratio signal which is what Beneish
        # DEPI cares about.
        "us-gaap:Depreciation",
    ],
    "property_plant_equipment": ["us-gaap:PropertyPlantAndEquipmentNet"],
    # PR 3e.2 — Dechow F-score Δinventory input.
    "inventory": ["us-gaap:InventoryNet"],
}

ALL_METRIC_KEYS: tuple[str, ...] = (
    # Phase 2 core
    "revenue",
    "net_income",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "cash",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "eps_basic",
    "eps_diluted",
    "shares_outstanding",
    # Phase 3 additions
    "gross_profit",
    "operating_income",
    "cost_of_revenue",
    "research_and_development",
    "sga_expense",
    "depreciation_and_amortization",
    "interest_expense",
    "income_tax_expense",
    "income_before_tax",
    "dividends_paid",
    "current_assets",
    "current_liabilities",
    "inventory",
    "accounts_receivable",
    "accounts_payable",
    "long_term_debt",
    "short_term_debt",
    "retained_earnings",
    "ebitda",  # computed = operating_income + D&A
    # Phase 3c additions
    "goodwill",
    "intangibles_net",
    # Phase 3e additions — Beneish M-score AQI + DEPI inputs
    "property_plant_equipment",
)


@dataclass
class FundamentalsSnapshot:
    """One row per ticker — a flat snapshot of latest values + latest filing_date."""

    ticker: str
    cik: str
    # Phase 2 core
    revenue: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    stockholders_equity: float | None = None
    cash: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    shares_outstanding: float | None = None
    # Phase 3 additions — income statement
    gross_profit: float | None = None
    operating_income: float | None = None
    cost_of_revenue: float | None = None
    research_and_development: float | None = None
    sga_expense: float | None = None
    depreciation_and_amortization: float | None = None
    interest_expense: float | None = None
    income_tax_expense: float | None = None
    income_before_tax: float | None = None
    dividends_paid: float | None = None
    # Phase 3 additions — balance sheet
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None
    accounts_receivable: float | None = None
    accounts_payable: float | None = None
    long_term_debt: float | None = None
    short_term_debt: float | None = None
    retained_earnings: float | None = None
    # Phase 3 derived
    ebitda: float | None = None  # operating_income + D&A
    # Phase 3c additions — Tangible BVPS inputs (Defense Playbook §PR 3c §2)
    goodwill: float | None = None
    intangibles_net: float | None = None
    # Phase 3e.1 — Property/plant/equipment net (Beneish M-score AQI + DEPI)
    property_plant_equipment: float | None = None
    # Filing dates
    latest_filed_date: date | None = None
    latest_period_end: date | None = None

    def to_record(self) -> dict[str, Any]:
        return {**self.__dict__}

    def missing_fields(self) -> list[str]:
        return [k for k in ALL_METRIC_KEYS if getattr(self, k, None) is None]


def _max_date(*candidates: date | None) -> date | None:
    real = [d for d in candidates if d is not None]
    return max(real) if real else None


def _try_balance_tags(facts, tags: list[str]) -> tuple[float | None, date | None, date | None]:
    """Return (value, period_end, filing_date) for the first tag that resolves."""
    for tag in tags:
        f = facts.get_fact(tag)
        if f is not None and f.value is not None:
            return float(f.value), f.period_end, f.filing_date
    return None, None, None


def _try_balance_tags_most_recent(
    facts, tags: list[str]
) -> tuple[float | None, date | None, date | None]:
    """Like ``_try_balance_tags`` but picks the candidate concept with the
    most recent ``period_end`` across the entire chain.

    Workaround for stale DEI cover-page facts (audit #6): the ``dei:Entity
    CommonStockSharesOutstanding`` tag holds the most-recent value for
    most filers (WMT post-split, META, ACN) BUT is frozen at 2010-2011
    for some legacy filers (MA shows 122M from 2010-10-27 vs the correct
    893M from 2026-03-31 via WeightedAverageDiluted; BRK-B shows 941k
    from 2011 vs the correct ~2.16B). First-non-null chain ordering
    can't distinguish "current DEI" from "stale DEI" — has to pick by
    date instead.

    Use this for any balance concept where multiple alternative tags
    have different reporting cadences (shares_outstanding is the
    canonical case).
    """
    candidates: list[tuple[float, date, date | None]] = []
    for tag in tags:
        f = facts.get_fact(tag)
        if f is None or f.value is None or f.period_end is None:
            continue
        try:
            v = float(f.value)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        candidates.append((v, f.period_end, f.filing_date))
    if not candidates:
        return None, None, None
    best = max(candidates, key=lambda c: c[1])
    return best


def _try_ttm_tags(facts, tags: list[str]) -> tuple[float | None, date | None]:
    """Return (TTM value, max filing_date across the 4 quarters)."""
    for tag in tags:
        try:
            ttm = facts.get_ttm(tag)
        except Exception:  # noqa: BLE001
            continue
        if ttm is not None and ttm.value is not None:
            latest_filed = None
            for pf in getattr(ttm, "period_facts", []) or []:
                fd = getattr(pf, "filing_date", None)
                if fd is not None and (latest_filed is None or fd > latest_filed):
                    latest_filed = fd
            return float(ttm.value), latest_filed
    return None, None


# TTM concept chains for revenue + net_income. Both walked by
# ``_try_ttm_max_fresh`` (NOT ``edgartools.get_ttm_revenue``) because:
#
# 1. edgartools' built-in helper iterates concepts but doesn't reject stale
#    data — NVDA stopped filing under ``RevenueFromContractWithCustomerExcludingAssessedTax``
#    in 2022, leaving FY2020 quarters as the "TTM" result ($10.9B instead of
#    the real $215B). The freshness check (period_end > today - 540d) rejects
#    those.
# 2. For REITs / Financials, both ``Revenues`` and ``RevenueFromContractWithCustomerExcludingAssessedTax``
#    can be fresh, but the latter is a subset (contract revenue only, excluding
#    rental income for REITs / interest income for banks). Taking the MAX
#    among fresh candidates picks the consolidated total — AVB ($3.07B) over
#    the $7.1M contract subset.
#
# Probed across 10 diverse tickers in 2026-05; both heuristics needed to
# cover all sectors.
_TTM_REVENUE_TAGS: list[str] = [
    "us-gaap:Revenues",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    # CrowdStrike + some other tech filers use the "Including" assessed-tax
    # variant of the ASC 606 concept rather than the more common
    # "Excluding" variant. Including = revenue gross of sales tax;
    # the MAX-of-fresh heuristic picks whichever is consolidated.
    "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
    # Utilities (DUK, AEP, ED, etc.) tag operating revenue under this
    # sector-specific concept. `us-gaap:Revenues` is often frozen at
    # pre-2018 quarters for these filers.
    "us-gaap:RegulatedAndUnregulatedOperatingRevenue",
    "us-gaap:SalesRevenueNet",
]
_TTM_NET_INCOME_TAGS: list[str] = [
    "us-gaap:NetIncomeLoss",
    # BKNG and some other filers tag NI under this longer concept while
    # leaving the standard NetIncomeLoss frozen at 2012-2015. The MAX-of-
    # fresh heuristic picks the right one — extending the chain is
    # enough.
    "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
    "us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted",
    "us-gaap:NetIncome",
    "us-gaap:ProfitLoss",
]
# Stale-data rejection threshold. 540 days = 18 months — generous tolerance
# for fiscal-calendar variance + filing lag.
_TTM_STALE_DAYS: int = 540


def _try_ttm_max_fresh(
    facts,
    tags: list[str],
    *,
    today: date | None = None,
) -> tuple[float | None, date | None, date | None]:
    """Walk ``tags`` and return (TTM value, filing_date, period_end) of the
    fresh concept with the **largest** TTM value.

    Workaround for edgartools' ``get_ttm_revenue()`` / ``get_ttm_net_income()``
    convenience helpers which (a) don't reject stale data and (b) return the
    first matching concept, which may be a subset of total revenue for
    REITs / banks / insurers.

    Freshness threshold: period_end must be within ``_TTM_STALE_DAYS`` (540
    days) of ``today``. Stale results are silently skipped — so if every
    candidate concept is stale, this returns ``(None, None, None)`` which
    surfaces as missing fundamentals (Section G coverage drop) rather than
    a corrupt-data ranking.
    """
    today = today or datetime.utcnow().date()
    cutoff = today - timedelta(days=_TTM_STALE_DAYS)
    candidates: list[tuple[float, date | None, date]] = []
    for tag in tags:
        try:
            ttm = facts.get_ttm(tag)
        except Exception:  # noqa: BLE001
            continue
        if ttm is None or ttm.value is None:
            continue
        latest_pe: date | None = None
        latest_filed: date | None = None
        for pf in getattr(ttm, "period_facts", []) or []:
            pe = getattr(pf, "period_end", None)
            if pe is not None and (latest_pe is None or pe > latest_pe):
                latest_pe = pe
            fd = getattr(pf, "filing_date", None)
            if fd is not None and (latest_filed is None or fd > latest_filed):
                latest_filed = fd
        if latest_pe is None or latest_pe < cutoff:
            continue
        candidates.append((float(ttm.value), latest_filed, latest_pe))
    if not candidates:
        return None, None, None
    return max(candidates, key=lambda c: c[0])


@retry(
    stop=(stop_after_delay(30) | stop_after_attempt(2)),
    wait=wait_exponential(min=2, max=8),
    reraise=True,
)
def _build_snapshot(ticker: str, cik: str) -> FundamentalsSnapshot:
    """Pull and assemble the snapshot from EDGAR. Caller wraps in retry-aware caching.

    Retry policy: caps at the FIRST of 30 seconds total wall-clock OR 2
    attempts. The previous ``stop_after_attempt(3)`` +
    ``wait_exponential(max=30)`` policy could spend 60-90s per stuck CIK
    under SEC API throttling (run #14 incident, 2026-05-10 — ~3-6× SEC
    API slowdown). Tightening to (30s | 2 attempts) caps per-stock retry
    cost at ~30s while still absorbing transient blips.
    """
    company = Company(cik or ticker)
    facts = company.get_facts()
    if facts is None:
        raise RuntimeError(f"No EntityFacts for {ticker}/{cik}")
    # Suppress edgartools' UserWarning noise on concept/period misses.
    # The TTM and balance-item concept lookups below tolerate misses (None
    # checks) but the warnings module formats traceback at stacklevel=2
    # plus optional difflib fuzzy-match suggestions — pure log noise that
    # we don't action on. Same pattern as _build_annual_history.
    try:
        facts._suppress_warnings = True
    except (AttributeError, TypeError):
        pass  # edgartools version variance — non-fatal

    snapshot_dates: list[date | None] = []
    period_dates: list[date | None] = []

    # TTM revenue + net_income via the freshness-aware MAX helper, NOT
    # edgartools' get_ttm_revenue() / get_ttm_net_income() helpers — see
    # _try_ttm_max_fresh() docstring for the NVDA + AVB regression cases
    # this guards against (audit #5 — pre-v1.0 stop-the-line, 2026-05).
    revenue_val, revenue_filed, revenue_pe = _try_ttm_max_fresh(facts, _TTM_REVENUE_TAGS)
    if revenue_pe is not None:
        period_dates.append(revenue_pe)
    snapshot_dates.append(revenue_filed)

    ni_val, ni_filed, ni_pe = _try_ttm_max_fresh(facts, _TTM_NET_INCOME_TAGS)
    if ni_pe is not None:
        period_dates.append(ni_pe)
    snapshot_dates.append(ni_filed)

    # Other TTM flow items
    cfo_val, cfo_filed = _try_ttm_tags(facts, _TTM_TAGS["operating_cash_flow"])
    capex_val, capex_filed = _try_ttm_tags(facts, _TTM_TAGS["capex"])
    snapshot_dates.extend([cfo_filed, capex_filed])

    fcf_val: float | None = None
    if cfo_val is not None and capex_val is not None:
        # Capex on cash flow statements is typically reported as a negative;
        # FCF = CFO - |CapEx|. edgartools usually returns the absolute outflow.
        fcf_val = cfo_val - abs(capex_val)

    # Latest balance sheet items
    balance_values: dict[str, float | None] = {}
    for key, tags in _BALANCE_TAGS.items():
        # shares_outstanding uses MAX-of-most-recent across alternative
        # concepts because the DEI tag is frozen at 2010-2011 for some
        # legacy filers (MA, BRK-B) while being current for others (WMT,
        # META, ACN). First-non-null chaining can't tell them apart;
        # most-recent-period selection picks the right one universally.
        # See `_try_balance_tags_most_recent` docstring for audit #6 detail.
        if key == "shares_outstanding":
            v, pe, fd = _try_balance_tags_most_recent(facts, tags)
        else:
            v, pe, fd = _try_balance_tags(facts, tags)
        balance_values[key] = v
        snapshot_dates.append(fd)
        if pe is not None:
            period_dates.append(pe)

    # Latest EPS values via normalized snake_case API (per-share figures
    # don't have a clean TTM-via-tag concept; consumers like pe_ratio
    # derive TTM EPS from NI_TTM / shares_outstanding instead).
    normalized: dict[str, float | None] = {}
    for out_key, concept in _NORMALIZED_LATEST.items():
        try:
            md = facts.get_concept(concept, return_metadata=True)
        except Exception:  # noqa: BLE001
            md = None
        if md is None:
            normalized[out_key] = None
            continue
        if isinstance(md, dict):
            normalized[out_key] = (
                float(md["value"]) if md.get("value") is not None else None
            )
        else:
            normalized[out_key] = float(md)

    # TTM income-statement flow items via the freshness-aware MAX helper
    # (audit #6). Replaces the previous `_NORMALIZED_LATEST` loop for
    # everything except EPS — those single-period values mixed quarterly /
    # YTD / annual across the universe, breaking gross_margin /
    # operating_margin / interest_coverage / Altman EBIT for ~88% of S&P 500.
    flow_values: dict[str, float | None] = {}
    for out_key, tags in _TTM_FLOW_TAGS.items():
        val, filed, pe = _try_ttm_max_fresh(facts, tags)
        flow_values[out_key] = val
        snapshot_dates.append(filed)
        if pe is not None:
            period_dates.append(pe)

    # Derive EBITDA from operating_income + D&A (knowledge §11.2; SEC doesn't
    # tag EBITDA directly). Both inputs are now TTM-aligned post-audit-#6
    # — previously they were quarterly/YTD partial values producing TSLA-
    # style 5× under-reporting on EV/EBITDA + Altman Z″ ratios.
    op_income = flow_values.get("operating_income")
    da = flow_values.get("depreciation_and_amortization")
    ebitda_val = (
        op_income + da if op_income is not None and da is not None else None
    )

    return FundamentalsSnapshot(
        ticker=ticker,
        cik=cik,
        revenue=revenue_val,
        net_income=ni_val,
        total_assets=balance_values.get("total_assets"),
        total_liabilities=balance_values.get("total_liabilities"),
        stockholders_equity=balance_values.get("stockholders_equity"),
        cash=balance_values.get("cash"),
        operating_cash_flow=cfo_val,
        capex=capex_val,
        free_cash_flow=fcf_val,
        eps_basic=normalized.get("eps_basic"),
        eps_diluted=normalized.get("eps_diluted"),
        shares_outstanding=balance_values.get("shares_outstanding"),
        gross_profit=flow_values.get("gross_profit"),
        operating_income=op_income,
        cost_of_revenue=flow_values.get("cost_of_revenue"),
        research_and_development=flow_values.get("research_and_development"),
        sga_expense=flow_values.get("sga_expense"),
        depreciation_and_amortization=da,
        interest_expense=flow_values.get("interest_expense"),
        income_tax_expense=flow_values.get("income_tax_expense"),
        income_before_tax=flow_values.get("income_before_tax"),
        dividends_paid=flow_values.get("dividends_paid"),
        current_assets=balance_values.get("current_assets"),
        current_liabilities=balance_values.get("current_liabilities"),
        inventory=balance_values.get("inventory"),
        accounts_receivable=balance_values.get("accounts_receivable"),
        accounts_payable=balance_values.get("accounts_payable"),
        long_term_debt=balance_values.get("long_term_debt"),
        short_term_debt=balance_values.get("short_term_debt"),
        retained_earnings=balance_values.get("retained_earnings"),
        ebitda=ebitda_val,
        goodwill=balance_values.get("goodwill"),
        intangibles_net=balance_values.get("intangibles_net"),
        property_plant_equipment=balance_values.get("property_plant_equipment"),
        latest_filed_date=_max_date(*snapshot_dates),
        latest_period_end=max(period_dates) if period_dates else None,
    )


def _cache_path_for(cik: str) -> os.PathLike[str]:
    config.FUNDAMENTALS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.FUNDAMENTALS_CACHE_DIR / f"{cik}.parquet"


def _load_cached(cik: str) -> FundamentalsSnapshot | None:
    path = _cache_path_for(cik)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to read fundamentals cache for cik=%s: %s", cik, e)
        return None
    if df.empty:
        return None
    record = df.iloc[0].to_dict()
    record["latest_filed_date"] = (
        pd.to_datetime(record["latest_filed_date"]).date()
        if record.get("latest_filed_date") is not None
        else None
    )
    record["latest_period_end"] = (
        pd.to_datetime(record["latest_period_end"]).date()
        if record.get("latest_period_end") is not None
        else None
    )
    # Drop NaN to None for floats.
    for k, v in list(record.items()):
        if pd.isna(v):
            record[k] = None
    return FundamentalsSnapshot(**record)


def _save_cached(snapshot: FundamentalsSnapshot) -> None:
    df = pd.DataFrame([snapshot.to_record()])
    df.to_parquet(_cache_path_for(snapshot.cik), index=False)


def _is_fresh(snapshot: FundamentalsSnapshot, today: date | None = None) -> bool:
    if snapshot.latest_filed_date is None:
        return False
    today = today or datetime.utcnow().date()
    return (today - snapshot.latest_filed_date) < timedelta(days=config.FUNDAMENTALS_REFETCH_DAYS)


def fetch_fundamentals(
    ticker: str, cik: str, *, today: date | None = None
) -> FundamentalsSnapshot | None:
    """Return a fundamentals snapshot for ``ticker``, hitting cache when fresh.

    Returns ``None`` on persistent EDGAR failure so the orchestrator can skip
    the ticker.
    """
    _require_identity()

    cached = _load_cached(cik) if cik else None
    if cached is not None and _is_fresh(cached, today=today):
        logger.debug("Fundamentals cache HIT for %s (filed=%s)", ticker, cached.latest_filed_date)
        return cached

    try:
        snapshot = _build_snapshot(ticker, cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("EDGAR fetch failed for %s/%s: %s", ticker, cik, e)
        return cached  # fall back to stale cache rather than nothing

    if cik:
        try:
            _save_cached(snapshot)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to write fundamentals cache for %s: %s", ticker, e)

    return snapshot


# -- Annual history (CAGR + Piotroski) --------------------------------------

@retry(
    stop=(stop_after_delay(30) | stop_after_attempt(2)),
    wait=wait_exponential(min=2, max=8),
    reraise=True,
)
def _build_annual_history(cik: str, years: int = ANNUAL_HISTORY_YEARS) -> pd.DataFrame:
    """Fetch ``years`` of annual 10-K facts for the metrics in ``_ANNUAL_TAGS``.

    Returns a tidy long DataFrame indexed by (fiscal_year, metric) with columns:
        value, period_end, filing_date, form_type

    Empty DataFrame on any failure so the caller can degrade gracefully.

    Retry policy
    ------------
    Caps at the FIRST of: 30 seconds total wall-clock OR 2 attempts. The
    earlier ``stop_after_attempt(3)`` + ``wait_exponential(max=30)`` policy
    could spend 60-90 seconds per stuck CIK under SEC API throttling
    (run #14 incident, 2026-05-10 — ~3-6× SEC API slowdown). Tightening
    to (30s | 2 attempts) caps per-stock retry cost at ~30s while still
    absorbing transient blips.
    """
    company = Company(cik)
    facts = company.get_facts()
    if facts is None:
        return pd.DataFrame()
    # Suppress edgartools' UserWarning storm on concept/fiscal-year misses.
    # Each get_annual_fact() call below misses for ~60-70% of (fy × tag)
    # combinations; the warnings are pure log noise (the call already
    # returns None which we already handle). Suppressing also skips the
    # difflib fuzzy-match suggestion pass at edgar/entity/entity_facts.py:677
    # which is the only non-trivial CPU cost in the warning path.
    try:
        facts._suppress_warnings = True
    except (AttributeError, TypeError):
        pass  # edgartools version variance — non-fatal

    today_year = datetime.utcnow().year
    fiscal_years = list(range(today_year - years - 1, today_year + 1))
    rows: list[dict[str, Any]] = []
    for fy in fiscal_years:
        for metric, tags in _ANNUAL_TAGS.items():
            for tag in tags:
                try:
                    f = facts.get_annual_fact(tag, fiscal_year=fy)
                except Exception:  # noqa: BLE001
                    f = None
                if f is None or f.value is None:
                    continue
                rows.append(
                    {
                        "fiscal_year": fy,
                        "metric": metric,
                        "value": float(f.value),
                        "period_end": getattr(f, "period_end", None),
                        "filing_date": getattr(f, "filing_date", None),
                        "form_type": getattr(f, "form_type", None),
                    }
                )
                break  # first non-null tag wins
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _annual_cache_path(cik: str) -> Path:
    config.FUNDAMENTALS_HISTORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.FUNDAMENTALS_HISTORY_CACHE_DIR / f"{cik}.parquet"


def fetch_fundamentals_history(
    cik: str, *, force_refresh: bool = False
) -> pd.DataFrame:
    """Return annual fundamentals history for ``cik``. Cached per CIK.

    Cache invalidates on the same 45-day rule as the snapshot — re-fetch when
    the latest annual filing is older than the threshold.
    """
    _require_identity()
    cache = _annual_cache_path(cik)

    if not force_refresh and cache.exists():
        try:
            cached_df = pd.read_parquet(cache)
            if not cached_df.empty:
                latest = pd.to_datetime(cached_df["filing_date"]).max()
                if (datetime.utcnow() - latest.to_pydatetime()).days < (
                    config.FUNDAMENTALS_REFETCH_DAYS * 4
                ):
                    return cached_df
        except Exception as e:  # noqa: BLE001
            logger.warning("Annual cache read failed for %s: %s", cik, e)

    try:
        df = _build_annual_history(cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("EDGAR annual fetch failed for %s: %s", cik, e)
        return pd.DataFrame()

    if not df.empty:
        try:
            df.to_parquet(cache, index=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("Annual cache write failed for %s: %s", cik, e)
    return df
