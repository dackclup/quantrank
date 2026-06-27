"""Tests for ``compute.portfolio.backtest`` — pure NAV math, no market data.

The backtest NAV engine is deliberately scoring-agnostic + pandas-free, so its
buy-and-hold-drift / gross-vs-net / delisting math is unit-testable from hand-
authored close series (Phase 7.0 PR-2b).
"""
from __future__ import annotations

from datetime import date

import pytest

from compute.portfolio.backtest import (
    align_benchmark_nav,
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


# --- benchmark alignment ------------------------------------------------------


def test_align_benchmark_nav_subset_dates_rebased() -> None:
    out = align_benchmark_nav(
        ["2021-01-04", "2021-01-06"],
        ["2021-01-04", "2021-01-05", "2021-01-06"],
        [400.0, 410.0, 420.0],
    )
    # rebased to 100 at the first portfolio date (400) -> 420/400*100 = 105
    assert out == pytest.approx([100.0, 105.0])


def test_align_benchmark_nav_forward_fills_missing_date() -> None:
    out = align_benchmark_nav(
        ["2021-01-04", "2021-01-05", "2021-01-06"],
        ["2021-01-04", "2021-01-06"],  # benchmark has no 01-05
        [400.0, 440.0],
    )
    # 01-05 forward-fills the 400 close -> 100; 01-06 = 440/400*100 = 110
    assert out == pytest.approx([100.0, 100.0, 110.0])


# --- Option-B dividend-pool-and-redeploy (issue #620) -------------------------


def test_div_pool_none_dividends_byte_identical() -> None:
    """dividends=None (or price_basis="adjusted") must produce BYTE-IDENTICAL output."""
    dates = ["2021-01-04", "2021-01-05", "2021-01-06"]
    closes = {"AAA": {"2021-01-04": 100.0, "2021-01-05": 105.0, "2021-01-06": 102.0}}
    reb = [("2021-01-04", {"AAA": 1.0})]

    baseline = build_portfolio_nav(dates, closes, reb)
    # dividends=None is the default: must be byte-identical
    with_none = build_portfolio_nav(dates, closes, reb, dividends=None)
    # price_basis="adjusted" with no dividends: also byte-identical
    with_adj = build_portfolio_nav(dates, closes, reb, price_basis="adjusted")
    # dividends supplied but price_basis="adjusted": guard deactivates, byte-identical
    dummy_divs = {"AAA": {"2021-01-05": 1.0}}
    with_divs_adj = build_portfolio_nav(dates, closes, reb, dividends=dummy_divs, price_basis="adjusted")

    assert baseline["gross"] == with_none["gross"]
    assert baseline["net"] == with_none["net"]
    assert baseline["gross"] == with_adj["gross"]
    assert baseline["net"] == with_adj["net"]
    assert baseline["gross"] == with_divs_adj["gross"]
    assert baseline["net"] == with_divs_adj["net"]
    # None path must NOT have cash_at_rebalance key
    assert "cash_at_rebalance" not in baseline
    assert "cash_at_rebalance" not in with_none
    assert "cash_at_rebalance" not in with_adj
    assert "cash_at_rebalance" not in with_divs_adj


def test_div_pool_accrues_cash_before_redeploy() -> None:
    """Single-name holding: ex-date dividend accumulates in cash and shows up in NAV.

    Setup: buy AAA at $100, flat price thereafter, $1 dividend on day 2.
    At rebalance (day 3) the cash is redeployed — NAV > price-only baseline.
    """
    dates = ["2021-01-04", "2021-01-05", "2021-01-06", "2021-04-14"]
    closes = {
        "AAA": {
            "2021-01-04": 100.0,
            "2021-01-05": 100.0,
            "2021-01-06": 100.0,
            "2021-04-14": 100.0,
        }
    }
    # Rebalance on day 1 (initial), day 4 (redeploy).
    reb = [("2021-01-04", {"AAA": 1.0}), ("2021-04-14", {"AAA": 1.0})]
    dividends = {"AAA": {"2021-01-05": 1.0}}  # $1 ex-date on day 2

    nav_div = build_portfolio_nav(
        dates, closes, reb, dividends=dividends, price_basis="raw", cost_bps_per_side=0.0
    )
    nav_base = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=0.0)

    # After the dividend accrues (day 2 onward), shadow NAV > price-only baseline.
    # Day 1 (initial deploy, no dividend yet): equal.
    assert nav_div["gross"][0] == pytest.approx(nav_base["gross"][0])
    # Day 2: shadow gross = 100 (price) + 1.0 (cash) = 101; baseline = 100.
    assert nav_div["gross"][1] == pytest.approx(101.0)
    assert nav_base["gross"][1] == pytest.approx(100.0)
    # cash_at_rebalance is present on the shadow result.
    assert "cash_at_rebalance" in nav_div
    # First entry is 0.0 (initial leg, no dividends accrued yet).
    assert nav_div["cash_at_rebalance"][0] == pytest.approx(0.0)
    # Second entry is the cash at the second rebalance (net path, $1 div × shares).
    # shares_net ≈ 1.0 share (at $100, invested $100, zero-cost → 1 share), cash ≈ $1.
    assert nav_div["cash_at_rebalance"][1] == pytest.approx(1.0, rel=1e-4)
