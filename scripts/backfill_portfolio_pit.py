"""Phase 7.0 PR-2b — point-in-time portfolio backtest backfill (workflow_dispatch).

Reconstructs the AI-pick rule's HISTORICAL performance honestly. At each
quarterly rebalance date ``T`` over the backtest window it:

  1. survivorship-corrects the universe via ``members_at(T)``;
  2. rebuilds each name's fundamentals **point-in-time** — annual 10-K facts with
     ``filing_date <= T`` only (``pit_fundamentals``), the two methodology-
     mandated guardrails being (a) the *history* frame fed to the growth/quality
     pillars is filed<=T, and (b) ``current_price`` is the price ON T;
  3. re-scores the existing 8-pillar composite (frozen ``PHASE3_EFFECTIVE_WEIGHTS``);
  4. picks + weights via ``compute.portfolio.weights`` (composite rank, 2/sector
     cap, inverse-volatility weights);
  5. builds a daily gross + net NAV (``compute.portfolio.backtest``) vs the
     benchmark index series.

Methodology (ratified 2026-06-04, Option A): this is a **point-in-time PROXY**
of the forward rule — fundamental pillars use ANNUAL (not the live TTM) basis,
GICS sectors are assumed stable from today, and survivorship is corrected via
the membership ledger. See ``meta.disclaimer`` in the output.

**v1 scope decisions (flagged for methodology / reviewer):**
  * **No defense-layer veto replay.** Selection is composite-rank only (NO sector
    cap — removed 2026-06-06; the basket concentrates by composite alone); the 7
    active vetoes are NOT recomputed point-in-time (they need the cross-source /
    manipulation layer). DISCLOSED — a `value-trap`-style name can appear in a
    historical pick that the live rule would have vetoed. Tracked as the PR-2c
    follow-up.
  * **NAV per holding count N=1..``MAX_PICKS`` (10).** At each rebalance the top-N
    picks are inverse-vol weighted and the artifact stores a daily NAV series for
    every N, so the PR-4 count slider (1-10) re-runs the backtest line vs the index
    directly (no client-side re-derivation). ``DEFAULT_COUNT`` (5) is the slider's
    landing position. Each rebalance also stores its ranked holdings + ``weights_by_count``.

**Run** (CI ``workflow_dispatch`` — needs warm price + fundamentals_history
caches; the dev sandbox has neither, so this script is CI-validated, not
locally-run): ``python -m scripts.backfill_portfolio_pit [--start YYYY-MM-DD]``.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot, fetch_fundamentals_history
from compute.ingest.historical_universe import members_at
from compute.ingest.prices import fetch_prices
from compute.ingest.universe import get_sp500_constituents
from compute.output.writer import write_backtest_pit_json
from compute.portfolio.backtest import (
    DEFAULT_COST_BPS_PER_SIDE,
    align_benchmark_nav,
    build_portfolio_nav,
    quarterly_rebalance_dates,
)
from compute.portfolio.pit_fundamentals import pit_history_rows, pit_snapshot_fields
from compute.portfolio.weights import (
    MAX_PICKS,
    PickCandidate,
    inverse_vol_weights,
    select_picks,
    trailing_return_sigma,
)
from compute.scoring.composite import compute_composite, neutralize_pillar_scores
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.restatement_filings import fetch_amendments

logger = logging.getLogger(__name__)

# The slider's default landing position. The artifact carries a NAV per holding
# count N=1..MAX_PICKS (the 1-10 slider re-runs the backtest line), so this is the
# count shown before the user touches the slider — not a cap.
DEFAULT_COUNT = 5
CONSERVATIVE_COST_BPS = 25.0  # the "show the cost band" second net line
BENCHMARKS_JSON = "portfolio/benchmarks.json"
RULE_VERSION = "phase3-effective-weights"

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
    "assumed stable from today, the defense-layer vetoes are not replayed, and "
    "survivorship is corrected via the point-in-time membership ledger. Figures are "
    "gross of slippage; per McLean-Pontiff (2016) published-factor edges decay ~32% "
    "post-publication."
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


def run_backfill(start: date, end: date, *, data_dir: Path | None = None) -> Path:
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

        candidates = [
            PickCandidate(
                ticker=str(t),
                composite_score=float(composite[t]),
                sector=sector_by_ticker.get(str(t), "Unknown"),
                risk_flags=(),  # v1: no point-in-time defense-veto replay (disclosed)
            )
            for t in composite.index
        ]
        picks = select_picks(candidates, count=MAX_PICKS)  # store up to 10 holdings
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
                    }
                    for t in picks
                ],
                "weights_by_count": {
                    str(n): {t: round(w, 6) for t, w in wmap.items()}
                    for n, wmap in weights_by_count.items()
                },
            }
        )

    nav = _assemble_nav(rebalance_picks, prices_by_ticker, data_dir)

    restate_pct = (
        round(100.0 * len(restate_names) / len(picked_names), 1) if picked_names else None
    )
    disclaimer = DISCLAIMER_BASE + _insample_lag_clause(nav, start, end)
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
            "veto_layer_replayed": False,
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
    # 5-year window. The survivorship ledger is 10y-READY (covers 2016+,
    # historical_universe.EARLIEST_EVENT_DATE = 2016-01), but a true 10y backtest
    # ALSO needs the DATA layer extended — PRICES_PERIOD ("5y"), the period-blind
    # price cache, and ANNUAL_HISTORY_YEARS (5) all cap usable history at ~5y. A
    # 10y --start silently yields a 5y NAV (the 2016-2021 legs have no price /
    # fundamentals data and are dropped). Revisit when the data layer is extended
    # (heavier weekly cron — prices + fundamentals fetch/parse ~2x).
    parser.add_argument("--start", default=date(today.year - 5, today.month, 1).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    args = parser.parse_args(argv)
    run_backfill(date.fromisoformat(args.start), date.fromisoformat(args.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
