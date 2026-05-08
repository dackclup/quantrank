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
from typing import Any

import pandas as pd
from edgar import Company, set_identity
from tenacity import retry, stop_after_attempt, wait_exponential

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
}

# Concepts queried via the normalized snake_case API for latest-annual values.
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

ALL_METRIC_KEYS: tuple[str, ...] = (
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
)


@dataclass
class FundamentalsSnapshot:
    """One row per ticker — a flat snapshot of latest values + latest filing_date."""

    ticker: str
    cik: str
    revenue: float | None
    net_income: float | None
    total_assets: float | None
    total_liabilities: float | None
    stockholders_equity: float | None
    cash: float | None
    operating_cash_flow: float | None
    capex: float | None
    free_cash_flow: float | None
    eps_basic: float | None
    eps_diluted: float | None
    shares_outstanding: float | None
    latest_filed_date: date | None
    latest_period_end: date | None

    def to_record(self) -> dict[str, Any]:
        return {**self.__dict__}

    def missing_fields(self) -> list[str]:
        return [k for k in ALL_METRIC_KEYS if getattr(self, k) is None]


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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
def _build_snapshot(ticker: str, cik: str) -> FundamentalsSnapshot:
    """Pull and assemble the snapshot from EDGAR. Caller wraps in retry-aware caching."""
    company = Company(cik or ticker)
    facts = company.get_facts()
    if facts is None:
        raise RuntimeError(f"No EntityFacts for {ticker}/{cik}")

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

    # Latest EPS via normalized API
    eps: dict[str, float | None] = {}
    for out_key, concept in _NORMALIZED_LATEST.items():
        try:
            md = facts.get_concept(concept, return_metadata=True)
        except Exception:  # noqa: BLE001
            md = None
        if md is None:
            eps[out_key] = None
            continue
        if isinstance(md, dict):
            eps[out_key] = (
                float(md["value"]) if md.get("value") is not None else None
            )
        else:
            eps[out_key] = float(md)

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
        eps_basic=eps.get("eps_basic"),
        eps_diluted=eps.get("eps_diluted"),
        shares_outstanding=balance_values.get("shares_outstanding"),
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
