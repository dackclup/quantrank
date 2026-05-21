"""Unit tests for compute.valuation.rim.

18 cases per kickoff Step 4.4 spec:
  A. Math correctness (4)
  B. Applicability gates delegated (4)
  C. Soft / unknown stale OK (2)
  D. Defensive overflow (1)
  E. Custom forecast_years (2)
  F. Custom cost_of_equity (1)
  G. Cross-method invariants (2)
  H. @network sanity (2, --run-network)
"""

from __future__ import annotations

import math
import os

import pytest

from compute import config
from compute.valuation.applicability import MethodApplicability
from compute.valuation.rim import rim_fair_price

# -- A. Math correctness ------------------------------------------------------

def test_A1_golden_flat_roe_above_ke_5y():
    """Hand-calculated reference: B_0=10, R=0.15, Ke=0.10, N=5.

    Year-by-year:
      t=1: RI = 0.05 × 10     = 0.50    PV = 0.50/1.10        ≈ 0.4545454545
           B  = 10 × 1.15     = 11.5
      t=2: RI = 0.05 × 11.5   = 0.575   PV = 0.575/1.21       ≈ 0.4752066116
           B  = 11.5 × 1.15   = 13.225
      t=3: RI = 0.05 × 13.225 = 0.66125 PV = 0.66125/1.331    ≈ 0.4968746804
           B  = 13.225 × 1.15 = 15.20875
      t=4: RI = 0.05 × 15.209 ≈ 0.7604  PV = 0.7604/1.4641    ≈ 0.5193053967
           B  = 15.209 × 1.15 = 17.490
      t=5: RI = 0.05 × 17.490 ≈ 0.8745  PV = 0.8745/1.61051   ≈ 0.5429319466
    Sum PVs ≈ 2.4888640898
    V_0 = 10 + 2.4889 ≈ 12.4889
    """
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        cost_of_equity=0.10,
        forecast_years=5,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    assert math.isclose(fair, 12.4889, abs_tol=1e-3)


def test_A2_boundary_roe_equals_ke_skipped_as_value_trap():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.10,
        cost_of_equity=0.10,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_A3_roe_just_above_ke_yields_small_residual():
    # spread = 0.005; V_0 should be barely above B_0.
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.105,
        cost_of_equity=0.10,
        forecast_years=5,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    assert 10.0 < fair < 11.0


def test_A4_high_roe_compounder_yields_substantial_v0():
    # spread = 0.15, plus aggressive book compounding (1.25/yr).
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.25,
        cost_of_equity=0.10,
        forecast_years=5,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 15.0


# -- B. Applicability gates delegated -----------------------------------------

def test_B1_roe_below_ke_skipped_as_value_trap():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.05,
        cost_of_equity=0.10,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_B2_none_roe_skipped():
    """Issue #11 fix: None ROE skips under `insufficient_history_for_roe`,
    not the value_trap reason — the ensemble doesn't append a spurious
    value_trap_risk warning for tickers with incomplete equity history."""
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=None,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "insufficient_history_for_roe"


def test_B3_none_tbvps_skipped():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=None,
        avg_3y_roe=0.20,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_or_missing_tangible_book"


def test_B4_hard_stale_skipped():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.20,
        lag_status="hard",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "stale_filing_hard"


# -- C. Soft / unknown stale OK -----------------------------------------------

def test_C1_soft_stale_computes_normally():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        lag_status="soft",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 0


def test_C2_unknown_stale_computes_normally():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        lag_status="unknown",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 0


# -- D. Defensive overflow ----------------------------------------------------

def test_D1_pathological_roe_200pct_5y_still_finite():
    # ROE=2.0 over 5y → B_5 = 10 × 3^5 = 2430 (well below 1e15 threshold).
    # Overflow guard should NOT fire for plausible-but-extreme ROE values.
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=2.0,
        cost_of_equity=0.10,
        forecast_years=5,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    assert math.isfinite(fair)
    assert fair > 0


def test_D2_overflow_guard_fires_on_truly_runaway_inputs():
    # ROE=10.0 (1000%) over 50 years → 11^50 ≈ 1e52 → guard fires.
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=10.0,
        cost_of_equity=0.10,
        forecast_years=50,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "rim_book_value_overflow"


# -- E. Custom forecast_years -------------------------------------------------

def test_E1_longer_horizon_yields_higher_v0():
    fair_5y, _ = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        cost_of_equity=0.10,
        forecast_years=5,
        lag_status="fresh",
    )
    fair_10y, _ = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        cost_of_equity=0.10,
        forecast_years=10,
        lag_status="fresh",
    )
    assert fair_5y is not None and fair_10y is not None
    assert fair_10y > fair_5y


def test_E2_one_year_forecast_yields_minimal_residual():
    # B_0=10, R=0.15, Ke=0.10, N=1
    # RI_1 = 0.05 × 10 = 0.50; PV = 0.50/1.10 ≈ 0.4545
    # V_0 ≈ 10.4545
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        cost_of_equity=0.10,
        forecast_years=1,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    assert math.isclose(fair, 10.4545, abs_tol=1e-3)


# -- F. Custom cost_of_equity -------------------------------------------------

def test_F1_lower_ke_yields_higher_v0():
    """Lower discount rate AND larger spread → V_0 increases."""
    fair_default_ke, _ = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        cost_of_equity=0.10,
        forecast_years=5,
        lag_status="fresh",
    )
    fair_low_ke, _ = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        cost_of_equity=0.08,
        forecast_years=5,
        lag_status="fresh",
    )
    assert fair_default_ke is not None and fair_low_ke is not None
    assert fair_low_ke > fair_default_ke


# -- G. Cross-method invariants -----------------------------------------------

def test_G1_returns_consistent_tuple_shape():
    fair, app = rim_fair_price(
        tangible_book_value_per_share=10.0,
        avg_3y_roe=0.15,
        lag_status="fresh",
    )
    assert isinstance(fair, float)
    assert isinstance(app, MethodApplicability)


def test_G2_default_forecast_years_is_5_from_config():
    assert config.RIM_FORECAST_YEARS == 5
    # And the default cost of equity remains 0.10 (Step 1 invariant).
    assert config.COST_OF_EQUITY == 0.10


def test_G3_module_re_exported_in_package_init():
    from compute import valuation
    assert hasattr(valuation, "rim_fair_price")
    assert callable(valuation.rim_fair_price)


# -- H. @network sanity (--run-network) --------------------------------------

@pytest.mark.network
def test_H1_aapl_rim_real_edgar():
    """Compute RIM for AAPL using EDGAR fundamentals.

    Lenient assertion (per Step 3 pattern): if avg_3y_roe > Ke, RIM
    must compute and V_0 > TBVPS (residual income is positive). If
    avg_3y_roe ≤ Ke (unlikely for AAPL), applicability skips with the
    value-trap reason.
    """
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    from compute.valuation.tangible_book import tangible_book_value_per_share
    set_identity(os.environ["EDGAR_USER_AGENT"])

    snap = fundamentals_mod._build_snapshot("AAPL", "0000320193")
    tbvps = tangible_book_value_per_share(snap)
    if tbvps is None:
        pytest.skip("AAPL TBVPS is None this snapshot — RIM precondition fails")

    # avg_3y_roe proxy from latest snapshot: NI / equity.
    if snap.net_income is None or snap.stockholders_equity in (None, 0):
        pytest.skip("AAPL net_income or stockholders_equity missing this snapshot")
    roe_proxy = float(snap.net_income) / float(snap.stockholders_equity)

    fair, app = rim_fair_price(
        tangible_book_value_per_share=tbvps,
        avg_3y_roe=roe_proxy,
        cost_of_equity=0.10,
        lag_status="fresh",
    )

    if roe_proxy <= 0.10:
        assert fair is None
        assert app.applicable is False
        assert app.reason == "value_trap_risk_roe_below_cost_of_equity"
    else:
        assert app.applicable is True
        assert fair is not None
        # Residual income positive → V_0 > B_0 strictly.
        assert fair > tbvps


@pytest.mark.network
def test_H2_breadth_5_tickers_produce_v0_or_value_trap():
    """≥3 of 5 quality tickers should produce applicable=True; the
    rest must skip with value-trap-risk reason (not arbitrary)."""
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    from compute.valuation.tangible_book import tangible_book_value_per_share
    set_identity(os.environ["EDGAR_USER_AGENT"])

    tickers = {
        "KO":   "0000021344",
        "PG":   "0000080424",
        "MSFT": "0000789019",
        "JNJ":  "0000200406",
        "MMM":  "0000066740",
    }

    applicable_count = 0
    skip_reasons: list[tuple[str, str | None]] = []
    for ticker, cik in tickers.items():
        snap = fundamentals_mod._build_snapshot(ticker, cik)
        tbvps = tangible_book_value_per_share(snap)
        if tbvps is None or snap.net_income is None or snap.stockholders_equity in (None, 0):
            skip_reasons.append((ticker, "missing_inputs"))
            continue
        roe_proxy = float(snap.net_income) / float(snap.stockholders_equity)
        fair, app = rim_fair_price(
            tangible_book_value_per_share=tbvps,
            avg_3y_roe=roe_proxy,
            lag_status="fresh",
        )
        if app.applicable:
            applicable_count += 1
        else:
            skip_reasons.append((ticker, app.reason))
            assert app.reason in (
                "value_trap_risk_roe_below_cost_of_equity",
                "non_positive_or_missing_tangible_book",
            ), f"{ticker} unexpected RIM skip reason: {app.reason}"

    assert applicable_count >= 3, (
        f"Only {applicable_count}/5 tickers produced V_0; expected ≥3 from "
        f"this set of high-ROE quality names. Skips: {skip_reasons}"
    )
