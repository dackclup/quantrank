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

The ``decompose=True`` opt-in adds a ``sub_periods`` key to the output — one
``SubPeriod`` per rebalance-to-rebalance (and final-to-end) interval with the
start weights, price relatives, gross/net sub-returns, and the RAW (un-rounded)
turnover cost drag ``δ_t``.  Existing callers with ``decompose=False`` (the
default) receive BYTE-IDENTICAL output — the flag is the only branch that adds
``sub_periods``.

The selection + weighting that PRODUCE the holdings live in ``weights.py`` and
the backfill script; this module is deliberately scoring-agnostic so its NAV
math is unit-testable without any market data or fundamentals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

# Novy-Marx-Velikov 2016 large-cap low-end; the backfill also reports a
# conservative second net line at a higher bps (methodology-scientist: show the
# cost band, do not present a single optimistic figure).
DEFAULT_COST_BPS_PER_SIDE: float = 10.0

# Quarter-end + this many days = the rebalance as-of date, so the most-recent
# 10-Q/10-K is public (S&P 500 = large-accelerated filers: 40-day 10-Q / 60-day
# 10-K deadlines; 45 covers the 10-Q and the backfill keys selection off the
# actual ``filing_date <= as_of`` filter regardless).
DEFAULT_FILING_LAG_DAYS: int = 45


@dataclass(frozen=True)
class SubPeriod:
    """One rebalance-to-rebalance (or final-to-end) attribution interval.

    Consumed by ``position_returns._compute_contribution`` via the Carino
    (1999) linking algorithm.  All weight and price-relative data are lifted
    directly from the engine's ``shares_gross`` / ``price_on`` carry-forward
    path — no second price walk (Condition C1).

    Fields
    ------
    date_from : str
        ISO date (YYYY-MM-DD) of the START of this sub-period (a rebalance
        date, or the first NAV date for the initial sub-period).
    date_to : str
        ISO date of the END of this sub-period (the NEXT rebalance date, or the
        last NAV date for the terminal sub-period).
    start_weights_gross : dict[str, float]
        POST-renormalization target weights (Σ = 1 over priced names) at
        ``date_from`` from the gross share path.  Names with no valid price on
        ``date_from`` are omitted; the engine already redistributed their weight
        pro-rata.
    price_relatives : dict[str, float]
        ``ρ_{i,t} = price(date_to) / price(date_from)`` for each held name,
        using the same carry-forward-safe ``price_on`` closure as the engine.
        A name whose price is unavailable at either boundary is omitted.
    gross_sub_return : float
        ``Π_i w_{i,t} × ρ_{i,t} − 1`` — the portfolio's gross return over this
        sub-period.  Equals ``Σ_i w_{i,t} × (ρ_{i,t} − 1)`` by identity.
    net_sub_return : float
        Gross sub-return minus the cost drag ``δ_t`` (= gross − δ_t, first
        period only since cost is applied at rebalance time, not distributed
        across trading days; for the initial deployment the cost drag is folded
        into NAV before the period begins).
    cost_drag : float
        RAW (un-rounded) turnover cost drag ``δ_t = turnover × cost_frac`` for
        this sub-period.  The ``turnover_by_rebalance`` list in the main output
        uses ``round(turnover, 6)``; this field retains full floating-point
        precision so the net-identity ``Σ(net_sub) + δ_t`` closes to the float
        floor rather than to ~1e-3 quantization error (methodology C-condition).
        Zero for sub-periods where no rebalance occurs (terminal interval).
    """

    date_from: str
    date_to: str
    start_weights_gross: dict[str, float] = field(default_factory=dict)
    price_relatives: dict[str, float] = field(default_factory=dict)
    gross_sub_return: float = 0.0
    net_sub_return: float = 0.0
    cost_drag: float = 0.0


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
    decompose: bool = False,
    dividends: Mapping[str, Mapping[str, float]] | None = None,
    price_basis: Literal["adjusted", "raw"] = "adjusted",
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
    decompose:
        When ``True``, the returned dict additionally contains a ``sub_periods``
        key — a list of ``SubPeriod`` objects, one per rebalance-to-rebalance
        (and final-to-end) interval.  Each ``SubPeriod`` carries the
        post-renormalization weights, price relatives, gross/net sub-returns,
        and the RAW (un-rounded) cost drag ``δ_t`` for that interval.
        Existing callers that omit this argument (``decompose=False``) receive
        BYTE-IDENTICAL output — no ``sub_periods`` key is added, no computation
        changes.
    dividends:
        Keyword-only. ``{ticker: {ex_date_iso: div_per_share}}`` mapping of
        cash dividends by ex-date. When ``None`` (default) or when
        ``price_basis="adjusted"``, the function is BYTE-IDENTICAL to the
        existing path — no dividend accrual, no cash bucket. Only active when
        **both** ``dividends`` is not ``None`` **and**
        ``price_basis="raw"``.

        Option-B dividend-pool-and-redeploy semantics (when active):
        * Positions drift on RAW split-adjusted ``Close`` only (price-return,
          NOT Adj Close — avoids double-counting since Adj Close already embeds
          dividend reinvestment per the double-count footgun documented in
          CLAUDE.md §Gotchas).
        * Between rebalances a cash bucket accrues per ex-date:
              cash(d) += Σ_i shares_i × div_per_share[i][d]
          Cash earns 0% (idle — methodology condition 1 disclosure:
          ``div_pool_idle_cash_rate=0.0``).
        * Daily book NAV = Σ_i shares_i × close_raw[i][d] + cash(d).
        * At rebalance: nav_total = price_value + cash; re-peg ALL of
          nav_total to new inverse-vol target weights at raw prices; reset
          cash=0. Net: turnover cost applies to the redeployed cash (extra
          buy-side turnover) — the existing ``nav_net *= (1 − turnover×cost_frac)``
          logic handles this automatically since turnover is computed over the
          full nav_total including redeployed cash.
        * Sold-name conservation: a name sold at a rebalance with an ex-date
          in its final sub-period has that dividend booked in its terminal
          price_value (shares × last price) PLUS the cash bucket accumulated
          before the rebalance, then redeployed to the next basket. No leakage.
    price_basis:
        Keyword-only. ``"adjusted"`` (default) uses the ``closes`` panel
        as-is (current behavior, byte-identical). ``"raw"`` switches to
        price-return-only pricing when ``dividends`` is also provided (the
        Option-B path). The ``closes`` argument MUST already be the raw
        split-adjusted panel when ``price_basis="raw"``; callers are
        responsible for passing the correct panel. ``"raw"`` with
        ``dividends=None`` falls back to byte-identical adjusted behavior.

    Returns
    -------
    dict with ``dates`` (from the first rebalance onward), ``gross``, ``net``
    (both rebased to ``base``), and ``turnover_by_rebalance`` (the Sum|Dw| at
    each rebalance, first entry ~1.0 = initial deployment).
    When ``decompose=True``, additionally contains ``sub_periods``
    (list of ``SubPeriod``).
    When Option-B is active (``dividends`` provided + ``price_basis="raw"``),
    additionally contains ``cash_at_rebalance`` — list of cash-bucket values
    (float) at each rebalance date (post-accrual, pre-redeploy), one entry per
    rebalance leg that starts the portfolio. Used by A/B-diff diagnostics.
    """
    # Option-B guard: dividend-pool path is ONLY active when BOTH conditions hold.
    # dividends=None OR price_basis="adjusted" => byte-identical existing path.
    _div_pool_active = (dividends is not None) and (price_basis == "raw")

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

    # Option-B: separate cash buckets for gross and net paths.
    # Both start at 0 and accumulate dividend income between rebalances.
    # At each rebalance the cash is included in nav_total for re-pegging (redeploy).
    cash_gross: float = 0.0
    cash_net: float = 0.0
    # Record cash-bucket values at each rebalance (pre-redeploy) for diagnostics.
    cash_at_rebalance: list[float] = []

    out_dates: list[str] = []
    gross: list[float] = []
    net: list[float] = []
    turnover_log: list[float] = []

    # Decompose-mode tracking: sub-period boundaries + state.
    # We record the target weights and date at each rebalance, then at the NEXT
    # rebalance (or the final date) we compute price relatives and sub-returns.
    _prev_rebal_date: str | None = None
    _prev_target: dict[str, float] = {}         # POST-renorm weights at prev rebalance
    _prev_nav_gross_before_cost: float = base    # gross NAV at prev rebalance (post-drift, pre-realloc)
    _prev_nav_net_before_cost: float = base      # net NAV at prev rebalance (post-cost-deduct, pre-realloc)
    _prev_cost_drag: float = 0.0                 # RAW δ_t at prev rebalance
    sub_periods: list[SubPeriod] = []

    for d in dates:
        # 1) mark-to-market existing holdings at today's (carry-forward) prices
        if started:
            nav_gross = _portfolio_value(shares_gross, d, price_on)
            nav_net = _portfolio_value(shares_net, d, price_on)
            # Option-B: accrue dividends paid on ex-dates between rebalances.
            # cash(d) += Σ_i shares_i × div_per_share[i][d]
            # Cash earns 0% (idle — methodology condition 1: div_pool_idle_cash_rate=0.0).
            if _div_pool_active:
                assert dividends is not None  # guarded above
                for t, div_map in dividends.items():
                    div_today = div_map.get(d)
                    if div_today is not None and div_today > 0.0:
                        sh_gross = shares_gross.get(t, 0.0)
                        sh_net = shares_net.get(t, 0.0)
                        cash_gross += sh_gross * div_today
                        cash_net += sh_net * div_today

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
                # First rebalance: record state for decompose; cost_drag=0 (initial deployment
                # charges cost but there is no prior sub-period to close yet).
                if decompose:
                    _prev_rebal_date = d
                    _prev_target = dict(target)
                    _prev_nav_gross_before_cost = base
                    _prev_nav_net_before_cost = base
                # Option-B: record initial cash (always 0 at start).
                if _div_pool_active:
                    cash_at_rebalance.append(cash_net)
            else:
                valid_px = {t: px[t] for t in px if _is_valid_price(px[t])}
                # include currently-held names' prices for drift
                for t in set(shares_net) | set(shares_gross):
                    p = price_on(t, d)
                    if _is_valid_price(p):
                        valid_px[t] = p
                # gross has no cost so it needs no drift; only net's turnover does
                drift_n = _drifted_weights(shares_net, valid_px)

                # Close the previous sub-period before applying costs.
                if decompose and _prev_rebal_date is not None:
                    sub_periods.append(
                        _build_sub_period(
                            date_from=_prev_rebal_date,
                            date_to=d,
                            prev_target=_prev_target,
                            price_on=price_on,
                            nav_gross_start=_prev_nav_gross_before_cost,
                            nav_gross_end=nav_gross,
                            cost_drag=_prev_cost_drag,
                        )
                    )

                # Option-B: record cash at this rebalance (post-accrual, pre-redeploy).
                if _div_pool_active:
                    cash_at_rebalance.append(cash_net)
                    # Include pooled cash in total NAV for re-pegging.
                    # nav_gross already reflects only the price-return path; add cash bucket.
                    nav_gross = nav_gross + cash_gross
                    nav_net = nav_net + cash_net
                    # Reset cash buckets after redeploy.
                    cash_gross = 0.0
                    cash_net = 0.0

            # turnover = Sum |w_target - w_drifted| (counts both sides; the net
            # cost = turnover * per-side bps == round-trip bps on the traded notional)
            keys = set(target) | set(drift_n)
            turnover = sum(abs(target.get(t, 0.0) - drift_n.get(t, 0.0)) for t in keys)
            turnover_log.append(round(turnover, 6))

            # RAW cost drag (full float precision — NOT rounded to 6dp).
            raw_cost_drag = turnover * cost_frac

            nav_net *= 1.0 - raw_cost_drag

            # re-allocate to target weights at today's prices
            shares_gross = _shares_for(target, nav_gross, d, price_on)
            shares_net = _shares_for(target, nav_net, d, price_on)

            # Update decompose state for the next sub-period.
            if decompose:
                _prev_rebal_date = d
                _prev_target = dict(target)
                _prev_nav_gross_before_cost = nav_gross
                _prev_nav_net_before_cost = nav_net
                _prev_cost_drag = raw_cost_drag

        if started:
            # Option-B: daily book NAV includes the cash bucket.
            if _div_pool_active:
                out_dates.append(d)
                gross.append(nav_gross + cash_gross)
                net.append(nav_net + cash_net)
            else:
                out_dates.append(d)
                gross.append(nav_gross)
                net.append(nav_net)

    # Close the terminal sub-period (from last rebalance to end of dates).
    if decompose and _prev_rebal_date is not None and out_dates:
        terminal_date = out_dates[-1]
        if terminal_date != _prev_rebal_date:
            # Compute gross NAV at terminal date (already in gross[-1]).
            terminal_nav_gross = gross[-1] if gross else _prev_nav_gross_before_cost
            sub_periods.append(
                _build_sub_period(
                    date_from=_prev_rebal_date,
                    date_to=terminal_date,
                    prev_target=_prev_target,
                    price_on=price_on,
                    nav_gross_start=_prev_nav_gross_before_cost,
                    nav_gross_end=terminal_nav_gross,
                    cost_drag=0.0,  # no rebalance at the terminal boundary
                )
            )

    # Raw NAV in initial-capital units: gross[0] == base; net[0] already
    # reflects the one-time entry cost, so net stays BELOW gross by the
    # cumulative cost drag. Do NOT rebase each series to its OWN anchor — that
    # would reset net back to `base` and erase the gross-vs-net gap. The
    # multi-timeframe chart rebases each WINDOW to 100 client-side (PR-4), and
    # the benchmark NAV is rebased to the same window start, so the comparison
    # stays honest.
    result: dict = {
        "dates": out_dates,
        "gross": gross,
        "net": net,
        "turnover_by_rebalance": turnover_log,
    }
    if decompose:
        result["sub_periods"] = sub_periods
    if _div_pool_active:
        result["cash_at_rebalance"] = cash_at_rebalance
    return result


def _build_sub_period(
    date_from: str,
    date_to: str,
    prev_target: dict[str, float],
    price_on,
    nav_gross_start: float,
    nav_gross_end: float,
    cost_drag: float,
) -> SubPeriod:
    """Build a ``SubPeriod`` for the interval [``date_from``, ``date_to``].

    Uses the engine's ``price_on`` closure (adjusted-close + carry-forward)
    so price relatives are sourced from the same adjusted-close series as
    the NAV computation (Condition C1 — no second price walk).

    The gross sub-return is derived from the ratio of NAV values rather than
    re-multiplying weights × price relatives; this guarantees
    ``Σ w_i ρ_i == 1 + gross_sub_return`` by the engine's own arithmetic
    (the engine IS the source of truth for NAV, not a second calculation).
    Price relatives are computed for observability / contribution attribution.
    """
    # Price relatives ρ_{i,t} = p(date_to) / p(date_from), carry-forward-safe.
    price_relatives: dict[str, float] = {}
    for ticker in prev_target:
        p_from = price_on(ticker, date_from)
        p_to = price_on(ticker, date_to)
        if _is_valid_price(p_from) and _is_valid_price(p_to):
            price_relatives[ticker] = float(p_to) / float(p_from)  # type: ignore[arg-type]

    # Gross sub-return: ratio of NAV values (engine-consistent arithmetic).
    gross_sub_return: float
    if nav_gross_start > 0:
        gross_sub_return = (nav_gross_end / nav_gross_start) - 1.0
    else:
        # Degenerate: if start NAV is 0, compute from weights × price relatives.
        weighted_sum = sum(
            prev_target.get(t, 0.0) * (price_relatives.get(t, 1.0) - 1.0)
            for t in prev_target
        )
        gross_sub_return = weighted_sum

    # Net sub-return = gross_sub_return − cost_drag (cost deducted at rebalance).
    net_sub_return = gross_sub_return - cost_drag

    return SubPeriod(
        date_from=date_from,
        date_to=date_to,
        start_weights_gross=dict(prev_target),
        price_relatives=price_relatives,
        gross_sub_return=gross_sub_return,
        net_sub_return=net_sub_return,
        cost_drag=cost_drag,
    )


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
