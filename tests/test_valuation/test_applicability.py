"""Unit tests for compute.valuation.applicability.

36 cases per kickoff Step 4.1 spec — six per-method applicability gates plus
the stale-filing primitives. All cases are pure-function, deterministic,
offline.
"""

from __future__ import annotations

from datetime import date

import pytest

from compute import config
from compute.valuation.applicability import (
    SKIP_REASONS,
    MethodApplicability,
    check_dcf_applicability,
    check_graham_applicability,
    check_multiples_ev_ebitda_applicability,
    check_multiples_pb_applicability,
    check_multiples_pe_applicability,
    check_rim_applicability,
    filing_lag_days,
    stale_filing_status,
)

# -- DCF -----------------------------------------------------------------------

def test_dcf_skips_financials():
    out = check_dcf_applicability(
        sector="Financials",
        fcf_5y=[100.0, 110.0, 120.0, 130.0, 140.0],
        shares_outstanding=1_000_000.0,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "sector_excluded_financials"


def test_dcf_skips_utilities():
    out = check_dcf_applicability(
        sector="Utilities",
        fcf_5y=[50.0, 55.0, 60.0, 65.0, 70.0],
        shares_outstanding=1_000_000.0,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "sector_excluded_utilities"


def test_dcf_applicable_for_it_with_positive_fcf_and_fresh():
    out = check_dcf_applicability(
        sector="Information Technology",
        fcf_5y=[100.0, 110.0, 120.0, 130.0, 140.0],
        shares_outstanding=1_000_000.0,
        lag_status="fresh",
    )
    assert out.applicable is True
    assert out.reason is None


def test_dcf_skips_when_fcf_median_non_positive():
    # 4 of 5 negative → median negative → skip.
    out = check_dcf_applicability(
        sector="Information Technology",
        fcf_5y=[-50.0, -40.0, -30.0, -20.0, 100.0],
        shares_outstanding=1_000_000.0,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "non_positive_fcf_5y_median"


def test_dcf_skips_when_shares_missing():
    out = check_dcf_applicability(
        sector="Information Technology",
        fcf_5y=[100.0, 110.0, 120.0, 130.0, 140.0],
        shares_outstanding=None,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "missing_shares_outstanding"


def test_dcf_skips_when_filing_hard_stale():
    out = check_dcf_applicability(
        sector="Information Technology",
        fcf_5y=[100.0, 110.0, 120.0, 130.0, 140.0],
        shares_outstanding=1_000_000.0,
        lag_status="hard",
    )
    assert out.applicable is False
    assert out.reason == "stale_filing_hard"


def test_dcf_handles_partial_none_fcf_list():
    # 2 valid, 3 None — median of valid pair = positive → applicable.
    out = check_dcf_applicability(
        sector="Information Technology",
        fcf_5y=[None, None, None, 100.0, 200.0],
        shares_outstanding=1_000_000.0,
        lag_status="fresh",
    )
    assert out.applicable is True


def test_dcf_skips_when_fcf_list_all_none():
    out = check_dcf_applicability(
        sector="Information Technology",
        fcf_5y=[None, None, None, None, None],
        shares_outstanding=1_000_000.0,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "non_positive_fcf_5y_median"


# -- Graham --------------------------------------------------------------------

def test_graham_applicable_with_positive_eps_and_tbvps_and_fresh():
    out = check_graham_applicability(
        eps_3y_avg=2.5, tbvps=10.0, lag_status="fresh"
    )
    assert out.applicable is True


def test_graham_skips_when_eps_3y_avg_non_positive():
    out = check_graham_applicability(
        eps_3y_avg=-1.0, tbvps=10.0, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "non_positive_eps_3y_avg"


def test_graham_skips_when_tbvps_none():
    out = check_graham_applicability(
        eps_3y_avg=2.5, tbvps=None, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "non_positive_or_missing_tangible_book"


def test_graham_skips_when_tbvps_negative():
    out = check_graham_applicability(
        eps_3y_avg=2.5, tbvps=-5.0, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "non_positive_or_missing_tangible_book"


def test_graham_skips_when_filing_hard_stale():
    out = check_graham_applicability(
        eps_3y_avg=2.5, tbvps=10.0, lag_status="hard"
    )
    assert out.applicable is False
    assert out.reason == "stale_filing_hard"


# -- RIM ----------------------------------------------------------------------

def test_rim_applicable_for_financials_when_roe_above_ke():
    # RIM is the right method for banks/insurers — book equity is meaningful.
    out = check_rim_applicability(
        avg_3y_roe=0.18,  # 18% ROE
        tbvps=10.0,
        lag_status="fresh",
        cost_of_equity=0.10,
    )
    assert out.applicable is True


def test_rim_skips_when_roe_below_cost_of_equity():
    out = check_rim_applicability(
        avg_3y_roe=0.05,  # 5% ROE
        tbvps=10.0,
        lag_status="fresh",
        cost_of_equity=0.10,
    )
    assert out.applicable is False
    assert out.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_rim_skips_when_roe_exactly_equal_to_ke():
    # Strict inequality: ROE == Ke is not enough (no economic value created).
    out = check_rim_applicability(
        avg_3y_roe=0.10, tbvps=10.0, lag_status="fresh", cost_of_equity=0.10
    )
    assert out.applicable is False
    assert out.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_rim_skips_when_avg_roe_none():
    out = check_rim_applicability(
        avg_3y_roe=None, tbvps=10.0, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_rim_skips_when_tbvps_none():
    out = check_rim_applicability(
        avg_3y_roe=0.20, tbvps=None, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "non_positive_or_missing_tangible_book"


def test_rim_skips_when_filing_hard_stale():
    out = check_rim_applicability(
        avg_3y_roe=0.20, tbvps=10.0, lag_status="hard"
    )
    assert out.applicable is False
    assert out.reason == "stale_filing_hard"


def test_rim_uses_config_cost_of_equity_by_default():
    # Without explicit cost_of_equity, applicability uses config.COST_OF_EQUITY.
    out = check_rim_applicability(
        avg_3y_roe=config.COST_OF_EQUITY + 0.01,
        tbvps=10.0,
        lag_status="fresh",
    )
    assert out.applicable is True


# -- Multiples P/E -------------------------------------------------------------

def test_multiples_pe_applicable_with_positive_inputs():
    out = check_multiples_pe_applicability(
        eps_ttm=2.5, peer_pe_median=15.0, lag_status="fresh"
    )
    assert out.applicable is True


def test_multiples_pe_skips_when_eps_negative():
    out = check_multiples_pe_applicability(
        eps_ttm=-1.0, peer_pe_median=15.0, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "non_positive_or_missing_eps_ttm"


def test_multiples_pe_skips_when_peer_median_missing():
    out = check_multiples_pe_applicability(
        eps_ttm=2.5, peer_pe_median=None, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "missing_or_non_positive_peer_pe"


def test_multiples_pe_skips_when_filing_hard_stale():
    out = check_multiples_pe_applicability(
        eps_ttm=2.5, peer_pe_median=15.0, lag_status="hard"
    )
    assert out.applicable is False
    assert out.reason == "stale_filing_hard"


# -- Multiples P/B -------------------------------------------------------------

def test_multiples_pb_applicable_with_positive_bvps_and_peer_median():
    out = check_multiples_pb_applicability(
        bvps_reported=10.0, peer_pb_median=2.0, lag_status="fresh"
    )
    assert out.applicable is True


def test_multiples_pb_skips_when_bvps_negative():
    out = check_multiples_pb_applicability(
        bvps_reported=-5.0, peer_pb_median=2.0, lag_status="fresh"
    )
    assert out.applicable is False
    assert out.reason == "non_positive_or_missing_bvps"


def test_multiples_pb_skips_when_filing_hard_stale():
    out = check_multiples_pb_applicability(
        bvps_reported=10.0, peer_pb_median=2.0, lag_status="hard"
    )
    assert out.applicable is False
    assert out.reason == "stale_filing_hard"


# -- Multiples EV/EBITDA -------------------------------------------------------

def test_multiples_ev_ebitda_skips_financials():
    out = check_multiples_ev_ebitda_applicability(
        sector="Financials",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "sector_excluded_financials"


def test_multiples_ev_ebitda_applicable_for_it_with_positive_inputs():
    out = check_multiples_ev_ebitda_applicability(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        lag_status="fresh",
    )
    assert out.applicable is True


def test_multiples_ev_ebitda_skips_when_ebitda_negative():
    out = check_multiples_ev_ebitda_applicability(
        sector="Information Technology",
        ebitda_ttm=-50.0,
        peer_ev_ebitda_median=12.0,
        lag_status="fresh",
    )
    assert out.applicable is False
    assert out.reason == "non_positive_or_missing_ebitda"


def test_multiples_ev_ebitda_skips_when_filing_hard_stale():
    out = check_multiples_ev_ebitda_applicability(
        sector="Information Technology",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        lag_status="hard",
    )
    assert out.applicable is False
    assert out.reason == "stale_filing_hard"


def test_multiples_ev_ebitda_utilities_NOT_excluded():
    # Per kickoff §B2, only Financials gets the EV/EBITDA sector exclusion.
    out = check_multiples_ev_ebitda_applicability(
        sector="Utilities",
        ebitda_ttm=100.0,
        peer_ev_ebitda_median=12.0,
        lag_status="fresh",
    )
    assert out.applicable is True


# -- Stale filing primitives ---------------------------------------------------

def test_stale_filing_status_fresh_at_50_days():
    assert stale_filing_status(50) == "fresh"


def test_stale_filing_status_soft_at_130_days():
    assert stale_filing_status(130) == "soft"


def test_stale_filing_status_hard_at_200_days():
    assert stale_filing_status(200) == "hard"


def test_stale_filing_status_unknown_when_none():
    assert stale_filing_status(None) == "unknown"


def test_stale_filing_status_boundary_120_is_fresh():
    # Strict > on the soft cutoff: lag == FILING_STALE_SOFT_DAYS is fresh.
    assert config.FILING_STALE_SOFT_DAYS == 120
    assert stale_filing_status(120) == "fresh"


def test_stale_filing_status_boundary_121_is_soft():
    assert stale_filing_status(121) == "soft"


def test_stale_filing_status_boundary_180_is_soft():
    # Strict > on the hard cutoff: lag == FILING_STALE_HARD_DAYS is still soft.
    assert config.FILING_STALE_HARD_DAYS == 180
    assert stale_filing_status(180) == "soft"


def test_stale_filing_status_boundary_181_is_hard():
    assert stale_filing_status(181) == "hard"


def test_filing_lag_days_returns_none_when_filing_date_missing():
    assert filing_lag_days(None, date(2026, 5, 1)) is None


def test_filing_lag_days_computes_120_day_lag():
    assert filing_lag_days(date(2026, 1, 1), date(2026, 5, 1)) == 120


# -- Invariants ----------------------------------------------------------------

def test_method_applicability_rejects_invalid_state():
    # applicable=True with a reason should raise ValueError.
    with pytest.raises(ValueError):
        MethodApplicability(applicable=True, reason="anything")
    # applicable=False with no reason should also raise.
    with pytest.raises(ValueError):
        MethodApplicability(applicable=False, reason=None)


def test_skip_reasons_taxonomy_is_stable():
    # All skip reasons that any check function may emit are listed in
    # SKIP_REASONS. Step 5 ensemble will string-match against this set.
    assert "stale_filing_hard" in SKIP_REASONS
    assert "value_trap_risk_roe_below_cost_of_equity" in SKIP_REASONS
    # No duplicates.
    assert len(set(SKIP_REASONS)) == len(SKIP_REASONS)
