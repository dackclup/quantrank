"""Rebalance-frequency experiment: quarterly vs semiannual vs annual.

Answers: would the AI-pick portfolio perform better with ANNUAL or SEMIANNUAL
rebalancing instead of the current QUARTERLY cadence?

Design class: dev-only analysis tool — same precedent as
``scripts/analysis_veto_counterfactual.py``. Never imported by production or CI.

Methodology
-----------
Reads the shipped ``backtest_pit.json`` (``--artifact``). Each rebalance in the
artifact carries ``band_weights`` — the exact per-ticker inverse-vol weights the
engine used for the adaptive (V55.1 hysteresis band) book at that date. These
weights are the output of the engine's scoring + band logic at each quarterly
as-of date, with the production rule (composite >= 65 entry, >= 55 hold, veto
replay, uncapped book).

Frequency variants are built by FILTERING the quarterly anchor list:
  - ``quarterly`` (baseline): all 40 rebalances — indices 0, 1, 2, … 39
  - ``semiannual``:           every 2nd — indices 0, 2, 4, … 38  (~20 rebalances)
  - ``annual``:               every 4th — indices 0, 4, 8, … 36  (~10 rebalances)

The first rebalance date is IDENTICAL across all variants (2016-08-14 in the
production artifact) so the NAV windows are comparable.

Important coupling caveat (band-tenure interaction)
---------------------------------------------------
The ``band_weights`` in the artifact were produced with QUARTERLY tenure state:
a name's "carry" status (held via the 55–65 band) was evaluated once per
quarter. Under a semiannual or annual schedule, the hold-band dynamics would
differ — names might be dropped or retained differently because fewer evaluations
occur per year.

This experiment does NOT re-run the engine for each frequency. Instead, it uses
the artifact's quarterly-derived ``band_weights`` but extends each holding period
to the next KEPT rebalance. This is an APPROXIMATION — it answers the question
"what if we used the same quarterly-derived selections but rebalanced less often?"
rather than "what if the band-tenure logic itself ran semiannually/annually?".
The approximation is materially useful (it isolates the cost-savings benefit of
fewer rebalances) but is disclosed in the output ``meta.tenure_coupling_caveat``.

A full re-run with frequency-adapted tenure logic would require modifying the
engine's ``run_backfill`` function (adding a monkeypatch on
``quarterly_rebalance_dates`` inside a --full-run mode). That path is documented
in the output and can be implemented after this initial signal check.

Net-of-cost formula
-------------------
Each rebalance charges the L1 half-turnover cost::

    NAV_net *= (1 - turnover * cost_bps_per_side / 10_000)

where ``turnover = Sum |w_target_t - w_drifted_{t-1}|`` is the L1 norm of the
weight change vector (already counts both the buy and sell legs — no additional
``× 2`` is applied). ``build_portfolio_nav`` (the engine function) computes
turnover from price-drifted weight vectors between consecutive rebalances and
returns both ``turnover_by_rebalance`` and the cumulative ``net_nav``.

For the frequency variants we pass the FILTERED legs to ``build_portfolio_nav``
with the SAME per-side bps, so the longer hold periods produce real drift and the
turnover is computed correctly — not pro-rated.

Net-of-cost CAGR at bps in (0, 10, 20):
  gross_return_ratio = final_nav / base
  net_nav(bps) = NAV built by build_portfolio_nav(cost_bps_per_side=bps)
  net_cagr(bps) = (net_nav_final / base)^(1/years) - 1

SPY benchmark
-------------
Taken directly from ``nav.benchmark.spy`` in the artifact — rebased to 100 at
the first portfolio date. No re-fetch.

Decision rule (pre-registered)
-------------------------------
Switch only if annual (or semiannual) wins BOTH gross and net-of-cost CAGR
(at 10 bps/side) without a worse maxDD; otherwise quarterly stands.

Usage
-----
Typical run (full artifact replay, all three variants):
    python -m scripts.experiment_rebalance_frequency

Smoke run (fast — no assertion, minimal rebalances):
    python -m scripts.experiment_rebalance_frequency \\
        --limit-rebalances 2 --skip-baseline-assert

All three variants explicitly:
    python -m scripts.experiment_rebalance_frequency \\
        --variants quarterly,semiannual,annual

Custom artifact path:
    python -m scripts.experiment_rebalance_frequency \\
        --artifact path/to/backtest_pit.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

# Engine imports — reuse production NAV math, no re-implementation.
from compute.ingest.prices import fetch_prices
from compute.portfolio.backtest import build_portfolio_nav
from scripts.backfill_portfolio_pit import _snap_to_trading_day

_DEFAULT_ARTIFACT = Path("frontend/public/data/portfolio/backtest_pit.json")
_OUTPUT_DIR = Path("scout_out/rebalance_freq")

# Cost tiers (bps per side) reported for net-of-cost CAGR.
_COST_TIERS_BPS: tuple[float, ...] = (0.0, 10.0, 20.0)

# Tolerance for baseline-assert comparison vs artifact (float rounding over
# ~40 price-carry steps; 0.05pp CAGR and 0.1% NAV are generous for floating
# point with the same price data).
_CAGR_TOLERANCE_PP: float = 0.05  # percentage-points
_NAV_TOLERANCE_PCT: float = 0.1  # percent of rebased NAV

# Stride map: variant name -> stride (keep every Nth rebalance starting at 0).
_VARIANT_STRIDE: dict[str, int] = {
    "quarterly": 1,
    "semiannual": 2,
    "annual": 4,
}


def _load_artifact(path: Path) -> dict:
    """Load and minimally validate the artifact."""
    if not path.exists():
        print(f"ERROR: artifact not found at {path}", flush=True)
        sys.exit(1)
    art = json.loads(path.read_text())
    if "meta" not in art or "rebalances" not in art or "nav" not in art:
        print("ERROR: artifact missing required keys (meta/rebalances/nav)", flush=True)
        sys.exit(1)
    return art


def _build_closes(
    tickers: set[str], start_iso: str
) -> dict[str, dict[str, float]]:
    """Fetch price closes for all tickers from the on-disk cache.

    Returns ``{ticker: {iso_date: adj_close}}`` for dates >= start_iso.
    Tickers missing from the cache are silently omitted (weight renormalises
    in ``build_portfolio_nav`` — same behavior as the production engine).
    """
    closes: dict[str, dict[str, float]] = {}
    for ticker in sorted(tickers):
        try:
            pf = fetch_prices(ticker, period="max")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARNING: price fetch failed for {ticker}: {exc}", flush=True)
            continue
        if pf is None or len(pf) == 0:
            continue
        col = "Adj Close" if "Adj Close" in pf.columns else "Close"
        series: dict[str, float] = {}
        for ts, val in pf[col].items():
            d_str = ts.strftime("%Y-%m-%d")
            if d_str < start_iso:
                continue
            try:
                f = float(val)
            except (TypeError, ValueError):
                continue
            if f == f and f > 0:
                series[d_str] = f
        if series:
            closes[ticker] = series
    return closes


def _collect_tickers(rebalances: list[dict]) -> set[str]:
    """Collect all tickers referenced in any rebalance's band_weights."""
    out: set[str] = set()
    for rb in rebalances:
        out.update(rb.get("band_weights", {}).keys())
    return out


def _filter_rebalances(rebalances: list[dict], stride: int) -> list[dict]:
    """Return every ``stride``-th rebalance starting at index 0."""
    return [rb for i, rb in enumerate(rebalances) if i % stride == 0]


def _build_legs(
    rebalances_subset: list[dict],
    all_dates: list[str],
) -> list[tuple[str, dict[str, float]]]:
    """Convert a subset of rebalances to ``build_portfolio_nav`` leg format.

    Returns ``[(snapped_date, {ticker: weight})]``, skipping any rebalance
    whose date cannot be snapped to a trading day in ``all_dates``.
    """
    legs: list[tuple[str, dict[str, float]]] = []
    for rb in rebalances_subset:
        snapped = _snap_to_trading_day(rb["date"], all_dates)
        if snapped is None:
            continue
        bw: dict[str, float] = rb.get("band_weights", {})
        if not bw:
            continue
        legs.append((snapped, bw))
    return legs


def _all_trading_dates(closes: dict[str, dict[str, float]]) -> list[str]:
    """Union of all dates in the closes dict, sorted ascending."""
    dates: set[str] = set()
    for series in closes.values():
        dates.update(series.keys())
    return sorted(dates)


def _cagr(final_nav: float, base: float, years: float) -> float:
    """Compound annual growth rate from rebased NAV."""
    if years <= 0 or final_nav <= 0 or base <= 0:
        return float("nan")
    return (final_nav / base) ** (1.0 / years) - 1.0


def _max_drawdown(nav_series: list[float]) -> float:
    """Maximum peak-to-trough drawdown on a rebased NAV series."""
    peak = 0.0
    mdd = 0.0
    for v in nav_series:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
    return mdd


def _annualized_turnover(turnover_by_rebalance: list[float], years: float) -> float:
    """Total turnover / years — same definition as the engine reports."""
    if years <= 0:
        return float("nan")
    return sum(turnover_by_rebalance) / years


def _per_year_returns(
    nav_series: list[float], dates: list[str]
) -> dict[str, float]:
    """Calendar-year NAV returns from a rebased series.

    Uses the first and last NAV value WITHIN each calendar year to compute the
    intra-year return.  Returns ``{str(year): return_fraction}``.
    """
    year_first: dict[str, float] = {}  # year -> first NAV value in that year
    year_last: dict[str, float] = {}   # year -> last NAV value in that year
    for d, v in zip(dates, nav_series, strict=False):
        y = d[:4]
        if y not in year_first:
            year_first[y] = v
        year_last[y] = v
    return {
        y: (year_last[y] / year_first[y] - 1.0)
        for y in sorted(year_first)
        if year_first[y] > 0
    }


def _compute_variant_metrics(
    rebalances_subset: list[dict],
    closes: dict[str, dict[str, float]],
    all_dates: list[str],
    start_date: date,
    end_date: date,
    cost_tiers_bps: tuple[float, ...],
) -> dict:
    """Build NAV and derive all metrics for one frequency variant.

    Returns a dict suitable for the results JSON.
    """
    years = (end_date - start_date).days / 365.25
    legs = _build_legs(rebalances_subset, all_dates)
    if not legs:
        return {"error": "no legs resolved"}

    # Gross NAV (0 bps/side) — base for CAGR.
    gross_result = build_portfolio_nav(
        all_dates, closes, legs, cost_bps_per_side=0.0
    )
    gross_nav = gross_result["net"]  # with 0 bps "net" == "gross"
    gross_dates = gross_result["dates"]
    tbr = gross_result["turnover_by_rebalance"]

    if not gross_nav:
        return {"error": "empty NAV series"}

    gross_final = gross_nav[-1]
    gross_cagr = _cagr(gross_final, 100.0, years)
    gross_total_return = gross_final / 100.0 - 1.0
    mdd = _max_drawdown(gross_nav)
    ann_turnover = _annualized_turnover(tbr, years)

    # Per-year returns on gross NAV.
    per_year = _per_year_returns(gross_nav, gross_dates)

    # Net-of-cost NAV at each cost tier.
    net_cagr_by_bps: dict[str, float] = {}
    net_final_nav_by_bps: dict[str, float] = {}
    for bps in cost_tiers_bps:
        if bps == 0.0:
            net_result = gross_result  # already computed
        else:
            net_result = build_portfolio_nav(
                all_dates, closes, legs, cost_bps_per_side=bps
            )
        net_nav_series = net_result["net"]
        if net_nav_series:
            nf = net_nav_series[-1]
            net_final_nav_by_bps[str(int(bps))] = round(nf, 4)
            net_cagr_by_bps[str(int(bps))] = round(_cagr(nf, 100.0, years) * 100, 4)
        else:
            net_final_nav_by_bps[str(int(bps))] = None  # type: ignore[assignment]
            net_cagr_by_bps[str(int(bps))] = None  # type: ignore[assignment]

    return {
        "n_rebalances": len(rebalances_subset),
        "n_legs_used": len(legs),
        "first_rebalance": rebalances_subset[0]["date"],
        "last_rebalance": rebalances_subset[-1]["date"],
        "gross_final_nav": round(gross_final, 4),
        "gross_cagr_pct": round(gross_cagr * 100, 4),
        "gross_total_return_pct": round(gross_total_return * 100, 4),
        "max_drawdown_pct": round(mdd * 100, 4),
        "annualized_turnover": round(ann_turnover, 4),
        "total_turnover": round(sum(tbr), 4),
        "turnover_by_rebalance": [round(t, 6) for t in tbr],
        "per_year_returns": {y: round(r * 100, 2) for y, r in per_year.items()},
        "net_cagr_pct_by_bps": net_cagr_by_bps,
        "net_final_nav_by_bps": net_final_nav_by_bps,
    }


def _spy_cagr(artifact_nav: dict, years: float) -> float | None:
    """SPY total-return CAGR from the artifact's benchmark nav.spy series."""
    spy_series = artifact_nav.get("benchmark", {}).get("spy")
    if not spy_series:
        return None
    # Series is rebased to 100 at first date; final non-None value gives total return.
    final = next((v for v in reversed(spy_series) if v is not None), None)
    if final is None or final <= 0:
        return None
    return _cagr(final, 100.0, years)


def _verify_baseline(
    quarterly_metrics: dict,
    artifact_nav: dict,
    artifact_meta: dict,
    *,
    skip: bool,
) -> bool:
    """Assert quarterly variant reproduces the artifact to float tolerance.

    Checks:
      1. Final adaptive net NAV (at 10 bps/side) within _NAV_TOLERANCE_PCT.
      2. CAGR (at 10 bps/side) within _CAGR_TOLERANCE_PP.
      3. Rebalance count matches artifact meta.rebalance_count.

    Returns True if all checks pass or skip=True.
    Prints PASS/FAIL for each check.
    """
    passed = True

    # Check 1: rebalance count.
    art_n = artifact_meta.get("rebalance_count", -1)
    exp_n = quarterly_metrics.get("n_rebalances", -1)
    if art_n == exp_n:
        print(f"  [PASS] rebalance_count {exp_n} == artifact {art_n}")
    else:
        print(f"  [FAIL] rebalance_count mismatch: got {exp_n}, artifact has {art_n}")
        passed = False

    # Check 2: final NAV.
    art_nav_series = artifact_nav.get("adaptive", {}).get("net", [])
    if not art_nav_series:
        # nav.adaptive.net is the required comparison series — its absence means
        # the artifact was built without an adaptive NAV series and the gate cannot
        # run. Treat as a hard FAIL (not a silent skip) so the caller knows.
        print(
            "  [FAIL] nav.adaptive.net absent from artifact — cannot verify NAV faithfulness. "
            "Artifact may pre-date the adaptive NAV series (pre-V55 artifact). "
            "Use --skip-baseline-assert if this artifact intentionally lacks an adaptive series."
        )
        passed = False
        art_final = None
    else:
        art_final = next((v for v in reversed(art_nav_series) if v is not None), None)
        # Net at 10 bps matches the artifact (which was built with DEFAULT_COST_BPS_PER_SIDE=10).
        exp_final = quarterly_metrics["net_final_nav_by_bps"].get("10")
        if art_final is not None and exp_final is not None:
            diff_pct = abs(exp_final - art_final) / max(abs(art_final), 1.0) * 100.0
            if diff_pct <= _NAV_TOLERANCE_PCT:
                print(
                    f"  [PASS] final NAV: reconstructed {exp_final:.4f} vs artifact {art_final:.4f}"
                    f" (diff {diff_pct:.3f}% <= {_NAV_TOLERANCE_PCT}%)"
                )
            else:
                print(
                    f"  [FAIL] final NAV mismatch: reconstructed {exp_final:.4f}"
                    f" vs artifact {art_final:.4f} (diff {diff_pct:.3f}% > {_NAV_TOLERANCE_PCT}%)"
                )
                passed = False
        else:
            print(f"  [WARN] final NAV check skipped (art={art_final}, exp={exp_final})")

    # Check 3: CAGR.
    exp_cagr = quarterly_metrics["net_cagr_pct_by_bps"].get("10")
    if art_final is not None and exp_cagr is not None:
        # Reconstruct artifact CAGR from its NAV for comparison.
        dates = artifact_nav.get("dates", [])
        if dates:
            t0 = date.fromisoformat(dates[0])
            t1 = date.fromisoformat(dates[-1])
            yrs = (t1 - t0).days / 365.25
            art_cagr_pct = _cagr(art_final, 100.0, yrs) * 100.0
            diff_pp = abs(exp_cagr - art_cagr_pct)
            if diff_pp <= _CAGR_TOLERANCE_PP:
                print(
                    f"  [PASS] CAGR: reconstructed {exp_cagr:.3f}% vs artifact"
                    f" {art_cagr_pct:.3f}% (diff {diff_pp:.4f}pp <= {_CAGR_TOLERANCE_PP}pp)"
                )
            else:
                print(
                    f"  [FAIL] CAGR mismatch: reconstructed {exp_cagr:.3f}%"
                    f" vs artifact {art_cagr_pct:.3f}% (diff {diff_pp:.4f}pp"
                    f" > {_CAGR_TOLERANCE_PP}pp)"
                )
                passed = False

    if skip and not passed:
        print("  [OVERRIDE] --skip-baseline-assert: continuing despite mismatch(es).")
        return True
    return passed


def _markdown_table(results: dict, spy_cagr_pct: float | None) -> str:
    """Render a Markdown comparison table from the results dict."""
    variants = list(results.get("variants", {}).keys())
    lines: list[str] = []

    # Decision rule header.
    lines.append("## Rebalance Frequency Experiment — Results")
    lines.append("")
    lines.append(
        "**Pre-registered decision rule:** switch only if annual (or semiannual) wins"
        " BOTH gross and net-of-cost CAGR (10 bps/side) without a worse maxDD;"
        " otherwise quarterly stands."
    )
    lines.append("")
    lines.append(
        "**Tenure caveat:** semiannual/annual use quarterly-derived ``band_weights``"
        " held for longer intervals. The V55 hold-band dynamics were calibrated to"
        " quarterly tenure cycles; less-frequent evaluation would produce different"
        " carry/drop behavior. This is an approximation — cost-savings signal only."
    )
    lines.append("")

    # Main metrics table.
    headers = [
        "Metric",
        *[v.capitalize() for v in variants],
        "SPY",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    def row(label: str, extractor) -> str:
        cells = [label]
        for v in variants:
            m = results["variants"].get(v, {})
            cells.append(extractor(m))
        # SPY cell only for CAGR-comparable rows.
        if spy_cagr_pct is not None and "CAGR" in label:
            cells.append(f"{spy_cagr_pct:.2f}%")
        else:
            cells.append("—")
        return "| " + " | ".join(cells) + " |"

    lines.append(row("N rebalances", lambda m: str(m.get("n_rebalances", "—"))))
    lines.append(row("Gross CAGR", lambda m: f"{m.get('gross_cagr_pct', float('nan')):.2f}%"))
    lines.append(row("Net CAGR (0 bps)", lambda m: f"{m['net_cagr_pct_by_bps'].get('0', float('nan')):.2f}%"))
    lines.append(row("Net CAGR (10 bps)", lambda m: f"{m['net_cagr_pct_by_bps'].get('10', float('nan')):.2f}%"))
    lines.append(row("Net CAGR (20 bps)", lambda m: f"{m['net_cagr_pct_by_bps'].get('20', float('nan')):.2f}%"))
    lines.append(row("Max Drawdown", lambda m: f"{m.get('max_drawdown_pct', float('nan')):.2f}%"))
    lines.append(row("Total Return (gross)", lambda m: f"{m.get('gross_total_return_pct', float('nan')):.2f}%"))
    lines.append(row("Annualized Turnover", lambda m: f"{m.get('annualized_turnover', float('nan')):.3f}"))
    lines.append(row("Total Turnover", lambda m: f"{m.get('total_turnover', float('nan')):.3f}"))
    lines.append(row("Final NAV (gross)", lambda m: f"{m.get('gross_final_nav', float('nan')):.2f}"))
    lines.append(row("Final NAV (net 10bps)", lambda m: f"{m.get('net_final_nav_by_bps', {}).get('10', float('nan')):.2f}"))

    lines.append("")
    lines.append("### Per-Calendar-Year Returns (Gross NAV)")
    lines.append("")
    # Collect all years.
    all_years: set[str] = set()
    for v in variants:
        all_years.update(results["variants"].get(v, {}).get("per_year_returns", {}).keys())
    year_headers = ["Year", *[v.capitalize() for v in variants]]
    lines.append("| " + " | ".join(year_headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(year_headers)) + " |")
    for y in sorted(all_years):
        cells = [y]
        for v in variants:
            r = results["variants"].get(v, {}).get("per_year_returns", {}).get(y)
            cells.append(f"{r:.1f}%" if r is not None else "—")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("### Net-of-Cost CAGR Detail")
    lines.append("")
    lines.append(
        "Cost model: each rebalance charges ``turnover × cost_bps_per_side``"
        " per side (round-trip = 2×). Turnover = Sum|Δweight| computed by"
        " ``compute.portfolio.backtest.build_portfolio_nav`` from drifted"
        " weight vectors (price-drift between rebalances). Gross = 0 bps/side."
    )
    lines.append("")
    cost_headers = ["BPS/side", *[v.capitalize() for v in variants]]
    lines.append("| " + " | ".join(cost_headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(cost_headers)) + " |")
    for bps in _COST_TIERS_BPS:
        bps_key = str(int(bps))
        cells = [f"{int(bps)} bps"]
        for v in variants:
            nc = results["variants"].get(v, {}).get("net_cagr_pct_by_bps", {}).get(bps_key)
            cells.append(f"{nc:.2f}%" if nc is not None else "—")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")

    # Decision readout.
    lines.append("### Decision Readout")
    lines.append("")
    if "quarterly" in results["variants"] and len(variants) > 1:
        q_gross = results["variants"]["quarterly"].get("gross_cagr_pct", float("nan"))
        q_net10 = results["variants"]["quarterly"]["net_cagr_pct_by_bps"].get("10", float("nan"))
        q_mdd = results["variants"]["quarterly"].get("max_drawdown_pct", float("nan"))
        decisions: list[str] = []
        for v in variants:
            if v == "quarterly":
                continue
            m = results["variants"].get(v, {})
            v_gross = m.get("gross_cagr_pct", float("nan"))
            v_net10 = m["net_cagr_pct_by_bps"].get("10", float("nan"))
            v_mdd = m.get("max_drawdown_pct", float("nan"))
            beats_gross = v_gross > q_gross if not (math.isnan(v_gross) or math.isnan(q_gross)) else False
            beats_net = v_net10 > q_net10 if not (math.isnan(v_net10) or math.isnan(q_net10)) else False
            mdd_ok = v_mdd <= q_mdd if not (math.isnan(v_mdd) or math.isnan(q_mdd)) else False
            passes = beats_gross and beats_net and mdd_ok
            verdict = "SWITCH" if passes else "KEEP QUARTERLY"
            diffs = f"gross Δ{v_gross - q_gross:+.2f}pp, net-10bps Δ{v_net10 - q_net10:+.2f}pp, maxDD Δ{v_mdd - q_mdd:+.2f}pp"
            decisions.append(
                f"- **{v.capitalize()}**: {verdict} ({diffs})"
                f" [beats_gross={beats_gross}, beats_net10={beats_net}, mdd_ok={mdd_ok}]"
            )
        lines.extend(decisions)
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--artifact",
        type=Path,
        default=_DEFAULT_ARTIFACT,
        help="Path to backtest_pit.json (default: frontend/public/data/portfolio/backtest_pit.json)",
    )
    ap.add_argument(
        "--variants",
        default="quarterly,semiannual,annual",
        help="Comma-separated list of variants to run (default: all three)",
    )
    ap.add_argument(
        "--limit-rebalances",
        type=int,
        default=None,
        metavar="N",
        help="Truncate the rebalance list to the first N entries (cheap smoke runs)",
    )
    ap.add_argument(
        "--skip-baseline-assert",
        action="store_true",
        help="Skip the engine-faithfulness gate (prints a loud warning; never for final analysis)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_OUTPUT_DIR,
        help="Output directory for results.json (default: scout_out/rebalance_freq)",
    )
    args = ap.parse_args(argv)

    requested_variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown = set(requested_variants) - set(_VARIANT_STRIDE.keys())
    if unknown:
        print(f"ERROR: unknown variant(s): {unknown}. Valid: {list(_VARIANT_STRIDE)}", flush=True)
        return 1

    if args.skip_baseline_assert:
        print(
            "\n*** WARNING: --skip-baseline-assert is set. The quarterly variant has NOT been"
            " verified against the shipped artifact. Any reported quarterly metrics may"
            " diverge from production. Use for smoke/plumbing checks ONLY. ***\n",
            flush=True,
        )

    # 1. Load artifact.
    print(f"Loading artifact: {args.artifact}", flush=True)
    art = _load_artifact(args.artifact)
    art_meta = art["meta"]
    art_nav = art["nav"]
    all_rebalances: list[dict] = art["rebalances"]

    if args.limit_rebalances is not None:
        all_rebalances = all_rebalances[: args.limit_rebalances]
        print(
            f"  --limit-rebalances {args.limit_rebalances}: using first"
            f" {len(all_rebalances)} rebalances",
            flush=True,
        )

    if not all_rebalances:
        print("ERROR: no rebalances in artifact (after limit).", flush=True)
        return 1

    # 2. Determine date window.
    # The NAV window starts at the first rebalance date (snapped to trading day),
    # ends at the artifact's last NAV date.
    nav_dates_from_art = art_nav.get("dates", [])
    start_iso = all_rebalances[0]["date"]
    end_date_str = nav_dates_from_art[-1] if nav_dates_from_art else all_rebalances[-1]["date"]
    start_date = date.fromisoformat(start_iso)
    end_date = date.fromisoformat(end_date_str)
    years = (end_date - start_date).days / 365.25

    # 3. Collect tickers and fetch prices.
    # Only fetch tickers that appear in the filtered variants — avoids any network
    # call for tickers not in the semiannual/annual subsets when limit is small.
    needed_tickers: set[str] = set()
    for v in requested_variants:
        stride = _VARIANT_STRIDE[v]
        for rb in all_rebalances[::stride]:
            needed_tickers.update(rb.get("band_weights", {}).keys())

    print(
        f"Fetching prices for {len(needed_tickers)} tickers"
        f" (from on-disk cache; may fall back to network if cold)...",
        flush=True,
    )
    closes = _build_closes(needed_tickers, start_iso)
    all_dates_full = _all_trading_dates(closes)
    if not all_dates_full:
        print("ERROR: no price data available for any ticker.", flush=True)
        return 1
    # Clip all_dates to the artifact's window end so the quarterly baseline's
    # final NAV is computed at the same date as nav.adaptive.net[-1]. Without
    # this clip, the experiment fetches one extra trading day beyond the artifact
    # (cached prices are fresher than the artifact's generation date) and the
    # baseline-assert NAV comparison would fail by one day's returns.
    all_dates = [d for d in all_dates_full if d <= end_date_str]
    if not all_dates:
        print(
            f"ERROR: no price data on or before the artifact's end date {end_date_str}.",
            flush=True,
        )
        return 1
    print(
        f"  Price data: {len(closes)} tickers, {all_dates[0]} to {all_dates[-1]}"
        f" ({len(all_dates)} trading days, clipped to artifact window {end_date_str})",
        flush=True,
    )

    # 4. Compute metrics for each requested variant.
    variant_results: dict[str, dict] = {}

    for variant in requested_variants:
        stride = _VARIANT_STRIDE[variant]
        subset = all_rebalances[::stride]
        print(
            f"\nVariant: {variant} (stride={stride},"
            f" {len(subset)} rebalances)...",
            flush=True,
        )
        metrics = _compute_variant_metrics(
            subset,
            closes,
            all_dates,
            start_date,
            end_date,
            _COST_TIERS_BPS,
        )
        variant_results[variant] = metrics
        if "error" in metrics:
            print(f"  ERROR: {metrics['error']}", flush=True)
        else:
            print(
                f"  Gross CAGR: {metrics.get('gross_cagr_pct', float('nan')):.2f}%"
                f"  Net CAGR (10bps): {metrics['net_cagr_pct_by_bps'].get('10', float('nan')):.2f}%"
                f"  MaxDD: {metrics.get('max_drawdown_pct', float('nan')):.2f}%"
                f"  AnnTurnover: {metrics.get('annualized_turnover', float('nan')):.3f}",
                flush=True,
            )

    # 5. Engine-faithfulness gate (baseline assert).
    # The gate fires only when quarterly was requested AND completed without error.
    # Old check ``"quarterly" not in ({"error"} & set(variant_results.get("quarterly", {})))``
    # was vacuously True (intersection of a singleton set and a dict-key set of
    # non-"error" strings is always empty). Fixed to check the actual error key.
    quarterly_ok = (
        "quarterly" in variant_results
        and "error" not in variant_results["quarterly"]
    )
    if quarterly_ok:
        print("\n--- Engine-faithfulness gate (quarterly vs artifact) ---", flush=True)
        gate_ok = _verify_baseline(
            variant_results["quarterly"],
            art_nav,
            art_meta,
            skip=args.skip_baseline_assert,
        )
        if not gate_ok:
            print(
                "\nFATAL: baseline assert FAILED. The quarterly variant does not"
                " reproduce the artifact to tolerance. Refusing to emit variant"
                " comparisons — results would be unreliable.\n"
                "Use --skip-baseline-assert to override (for plumbing smoke only).",
                flush=True,
            )
            return 2
        print("--- Gate passed ---\n", flush=True)
    elif "quarterly" in variant_results and "error" in variant_results["quarterly"]:
        print(
            f"\nFATAL: quarterly variant failed with error: "
            f"{variant_results['quarterly']['error']}. "
            "Cannot run engine-faithfulness gate without a successful quarterly baseline.",
            flush=True,
        )
        if not args.skip_baseline_assert:
            return 2
        print("[Gate skipped via --skip-baseline-assert despite quarterly error]\n", flush=True)
    elif args.skip_baseline_assert:
        print("\n[Gate skipped — quarterly not in requested variants or --skip-baseline-assert set]\n", flush=True)

    # 6. SPY CAGR from the artifact benchmark series.
    spy_cagr = _spy_cagr(art_nav, years)
    spy_cagr_pct: float | None = round(spy_cagr * 100.0, 4) if spy_cagr is not None else None

    # 7. Assemble results payload.
    results = {
        "meta": {
            "artifact_path": str(args.artifact),
            "artifact_rule_version": art_meta.get("rule_version"),
            "artifact_generated_utc": art_meta.get("generated_utc"),
            "artifact_rebalance_count_full": art_meta.get("rebalance_count"),
            "limit_rebalances": args.limit_rebalances,
            "skip_baseline_assert": args.skip_baseline_assert,
            "window_start": start_iso,
            "window_end": end_date_str,
            "years": round(years, 4),
            "cost_tiers_bps": list(_COST_TIERS_BPS),
            "cost_formula": (
                "Per rebalance: NAV_net *= (1 - turnover * cost_bps_per_side / 10000). "
                "Turnover = Sum|w_target - w_drifted|, computed by "
                "compute.portfolio.backtest.build_portfolio_nav from price-drifted "
                "weight vectors between consecutive rebalances. "
                "cost_bps_per_side is per-side (round-trip = 2x per_side)."
            ),
            "spy_cagr_pct": spy_cagr_pct,
            "spy_source": "artifact nav.benchmark.spy (rebased, artifact window)",
            "baseline_tolerance_nav_pct": _NAV_TOLERANCE_PCT,
            "baseline_tolerance_cagr_pp": _CAGR_TOLERANCE_PP,
            "adaptive_rule": art_meta.get("adaptive_rule"),
            "requested_variants": requested_variants,
            "variant_strides": {v: _VARIANT_STRIDE[v] for v in requested_variants},
            "tenure_coupling_caveat": (
                "band_weights in the artifact were produced with QUARTERLY tenure "
                "state (V55.1 hysteresis: entry >=65, hold >=55). Under semiannual/"
                "annual schedules, the hold-band carry/drop logic would evaluate "
                "differently — names might be retained or dropped at different points. "
                "This experiment holds the quarterly-derived band_weights but extends "
                "each holding period to the next KEPT rebalance. This isolates "
                "transaction-cost savings but does NOT model frequency-adapted tenure "
                "dynamics. A full re-run with engine-level frequency control (monkeypatching "
                "quarterly_rebalance_dates in run_backfill) would capture tenure effects "
                "but requires warm caches and ~30-60 min per variant."
            ),
            "preregistered_decision_rule": (
                "Switch only if annual (or semiannual) wins BOTH gross and net-of-cost "
                "CAGR (at 10 bps/side) without a worse maxDD; otherwise quarterly stands."
            ),
        },
        "variants": variant_results,
    }

    # 8. Write output.
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "results.json"
    out_path.write_text(json.dumps(results, indent=2, allow_nan=False, default=str))
    print(f"Results written to: {out_path}", flush=True)

    # 9. Print Markdown table.
    print()
    md = _markdown_table(results, spy_cagr_pct)
    print(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
