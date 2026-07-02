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
    (ANY active veto in ``risk_flags`` — the 10 ``KNOWN_RISK_FLAGS``,
    e.g. altman / sloan / NSI / data-quality / beneish / dechow /
    non-reliance / fundamentals-unavailable / post-split-unreconciled /
    stale-filing-hard) cannot earn ``entered_top5``. NB: this Top-5 gate
    (``if risk_flags.get(ticker): continue``) is BROADER than the 7-flag
    AI-pick-basket gate (``ACTIVE_VETO_FLAGS``) and the 4-flag cautious-label
    gate (``_CAUTIOUS_FORCING_RISK``) — three distinct sets, by design
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
    fetch_yfinance_market_cap,
    fetch_yfinance_shares_outstanding,
)
from compute.ingest.fundamentals import (
    FundamentalsSnapshot,
    fetch_fundamentals,
    fetch_fundamentals_history,
)
from compute.ingest.fundamentals import (
    get_filing_precheck_skip_count as get_fundamentals_filing_precheck_skip_count,
)
from compute.ingest.fundamentals import (
    reset_filing_precheck_skip_count as reset_fundamentals_filing_precheck_skip_count,
)
from compute.ingest.prices import (
    fetch_benchmarks,
    fetch_spy_benchmark,
)
from compute.ingest.universe import (
    fetch_dow30_constituents,
    fetch_ndx_constituents,
    get_sp500_constituents,
    get_sp900_constituents,
    get_sp1500_constituents,
)
from compute.orchestrator import ComputeState
from compute.orchestrator.form4 import fetch_all_form4
from compute.orchestrator.fundamentals import fetch_all_fundamentals
from compute.orchestrator.osap import run_osap_pipeline
from compute.orchestrator.per_ticker import (
    build_ticker_membership_maps,
    run_per_ticker_loop,
)
from compute.orchestrator.prices import fetch_all_prices
from compute.orchestrator.tier2 import fetch_all_tier2
from compute.output.schemas import (
    Metadata,
    OsapGateDiagnostic,
    RawMetrics,
    StockSummary,
)
from compute.output.writer import (
    prune_orphan_stock_files,
    read_previous_top5,
    write_benchmarks_json,
    write_metadata_json,
    write_rankings_json,
)
from compute.portfolio.weights import (
    HIGH_CONVICTION_COMPOSITE_MIN,
    HIGH_CONVICTION_RECOMMENDATIONS,
    PickCandidate,
    is_eligible,
    is_high_conviction,
)
from compute.scoring.beneish import BeneishResult, compute_beneish
from compute.scoring.bonferroni_shadow import compute_bonferroni_shadow
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
from compute.scoring.dechow_f import DechowResult, compute_dechow_f
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.regime import compute_market_regime
from compute.scoring.rem import compute_rem_flags
from compute.scoring.risk_overlay import (
    PostSplitResult,
    check_post_split_share_lag,
    compute_cross_source_corruption_shadow,
    compute_risk_flags,
)
from compute.scoring.sanity import compute_mos_trailing_ic
from compute.scoring.tier2 import _EIGHT_K_DEFENSES_ENABLED
from compute.scoring.tier2 import (
    coverage_pct as tier2_coverage_pct_calc,
)
from compute.valuation.applicability import stale_filing_status

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


def _passes_ex_loss_chance(c: PickCandidate) -> bool:
    """HC gate with the loss_chance leg (leg 5) REMOVED — legs 1-4 only.

    This is the marginal-bite denominator: names passing legs 1-4 but failing
    leg 5 are the ones the loss-chance filter actually removes.  Reuses the
    live constants from ``compute.portfolio.weights`` (not inlined literals).

    Fail-closed on None inputs for legs 1-3 (same as ``is_high_conviction``);
    ``loss_chance_pct`` is NEITHER required NOR fail-closed here — that is the
    point.
    """
    # leg 1 — no active rank-gate veto
    if not is_eligible(c.risk_flags):
        return False
    # leg 2 — bullish or lean_bullish
    if c.recommendation not in HIGH_CONVICTION_RECOMMENDATIONS:
        return False
    # leg 3 — strict undervaluation (Graham-Dodd; fail-closed on None)
    if c.mos_pct is None or c.mos_pct <= 0.0:
        return False
    # leg 4 — minimum composite quality bar (fail-closed on None implicitly
    # since composite_score is float, not Optional; PickCandidate constructor
    # ensures it is always set)
    if c.composite_score < HIGH_CONVICTION_COMPOSITE_MIN:
        return False
    # leg 5 (loss_chance ≤ 45) deliberately omitted — this is the instrument
    return True


def _count_high_conviction(
    summaries: list[StockSummary],
) -> tuple[int, int]:
    """Count stocks clearing the high-conviction gate in the ranked universe.

    This is **purely additive observability** — it NEVER mutates summaries,
    changes the composite, influences selection, or touches the defense layer.
    The gate (``is_high_conviction``) is already the production selection driver
    in the backfill; this helper measures the marginal bite of its loss-chance
    leg on today's cron snapshot.

    Returns
    -------
    (high_conviction_count, high_conviction_ex_loss_chance_count)

    ``high_conviction_count``
        Full-gate pass count: clears all 5 legs (is_eligible + rec ∈
        {bullish, lean_bullish} + MoS > 0 + composite ≥ 50 + loss_chance ≤ 45).

    ``high_conviction_ex_loss_chance_count``
        Count passing legs 1-4 only (loss-chance leg omitted).  By construction
        ex_loss_chance_count ≥ high_conviction_count always.  The marginal-bite
        of leg 5 is:
          bite = high_conviction_ex_loss_chance_count − high_conviction_count
        A materially positive bite across crons means leg 5 is doing real work.
        A bite ≈ 0 across crons means leg 5 is redundant (drop candidate).

    Methodology citation (C-1 RATIFY-WITH-CONDITION 2026-06-26):
        Gate-flip pre-registration: hc_count ≥ ADAPTIVE_MIN_PICKS + 2 (≥ 7)
        across ALL crons AND ALL rebalance legs, AND the marginal-bite read
        (ex_loss_chance_count − hc_count) resolves whether to keep
        loss_chance ≤ 45 (bites) or drop the leg (≈ 0).  NOT a bare
        below_floor gate.  Issue #130.
    """
    hc_count = 0
    ex_loss_chance_count = 0
    for s in summaries:
        c = PickCandidate(
            ticker=s.ticker,
            composite_score=s.composite_score,
            sector=s.sector,
            risk_flags=tuple(s.risk_flags),
            recommendation=s.recommendation,
            mos_pct=s.margin_of_safety_pct,
            loss_chance_pct=s.loss_chance_pct,
        )
        if is_high_conviction(c):
            hc_count += 1
        if _passes_ex_loss_chance(c):
            ex_loss_chance_count += 1
    return hc_count, ex_loss_chance_count


def _count_restatement_demote_delta(summaries: list[StockSummary]) -> int:
    """Count summaries whose valuation_warnings carry the bare-restater pattern.

    "Bare restater" = ``restatement_history`` present **and**
    ``restatement_high_confidence`` absent.  These are the tickers whose
    manipulation-index contribution drops 5.0→0.0 under the weight demotion
    (``RESTATEMENT_HISTORY_WEIGHT 5.0→0.0``).  Tickers carrying *both* flags
    (the irregularity subset) net zero delta because
    ``RESTATEMENT_HIGH_CONFIDENCE_WEIGHT`` rose 3.0→8.0 to compensate.

    Returns
    -------
    int
        Count of summaries matching the bare-restater predicate.

    Notes
    -----
    OBSERVABILITY-ONLY (issue #16) — never reads or mutates scores, composite,
    pillar logic, veto/flag, fair-price, or ``select_picks``.  Defense layer
    UNCHANGED at 36.  Pure function — no I/O, no side-effects.  The caller
    wraps in ``try/except → None`` so failures never block the cron.
    """
    return sum(
        1
        for _s in summaries
        if "restatement_history" in set(_s.valuation_warnings)
        and "restatement_high_confidence" not in set(_s.valuation_warnings)
    )


# Per-stock fundamentals fetch ceiling. Belt-and-suspenders for the
# tightened tenacity retry (stop_after_delay(30) | stop_after_attempt(2))
# in compute/ingest/fundamentals.py. Defends the orchestrator against a
# truly stuck task (e.g., SEC's HTTP layer hanging mid-stream past the
# inner retry's wall-clock cap).
_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS = 45


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
    snapshot: FundamentalsSnapshot | None,
    current_price: float,
    *,
    shares_outstanding_pre_split_raw: float | None = None,
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
        # Post-split share-lag defense (defense layer 35, 0.10.25-phase8pilot).
        # Populated only on Tier-1 correction; None on all other tickers.
        shares_outstanding_pre_split_raw=shares_outstanding_pre_split_raw,
        market_cap=market_cap,
        pe_ratio_ttm=pe_ttm,
        goodwill=snapshot.goodwill,
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


def _coverage_pct(by_ticker: dict[str, object | None]) -> float | None:
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


def _run_smallcap_coverage_probe(
    sp1500_df: pd.DataFrame,
) -> tuple[float | None, float | None, float | None, dict[str, int]]:
    """Diagnostic-only coverage probe over the S&P 600 small-cap cohort.

    S&P 1500 cutover Slice 2 (Rule 18 observability-before-wiring). This
    probe is the sp600 sibling of ``_run_midcap_coverage_probe``. It:
      - iterates only over the ``sp600`` rows of ``sp1500_df``
      - calls ``fetch_fundamentals`` on each ticker (reusing the production
        tenacity / cache layer — no new retry policy needed)
      - counts non-null snapshots (= GAAP coverage) vs nulls
      - does NOT feed ``summaries``, the writer, or any scoring path
      - returns (coverage_pct, null_rate_pct, cik_resolution_pct, cohort_sizes)

    Ranked output is BYTE-IDENTICAL whether or not this probe ran. The probe
    runs in the main thread (sequential) to avoid blowing through the EDGAR
    10 req/s ceiling on top of the ~900 fundamentals fetches already done.

    An empty sp600 cohort (e.g. ``fetch_sp600_constituents`` degraded) returns
    (None, None, None, cohort_sizes) — graceful degradation, cron-safe.

    Returns (None, None, None, {}) on any unexpected failure so the outer
    Metadata population still proceeds cleanly.
    """
    try:
        cohort_sizes: dict[str, int] = {}
        for cohort_label in ("sp500", "sp400", "sp600"):
            mask = sp1500_df["cohort"] == cohort_label
            cohort_sizes[cohort_label] = int(mask.sum())

        smallcap_mask = sp1500_df["cohort"] == "sp600"
        smallcap_df = sp1500_df[smallcap_mask].reset_index(drop=True)
        total_smallcap = len(smallcap_df)

        if total_smallcap == 0:
            logger.warning(
                "[sp1500-probe] No sp600 tickers found in sp1500 DataFrame — "
                "probe skipped (fetch_sp600_constituents may have degraded)"
            )
            return None, None, None, cohort_sizes

        logger.info(
            "[sp1500-probe] Starting smallcap coverage probe: %d sp600 tickers "
            "(sequential, cache-safe)",
            total_smallcap,
        )

        # CIK resolution bookkeeping
        cik_resolved = 0
        for _, row in smallcap_df.iterrows():
            if row.get("cik") and str(row["cik"]).strip() not in ("", "None", "nan"):
                cik_resolved += 1
        cik_resolution_pct = round(100.0 * cik_resolved / total_smallcap, 2)
        logger.info(
            "[sp1500-probe] CIK resolution: %d / %d (%.1f%%)",
            cik_resolved,
            total_smallcap,
            cik_resolution_pct,
        )

        n_ok = 0
        n_null = 0
        for _, row in smallcap_df.iterrows():
            ticker = str(row["ticker"])
            cik_raw = row.get("cik")
            cik = (
                str(cik_raw).strip()
                if cik_raw and str(cik_raw).strip() not in ("", "None", "nan")
                else ""
            )
            try:
                snap = fetch_fundamentals(ticker, cik)
                if snap is not None:
                    n_ok += 1
                else:
                    n_null += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[sp1500-probe] fetch_fundamentals failed for %s: %s", ticker, exc
                )
                n_null += 1

        coverage_pct = round(100.0 * n_ok / total_smallcap, 2)
        null_rate_pct = round(100.0 * n_null / total_smallcap, 2)
        logger.info(
            "[sp1500-probe] Smallcap GAAP coverage: %d / %d = %.1f%% (null: %d = %.1f%%)",
            n_ok,
            total_smallcap,
            coverage_pct,
            n_null,
            null_rate_pct,
        )
        return coverage_pct, null_rate_pct, cik_resolution_pct, cohort_sizes

    except Exception as exc:  # noqa: BLE001
        logger.error("[sp1500-probe] Diagnostic probe failed unexpectedly: %s", exc)
        return None, None, None, {}


def _run_broad_universe_probe(
    prices_by_ticker: dict[str, pd.DataFrame],
    security_types_by_ticker: dict[str, str | None] | None = None,
) -> dict[str, int | float | None]:
    """Phase 9.1 — Broad Investable US universe coverage probe (Rule 18, obs-first).

    Fetches the Broad Investable US candidate pool from the disk cache / edgartools
    bundled parquet / live SEC JSON, then runs the price >= $5 AND ADV >= $5M
    investability screen against the ``prices_by_ticker`` dict already in memory
    from Step 1 (no extra network calls for prices).

    This function is DIAGNOSTIC ONLY.  It returns a dict suitable for unpacking
    into the ``Metadata`` constructor.  It does NOT modify any scored ticker data
    and MUST NEVER feed scoring, composite, pillar computation, veto/flag logic,
    fair-price, or ``select_picks``.  Rankings/scores/flags are BYTE-IDENTICAL
    whether or not this probe ran.  Defense layer is UNCHANGED at 36.

    HARD NAMING CONSTRAINT (legal/trademark, 2026-06-29):
        Call this universe "Broad Investable US" everywhere.  NEVER use the
        strings "Russell 3000", "Russell-3000-class", or "equivalent to Russell
        3000" in any field name, label, log line, comment, or user-visible string.

    Escape hatch: returns a dict of all-None values when
    ``QR_SKIP_BROAD_UNIVERSE=1`` is set (used in CI pre-merge simulations).

    Parameters
    ----------
    prices_by_ticker:
        The Step-1 price dict (ticker → OHLCV DataFrame) already in memory.
        The probe reuses it to avoid extra yfinance round-trips.
    security_types_by_ticker:
        Optional ticker → security_type mapping (from ``fetch_yfinance_security_type``
        / ``_QUOTE_TYPE_LABEL``).  Used to drop ETF/fund tickers that slipped
        through the name filter.  ``None`` = security-type filtering skipped
        (graceful degradation).

    Returns
    -------
    dict with keys matching the six ``Metadata.broad_universe_*`` fields.
    All values are ``None`` on failure or when the probe is skipped.
    """
    _empty: dict[str, int | float | None] = {
        "broad_universe_raw_count": None,
        "broad_universe_candidate_count": None,
        "broad_universe_screened_count": None,
        "broad_universe_price_fail_pct": None,
        "broad_universe_adv_fail_pct": None,
        "broad_universe_coverage_pct": None,
    }

    if os.environ.get(config.BROAD_UNIVERSE_SKIP_ENV_VAR, "").lower() in (
        "1", "true", "yes"
    ):
        logger.info(
            "[broad-universe-probe] Skipped via %s env-var.",
            config.BROAD_UNIVERSE_SKIP_ENV_VAR,
        )
        return _empty

    try:
        from compute.ingest.broad_universe import (  # noqa: PLC0415
            fetch_broad_universe_candidates,
            screen_broad_universe_investability,
        )

        logger.info(
            "[broad-universe-probe] Fetching Broad Investable US candidate pool "
            "(Rule 18 observability-before-wiring, Phase 9.1)…"
        )
        candidates = fetch_broad_universe_candidates()
        logger.info(
            "[broad-universe-probe] Candidate pool size: %d tickers",
            len(candidates),
        )

        result = screen_broad_universe_investability(
            candidates=candidates,
            prices_by_ticker=prices_by_ticker,
            security_types_by_ticker=security_types_by_ticker,
        )

        logger.info(
            "[broad-universe-probe] Complete: raw=%s candidates=%s screened=%s "
            "coverage=%.1f%% price_fail=%.1f%% adv_fail=%.1f%%",
            result.get("broad_universe_raw_count"),
            result.get("broad_universe_candidate_count"),
            result.get("broad_universe_screened_count"),
            result.get("broad_universe_coverage_pct") or 0.0,
            result.get("broad_universe_price_fail_pct") or 0.0,
            result.get("broad_universe_adv_fail_pct") or 0.0,
        )
        return result

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[broad-universe-probe] Probe failed unexpectedly (non-fatal): %s", exc
        )
        return _empty


def run_weekly_compute() -> int:
    """Run the full weekly compute. Returns the count of successfully scored tickers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # PR #259-R1 — per-run state container (FACADE-FIRST, byte-identical).
    # R1 seats the shares-fallback metrics; R2-R7 migrate more accumulators.
    state = ComputeState()

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

    # Universe selector seam.
    # QR_UNIVERSE=sp500 (default sp500 path): loads SP500 only; adds cohort="sp500"
    #   so the column exists unconditionally for index_membership propagation.
    # QR_UNIVERSE=sp900: loads the full SP900 frame (cohort column already present
    #   from get_sp900_constituents); all ~903 tickers are ranked. The midcap
    #   diagnostic probe reuses this frame — no second fetch. (PR 3a)
    # QR_UNIVERSE=sp1500 (Slice 7, cron-default flip — mirrors #492): loads the full
    #   SP1500 frame (sp500 + sp400 + sp600, de-duped). ALL ~1500 tickers are SCORED
    #   and ranked (sp600 small-caps are NOW included — the Slice-2 probe-only filter
    #   is lifted in this Slice). The smallcap diagnostic probe (Rule 18) still runs
    #   immediately after the frame is loaded so coverage data reaches Metadata before
    #   scoring proceeds. Metadata.universe emits "SP1500" (ranked), not "SP1500-probe".
    #   russell1000 proxy suppression for sp600 cohorts in derive_index_memberships
    #   stays in place — sp600 small-caps sit below the Russell 1000 cutoff.
    #   CRON DEFAULT: sp1500 (Slice 7 flip, 2026-06-20). Revert: change
    #   || 'sp1500' → || 'sp900' in compute-rankings.yml + precache-edgar.yml.
    # QR_UNIVERSE=broad_investable_us (Phase 9.3, DISPATCH-ONLY — manual
    #   workflow_dispatch, NEVER the scheduled cron default which stays sp1500):
    #   loads the ~6,883-name Broad Investable US candidate pool (SEC
    #   company_tickers.json + exchange/name/format exclusions, HARD NAMING:
    #   never "Russell 3000"), shaped into a universe frame with
    #   sector="Unknown" / cohort="broad" (candidates_to_universe_frame).
    #   Step 1 (below) fetches prices for the FULL candidate pool — NOT a
    #   restricted sp1500 dict — then the investability screen
    #   (price >= $5 AND trailing-30d ADV >= $5M, same floors as the
    #   Phase-9.1 probe) reduces to the ~3,545 survivors BEFORE fundamentals
    #   (Step 2) so EDGAR load stays bounded. Non-survivors are REMOVED from
    #   the peer set entirely (P1-G3 methodology gate) — they do NOT get a
    #   low_liquidity annotate (that annotate is for names that ARE ranked
    #   but trade thinly; broad-universe sub-floor names are never ranked).
    #   Metadata.universe emits "BROAD_INVESTABLE_US".
    #   P1-G4 RE-NORMALIZATION DISCLOSURE (methodology-REQUIRED): broadening
    #   the scored universe RE-BASES every cross-sectional percentile and
    #   sector median the 8-pillar composite uses — a score on this path is
    #   NOT comparable to the same ticker's sp1500-cron score. See
    #   ``compute/ingest/broad_universe.py`` module docstring + CLAUDE.md
    #   §Gotchas for the full caveat. Frontend disclaimer is Phase 9.4 scope
    #   (not this PR).
    logger.info("Loading universe… (QR_UNIVERSE=%s)", config.QR_UNIVERSE)
    _pilot_cohort_sizes: dict[str, int] | None = None
    _pilot_midcap_coverage_pct: float | None = None
    _pilot_midcap_null_rate_pct: float | None = None
    _pilot_midcap_cik_resolution_pct: float | None = None
    # Slice 2 smallcap probe variables — None on sp500/sp900 paths.
    _pilot_smallcap_coverage_pct: float | None = None
    _pilot_smallcap_null_rate_pct: float | None = None
    _pilot_smallcap_cik_resolution_pct: float | None = None
    # Phase 9.1 — Broad Investable US probe variables (Rule 18 observability,
    # initialized to None here; populated after Step 1 prices when the env-var
    # gate passes).  All six are None on any failure or skip path.
    _broad_universe_raw_count: int | None = None
    _broad_universe_candidate_count: int | None = None
    _broad_universe_screened_count: int | None = None
    _broad_universe_price_fail_pct: float | None = None
    _broad_universe_adv_fail_pct: float | None = None
    _broad_universe_coverage_pct: float | None = None
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
    elif config.QR_UNIVERSE == "sp1500":
        # S&P 1500 cutover — Slice 7 (cron-default flip, mirrors #492 sp500→sp900).
        #
        # The FULL sp1500 frame (sp500 + sp400 + sp600) is loaded. ALL ~1500 tickers
        # are scored and ranked — the Slice-2 probe-only sp600 filter is lifted here.
        # The smallcap coverage probe (Rule 18) still runs immediately so coverage
        # data reaches Metadata before scoring proceeds, but sp600 rows are no longer
        # dropped before Step 1 (prices).
        #
        # russell1000 proxy suppression for sp600 cohorts in derive_index_memberships
        # stays intact — sp600 small-caps are below the Russell 1000 cutoff so they
        # must NOT receive the russell1000 tag.  RUT (Russell 2000) would be correct
        # but requires a dedicated FTSE Russell source, not a market-cap proxy.
        logger.info("[sp1500] Loading SP1500 universe (sp500 + sp400 + sp600 de-duped)…")
        _sp1500_full_frame = get_sp1500_constituents()
        logger.info(
            "[sp1500] Full frame size: %d (sp500+sp400+sp600 combined; all three cohorts ranked)",
            len(_sp1500_full_frame),
        )
        # Midcap probe — runs on the FULL frame to capture sp400 cohort stats.
        logger.info("[sp1500-probe] Running midcap diagnostic probe (Rule 18)…")
        try:
            (
                _pilot_midcap_coverage_pct,
                _pilot_midcap_null_rate_pct,
                _pilot_midcap_cik_resolution_pct,
                _pilot_cohort_sizes,
            ) = _run_midcap_coverage_probe(_sp1500_full_frame)
            logger.info(
                "[sp1500-probe] Midcap complete: cohorts=%s coverage=%.1f%% null_rate=%.1f%% cik_resolution=%.1f%%",
                _pilot_cohort_sizes,
                _pilot_midcap_coverage_pct or 0.0,
                _pilot_midcap_null_rate_pct or 0.0,
                _pilot_midcap_cik_resolution_pct or 0.0,
            )
        except Exception as _sp1500_mid_exc:  # noqa: BLE001
            logger.error(
                "[sp1500-probe] Midcap probe block failed (non-fatal): %s", _sp1500_mid_exc
            )
        # Smallcap probe — sp600 cohort within the FULL frame (probe-only; sp600
        # rows are NOT fed to scoring below).
        logger.info("[sp1500-probe] Running smallcap diagnostic probe (Rule 18)…")
        try:
            (
                _pilot_smallcap_coverage_pct,
                _pilot_smallcap_null_rate_pct,
                _pilot_smallcap_cik_resolution_pct,
                _sp1500_cohort_sizes,
            ) = _run_smallcap_coverage_probe(_sp1500_full_frame)
            # Merge sp600 key into the cohort-sizes dict (probe returns all 3 cohorts).
            if _sp1500_cohort_sizes and _pilot_cohort_sizes is None:
                _pilot_cohort_sizes = _sp1500_cohort_sizes
            elif _sp1500_cohort_sizes:
                _pilot_cohort_sizes.update(_sp1500_cohort_sizes)
            logger.info(
                "[sp1500-probe] Smallcap complete: coverage=%.1f%% null_rate=%.1f%% cik_resolution=%.1f%%",
                _pilot_smallcap_coverage_pct or 0.0,
                _pilot_smallcap_null_rate_pct or 0.0,
                _pilot_smallcap_cik_resolution_pct or 0.0,
            )
        except Exception as _sp1500_sml_exc:  # noqa: BLE001
            logger.error(
                "[sp1500-probe] Smallcap probe block failed (non-fatal): %s", _sp1500_sml_exc
            )
        # Slice 7: sp600 rows are NO LONGER dropped — all ~1500 tickers are ranked.
        # The Slice-2 probe-only filter (cohort != "sp600") is lifted here.
        universe = _sp1500_full_frame.reset_index(drop=True)
        logger.info(
            "[sp1500] Slice 7 (cron-default): ranked universe: %d (sp500+sp400+sp600 — full S&P 1500)",
            len(universe),
        )
    elif config.QR_UNIVERSE == "broad_investable_us":
        # Phase 9.3 — Broad Investable US RANKED path (DISPATCH-ONLY; the
        # scheduled cron never sets QR_UNIVERSE=broad_investable_us — it
        # stays sp1500).  Loads the ~6,883-name candidate pool and shapes it
        # into a universe frame; Step 1 below fetches prices for the FULL
        # candidate pool (not a restricted sp1500 dict), then the
        # investability screen reduces to survivors before fundamentals.
        # See the module docstring in compute/ingest/broad_universe.py for
        # the full P1-G3 (pre-scoring membership gate) + P1-G4
        # (re-normalization disclosure) methodology detail.
        from compute.ingest.broad_universe import (  # noqa: PLC0415
            candidates_to_universe_frame,
            fetch_broad_universe_candidates,
        )

        logger.info(
            "[broad-investable-us] Fetching Broad Investable US candidate pool "
            "(Phase 9.3 RANKED path, dispatch-only)…"
        )
        _broad_candidates_df = fetch_broad_universe_candidates()
        universe = candidates_to_universe_frame(_broad_candidates_df)
        logger.info(
            "[broad-investable-us] Candidate universe size: %d (pre-screen — "
            "the investability screen after Step 1 prices reduces this to "
            "survivors before fundamentals)",
            len(universe),
        )
    else:
        # Default sp500 path — byte-identical scoring to pre-PR-3a.
        # Add cohort column so _fetch_prices_one.row.get("cohort") is always defined.
        universe = get_sp500_constituents()
        universe = universe.copy()
        universe["cohort"] = "sp500"
        logger.info("Universe size: %d", len(universe))

    # Multi-index membership — Dow 30 + NDX 100 (0.10.23-phase8pilot).
    # Fetched ONCE per run on BOTH the sp500 and sp900 paths (Dow/NDX are
    # sp500 subsets, so they populate on the normal weekday cron).
    # Graceful degradation: fetch_dow30_constituents / fetch_ndx_constituents
    # return empty sets on failure — the cron MUST NOT crash here.
    logger.info("Fetching Dow 30 + NDX 100 overlap membership sets…")
    _dow30_tickers: set[str] = set()
    _ndx_tickers: set[str] = set()
    try:
        _dow30_tickers = fetch_dow30_constituents()
        logger.info("DOW30: %d tickers loaded", len(_dow30_tickers))
    except Exception as _dow_exc:  # noqa: BLE001
        logger.warning("DOW30 fetch failed (non-fatal, membership will be empty): %s", _dow_exc)
    try:
        _ndx_tickers = fetch_ndx_constituents()
        logger.info("NDX: %d tickers loaded", len(_ndx_tickers))
    except Exception as _ndx_exc:  # noqa: BLE001
        logger.warning("NDX fetch failed (non-fatal, membership will be empty): %s", _ndx_exc)

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

    # Step 1 — prices in parallel (loop extracted to compute.orchestrator.prices).
    rows, prices_by_ticker, adv_by_ticker = fetch_all_prices(universe)
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

    # Phase 9.1 — Broad Investable US universe coverage probe (Rule 18,
    # observability-before-wiring).  Runs immediately after Step 1 so the
    # full ``prices_by_ticker`` dict is available for the investability screen
    # (price >= $5 / ADV >= $5M).  The probe is WRITE-ONLY / OBSERVABILITY-ONLY:
    # its output feeds the ``Metadata`` constructor and NOTHING ELSE.
    # Rankings/scores/flags are BYTE-IDENTICAL whether or not this block ran.
    # Defense layer is UNCHANGED at 36.
    #
    # The probe is gated on:
    #   (a) QR_SKIP_BROAD_UNIVERSE != "1" / "true" / "yes"
    #       (set in the pre-merge sim workflow to avoid the live SEC call)
    #   (b) graceful degradation: any exception → all-None, cron never blocked
    #
    # ``security_types_by_ticker`` is not yet available here (Step 8 builds it).
    # The probe passes ``security_types_by_ticker=None`` so the security-type
    # filter is skipped on this slice (graceful degradation documented in
    # ``screen_broad_universe_investability``).  A Phase 9.3 follow-up can
    # re-order or cache the types earlier if the sec-type filter proves material.
    try:
        _broad_probe_result = _run_broad_universe_probe(
            prices_by_ticker=prices_by_ticker,
            security_types_by_ticker=None,  # not yet available at Step 1+
        )
        _broad_universe_raw_count = _broad_probe_result.get("broad_universe_raw_count")
        _broad_universe_candidate_count = _broad_probe_result.get(
            "broad_universe_candidate_count"
        )
        _broad_universe_screened_count = _broad_probe_result.get(
            "broad_universe_screened_count"
        )
        _broad_universe_price_fail_pct = _broad_probe_result.get(
            "broad_universe_price_fail_pct"
        )
        _broad_universe_adv_fail_pct = _broad_probe_result.get(
            "broad_universe_adv_fail_pct"
        )
        _broad_universe_coverage_pct = _broad_probe_result.get(
            "broad_universe_coverage_pct"
        )
    except Exception as _broad_exc:  # noqa: BLE001
        logger.error(
            "[broad-universe-probe] Outer block failed (non-fatal): %s", _broad_exc
        )
        # _broad_universe_* variables remain at their None-initialized defaults.

    # Phase 9.3 — Broad Investable US RANKED path: reduce the scored frame to
    # investability-screen survivors BEFORE fundamentals (Step 2).  DISPATCH-
    # ONLY (config.QR_UNIVERSE == "broad_investable_us"); every other path is
    # a no-op here (the block body never executes) so sp1500/sp900/sp500
    # scoring is UNCHANGED.
    #
    # Sequencing: at this point ``prices_by_ticker`` holds prices for the
    # FULL candidate pool (Step 1 fetched prices for ``universe``, which on
    # this path is the unscreened ~6,883-name candidate frame — see the
    # universe-selector seam above).  ``select_broad_universe_survivors``
    # applies the identical price >= $5 / trailing-30d ADV >= $5M floors the
    # Phase 9.1 probe uses (just run above, on this same prices_by_ticker
    # dict — so its ``broad_universe_screened_count`` etc. now describe the
    # TRUE broad-universe screen, not the sp1500-restricted lower bound the
    # probe-only Phase 9.1 slice produced).
    #
    # ``df`` / ``rows`` / ``prices_by_ticker`` / ``adv_by_ticker`` are all
    # reduced to the survivor set so Step 2 (fundamentals), the tier2 8-K
    # loop, the Form-4 loop, and every per-ticker scoring step downstream
    # run ONLY on the ~3,545 survivors — never on all ~6,883 candidates.
    # This bounds EDGAR load to roughly the same order of magnitude as the
    # existing sp1500 path (perf-engineer confirmed no EDGAR_MAX_WORKERS /
    # tenacity-policy change is needed for this scale).
    #
    # P1-G3 (methodology-scientist ratified): non-survivors are REMOVED from
    # the peer set entirely — they are NOT emitted as a ``low_liquidity``
    # annotate (that annotate is for names that ARE ranked but trade
    # thinly; a name that never enters the scored frame has nothing to
    # annotate).
    #
    # Failure handling: UNLIKE most graceful-degradation blocks in this
    # module (which fall through to a smaller/None result and keep going),
    # a failure HERE aborts the run (``return 0``, mirroring the
    # ``assert_sec_api_usable`` / ``MIN_VALID_TICKERS`` abort idiom already
    # used elsewhere in this function) rather than falling through to
    # scoring the FULL unscreened ~6,883-name candidate frame.  Silently
    # scoring the unscreened frame would double the fundamentals-fetch
    # volume this PR is explicitly bounding (task requirement: "control
    # runtime") and risks tripping the CI timeout budget — on THIS
    # dispatch-only path an abort-and-preserve-last-good-data is the safer
    # failure mode than an unbounded-runtime partial run.
    if config.QR_UNIVERSE == "broad_investable_us":
        try:
            from compute.ingest.broad_universe import (  # noqa: PLC0415
                select_broad_universe_survivors,
            )

            _broad_survivor_tickers = select_broad_universe_survivors(
                candidates=universe,
                prices_by_ticker=prices_by_ticker,
            )
        except Exception as _broad_screen_exc:  # noqa: BLE001
            logger.error(
                "[broad-investable-us] Investability-screen computation failed — "
                "aborting without writing JSON to preserve last-good data "
                "(scoring the full unscreened candidate frame is not a safe "
                "fallback on this runtime-bounded path): %s",
                _broad_screen_exc,
            )
            return 0

        _pre_screen_count = len(df)
        df = df[df["ticker"].isin(_broad_survivor_tickers)].copy()
        rows = [r for r in rows if r["ticker"] in _broad_survivor_tickers]
        prices_by_ticker = {
            t: p for t, p in prices_by_ticker.items() if t in _broad_survivor_tickers
        }
        adv_by_ticker = {
            t: a for t, a in adv_by_ticker.items() if t in _broad_survivor_tickers
        }
        logger.info(
            "[broad-investable-us] Investability screen: %d / %d priced candidates "
            "survived (price >= $5 AND trailing-30d ADV >= $5M) — fundamentals "
            "(Step 2) will run ONLY on survivors",
            len(df), _pre_screen_count,
        )
        if len(df) < config.MIN_VALID_TICKERS:
            logger.error(
                "[broad-investable-us] Only %d survivors — below minimum of %d. "
                "Aborting without writing JSON to preserve last-good data.",
                len(df), config.MIN_VALID_TICKERS,
            )
            return 0

    # Step 2 — fundamentals snapshot in parallel.
    logger.info(
        "Fetching fundamentals for %d tickers (max_workers=%d)…",
        len(df),
        config.EDGAR_MAX_WORKERS,
    )
    # Issue #246 PR2a (0.10.3-phase4.5e) — reset Rule 18 shares-fallback
    # counters before the fetch loop so this run's counts start at 0.
    # Read back via ``state.metrics.shares_fallback_stats`` after the loop.
    # PR #259-R1: routed through MetricsCollector facade (delegates to
    # fundamentals.reset_fallback_stats() — the module-global + lock are
    # unchanged; byte-identical behaviour).
    state.metrics.reset_shares_fallback()
    # Issue #471 — reset the filing-precheck skip counter (Design B, filing-date gate).
    # Read back via ``get_fundamentals_filing_precheck_skip_count()`` after the histogram log.
    reset_fundamentals_filing_precheck_skip_count()
    # PR #259-R3 — Step-2 parallel fetch extracted to compute.orchestrator.fundamentals.
    # The two resets above and the "Fetching fundamentals…" info log (below) remain
    # here so they fire in the same position and exactly once.  Everything after this
    # call (coverage calc, histogram, abort gate) is unchanged.
    snapshots, fundamentals_latency = fetch_all_fundamentals(
        df, timeout=_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS
    )

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
    # Extracted to compute.orchestrator.form4 as part of PR #259-R4.
    # Absorbs smell #9: _fetch_one_form4 closure moved to module scope in
    # the orchestrator. All SKIP / happy-path / outer-except semantics are
    # byte-identical to the original inline block.
    (
        form4_diagnostics,
        form4_latencies,
        form4_failures,
        form4_wall_clock_seconds,
        form4_negation_guard_downgrade_count,
    ) = fetch_all_form4(df)

    # Step 3b — post-split share-lag correction pass (defense layer 35,
    # 2026-06-18 methodology-scientist ruling).
    #
    # This pass MUST run BEFORE Step 4 (TickerInputs + pillar scoring) so
    # that EPS / market_cap / value-pillar / composite ALL derive from the
    # corrected share count automatically.
    #
    # Correction strategy (chosen over alternatives):
    #   - Correction at snapshot level (here) is the least-invasive option:
    #     ``snap.shares_outstanding`` is mutated directly on the snapshot
    #     dataclass object, so every downstream consumer (pillars, valuation,
    #     DQIC, NSI) reads the corrected value without any code changes.
    #   - An alternative "pre-scoring pass in main.py" that patches a
    #     derived df column would need to touch each pillar separately.
    #   - Correcting inside fundamentals.py would require yfinance split data
    #     at ingest time, adding a cross-source dependency to a pure EDGAR
    #     module (wrong layer boundary).
    #
    # Graceful-degradation: the entire pass is wrapped in try/except so a
    # bug or fetch failure never blocks the cron.  On failure, snapshots
    # are unchanged and `post_split_results` remains empty — the flag just
    # doesn't fire.
    #
    # QR_SKIP_SPLITS=1 is the escape hatch for pre-merge-prod-sim (mirrors
    # QR_SKIP_CROSS_SOURCE pattern; honored inside fetch_splits()).
    post_split_results: dict[str, PostSplitResult] = {}
    post_split_correction_applied_count: int = 0
    post_split_veto_count: int = 0
    try:
        _price_by_ticker: dict[str, float | None] = {
            str(r["ticker"]): float(r["current_price"]) if r.get("current_price") is not None else None
            for _, r in df.iterrows()
        }
        for _ticker, _snap in snapshots.items():
            if _snap is None:
                continue
            _current_price = _price_by_ticker.get(_ticker)
            # Fetch yfinance market cap from the existing cache (24h TTL,
            # same call site as Step 8's cross-source validation).  On a
            # warm cache this is a cheap JSON read; on a cold cache it does
            # a live yfinance.info call that also populates sharesOutstanding
            # into the cache as a side-effect (_yf_info_fetch dual-field).
            # The split pass only triggers when the 3-leg check passes, so
            # cold-cache overhead is bounded to actual split candidates.
            #
            # After the market_cap fetch (which primes the cache), read the
            # sharesOutstanding directly from the same cache file.  This
            # avoids the cache-timing trap where yf_market_cap / current_price
            # gives a wrong implied count when the market_cap and prices caches
            # straddle the split date (yfinance retroactively split-adjusts
            # price bars but not marketCap snapshots on the same cadence).
            # When the override is unavailable (None) — cold cache,
            # QR_SKIP_CROSS_SOURCE=1, or missing info field — leg 3 falls
            # back gracefully to the existing market_cap / price path.
            _yf_mc = fetch_yfinance_market_cap(_ticker)
            _yf_shares = fetch_yfinance_shares_outstanding(_ticker)
            _psr = check_post_split_share_lag(
                _ticker,
                _snap,
                yf_market_cap=_yf_mc,
                current_price=_current_price,
                yf_shares_outstanding_override=_yf_shares,
            )
            if _psr.tier == 0:
                continue
            post_split_results[_ticker] = _psr
            if _psr.tier == 1:
                # Tier-1 CORRECT: mutate the snapshot's shares_outstanding
                # in-place so all downstream scoring sees the corrected value.
                # The raw value is preserved in RawMetrics.shares_outstanding_pre_split_raw
                # (written in the Step 8 per-ticker loop below).
                assert _psr.corrected_shares is not None  # invariant: tier==1 always has corrected_shares
                _snap.shares_outstanding = _psr.corrected_shares
                post_split_correction_applied_count += 1
                logger.info(
                    "[post_split] %s: in-place correction applied "
                    "edgar_raw=%.2fM → corrected=%.2fM (%.0f:1 split %s)",
                    _ticker,
                    _psr.edgar_shares / 1e6,  # type: ignore[operator]
                    _psr.corrected_shares / 1e6,
                    _psr.split_event.ratio,  # type: ignore[union-attr]
                    _psr.split_event.split_date.isoformat(),  # type: ignore[union-attr]
                )
            elif _psr.tier == 2:
                post_split_veto_count += 1
    except Exception as _split_exc:  # noqa: BLE001
        logger.warning(
            "Post-split share-lag correction pass failed (non-fatal — "
            "snapshots unchanged, post_split_share_lag flag will not fire): %s",
            _split_exc,
        )
        post_split_results = {}
        post_split_correction_applied_count = 0
        post_split_veto_count = 0

    if post_split_results:
        logger.info(
            "[post_split] Pass complete: %d corrections applied, %d vetoes "
            "(%d total flagged tickers out of %d universe)",
            post_split_correction_applied_count,
            post_split_veto_count,
            len(post_split_results),
            len(snapshots),
        )

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

    # Step 4b — Tier-2 event defenses (PR 3d; loop extracted to
    # compute.orchestrator.tier2 as part of PR #259-R5). Fetched in
    # parallel ahead of risk-flag computation so the resulting
    # non_reliance veto can be injected into compute_risk_flags (avoiding
    # a duplicate EDGAR fetch inside the risk-overlay layer). See
    # compute/scoring/tier2.py.
    tier2_results, tier2_wall_clock_seconds = fetch_all_tier2(df)
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
    #
    # Proposal A — shrinkage composite (Rule 18 observability-first).
    # HOISTED here (before compute_composite) so blended_w exists at call time.
    # PIT-clean: walk_ic_history reads COMMITTED PRIOR rankings only — the
    # current run is not committed yet, so there is zero look-ahead.
    # Guarded by QR_SKIP_DECAY_MONITOR (reuses the IC-history guard — both
    # are IC-history machinery; no separate env-var needed per the co-location
    # decision 2026-06-24 that also applies to Proposal F).
    # C5: try/except → degrade-to-empty → degenerate=True → blended_w=w0 →
    # composite byte-identical.  NEVER raises; cron never blocked.
    # Identity-at-launch: SHRINKAGE_LAMBDA_PIN=1.0 + all pillars preliminary
    # → blended_w == PHASE3_EFFECTIVE_WEIGHTS → composite byte-identical.
    _shrinkage_skip = (
        os.environ.get("QR_SKIP_DECAY_MONITOR", "").lower() in ("1", "true", "yes")
    )
    # Diagnostics for Metadata (6 Proposal-A fields).
    _shrinkage_lambda: float | None = None
    _shrinkage_lambda_applied: float | None = None
    _ic_weight_by_pillar: dict[str, float] | None = None
    _shrinkage_blended_weight_by_pillar: dict[str, float] | None = None
    _n_preliminary_pillars: int | None = None
    _shrinkage_weights_degenerate: bool | None = None
    # The shared _ic_walk_result is consumed here AND by the decay/half-life
    # monitors below (Proposal A #605 consolidation — ONE git-walk, not two).
    _ic_walk_result = None

    if not _shrinkage_skip:
        try:
            from compute.scoring.composite import (
                ACTIVE_PILLARS_PHASE3 as _SHRINK_ACTIVE_PILLARS,
            )
            from compute.scoring.composite import (
                PHASE3_EFFECTIVE_WEIGHTS as _SHRINK_W0,
            )
            from compute.scoring.shrinkage import (
                SHRINKAGE_LAMBDA_PIN as _SHRINK_PIN,
            )
            from compute.scoring.shrinkage import (
                SHRINKAGE_TAU_MONTHS as _SHRINK_TAU,
            )
            from compute.scoring.shrinkage import (
                blend_weights as _blend_weights,
            )
            from compute.scoring.shrinkage import (
                build_ic_weights as _build_ic_weights,
            )
            from compute.scoring.shrinkage import (
                compute_shrinkage_lambda as _compute_shrinkage_lambda,
            )
            from compute.validation.ic_decay import (
                IC_HORIZON_MONTHS as _SHRINK_HORIZON,
            )
            from compute.validation.ic_decay import (
                IC_LOOKBACK_MONTHS as _SHRINK_LOOKBACK,
            )
            from compute.validation.ic_decay import (
                build_decay_report as _shrink_build_decay,
            )
            from compute.validation.ic_decay import (
                walk_ic_history as _walk_ic_history,
            )

            # ONE git-walk (#605 consolidation).
            _ic_walk_result = _walk_ic_history(
                horizon_months=_SHRINK_HORIZON,
                lookback_months=_SHRINK_LOOKBACK,
            )

            # Build per-pillar decay reports using the injected panels
            # (no second git-walk).
            _shrink_decay_reports, _, _shrink_n_dates = _shrink_build_decay(
                panels=_ic_walk_result.panels,
                entries=_ic_walk_result.entries,
                n_dates_with_ic=_ic_walk_result.n_dates_with_ic,
            )

            # Compute IC-implied weights (reads ICDecayReport.preliminary — C1).
            _w_ic, _prelim_mask, _degenerate = _build_ic_weights(
                _shrink_decay_reports,
                _SHRINK_W0,
                _SHRINK_ACTIVE_PILLARS,
            )

            # Schedule-derived lambda (most-history pillar proxy).
            _max_n = max(
                (r.n_observations for r in _shrink_decay_reports
                 if r.pillar in _SHRINK_ACTIVE_PILLARS),
                default=0,
            )
            _lam = _compute_shrinkage_lambda(_max_n, tau=_SHRINK_TAU)

            # Blend (SHRINKAGE_LAMBDA_PIN=1.0 → blended_w == w0 at launch).
            _blended_w = _blend_weights(
                _SHRINK_W0,
                _w_ic,
                _lam,
                _prelim_mask,
                lambda_pin=_SHRINK_PIN,
            )

            # C-canary: assert renorm held before handing to compute_composite.
            _blended_sum = sum(_blended_w.values())
            if abs(_blended_sum - 1.0) > 1e-9:
                raise ValueError(
                    f"Proposal A: blended weight sum={_blended_sum:.15f} "
                    "deviates from 1.0 by > 1e-9 — aborting shrinkage; "
                    "falling back to w0."
                )

            # Populate 6 Metadata diagnostics.
            _shrinkage_lambda = _lam
            _shrinkage_lambda_applied = (
                float(_SHRINK_PIN) if _SHRINK_PIN is not None else _lam
            )
            _ic_weight_by_pillar = dict(_w_ic)
            _shrinkage_blended_weight_by_pillar = dict(_blended_w)
            _n_preliminary_pillars = len(_prelim_mask)
            _shrinkage_weights_degenerate = bool(_degenerate)

            logger.info(
                "Proposal A shrinkage: lambda=%.4f applied=%.4f "
                "preliminary=%d/%d degenerate=%s",
                _lam,
                _shrinkage_lambda_applied,
                _n_preliminary_pillars,
                len(_SHRINK_ACTIVE_PILLARS),
                _degenerate,
            )

        except Exception as _shrink_exc:  # noqa: BLE001
            logger.warning(
                "Proposal A shrinkage failed (non-fatal — falling back to w0); "
                "blended_w := PHASE3_EFFECTIVE_WEIGHTS.  Error: %s",
                _shrink_exc,
            )
            _blended_w = None  # signal: use default below
            _ic_walk_result = None  # decay/half-life monitors will self-walk

    # Determine the weight vector for compute_composite.
    # When shrinkage succeeded → use _blended_w (byte-identical to w0 while pinned).
    # When shrinkage was skipped / failed → pass None (compute_composite defaults to w0).
    _composite_weights = _blended_w if (not _shrinkage_skip and _blended_w is not None) else None
    composite = compute_composite(pillar_df, weights=_composite_weights)
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
        post_split_results=post_split_results if post_split_results else None,
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
    # Extracted to compute/orchestrator/osap.py as part of PR #259-R6
    # (incremental refactor of run_weekly_compute) — a PURE CODE MOVE, no
    # behaviour change. See that module's docstring for the full
    # byte-identical guarantee. Observability-only this phase: Top-5
    # ranking still uses raw ``composite_score`` per SKILL.md Rule 16.
    (
        osap_signals_used,
        osap_excluded_signals,
        osap_signals_ic_12m,
        osap_signal_map,
        osap_signals_coverage_pct,
        composite_osap_adjusted,
        osap_signals_missing_from_dataset,
        osap_gate_diagnostics,
        osap_signals_dropped_no_long_short_list,
        osap_wall_clock_seconds,
    ) = run_osap_pipeline(pillar_df, composite, asof_date)

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

    # PR #259-R7a — pre-loop membership-map building moved to
    # compute.orchestrator.per_ticker.build_ticker_membership_maps (pure
    # code move; see that module's docstring for the byte-identical
    # guarantee). cik_by_ticker / market_cap_by_ticker are now fully
    # internal to the helper — nothing downstream reads them directly.
    multi_class_flagged_tickers, cohort_by_ticker, memberships_by_ticker = (
        build_ticker_membership_maps(
            df, snapshots, dow30=_dow30_tickers, ndx=_ndx_tickers
        )
    )
    # Step 8 — combined per-ticker loop: fair-price ensemble + price history
    # write + StockSummary + StockDetail. Extracted to
    # compute.orchestrator.per_ticker.run_per_ticker_loop as part of PR
    # #259-R7b (final slice of the incremental refactor of
    # run_weekly_compute, issue #259) — a PURE CODE MOVE, no behaviour
    # change. See that module's docstring for the full byte-identical
    # guarantee (incl. why ``_filing_lag`` / ``_build_raw_metrics`` are
    # injected as callables rather than moved).
    result = run_per_ticker_loop(
        df=df,
        snapshots=snapshots,
        pillar_df=pillar_df,
        risk_flags=risk_flags,
        beneish_results=beneish_results,
        dechow_results=dechow_results,
        rem_results=rem_results,
        post_split_results=post_split_results,
        tier2_results=tier2_results,
        histories=histories,
        historical_metrics=historical_metrics,
        universe_metrics=universe_metrics,
        by_sector=by_sector,
        by_sub_industry=by_sub_industry,
        broad_ex_fin_util=broad_ex_fin_util,
        adv_by_ticker=adv_by_ticker,
        prices_by_ticker=prices_by_ticker,
        imputed_by_ticker=imputed_by_ticker,
        sector_pillar_baselines=sector_pillar_baselines,
        form4_diagnostics=form4_diagnostics,
        osap_signal_map=osap_signal_map,
        composite_osap_adjusted=composite_osap_adjusted,
        cohort_by_ticker=cohort_by_ticker,
        memberships_by_ticker=memberships_by_ticker,
        multi_class_flagged_tickers=multi_class_flagged_tickers,
        entered=entered,
        exited=exited,
        asof_date=asof_date,
        now=now,
        filing_lag_fn=_filing_lag,
        build_raw_metrics_fn=_build_raw_metrics,
    )
    cross_source_wall_clock_seconds = result.cross_source_wall_clock_seconds
    summaries = result.summaries
    all_details = result.all_details
    loss_avoidance_size_invariant_firing_count = (
        result.loss_avoidance_size_invariant_firing_count
    )
    share_count_extraction_missing_count = result.share_count_extraction_missing_count
    fundamentals_unavailable_count = result.fundamentals_unavailable_count
    low_liquidity_annotate_count = result.low_liquidity_annotate_count
    extreme_estimate_majority_count = result.extreme_estimate_majority_count
    extreme_estimate_majority_lowapp_count = (
        result.extreme_estimate_majority_lowapp_count
    )
    cross_source_disagreement_count = result.cross_source_disagreement_count
    cross_source_delta_histogram = result.cross_source_delta_histogram
    cross_source_delta_by_ticker = result.cross_source_delta_by_ticker
    _cs_yf_market_cap_by_ticker = result._cs_yf_market_cap_by_ticker
    _cs_yf_shares_by_ticker = result._cs_yf_shares_by_ticker
    _median_trimmed_by_ticker = result._median_trimmed_by_ticker
    exchange_by_ticker = result.exchange_by_ticker
    country_by_ticker = result.country_by_ticker
    _dividend_yield_pct_by_ticker = result._dividend_yield_pct_by_ticker
    _security_type_by_ticker = result._security_type_by_ticker
    value_trap_risk_count_without_sector_coe = (
        result.value_trap_risk_count_without_sector_coe
    )
    value_trap_risk_count_with_sector_coe = result.value_trap_risk_count_with_sector_coe
    value_trap_risk_two_factor_shadow_count = (
        result.value_trap_risk_two_factor_shadow_count
    )
    value_trap_risk_count_without_sector_coe_by_sector = (
        result.value_trap_risk_count_without_sector_coe_by_sector
    )
    value_trap_risk_count_with_sector_coe_by_sector = (
        result.value_trap_risk_count_with_sector_coe_by_sector
    )
    insider_sell_cluster_firing_count = result.insider_sell_cluster_firing_count
    c_suite_unusual_sell_firing_count = result.c_suite_unusual_sell_firing_count
    form4_rule10b5_one_excluded_count = result.form4_rule10b5_one_excluded_count
    multi_class_aggregate_shares_suspected_count = (
        result.multi_class_aggregate_shares_suspected_count
    )

    # Step 9 — sanity smoke test (Phase 3c Step 8). Cross-sectional Spearman
    # rank corr between margin_of_safety_pct and trailing 1y return. NOT a
    # backtest — see compute/scoring/sanity.py docstring.
    mos_ic = compute_mos_trailing_ic(
        rankings=summaries,
        prices_by_ticker=prices_by_ticker,
    )
    logger.info("MoS trailing IC smoke: %s", mos_ic)

    # Phase 8 pilot — post-scoring cohort-size recompute (sp900 + sp1500 paths).
    # Bug fix: ``_pilot_cohort_sizes`` was previously populated from the
    # PRE-scoring universe frame in ``_run_midcap_coverage_probe`` (lines
    # ~763-766), which counted 503 sp500 tickers (including one recently-
    # delisted name that later fails ``fetch_prices`` and is silently
    # dropped before the write step).  That produced
    # ``universe_cohort_sizes.sp500 = 503`` while ``rankings.json`` had
    # 502 sp500 rows, making ``sum(universe_cohort_sizes.values()) = 903
    # ≠ universe_size = 902`` — a contradictory metadata surface.
    #
    # Fix: recompute from the POST-scoring ``summaries`` list (the same
    # rows that are written to ``rankings.json``) so the per-cohort counts
    # always sum to ``universe_size``.  On the default sp500 path
    # ``_pilot_cohort_sizes`` stays None (no change).
    #
    # sp1500 extension (Slice 7): the gate was previously "sp900" only, so on
    # the sp1500 ranked path the stale PRE-scoring dict (sp500+sp400+sp600
    # summing to ~1500 across the full frame) leaked into metadata.json as
    # ``universe_cohort_sizes`` while ``universe_size`` reflected the smaller
    # POST-scoring count — a contradictory pair.  Widening to include "sp1500"
    # fixes this.  The recompute loop keys off ``s.index_membership`` which
    # correctly carries "sp600" for small-cap names (set from ``cohort_by_ticker``
    # which reads the "cohort" column written by ``get_sp1500_constituents``).
    # The sp500 path is unaffected (_pilot_cohort_sizes stays None there).
    if config.QR_UNIVERSE in ("sp900", "sp1500") and _pilot_cohort_sizes is not None:
        post_scoring_cohort_sizes: dict[str, int] = {}
        for s in summaries:
            membership = s.index_membership  # "sp500" | "sp400" | "sp600"
            post_scoring_cohort_sizes[membership] = (
                post_scoring_cohort_sizes.get(membership, 0) + 1
            )
        _pilot_cohort_sizes = post_scoring_cohort_sizes
        logger.info(
            "[%s] Post-scoring cohort sizes (replaces pre-scoring probe count): %s",
            config.QR_UNIVERSE,
            _pilot_cohort_sizes,
        )

    # Issue #177 PR-A (0.10.24-phase8pilot) — compute the blast-radius
    # metric for the shadow trimmed median across the scored universe.
    # Counts tickers where the MoS SIGN would flip under median_trimmed
    # vs the live median (the "would the recommendation direction change?"
    # measure). Sign convention: positive mos_pct = undervalued (median >
    # price); negative = overvalued. A flip means the live median calls
    # a stock undervalued but the trim says overvalued (or vice versa).
    # Only counted when median_trimmed is not None (excludes majority-
    # collapse cases where < 2 non-extreme survivors remain). Reads from
    # _median_trimmed_by_ticker populated in the Step 8 per-ticker loop.
    median_trim_delta_count: int | None = None
    try:
        _sign_flips = 0
        _trim_eligible = 0
        for s in summaries:
            _mt = _median_trimmed_by_ticker.get(s.ticker)
            if _mt is None:
                continue
            _price = s.current_price
            # Shadow MoS under trimmed median (same sign convention as mos_pct:
            # positive = intrinsic value above market price = potential undervaluation).
            if _mt > 0 and _price > 0:
                _trim_mos = (_mt - _price) / _mt * 100.0
            else:
                continue
            _live_mos = s.margin_of_safety_pct
            if _live_mos is None:
                continue
            _trim_eligible += 1
            # Sign flip: one side says undervalued (>= 0) and the other says overvalued (< 0).
            if (_trim_mos >= 0) != (_live_mos >= 0):
                _sign_flips += 1
        median_trim_delta_count = _sign_flips
        logger.info(
            "median_trim_delta_count=%d (sign flips out of %d trim-eligible tickers; "
            "Issue #177 PR-A blast-radius metric)",
            _sign_flips,
            _trim_eligible,
        )
    except Exception as _trim_exc:  # noqa: BLE001
        logger.warning(
            "median_trim_delta_count computation failed (non-fatal): %s", _trim_exc
        )
        median_trim_delta_count = None

    # Issue #542 Slice-8 Bonferroni shadow counter (0.10.30-phase8pilot, Rule 18).
    # Reads beneish_m_scores already computed in Step 5 — zero new computation.
    # Wrapped in try/except so a bug never blocks the cron — all 3 counters fall
    # to None on failure (backward-compatible with legacy consumers).
    bonferroni_shadow_flip_count: int | None = None
    bonferroni_shadow_live_fire_count: int | None = None
    bonferroni_shadow_provisional_fire_count: int | None = None
    try:
        (
            bonferroni_shadow_flip_count,
            bonferroni_shadow_live_fire_count,
            bonferroni_shadow_provisional_fire_count,
        ) = compute_bonferroni_shadow(beneish_m_scores)
    except Exception as _bonf_exc:  # noqa: BLE001
        logger.warning(
            "bonferroni_shadow computation failed (non-fatal, #542): %s", _bonf_exc
        )
        bonferroni_shadow_flip_count = None
        bonferroni_shadow_live_fire_count = None
        bonferroni_shadow_provisional_fire_count = None

    # Issue #16 — restatement_history weight-demotion delta counter
    # (Q3 2026 cohort audit, 0.10.42-phase8pilot, Rule 18 observability-first).
    #
    # Counts tickers carrying ``restatement_history`` in valuation_warnings
    # but NOT ``restatement_high_confidence``.  These are exactly the "plain
    # restater" tickers whose manipulation-index contribution drops by 5.0
    # points under the weight demotion (RESTATEMENT_HISTORY_WEIGHT 5.0→0.0).
    # Irregularity tickers carry BOTH flags; their net delta is zero because
    # RESTATEMENT_HIGH_CONFIDENCE_WEIGHT rose 3.0→8.0 to compensate.
    #
    # OBSERVABILITY-ONLY — never read by scoring, composite, pillar logic,
    # veto/flag, fair-price, or select_picks.  Defense layer UNCHANGED at 36.
    # Wrapped in try/except so a bug never blocks the cron.
    restatement_history_weight_demote_delta_count: int | None = None
    try:
        _demote_delta = _count_restatement_demote_delta(summaries)
        restatement_history_weight_demote_delta_count = _demote_delta
        logger.info(
            "restatement_history_weight_demote_delta_count=%d "
            "(plain-restater tickers whose manipulation-index drops 5.0→0.0; "
            "irregularity subset carries both flags, net delta=0; issue #16)",
            _demote_delta,
        )
    except Exception as _rst_exc:  # noqa: BLE001
        logger.warning(
            "restatement_history_weight_demote_delta_count computation failed "
            "(non-fatal, #16): %s",
            _rst_exc,
        )
        restatement_history_weight_demote_delta_count = None

    # PR-1 cross-source corruption shadow (0.10.26-phase8pilot, Rule 18).
    # Aggregates the per-ticker grade results into the 4 new Metadata counters.
    # Uses the delta dict already populated in Step 8, plus the yf_market_cap
    # and yf_shares_outstanding dicts collected as a zero-cost cache-read
    # side-channel in the same Step 8 per-ticker loop.
    # Wrapped in try/except so a bug never blocks the cron — all 4 counters
    # fall to None on failure (backward-compatible with legacy consumers).
    cross_source_corruption_correct_candidate_count: int | None = None
    cross_source_corruption_veto_candidate_count: int | None = None
    cross_source_corruption_ratio_disagreement_count: int | None = None
    cross_source_corruption_inferred_ratio_by_ticker: dict[str, float] | None = None
    try:
        (
            cross_source_corruption_correct_candidate_count,
            cross_source_corruption_veto_candidate_count,
            cross_source_corruption_ratio_disagreement_count,
            cross_source_corruption_inferred_ratio_by_ticker,
        ) = compute_cross_source_corruption_shadow(
            universe_deltas=cross_source_delta_by_ticker,
            snapshots=snapshots,
            current_prices={
                str(r["ticker"]): (
                    float(r["current_price"])
                    if r.get("current_price") is not None
                    else None
                )
                for _, r in df.iterrows()
            },
            yf_market_caps=_cs_yf_market_cap_by_ticker,
            yf_shares_outstanding=_cs_yf_shares_by_ticker,
        )
        logger.info(
            "[cross_source_corruption shadow] correct_candidate=%s "
            "veto_candidate=%s ratio_disagreement=%s inferred_tickers=%s",
            cross_source_corruption_correct_candidate_count,
            cross_source_corruption_veto_candidate_count,
            cross_source_corruption_ratio_disagreement_count,
            list(cross_source_corruption_inferred_ratio_by_ticker or {})[:10],
        )
    except Exception as _cs_corruption_exc:  # noqa: BLE001
        logger.warning(
            "cross_source_corruption shadow aggregation failed (non-fatal — "
            "Metadata counters will be None): %s",
            _cs_corruption_exc,
        )

    # Issue #246 PR2a (0.10.3-phase4.5e) — read the universe-wide
    # shares-fallback counters that accumulated inside
    # ``_build_snapshot`` calls during the threaded fundamentals fetch
    # loop. Lock acquired by get_fallback_stats() so this returns a
    # consistent snapshot even if the loop is somehow still running.
    # PR #259-R1: routed through MetricsCollector facade (byte-identical).
    shares_fallback_stats = state.metrics.shares_fallback_stats
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

    # Dividend signal PR-1 (roadmap item #5 / 7a, 0.10.27-phase8pilot,
    # Rule 18 observability-first) — aggregate coverage diagnostic after loop.
    # Reuses the ``_coverage_pct`` helper (same formula as exchange/country).
    # ``dividend_yield_pct`` is non-None whenever yfinance returned a value
    # (including 0.0 for confirmed non-payers) so a high coverage % means
    # the cache was warm and dividend data is available for display.
    dividend_coverage_pct = _coverage_pct(_dividend_yield_pct_by_ticker)
    n_with_dividend = sum(
        1 for v in _dividend_yield_pct_by_ticker.values() if v is not None
    )
    logger.info(
        "Dividend coverage: %d / %d (%.1f%%)",
        n_with_dividend,
        len(_dividend_yield_pct_by_ticker),
        dividend_coverage_pct if dividend_coverage_pct is not None else 0.0,
    )

    # Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.30-phase8pilot,
    # Rule 18 observability-first) — aggregate coverage diagnostic after loop.
    # Reuses the ``_coverage_pct`` helper (same formula as dividend / exchange).
    # ``security_type`` is non-None whenever yfinance fast_info returned a
    # ``quote_type`` and it was in the warm cache by the time the pure
    # cache-read ran.  A high coverage % (expected ~95-99%) confirms the
    # ``quote_type`` field is reliably populated; a low value signals the
    # fast_info cache was cold.
    security_type_coverage_pct = _coverage_pct(_security_type_by_ticker)
    n_with_security_type = sum(
        1 for v in _security_type_by_ticker.values() if v is not None
    )
    logger.info(
        "Security-type coverage: %d / %d (%.1f%%)",
        n_with_security_type,
        len(_security_type_by_ticker),
        security_type_coverage_pct if security_type_coverage_pct is not None else 0.0,
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
    #
    # Proposal A #605 consolidation: reuses ``_ic_walk_result`` from the
    # hoisted shrinkage block (ONE git-walk, not two).  When
    # ``_ic_walk_result`` is None (shrinkage skipped or failed), the decay
    # monitor self-walks via the injected-panels=None path (backward-compat,
    # byte-identical to the pre-#605 behaviour).
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

            # Reuse _ic_walk_result if available (#605 — no second git-walk).
            if _ic_walk_result is not None:
                _decay_reports, _decay_status, _decay_n_dates = build_decay_report(
                    panels=_ic_walk_result.panels,
                    entries=_ic_walk_result.entries,
                    n_dates_with_ic=_ic_walk_result.n_dates_with_ic,
                )
            else:
                # Self-walk fallback (shrinkage was skipped or failed).
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

    # Proposal F — IC half-life monitor (Rule 18 observability-before-wiring).
    # Co-located with the IC-decay monitor block above (both read the same
    # ``panels`` produced by ``pillar_entries_to_monthly_panel``).
    # SHADOW / OBSERVABILITY-ONLY — NEVER modifies scores, flags, vetoes, or
    # rankings.  Skip-safe via QR_SKIP_DECAY_MONITOR=1 (reuses the same guard
    # as the decay monitor — both are IC-history machinery; no separate env-var
    # needed per the co-location decision 2026-06-24).
    # On first cron with ~1 week of git IC history the expected outcome is
    # all ``None`` (preliminary=True for every pillar) — identical posture to
    # ``bonferroni_shadow_*`` / ``cross_source_corruption_*``.
    #
    # Proposal A #605 consolidation: reuses ``_ic_walk_result.panels`` so the
    # duplicate git-walk (block-2 re-walk) is DELETED.  When _ic_walk_result
    # is None, falls back to a standalone panel build from empty entries.
    pillar_ic_half_life_months: dict[str, float | None] | None = None
    pillar_ic_decay_fit_model: dict[str, str | None] | None = None
    if os.environ.get("QR_SKIP_DECAY_MONITOR", "").lower() not in ("1", "true", "yes"):
        try:
            from compute.validation.historical_ic import (
                DEFAULT_PILLARS as _DEFAULT_PILLARS_HL,
            )
            from compute.validation.ic_decay import (
                build_pillar_half_lives,
            )
            from compute.validation.ic_decay import (
                pillar_entries_to_monthly_panel as _panel_for_hl,
            )

            # Reuse _ic_walk_result panels (#605 — block-2 re-walk deleted).
            if _ic_walk_result is not None:
                _hl_panels = _ic_walk_result.panels
            else:
                # Fallback: build from empty (shrinkage was skipped or failed).
                _hl_panels = _panel_for_hl([])

            _hl_results = build_pillar_half_lives(_hl_panels)
            # Surface results: per-pillar half-life + winning model.
            # Missing pillars (no history at all) map to None.
            pillar_ic_half_life_months = {
                p: _hl_results[p].half_life_months if p in _hl_results else None
                for p in _DEFAULT_PILLARS_HL
            }
            pillar_ic_decay_fit_model = {
                p: _hl_results[p].fit_model if p in _hl_results else None
                for p in _DEFAULT_PILLARS_HL
            }
            logger.info(
                "IC half-life monitor: fitted=%d pillars (non-None half-life), "
                "preliminary=%d pillars",
                sum(1 for v in pillar_ic_half_life_months.values() if v is not None),
                sum(
                    1
                    for p in _DEFAULT_PILLARS_HL
                    if p in _hl_results and _hl_results[p].preliminary
                ),
            )
        except Exception as _hl_exc:  # noqa: BLE001
            logger.warning(
                "IC half-life monitor failed (non-fatal — cron continues); "
                "pillar_ic_half_life_months → None. Error: %s",
                _hl_exc,
            )
            pillar_ic_half_life_months = None
            pillar_ic_decay_fit_model = None

    # Proposal D — market-regime diagnostic (Rule 18 observability-before-wiring).
    # Reuses prices_by_ticker from Step 1 — NO new network call, NO new data source.
    # WRITE-ONLY / OBSERVABILITY-ONLY — feeds ONLY the Metadata constructor below.
    # NEVER read by scoring, flags, composite, valuation, or select_picks.
    # Rejection rationale: Welch-Goyal 2008 *RFS* 21(4) shows equity-premium
    # predictors fail OOS; breadth is a PLACEHOLDER FEATURE for Phase-7 HMM.
    # Wrapped in try/except so any failure degrades gracefully to None (never
    # blocks the cron). Rankings/scores/flags are byte-identical.
    market_breadth_above_200dma_pct: float | None = None
    market_regime_state: str | None = None
    try:
        market_breadth_above_200dma_pct, market_regime_state = compute_market_regime(
            prices_by_ticker
        )
    except Exception as _regime_exc:  # noqa: BLE001
        logger.warning(
            "market_regime diagnostic failed (non-fatal — cron continues); "
            "market_breadth_above_200dma_pct → None. Error: %s",
            _regime_exc,
        )
        market_breadth_above_200dma_pct = None
        market_regime_state = None

    # --- Proposal C-2 — MoS tilt shadow canary (Rule 18 observability-first).
    # Reads backtest_pit.json (written earlier in the cron by the PIT-backtest
    # refresh) and extracts the maximum per-rebalance mos_tilt_max_abs_weight_delta_pp
    # across ALL legs as the cross-universe canary for Metadata.
    # Graceful: absent artifact / missing field → None (never blocks cron).
    # HARD CONSTRAINT: this value MUST NEVER be read by scoring, composite,
    # pillar, veto/flag, fair-price, select_picks, or inverse_vol_weights.
    # Rankings/scores/flags are byte-identical.  Defense layer UNCHANGED at 36.
    _mos_tilt_shadow_max_delta_pp: float | None = None
    try:
        import json as _json_mod

        _pit_json_path = config.DATA_DIR / "portfolio" / "backtest_pit.json"
        if _pit_json_path.exists():
            with _pit_json_path.open("r", encoding="utf-8") as _pit_fh:
                _pit_data = _json_mod.load(_pit_fh)
            _per_leg_deltas: list[float] = [
                float(rb["mos_tilt_max_abs_weight_delta_pp"])
                for rb in _pit_data.get("rebalances", [])
                if rb.get("mos_tilt_max_abs_weight_delta_pp") is not None
            ]
            if _per_leg_deltas:
                _mos_tilt_shadow_max_delta_pp = round(max(_per_leg_deltas), 6)
            logger.info(
                "C-2 mos_tilt canary: max_delta_pp=%.6f across %d legs",
                _mos_tilt_shadow_max_delta_pp or 0.0,
                len(_per_leg_deltas),
            )
        else:
            logger.debug(
                "C-2 mos_tilt canary: backtest_pit.json not found at %s — "
                "mos_tilt_shadow_max_delta_pp will be None",
                _pit_json_path,
            )
    except Exception as _mos_tilt_exc:  # noqa: BLE001
        logger.warning(
            "C-2 mos_tilt canary read failed (non-fatal): %s — "
            "mos_tilt_shadow_max_delta_pp → None",
            _mos_tilt_exc,
        )

    # --- Proposal C-1 — high-conviction gate counters (Rule 18 observability-first).
    # Measures the marginal bite of the loss-chance leg in the ALREADY-LIVE
    # high-conviction gate (``gate="high_conviction"`` wired in the backfill since
    # PR #604).  PURELY ADDITIVE — never mutates summaries, composite, or selection.
    # Rankings/scores/flags are byte-identical.  Defense layer UNCHANGED at 36.
    # HARD CONSTRAINT: these counters MUST NEVER be read by scoring, composite,
    # pillar, veto/flag, fair-price, select_picks, or inverse_vol_weights.
    # Wrapped in try/except so any failure degrades gracefully to None (never
    # blocks the cron).
    _hc_count: int | None = None
    _hc_ex_loss_chance_count: int | None = None
    try:
        _hc_count, _hc_ex_loss_chance_count = _count_high_conviction(summaries)
        logger.info(
            "C-1 HC gate: count=%d ex_loss_chance=%d bite=%d (universe=%d)",
            _hc_count,
            _hc_ex_loss_chance_count,
            _hc_ex_loss_chance_count - _hc_count,
            len(summaries),
        )
    except Exception as _hc_exc:  # noqa: BLE001
        logger.warning(
            "high_conviction counter failed (non-fatal, #C-1): %s",
            _hc_exc,
        )
        _hc_count = None
        _hc_ex_loss_chance_count = None

    # --- Proposal C-1 — below_floor starvation canary.
    # Read the refreshed backtest_pit.json (same artifact-read pattern as C-2's
    # mos_tilt canary above).  True when ANY rebalance leg has
    # eligible_high_conviction_count < ADAPTIVE_MIN_PICKS (5) — the per-rebalance
    # starvation signal.  The cron's full-universe count is always >> 5, so a
    # universe-level < 5 check is structurally useless; this reads the backfill
    # artifact where the per-leg band-book size is 5-20 names.
    # None when the artifact is absent or unreadable (graceful-degradation).
    _hc_below_floor: bool | None = None
    _ADAPTIVE_MIN_PICKS_C1: int = 5  # mirrors ADAPTIVE_MIN_PICKS in backfill
    try:
        import json as _json_c1

        _c1_pit_path = config.DATA_DIR / "portfolio" / "backtest_pit.json"
        if _c1_pit_path.exists():
            with _c1_pit_path.open("r", encoding="utf-8") as _c1_fh:
                _c1_pit_data = _json_c1.load(_c1_fh)
            _below_floor_legs = [
                int(rb["eligible_high_conviction_count"])
                for rb in _c1_pit_data.get("rebalances", [])
                if rb.get("eligible_high_conviction_count") is not None
            ]
            if _below_floor_legs:
                _hc_below_floor = any(
                    n < _ADAPTIVE_MIN_PICKS_C1 for n in _below_floor_legs
                )
                logger.info(
                    "C-1 below_floor canary: min_leg=%d across %d legs → %s",
                    min(_below_floor_legs),
                    len(_below_floor_legs),
                    _hc_below_floor,
                )
            else:
                logger.debug(
                    "C-1 below_floor canary: no eligible_high_conviction_count "
                    "entries found in backtest_pit.json — high_conviction_below_floor → None"
                )
        else:
            logger.debug(
                "C-1 below_floor canary: backtest_pit.json not found at %s — "
                "high_conviction_below_floor → None",
                _c1_pit_path,
            )
    except Exception as _hc_floor_exc:  # noqa: BLE001
        logger.warning(
            "C-1 below_floor canary read failed (non-fatal, #C-1): %s — "
            "high_conviction_below_floor → None",
            _hc_floor_exc,
        )
        _hc_below_floor = None

    # --- Proposal E — Turnover / hysteresis diagnostic + liq-capacity tilt canaries.
    # Reads the refreshed backtest_pit.json (same artifact-read pattern as C-2 and C-1).
    # HARD CONSTRAINT: these fields MUST NEVER be read by scoring, composite, pillar,
    # veto/flag, fair-price, select_picks, or inverse_vol_weights.  Written to
    # Metadata ONLY.  Rankings/scores/flags are byte-identical.  Defense layer
    # UNCHANGED at 36.
    _hysteresis_turnover_reduction_mean_pp: float | None = None
    _low_liquidity_held_count: int | None = None
    try:
        import json as _json_e

        _e_pit_path = config.DATA_DIR / "portfolio" / "backtest_pit.json"
        if _e_pit_path.exists():
            with _e_pit_path.open("r", encoding="utf-8") as _e_fh:
                _e_pit_data = _json_e.load(_e_fh)
            # hysteresis_turnover_reduction_mean_pp: mean turnover_reduction_pp
            # across ALL rebalance legs that carry the E shadow fields.
            _e_reductions: list[float] = [
                float(rb["turnover_reduction_pp"])
                for rb in _e_pit_data.get("rebalances", [])
                if rb.get("turnover_reduction_pp") is not None
            ]
            if _e_reductions:
                _hysteresis_turnover_reduction_mean_pp = round(
                    sum(_e_reductions) / len(_e_reductions), 4
                )
            logger.info(
                "E turnover canary: mean_reduction_pp=%.4f across %d legs",
                _hysteresis_turnover_reduction_mean_pp or 0.0,
                len(_e_reductions),
            )
            # low_liquidity_held_count: count of low_liquidity_holdings in the
            # FINAL rebalance leg (the current AI-pick book's liq exposure).
            _e_rebalances = _e_pit_data.get("rebalances", [])
            if _e_rebalances:
                _final_leg = _e_rebalances[-1]
                _ll_holdings = _final_leg.get("low_liquidity_holdings")
                if isinstance(_ll_holdings, list):
                    _low_liquidity_held_count = len(_ll_holdings)
            logger.info(
                "E liq canary: low_liquidity_held_count=%s (final leg)",
                _low_liquidity_held_count,
            )
        else:
            logger.debug(
                "E canary: backtest_pit.json not found at %s — "
                "hysteresis_turnover_reduction_mean_pp and low_liquidity_held_count → None",
                _e_pit_path,
            )
    except Exception as _e_canary_exc:  # noqa: BLE001
        logger.warning(
            "E canary read failed (non-fatal): %s — "
            "hysteresis_turnover_reduction_mean_pp and low_liquidity_held_count → None",
            _e_canary_exc,
        )

    # --- Option-B dividend-pool shadow canaries (issue #620, 0.10.41-phase8pilot).
    # Reads the refreshed backtest_pit.json (same artifact-read pattern as C-2, C-1, E).
    # HARD CONSTRAINT: these fields MUST NEVER be read by scoring, composite, pillar,
    # veto/flag, fair-price, select_picks, or inverse_vol_weights.  Written to
    # Metadata ONLY.  Rankings/scores/flags are byte-identical.  Defense layer
    # UNCHANGED at 36.
    _div_pool_shadow_terminal_nav_delta_pct: float | None = None
    _div_stream_coverage_pct: float | None = None
    try:
        import json as _json_divpool

        _divpool_pit_path = config.DATA_DIR / "portfolio" / "backtest_pit.json"
        if _divpool_pit_path.exists():
            with _divpool_pit_path.open("r", encoding="utf-8") as _divpool_fh:
                _divpool_pit_data = _json_divpool.load(_divpool_fh)
            # div_stream_coverage_pct: read directly from the artifact meta field
            # (populated by the backfill's fetch_dividends_panel call).
            _div_stream_coverage_pct = _divpool_pit_data.get("meta", {}).get(
                "div_stream_coverage_pct"
            )
            # div_pool_shadow_terminal_nav_delta_pct: compute from the terminal
            # NAV values of both the live and shadow series.
            _divpool_nav = _divpool_pit_data.get("nav", {})
            _live_net = _divpool_nav.get("adaptive", {}).get("net", [])
            _shadow_net = _divpool_nav.get("adaptive_div_pooled", {}).get("net", [])
            if _live_net and _shadow_net:
                _live_terminal = next((v for v in reversed(_live_net) if v is not None), None)
                _shadow_terminal = next((v for v in reversed(_shadow_net) if v is not None), None)
                if _live_terminal and _shadow_terminal and _live_terminal > 0:
                    _div_pool_shadow_terminal_nav_delta_pct = round(
                        100.0 * (_shadow_terminal / _live_terminal - 1.0), 4
                    )
            logger.info(
                "Option-B canary: div_stream_coverage_pct=%s, terminal_delta_pct=%s",
                _div_stream_coverage_pct,
                _div_pool_shadow_terminal_nav_delta_pct,
            )
        else:
            logger.debug(
                "Option-B canary: backtest_pit.json not found at %s — "
                "div_pool_shadow_terminal_nav_delta_pct and div_stream_coverage_pct → None",
                _divpool_pit_path,
            )
    except Exception as _divpool_canary_exc:  # noqa: BLE001
        logger.warning(
            "Option-B canary read failed (non-fatal): %s — "
            "div_pool_shadow_terminal_nav_delta_pct and div_stream_coverage_pct → None",
            _divpool_canary_exc,
        )

    meta = Metadata(
        version=config.SCHEMA_VERSION,
        last_update_utc=_iso(now),
        next_update_utc=_iso(now + timedelta(days=_next_business_day_offset(now))),
        # Universe label: "SP1500" when QR_UNIVERSE=sp1500 (Slice 7 — sp600 is
        # NOW ranked; the probe-only "SP1500-probe" label from Slice 2 is retired).
        # "SP900" on the sp900 path; "BROAD_INVESTABLE_US" on the Phase 9.3
        # dispatch-only ranked path (P1-G4: NOT comparable to sp1500-cron
        # scores — see the universe-selector seam docstring); config.UNIVERSE
        # ("SP500") on the default sp500 path.
        universe=(
            "SP1500"
            if config.QR_UNIVERSE == "sp1500"
            else (
                "SP900"
                if config.QR_UNIVERSE == "sp900"
                else (
                    "BROAD_INVESTABLE_US"
                    if config.QR_UNIVERSE == "broad_investable_us"
                    else config.UNIVERSE
                )
            )
        ),
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
        fundamentals_unavailable_count=fundamentals_unavailable_count,
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
        # Dividend signal PR-1 (roadmap item #5 / 7a, 0.10.27-phase8pilot,
        # Rule 18 observability-first). Aggregated from the Step 8 per-ticker
        # loop; None on failure or empty universe.
        dividend_coverage_pct=dividend_coverage_pct,
        # Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.30-phase8pilot,
        # Rule 18 observability-first). Aggregated from the Step 8 per-ticker
        # loop; None on failure or empty universe.
        security_type_coverage_pct=security_type_coverage_pct,
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
        # Populated on the scored sp900/sp1500 path (probe reuses the live universe
        # frame). None on the default sp500 path. Under sp1500, the dict carries
        # all 3 cohort keys: "sp500", "sp400", "sp600".
        universe_cohort_sizes=_pilot_cohort_sizes or None,
        midcap_fundamentals_coverage_pct=_pilot_midcap_coverage_pct,
        midcap_null_rate_pct=_pilot_midcap_null_rate_pct,
        midcap_cik_resolution_pct=_pilot_midcap_cik_resolution_pct,
        # S&P 1500 cutover Slice 2 (0.10.27-phase8pilot, Rule 18) — smallcap probe.
        # Populated ONLY when QR_UNIVERSE=sp1500; None on sp900/sp500 paths.
        smallcap_fundamentals_coverage_pct=_pilot_smallcap_coverage_pct,
        smallcap_null_rate_pct=_pilot_smallcap_null_rate_pct,
        smallcap_cik_resolution_pct=_pilot_smallcap_cik_resolution_pct,
        # Issue #177 PR-A (0.10.24-phase8pilot) — shadow trimmed-median blast-radius
        # metric. Count of universe tickers whose MoS SIGN would flip under the
        # shadow trimmed median vs the live median. Decision-critical gate for the
        # follow-up PR that wires median_trimmed → mos_pct. None when the
        # computation failed or all tickers had null median_trimmed.
        median_trim_delta_count=median_trim_delta_count,
        # Post-split share-lag defense (defense layer 35, 0.10.25-phase8pilot,
        # Rule 18 observability). Populated from the Step 3b correction pass.
        # Zero is a valid value (pass ran, no splits found); None semantics
        # would mean the pass was entirely skipped (shouldn't happen in
        # production since the try/except sets zeros on failure).
        post_split_share_lag_count=(
            post_split_correction_applied_count + post_split_veto_count
        ),
        post_split_correction_applied_count=post_split_correction_applied_count,
        post_split_veto_count=post_split_veto_count,
        # PR-1 cross-source share-count-corruption shadow (0.10.26-phase8pilot,
        # Rule 18 observability-first). Aggregated from the Step 8 per-ticker
        # grading pass in compute_cross_source_corruption_shadow(). All 4 fields
        # are None on failure (graceful-degradation) — backward-compatible with
        # legacy consumers.  PR-2 will wire the actual veto/correction once the
        # first cron confirms the grades.
        cross_source_corruption_correct_candidate_count=cross_source_corruption_correct_candidate_count,
        cross_source_corruption_veto_candidate_count=cross_source_corruption_veto_candidate_count,
        cross_source_corruption_ratio_disagreement_count=cross_source_corruption_ratio_disagreement_count,
        cross_source_corruption_inferred_ratio_by_ticker=(
            cross_source_corruption_inferred_ratio_by_ticker
            if cross_source_corruption_inferred_ratio_by_ticker
            else None
        ),
        # S&P 1500 Slice 4 — ADV liquidity backstop (defense layer 36,
        # 0.10.29-phase8pilot, Rule 18 observability-before-wiring).
        # Universe-wide count of tickers where the ``low_liquidity``
        # annotate fired on this cron run. Expected base rate for S&P 900:
        # near-zero (large-caps all clear $5M/day comfortably); designed
        # for S&P 1500 small-cap exposure. Zero is valid (counter ran,
        # no tickers fired); None semantics would indicate the counter
        # was never reached (shouldn't happen in production).
        low_liquidity_annotate_count=low_liquidity_annotate_count,
        # Issue #542 Slice-8 Bonferroni shadow counter (0.10.30-phase8pilot,
        # Rule 18 observability-before-wiring). SHADOW / OBSERVABILITY-ONLY —
        # live scores, flags, rankings are byte-identical. Methodology-scientist
        # must review first cron's counts before any threshold is promoted.
        # None on failure (graceful-degradation) or pre-0.10.30 legacy snapshots.
        bonferroni_shadow_flip_count=bonferroni_shadow_flip_count,
        bonferroni_shadow_live_fire_count=bonferroni_shadow_live_fire_count,
        bonferroni_shadow_provisional_fire_count=bonferroni_shadow_provisional_fire_count,
        # Issue #587 (0.10.32-phase8pilot) — Rule 18 observability counter for
        # the low-applicability floor delta (RE-BASE-WITH-FLOOR recalibration).
        # Counts tickers firing ``extreme_estimate_majority`` EXCLUSIVELY via the
        # new floor (n_applicable ≤ 3 AND n_extreme ≥ 2 AND strict-majority)
        # but NOT via the old 3-of-6 baseline. Pre-measured delta: 16 tickers
        # (GFF, SMTC, DD, NRG, LGIH, GEV, BILL, TTWO, HASI, HIMS, CRWD, MSGS,
        # NABL, CHTR, COKE, EMBC) on cron 8c89a5af0. Annotate-only; defense
        # layer UNCHANGED at 36.
        extreme_estimate_majority_lowapp_count=extreme_estimate_majority_lowapp_count,
        # Two-factor value_trap_risk shadow counter (0.10.33-phase8pilot, Rule 18).
        # SHADOW / OBSERVABILITY-ONLY — live scores, flags, rankings are byte-identical.
        # Counts tickers satisfying: (a) ROE≤Ke fires AND (b) eps_ttm > 0 AND
        # (c) ticker P/E < sector-peer median P/E.  Methodology-scientist gate:
        # review the ratio of this count to value_trap_risk_count_with_sector_coe
        # before wiring the second-leg into the live warning path.
        value_trap_risk_two_factor_shadow_count=value_trap_risk_two_factor_shadow_count,
        # Proposal F — IC half-life monitor (0.10.34-phase8pilot, Rule 18
        # observability-before-wiring).  SHADOW / OBSERVABILITY-ONLY — live
        # scores, flags, rankings are byte-identical; defense layer UNCHANGED at 36.
        # Per-pillar fitted IC decay half-life (months) + winning model label.
        # Expected launch-day value: all per-pillar entries → None (preliminary=True
        # with ~1 week of git IC history — identical honest posture to
        # bonferroni_shadow_* / cross_source_corruption_*).
        # Co-located with QR_SKIP_DECAY_MONITOR guard (see block above).
        pillar_ic_half_life_months=pillar_ic_half_life_months or None,
        pillar_ic_decay_fit_model=pillar_ic_decay_fit_model or None,
        # Proposal D — market-regime diagnostic (0.10.36-phase8pilot, Rule 18).
        # WRITE-ONLY / OBSERVABILITY-ONLY — live scores, flags, rankings are
        # byte-identical.  Defense layer UNCHANGED at 36.
        # Breadth: % of the ranked universe whose latest close > 200-day SMA.
        # Regime label: "risk_on" / "neutral" / "risk_off" (Tier-3 thresholds,
        # REGIME_RISK_ON_THRESHOLD=60% / REGIME_RISK_OFF_THRESHOLD=40%).
        # Rejection-as-tilt: Welch-Goyal 2008 *RFS* 21(4) — no tilt, ever.
        market_breadth_above_200dma_pct=market_breadth_above_200dma_pct,
        market_regime_state=market_regime_state,
        # Proposal A — shrinkage composite diagnostics (0.10.37-phase8pilot,
        # Rule 18 observability-first).
        # SHADOW / OBSERVABILITY-ONLY — live scores, flags, rankings are
        # byte-identical (SHRINKAGE_LAMBDA_PIN=1.0 + all pillars preliminary
        # → blended_w == PHASE3_EFFECTIVE_WEIGHTS at launch).
        # Defense layer UNCHANGED at 36.
        shrinkage_lambda=_shrinkage_lambda,
        shrinkage_lambda_applied=_shrinkage_lambda_applied,
        ic_weight_by_pillar=_ic_weight_by_pillar,
        shrinkage_blended_weight_by_pillar=_shrinkage_blended_weight_by_pillar,
        n_preliminary_pillars=_n_preliminary_pillars,
        shrinkage_weights_degenerate=_shrinkage_weights_degenerate,
        # Proposal C-2 — MoS tilt shadow canary (0.10.38-phase8pilot, Rule 18).
        # SHADOW / OBSERVABILITY-ONLY — live scores, flags, rankings are
        # byte-identical.  None when backtest_pit.json is absent or the
        # per-rebalance delta field is missing (first cron after a cold clone
        # or when the backfill was not re-run since C-2 landed).
        # Defense layer UNCHANGED at 36.
        mos_tilt_shadow_max_delta_pp=_mos_tilt_shadow_max_delta_pp,
        # Proposal C-1 — high-conviction gate counters (0.10.39-phase8pilot, Rule 18).
        # PURELY ADDITIVE / OBSERVABILITY-ONLY — live scores, flags, rankings are
        # byte-identical.  Measures the marginal bite of the loss-chance leg in the
        # ALREADY-LIVE high-conviction gate (backfill ``gate="high_conviction"``).
        # None when the helper failed (non-fatal try/except — cron never blocked).
        # Defense layer UNCHANGED at 36.
        high_conviction_count=_hc_count,
        # Marginal-bite denominator: passes legs 1-4 only (loss-chance omitted).
        # bite = ex_loss_chance_count − hc_count.  Both None on helper failure.
        high_conviction_ex_loss_chance_count=_hc_ex_loss_chance_count,
        # below_floor: True if ANY rebalance leg in backtest_pit.json has
        # eligible_high_conviction_count < 5 (ADAPTIVE_MIN_PICKS).
        # None when the artifact is absent or unreadable.
        high_conviction_below_floor=_hc_below_floor,
        # Proposal E — Turnover / hysteresis diagnostic + liq-capacity tilt
        # canaries (0.10.40-phase8pilot, Rule 18 observability-first).
        # SHADOW / OBSERVABILITY-ONLY — live scores, flags, rankings byte-identical.
        # Defense layer UNCHANGED at 36.  Both None when the artifact is absent
        # (first cron after cold clone or before backfill re-runs with E wiring).
        hysteresis_turnover_reduction_mean_pp=_hysteresis_turnover_reduction_mean_pp,
        low_liquidity_held_count=_low_liquidity_held_count,
        # Option-B dividend-pool-and-redeploy SHADOW canaries (issue #620,
        # 0.10.41-phase8pilot, Rule 18 observability-first).
        # SHADOW / OBSERVABILITY-ONLY — live scores, flags, rankings byte-identical.
        # Defense layer UNCHANGED at 36.
        # div_pool_shadow_terminal_nav_delta_pct: terminal NAV uplift (%) of the
        #   dividend-pooled shadow vs the live nav.adaptive (net-of-cost).
        #   Positive = dividends add value once redeployed.  None when artifact
        #   absent or nav.adaptive_div_pooled not yet in the artifact.
        # div_stream_coverage_pct: fraction of ranked tickers with ≥1 ex-date
        #   dividend entry; Rule-18 coverage canary (~40–60% expected on S&P 1500).
        #   None when QR_SKIP_DIVIDENDS=1 or Dividends column absent from all frames.
        div_pool_shadow_terminal_nav_delta_pct=_div_pool_shadow_terminal_nav_delta_pct,
        div_stream_coverage_pct=_div_stream_coverage_pct,
        # Phase 9.1 — Broad Investable US universe coverage probe (Rule 18
        # observability-before-wiring; issue #661 follow-up).
        # WRITE-ONLY / OBSERVABILITY-ONLY — live scores, flags, rankings
        # byte-identical.  Defense layer UNCHANGED at 38.
        # All six are None when QR_SKIP_BROAD_UNIVERSE=1 or when the probe
        # failed unexpectedly (graceful degradation, cron-safe).
        #
        # HARD NAMING CONSTRAINT (legal/trademark, 2026-06-29):
        #   "Broad Investable US" only — NEVER "Russell 3000" /
        #   "Russell-3000-class" / "equivalent to Russell 3000".
        #
        # HARD RULE 18 CONSTRAINT:
        #   These six fields MUST NEVER be read by scoring, composite, pillar
        #   computation, veto/flag logic, fair-price, or ``select_picks``.
        broad_universe_raw_count=_broad_universe_raw_count,
        broad_universe_candidate_count=_broad_universe_candidate_count,
        broad_universe_screened_count=_broad_universe_screened_count,
        broad_universe_price_fail_pct=_broad_universe_price_fail_pct,
        broad_universe_adv_fail_pct=_broad_universe_adv_fail_pct,
        broad_universe_coverage_pct=_broad_universe_coverage_pct,
        # Issue #16 — restatement_history weight-demotion delta counter
        # (Q3 2026 cohort audit, 0.10.43-phase9pilot, Rule 18 observability-first).
        # OBSERVABILITY-ONLY — never read by scoring or selection logic.
        # Counts "plain restater" tickers (bare restatement_history only, not
        # restatement_high_confidence) — the population whose manipulation-index
        # contribution drops 5.0→0.0 under the weight demotion (issue #16).
        # Irregularity subset (both flags) nets zero delta (hc weight rose 3→8).
        # None on failure (non-fatal try/except — cron never blocked).
        restatement_history_weight_demote_delta_count=restatement_history_weight_demote_delta_count,
    )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_rankings_json(summaries, config.DATA_DIR)
    write_metadata_json(meta, config.DATA_DIR)
    # Remove per-stock files for tickers dropped from the universe (e.g. an
    # index de-listing). The cron's `git add frontend/public/data/` stages the
    # deletions; guarded by a safety floor so a degraded run can't wipe stocks/.
    prune_orphan_stock_files((s.ticker for s in summaries), config.DATA_DIR)
    logger.info("Wrote rankings.json (%d rows) and metadata.json", len(summaries))

    # --- Step 13.5 — Research warehouse Parquet snapshot (Rule 18 observability-first).
    # Writes a point-in-time flat Parquet snapshot of all computed stock data to
    # data/warehouse/ (NOT under frontend/public — research data must NOT ship in the
    # static deploy). Nothing reads the warehouse yet; the read/query layer ships in
    # a later slice. NEVER blocks the cron — wrapped in try/except.
    # Skip via QR_SKIP_WAREHOUSE=1 (mirrors QR_SKIP_DECAY_MONITOR pattern).
    if os.environ.get("QR_SKIP_WAREHOUSE", "").lower() in ("1", "true", "yes"):
        logger.info(
            "Research warehouse SKIPPED via QR_SKIP_WAREHOUSE. "
            "No Parquet snapshot written this run."
        )
    else:
        try:
            from compute.warehouse.writer import write_run_snapshot

            _wh_row_count = write_run_snapshot(
                details=all_details,
                summaries=summaries,
                meta=meta,
                run_date=now.date(),
                warehouse_dir=config.WAREHOUSE_DIR,
            )
            logger.info(
                "Research warehouse: wrote %d rows to %s (run_date=%s)",
                _wh_row_count,
                config.WAREHOUSE_DIR,
                now.date().isoformat(),
            )
        except Exception as _wh_exc:  # noqa: BLE001
            logger.warning(
                "Research warehouse write failed (non-fatal — cron continues); "
                "snapshot skipped. Error: %s",
                _wh_exc,
            )

        # --- Step 13.5b — Portfolio / AI-pick warehouse capture (Gap 2).
        # Reads backtest_pit.json (written earlier in the cron by the PIT-backtest
        # refresh) and persists its basket composition into
        # data/warehouse/portfolio/year=<YYYY>/run_date=<ISO>/part-0.parquet
        # plus a portfolio_manifest.parquet with json-encoded meta/nav blobs.
        # Graceful: absent artifact → log warning + return 0 (never blocks cron).
        try:
            from compute.warehouse.portfolio_writer import write_portfolio_snapshot

            _wh_portfolio_count = write_portfolio_snapshot(
                run_date=now.date(),
                warehouse_dir=config.WAREHOUSE_DIR,
            )
            logger.info(
                "Research warehouse portfolio: wrote %d holding rows (run_date=%s)",
                _wh_portfolio_count,
                now.date().isoformat(),
            )
        except Exception as _wh_po_exc:  # noqa: BLE001
            logger.warning(
                "Research warehouse portfolio write failed (non-fatal — cron continues); "
                "portfolio snapshot skipped. Error: %s",
                _wh_po_exc,
            )

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
