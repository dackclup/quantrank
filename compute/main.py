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
from compute.features.osap_replicate import (
    compute_long_short_returns,
    compute_osap_signals,
    coverage_by_signal,
    signals_dropped_no_long_short,
    signals_in_dataframe,
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
from compute.ingest.osap import fetch_osap_returns
from compute.ingest.prices import fetch_prices, fetch_spy_benchmark
from compute.ingest.universe import get_sp500_constituents
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
    read_previous_top5,
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
from compute.scoring.dechow_f import DechowResult, compute_dechow_f
from compute.scoring.earnings_quality import (
    check_accruals_momentum,
    check_loss_avoidance,
)
from compute.scoring.loss_chance import derive_loss_chance
from compute.scoring.manipulation_index import (
    compute_adjusted_composite,
    compute_manipulation_index,
    manipulation_components,
)
from compute.scoring.osap_blend import aggregate_osap_signals, apply_osap_blend
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.recommendation import derive_recommendation
from compute.scoring.rem import compute_rem_flags
from compute.scoring.restatement_filings import (
    check_late_filing,
    check_restatement_history,
)
from compute.scoring.risk_overlay import compute_risk_flags
from compute.scoring.sanity import compute_mos_trailing_ic
from compute.scoring.tier2 import (
    Tier2Result,
    fetch_tier2_for_ticker,
    tier2_events_dict,
)
from compute.scoring.tier2 import (
    coverage_pct as tier2_coverage_pct_calc,
)
from compute.validation.osap_validation import (
    compute_rolling_ic_12m,
    filter_accepted_signals,
    gate_osap_signals,
)
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
    if (
        snapshot.net_income is not None
        and snapshot.net_income > 0
        and snapshot.shares_outstanding is not None
        and snapshot.shares_outstanding > 0
        and current_price > 0
    ):
        ttm_eps = snapshot.net_income / snapshot.shares_outstanding
        if ttm_eps > 0:
            pe_ttm = current_price / ttm_eps
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
        eps_basic=snapshot.eps_basic,
        eps_diluted=snapshot.eps_diluted,
        shares_outstanding=snapshot.shares_outstanding,
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

    PR 4c (issue #11): previously this function used the **current**
    snapshot's equity as denominator for all 3 years' net income —
    "smoothed-NI / latest-equity". For a firm whose equity grew 30%
    over 3 years (typical growers + dividend-paying staples), this
    biased ROE **downward** by ~15%, which over-fired
    ``value_trap_risk_roe_below_cost_of_equity`` on 44% of the S&P 500
    universe.

    The fix: require ``stockholders_equity`` to be present in the
    annual history alongside ``net_income``, and average per-year ROE
    (= per-year NI / per-year equity) across the 3 most recent
    fiscal years.

    Fallback: if the annual history lacks 3 years of equity (older
    filers, recent IPOs), we fall back to the prior behavior — mean
    NI / current equity — so the RIM applicability gate still has an
    input. The fallback path is logged at debug level so the count
    can be tracked across runs.
    """
    if hist is None or len(hist) == 0 or "metric" not in hist.columns:
        return None
    if snap is None or snap.stockholders_equity in (None, 0):
        return None
    current_equity = float(snap.stockholders_equity)
    if current_equity <= 0:
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

    # Per-year ROE path (PR 4c primary).
    eq_rows = hist[hist["metric"] == "stockholders_equity"].sort_values(
        "fiscal_year", ascending=False
    )
    if not eq_rows.empty:
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
                per_year_roe = []
                break
            per_year_roe.append(float(ni_row["value"]) / eq_f)
        if len(per_year_roe) == 3:
            return float(sum(per_year_roe) / 3.0)

    # Fallback: legacy single-period-equity denominator. Triggers when
    # the annual history is missing equity for one of the 3 fiscal
    # years (recent IPOs, off-cycle filers, audit #6 residual gaps).
    avg_ni = float(sum(ni_values) / 3.0)
    return avg_ni / current_equity


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

    logger.info("Loading S&P 500 universe…")
    universe = get_sp500_constituents()
    logger.info("Universe size: %d", len(universe))

    logger.info("Fetching SPY benchmark for beta…")
    benchmark = fetch_spy_benchmark()
    if benchmark is None or benchmark.empty:
        logger.warning("SPY benchmark unavailable — beta will be NaN for all tickers")
        benchmark = None

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
    tier2_coverage = tier2_coverage_pct_calc(tier2_results)
    logger.info(
        "Tier-2 coverage: %s%% (gc=%d, nr=%d, ac=%d)",
        tier2_coverage if tier2_coverage is not None else "n/a",
        sum(1 for r in tier2_results.values() if r.going_concern_disclosure),
        sum(1 for r in tier2_results.values() if r.non_reliance_flag.fired),
        sum(1 for r in tier2_results.values() if r.auditor_change_flag.fired),
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

    now = _now_utc()
    asof_date = now.date()

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
    try:
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

    # Step 8 — combined per-ticker loop: fair-price ensemble + price history
    # write + StockSummary + StockDetail. Single pass so per-ticker outputs
    # stay synchronized (e.g., has_history reflects the actual write result;
    # ensemble warnings flow into both summary and detail consistently).
    summaries: list[StockSummary] = []
    detail_count = 0
    history_count = 0
    fair_price_count = 0
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

        # Cross-source market-cap validator (PR 4b §1, ANNOTATE-only).
        # Compares SEC-derived market cap (shares × current_price) vs
        # yfinance .info marketCap. Delta > 5% surfaces as
        # ``cross_source_disagreement``. Catches yfinance scraper drift
        # (pre-split share counts, intraday vs EOD price snapshots, M&A
        # ticker rotation). See compute/ingest/cross_source.py +
        # `.claude/skills/phase-4/defense-infrastructure/PLAN.md` §1.
        if cross_source_validate_market_cap(
            ticker=ticker,
            snap=snap,
            current_price=current_price,
        ) and "cross_source_disagreement" not in valuation_warnings:
            valuation_warnings.append("cross_source_disagreement")

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
        # fiscal years of tiny-positive NI (∈ [0, $5M]) OR tiny-
        # positive EPS (∈ [0, $0.05]) = managers shading reported
        # earnings just enough to clear the loss threshold.
        loss_avoid = check_loss_avoidance(snap, histories.get(ticker))
        if (
            loss_avoid.fired
            and "loss_avoidance_pattern" not in valuation_warnings
        ):
            valuation_warnings.append("loss_avoidance_pattern")

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
            osap_signals=osap_signal_map.get(ticker),
            osap_blended_score=(
                round(float(composite_osap_adjusted[ticker]), 2)
                if ticker in composite_osap_adjusted.index
                and not pd.isna(composite_osap_adjusted[ticker])
                else None
            ),
            entered_top5=ticker in entered,
            exited_top5=ticker in exited,
        )
        write_stock_detail(detail, config.DATA_DIR)
        detail_count += 1

    logger.info(
        "Wrote %d stock detail JSON files; %d with fair_price; %d with price history",
        detail_count,
        fair_price_count,
        history_count,
    )

    # Step 9 — sanity smoke test (Phase 3c Step 8). Cross-sectional Spearman
    # rank corr between margin_of_safety_pct and trailing 1y return. NOT a
    # backtest — see compute/scoring/sanity.py docstring.
    mos_ic = compute_mos_trailing_ic(
        rankings=summaries,
        prices_by_ticker=prices_by_ticker,
    )
    logger.info("MoS trailing IC smoke: %s", mos_ic)

    meta = Metadata(
        version=config.SCHEMA_VERSION,
        last_update_utc=_iso(now),
        next_update_utc=_iso(now + timedelta(days=_next_business_day_offset(now))),
        universe=config.UNIVERSE,
        universe_size=len(summaries),
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
    )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_rankings_json(summaries, config.DATA_DIR)
    write_metadata_json(meta, config.DATA_DIR)
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
