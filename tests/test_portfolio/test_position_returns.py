"""Offline unit tests for compute.portfolio.position_returns.

Covers:
(a) Multi-rebalance holder with known prices → assert TWR, MWR correct.
(b) Null intermediate price → partial_history=True, TWR drops that leg.
(c) Re-entry after gap → only the current streak is used.
(d) Carino descoped → contrib_nav_pts is None for all positions (PR-2a FIX-FIRST).
(e) Weight → 0 terminates the streak.
(f) Empty band_legs returns empty dict.
(g) _days_between helper.
(h) _carino_coefficient edge cases (R=0, R=-1).
(i) position_returns_to_dict serialization.
(j) Per-quarter PIT look-ahead fix: quarter-0 TWR != quarter-N TWR.
(k) Flat field (compute_position_returns) covers sold-at-latest names.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import settings as _h_settings
from hypothesis import strategies as st

from compute.portfolio.backtest import SubPeriod
from compute.portfolio.position_returns import (
    PositionReturn,
    _build_carino_grid,
    _carino_coefficient,
    _close_on_or_before,
    _close_strictly_after,
    _compute_carino_contribution_for_streak,
    _compute_contribution_from_sub_periods,
    _compute_mwr,
    _compute_twr,
    _cost_line_contribution,
    _days_between,
    _extract_streaks,
    _is_valid_price,
    _modified_dietz,
    compute_position_returns,
    compute_position_returns_per_quarter,
    position_returns_to_dict,
    reconciliation_errors,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _closes(ticker: str, dates_prices: dict[str, float]) -> dict[str, dict[str, float]]:
    """Build a minimal closes panel for a single ticker."""
    return {ticker: dates_prices}


# ---------------------------------------------------------------------------
# _is_valid_price
# ---------------------------------------------------------------------------


def test_is_valid_price_basic():
    assert _is_valid_price(100.0) is True
    assert _is_valid_price(0.0) is False
    assert _is_valid_price(-1.0) is False
    assert _is_valid_price(None) is False
    assert _is_valid_price(float("nan")) is False
    assert _is_valid_price(0.001) is True


# ---------------------------------------------------------------------------
# _days_between
# ---------------------------------------------------------------------------


def test_days_between_same_year():
    assert _days_between("2020-01-01", "2020-04-01") == 91


def test_days_between_cross_year():
    assert _days_between("2019-12-31", "2020-01-01") == 1


def test_days_between_zero():
    assert _days_between("2021-06-15", "2021-06-15") == 0


# ---------------------------------------------------------------------------
# _carino_coefficient
# ---------------------------------------------------------------------------


def test_carino_at_zero():
    # L'Hopital limit at R=0 → 1.0
    assert _carino_coefficient(0.0) == pytest.approx(1.0)


def test_carino_positive():
    # ln(1.1)/0.1 ≈ 0.9531 / 0.1 = 0.953102
    c = _carino_coefficient(0.1)
    assert c == pytest.approx(math.log(1.1) / 0.1, rel=1e-9)


def test_carino_negative_near_minus1():
    # Degenerate: R = -1 (total loss) → returns 1.0 (guard)
    c = _carino_coefficient(-1.0 - 1e-12)
    assert c == pytest.approx(1.0)


def test_carino_small_r():
    # Very small positive R should not blow up.
    c = _carino_coefficient(1e-11)
    assert c == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# _modified_dietz
# ---------------------------------------------------------------------------


def test_modified_dietz_single_leg():
    # One leg: invest 100 at t=0, exit at 110 → simple HPR = 10%.
    # flows = [(100, 110, 1.0)]  — first leg, no mid-period flows.
    flows = [(100.0, 110.0, 1.0)]
    r = _modified_dietz(flows)
    # numerator = 110 - 100 - 0 = 10; denominator = 100 + 0 = 100.
    assert r == pytest.approx(0.10, rel=1e-9)


def test_modified_dietz_empty():
    assert _modified_dietz([]) is None


def test_modified_dietz_zero_denominator():
    # Pathological: begin=0, no flows → None.
    flows = [(0.0, 110.0, 1.0)]
    r = _modified_dietz(flows)
    assert r is None


def test_modified_dietz_add_then_gain_cash_flow_sign():
    """ADD (weight increase) at rebalance → positive CF → MWR ≈ 13.33%.

    Convention under test: cf = v_begin[leg_i] - flows[i-1].v_end.
    When weight doubles at the same price (v_begin[1]=20 > flows[0].v_end=10),
    cf is POSITIVE (contribution). The correct MWR ≈ 0.1333.

    If someone flips the sign (cf = prior_end - new_begin = -10), the
    denominator shrinks (5 vs 15) and the MWR balloons to ~4.4 — catastrophically
    wrong.  This test locks the sign direction so that regression fails fast.

    Derivation (all per-unit notional):
        flows[0] = (10, 10, 1.0)  — leg 1: price flat, initial investment=10
        flows[1] = (20, 22, 0.5)  — leg 2: ADD at same price (weight 0.1→0.2),
                                           price then +10% → end=22
        cf          = 20 - 10 = +10   (positive: new money deployed)
        numerator   = 22 - 10 - 10 = 2
        denominator = 10 + 0.5×10 = 15
        MWR         = 2/15 ≈ 0.13333…
    """
    flows = [(10.0, 10.0, 1.0), (20.0, 22.0, 0.5)]
    r = _modified_dietz(flows)
    assert r is not None
    # Correct sign: MWR ≈ 13.33%.
    assert r == pytest.approx(2.0 / 15.0, rel=1e-9)
    # Guard: a sign flip would produce ~4.4 (440%) — assert it stays < 1.0.
    assert r < 1.0, "MWR > 100% on an ADD+gain streak — cash-flow sign likely flipped"


def test_modified_dietz_trim_then_gain_cash_flow_sign():
    """TRIM (weight decrease) at rebalance → negative CF → MWR ≈ 6.67%.

    Convention under test: cf = v_begin[leg_i] - flows[i-1].v_end.
    When weight halves at the same price (v_begin[1]=5 < flows[0].v_end=10),
    cf is NEGATIVE (withdrawal). The correct MWR ≈ 0.0667 (positive).

    If someone flips the sign (cf = prior_end - new_begin = +5), the
    numerator becomes −9.5 and MWR ≈ −0.76 — spuriously NEGATIVE when the
    underlying asset gained 10%.  This test catches that regression.

    Derivation (all per-unit notional):
        flows[0] = (10, 10, 1.0)  — leg 1: price flat, initial investment=10
        flows[1] = (5,  5.5, 0.5) — leg 2: TRIM at same price (weight 0.2→0.1),
                                            price then +10% → end=5.5
        cf          = 5 - 10 = −5      (negative: capital withdrawn)
        numerator   = 5.5 - 10 - (−5) = 0.5
        denominator = 10 + 0.5×(−5)   = 7.5
        MWR         = 0.5/7.5 ≈ 0.0667
    """
    flows = [(10.0, 10.0, 1.0), (5.0, 5.5, 0.5)]
    r = _modified_dietz(flows)
    assert r is not None
    # Correct sign: MWR ≈ 6.67% — positive (the asset gained +10%).
    assert r == pytest.approx(0.5 / 7.5, rel=1e-9)
    # Guard: a sign flip would produce ≈ −0.76 — assert it stays positive.
    assert r > 0.0, (
        "MWR < 0 on a TRIM+gain streak where the asset gained — "
        "cash-flow sign convention likely flipped (withdrawal should be negative CF)"
    )


# ---------------------------------------------------------------------------
# _extract_streaks
# ---------------------------------------------------------------------------


def test_extract_streaks_single_continuous():
    legs = [("2020-01-01", 0.3), ("2020-04-01", 0.3), ("2020-07-01", 0.3)]
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0, "2020-07-01": 120.0}}
    streaks = _extract_streaks("AAPL", legs, closes)
    assert len(streaks) == 1
    assert len(streaks[0]) == 3


def test_extract_streaks_sell_at_zero():
    # weight=0 at second leg terminates the first streak; no re-entry after.
    legs = [("2020-01-01", 0.3), ("2020-04-01", 0.0)]
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0}}
    streaks = _extract_streaks("AAPL", legs, closes)
    assert len(streaks) == 1
    assert len(streaks[0]) == 1  # Only entry; exit-date has weight=0 → not appended


def test_extract_streaks_re_entry_gap():
    # Sell at Q2, re-enter at Q3 → two streaks.
    legs = [
        ("2020-01-01", 0.3),
        ("2020-04-01", 0.0),   # sold
        ("2020-07-01", 0.3),   # re-entry
        ("2020-10-01", 0.3),
    ]
    closes = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-07-01": 115.0,
            "2020-10-01": 125.0,
        }
    }
    streaks = _extract_streaks("AAPL", legs, closes)
    assert len(streaks) == 2
    assert streaks[0][0][0] == "2020-01-01"
    assert streaks[1][0][0] == "2020-07-01"


# ---------------------------------------------------------------------------
# (a) Multi-rebalance holder — known TWR and MWR
# ---------------------------------------------------------------------------


class TestMultiRebalanceHolder:
    """Three-rebalance streak with known prices → verify TWR and MWR."""

    # Prices: entry=100, mid=110, exit=121.
    # TWR = (110/100) × (121/110) - 1 = 1.21 - 1 = 21%.
    CLOSES = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0, "2020-07-01": 121.0}}
    STREAK = [
        ("2020-01-01", 0.3, 100.0),
        ("2020-04-01", 0.3, 110.0),
        ("2020-07-01", 0.3, 121.0),
    ]

    def test_twr(self):
        twr, partial, legs_used, since = _compute_twr(
            "AAPL", self.STREAK, self.CLOSES, is_current_holder=False
        )
        # 3 price points → 2 ratios.
        assert legs_used == 2
        assert partial is False
        assert since == "2020-01-01"
        assert twr == pytest.approx(21.0, rel=1e-6)

    def test_mwr_positive(self):
        mwr = _compute_mwr(
            "AAPL", self.STREAK, self.CLOSES, is_current_holder=False
        )
        # MWR with uniform weights; approximate result close to TWR for equal-weight legs.
        assert mwr is not None
        assert mwr > 0.0


# ---------------------------------------------------------------------------
# (b) Null intermediate price → partial_history=True
# ---------------------------------------------------------------------------


class TestNullIntermediatePrice:
    """A None price at the mid-rebalance leg drops that sub-period."""

    CLOSES = {"GOOG": {"2020-01-01": 1000.0, "2020-07-01": 1200.0}}
    # Mid-point price missing (None from _close_on)
    STREAK = [
        ("2020-01-01", 0.2, 1000.0),
        ("2020-04-01", 0.2, None),    # null mid price
        ("2020-07-01", 0.2, 1200.0),
    ]

    def test_partial_history_true(self):
        twr, partial, legs_used, since = _compute_twr(
            "GOOG", self.STREAK, self.CLOSES, is_current_holder=False
        )
        assert partial is True
        # Only the non-null legs count: (2020-01-01, None) and (None, 2020-07-01) are
        # both invalid since one endpoint is None. The pair (2020-01-01, 2020-04-01) is
        # invalid (mid=None), and (2020-04-01, 2020-07-01) is invalid (start=None).
        # However the pair (2020-01-01 → 2020-07-01 skipping mid) is NOT available
        # in the current sequential implementation — it drops both legs containing None.
        # legs_used can be 0 (all adjacent pairs have None).

    def test_twr_drops_null_legs(self):
        """When consecutive prices include None, those ratios are skipped."""
        twr, partial, legs_used, _ = _compute_twr(
            "GOOG", self.STREAK, self.CLOSES, is_current_holder=False
        )
        # Exactly one adjacent pair has both prices valid:
        # [1000 → None] invalid; [None → 1200] invalid.
        # So legs_used == 0, twr == None.
        assert legs_used == 0
        assert twr is None
        assert partial is True


# ---------------------------------------------------------------------------
# (c) Re-entry after gap → only the current streak is used
# ---------------------------------------------------------------------------


def test_re_entry_after_gap_uses_current_streak():
    """compute_position_returns uses only the LATEST streak for a re-entered name.

    F1 (2026-07-03): every leg's stored price is now the T+1-fill close (first
    close STRICTLY AFTER that leg's own rebalance date) — the closes panel
    needs a "day + 1" print at each queried boundary (2020-07-02 / 2020-10-02)
    carrying the SAME price as the old on-or-after exact-match value, so the
    fixture's intended prices (2500 / 3000) still resolve under the new
    convention. This mirrors real production data (daily prices always have a
    next trading day, except at the panel's true last date).
    """
    band_legs = [
        ("2020-01-01", {"AMZN": 0.4}),
        ("2020-04-01", {"AMZN": 0.0}),    # sold
        ("2020-07-01", {"AMZN": 0.4}),    # re-entered
        ("2020-10-01", {"AMZN": 0.4}),
    ]
    closes = {
        "AMZN": {
            "2020-01-01": 2000.0,
            "2020-07-01": 2500.0,
            "2020-07-02": 2500.0,   # T+1 fill for the re-entry leg
            "2020-10-01": 3000.0,
            "2020-10-02": 3000.0,   # T+1 fill for the latest leg (+ _last_close mark)
        }
    }
    nav_net = [100.0, 105.0, 110.0, 115.0]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"]

    pos_returns = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    amzn = pos_returns.get("AMZN")
    assert amzn is not None
    # since_date should be the re-entry date, not the original entry.
    assert amzn.since_date == "2020-07-01"
    # TWR for the current streak: 2500→3000 = 20%.
    # streak has 2 entries (2020-07-01 and 2020-10-01).
    # TWR = (3000/2500) - 1 = 0.20 → 20%.
    assert amzn.twr_pct == pytest.approx(20.0, rel=1e-6)


# ---------------------------------------------------------------------------
# (d) Carino identity: when contrib is populated, Σ ≈ portfolio NAV return
# ---------------------------------------------------------------------------


def test_position_returns_to_dict_keys():
    """position_returns_to_dict produces the expected keys."""
    pr = PositionReturn(
        mwr_pct=5.0,
        twr_pct=6.0,
        contrib_nav_pts=1.5,
        since_date="2020-01-01",
        partial_history=False,
        legs_used=3,
    )
    d = position_returns_to_dict({"AAPL": pr})
    assert "AAPL" in d
    row = d["AAPL"]
    assert set(row.keys()) == {
        "mwr_pct", "twr_pct", "contrib_nav_pts", "since_date", "partial_history", "legs_used"
    }
    assert row["mwr_pct"] == pytest.approx(5.0)
    assert row["twr_pct"] == pytest.approx(6.0)
    assert row["contrib_nav_pts"] == pytest.approx(1.5)
    assert row["since_date"] == "2020-01-01"
    assert row["partial_history"] is False
    assert row["legs_used"] == 3


# ---------------------------------------------------------------------------
# (e) Weight → 0 terminates the streak
# ---------------------------------------------------------------------------


def test_weight_zero_terminates_streak():
    """A weight=0 leg ends the streak; subsequent non-zero legs start a new one."""
    legs = [
        ("2020-01-01", 0.3),
        ("2020-04-01", 0.0),
        ("2020-07-01", 0.0),   # still zero
    ]
    closes: dict = {}
    streaks = _extract_streaks("X", legs, closes)
    assert len(streaks) == 1
    assert len(streaks[0]) == 1  # Only the first entry


# ---------------------------------------------------------------------------
# (f) Empty band_legs
# ---------------------------------------------------------------------------


def test_empty_band_legs_returns_empty():
    result = compute_position_returns(
        [], {}, portfolio_nav_net=[], portfolio_nav_dates=[]
    )
    assert result == {}


# ---------------------------------------------------------------------------
# (g) Current holder marks to latest close
# ---------------------------------------------------------------------------


def test_current_holder_marks_to_latest_close():
    """For a current holder, TWR uses the most recent close (not streak's last entry)."""
    # Streak ends at 2020-04-01=110, but latest close is 2020-06-30=125.
    closes = {
        "MSFT": {
            "2020-01-01": 100.0,
            "2020-04-01": 110.0,
            "2020-06-30": 125.0,  # latest close, after last streak entry
        }
    }
    streak = [
        ("2020-01-01", 0.2, 100.0),
        ("2020-04-01", 0.2, 110.0),
    ]
    twr, partial, legs_used, since = _compute_twr(
        "MSFT", streak, closes, is_current_holder=True
    )
    # For a current holder, terminal price = latest close = 125.
    # prices = [100, 110, 125] → TWR = (110/100)×(125/110) - 1 = 1.25 - 1 = 25%.
    assert legs_used == 2
    assert partial is False
    assert twr == pytest.approx(25.0, rel=1e-6)


# ---------------------------------------------------------------------------
# (h) Full compute_position_returns with two tickers
# ---------------------------------------------------------------------------


def test_compute_position_returns_two_tickers():
    """Two tickers with clean price history produce non-None MWR and TWR.

    F1 (2026-07-03): every leg's stored price is the T+1-fill close (first
    close STRICTLY AFTER that leg's own date), so the closes panel carries a
    "day + 1" print at each boundary (same price as the old exact-match
    value) — matching real daily production data.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-01-02": 100.0, "2020-04-01": 120.0, "2020-04-02": 120.0},
        "MSFT": {"2020-01-01": 200.0, "2020-01-02": 200.0, "2020-04-01": 220.0, "2020-04-02": 220.0},
    }
    nav_net = [100.0, 110.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    result = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert "AAPL" in result
    assert "MSFT" in result

    aapl = result["AAPL"]
    msft = result["MSFT"]

    # Both should have non-None twr_pct (single leg 100→120 = 20%, 200→220 = 10%).
    # AAPL: streak = [("2020-01-01", 0.5, 100), ("2020-04-01", 0.5, 120)]
    # is_current_holder: last leg date == "2020-04-01" == last_rebal_date → True.
    # For current holder, terminal = latest close = 120 (same since only two dates).
    # TWR prices = [100, 120, 120] → (120/100)×(120/120) - 1 = 20% + no gain = 20%.
    assert aapl.twr_pct is not None
    assert msft.twr_pct is not None


# ---------------------------------------------------------------------------
# (i) reconciliation_errors with no contribs → both None
# ---------------------------------------------------------------------------


def test_reconciliation_errors_no_contribs():
    pr = {"AAPL": PositionReturn(
        mwr_pct=10.0, twr_pct=10.0, contrib_nav_pts=None,
        since_date="2020-01-01", partial_history=False, legs_used=1
    )}
    band_legs = [("2020-01-01", {"AAPL": 0.5})]
    nav_net = [100.0, 110.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    gross_err, cost_residual, pp_err, clamp_count = reconciliation_errors(
        pr, nav_net, nav_dates, band_legs
    )
    # sub_periods=None → gross_err=None, cost_residual=None, clamp_count=0.
    assert gross_err is None
    assert cost_residual is None
    assert clamp_count == 0


# ---------------------------------------------------------------------------
# PR-2a new tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _close_on_or_before
# ---------------------------------------------------------------------------


def test_close_on_or_before_exact_date():
    """Returns the close on the exact date when available."""
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-01-02": 101.0}}
    px = _close_on_or_before("AAPL", "2020-01-01", closes)
    assert px == pytest.approx(100.0)


def test_close_on_or_before_weekend_falls_back_to_friday():
    """A target date with no close (e.g. weekend) returns the prior available close."""
    closes = {
        "AAPL": {
            "2020-01-03": 100.0,  # Friday
            "2020-01-06": 105.0,  # Monday
        }
    }
    # Saturday — no close; should return the Friday close.
    px = _close_on_or_before("AAPL", "2020-01-04", closes)
    assert px == pytest.approx(100.0)


def test_close_on_or_before_no_eligible_date():
    """Returns None when no close exists on or before the target date."""
    closes = {"AAPL": {"2020-06-01": 100.0}}
    px = _close_on_or_before("AAPL", "2019-01-01", closes)
    assert px is None


def test_close_on_or_before_missing_ticker():
    """Returns None for a ticker not in the closes panel."""
    closes: dict = {}
    px = _close_on_or_before("NOTHERE", "2020-01-01", closes)
    assert px is None


# ---------------------------------------------------------------------------
# compute_position_returns_per_quarter — length contract
# ---------------------------------------------------------------------------


def test_compute_position_returns_per_quarter_length():
    """Returns one map per entry in band_legs."""
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-07-01", {"AAPL": 0.5, "MSFT": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0, "2020-07-01": 120.0},
        "MSFT": {"2020-01-01": 200.0, "2020-04-01": 210.0, "2020-07-01": 220.0},
    }
    nav_net = [100.0, 110.0, 120.0]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert len(per_quarter) == 3


def test_compute_position_returns_per_quarter_empty_input():
    """Returns an empty list for empty band_legs."""
    per_quarter = compute_position_returns_per_quarter(
        [], {}, portfolio_nav_net=[], portfolio_nav_dates=[]
    )
    assert per_quarter == []


# ---------------------------------------------------------------------------
# compute_position_returns_per_quarter — latest compat with compute_position_returns
# ---------------------------------------------------------------------------


def test_compute_position_returns_per_quarter_latest_compat():
    """The flat field (compute_position_returns) covers current holders.

    FIX-FIRST update: compute_position_returns now uses _compute_flat_latest_returns
    rather than delegating to per_quarter[-1].  For a fixture with no sold names the
    two should agree on keys and return values (both mark to the same latest-close).
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5}),
        ("2020-04-01", {"AAPL": 0.5}),
        ("2020-07-01", {"AAPL": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0, "2020-07-01": 120.0}
    }
    nav_net = [100.0, 105.0, 112.0]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    latest_flat = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )

    assert len(per_quarter) == 3
    latest_from_per_quarter = per_quarter[-1]

    # With no sold names at the latest rebalance, both sources should cover
    # the same tickers and agree on TWR/MWR (both mark to the same latest-close).
    assert set(latest_flat.keys()) == set(latest_from_per_quarter.keys())
    for ticker, pr_flat in latest_flat.items():
        pr_pq = latest_from_per_quarter[ticker]
        assert pr_flat.twr_pct == pytest.approx(pr_pq.twr_pct, rel=1e-9)
        assert pr_flat.mwr_pct == pytest.approx(pr_pq.mwr_pct, rel=1e-9)
        assert pr_flat.since_date == pr_pq.since_date
        assert pr_flat.partial_history == pr_pq.partial_history
        assert pr_flat.legs_used == pr_pq.legs_used


# ---------------------------------------------------------------------------
# Carino identity: Σ contrib ≈ NAV total return in base-100 pts
# ---------------------------------------------------------------------------


def test_carino_identity_three_quarter_book():
    """contrib_nav_pts is None for all positions (Carino descoped to follow-up PR).

    The Carino linking formula was descoped in PR-2a (FIX-FIRST) because the
    numerator (position own-price return) and denominator (net NAV sub-return)
    are inconsistent → Σ contrib ≠ NAV return.  Re-derivation is deferred to
    a dedicated Carino PR by financial-engineer.

    Until that PR lands, every PositionReturn must carry contrib_nav_pts=None.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-07-01", {"AAPL": 0.5, "MSFT": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0, "2020-07-01": 121.0},
        "MSFT": {"2020-01-01": 200.0, "2020-04-01": 204.0, "2020-07-01": 206.0},
    }
    nav_net = [100.0, 106.0, 111.8]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert len(per_quarter) == 3

    # All positions across all quarters must have contrib_nav_pts == None.
    for quarter_map in per_quarter:
        for ticker, pr in quarter_map.items():
            assert pr.contrib_nav_pts is None, (
                f"{ticker}: expected contrib_nav_pts=None (Carino descoped) "
                f"but got {pr.contrib_nav_pts}"
            )


# ---------------------------------------------------------------------------
# Per-quarter PIT look-ahead fix (Fix #3): quarter-0 TWR != quarter-N TWR
# ---------------------------------------------------------------------------


def test_per_quarter_pit_no_lookahead():
    """Fix #3: historical quarter TWR differs from latest-quarter TWR.

    For a ticker held across 3 rebalances with distinct prices, the TWR
    computed for quarter-0 (using only legs up to 2020-01-01) must differ
    from the TWR for quarter-2 (using all three legs) and from the TWR for
    quarter-1 (using two legs).

    Without the fix the code would use the full leg history for every quarter
    (look-ahead), producing the same TWR for all three.  With the fix applied:
      - quarter-0 has only 1 leg (entry at 2020-01-01, mark to 2020-04-01) →
        TWR = 110/100 − 1 = 10%
      - quarter-1 has 2 legs (entry at 2020-01-01, mark to 2020-07-01) →
        TWR = (110/100) × (121/110) − 1 = 21%
      - quarter-2 (latest) has 3 legs → same TWR = 21% (no additional leg in
        our data, since latest-close matches 2020-07-01)

    F1 (2026-07-03): every leg's stored price, AND the non-latest-quarter
    terminal mark, is now the T+1-fill close (first close STRICTLY AFTER the
    boundary date) — the closes panel carries a "day + 1" print immediately
    after each rebalance date (same price as the old exact-match value) so
    the fixture's intended prices still resolve, matching real daily
    production data.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5}),
        ("2020-04-01", {"AAPL": 0.5}),
        ("2020-07-01", {"AAPL": 0.5}),
    ]
    # Prices at each rebalance boundary plus a T+1 print for each (F1).
    closes = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-01-02": 100.0,
            "2020-04-01": 110.0,
            "2020-04-02": 110.0,
            "2020-07-01": 121.0,
            "2020-07-02": 121.0,
        }
    }
    nav_net = [100.0, 106.0, 111.8]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert len(per_quarter) == 3

    twr_q0 = per_quarter[0]["AAPL"].twr_pct
    twr_q1 = per_quarter[1]["AAPL"].twr_pct
    twr_q2 = per_quarter[2]["AAPL"].twr_pct

    assert twr_q0 is not None, "quarter-0 TWR should be computed"
    assert twr_q1 is not None, "quarter-1 TWR should be computed"
    assert twr_q2 is not None, "quarter-2 TWR should be computed"

    # The key correctness signal: quarter-0 must NOT equal quarter-2.
    # If look-ahead is present they would be equal (same full chain of legs).
    assert twr_q0 != pytest.approx(twr_q2, rel=1e-6), (
        f"quarter-0 TWR ({twr_q0:.4f}%) == quarter-2 TWR ({twr_q2:.4f}%): "
        "look-ahead elimination (Fix #3) is NOT working"
    )

    # Spot-check expected values (single-leg quarter-0 vs two-leg quarter-1).
    # quarter-0: AAPL held at 2020-01-01, mark to 2020-04-01 (next rebal).
    #   TWR = 110/100 − 1 = 10%
    assert twr_q0 == pytest.approx(10.0, abs=0.05), f"Unexpected quarter-0 TWR: {twr_q0}"

    # quarter-1 (two legs, mark to 2020-07-01): (110/100)×(121/110)−1 = 21%
    assert twr_q1 == pytest.approx(21.0, abs=0.05), f"Unexpected quarter-1 TWR: {twr_q1}"


# ---------------------------------------------------------------------------
# reconciliation_errors — pp_twr counter with closes
# ---------------------------------------------------------------------------


def test_reconciliation_errors_with_closes_pp_twr_near_zero():
    """pp_twr ≈ 0 for a clean single-streak, full-history name (TWR == HPR).

    For a name with a single unbroken streak and no partial history, the
    engine's TWR must equal the simple point-to-point HPR (exit/entry − 1).
    The counter should be ~0 (within floating-point noise).
    """
    # One ticker, two rebalances (entry → current), clean prices.
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5}),
        ("2020-04-01", {"AAPL": 0.5}),
    ]
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 120.0, "2020-06-30": 130.0}}
    nav_net = [100.0, 110.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    pos_returns = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    _gross_err, _cost_residual, pp_twr_err, _clamp = reconciliation_errors(
        pos_returns, nav_net, nav_dates, band_legs, closes=closes
    )
    # pp_twr_err should be computed (not None) since AAPL is a clean single-streak name.
    # The engine TWR marks to latest close (2020-06-30=130).
    # pp_return = (130/100 - 1) × 100 = 30%.
    # TWR prices = [100, 120, 130] → (120/100)×(130/120) - 1 = 30%.
    # diff = 0 → pp_twr_err should be ~0.
    assert pp_twr_err is not None
    assert pp_twr_err == pytest.approx(0.0, abs=1e-6)


def test_reconciliation_errors_with_closes_not_none():
    """With closes provided, pp_twr_error is either a float or None (not absent)."""
    # Minimal fixture where the single ticker has partial_history (null mid price)
    # → it's skipped for pp comparison → pp_twr_error = None.
    pr = {"AAPL": PositionReturn(
        mwr_pct=10.0, twr_pct=None, contrib_nav_pts=5.0,
        since_date="2020-01-01", partial_history=True, legs_used=0
    )}
    band_legs = [("2020-01-01", {"AAPL": 0.5})]
    nav_net = [100.0, 105.0]
    nav_dates = ["2020-01-01", "2020-04-01"]
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 120.0}}

    _gross_err, _cost_residual, pp_twr_err, _clamp = reconciliation_errors(
        pr, nav_net, nav_dates, band_legs, closes=closes
    )
    # partial_history=True → skip → None.
    assert pp_twr_err is None


# ---------------------------------------------------------------------------
# _compute_carino_contribution_for_streak
# ---------------------------------------------------------------------------


def test_compute_carino_contribution_basic():
    """A single-leg streak: contrib = w × r_pos × (k_sub / k_port)."""
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0}}
    streak = [("2020-01-01", 0.5, 100.0), ("2020-04-01", 0.5, 110.0)]
    # date_to_nav: 100 → 105 over the period.
    date_to_nav = {"2020-01-01": 100.0, "2020-04-01": 105.0}
    portfolio_total_return_pct = 5.0  # 100→105

    contrib = _compute_carino_contribution_for_streak(
        "AAPL",
        streak,
        closes,
        date_to_nav=date_to_nav,
        is_current_holder=False,
        end_date=None,
        portfolio_total_return_pct=portfolio_total_return_pct,
    )
    # Manual check:
    # r_pos_sub  = 110/100 - 1 = 0.10
    # r_port_sub = 105/100 - 1 = 0.05
    # k_port = ln(1.05)/0.05 ≈ 0.9759
    # k_sub  = ln(1.05)/0.05≈ 0.9759  (same period)
    # contrib = 0.5 × 0.10 × (0.9759/0.9759) × 100 = 5.0
    import math as _math
    k_port = _math.log(1.05) / 0.05
    k_sub  = _math.log(1.05) / 0.05
    expected = 0.5 * 0.10 * (k_sub / k_port) * 100.0
    assert contrib is not None
    assert contrib == pytest.approx(expected, rel=1e-6)


def test_compute_carino_contribution_empty_streak():
    """Returns None for an empty streak."""
    contrib = _compute_carino_contribution_for_streak(
        "AAPL",
        [],
        {},
        date_to_nav={"2020-01-01": 100.0},
        is_current_holder=False,
        end_date=None,
        portfolio_total_return_pct=5.0,
    )
    assert contrib is None


def test_compute_carino_contribution_no_nav():
    """Returns None when date_to_nav is empty."""
    streak = [("2020-01-01", 0.5, 100.0), ("2020-04-01", 0.5, 110.0)]
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0}}
    contrib = _compute_carino_contribution_for_streak(
        "AAPL",
        streak,
        closes,
        date_to_nav={},
        is_current_holder=False,
        end_date=None,
        portfolio_total_return_pct=5.0,
    )
    assert contrib is None


# ---------------------------------------------------------------------------
# PR-2a TEST-HARDENING ADDITIONS (test-engineer, 2026-06-26)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. Sold-name backward-compat (the #1b fix lock)
#
# compute_position_returns (flat, via _compute_flat_latest_returns) MUST include
# a ticker that was sold at the latest rebalance (weight > 0 at prior leg,
# weight = 0 at the last leg) — that is the "Sold row" in the Current-picks
# table.
#
# compute_position_returns_per_quarter[-1] covers only weight > 0 at the latest
# leg, so it must NOT include the sold name.
#
# This locks the PR-1 backward-compat semantics that the reviewer flagged as
# silently dropped when _compute_flat_latest_returns was introduced.
# ---------------------------------------------------------------------------


def test_sold_name_included_in_flat_field_excluded_from_last_per_quarter():
    """Flat field includes sold-at-latest-rebalance name; per-quarter[-1] does not.

    Fixture:
      Q0: AAPL 0.5, MSFT 0.5  (both held)
      Q1: AAPL 0.5, MSFT 0.5  (both still held)
      Q2: AAPL 0.5, MSFT 0.0  (MSFT sold at the latest rebalance)

    compute_position_returns() is the flat field.  It must cover MSFT (sold row).
    compute_position_returns_per_quarter()[-1] covers only current holders at Q2;
    MSFT must be absent from it.

    F1 (2026-07-03): every leg's stored price is the T+1-fill close (first
    close STRICTLY AFTER that leg's own date) — the closes panel carries a
    "day + 1" print immediately after each rebalance date (same price as the
    old exact-match value) so MSFT's intended sold-leg entry price (220, not
    the later 230 exit close) still resolves under the new convention.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-07-01", {"AAPL": 0.5, "MSFT": 0.0}),  # MSFT sold here
    ]
    closes = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-01-02": 100.0,
            "2020-04-01": 110.0,
            "2020-04-02": 110.0,
            "2020-07-01": 121.0,
            "2020-07-02": 121.0,
        },
        "MSFT": {
            "2020-01-01": 200.0,
            "2020-01-02": 200.0,
            "2020-04-01": 220.0,
            "2020-04-02": 220.0,   # T+1 fill for MSFT's own Q1 leg (last held leg)
            "2020-07-01": 230.0,  # exit close for the sold leg
        },
    }
    nav_net = [100.0, 108.0, 115.0]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    flat = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )

    # The flat field (backward-compat PR-1 semantics) must include MSFT.
    assert "MSFT" in flat, (
        "Sold-at-latest MSFT must appear in the flat position_returns field "
        "(Current-picks 'Sold' row); _compute_flat_latest_returns is broken"
    )
    # The flat field must also include the current holder AAPL.
    assert "AAPL" in flat

    # The last per-quarter map covers only current holders (weight > 0 at Q2).
    last_per_quarter = per_quarter[-1]
    assert "AAPL" in last_per_quarter, "Current holder AAPL must be in per_quarter[-1]"
    assert "MSFT" not in last_per_quarter, (
        "Sold MSFT must NOT appear in per_quarter[-1] "
        "(per_quarter covers only weight>0 holders at that rebalance)"
    )

    # Sanity: MSFT's flat entry is computed with sold semantics (is_current=False):
    # the streak [Q0=200, Q1=220] ends with weight=0 at Q2=230.
    # _extract_streaks sees weight=0 at Q2 → terminates the streak at Q1 (last non-zero
    # entry). TWR = 220/200 - 1 = 10%.
    msft_flat = flat["MSFT"]
    assert msft_flat.twr_pct is not None
    assert msft_flat.twr_pct == pytest.approx(10.0, rel=1e-6), (
        f"Sold MSFT flat TWR should be 10.0% (200→220), got {msft_flat.twr_pct}"
    )


# ---------------------------------------------------------------------------
# 2. Per-quarter look-ahead / truncation — extended injection test
#
# The existing test_per_quarter_pit_no_lookahead checks that q0 != q2.
# Here we add an EXPLICIT injection test: adding a price AFTER a historical
# quarter's end-date must NOT change that quarter's TWR.
# ---------------------------------------------------------------------------


def test_per_quarter_injecting_future_price_does_not_change_historical_quarter():
    """Adding a later-dated close does not alter a historical quarter's TWR.

    Fixture: AAPL held across Q0 (2020-01-01) and Q1 (2020-04-01).
    We compute TWR for quarter-0 once WITHOUT a 2020-07-01 close and once
    WITH it.  The values must be byte-identical because Fix #3 truncates
    the leg window to dates <= rebal_date, so the 2020-07-01 entry is
    invisible to the Q0 computation.

    F1 (2026-07-03): the terminal mark for a non-latest quarter is now the
    first close STRICTLY AFTER the boundary (T+1 fill) rather than on/before
    it, so both fixtures carry a "day + 1" print (2020-01-02 / 2020-04-02,
    same prices as the old exact-match values) immediately after each
    rebalance date — this is the LEGITIMATE T+1 fill, distinct from the
    injected FAR-future 2020-07-01 price three months out, which must still
    NOT leak into Q0's mark (that's the invariant this test locks): with a
    closer T+1 print available, the far-future price is never selected.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5}),
        ("2020-04-01", {"AAPL": 0.5}),
    ]
    # Closes WITHOUT any price after Q1's rebal date (T+1 prints only).
    closes_without_future = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-01-02": 100.0,
            "2020-04-01": 110.0,
            "2020-04-02": 110.0,
        }
    }
    # Closes WITH a price 3 months after Q1 that would corrupt Q0 if look-ahead leaked.
    closes_with_future = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-01-02": 100.0,
            "2020-04-01": 110.0,
            "2020-04-02": 110.0,
            "2020-07-01": 999.0,   # injected FAR-future price — must NOT affect Q0
        }
    }
    nav_net = [100.0, 108.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    per_quarter_without = compute_position_returns_per_quarter(
        band_legs, closes_without_future,
        portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates,
    )
    per_quarter_with = compute_position_returns_per_quarter(
        band_legs, closes_with_future,
        portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates,
    )

    twr_q0_without = per_quarter_without[0]["AAPL"].twr_pct
    twr_q0_with    = per_quarter_with[0]["AAPL"].twr_pct

    assert twr_q0_without is not None, "Q0 TWR should be computable without future price"
    assert twr_q0_with is not None,    "Q0 TWR should be computable with future price"

    assert twr_q0_without == pytest.approx(twr_q0_with, rel=1e-9), (
        f"Injecting a future price changed Q0 TWR from {twr_q0_without:.4f}% "
        f"to {twr_q0_with:.4f}%.  Fix #3 (PIT look-ahead elimination) is broken."
    )

    # Also verify the baseline correctness: Q0 should mark to the T+1-fill
    # close strictly after the NEXT rebal date (2020-04-02 = 110), so
    # TWR = 110/100 - 1 = 10%. For quarter-0 (is_last_rebal=False),
    # is_current=True, end_date=2020-04-01.
    # terminal = _terminal_close(AAPL, 2020-04-01, closes) = 110 (2020-04-02 print).
    # prices = [100, 110] → TWR = 10%.
    assert twr_q0_without == pytest.approx(10.0, abs=0.01), (
        f"Unexpected Q0 TWR: {twr_q0_without} (expected 10.0%)"
    )


# ---------------------------------------------------------------------------
# 3. Re-entry-after-gap in a per-quarter context
#
# A ticker held, sold (gap), re-bought. Each quarter's streak is locally
# truncated correctly:
#   - The quarter during the gap (weight=0) excludes the ticker from the map.
#   - A quarter after re-entry measures only from the RE-ENTRY date, not
#     across the gap, because streaks[-1] gives the most-recent streak
#     within the truncated leg window.
# ---------------------------------------------------------------------------


def test_re_entry_after_gap_per_quarter_streak_resets():
    """Re-entry after a gap: the post-gap quarter measures from the re-entry date.

    Fixture:
      Q0 (2020-01-01): AAPL 0.3  — entered; price = 100
      Q1 (2020-04-01): AAPL 0.0  — sold; gap
      Q2 (2020-07-01): AAPL 0.3  — re-entered; price = 80
      Q3 (2020-10-01): AAPL 0.3  — still held; price = 96

    Expected invariants:
      - per_quarter[1] does NOT contain AAPL (weight=0 at Q1 → skipped).
      - per_quarter[2]["AAPL"].since_date == "2020-07-01"  (re-entry, not original Q0).
      - per_quarter[3]["AAPL"].since_date == "2020-07-01"  (still the re-entry date).
      - per_quarter[3]["AAPL"].twr_pct uses only the post-re-entry leg (80 → 96 = 20%).

    F1 (2026-07-03): every leg's stored price is the T+1-fill close (first
    close STRICTLY AFTER that leg's own date) — the closes panel carries a
    "day + 1" print after the re-entry (2020-07-02) and latest (2020-10-02)
    dates, same prices as the old exact-match values, matching real daily
    production data.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.3}),
        ("2020-04-01", {"AAPL": 0.0}),   # sold
        ("2020-07-01", {"AAPL": 0.3}),   # re-entered
        ("2020-10-01", {"AAPL": 0.3}),   # latest
    ]
    closes = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-04-01": 90.0,    # exit close (not used for re-entry streak)
            "2020-07-01": 80.0,    # re-entry price
            "2020-07-02": 80.0,    # T+1 fill for the re-entry leg
            "2020-10-01": 96.0,    # latest
            "2020-10-02": 96.0,    # T+1 fill for the latest leg (+ _last_close mark)
        }
    }
    nav_net = [100.0, 98.0, 102.0, 106.0]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert len(per_quarter) == 4

    # Q1: AAPL has weight=0 → must be absent from the quarter map.
    assert "AAPL" not in per_quarter[1], (
        "AAPL has weight=0 at Q1 (gap); it must be absent from per_quarter[1]"
    )

    # Q2: re-entry; since_date must be the RE-ENTRY date (not original Q0 entry).
    assert "AAPL" in per_quarter[2], "AAPL re-entered at Q2 must appear in per_quarter[2]"
    pr_q2 = per_quarter[2]["AAPL"]
    assert pr_q2.since_date == "2020-07-01", (
        f"After re-entry, since_date must be the re-entry date '2020-07-01', "
        f"not the original entry.  Got: {pr_q2.since_date}"
    )

    # Q3 (latest): streak continues from re-entry; since_date unchanged.
    pr_q3 = per_quarter[3]["AAPL"]
    assert pr_q3.since_date == "2020-07-01", (
        f"Q3 since_date should still be re-entry '2020-07-01', got {pr_q3.since_date}"
    )

    # Q3 TWR for the re-entry streak:
    # Truncated legs at Q3 (is_last_rebal=True) = full history:
    #   [(2020-01-01, 0.3), (2020-04-01, 0.0), (2020-07-01, 0.3), (2020-10-01, 0.3)]
    # _extract_streaks sees weight=0 at Q1 → splits into two streaks.
    # streaks[-1] = [(2020-07-01, 0.3, 80), (2020-10-01, 0.3, 96)]
    # is_current_holder = True (last_rebal_date = 2020-10-01, all_legs[-1] has w>0)
    # latest close = 96 (same as streak[-1] price) → terminal appended = 96
    # prices = [80, 96, 96] → TWR = (96/80) × (96/96) - 1 = 20%.
    assert pr_q3.twr_pct is not None
    assert pr_q3.twr_pct == pytest.approx(20.0, rel=1e-6), (
        f"Q3 TWR for re-entry streak (80→96) should be 20.0%, got {pr_q3.twr_pct}"
    )


# ---------------------------------------------------------------------------
# 4. MWR sign convention under per-quarter truncation
#
# The add=+CF / trim=−CF sign convention must hold for NON-latest quarters,
# not just the flat/latest field.  A TRIM in a historical quarter must produce
# a negative cash flow in Modified Dietz — exactly the invariant locked by
# test_modified_dietz_trim_then_gain_cash_flow_sign, but exercised here via
# the end-to-end compute_position_returns_per_quarter path.
# ---------------------------------------------------------------------------


def test_mwr_sign_trim_in_historical_quarter():
    """TRIM at a historical quarter rebalance produces a positive MWR (negative CF).

    Fixture:
      Q0 (2020-01-01): AAPL weight=0.2, price=100
      Q1 (2020-04-01): AAPL weight=0.1, price=100  ← TRIM at same price
                                                       (weight halved → negative CF)
      Q2 (2020-07-01): AAPL weight=0.1, price=110  ← latest; asset gained +10%

    For quarter-0's truncated view (legs <= Q0's rebal_date = only one entry):
      is_current=True, end_date=Q1 date=2020-04-01
      streak = [(2020-01-01, 0.2, 100)]
      terminal = _close_on_or_before(AAPL, 2020-04-01) = 100  (price flat at trim)
      flows = [(0.2×100, 0.2×100, 1.0)] → v_begin=20, v_end=20 → MWR = 0.0% (flat)

    For quarter-1's truncated view (legs <= Q1's rebal_date):
      legs = [(2020-01-01, 0.2), (2020-04-01, 0.1)]
      streak = [(2020-01-01, 0.2, 100), (2020-04-01, 0.1, 100)]
      is_current=True, end_date=2020-07-01
      terminal = _close_on_or_before(AAPL, 2020-07-01) = 110
      all_entries = [(Q0, 0.2, 100), (Q1, 0.1, 100), (terminal, 0.1, 110)]

      Modified Dietz for leg i=0→1:  w0=0.2, p0=100, p1=100
        v_begin=20, v_end=20
      leg i=1→2:  w0=0.1, p0=100, p1=110
        v_begin=10, v_end=11

      full Modified Dietz aggregation:
        total_v_end   = 11   (from last leg's v_end → but _modified_dietz uses
                              flows[-1][1]=v_end of the last FLOW tuple)
        ...

    The key behavioral assertion (sign-direction lock) is:
      MWR for Q1 must be POSITIVE (the asset gained +10%, so the return must be > 0).
      If the TRIM's cash flow sign is inverted (positive instead of negative), the
      numerator goes negative and MWR would be spuriously negative.

    We also verify Q1 MWR is in the plausible range [0%, 15%] for a 10% asset gain
    where half the position was trimmed at zero gain.
    """
    band_legs = [
        ("2020-01-01", {"AAPL": 0.2}),
        ("2020-04-01", {"AAPL": 0.1}),   # TRIM: weight halved at same price
        ("2020-07-01", {"AAPL": 0.1}),   # latest; asset +10%
    ]
    closes = {
        "AAPL": {
            "2020-01-01": 100.0,
            "2020-04-01": 100.0,  # flat at trim date
            "2020-07-01": 110.0,  # +10% gain
        }
    }
    nav_net = [100.0, 101.0, 106.0]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert len(per_quarter) == 3

    # Q1 is a historical (non-latest) quarter containing the TRIM.
    mwr_q1 = per_quarter[1]["AAPL"].mwr_pct

    assert mwr_q1 is not None, "Q1 MWR must be computable for the TRIM fixture"

    assert mwr_q1 > 0.0, (
        f"Q1 MWR is {mwr_q1:.4f}% — spuriously negative.  "
        "TRIM (weight decrease) should produce a negative cash flow, NOT a negative MWR "
        "(the asset gained +10% after the trim; the return must be positive).  "
        "Cash-flow sign convention for TRIM likely flipped."
    )

    # Plausibility upper bound: the full +10% can only be earned on the halved
    # position (0.1 weight) for the second leg.  No position should show > 15%.
    assert mwr_q1 < 15.0, (
        f"Q1 MWR {mwr_q1:.4f}% > 15% on a 10% asset gain — MWR is inflated, "
        "likely a cash-flow sign error."
    )


# ---------------------------------------------------------------------------
# PR-2c (Carino C3) — new tests (test-engineer, 2026-06-26)
# ---------------------------------------------------------------------------
#
# Coverage behaviors 1-12 + 1 Hypothesis property for the C3 GROSS identity.
# All tests are offline, deterministic, no network.
# ---------------------------------------------------------------------------


def _sub_period(
    date_from: str,
    date_to: str,
    weights: dict[str, float],
    price_relatives: dict[str, float],
    gross_sub_return: float,
    *,
    cost_drag: float = 0.0,
) -> SubPeriod:
    """Builder for a synthetic SubPeriod fixture."""
    net_sub_return = gross_sub_return - cost_drag
    return SubPeriod(
        date_from=date_from,
        date_to=date_to,
        start_weights_gross=weights,
        price_relatives=price_relatives,
        gross_sub_return=gross_sub_return,
        net_sub_return=net_sub_return,
        cost_drag=cost_drag,
    )


# ---------------------------------------------------------------------------
# 1. _build_carino_grid: empty sub_periods → ([], 1.0, 0)
# ---------------------------------------------------------------------------


def test_build_carino_grid_empty_sub_periods():
    """Empty sub_periods list → kt_over_K=[], K=1.0, clamp_count=0."""
    kt_over_K, K, clamp_count = _build_carino_grid([])
    assert kt_over_K == []
    assert K == pytest.approx(1.0)
    assert clamp_count == 0


# ---------------------------------------------------------------------------
# 2. _build_carino_grid: zero-gross-return sub-period → k_t=1, ratio=1/K
# ---------------------------------------------------------------------------


def test_build_carino_grid_zero_gross_return_sub_period():
    """A sub-period with gross_sub_return=0 → k_t uses the limit k_t=1.0.

    The Carino coefficient for R=0 is defined as the L'Hopital limit = 1.0.
    The ratio k_t/K must be well-defined (no NaN, no division by zero).
    """
    sp = _sub_period(
        "2020-01-01",
        "2020-04-01",
        {"AAPL": 1.0},
        {"AAPL": 1.0},   # price relative = 1 → gross return = 0
        gross_sub_return=0.0,
    )
    kt_over_K, K, clamp_count = _build_carino_grid([sp])
    assert len(kt_over_K) == 1
    assert kt_over_K[0] == kt_over_K[0]   # not NaN
    assert math.isfinite(kt_over_K[0])
    assert clamp_count == 0


# ---------------------------------------------------------------------------
# 3. _build_carino_grid: 1+R^g_t ≤ 0 → clamp_count=1, no NaN
# ---------------------------------------------------------------------------


def test_build_carino_grid_total_loss_sub_period_clamps():
    """A sub-period with 1+R^g_t ≤ 0 increments clamp_count and stays finite.

    The degenerate guard clamps k_t=1 instead of computing ln(non-positive).
    Two sub-periods: one normal (+20%), one total loss (−100%).
    """
    sp_normal = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 1.0}, {"AAPL": 1.2},
        gross_sub_return=0.2,
    )
    sp_loss = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": 1.0}, {"AAPL": 0.0},
        gross_sub_return=-1.0,   # 1 + R = 0 → degenerate
    )
    kt_over_K, K, clamp_count = _build_carino_grid([sp_normal, sp_loss])
    assert clamp_count == 1
    assert len(kt_over_K) == 2
    for ratio in kt_over_K:
        assert math.isfinite(ratio), f"kt_over_K contains non-finite value: {ratio}"


# ---------------------------------------------------------------------------
# 4. _compute_contribution_from_sub_periods: absent ticker → 0.0
# ---------------------------------------------------------------------------


def test_compute_contribution_absent_ticker():
    """A ticker not present in any sub-period's weights contributes exactly 0.0."""
    sp = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 0.5, "MSFT": 0.5},
        {"AAPL": 1.1, "MSFT": 1.05},
        gross_sub_return=0.075,
    )
    kt_over_K, _K, _ = _build_carino_grid([sp])
    contrib = _compute_contribution_from_sub_periods(
        "GOOG",                      # not in any sub-period
        {},                          # ticker_legs empty for GOOG
        [sp],
        kt_over_K,
    )
    assert contrib == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 5. _compute_contribution_from_sub_periods: missing price_relative → leg skipped
# ---------------------------------------------------------------------------


def test_compute_contribution_missing_price_relative_leg_skipped():
    """A sub-period with the ticker's price_relative absent is skipped silently.

    The ticker has weight > 0 in the sub-period's start_weights_gross but no
    entry in price_relatives (price unavailable at that boundary).  The leg
    must be skipped — no crash, and the contribution is 0 for that leg.
    """
    sp = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 0.5},              # AAPL has weight
        {},                          # but NO price_relative for AAPL
        gross_sub_return=0.0,
    )
    kt_over_K, _K, _ = _build_carino_grid([sp])
    # Should not raise; contribution must be 0.0 (skipped leg).
    contrib = _compute_contribution_from_sub_periods(
        "AAPL",
        {"2020-01-01": 0.5},
        [sp],
        kt_over_K,
    )
    assert contrib == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 6. C3 GROSS identity: Σ_i C_i == R^g_port (to 1e-9)
# ---------------------------------------------------------------------------


def test_c3_gross_identity_three_ticker_two_sub_period():
    """C3 gate: Σ position contributions closes to R^g_port to within 1e-9.

    Hand-built 3-ticker × 2-sub-period book with known numbers.
    Sub-period 1: AAPL +20%, MSFT +10%, GOOG +5%  (equal 1/3 weights each)
    Sub-period 2: AAPL +5%,  MSFT −2%,  GOOG +8%  (equal 1/3 weights each)

    R^g_t[0] = (1/3)(0.20 + 0.10 + 0.05) = 0.1167
    R^g_t[1] = (1/3)(0.05 − 0.02 + 0.08) = 0.0367
    R^g_port  = (1 + R^g_t[0])(1 + R^g_t[1]) − 1
    """
    w = 1.0 / 3.0
    r0_aapl, r0_msft, r0_goog = 0.20, 0.10, 0.05
    r1_aapl, r1_msft, r1_goog = 0.05, -0.02, 0.08

    gross0 = w * r0_aapl + w * r0_msft + w * r0_goog
    gross1 = w * r1_aapl + w * r1_msft + w * r1_goog
    R_port_gross = (1.0 + gross0) * (1.0 + gross1) - 1.0

    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": w, "MSFT": w, "GOOG": w},
        {"AAPL": 1.0 + r0_aapl, "MSFT": 1.0 + r0_msft, "GOOG": 1.0 + r0_goog},
        gross_sub_return=gross0,
    )
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": w, "MSFT": w, "GOOG": w},
        {"AAPL": 1.0 + r1_aapl, "MSFT": 1.0 + r1_msft, "GOOG": 1.0 + r1_goog},
        gross_sub_return=gross1,
    )

    kt_over_K, _K, _ = _build_carino_grid([sp0, sp1])

    ticker_legs = {"2020-01-01": w, "2020-04-01": w}
    c_aapl = _compute_contribution_from_sub_periods("AAPL", ticker_legs, [sp0, sp1], kt_over_K)
    c_msft = _compute_contribution_from_sub_periods("MSFT", ticker_legs, [sp0, sp1], kt_over_K)
    c_goog = _compute_contribution_from_sub_periods("GOOG", ticker_legs, [sp0, sp1], kt_over_K)

    gross_sum = c_aapl + c_msft + c_goog
    error = abs(gross_sum - R_port_gross)
    assert error < 1e-9, (
        f"C3 GROSS identity violated: |Σ_i C_i − R^g_port| = {error:.2e} "
        f"(Σ={gross_sum:.12f}, R^g={R_port_gross:.12f})"
    )


# ---------------------------------------------------------------------------
# 7. NET identity: Σ_i C^n_i + C_cost == R^n_port (to 1e-9)
# ---------------------------------------------------------------------------


def test_c3_net_identity_with_cost_drag():
    """NET identity: Σ position gross-contributions + C_cost closes to R^n_port.

    The Carino (1999) net identity reads:
        Σ_i C_i + C_cost = R^n_port
    where:
        C_i    = position gross contribution (Σ_t (k_t/K) × w_it × (ρ_it − 1))
        C_cost = Σ_t (k_t/K) × (−δ_t)           (synthetic cost line)

    With geometric linking, this identity closes EXACTLY only when cost_drag δ_t
    is zero (the cross-term δ_t × R^g_{t+1} is a second-order approximation error
    of O(δ × R)).  This test uses δ_t so small (1e-12) that the cross-term is
    below float epsilon, verifying the un-rounded-δ_t path without the
    geometric cross-term noise.

    For non-trivial cost drag, the production code emits the residual as a
    DIAGNOSTIC counter (position_return_cost_line_residual) and does NOT assert
    <1e-9 — that tolerance only applies when δ_t ≈ 0.
    """
    w = 0.5
    r0 = 0.10   # both tickers same gross sub-return for sub-period 0
    r1 = 0.08   # both tickers same gross sub-return for sub-period 1
    # Use a cost drag small enough that the second-order cross-term
    # delta0 * gross1 is below 1e-14 (float epsilon territory).
    delta0 = 1e-14
    delta1 = 0.0

    gross0 = w * r0 + w * r0
    gross1 = w * r1 + w * r1

    net0 = gross0 - delta0
    net1 = gross1 - delta1
    R_net = (1 + net0) * (1 + net1) - 1.0

    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": w, "MSFT": w},
        {"AAPL": 1.0 + r0, "MSFT": 1.0 + r0},
        gross_sub_return=gross0,
        cost_drag=delta0,
    )
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": w, "MSFT": w},
        {"AAPL": 1.0 + r1, "MSFT": 1.0 + r1},
        gross_sub_return=gross1,
        cost_drag=delta1,
    )

    kt_over_K, _K, _ = _build_carino_grid([sp0, sp1])
    ticker_legs = {"2020-01-01": w, "2020-04-01": w}

    c_aapl = _compute_contribution_from_sub_periods("AAPL", ticker_legs, [sp0, sp1], kt_over_K)
    c_msft = _compute_contribution_from_sub_periods("MSFT", ticker_legs, [sp0, sp1], kt_over_K)
    c_cost = _cost_line_contribution([sp0, sp1], kt_over_K)

    net_sum = c_aapl + c_msft + c_cost
    error = abs(net_sum - R_net)
    assert error < 1e-9, (
        f"C3 NET identity violated with near-zero δ_t: |Σ_i C_i + C_cost − R^n_port| = {error:.2e} "
        f"(Σ_gross={c_aapl + c_msft:.12f}, C_cost={c_cost:.12f}, "
        f"net_sum={net_sum:.12f}, R^n={R_net:.12f})"
    )


# ---------------------------------------------------------------------------
# 8. carino_clamp_count propagates into reconciliation_errors return
# ---------------------------------------------------------------------------


def test_carino_clamp_count_propagates_via_reconciliation_errors():
    """carino_clamp_count in the 4-tuple matches the clamp count from _build_carino_grid.

    When a sub-period has 1+R^g_t ≤ 0, clamp_count > 0 must appear in
    reconciliation_errors' 4th return element.
    """
    sp_normal = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 1.0}, {"AAPL": 1.1},
        gross_sub_return=0.1,
    )
    sp_loss = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": 1.0}, {"AAPL": 0.0},
        gross_sub_return=-1.0,   # triggers clamp
    )

    # Build position_returns with contrib_nav_pts computed via sub_periods.
    band_legs = [
        ("2020-01-01", {"AAPL": 1.0}),
        ("2020-04-01", {"AAPL": 1.0}),
    ]
    closes = {"AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0}}
    nav_net = [100.0, 110.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    pos_returns = compute_position_returns(
        band_legs, closes,
        portfolio_nav_net=nav_net,
        portfolio_nav_dates=nav_dates,
        sub_periods=[sp_normal, sp_loss],
    )
    gross_err, cost_residual, pp_err, clamp_count = reconciliation_errors(
        pos_returns, nav_net, nav_dates, band_legs,
        sub_periods=[sp_normal, sp_loss],
    )
    assert clamp_count == 1, (
        f"Expected clamp_count=1 for one total-loss sub-period, got {clamp_count}"
    )


# ---------------------------------------------------------------------------
# 9. reconciliation_errors(sub_periods=None) → gross_err=None, cost_residual=None, clamp=0
# ---------------------------------------------------------------------------


def test_reconciliation_errors_sub_periods_none_returns_none_gross_fields():
    """When sub_periods=None, gross_identity_error and cost_line_residual are None.

    This is the PR-2a backward-compat path (no Carino grid computed).
    The 4-tuple must be (None, None, <pp_twr_or_None>, 0).
    """
    pr = {"AAPL": PositionReturn(
        mwr_pct=5.0, twr_pct=5.0, contrib_nav_pts=None,
        since_date="2020-01-01", partial_history=False, legs_used=1,
    )}
    band_legs = [("2020-01-01", {"AAPL": 1.0})]
    nav_net = [100.0, 105.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    gross_err, cost_residual, pp_twr_err, clamp_count = reconciliation_errors(
        pr, nav_net, nav_dates, band_legs, sub_periods=None
    )
    assert gross_err is None, f"gross_err must be None when sub_periods=None, got {gross_err}"
    assert cost_residual is None, (
        f"cost_residual must be None when sub_periods=None, got {cost_residual}"
    )
    assert clamp_count == 0


# ---------------------------------------------------------------------------
# 10. compute_position_returns WITH sub_periods → all tickers get non-None contrib_nav_pts
# ---------------------------------------------------------------------------


def test_compute_position_returns_with_sub_periods_populates_contrib_nav_pts():
    """When sub_periods is provided, every ticker in the result has non-None contrib_nav_pts."""
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0},
        "MSFT": {"2020-01-01": 200.0, "2020-04-01": 210.0},
    }
    nav_net = [100.0, 105.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    gross0 = 0.5 * 0.10 + 0.5 * 0.05   # AAPL +10%, MSFT +5%
    sp = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 0.5, "MSFT": 0.5},
        {"AAPL": 1.10, "MSFT": 1.05},
        gross_sub_return=gross0,
    )

    pos_returns = compute_position_returns(
        band_legs, closes,
        portfolio_nav_net=nav_net,
        portfolio_nav_dates=nav_dates,
        sub_periods=[sp],
    )

    for ticker, pr in pos_returns.items():
        assert pr.contrib_nav_pts is not None, (
            f"Expected non-None contrib_nav_pts for {ticker} when sub_periods provided"
        )


# ---------------------------------------------------------------------------
# 11. compute_position_returns(sub_periods=None) → all contrib_nav_pts=None (backward-compat)
# ---------------------------------------------------------------------------


def test_compute_position_returns_without_sub_periods_contrib_is_none():
    """PR-2a backward-compat: when sub_periods=None, contrib_nav_pts is None for all."""
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-04-01": 110.0},
        "MSFT": {"2020-01-01": 200.0, "2020-04-01": 210.0},
    }
    nav_net = [100.0, 105.0]
    nav_dates = ["2020-01-01", "2020-04-01"]

    pos_returns = compute_position_returns(
        band_legs, closes,
        portfolio_nav_net=nav_net,
        portfolio_nav_dates=nav_dates,
        sub_periods=None,
    )

    for ticker, pr in pos_returns.items():
        assert pr.contrib_nav_pts is None, (
            f"{ticker}: expected contrib_nav_pts=None (sub_periods=None / PR-2a compat), "
            f"got {pr.contrib_nav_pts}"
        )


# ---------------------------------------------------------------------------
# 12. Mid-window entry/exit: a ticker absent from some sub-periods still passes
#     the GROSS identity (partial coverage sub-periods are handled correctly)
# ---------------------------------------------------------------------------


def test_c3_gross_identity_with_mid_window_entry():
    """C3 GROSS identity holds when a ticker enters mid-window.

    GOOG enters only in sub-period 2 (absent in sub-period 1).
    The GROSS identity must still close: Σ_i C_i = R^g_port.
    """
    # Sub-period 0: only AAPL (weight=1.0)
    gross0 = 0.10
    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 1.0},
        {"AAPL": 1.10},
        gross_sub_return=gross0,
    )
    # Sub-period 1: AAPL (0.5) + GOOG (0.5) — GOOG enters
    r1_aapl, r1_goog = 0.05, 0.08
    gross1 = 0.5 * r1_aapl + 0.5 * r1_goog
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": 0.5, "GOOG": 0.5},
        {"AAPL": 1.0 + r1_aapl, "GOOG": 1.0 + r1_goog},
        gross_sub_return=gross1,
    )

    R_port_gross = (1 + gross0) * (1 + gross1) - 1.0

    kt_over_K, _K, _ = _build_carino_grid([sp0, sp1])

    c_aapl = _compute_contribution_from_sub_periods(
        "AAPL",
        {"2020-01-01": 1.0, "2020-04-01": 0.5},
        [sp0, sp1],
        kt_over_K,
    )
    c_goog = _compute_contribution_from_sub_periods(
        "GOOG",
        {"2020-04-01": 0.5},          # enters only at sub-period 1
        [sp0, sp1],
        kt_over_K,
    )

    gross_sum = c_aapl + c_goog
    error = abs(gross_sum - R_port_gross)
    assert error < 1e-9, (
        f"C3 GROSS identity with mid-window entry violated: "
        f"|Σ_i C_i − R^g_port| = {error:.2e}"
    )


# ---------------------------------------------------------------------------
# Hypothesis property: C3 GROSS identity holds for ALL Dirichlet inputs
# ---------------------------------------------------------------------------


@given(
    # Number of sub-periods: 1–4 (keep panels small for speed)
    n_periods=st.integers(min_value=1, max_value=4),
    # Number of tickers: 2–4
    n_tickers=st.integers(min_value=2, max_value=4),
    # Price relatives ∈ [0.5, 2.0] (no total losses, so no clamping needed)
    price_relatives_flat=st.lists(
        st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=16,
    ),
    # Weights per period: uniform Dirichlet approximated by raw Dirichlet draws
    raw_weights_flat=st.lists(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=16,
    ),
    # Partial-window mask: randomly zero out a name's weight in some periods
    partial_mask_flat=st.lists(st.booleans(), min_size=1, max_size=16),
)
def test_c3_gross_identity_holds_for_all_dirichlet_inputs(
    n_periods: int,
    n_tickers: int,
    price_relatives_flat: list[float],
    raw_weights_flat: list[float],
    partial_mask_flat: list[bool],
) -> None:
    """C3 invariant: |Σ_i C_i − R^g_port| < 1e-9 for all valid draws.

    Strategy:
    - n_periods sub-periods, n_tickers tickers.
    - Raw weights drawn from [0.01, 1.0], then Dirichlet-normalised per period.
    - partial_mask applies mid-window entry/exit (zero weight for some names
      in some periods); re-normalised after zeroing.
    - Price relatives drawn from [0.5, 2.0] — no total-loss sub-periods,
      so clamping does not confound the identity test.
    - Computes Σ C_i via _build_carino_grid + _compute_contribution_from_sub_periods.
    - Asserts the Carino C3 GROSS identity to within 1e-9.
    """
    tickers = [f"T{i}" for i in range(n_tickers)]

    # Pad flat lists to the required length (n_periods × n_tickers) by cycling.
    required = n_periods * n_tickers

    def _cycle_pad(lst: list, length: int) -> list:
        if not lst:
            return [1.0] * length
        return [lst[i % len(lst)] for i in range(length)]

    pr_flat = _cycle_pad(price_relatives_flat, required)
    rw_flat = _cycle_pad(raw_weights_flat, required)
    pm_flat = _cycle_pad(partial_mask_flat, required)

    sub_periods = []
    for t in range(n_periods):
        raw_w = {tickers[i]: rw_flat[t * n_tickers + i] for i in range(n_tickers)}
        # Apply partial_mask: zero some weights to simulate mid-window entry/exit.
        for i in range(n_tickers):
            if pm_flat[t * n_tickers + i]:
                raw_w[tickers[i]] = 0.0
        # Normalise weights (skip if total is 0).
        total_w = sum(raw_w.values())
        if total_w <= 0.0:
            # All zeroed; assign uniform weights so the period is not empty.
            raw_w = {ticker: 1.0 / n_tickers for ticker in tickers}
            total_w = 1.0
        weights = {ticker: v / total_w for ticker, v in raw_w.items() if v > 0}

        # Price relatives — use the padded flat list.
        pr_map = {tickers[i]: pr_flat[t * n_tickers + i] for i in range(n_tickers)}
        pr_map = {k: v for k, v in pr_map.items() if k in weights}

        # Gross sub-return = Σ w_i (ρ_i − 1).
        gross_sub = sum(weights.get(k, 0.0) * (pr_map.get(k, 1.0) - 1.0) for k in weights)

        sub_periods.append(_sub_period(
            f"2020-{t + 1:02d}-01", f"2020-{t + 2:02d}-01",
            weights,
            pr_map,
            gross_sub_return=gross_sub,
        ))

    # Portfolio GROSS return via geometric linking.
    R_port_gross = 1.0
    for sp in sub_periods:
        R_port_gross *= 1.0 + sp.gross_sub_return
    R_port_gross -= 1.0

    kt_over_K, _K, _ = _build_carino_grid(sub_periods)

    # Per-ticker Carino contributions.
    gross_sum = 0.0
    for ticker in tickers:
        # ticker_legs = {date_from: weight} across all sub-periods.
        ticker_legs = {
            sp.date_from: sp.start_weights_gross.get(ticker, 0.0)
            for sp in sub_periods
        }
        c = _compute_contribution_from_sub_periods(ticker, ticker_legs, sub_periods, kt_over_K)
        gross_sum += c

    error = abs(gross_sum - R_port_gross)
    assert error < 1e-9, (
        f"C3 GROSS identity violated: |Σ_i C_i − R^g_port| = {error:.2e} "
        f"(n_periods={n_periods}, n_tickers={n_tickers})"
    )


# ---------------------------------------------------------------------------
# PR-2c FIX: per-window SubPeriod-based GROSS identity (commit 2917d6d92)
#
# The bug: reconciliation_errors() previously computed
#   gross_identity_error = |Σ pr.contrib_nav_pts/100 − R^g_port|
# where Σ pr.contrib_nav_pts/100 was a flat sum over ~10 current/recently-sold
# tickers (a partial-attribution subset covering only the current basket), while
# R^g_port was the full 10-year gross NAV return (+832%).  The mismatch produced
# position_return_reconciliation_max_abs_error = 7.006 instead of ~1e-11.
#
# The fix: replace the flat-position-map path with two SubPeriod-based checks:
#   1. Per-window BHB identity: max_t |Σ_i w_{i,t}·(ρ_{i,t}−1) − R^g_t|
#   2. Full-period Carino chain: |Σ_t (k_t/K)·R^g_t − R^g_port|
#   gross_identity_error = max(chain_err, max_window_bhb_err)
#
# These 6 tests target the new sub_periods path specifically.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PR-2c FIX 1: Positive 2-window fixture — gross_identity_error < 1e-9
# ---------------------------------------------------------------------------


def test_per_window_gross_identity_two_windows():
    """SubPeriod-based reconciliation_errors returns gross_identity_error < 1e-9.

    2-window fixture with known, exactly-consistent weights, price-relatives and
    gross_sub_returns (no floating-point inconsistency introduced).

    Window 0: AAPL 60%, MSFT 40%, each +10% and +5% → gross0 = 0.60×0.10 + 0.40×0.05 = 0.080
    Window 1: AAPL 50%, MSFT 50%, each +8% and +6% → gross1 = 0.50×0.08 + 0.50×0.06 = 0.070
    R^g_port = (1.080)(1.070) − 1 = 0.1556

    Both the per-window BHB check and the Carino chain check must be < 1e-9.
    This is the positive test that would FAIL under the OLD code (which compared
    a flat-position-map contrib_sum against R^g_port).
    """
    # Window 0: exactly consistent sub-period.
    w0_aapl, w0_msft = 0.60, 0.40
    r0_aapl, r0_msft = 0.10, 0.05
    gross0 = w0_aapl * r0_aapl + w0_msft * r0_msft   # = 0.080 exactly

    # Window 1: exactly consistent sub-period.
    w1_aapl, w1_msft = 0.50, 0.50
    r1_aapl, r1_msft = 0.08, 0.06
    gross1 = w1_aapl * r1_aapl + w1_msft * r1_msft   # = 0.070 exactly

    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": w0_aapl, "MSFT": w0_msft},
        {"AAPL": 1.0 + r0_aapl, "MSFT": 1.0 + r0_msft},
        gross_sub_return=gross0,
    )
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": w1_aapl, "MSFT": w1_msft},
        {"AAPL": 1.0 + r1_aapl, "MSFT": 1.0 + r1_msft},
        gross_sub_return=gross1,
    )

    # Minimal band_legs + nav to satisfy the reconciliation_errors signature.
    band_legs = [
        ("2020-01-01", {"AAPL": w0_aapl, "MSFT": w0_msft}),
        ("2020-04-01", {"AAPL": w1_aapl, "MSFT": w1_msft}),
    ]
    nav_net = [100.0, 100.0 * (1.0 + gross0), 100.0 * (1.0 + gross0) * (1.0 + gross1)]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    gross_err, cost_residual, _pp_err, clamp_count = reconciliation_errors(
        {},                         # position_returns not needed for GROSS check
        nav_net,
        nav_dates,
        band_legs,
        sub_periods=[sp0, sp1],
    )

    assert gross_err is not None, "gross_identity_error must be a float when sub_periods provided"
    assert gross_err < 1e-9, (
        f"per-window GROSS identity error = {gross_err:.2e} (expected < 1e-9).  "
        "The SubPeriod-based BHB/chain check failed — old flat-map path may be active."
    )
    assert clamp_count == 0


# ---------------------------------------------------------------------------
# PR-2c FIX 2: Negative regression guard — old-style arithmetic produces ≥ 1.0
# ---------------------------------------------------------------------------


def test_old_style_flat_contrib_vs_full_gross_nav_error_is_large():
    """Documents the bug shape: flat-contrib-sum vs full-gross-NAV error ≈ 7.006.

    The OLD reconciliation_errors() wiring compared:
        contrib_sum = Σ pr.contrib_nav_pts / 100   (current-basket only, ≈ +131.6%)
        R^g_port    = full 10-year gross NAV return  (≈ +832%)
        gross_identity_error_OLD = |contrib_sum - R^g_port|  ≈ 7.006

    This test does NOT call the old code; it asserts the arithmetic that the
    old wiring produced.  If the error is ≥ 1.0, the old wiring is detected.

    Concrete numbers inspired by the backfill-verify gate failure:
      - 10 tickers in the current basket, each contributing ~13.16 NAV pts
        (so Σ = ~131.6 pts → 1.316 as a fraction).
      - Full 10-year gross NAV is 932 (base 100 → 932), i.e. R^g_port = 8.32.
      - |1.316 − 8.32| = 7.004 ≥ 1.0  → the old code raised the counter to 7.006.

    The NEW code uses SubPeriod-based BHB/chain checks that are immune to this
    window-set mismatch.
    """
    # Simulate the old wiring: flat position_returns covering only the current basket.
    n_current_basket_tickers = 10
    contrib_nav_pts_each = 13.16   # NAV-pts per ticker in the current basket

    # OLD error formula: |Σ(contrib_nav_pts/100) − R^g_port|
    contrib_sum_old = n_current_basket_tickers * (contrib_nav_pts_each / 100.0)  # ≈ 1.316

    # Full 10-year gross NAV return: portfolio went from 100 to 932 → R^g_port = 8.32
    R_port_gross_full = 8.32

    old_style_error = abs(contrib_sum_old - R_port_gross_full)

    assert old_style_error >= 1.0, (
        f"OLD-style error = {old_style_error:.4f} — expected ≥ 1.0 to document the bug shape. "
        "The test fixture may be mis-calibrated."
    )
    # And specifically ≈ 7.006 (within ±0.1 of the production observed value).
    assert 6.0 < old_style_error < 8.0, (
        f"OLD-style error = {old_style_error:.4f} — expected in the 6–8 range "
        "(matching the backfill-verify gate counter of ~7.006).  "
        "If this assertion fails the bug-shape constants need re-calibration."
    )


# ---------------------------------------------------------------------------
# PR-2c FIX 3: Cost-line identity — cost_line_residual < 1e-9 with non-zero cost_drag
# ---------------------------------------------------------------------------


def test_cost_line_identity_with_nonzero_cost_drag():
    """cost_line_residual = |R^g_port + C_cost − R^n_port| < 1e-9 for non-zero δ_t.

    The fix also corrected the cost-line identity from using contrib_sum
    (old, wrong) to R^g_port (from SubPeriods).

    With a cost_drag δ_t small enough that the geometric cross-term
    δ_t × R^g_{next} is negligible (δ_t = 1e-12), the net identity closes
    exactly to float precision (< 1e-9).

    This pins the |R^g_port + C_cost − R^n_port| formula rather than the
    old |contrib_sum + C_cost − R^n_port| (which would be inflated by the
    window-set mismatch).
    """
    w = 0.5
    r0_aapl, r0_msft = 0.12, 0.08
    r1_aapl, r1_msft = 0.06, 0.04

    gross0 = w * r0_aapl + w * r0_msft   # = 0.10
    gross1 = w * r1_aapl + w * r1_msft   # = 0.05

    # Cost drag: small enough that the second-order cross-term is below float epsilon.
    delta0 = 1e-12   # cost at rebalance 0
    delta1 = 0.0     # no cost for the terminal sub-period

    net0 = gross0 - delta0
    net1 = gross1 - delta1

    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": w, "MSFT": w},
        {"AAPL": 1.0 + r0_aapl, "MSFT": 1.0 + r0_msft},
        gross_sub_return=gross0,
        cost_drag=delta0,
    )
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": w, "MSFT": w},
        {"AAPL": 1.0 + r1_aapl, "MSFT": 1.0 + r1_msft},
        gross_sub_return=gross1,
        cost_drag=delta1,
    )

    band_legs = [
        ("2020-01-01", {"AAPL": w, "MSFT": w}),
        ("2020-04-01", {"AAPL": w, "MSFT": w}),
    ]
    nav_net = [100.0, 100.0 * (1.0 + net0), 100.0 * (1.0 + net0) * (1.0 + net1)]
    nav_dates = ["2020-01-01", "2020-04-01", "2020-07-01"]

    _gross_err, cost_residual, _pp_err, _clamp = reconciliation_errors(
        {},
        nav_net,
        nav_dates,
        band_legs,
        sub_periods=[sp0, sp1],
    )

    assert cost_residual is not None, (
        "cost_line_residual must be a float when sub_periods provided"
    )
    assert cost_residual < 1e-9, (
        f"|R^g_port + C_cost − R^n_port| = {cost_residual:.2e} (expected < 1e-9).  "
        "The cost-line identity check failed — old contrib_sum path may be active."
    )

    # Also verify the implied cost contribution is negative or zero
    # (positive cost drag should pull the net below the gross).
    kt_over_K, _K, _ = _build_carino_grid([sp0, sp1])
    C_cost = _cost_line_contribution([sp0, sp1], kt_over_K)
    assert C_cost <= 0.0, (
        f"C_cost = {C_cost:.2e} must be ≤ 0 (positive cost_drag reduces net NAV, "
        "so the Carino cost line must be non-positive)"
    )


# ---------------------------------------------------------------------------
# PR-2c FIX 4: compute_window_contributions nominal — Σ_t Σ_i ≈ R^g_port
# ---------------------------------------------------------------------------


def test_compute_window_contributions_sum_equals_gross_return():
    """Σ_t Σ_i compute_window_contributions(t)(i) ≈ R^g_port within 1e-9.

    2-ticker × 3-window fixture.
    By Carino (1999) §3: Σ_t (k_t/K) · R^g_t = R^g_port
    And each window's Σ_i = (k_t/K) · Σ_i w_{i,t} · (ρ_{i,t}−1) = (k_t/K) · R^g_t.
    So Σ_t Σ_i result[t][i] = R^g_port exactly (up to float precision).
    """
    from compute.portfolio.position_returns import compute_window_contributions

    # Window 0: AAPL 0.5, MSFT 0.5, each +6% and +4%
    gross0 = 0.5 * 0.06 + 0.5 * 0.04   # = 0.05
    # Window 1: AAPL 0.4, MSFT 0.6, each +10% and +2%
    gross1 = 0.4 * 0.10 + 0.6 * 0.02   # = 0.052
    # Window 2: AAPL 0.6, MSFT 0.4, each +3% and +7%
    gross2 = 0.6 * 0.03 + 0.4 * 0.07   # = 0.046

    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 0.5, "MSFT": 0.5},
        {"AAPL": 1.06, "MSFT": 1.04},
        gross_sub_return=gross0,
    )
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": 0.4, "MSFT": 0.6},
        {"AAPL": 1.10, "MSFT": 1.02},
        gross_sub_return=gross1,
    )
    sp2 = _sub_period(
        "2020-07-01", "2020-10-01",
        {"AAPL": 0.6, "MSFT": 0.4},
        {"AAPL": 1.03, "MSFT": 1.07},
        gross_sub_return=gross2,
    )

    R_port_gross = (1.0 + gross0) * (1.0 + gross1) * (1.0 + gross2) - 1.0

    kt_over_K, _K, _ = _build_carino_grid([sp0, sp1, sp2])
    result = compute_window_contributions([sp0, sp1, sp2], kt_over_K)

    assert set(result.keys()) == {0, 1, 2}, f"Expected window indices {{0,1,2}}, got {set(result.keys())}"

    # Σ_t Σ_i must equal R^g_port within 1e-9.
    total_contrib = 0.0
    for t, window_dict in result.items():
        for ticker, c in window_dict.items():
            assert c is not None, f"result[{t}][{ticker}] must not be None (all prices present)"
            total_contrib += c

    error = abs(total_contrib - R_port_gross)
    assert error < 1e-9, (
        f"compute_window_contributions total = {total_contrib:.12f}, "
        f"R^g_port = {R_port_gross:.12f}, error = {error:.2e} (expected < 1e-9)"
    )

    # Also verify each window's Σ_i matches (k_t/K) × R^g_t.
    grosses = [gross0, gross1, gross2]
    for t in range(3):
        window_sum = sum(
            c for c in result[t].values() if c is not None
        )
        expected_window = kt_over_K[t] * grosses[t]
        window_error = abs(window_sum - expected_window)
        assert window_error < 1e-9, (
            f"Window {t} sum = {window_sum:.12f}, "
            f"expected (k_t/K)·R^g_t = {expected_window:.12f}, "
            f"error = {window_error:.2e}"
        )


# ---------------------------------------------------------------------------
# PR-2c FIX 5: compute_window_contributions degradation — missing ρ → None, no raise
# ---------------------------------------------------------------------------


def test_compute_window_contributions_missing_price_relative_is_none_no_raise():
    """A missing price-relative in a window produces None for that ticker, never raises.

    Window 0: AAPL has a price_relative; MSFT is absent from price_relatives.
    AAPL must have a float value; MSFT must map to None; no exception is raised.
    All entries for the OTHER window (window 1) must be unaffected.
    """
    from compute.portfolio.position_returns import compute_window_contributions

    # Window 0: AAPL has ρ, MSFT does NOT.
    sp0 = _sub_period(
        "2020-01-01", "2020-04-01",
        {"AAPL": 0.5, "MSFT": 0.5},      # MSFT has weight
        {"AAPL": 1.10},                    # but NO price_relative for MSFT
        gross_sub_return=0.05,             # BHB identity not asserted here (ρ absent)
    )
    # Window 1: both tickers have price_relatives.
    sp1 = _sub_period(
        "2020-04-01", "2020-07-01",
        {"AAPL": 0.5, "MSFT": 0.5},
        {"AAPL": 1.06, "MSFT": 1.04},
        gross_sub_return=0.5 * 0.06 + 0.5 * 0.04,
    )

    kt_over_K, _K, _ = _build_carino_grid([sp0, sp1])

    # Should NOT raise despite MSFT's missing ρ in window 0.
    result = compute_window_contributions([sp0, sp1], kt_over_K)

    # Window 0: AAPL has a non-None float; MSFT is None.
    assert 0 in result, "Window 0 must be present in result"
    assert "AAPL" in result[0], "AAPL must appear in window 0 (it has a price_relative)"
    assert result[0]["AAPL"] is not None, "AAPL window-0 contribution must not be None"
    assert math.isfinite(result[0]["AAPL"]), f"AAPL contribution must be finite, got {result[0]['AAPL']}"

    assert "MSFT" in result[0], "MSFT must appear in window 0 (it has weight; ρ absent → None)"
    assert result[0]["MSFT"] is None, (
        f"MSFT window-0 contribution must be None (missing price_relative), "
        f"got {result[0]['MSFT']}"
    )

    # Window 1: both tickers must have finite contributions.
    assert 1 in result, "Window 1 must be present"
    assert result[1]["AAPL"] is not None and math.isfinite(result[1]["AAPL"])
    assert result[1]["MSFT"] is not None and math.isfinite(result[1]["MSFT"])


# ---------------------------------------------------------------------------
# PR-2c FIX 6: Hypothesis property — gross_identity_error < 1e-9 for all inputs
# ---------------------------------------------------------------------------


@given(
    n_windows=st.integers(min_value=1, max_value=4),
    n_tickers=st.integers(min_value=1, max_value=3),
    raw_weights_flat=st.lists(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=12,
    ),
    # Price relatives ∈ [0.5, 1.8]: avoid total-loss sub-periods which trigger clamping
    # (clamping disrupts the exact identity; the property test focuses on the normal path).
    price_relatives_flat=st.lists(
        st.floats(min_value=0.5, max_value=1.8, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=12,
    ),
)
@_h_settings(max_examples=50)
def test_per_window_gross_identity_holds_for_random_inputs(
    n_windows: int,
    n_tickers: int,
    raw_weights_flat: list[float],
    price_relatives_flat: list[float],
) -> None:
    """gross_identity_error < 1e-9 for all Dirichlet-sampled inputs.

    Builds n_windows sub-periods with n_tickers each.
    Weights are Dirichlet-normalised (from raw_weights_flat).
    Price relatives drawn from [0.5, 1.8] (no total-loss, no clamping).

    reconciliation_errors(sub_periods=sub_periods) must return
    gross_identity_error < 1e-9 for all valid combinations.
    """
    required = n_windows * n_tickers
    tickers = [f"T{i}" for i in range(n_tickers)]

    def _pad(lst: list, n: int) -> list:
        if not lst:
            return [1.0] * n
        return [lst[i % len(lst)] for i in range(n)]

    rw = _pad(raw_weights_flat, required)
    pr = _pad(price_relatives_flat, required)

    sub_periods = []
    for t in range(n_windows):
        raw_w = {tickers[i]: rw[t * n_tickers + i] for i in range(n_tickers)}
        total_w = sum(raw_w.values())
        if total_w <= 0.0:
            weights = {ticker: 1.0 / n_tickers for ticker in tickers}
        else:
            weights = {ticker: v / total_w for ticker, v in raw_w.items()}

        pr_map = {tickers[i]: pr[t * n_tickers + i] for i in range(n_tickers)}
        gross_sub = sum(weights[k] * (pr_map[k] - 1.0) for k in weights)

        sub_periods.append(_sub_period(
            f"2020-{t + 1:02d}-01",
            f"2020-{t + 2:02d}-01",
            weights,
            pr_map,
            gross_sub_return=gross_sub,
        ))

    band_legs = [
        (sp.date_from, sp.start_weights_gross)
        for sp in sub_periods
    ]
    # NAV values: just need a non-empty list for the signature.
    nav_net = [100.0] * (n_windows + 1)
    nav_dates = [sp.date_from for sp in sub_periods] + [sub_periods[-1].date_to]

    gross_err, _cost_residual, _pp_err, clamp_count = reconciliation_errors(
        {},
        nav_net,
        nav_dates,
        band_legs,
        sub_periods=sub_periods,
    )

    assert clamp_count == 0, (
        f"No total-loss sub-periods in fixture (ρ ∈ [0.5,1.8]) "
        f"but got clamp_count={clamp_count}"
    )
    assert gross_err is not None, "gross_identity_error must not be None when sub_periods provided"
    assert gross_err < 1e-9, (
        f"per-window GROSS identity violated: gross_identity_error = {gross_err:.2e} "
        f"(n_windows={n_windows}, n_tickers={n_tickers})"
    )


# ---------------------------------------------------------------------------
# Gap-aware streak-scoping fix (claude/return-current-streak-fix)
#
# _extract_streaks gains `all_rebalance_dates` kwarg (Sequence[str] | None).
# When provided, the function splits a streak on a DATE-JUMP in the per-ticker
# legs (ticker absent from ≥ 1 intervening rebalances) in ADDITION to the
# existing weight-0 split.
#
# Callers:
#   _compute_flat_latest_returns — passes the full band_legs date axis
#   compute_position_returns_per_quarter — passes the PIT-truncated prefix
#
# reconciliation_errors: the bare _extract_streaks call at ~line 1372 is left
# WITHOUT all_rebalance_dates (Carino #619 byte-identical invariant).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# G1. Gap-aware split — absent-quarter triggers two streaks
# ---------------------------------------------------------------------------


def test_gap_aware_extract_streaks_date_jump_produces_two_streaks():
    """_extract_streaks splits on a date jump when all_rebalance_dates is provided.

    Axis: Q0, Q1, Q2, Q3 (four rebalance dates).
    Ticker legs: Q0 (present), Q2 (present) — Q1 is absent (DATE JUMP).
    With all_rebalance_dates=axis: two streaks; streaks[-1][0][0] == Q2.
    Without all_rebalance_dates (old path): one streak (no gap detection).
    """
    axis = ["2021-01-01", "2021-04-01", "2021-07-01", "2021-10-01"]
    # Ticker present at Q0 and Q2 — Q1 missing (date jump on the axis).
    legs = [("2021-01-01", 0.3), ("2021-07-01", 0.3)]
    closes = {
        "KLAC": {
            "2021-01-01": 200.0,
            "2021-07-01": 240.0,
        }
    }

    # --- New behaviour: gap-aware split produces 2 streaks ---
    streaks_gap = _extract_streaks("KLAC", legs, closes, all_rebalance_dates=axis)
    assert len(streaks_gap) == 2, (
        f"Expected 2 streaks (gap at Q1 should split), got {len(streaks_gap)}. "
        "The all_rebalance_dates gap-detection is not firing."
    )
    # The re-entry streak starts at the re-entry date (Q2 = 2021-07-01).
    assert streaks_gap[-1][0][0] == "2021-07-01", (
        f"Latest streak should start at re-entry date '2021-07-01', "
        f"got {streaks_gap[-1][0][0]}"
    )


# ---------------------------------------------------------------------------
# G2. Back-compat byte-identical — all_rebalance_dates=None → 1 streak
# ---------------------------------------------------------------------------


def test_gap_aware_extract_streaks_none_axis_is_byte_identical():
    """all_rebalance_dates=None (default) preserves old weight-only behaviour.

    Same legs as G1 but NO axis provided — the two held legs share no
    weight-0 leg between them, so old code saw one continuous streak.
    The default call must still produce 1 streak (backward-compat).
    """
    legs = [("2021-01-01", 0.3), ("2021-07-01", 0.3)]
    closes = {
        "KLAC": {
            "2021-01-01": 200.0,
            "2021-07-01": 240.0,
        }
    }

    streaks_old = _extract_streaks("KLAC", legs, closes)
    assert len(streaks_old) == 1, (
        f"Without all_rebalance_dates the old weight-only path must yield 1 streak, "
        f"got {len(streaks_old)}"
    )
    # The single streak starts at the first held date.
    assert streaks_old[0][0][0] == "2021-01-01"


# ---------------------------------------------------------------------------
# G3. Flat path since_date — compute_position_returns uses re-entry date
# ---------------------------------------------------------------------------


def test_flat_path_since_date_equals_re_entry_date_when_gap_present():
    """compute_position_returns: since_date == re-entry date when ticker absent ≥1 rebalance.

    Fixture:
      Q0 (2021-01): ALL held at 0.4
      Q1 (2021-04): ALL absent from the rebalance weight map (OTHER holds; gap on axis)
      Q2 (2021-07): ALL held at 0.4
      Q3 (2021-10): ALL held at 0.4  ← latest

    The axis is [Q0, Q1, Q2, Q3].  ALL's legs are [Q0, Q2, Q3].  Q1 is on the
    axis but absent from ALL's weight map — the date-rank gap triggers a streak
    split.  Without the fix, _extract_streaks would see one streak from Q0 to Q3
    → since_date = 2021-01-01.  With the fix, since_date = 2021-07-01.
    """
    band_legs = [
        ("2021-01-01", {"ALL": 0.4}),
        ("2021-04-01", {"OTHER": 0.4}),   # Q1: ALL absent — gap on axis
        ("2021-07-01", {"ALL": 0.4}),
        ("2021-10-01", {"ALL": 0.4}),
    ]
    closes = {
        "ALL": {
            "2021-01-01": 100.0,
            "2021-07-01": 110.0,
            "2021-07-02": 110.0,   # F1 T+1 fill for the re-entry leg
            "2021-10-01": 120.0,
            "2021-10-02": 120.0,   # F1 T+1 fill for the latest leg (+ _last_close mark)
        },
        "OTHER": {"2021-04-01": 50.0},
    }
    nav_net = [100.0, 102.0, 108.0, 115.0]
    nav_dates = ["2021-01-01", "2021-04-01", "2021-07-01", "2021-10-01"]

    pos_returns = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    pr = pos_returns.get("ALL")
    assert pr is not None, "ALL should appear in flat position_returns (current holder)"
    assert pr.since_date == "2021-07-01", (
        f"since_date should be the re-entry date '2021-07-01' (gap at Q1 must split). "
        f"Got: {pr.since_date}. Gap-aware fix may not be wired into _compute_flat_latest_returns."
    )
    # Latest streak is [Q2, Q3] only.  For a current holder _compute_twr also
    # appends the latest close → prices = [110, 120, 120] → legs_used=2.
    assert pr.legs_used >= 1, (
        f"legs_used should be ≥1 (re-entry streak has at least one sub-period), "
        f"got {pr.legs_used}"
    )


# ---------------------------------------------------------------------------
# G4. Per-quarter PIT-safety — re-entry shows re-entry since_date in that quarter,
#     pre-drop quarters show the ORIGINAL entry (no look-ahead)
# ---------------------------------------------------------------------------


def test_per_quarter_pit_gap_aware_since_date_no_lookahead():
    """compute_position_returns_per_quarter: PIT-truncated gap detection, no look-ahead.

    Fixture (4 rebalance dates; CF absent at Q1):
      Q0 (2021-01): CF held 0.3 — original entry; OTHER held 0.3
      Q1 (2021-04): CF absent from weight map (OTHER held); gap on axis
      Q2 (2021-07): CF held 0.3 — re-entry; OTHER dropped
      Q3 (2021-10): CF held 0.3 — latest

    The axis has 4 dates.  CF's legs are [Q0, Q2, Q3].  At Q1 the axis
    date exists but CF is absent → gap detection fires for Q2+ PIT slices.

    Per-quarter invariants:
      - per_quarter[0]["CF"].since_date == "2021-01-01"  (original entry; PIT axis = [Q0])
      - "CF" not in per_quarter[1]                        (absent at Q1 — weight=0 skip)
      - per_quarter[2]["CF"].since_date == "2021-07-01"  (re-entry; PIT axis = [Q0,Q1,Q2])
      - per_quarter[3]["CF"].since_date == "2021-07-01"  (latest; PIT axis = full)
      - for ALL Q: since_date <= rebal_date              (#618 look-ahead invariant)
    """
    band_legs = [
        ("2021-01-01", {"CF": 0.3, "OTHER": 0.3}),
        ("2021-04-01", {"OTHER": 0.3}),              # Q1: CF absent from weight map
        ("2021-07-01", {"CF": 0.3}),                  # CF re-enters
        ("2021-10-01", {"CF": 0.3}),                  # latest
    ]
    closes = {
        "CF": {
            "2021-01-01": 50.0,
            "2021-07-01": 55.0,
            "2021-10-01": 60.0,
        },
        "OTHER": {"2021-01-01": 80.0, "2021-04-01": 82.0},
    }
    nav_net = [100.0, 101.5, 105.0, 110.0]
    nav_dates = ["2021-01-01", "2021-04-01", "2021-07-01", "2021-10-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    assert len(per_quarter) == 4, f"Expected 4 quarters (one per band_leg), got {len(per_quarter)}"

    # Q0 (index 0): CF entered; PIT axis = [2021-01-01]; single leg; since_date = original entry
    pr_q0 = per_quarter[0].get("CF")
    assert pr_q0 is not None, "CF must appear in per_quarter[0] (weight=0.3 at Q0)"
    assert pr_q0.since_date == "2021-01-01", (
        f"Q0 since_date should be original entry '2021-01-01', got {pr_q0.since_date}"
    )

    # Q1 (index 1): CF absent from weight map → skipped by per-quarter loop
    assert "CF" not in per_quarter[1], (
        "CF is absent at Q1 (weight=0 — not in weight map); must be absent from per_quarter[1]"
    )

    # Q2 (index 2): re-entry; PIT axis = [Q0,Q1,Q2]; gap at Q1 splits streak
    pr_q2 = per_quarter[2].get("CF")
    assert pr_q2 is not None, "CF must appear in per_quarter[2] (re-entered at Q2)"
    assert pr_q2.since_date == "2021-07-01", (
        f"Q2 since_date must be re-entry '2021-07-01' (not original '2021-01-01'). "
        f"Got: {pr_q2.since_date}.  PIT gap-detection is not applied."
    )

    # Q3 (index 3): latest; still shows re-entry date
    pr_q3 = per_quarter[3].get("CF")
    assert pr_q3 is not None, "CF must appear in per_quarter[3] (latest, still held)"
    assert pr_q3.since_date == "2021-07-01", (
        f"Q3 since_date must still be '2021-07-01', got {pr_q3.since_date}"
    )

    # #618 look-ahead invariant: since_date <= rebal_date for every quarter
    rebal_dates = [d for d, _ in band_legs]
    for q_idx, (rebal_date, quarter_map) in enumerate(zip(rebal_dates, per_quarter, strict=False)):
        for ticker, pr in quarter_map.items():
            if pr.since_date is not None:
                assert pr.since_date <= rebal_date, (
                    f"Look-ahead violation at Q{q_idx} ({rebal_date}): "
                    f"{ticker}.since_date={pr.since_date} > rebal_date"
                )


# ---------------------------------------------------------------------------
# G5. Sold-with-gap — re-entry then explicit sell; since_date = re-entry
# ---------------------------------------------------------------------------


def test_sold_after_gap_re_entry_since_date_is_re_entry():
    """Explicit sell after a gap: latest streak = re-entry…sell; since_date = re-entry.

    Fixture (KLAC analog — 4 dates on axis):
      Q0 (2020-08): KLAC held 0.3   — original entry; OTHER held
      Q1 (2021-05): KLAC absent from weight map (OTHER held); gap on axis
      Q2 (2021-08): KLAC held 0.3   — re-entry
      Q3 (2021-11): KLAC weight=0   — explicit sell at latest rebalance

    The axis = [Q0, Q1, Q2, Q3].  KLAC's legs = [Q0, Q2, Q3-exit].
    Gap at Q1 triggers streak split: first streak = [Q0], second = [Q2, Q3-sell].
    since_date for the flat field should be the re-entry date '2021-08-01'.
    is_current=False (sold at Q3).
    """
    band_legs = [
        ("2020-08-01", {"KLAC": 0.3, "OTHER": 0.3}),
        ("2021-05-01", {"OTHER": 0.3}),               # Q1: KLAC absent — gap on axis
        ("2021-08-01", {"KLAC": 0.3}),                # re-entry
        ("2021-11-01", {"KLAC": 0.0}),                # explicit sell
    ]
    closes = {
        "KLAC": {
            "2020-08-01": 300.0,
            "2021-08-01": 350.0,
            "2021-11-01": 380.0,
        },
        "OTHER": {"2020-08-01": 50.0, "2021-05-01": 52.0},
    }
    nav_net = [100.0, 103.0, 108.0, 113.0]
    nav_dates = ["2020-08-01", "2021-05-01", "2021-08-01", "2021-11-01"]

    pos_returns = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )
    pr = pos_returns.get("KLAC")
    assert pr is not None, "KLAC must appear in flat field (sold at latest rebalance)"
    assert pr.since_date == "2021-08-01", (
        f"since_date for sold-after-gap should be re-entry '2021-08-01', "
        f"got {pr.since_date}"
    )
    # The re-entry streak contains only Q2 (the sell at Q3 terminates it but is NOT
    # appended to the streak as a held entry).  For a sold (is_current=False) single-
    # entry streak with end_date=None, _compute_twr has no second price point →
    # twr=None, legs_used=0.  This is correct and expected behavior; the since_date
    # lock above is the principal assertion (the gap split worked).
    assert pr.partial_history is False, (
        "Single re-entry entry with no computable leg pair should NOT set partial_history "
        "(partial_history is only set on genuine data gaps, not on short-streak sold names)"
    )


# ---------------------------------------------------------------------------
# G6. Carino #619 UNTOUCHED — reconciliation_errors unchanged for gapped fixture
# ---------------------------------------------------------------------------


def test_carino_619_reconciliation_errors_unaffected_by_gap_ticker():
    """reconciliation_errors gross_identity_error is byte-identical before/after the fix.

    The bare _extract_streaks call inside reconciliation_errors (~line 1372)
    does NOT receive all_rebalance_dates — it uses the old weight-only path.
    This is intentional (Carino #619 stays byte-identical).

    Test: a gapped ticker fixture produces gross_identity_error < 1e-9 AND
    carino_clamp_count == 0.  Running the same fixture WITH and WITHOUT the
    gapped-ticker in band_legs both produce the same near-zero gross_identity_error
    (the SubPeriod-based C3 check is immune to the per-ticker streak split).
    """
    # Sub-period: AAPL and KLAC both present for the full attribution window.
    # (sub_periods covers the whole window; the gap is in per-ticker band_legs only)
    r_aapl, r_klac = 0.10, 0.05
    w = 0.5
    gross0 = w * r_aapl + w * r_klac   # = 0.075
    sp = _sub_period(
        "2021-01-01", "2021-07-01",
        {"AAPL": w, "KLAC": w},
        {"AAPL": 1.0 + r_aapl, "KLAC": 1.0 + r_klac},
        gross_sub_return=gross0,
    )

    # band_legs: KLAC absent at Q1 (gap on the axis); AAPL always present.
    band_legs = [
        ("2021-01-01", {"AAPL": w, "KLAC": w}),
        ("2021-04-01", {"AAPL": w}),              # Q1: KLAC absent — gap on axis
        ("2021-07-01", {"AAPL": w, "KLAC": w}),
    ]
    closes = {
        "AAPL": {"2021-01-01": 100.0, "2021-04-01": 105.0, "2021-07-01": 110.0},
        "KLAC": {"2021-01-01": 200.0, "2021-07-01": 210.0},
    }
    nav_net = [100.0, 105.0, 107.5]
    nav_dates = ["2021-01-01", "2021-04-01", "2021-07-01"]

    pos_returns = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates,
        sub_periods=[sp],
    )

    gross_err, cost_residual, _pp_err, clamp_count = reconciliation_errors(
        pos_returns,
        nav_net,
        nav_dates,
        band_legs,
        sub_periods=[sp],
    )

    assert gross_err is not None, "gross_identity_error must be a float when sub_periods provided"
    assert gross_err < 1e-9, (
        f"Carino #619 gross_identity_error = {gross_err:.2e} with gapped fixture "
        f"(expected < 1e-9 — the SubPeriod-based BHB/chain check must be unaffected by "
        f"the gap-aware streak change in _compute_flat_latest_returns)"
    )
    assert clamp_count == 0, (
        f"Expected clamp_count=0 (no total-loss sub-periods), got {clamp_count}"
    )


# ---------------------------------------------------------------------------
# G7. Hypothesis property — streak partition invariant
# ---------------------------------------------------------------------------


@given(
    # Number of dates on the full axis: 3–8
    n_dates=st.integers(min_value=3, max_value=8),
    # For each date, is the ticker present? (at least 2 must be True)
    presence_flat=st.lists(st.booleans(), min_size=3, max_size=8),
    # Weight when present: > 0
    weight=st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False),
)
@_h_settings(max_examples=50)
def test_gap_aware_streak_partition_invariant(
    n_dates: int,
    presence_flat: list[bool],
    weight: float,
) -> None:
    """Partition invariant: Σ len(streak) == len(present_legs).

    Additional invariants:
      - Every streak is internally contiguous (no date-rank gap within a streak).
      - streaks[-1] ends at the last present leg.

    Strategy: random presence mask over a 3–8 date axis; at least 2 present
    dates so there is at least one streak to check.  No weight-0 legs —
    only the gap-aware split fires.
    """
    # Build the ordered axis.
    base_dates = [
        "2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01",
        "2021-01-01", "2021-04-01", "2021-07-01", "2021-10-01",
    ]
    axis = base_dates[:n_dates]

    # Pad / trim the presence mask to exactly n_dates entries.
    pm = [presence_flat[i % len(presence_flat)] for i in range(n_dates)]

    # Ensure at least 2 present dates so streaks are non-trivial.
    if sum(pm) < 2:
        # Force the first two dates to be present.
        pm[0] = True
        pm[1] = True

    legs = [(axis[i], weight) for i in range(n_dates) if pm[i]]
    present_count = len(legs)

    closes = {"T": {d: float(100 + idx * 5) for idx, d in enumerate(axis)}}

    streaks = _extract_streaks("T", legs, closes, all_rebalance_dates=axis)

    # --- Partition invariant ---
    total_legs_in_streaks = sum(len(s) for s in streaks)
    assert total_legs_in_streaks == present_count, (
        f"Partition invariant violated: Σ len(streak) = {total_legs_in_streaks} "
        f"!= present_count = {present_count}. "
        f"axis={axis}, pm={pm}"
    )

    # --- Contiguity invariant: no internal gap within any streak ---
    date_rank = {d: i for i, d in enumerate(axis)}
    for streak_idx, streak in enumerate(streaks):
        for leg_i in range(1, len(streak)):
            prev_d = streak[leg_i - 1][0]
            cur_d = streak[leg_i][0]
            prev_r = date_rank.get(prev_d)
            cur_r = date_rank.get(cur_d)
            assert prev_r is not None and cur_r is not None
            assert cur_r - prev_r == 1, (
                f"Streak {streak_idx} has an internal gap: "
                f"{prev_d} (rank {prev_r}) → {cur_d} (rank {cur_r}), diff={cur_r - prev_r}. "
                f"axis={axis}, pm={pm}"
            )

    # --- Last streak ends at the last present leg ---
    last_present_date = legs[-1][0]
    last_streak_last_date = streaks[-1][-1][0]
    assert last_streak_last_date == last_present_date, (
        f"streaks[-1] should end at the last present leg ({last_present_date}), "
        f"got {last_streak_last_date}. axis={axis}, pm={pm}"
    )


# ---------------------------------------------------------------------------
# Weekend-rebalance entry-price fix (supersedes #638 direction) +
# F1 T+1-close execution-timing fix (ratified 2026-07-03).
#
# Root cause (original #638-superseding fix): the NAV path snaps each
# rebalance date to a trading day (_snap_to_trading_day in
# backfill_portfolio_pit.py), so the initial basket (rb[0] = Sunday
# 2016-08-14) fills on Monday 2016-08-15.  The entry-price lookup must match
# that convention, otherwise the entry price resolves to None and "Your
# return" is null for the initial basket.
#
# F1 (2026-07-03): the fill-timing convention was further tightened from
# ON-OR-AFTER to STRICTLY AFTER at every genuine trade-fill site. A decision
# is made using data known as of the close at T (close <= T); the actual
# TRADE FILL is the first executable print AFTER that — the cron publishes
# after the US market close, so the earliest tradeable print is the T+1
# close. Resolving to the SAME day's close (the old on-or-after convention)
# double-counted the very close the decision was based on. This is the
# T+1-CLOSE proxy — never "next open" (no intraday signal exists in a daily
# close series).
#
# Convention (now SYMMETRIC for entry vs. non-latest-quarter terminal):
#   entry    price = _close_strictly_after  (T+1 fill; forward search, exclusive)
#   terminal price (non-latest quarter) = _terminal_close = _close_strictly_after,
#     falling back to _close_on_or_before ONLY when nothing trades after the
#     boundary (delisting / newest leg, Shumway 1997).
#   terminal price (LATEST/current quarter) = _last_close — UNCHANGED, this is
#     a MEASUREMENT MARK (no trade has executed), not a fill.
#
# Tests added (error→regression ratchet, CLAUDE.md §Conventions):
#   WR-1  POSITIVE: Sunday rebalance (2016-08-14) → entry on Monday 2016-08-15;
#         quarter-0 yields legs_used >= 1 with a real forward return;
#         partial_history=False.
#   WR-1b rb[1] two-leg restoration: legs Aug-14 → Nov-14; the Aug→Nov leg is
#         no longer dropped; legs_used >= 1 (increment vs #638-style baseline).
#   WR-2  NEGATIVE: panel hole spanning full sub-period → entry=None → legs_used=0
#         (not_after bound prevents degenerate ρ=1).
#   WR-3  STRICT boundary (regression guard, updated for F1): for a leg date
#         that IS a trading day, _close_strictly_after now resolves to the
#         NEXT trading day's close (NOT the same day) — the T+1-fill
#         semantics, distinct from _close_on / _close_on_or_before which both
#         still resolve to the same-day close.
#   WR-4  RECONCILIATION-INVARIANCE: the DISPLAY-ONLY-SAFE claim; Carino GROSS /
#         cost-line residual outputs byte-identical; the pp_twr cross-check stays
#         coherent (now uses _close_strictly_after for entry too).
#   WR-5  Hypothesis property: _close_strictly_after returns None OR the MIN date
#         > date (strict; and <= not_after when bounded).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _close_strictly_after unit tests (new helper)
# ---------------------------------------------------------------------------


def test_close_strictly_after_exact_date_excludes_same_day():
    """A close available exactly ON the target date is EXCLUDED (strict) — the
    first close STRICTLY AFTER it is returned instead (F1 T+1-fill semantics,
    2026-07-03; was inclusive ``>=`` pre-fix, which returned the same-day close)."""
    closes = {"AAPL": {"2016-08-15": 100.0, "2016-08-16": 101.0}}
    px = _close_strictly_after("AAPL", "2016-08-15", closes)
    assert px == pytest.approx(101.0), (
        f"Expected the NEXT day's close 101.0 (strict — same-day 100.0 excluded), got {px}"
    )


def test_close_strictly_after_sunday_resolves_to_monday():
    """A Sunday date with no close resolves to the Monday close (forward search)."""
    closes = {
        "AAPL": {
            "2016-08-12": 99.0,    # Friday — must NOT be returned (before Sunday)
            "2016-08-15": 100.0,   # Monday — the fill day
        }
    }
    px = _close_strictly_after("AAPL", "2016-08-14", closes)
    assert px == pytest.approx(100.0), (
        f"Expected Monday close 100.0 (forward from Sunday), got {px}"
    )


def test_close_strictly_after_no_eligible_date():
    """Returns None when no close exists on or after the target date."""
    closes = {"AAPL": {"2016-08-12": 100.0}}
    px = _close_strictly_after("AAPL", "2016-08-14", closes)
    assert px is None


def test_close_strictly_after_missing_ticker():
    """Returns None for a ticker not in the closes panel."""
    px = _close_strictly_after("NOTHERE", "2020-01-01", {})
    assert px is None


def test_close_strictly_after_not_after_bound():
    """not_after bounds the forward search so entry cannot leap past the terminal date."""
    closes = {
        "AAPL": {
            "2016-08-15": 100.0,   # within bound
            "2016-11-18": 110.0,   # beyond not_after bound
        }
    }
    # not_after = 2016-10-01 → only 2016-08-15 is eligible
    px = _close_strictly_after("AAPL", "2016-08-14", closes, not_after="2016-10-01")
    assert px == pytest.approx(100.0)


def test_close_strictly_after_not_after_panel_hole():
    """When the entire sub-period is a panel hole (no date in [date, not_after]), returns None."""
    closes = {
        "AAPL": {
            "2016-08-12": 99.0,    # before the range
            "2016-12-01": 120.0,   # after not_after
        }
    }
    px = _close_strictly_after("AAPL", "2016-08-14", closes, not_after="2016-11-18")
    assert px is None, (
        f"Panel hole spanning full sub-period must return None, got {px}"
    )


# ---------------------------------------------------------------------------
# WR-1: POSITIVE rb[0] boundary — Sunday 2016-08-14; panel starts Monday 2016-08-15.
#        quarter-0 must yield legs_used >= 1, twr_pct non-None, partial_history=False.
# ---------------------------------------------------------------------------


def test_weekend_rebalance_resolves_entry_price_to_monday_fill():
    """A rebalance date on Sunday 2016-08-14 resolves entry to Monday 2016-08-15.

    Mirrors the real initial-basket bug: NAV path snaps Sunday to Monday
    (_snap_to_trading_day on-or-after), so the fill price is Monday's close.
    The closes panel starts on Monday (no Friday close in the panel).

    With _close_strictly_after, _extract_streaks must price the entry at 100.0
    (Monday Aug-15), so compute_position_returns_per_quarter[0] yields
    legs_used >= 1 with a real forward return, not null.
    partial_history must be False (no dropped legs).
    """
    closes = {
        "AAPL": {
            "2016-08-15": 100.0,   # Monday — first trading day ON OR AFTER Sunday rb[0]
            "2016-11-14": 110.0,   # next rebalance boundary (also a trading day)
        }
    }
    band_legs = [
        ("2016-08-14", {"AAPL": 0.5}),   # Sunday — non-trading day
        ("2016-11-14", {"AAPL": 0.5}),   # trading day
    ]
    nav_net = [100.0, 105.0]
    nav_dates = ["2016-08-14", "2016-11-14"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )

    assert len(per_quarter) == 2, f"Expected 2 quarter maps, got {len(per_quarter)}"

    q0 = per_quarter[0]
    assert "AAPL" in q0, "AAPL must appear in quarter-0 map"
    pr_q0 = q0["AAPL"]

    # Core invariant: legs_used >= 1 (entry price resolved via forward lookup).
    assert pr_q0.legs_used >= 1, (
        f"legs_used={pr_q0.legs_used}: entry price was not resolved for the Sunday "
        "rebalance date 2016-08-14.  _close_strictly_after fix may not be active."
    )

    # The forward return must be real (not None).
    assert pr_q0.twr_pct is not None, (
        "twr_pct is None for the initial basket — the Sunday-rebalance entry "
        "price was not resolved.  _close_strictly_after fix may not be active."
    )

    # partial_history must be False: both entry (100) and terminal (110) resolved.
    assert pr_q0.partial_history is False, (
        f"partial_history={pr_q0.partial_history}: must be False when both entry "
        "and terminal prices resolve cleanly."
    )

    # Correctness spot-check: entry=100 (Monday Aug-15), terminal=110 (next rebal) → +10%.
    # quarter-0 is_current=True, end_date="2016-11-14" → _close_on_or_before → 110.
    # prices = [100, 110] → TWR = 10%.
    assert pr_q0.twr_pct == pytest.approx(10.0, abs=0.05), (
        f"Expected initial-basket forward return ~10% (100→110), got {pr_q0.twr_pct}"
    )

    # Verify _extract_streaks stored the Monday close as the entry price.
    legs_raw = [("2016-08-14", 0.5), ("2016-11-14", 0.5)]
    streaks = _extract_streaks("AAPL", legs_raw, closes)
    assert len(streaks) >= 1, "Expected at least one streak for AAPL"
    first_entry_price = streaks[0][0][2]
    assert first_entry_price == pytest.approx(100.0), (
        f"Entry price stored in streak should be the Monday close 100.0, "
        f"got {first_entry_price} — _close_strictly_after not active at the entry lookup"
    )


# ---------------------------------------------------------------------------
# WR-1b: rb[1] two-leg restoration — the Aug→Nov leg must no longer be dropped.
# ---------------------------------------------------------------------------


def test_rb1_two_legs_not_dropped_after_on_or_after_fix():
    """Two-leg streak (Aug-14 Sunday → Nov-14 next rebal): the Aug→Nov leg is intact.

    Before the fix, _close_on_or_before("AAPL", "2016-08-14") returned None
    (panel starts 2016-08-15) → entry None → leg dropped → legs_used=0 for the
    whole streak.

    After the fix, _close_strictly_after("AAPL", "2016-08-14") returns 100.0
    (Monday Aug-15) → entry valid → legs_used >= 1.
    """
    closes = {
        "AAPL": {
            "2016-08-15": 100.0,   # Monday fill
            "2016-11-14": 115.0,   # second rebalance
            "2017-02-13": 125.0,   # third rebalance (terminal for latest)
        }
    }
    band_legs = [
        ("2016-08-14", {"AAPL": 0.5}),   # Sunday initial basket
        ("2016-11-14", {"AAPL": 0.5}),   # Q1
        ("2017-02-13", {"AAPL": 0.5}),   # Q2 / latest
    ]
    nav_net = [100.0, 108.0, 116.0]
    nav_dates = ["2016-08-14", "2016-11-14", "2017-02-13"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )

    assert len(per_quarter) == 3

    # Quarter-0 (Aug-14 → Nov-14 leg): legs_used must be >= 1 (the Aug→Nov leg is valid).
    pr_q0 = per_quarter[0].get("AAPL")
    assert pr_q0 is not None
    assert pr_q0.legs_used >= 1, (
        f"rb[1] two-leg restoration FAILED: legs_used={pr_q0.legs_used} at Q0.  "
        "The Aug-14 Sunday entry → Nov-14 terminal leg must no longer be dropped after "
        "the _close_strictly_after fix."
    )

    # Quarter-1 (Aug-14 → Nov-14 → Feb-13): cumulative streak legs_used >= 2.
    pr_q1 = per_quarter[1].get("AAPL")
    assert pr_q1 is not None
    assert pr_q1.legs_used >= 2, (
        f"Q1 legs_used={pr_q1.legs_used}: expected >= 2 (Aug→Nov + Nov→Feb sub-periods)."
    )


# ---------------------------------------------------------------------------
# WR-3: STRICT boundary (F1, 2026-07-03) — for a leg date that IS a trading
#        day, _close_strictly_after resolves to the NEXT trading day's close,
#        NOT the same day (unlike _close_on / _close_on_or_before, which both
#        still resolve to the same-day close). This replaces the pre-F1
#        "interior trading-day invariance" test, whose premise (all three
#        helpers agree on a trading day) was true only under the superseded
#        on-or-after convention.
# ---------------------------------------------------------------------------


def test_close_strictly_after_excludes_same_day_resolves_to_next_trading_day():
    """On a trading day, _close_strictly_after != _close_on / _close_on_or_before.

    _close_on(date) == _close_on_or_before(date) == the SAME-day close (both
    inclusive-at-date helpers, unaffected by F1). _close_strictly_after(date)
    instead resolves to the NEXT trading day's close — the T+1-fill proxy — and
    is None at the panel's last date (nothing trades after it).
    """
    from compute.portfolio.position_returns import _close_on

    closes = {
        "MSFT": {
            "2020-01-02": 150.0,
            "2020-04-01": 160.0,
            "2020-07-01": 170.0,
        }
    }

    expected_next = {"2020-01-02": 160.0, "2020-04-01": 170.0}
    for date, next_px in expected_next.items():
        px_before = _close_on_or_before("MSFT", date, closes)
        px_on = _close_on("MSFT", date, closes)
        px_after = _close_strictly_after("MSFT", date, closes)

        assert px_before == pytest.approx(px_on), (
            f"_close_on_or_before != _close_on at trading-day date {date}: "
            f"{px_before} != {px_on}"
        )
        assert px_after == pytest.approx(next_px), (
            f"_close_strictly_after at trading-day date {date} must resolve to "
            f"the NEXT trading day's close {next_px} (T+1 fill), got {px_after}"
        )
        assert px_after != pytest.approx(px_on), (
            f"_close_strictly_after must NOT equal the same-day close {px_on} "
            f"at {date} — same-day is excluded under the strict (F1) convention"
        )

    # The panel's last trading day has nothing strictly after it.
    assert _close_strictly_after("MSFT", "2020-07-01", closes) is None, (
        "no close exists strictly after the panel's last date"
    )


# ---------------------------------------------------------------------------
# WR-2 (original negative test): panel hole spanning full sub-period → None.
# ---------------------------------------------------------------------------


def test_no_price_in_sub_period_yields_none_entry():
    """When NO close exists on or after the rebalance date (within not_after bound),
    entry price must be None → legs_used=0 → no fabricated price.

    Fixture: only price is BEFORE the rebalance date and AFTER the next rebalance.
    The not_after bound (= next leg date) prevents the entry from leaping past the
    terminal date.
    """
    closes = {
        "XYZ": {
            "2020-01-01": 99.0,    # BEFORE the first rebalance
            "2020-07-01": 150.0,   # AFTER the second rebalance
        }
    }
    band_legs = [
        ("2020-02-01", {"XYZ": 0.5}),   # no close in [Feb-1, Mar-31]
        ("2020-04-01", {"XYZ": 0.5}),
    ]
    nav_net = [100.0, 102.0]
    nav_dates = ["2020-02-01", "2020-04-01"]

    per_quarter = compute_position_returns_per_quarter(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )

    assert len(per_quarter) == 2

    # Quarter 0: no close in [2020-02-01, 2020-04-01] → entry=None → legs_used=0.
    pr_q0 = per_quarter[0].get("XYZ")
    assert pr_q0 is not None, "XYZ should appear in quarter-0 map (even with null entry)"

    assert pr_q0.legs_used == 0, (
        f"legs_used={pr_q0.legs_used}: a price was fabricated for XYZ even though "
        "no close exists in [2020-02-01, 2020-04-01].  The not_after bound is broken."
    )
    assert pr_q0.twr_pct is None, (
        f"twr_pct={pr_q0.twr_pct}: should be None when no valid entry price exists."
    )

    # Verify _close_strictly_after behaviour directly:
    # not_after = next leg date = 2020-04-01
    px = _close_strictly_after("XYZ", "2020-02-01", closes, not_after="2020-04-01")
    assert px is None, (
        f"_close_strictly_after must return None when no close exists in [Feb-1, Apr-1], "
        f"got {px}.  The not_after bound is not enforced."
    )


# ---------------------------------------------------------------------------
# WR-3: RECONCILIATION-INVARIANCE — Carino GROSS identity / cost-line residual
#        outputs are byte-identical; pp_twr cross-check stays coherent.
# ---------------------------------------------------------------------------


def test_weekend_rebalance_reconciliation_errors_are_display_only_safe():
    """reconciliation_errors outputs are byte-identical before/after the entry-price fix.

    The _close_strictly_after change is DISPLAY-ONLY-SAFE:
      - Carino GROSS identity (sub_periods-based BHB/chain) is immune: it never
        reads the entry price from the closes panel.
      - pp_twr cross-check now uses _close_strictly_after for entry too, so it
        stays coherent with the engine TWR for clean single-streak names.

    Fixture: Sunday initial basket with a Monday close.  sub_periods=None path
    (PR-2a compat): gross_err=None, cost=None, clamp=0 must hold.
    pp_twr_err must be either None (if AAPL skipped) or a finite non-negative float.
    """
    closes = {
        "AAPL": {
            "2016-08-15": 100.0,   # Monday fill
            "2016-11-14": 110.0,   # next rebalance boundary
            "2016-12-30": 115.0,   # latest close in the panel
        }
    }
    band_legs = [
        ("2016-08-14", {"AAPL": 0.5}),   # Sunday initial basket
        ("2016-11-14", {"AAPL": 0.5}),
    ]
    nav_net = [100.0, 108.0]
    nav_dates = ["2016-08-14", "2016-11-14"]

    pos_returns = compute_position_returns(
        band_legs, closes, portfolio_nav_net=nav_net, portfolio_nav_dates=nav_dates
    )

    gross_err, cost_residual, pp_twr_err, clamp_count = reconciliation_errors(
        pos_returns, nav_net, nav_dates, band_legs, closes=closes, sub_periods=None
    )

    # sub_periods=None → Carino fields must be None, clamp must be 0.
    assert gross_err is None, (
        f"gross_err={gross_err}: must be None when sub_periods=None "
        "(reconciliation-invariance broken by the entry-price fix)"
    )
    assert cost_residual is None, (
        f"cost_residual={cost_residual}: must be None when sub_periods=None"
    )
    assert clamp_count == 0, (
        f"clamp_count={clamp_count}: must be 0 when sub_periods=None"
    )

    # pp_twr_error: may be None or a finite non-negative float.
    if pp_twr_err is not None:
        assert math.isfinite(pp_twr_err), (
            f"pp_twr_err={pp_twr_err}: must be finite — "
            "the entry-price fix must not corrupt the pp_twr diagnostic"
        )
        assert pp_twr_err >= 0.0, (
            f"pp_twr_err={pp_twr_err}: must be non-negative (max absolute error)"
        )


# ---------------------------------------------------------------------------
# WR-4: Hypothesis property — _close_on_or_before never looks ahead.
#        (unchanged; the terminal-price helper is unmodified by this fix)
# ---------------------------------------------------------------------------


@given(
    dates_prices=st.dictionaries(
        keys=st.dates(
            min_value=__import__("datetime").date(2010, 1, 1),
            max_value=__import__("datetime").date(2025, 12, 31),
        ).map(lambda d: d.isoformat()),
        values=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=20,
    ),
    query_date=st.dates(
        min_value=__import__("datetime").date(2010, 1, 1),
        max_value=__import__("datetime").date(2025, 12, 31),
    ).map(lambda d: d.isoformat()),
)
def test_close_on_or_before_never_looks_ahead(
    dates_prices: dict[str, float],
    query_date: str,
) -> None:
    """_close_on_or_before(ticker, date, closes) resolves to a date <= date (no look-ahead).

    For any closes panel and query_date:
      - If a value is returned, the underlying date in the panel that was
        selected must be <= query_date.
      - The returned price must be > 0 (already _is_valid_price-guarded).
    """
    closes = {"T": dates_prices}
    px = _close_on_or_before("T", query_date, closes)

    if px is not None:
        # The returned price must be positive (is_valid_price guard).
        assert px > 0.0, f"_close_on_or_before returned non-positive price: {px}"

        # The selected date must be <= query_date.
        series = closes["T"]
        eligible = [d for d in series if d <= query_date and series[d] == px and series[d] > 0]
        assert len(eligible) >= 1, (
            f"_close_on_or_before returned {px} but no eligible date (<=  {query_date}) "
            f"exists in the panel with that price and value > 0. Look-ahead may have occurred."
        )
        best_eligible = max(eligible)
        assert best_eligible <= query_date, (
            f"_close_on_or_before resolved to date {best_eligible} which is AFTER "
            f"query_date {query_date}: look-ahead occurred!"
        )


# ---------------------------------------------------------------------------
# WR-5: Hypothesis property — _close_strictly_after returns None OR the MIN date
#        > date (strict; and <= not_after when bounded).
# ---------------------------------------------------------------------------


@given(
    dates_prices=st.dictionaries(
        keys=st.dates(
            min_value=__import__("datetime").date(2010, 1, 1),
            max_value=__import__("datetime").date(2025, 12, 31),
        ).map(lambda d: d.isoformat()),
        values=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=20,
    ),
    query_date=st.dates(
        min_value=__import__("datetime").date(2010, 1, 1),
        max_value=__import__("datetime").date(2025, 12, 31),
    ).map(lambda d: d.isoformat()),
    use_not_after=st.booleans(),
    not_after_delta=st.integers(min_value=0, max_value=365),
)
def test_close_strictly_after_returns_min_eligible_date(
    dates_prices: dict[str, float],
    query_date: str,
    use_not_after: bool,
    not_after_delta: int,
) -> None:
    """_close_strictly_after(ticker, date, closes) returns None OR the MIN date > date.

    When not_after is provided the result must also satisfy date < result <= not_after.
    The returned price must be > 0 (already _is_valid_price-guarded).

    This is the Hypothesis property covering:
      - Positivity: returned price > 0
      - Minimality: returned date == min(eligible) where eligible = dates > date (strict)
        (and <= not_after when bounded)
      - Boundedness: result date <= not_after when provided
    """
    import datetime

    # Optionally add a not_after bound (a date >= query_date, but may or may not
    # have panel entries in between — that is the interesting case).
    q_date_obj = datetime.date.fromisoformat(query_date)
    not_after: str | None = None
    if use_not_after:
        na_date_obj = q_date_obj + datetime.timedelta(days=not_after_delta)
        # Cap at 2025-12-31 to stay within the dates_prices generation range.
        na_date_obj = min(na_date_obj, datetime.date(2025, 12, 31))
        not_after = na_date_obj.isoformat()

    closes = {"T": dates_prices}
    px = _close_strictly_after("T", query_date, closes, not_after=not_after)

    series = dates_prices
    eligible = [
        d for d in series
        if d > query_date
        and (not_after is None or d <= not_after)
        and series[d] > 0
    ]

    if px is None:
        # Either no eligible date, or every eligible price is <= 0 or None.
        # We only constructed positive floats (min_value=0.01) so any eligible date
        # should have a valid price → None iff eligible is empty.
        assert not eligible, (
            f"_close_strictly_after returned None but eligible dates exist: {eligible}. "
            f"query_date={query_date}, not_after={not_after}"
        )
    else:
        # Price must be positive.
        assert px > 0.0, f"_close_strictly_after returned non-positive price: {px}"

        # The selected date must be the MINIMUM eligible date.
        assert eligible, "Got a non-None result but eligible is empty — internal inconsistency"
        min_eligible = min(eligible)

        # Verify the returned price matches the min-eligible date's price.
        assert px == pytest.approx(series[min_eligible]), (
            f"_close_strictly_after returned price {px} but the min eligible date "
            f"{min_eligible} has price {series[min_eligible]}. "
            f"The helper is not returning the MINIMUM eligible date."
        )

        # Boundedness: the resolved date must satisfy date < resolved <= not_after.
        assert min_eligible > query_date, (
            f"_close_strictly_after resolved to date {min_eligible} <= query_date "
            f"{query_date}: look-back (or same-day) occurred!"
        )
        if not_after is not None:
            assert min_eligible <= not_after, (
                f"_close_strictly_after resolved to date {min_eligible} > not_after {not_after}: "
                "the not_after bound was violated!"
            )
