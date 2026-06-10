"""Phase 7.0 PR-2c — point-in-time portfolio backtest backfill with veto-layer replay.

Reconstructs the AI-pick rule's HISTORICAL performance honestly. At each
quarterly rebalance date ``T`` over the backtest window it:

  1. survivorship-corrects the universe via ``members_at(T)``;
  2. rebuilds each name's fundamentals **point-in-time** — annual 10-K facts with
     ``filing_date <= T`` only (``pit_fundamentals``), the two methodology-
     mandated guardrails being (a) the *history* frame fed to the growth/quality
     pillars is filed<=T, and (b) ``current_price`` is the price ON T;
  3. re-scores the existing 8-pillar composite (frozen ``PHASE3_EFFECTIVE_WEIGHTS``);
  4. replays the 6 accounting-based active vetoes **point-in-time** against the PIT
     cross-section at T (Phase 7.0c). ``non_reliance_filing`` is EXCLUDED from the
     replay (no 8-K Item-4.02 history in the loaded PIT data — see
     ``meta.vetoes_not_replayed``); replayed veto state drives ``select_picks`` as in
     the live rule, and vetoed candidates are recorded in
     ``rebalances[i].vetoed_pick_candidates``;
  5. picks + weights via ``compute.portfolio.weights`` (composite rank,
     inverse-volatility weights, NO sector cap);
  6. builds a daily gross + net NAV (``compute.portfolio.backtest``) vs the
     benchmark index series.
  7. exports per-rebalance supplementary fields: ``full_ranked`` (top-40 by
     composite), ``mos_pct`` on each holding, ``sector_weights_by_count``,
     ``high_conviction_count``.

Methodology (ratified 2026-06-04, Option A): this is a **point-in-time PROXY**
of the forward rule — fundamental pillars use ANNUAL (not the live TTM) basis,
GICS sectors are assumed stable from today, and survivorship is corrected via
the membership ledger. See ``meta.disclaimer`` in the output.

**Veto replay scope (Phase 7.0c):**
  * Six of the seven active vetoes are replayed PIT:
      - ``data_quality_input_corruption`` — snapshot-only (TBVPS / revenue patterns)
      - ``altman_distress`` — Altman Z″ from PIT balance-sheet snapshot
      - ``sloan_accruals_top_decile`` — (NI−CFO)/TA, cross-section at T
      - ``net_issuance_top_decile`` — ln(shares_t/shares_{t-12m}), within-sector at T
      - ``beneish_manipulation_veto`` — 8-ratio M-score from PIT snapshot + history
      - ``dechow_manipulation_veto`` — F-score from PIT snapshot + history
  * ``non_reliance_filing`` is NOT replayed: the 8-K Item-4.02 filing history is
    not present in the pre-loaded PIT data and fetching it per-name per-rebalance
    would add EDGAR network calls not budgeted for the backfill step. Disclosed via
    ``meta.vetoes_not_replayed``.
  * When all six accounting vetoes replay cleanly, ``meta.veto_layer_replayed`` is
    ``true`` (the primary Phase 5 entry-gate metric). ``non_reliance_filing``
    appearing in ``meta.vetoes_not_replayed`` is expected and does NOT suppress the
    flag.

**Run** (CI ``workflow_dispatch`` — needs warm price + fundamentals_history
caches; the dev sandbox has neither, so this script is CI-validated, not
locally-run): ``python -m scripts.backfill_portfolio_pit [--start YYYY-MM-DD]``.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import logging
import statistics
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot, fetch_fundamentals_history
from compute.ingest.historical_universe import members_at
from compute.ingest.prices import fetch_prices
from compute.ingest.universe import get_sp500_constituents

# Reuse the LIVE cross-sectional valuation-input builders (private, but pure) so the
# PIT proxy's MoS/recommendation match the forward rule exactly. Importing them keeps
# compute/main.py untouched for PR-1 (methodology-scientist: no live main.py change
# until PR-3); a future refactor could extract them to a shared module.
from compute.main import (
    _build_historical_metrics,
    _build_peer_groupings,
    _build_universe_metrics,
)
from compute.output.writer import write_backtest_pit_json
from compute.portfolio.backtest import (
    DEFAULT_COST_BPS_PER_SIDE,
    align_benchmark_nav,
    build_portfolio_nav,
    quarterly_rebalance_dates,
)
from compute.portfolio.pit_fundamentals import pit_history_rows, pit_snapshot_fields
from compute.portfolio.weights import (
    HIGH_CONVICTION_COMPOSITE_MIN,
    HIGH_CONVICTION_LOSS_CHANCE_MAX,
    HIGH_CONVICTION_RECOMMENDATIONS,
    MAX_PICKS,
    PickCandidate,
    inverse_vol_weights,
    is_high_conviction,
    select_picks,
    trailing_return_sigma,
)
from compute.scoring.beneish import compute_beneish
from compute.scoring.composite import compute_composite, neutralize_pillar_scores
from compute.scoring.dechow_f import compute_dechow_f
from compute.scoring.loss_chance import derive_loss_chance
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.recommendation import derive_recommendation
from compute.scoring.restatement_filings import fetch_amendments
from compute.scoring.risk_overlay import compute_risk_flags
from compute.valuation.ensemble import compute_fair_price_ensemble

logger = logging.getLogger(__name__)

# The slider's default landing position. The artifact carries a NAV per holding
# count N=1..MAX_PICKS (the 1-20 slider re-runs the backtest line), so this is the
# count shown before the user touches the slider — not a cap.
DEFAULT_COUNT = 5
CONSERVATIVE_COST_BPS = 25.0  # the "show the cost band" second net line
BENCHMARKS_JSON = "portfolio/benchmarks.json"

# Phase 7.0c: +veto-replay suffix marks artifacts where veto_layer_replayed=True.
# Prior artifacts (veto_layer_replayed=False) carry the plain "phase3-effective-weights"
# version so callers can distinguish the two datasets unambiguously.
RULE_VERSION = "phase3-effective-weights+veto-replay"

# methodology-scientist RATIFY 2026-06-08 (Option B, condition C2): the backtest has
# ANNUAL 10-K data only, so the live 180d hard-stale gate (config.FILING_STALE_HARD_DAYS)
# would null the fair-price ensemble ~3 of 4 quarters. Relax the hard-stale ceiling to
# 455d FOR THE BACKTEST PIT PATH ONLY (= the SEC 75-day large-accelerated 10-K filing
# deadline + 365 + a 15d buffer = the worst-case LEGITIMATE 10-K-to-next-10-K gap; a
# genuinely skipped annual cycle is older than this and still nulls). Threaded via
# compute_fair_price_ensemble(hard_stale_days=...) — the live path NEVER sets it (keeps
# config's 180d). Provenance: GUT-FEEL-WITH-SEC-DEADLINE-RATIONALE.
BACKTEST_HARD_STALE_DAYS = 455

# The six accounting vetoes replayed point-in-time (Phase 7.0c). All derive from the
# already-loaded PIT snapshot + PIT history — no additional EDGAR fetching required.
_VETOES_REPLAYED: tuple[str, ...] = (
    "data_quality_input_corruption",
    "altman_distress",
    "sloan_accruals_top_decile",
    "net_issuance_top_decile",
    "beneish_manipulation_veto",
    "dechow_manipulation_veto",
)

# non_reliance_filing is excluded from replay: it requires 8-K Item-4.02 filing
# history from EDGAR that is NOT part of the pre-loaded PIT fundamentals data.
# Fetching it per-name per-rebalance would add O(N_picked × N_rebalances) EDGAR
# calls beyond the restatement-canary amendment fetch that already runs per-picked-
# name. The flag is a real-time check (trailing 365d), and its historical filings
# index is not available in the warm fundamentals/price caches that the backfill
# relies on. This exclusion is honest: the live rule does enforce it; the backtest
# is a proxy that cannot fully replay it point-in-time.
_VETOES_NOT_REPLAYED: tuple[dict[str, str], ...] = (
    {"name": "non_reliance_filing", "reason": "no_8k_history_in_pit_data"},
)

# Maximum number of top-composite names exported per rebalance as full_ranked.
# 40 dicts × ~5 fields × 2-4 bytes/field ≈ 0.3 KB per rebalance; 40 rebalances
# ≈ 12 KB — negligible vs the NAV series. Keeps the artifact < ~2 MB total.
_FULL_RANKED_LIMIT = 40

# Method caveats only. The result-dependent in-sample lead/lag sentence (vs SPY) is
# computed from the ACTUAL NAV and appended in run_backfill so the disclaimer can never
# contradict the line shown (methodology-scientist: the old "upper bound" tail implied a
# win and misframed a losing default).
DISCLAIMER_BASE = (
    "Illustrative backtest, not investment advice. This is a point-in-time PROXY "
    "of QuantRank's ranking rule, not a replay of the live composite: at each "
    "historical rebalance it re-runs the current frozen 8-pillar weights using only "
    "data filed on or before that date, but fundamental pillars use ANNUAL (10-K) "
    "figures in place of the live trailing-twelve-month basis, GICS sectors are "
    "assumed stable from today, and survivorship is corrected via the point-in-time "
    "membership ledger. The basket holds ONLY high-conviction names — Strong Buy / "
    "Buy rated, undervalued (margin of safety > 0), composite >= 50 and loss-chance "
    "<= 45 — taking the top names by composite among those (a name that decays out "
    "of the gate is dropped at the next rebalance). The recommendation + 6-method "
    "valuation layer is replayed point-in-time, with the fair-value staleness gate "
    "widened to ~15 months for the once-a-year 10-K cadence (vs the live 180-day "
    "gate). Six of the seven active accounting vetoes (Altman distress, Sloan "
    "accruals, net issuance, Beneish manipulation, Dechow F-score, and data-quality "
    "corruption) are replayed point-in-time against the PIT cross-section; "
    "non_reliance_filing (8-K Item 4.02) is NOT replayed — no 8-K history is "
    "available in the loaded PIT data — so a name that filed an Item 4.02 in the "
    "trailing year at a historical rebalance will appear in this backtest un-vetoed. "
    "Net figures charge a modeled per-side spread cost (10-25 bps on turnover) but "
    "are gross of additional market-impact slippage; per McLean-Pontiff (2016) "
    "published-factor edges decay ~32% post-publication."
)

_SNAPSHOT_FIELDS = {f.name for f in dataclasses.fields(FundamentalsSnapshot)}


def _annual_rows(history: pd.DataFrame | None) -> list[dict]:
    """Cached annual-history DataFrame -> plain rows for the pure PIT selectors.

    ISO-stringifies the date columns so the (pandas-free) ``pit_fundamentals``
    helpers can compare ``filing_date <= T`` lexically.
    """
    if history is None or len(history) == 0:
        return []
    rows: list[dict] = []
    for r in history.itertuples(index=False):
        fd = getattr(r, "filing_date", None)
        rows.append(
            {
                "metric": getattr(r, "metric", None),
                "fiscal_year": getattr(r, "fiscal_year", None),
                "value": getattr(r, "value", None),
                "filing_date": fd.isoformat() if hasattr(fd, "isoformat") else fd,
                "form_type": getattr(r, "form_type", None),
            }
        )
    return rows


def _pit_snapshot(ticker: str, cik: str, rows: list[dict], as_of: str) -> FundamentalsSnapshot:
    fields = {k: v for k, v in pit_snapshot_fields(rows, as_of).items() if k in _SNAPSHOT_FIELDS}
    return FundamentalsSnapshot(ticker=ticker, cik=cik, **fields)


def _pit_filing_lag(rows: list[dict], as_of: str, as_of_date: date) -> int | None:
    """Days from the latest 10-K filed on/before ``as_of`` (annual PIT staleness).

    The PIT snapshot (``pit_snapshot_fields``) returns only metric values, not the
    filing date, so Defense #3's lag is computed here from the SAME eligible rows
    (``form_type == "10-K"`` AND ``filing_date <= as_of``). ``None`` when no 10-K is
    public at ``as_of`` — the ensemble then reads freshness as "unknown" (NOT
    hard-stale), which is the existing behavior for a name with no filing date."""
    fds = [
        r["filing_date"]
        for r in rows
        if r.get("form_type") == "10-K"
        and isinstance(r.get("filing_date"), str)
        and r["filing_date"] <= as_of
    ]
    if not fds:
        return None
    return (as_of_date - date.fromisoformat(max(fds))).days


def _price_at(prices: pd.DataFrame, as_of_ts: pd.Timestamp) -> float | None:
    """GUARDRAIL 2 — the close on the latest trading day on or before ``as_of``."""
    if prices is None or len(prices) == 0:
        return None
    col = "Adj Close" if "Adj Close" in prices.columns else "Close"
    sliced = prices.loc[:as_of_ts, col]
    if len(sliced) == 0:
        return None
    val = sliced.iloc[-1]
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 0 else None


def _restatement_at_risk(amendments: list[dict] | None, as_of: str) -> bool:
    """True if the name filed ANY 10-K/A or 10-Q/A AFTER ``as_of``.

    Re-sourced (methodology-scientist 2026-06-05) from the SAME EDGAR filings-index
    feed the live ``restatement_history`` flag uses (``fetch_amendments`` →
    ``company.get_filings``), NOT the companyfacts-XBRL annual-fact scan it used
    before — that scan only saw amendments that re-filed a pulled annual XBRL concept,
    so it systematically under-counted partial / non-financial amendments and reported
    a misleading 0.0%. This is a CONSERVATIVE look-ahead-contamination canary: a
    post-as-of amendment means the cached companyfacts data the backtest read at T may
    silently reflect that later restatement. It does NOT restrict to the specific
    fiscal years that fed the as-of score (the filings index carries no period map), so
    it over- rather than under-counts — the safe direction for a disclosed canary.
    ``None`` (fetch failed / no EDGAR identity) is treated as "unresolved", NOT at-risk
    (the caller counts those separately).
    """
    if not amendments:
        return False
    for f in amendments:
        fd = f.get("filing_date")
        if isinstance(fd, str) and fd > as_of:
            return True
    return False


def _insample_lag_clause(nav: dict, start: date, end: date) -> str:
    """Result-dependent honesty sentence appended to the disclaimer.

    States how the DEFAULT-count NET line actually did vs SPY in-sample, computed from
    the produced NAV so the disclaimer can never claim a win the chart contradicts
    (methodology-scientist 2026-06-05). Falls back to a generic caveat if either series
    is unavailable.
    """
    series = nav.get("by_count", {}).get(str(DEFAULT_COUNT), {})
    net = series.get("net") or []
    spy = nav.get("benchmark", {}).get("spy") or []
    p = next((v for v in reversed(net) if v is not None), None)
    s = next((v for v in reversed(spy) if v is not None), None)
    if p is None or s is None:
        return (
            " Past performance, even favorable, does not predict future results; read the"
            " full holding-count ladder, not any single line."
        )
    verb = "underperformed" if p < s - 0.5 else "outperformed" if p > s + 0.5 else "tracked"
    return (
        f" In this {start.year}-{end.year} sample the default {DEFAULT_COUNT}-holding net"
        f" line {verb} the S&P 500 ({p:.0f} vs {s:.0f}, both rebased to 100 at the start):"
        f" a factor-tilted, sector-CONCENTRATED book (no per-sector cap — it can hold many"
        f" names in one sector) carries higher single-sector risk and can diverge from a"
        f" cap-weighted index, in either direction, for long stretches. Any in-sample edge"
        f" is concentration- and regime-driven, not a free lunch (McLean-Pontiff 2016) —"
        f" past performance, even favorable, does not predict future results; read the full"
        f" 1-{MAX_PICKS} holding-count ladder, not any single line."
    )


def _compute_pit_risk_flags(
    snapshots: dict[str, FundamentalsSnapshot | None],
    pit_histories: dict[str, pd.DataFrame | None],
    sectors: dict[str, str],
    rebalance_date: date,
    beneish_scores: dict[str, float | None],
    dechow_scores: dict[str, float | None],
) -> dict[str, list[str]]:
    """Compute the six accounting-based active vetoes against the PIT cross-section.

    This is a SUBSET of ``compute_risk_flags`` — non_reliance_filing is excluded
    (no 8-K history in the PIT data). Sloan + NSI cross-sections are computed against
    the live cohort AT THIS REBALANCE, not today's universe, so the within-sector
    decile thresholds are PIT-correct.

    ``beneish_scores`` and ``dechow_scores`` are pre-computed per-ticker before calling
    this function (to avoid recomputing inside compute_risk_flags which doesn't call
    those scorers directly — it only applies thresholds via the inject paths).
    """
    return compute_risk_flags(
        snapshots=snapshots,
        histories={t: h for t, h in pit_histories.items() if h is not None},
        sectors=sectors,
        today=rebalance_date,  # PIT: NSI lookback anchors to T, not today
        non_reliance_by_ticker={t: False for t in snapshots},  # excluded; all False
        beneish_m_scores=beneish_scores,
        dechow_f_scores=dechow_scores,
    )


def _sector_weights_by_count(
    weights_by_count: dict[int, dict[str, float]],
    sector_by_ticker: dict[str, str],
) -> dict[str, dict[str, float]]:
    """Aggregate per-ticker weights into sector-weight maps for each count N.

    Returns ``{str(N): {sector: total_weight}}``. Sectors with zero weight in a
    given count are omitted (saves space). Weights round to 4 dp (2 dp is too coarse
    for small portfolios; 4 dp matches the inverse-vol weight precision needs).
    """
    out: dict[str, dict[str, float]] = {}
    for n, wmap in weights_by_count.items():
        by_sector: dict[str, float] = {}
        for ticker, w in wmap.items():
            s = sector_by_ticker.get(ticker, "Unknown")
            by_sector[s] = round(by_sector.get(s, 0.0) + w, 4)
        if by_sector:
            out[str(n)] = by_sector
    return out


def run_backfill(
    start: date, end: date, *, data_dir: Path | None = None, gate: str = "high_conviction"
) -> Path:
    """``gate`` selects the eligibility filter (see ``select_picks``): the production
    default ``"high_conviction"`` (Strong Buy/Buy + MoS>0 + composite>=50 +
    loss-chance<=45) or ``"veto_only"`` (the legacy composite-rank basket). The
    end-to-end WIRING (snapshot -> pillars -> composite -> NAV -> canary) is gate-
    independent, so wiring tests pass ``gate="veto_only"`` to exercise it with
    synthetic data that need not clear the conviction gate."""
    data_dir = data_dir or config.DATA_DIR
    members = get_sp500_constituents()
    current = {str(r.ticker) for r in members.itertuples(index=False)}
    cik_by_ticker = {str(r.ticker): str(r.cik) for r in members.itertuples(index=False)}
    sector_by_ticker = {str(r.ticker): str(r.sector) for r in members.itertuples(index=False)}

    # Load each name's caches ONCE (warm in CI). annual rows (PIT) + price frame.
    rows_by_ticker: dict[str, list[dict]] = {}
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    for ticker in sorted(current):
        try:
            rows_by_ticker[ticker] = _annual_rows(fetch_fundamentals_history(cik_by_ticker[ticker]))
            pf = fetch_prices(ticker)
            if pf is not None and len(pf) > 0:
                prices_by_ticker[ticker] = pf
        except Exception as e:  # noqa: BLE001 — one bad name never kills the backfill
            logger.warning("backfill: load failed for %s: %s", ticker, e)
    spy = fetch_prices("SPY")

    rebal_dates = quarterly_rebalance_dates(start, end)
    rebalances_out: list[dict] = []
    # Per rebalance: (snapped_date, {count N -> {ticker -> weight}}) for N=1..MAX_PICKS.
    # The NAV builder turns each N into its own daily NAV series; the frontend slider
    # reads the matching count.
    rebalance_picks: list[tuple[str, dict[int, dict[str, float]]]] = []
    incomplete_membership = 0
    restate_names: set[str] = set()
    picked_names: set[str] = set()
    restate_unresolved: set[str] = set()
    hc_counts: list[int] = []  # PR-1: per-rebalance high-conviction-eligible counts (C1)

    # Restatement canary — re-sourced from the EDGAR filings index (the live
    # restatement_history flag's feed) rather than companyfacts-XBRL. Amendment history
    # is per-name (filtered by filing_date > T per rebalance), so fetch it LAZILY per
    # picked name and memoize: only the ~50-80 names ever selected hit EDGAR, not the
    # full ~500 universe. Lookback spans the whole window back from today.
    amend_window_days = (date.today() - start).days + 60
    amend_memo: dict[str, list[dict] | None] = {}

    def _amendments(ticker: str) -> list[dict] | None:
        if ticker not in amend_memo:
            try:
                amend_memo[ticker] = fetch_amendments(ticker, lookback_days=amend_window_days)
            except Exception as e:  # noqa: BLE001 — a canary fetch never kills the backfill
                logger.warning("backfill: amendment fetch failed for %s: %s", ticker, e)
                amend_memo[ticker] = None
        return amend_memo[ticker]

    for T in rebal_dates:
        T_iso = T.isoformat()
        T_ts = pd.Timestamp(T)
        res = members_at(T, current_universe=current)
        if not res.is_complete:
            incomplete_membership += 1
            continue  # don't trust a leg whose survivorship is degraded
        cohort = res.tickers

        inputs: dict[str, TickerInputs] = {}
        for ticker in cohort:
            rows = rows_by_ticker.get(ticker, [])
            prices = prices_by_ticker.get(ticker)
            if prices is None:
                continue
            cur_px = _price_at(prices, T_ts)
            if cur_px is None:
                continue
            snap = _pit_snapshot(ticker, cik_by_ticker.get(ticker, ""), rows, T_iso)
            # GUARDRAIL 1 — history fed to growth/quality pillars is filed<=T.
            pit_hist = pd.DataFrame(pit_history_rows(rows, T_iso)) if rows else None
            inputs[ticker] = TickerInputs(
                snapshot=snap,
                prices=prices.loc[:T_ts],
                benchmark_prices=spy.loc[:T_ts] if spy is not None else None,
                current_price=cur_px,
                sector=sector_by_ticker.get(ticker, "Unknown"),
                history=pit_hist,
            )

        if not inputs:
            continue

        pillar_df = compute_all_pillars(inputs)
        pillar_df, _ = neutralize_pillar_scores(pillar_df)
        composite = compute_composite(pillar_df)

        # --- Point-in-time valuation + recommendation replay. Reuse the LIVE
        # cross-sectional builders on THIS rebalance's PIT cohort so MoS / recommendation
        # / loss-chance match the forward rule. PR-1 added this to COUNT eligibles; PR-2
        # now FEEDS it into selection — `select_picks(gate=gate)` (production default
        # "high_conviction") holds only names clearing Strong Buy/Buy + MoS>0 +
        # composite>=50 + loss-chance<=45. eligible_high_conviction_count stays as the
        # per-rebalance diagnostic (C1 cleared: median 52 >> DEFAULT_COUNT).
        snaps_by_ticker = {t: inp.snapshot for t, inp in inputs.items()}
        hist_by_ticker = {
            t: inp.history for t, inp in inputs.items() if inp.history is not None
        }
        val_df = pd.DataFrame(
            [
                {"ticker": t, "current_price": inp.current_price, "sector": inp.sector}
                for t, inp in inputs.items()
            ]
        )
        universe_metrics = _build_universe_metrics(snaps_by_ticker, val_df)
        _by_sub, by_sector_panel, broad_ex_fin_util = _build_peer_groupings(val_df)
        historical_metrics = _build_historical_metrics(hist_by_ticker, snaps_by_ticker)

        mos_by_ticker: dict[str, float | None] = {}
        rec_by_ticker: dict[str, str | None] = {}
        lc_by_ticker: dict[str, float | None] = {}
        for raw_t in composite.index:
            t = str(raw_t)
            inp = inputs.get(t)
            snap_t = snaps_by_ticker.get(t)
            if inp is None or snap_t is None:
                continue
            sector_panel = [x for x in by_sector_panel.get(inp.sector, []) if x != t]
            broad_panel = [x for x in broad_ex_fin_util if x != t]
            tier_panel = {
                "sub_industry": [],  # GICS sub-industry not carried PIT -> sector fallback
                "industry": [],
                "sector": sector_panel,
                "broad": broad_panel,
            }
            peer_panels = {"pe": tier_panel, "pb": tier_panel, "ev_ebitda": tier_panel}
            mos: float | None = None
            try:
                result, _flags = compute_fair_price_ensemble(
                    ticker=t,
                    snap=snap_t,
                    sector=inp.sector,
                    sub_industry=None,
                    industry=None,
                    current_price=inp.current_price,
                    filing_lag_days_value=_pit_filing_lag(rows_by_ticker.get(t, []), T_iso, T),
                    peer_panels=peer_panels,
                    universe_metrics=universe_metrics,
                    historical_metrics=historical_metrics,
                    hard_stale_days=BACKTEST_HARD_STALE_DAYS,
                )
                mos = result.mos_pct
            except Exception as e:  # noqa: BLE001 — one bad name never kills the backfill
                logger.warning("backfill: ensemble failed for %s @ %s: %s", t, T_iso, e)
            cs = float(composite[t])
            mos_by_ticker[t] = mos
            rec_by_ticker[t] = derive_recommendation(
                composite_score=cs, risk_flags=(), valuation_warnings=(), mos_pct=mos
            )
            lc_by_ticker[t] = derive_loss_chance(
                composite_score=cs, risk_flags=(), valuation_warnings=(), mos_pct=mos
            )

        # --- Phase 7.0c: PIT veto-layer replay ---
        # Compute Beneish and Dechow scores per-ticker before calling compute_risk_flags
        # (the inject paths in compute_risk_flags take pre-computed scores as dicts).
        # Using PIT pit_hist ensures the prior-year lookbacks are also filed<=T.
        beneish_scores: dict[str, float | None] = {}
        dechow_scores: dict[str, float | None] = {}
        for t, inp in inputs.items():
            snap_t = snaps_by_ticker.get(t)
            pit_hist_t = inp.history  # already filed<=T (GUARDRAIL 1 above)
            try:
                br = compute_beneish(snap_t, pit_hist_t)
                beneish_scores[t] = br.m_score
            except Exception as e:  # noqa: BLE001
                logger.warning("backfill: beneish failed for %s @ %s: %s", t, T_iso, e)
                beneish_scores[t] = None
            try:
                dr = compute_dechow_f(snap_t, pit_hist_t)
                dechow_scores[t] = dr.f_score
            except Exception as e:  # noqa: BLE001
                logger.warning("backfill: dechow failed for %s @ %s: %s", t, T_iso, e)
                dechow_scores[t] = None

        pit_risk_flags = _compute_pit_risk_flags(
            snapshots=snaps_by_ticker,
            pit_histories={t: inp.history for t, inp in inputs.items()},
            sectors={t: inp.sector for t, inp in inputs.items()},
            rebalance_date=T,
            beneish_scores=beneish_scores,
            dechow_scores=dechow_scores,
        )

        # Build full_ranked: top-_FULL_RANKED_LIMIT names by composite at this rebalance,
        # including vetoed names (the rank excludes no one — vetoed names just can't be
        # picked). Provides the raw composite leaderboard the veto selection effect
        # analysis reads from.
        composite_sorted = sorted(
            [(str(t), float(composite[t])) for t in composite.index],
            key=lambda x: -x[1],
        )
        full_ranked = [
            {
                "ticker": t,
                "composite_score": round(cs, 2),
                "sector": sector_by_ticker.get(t, "Unknown"),
                "mos_pct": (
                    round(mos_by_ticker[t], 2) if mos_by_ticker.get(t) is not None else None
                ),
                "recommendation": rec_by_ticker.get(t),
            }
            for t, cs in composite_sorted[:_FULL_RANKED_LIMIT]
        ]

        candidates = [
            PickCandidate(
                ticker=str(t),
                composite_score=float(composite[t]),
                sector=sector_by_ticker.get(str(t), "Unknown"),
                risk_flags=tuple(pit_risk_flags.get(str(t), [])),  # PIT veto flags
                recommendation=rec_by_ticker.get(str(t)),
                mos_pct=mos_by_ticker.get(str(t)),
                loss_chance_pct=lc_by_ticker.get(str(t)),
            )
            for t in composite.index
        ]
        # Fast O(1) lookup for the high_conviction_count per-pick computation below.
        candidates_by_ticker: dict[str, PickCandidate] = {c.ticker: c for c in candidates}
        # PR-2: the high-conviction gate now DRIVES selection (C1 cleared on PR-1's
        # backfill — median eligible 52 >> DEFAULT_COUNT). eligible_high_conviction_count
        # stays as the per-rebalance diagnostic; picks = top-N BY COMPOSITE among the
        # gate-eligible names (Strong Buy/Buy + MoS>0 + composite>=50 + loss-chance<=45).
        high_conviction_count = sum(1 for c in candidates if is_high_conviction(c))
        mos_positive_count = sum(
            1 for c in candidates if c.mos_pct is not None and c.mos_pct > 0.0
        )
        hc_counts.append(high_conviction_count)

        # Phase 7.0c: Record names that would have been top-MAX_PICKS picks by composite
        # but were excluded by veto flags. These are the "selection effect" names — the
        # headline measurement of whether the veto layer rescues or suppresses picks.
        # We collect candidates that: (a) have at least one active veto flag, and
        # (b) rank in the top MAX_PICKS by composite among all candidates, so they
        # WOULD have appeared if the veto layer were absent.
        vetoed_pick_candidates: list[dict] = []
        top_n_by_composite = sorted(candidates, key=lambda c: -c.composite_score)[:MAX_PICKS]
        for c in top_n_by_composite:
            flags = list(c.risk_flags)
            if flags:  # has at least one active veto -> would have been in top-N but vetoed
                vetoed_pick_candidates.append(
                    {
                        "ticker": c.ticker,
                        "composite_score": round(c.composite_score, 2),
                        "flags": flags,
                    }
                )

        # Sell-eviction is implicit: a name that decayed out of the gate this quarter
        # is absent from the eligible set and won't be re-picked (the basket is rebuilt
        # from scratch each rebalance).
        picks = select_picks(candidates, count=MAX_PICKS, gate=gate)
        if not picks:
            continue

        sigmas: dict[str, float] = {}
        for t in picks:
            closes = prices_by_ticker[t].loc[:T_ts]
            col = "Adj Close" if "Adj Close" in closes.columns else "Close"
            sig = trailing_return_sigma(closes[col].tolist())
            if sig is not None:
                sigmas[t] = sig
        # Per-count inverse-vol weights: for each selectable basket size N=1..MAX_PICKS,
        # weight the top-N picks by inverse vol (the SAME ratified rule, applied to the
        # top-N subset of THIS rebalance's cohort). The 1-10 slider reads
        # weights_by_count[N]; _assemble_nav builds a NAV per N from these.
        weights_by_count: dict[int, dict[str, float]] = {}
        for n in range(1, MAX_PICKS + 1):
            sub = {t: sigmas[t] for t in picks[:n] if t in sigmas}
            w = inverse_vol_weights(sub) if sub else {}
            if w:
                weights_by_count[n] = w
        if not weights_by_count:
            continue  # no name in this leg had a computable 90d sigma
        rebalance_picks.append((T_iso, weights_by_count))

        # Contamination canary tracks the FULL selectable set (top-MAX_PICKS) — any of
        # these names can surface once the user slides the count up. A name whose
        # amendment fetch failed is "unresolved" (counted separately), not at-risk.
        picked_names.update(picks)
        for t in picks:
            amends = _amendments(t)
            if amends is None:
                restate_unresolved.add(t)
            elif _restatement_at_risk(amends, T_iso):
                restate_names.add(t)

        # Phase 7.0c: sector_weights_by_count — derived per-N sector-weight map.
        sw_by_count = _sector_weights_by_count(weights_by_count, sector_by_ticker)

        rebalances_out.append(
            {
                "date": T_iso,
                "members_complete": True,
                "holdings": [
                    {
                        "ticker": t,
                        "composite_score": round(float(composite[t]), 2),
                        "sector": sector_by_ticker.get(t, "Unknown"),
                        "sigma_90d": round(sigmas[t], 6) if t in sigmas else None,
                        # Phase 7.0c: signed MoS% per holding (None-safe).
                        "mos_pct": (
                            round(mos_by_ticker[t], 2)
                            if mos_by_ticker.get(t) is not None
                            else None
                        ),
                    }
                    for t in picks
                ],
                "weights_by_count": {
                    str(n): {t: round(w, 6) for t, w in wmap.items()}
                    for n, wmap in weights_by_count.items()
                },
                # PR-1 observability (not yet driving selection): how many cohort names
                # would clear the high-conviction gate / have positive MoS this rebalance.
                "eligible_high_conviction_count": high_conviction_count,
                "mos_positive_count": mos_positive_count,
                # Phase 7.0c: new fields.
                # full_ranked: top-_FULL_RANKED_LIMIT names by composite (including vetoed);
                # enables rank-banding + sector-cap experiments.
                "full_ranked": full_ranked,
                # high_conviction_count: how many of the MAX_PICKS picks cleared
                # the high-conviction gate at this rebalance (distinct from the
                # cohort-wide eligible_high_conviction_count above).
                "high_conviction_count": sum(
                    1 for t in picks
                    if is_high_conviction(candidates_by_ticker.get(t, PickCandidate(
                        ticker=t, composite_score=0.0, sector="Unknown"
                    )))
                ),
                # sector_weights_by_count: {str(N): {sector: total_weight}}.
                "sector_weights_by_count": sw_by_count,
                # vetoed_pick_candidates: names that would have appeared in the top-N
                # composite basket but were excluded by at least one active veto.
                "vetoed_pick_candidates": vetoed_pick_candidates,
            }
        )

    nav = _assemble_nav(rebalance_picks, prices_by_ticker, data_dir)

    restate_pct = (
        round(100.0 * len(restate_names) / len(picked_names), 1) if picked_names else None
    )
    disclaimer = DISCLAIMER_BASE + _insample_lag_clause(nav, start, end)

    # Phase 7.0c: veto_layer_replayed is True when all six accounting vetoes were
    # included in the replay (non_reliance_filing is deliberately excluded and
    # disclosed in vetoes_not_replayed — this does NOT suppress the True flag).
    # The flag answers: "did the backtest include the accounting veto layer?" = yes.
    payload = {
        "meta": {
            "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule_version": RULE_VERSION,
            "as_of_start": start.isoformat(),
            "as_of_end": end.isoformat(),
            "rebalance_count": len(rebalances_out),
            "max_holdings": MAX_PICKS,
            "default_count": DEFAULT_COUNT,
            "default_benchmark": "spy",
            "cost_bps_per_side": DEFAULT_COST_BPS_PER_SIDE,
            "cost_bps_conservative": CONSERVATIVE_COST_BPS,
            "incomplete_membership_count": incomplete_membership,
            "restatement_contamination_pct": restate_pct,
            "restatement_canary_source": "edgar-filings-index",
            "restatement_canary_unresolved_count": len(restate_unresolved),
            "sector_from_today": True,
            # Phase 7.0c: veto_layer_replayed=True — six of seven accounting vetoes
            # are replayed point-in-time from PIT snapshot + history. The one
            # excluded veto (non_reliance_filing) is disclosed in vetoes_not_replayed.
            "veto_layer_replayed": True,
            "vetoes_replayed": list(_VETOES_REPLAYED),
            "vetoes_not_replayed": [
                {"name": v["name"], "reason": v["reason"]}
                for v in _VETOES_NOT_REPLAYED
            ],
            # PR-2 (Phase 7): the recommendation/valuation layer is replayed point-in-time
            # AND now DRIVES selection (gate_active=True) — the basket holds only
            # high-conviction names. C1 cleared on PR-1's backfill (median eligible 52 >>
            # default_count). The cross-source manipulation vetoes are still NOT replayed
            # (veto_layer_replayed stays False). high_conviction_eligible_median remains the
            # per-rebalance diagnostic (picks = top-N by composite among the eligible set).
            "recommendation_layer_replayed": True,
            "high_conviction_gate_active": gate == "high_conviction",
            "high_conviction_eligible_median": (
                statistics.median(hc_counts) if hc_counts else None
            ),
            "high_conviction_gate": {
                "recommendations": sorted(HIGH_CONVICTION_RECOMMENDATIONS),
                "mos_pct_min_exclusive": 0.0,
                "composite_min": HIGH_CONVICTION_COMPOSITE_MIN,
                "loss_chance_max": HIGH_CONVICTION_LOSS_CHANCE_MAX,
                "hard_stale_days": BACKTEST_HARD_STALE_DAYS,
            },
            "disclaimer": disclaimer,
        },
        "rebalances": rebalances_out,
        "nav": nav,
    }
    out = write_backtest_pit_json(payload, data_dir)
    logger.info(
        "backfill wrote %s — %d rebalances, %d incomplete-membership legs, restatement %.1f%%",
        out, len(rebalances_out), incomplete_membership, restate_pct or 0.0,
    )
    return out


def _snap_to_trading_day(date_iso: str, dates: list[str]) -> str | None:
    """First trading day in ``dates`` on or after ``date_iso`` (decide at T, trade the
    next open); falls back to the last trading day before it if none follows. ``dates``
    is sorted-ascending ISO strings (lexical == chronological). None only if empty."""
    if not dates:
        return None
    i = bisect.bisect_left(dates, date_iso)
    return dates[i] if i < len(dates) else dates[-1]


def _assemble_nav(
    rebalance_picks: list[tuple[str, dict[int, dict[str, float]]]],
    prices_by_ticker: dict[str, pd.DataFrame],
    data_dir: Path,
) -> dict:
    """Daily gross/net/conservative NAV for EACH holding count N=1..MAX_PICKS + benchmarks.

    ``rebalance_picks`` is ``[(as_of_date, {N: {ticker: weight}})]``. For each count N
    the matching per-rebalance weight maps become one daily NAV series (the 1-10 slider
    selects the count); ``dates`` + ``benchmark`` are shared across all counts (same
    trading calendar, same rebased index lines).
    """
    empty = {"dates": [], "benchmark": {}, "by_count": {}, "default_count": DEFAULT_COUNT}
    if not rebalance_picks:
        return empty

    held = sorted({t for _, wbc in rebalance_picks for wmap in wbc.values() for t in wmap})
    start_ts = pd.Timestamp(rebalance_picks[0][0])

    closes: dict[str, dict[str, float]] = {}
    all_dates: set[str] = set()
    for t in held:
        pf = prices_by_ticker.get(t)
        if pf is None:
            continue
        col = "Adj Close" if "Adj Close" in pf.columns else "Close"
        for ts, v in pf.loc[start_ts:, col].items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f and f > 0:
                d = ts.strftime("%Y-%m-%d")
                closes.setdefault(t, {})[d] = f
                all_dates.add(d)

    dates = sorted(all_dates)
    if not dates:
        return empty

    # Snap each calendar rebalance (quarter-end + 45d — may land on a weekend) to the
    # first trading day on/after it, so every leg fires on a real price date. The axis
    # = every trading day from the earliest snapped rebalance; each count's NAV is a
    # suffix of it, so a count first selectable at a LATER rebalance is left-padded with
    # None (the same gap contract the benchmark line uses). In a full-universe run every
    # count is present from the first rebalance and no padding occurs.
    global_start = _snap_to_trading_day(rebalance_picks[0][0], dates)
    axis = [d for d in dates if d >= global_start]

    by_count: dict[str, dict] = {}
    for n in range(1, MAX_PICKS + 1):
        legs = [
            (snapped, wbc[n])
            for d, wbc in rebalance_picks
            if n in wbc and (snapped := _snap_to_trading_day(d, dates)) is not None
        ]
        if not legs:
            continue
        gn = build_portfolio_nav(dates, closes, legs)
        cons = build_portfolio_nav(
            dates, closes, legs, cost_bps_per_side=CONSERVATIVE_COST_BPS
        )
        pad: list[float | None] = [None] * (len(axis) - len(gn["dates"]))
        by_count[str(n)] = {
            "gross": pad + gn["gross"],
            "net": pad + gn["net"],
            "net_conservative": pad + cons["net"],
            "turnover_by_rebalance": gn["turnover_by_rebalance"],
        }

    return {
        "dates": axis,
        "benchmark": _benchmark_navs(axis, data_dir),
        "by_count": by_count,
        "default_count": DEFAULT_COUNT,
    }


def _benchmark_navs(portfolio_dates: list[str], data_dir: Path) -> dict[str, list]:
    """Rebased benchmark NAVs aligned to the portfolio dates, from benchmarks.json."""
    import json

    out: dict[str, list] = {}
    path = data_dir / BENCHMARKS_JSON
    if not portfolio_dates or not path.exists():
        return out
    try:
        bench = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        logger.warning("backfill: could not read %s: %s", path, e)
        return out
    bench_dates = bench.get("dates", [])
    for sym in ("spy", "qqq", "dia", "iwm"):
        closes = bench.get(sym)
        if closes:
            out[sym] = align_benchmark_nav(portfolio_dates, bench_dates, closes)
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Phase 7.0 point-in-time portfolio backtest backfill")
    today = datetime.now(UTC).date()
    # 10-year window. The survivorship ledger covers 2016+
    # (historical_universe.EARLIEST_EVENT_DATE = 2016-01) and the DATA layer is now 10y
    # too (config.PRICES_PERIOD="10y" + fundamentals.ANNUAL_HISTORY_YEARS=10). Caveat:
    # ~15-20 tickers renamed before ~2021 (e.g. CDAY→DAY) — yfinance can't resolve the
    # historical alias from the current symbol, so their pre-rename legs are dropped and
    # the 2016-2020 cohort is slightly thinner than 2021+. The FIRST 10y backfill must run
    # via the manual backfill-portfolio.yml dispatch: the cold run (~60-85m: 10y price +
    # 10y fundamentals re-fetch + ~40 quarterly rebalances) exceeds the cron's 40m folded-
    # step cap; warm steady-state (~30-35m) fits. Requires the cache-vN-fast key bump
    # (period-blind caches) to have landed first.
    parser.add_argument("--start", default=date(today.year - 10, today.month, 1).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    args = parser.parse_args(argv)
    run_backfill(date.fromisoformat(args.start), date.fromisoformat(args.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
