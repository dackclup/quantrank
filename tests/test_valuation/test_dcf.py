"""Unit tests for compute.valuation.dcf.

24+ cases per kickoff Step 4.5 spec:
  A. Math correctness (4)
  B. Defense #5 — Terminal-g constraint (3)
  C. Applicability gates delegated (5)
  D. Edge cases — equity / debt (3)
  E. Stale OK (2)
  F. Custom forecast_years (1)
  G. FCF normalization (2)
  H. Cross-method invariants (2)
  I. @network sanity (2, --run-network)
"""

from __future__ import annotations

import math
import os

import pytest

from compute import config
from compute.valuation.applicability import MethodApplicability
from compute.valuation.dcf import dcf_fair_price


# Convenience: standard 5-year flat-FCF synthetic input for math tests.
def _flat_fcf(value: float, n: int = 5) -> list[float | None]:
    return [value] * n


# -- A. Math correctness ------------------------------------------------------

def test_A1_golden_flat_fcf_100m_5y_wacc10_g3_no_debt_10m_shares():
    """Hand-calculated reference (kickoff Step 4.5 §A1):

    FCF=$100M flat, WACC=10%, g=3%, net_debt=0, shares=10M, IT sector.

    Stage 1 PV   = 100 × Σ(1/1.10^t for t=1..5) ≈ 379.0787
    Terminal raw = 100 × 1.03 / (0.10 − 0.03) = 1471.4286
    Terminal PV  = 1471.4286 / 1.10^5            = 913.5612
    EV           = 379.0787 + 913.5612            = 1292.6399
    Equity       = 1292.6399 − 0                  = 1292.6399
    Per share    = 1292.6399 / 10                 ≈ 129.26
    """
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.10,
        terminal_growth=0.03,
        forecast_years=5,
    )
    assert app.applicable is True
    assert fair is not None
    assert math.isclose(fair, 129.27, abs_tol=0.05)


def test_A2_higher_wacc_yields_lower_fair_value():
    fair_default, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.10,
        terminal_growth=0.03,
        forecast_years=5,
    )
    fair_high_wacc, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.12,
        terminal_growth=0.03,
        forecast_years=5,
    )
    assert app.applicable is True
    assert fair_default is not None and fair_high_wacc is not None
    assert fair_high_wacc < fair_default
    # Sanity: higher WACC should land in the $90-110 range vs ~$129 baseline.
    assert 80.0 < fair_high_wacc < 115.0


def test_A3_higher_g_yields_higher_fair_value():
    """Ordering: g=2.5% < g=3.0% < g=NA at higher (capped at 0.03)."""
    fair_g25, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.10,
        terminal_growth=0.025,
        forecast_years=5,
    )
    fair_g30, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.10,
        terminal_growth=0.030,
        forecast_years=5,
    )
    assert fair_g25 is not None and fair_g30 is not None
    assert fair_g25 < fair_g30


def test_A4_net_debt_impact_positive_and_negative():
    """Adding $200M net_debt → per share drops by 20.
    Cash-rich -$300M net_debt → per share rises by 30."""
    fair_base, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    fair_levered, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=200.0,
        lag_status="fresh",
    )
    fair_cash_rich, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=-300.0,
        lag_status="fresh",
    )
    assert fair_base is not None and fair_levered is not None and fair_cash_rich is not None
    # net_debt subtracts from EV; per share decreases by net_debt / shares.
    assert math.isclose(fair_base - fair_levered, 200.0 / 10.0, abs_tol=1e-6)
    assert math.isclose(fair_cash_rich - fair_base, 300.0 / 10.0, abs_tol=1e-6)


# -- B. Defense #5 — terminal-g constraint -----------------------------------

def test_B1_g_at_wacc_minus_1pct_but_above_03_long_run_cap_skips():
    # terminal_growth=0.09 with WACC=0.10. Caps: min(0.03, 0.09)=0.03.
    # 0.09 > 0.03 → unsafe.
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.10,
        terminal_growth=0.09,
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "terminal_g_unsafe_g_too_close_to_wacc"


def test_B2_default_g_03_with_wacc_10_is_safe():
    # 0.03 ≤ min(0.03, 0.09) = 0.03 → safe (≤ holds, not <).
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None


def test_B3_pathological_g_above_wacc_skips():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        wacc=0.10,
        terminal_growth=0.15,
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "terminal_g_unsafe_g_too_close_to_wacc"


# -- C. Applicability gates delegated ----------------------------------------

def test_C1_financials_sector_skipped():
    fair, app = dcf_fair_price(
        sector="Financials",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "sector_excluded_financials"


def test_C2_utilities_sector_skipped():
    fair, app = dcf_fair_price(
        sector="Utilities",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "sector_excluded_utilities"


def test_C3_negative_fcf_median_skipped():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=[-50.0, -40.0, -30.0, -20.0, 100.0],  # median negative
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_fcf_5y_median"


def test_C4_none_shares_skipped():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=None,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "missing_shares_outstanding"


def test_C5_hard_stale_skipped():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="hard",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "stale_filing_hard"


# -- D. Edge cases — equity / debt --------------------------------------------

def test_D1_high_leverage_negative_equity_skipped():
    """FCF=10M, net_debt=500M: EV ~129M, equity ~-371M → skip."""
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(10.0),
        shares_outstanding=10.0,
        net_debt=500.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "dcf_negative_equity_post_debt"


def test_D2_none_net_debt_skipped():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=None,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "dcf_net_debt_unknown"


def test_D3_zero_net_debt_equity_equals_ev():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    # Per A1 reference: ~$129.27.
    assert math.isclose(fair, 129.27, abs_tol=0.05)


# -- E. Stale OK --------------------------------------------------------------

def test_E1_soft_stale_computes_normally():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="soft",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 0


def test_E2_unknown_stale_computes_normally():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="unknown",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 0


# -- F. Custom forecast_years ------------------------------------------------

def test_F1_longer_horizon_modest_change():
    """N=5 vs N=10: changes within ±20%. Stage 1 grows; Stage 2 shrinks."""
    fair_n5, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        forecast_years=5,
    )
    fair_n10, _ = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
        forecast_years=10,
    )
    assert fair_n5 is not None and fair_n10 is not None
    rel_change = abs(fair_n10 - fair_n5) / fair_n5
    assert rel_change < 0.20, (
        f"N=10 vs N=5 changed by {rel_change*100:.1f}%, expected <20%"
    )


# -- G. FCF normalization ----------------------------------------------------

def test_G1_mixed_positive_negative_uses_positives_only_median():
    """fcf_5y = [80, 90, -30, 110, 120] — gate uses median of all
    finite = 90 (passes, > 0). Normalization uses POSITIVES only =
    median(80,90,110,120) = 100. Per-share output anchors on 100, so
    output should match the A1 reference (FCF=100, ~$129.27)."""
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=[80.0, 90.0, -30.0, 110.0, 120.0],
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    assert math.isclose(fair, 129.27, abs_tol=0.05)


def test_G2_all_zero_fcf_skipped_at_gate():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=[0.0, 0.0, 0.0, 0.0, 0.0],
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_fcf_5y_median"


# -- H. Cross-method invariants ----------------------------------------------

def test_H1_returns_consistent_tuple_shape():
    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=_flat_fcf(100.0),
        shares_outstanding=10.0,
        net_debt=0.0,
        lag_status="fresh",
    )
    assert isinstance(fair, float)
    assert isinstance(app, MethodApplicability)


def test_H2_default_args_from_config():
    assert config.DISCOUNT_RATE == 0.10
    assert config.TERMINAL_GROWTH == 0.03
    assert config.DCF_FORECAST_YEARS == 5


def test_H3_module_re_exported_in_package_init():
    from compute import valuation
    assert hasattr(valuation, "dcf_fair_price")
    assert callable(valuation.dcf_fair_price)


def test_H4_new_skip_reasons_in_taxonomy():
    from compute.valuation.applicability import SKIP_REASONS
    for new_reason in (
        "terminal_g_unsafe_g_too_close_to_wacc",
        "dcf_net_debt_unknown",
        "dcf_negative_equity_post_debt",
    ):
        assert new_reason in SKIP_REASONS


# -- I. @network sanity (--run-network) --------------------------------------

@pytest.mark.network
def test_I1_aapl_dcf_real_edgar():
    """Compute DCF for AAPL using EDGAR fundamentals.

    Lenient: if all inputs available, expect applicable=True with a
    sane positive value. If applicable=False, reason must be in the
    known taxonomy (no math errors)."""
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    set_identity(os.environ["EDGAR_USER_AGENT"])

    snap = fundamentals_mod._build_snapshot("AAPL", "0000320193")
    if snap.free_cash_flow is None or snap.shares_outstanding in (None, 0):
        pytest.skip("AAPL FCF or shares missing this snapshot")

    # Use latest FCF as a flat 5y proxy (history fetch happens in Step 7).
    fcf_proxy_5y = [snap.free_cash_flow] * 5
    long_term_debt = snap.long_term_debt or 0.0
    short_term_debt = snap.short_term_debt or 0.0
    cash = snap.cash or 0.0
    net_debt = (long_term_debt + short_term_debt) - cash

    fair, app = dcf_fair_price(
        sector="Information Technology",
        fcf_5y=fcf_proxy_5y,
        shares_outstanding=snap.shares_outstanding,
        net_debt=net_debt,
        lag_status="fresh",
    )

    if app.applicable:
        assert fair is not None
        assert fair > 0
    else:
        # Must skip with a known reason, not crash.
        from compute.valuation.applicability import SKIP_REASONS
        assert app.reason in SKIP_REASONS


@pytest.mark.network
def test_I2_breadth_5_tickers_produce_dcf():
    """≥3 of 5 mature firms should produce applicable=True. For
    skips, reason must be in known taxonomy."""
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    from compute.valuation.applicability import SKIP_REASONS
    set_identity(os.environ["EDGAR_USER_AGENT"])

    tickers = {
        "KO":   "0000021344",
        "PG":   "0000080424",
        "MSFT": "0000789019",
        "JNJ":  "0000200406",
        "MMM":  "0000066740",
    }

    applicable_count = 0
    skip_log: list[tuple[str, str | None]] = []
    for ticker, cik in tickers.items():
        snap = fundamentals_mod._build_snapshot(ticker, cik)
        if snap.free_cash_flow is None or snap.shares_outstanding in (None, 0):
            skip_log.append((ticker, "missing_inputs"))
            continue
        long_term_debt = snap.long_term_debt or 0.0
        short_term_debt = snap.short_term_debt or 0.0
        cash = snap.cash or 0.0
        net_debt = (long_term_debt + short_term_debt) - cash
        fair, app = dcf_fair_price(
            sector="Consumer Staples",  # close enough for these names
            fcf_5y=[snap.free_cash_flow] * 5,
            shares_outstanding=snap.shares_outstanding,
            net_debt=net_debt,
            lag_status="fresh",
        )
        if app.applicable:
            applicable_count += 1
        else:
            skip_log.append((ticker, app.reason))
            assert app.reason in SKIP_REASONS, (
                f"{ticker} unexpected DCF reason: {app.reason}"
            )

    assert applicable_count >= 3, (
        f"Only {applicable_count}/5 tickers produced DCF; expected ≥3. "
        f"Skips: {skip_log}"
    )
