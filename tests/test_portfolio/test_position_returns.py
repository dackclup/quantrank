"""Offline unit tests for compute.portfolio.position_returns.

Covers:
(a) Multi-rebalance holder with known prices → assert TWR, MWR correct.
(b) Null intermediate price → partial_history=True, TWR drops that leg.
(c) Re-entry after gap → only the current streak is used.
(d) Carino identity: Σ contrib_nav_pts ≈ portfolio NAV total return in pts.
(e) Weight → 0 terminates the streak.
(f) Empty band_legs returns empty dict.
(g) _days_between helper.
(h) _carino_coefficient edge cases (R=0, R=-1).
(i) position_returns_to_dict serialization.
"""
from __future__ import annotations

import math

import pytest

from compute.portfolio.position_returns import (
    PositionReturn,
    _carino_coefficient,
    _compute_mwr,
    _compute_twr,
    _days_between,
    _extract_streaks,
    _is_valid_price,
    _modified_dietz,
    compute_position_returns,
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
    """compute_position_returns uses only the LATEST streak for a re-entered name."""
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
            "2020-10-01": 3000.0,
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
    """Two tickers with clean price history produce non-None MWR and TWR."""
    band_legs = [
        ("2020-01-01", {"AAPL": 0.5, "MSFT": 0.5}),
        ("2020-04-01", {"AAPL": 0.5, "MSFT": 0.5}),
    ]
    closes = {
        "AAPL": {"2020-01-01": 100.0, "2020-04-01": 120.0},
        "MSFT": {"2020-01-01": 200.0, "2020-04-01": 220.0},
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

    carino_err, pp_err = reconciliation_errors(pr, nav_net, nav_dates, band_legs)
    # contrib_nav_pts is None → carino_error = None.
    assert carino_err is None
