"""Phase 3c weekly compute orchestrator.

Pipeline:
1. Universe (S&P 500 from Wikipedia, cached)
2. Prices (yfinance, parallel) + SPY benchmark for beta
3. Fundamentals snapshot (SEC EDGAR, parallel)
4. Annual fundamentals history (SEC EDGAR, parallel)
5. 8-pillar scoring via ``compute.scoring.pillars`` (Defense #6 sector
   exclusions applied at the pillar wrapper layer)
6. NaN pillar imputation (50.0 = neutral) per SKILL.md Rule 7
7. 10-pillar weighted composite (sentiment+ml redistributed pro-rata)
8. Risk overlay flags (annotate-only): altman_distress +
   sloan_accruals_top_decile + net_issuance_top_decile
9. **Cross-sectional inputs** for fair-price ensemble: universe_metrics
   (P/E, P/B, EV/EBITDA per ticker), peer groupings (sub_industry /
   sector / broad-ex-Fin-Util), historical_metrics (eps_3y_avg,
   avg_3y_roe, fcf_5y per ticker)
10. **Per-ticker fair-price ensemble**: 6 methods + Defenses #2/#3/#4
    (goodwill_heavy, stale-filing, outlier-5×). Merge ensemble's
    risk_flags into the per-ticker risk list.
11. Sort by composite, assign rank
12. Top-5 rotation: compare to previous rankings.json; flagged stocks
    (any of 4 active vetoes — altman / sloan / NSI / data-quality;
    non-reliance 8-K is deferred per issue #14) cannot earn
    ``entered_top5``
13. Atomic writes: rankings.json, metadata.json, stocks/{TICKER}.json,
    stocks/history/{TICKER}.json
14. Final RSS memory log (best-effort via psutil)
"""

from __future__ import annotations

import concurrent.futures as _cf
import logging
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from compute import config
from compute.ingest.cross_source import (
    BUCKET_KEYS as CROSS_SOURCE_BUCKET_KEYS,
)
from compute.ingest.cross_source import (
    bucket_delta as cross_source_bucket_delta,
)
from compute.ingest.cross_source import (
    country_for_exchange,
    exchange_name,
    fetch_yfinance_exchange,
)
from compute.ingest.cross_source import (
    validate_market_cap as cross_source_validate_market_cap,
)
from compute.ingest.fundamentals import (
    ALL_METRIC_KEYS,
    FundamentalsSnapshot,
    fetch_fundamentals,
    fetch_fundamentals_history,
)
from compute.ingest.fundamentals import (
    get_fallback_stats as get_shares_fallback_stats,
)
from compute.ingest.fundamentals import (
    get_filing_precheck_skip_count as get_fundamentals_filing_precheck_skip_count,
)
from compute.ingest.fundamentals import (
    reset_fallback_stats as reset_shares_fallback_stats,
)
from compute.ingest.fundamentals import (
    reset_filing_precheck_skip_count as reset_fundamentals_filing_precheck_skip_count,
)
from compute.ingest.prices import fetch_benchmarks, fetch_prices, fetch_spy_benchmark
from compute.ingest.universe import get_sp500_constituents, get_sp900_constituents
from compute.output.schemas import (
    DataQuality,
    Metadata,
    OsapGateDiagnostic,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)
from compute.output.writer import (
    prune_orphan_stock_files,
    read_previous_top5,
    write_benchmarks_json,
    write_metadata_json,
    write_rankings_json,
    write_stock_detail,
    write_stock_history,
)
from compute.scoring.beneish import BeneishResult, compute_beneish
from compute.scoring.composite import (
    build_sector_pillar_baselines,
    compute_composite,
    neutralize_pillar_scores,
)

# OSAP imports (compute.ingest.osap, compute.features.osap_replicate,
# compute.scoring.osap_blend, compute.validation.osap_validation) are
# deferred into the OSAP try-block in run_weekly_compute(). compute.ingest.osap
# does `import openassetpricing` at module load, which is only installed
# via the `.[factors]` optional extra; deferring keeps `tests/test_main.py`
# collection green in base-install environments (Phase 4a). The existing
# call-site try/except (graceful degradation per Rule 18) already catches
# ImportError as a subclass of Exception.
from compute.scoring.cost_of_equity import get_cost_of_equity
from compute.scoring.dechow_f import DechowResult, compute_dechow_f
from compute.scoring.earnings_quality import (
    check_accruals_momentum,
    check_loss_avoidance,
    check_loss_avoidance_size_invariant,
)
from compute.scoring.eight_k_events import get_non_reliance_filing_dates
from compute.scoring.form4_insider import (
    fetch_recent_form4,
    get_negation_downgrade_count,
    reset_negation_downgrade_count,
)
from compute.scoring.form4_signals import (
    count_10b5_1_filtered_transactions,
    detect_c_suite_unusual_sell,
    detect_insider_sell_cluster,
)
from compute.scoring.loss_chance import derive_loss_chance
from compute.scoring.manipulation_index import (
    compute_adjusted_composite,
    compute_manipulation_index,
    manipulation_components,
)
from compute.scoring.multi_class_shares import (
    detect_multi_class_aggregate_shares_suspected,
)
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.recommendation import derive_recommendation
from compute.scoring.rem import compute_rem_flags
from compute.scoring.restatement_filings import (
    check_late_filing,
    check_restatement_history,
    compute_high_confidence_restatement,
    get_amendment_filing_dates,
)
from compute.scoring.risk_overlay import (
    check_share_count_extraction_missing,
    compute_risk_flags,
)
from compute.scoring.sanity import compute_mos_trailing_ic
from compute.scoring.tier2 import (
    _EIGHT_K_DEFENSES_ENABLED,
    Tier2Result,
    fetch_tier2_for_ticker,
    tier2_events_dict,
)
from compute.scoring.tier2 import (
    coverage_pct as tier2_coverage_pct_calc,
)
from compute.valuation.applicability import check_rim_applicability, stale_filing_status
from compute.valuation.ensemble import (
    EnsembleResult,
    compute_fair_price_ensemble,
    ensemble_result_to_dict,
)
from compute.valuation.tangible_book import tangible_book_value_per_share

logger = logging.getLogger(__name__)


def _next_business_day_offset(now: datetime) -> int:
    """Calendar-day offset to the next Mon-Fri cron run.

    Cron schedule is `0 22 * * 1-5` (Mon-Fri 22:00 UTC) — so the next
    run is the next weekday on or after `now + 1 day`. Friday →
    Monday (3 days); Sat → Mon (2); Sun → Mon (1); Mon-Thu → next
    day (1).
    """
    # weekday: Mon=0, Tue=1, ..., Fri=4, Sat=5, Sun=6
    wd = now.weekday()
    if wd == 4:  # Friday → Monday
        return 3
    if wd == 5:  # Saturday → Monday
        return 2
    return 1


def _resolve_close_column(prices: pd.DataFrame) -> str | None:
    if "Adj Close" in prices.columns:
        return "Adj Close"
    if "Close" in prices.columns:
        return "Close"
    return None


def _fetch_prices_one(row: pd.Series) -> dict | None:
    """Fetch prices + extract last close for one ticker."""
    ticker = row["ticker"]
    prices = fetch_prices(ticker)
    if prices is None or prices.empty:
        return None
    col = _resolve_close_column(prices)
    if col is None:
        return None
    last = prices[col].dropna()
    if last.empty:
        return None
    current = float(last.iloc[-1])
    if math.isnan(current) or current <= 0:
        return None
    # PR 4f follow-up — 1-day percent change for the ranking-table
    # quote line. Computed here so the per-stock JSON has the value
    # ready (no frontend fetch of 502 history files).
    price_change_1d_pct: float | None = None
    if len(last) >= 2:
        prev = float(last.iloc[-2])
        if not math.isnan(prev) and prev > 0:
            price_change_1d_pct = (current - prev) / prev * 100.0
    return {
        "ticker": ticker,
        "name": row["name"],
        "sector": row["sector"],
        "industry": row.get("sub_industry"),
        "cik": row.get("cik"),
        # Phase 8 pilot PR 3a — carry cohort so index_membership propagates
        # into StockSummary / StockDetail without a second universe lookup.
        # "sp500" default keeps the sp500 path byte-identical.
        "cohort": row.get("cohort", "sp500"),
        "current_price": current,
        "price_change_1d_pct": price_change_1d_pct,
        "_prices": prices,
    }


# Per-stock fundamentals fetch ceiling. Belt-and-suspenders for the
# tightened tenacity retry (stop_after_delay(30) | stop_after_attempt(2))
# in compute/ingest/fundamentals.py. Defends the orchestrator against a
# truly stuck task (e.g., SEC's HTTP layer hanging mid-stream past the
# inner retry's wall-clock cap).
_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS = 45


def _fundamentals_one(
    ticker: str, cik: str
) -> tuple[FundamentalsSnapshot | None, float]:
    """Fetch the snapshot for one ticker, timed.

    Returns (snapshot, elapsed_seconds). ``snapshot`` is ``None`` on
    any failure (logged, not raised). The elapsed is captured even on
    failure so the latency histogram covers stuck/erroring tickers.
    """
    t0 = time.perf_counter()
    snap: FundamentalsSnapshot | None = None
    try:
        snap = fetch_fundamentals(ticker, cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals raised for %s/%s: %s", ticker, cik, e)
    elapsed = time.perf_counter() - t0
    logger.info(
        "fundamentals_fetch ticker=%s elapsed_seconds=%.2f status=%s",
        ticker,
        elapsed,
        "success" if snap is not None else "failure",
    )
    return snap, elapsed


def _history_one(ticker: str, cik: str) -> tuple[pd.DataFrame, float]:
    """Fetch annual history for one CIK, timed.

    Returns (history_df, elapsed_seconds). Empty DataFrame on missing
    CIK or any failure. Elapsed always captured.
    """
    t0 = time.perf_counter()
    if not cik:
        return pd.DataFrame(), 0.0
    df: pd.DataFrame = pd.DataFrame()
    try:
        df = fetch_fundamentals_history(cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals_history raised for cik=%s: %s", cik, e)
    elapsed = time.perf_counter() - t0
    logger.debug(
        "fundamentals_history_fetch ticker=%s elapsed_seconds=%.2f status=%s",
        ticker,
        elapsed,
        "success" if not df.empty else "empty",
    )
    return df, elapsed


def _latency_histogram(elapsed_values: list[float]) -> dict[str, int]:
    """Bucket fundamentals-fetch latencies for at-a-glance throttling diagnostics.

    Buckets: <5s, 5-15s, 15-30s, 30s+. The 15s and 30s thresholds align
    with the inner ``stop_after_delay(30)`` retry budget — anything in
    the 15-30s bucket is "retried once successfully", and 30s+ tickers
    are likely retry-exhausted or future-timed out. Phase 4 will use
    the slow-tickers list to special-case chronically-slow CIKs.
    """
    buckets = {"<5s": 0, "5-15s": 0, "15-30s": 0, "30s+": 0}
    for e in elapsed_values:
        if e < 5:
            buckets["<5s"] += 1
        elif e < 15:
            buckets["5-15s"] += 1
        elif e < 30:
            buckets["15-30s"] += 1
        else:
            buckets["30s+"] += 1
    return buckets


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile for a pre-sorted list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    idx = (len(sorted_values) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_raw_metrics(
    snapshot: FundamentalsSnapshot | None, current_price: float
) -> RawMetrics:
    if snapshot is None:
        return RawMetrics()
    market_cap = (
        current_price * snapshot.shares_outstanding
        if snapshot.shares_outstanding is not None
        else None
    )
    # PE shown in raw_metrics.pe_ratio_ttm — derive TTM EPS from
    # NI_TTM / shares_outstanding rather than snap.eps_diluted (single-
    # period). Audit #6 follow-up: this _build_raw_metrics helper was
    # missed in PR #49 — production median PE stayed at 77.5 (broken)
    # instead of dropping to ~26 (correct) until this fix lands.
    pe_ttm: float | None = None
    ttm_eps: float | None = None
    if (
        snapshot.net_income is not None
        and snapshot.shares_outstanding is not None
        and snapshot.shares_outstanding > 0
    ):
        ttm_eps = snapshot.net_income / snapshot.shares_outstanding
        # pe_ttm requires positive earnings (negative P/E is meaningless);
        # eps_basic / eps_diluted display fields keep the signed TTM value
        # so users see "−$0.42 EPS" on a loss-year stock.
        if (
            snapshot.net_income > 0
            and current_price > 0
            and ttm_eps > 0
        ):
            pe_ttm = current_price / ttm_eps
    # Issue #DD-eps mis-parse fix: snapshot.eps_diluted /
    # snapshot.eps_basic carry the XBRL single-period value
    # (`facts.get_concept` returns "latest single-period" per
    # `fundamentals.py:114-117`) — for a quarterly filer that's one
    # quarter's EPS, not TTM. Replace the display field with the
    # NI/shares-derived TTM value so the /stock/<TICKER> page shows a
    # number consistent with pe_ratio_ttm and the rest of the
    # valuation chain. Basic and diluted share the same denominator
    # here (shares_outstanding) — the basic-vs-diluted spread in XBRL
    # is typically < 1-3% on the S&P 500, well within display
    # precision.
    return RawMetrics(
        revenue=snapshot.revenue,
        net_income=snapshot.net_income,
        total_assets=snapshot.total_assets,
        total_liabilities=snapshot.total_liabilities,
        stockholders_equity=snapshot.stockholders_equity,
        cash=snapshot.cash,
        operating_cash_flow=snapshot.operating_cash_flow,
        capex=snapshot.capex,
        free_cash_flow=snapshot.free_cash_flow,
        eps_basic=ttm_eps,
        eps_diluted=ttm_eps,
        shares_outstanding=snapshot.shares_outstanding,
        # Issue #374 (RATIFY-B, 2026-06-11) — listed-class per-class share count;
        # None for non-MULTI_CLASS_OVERCOUNT tickers and on warm-cache crons.
        shares_outstanding_listed_class=snapshot.shares_outstanding_listed_class,
        market_cap=market_cap,
        pe_ratio_ttm=pe_ttm,
        goodwill=snapshot.goodwill,
    )


def _build_data_quality(
    snapshot: FundamentalsSnapshot | None,
    today: datetime,
    imputed_pillars: list[str],
) -> DataQuality:
    if snapshot is None:
        return DataQuality(
            missing_metrics=list(ALL_METRIC_KEYS),
            imputed_metrics=imputed_pillars,
        )
    filing_lag: int | None = None
    if snapshot.latest_filed_date is not None:
        filing_lag = (today.date() - snapshot.latest_filed_date).days
    return DataQuality(
        missing_metrics=snapshot.missing_fields(),
        imputed_metrics=imputed_pillars,
        filing_lag_days=filing_lag,
        latest_period_end=str(snapshot.latest_period_end)
        if snapshot.latest_period_end
        else None,
        latest_filed_date=str(snapshot.latest_filed_date)
        if snapshot.latest_filed_date
        else None,
    )


# --- Phase 3c cross-sectional builders for fair-price ensemble --------------

def _filing_lag(snap: FundamentalsSnapshot | None, asof: date) -> int | None:
    """Days between asof and the snapshot's latest filing date."""
    if snap is None or snap.latest_filed_date is None:
        return None
    return (asof - snap.latest_filed_date).days


def _build_universe_metrics(
    snapshots: dict[str, FundamentalsSnapshot | None],
    df: pd.DataFrame,
) -> dict[str, dict[str, float | None]]:
    """Per-ticker P/E, P/B (reported), EV/EBITDA TTM ratios for peer median.

    None values flow through; the peer-median walk filters them out.
    """
    out: dict[str, dict[str, float | None]] = {}
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        snap = snapshots.get(ticker)
        cp = float(r["current_price"])
        if snap is None:
            out[ticker] = {"pe_ttm": None, "pb_reported": None, "ev_ebitda_ttm": None}
            continue

        # PE shown in raw_metrics — derive TTM EPS from NI_TTM / shares
        # rather than snap.eps_diluted, which is single-period (audit #6).
        # Matches the same fix applied in compute/features/value.py::pe_ratio
        # and compute/valuation/ensemble.py multiples_pe_fair_price.
        pe_ttm: float | None = None
        if (
            snap.net_income is not None
            and snap.net_income > 0
            and snap.shares_outstanding is not None
            and snap.shares_outstanding > 0
            and cp > 0
        ):
            ttm_eps = snap.net_income / snap.shares_outstanding
            if ttm_eps > 0:
                pe_ttm = cp / ttm_eps

        pb_reported: float | None = None
        if (
            snap.stockholders_equity is not None
            and snap.stockholders_equity > 0
            and snap.shares_outstanding not in (None, 0)
        ):
            bvps = float(snap.stockholders_equity) / float(snap.shares_outstanding)
            if bvps > 0 and cp > 0:
                pb_reported = cp / bvps

        ev_ebitda_ttm: float | None = None
        if (
            snap.ebitda is not None
            and snap.ebitda > 0
            and snap.shares_outstanding not in (None, 0)
            and cp > 0
        ):
            mc = cp * float(snap.shares_outstanding)
            ltd = float(snap.long_term_debt or 0.0)
            std = float(snap.short_term_debt or 0.0)
            cash = float(snap.cash or 0.0)
            ev = mc + (ltd + std - cash)
            ev_ebitda_ttm = ev / float(snap.ebitda)

        out[ticker] = {
            "pe_ttm": pe_ttm,
            "pb_reported": pb_reported,
            "ev_ebitda_ttm": ev_ebitda_ttm,
        }
    return out


def _build_peer_groupings(
    df: pd.DataFrame,
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Build (sub_industry → tickers, sector → tickers, broad-ex-Fin-Util tickers).

    The Wikipedia universe loader populates only ``sector`` and
    ``sub_industry`` (level-1 + level-3 GICS); level-2 industry is not
    parsed. The "industry" tier in the ensemble peer-median walk
    therefore receives an empty list and falls through to sector. This
    is fine: with 502 S&P 500 stocks and 11 sectors the smallest sector
    (Energy n=21) comfortably exceeds the 8-peer floor, so the
    sub_industry → sector fallback is the only path that fires in
    practice.
    """
    by_sub_industry: dict[str, list[str]] = {}
    by_sector: dict[str, list[str]] = {}
    broad_ex_fin_util: list[str] = []
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        sector = str(r["sector"])
        sub_industry_raw = r.get("industry")
        sub_industry = (
            str(sub_industry_raw)
            if sub_industry_raw is not None and pd.notna(sub_industry_raw)
            else None
        )
        if sub_industry is not None:
            by_sub_industry.setdefault(sub_industry, []).append(ticker)
        by_sector.setdefault(sector, []).append(ticker)
        if sector not in ("Financials", "Utilities"):
            broad_ex_fin_util.append(ticker)
    return by_sub_industry, by_sector, broad_ex_fin_util


def _build_historical_metrics(
    histories: dict[str, pd.DataFrame],
    snapshots: dict[str, FundamentalsSnapshot | None],
) -> dict[str, dict[str, float | list[float] | None]]:
    """Per-ticker historical metrics: eps_3y_avg, avg_3y_roe, fcf_5y."""
    out: dict[str, dict[str, float | list[float] | None]] = {}
    for ticker, hist in histories.items():
        out[ticker] = {
            "eps_3y_avg": _eps_3y_avg(hist),
            "avg_3y_roe": _avg_3y_roe(hist, snapshots.get(ticker)),
            "fcf_5y": _fcf_5y(hist),
        }
    return out


def _eps_3y_avg(hist: pd.DataFrame | None) -> float | None:
    if hist is None or len(hist) == 0 or "metric" not in hist.columns:
        return None
    rows = hist[hist["metric"] == "eps_diluted"].sort_values(
        "fiscal_year", ascending=False
    )
    if len(rows) < 3:
        return None
    values = rows["value"].head(3).astype(float).tolist()
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in values):
        return None
    return float(sum(values) / 3.0)


def _avg_3y_roe(
    hist: pd.DataFrame | None, snap: FundamentalsSnapshot | None
) -> float | None:
    """Avg 3y ROE = mean over last 3 years of (NI_t / Equity_t).

    Per-year denominator required. Issue #11 history:

    - PR 4c added the per-year ``stockholders_equity`` history collection
      + the per-year ROE path. A fallback to single-period equity
      (current-snapshot equity for all 3 years' NI) was retained to
      keep RIM applicable for tickers with incomplete history.
    - The fallback is the very bug PR 4c was meant to fix: for a firm
      whose equity grew 30% over 3 years, single-period-equity-as-
      denominator biases ROE **downward** by ~15% → spurious
      ``value_trap_risk`` flag. As long as the fallback fires, the
      universe-level over-firing persists.
    - This PR removes the fallback. When per-year equity history is
      incomplete, return ``None`` and let ``check_rim_applicability``
      skip RIM under the distinct ``insufficient_history_for_roe``
      reason (which does NOT trigger the ``value_trap_risk`` warning
      at the ensemble layer).

    Side-effect: tickers with < 3y of stockholders_equity history
    (recent IPOs, off-cycle filers, audit #6 residual gaps) lose RIM
    as an applicable method. The 5 remaining methods still produce a
    fair-price estimate.
    """
    if hist is None or len(hist) == 0 or "metric" not in hist.columns:
        return None
    if snap is None or snap.stockholders_equity in (None, 0):
        return None
    if float(snap.stockholders_equity) <= 0:
        return None

    ni_rows = hist[hist["metric"] == "net_income"].sort_values(
        "fiscal_year", ascending=False
    )
    if len(ni_rows) < 3:
        return None
    ni_top3 = ni_rows.head(3)
    ni_values = ni_top3["value"].astype(float).tolist()
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in ni_values):
        return None

    eq_rows = hist[hist["metric"] == "stockholders_equity"].sort_values(
        "fiscal_year", ascending=False
    )
    if eq_rows.empty:
        return None
    # Match equity to net_income by fiscal_year (handles 10-K/calendar
    # mismatches where one history has an extra year vs the other).
    eq_by_year = eq_rows.set_index("fiscal_year")["value"]
    per_year_roe: list[float] = []
    for _, ni_row in ni_top3.iterrows():
        fy = ni_row["fiscal_year"]
        eq = eq_by_year.get(fy)
        try:
            eq_f = float(eq) if eq is not None else None
        except (TypeError, ValueError):
            eq_f = None
        if eq_f is None or math.isnan(eq_f) or eq_f <= 0:
            return None
        per_year_roe.append(float(ni_row["value"]) / eq_f)
    return float(sum(per_year_roe) / 3.0)


def _fcf_5y(hist: pd.DataFrame | None) -> list[float | None]:
    """Last 5 years of FCF = OCF − |capex|, in chronological order.

    Returns an empty list if the annual history doesn't have either
    column populated; returns up to 5 values when they overlap.
    """
    if hist is None or len(hist) == 0 or "metric" not in hist.columns:
        return []
    ocf = hist[hist["metric"] == "operating_cash_flow"].set_index("fiscal_year")["value"]
    capex = hist[hist["metric"] == "capex"].set_index("fiscal_year")["value"]
    if ocf.empty or capex.empty:
        return []
    common_fy = sorted(set(ocf.index) & set(capex.index), reverse=True)[:5]
    if not common_fy:
        return []
    out: list[float | None] = []
    for fy in sorted(common_fy):  # chronological order (oldest → newest)
        try:
            o = float(ocf[fy])
            c = float(capex[fy])
            if math.isnan(o) or math.isnan(c):
                out.append(None)
            else:
                out.append(o - abs(c))
        except (KeyError, TypeError, ValueError):
            out.append(None)
    return out


def _pillar_scores_to_schema(row: pd.Series) -> PillarScores:
    """Convert a one-ticker pillar score row into a PillarScores model.

    Rounds to 2 decimals; null pillars (sentiment, ml) stay None.
    """
    def r(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return round(float(v), 2)

    return PillarScores(
        quality=r(row.get("quality")),
        value=r(row.get("value")),
        growth=r(row.get("growth")),
        momentum=r(row.get("momentum")),
        health=r(row.get("health")),
        profitability=r(row.get("profitability")),
        technical=r(row.get("technical")),
        risk=r(row.get("risk")),
        sentiment=None,
        ml=None,
    )


def _coverage_pct(by_ticker: dict[str, str | None]) -> float | None:
    """PR-A2 — % of the iterated universe with a non-null value (display-only).

    Rule-18 observability formula for the listing-metadata fields. Shared by
    BOTH ``exchange_coverage_pct`` and ``country_coverage_pct`` (0.10.13-phase4.6)
    — the two are NOT redundant: ``exchange`` passes an unknown code through
    verbatim (counts as covered), while ``country`` resolves only known US codes
    (an unknown code → None → uncovered), so the two diverge exactly on a raw
    passthrough code. ``country_coverage_pct`` is therefore the strict canary
    ``exchange_coverage_pct`` structurally cannot be (the CBOE/``BTS`` case,
    2026-06-02 audit). ``None`` only on an empty universe (avoids
    ZeroDivisionError); otherwise a 0-100 float (0.0 is a real "nothing
    resolved" signal — e.g. a cold simulate cache under ``QR_SKIP_CROSS_SOURCE``).
    Pure helper so the tests import the production formula instead of copying it
    (CLAUDE.md §Gotchas PR #310 — no verbatim-copy test helpers).
    """
    if not by_ticker:
        return None
    n_resolved = sum(1 for v in by_ticker.values() if v is not None)
    return round(100.0 * n_resolved / len(by_ticker), 2)


def _acquire_alpha158_inputs(asof_date: date, tickers: list[str]) -> tuple:
    """Acquire the three Alpha158 adapter inputs — DEFERRED (Phase 4j.1).

    The live Alpha158 feature panel requires a populated Qlib ``.bin``
    cache, and the yfinance→Qlib BYO ``dump_bin`` adapter is a separate
    infra lift (deferred per the scout — see
    ``compute/ingest/qlib_features.py``). Phase 4j.1 ships the diagnostic
    ``Metadata.alpha158_*`` surface + the adapter
    (``compute/features/alpha158_replicate.py``) + the gate WIRING ahead
    of the live data (SKILL.md Rule 18 observability-before-wiring);
    methodology-scientist pre-ratified ``used=0`` / all-``None`` on the
    early crons as the honest, conservative outcome (insufficient
    history). This raises until the bin cache lands; the Step 7.6
    try/except degrades every ``alpha158_*`` field to ``None``.

    The follow-on (the bin-cache PR) implements the body to return:
        - feature_panel: ``(date, ticker)``-MultiIndexed Alpha158 feature
          values (``qlib_features.fetch_alpha158_features`` over the
          populated bin cache).
        - period_returns: ``(date, ticker)`` trailing per-period returns
          built from the existing price cache.
        - universe_provider: ``as_of -> (members, is_complete)`` wired to
          ``compute.ingest.historical_universe.members_at`` so the
          monthly ranking universe is point-in-time + survivorship-honest.
    """
    raise RuntimeError(
        "Alpha158 feature panel unavailable: the yfinance→Qlib .bin BYO "
        "dump_bin adapter is deferred (Phase 4j.1 observability scope). "
        "The diagnostic surface + adapter + gate wiring shipped; live "
        f"feature data lands when the bin cache is wired (asof="
        f"{asof_date.isoformat()}, universe={len(tickers)})."
    )


def _run_midcap_coverage_probe(
    sp900_df: pd.DataFrame,
) -> tuple[float | None, float | None, float | None, dict[str, int]]:
    """Diagnostic-only coverage probe over the S&P 400 mid-cap cohort.

    Phase 8 pilot PR 1 (Rule 18 observability-before-wiring). This probe:
      - iterates only over the ``sp400`` rows of ``sp900_df``
      - calls ``fetch_fundamentals`` on each ticker (reusing the production
        tenacity / cache layer — no new retry policy needed)
      - counts non-null snapshots (= GAAP coverage) vs nulls
      - does NOT feed ``summaries``, the writer, or any scoring path
      - returns (coverage_pct, null_rate_pct, cik_resolution_pct, cohort_sizes)

    The ranked output (rankings.json + stocks/*.json) is BYTE-IDENTICAL
    whether or not this probe ran. The probe runs in the main thread
    (sequential) to avoid blowing through the EDGAR 10 req/s ceiling on
    top of the 500 fundamentals fetch that already ran.

    Returns (None, None, None, {}) on any unexpected failure so the outer
    Metadata population still proceeds cleanly.
    """
    try:
        cohort_sizes: dict[str, int] = {}
        for cohort_label in ("sp500", "sp400"):
            mask = sp900_df["cohort"] == cohort_label
            cohort_sizes[cohort_label] = int(mask.sum())

        midcap_mask = sp900_df["cohort"] == "sp400"
        midcap_df = sp900_df[midcap_mask].reset_index(drop=True)
        total_midcap = len(midcap_df)

        if total_midcap == 0:
            logger.warning("[sp900-probe] No sp400 tickers found in sp900 DataFrame — probe skipped")
            return None, None, None, cohort_sizes

        logger.info(
            "[sp900-probe] Starting midcap coverage probe: %d sp400 tickers (sequential, cache-safe)",
            total_midcap,
        )

        # CIK resolution bookkeeping
        cik_resolved = 0
        for _, row in midcap_df.iterrows():
            if row.get("cik") and str(row["cik"]).strip() not in ("", "None", "nan"):
                cik_resolved += 1
        cik_resolution_pct = round(100.0 * cik_resolved / total_midcap, 2)
        logger.info(
            "[sp900-probe] CIK resolution: %d / %d (%.1f%%)",
            cik_resolved,
            total_midcap,
            cik_resolution_pct,
        )

        n_ok = 0
        n_null = 0
        for _, row in midcap_df.iterrows():
            ticker = str(row["ticker"])
            cik_raw = row.get("cik")
            cik = str(cik_raw).strip() if cik_raw and str(cik_raw).strip() not in ("", "None", "nan") else ""
            try:
                snap = fetch_fundamentals(ticker, cik)
                if snap is not None:
                    n_ok += 1
                else:
                    n_null += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("[sp900-probe] fetch_fundamentals failed for %s: %s", ticker, exc)
                n_null += 1

        coverage_pct = round(100.0 * n_ok / total_midcap, 2)
        null_rate_pct = round(100.0 * n_null / total_midcap, 2)
        logger.info(
            "[sp900-probe] Midcap GAAP coverage: %d / %d = %.1f%% (null: %d = %.1f%%)",
            n_ok,
            total_midcap,
            coverage_pct,
            n_null,
            null_rate_pct,
        )
        return coverage_pct, null_rate_pct, cik_resolution_pct, cohort_sizes

    except Exception as exc:  # noqa: BLE001
        logger.error("[sp900-probe] Diagnostic probe failed unexpectedly: %s", exc)
        return None, None, None, {}


def run_weekly_compute() -> int:
    """Run the full weekly compute. Returns the count of successfully scored tickers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # PR-3d quick wins: probe SEC EDGAR health BEFORE doing any other
    # work. If SEC is degraded, abort the workflow in <1 minute rather
    # than burn the full 90-min ceiling for ~0% coverage. The probe is
    # a single cheap GET (~400 KB submissions endpoint). When healthy,
    # adds ~1-2s; the operator can set QR_SKIP_SEC_HEALTH=1 to bypass.
    # Raises RuntimeError on degraded SEC; we catch + exit non-zero so
    # the GitHub Actions workflow surfaces a clear failure state.
    from compute.ingest.sec_health import assert_sec_api_usable
    try:
        assert_sec_api_usable()
    except RuntimeError:
        # Already logged at error level by the helper; bail immediately.
        return 0

    # Phase 8 pilot PR 3a — universe selector seam (wires scored output).
    # QR_UNIVERSE=sp500 (default): loads SP500 only; adds cohort="sp500" so
    #   the column exists unconditionally for index_membership propagation.
    # QR_UNIVERSE=sp900: loads the full SP900 frame (cohort column already
    #   present from get_sp900_constituents); all ~903 tickers are ranked.
    #   The diagnostic probe reuses this frame — no second fetch.
    #
    # CRON DEFAULT: QR_UNIVERSE is "sp500" (compute-rankings.yml unchanged).
    # The sp900 path is active only via manual `workflow_dispatch universe: sp900`.
    logger.info("Loading universe… (QR_UNIVERSE=%s)", config.QR_UNIVERSE)
    _pilot_cohort_sizes: dict[str, int] | None = None
    _pilot_midcap_coverage_pct: float | None = None
    _pilot_midcap_null_rate_pct: float | None = None
    _pilot_midcap_cik_resolution_pct: float | None = None
    if config.QR_UNIVERSE == "sp900":
        logger.info("[sp900] Loading SP900 universe (sp500 + sp400 de-duped)…")
        universe = get_sp900_constituents()
        logger.info("[sp900] Universe size: %d (sp500+sp400 combined)", len(universe))
        # Diagnostic probe reuses the already-loaded frame — no second fetch.
        logger.info("[sp900-probe] Running midcap diagnostic probe (Rule 18)…")
        try:
            (
                _pilot_midcap_coverage_pct,
                _pilot_midcap_null_rate_pct,
                _pilot_midcap_cik_resolution_pct,
                _pilot_cohort_sizes,
            ) = _run_midcap_coverage_probe(universe)
            logger.info(
                "[sp900-probe] Complete: cohorts=%s coverage=%.1f%% null_rate=%.1f%% cik_resolution=%.1f%%",
                _pilot_cohort_sizes,
                _pilot_midcap_coverage_pct or 0.0,
                _pilot_midcap_null_rate_pct or 0.0,
                _pilot_midcap_cik_resolution_pct or 0.0,
            )
        except Exception as _sp900_exc:  # noqa: BLE001
            logger.error("[sp900-probe] Outer probe block failed (non-fatal): %s", _sp900_exc)
    else:
        # Default sp500 path — byte-identical scoring to pre-PR-3a.
        # Add cohort column so _fetch_prices_one.row.get("cohort") is always defined.
        universe = get_sp500_constituents()
        universe = universe.copy()
        universe["cohort"] = "sp500"
        logger.info("Universe size: %d", len(universe))

    logger.info("Fetching SPY benchmark for beta…")
    benchmark = fetch_spy_benchmark()
    if benchmark is None or benchmark.empty:
        logger.warning("SPY benchmark unavailable — beta will be NaN for all tickers")
        benchmark = None

    # Phase 7.0 PR-1 — export the benchmark index series (SPY/QQQ/DIA/IWM) for
    # the portfolio-backtest comparison chart. Observability-before-wiring:
    # benchmarks.json + benchmark_coverage_pct ship now; the home page reads the
    # file in PR-4. SPY is already warm in the price cache from the beta fetch.
    benchmark_coverage_pct: float | None = None
    try:
        _bench_path, benchmark_coverage_pct = write_benchmarks_json(
            fetch_benchmarks(), config.DATA_DIR
        )
        logger.info(
            "Benchmark export: %s (coverage %.1f%%)",
            _bench_path if _bench_path is not None else "NONE",
            benchmark_coverage_pct,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Benchmark export failed (non-fatal): %s", e)

    # Step 1 — prices in parallel.
    rows: list[dict] = []
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=config.MAX_PARALLEL_FETCHES) as ex:
        futures = {
            ex.submit(_fetch_prices_one, row): row["ticker"]
            for _, row in universe.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.warning("Price fetch failed for %s: %s", ticker, e)
                continue
            if result is not None:
                prices_by_ticker[ticker] = result.pop("_prices")
                rows.append(result)

    logger.info("Fetched prices for %d / %d tickers", len(rows), len(universe))
    if len(rows) < config.MIN_VALID_TICKERS:
        logger.error(
            "Only %d tickers priced — below minimum of %d. Aborting without writing JSON "
            "to preserve last-good data.",
            len(rows),
            config.MIN_VALID_TICKERS,
        )
        return 0

    df = pd.DataFrame(rows)
    df = df.set_index("ticker", drop=False)

    # Step 2 — fundamentals snapshot in parallel.
    logger.info(
        "Fetching fundamentals for %d tickers (max_workers=%d)…",
        len(df),
        config.EDGAR_MAX_WORKERS,
    )
    snapshots: dict[str, FundamentalsSnapshot | None] = {}
    fundamentals_latency: dict[str, float] = {}
    # Issue #246 PR2a (0.10.3-phase4.5e) — reset Rule 18 shares-fallback
    # counters before the fetch loop so this run's counts start at 0.
    # Read back via ``get_shares_fallback_stats()`` after the loop.
    reset_shares_fallback_stats()
    # Issue #471 — reset the filing-precheck skip counter (Design B, filing-date gate).
    # Read back via ``get_fundamentals_filing_precheck_skip_count()`` after the histogram log.
    reset_fundamentals_filing_precheck_skip_count()
    with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as ex:
        futures = {
            ex.submit(_fundamentals_one, r["ticker"], str(r.get("cik") or "")): r["ticker"]
            for _, r in df.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                snap, elapsed = fut.result(timeout=_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS)
            except _cf.TimeoutError:
                logger.warning(
                    "Fundamentals task timed out (>%ds) for %s — skipping ticker.",
                    _FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS,
                    ticker,
                )
                snap = None
                elapsed = float(_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS)
            except Exception as e:  # noqa: BLE001
                logger.warning("Fundamentals task raised for %s: %s", ticker, e)
                snap = None
                elapsed = 0.0
            snapshots[ticker] = snap
            fundamentals_latency[ticker] = elapsed

    coverage = sum(1 for v in snapshots.values() if v is not None) / max(len(df), 1)
    logger.info(
        "Fundamentals coverage: %d / %d (%.1f%%)",
        sum(1 for v in snapshots.values() if v is not None),
        len(df),
        coverage * 100,
    )

    # PR 3d Part 2 — observability. Per-stock latency histogram surfaces
    # SEC-API throttling at-a-glance. p50 / p95 plus the histogram are
    # mirrored into ``Metadata`` so the JSON output captures the run's
    # cost profile (Phase 4 will mine slow tickers for special-case caching).
    elapsed_values = sorted(fundamentals_latency.values())
    latency_buckets = _latency_histogram(elapsed_values)
    slow_tickers = sorted(
        ((t, e) for t, e in fundamentals_latency.items() if e >= 15.0),
        key=lambda p: -p[1],
    )[:20]
    fundamentals_p50 = _percentile(elapsed_values, 0.50)
    fundamentals_p95 = _percentile(elapsed_values, 0.95)
    fundamentals_coverage_pct = round(100 * coverage, 2)
    logger.info("fundamentals_latency_histogram: %s", latency_buckets)
    logger.info(
        "fundamentals_latency_p50=%.2fs p95=%.2fs coverage=%.2f%%",
        fundamentals_p50 if fundamentals_p50 is not None else 0.0,
        fundamentals_p95 if fundamentals_p95 is not None else 0.0,
        fundamentals_coverage_pct,
    )
    if slow_tickers:
        logger.info(
            "fundamentals_slow_tickers (>=15s, top 20): %s",
            [(t, round(e, 2)) for t, e in slow_tickers],
        )
    # Issue #471 — Design B filing-precheck diagnostic.  Tickers served from the
    # filing-precheck middle path instead of a live _build_snapshot are excluded from
    # the elapsed_values above (their fetch returns immediately via the precheck),
    # so the histogram above already reflects the reduced tail.  This line surfaces
    # the aggregate skip count alongside it for at-a-glance confirmation of the fix.
    filing_precheck_skip_count = get_fundamentals_filing_precheck_skip_count()
    logger.info(
        "fundamentals_filing_precheck_skip_count=%d "
        "(tickers served from filing-precheck cache, no new SEC filing, "
        "skipping companyfacts pull; #471)",
        filing_precheck_skip_count,
    )
    if coverage < config.MIN_FUNDAMENTALS_COVERAGE:
        logger.error(
            "Fundamentals coverage %.1f%% below threshold %.1f%%. Aborting.",
            coverage * 100,
            config.MIN_FUNDAMENTALS_COVERAGE * 100,
        )
        return 0

    # Step 3 — annual history in parallel (feeds growth CAGRs).
    logger.info("Fetching annual fundamentals history…")
    histories: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as ex:
        futures = {
            ex.submit(
                _history_one, r["ticker"], str(r.get("cik") or "")
            ): r["ticker"]
            for _, r in df.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                hist_df, _hist_elapsed = fut.result(
                    timeout=_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS
                )
                histories[ticker] = hist_df
            except _cf.TimeoutError:
                logger.warning(
                    "History task timed out (>%ds) for %s — skipping ticker.",
                    _FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS,
                    ticker,
                )
                histories[ticker] = pd.DataFrame()
            except Exception as e:  # noqa: BLE001
                logger.warning("History task raised for %s: %s", ticker, e)
                histories[ticker] = pd.DataFrame()

    # Phase 4.5e PR 2 — Form-4 insider-transaction fetch loop.
    # Observability only in this PR: form4_enabled=False means the scoring
    # layer (PR 3) is not yet wired. The loop populates form4_diagnostics
    # per-ticker so PR 2's Metadata surface has real latency + coverage
    # numbers after ≥ 1 cron run. Wrapped in outer try/except so any
    # catastrophic failure resets to empty state and the cron continues.
    #
    # 2026-05-22 hotfix #2: parallelized via ThreadPoolExecutor matching
    # the sibling EDGAR loops at lines 695 (fundamentals) and 763 (tier2/
    # 8-K). The original sequential ``for`` loop combined with the
    # property→method parser fix (also this PR) blew the 45-min CI cap
    # twice in a row — pre-merge-prod-sim canceled at 43m44s on commit
    # 3f3bc292 (365d) and again at 45m on e2c6740b (180d sequential).
    # 502 tickers × ~7s/ticker sequential = ~60 min; with 8 workers it
    # drops to ~7-8 min while staying under the EDGAR 10 req/s ceiling
    # (each worker issues ~1 req/s sustained — matching the empirically
    # safe pattern from PR-3d's bump from 5 → 8 workers).
    form4_diagnostics: dict[str, dict] = {}
    form4_latencies: list[float] = []
    form4_failures: list[str] = []
    # Issue #287 PR A — wall-clock for the Form-4 loop. `None` semantics:
    # never assigned when FORM4_FETCH_SKIP=1 (loop didn't run) OR when the
    # outer try/except fired before the end marker. Populated to the
    # rounded float seconds on the happy path.
    form4_wall_clock_seconds: float | None = None
    _form4_wc_start: float | None = None
    # PR 6 (residual footgun #1 from PR 4-eq) — count of True → False
    # downgrades applied by the post-detector negation guard during cache
    # build (e.g. "10b5-1 plan terminated 2022" + "no 10b5-1 plan in
    # effect"). `None` semantics mirrors form4_wall_clock_seconds: None
    # when FORM4_FETCH_SKIP=1 OR when the outer try/except fired. On the
    # happy path the value is the integer count of downgrades across the
    # universe-wide cache-build. Warm-cache runs report 0 (no detector
    # ran this cron — cached `is_rule_10b5_one` is read as-is); cold-
    # cache runs populate the real cohort number for Q3 cohort audit.
    form4_negation_guard_downgrade_count: int | None = None

    # 2026-05-22 hotfix #3: env-var escape hatch for cold-cache CI
    # contexts (pre-merge-prod-sim). The Form-4 fetch is observability
    # only (form4_enabled=False; _FORM4_FLAGS_ENABLED=False) — it has
    # ZERO scoring impact, so the pre-merge-prod-sim's composite-diff
    # check does NOT need it. The 45-min CI cap on that workflow blew
    # 3x because the property→method parser fix made each filing.obj()
    # do its real HTTP round-trip on a never-populated form4 cache.
    # Weekly cron (compute-rankings.yml, default 360min budget) still
    # runs the full fetch + populates the cache for future sims.
    if os.environ.get("FORM4_FETCH_SKIP", "").lower() in ("1", "true", "yes"):
        logger.info(
            "Phase 4.5e PR 2 — Form-4 fetch SKIPPED via FORM4_FETCH_SKIP "
            "env var. All form4_* Metadata fields will be None / empty "
            "(observability-only signal; zero scoring impact). The "
            "weekly cron populates these fields at default budget."
        )
        # form4_diagnostics / form4_latencies / form4_failures remain
        # empty; the Metadata constructor's `if form4_diagnostics`
        # guards (lines 2092-2118) coerce each form4_* field to None.

    else:

        def _fetch_one_form4(ticker: str) -> tuple[dict, float, bool]:
            """Per-ticker Form-4 fetch worker. Returns (diagnostic_dict,
            elapsed_seconds, is_failure). Catches every exception inline so
            the ThreadPoolExecutor never sees a raised future — keeps the
            outer loop's failure semantics intact."""
            t0 = time.perf_counter()
            try:
                transactions = fetch_recent_form4(ticker)
                elapsed = time.perf_counter() - t0
                if transactions is None:
                    return (
                        {
                            "insider_count": 0,
                            "latest_filing_date": None,
                            "fetch_status": "failed",
                        },
                        elapsed,
                        True,
                    )
                distinct = len({t["insider_cik"] for t in transactions})
                latest = transactions[0]["filing_date"] if transactions else None
                return (
                    {
                        "insider_count": distinct,
                        "latest_filing_date": latest,
                        "fetch_status": "ok",
                    },
                    elapsed,
                    False,
                )
            except Exception as _f4_e:  # noqa: BLE001
                elapsed = time.perf_counter() - t0
                logger.warning("form4 fetch failed for %s: %s", ticker, _f4_e)
                return (
                    {
                        "insider_count": 0,
                        "latest_filing_date": None,
                        "fetch_status": "failed",
                    },
                    elapsed,
                    True,
                )

        try:
            _f4_tickers = [str(_f4_r["ticker"]) for _, _f4_r in df.iterrows()]
            logger.info(
                "Phase 4.5e PR 2 — fetching Form-4 insider data for %d tickers "
                "with %d workers …",
                len(_f4_tickers),
                config.EDGAR_MAX_WORKERS,
            )
            # Issue #287 PR A — wall-clock start marker (inside else+try so
            # FORM4_FETCH_SKIP=1 leaves form4_wall_clock_seconds=None).
            _form4_wc_start = time.monotonic()
            # PR 6 — reset the module-level negation-guard counter before
            # the fetch loop begins. Counter accumulates True → False
            # downgrades across all worker threads (thread-safe via
            # ``_negation_lock`` inside form4_insider). Read after the
            # ThreadPoolExecutor block completes and aliased to
            # ``form4_negation_guard_downgrade_count`` for Metadata.
            reset_negation_downgrade_count()
            with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as _f4_ex:
                _f4_future_to_ticker = {
                    _f4_ex.submit(_fetch_one_form4, _t): _t for _t in _f4_tickers
                }
                for _f4_future in as_completed(_f4_future_to_ticker):
                    _f4_ticker = _f4_future_to_ticker[_f4_future]
                    try:
                        _f4_diag, _f4_elapsed, _f4_is_failure = _f4_future.result()
                        form4_diagnostics[_f4_ticker] = _f4_diag
                        form4_latencies.append(_f4_elapsed)
                        if _f4_is_failure:
                            form4_failures.append(_f4_ticker)
                    except Exception as _f4_e:  # noqa: BLE001
                        form4_failures.append(_f4_ticker)
                        form4_diagnostics[_f4_ticker] = {
                            "insider_count": 0,
                            "latest_filing_date": None,
                            "fetch_status": "failed",
                        }
                        logger.warning(
                            "form4 future raised for %s: %s", _f4_ticker, _f4_e
                        )
            # Issue #287 PR A — wall-clock end marker (success path).
            form4_wall_clock_seconds = round(
                time.monotonic() - _form4_wc_start, 1
            )
            # PR 6 — read the negation-guard counter accumulated across
            # all worker threads. Always populated on the happy path
            # (zero is a valid value — warm-cache cron OR cold-cache cron
            # with no negation-phrase footnotes in the universe).
            form4_negation_guard_downgrade_count = get_negation_downgrade_count()
            logger.info(
                "Form-4 fetch complete: %d ok, %d failures, p50=%.2fs p95=%.2fs, "
                "wall_clock=%ss, negation_downgrades=%d",
                len(form4_diagnostics) - len(form4_failures),
                len(form4_failures),
                float(np.median(form4_latencies)) if form4_latencies else 0.0,
                float(np.percentile(form4_latencies, 95)) if form4_latencies else 0.0,
                form4_wall_clock_seconds,
                form4_negation_guard_downgrade_count,
            )
        except Exception as _f4_outer_e:  # noqa: BLE001
            logger.warning(
                "Form-4 fetch loop failed entirely (%s); form4_diagnostics → empty.",
                _f4_outer_e,
            )
            form4_diagnostics = {}
            form4_latencies = []
            form4_failures = []
            # Issue #287 PR A — leave form4_wall_clock_seconds = None on failure.
            form4_wall_clock_seconds = None
            # PR 6 — leave negation-guard count = None on outer-try failure
            # (mirrors form4_wall_clock_seconds semantics).
            form4_negation_guard_downgrade_count = None

    # Step 4 — assemble TickerInputs and compute all pillars.
    inputs: dict[str, TickerInputs] = {}
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        inputs[ticker] = TickerInputs(
            snapshot=snapshots.get(ticker),
            prices=prices_by_ticker.get(ticker),
            benchmark_prices=benchmark,
            current_price=float(r["current_price"]),
            sector=str(r["sector"]),
            history=histories.get(ticker),
        )

    logger.info("Computing pillar scores for %d tickers…", len(inputs))
    pillar_df = compute_all_pillars(inputs)
    pillar_df, imputed_by_ticker = neutralize_pillar_scores(pillar_df)

    # Step 4b — Tier-2 event defenses (PR 3d). Fetched in parallel ahead of
    # risk-flag computation so the resulting non_reliance veto can be
    # injected into compute_risk_flags (avoiding a duplicate EDGAR fetch
    # inside the risk-overlay layer). See compute/scoring/tier2.py.
    #
    # fetch_tier2_for_ticker catches every per-defense exception
    # internally, so a failed fetch surfaces as a Tier2Result with
    # fetch_succeeded=False (not an exception). The defensive try/except
    # below covers only the unexpected case (e.g., interpreter-level
    # bug); a missing-ticker entry in tier2_results just means no veto
    # and an empty tier2_events display dict for that ticker.
    logger.info("Fetching Tier-2 event defenses (10-K + 8-K) for %d tickers…", len(df))
    tier2_results: dict[str, Tier2Result] = {}
    # Issue #287 PR A — wall-clock start marker.
    _tier2_wc_start = time.monotonic()
    tier2_wall_clock_seconds: float | None = None
    try:
        with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as ex:
            futures = {
                ex.submit(fetch_tier2_for_ticker, r["ticker"]): r["ticker"]
                for _, r in df.iterrows()
            }
            for fut in as_completed(futures):
                ticker = futures[fut]
                try:
                    tier2_results[ticker] = fut.result()
                except Exception as e:  # noqa: BLE001
                    logger.warning("Tier-2 task raised for %s: %s", ticker, e)
                    # Skip this ticker — downstream uses .get() with safe defaults.
        tier2_wall_clock_seconds = round(time.monotonic() - _tier2_wc_start, 1)
    except Exception as _t2_outer_e:  # noqa: BLE001
        # Defensive: an interpreter-level failure before the end marker
        # keeps `tier2_wall_clock_seconds = None` (skipped semantic).
        logger.warning("Tier-2 loop failed entirely: %s", _t2_outer_e)
    tier2_coverage = tier2_coverage_pct_calc(tier2_results)
    logger.info(
        "Tier-2 coverage: %s%% (gc=%d, nr=%d, ac=%d, wall_clock=%ss)",
        tier2_coverage if tier2_coverage is not None else "n/a",
        sum(1 for r in tier2_results.values() if r.going_concern_disclosure),
        sum(1 for r in tier2_results.values() if r.non_reliance_flag.fired),
        sum(1 for r in tier2_results.values() if r.auditor_change_flag.fired),
        tier2_wall_clock_seconds if tier2_wall_clock_seconds is not None else "n/a",
    )

    # Step 5 — composite + risk flags. NSI flag (Defense Playbook §PR 3c §1)
    # requires per-ticker history + sector to compute within-sector top-decile
    # threshold, so we pass both into compute_risk_flags. Top-5 rotation below
    # already iterates risk_flags.get(ticker) → no change needed there for NSI
    # to enter the existing flagged-skip path (annotate-and-veto-Top-N pattern,
    # SKILL.md Rule 16).
    #
    # PR 3d Defense #9: ``non_reliance_by_ticker`` injects the pre-computed
    # 4.02 veto results from Step 4b above so compute_risk_flags doesn't
    # re-issue the EDGAR fetch.
    composite = compute_composite(pillar_df)
    sectors_dict = {t: inp.sector for t, inp in inputs.items()}
    non_reliance_by_ticker = {
        t: r.non_reliance_flag.fired
        for t, r in tier2_results.items()
        if r.non_reliance_flag.fired
    }
    # PR 4.5a.2 + 4.5a.3 — pre-compute Beneish + Dechow scores before
    # risk-flag pass so `compute_risk_flags` can apply the soft-vetoes
    # at M > -1.78 / F > 3.0. The per-ticker loop below (Step 8) reuses
    # these cached results when writing `beneish_high` / `dechow_high`
    # annotates at the looser thresholds and the numeric scores on
    # StockDetail.
    beneish_results: dict[str, BeneishResult] = {}
    beneish_m_scores: dict[str, float | None] = {}
    dechow_results: dict[str, DechowResult] = {}
    dechow_f_scores: dict[str, float | None] = {}
    for ticker, snap in snapshots.items():
        b_result = compute_beneish(snap, histories.get(ticker))
        beneish_results[ticker] = b_result
        beneish_m_scores[ticker] = b_result.m_score
        d_result = compute_dechow_f(snap, histories.get(ticker))
        dechow_results[ticker] = d_result
        dechow_f_scores[ticker] = d_result.f_score
    risk_flags = compute_risk_flags(
        snapshots,
        histories=histories,
        sectors=sectors_dict,
        non_reliance_by_ticker=non_reliance_by_ticker,
        beneish_m_scores=beneish_m_scores,
        dechow_f_scores=dechow_f_scores,
    )

    # PR 4.5c — Roychowdhury 2006 Real Earnings Management. Three
    # abnormal proxies (CFO, production, discretionary expenses) fit
    # per-sector via OLS; flag `rem_suspect` fires when 2 of 3
    # residuals sit in their respective "worst" decile within sector.
    # ANNOTATE-only — appended to `valuation_warnings` in the Step-8
    # per-ticker loop below. Single pass (one sector regression per
    # sector, then per-ticker residual lookup).
    rem_results = compute_rem_flags(
        snapshots,
        histories=histories,
        sectors=sectors_dict,
    )

    # Step 5b — cross-sectional inputs for the fair-price ensemble.
    # Built ONCE; reused inside the per-ticker loop below.
    logger.info("Building cross-sectional inputs for fair-price ensemble…")
    universe_metrics = _build_universe_metrics(snapshots, df)
    by_sub_industry, by_sector, broad_ex_fin_util = _build_peer_groupings(df)
    historical_metrics = _build_historical_metrics(histories, snapshots)

    # Step 5c — per-sector pillar median baselines for the stock-detail
    # overlay (issue #34). Built once; looked up by sector in the per-
    # ticker loop below. Sectors below PILLAR_BASELINE_MIN_PEERS are
    # absent here — those tickers carry pillar_baseline=None.
    sector_pillar_baselines = build_sector_pillar_baselines(
        pillar_df, by_sector, min_peers=config.PILLAR_BASELINE_MIN_PEERS,
    )
    logger.info(
        "Sector pillar baselines built for %d/%d sectors (min_peers=%d)",
        len(sector_pillar_baselines),
        len(by_sector),
        config.PILLAR_BASELINE_MIN_PEERS,
    )

    # Step 6 — assemble ranking DataFrame.
    df = df.assign(composite_score=composite.reindex(df.index).fillna(0.0))
    df = df.sort_values(
        "composite_score", ascending=False, kind="mergesort"
    ).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)

    # asof_date is needed by the Step-6b stale-filing pre-scan below (and
    # reused throughout Step 8); hoisted here from its later definition so
    # the pre-Step-7 lag check can reference it.
    now = _now_utc()
    asof_date = now.date()

    # Step 6b — inject stale_filing_hard into risk_flags BEFORE the Step-7
    # rotation so the veto check below sees it (issue #309). The fair-price
    # ensemble also returns stale_filing_hard and the Step-8 loop merges it,
    # but that merge runs AFTER rotation — without this pre-scan a hard-stale
    # stock could keep entered_top5 despite a non-empty risk_flags (Rule 16
    # violation). The Step-8 merge stays (idempotent; deduped there).
    for _, _r in df.iterrows():
        _ticker = str(_r["ticker"])
        _snap = snapshots.get(_ticker)
        if _snap is None:
            continue
        if stale_filing_status(_filing_lag(_snap, asof_date)) == "hard":
            _merged = list(risk_flags.get(_ticker, []))
            if "stale_filing_hard" not in _merged:
                _merged.append("stale_filing_hard")
                risk_flags[_ticker] = _merged

    # Step 7 — Top-5 rotation. Flagged stocks never earn entered_top5
    # regardless of rank (per PR-3b veto enforcement decision 2026-05-08).
    previous_top5 = read_previous_top5(config.DATA_DIR)
    current_top5: list[str] = []
    for _, r in df.iterrows():
        if len(current_top5) >= 5:
            break
        ticker = str(r["ticker"])
        if risk_flags.get(ticker):
            continue  # skip flagged stocks even if they'd qualify
        current_top5.append(ticker)
    current_top5_set = set(current_top5)
    entered = current_top5_set - previous_top5
    exited = previous_top5 - current_top5_set
    logger.info(
        "Top-5 rotation: entered=%s exited=%s (flagged-skipped count=%d)",
        sorted(entered),
        sorted(exited),
        sum(1 for f in risk_flags.values() if f),
    )

    # Phase 4h — OSAP signal replication + PBO/DSR gate + Path-b blend.
    # Observability-only this phase: Top-5 ranking still uses raw
    # ``composite_score`` per SKILL.md Rule 16. The blend writes a
    # ``composite_score_osap_adjusted`` per ticker into
    # ``StockDetail.osap_blended_score`` for delta-attribution. Wrapped
    # in try/except so OSAP fetch / library / network failure NEVER
    # blocks weekly production — every OSAP-bearing field degrades to
    # ``None`` on the schema (already ``| None = None`` in
    # ``compute/output/schemas.py``).
    osap_signals_used: list[str] = []
    osap_excluded_signals: list[str] = []
    osap_signals_ic_12m: dict[str, float] = {}
    osap_signal_map: dict[str, dict[str, float] | None] = {}
    osap_signals_coverage_pct: dict[str, float] = {}
    composite_osap_adjusted: pd.Series = pd.Series(dtype=float)
    # Phase 4h.2 Part 1 (issue #116) — manifest entries the OSAP fetch
    # returned no rows for. Populated inside the try block below; left
    # empty when the OSAP pipeline fails entirely (graceful-degradation
    # path leaves every osap_* metadata field None).
    osap_signals_missing_from_dataset: list[str] = []
    # Phase 4h.2 Part 1 (issue #116) — per-signal PBO/DSR/Sharpe/
    # rejection_reason diagnostics for every signal that reaches the
    # gate. Populated inside the try block from ``gate_results``.
    osap_gate_diagnostics: dict[str, OsapGateDiagnostic] = {}
    # Phase 4h.2 Part 2 (issue #116) — signals present in the OSAP
    # dataset but with <2 distinct port buckets (silent drop in
    # 0.9.0-0.9.1; visible here). Closes the 100-signal accounting
    # equation alongside ``osap_signals_missing_from_dataset`` and
    # ``osap_signals_used`` / ``osap_excluded_signals``.
    osap_signals_dropped_no_long_short_list: list[str] = []
    # Issue #287 PR A — wall-clock for the OSAP pipeline. Measures the
    # entire try block including the dataset fetch + gate + per-signal
    # IC compute + blend. `None` semantics: only set to None when the
    # outer except fires (full pipeline failure). On a QR_SKIP_OSAP
    # cache-hit fast return the wall-clock will be a small float (~0.5-2s)
    # — informative as "skipped fast" vs the cold ~120-300s download.
    _osap_wc_start = time.monotonic()
    osap_wall_clock_seconds: float | None = None
    try:
        # Phase 4a — deferred imports. `compute.ingest.osap` pulls in
        # `openassetpricing` at module load (only installed via the
        # `.[factors]` optional extra), so a top-level import would
        # break `tests/test_main.py` collection in base-install envs.
        # ImportError here is caught by the existing `except Exception`
        # below and falls through to the same graceful-degradation path
        # any other OSAP-pipeline failure takes (every osap_* field
        # already nullable per Rule 18).
        from compute.features.osap_replicate import (
            compute_long_short_returns,
            compute_osap_signals,
            coverage_by_signal,
            signals_dropped_no_long_short,
            signals_in_dataframe,
        )
        from compute.ingest.osap import fetch_osap_returns
        from compute.scoring.osap_blend import aggregate_osap_signals, apply_osap_blend
        from compute.validation.osap_validation import (
            compute_rolling_ic_12m,
            filter_accepted_signals,
            gate_osap_signals,
        )

        logger.info(
            "Phase 4h — fetching OSAP returns for %d-signal manifest "
            "(as_of=%s)",
            len(config.OSAP_SIGNALS_100),
            asof_date.isoformat(),
        )
        osap_returns_raw = fetch_osap_returns(
            signals=list(config.OSAP_SIGNALS_100),
            as_of=asof_date,
        )
        # Phase 4h.2 Part 1 — surface silent drops between manifest and
        # dataset (issue #116). 100 manifest signals, but production
        # observation has shown only ~22 reach the gate; the other ~78
        # silently disappeared at this filter step in 0.9.0-phase4h.
        # Now they land in metadata.osap_signals_missing_from_dataset.
        present_signals = signals_in_dataframe(osap_returns_raw)
        osap_signals_missing_from_dataset = sorted(
            set(config.OSAP_SIGNALS_100) - present_signals
        )
        if osap_signals_missing_from_dataset:
            logger.warning(
                "OSAP manifest signals not in dataset: %d/%d missing "
                "(first 5: %s)",
                len(osap_signals_missing_from_dataset),
                len(config.OSAP_SIGNALS_100),
                osap_signals_missing_from_dataset[:5],
            )
        # Phase 4h.2 Part 2 — signals with <2 port buckets (no LS pair).
        # Restrict to the requested manifest so the accounting equation
        # closes against OSAP_SIGNALS_100 (dataset rows for non-manifest
        # signals are filtered out by fetch_osap_returns).
        osap_signals_dropped_no_long_short_list = [
            s
            for s in signals_dropped_no_long_short(osap_returns_raw)
            if s in set(config.OSAP_SIGNALS_100)
        ]
        if osap_signals_dropped_no_long_short_list:
            logger.warning(
                "OSAP signals in dataset but with <2 port buckets "
                "(no LS pair possible): %d/%d dropped (first 5: %s)",
                len(osap_signals_dropped_no_long_short_list),
                len(config.OSAP_SIGNALS_100),
                osap_signals_dropped_no_long_short_list[:5],
            )
        osap_ls = compute_long_short_returns(osap_returns_raw)
        logger.info(
            "OSAP long-short rows: %d across %d signals",
            len(osap_ls),
            osap_ls["signalname"].nunique() if not osap_ls.empty else 0,
        )

        gate_results = gate_osap_signals(
            osap_ls,
            requested_signals=config.OSAP_SIGNALS_100,
        )
        # Phase 4h.2 Part 1 — persist per-signal gate decisions into
        # metadata (issue #116). Captures EVERY signal that reached the
        # gate (both accepted and rejected); accepted signals carry
        # ``rejection_reason=None`` while rejected carry one of the
        # canonical taxonomy values (``high_pbo`` / ``low_dsr`` /
        # ``insufficient_data`` / ``gate_failed``) per
        # ``compute/validation/osap_validation.py::GateResult``.
        osap_gate_diagnostics = {
            sig: OsapGateDiagnostic(
                pbo=result.pbo,
                dsr=result.dsr,
                sharpe=result.sharpe,
                rejection_reason=result.rejection_reason,
            )
            for sig, result in gate_results.items()
        }
        osap_signals_used, osap_excluded_signals = filter_accepted_signals(
            gate_results
        )
        logger.info(
            "OSAP PBO/DSR gate: %d accepted, %d excluded "
            "(of %d candidates)",
            len(osap_signals_used),
            len(osap_excluded_signals),
            len(gate_results),
        )

        # Rolling-12m Spearman IC per accepted signal — observability only,
        # NOT a gate decision (canonical full walk-forward + purged-embargo
        # CV is deferred to Phase 5 per defense-infrastructure/PLAN.md:270).
        for sig in osap_signals_used:
            ic = compute_rolling_ic_12m(osap_ls, sig)
            if ic is not None:
                osap_signals_ic_12m[sig] = round(float(ic), 4)

        # Per-ticker signal map (commit 2 proxy mode — every ticker gets
        # the market-wide cross-sectional rank). Only the accepted signal
        # subset is consumed; excluded signals never blend.
        if osap_signals_used:
            osap_filtered_returns = osap_returns_raw[
                osap_returns_raw["signalname"].isin(osap_signals_used)
            ]
            osap_signal_map = compute_osap_signals(
                osap_filtered_returns,
                tickers=list(pillar_df.index),
                as_of=asof_date,
                requested_signals=tuple(osap_signals_used),
            )
            osap_signals_coverage_pct = {
                sig: round(pct, 2)
                for sig, pct in coverage_by_signal(osap_signal_map).items()
            }

            # Path-b blend (commit 3) — applied OUTSIDE compute_composite()
            # so PHASE3_WEIGHTS sum-to-1.0 invariant at composite.py:43-45
            # stays intact. 50/50 default locked in
            # osap-integration/PLAN.md:168-170.
            osap_aggregate = aggregate_osap_signals(osap_signal_map)
            composite_osap_adjusted = apply_osap_blend(
                composite, osap_aggregate
            )
        else:
            logger.warning(
                "OSAP gate accepted 0 signals — skipping per-ticker map + "
                "blend; osap_blended_score will be None for every ticker"
            )
        # Issue #287 PR A — wall-clock end marker (success path).
        osap_wall_clock_seconds = round(time.monotonic() - _osap_wc_start, 1)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "OSAP pipeline failed (observability-only — production "
            "continues); StockDetail.osap_* + metadata.osap_* → None. "
            "Error: %s",
            e,
        )
        osap_signals_used = []
        osap_excluded_signals = []
        osap_signals_ic_12m = {}
        osap_signal_map = {}
        osap_signals_coverage_pct = {}
        composite_osap_adjusted = pd.Series(dtype=float)
        osap_signals_missing_from_dataset = []
        osap_gate_diagnostics = {}
        osap_signals_dropped_no_long_short_list = []
        # Issue #287 PR A — leave osap_wall_clock_seconds = None on failure.
        osap_wall_clock_seconds = None

    # Phase 4j.1 — Qlib Alpha158 factor integration, OBSERVABILITY-ONLY
    # (SKILL.md Rule 18). The adapter
    # (``compute/features/alpha158_replicate.py``) converts the 158
    # per-stock Alpha158 feature values into the ``(date × signal)``
    # long-short return contract so the Phase-4h PBO/DSR gate
    # (``osap_validation.gate_osap_signals``) applies UNCHANGED with
    # ``n_trials=158``. This phase blends NOTHING — Top-5 + every
    # ``composite_score`` is byte-identical to pre-4j.1 (Δscore = 0 on
    # every ticker, per Rule 16); the rank-influencing blend is deferred
    # to 4j.2. Wrapped in try/except so an Alpha158 / Qlib / data failure
    # NEVER blocks weekly production — every ``alpha158_*`` field degrades
    # to ``None``. The live feature SOURCE is itself deferred
    # (``_acquire_alpha158_inputs`` raises until the Qlib bin cache is
    # wired); the diagnostic surface + adapter + gate wiring ship now and
    # are verified by the offline test suite.
    alpha158_features_used: list[str] = []
    alpha158_excluded_features: list[str] = []
    alpha158_features_ic_12m: dict[str, float] = {}
    alpha158_features_missing_from_compute: list[str] = []
    alpha158_features_dropped_no_long_short_list: list[str] = []
    alpha158_gate_diagnostics: dict[str, OsapGateDiagnostic] = {}
    alpha158_coverage_pct: float | None = None
    alpha158_survivorship_bias_corrected: bool | None = None
    _alpha158_wc_start = time.monotonic()
    alpha158_wall_clock_seconds: float | None = None
    try:
        from compute.features.alpha158_replicate import (
            compute_alpha158_long_short_returns,
            features_dropped_no_long_short,
            features_missing_from_compute,
        )
        from compute.features.alpha158_replicate import (
            coverage_pct as alpha158_coverage_fn,
        )
        from compute.ingest.qlib_features import ALPHA158_FEATURE_NAMES
        from compute.validation.osap_validation import (
            compute_rolling_ic_12m,
            filter_accepted_signals,
            gate_osap_signals,
        )

        # Acquire the feature panel + forward-return panel + point-in-time
        # universe provider. DEFERRED — raises until the Qlib bin cache
        # lands (see the helper docstring); caught below → every field None.
        (
            alpha158_features,
            alpha158_period_returns,
            alpha158_universe_provider,
        ) = _acquire_alpha158_inputs(asof_date, list(pillar_df.index))

        ls_result = compute_alpha158_long_short_returns(
            alpha158_features,
            alpha158_period_returns,
            universe_provider=alpha158_universe_provider,
        )
        alpha158_ls = ls_result.long_short
        alpha158_survivorship_bias_corrected = (
            ls_result.survivorship_bias_corrected
        )

        # Accounting buckets 1 + 2: never-computed + computed-but-no-LS.
        alpha158_features_missing_from_compute = features_missing_from_compute(
            alpha158_features, ALPHA158_FEATURE_NAMES
        )
        alpha158_features_dropped_no_long_short_list = (
            features_dropped_no_long_short(
                alpha158_ls, alpha158_features, ALPHA158_FEATURE_NAMES
            )
        )

        # The Phase-4h PBO/DSR gate, reused verbatim with n_trials=158.
        gate_results = gate_osap_signals(
            alpha158_ls, requested_signals=ALPHA158_FEATURE_NAMES
        )
        alpha158_gate_diagnostics = {
            feat: OsapGateDiagnostic(
                pbo=result.pbo,
                dsr=result.dsr,
                sharpe=result.sharpe,
                rejection_reason=result.rejection_reason,
            )
            for feat, result in gate_results.items()
        }
        alpha158_features_used, alpha158_excluded_features = (
            filter_accepted_signals(gate_results)
        )

        # Rolling-12m IC per accepted feature — observability ONLY, never a
        # gate decision. A surfaced |IC| > 0.05 is an overfit / look-ahead
        # ALARM to audit, not a win (methodology-scientist red flag).
        for feat in alpha158_features_used:
            ic = compute_rolling_ic_12m(alpha158_ls, feat)
            if ic is not None:
                alpha158_features_ic_12m[feat] = round(float(ic), 4)

        alpha158_coverage_pct = alpha158_coverage_fn(
            alpha158_features, len(pillar_df.index)
        )

        # Accounting equation guard — logged, NEVER fatal. The invariant
        # whose absence made Phase 4h's ~78-signal silent drop invisible
        # for a full phase:
        #   158 == missing + dropped + used + excluded
        _alpha158_accounted = (
            len(alpha158_features_missing_from_compute)
            + len(alpha158_features_dropped_no_long_short_list)
            + len(alpha158_features_used)
            + len(alpha158_excluded_features)
        )
        if _alpha158_accounted != config.ALPHA158_FEATURE_COUNT:
            logger.warning(
                "Alpha158 accounting equation does NOT close: %d "
                "(missing=%d + dropped=%d + used=%d + excluded=%d) != %d",
                _alpha158_accounted,
                len(alpha158_features_missing_from_compute),
                len(alpha158_features_dropped_no_long_short_list),
                len(alpha158_features_used),
                len(alpha158_excluded_features),
                config.ALPHA158_FEATURE_COUNT,
            )
        alpha158_wall_clock_seconds = round(
            time.monotonic() - _alpha158_wc_start, 1
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Alpha158 pipeline failed/deferred (observability-only — "
            "production continues); metadata.alpha158_* → None. Error: %s",
            e,
        )
        alpha158_features_used = []
        alpha158_excluded_features = []
        alpha158_features_ic_12m = {}
        alpha158_features_missing_from_compute = []
        alpha158_features_dropped_no_long_short_list = []
        alpha158_gate_diagnostics = {}
        alpha158_coverage_pct = None
        alpha158_survivorship_bias_corrected = None
        alpha158_wall_clock_seconds = None

    # Step 8 — combined per-ticker loop: fair-price ensemble + price history
    # write + StockSummary + StockDetail. Single pass so per-ticker outputs
    # stay synchronized (e.g., has_history reflects the actual write result;
    # ensemble warnings flow into both summary and detail consistently).
    # Issue #287 PR A — wall-clock for the entire Step 8 loop. Documented
    # limitation: this includes fair-price ensemble + manipulation_index
    # + StockDetail write — not just the cross_source_validate_market_cap
    # sub-call. On cold-cache cross-source (502 × 2-8s serial yfinance.info
    # = 17-67 min) the sub-call dominates; on warm cache the other Step 8
    # work (~50s total) dominates.
    _cross_source_wc_start = time.monotonic()
    cross_source_wall_clock_seconds: float | None = None
    summaries: list[StockSummary] = []
    detail_count = 0
    history_count = 0
    fair_price_count = 0
    # Phase 4b — observability surface for the new Roychowdhury 2006
    # size-invariant loss-avoidance annotate. Counter increments inside
    # the per-ticker loop when the flag is appended to valuation_warnings;
    # written to Metadata.loss_avoidance_size_invariant_firing_count so
    # the next cron's firing rate is visible without grepping per-stock
    # JSONs (Rule 18 observability-before-wiring).
    loss_avoidance_size_invariant_firing_count: int = 0
    # Issue #176 — same Rule 18 observability surface for the new
    # ``share_count_extraction_missing`` annotate. Counter increments
    # inside the per-ticker loop when the flag is appended to
    # valuation_warnings; written to
    # Metadata.share_count_extraction_missing_count so the universe-
    # wide firing rate of the STZ-style partial-XBRL-extraction pattern
    # is visible at-a-glance from the next cron without grepping
    # per-stock JSONs.
    share_count_extraction_missing_count: int = 0
    # Issue #177 — same Rule 18 observability surface for the new
    # ``extreme_estimate_majority`` annotate. The flag itself is
    # appended by ``compute.valuation.ensemble`` when ≥
    # ``config.EXTREME_MAJORITY_THRESHOLD`` of the 6 methods fire
    # Defense #4 outlier guard; this counter increments here when the
    # flag is observed on the ensemble's ``valuation_warnings`` list.
    # Written to Metadata.extreme_estimate_majority_count so the next
    # cron's firing rate (gates the follow-up median-exclusion PR per
    # methodology-scientist Mode B 2026-05-21) is visible at-a-glance.
    extreme_estimate_majority_count: int = 0
    # Issue #248 PR2a (0.10.3-phase4.5e) — Rule 18 observability for the
    # cross-source market-cap validator. Counter + histogram + per-ticker
    # delta all populated from the validator's tuple-return refactor
    # (`compute/ingest/cross_source.validate_market_cap` now returns
    # ``(disagreement: bool, delta: float | None)``). Histogram buckets
    # init to zero across all 9 keys so the schema-snapshot key set is
    # stable even on a no-fire run.
    cross_source_disagreement_count: int = 0
    cross_source_delta_histogram: dict[str, int] = {
        key: 0 for key in CROSS_SOURCE_BUCKET_KEYS
    }
    cross_source_delta_by_ticker: dict[str, float | None] = {}
    # PR-A2 — listing-metadata wiring (StockDetail.exchange / .country).
    # Display-mapped exchange name + derived country, one entry per ticker
    # iterated in Step 8. Skip-safe: fetch_yfinance_exchange honors
    # QR_SKIP_CROSS_SOURCE internally (returns None on cold simulate cache).
    exchange_by_ticker: dict[str, str | None] = {}
    country_by_ticker: dict[str, str | None] = {}
    # Issue #67 — Rule 18 observability surface for sector-adjusted CoE.
    # Both counts are computed on EVERY cron regardless of USE_SECTOR_COE
    # so the delta (flat-10% vs per-sector) is observable before the flag
    # is flipped.  ``_without_sector_coe`` = baseline (ROE ≤ flat 0.10);
    # ``_with_sector_coe`` = count under SECTOR_COST_OF_EQUITY dict lookup.
    # See compute/scoring/cost_of_equity.py for the Damodaran 2019 table.
    value_trap_risk_count_without_sector_coe: int = 0
    value_trap_risk_count_with_sector_coe: int = 0
    # Issue #67 follow-up (0.10.10-phase4.6) — per-sector breakdown of the
    # same counts, keyed by GICS sector name. Methodology-scientist Q2
    # verdict 2026-05-28 (deferred from PR #294) requested this for
    # Q3 2026-08-19 quarterly cohort audit visibility — confirms the
    # Damodaran 2019 Ch. 8.4 shape (lower-Ke sectors drop flags, higher-
    # Ke sectors gain flags) before ≥ 12 cron weeks of post-flip data
    # accumulate. The delta is computed below at Metadata-construction
    # time as `_without - _with` per sector.
    value_trap_risk_count_without_sector_coe_by_sector: dict[str, int] = {}
    value_trap_risk_count_with_sector_coe_by_sector: dict[str, int] = {}
    # Phase 4.5e PR 3 — Rule 18 observability for the new Form-4 annotates.
    # Counters increment inside the per-ticker loop when the flag is
    # appended to valuation_warnings; written to
    # Metadata.insider_sell_cluster_firing_count +
    # Metadata.c_suite_unusual_sell_firing_count so the first cron with
    # the flags wired shows the universe-wide firing rate at-a-glance.
    # Gates the methodology-scientist Q3 2026-08-19 cohort-acceptance
    # check that may promote INSIDER_SELL_CLUSTER_WEIGHT from 5.0 → 10.0.
    insider_sell_cluster_firing_count: int = 0
    c_suite_unusual_sell_firing_count: int = 0
    # Phase 4.5e PR 4-eq — Rule 18 observability for the 10b5-1
    # contamination filter applied in _is_opportunistic_sell. Counts
    # the universe-wide total of transactions excluded by the filter
    # (would have been opportunistic absent the gate) — the empirical
    # lever for the methodology-scientist Q3 2026-08-19 cohort-
    # acceptance check (issue #130). Expected delta vs PR #222 baseline:
    # -30% to -45% on insider_sell_cluster_firing_count per
    # Jagolinzer 2009 §3.2 + SEC 2022 economic analysis.
    form4_rule10b5_one_excluded_count: int = 0
    # Issue #261 (0.10.5-phase4.5e) — pre-compute the CIK-collision set
    # BEFORE the per-ticker loop so each ticker's annotate emit is a
    # simple `ticker in flagged_set` membership test. The detector
    # needs the FULL universe upfront (it's a universe-level scan, not
    # a per-ticker check). cik_by_ticker is sourced from the already-
    # built `snapshots` dict; market_cap_by_ticker mirrors the
    # `_build_raw_metrics` line 319 computation (price × shares).
    # Tickers with missing snapshots / shares fall out of both maps —
    # the detector returns an empty set if no CIK collisions are
    # observable on the available data (graceful degradation, no
    # exception path).
    cik_by_ticker: dict[str, str | None] = {}
    market_cap_by_ticker: dict[str, float | None] = {}
    for _, r in df.iterrows():
        t = str(r["ticker"])
        s = snapshots.get(t)
        if s is None:
            cik_by_ticker[t] = None
            market_cap_by_ticker[t] = None
            continue
        cik_by_ticker[t] = s.cik
        market_cap_by_ticker[t] = (
            float(r["current_price"]) * s.shares_outstanding
            if s.shares_outstanding is not None
            else None
        )
    multi_class_flagged_tickers: set[str] = (
        detect_multi_class_aggregate_shares_suspected(
            cik_by_ticker, market_cap_by_ticker
        )
    )
    multi_class_aggregate_shares_suspected_count: int = 0
    # Phase 8 pilot PR 3a — cohort-by-ticker lookup for index_membership.
    # Built once from df (which carries "cohort" from _fetch_prices_one);
    # defaults to "sp500" so any ticker absent from df (e.g. post-price-fail
    # drop) stays safe. The column is unconditionally present on both the
    # sp500 and sp900 paths (added in the universe-load seam above).
    cohort_by_ticker: dict[str, str] = {
        str(r["ticker"]): str(r.get("cohort", "sp500"))
        for _, r in df.iterrows()
    }
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        snap = snapshots.get(ticker)
        current_price = float(r["current_price"])
        sector = str(r["sector"])
        sub_industry_raw = r.get("industry")
        sub_industry = (
            str(sub_industry_raw)
            if sub_industry_raw is not None and pd.notna(sub_industry_raw)
            else None
        )
        pillar_row = pillar_df.loc[ticker] if ticker in pillar_df.index else pd.Series(dtype=float)

        # Fair-price ensemble (skipped when snapshot is missing — without
        # fundamentals there's no input to any of the 6 methods).
        ensemble: EnsembleResult | None = None
        ensemble_dict: dict | None = None
        valuation_warnings: list[str] = []
        tbvps_value: float | None = None
        if snap is not None:
            tbvps_value = tangible_book_value_per_share(snap)
            sub_panel = (
                [t for t in by_sub_industry.get(sub_industry, []) if t != ticker]
                if sub_industry is not None
                else []
            )
            sector_panel = [t for t in by_sector.get(sector, []) if t != ticker]
            broad_panel = [t for t in broad_ex_fin_util if t != ticker]
            tier_panel = {
                "sub_industry": sub_panel,
                "industry": [],  # GICS level-2 not parsed; falls through to sector
                "sector": sector_panel,
                "broad": broad_panel,
            }
            peer_panels = {
                "pe": tier_panel,
                "pb": tier_panel,
                "ev_ebitda": tier_panel,
            }
            ensemble, extra_flags = compute_fair_price_ensemble(
                ticker=ticker,
                snap=snap,
                sector=sector,
                sub_industry=sub_industry,
                industry=None,
                current_price=current_price,
                filing_lag_days_value=_filing_lag(snap, asof_date),
                peer_panels=peer_panels,
                universe_metrics=universe_metrics,
                historical_metrics=historical_metrics,
            )
            ensemble_dict = ensemble_result_to_dict(ensemble)
            valuation_warnings = list(ensemble.valuation_warnings)
            if extra_flags:
                merged = list(risk_flags.get(ticker, []))
                for f in extra_flags:
                    if f not in merged:
                        merged.append(f)
                risk_flags[ticker] = merged
            if ensemble.median is not None or ensemble.max is not None:
                fair_price_count += 1

        # Issue #262 (2026-05-26) — writer-parity for the input-level
        # ``data_quality_input_corruption`` veto. When the veto fires
        # in ``risk_flags`` (input-level corruption per
        # ``compute/scoring/risk_overlay.py::_data_quality_input_corruption``:
        # TBVPS > $10K/share / TTM revenue < $50M / |NI| > |revenue|),
        # ALSO append the parallel ``valuation_output_anomalous``
        # annotate to ``valuation_warnings`` so the UI surface
        # (``FairPriceCard.tsx``) renders the explanation chip for the
        # all-null fair-price ensemble. Closes the veto-only-cohort
        # UI explainability gap surfaced by methodology-scientist
        # Mode B 2026-05-26 — 4 tickers (MTB / CPT / MRNA / HBAN on
        # the 2026-05-23 cron #3) carried the veto but had no UI
        # annotate because the ensemble-layer Site-2 check didn't
        # additionally fire. Composite rank UNCHANGED — the veto
        # surface already handles Top-5 suppression; this only adds
        # the annotate for UI parity.
        if (
            "data_quality_input_corruption" in risk_flags.get(ticker, [])
            and "valuation_output_anomalous" not in valuation_warnings
        ):
            valuation_warnings.append("valuation_output_anomalous")

        # Beneish M-score (PR 3e.1 ANNOTATE at M > -2.22 + PR 4.5a.2
        # soft-veto promotion at M > -1.78). The active-veto path is
        # already wired into ``risk_flags`` above via
        # ``beneish_m_scores`` injection; this block keeps the
        # ``beneish_high`` annotate (M > -2.22 band) on
        # `valuation_warnings` and the numeric m_score on StockDetail
        # for transparency. Cached from the pre-compute pass to avoid
        # recomputing the 8-ratio model twice per ticker.
        beneish_result = beneish_results[ticker]
        if beneish_result.is_high and "beneish_high" not in valuation_warnings:
            valuation_warnings.append("beneish_high")

        # Dechow F-score (PR 3e.2 ANNOTATE at F > 2.45 + PR 4.5a.3
        # soft-veto promotion at F > 3.0). Active-veto path is wired
        # into ``risk_flags`` above via ``dechow_f_scores`` injection;
        # this block keeps the ``dechow_high`` annotate (F > 2.45 band)
        # on `valuation_warnings`. Cached from pre-compute pass.
        dechow_result = dechow_results[ticker]
        if dechow_result.is_high and "dechow_high" not in valuation_warnings:
            valuation_warnings.append("dechow_high")

        # PR 4.5a.3 — `manipulation_triple_flag` joint-gate badge.
        # Fires when Sloan (cross-sectional or sector-relative)
        # AND Beneish annotate AND Dechow annotate all fire on the
        # SAME ticker. Rare but high-confidence — typically 0-3
        # tickers per universe. UI-only badge in `valuation_warnings`;
        # does NOT add a third veto on top of the individual vetoes
        # already doing that work. Per PR #86 plan §4.5a.3.
        ticker_risk = set(risk_flags.get(ticker) or [])
        if (
            "sloan_accruals_top_decile" in ticker_risk
            and "beneish_high" in valuation_warnings
            and "dechow_high" in valuation_warnings
            and "manipulation_triple_flag" not in valuation_warnings
        ):
            valuation_warnings.append("manipulation_triple_flag")

        # Cross-source market-cap validator (PR 4b §1 + PR2a Issue #248
        # tuple-return refactor 0.10.3). Compares SEC-derived market cap
        # (shares × current_price) vs yfinance .info marketCap. Delta > 5%
        # surfaces as ``cross_source_disagreement`` annotate. Catches
        # yfinance scraper drift (pre-split share counts, intraday vs EOD,
        # M&A ticker rotation) AND multi-class XBRL extraction failures
        # (V/Visa Class A-only, FOXA, NWS/NWSA — issue #248). The delta
        # is now ALSO recorded per-ticker (StockDetail.cross_source_delta)
        # and aggregated into a universe histogram
        # (Metadata.cross_source_delta_histogram) for PR2b severe-threshold
        # calibration per methodology-scientist Mode B verdict 2026-05-25.
        disagreement, csd_delta = cross_source_validate_market_cap(
            ticker=ticker,
            snap=snap,
            current_price=current_price,
        )
        cross_source_delta_by_ticker[ticker] = csd_delta
        cross_source_delta_histogram[cross_source_bucket_delta(csd_delta)] += 1
        if disagreement:
            cross_source_disagreement_count += 1
            if "cross_source_disagreement" not in valuation_warnings:
                valuation_warnings.append("cross_source_disagreement")

        # PR-A2 — listing metadata (display-only; no scoring/ranking impact).
        # Piggybacks the cross_source yfinance loop; skip-safe via
        # QR_SKIP_CROSS_SOURCE inside fetch_yfinance_exchange.
        exchange_code = fetch_yfinance_exchange(ticker)
        exchange_by_ticker[ticker] = exchange_name(exchange_code)
        country_by_ticker[ticker] = country_for_exchange(exchange_code)

        # Issue #261 — multi_class_aggregate_shares_suspected annotate.
        # CIK-collision detector (precomputed before this loop) flags
        # tickers from multi-class issuers where the SEC companyfacts
        # API returns the AGGREGATE share count rather than the per-
        # class breakdown — the GOOG/GOOGL overcount pattern (opposite
        # direction to the PR #257 allowlist which corrects undercount
        # via per-filing XBRL dimensional sum). Annotate-only —
        # composite rank unchanged; surfaces the structural pattern
        # for Q3 2026-08-19 quarterly-audit cohort visibility while
        # PR-B (reverse-allowlist per-class XBRL extraction) lands as
        # the structural fix.
        if ticker in multi_class_flagged_tickers:
            multi_class_aggregate_shares_suspected_count += 1
            if "multi_class_aggregate_shares_suspected" not in valuation_warnings:
                valuation_warnings.append("multi_class_aggregate_shares_suspected")

        # PR 4.5b §1 — restatement_history annotate. 10-K/A or 10-Q/A
        # filings in the trailing 5 years from SEC EDGAR. Hennes-Leone-
        # Miller 2008 *TAR* — restating firms see -9% abnormal return
        # on announcement; recurrent restaters compound the effect.
        # ANNOTATE-only (sector-agnostic base rate, no veto).
        restatement_result = check_restatement_history(ticker, asof=asof_date)
        if (
            restatement_result.fired
            and "restatement_history" not in valuation_warnings
        ):
            valuation_warnings.append("restatement_history")

        # Epic #150 Phase 2.2 — restatement_high_confidence annotate.
        # Co-occurrence of a 10-K/A or 10-Q/A amendment with an 8-K
        # Item 4.02 (non-reliance) filing within 90 days. Hennes-Leone-
        # Miller 2008 *TAR* "irregularity" signature — PPV ~70% vs
        # bare `restatement_history`'s ~30%. Annotate path (lands in
        # `valuation_warnings`, not `risk_flags`): composite-rank
        # source stays raw composite per SKILL.md Rule 16, but the
        # flag contributes to `manipulation_index` (delta +3.0 on top
        # of bare flag's +5.0 → 8.0 total when both fire), which
        # feeds the 10-pt-max soft penalty into `composite_score_adjusted`
        # on the detail-page Manipulation Risk card. Existing
        # `restatement_history` semantics + weight unchanged in this
        # PR (Phase 2.2 follow-up will decide whether to retire the
        # bare flag after a cohort acceptance check).
        amendment_dates = get_amendment_filing_dates(ticker, asof=asof_date)
        non_reliance_dates = get_non_reliance_filing_dates(ticker, asof=asof_date)
        high_conf_result = compute_high_confidence_restatement(
            amendment_dates, non_reliance_dates
        )
        if (
            high_conf_result.fired
            and "restatement_high_confidence" not in valuation_warnings
        ):
            valuation_warnings.append("restatement_high_confidence")

        # PR 4.5b §2 — late_filing_notification annotate. SEC Form
        # 12b-25 (NT 10-K / NT 10-Q) within the trailing 365 days.
        # Bartov-Lai-Yeung 2002 *JAR* — late filers see -5-7%
        # abnormal returns. ANNOTATE-only.
        late_filing_result = check_late_filing(ticker, asof=asof_date)
        if (
            late_filing_result.fired
            and "late_filing_notification" not in valuation_warnings
        ):
            valuation_warnings.append("late_filing_notification")

        # PR 4.5c — Roychowdhury 2006 REM. `rem_suspect` annotate
        # fires when 2 of 3 abnormal proxies (CFO, production,
        # discretionary expenses) sit in their respective worst
        # decile within sector. Results pre-computed above; this is
        # just the per-ticker append. Catches REAL manipulation —
        # cutting R&D, channel stuffing, deferring maintenance —
        # invisible to Sloan/Beneish/Dechow accrual targets.
        rem_result = rem_results.get(ticker)
        if (
            rem_result is not None
            and rem_result.fired
            and "rem_suspect" not in valuation_warnings
        ):
            valuation_warnings.append("rem_suspect")

        # PR 4.5d §1 — accruals_momentum_high annotate.
        # Δ(TATA = (NI − CFO)/TA) over trailing 3 fiscal years.
        # Threshold +0.05 ≈ Beneish 1999 ΔM > +0.5 via the β_TATA
        # coefficient. Catches manipulation gathering steam — the
        # snapshot-only Sloan + Beneish flags miss the trajectory.
        accruals_mom = check_accruals_momentum(snap, histories.get(ticker))
        if (
            accruals_mom.fired
            and "accruals_momentum_high" not in valuation_warnings
        ):
            valuation_warnings.append("accruals_momentum_high")

        # PR 4.5d §2 — loss_avoidance_pattern annotate.
        # Burgstahler-Dichev 1997 *JAE* kink at zero. 3+ consecutive
        # fiscal years of tiny-positive NI (∈ [0, $50M]) OR tiny-
        # positive EPS (∈ [0, $0.50]) = managers shading reported
        # earnings just enough to clear the loss threshold. (Phase
        # 2.4 of epic #150 rescaled the bands 10× for S&P 500 scale.)
        loss_avoid = check_loss_avoidance(snap, histories.get(ticker))
        if (
            loss_avoid.fired
            and "loss_avoidance_pattern" not in valuation_warnings
        ):
            valuation_warnings.append("loss_avoidance_pattern")

        # Phase 4b — loss_avoidance_pattern_size_invariant annotate.
        # Roychowdhury 2006 *JAE* §5.2 suspect-firm definition:
        # NI / TotalAssets ∈ [0, 0.005] for 3+ consecutive fiscal years.
        # Size-invariant sibling of the absolute-$ variant above; catches
        # chronically thin-margin large caps the BD 1997 dollar band misses.
        loss_avoid_si = check_loss_avoidance_size_invariant(
            snap, histories.get(ticker)
        )
        if (
            loss_avoid_si.fired
            and "loss_avoidance_pattern_size_invariant" not in valuation_warnings
        ):
            valuation_warnings.append("loss_avoidance_pattern_size_invariant")
            loss_avoidance_size_invariant_firing_count += 1

        # Issue #176 — share_count_extraction_missing annotate.
        # Fires when the snapshot has revenue + total_assets but
        # shares_outstanding is None (STZ 2026-05-14 pattern). Annotate-
        # only — distinct from the data_quality_input_corruption veto,
        # which keeps its shares_outstanding=None silence contract per
        # issue #18 / test_D3.
        if (
            check_share_count_extraction_missing(snap)
            and "share_count_extraction_missing" not in valuation_warnings
        ):
            valuation_warnings.append("share_count_extraction_missing")
            share_count_extraction_missing_count += 1

        # Issue #177 — extreme_estimate_majority annotate count.
        # The flag is appended by ``compute.valuation.ensemble`` when
        # ≥ config.EXTREME_MAJORITY_THRESHOLD of the 6 methods fire
        # Defense #4; we just count here so the universe-wide firing
        # rate is surfaced on Metadata for the next cron's audit (gates
        # the follow-up median-exclusion PR).
        if "extreme_estimate_majority" in valuation_warnings:
            extreme_estimate_majority_count += 1

        # Phase 4.5e PR 3 — Form-4 insider-cluster annotates.
        #
        # The per-ticker `fetch_recent_form4` is gated on PR 2's
        # diagnostic dict — we ONLY consult the cache when PR 2's fetch
        # loop above confirmed a populated entry (``fetch_status="ok"``).
        # This is critical for pre-merge-prod-sim which sets
        # ``FORM4_FETCH_SKIP=1`` to skip PR 2's bulk loop (cache is
        # cold; 502 × per-filing HTTP would exceed the 45-min CI cap —
        # confirmed by the 2026-05-23 cancellation on PR #222
        # workflow_run 26330610740). Without the gate,
        # ``fetch_recent_form4`` would cache-miss → fall through to a
        # live SEC fetch in the scoring loop and reproduce the same
        # blast radius PR 2 was carved out to avoid.
        #
        # On the weekly cron (compute-rankings.yml, no FORM4_FETCH_SKIP),
        # the diagnostic check is essentially free (dict lookup) and
        # all 502 tickers normally pass — the fast-path runs the
        # predicates over the full universe.
        #
        # Annotate-only per Rule 16 + portable-annotate-before-veto:
        # composite rank unchanged; only ``manipulation_index`` +
        # ``composite_score_adjusted`` soft penalty is impacted.
        _form4_diag = form4_diagnostics.get(ticker)
        if _form4_diag and _form4_diag.get("fetch_status") == "ok":
            _form4_txns = fetch_recent_form4(ticker)
            if detect_insider_sell_cluster(_form4_txns, asof_date):
                if "insider_sell_cluster" not in valuation_warnings:
                    valuation_warnings.append("insider_sell_cluster")
                insider_sell_cluster_firing_count += 1
            if detect_c_suite_unusual_sell(_form4_txns, asof_date):
                if "c_suite_unusual_sell" not in valuation_warnings:
                    valuation_warnings.append("c_suite_unusual_sell")
                c_suite_unusual_sell_firing_count += 1
            # PR 4-eq Rule 18 diagnostic — sum the count of transactions
            # excluded by the 10b5-1 filter (within the 30d cluster window
            # only) so the universe-wide contamination-eliminated metric
            # is visible on metadata.json for the Q3 cohort audit.
            form4_rule10b5_one_excluded_count += (
                count_10b5_1_filtered_transactions(_form4_txns, asof_date)
            )

        # Issue #67 — Rule 18 dual-count for sector-adjusted CoE delta.
        # We call check_rim_applicability twice — once with the flat 0.10
        # baseline and once with the per-sector Ke — so the universe-wide
        # delta is visible in Metadata on every cron regardless of the
        # USE_SECTOR_COE flag.  The per-ticker inputs (avg_3y_roe, tbvps,
        # lag_status) are already computed above; we just reuse them here.
        # This is a read-only measurement pass — no risk_flags or
        # valuation_warnings are modified by these calls.
        _hist_67 = historical_metrics.get(ticker, {})
        _avg_roe_67 = _hist_67.get("avg_3y_roe")
        _tbvps_67 = tangible_book_value_per_share(snap) if snap is not None else None
        _lag_67 = _filing_lag(snap, asof_date)
        _lag_status_67 = stale_filing_status(_lag_67)
        _rim_flat = check_rim_applicability(
            avg_3y_roe=_avg_roe_67,
            tbvps=_tbvps_67,
            lag_status=_lag_status_67,
            cost_of_equity=config.COST_OF_EQUITY,
        )
        if (
            not _rim_flat.applicable
            and _rim_flat.reason == "value_trap_risk_roe_below_cost_of_equity"
        ):
            value_trap_risk_count_without_sector_coe += 1
            value_trap_risk_count_without_sector_coe_by_sector[sector] = (
                value_trap_risk_count_without_sector_coe_by_sector.get(sector, 0) + 1
            )
        _rim_sector = check_rim_applicability(
            avg_3y_roe=_avg_roe_67,
            tbvps=_tbvps_67,
            lag_status=_lag_status_67,
            cost_of_equity=get_cost_of_equity(sector),
        )
        if (
            not _rim_sector.applicable
            and _rim_sector.reason == "value_trap_risk_roe_below_cost_of_equity"
        ):
            value_trap_risk_count_with_sector_coe += 1
            value_trap_risk_count_with_sector_coe_by_sector[sector] = (
                value_trap_risk_count_with_sector_coe_by_sector.get(sector, 0) + 1
            )

        # Price history JSON (sliced from already-fetched prices, no new
        # fetches per Step 5 spec).
        prices_df = prices_by_ticker.get(ticker)
        has_history = False
        if prices_df is not None:
            has_history = write_stock_history(
                ticker=ticker,
                prices_df=prices_df,
                output_dir=config.DATA_DIR,
            )
            if has_history:
                history_count += 1

        # PR 4d — recommendation tier (Option B locked: bullish / lean_bullish
        # / neutral / cautious). Deterministic derivation from composite +
        # risk_flags + valuation_warnings + MoS. See
        # `compute/scoring/recommendation.py` for the rubric.
        recommendation = derive_recommendation(
            composite_score=float(r["composite_score"]),
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
            mos_pct=ensemble.mos_pct if ensemble is not None else None,
        )

        # PR 4e — Loss Chance % heuristic (Option D locked: "Loss Chance %"
        # label + small italic "heuristic" qualifier in the UI). Pure
        # combiner over composite + risk_flags + valuation_warnings + MoS.
        # Returns None when MoS unavailable (no ensemble) — frontend
        # renders em-dash placeholder. See `compute/scoring/loss_chance.py`.
        loss_chance_pct = derive_loss_chance(
            composite_score=float(r["composite_score"]),
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
            mos_pct=ensemble.mos_pct if ensemble is not None else None,
        )

        # PR 4.5f — manipulation_index rollup + soft composite penalty.
        # Rank stays the raw composite per SKILL.md Rule 16 ("composite
        # rank unchanged"); composite_score_adjusted is informational.
        m_index = compute_manipulation_index(
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
        )
        composite_adj = compute_adjusted_composite(
            composite_score=float(r["composite_score"]),
            manipulation_index=m_index,
        )
        m_components = manipulation_components(
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
        )

        summaries.append(
            StockSummary(
                rank=int(r["rank"]),
                ticker=ticker,
                name=str(r["name"]),
                sector=sector,
                composite_score=round(float(r["composite_score"]), 2),
                current_price=round(current_price, 4),
                fair_price=ensemble.median if ensemble is not None else None,
                max_fair_price=ensemble.max if ensemble is not None else None,
                margin_of_safety_pct=ensemble.mos_pct if ensemble is not None else None,
                pillar_scores=_pillar_scores_to_schema(pillar_row),
                risk_flags=risk_flags.get(ticker, []),
                valuation_warnings=valuation_warnings,
                recommendation=recommendation,
                loss_chance_pct=loss_chance_pct,
                price_change_1d_pct=(
                    round(float(r["price_change_1d_pct"]), 4)
                    if r.get("price_change_1d_pct") is not None
                    and not math.isnan(float(r["price_change_1d_pct"]))
                    else None
                ),
                manipulation_index=m_index,
                composite_score_adjusted=composite_adj,
                entered_top5=ticker in entered,
                exited_top5=ticker in exited,
                # Phase 8 pilot PR 3a — index membership from cohort column.
                index_membership=cohort_by_ticker.get(ticker, "sp500"),
            )
        )

        raw_metrics = _build_raw_metrics(snap, current_price)
        imputed = imputed_by_ticker.get(ticker, [])
        tier2_result = tier2_results.get(ticker)
        tier2_dict = tier2_events_dict(tier2_result) if tier2_result is not None else None
        detail = StockDetail(
            ticker=ticker,
            name=str(r["name"]),
            sector=sector,
            industry=sub_industry,
            exchange=exchange_by_ticker.get(ticker),
            country=country_by_ticker.get(ticker),
            market_cap=raw_metrics.market_cap,
            current_price=round(current_price, 4),
            rank=int(r["rank"]),
            composite_score=round(float(r["composite_score"]), 2),
            pillar_scores=_pillar_scores_to_schema(pillar_row),
            raw_metrics=raw_metrics,
            fair_price=ensemble_dict,
            data_quality=_build_data_quality(snap, now, imputed),
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
            has_history=has_history,
            tangible_book_value=tbvps_value,
            tier2_events=tier2_dict,
            pillar_baseline=sector_pillar_baselines.get(sector),
            beneish_m_score=beneish_result.m_score,
            dechow_f_score=dechow_result.f_score,
            recommendation=recommendation,
            loss_chance_pct=loss_chance_pct,
            price_change_1d_pct=(
                round(float(r["price_change_1d_pct"]), 4)
                if r.get("price_change_1d_pct") is not None
                and not math.isnan(float(r["price_change_1d_pct"]))
                else None
            ),
            manipulation_index=m_index,
            composite_score_adjusted=composite_adj,
            manipulation_components=m_components,
            valuation_methods_applicable=(
                ensemble.valuation_methods_applicable if ensemble is not None else None
            ),
            osap_signals=osap_signal_map.get(ticker),
            osap_blended_score=(
                round(float(composite_osap_adjusted[ticker]), 2)
                if ticker in composite_osap_adjusted.index
                and not pd.isna(composite_osap_adjusted[ticker])
                else None
            ),
            entered_top5=ticker in entered,
            exited_top5=ticker in exited,
            # Phase 8 pilot PR 3a — index membership from cohort column.
            index_membership=cohort_by_ticker.get(ticker, "sp500"),
            form4_diagnostics=form4_diagnostics.get(ticker),
            cross_source_delta=cross_source_delta_by_ticker.get(ticker),
        )
        write_stock_detail(detail, config.DATA_DIR)
        detail_count += 1

    # Issue #287 PR A — wall-clock end marker for Step 8 (cross_source umbrella).
    cross_source_wall_clock_seconds = round(
        time.monotonic() - _cross_source_wc_start, 1
    )
    logger.info(
        "Wrote %d stock detail JSON files; %d with fair_price; %d with price history; "
        "Step 8 wall_clock=%ss",
        detail_count,
        fair_price_count,
        history_count,
        cross_source_wall_clock_seconds,
    )

    # Step 9 — sanity smoke test (Phase 3c Step 8). Cross-sectional Spearman
    # rank corr between margin_of_safety_pct and trailing 1y return. NOT a
    # backtest — see compute/scoring/sanity.py docstring.
    mos_ic = compute_mos_trailing_ic(
        rankings=summaries,
        prices_by_ticker=prices_by_ticker,
    )
    logger.info("MoS trailing IC smoke: %s", mos_ic)

    # Issue #246 PR2a (0.10.3-phase4.5e) — read the universe-wide
    # shares-fallback counters that accumulated inside
    # ``_build_snapshot`` calls during the threaded fundamentals fetch
    # loop. Lock acquired by ``get_fallback_stats()`` so this returns a
    # consistent snapshot even if the loop is somehow still running.
    shares_fallback_stats = get_shares_fallback_stats()
    shares_fallback_triggered_count = shares_fallback_stats["triggered"]
    shares_fallback_too_low_count = shares_fallback_stats["too_low"]
    shares_fallback_dimensional_override_count = shares_fallback_stats[
        "dimensional_override"
    ]
    logger.info(
        "shares_outstanding fallback summary: triggered=%d, of which too_low=%d, "
        "dimensional_override=%d",
        shares_fallback_triggered_count,
        shares_fallback_too_low_count,
        shares_fallback_dimensional_override_count,
    )

    # PR-A2 — Rule 18 observability: exchange-resolution coverage across the
    # universe (display-only fields). Watch this for >= 1 cron before PR-B
    # wires the frontend country/exchange chips (observability-before-wiring).
    # country_coverage_pct (0.10.13-phase4.6) is the strict-resolution sibling:
    # exchange counts passthrough codes as covered, country does not, so a gap
    # between them flags an unknown venue code (the CBOE/BTS canary).
    n_with_exchange = sum(1 for v in exchange_by_ticker.values() if v is not None)
    exchange_coverage_pct = _coverage_pct(exchange_by_ticker)
    country_coverage_pct = _coverage_pct(country_by_ticker)
    n_with_country = sum(1 for v in country_by_ticker.values() if v is not None)
    logger.info(
        "Exchange coverage: %d / %d (%.1f%%) | Country coverage: %d / %d (%.1f%%)",
        n_with_exchange,
        len(exchange_by_ticker),
        exchange_coverage_pct if exchange_coverage_pct is not None else 0.0,
        n_with_country,
        len(country_by_ticker),
        country_coverage_pct if country_coverage_pct is not None else 0.0,
    )
    if (
        exchange_coverage_pct is not None
        and country_coverage_pct is not None
        and country_coverage_pct < exchange_coverage_pct
    ):
        # Divergence = an exchange code resolved to a display name but not to a
        # US country tag (unknown venue passthrough). Surfaces the next CBOE/BTS
        # before it reaches a user as a flagless raw-code chip.
        logger.warning(
            "Listing-metadata coverage divergence: country %.2f%% < exchange "
            "%.2f%% — an unknown exchange code passed through without a country "
            "tag (add it to _EXCHANGE_NAME_BY_CODE in cross_source.py)",
            country_coverage_pct,
            exchange_coverage_pct,
        )

    # Issue #75 §3 — IC-decay monitor (Rule 18 observability-before-wiring).
    # Reads git-committed prior rankings (the current run is NOT committed
    # yet — correct; this is a backward-looking monitor). Always emits the
    # artifact even when status="insufficient_history" so the static
    # frontend build always has the file. Wrapped in try/except so any
    # git/network/data failure NEVER blocks the cron; degrades to
    # decay_report_url=None. Skip-safe via QR_SKIP_DECAY_MONITOR=1.
    decay_report_url: str | None = None
    _decay_report_path = config.DATA_DIR / "decay_report.json"
    if os.environ.get("QR_SKIP_DECAY_MONITOR", "").lower() in ("1", "true", "yes"):
        logger.info(
            "IC-decay monitor SKIPPED via QR_SKIP_DECAY_MONITOR. "
            "decay_report_url will be None."
        )
    else:
        try:
            from compute.validation.ic_decay import (
                IC_DECAY_DURATION_MONTHS,
                IC_DECAY_THRESHOLD,
                IC_HORIZON_MONTHS,
                MIN_HISTORY_MONTHS,
                build_decay_report,
                emit_decay_report,
            )

            _decay_reports, _decay_status, _decay_n_dates = build_decay_report()
            emit_decay_report(
                _decay_reports,
                _decay_report_path,
                threshold=IC_DECAY_THRESHOLD,
                duration_months=IC_DECAY_DURATION_MONTHS,
                horizon_months=IC_HORIZON_MONTHS,
                min_history_months=MIN_HISTORY_MONTHS,
                status=_decay_status,
                n_dates_with_ic=_decay_n_dates,
            )
            decay_report_url = "/data/decay_report.json"
            logger.info(
                "IC-decay monitor: status=%s, n_dates_with_ic=%d, "
                "alerted=%s, written to %s",
                _decay_status,
                _decay_n_dates,
                [r.pillar for r in _decay_reports if r.alert],
                _decay_report_path,
            )
        except Exception as _decay_exc:  # noqa: BLE001
            logger.warning(
                "IC-decay monitor failed (non-fatal — cron continues); "
                "decay_report_url → None. Error: %s",
                _decay_exc,
            )
            decay_report_url = None

    meta = Metadata(
        version=config.SCHEMA_VERSION,
        last_update_utc=_iso(now),
        next_update_utc=_iso(now + timedelta(days=_next_business_day_offset(now))),
        # Phase 8 pilot PR 3a — universe label: "SP900" when ranked output
        # covers the full S&P 900; "SP500" on the default cron path.
        universe="SP900" if config.QR_UNIVERSE == "sp900" else config.UNIVERSE,
        universe_size=len(summaries),
        # Phase 7.0 PR-1 — benchmark index export coverage (Rule 18 observability).
        benchmark_coverage_pct=benchmark_coverage_pct,
        # Phase 4.6 (0.10.7-phase4.6) — survivorship-bias provenance per
        # Research Report v1.0 §7.4. Forward cron's as-of is today, and
        # the universe we just scored IS today's current S&P 500 — so
        # the lookup is honest by definition. survivorship_bias_corrected
        # = True signals "this output's universe assumption is honest for
        # its as_of_date" (vs False = historical query that fell back to
        # current). Backtest / validation callers populate these from
        # ``compute.ingest.historical_universe.members_at()`` directly.
        universe_membership_as_of=now.date().isoformat(),
        survivorship_bias_corrected=True,
        compute_run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        git_commit=(os.environ.get("GITHUB_SHA") or "unknown")[:40],
        mos_trailing_ic_smoke=mos_ic,
        tier2_coverage_pct=tier2_coverage,
        fundamentals_coverage_pct=fundamentals_coverage_pct,
        fundamentals_latency_p50_seconds=(
            round(fundamentals_p50, 2) if fundamentals_p50 is not None else None
        ),
        fundamentals_latency_p95_seconds=(
            round(fundamentals_p95, 2) if fundamentals_p95 is not None else None
        ),
        osap_signals_used=osap_signals_used or None,
        osap_excluded_signals=osap_excluded_signals or None,
        osap_signals_ic_12m=osap_signals_ic_12m or None,
        osap_signals_coverage_pct=osap_signals_coverage_pct or None,
        osap_signals_missing_from_dataset=(
            osap_signals_missing_from_dataset or None
        ),
        osap_gate_diagnostics=osap_gate_diagnostics or None,
        osap_signals_dropped_no_long_short=(
            osap_signals_dropped_no_long_short_list or None
        ),
        # Phase 4j.1 (0.10.15-phase4.6) — Qlib Alpha158 observability surface
        # (no blend; composite_score unchanged). `x or None` so the
        # graceful-degradation path (empty list/dict) serializes as None.
        # Coverage / survivorship / wall-clock pass through directly (they
        # are already None on the degraded path).
        alpha158_features_used=alpha158_features_used or None,
        alpha158_excluded_features=alpha158_excluded_features or None,
        alpha158_features_ic_12m=alpha158_features_ic_12m or None,
        alpha158_features_missing_from_compute=(
            alpha158_features_missing_from_compute or None
        ),
        alpha158_features_dropped_no_long_short=(
            alpha158_features_dropped_no_long_short_list or None
        ),
        alpha158_gate_diagnostics=alpha158_gate_diagnostics or None,
        alpha158_coverage_pct=alpha158_coverage_pct,
        alpha158_survivorship_bias_corrected=alpha158_survivorship_bias_corrected,
        alpha158_wall_clock_seconds=alpha158_wall_clock_seconds,
        tier2_enabled=_EIGHT_K_DEFENSES_ENABLED,
        loss_avoidance_size_invariant_firing_count=(
            loss_avoidance_size_invariant_firing_count
        ),
        share_count_extraction_missing_count=(
            share_count_extraction_missing_count
        ),
        extreme_estimate_majority_count=(
            extreme_estimate_majority_count
        ),
        insider_sell_cluster_firing_count=(
            insider_sell_cluster_firing_count
        ),
        c_suite_unusual_sell_firing_count=(
            c_suite_unusual_sell_firing_count
        ),
        form4_rule10b5_one_excluded_count=(
            form4_rule10b5_one_excluded_count
        ),
        sector_coe_enabled=config.USE_SECTOR_COE,
        value_trap_risk_count_without_sector_coe=(
            value_trap_risk_count_without_sector_coe
        ),
        value_trap_risk_count_with_sector_coe=(
            value_trap_risk_count_with_sector_coe
        ),
        # Issue #67 follow-up (0.10.10-phase4.6) — per-sector delta.
        # `delta[sector] = without - with` so positive means sector dropped
        # flags after sector-CoE flip (gained leniency per lower Ke);
        # negative means sector gained flags (stricter per higher Ke).
        # Universe of keys = union of both dicts (sectors with zero firings
        # in either path are omitted to keep the dict small; sectors with
        # zero delta after both paths fire are included as 0 for explicit
        # parity signal).
        value_trap_risk_delta_by_sector={
            _sec: (
                value_trap_risk_count_without_sector_coe_by_sector.get(_sec, 0)
                - value_trap_risk_count_with_sector_coe_by_sector.get(_sec, 0)
            )
            for _sec in sorted(
                set(value_trap_risk_count_without_sector_coe_by_sector)
                | set(value_trap_risk_count_with_sector_coe_by_sector)
            )
        } or None,
        cross_source_disagreement_count=cross_source_disagreement_count,
        cross_source_delta_histogram=cross_source_delta_histogram,
        exchange_coverage_pct=exchange_coverage_pct,
        country_coverage_pct=country_coverage_pct,
        shares_fallback_triggered_count=shares_fallback_triggered_count,
        shares_fallback_too_low_count=shares_fallback_too_low_count,
        shares_fallback_dimensional_override_count=(
            shares_fallback_dimensional_override_count
        ),
        multi_class_aggregate_shares_suspected_count=(
            multi_class_aggregate_shares_suspected_count
        ),
        multi_class_per_class_override_count=(
            shares_fallback_stats.get("per_class_override")
        ),
        multi_class_per_class_attempt_count=(
            shares_fallback_stats.get("per_class_attempt")
        ),
        multi_class_mc_reconcile_failure_count=(
            shares_fallback_stats.get("mc_reconcile_failure")
        ),
        form4_enabled=False,
        form4_coverage_pct=(
            round(
                100.0
                * (len(form4_diagnostics) - len(form4_failures))
                / max(len(form4_diagnostics), 1),
                2,
            )
            if form4_diagnostics
            else None
        ),
        form4_fetch_latency_p50_seconds=(
            round(float(np.median(form4_latencies)), 2)
            if form4_latencies
            else None
        ),
        form4_fetch_latency_p95_seconds=(
            round(float(np.percentile(form4_latencies, 95)), 2)
            if form4_latencies
            else None
        ),
        form4_universe_insider_count_median=(
            int(np.median([d["insider_count"] for d in form4_diagnostics.values()]))
            if form4_diagnostics
            else None
        ),
        form4_tickers_with_recent_activity=(
            sum(
                1
                for d in form4_diagnostics.values()
                if d.get("insider_count", 0) > 0
            )
            if form4_diagnostics
            else None
        ),
        form4_fetch_failures=(
            sorted(form4_failures)[:20] if form4_failures else None
        ),
        # Issue #287 PR A — per-loop wall-clock observability.
        tier2_wall_clock_seconds=tier2_wall_clock_seconds,
        form4_wall_clock_seconds=form4_wall_clock_seconds,
        osap_wall_clock_seconds=osap_wall_clock_seconds,
        cross_source_wall_clock_seconds=cross_source_wall_clock_seconds,
        # PR 6 — negation-guard downgrade count (footgun #1 residual).
        # Gates Q3 2026-08-19 cohort-acceptance check for INSIDER_SELL_CLUSTER_WEIGHT
        # 5.0 → 7.0 promotion alongside form4_rule10b5_one_excluded_count.
        form4_negation_guard_downgrade_count=form4_negation_guard_downgrade_count,
        # Issue #75 §3 — IC-decay monitor artifact URL (Rule 18).
        decay_report_url=decay_report_url,
        # Phase 8 pilot PR 3a — cohort-size diagnostics (Rule 18).
        # Populated on the scored sp900 path (probe reuses the live universe frame).
        # None on the default sp500 path.
        universe_cohort_sizes=_pilot_cohort_sizes or None,
        midcap_fundamentals_coverage_pct=_pilot_midcap_coverage_pct,
        midcap_null_rate_pct=_pilot_midcap_null_rate_pct,
        midcap_cik_resolution_pct=_pilot_midcap_cik_resolution_pct,
    )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_rankings_json(summaries, config.DATA_DIR)
    write_metadata_json(meta, config.DATA_DIR)
    # Remove per-stock files for tickers dropped from the universe (e.g. an
    # index de-listing). The cron's `git add frontend/public/data/` stages the
    # deletions; guarded by a safety floor so a degraded run can't wipe stocks/.
    prune_orphan_stock_files((s.ticker for s in summaries), config.DATA_DIR)
    logger.info("Wrote rankings.json (%d rows) and metadata.json", len(summaries))

    # Best-effort RSS memory log (psutil is not a hard requirement; production
    # still runs without it).
    try:
        import psutil  # type: ignore[import-not-found]

        rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        logger.info("Final RSS memory: %.1f MB", rss_mb)
    except ImportError:
        logger.debug("psutil not installed — skipping RSS memory log")
    except Exception as e:  # noqa: BLE001
        logger.debug("psutil RSS log failed: %s", e)

    return len(summaries)


if __name__ == "__main__":
    sys.exit(0 if run_weekly_compute() > 0 else 1)
