"""Unit tests for compute.valuation.multiples.

24+ cases per kickoff Step 4.3 spec:
  A. compute_peer_medians (8 cases)
  B. P/E method (4-5 cases)
  C. P/B method (4 cases)
  D. EV/EBITDA method (7-8 cases)
  E. Cross-method invariants (4-5 cases)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import is_dataclass

import pytest

from compute import config
from compute.valuation.applicability import SKIP_REASONS, MethodApplicability
from compute.valuation.multiples import (
    PeerMedian,
    PeerTierUsed,
    _linear_percentile,
    _winsorize_5_95,
    compute_peer_medians,
    multiples_ev_ebitda_fair_price,
    multiples_pb_fair_price,
    multiples_pe_fair_price,
)

# -- Group A: compute_peer_medians peer-tier walk ----------------------------

def test_A1_sub_industry_tier_succeeds_with_10_peers():
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: [f"P{i:02d}" for i in range(10)],
        PeerTierUsed.INDUSTRY: [f"I{i:02d}" for i in range(20)],
        PeerTierUsed.SECTOR: [f"S{i:02d}" for i in range(50)],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [f"B{i:03d}" for i in range(400)],
    }
    metric_values = {f"P{i:02d}": 10.0 + i for i in range(10)}
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.SUB_INDUSTRY
    assert out.peer_count == 10
    # Median of [10..19] = (14+15)/2 = 14.5 (post-winsorize, no extremes)
    assert out.median is not None
    assert math.isclose(out.median, 14.5, abs_tol=1e-6)


def test_A2_industry_tier_falls_through_when_sub_industry_too_small():
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: [f"S{i}" for i in range(5)],   # only 5 — below 8
        PeerTierUsed.INDUSTRY: [f"I{i}" for i in range(15)],     # 15 — sufficient
        PeerTierUsed.SECTOR: [f"X{i}" for i in range(50)],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [],
    }
    metric_values = {**{f"S{i}": 5.0 for i in range(5)},
                     **{f"I{i}": 20.0 + i for i in range(15)}}
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.INDUSTRY
    assert out.peer_count == 15


def test_A3_sector_tier_falls_through_when_smaller_tiers_insufficient():
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: ["S1", "S2"],         # 2
        PeerTierUsed.INDUSTRY: ["I1", "I2", "I3"],       # 3
        PeerTierUsed.SECTOR: [f"X{i}" for i in range(50)],   # 50 — sufficient
        PeerTierUsed.BROAD_EX_FIN_UTIL: [],
    }
    metric_values = {
        **{f"S{i}": 100.0 for i in range(1, 3)},
        **{f"I{i}": 100.0 for i in range(1, 4)},
        **{f"X{i}": 30.0 for i in range(50)},
    }
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.SECTOR
    assert out.peer_count == 50


def test_A4_broad_fallback_used_when_all_gics_tiers_insufficient():
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: [],
        PeerTierUsed.INDUSTRY: [],
        PeerTierUsed.SECTOR: [],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [f"B{i:03d}" for i in range(490)],
    }
    metric_values = {f"B{i:03d}": 18.0 + (i % 7) for i in range(490)}
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.BROAD_EX_FIN_UTIL
    assert out.peer_count == 490


def test_A5_all_4_tiers_fail_returns_insufficient():
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: ["A", "B"],
        PeerTierUsed.INDUSTRY: ["C", "D"],
        PeerTierUsed.SECTOR: ["E", "F", "G"],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [],
    }
    metric_values = {t: 10.0 for t in ("A", "B", "C", "D", "E", "F", "G")}
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.INSUFFICIENT
    assert out.median is None
    assert out.peer_count == 0
    # Audit trail shows all 4 tiers attempted
    assert len(out.tier_thresholds_tried) == 4


def test_A6_target_ticker_excluded_from_peer_set():
    # 9 peers including the target; target's metric should NOT count.
    # 8 valid peers + the target → peer_count after exclusion = 8.
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: ["TGT", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
        PeerTierUsed.INDUSTRY: [],
        PeerTierUsed.SECTOR: [],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [],
    }
    metric_values = {"TGT": 999.0,  # target's metric — must NOT be in median
                     **{f"P{i}": 10.0 for i in range(1, 9)}}
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.SUB_INDUSTRY
    assert out.peer_count == 8
    assert out.median == 10.0  # peer median, not influenced by 999


def test_A7_winsorization_caps_extreme_outliers():
    sorted_input = [1, 1, 5, 10, 12, 14, 16, 20, 25, 30, 35, 1000]
    tickers = [f"P{i}" for i in range(len(sorted_input))]
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: tickers,
        PeerTierUsed.INDUSTRY: [],
        PeerTierUsed.SECTOR: [],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [],
    }
    metric_values = dict(zip(tickers, [float(v) for v in sorted_input], strict=False))
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.SUB_INDUSTRY
    assert out.peer_count == 12
    # Median is robust to one top outlier; post-winsorize median = 15.
    assert out.median is not None
    assert math.isclose(out.median, 15.0, abs_tol=1e-9)


def test_A8_filters_out_none_zero_and_negative_metric_values():
    tickers = [f"P{i:02d}" for i in range(11)]
    tickers_by_tier = {
        PeerTierUsed.SUB_INDUSTRY: tickers,
        PeerTierUsed.INDUSTRY: [],
        PeerTierUsed.SECTOR: [],
        PeerTierUsed.BROAD_EX_FIN_UTIL: [],
    }
    metric_values = {
        "P00": None,
        "P01": 0.0,
        "P02": -5.0,
        "P03": 10.0, "P04": 12.0, "P05": 14.0, "P06": 16.0,
        "P07": 18.0, "P08": 20.0, "P09": 22.0, "P10": 24.0,
    }
    out = compute_peer_medians(
        tickers_by_tier=tickers_by_tier,
        metric_values=metric_values,
        target_ticker="TGT",
    )
    assert out.tier_used == PeerTierUsed.SUB_INDUSTRY
    assert out.peer_count == 8  # P00/P01/P02 filtered
    # Median of 8 valid: [10,12,14,16,18,20,22,24] → (16+18)/2 = 17
    assert out.median is not None
    assert math.isclose(out.median, 17.0, abs_tol=1e-9)


# Bonus A: linear-percentile + winsorize unit tests

def test_linear_percentile_matches_numpy_default():
    sorted_v = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert math.isclose(_linear_percentile(sorted_v, 0.25), 2.0)
    assert math.isclose(_linear_percentile(sorted_v, 0.50), 3.0)
    assert math.isclose(_linear_percentile(sorted_v, 0.75), 4.0)


def test_winsorize_5_95_clips_correctly():
    vals = [1, 1, 5, 10, 12, 14, 16, 20, 25, 30, 35, 1000]
    out = _winsorize_5_95([float(v) for v in vals])
    assert min(out) >= 1.0
    assert max(out) <= 469.25 + 1e-6
    assert math.isclose(statistics.median(out), 15.0, abs_tol=1e-9)


# -- Group B: P/E method ------------------------------------------------------

def test_B1_pe_fair_price_simple_multiplication():
    fair, app = multiples_pe_fair_price(
        eps_ttm=2.0,
        peer_pe_median=15.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair == 30.0


def test_B2_pe_skips_when_eps_non_positive():
    fair, app = multiples_pe_fair_price(
        eps_ttm=-1.0,
        peer_pe_median=15.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_or_missing_eps_ttm"


def test_B3_pe_skips_when_peer_median_none():
    fair, app = multiples_pe_fair_price(
        eps_ttm=2.0,
        peer_pe_median=None,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "missing_or_non_positive_peer_pe"


def test_B4_pe_skips_when_filing_hard_stale():
    fair, app = multiples_pe_fair_price(
        eps_ttm=2.0,
        peer_pe_median=15.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="hard",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "stale_filing_hard"


def test_B5_pe_skips_when_tier_insufficient():
    fair, app = multiples_pe_fair_price(
        eps_ttm=2.0,
        peer_pe_median=None,
        peer_tier_used=PeerTierUsed.INSUFFICIENT,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "insufficient_peers_all_tiers"


# -- Group C: P/B method ------------------------------------------------------

def test_C1_pb_fair_price_uses_reported_bvps_not_tbvps():
    fair, app = multiples_pb_fair_price(
        bvps_reported=10.0,
        peer_pb_median=2.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair == 20.0


def test_C2_pb_skips_when_bvps_non_positive():
    fair, app = multiples_pb_fair_price(
        bvps_reported=-5.0,
        peer_pb_median=2.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_or_missing_bvps"


def test_C3_pb_skips_when_peer_median_none():
    fair, app = multiples_pb_fair_price(
        bvps_reported=10.0,
        peer_pb_median=None,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "missing_or_non_positive_peer_pb"


def test_C4_pb_skips_when_filing_hard_stale():
    fair, app = multiples_pb_fair_price(
        bvps_reported=10.0,
        peer_pb_median=2.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        lag_status="hard",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "stale_filing_hard"


# -- Group D: EV/EBITDA method ------------------------------------------------

def test_D1_ev_ebitda_simple_case():
    # EV = 100 × 12 = 1200; equity = 1200 − 200 = 1000; per share = 100
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=200.0,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert math.isclose(fair, 100.0)


def test_D2_ev_ebitda_cash_rich_negative_net_debt():
    # net_debt = -300 (cash exceeds debt). EV = 1000; equity = 1000 - (-300)
    # = 1300; per share = 130.
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=10.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=-300.0,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert math.isclose(fair, 130.0)


def test_D3_ev_ebitda_high_leverage_negative_equity_skips():
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=50.0,
        peer_ev_ebitda_median=8.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=500.0,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "ev_ebitda_negative_equity_post_debt"


def test_D4_ev_ebitda_skips_financials_via_applicability():
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Financials",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=200.0,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "sector_excluded_financials"


def test_D5_ev_ebitda_skips_when_ebitda_none():
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=None,
        peer_ev_ebitda_median=12.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=200.0,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_or_missing_ebitda"


def test_D6_ev_ebitda_skips_when_net_debt_unknown():
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=None,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "ev_ebitda_net_debt_unknown"


def test_D7_ev_ebitda_skips_when_shares_missing():
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=200.0,
        shares_outstanding=None,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "missing_shares_outstanding"


def test_D8_ev_ebitda_skips_when_tier_insufficient():
    fair, app = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=None,
        peer_tier_used=PeerTierUsed.INSUFFICIENT,
        net_debt=200.0,
        shares_outstanding=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "insufficient_peers_all_tiers"


# -- Group E: cross-method invariants ----------------------------------------

def test_E1_all_methods_return_consistent_tuple_shape():
    fair_pe, app_pe = multiples_pe_fair_price(
        eps_ttm=2.0, peer_pe_median=15.0,
        peer_tier_used=PeerTierUsed.SECTOR, lag_status="fresh",
    )
    fair_pb, app_pb = multiples_pb_fair_price(
        bvps_reported=10.0, peer_pb_median=2.0,
        peer_tier_used=PeerTierUsed.SECTOR, lag_status="fresh",
    )
    fair_ev, app_ev = multiples_ev_ebitda_fair_price(
        sector="Information Technology",
        ebitda_ttm=100.0, peer_ev_ebitda_median=12.0,
        peer_tier_used=PeerTierUsed.SECTOR,
        net_debt=200.0, shares_outstanding=10.0, lag_status="fresh",
    )
    for fair, app in ((fair_pe, app_pe), (fair_pb, app_pb), (fair_ev, app_ev)):
        assert isinstance(fair, float)
        assert isinstance(app, MethodApplicability)
        assert app.applicable is True


def test_E2_peer_median_dataclass_is_frozen_with_expected_fields():
    assert is_dataclass(PeerMedian)
    pm = PeerMedian(
        median=15.0,
        tier_used=PeerTierUsed.SECTOR,
        peer_count=12,
        tier_thresholds_tried=((PeerTierUsed.SUB_INDUSTRY, 5),
                               (PeerTierUsed.INDUSTRY, 6),
                               (PeerTierUsed.SECTOR, 12)),
    )
    assert pm.median == 15.0
    assert pm.tier_used == PeerTierUsed.SECTOR
    assert pm.peer_count == 12
    assert len(pm.tier_thresholds_tried) == 3
    with pytest.raises(Exception):  # noqa: B017
        pm.median = 99.0  # type: ignore[misc]


def test_E3_new_skip_reasons_added_to_taxonomy():
    for new_reason in (
        "ev_ebitda_negative_equity_post_debt",
        "ev_ebitda_net_debt_unknown",
        "insufficient_peers_all_tiers",
    ):
        assert new_reason in SKIP_REASONS


def test_E4_module_public_surface_re_exported():
    from compute import valuation
    for name in (
        "PeerMedian", "PeerTierUsed", "compute_peer_medians",
        "multiples_pe_fair_price", "multiples_pb_fair_price",
        "multiples_ev_ebitda_fair_price",
    ):
        assert hasattr(valuation, name)


def test_E5_min_peers_constant_is_8():
    assert config.MULTIPLES_MIN_PEERS == 8
