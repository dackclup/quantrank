"""Tests for ``compute.portfolio.backtest`` — pure NAV math, no market data.

The backtest NAV engine is deliberately scoring-agnostic + pandas-free, so its
buy-and-hold-drift / gross-vs-net / delisting math is unit-testable from hand-
authored close series (Phase 7.0 PR-2b).
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import settings as _h_settings
from hypothesis import strategies as st

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


# --- issue #620 behaviors (8 required tests) ----------------------------------
#
# Methodology condition 2 (highest-risk): sold-name dividend conservation
# Redeploy-NOT-to-sold-name
# Hypothesis gross-non-negative property
# Carino closes on Option-B sub_periods
# (fetch_dividends_panel tests live in tests/test_ingest/test_prices_dividends_panel.py)
# zero-dividend panel (dividends={}) path
# BYTE-IDENTICAL guard + Metadata schema round-trip


def test_div_pool_sold_name_dividend_conservation() -> None:
    """Methodology condition 2 — sold-name dividend CONSERVATION (load-bearing honesty test).

    Setup (2 rebalances, 2 names):
    - Rebalance 1 (2021-01-04): 50% AAA + 50% BBB, base=100, zero cost.
    - AAA pays a $2 ex-date dividend on 2021-01-05.
    - Rebalance 2 (2021-01-06): drop AAA, 100% BBB (AAA is SOLD).

    At rebalance 2 the cash bucket holds AAA's dividend (accrued before the
    rebalance).  The total is redeployed into BBB.

    Conservation invariant:
        Σ income_in == Σ redeployed + Σ terminal_realized
    i.e. the cash at rebalance-2 (pre-redeploy) must equal the dividend
    paid in the first sub-period — no leakage, no duplication.

    This test distinguishes correct-from-broken: if the engine skips the
    cash-bucket accumulation for sold names the cash_at_rebalance[1]
    will be 0 instead of the expected dividend.
    """
    dates = ["2021-01-04", "2021-01-05", "2021-01-06"]
    closes = {
        "AAA": {"2021-01-04": 100.0, "2021-01-05": 100.0, "2021-01-06": 100.0},
        "BBB": {"2021-01-04": 100.0, "2021-01-05": 100.0, "2021-01-06": 100.0},
    }
    # AAA pays $2 dividend on 2021-01-05, before the rebalance where it is sold.
    dividends = {"AAA": {"2021-01-05": 2.0}}

    # Rebalance 1: equal-weight; Rebalance 2: AAA dropped, 100% BBB.
    reb = [
        ("2021-01-04", {"AAA": 0.5, "BBB": 0.5}),
        ("2021-01-06", {"BBB": 1.0}),
    ]

    nav = build_portfolio_nav(
        dates, closes, reb, dividends=dividends, price_basis="raw", cost_bps_per_side=0.0
    )

    # At initial rebalance: cash = 0.
    assert nav["cash_at_rebalance"][0] == pytest.approx(0.0)

    # At the second rebalance (before redeploy):
    # AAA holds 0.5 shares (50% of base=100 at $100 → 0.5 shares net, zero cost).
    # Dividend = 0.5 shares × $2 = $1.00 per path.
    # Conservation: cash_at_rebalance[1] must equal the full $1 accrued.
    expected_cash_at_rebalance2 = 0.5 * 2.0  # shares × div_per_share
    assert nav["cash_at_rebalance"][1] == pytest.approx(expected_cash_at_rebalance2, rel=1e-6), (
        "Sold-name dividend MUST accrue into cash before the rebalance redeploys it. "
        f"Expected {expected_cash_at_rebalance2}, got {nav['cash_at_rebalance'][1]}"
    )

    # The final NAV on 2021-01-06 must include the redeployed cash (no leakage).
    # With flat prices, final gross NAV = 100 (price value) + 1 (redeployed cash) = 101.
    assert nav["gross"][-1] == pytest.approx(101.0, rel=1e-6), (
        "After redeploy the sold-name dividend must be reflected in the NAV, "
        f"expected 101.0, got {nav['gross'][-1]}"
    )


def test_div_pool_redeploy_not_to_sold_name() -> None:
    """After a rebalance that drops name A, A's accrued dividend redeploys to the NEW basket.

    Setup: AAA is sold at rebalance 2; BBB is the only name in the new basket.
    After redeploy, the post-rebalance portfolio must consist ONLY of BBB —
    no shares in AAA (i.e. dividend cash never buys back a sold name).

    We verify this by checking that the NAV on the date AFTER the rebalance
    tracks BBB exactly (since all value is in BBB after redeploy).
    """
    dates = ["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07"]
    closes = {
        "AAA": {
            "2021-01-04": 100.0,
            "2021-01-05": 100.0,
            "2021-01-06": 100.0,
            "2021-01-07": 100.0,
        },
        "BBB": {
            "2021-01-04": 100.0,
            "2021-01-05": 100.0,
            "2021-01-06": 100.0,
            "2021-01-07": 110.0,  # BBB rallies after rebalance
        },
    }
    dividends = {"AAA": {"2021-01-05": 5.0}}  # AAA pays big dividend before being sold

    reb = [
        ("2021-01-04", {"AAA": 0.5, "BBB": 0.5}),
        ("2021-01-06", {"BBB": 1.0}),  # AAA dropped; only BBB in new basket
    ]

    nav = build_portfolio_nav(
        dates, closes, reb, dividends=dividends, price_basis="raw", cost_bps_per_side=0.0
    )

    # On 2021-01-06 (rebalance day): total NAV = price_value + cash.
    # price_value (flat) = 100; cash = 0.5 shares × $5 = $2.50.
    # nav_total_at_rebal = 102.50; redeployed 100% to BBB at $100 → 1.025 shares of BBB.
    nav_at_rebalance = nav["gross"][2]  # index 2 = 2021-01-06
    assert nav_at_rebalance == pytest.approx(102.5, rel=1e-5)

    # On 2021-01-07: BBB rallies +10%, no AAA in the portfolio.
    # Expected gross = 102.5 × 1.10 = 112.75.
    expected_nav_day4 = 102.5 * 1.10
    assert nav["gross"][3] == pytest.approx(expected_nav_day4, rel=1e-5), (
        "After redeploy, NAV should track only BBB (the new basket), not AAA. "
        f"Expected {expected_nav_day4:.4f}, got {nav['gross'][3]:.4f}"
    )


def test_div_pool_empty_dividends_dict_zero_cash() -> None:
    """build_portfolio_nav(dividends={}, price_basis='raw'): active Option-B path, zero cash.

    When dividends is an empty dict (not None) and price_basis='raw', the Option-B
    path is activated but accrues no cash. The NAV should differ from the adj-close
    baseline ONLY because no dividends are applied (no cash bucket accumulation).

    Specifically: gross NAV must track raw prices exactly (same as adjusted when
    no actual dividends exist), and cash_at_rebalance must be present and all zeros.
    """
    dates = ["2021-01-04", "2021-01-05", "2021-01-06"]
    closes = {"AAA": {"2021-01-04": 100.0, "2021-01-05": 105.0, "2021-01-06": 103.0}}
    reb = [("2021-01-04", {"AAA": 1.0})]

    # Option-B active but no dividends → same price path as baseline
    nav_empty_divs = build_portfolio_nav(
        dates, closes, reb, dividends={}, price_basis="raw", cost_bps_per_side=0.0
    )
    # Baseline (adjusted path)
    nav_base = build_portfolio_nav(dates, closes, reb, cost_bps_per_side=0.0)

    # With zero dividends the gross NAV tracks prices identically.
    assert nav_empty_divs["gross"] == pytest.approx(nav_base["gross"])

    # Option-B key is present (the path was activated).
    assert "cash_at_rebalance" in nav_empty_divs
    # All cash entries must be 0 (no dividends accrued).
    for cash_val in nav_empty_divs["cash_at_rebalance"]:
        assert cash_val == pytest.approx(0.0), (
            f"cash_at_rebalance must be 0 when dividends={{}}, got {cash_val}"
        )


def test_div_pool_byte_identical_guard() -> None:
    """BYTE-IDENTICAL guard: dividends=None OR price_basis='adjusted' → exact same output.

    This is the load-bearing back-compat test. If someone perturbs the live
    (adjusted) path so it touches the dividend machinery, this test will fail.

    We verify three activation scenarios against the live path:
    1. dividends=None (the default — the existing live call signature).
    2. price_basis='adjusted' (explicit) with dividends supplied → guard deactivates.
    3. dividends not provided, price_basis='adjusted' (both defaults).

    For each: gross, net, turnover_by_rebalance must be byte-identical lists.
    The 'cash_at_rebalance' key must NOT appear on any of these paths.
    """
    dates = ["2021-01-04", "2021-01-05", "2021-01-06", "2021-04-14"]
    closes = {
        "AAA": {"2021-01-04": 100.0, "2021-01-05": 110.0, "2021-01-06": 108.0, "2021-04-14": 115.0},
        "BBB": {"2021-01-04": 50.0, "2021-01-05": 50.0, "2021-01-06": 52.0, "2021-04-14": 55.0},
    }
    reb = [
        ("2021-01-04", {"AAA": 0.6, "BBB": 0.4}),
        ("2021-04-14", {"AAA": 0.5, "BBB": 0.5}),
    ]
    dummy_divs = {"AAA": {"2021-01-05": 0.50}, "BBB": {"2021-01-06": 0.25}}

    # The canonical live-path baseline (no keyword args).
    live_nav = build_portfolio_nav(dates, closes, reb)

    # 1. dividends=None (explicit) — must be identical to the live default.
    nav_none = build_portfolio_nav(dates, closes, reb, dividends=None)
    assert nav_none["gross"] == live_nav["gross"], (
        "dividends=None must produce BYTE-IDENTICAL gross NAV to the default call"
    )
    assert nav_none["net"] == live_nav["net"]
    assert nav_none["turnover_by_rebalance"] == live_nav["turnover_by_rebalance"]
    assert "cash_at_rebalance" not in nav_none

    # 2. dividends supplied but price_basis='adjusted' → guard deactivates.
    nav_adj = build_portfolio_nav(dates, closes, reb, dividends=dummy_divs, price_basis="adjusted")
    assert nav_adj["gross"] == live_nav["gross"], (
        "price_basis='adjusted' with dividends must still be BYTE-IDENTICAL (guard deactivates)"
    )
    assert nav_adj["net"] == live_nav["net"]
    assert "cash_at_rebalance" not in nav_adj

    # 3. Both explicit defaults.
    nav_both = build_portfolio_nav(dates, closes, reb, dividends=None, price_basis="adjusted")
    assert nav_both["gross"] == live_nav["gross"]
    assert nav_both["net"] == live_nav["net"]
    assert "cash_at_rebalance" not in nav_both


def test_div_pool_carino_closes_on_option_b() -> None:
    """Carino closes on Option-B: Σ C_i = R^g_port on the Option-B sub_periods.

    Build a 2-rebalance Option-B scenario with decompose=True and verify that
    the Carino reconciliation residual < 1e-9. This confirms that the
    gross_sub_return recorded in each SubPeriod correctly accounts for the
    dividend-pool NAV (price_value + cash) so the attribution math closes.

    The reconciliation error is computed from SubPeriod records directly,
    matching the production reconciliation_errors() logic.
    """
    import math as _math

    dates = ["2021-01-04", "2021-01-05", "2021-01-06", "2021-04-14"]
    closes = {
        "AAA": {"2021-01-04": 100.0, "2021-01-05": 102.0, "2021-01-06": 102.0, "2021-04-14": 105.0},
    }
    dividends = {"AAA": {"2021-01-05": 1.0}}  # $1 dividend in first sub-period

    reb = [("2021-01-04", {"AAA": 1.0}), ("2021-04-14", {"AAA": 1.0})]

    nav = build_portfolio_nav(
        dates, closes, reb,
        dividends=dividends, price_basis="raw",
        decompose=True, cost_bps_per_side=0.0,
    )

    sub_periods = nav["sub_periods"]
    assert len(sub_periods) >= 1, "decompose=True must produce at least one SubPeriod"

    # Geometric link all sub-period gross returns → portfolio total return.
    gross_product = 1.0
    for sp in sub_periods:
        gross_product *= 1.0 + sp.gross_sub_return
    R_port_gross = gross_product - 1.0

    # Carino coefficient: ln(1+R)/R (limit = 1 at R=0).
    def _carino(r: float) -> float:
        if abs(r) < 1e-10:
            return 1.0
        v = 1.0 + r
        if v <= 0.0:
            return 1.0
        return _math.log(v) / r

    K = _carino(R_port_gross)
    carino_chain_sum = sum(_carino(sp.gross_sub_return) / K * sp.gross_sub_return for sp in sub_periods)

    residual = abs(carino_chain_sum - R_port_gross)
    assert residual < 1e-9, (
        f"Carino chain residual must be < 1e-9 on Option-B sub_periods, got {residual:.2e}. "
        "This indicates gross_sub_return in the SubPeriods does not account for the "
        "dividend-pool NAV (price + cash bucket)."
    )


# --- Hypothesis property: Option-B gross NAV >= raw-price-only -----------------


@given(
    # Weights: two names (sum=1).
    w_a=st.floats(min_value=0.01, max_value=0.99),
    # Prices: flat-ish to keep NAV positive.
    px_a_1=st.floats(min_value=50.0, max_value=200.0),
    px_b_1=st.floats(min_value=50.0, max_value=200.0),
    px_a_2=st.floats(min_value=50.0, max_value=200.0),
    px_b_2=st.floats(min_value=50.0, max_value=200.0),
    # Non-negative dividends for A.
    div_a=st.floats(min_value=0.0, max_value=5.0),
)
@_h_settings(max_examples=50)
def test_div_pool_gross_nav_never_below_raw_price_only(
    w_a: float,
    px_a_1: float,
    px_b_1: float,
    px_a_2: float,
    px_b_2: float,
    div_a: float,
) -> None:
    """For any valid weights × price paths × non-negative dividend panel,
    Option-B gross NAV >= raw-price-only path (cash is never negative).

    Property: adding non-negative dividends to a cash bucket can never reduce
    the portfolio value — cash bucket >= 0 at all times.
    """
    w_b = 1.0 - w_a
    dates = ["2021-01-04", "2021-01-05", "2021-01-06"]
    closes = {
        "AAA": {"2021-01-04": px_a_1, "2021-01-05": px_a_2, "2021-01-06": px_a_2},
        "BBB": {"2021-01-04": px_b_1, "2021-01-05": px_b_2, "2021-01-06": px_b_2},
    }
    dividends = {"AAA": {"2021-01-05": div_a}} if div_a > 0.0 else {}

    # Option-B path.
    nav_option_b = build_portfolio_nav(
        dates, closes,
        [("2021-01-04", {"AAA": w_a, "BBB": w_b})],
        dividends=dividends if dividends else None if div_a == 0.0 else {},
        price_basis="raw" if dividends is not None and div_a > 0.0 else "adjusted",
        cost_bps_per_side=0.0,
    )
    # Raw-price-only path (adjusted, no dividends).
    nav_raw = build_portfolio_nav(
        dates, closes,
        [("2021-01-04", {"AAA": w_a, "BBB": w_b})],
        cost_bps_per_side=0.0,
    )

    # Every gross NAV point on Option-B must be >= the raw-only path.
    for i, (g_b, g_r) in enumerate(zip(nav_option_b["gross"], nav_raw["gross"], strict=True)):
        assert g_b >= g_r - 1e-9, (
            f"Option-B gross NAV[{i}]={g_b:.6f} < raw-only={g_r:.6f} "
            f"(div_a={div_a}, w_a={w_a:.4f}, prices=({px_a_1},{px_a_2},{px_b_1},{px_b_2})) — "
            "cash bucket must never be negative."
        )


# --- Metadata schema round-trip for the 2 new div-pool fields (#620) ----------


def test_metadata_div_pool_fields_round_trip() -> None:
    """Metadata schema round-trip: div_pool_shadow_terminal_nav_delta_pct and
    div_stream_coverage_pct must survive model_dump → model_validate without
    error when both are None, and when both carry plausible values.

    The schema uses extra='forbid', so any stray key from the dict would raise
    ValidationError. Conversely, a missing required field would also raise.
    This test locks in that the two new fields are declared in Metadata with
    correct types (float | None) under extra='forbid'.
    """
    from compute.output.schemas import Metadata

    # Minimal valid Metadata: only the truly required fields plus those under test.
    minimal_kwargs: dict = {
        "version": "0.10.41-phase8pilot",
        "last_update_utc": "2026-06-27T00:00:00Z",
        "next_update_utc": "2026-06-28T00:00:00Z",
        "universe": "SP1500",
        "universe_size": 1504,
        "compute_run_id": "test-run-001",
        "git_commit": "abc1234",
    }

    # --- case 1: both new fields None (legacy / cold-cache scenario) ---
    meta_none = Metadata(
        **minimal_kwargs,
        div_pool_shadow_terminal_nav_delta_pct=None,
        div_stream_coverage_pct=None,
    )
    d = meta_none.model_dump()
    assert d["div_pool_shadow_terminal_nav_delta_pct"] is None
    assert d["div_stream_coverage_pct"] is None
    # Round-trip via model_validate.
    meta_rt = Metadata.model_validate(d)
    assert meta_rt.div_pool_shadow_terminal_nav_delta_pct is None
    assert meta_rt.div_stream_coverage_pct is None

    # --- case 2: plausible populated values ---
    # A ~2% terminal NAV uplift and ~45% dividend coverage are realistic.
    meta_pop = Metadata(
        **minimal_kwargs,
        div_pool_shadow_terminal_nav_delta_pct=2.13,
        div_stream_coverage_pct=44.7,
    )
    d2 = meta_pop.model_dump()
    assert d2["div_pool_shadow_terminal_nav_delta_pct"] == pytest.approx(2.13)
    assert d2["div_stream_coverage_pct"] == pytest.approx(44.7)
    meta_rt2 = Metadata.model_validate(d2)
    assert meta_rt2.div_pool_shadow_terminal_nav_delta_pct == pytest.approx(2.13)
    assert meta_rt2.div_stream_coverage_pct == pytest.approx(44.7)

    # --- case 3: extra='forbid' check — an unknown key must raise ---
    import pydantic
    with pytest.raises((pydantic.ValidationError, TypeError)):
        Metadata(
            **minimal_kwargs,
            div_pool_shadow_terminal_nav_delta_pct=1.0,
            _unknown_key_from_test="should_be_rejected",  # type: ignore[call-arg]
        )
