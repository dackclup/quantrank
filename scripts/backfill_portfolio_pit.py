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
  * **No defense-layer veto replay.** Selection is composite-rank + sector-cap
    only; the 7 active vetoes are NOT recomputed point-in-time (they need the
    cross-source / manipulation layer). DISCLOSED — a `value-trap`-style name
    can appear in a historical pick that the live rule would have vetoed. Tracked
    as the PR-2c follow-up.
  * **Headline count = 5**, holdings stored for up to ``MAX_PICKS`` (10) per
    rebalance with their σ so the PR-4 count slider (1-10) can re-derive + re-
    weight client-side from the per-stock history.

**Run** (CI ``workflow_dispatch`` — needs warm price + fundamentals_history
caches; the dev sandbox has neither, so this script is CI-validated, not
locally-run): ``python -m scripts.backfill_portfolio_pit [--start YYYY-MM-DD]``.
"""

from __future__ import annotations

import argparse
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

logger = logging.getLogger(__name__)

HEADLINE_COUNT = 5
CONSERVATIVE_COST_BPS = 25.0  # the "show the cost band" second net line
BENCHMARKS_JSON = "portfolio/benchmarks.json"
RULE_VERSION = "phase3-effective-weights"

DISCLAIMER = (
    "Illustrative backtest, not investment advice. This is a point-in-time PROXY "
    "of QuantRank's ranking rule, not a replay of the live composite: at each "
    "historical rebalance it re-runs the current frozen 8-pillar weights using only "
    "data filed on or before that date, but fundamental pillars use ANNUAL (10-K) "
    "figures in place of the live trailing-twelve-month basis, GICS sectors are "
    "assumed stable from today, the defense-layer vetoes are not replayed, and "
    "survivorship is corrected via the point-in-time membership ledger. Figures are "
    "gross of slippage; per McLean-Pontiff (2016) published-factor edges decay ~32% "
    "post-publication — treat historical results as an upper bound, not an expectation."
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


def _restatement_at_risk(rows: list[dict], as_of: str) -> bool:
    """True if any 10-K/A was filed AFTER ``as_of`` for a fiscal year visible at T.

    The methodology-scientist's upper-bound contamination metric: a selected name
    is "at risk" of a silent companyfacts restatement overwrite if it has a later
    amendment on a year that contributed to its as-of-T score.
    """
    for r in rows:
        if r.get("form_type") == "10-K/A":
            fd = r.get("filing_date")
            if isinstance(fd, str) and fd > as_of:
                return True
    return False


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
    rebalance_weights: list[tuple[str, dict[str, float]]] = []  # (snapped_date, headline weights)
    incomplete_membership = 0
    restate_names: set[str] = set()
    picked_names: set[str] = set()

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
        full_weights = inverse_vol_weights(sigmas) if sigmas else {}

        # headline basket = top-HEADLINE_COUNT, re-weighted over just those names
        head = picks[:HEADLINE_COUNT]
        head_sig = {t: sigmas[t] for t in head if t in sigmas}
        head_weights = inverse_vol_weights(head_sig) if head_sig else {}
        if head_weights:
            rebalance_weights.append((T_iso, head_weights))

        picked_names.update(head)
        for t in head:
            if _restatement_at_risk(rows_by_ticker.get(t, []), T_iso):
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
                        "weight": round(full_weights.get(t, 0.0), 6),
                    }
                    for t in picks
                ],
            }
        )

    nav = _assemble_nav(rebalance_weights, prices_by_ticker, data_dir)

    restate_pct = (
        round(100.0 * len(restate_names) / len(picked_names), 1) if picked_names else None
    )
    payload = {
        "meta": {
            "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule_version": RULE_VERSION,
            "as_of_start": start.isoformat(),
            "as_of_end": end.isoformat(),
            "rebalance_count": len(rebalances_out),
            "max_holdings": MAX_PICKS,
            "headline_count": HEADLINE_COUNT,
            "default_benchmark": "spy",
            "cost_bps_per_side": DEFAULT_COST_BPS_PER_SIDE,
            "cost_bps_conservative": CONSERVATIVE_COST_BPS,
            "incomplete_membership_count": incomplete_membership,
            "restatement_contamination_pct": restate_pct,
            "sector_from_today": True,
            "veto_layer_replayed": False,
            "disclaimer": DISCLAIMER,
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


def _assemble_nav(
    rebalance_weights: list[tuple[str, dict[str, float]]],
    prices_by_ticker: dict[str, pd.DataFrame],
    data_dir: Path,
) -> dict:
    """Daily gross + net (+ conservative net) NAV for the headline basket + benchmarks."""
    if not rebalance_weights:
        return {"dates": [], "portfolio_gross": [], "portfolio_net": [],
                "portfolio_net_conservative": [], "benchmark": {}, "turnover_by_rebalance": []}

    held = sorted({t for _, w in rebalance_weights for t in w})
    start_iso = rebalance_weights[0][0]
    start_ts = pd.Timestamp(start_iso)

    closes: dict[str, dict[str, float]] = {}
    all_dates: set[str] = set()
    for t in held:
        pf = prices_by_ticker.get(t)
        if pf is None:
            continue
        col = "Adj Close" if "Adj Close" in pf.columns else "Close"
        series = pf.loc[start_ts:, col]
        m: dict[str, float] = {}
        for ts, v in series.items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f and f > 0:
                d = ts.strftime("%Y-%m-%d")
                m[d] = f
                all_dates.add(d)
        closes[t] = m

    dates = sorted(all_dates)
    gross_net = build_portfolio_nav(dates, closes, rebalance_weights)
    conservative = build_portfolio_nav(
        dates, closes, rebalance_weights, cost_bps_per_side=CONSERVATIVE_COST_BPS
    )

    benchmark = _benchmark_navs(dates, data_dir)
    return {
        "dates": gross_net["dates"],
        "portfolio_gross": gross_net["gross"],
        "portfolio_net": gross_net["net"],
        "portfolio_net_conservative": conservative["net"],
        "benchmark": benchmark,
        "turnover_by_rebalance": gross_net["turnover_by_rebalance"],
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
    parser.add_argument("--start", default=date(today.year - 5, today.month, 1).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    args = parser.parse_args(argv)
    run_backfill(date.fromisoformat(args.start), date.fromisoformat(args.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
