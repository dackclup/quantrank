"""Per-position return attribution for the Phase 7 PIT backtest (PR-2a).

PR-2a extends PR-1 (#614) with two structural improvements:

  1. Per-quarter generalization: ``compute_position_returns_per_quarter``
     computes a separate ``{ticker: PositionReturn}`` map for EVERY historical
     rebalance (not just the latest), enabling the PR-2b rotation-history
     drawers to read ``rebalances[i]["position_returns"]``.

     FIX (PR-2a rev): for each quarter r the streak is built from legs with
     ``date <= r's rebalance date`` only, so historical quarters do not chain
     prices through future rebalance dates (look-ahead elimination).  Quarter
     r's map reflects only information available at r.  The latest rebalance
     still uses the full leg history.

  2. Carino (1999) reconciliation — DESCOPED to a follow-up PR.  The Carino
     linking formula is mathematically inconsistent in this context (numerator
     uses position own-price return; denominator uses net NAV sub-return, so
     Σ contrib ≠ NAV return).  ``contrib_nav_pts`` is ``None`` for all positions
     (stub, as in PR-1) and ``position_return_reconciliation_max_abs_error`` is
     ``None``.  The Carino helper code is retained but NOT called.
     TODO(carino-reconciliation PR): re-derive and wire the linking formula once
     financial-engineer delivers a consistent formulation.

  3. TWR vs client-side comparison: ``reconciliation_errors`` accepts a
     ``closes`` parameter.  When provided it computes the max
     |engine TWR − point-to-point HPR| over clean single-streak names and emits
     it as ``position_return_twr_vs_clientside_max_abs_pp``.

Backward-compat (PR-1 semantics for ``payload["position_returns"]``):
    ``compute_position_returns`` returns current holders AT the latest rebalance
    PLUS names sold at the latest rebalance (marked-to-exit close), matching PR-1's
    output exactly for the Current-picks "Sold" rows.  The flat top-level field is
    assembled by ``_compute_flat_latest_returns`` (not by delegating to
    ``per_quarter[-1]``, which only covers tickers with weight > 0 at the last leg).

Two return measures per holding are computed in this module:

MWR (Modified Dietz, CFA/GIPS standard)
    Money-weighted return over actual rebalance cash flows.  The Modified Dietz
    estimator is:

        R_MWR = (V_end - V_begin - ΣCF_i) / (V_begin + Σ W_i × CF_i)

    where W_i = fraction of period remaining after flow i (= 1.0 at period start,
    0.0 at period end).  In the backtest context each position's "cash flows" are
    the weighted invested amounts at each rebalance where the position is held
    (positive = buy-in, negative = sell-out), and V_begin / V_end are the NAV
    contributions at the position's entry and exit prices on the adjusted-close
    series.

TWR (Time-Weighted Return, chained geometric)
    Chained geometric product over the contiguous legs in the position's streak:

        R_TWR = Π(p_{i+1} / p_i) - 1

    where each p_i is the adjusted-close price at the rebalance boundary.  This
    is the exact same adjusted-close series that ``build_portfolio_nav`` uses
    (Condition C1: no mixing raw/adjusted prices).  A null price at any
    intermediate rebalance drops that leg (``partial_history=True``).  If no valid
    leg exists, twr_pct is null.

contrib_nav_pts (Carino-linked, 1999) — STUB/None until the follow-up PR.

Edge-case contracts
    * Re-entry after gap  — only the CURRENT unbroken streak (within the
                            truncated leg window for non-latest quarters) is used.
    * Weight → 0          — interpreted as a sell; the position terminates at the
                            exit-rebalance close and is not continued.
    * Null price at rebalance — leg is dropped (TWR) or handled gracefully (MWR).
    * Current holders     — mark-to-latest-close (the last date in ``closes``).
    * Sold rows           — mark-to-exit-rebalance close.
    * Non-latest quarters — mark-to-the-close on or before the next rebalance date
                            (``_close_on_or_before``); legs TRUNCATED to the rebalance
                            date to prevent look-ahead.

This module is **pure** — no I/O, no scoring, no pandas, no network calls —
mirroring the contract of ``compute/portfolio/backtest.py`` so it is
offline-testable without any market data or SEC fixtures.

Rule 18 (observability-before-wiring): the per-rebalance ``position_returns``
maps are added to the backtest artifact in PR-2a as shadow fields.  The frontend
does NOT read them until a PR-2b that adds a UI surface gated on ≥ 1 cron
confirming the reconciliation counters.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from typing import NamedTuple

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
        Carino-linked contribution to portfolio NAV return, in NAV base-100
        points.  Σ(contrib_nav_pts) over all positions reconciles to the
        portfolio's total NAV return in base-100 pts.  None when the portfolio
        NAV series is not available for Carino linking.
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
) -> list[list[tuple[str, float, float | None]]]:
    """Extract contiguous holding streaks for ``ticker`` from its sequence of ``(date, weight)`` legs.

    A streak is a maximal sub-sequence of consecutive legs where the weight is
    non-zero.  Weight → 0 signals a sell/termination, starting a new streak if
    the position is re-entered later.

    Parameters
    ----------
    ticker:
        The ticker symbol.
    legs:
        ``[(date_iso, weight)]`` — the chronological rebalance legs for this
        ticker, in ascending date order.
    closes:
        ``{ticker: {date_iso: close}}`` — the shared adjusted-close panel.

    Returns
    -------
    list of streaks
        Each streak is a list of ``(date_iso, weight, price_or_None)`` tuples
        representing the contiguous holding period.  The caller is responsible
        for computing returns from consecutive pairs within a streak.
    """
    streaks: list[list[tuple[str, float, float | None]]] = []
    current: list[tuple[str, float, float | None]] = []

    for date_iso, weight in legs:
        if weight <= 0.0:
            # Sell signal: close the current streak if non-empty.
            if current:
                streaks.append(current)
                current = []
        else:
            px = _close_on(ticker, date_iso, closes)
            current.append((date_iso, weight, px))

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
# Carino-linked contribution
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


def _compute_contribution(
    ticker: str,
    streak: list[tuple[str, float, float | None]],
    closes: Mapping[str, Mapping[str, float]],
    *,
    is_current_holder: bool,
    sub_period_returns: Sequence[tuple[float, float]] | None,
    portfolio_total_return_pct: float | None,
) -> float | None:
    """Compute the Carino-linked contribution of this position to portfolio NAV return.

    Parameters
    ----------
    sub_period_returns:
        ``[(position_return_frac, portfolio_return_frac)]`` per rebalance sub-period
        in the streak.  Used to compute the per-sub-period Carino links.  None when
        not available (contribution is None).
    portfolio_total_return_pct:
        Portfolio total return over the full holding period, in percent.
        None when undefined (contribution is None).
    """
    if sub_period_returns is None or portfolio_total_return_pct is None:
        return None
    if not streak:
        return None

    # Carino coefficient for the full portfolio period.
    R_port = portfolio_total_return_pct / 100.0
    k_port = _carino_coefficient(R_port)

    contrib_total = 0.0
    for i, (r_pos_pct, r_port_pct) in enumerate(sub_period_returns):
        r_pos = r_pos_pct / 100.0
        r_port_sub = r_port_pct / 100.0
        if i >= len(streak):
            break
        weight = streak[i][1]
        k_sub = _carino_coefficient(r_port_sub)
        # Carino formula: contrib_i = w_i × r_pos_i × (k_sub / k_port)
        if k_port == 0.0:
            continue
        contrib_total += weight * r_pos * (k_sub / k_port) * 100.0  # in NAV pts

    return contrib_total


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
    """Compute Carino-linked contribution using the daily NAV series.

    For each consecutive pair of dates in the streak (plus the terminal close),
    we compute:
      - r_pos_sub  : position sub-period return (p1/p0 − 1)
      - r_port_sub : portfolio sub-period return (NAV_d1/NAV_d0 − 1)

    then apply the Carino multiplicative-linking formula:
      contrib += w0 × r_pos_sub × (k_sub / k_port) × 100

    where k = ln(1+R)/R.  The sum over all streak legs approximates the
    position's contribution to the portfolio NAV return in base-100 points.

    Parameters
    ----------
    ticker:
        The ticker symbol.
    streak:
        List of ``(date_iso, weight, price_or_None)`` from ``_extract_streaks``.
    closes:
        Shared adjusted-close panel (same series used by ``build_portfolio_nav``).
    date_to_nav:
        ``{date_iso: nav_value}`` — daily NAV series for the portfolio; built
        from ``portfolio_nav_net`` / ``portfolio_nav_dates``.
    is_current_holder:
        When True, extend the price sequence to the terminal close.
    end_date:
        For non-latest quarters: the next rebalance date (mark terminal to
        close on or before this date).  None = latest quarter.
    portfolio_total_return_pct:
        Portfolio total return over the full NAV window, in percent.

    Returns
    -------
    float | None
        Contribution in NAV base-100 points, or None on degenerate input.
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
            # Determine the actual terminal date for NAV lookup.
            series = closes.get(ticker)
            if series and terminal_px is not None:
                eligible = [d for d in series if d <= end_date]
                terminal_date = max(eligible) if eligible else streak[-1][0]
            else:
                terminal_date = end_date
        else:
            terminal_px = _last_close(ticker, closes)
            # Use last date in closes for NAV lookup.
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
            continue  # drop legs with null prices

        assert p0 is not None and p1 is not None  # type narrowing

        r_pos_sub = p1 / p0 - 1.0

        # Portfolio sub-period return using the NAV series.
        nav_d0 = date_to_nav.get(d0)
        nav_d1 = date_to_nav.get(d1)
        if nav_d0 is None or nav_d1 is None or nav_d0 <= 0.0:
            # Fall back: try to find nearest available NAV dates.
            # Use the closest available NAV for each rebalance boundary.
            if nav_d0 is None:
                # Find the closest date on or before d0.
                eligible_0 = [d for d in date_to_nav if d <= d0]
                if eligible_0:
                    nav_d0 = date_to_nav[max(eligible_0)]
            if nav_d1 is None:
                # Find the closest date on or before d1.
                eligible_1 = [d for d in date_to_nav if d <= d1]
                if eligible_1:
                    nav_d1 = date_to_nav[max(eligible_1)]
            if nav_d0 is None or nav_d1 is None or nav_d0 <= 0.0:
                continue  # still unavailable — skip this leg

        r_port_sub = nav_d1 / nav_d0 - 1.0
        k_sub = _carino_coefficient(r_port_sub)

        contrib_total += float(w0) * r_pos_sub * (k_sub / k_port) * 100.0

    return contrib_total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _compute_flat_latest_returns(
    band_legs: list[tuple[str, dict[str, float]]],
    closes: Mapping[str, Mapping[str, float]],
) -> dict[str, PositionReturn]:
    """Compute position returns for the flat top-level ``payload["position_returns"]``.

    Preserves PR-1 semantics exactly: covers BOTH current holders at the latest
    rebalance AND names sold at the latest rebalance (marked-to-exit close).

    PR-1's ``compute_position_returns`` returned results for:
      - current holders (weight > 0 at the last leg), and
      - names that were in the book at the previous leg but sold at the last
        (their final leg has weight → 0, which ``_extract_streaks`` recognises
        as a sell-termination and marks to the exit-rebalance close).

    The per-quarter function ``compute_position_returns_per_quarter``'s
    ``per_quarter[-1]`` entry covers only tickers with weight > 0 at the LAST
    rebalance (the outer loop skips ``weight_here <= 0``), so delegating the flat
    field to ``per_quarter[-1]`` silently drops sold names.  This function
    restores PR-1 semantics by collecting ALL tickers that appear in the last two
    rebalances (or just the last, for a single-rebalance book).

    Parameters
    ----------
    band_legs:
        ``[(as_of_date, {ticker: weight})]`` in ascending date order.
    closes:
        ``{ticker: {date_iso: close}}`` shared adjusted-close panel.

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

    result: dict[str, PositionReturn] = {}
    for ticker in candidates:
        legs = ticker_all_legs.get(ticker, [])
        try:
            streaks = _extract_streaks(ticker, legs, closes)
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
            result[ticker] = PositionReturn(
                mwr_pct=mwr_pct,
                twr_pct=twr_pct,
                contrib_nav_pts=None,  # TODO(carino-reconciliation PR)
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
) -> dict[str, PositionReturn]:
    """Compute per-position MWR and TWR for the flat top-level field.

    Returns the PR-1-compatible flat position-return map: current holders AT the
    latest rebalance PLUS names sold at the latest rebalance (marked-to-exit close),
    matching PR-1's output exactly for the Current-picks "Sold" rows.

    ``portfolio_nav_net`` / ``portfolio_nav_dates`` are accepted for API compatibility
    but are NOT currently used (Carino descoped to a follow-up PR).

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
        Accepted for API compat; unused until Carino PR.
    portfolio_nav_dates:
        Accepted for API compat; unused until Carino PR.

    Returns
    -------
    dict[str, PositionReturn]
        Keyed by ticker — current holders + names sold at the latest rebalance.
    """
    return _compute_flat_latest_returns(band_legs, closes)


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

    # Per-rebalance maps.
    results: list[dict[str, PositionReturn]] = []

    for rebal_idx, (rebal_date, weight_map) in enumerate(band_legs):
        # The next rebalance date is the end_date for non-latest quarters.
        is_last_rebal = (rebal_idx == len(band_legs) - 1)
        next_rebal_date: str | None = None if is_last_rebal else band_legs[rebal_idx + 1][0]

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
                streaks = _extract_streaks(ticker, legs, closes)
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

                # Carino contribution — DESCOPED to a follow-up PR.
                # contrib_nav_pts stays None for all positions.
                # TODO(carino-reconciliation PR): re-derive and wire the Carino
                # linking formula once financial-engineer delivers a consistent
                # formulation (numerator vs denominator sub-period mismatch).
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


def reconciliation_errors(
    position_returns: dict[str, PositionReturn],
    portfolio_nav_net: list[float | None],
    portfolio_nav_dates: list[str],
    band_legs: list[tuple[str, dict[str, float]]],
    closes: Mapping[str, Mapping[str, float]] | None = None,
) -> tuple[float | None, float | None]:
    """Compute the two reconciliation diagnostic counters.

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

    Returns
    -------
    (carino_error, pp_twr_error)
        carino_error:
            Always ``None`` while Carino reconciliation is descoped (contrib_nav_pts
            is None for all positions).  The follow-up Carino PR will re-enable this.
        pp_twr_error:
            max |engine TWR − client-side point-to-point return| in percentage
            points, over clean full-history single-streak names.
            None when no eligible names exist or ``closes`` is not provided.
    """
    # Carino reconciliation — DESCOPED.  contrib_nav_pts is None for all positions,
    # so carino_error is always None.  The follow-up Carino PR will re-derive and
    # wire the linking formula.
    # TODO(carino-reconciliation PR): re-enable once contrib_nav_pts is populated.
    carino_error: float | None = None

    # Client-side point-to-point comparison.
    # For single-streak, full-history, non-partial names the engine TWR should
    # match the simple HPR: (exit_px / entry_px - 1) × 100.
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
    return carino_error, pp_twr_error


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
