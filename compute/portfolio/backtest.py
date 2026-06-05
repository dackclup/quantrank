"""Point-in-time portfolio NAV construction for the Phase 7.0 backtest backfill.

Pure, offline-testable helpers — **no I/O, no scoring, no pandas**. Given the
per-rebalance holdings (tickers + weights, produced by ``weights.py`` + the
backfill script) and each holding's daily close series, build the
buy-and-hold-drift daily NAV (gross + net of turnover cost) rebased to 100,
alongside the benchmark NAV on the same dates.

This module owns ONLY the NAV math the methodology-scientist ratified for
Phase 7.0:

* **Quarterly rebalance** (``quarterly_rebalance_dates`` — quarter-end + a
  filing-lag offset so the latest 10-Q is public at the as-of date).
* **Buy-and-hold drift** between rebalances — positions float with price;
  weights are NOT re-pegged daily (re-pegging would invent turnover that did
  not happen).
* **Gross AND net** — net subtracts a per-rebalance turnover cost
  ``turnover x cost_bps_per_side`` (Novy-Marx-Velikov 2016; 10 bps/side is the
  conservative low end for S&P 500 large-caps, round-trip ~20 bps). Both are
  reported so the gross-vs-net gap is visible (Rule 15 honesty).
* **Delisting** = carry-forward the last available close, then liquidate into
  the next rebalance's redistribution (a delisting is NEVER treated as a 0).

The selection + weighting that PRODUCE the holdings live in ``weights.py`` and
the backfill script; this module is deliberately scoring-agnostic so its NAV
math is unit-testable without any market data or fundamentals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

# Novy-Marx-Velikov 2016 large-cap low-end; the backfill also reports a
# conservative second net line at a higher bps (methodology-scientist: show the
# cost band, do not present a single optimistic figure).
DEFAULT_COST_BPS_PER_SIDE: float = 10.0

# Quarter-end + this many days = the rebalance as-of date, so the most-recent
# 10-Q/10-K is public (S&P 500 = large-accelerated filers: 40-day 10-Q / 60-day
# 10-K deadlines; 45 covers the 10-Q and the backfill keys selection off the
# actual ``filing_date <= as_of`` filter regardless).
DEFAULT_FILING_LAG_DAYS: int = 45


def quarterly_rebalance_dates(
    start: date, end: date, *, lag_days: int = DEFAULT_FILING_LAG_DAYS
) -> list[date]:
    """Calendar rebalance dates = each quarter-end in ``[start, end]`` + ``lag_days``.

    Returns the as-of dates (still calendar dates — the backfill snaps each to
    the nearest trading day that has price data). Only dates ``<= end`` and
    ``>= start`` are returned, ascending.
    """
    out: list[date] = []
    year = start.year
    while year <= end.year:
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qend = date(year, m, d)
            asof = _add_days(qend, lag_days)
            if start <= asof <= end:
                out.append(asof)
        year += 1
    return out


def _add_days(d: date, days: int) -> date:
    from datetime import timedelta

    return d + timedelta(days=days)


def _is_valid_price(px: float | None) -> bool:
    return px is not None and px == px and px > 0  # not None, not NaN, positive


def _drifted_weights(
    shares: Mapping[str, float], price_at: Mapping[str, float]
) -> dict[str, float]:
    """Current (pre-rebalance) weights implied by held shares at today's prices."""
    values = {t: sh * price_at[t] for t, sh in shares.items() if t in price_at}
    total = sum(values.values())
    if total <= 0:
        return {}
    return {t: v / total for t, v in values.items()}


def build_portfolio_nav(
    dates: Sequence[str],
    closes: Mapping[str, Mapping[str, float]],
    rebalances: Sequence[tuple[str, Mapping[str, float]]],
    *,
    cost_bps_per_side: float = DEFAULT_COST_BPS_PER_SIDE,
    base: float = 100.0,
) -> dict:
    """Build the daily gross + net NAV for a rebalanced, buy-and-hold portfolio.

    Parameters
    ----------
    dates:
        Sorted-ascending ISO ``YYYY-MM-DD`` trading dates spanning the backtest.
    closes:
        ``{ticker: {date: close}}`` — sparse is fine; a missing date for a held
        name carries forward its last known close (delisting-safe).
    rebalances:
        Sorted-ascending ``[(as_of_date, {ticker: target_weight})]``; each
        ``as_of_date`` must appear in ``dates``. Weights are renormalised over
        the names that have a valid price on that date (a name with no price is
        dropped and its weight redistributed pro-rata — the delisting path).
    cost_bps_per_side:
        Per-side turnover cost in basis points (round-trip = 2x). Net NAV only.
    base:
        Rebased starting value (default 100).

    Returns
    -------
    dict with ``dates`` (from the first rebalance onward), ``gross``, ``net``
    (both rebased to ``base``), and ``turnover_by_rebalance`` (the Sum|Dw| at
    each rebalance, first entry ~1.0 = initial deployment).
    """
    cost_frac = cost_bps_per_side / 10_000.0
    rebal_by_date: dict[str, dict[str, float]] = {d: dict(w) for d, w in rebalances}

    last_px: dict[str, float] = {}

    def price_on(ticker: str, d: str) -> float | None:
        raw = closes.get(ticker, {}).get(d)
        if _is_valid_price(raw):
            last_px[ticker] = float(raw)  # type: ignore[arg-type]
            return float(raw)  # type: ignore[arg-type]
        return last_px.get(ticker)  # carry-forward (None if never priced)

    shares_gross: dict[str, float] = {}
    shares_net: dict[str, float] = {}
    nav_gross = base
    nav_net = base
    started = False

    out_dates: list[str] = []
    gross: list[float] = []
    net: list[float] = []
    turnover_log: list[float] = []

    for d in dates:
        # 1) mark-to-market existing holdings at today's (carry-forward) prices
        if started:
            nav_gross = _portfolio_value(shares_gross, d, price_on)
            nav_net = _portfolio_value(shares_net, d, price_on)

        # 2) rebalance on a rebalance date
        if d in rebal_by_date:
            target_raw = rebal_by_date[d]
            px = {t: price_on(t, d) for t in target_raw}
            priced = {
                t: wt for t, wt in target_raw.items() if _is_valid_price(px[t]) and wt > 0
            }
            sw = sum(priced.values())
            target = {t: wt / sw for t, wt in priced.items()} if sw > 0 else {}

            if not started:
                nav_gross = base
                nav_net = base
                drift_n: dict[str, float] = {}
                started = True
            else:
                valid_px = {t: px[t] for t in px if _is_valid_price(px[t])}
                # include currently-held names' prices for drift
                for t in set(shares_net) | set(shares_gross):
                    p = price_on(t, d)
                    if _is_valid_price(p):
                        valid_px[t] = p
                # gross has no cost so it needs no drift; only net's turnover does
                drift_n = _drifted_weights(shares_net, valid_px)

            # turnover = Sum |w_target - w_drifted| (counts both sides; the net
            # cost = turnover * per-side bps == round-trip bps on the traded notional)
            keys = set(target) | set(drift_n)
            turnover = sum(abs(target.get(t, 0.0) - drift_n.get(t, 0.0)) for t in keys)
            turnover_log.append(round(turnover, 6))

            nav_net *= 1.0 - turnover * cost_frac

            # re-allocate to target weights at today's prices
            shares_gross = _shares_for(target, nav_gross, d, price_on)
            shares_net = _shares_for(target, nav_net, d, price_on)

        if started:
            out_dates.append(d)
            gross.append(nav_gross)
            net.append(nav_net)

    # Raw NAV in initial-capital units: gross[0] == base; net[0] already
    # reflects the one-time entry cost, so net stays BELOW gross by the
    # cumulative cost drag. Do NOT rebase each series to its OWN anchor — that
    # would reset net back to `base` and erase the gross-vs-net gap. The
    # multi-timeframe chart rebases each WINDOW to 100 client-side (PR-4), and
    # the benchmark NAV is rebased to the same window start, so the comparison
    # stays honest.
    return {
        "dates": out_dates,
        "gross": gross,
        "net": net,
        "turnover_by_rebalance": turnover_log,
    }


def _portfolio_value(shares: Mapping[str, float], d: str, price_on) -> float:
    total = 0.0
    for t, sh in shares.items():
        p = price_on(t, d)
        if _is_valid_price(p):
            total += sh * p
    return total


def _shares_for(
    weights: Mapping[str, float], nav: float, d: str, price_on
) -> dict[str, float]:
    out: dict[str, float] = {}
    for t, w in weights.items():
        p = price_on(t, d)
        if _is_valid_price(p) and w > 0:
            out[t] = (w * nav) / p
    return out


def rebase(values: Sequence[float | None], *, base: float = 100.0) -> list[float | None]:
    """Rebase a series so its first finite-positive value == ``base``.

    Utility for aligning a benchmark close series to the portfolio NAV's window
    start (the client re-applies this per timeframe). None / NaN entries pass
    through as None so a sparse benchmark series stays gap-aware.
    """
    anchor = next(
        (v for v in values if v is not None and v == v and v > 0), None
    )
    if anchor is None:
        return [None for _ in values]
    out: list[float | None] = []
    for v in values:
        out.append(base * (v / anchor) if (v is not None and v == v) else None)
    return out


def align_benchmark_nav(
    portfolio_dates: Sequence[str],
    bench_dates: Sequence[str],
    bench_closes: Sequence[float | None],
    *,
    base: float = 100.0,
) -> list[float | None]:
    """Forward-fill a benchmark close series onto the portfolio's dates, rebased.

    For each portfolio date use the most-recent benchmark close on or before it
    (forward-fill), then rebase to ``base`` at the first portfolio date with a
    value — so the benchmark line shares the portfolio NAV's window start. A
    portfolio date before the benchmark's first valid close maps to None.
    Pure: lets the multi-timeframe comparison be assembled + tested offline.
    """
    pairs = sorted(zip(bench_dates, bench_closes, strict=False), key=lambda x: x[0])
    n = len(pairs)
    j = 0
    last_valid: float | None = None
    aligned: list[float | None] = []
    for d in portfolio_dates:
        while j < n and pairs[j][0] <= d:
            c = pairs[j][1]
            if c is not None and c == c and c > 0:
                last_valid = float(c)
            j += 1
        aligned.append(last_valid)
    return rebase(aligned, base=base)
