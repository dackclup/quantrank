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
        "us-gaap:CommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesIssued",
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
_NORMALIZED_LATEST: dict[str, str] = {
    "eps_basic": "earnings_per_share_basic",
    "eps_diluted": "earnings_per_share_diluted",
    "gross_profit": "gross_profit",
    "operating_income": "operating_income",
    "cost_of_revenue": "cost_of_revenue",
    "research_and_development": "research_and_development",
    "sga_expense": "sga_expense",
    "depreciation_and_amortization": "depreciation_and_amortization",
    "interest_expense": "interest_expense",
    "income_tax_expense": "income_tax_expense",
    "income_before_tax": "income_before_tax",
    "dividends_paid": "dividends_paid",
}

# US-GAAP tags for TTM flow items.
_TTM_TAGS: dict[str, list[str]] = {
    "operating_cash_flow": ["us-gaap:NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
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
    "cost_of_revenue": ["us-gaap:CostOfGoodsAndServicesSold", "us-gaap:CostOfRevenue"],
    "accounts_receivable": ["us-gaap:AccountsReceivableNetCurrent"],
    "sga_expense": [
        "us-gaap:SellingGeneralAndAdministrativeExpense",
        "us-gaap:GeneralAndAdministrativeExpense",
    ],
    "depreciation_and_amortization": [
        "us-gaap:DepreciationAndAmortization",
        "us-gaap:DepreciationDepletionAndAmortization",
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

    # TTM revenue + net_income via convenience helpers (handle concept fallback).
    revenue_val: float | None = None
    revenue_filed: date | None = None
    try:
        rev_ttm = facts.get_ttm_revenue()
        if rev_ttm is not None and rev_ttm.value is not None:
            revenue_val = float(rev_ttm.value)
            for pf in getattr(rev_ttm, "period_facts", []) or []:
                fd = getattr(pf, "filing_date", None)
                if fd is not None and (revenue_filed is None or fd > revenue_filed):
                    revenue_filed = fd
                pe = getattr(pf, "period_end", None)
                if pe is not None:
                    period_dates.append(pe)
    except Exception as e:  # noqa: BLE001
        logger.debug("get_ttm_revenue failed for %s: %s", ticker, e)
    snapshot_dates.append(revenue_filed)

    ni_val: float | None = None
    ni_filed: date | None = None
    try:
        ni_ttm = facts.get_ttm_net_income()
        if ni_ttm is not None and ni_ttm.value is not None:
            ni_val = float(ni_ttm.value)
            for pf in getattr(ni_ttm, "period_facts", []) or []:
                fd = getattr(pf, "filing_date", None)
                if fd is not None and (ni_filed is None or fd > ni_filed):
                    ni_filed = fd
    except Exception as e:  # noqa: BLE001
        logger.debug("get_ttm_net_income failed for %s: %s", ticker, e)
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
        v, pe, fd = _try_balance_tags(facts, tags)
        balance_values[key] = v
        snapshot_dates.append(fd)
        if pe is not None:
            period_dates.append(pe)

    # Latest values via normalized snake_case API (EPS, income statement
    # detail, cash flow detail). Returns None when the concept isn't tagged.
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

    # Derive EBITDA from operating_income + D&A (knowledge §11.2; SEC doesn't
    # tag EBITDA directly).
    op_income = normalized.get("operating_income")
    da = normalized.get("depreciation_and_amortization")
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
        gross_profit=normalized.get("gross_profit"),
        operating_income=op_income,
        cost_of_revenue=normalized.get("cost_of_revenue"),
        research_and_development=normalized.get("research_and_development"),
        sga_expense=normalized.get("sga_expense"),
        depreciation_and_amortization=da,
        interest_expense=normalized.get("interest_expense"),
        income_tax_expense=normalized.get("income_tax_expense"),
        income_before_tax=normalized.get("income_before_tax"),
        dividends_paid=normalized.get("dividends_paid"),
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
