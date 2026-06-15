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
import math
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from edgar import Company, set_identity
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential

from compute import config

logger = logging.getLogger(__name__)


# Issue #246 PR2a (0.10.3-phase4.5e) — Rule 18 observability retrofit for
# the ``_fetch_shares_from_per_filing_xbrl`` fallback trigger extended in
# PR #253. Counters increment from inside ``_build_snapshot``, which runs
# under a ThreadPoolExecutor in ``compute/main.py:717`` — hence the lock.
# Sequential-loop counter pattern used by other Rule-18 surfaces in main.py
# doesn't apply here because the fallback fires before the snapshot is
# returned (snapshot doesn't carry per-ticker fallback metadata; adding
# such a field would pollute the serialized schema).
#
# Lifecycle:
#   - ``reset_fallback_stats()`` BEFORE the fundamentals fetch loop in main.py
#   - ``get_fallback_stats()`` AFTER the fetch loop to read counters
#   - counters are NOT reset between successive ``run_weekly_compute`` calls
#     within the same process; consumer responsibility (main.py calls reset).
_FALLBACK_STATS_LOCK = threading.Lock()
_FALLBACK_STATS: dict[str, int] = {
    "triggered": 0,
    "too_low": 0,
    "dimensional_override": 0,
    # Issue #261 PR-B (0.10.6-phase4.5e); semantics updated #374 (RATIFY-B,
    # 2026-06-11). ``per_class_override`` = tickers where the
    # MULTI_CLASS_OVERCOUNT allowlist path (Branch 3) CAPTURED the listed
    # line's per-class count into ``shares_outstanding_listed_class`` (GOOG /
    # GOOGL). Since #374 ``shares_outstanding`` RETAINS the companyfacts
    # company-total aggregate (ASC 260, class-invariant) — the per-class value
    # no longer overrides it; the counter still increments per Branch-3 capture
    # (name kept for cross-cron comparability). ``mc_reconcile_failure`` =
    # defensive Rule-18 counter for the post-capture sanity check
    # |Σ per-class − aggregate| / aggregate < 5% (Damodaran 2019 Ch. 16
    # identity check; expected steady-state = 0 firings).
    "per_class_override": 0,
    "mc_reconcile_failure": 0,
    # Issue #288 (0.10.8-phase4.6, 2026-05-28) — Rule-18 disambiguator.
    # ``per_class_attempt`` increments each time Branch 3 ENTERS the
    # ``_fetch_shares_from_per_filing_xbrl(target_class_member=...)`` call,
    # regardless of whether XBRL lookup succeeds. Disambiguates the prior
    # silent-None mode: pre-fix this counter would be 2 (GOOG + GOOGL
    # both entered Branch 3) while ``per_class_override`` was 0, surfacing
    # the XBRL lookup failure that PR #269 missed. Post-fix expected
    # steady-state: per_class_attempt = per_class_override = 2.
    "per_class_attempt": 0,
}


def reset_fallback_stats() -> None:
    """Reset module-level fallback counters. Call BEFORE the per-ticker
    fundamentals fetch loop in main.py so the new cron's count starts at 0.
    """
    with _FALLBACK_STATS_LOCK:
        _FALLBACK_STATS["triggered"] = 0
        _FALLBACK_STATS["too_low"] = 0
        _FALLBACK_STATS["dimensional_override"] = 0
        _FALLBACK_STATS["per_class_override"] = 0
        _FALLBACK_STATS["mc_reconcile_failure"] = 0
        _FALLBACK_STATS["per_class_attempt"] = 0


def get_fallback_stats() -> dict[str, int]:
    """Return a shallow copy of the module-level fallback counters. Read
    AFTER the fundamentals fetch loop completes to populate
    ``Metadata.shares_fallback_triggered_count`` +
    ``Metadata.shares_fallback_too_low_count`` +
    ``Metadata.shares_fallback_dimensional_override_count``.
    """
    with _FALLBACK_STATS_LOCK:
        return dict(_FALLBACK_STATS)


# Issue #471 / #15 — Design B filing-precheck skip counter.
# Incremented (thread-safe) each time fetch_fundamentals serves the cached
# snapshot because SEC shows no new filing since the cached snapshot, skipping
# the heavy get_facts() companyfacts pull.
# Reset by reset_filing_precheck_skip_count() before the fetch loop; read by
# get_filing_precheck_skip_count() after.  Log-only diagnostic — no
# Metadata/schema field (keeps this PR off the schema triple).
_FILING_PRECHECK_SKIP_LOCK = threading.Lock()
_FILING_PRECHECK_SKIP_COUNT: list[int] = [0]  # list wrapper so the lock closure mutates in place


def reset_filing_precheck_skip_count() -> None:
    """Reset the filing-precheck skip counter. Call BEFORE the fundamentals fetch loop."""
    with _FILING_PRECHECK_SKIP_LOCK:
        _FILING_PRECHECK_SKIP_COUNT[0] = 0


def get_filing_precheck_skip_count() -> int:
    """Return the filing-precheck skip count accumulated since the last reset."""
    with _FILING_PRECHECK_SKIP_LOCK:
        return _FILING_PRECHECK_SKIP_COUNT[0]


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
# 10y (was 5) so the decade-long AI-pick backtest has 10-K facts back to ~2015 for
# its earliest (2016) rebalances. The live pillars only read their own shorter
# window, so older rows are simply ignored — no live-scoring change. Like a tag
# change, bumping this needs a workflow cache-key bump (the history cache is
# period-blind by CIK — see the cache-stale guard below).
ANNUAL_HISTORY_YEARS: int = 10

# ⚠️ Cache-stale guard (PR 4c.1 lesson — see fundamentals.py history):
# Adding a new metric to `_ANNUAL_TAGS` extends the parquet schema written
# to `compute/cache/fundamentals_history/<cik>.parquet`. Cached parquets
# from before the schema change are still considered "fresh" by
# `fetch_fundamentals_history` (180-day filing-date freshness only — it
# doesn't introspect columns). To force a fresh fetch in production,
# bump the workflow cache key (`cache-v4-` → `cache-v5-`) in
# `.github/workflows/compute-rankings.yml`.
#
# Same rule applies to `_TTM_REVENUE_TAGS`, `_TTM_NET_INCOME_TAGS`,
# `_TTM_FLOW_TAGS`, and `_BALANCE_TAGS` (see audit #6 / PR #49 history).
_ANNUAL_TAGS: dict[str, list[str]] = {
    "revenue": [
        # Mirror `_TTM_REVENUE_TAGS` for consistent annual history coverage
        # across utilities (DUK), tech (CRWD), banks (WFC / GS), etc.
        # Without these, _avg_3y_roe + revenue_cagr / DCF inputs all skip
        # for sector-specific filers (audit #6 deeper sweep).
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:RegulatedAndUnregulatedOperatingRevenue",
        "us-gaap:RevenuesNetOfInterestExpense",
        "us-gaap:SalesRevenueNet",
        # E&P / oil-and-gas filers (APA, COP, OXY, etc.) use this sector-
        # specific concept.  LAST in the chain so the `break` on first-non-
        # null (line ~1522) ensures standard filers never reach this tag.
        # (Issue #385 — mirrors _TTM_REVENUE_TAGS addition)
        "us-gaap:OilAndGasRevenue",
    ],
    "net_income": [
        # BKNG and similar filers tag NI under the longer concept name
        # while the standard one is frozen pre-2015.
        "us-gaap:NetIncomeLoss",
        "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
        "us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted",
        "us-gaap:ProfitLoss",
    ],
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
    # PR 4c — per-year stockholders_equity history (issue #11). Lets
    # `_avg_3y_roe` use per-year equity denominators instead of the
    # current-snapshot equity for all 3 years. Mirrors the `_BALANCE_TAGS`
    # chain (StockholdersEquity primary; the "IncludingNCI" variant covers
    # filers that consolidate non-controlling interest).
    "stockholders_equity": [
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
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
    # Issue #374 (RATIFY-B, 2026-06-11) — listed ticker's own per-class share
    # count from per-filing XBRL (e.g., GOOG Class C ≈ 5.43B, GOOGL Class A
    # ≈ 5.82B).  ``shares_outstanding`` above now holds the SEC companyfacts
    # AGGREGATE (company-total across ALL classes) per ASC 260 / RATIFY-B.
    # This field is populated only on cold/live crons for MULTI_CLASS_OVERCOUNT
    # tickers; warm-cache crons leave it as whatever was cached (may be None or
    # stale — acceptable because no scoring consumer reads this field).
    shares_outstanding_listed_class: float | None = None
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
    # Investment banks + diversified banks (GS, WFC, MS, ...) report
    # consolidated revenue net of interest expense under this concept.
    # Without it, pure banks ship with revenue=None.
    "us-gaap:RevenuesNetOfInterestExpense",
    "us-gaap:SalesRevenueNet",
    # E&P / oil-and-gas filers (APA, COP, OXY, etc.) tag consolidated
    # revenue under this sector-specific concept rather than the generic
    # `Revenues` concept.  The TTM selector is MAX-of-fresh (largest fresh
    # value wins, ORDER-INDEPENDENT — position in this list is irrelevant):
    # co-reporters keep their consolidated total (a segment line can't
    # exceed it); pure-E&P filers lacking every standard tag resolve here.
    # (Issue #385; co-report behavior pinned by
    # tests/test_ingest/test_oil_gas_revenue.py::test_ttm_co_reporter_max_wins)
    "us-gaap:OilAndGasRevenue",
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


def _fetch_shares_from_per_filing_xbrl(
    company: Company,
    ticker: str | None = None,
    *,
    target_class_member: str | None = None,
) -> float | None:
    """Issue #176 fallback — recover ``shares_outstanding`` from per-filing
    XBRL when the SEC companyfacts aggregate API has nothing OR when the
    aggregate is the wrong shape (returns total-across-classes when we
    want a single class — Issue #261 PR-B GOOG/GOOGL case).

    ``ticker`` is optional for back-compat (the function ran ticker-less
    in PR #182 and the 8 offline tests pass it positionally). When
    supplied, it's threaded into the failure-path ``logger.warning`` so
    a silent fallback miss (e.g., the cron #3 STZ regression on
    2026-05-23 where the recovery worked in a 2026-05-21 live probe but
    returned ``None`` two days later under cron load) is no longer
    invisible to the operator. See the PR-3d amplification precedent —
    bare ``except: return None`` is the same silent-drop pattern.

    ``target_class_member`` (Issue #261 PR-B, 2026-05-26) selects mode:

    - **None (default, sum-all mode)** — the PR #182 STZ-pattern: sum
      across ALL dimensional contexts at the most-recent date. Used for
      the UNDERCOUNT case where SEC ``companyfacts`` returns a per-class
      subset (or nothing) and the per-filing XBRL must aggregate every
      share class to recover the total. Triggered by the
      ``primary is None OR primary < MIN_PLAUSIBLE_SHARE_COUNT`` gate.
    - **Set (per-class filter mode)** — Issue #261 PR-B path: filter
      dimensional contexts to ONLY the row whose
      ``us-gaap:StatementClassOfStockAxis`` dimension equals the
      supplied member (e.g., ``"goog:CapitalClassCMember"`` for GOOG).
      Returns that single class's share count. Used for the OVERCOUNT
      case where ``companyfacts`` returns the AGGREGATE and the
      per-class ticker's ``market_cap`` was inflated 2× as a result.
      The filter requires ``xbrl.contexts[<context_ref>].dimensions``
      lookup — when that table is unavailable (older edgartools,
      missing context map), filter mode degrades to ``None`` rather
      than guessing.

    Background (2026-05-21 live SEC probe on STZ / Constellation Brands):

    - ``https://data.sec.gov/api/xbrl/companyfacts/CIK<n>.json`` filters
      out *dimensional* facts (those tagged with a member like a share
      class).
    - STZ files ``dei:EntityCommonStockSharesOutstanding`` only with a
      Class A / Class B dimension, so the aggregate returns nothing —
      cascading to a ``shares_outstanding = None`` snapshot even though
      revenue + balance-sheet totals extract cleanly.
    - The per-filing XBRL (``Filing.xbrl().facts.get_facts_by_concept``)
      DOES expose the dimensional contexts, so we can sum across share
      classes to get total common shares outstanding.

    Background (2026-05-26 live SEC probe on GOOG / Alphabet, Issue #261):

    - Alphabet files ``us-gaap:CommonStockSharesOutstanding`` with THREE
      dimensional contexts at FY2025 end: Class A (``us-gaap:Common-
      ClassAMember``, 5.822B = GOOGL), Class B (``us-gaap:CommonClass-
      BMember``, 0.837B, not traded), Class C (``goog:CapitalClass-
      CMember``, 5.429B = GOOG). Per-class sum reconciles to the
      non-dimensioned aggregate row (12.088B) exactly.
    - **Critical gotcha**: GOOG's Class C uses the **filer-specific
      namespace** ``goog:`` not the standard ``us-gaap:``. An allowlist
      keyed to ``us-gaap:CommonClassCMember`` would silently return
      zero rows. The :data:`compute.config.MULTI_CLASS_OVERCOUNT_ALLOWLIST`
      maps each ticker to the exact namespace+member string verified
      against the live filing.

    This function pulls the company's most recent 10-K (annual, largest
    fact set; falls back to 10-Q if no 10-K is on file), aggregates the
    cover-page common-shares-outstanding fact across the requested
    dimensional contexts (all of them in sum-all mode; just the target
    in filter mode), and returns the sum.

    Failure modes (all return ``None`` — graceful degradation per the
    ``portable-graceful-degradation-try-except`` discipline):

    - ``edgartools`` raises (network blip, schema drift, missing filing)
    - The most-recent filing has no XBRL attachment
    - None of the 3 queried concepts (``dei:EntityCommonStockSharesOutstanding``,
      ``us-gaap:CommonStockSharesOutstanding``, ``us-gaap:CommonStockSharesIssued``)
      returns dimensional rows matching the target class member
    - The summed value is zero or non-finite
    - **Filter mode only**: ``xbrl.contexts`` is missing or the target
      member doesn't appear in any context (allowlist entry is stale)

    The upstream ``share_count_extraction_missing`` annotate (PR #181)
    +``multi_class_aggregate_shares_suspected`` (PR #264) keep firing
    on ``None`` returns so the visibility gap stays closed even when
    this fallback can't recover the value.

    Cost: ~5-10s per affected ticker (one extra XBRL HTTP fetch). The
    caller gates the invocation on narrow signatures — either
    ``shares is None AND revenue > 0 AND total_assets > 0`` (sum-all
    mode) or ``ticker in MULTI_CLASS_OVERCOUNT_ALLOWLIST AND primary is
    plausible`` (filter mode) — so the universe-wide cost is bounded.
    """
    try:
        filings_10k = company.get_filings(form="10-K")
        filings_10q = company.get_filings(form="10-Q")
        # Prefer 10-K because it carries the larger fact set and the
        # most recent end-of-fiscal-year share count; fall back to the
        # latest 10-Q only when no 10-K is on file (rare on the S&P 500
        # but cheap to guard).
        candidates = []
        for fset in (filings_10k, filings_10q):
            if fset is None:
                continue
            try:
                top = fset.head(1)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "shares_outstanding fallback filings.head() failed for %s: %s: %s",
                    ticker or "?",
                    type(e).__name__,
                    e,
                )
                continue
            if top is None or len(top) == 0:
                continue
            candidates.append(top[0])
            break
        if not candidates:
            return None
        filing = candidates[0]
        xbrl = filing.xbrl()
        if xbrl is None or not hasattr(xbrl, "facts"):
            return None
        facts_view = xbrl.facts
        for concept in (
            "dei:EntityCommonStockSharesOutstanding",
            # Issue #288 fix (2026-05-28): `us-gaap:CommonStockSharesOutstanding`
            # was missing from the XBRL fallback concept list. Alphabet
            # (GOOG / GOOGL) files per-class share counts under THIS concept,
            # not under ``dei:EntityCommonStockSharesOutstanding``. Without
            # this concept in the query tuple, the filter-mode lookup at
            # lines 768-808 below would never find dimensional rows, so
            # ``_fetch_shares_from_per_filing_xbrl`` returned None for both
            # tickers since PR #269 landed (2026-05-26). The primary path at
            # lines 115-124 already queries all 3 concepts in this order;
            # this fix brings the XBRL fallback path to parity.
            "us-gaap:CommonStockSharesOutstanding",
            "us-gaap:CommonStockSharesIssued",
        ):
            try:
                df = facts_view.get_facts_by_concept(concept)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "shares_outstanding fallback get_facts_by_concept(%s) failed for %s: %s: %s",
                    concept,
                    ticker or "?",
                    type(e).__name__,
                    e,
                )
                continue
            if df is None or len(df) == 0:
                continue
            if "numeric_value" not in df.columns:
                continue
            # Share-count facts are instant-type in edgartools' shape —
            # the "as-of" date column is ``period_instant`` not
            # ``period_end`` (which is for flow-type facts like revenue).
            # Some shapes carry both; some carry just one. Use whichever
            # the DataFrame supplies, in instant-first order since the
            # canonical concepts here are instant-type.
            for date_col in ("period_instant", "period_end"):
                if date_col not in df.columns:
                    continue
                sub = df.dropna(subset=["numeric_value", date_col])
                if len(sub) == 0:
                    continue
                latest = sub[date_col].max()
                most_recent = sub[sub[date_col] == latest]
                if target_class_member is not None:
                    # Issue #261 PR-B filter mode — narrow to rows whose
                    # ``StatementClassOfStockAxis`` dimension equals the
                    # target member. Requires ``xbrl.contexts`` to map
                    # each row's ``context_ref`` to its dimensions dict.
                    if "context_ref" not in most_recent.columns:
                        continue
                    contexts = getattr(xbrl, "contexts", None)
                    if contexts is None:
                        continue
                    matched_values: list[float] = []
                    for _, row in most_recent.iterrows():
                        ctx_ref = row.get("context_ref")
                        if ctx_ref is None:
                            continue
                        try:
                            ctx = (
                                contexts.get(ctx_ref)
                                if hasattr(contexts, "get")
                                else contexts[ctx_ref]
                            )
                        except (KeyError, TypeError):
                            continue
                        if ctx is None:
                            continue
                        dims = getattr(ctx, "dimensions", None) or {}
                        # Match against the canonical axis; tolerate
                        # both ``us-gaap:`` and bare-axis-name forms
                        # (edgartools version drift).
                        axis_value = (
                            dims.get("us-gaap:StatementClassOfStockAxis")
                            or dims.get("StatementClassOfStockAxis")
                        )
                        if axis_value == target_class_member:
                            try:
                                matched_values.append(float(row["numeric_value"]))
                            except (TypeError, ValueError):
                                continue
                    if not matched_values:
                        continue
                    total = sum(matched_values)
                else:
                    total = float(most_recent["numeric_value"].sum())
                if math.isfinite(total) and total > 0:
                    return total
        return None
    except Exception as e:  # noqa: BLE001
        # Bug 2 fix (issue #220 / cron #3 STZ regression): on the outer
        # except, surface the failure as a WARNING (not silent None
        # return). The annotate `share_count_extraction_missing` still
        # fires upstream as the safety net, but the operator now has a
        # log line distinguishing "transient SEC 429" from "structural
        # XBRL shape drift" without re-running a live probe.
        logger.warning(
            "shares_outstanding fallback FAILED for %s — %s: %s "
            "(annotate share_count_extraction_missing will fire as safety net)",
            ticker or "?",
            type(e).__name__,
            e,
        )
        return None


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
    # Issue #374 (RATIFY-B, 2026-06-11) — accumulates the per-class share
    # count for MULTI_CLASS_OVERCOUNT tickers (GOOG / GOOGL).  Populated in
    # Branch 3 below; None for all other tickers.  ``shares_outstanding``
    # always holds the companyfacts AGGREGATE (company-total, class-invariant).
    _shares_outstanding_listed_class: float | None = None

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

    # Issue #176 + #246 fallback — per-filing XBRL dimensional-fact
    # aggregation for filers whose share-count facts are reported with
    # share-class dimensions (STZ Class A / Class B, ERIE Class A /
    # Class B) and therefore filtered out by the SEC companyfacts
    # aggregate API.
    #
    # Triggers when the rest of the snapshot looks healthy (revenue +
    # total_assets present) AND the primary path either returned None
    # (Issue #176 STZ signature shipped in PR #181) OR returned a value
    # below ``MIN_PLAUSIBLE_SHARE_COUNT`` (Issue #246 ERIE signature —
    # the aggregate API returned only Class B's 2,541 shares).
    # ``MIN_PLAUSIBLE_SHARE_COUNT`` is the S&P-500-floor sanity gate
    # documented in compute/config.py — see that comment for the
    # 30× safety margin rationale.
    #
    # See `_fetch_shares_from_per_filing_xbrl` docstring for the SEC API
    # probe results that motivated this fallback. Graceful-degradation
    # try/except keeps any per-filing fetch failure silent so the upstream
    # annotate keeps firing and ranks don't depend on this fallback path.
    primary_shares = balance_values.get("shares_outstanding")
    primary_too_low = (
        primary_shares is not None
        and primary_shares < config.MIN_PLAUSIBLE_SHARE_COUNT
    )
    if (
        (primary_shares is None or primary_too_low)
        and (revenue_val or 0) > 0
        and (balance_values.get("total_assets") or 0) > 0
    ):
        fallback_shares = _fetch_shares_from_per_filing_xbrl(company, ticker=ticker)
        if fallback_shares is not None:
            balance_values["shares_outstanding"] = fallback_shares
            # Issue #246 PR2a (0.10.3-phase4.5e) — Rule 18 observability
            # counter for the universe-wide fallback firing rate. Lock the
            # increment because _build_snapshot runs under a ThreadPool.
            with _FALLBACK_STATS_LOCK:
                _FALLBACK_STATS["triggered"] += 1
                if primary_too_low:
                    _FALLBACK_STATS["too_low"] += 1
            logger.info(
                "shares_outstanding fallback fired for %s/%s — "
                "primary=%s, fallback=%.0f (per-filing XBRL dimensional aggregation)",
                ticker,
                cik,
                "None" if primary_shares is None else f"{primary_shares:.0f}",
                fallback_shares,
            )
    elif (
        # Issue #248 PR2b (0.10.4-phase4.5e) — multi-class dimensional
        # override path. Primary path returned a PLAUSIBLE value (not None,
        # not implausibly low) but the ticker is a known multi-class issuer
        # whose ``companyfacts`` aggregate filters out non-primary share
        # classes. Peek the per-filing XBRL; if the dimensional sum across
        # all classes exceeds primary, the summed value is the truth
        # (Damodaran 2019 Ch. 16 — TSO = sum across all classes). The
        # allowlist gate keeps the peek bounded to the 7 verified tickers
        # so the universe-wide HTTP cost stays negligible.
        #
        # ``QR_SKIP_FUNDAMENTALS`` escape-hatch guard: simulate / CI runs
        # explicitly trade precision for speed. Skip the extra per-filing
        # XBRL probe (~10s/ticker × 7 tickers) on the cold-cache fallthrough
        # path — the primary plausible value is still written; only the
        # multi-class refinement is skipped. Closes the PR #257 simulate
        # 90-min cancellation root cause (ci-triage-engineer 2026-05-23).
        ticker is not None
        and ticker in config.MULTI_CLASS_SHARE_ALLOWLIST
        and primary_shares is not None
        and not primary_too_low
        and (revenue_val or 0) > 0
        and (balance_values.get("total_assets") or 0) > 0
        and not os.environ.get("QR_SKIP_FUNDAMENTALS")
    ):
        dimensional_summed = _fetch_shares_from_per_filing_xbrl(
            company, ticker=ticker
        )
        if (
            dimensional_summed is not None
            and dimensional_summed > primary_shares
        ):
            balance_values["shares_outstanding"] = dimensional_summed
            with _FALLBACK_STATS_LOCK:
                _FALLBACK_STATS["dimensional_override"] += 1
            logger.info(
                "shares_outstanding dimensional override for %s/%s — "
                "primary=%.0f, summed=%.0f (gain %.1f%%, multi-class allowlist)",
                ticker,
                cik,
                primary_shares,
                dimensional_summed,
                (dimensional_summed - primary_shares) / primary_shares * 100.0,
            )
    elif (
        # Issue #261 PR-B (0.10.6-phase4.5e) — per-class XBRL extraction
        # for the OVERCOUNT pattern. SEC ``companyfacts`` returns the
        # AGGREGATE share count across all classes for filers like
        # Alphabet (GOOG / GOOGL); each per-class ticker then renders a
        # $4.6T market_cap vs the real ~$1.05T per class (4.4× inflation).
        # Opposite direction to the PR #257 UNDERCOUNT allowlist elif
        # branch above (which SUMS to recover the total; this branch
        # FILTERS to extract a single class member).
        #
        # Trigger conditions:
        # - Ticker is on ``MULTI_CLASS_OVERCOUNT_ALLOWLIST`` (currently
        #   GOOG + GOOGL — see edgar-debugger probe 2026-05-26 for the
        #   filer-namespace gotcha around Class C)
        # - Primary path returned a PLAUSIBLE value (not None / too low)
        #   — this is the aggregate value we need to OVERRIDE
        # - ``QR_SKIP_FUNDAMENTALS`` not set (simulate / CI runs skip the
        #   precision refinement; matches the PR #257 elif behavior)
        #
        # Override condition: per_class_shares < primary_shares (the
        # per-class subset must be SMALLER than the aggregate — opposite
        # of the PR #257 ``summed > primary`` invariant). If the filter
        # returns >= primary, treat as a sanity-check failure and DO NOT
        # override (rather log the unexpected and keep primary).
        ticker is not None
        and ticker in config.MULTI_CLASS_OVERCOUNT_ALLOWLIST
        and primary_shares is not None
        and not primary_too_low
        and (revenue_val or 0) > 0
        and (balance_values.get("total_assets") or 0) > 0
        and not os.environ.get("QR_SKIP_FUNDAMENTALS")
    ):
        target_class = config.MULTI_CLASS_OVERCOUNT_ALLOWLIST[ticker]
        # Issue #288 (2026-05-28) — increment attempt counter BEFORE the
        # XBRL call so the Rule-18 diagnostic captures "branch entered but
        # XBRL returned None" (the regression mode PR #269 silently hit).
        with _FALLBACK_STATS_LOCK:
            _FALLBACK_STATS["per_class_attempt"] += 1
        per_class_shares = _fetch_shares_from_per_filing_xbrl(
            company, ticker=ticker, target_class_member=target_class
        )
        if (
            per_class_shares is not None
            and per_class_shares > 0
            and per_class_shares < primary_shares
        ):
            # Issue #374 (RATIFY-B, 2026-06-11) — REVERT the shares_outstanding
            # override.  ``shares_outstanding`` must hold the company-total
            # aggregate (ASC 260 / RATIFY-B convention) so it is class-invariant
            # and cannot corrupt the CIK-keyed parquet cache.  The per-class value
            # is preserved in the new ``shares_outstanding_listed_class`` field for
            # checksum / display purposes; no scoring consumer reads it.
            _shares_outstanding_listed_class = per_class_shares
            with _FALLBACK_STATS_LOCK:
                _FALLBACK_STATS["per_class_override"] += 1
            reduction_pct = (
                (primary_shares - per_class_shares) / primary_shares * 100.0
            )
            logger.info(
                "shares_outstanding_listed_class captured for %s/%s — "
                "aggregate=%.0f (kept in shares_outstanding), per_class=%.0f (%s), "
                "delta %.1f%% (RATIFY-B: aggregate is company-total, class-invariant)",
                ticker,
                cik,
                primary_shares,
                per_class_shares,
                target_class,
                reduction_pct,
            )
            # Defensive Rule-18 reconcile diagnostic (methodology Q3
            # 2026-05-26): the per-class value should be ~50% of primary
            # for GOOG/GOOGL (Alphabet's Class A ≈ Class C economic
            # weight). If the per-class is < 5% or > 95% of primary,
            # something looks structurally wrong — flag it. Does NOT
            # discard the captured ``shares_outstanding_listed_class``
            # value (it is still the best available per-class figure) but
            # surfaces the surprise for cohort-audit review.
            fraction = per_class_shares / primary_shares
            if fraction < 0.05 or fraction > 0.95:
                with _FALLBACK_STATS_LOCK:
                    _FALLBACK_STATS["mc_reconcile_failure"] += 1
                logger.warning(
                    "multi_class reconcile sanity check for %s/%s — "
                    "per_class=%.0f is %.1f%% of primary=%.0f "
                    "(outside expected 5-95%% band; verify XBRL shape)",
                    ticker,
                    cik,
                    per_class_shares,
                    fraction * 100.0,
                    primary_shares,
                )
        elif per_class_shares is not None and per_class_shares >= primary_shares:
            # Per-class >= primary is the sanity-check failure case —
            # the filter returned a value that's the same or larger
            # than the aggregate. Could mean (a) the filer's XBRL is
            # malformed, (b) we picked the wrong member, (c) the
            # allowlist entry is stale. DO NOT capture into
            # shares_outstanding_listed_class; log as warning so the
            # operator notices. (shares_outstanding stays the aggregate
            # regardless — RATIFY-B #374.)
            with _FALLBACK_STATS_LOCK:
                _FALLBACK_STATS["mc_reconcile_failure"] += 1
            logger.warning(
                "multi_class per-class capture SKIPPED for %s/%s — "
                "per_class=%.0f (%s) >= primary=%.0f; possible stale "
                "allowlist or XBRL shape drift",
                ticker,
                cik,
                per_class_shares,
                target_class,
                primary_shares,
            )

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
        # Issue #374 (RATIFY-B, 2026-06-11) — populated only when Branch 3 fires
        # (MULTI_CLASS_OVERCOUNT tickers on cold/live crons); None otherwise.
        shares_outstanding_listed_class=_shares_outstanding_listed_class,
        latest_filed_date=_max_date(*snapshot_dates),
        latest_period_end=max(period_dates) if period_dates else None,
    )


def _latest_filing_date(cik: str) -> date | None:
    """Return the most-recent 10-K or 10-Q filing date for ``cik``, or ``None``
    on any failure.

    Design B (#471 / #15): a cheap precheck that re-verifies the latest SEC
    filing date each cron run, so fetch_fundamentals can skip the heavy
    get_facts() / companyfacts pull when no new filing has appeared since the
    cached snapshot was written.

    Reuses the exact same Company + get_filings() pattern already proven in
    ``_fetch_shares_from_per_filing_xbrl`` (lines 764-765).  No new edgartools
    API surface introduced — ``get_filings`` is already called in-file.

    The whole body is wrapped in a broad ``except Exception`` so any edgartools
    drift, network blip, or unexpected shape returns ``None`` and the caller
    falls through to ``_build_snapshot`` (never skips on uncertainty).
    """
    try:
        company = Company(cik)
        filings_10k = company.get_filings(form="10-K")
        filings_10q = company.get_filings(form="10-Q")
        latest: date | None = None
        for fset in (filings_10k, filings_10q):
            if fset is None:
                continue
            try:
                top = fset.head(1)
            except Exception:  # noqa: BLE001
                continue
            if top is None or len(top) == 0:
                continue
            filing = top[0]
            fd = getattr(filing, "filing_date", None)
            if fd is None:
                continue
            # filing_date may be a date or datetime depending on edgartools
            # version; normalise to date.
            if isinstance(fd, datetime):
                fd = fd.date()
            if latest is None or fd > latest:
                latest = fd
        return latest
    except Exception:  # noqa: BLE001
        return None


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

    ``QR_SKIP_FUNDAMENTALS=1`` escape hatch: when set, the freshness gate is
    bypassed — if a cached snapshot exists for ``cik``, it is returned without
    a live EDGAR round-trip even if older than ``FUNDAMENTALS_REFETCH_DAYS``.
    Used by ``.github/workflows/pre-merge-prod-sim.yml`` to skip the 25-50 min
    cold-cache SEC fetch on docstring / comment / scoring-only PRs (the
    composite-score diff this workflow tracks compares PR-branch vs main's
    committed JSON — both sides should use the same upstream fundamentals
    input, so the cached parquets the weekly cron wrote are the CORRECT
    input). Falls through to live fetch when no cache exists (cold runner).
    Wired 2026-05-24 PR #230 — the QR_SKIP_TIER2 fix alone left the 25-50m
    fundamentals loop running, so simulate still cancelled at 45m.
    """
    if os.environ.get("QR_SKIP_FUNDAMENTALS"):
        cached = _load_cached(cik) if cik else None
        if cached is not None:
            logger.debug(
                "Fundamentals cache FORCE-HIT (QR_SKIP_FUNDAMENTALS=1) for %s "
                "(filed=%s)", ticker, cached.latest_filed_date,
            )
            return cached
        # No cache → fall through to live fetch (cold runner has nothing
        # to read; the simulate workflow's cache restore failed or is empty)
        logger.warning(
            "QR_SKIP_FUNDAMENTALS set but no cached parquet for %s — "
            "falling through to live EDGAR fetch", ticker,
        )

    _require_identity()

    cached = _load_cached(cik) if cik else None
    if cached is not None and _is_fresh(cached, today=today):
        logger.debug("Fundamentals cache HIT for %s (filed=%s)", ticker, cached.latest_filed_date)
        return cached

    # Issue #471 / #15 — Design B filing-date precheck (replaces Design C mtime gate).
    #
    # ROOT CAUSE: when a ticker's latest SEC filing is >FUNDAMENTALS_REFETCH_DAYS
    # old (e.g. big filers C/GE/IBM/Chubb in the quiet period between 10-Qs),
    # _is_fresh() returns False and we fall through to _build_snapshot() on EVERY
    # cron run.  But _build_snapshot() calls Company(cik).get_facts() — the heavy
    # companyfacts XBRL pull (19-36s for big filers).  Since the company hasn't
    # filed anything new, the refetch returns IDENTICAL data and latest_filed_date
    # doesn't advance, so it's stale again next run: a 100%-wasteful refetch loop.
    #
    # WHY NOT DESIGN C (mtime gate): the cron's fast cache uses an EXACT quarter
    # key (cache-v8-fast-<quarter>-<os>); on a cache hit, actions/cache SKIPS the
    # post-job save (immutability).  The fast cache is FROZEN within a quarter, so
    # a restored parquet's st_mtime is the last reseed time — often weeks old —
    # and the mtime < 7d gate NEVER fires for the stale tickers it was meant to
    # help.  Under the frozen cache the "wasteful" refetch is also LOAD-BEARING
    # for output freshness: a plain serve-cache design causes real staleness.
    #
    # FIX (Design B — filing-date precheck): for a stale-but-cached ticker, call
    # _latest_filing_date(cik) (a cheap get_filings("10-K"/"10-Q") that re-verifies
    # the latest SEC filing date each run) and skip _build_snapshot ONLY when no new
    # filing has appeared since the cached snapshot.  This reuses the Company
    # construction the refetch path already pays and skips ONLY the heavy get_facts()
    # companyfacts pull — less SEC load, no staleness.  The precheck itself is a
    # single HTTP call for the filings index, not the full companyfacts blob.
    #
    # FALLTHROUGH rule: if _latest_filing_date returns None (network error, missing
    # filings, any edgartools drift) OR if a newer filing is found, we ALWAYS fall
    # through to _build_snapshot.  Never skip on uncertainty.
    if cached is not None and cik and cached.latest_filed_date is not None:
        latest = _latest_filing_date(cik)  # cheap; None on any error
        if latest is not None and latest <= cached.latest_filed_date:
            # No new SEC filing since the cached snapshot — companyfacts are
            # unchanged; serve cache and skip the heavy get_facts() pull (#471/#15).
            with _FILING_PRECHECK_SKIP_LOCK:
                _FILING_PRECHECK_SKIP_COUNT[0] += 1
            logger.debug(
                "Fundamentals filing-precheck SKIP for %s "
                "(cached filed=%s, SEC latest=%s) — "
                "no new filing, skipping companyfacts pull (#471)",
                ticker,
                cached.latest_filed_date,
                latest,
            )
            return cached
        # else: latest is None (helper failed) or latest > cached.latest_filed_date
        # (new filing exists) → fall through to live _build_snapshot below.

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

    ``QR_SKIP_FUNDAMENTALS=1`` escape hatch: when set (and
    ``force_refresh=False``), the annual cache is returned regardless of
    age. Pairs with ``fetch_fundamentals`` above; see that docstring for the
    simulate-workflow rationale.
    """
    if os.environ.get("QR_SKIP_FUNDAMENTALS") and not force_refresh:
        cache = _annual_cache_path(cik)
        if cache.exists():
            try:
                cached_df = pd.read_parquet(cache)
                if not cached_df.empty:
                    return cached_df
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "QR_SKIP_FUNDAMENTALS annual cache read failed for %s: %s "
                    "— falling through to live fetch", cik, e,
                )
        # No cache or read failed → fall through to normal path

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
