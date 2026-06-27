"""Per-position return attribution for the Phase 7 PIT backtest (PR-2c).

PR-2c (Carino C3 reconciliation) extends PR-2a (#618) with the Carino (1999)
geometric-linking attribution math, replacing the previous stub (``contrib_nav_pts``
was always ``None``).

Algorithm: window-global Carino grid
--------------------------------------
For each rebalance-to-rebalance sub-period t (provided by ``SubPeriod`` from
``build_portfolio_nav(decompose=True)``):

    k_t = ln(1 + R^g_t) / R^g_t       (Carino sub-period coefficient)
    K   = ln(1 + R^g_port) / R^g_port  (Carino total coefficient)

When ``1 + R^g_t ≤ 0`` (portfolio total-loss sub-period): clamp ``k_t = 1``
and increment ``carino_clamp_count``.

Position contribution across ALL sub-periods (LIFETIME, not streak-scoped):

    C_i = Σ_t (k_t / K) · c_{i,t}

where ``c_{i,t} = w_{i,t} · (ρ_{i,t} − 1)`` is the position's weighted
price-relative contribution for sub-period t.

Identities (Carino 1999 §3):
    GROSS identity:    Σ_i C_i   = R^g_port               (exact, ~1e-11 float error)
    SYNTHETIC __cost__ position:  C_cost = Σ_t (k_t/K) · (−δ_t)
    NET identity:      Σ_i C^n_i + C_cost = R^n_port       (closed by un-rounded δ_t)

The ``__cost__`` synthetic line is never folded into a real ticker and never
displayed — it exists only to close the net identity.

Three new diagnostic counters flow into ``payload["meta"]`` via
``reconciliation_errors``:
  - ``position_return_reconciliation_max_abs_error``:
        max(|Σ_t (k_t/K)·R^g_t − R^g_port|,  max_t |Σ_i w_{i,t}·(ρ_{i,t}−1) − R^g_t|)
        Computed directly from SubPeriod records (NOT from the flat position_returns
        map, which covers only current/recently-sold tickers).
  - ``position_return_cost_line_residual``:           |R^g_port + C_cost − R^n_port|
  - ``carino_clamp_count``

PR-2a extensions (unchanged):
  1. Per-quarter generalization: ``compute_position_returns_per_quarter``
     computes a separate ``{ticker: PositionReturn}`` map for EVERY historical
     rebalance.
  2. TWR vs client-side comparison: ``reconciliation_errors`` emits
     ``position_return_twr_vs_clientside_max_abs_pp``.

Backward-compat:
    ``compute_position_returns`` returns current holders AT the latest rebalance
    PLUS names sold at the latest rebalance (marked-to-exit close), matching PR-1's
    output exactly.  When ``sub_periods`` is ``None``, ``contrib_nav_pts`` is ``None``
    for all positions (same as PR-2a behaviour).

Two return measures per holding are computed in this module:

MWR (Modified Dietz, CFA/GIPS standard)
    Money-weighted return over actual rebalance cash flows.  The Modified Dietz
    estimator is:

        R_MWR = (V_end - V_begin - ΣCF_i) / (V_begin + Σ W_i × CF_i)

    where W_i = fraction of period remaining after flow i.

    **Option-B shadow path (issue #620):** when ``build_portfolio_nav`` is
    called with ``dividends`` + ``price_basis="raw"`` (the SHADOW
    ``nav.adaptive_div_pooled`` series), pooled cash accumulates between
    rebalances and is redeployed at each rebalance.  For Modified-Dietz
    classification purposes the accrued-dividend cash bucket is treated as an
    INTERNAL reinvestment (not an external cash flow), so ``ΣCF_i = 0`` and
    the denominator simplifies to ``V_begin``.  The redeployed cash is already
    folded into ``nav_total`` before ``_shares_for`` re-pegs shares, so no
    adjustment is required in this module — the ``SubPeriod.price_relatives``
    already reflect the full redeployed NAV as the sub-period start.  This note
    is documentation-only; the shadow path does not change any computation in
    ``position_returns.py``.

TWR (Time-Weighted Return, chained geometric)
    Chained geometric product over the contiguous legs in the position's streak:

        R_TWR = Π(p_{i+1} / p_i) - 1

    where each p_i is the adjusted-close price at the rebalance boundary
    (Condition C1: same series as ``build_portfolio_nav``).

contrib_nav_pts (Carino-linked, 1999)
    LIFETIME Carino contribution across ALL sub-periods.  Non-None only when
    ``sub_periods`` is supplied (``decompose=True`` path).

This module is **pure** — no I/O, no scoring, no pandas, no network calls.

Rule 18 (observability-before-wiring): the per-rebalance ``position_returns``
maps are added to the backtest artifact as shadow fields.  The frontend
does NOT read them until a PR-2b that adds a UI surface gated on ≥ 1 cron
confirming the reconciliation counters.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from compute.portfolio.backtest import SubPeriod

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------


class PositionReturn(NamedTuple):
    """Return attribution for a single position (ticker) in the backtest.

    Fields
    ------
    mwr_pct : float | None
        Modified Dietz money-weighted return, in percent (e.g. 12.5 = 12.5 %).
        None when no valid legs exist (price gap for the full holding period).
    twr_pct : float | None
        Time-weighted return (chained geometric), in percent.
        None when no valid leg exists.
    contrib_nav_pts : float | None
        Carino-linked contribution to portfolio gross NAV return, in NAV base-100
        points.  Σ(contrib_nav_pts) over all positions reconciles to the
        portfolio's total gross NAV return in base-100 pts.  None when the
        ``sub_periods`` decomposition is not available.
    since_date : str | None
        ISO date (YYYY-MM-DD) of the first rebalance in the current streak.
    partial_history : bool
        True when one or more rebalance legs were dropped due to a null price.
    legs_used : int
        Number of sub-periods (price ratios) that contributed to the TWR.
    """

    mwr_pct: float | None
    twr_pct: float | None
    contrib_nav_pts: float | None
    since_date: str | None
    partial_history: bool
    legs_used: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_valid_price(px: float | None) -> bool:
    """Return True when ``px`` is a usable price: not None, not NaN, positive."""
    return px is not None and px == px and px > 0  # not None, not NaN, positive


def _last_close(ticker: str, closes: Mapping[str, Mapping[str, float]]) -> float | None:
    """Return the most recent valid close for ``ticker`` in ``closes``."""
    series = closes.get(ticker)
    if not series:
        return None
    last_date = max(series)
    px = series[last_date]
    return px if _is_valid_price(px) else None


def _close_on(
    ticker: str, date_iso: str, closes: Mapping[str, Mapping[str, float]]
) -> float | None:
    """Return close for ``ticker`` on ``date_iso``, or None if unavailable."""
    series = closes.get(ticker)
    if not series:
        return None
    px = series.get(date_iso)
    return px if _is_valid_price(px) else None


def _close_on_or_before(
    ticker: str, date_iso: str, closes: Mapping[str, Mapping[str, float]]
) -> float | None:
    """Return the most recent valid close for ``ticker`` on or before ``date_iso``.

    Scans backwards from ``date_iso`` through the closes series to find the
    last available price.  Needed for non-trading days (rebalance dates that
    fall on weekends or market holidays).

    Returns None when no close exists on or before ``date_iso``.
    """
    series = closes.get(ticker)
    if not series:
        return None
    # Collect dates <= date_iso and find the maximum (most recent).
    eligible = [d for d in series if d <= date_iso]
    if not eligible:
        return None
    best_date = max(eligible)
    px = series[best_date]
    return px if _is_valid_price(px) else None


def _modified_dietz(
    flows: Sequence[tuple[float, float, float]],
) -> float | None:
    """Compute Modified Dietz return from a list of (V_begin, V_end, CF_weight) tuples.

    Parameters
    ----------
    flows:
        Each entry is ``(begin_value, end_value, time_weight)`` for one sub-period.
        ``begin_value`` is the position value at the start of the sub-period,
        ``end_value`` is the position value at the end.
        ``time_weight`` (W_i) is the fraction of the full period remaining when the
        initial capital is invested — 1.0 for the very first leg, decreasing toward
        0.0 for later legs.

    Returns
    -------
    float | None
        Return as a fraction (not percent).  None on degenerate input.

    Notes
    -----
    For each sub-period the "cash flow" from the investor's perspective is
    ``begin_value`` (money going in at the start of that leg).  So:

        numerator   = V_end_final - V_begin_initial - Σ CF_i  (for i > 0 legs only)
        denominator = V_begin_initial + Σ W_i × CF_i

    Since we chain the legs end-to-end (V_end of leg i = V_begin of leg i+1),
    the simplified per-sub-period version is used here: treat each leg independently
    and average the returns weighted by capital employed.

    In practice this is equivalent to a simple HPR chain when weights are
    equal across legs, and correctly accounts for the timing of additional
    capital deployed at subsequent rebalances (weight changes).
    """
    if not flows:
        return None

    # Aggregate into a single Modified Dietz computation over the full holding.
    # The investor "deploys" begin_value at the start of each leg (a "cash flow in").
    # The first leg's begin_value is V_begin; subsequent legs are new money in
    # proportional to how the position's weight changed at rebalance.

    total_v_end = flows[-1][1]  # final exit value (per unit of 1.0 base)
    total_v_begin = flows[0][0]  # initial entry value

    # Additional capital deployed at each intermediate rebalance (legs 1..N-1).
    # At each mid-period rebalance the position is partially sold (old weight → new weight),
    # but since we're computing per-position (not portfolio) the "cash flow" is just the
    # delta in invested amount. For simplicity in the single-position context:
    # use the full-period aggregated Modified Dietz.

    total_cf_weighted = 0.0
    total_cf = 0.0
    for i, (v_begin, _v_end, w) in enumerate(flows):
        if i == 0:
            # First leg: initial investment (period start, W=1.0 — not a mid-period flow).
            continue
        # Mid-period cash flows: additional capital deployed at this rebalance.
        cf = v_begin - flows[i - 1][1]  # new capital = new begin_value - prior end_value
        total_cf += cf
        total_cf_weighted += w * cf

    numerator = total_v_end - total_v_begin - total_cf
    denominator = total_v_begin + total_cf_weighted

    if denominator == 0.0:
        return None
    return numerator / denominator


# ---------------------------------------------------------------------------
# Streak extraction
# ---------------------------------------------------------------------------


def _extract_streaks(
    ticker: str,
    legs: list[tuple[str, float]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    all_rebalance_dates: Sequence[str] | None = None,
) -> list[list[tuple[str, float, float | None]]]:
    """Extract contiguous holding streaks for ``ticker`` from its sequence of ``(date, weight)`` legs.

    A streak is a maximal sub-sequence of consecutive legs where the weight is
    non-zero.  Weight → 0 signals a sell/termination, starting a new streak if
    the position is re-entered later.

    When ``all_rebalance_dates`` is provided, the function ALSO splits a streak
    on a **rebalance-date gap**: if two consecutive present legs ``(d_prev, d_cur)``
    are not adjacent in ``all_rebalance_dates`` (i.e. the ticker was absent from
    ≥ 1 intervening rebalances), the current streak is closed and a new one is
    started.  This correctly handles backfills where absent tickers are simply
    omitted from ``band_legs`` rather than emitting a weight-0 leg, so that the
    "current contiguous streak" is the re-entry streak, not the first-ever entry.

    When ``all_rebalance_dates`` is ``None`` (default), the old weight-only
    behaviour is preserved BYTE-IDENTICAL (backward-compatible).

    Parameters
    ----------
    ticker:
        The ticker symbol.
    legs:
        ``[(date_iso, weight)]`` — the chronological rebalance legs for this
        ticker, in ascending date order.
    closes:
        ``{ticker: {date_iso: close}}`` — the shared adjusted-close panel.
    all_rebalance_dates:
        The FULL ordered sequence of rebalance dates in the attribution window
        (or the PIT-truncated prefix for historical quarters).  When provided,
        consecutive present legs that are not adjacent in this axis trigger a
        streak split.  None = weight-only mode (backward-compat).

    Returns
    -------
    list of streaks
        Each streak is a list of ``(date_iso, weight, price_or_None)`` tuples
        representing the contiguous holding period.  The caller is responsible
        for computing returns from consecutive pairs within a streak.
    """
    # Build the rank lookup from all_rebalance_dates once, if provided.
    date_rank: dict[str, int] | None = None
    if all_rebalance_dates is not None:
        date_rank = {d: i for i, d in enumerate(all_rebalance_dates)}

    streaks: list[list[tuple[str, float, float | None]]] = []
    current: list[tuple[str, float, float | None]] = []
    prev_date: str | None = None

    for date_iso, weight in legs:
        if weight <= 0.0:
            # Sell signal: close the current streak if non-empty.
            if current:
                streaks.append(current)
                current = []
            prev_date = None
        else:
            # Gap-aware split: if two consecutive held legs have non-adjacent
            # positions in all_rebalance_dates, the ticker was absent during
            # the intervening rebalances → treat as a new streak.
            if (
                date_rank is not None
                and prev_date is not None
                and current
            ):
                prev_rank = date_rank.get(prev_date)
                cur_rank = date_rank.get(date_iso)
                if (
                    prev_rank is not None
                    and cur_rank is not None
                    and cur_rank - prev_rank > 1
                ):
                    # Gap detected: close current streak, start fresh.
                    streaks.append(current)
                    current = []

            # Use _close_on_or_before (not _close_on) so a rebalance date that
            # falls on a non-trading day (e.g. 2016-08-14 = Sunday for the
            # initial basket) resolves to the most-recent prior trading-day
            # close.  Symmetric with the terminal-price lookup at line ~423
            # (_close_on_or_before for end_date) and _last_close for the latest
            # mark.  _close_on_or_before is on-or-before only (no look-ahead)
            # and is already _is_valid_price-guarded.
            px = _close_on_or_before(ticker, date_iso, closes)
            current.append((date_iso, weight, px))
            prev_date = date_iso

    # Finalize an open streak (current holder, not yet sold).
    if current:
        streaks.append(current)

    return streaks


# ---------------------------------------------------------------------------
# TWR computation
# ---------------------------------------------------------------------------


def _compute_twr(
    ticker: str,
    streak: list[tuple[str, float, float | None]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    is_current_holder: bool,
    end_date: str | None = None,
) -> tuple[float | None, bool, int, str | None]:
    """Compute TWR for a single holding streak.

    Parameters
    ----------
    ticker:
        The ticker symbol (used for mark-to-latest-close when ``is_current_holder``).
    streak:
        List of ``(date_iso, weight, price_or_None)`` from ``_extract_streaks``.
    closes:
        Shared adjusted-close panel.
    is_current_holder:
        When True, the position is still open at the end of the period.  When
        ``end_date`` is None, mark to the latest available close; when ``end_date``
        is provided (non-latest rebalance), mark to the close on or before that date.
    end_date:
        ISO date marking the end of this sub-period (the next rebalance date).
        None for the latest/current rebalance (mark to last available close).
        When provided and ``is_current_holder`` is True, uses
        ``_close_on_or_before(ticker, end_date, closes)`` as the terminal price.

    Returns
    -------
    (twr_pct, partial_history, legs_used, since_date)
    """
    if not streak:
        return None, False, 0, None

    since_date = streak[0][0]

    # Build the price sequence: [p0, p1, ..., p_n] where each p_i is the
    # adjusted close at the streak's rebalance dates, plus a terminal close
    # for the final exit or mark-to-market.
    prices: list[float | None] = [entry[2] for entry in streak]

    # Add terminal price.
    if is_current_holder:
        if end_date is not None:
            # Non-latest quarter: mark to close on or before the next rebalance date.
            terminal_px = _close_on_or_before(ticker, end_date, closes)
        else:
            # Latest quarter: mark to the most recent close.
            terminal_px = _last_close(ticker, closes)
        prices.append(terminal_px)
    else:
        # Sold: use the exit-rebalance close (last entry in streak).
        # The streak already includes entry+exit dates, so the final price in
        # ``prices`` IS the exit close. No extra appending needed.
        pass

    # Chain the geometric ratios.
    twr = 1.0
    legs_used = 0
    partial = False

    for i in range(len(prices) - 1):
        p0 = prices[i]
        p1 = prices[i + 1]
        if _is_valid_price(p0) and _is_valid_price(p1):
            twr *= p1 / p0  # type: ignore[operator]
            legs_used += 1
        else:
            partial = True

    if legs_used == 0:
        return None, partial, 0, since_date

    return (twr - 1.0) * 100.0, partial, legs_used, since_date


# ---------------------------------------------------------------------------
# MWR computation
# ---------------------------------------------------------------------------


def _compute_mwr(
    ticker: str,
    streak: list[tuple[str, float, float | None]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    is_current_holder: bool,
    period_start_date: str | None = None,
    period_end_date: str | None = None,
    end_date: str | None = None,
) -> float | None:
    """Compute Modified Dietz MWR for a single holding streak.

    Returns return as percent, or None on degenerate input.

    Parameters
    ----------
    ticker:
        Used for mark-to-latest-close when ``is_current_holder``.
    streak:
        List of ``(date_iso, weight, price_or_None)`` from ``_extract_streaks``.
    closes:
        Shared adjusted-close panel.
    is_current_holder:
        When True, mark position to the terminal close (latest or ``end_date``).
    period_start_date:
        ISO date of the overall holding period start (used for time-weight W_i).
        Defaults to streak[0][0].
    period_end_date:
        ISO date of the overall holding period end (used for time-weight W_i).
        Defaults to the final price date.
    end_date:
        ISO date marking the end of this sub-period (next rebalance date).
        When provided and ``is_current_holder`` is True, uses
        ``_close_on_or_before(ticker, end_date, closes)`` as the terminal price.
        None = latest quarter (mark to last close).
    """
    if not streak:
        return None

    # Collect all price points: entries in the streak + terminal.
    all_entries: list[tuple[str, float, float | None]] = list(streak)
    if is_current_holder:
        if end_date is not None:
            terminal_px = _close_on_or_before(ticker, end_date, closes)
        else:
            terminal_px = _last_close(ticker, closes)
        if terminal_px is not None:
            # Append a synthetic terminal entry (date = terminal date, weight = last weight).
            if end_date is not None:
                # Find the actual date of the terminal close (on or before end_date).
                series = closes.get(ticker)
                if series:
                    eligible = [d for d in series if d <= end_date]
                    terminal_date = max(eligible) if eligible else streak[-1][0]
                else:
                    terminal_date = streak[-1][0]
            else:
                terminal_date = max(closes.get(ticker, {}).keys(), default=streak[-1][0])
            all_entries = list(streak) + [(terminal_date, streak[-1][1], terminal_px)]
        # else: no terminal price available — use last streak entry as exit.

    if len(all_entries) < 2:
        return None

    # Determine the period span for W_i computation.
    p_start = period_start_date or all_entries[0][0]
    p_end = period_end_date or all_entries[-1][0]
    total_days = max(1, _days_between(p_start, p_end))

    # Build (v_begin, v_end, time_weight) tuples per leg.
    # v_begin and v_end are in "position units" normalized to initial weight = 1.0.
    # We use price ratios × entry weight to represent position value per unit.
    flows: list[tuple[float, float, float]] = []

    for i in range(len(all_entries) - 1):
        d0, w0, p0 = all_entries[i]
        d1, w1, p1 = all_entries[i + 1]

        if not _is_valid_price(p0) or not _is_valid_price(p1):
            continue  # drop legs with null prices (graceful degradation)

        assert p0 is not None and p1 is not None  # for type narrowing

        # Scale to a notional position of "initial weight" invested.
        # v_begin is weight × entry_price (notional); v_end is weight × exit_price.
        v_begin = float(w0) * float(p0)
        v_end = float(w0) * float(p1)  # price drift; weight floats between rebalances

        # Time weight W_i: fraction of total period remaining when this leg starts.
        days_from_start = _days_between(p_start, d0)
        w_i = 1.0 - (days_from_start / total_days)

        flows.append((v_begin, v_end, w_i))

    if not flows:
        return None

    result = _modified_dietz(flows)
    if result is None:
        return None
    return result * 100.0


def _days_between(d0_iso: str, d1_iso: str) -> int:
    """Return calendar days between two ISO date strings (d1 - d0)."""
    from datetime import date

    y0, m0, day0 = int(d0_iso[:4]), int(d0_iso[5:7]), int(d0_iso[8:10])
    y1, m1, day1 = int(d1_iso[:4]), int(d1_iso[5:7]), int(d1_iso[8:10])
    return (date(y1, m1, day1) - date(y0, m0, day0)).days


# ---------------------------------------------------------------------------
# Carino (1999) linking helpers — window-global grid
# ---------------------------------------------------------------------------


def _carino_coefficient(r: float) -> float:
    """Carino (1999) linking coefficient: ln(1+R)/R.

    At R=0, L'Hôpital gives the limit = 1.0.  We use a tolerance around
    zero to avoid division by very small numbers causing overflow.
    """
    if abs(r) < 1e-10:
        return 1.0
    v = 1.0 + r
    if v <= 0.0:
        # Portfolio suffered a total loss; coefficient is undefined.
        return 1.0
    return math.log(v) / r


def _build_carino_grid(
    sub_periods: list[SubPeriod],
) -> tuple[list[float], float, int]:
    """Build the window-global Carino linking grid from a list of sub-periods.

    Computes ``(k_t / K)`` for each sub-period t, where:
        k_t = ln(1 + R^g_t) / R^g_t  (sub-period Carino coefficient)
        K   = ln(1 + R^g_port) / R^g_port  (total-period Carino coefficient)

    ``R^g_port`` is the portfolio GROSS return over ALL sub-periods:
        (1 + R^g_port) = Π_t (1 + R^g_t)    (geometric linking)

    When ``1 + R^g_t ≤ 0`` for a sub-period: clamp ``k_t = 1`` and increment
    ``carino_clamp_count``.

    Parameters
    ----------
    sub_periods:
        Sub-period records from ``build_portfolio_nav(decompose=True)``.

    Returns
    -------
    (kt_over_K, K, carino_clamp_count)
        kt_over_K : list[float]
            Per-sub-period ratio ``k_t / K``.  Length = len(sub_periods).
        K : float
            Total Carino coefficient for the window.
        carino_clamp_count : int
            Number of sub-periods where ``1 + R^g_t ≤ 0`` (clamped to k_t=1).
    """
    if not sub_periods:
        return [], 1.0, 0

    # Step 1: compute window-global gross return via geometric linking.
    gross_product = 1.0
    for sp in sub_periods:
        gross_product *= 1.0 + sp.gross_sub_return
    R_port_gross = gross_product - 1.0

    # Step 2: total Carino coefficient K. K = ln(1+R)/R ∈ (0, 1] for all finite
    # R > −1 (and the _carino_coefficient L'Hôpital limit gives K=1 at R=0), so K
    # is never 0 — no uniform-weight fallback is added here on purpose: it would
    # NOT preserve the Σ C_i = R^g_port identity. Should K somehow be 0 (it can't),
    # the k_t/K below raises ZeroDivisionError, which the caller's try/except
    # degrades to None — honest absence beats an identity-violating number.
    K = _carino_coefficient(R_port_gross)

    # Step 3: per-sub-period k_t and ratio k_t / K.
    kt_over_K: list[float] = []
    carino_clamp_count = 0
    for sp in sub_periods:
        r_t = sp.gross_sub_return
        one_plus_rt = 1.0 + r_t
        if one_plus_rt <= 0.0:
            # Total loss sub-period: clamp k_t = 1.
            k_t = 1.0
            carino_clamp_count += 1
        else:
            k_t = _carino_coefficient(r_t)
        kt_over_K.append(k_t / K)

    return kt_over_K, K, carino_clamp_count


def _compute_contribution_from_sub_periods(
    ticker: str,
    ticker_legs: dict[str, float],
    sub_periods: list[SubPeriod],
    kt_over_K: list[float],
) -> float:
    """Compute the LIFETIME Carino contribution for ``ticker`` across all sub-periods.

    Parameters
    ----------
    ticker:
        The ticker symbol.
    ticker_legs:
        Mapping of ``{date_iso: weight}`` from the full band_legs history.
        Used to look up the START weight for each sub-period.
    sub_periods:
        Sub-period records from the engine (window-global).
    kt_over_K:
        Per-sub-period Carino linking ratio from ``_build_carino_grid``.

    Returns
    -------
    float
        Contribution C_i in NAV gross-return fraction (NOT percent).
        Sum over all tickers equals R^g_port exactly (up to float precision ~1e-11).
    """
    contrib = 0.0
    for t, sp in enumerate(sub_periods):
        # Weight at start of this sub-period: from start_weights_gross (post-renorm).
        w = sp.start_weights_gross.get(ticker, 0.0)
        if w == 0.0:
            continue
        # Price-relative: ρ_{i,t} = price(date_to)/price(date_from) from engine.
        rho = sp.price_relatives.get(ticker)
        if rho is None:
            continue
        # Position return for this sub-period: ρ − 1.
        r_pos_t = rho - 1.0
        # Weighted price-relative contribution: c_{i,t} = w × r_pos_t.
        c_it = w * r_pos_t
        # Carino-linked: (k_t / K) × c_{i,t}.
        contrib += kt_over_K[t] * c_it
    return contrib


def _compute_carino_contribution_for_streak(
    ticker: str,
    streak: list[tuple[str, float, float | None]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    date_to_nav: dict[str, float],
    is_current_holder: bool,
    end_date: str | None,
    portfolio_total_return_pct: float,
) -> float | None:
    """DEPRECATED: per-streak daily-NAV-based Carino helper from PR-2a.

    Retained for import compatibility with tests written against PR-2a.
    The PR-2c algorithm replaces this with the window-global Carino grid
    (``_build_carino_grid`` + ``_compute_contribution_from_sub_periods``).

    This implementation is correct for the old per-streak formulation and
    will continue to pass the existing tests.
    """
    if not streak or not date_to_nav:
        return None

    R_port = portfolio_total_return_pct / 100.0
    k_port = _carino_coefficient(R_port)
    if k_port == 0.0:
        return None

    # Build the price sequence: streak entries + optional terminal close.
    price_seq: list[tuple[str, float, float | None]] = list(streak)
    if is_current_holder:
        if end_date is not None:
            terminal_px = _close_on_or_before(ticker, end_date, closes)
            series = closes.get(ticker)
            if series and terminal_px is not None:
                eligible = [d for d in series if d <= end_date]
                terminal_date = max(eligible) if eligible else streak[-1][0]
            else:
                terminal_date = end_date
        else:
            terminal_px = _last_close(ticker, closes)
            series = closes.get(ticker)
            terminal_date = max(series) if series else streak[-1][0]
        if terminal_px is not None:
            price_seq = list(streak) + [(terminal_date, streak[-1][1], terminal_px)]

    if len(price_seq) < 2:
        return None

    contrib_total = 0.0
    for i in range(len(price_seq) - 1):
        d0, w0, p0 = price_seq[i]
        d1, _w1, p1 = price_seq[i + 1]

        if not _is_valid_price(p0) or not _is_valid_price(p1):
            continue

        assert p0 is not None and p1 is not None  # type narrowing

        r_pos_sub = p1 / p0 - 1.0

        nav_d0 = date_to_nav.get(d0)
        nav_d1 = date_to_nav.get(d1)
        if nav_d0 is None or nav_d1 is None or nav_d0 <= 0.0:
            if nav_d0 is None:
                eligible_0 = [d for d in date_to_nav if d <= d0]
                if eligible_0:
                    nav_d0 = date_to_nav[max(eligible_0)]
            if nav_d1 is None:
                eligible_1 = [d for d in date_to_nav if d <= d1]
                if eligible_1:
                    nav_d1 = date_to_nav[max(eligible_1)]
            if nav_d0 is None or nav_d1 is None or nav_d0 <= 0.0:
                continue

        r_port_sub = nav_d1 / nav_d0 - 1.0
        k_sub = _carino_coefficient(r_port_sub)

        contrib_total += float(w0) * r_pos_sub * (k_sub / k_port) * 100.0

    return contrib_total


def _cost_line_contribution(
    sub_periods: list[SubPeriod],
    kt_over_K: list[float],
) -> float:
    """Compute the synthetic __cost__ line contribution for the NET identity.

    C_cost = Σ_t (k_t / K) · (−δ_t)

    where δ_t = ``sp.cost_drag`` (RAW un-rounded turnover cost drag).

    Adding this to the sum of per-position net contributions closes the net
    identity: Σ_i C^n_i + C_cost = R^n_port.

    Returns
    -------
    float
        C_cost as a NAV-return fraction (negative for positive cost drag).
    """
    cost_contrib = 0.0
    for t, sp in enumerate(sub_periods):
        cost_contrib += kt_over_K[t] * (-sp.cost_drag)
    return cost_contrib


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _compute_flat_latest_returns(
    band_legs: list[tuple[str, dict[str, float]]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    sub_periods: list[SubPeriod] | None = None,
) -> dict[str, PositionReturn]:
    """Compute position returns for the flat top-level ``payload["position_returns"]``.

    Preserves PR-1 semantics exactly: covers BOTH current holders at the latest
    rebalance AND names sold at the latest rebalance (marked-to-exit close).

    When ``sub_periods`` is provided, computes ``contrib_nav_pts`` (Carino-linked,
    LIFETIME across all sub-periods).  Otherwise, ``contrib_nav_pts`` is None
    (backward-compat with PR-2a).

    Parameters
    ----------
    band_legs:
        ``[(as_of_date, {ticker: weight})]`` in ascending date order.
    closes:
        ``{ticker: {date_iso: close}}`` shared adjusted-close panel.
    sub_periods:
        Sub-period records from ``build_portfolio_nav(decompose=True)``.
        None = contrib_nav_pts stays None.

    Returns
    -------
    dict[str, PositionReturn]
        Keyed by ticker.  Empty when ``band_legs`` is empty.
    """
    if not band_legs:
        return {}

    last_weight_map = band_legs[-1][1]

    # Candidates: tickers present at the last rebalance (current holders, weight > 0)
    # PLUS tickers present at the prior rebalance with weight > 0 that now have
    # weight == 0 at the last rebalance (sold at the latest rebalance = "Sold rows").
    candidates: set[str] = set()
    # Current holders.
    for ticker, w in last_weight_map.items():
        if w > 0.0:
            candidates.add(ticker)
    # Sold at latest rebalance: in prior leg with weight > 0, now weight == 0.
    if len(band_legs) >= 2:
        prev_weight_map = band_legs[-2][1]
        for ticker, w_prev in prev_weight_map.items():
            if w_prev > 0.0:
                # Include if they now have weight 0 (sold) or are absent from the last map.
                if last_weight_map.get(ticker, 0.0) <= 0.0:
                    candidates.add(ticker)

    # Build the full per-ticker legs list (all rebalances — same as per_quarter).
    ticker_all_legs: dict[str, list[tuple[str, float]]] = {}
    for date_iso, weight_map in band_legs:
        for ticker, weight in weight_map.items():
            ticker_all_legs.setdefault(ticker, []).append((date_iso, weight))

    # Build Carino grid when sub_periods are available.
    kt_over_K: list[float] | None = None
    ticker_date_weights: dict[str, dict[str, float]] = {}
    if sub_periods is not None:
        kt_over_K, _K, _clamp = _build_carino_grid(sub_periods)
        # Build per-ticker {date: weight} lookup from band_legs.
        for date_iso, weight_map in band_legs:
            for ticker, weight in weight_map.items():
                ticker_date_weights.setdefault(ticker, {})[date_iso] = weight

    # Full ordered rebalance-date axis for gap-aware streak splitting.
    all_rebalance_dates_flat: list[str] = [d for d, _ in band_legs]

    result: dict[str, PositionReturn] = {}
    for ticker in candidates:
        legs = ticker_all_legs.get(ticker, [])
        try:
            streaks = _extract_streaks(
                ticker, legs, closes,
                all_rebalance_dates=all_rebalance_dates_flat,
            )
            if not streaks:
                result[ticker] = PositionReturn(
                    mwr_pct=None,
                    twr_pct=None,
                    contrib_nav_pts=None,
                    since_date=None,
                    partial_history=False,
                    legs_used=0,
                )
                continue

            streak = streaks[-1]

            # Current holder iff weight > 0 at the LAST rebalance.
            is_current = (last_weight_map.get(ticker, 0.0) > 0.0)

            twr_pct, partial_history, legs_used, since_date = _compute_twr(
                ticker, streak, closes,
                is_current_holder=is_current,
                end_date=None,  # flat field always marks to latest close for holders
            )
            mwr_pct = _compute_mwr(
                ticker, streak, closes,
                is_current_holder=is_current,
                end_date=None,
            )

            # Carino contribution (LIFETIME across all sub-periods).
            contrib_nav_pts: float | None = None
            if sub_periods is not None and kt_over_K is not None:
                try:
                    contrib_raw = _compute_contribution_from_sub_periods(
                        ticker,
                        ticker_date_weights.get(ticker, {}),
                        sub_periods,
                        kt_over_K,
                    )
                    # Report in NAV base-100 points (fraction × 100).
                    contrib_nav_pts = contrib_raw * 100.0
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "_compute_flat_latest_returns: Carino error for %s (graceful skip)",
                        ticker,
                        exc_info=True,
                    )
                    contrib_nav_pts = None

            result[ticker] = PositionReturn(
                mwr_pct=mwr_pct,
                twr_pct=twr_pct,
                contrib_nav_pts=contrib_nav_pts,
                since_date=since_date,
                partial_history=partial_history,
                legs_used=legs_used,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "_compute_flat_latest_returns: error for %s (graceful skip)",
                ticker,
                exc_info=True,
            )
            result[ticker] = PositionReturn(
                mwr_pct=None,
                twr_pct=None,
                contrib_nav_pts=None,
                since_date=None,
                partial_history=True,
                legs_used=0,
            )

    return result


def compute_position_returns(
    band_legs: list[tuple[str, dict[str, float]]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    portfolio_nav_net: list[float | None],
    portfolio_nav_dates: list[str],
    sub_periods: list[SubPeriod] | None = None,
) -> dict[str, PositionReturn]:
    """Compute per-position MWR, TWR, and (optionally) Carino contribution.

    Returns the PR-1-compatible flat position-return map: current holders AT the
    latest rebalance PLUS names sold at the latest rebalance (marked-to-exit close).

    When ``sub_periods`` is provided (from ``build_portfolio_nav(decompose=True)``),
    also computes ``contrib_nav_pts`` using the window-global Carino (1999) grid.
    Otherwise ``contrib_nav_pts`` is None (backward-compat with PR-2a).

    Parameters
    ----------
    band_legs:
        ``[(as_of_date, {ticker: weight})]`` — the V55 hysteresis band book legs
        in ascending date order.  Mirrors the ``band_legs_for_nav`` variable in
        ``backfill_portfolio_pit.py``.
    closes:
        ``{ticker: {date_iso: close}}`` — the shared adjusted-close panel built by
        ``_build_price_panel`` (same series used by ``build_portfolio_nav``; Condition C1).
    portfolio_nav_net:
        Accepted for API compat; unused in contribution math (Carino uses gross NAV
        from sub_periods directly).
    portfolio_nav_dates:
        Accepted for API compat; unused in contribution math.
    sub_periods:
        Sub-period records from ``build_portfolio_nav(decompose=True)``.  When
        provided, enables LIFETIME Carino contributions.  None = stub (PR-2a compat).

    Returns
    -------
    dict[str, PositionReturn]
        Keyed by ticker — current holders + names sold at the latest rebalance.
    """
    return _compute_flat_latest_returns(band_legs, closes, sub_periods=sub_periods)


def compute_position_returns_per_quarter(
    band_legs: list[tuple[str, dict[str, float]]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    portfolio_nav_net: list[float | None],
    portfolio_nav_dates: list[str],
) -> list[dict[str, PositionReturn]]:
    """Compute per-position returns for EVERY rebalance quarter.

    Returns one ``{ticker: PositionReturn}`` map per rebalance entry in
    ``band_legs``, enabling the rotation-history drawers to display attribution
    for each historical holding quarter.

    For each quarter i the map covers every ticker that held a non-zero weight
    at rebalance i.  ``is_current_holder=True`` for the ticker within quarter i
    when the position was still held at the NEXT rebalance boundary (or is the
    last rebalance overall).  Non-latest quarters mark to the close on or before
    the next rebalance date (``end_date``).

    Condition C1: ``closes`` must be the SAME adjusted-close series used by
    ``build_portfolio_nav`` (no mixing raw/adjusted prices).

    Note: per-quarter ``contrib_nav_pts`` is ``None`` — the window-global Carino
    grid is defined over the FULL attribution window, not individual quarters.
    The flat ``compute_position_returns`` function provides LIFETIME contributions.

    Parameters
    ----------
    band_legs:
        ``[(as_of_date, {ticker: weight})]`` — the V55 hysteresis band book legs.
    closes:
        Shared adjusted-close panel.
    portfolio_nav_net:
        Daily net NAV series.
    portfolio_nav_dates:
        ISO date strings for the NAV series.

    Returns
    -------
    list[dict[str, PositionReturn]]
        One map per rebalance (same length as ``band_legs``).  An empty list
        when ``band_legs`` is empty.
    """
    if not band_legs:
        return []

    # Build the full per-ticker legs list (across ALL rebalances).
    # For per-quarter computation we TRUNCATE this to legs with date <= rebal_date
    # inside the loop to eliminate look-ahead (Fix #3 — per-quarter PIT look-ahead).
    ticker_all_legs: dict[str, list[tuple[str, float]]] = {}
    for date_iso, weight_map in band_legs:
        for ticker, weight in weight_map.items():
            ticker_all_legs.setdefault(ticker, []).append((date_iso, weight))

    # The last rebalance date — used to identify "current" holders.
    last_rebal_date = band_legs[-1][0]

    # Full ordered rebalance-date axis for gap-aware streak splitting.
    # Each per-quarter iteration passes a PIT-truncated prefix of this list.
    all_dates_full: list[str] = [d for d, _ in band_legs]

    # Per-rebalance maps.
    results: list[dict[str, PositionReturn]] = []

    for rebal_idx, (rebal_date, weight_map) in enumerate(band_legs):
        # The next rebalance date is the end_date for non-latest quarters.
        is_last_rebal = (rebal_idx == len(band_legs) - 1)
        next_rebal_date: str | None = None if is_last_rebal else band_legs[rebal_idx + 1][0]

        # PIT-truncated rebalance axis for gap detection: dates up to and including
        # rebal_date only — mirrors the Fix-#3 leg truncation so gap detection
        # stays PIT-safe with no look-ahead.
        pit_rebalance_dates = all_dates_full[: rebal_idx + 1]

        quarter_map: dict[str, PositionReturn] = {}

        for ticker in weight_map:
            weight_here = weight_map[ticker]
            if weight_here <= 0.0:
                continue  # skip tickers with zero weight this rebalance

            # Fix #3 — PIT look-ahead elimination: truncate legs to those with
            # date <= rebal_date so historical quarters do not chain prices through
            # future rebalance dates.  The latest rebalance uses the full leg list
            # (no truncation needed: it IS the last date).
            all_legs = ticker_all_legs.get(ticker, [])
            if is_last_rebal:
                legs = all_legs
            else:
                legs = [(d, w) for d, w in all_legs if d <= rebal_date]

            try:
                streaks = _extract_streaks(
                    ticker, legs, closes,
                    all_rebalance_dates=pit_rebalance_dates,
                )
                if not streaks:
                    quarter_map[ticker] = PositionReturn(
                        mwr_pct=None,
                        twr_pct=None,
                        contrib_nav_pts=None,
                        since_date=None,
                        partial_history=False,
                        legs_used=0,
                    )
                    continue

                # Use only the current (latest) streak — re-entry after gap discards history.
                streak = streaks[-1]

                # A ticker is a "current holder" at this rebalance when its streak
                # is still open at this point.  For non-latest quarters, is_current=True
                # means the position is open at rebal_date (it has weight > 0 in the
                # truncated legs); the terminal price marks to close on or before the
                # NEXT rebalance date (not to latest-close, which would be look-ahead).
                if is_last_rebal:
                    # Latest rebalance: current holder iff weight > 0 at last_rebal_date.
                    is_current = (
                        all_legs and all_legs[-1][1] > 0.0 and all_legs[-1][0] == last_rebal_date
                    )
                else:
                    # Non-latest rebalance: "current" if the streak is open (not yet sold)
                    # at rebal_date within the truncated leg window.  Terminal price marks
                    # to close on or before next_rebal_date (not beyond).
                    is_current = True

                # TWR
                twr_pct, partial_history, legs_used, since_date = _compute_twr(
                    ticker, streak, closes,
                    is_current_holder=is_current,
                    end_date=next_rebal_date,
                )

                # MWR
                mwr_pct = _compute_mwr(
                    ticker, streak, closes,
                    is_current_holder=is_current,
                    end_date=next_rebal_date,
                )

                # Per-quarter contrib_nav_pts stays None — the window-global Carino
                # grid is defined over the FULL attribution window, not individual
                # quarters.  The flat compute_position_returns provides LIFETIME
                # contributions instead.
                contrib_nav_pts: float | None = None

                quarter_map[ticker] = PositionReturn(
                    mwr_pct=mwr_pct,
                    twr_pct=twr_pct,
                    contrib_nav_pts=contrib_nav_pts,
                    since_date=since_date,
                    partial_history=partial_history,
                    legs_used=legs_used,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "compute_position_returns_per_quarter: error for %s at %s (graceful skip)",
                    ticker,
                    rebal_date,
                    exc_info=True,
                )
                quarter_map[ticker] = PositionReturn(
                    mwr_pct=None,
                    twr_pct=None,
                    contrib_nav_pts=None,
                    since_date=None,
                    partial_history=True,
                    legs_used=0,
                )

        results.append(quarter_map)

    return results


def compute_window_contributions(
    sub_periods: list[SubPeriod],
    kt_over_K: list[float],
) -> dict[int, dict[str, float]]:
    """Compute per-window Carino contributions for every ticker across all sub-periods.

    This is the per-window primitive consumed by the PR-2b display layer.  Each
    value ``result[t][ticker]`` is the Carino-weighted contribution of ``ticker``
    in sub-period ``t``:

        c_{i,t} = (k_t / K) · w_{i,t} · (ρ_{i,t} − 1)

    Summing over all windows gives the LIFETIME contribution from
    ``_compute_contribution_from_sub_periods``:

        C_i = Σ_t result[t][ticker]     (== contrib_nav_pts / 100 for that ticker)

    Summing over all tickers for a fixed window gives the Carino-weighted
    single-window contribution (fraction of R^g_port attributable to that window):

        Σ_i result[t][ticker] = (k_t / K) · R^g_t

    Parameters
    ----------
    sub_periods:
        Sub-period records from ``build_portfolio_nav(decompose=True)``.
        Must be non-empty and aligned with ``kt_over_K``.
    kt_over_K:
        Per-sub-period Carino linking ratio ``k_t / K`` from
        ``_build_carino_grid``.  Must have the same length as ``sub_periods``.

    Returns
    -------
    dict[int, dict[str, float]]
        ``{window_index: {ticker: contribution_fraction}}``.
        Tickers with zero weight in a window are omitted from that window's dict.
        Windows where a price-relative is missing produce ``None`` for that ticker
        (never raise).  An empty ``sub_periods`` returns ``{}``.

    Notes
    -----
    Rule 18 (observability-before-wiring): this function is emitted as a
    diagnostic primitive for PR-2b display; it does NOT feed production
    scoring, vetoes, or the composite.
    """
    if not sub_periods:
        return {}

    result: dict[int, dict[str, float]] = {}
    for t, sp in enumerate(sub_periods):
        window_contribs: dict[str, float] = {}
        for ticker, w in sp.start_weights_gross.items():
            if w == 0.0:
                continue
            rho = sp.price_relatives.get(ticker)
            if rho is None:
                # Missing price-relative: emit None, never raise (graceful degradation).
                window_contribs[ticker] = None  # type: ignore[assignment]
                continue
            r_pos_t = rho - 1.0
            window_contribs[ticker] = kt_over_K[t] * w * r_pos_t
        result[t] = window_contribs
    return result


def reconciliation_errors(
    position_returns: dict[str, PositionReturn],
    portfolio_nav_net: list[float | None],
    portfolio_nav_dates: list[str],
    band_legs: list[tuple[str, dict[str, float]]],
    closes: Mapping[str, Mapping[str, float]] | None = None,
    *,
    sub_periods: list[SubPeriod] | None = None,
) -> tuple[float | None, float | None, float | None, int]:
    """Compute the four reconciliation diagnostic counters.

    Parameters
    ----------
    position_returns:
        Latest-quarter position returns (from ``compute_position_returns`` or
        the last entry of ``compute_position_returns_per_quarter``).
    portfolio_nav_net:
        Daily net NAV series.
    portfolio_nav_dates:
        ISO date strings for the NAV series.
    band_legs:
        Band-book legs (for streak identification).
    closes:
        Shared adjusted-close panel.  When provided, enables the TWR vs
        client-side point-to-point comparison.  None = PR-1 compat (pp_twr → None).
    sub_periods:
        Sub-period records from ``build_portfolio_nav(decompose=True)``.
        When provided, enables C3 reconciliation counters (carino_error +
        cost_line_residual).  None = those two remain None.

    Returns
    -------
    (gross_identity_error, cost_line_residual, pp_twr_error, carino_clamp_count)
        gross_identity_error:
            ``max(|Σ_t (k_t/K)·R^g_t − R^g_port|, max_t |Σ_i w_{i,t}·(ρ_{i,t}−1) − R^g_t|)``
            — the stricter of the full-period Carino chain error and the worst
            per-window BHB primitive error (expected ~1e-11).  Computed directly
            from ``sub_periods`` — NOT from the flat ``position_returns`` map
            (which covers only current/recently-sold tickers, not the full
            attribution universe).  None when ``sub_periods`` is None.
        cost_line_residual:
            |R^g_port + C_cost − R^n_port| — how close the net identity closes
            (expected ~1e-11 with un-rounded δ_t; C_cost = Σ_t (k_t/K)·(−δ_t)).
            None when ``sub_periods`` is None or net NAV unavailable.
        pp_twr_error:
            max |engine TWR − client-side point-to-point return| in percentage
            points, over clean full-history single-streak names.
            None when no eligible names exist or ``closes`` is not provided.
        carino_clamp_count:
            Number of sub-periods where 1+R^g_t ≤ 0 (clamped to k_t=1).
            0 when ``sub_periods`` is None.
    """
    # --- C3 Carino GROSS identity ---
    gross_identity_error: float | None = None
    cost_line_residual: float | None = None
    carino_clamp_count_out: int = 0

    if sub_periods is not None:
        try:
            # Build the Carino grid to get R^g_port and clamp count.
            kt_over_K, K, carino_clamp_count_out = _build_carino_grid(sub_periods)

            # R^g_port from geometric linking.
            gross_product = 1.0
            for sp in sub_periods:
                gross_product *= 1.0 + sp.gross_sub_return
            R_port_gross = gross_product - 1.0

            # --- GROSS identity: SubPeriod-based (fix for PR-2c reconciliation bug) ---
            # The old code summed contrib_nav_pts from _pos_returns (flat current-basket
            # only, ~10 tickers) and compared against R^g_port (+832% full 10y).
            # That pairing is incoherent: the flat map covers ONLY current/recently-sold
            # tickers, NOT the full attribution universe across all rebalance windows.
            #
            # Correct check: verify both the per-window BHB identity and the full-period
            # Carino chain DIRECTLY from SubPeriod records (which already hold all
            # position weights and price relatives for every window):
            #
            #   Per-window BHB:  Σ_i w_{i,t}·(ρ_{i,t}−1) = R^g_t    (engine invariant)
            #   Carino chain:    Σ_t (k_t/K)·R^g_t        = R^g_port  (~1e-11)
            #
            # Both checks use only sub_periods — no position_returns needed for GROSS.

            # 1. Per-window BHB primitive: max_t |Σ_i w·(ρ−1) − R^g_t|
            max_window_bhb_err: float = 0.0
            for sp in sub_periods:
                bhb_sum = sum(
                    w * (sp.price_relatives.get(ticker, 1.0) - 1.0)
                    for ticker, w in sp.start_weights_gross.items()
                )
                window_err = abs(bhb_sum - sp.gross_sub_return)
                if window_err > max_window_bhb_err:
                    max_window_bhb_err = window_err

            # 2. Full-period Carino chain: |Σ_t (k_t/K)·R^g_t − R^g_port|
            carino_chain_sum = sum(
                kt_over_K[t] * sp.gross_sub_return
                for t, sp in enumerate(sub_periods)
            )
            chain_err = abs(carino_chain_sum - R_port_gross)

            gross_identity_error = max(chain_err, max_window_bhb_err)

            # --- Cost line residual (NET identity) ---
            # Σ_i C_i = R^g_port exactly (Carino 1999 §3).  The net identity is:
            #   R^g_port + C_cost = R^n_port
            # where C_cost = Σ_t (k_t/K)·(−δ_t) (Menchero 2000 cost-drag line).
            # Using R^g_port (from SubPeriods) avoids the flat-position-map subset
            # problem that afflicted the old contrib_sum path.
            C_cost = _cost_line_contribution(sub_periods, kt_over_K)
            # R^n_port from geometric linking of net sub-returns.
            net_product = 1.0
            for sp in sub_periods:
                net_product *= 1.0 + sp.net_sub_return
            R_port_net = net_product - 1.0
            cost_line_residual = abs(R_port_gross + C_cost - R_port_net)

        except Exception:  # noqa: BLE001
            logger.warning(
                "reconciliation_errors: Carino C3 check failed (graceful skip)",
                exc_info=True,
            )
            gross_identity_error = None
            cost_line_residual = None
            carino_clamp_count_out = 0

    # --- Client-side point-to-point comparison (unchanged from PR-2a) ---
    pp_errors: list[float] = []
    ticker_legs: dict[str, list[tuple[str, float]]] = {}
    for date_iso, weight_map in band_legs:
        for ticker, weight in weight_map.items():
            ticker_legs.setdefault(ticker, []).append((date_iso, weight))

    if closes is not None:
        for ticker, pr in position_returns.items():
            if pr.partial_history or pr.twr_pct is None or pr.since_date is None:
                continue
            legs = ticker_legs.get(ticker, [])
            # Use empty closes just for streak count check.
            streaks_check = _extract_streaks(ticker, legs, {})
            if len(streaks_check) != 1:
                continue  # skip multi-streak names

            # For clean single-streak names, compute the point-to-point HPR.
            # Entry price = close at since_date; exit price = last close in series
            # (for current holders, same as what _compute_twr marks to).
            entry_px = _close_on(ticker, pr.since_date, closes)
            exit_px = _last_close(ticker, closes)
            if entry_px is None or exit_px is None:
                continue
            if not _is_valid_price(entry_px) or not _is_valid_price(exit_px):
                continue
            pp_return = (exit_px / entry_px - 1.0) * 100.0
            pp_errors.append(abs(pr.twr_pct - pp_return))

    pp_twr_error: float | None = max(pp_errors) if pp_errors else None
    return gross_identity_error, cost_line_residual, pp_twr_error, carino_clamp_count_out


def position_returns_to_dict(
    position_returns: dict[str, PositionReturn],
) -> dict[str, dict]:
    """Serialize ``position_returns`` to a plain dict for JSON embedding.

    Suitable for direct insertion into ``payload["rebalances"][i]["position_returns"]``
    or ``payload["position_returns"]`` in the backtest artifact.

    Returns
    -------
    dict[str, dict]
        ``{ticker: {mwr_pct, twr_pct, contrib_nav_pts, since_date, partial_history, legs_used}}``
    """
    return {
        ticker: {
            "mwr_pct": pr.mwr_pct,
            "twr_pct": pr.twr_pct,
            "contrib_nav_pts": pr.contrib_nav_pts,
            "since_date": pr.since_date,
            "partial_history": pr.partial_history,
            "legs_used": pr.legs_used,
        }
        for ticker, pr in position_returns.items()
    }
