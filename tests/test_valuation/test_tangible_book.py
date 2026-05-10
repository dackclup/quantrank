"""Unit tests for compute.valuation.tangible_book.

Cases (a)-(h) per PR-3c kickoff §3.3 — synthetic, deterministic, offline.
Case (i) is the ``@pytest.mark.network`` golden anchor against AAPL FY2024
fundamentals from SEC EDGAR. Skipped in CI by default; run on demand via
``pytest --run-network``.
"""

from __future__ import annotations

import math
import os
from datetime import date

import pytest

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.valuation.tangible_book import (
    goodwill_heavy_flag,
    tangible_book_value_per_share,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    """Minimal FundamentalsSnapshot with sensible defaults.

    Defaults yield TBVPS = (100 - 0 - 0) / 10 = 10.0 (clean balance sheet).
    Tests override goodwill/intangibles/equity/shares to exercise edges.
    """
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "stockholders_equity": 100.0,
        "shares_outstanding": 10.0,
        "goodwill": 0.0,
        "intangibles_net": 0.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


# -- (a) Synthetic baseline ---------------------------------------------------

def test_tbvps_baseline_synthetic():
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=30.0,
        intangibles_net=20.0,
        shares_outstanding=10.0,
    )
    assert tangible_book_value_per_share(snap) == 5.0


# -- (b) No goodwill, no intangibles → coerce None to 0 -----------------------

def test_tbvps_none_intangibles_coerce_to_zero():
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=None,
        intangibles_net=None,
        shares_outstanding=10.0,
    )
    assert tangible_book_value_per_share(snap) == 10.0


# -- (c) Negative tangible book → None ----------------------------------------

def test_tbvps_negative_tangible_book_returns_none():
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=80.0,
        intangibles_net=30.0,  # 80+30 > 100 → tangible book < 0
        shares_outstanding=10.0,
    )
    assert tangible_book_value_per_share(snap) is None


# -- (d) Zero shares → None ---------------------------------------------------

def test_tbvps_zero_shares_returns_none():
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=10.0,
        intangibles_net=0.0,
        shares_outstanding=0.0,
    )
    assert tangible_book_value_per_share(snap) is None


# -- (e) None equity → None ---------------------------------------------------

def test_tbvps_none_equity_returns_none():
    snap = _snap(
        stockholders_equity=None,
        goodwill=0.0,
        intangibles_net=0.0,
        shares_outstanding=10.0,
    )
    assert tangible_book_value_per_share(snap) is None


# Bonus edge: None shares → None (parallel to (d), but None vs 0)

def test_tbvps_none_shares_returns_none():
    snap = _snap(
        stockholders_equity=100.0,
        shares_outstanding=None,
    )
    assert tangible_book_value_per_share(snap) is None


# Bonus edge: tangible book = 0 exactly → None (we require strictly positive)

def test_tbvps_zero_tangible_book_returns_none():
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=60.0,
        intangibles_net=40.0,
        shares_outstanding=10.0,
    )
    assert tangible_book_value_per_share(snap) is None


# -- (f) Goodwill-heavy positive ---------------------------------------------

def test_goodwill_heavy_flag_fires_when_ratio_below_threshold():
    # equity=100, goodwill=40, intangibles=20, shares=10 →
    # BVPS_reported = 10.0; TBVPS = 4.0; ratio = 0.4 < 0.5
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=40.0,
        intangibles_net=20.0,
        shares_outstanding=10.0,
    )
    tbvps = tangible_book_value_per_share(snap)
    assert tbvps == 4.0
    assert goodwill_heavy_flag(snap, tbvps) is True


# -- (g) Goodwill-heavy negative (clean balance) ------------------------------

def test_goodwill_heavy_flag_does_not_fire_for_clean_balance_sheet():
    # equity=100, goodwill=10, intangibles=5, shares=10 →
    # BVPS_reported = 10.0; TBVPS = 8.5; ratio = 0.85 > 0.5
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=10.0,
        intangibles_net=5.0,
        shares_outstanding=10.0,
    )
    tbvps = tangible_book_value_per_share(snap)
    assert tbvps == 8.5
    assert goodwill_heavy_flag(snap, tbvps) is False


# -- (h) Goodwill-heavy edge: TBVPS=None → flag is False ---------------------

def test_goodwill_heavy_flag_false_when_tbvps_is_none():
    snap = _snap(stockholders_equity=None)
    assert goodwill_heavy_flag(snap, None) is False


# Additional defensive cases for goodwill_heavy_flag:

def test_goodwill_heavy_flag_false_when_equity_negative():
    snap = _snap(stockholders_equity=-50.0)
    # Provide a positive TBVPS to isolate the negative-equity guard.
    assert goodwill_heavy_flag(snap, 4.0) is False


def test_goodwill_heavy_flag_false_when_shares_zero():
    snap = _snap(shares_outstanding=0.0)
    assert goodwill_heavy_flag(snap, 5.0) is False


def test_goodwill_heavy_flag_at_exact_threshold_does_not_fire():
    # Strict-inequality semantics: ratio == 0.5 exactly should NOT flag.
    # equity=100, goodwill=50, intangibles=0, shares=10 →
    # BVPS_reported=10, TBVPS=5, ratio = 0.5
    snap = _snap(
        stockholders_equity=100.0,
        goodwill=50.0,
        intangibles_net=0.0,
        shares_outstanding=10.0,
    )
    tbvps = tangible_book_value_per_share(snap)
    assert tbvps == 5.0
    assert goodwill_heavy_flag(snap, tbvps) is False


# -- (i) @network golden test against real AAPL EDGAR fundamentals -----------
#
# Wide tolerance band on TBVPS because EDGAR's
# `us-gaap:IntangibleAssetsNetExcludingGoodwill` tag may resolve to
# different sub-concepts depending on AAPL's annual taxonomy choice; the
# Step 1 fallback chain handles this but the precise number can swing
# multi-billion. We assert (i) TBVPS computes to a finite positive float
# OR returns None, and (ii) the math is internally consistent (TBVPS *
# shares + goodwill + intangibles == reported equity, within rounding).

@pytest.mark.network
def test_aapl_tbvps_real_edgar():
    if not os.environ.get("EDGAR_USER_AGENT"):
        pytest.skip("EDGAR_USER_AGENT not set")

    from edgar import set_identity

    from compute.ingest import fundamentals as fundamentals_mod
    set_identity(os.environ["EDGAR_USER_AGENT"])

    snap = fundamentals_mod._build_snapshot("AAPL", "0000320193")

    # Sanity floor on prerequisites:
    assert snap.stockholders_equity is not None and snap.stockholders_equity > 0, (
        f"AAPL stockholders_equity should be a positive number; got "
        f"{snap.stockholders_equity!r}"
    )
    assert snap.shares_outstanding is not None and snap.shares_outstanding > 1e9, (
        f"AAPL shares_outstanding should be >1B; got {snap.shares_outstanding!r}"
    )
    assert snap.goodwill is not None, "Goodwill probe expected non-null for AAPL"
    # Note: snap.intangibles_net may be None for some quarters depending on
    # which fallback tag fires; we don't hard-assert it here.

    tbvps = tangible_book_value_per_share(snap)

    # Two acceptable outcomes: (1) tangible book computes positive, or
    # (2) intangibles + goodwill exceed equity → None. Both are valid
    # production behaviors; we just verify the math, not a specific value.
    if tbvps is not None:
        assert tbvps > 0.0, "TBVPS must be strictly positive when not None"
        # Internal consistency: tbvps * shares + goodwill + (intangibles or 0)
        # ≈ stockholders_equity. Allow ±1% rounding error.
        intangibles = float(snap.intangibles_net or 0.0)
        reconstructed = (
            tbvps * float(snap.shares_outstanding)
            + float(snap.goodwill)
            + intangibles
        )
        rel_err = abs(reconstructed - float(snap.stockholders_equity)) / float(
            snap.stockholders_equity
        )
        assert rel_err < 0.01, (
            f"TBVPS reconstruction mismatch: tbvps*shares+gw+intang="
            f"{reconstructed:,.0f} vs equity={snap.stockholders_equity:,.0f} "
            f"({rel_err*100:.2f}% off)"
        )
        # goodwill_heavy_flag is informational on AAPL — record but don't
        # assert (the flag's sensitivity to intangibles tagging is exactly
        # the kind of thing PR-3d UI surfaces for user judgment).
        flag = goodwill_heavy_flag(snap, tbvps)
        assert isinstance(flag, bool)
    else:
        # tbvps=None implies snap.goodwill + (snap.intangibles_net or 0)
        # >= snap.stockholders_equity. Sanity-check the arithmetic.
        intangibles = float(snap.intangibles_net or 0.0)
        assert (
            float(snap.goodwill) + intangibles
            >= float(snap.stockholders_equity)
        ), "TBVPS=None should only happen when goodwill+intangibles >= equity"


# Module-level invariant: importing the module succeeds and the public
# surface is what compute/valuation/__init__.py advertises.

def test_tangible_book_module_public_surface():
    from compute import valuation

    assert hasattr(valuation, "tangible_book_value_per_share")
    assert hasattr(valuation, "goodwill_heavy_flag")
    assert callable(valuation.tangible_book_value_per_share)
    assert callable(valuation.goodwill_heavy_flag)


def test_imports_resolve_and_constants_are_finite():
    from compute import config

    assert math.isfinite(config.GOODWILL_HEAVY_RATIO)
    assert 0.0 < config.GOODWILL_HEAVY_RATIO < 1.0
