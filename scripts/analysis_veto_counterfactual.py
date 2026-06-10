"""Veto-layer counterfactual: veto book vs no-veto book on IDENTICAL data.

Answers the Phase 5 entry-gate (a) question — "does the defense layer rescue
the composite?" — by rebuilding TWO portfolio books per rebalance from a
veto-replayed ``backtest_pit.json`` (``meta.veto_layer_replayed == true``,
PR #451) and pricing both through the REAL engine functions
(``trailing_return_sigma`` / ``inverse_vol_weights`` / ``build_portfolio_nav``),
so the only difference between the books is the veto layer itself:

- **veto book** — the artifact's actual ``holdings`` (high-conviction gate WITH
  the 6-replayed-veto eligibility filter), exactly as production selected them.
- **no-veto book** — the counterfactual: every ``vetoed_pick_candidates`` entry
  that ALSO clears the conviction side of the high-conviction gate
  (Strong Buy/Buy + MoS > 0 + composite >= 50, read from ``full_ranked``'s
  deliberately pre-veto labels) is merged back at its composite rank, then the
  same dual-class dedup + top-N cut is applied. ``loss_chance_pct`` is not
  exported per full_ranked name, so the conviction-side check is one clause
  short — the no-veto book is therefore an UPPER bound on the veto layer's
  bite (a vetoed name that would also have failed the loss-chance ceiling is
  re-inserted here). 82 of 164 vetoed candidacies cleared the three checkable
  clauses on the first veto-replayed artifact (2026-06-10).

Both books are weighted and NAV'd identically (inverse-vol on trailing 90d
sigma, 35% cap, 10 bps/side net), on the same yfinance Adj Close series, so
``veto - noveto`` per N is the PURE selection effect of the veto layer.

Validation: the rebuilt veto-book net CAGR matched the artifact's
``nav.by_count[N].net`` to 0.1pp at every N on the 2026-06-10 artifact (same
engine functions + same price source), which is what licenses trusting the
no-veto leg of the comparison.

Network: fetches ~130 tickers of daily Adj Close from yfinance (one batch).
Dev-analysis tool only — never imported by production or CI.

Usage:
    python -m scripts.analysis_veto_counterfactual \
        [--artifact frontend/public/data/portfolio/backtest_pit.json] \
        [--max-n 20]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from bisect import bisect_left
from pathlib import Path

import pandas as pd

from compute.portfolio.backtest import build_portfolio_nav
from compute.portfolio.weights import (
    HIGH_CONVICTION_COMPOSITE_MIN,
    HIGH_CONVICTION_RECOMMENDATIONS,
    _company_key,
    inverse_vol_weights,
    trailing_return_sigma,
)

DEFAULT_ARTIFACT = Path("frontend/public/data/portfolio/backtest_pit.json")


def build_books(
    rebalances: list[dict], max_n: int
) -> list[tuple[str, list[str], list[str], list[tuple[str, float, str]]]]:
    """Per rebalance: (date, veto_book, no_veto_book, reinserted_names).

    The no-veto book re-inserts vetoed pick candidates that clear the checkable
    conviction-side clauses (recommendation + MoS + composite floor) at their
    composite rank, then re-applies select_picks' dual-class dedup + top-N cut.
    """
    out = []
    for rb in rebalances:
        veto = [h["ticker"] for h in rb["holdings"]]
        comp = {h["ticker"]: h["composite_score"] for h in rb["holdings"]}
        fr = {x["ticker"]: x for x in rb["full_ranked"]}
        pool = [(t, comp[t]) for t in veto]
        inserted: list[tuple[str, float, str]] = []
        for v in rb["vetoed_pick_candidates"]:
            e = fr.get(v["ticker"])
            if e is None:  # outside the exported leaderboard — cannot qualify it
                continue
            if (
                e.get("recommendation") in HIGH_CONVICTION_RECOMMENDATIONS
                and e.get("mos_pct") is not None
                and e["mos_pct"] > 0
                and v["composite_score"] >= HIGH_CONVICTION_COMPOSITE_MIN
            ):
                pool.append((v["ticker"], v["composite_score"]))
                inserted.append((v["ticker"], v["composite_score"], ",".join(v["flags"])))
        pool.sort(key=lambda x: (-x[1], x[0]))
        eligible = {t for t, _ in pool}
        no_veto: list[str] = []
        seen: set[str] = set()
        for t, _ in pool:
            key = _company_key(t)
            if key in seen:
                continue
            seen.add(key)
            no_veto.append(key if key in eligible else t)
            if len(no_veto) >= max_n:
                break
        out.append((rb["date"], veto, no_veto, inserted))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    ap.add_argument("--max-n", type=int, default=20)
    args = ap.parse_args(argv)

    import yfinance as yf  # deferred: keep module importable offline

    art = json.loads(args.artifact.read_text())
    if not art["meta"].get("veto_layer_replayed"):
        print("artifact has veto_layer_replayed=false — nothing to counterfactual", flush=True)
        return 1
    books = build_books(art["rebalances"], args.max_n)
    n_inserted = sum(len(b[3]) for b in books)
    n_candidacies = sum(len(rb["vetoed_pick_candidates"]) for rb in art["rebalances"])
    print(f"{len(books)} rebalances | conviction-side-qualified vetoed candidacies: "
          f"{n_inserted}/{n_candidacies}")

    tickers = sorted({t for _, v, nv, _ in books for t in v + nv})
    fetch = tickers + ["SPY", "QQQ"]
    print(f"fetching {len(fetch)} tickers from yfinance ...", flush=True)
    px = yf.download(
        fetch, start="2016-01-01", auto_adjust=False, progress=False, threads=True
    )["Adj Close"]
    priced = [t for t in fetch if t in px.columns and px[t].notna().sum() > 100]
    thin = sorted(set(fetch) - set(priced))
    if thin:
        print(f"WARNING — unpriced/thin (dropped, weights renormalize): {thin}")

    series = {t: px[t].dropna() for t in priced}
    closes = {
        t: {ts.strftime("%Y-%m-%d"): float(v) for ts, v in s.items() if v == v and v > 0}
        for t, s in series.items()
    }
    dates = sorted({d for m in closes.values() for d in m})

    def snap(d: str) -> str:
        i = bisect_left(dates, d)
        return dates[i] if i < len(dates) else dates[-1]

    legs: dict[tuple[str, int], list[tuple[str, dict[str, float]]]] = {}
    for d, veto, no_veto, _ in books:
        ts, sd = pd.Timestamp(d), snap(d)
        sig = {}
        for t in set(veto) | set(no_veto):
            if t not in series:
                continue
            s = trailing_return_sigma(series[t].loc[:ts].tolist())
            if s is not None:
                sig[t] = s
        for n in range(1, args.max_n + 1):
            for key, book in (("veto", veto), ("noveto", no_veto)):
                sub = {t: sig[t] for t in book[:n] if t in sig}
                w = inverse_vol_weights(sub) if sub else {}
                if w:
                    legs.setdefault((key, n), []).append((sd, w))

    navs = {k: build_portfolio_nav(dates, closes, v) for k, v in legs.items()}
    first = snap(books[0][0])
    for b in ("SPY", "QQQ"):
        navs[(b.lower(), 0)] = build_portfolio_nav(
            dates, closes, [(first, {b: 1.0})], cost_bps_per_side=0.0
        )

    rdates = [snap(b[0]) for b in books]

    def leg_returns(nav: dict) -> list[float | None]:
        ds, vals = nav["dates"], nav["net"]
        idx = {d: i for i, d in enumerate(ds)}

        def at(d: str) -> float | None:
            i = idx.get(d)
            if i is None:
                j = bisect_left(ds, d) - 1
                i = j if 0 <= j < len(ds) else None
            return vals[i] if i is not None else None

        pts = rdates + [ds[-1]]
        return [
            (y / x - 1 if x and y else None) for x, y in ((at(a), at(b)) for a, b in zip(pts, pts[1:], strict=False))
        ]

    spy_legs = leg_returns(navs[("spy", 0)])
    t0 = dt.date.fromisoformat(navs[("spy", 0)]["dates"][0])
    t1 = dt.date.fromisoformat(navs[("spy", 0)]["dates"][-1])
    yrs = (t1 - t0).days / 365.25

    def cagr(nav: dict) -> float:
        return (nav["net"][-1] / nav["net"][0]) ** (1 / yrs) - 1

    spy_c = cagr(navs[("spy", 0)])
    qqq_c = cagr(navs[("qqq", 0)])
    print(f"\n=== PURE VETO EFFECT (net 10bps/side) — SPY {spy_c * 100:.1f}% "
          f"QQQ {qqq_c * 100:.1f}% over {yrs:.1f}y ===")
    print(f"{'N':>3} | beat noVETO | beat VETO  |  d  | CAGR noVETO | CAGR VETO |  d(pp)")
    deltas = []
    for n in range(1, args.max_n + 1):
        rv, rn = navs[("veto", n)], navs[("noveto", n)]
        lv, ln = leg_returns(rv), leg_returns(rn)
        pairs_v = [(p, s) for p, s in zip(lv, spy_legs, strict=True) if p is not None and s is not None]
        pairs_n = [(p, s) for p, s in zip(ln, spy_legs, strict=True) if p is not None and s is not None]
        bv = sum(1 for p, s in pairs_v if p > s)
        bn = sum(1 for p, s in pairs_n if p > s)
        cv, cn = cagr(rv), cagr(rn)
        deltas.append((cv - cn) * 100)
        print(
            f"{n:>3} | {bn:>3}/{len(pairs_n)} {bn / len(pairs_n) * 100:3.0f}% "
            f"| {bv:>3}/{len(pairs_v)} {bv / len(pairs_v) * 100:3.0f}% | {bv - bn:+3d} "
            f"| {cn * 100:10.1f}% | {cv * 100:8.1f}% | {(cv - cn) * 100:+6.1f}"
        )
    neg = sum(1 for d in deltas if d < 0)
    print(f"\nCAGR delta veto-minus-noveto: mean {sum(deltas) / len(deltas):+.2f}pp | "
          f"negative at {neg}/{len(deltas)} N | ex-N1-2 mean {sum(deltas[2:]) / (len(deltas) - 2):+.2f}pp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
