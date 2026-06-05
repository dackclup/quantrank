"""Tests for ``compute.portfolio.backtest`` — pure NAV math, no market data.

The backtest NAV engine is deliberately scoring-agnostic + pandas-free, so its
buy-and-hold-drift / gross-vs-net / delisting math is unit-testable from hand-
authored close series (Phase 7.0 PR-2b).
"""
from __future__ import annotations

from datetime import date

import pytest

from compute.portfolio.backtest import (
    build_portfolio_nav,
    quarterly_rebalance_dates,
    rebase,
)

# --- rebalance-date generation ------------------------------------------------


def test_quarterly_rebalance_dates_in_window() -> None:
    out = quarterly_rebalance_dates(date(2021, 6, 1), date(2022, 6, 30), lag_days=45)
    # quarter-end + 45d: Q2'21 -> 2021-08-14, Q3'21 -> 11-14, Q4'21 -> 2022-02-14,
    # Q1'22 -> 05-15; Q2'22 -> 08-14 falls past end and is excluded.
    assert date(2021, 8, 14) in out
    assert date(2021, 11, 14) in out
    assert date(2022, 2, 14) in out
    assert date(2022, 5, 15) in out
    assert all(date(2021, 6, 1) <= d <= date(2022, 6, 30) for d in out)
    assert out == sorted(out)


def test_quarterly_rebalance_dates_roughly_quarterly() -> None:
    out = quarterly_rebalance_dates(date(2021, 1, 1), date(2025, 12, 31))
    assert 18 <= len(out) <= 21  # ~4/yr over 5y


# --- rebase utility -----------------------------------------------------------


def test_rebase_to_base() -> None:
    assert rebase([50.0, 75.0, 100.0], base=100.0) == [100.0, 150.0, 200.0]
    assert rebase([200.0, 100.0], base=100.0) == [100.0, 50.0]


def test_rebase_skips_leading_none_and_zero() -> None:
    out = rebase([None, 0.0, 200.0, 300.0], base=100.0)
    assert out[0] is None
    assert out[2] == pytest.approx(100.0)  # anchors on first finite-positive (200)
    assert out[3] == pytest.approx(150.0)


# --- NAV construction ---------------------------------------------------------


def test_single_stock_nav_tracks_return() -> None:
    dates = ["2021-01-04", "2021-01-05", "2021-01-06"]
    closes = {"AAA": {"2021-01-04": 100.0, "2021-01-05": 110.0, "2021-01-06": 99.0}}
    reb = [("2021-01-04", {"AAA": 1.0})]
    nav = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=10.0)

    assert nav["dates"] == dates
    # gross tracks the single holding exactly
    assert nav["gross"] == pytest.approx([100.0, 110.0, 99.0])
    # net starts below gross by the entry cost (turnover 1.0 * 10bps = 0.1%)
    assert nav["net"][0] == pytest.approx(99.9)
    assert nav["net"][1] == pytest.approx(109.89)
    assert nav["turnover_by_rebalance"] == pytest.approx([1.0])


def test_equal_weight_two_stock_zero_cost() -> None:
    dates = ["2021-01-04", "2021-01-05"]
    closes = {
        "AAA": {"2021-01-04": 100.0, "2021-01-05": 120.0},  # +20%
        "BBB": {"2021-01-04": 100.0, "2021-01-05": 100.0},  # flat
    }
    reb = [("2021-01-04", {"AAA": 0.5, "BBB": 0.5})]
    nav = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=0.0)
    # 50/50 of +20% and 0% -> +10%
    assert nav["gross"] == pytest.approx([100.0, 110.0])
    assert nav["net"] == pytest.approx([100.0, 110.0])  # zero cost -> net == gross


def test_net_below_gross_with_turnover_cost() -> None:
    dates = ["2021-01-04", "2021-04-14", "2021-04-15"]
    flat = {"2021-01-04": 100.0, "2021-04-14": 100.0, "2021-04-15": 100.0}
    closes = {"AAA": dict(flat), "BBB": dict(flat)}
    # full switch AAA -> BBB at the 2nd rebalance
    reb = [("2021-01-04", {"AAA": 1.0}), ("2021-04-14", {"BBB": 1.0})]
    nav = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=10.0)

    assert nav["gross"] == pytest.approx([100.0, 100.0, 100.0])  # flat prices
    assert nav["net"][-1] < nav["gross"][-1]  # cost drag
    # entry turnover 1.0 + full switch turnover 2.0 (sell AAA, buy BBB)
    assert nav["turnover_by_rebalance"] == pytest.approx([1.0, 2.0])
    # net = 100 * (1 - 1.0*1e-3) * (1 - 2.0*1e-3)
    assert nav["net"][-1] == pytest.approx(100.0 * 0.999 * 0.998)


def test_higher_cost_lowers_net() -> None:
    dates = ["2021-01-04", "2021-01-05"]
    closes = {"AAA": {"2021-01-04": 100.0, "2021-01-05": 100.0}}
    reb = [("2021-01-04", {"AAA": 1.0})]
    cheap = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=10.0)
    dear = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=30.0)
    assert dear["net"][0] < cheap["net"][0]  # conservative band lands lower


def test_delisting_carry_forward_not_zero() -> None:
    dates = ["2021-01-04", "2021-01-05", "2021-01-06"]
    closes = {"AAA": {"2021-01-04": 100.0}}  # stops trading after day 1
    reb = [("2021-01-04", {"AAA": 1.0})]
    nav = build_portfolio_nav(dates, closes, reb)
    # carry-forward the last close — a delisting is NEVER marked to 0
    assert nav["gross"] == pytest.approx([100.0, 100.0, 100.0])


def test_weights_renormalized_over_priced_names() -> None:
    # BBB has no price at the rebalance -> dropped, AAA's weight renormalized to 1
    dates = ["2021-01-04", "2021-01-05"]
    closes = {"AAA": {"2021-01-04": 100.0, "2021-01-05": 150.0}}
    reb = [("2021-01-04", {"AAA": 0.5, "BBB": 0.5})]
    nav = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=0.0)
    # only AAA priced -> 100% AAA -> tracks AAA (+50%)
    assert nav["gross"] == pytest.approx([100.0, 150.0])
