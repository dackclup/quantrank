"""Unit tests for compute.valuation.graham.

15 cases per kickoff Step 4.2 spec:
  1-3   golden synthetic with deterministic Graham math
  4-9   per-input skip cases (EPS, TBVPS, lag_status)
  10-11 soft + unknown lag_status pass-through (Step 5 annotates)
  12    fresh + valid round-trip (parity with case 1)
  13    sqrt round-trip stability invariant
  14    @network golden against AAPL FY2024 (lenient — TBVPS may be None)
  15    @network breadth check (5 tickers — at least 3 produce values)
"""

from __future__ import annotations

import math
import os

import pytest

from compute.valuation.graham import graham_fair_price

# -- (1) Deterministic synthetic golden --------------------------------------

def test_graham_golden_synthetic_eps2_tbvps10():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=10.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert app.reason is None
    # √(22.5 × 2.0 × 10.0) = √450 = 21.21320343559643
    assert fair is not None
    assert math.isclose(fair, 21.213203435596427, abs_tol=1e-6)


# -- (2) Conservative case ---------------------------------------------------

def test_graham_conservative_eps1_tbvps5():
    fair, app = graham_fair_price(
        eps_3y_avg=1.0,
        tangible_book_value_per_share=5.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    # √(22.5 × 1.0 × 5.0) = √112.5 ≈ 10.6066017177982
    assert fair is not None
    assert math.isclose(fair, 10.606601717798213, abs_tol=1e-6)


# -- (3) Large case (high-quality compounder) --------------------------------

def test_graham_large_eps10_tbvps50():
    fair, app = graham_fair_price(
        eps_3y_avg=10.0,
        tangible_book_value_per_share=50.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    # √(22.5 × 10.0 × 50.0) = √11250 ≈ 106.06601717798213
    assert fair is not None
    assert math.isclose(fair, 106.06601717798213, abs_tol=1e-6)


# -- (4) Negative EPS skip ---------------------------------------------------

def test_graham_skips_negative_eps():
    fair, app = graham_fair_price(
        eps_3y_avg=-0.5,
        tangible_book_value_per_share=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_eps_3y_avg"


# -- (5) None EPS skip -------------------------------------------------------

def test_graham_skips_none_eps():
    fair, app = graham_fair_price(
        eps_3y_avg=None,
        tangible_book_value_per_share=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_eps_3y_avg"


# -- (6) Zero EPS skip (boundary) --------------------------------------------

def test_graham_skips_zero_eps_boundary():
    fair, app = graham_fair_price(
        eps_3y_avg=0.0,
        tangible_book_value_per_share=10.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_eps_3y_avg"


# -- (7) None TBVPS skip -----------------------------------------------------

def test_graham_skips_none_tbvps():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=None,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_or_missing_tangible_book"


# -- (8) Negative TBVPS skip -------------------------------------------------

def test_graham_skips_negative_tbvps():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=-5.0,
        lag_status="fresh",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_or_missing_tangible_book"


# -- (9) Hard stale skip -----------------------------------------------------

def test_graham_skips_hard_stale_filing():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=10.0,
        lag_status="hard",
    )
    assert fair is None
    assert app.applicable is False
    assert app.reason == "stale_filing_hard"


# -- (10) Soft stale OK (Step 5 annotates separately) ------------------------

def test_graham_computes_under_soft_stale():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=10.0,
        lag_status="soft",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 0


# -- (11) Unknown stale OK ---------------------------------------------------

def test_graham_computes_under_unknown_stale():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=10.0,
        lag_status="unknown",
    )
    assert app.applicable is True
    assert fair is not None
    assert fair > 0


# -- (12) Fresh + valid (parity with case 1) ---------------------------------

def test_graham_fresh_valid_returns_applicable_true():
    fair, app = graham_fair_price(
        eps_3y_avg=2.0,
        tangible_book_value_per_share=10.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert app.reason is None
    assert fair is not None
    assert fair > 0


# -- (13) Internal consistency: sqrt round-trip stability --------------------

def test_graham_sqrt_round_trip_stable():
    eps = 2.5
    tbvps = 12.345
    fair, app = graham_fair_price(
        eps_3y_avg=eps,
        tangible_book_value_per_share=tbvps,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    expected_product = 22.5 * eps * tbvps
    # fair**2 should equal product within float tolerance
    assert math.isclose(fair * fair, expected_product, rel_tol=1e-9)


# Bonus: verify the ratio-invariant fair / sqrt(eps * tbvps) ≈ sqrt(22.5)

def test_graham_multiplier_ratio_invariant():
    """fair / sqrt(eps * tbvps) ≈ √22.5 ≈ 4.7434"""
    fair, app = graham_fair_price(
        eps_3y_avg=4.0,
        tangible_book_value_per_share=25.0,
        lag_status="fresh",
    )
    assert app.applicable is True
    assert fair is not None
    ratio = fair / math.sqrt(4.0 * 25.0)
    assert math.isclose(ratio, math.sqrt(22.5), rel_tol=1e-9)


# Bonus: invalid input states crashes (None for both)

def test_graham_skips_when_both_inputs_none():
    fair, app = graham_fair_price(
        eps_3y_avg=None,
        tangible_book_value_per_share=None,
        lag_status="fresh",
    )
    # Applicability checks EPS first, so we expect the EPS reason.
    assert fair is None
    assert app.applicable is False
    assert app.reason == "non_positive_eps_3y_avg"


# -- (14) @network golden against AAPL FY2024 EDGAR --------------------------
#
# Lenient assertion (per Step 3 pattern): if AAPL TBVPS computes to a
# positive value, Graham must produce a sane positive fair price; if
# TBVPS is None (intangibles + goodwill exceed equity given AAPL's
# tagging), applicability must skip with the tangible-book reason.
# Both branches are valid production behaviors.

@pytest.mark.network
def test_graham_aapl_real_edgar():
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    from compute.valuation.tangible_book import tangible_book_value_per_share
    set_identity(os.environ["EDGAR_USER_AGENT"])

    snap = fundamentals_mod._build_snapshot("AAPL", "0000320193")
    tbvps = tangible_book_value_per_share(snap)

    # Estimate EPS_3y_avg. Without history fetched we approximate with
    # eps_diluted; the test's purpose is to exercise the function on real
    # EDGAR-derived inputs, not to lock a specific Graham value.
    eps_proxy = snap.eps_diluted

    # Pick a fresh lag (we don't know exact lag without computing it).
    fair, app = graham_fair_price(
        eps_3y_avg=eps_proxy,
        tangible_book_value_per_share=tbvps,
        lag_status="fresh",
    )

    if tbvps is None:
        # AAPL's intangibles tagging put TBVPS in the negative branch.
        assert fair is None
        assert app.applicable is False
        assert app.reason == "non_positive_or_missing_tangible_book"
        return

    if eps_proxy is None or eps_proxy <= 0:
        assert fair is None
        assert app.applicable is False
        assert app.reason == "non_positive_eps_3y_avg"
        return

    # Both inputs positive — Graham must compute.
    assert app.applicable is True
    assert fair is not None
    assert fair > 0
    # Internal consistency: fair² ≈ 22.5 × eps × tbvps within 1e-9
    assert math.isclose(
        fair * fair, 22.5 * float(eps_proxy) * float(tbvps), rel_tol=1e-9
    )


# -- (15) @network breadth check across 5 reference tickers ------------------

@pytest.mark.network
def test_graham_breadth_5_tickers():
    """Verify graham_fair_price returns a positive value for ≥3 of 5
    reference tickers. Acknowledges some may have negative TBVPS due to
    heavy-buyback-into-deficit balance sheets (e.g., AZO-style)."""
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    from compute.valuation.tangible_book import tangible_book_value_per_share
    set_identity(os.environ["EDGAR_USER_AGENT"])

    tickers = {
        "KO":   "0000021344",  # Coca-Cola, Consumer Staples
        "PG":   "0000080424",  # Procter & Gamble, Consumer Staples
        "MSFT": "0000789019",  # Microsoft, IT
        "JNJ":  "0000200406",  # Johnson & Johnson, Health Care
        "MMM":  "0000066740",  # 3M, Industrials
    }

    positive_count = 0
    skip_reasons: list[tuple[str, str | None]] = []
    for ticker, cik in tickers.items():
        snap = fundamentals_mod._build_snapshot(ticker, cik)
        tbvps = tangible_book_value_per_share(snap)
        eps_proxy = snap.eps_diluted

        fair, app = graham_fair_price(
            eps_3y_avg=eps_proxy,
            tangible_book_value_per_share=tbvps,
            lag_status="fresh",
        )
        if app.applicable and fair is not None and fair > 0:
            positive_count += 1
        else:
            skip_reasons.append((ticker, app.reason))

    assert positive_count >= 3, (
        f"Graham produced positive values for {positive_count}/5 tickers; "
        f"expected at least 3. Skip reasons: {skip_reasons}"
    )


# Module-level public-surface invariant ---------------------------------------

def test_graham_module_exposed_in_package_init():
    from compute import valuation

    assert hasattr(valuation, "graham_fair_price")
    assert callable(valuation.graham_fair_price)
