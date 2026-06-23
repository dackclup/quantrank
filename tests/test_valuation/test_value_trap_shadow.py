"""Tests for the value_trap_risk two-factor shadow gate (0.10.32-phase8pilot).

Verifies the SHADOW gate logic and confirms live ``value_trap_risk`` warning
behaviour is UNCHANGED.

Coverage targets
----------------
S1  loss-making / undefined-P/E firm does NOT count toward shadow gate
S2  cheap-P/E (below sector median) + below-hurdle ROE → shadow gate fires
S3  below-hurdle ROE but P/E ABOVE sector median → shadow gate does NOT fire
S4  live ``value_trap_risk`` warning still emits on old single-leg condition
    regardless of the shadow gate (P/E position does not affect live warning)

Design notes
------------
The shadow gate is computed inline in compute/main.py's per-ticker loop.  We
test the constituent decision rules directly using the public functions that
the loop calls:

- ``check_rim_applicability`` (applicability.py) verifies the ROE≤Ke condition.
- ``compute_fair_price_ensemble`` (ensemble.py) verifies the live warning path.

The shadow counter arithmetic (condition a AND b AND c) is validated by
constructing synthetic inputs and running the same boolean algebra the
main.py loop uses — without importing main.py (which would pull in the
full compute pipeline and requires network mocks).
"""

from __future__ import annotations

import statistics
from datetime import date

import pytest

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.cost_of_equity import get_cost_of_equity
from compute.valuation.applicability import check_rim_applicability
from compute.valuation.ensemble import compute_fair_price_ensemble

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _snap(
    *,
    net_income: float | None = 100_000_000.0,
    stockholders_equity: float | None = 500_000_000.0,
    shares_outstanding: float | None = 10_000_000.0,
    revenue: float | None = 1_000_000_000.0,
    total_assets: float | None = 2_000_000_000.0,
    total_liabilities: float | None = 1_500_000_000.0,
    goodwill: float | None = 0.0,
    intangibles_net: float | None = 0.0,
) -> FundamentalsSnapshot:
    """Build a minimal FundamentalsSnapshot for shadow gate tests."""
    return FundamentalsSnapshot(
        ticker="TEST",
        cik="0000000001",
        net_income=net_income,
        stockholders_equity=stockholders_equity,
        shares_outstanding=shares_outstanding,
        revenue=revenue,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        goodwill=goodwill,
        intangibles_net=intangibles_net,
        # Set explicit stale dates to avoid None-lag short-circuit.
        latest_filed_date=date(2025, 3, 1),
        latest_period_end=date(2025, 3, 1),
    )


def _shadow_gate_fires(
    *,
    snap: FundamentalsSnapshot,
    avg_3y_roe: float | None,
    current_price: float,
    sector: str,
    sector_pe_values: list[float],
) -> bool:
    """Replicate the main.py shadow gate boolean for a single ticker.

    Returns True iff ALL three legs fire:
      (a) rim_applicability fires value_trap_risk_roe_below_cost_of_equity
      (b) eps_ttm > 0  (loss-making / pre-revenue = EXEMPT, returns False)
      (c) ticker P/E < median(sector_pe_values)
    """
    ke = get_cost_of_equity(sector)
    rim_result = check_rim_applicability(
        avg_3y_roe=avg_3y_roe,
        tbvps=None,   # tbvps check comes later in the gate, irrelevant here
        lag_status="fresh",
        cost_of_equity=ke,
    )
    # Leg (a): ROE≤Ke skip must fire.
    if rim_result.reason != "value_trap_risk_roe_below_cost_of_equity":
        return False

    # Leg (b): eps_ttm > 0 (loss-making firms are EXEMPT).
    if (
        snap.net_income is None
        or snap.shares_outstanding is None
        or snap.shares_outstanding <= 0
        or snap.net_income <= 0
    ):
        return False  # loss-making or undefined P/E → EXEMPT
    eps_ttm = snap.net_income / snap.shares_outstanding
    if eps_ttm <= 0:
        return False

    if current_price <= 0:
        return False
    pe_ttm = current_price / eps_ttm

    # Leg (c): ticker P/E must be below sector-peer median.
    if not sector_pe_values:
        return False
    sector_median_pe = statistics.median(sector_pe_values)
    return pe_ttm < sector_median_pe


# ---------------------------------------------------------------------------
# S1 — loss-making / undefined-P/E firm is EXEMPT
# ---------------------------------------------------------------------------

class TestS1LossMakingExempt:
    """Loss-making firms (net_income ≤ 0) must NOT count toward the shadow gate
    even when ROE≤Ke fires and the computed P/E would be below the sector median."""

    def test_negative_net_income_exempt(self):
        """Firm with NI < 0 is loss-making: eps_ttm ≤ 0 → shadow gate DOES NOT fire."""
        snap = _snap(net_income=-50_000_000.0)
        # avg_3y_roe is None but that's not the test point; we use a positive
        # ROE below Ke to satisfy leg (a) via a synthetic value.
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.02,          # ROE=2% < Ke (~9-10%) → leg (a) fires
            current_price=100.0,
            sector="Information Technology",
            sector_pe_values=[20.0, 25.0, 30.0],  # sector median 25×
        )
        assert not fires, "Loss-making firm (NI < 0) must be EXEMPT from shadow gate"

    def test_zero_net_income_exempt(self):
        """Firm with NI == 0 has undefined P/E: shadow gate DOES NOT fire."""
        snap = _snap(net_income=0.0)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.02,
            current_price=100.0,
            sector="Information Technology",
            sector_pe_values=[20.0, 25.0, 30.0],
        )
        assert not fires, "Zero-earnings firm (undefined P/E) must be EXEMPT"

    def test_none_net_income_exempt(self):
        """Firm with NI = None has no P/E: shadow gate DOES NOT fire."""
        snap = _snap(net_income=None)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.02,
            current_price=100.0,
            sector="Information Technology",
            sector_pe_values=[20.0, 25.0, 30.0],
        )
        assert not fires, "Firm with no NI data (undefined P/E) must be EXEMPT"

    def test_none_shares_outstanding_exempt(self):
        """Firm with shares_outstanding = None has no eps_ttm: shadow gate DOES NOT fire."""
        snap = _snap(net_income=100_000_000.0, shares_outstanding=None)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.02,
            current_price=100.0,
            sector="Information Technology",
            sector_pe_values=[20.0, 25.0, 30.0],
        )
        assert not fires, "Firm with no shares data (undefined P/E) must be EXEMPT"


# ---------------------------------------------------------------------------
# S2 — cheap P/E + below-hurdle ROE → shadow gate fires
# ---------------------------------------------------------------------------

class TestS2CheapPEFires:
    """Firm with ROE≤Ke AND P/E below sector median: shadow gate MUST fire."""

    def test_below_hurdle_roe_cheap_pe_fires(self):
        """Classic value-trap: sub-hurdle ROE + stock priced below peer median.
        Shadow gate fires (two-factor condition satisfied)."""
        # NI=50M, shares=10M → eps_ttm=5.0. At price=$50: P/E=10×.
        # Sector median = 20× → P/E is CHEAP relative to sector.
        snap = _snap(net_income=50_000_000.0, shares_outstanding=10_000_000.0)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.03,          # ROE=3% < Ke (~9%) for IT → leg (a) fires
            current_price=50.0,       # P/E = $50 / $5 = 10×
            sector="Information Technology",
            sector_pe_values=[18.0, 20.0, 22.0],  # sector median 20×
        )
        assert fires, (
            "Below-hurdle ROE + P/E below sector median must fire the shadow gate"
        )

    def test_fires_with_exact_boundary_below(self):
        """P/E strictly below (not equal to) sector median: fires."""
        snap = _snap(net_income=100_000_000.0, shares_outstanding=10_000_000.0)
        # eps_ttm = 10.0; at price=190: P/E = 19×; sector median = 20× (P/E < median)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.04,
            current_price=190.0,      # P/E = 19×
            sector="Utilities",       # sector Ke < 10% so even 4% may be ≤ Ke
            sector_pe_values=[20.0, 20.0, 20.0],  # sector median exactly 20×
        )
        # Verify sector Ke makes ROE≤Ke true for this sector.
        ke = get_cost_of_equity("Utilities")
        if 0.04 > ke:
            pytest.skip(f"Utilities Ke ({ke:.3f}) > 0.04 — leg (a) doesn't fire")
        assert fires, "P/E strictly below sector median (19× < 20×) must fire"


# ---------------------------------------------------------------------------
# S3 — below-hurdle ROE but P/E ABOVE sector median → shadow gate does NOT fire
# ---------------------------------------------------------------------------

class TestS3AboveSectorMedianDoesNotFire:
    """Firm with ROE≤Ke but premium P/E vs sector peers: shadow gate must NOT fire.
    This is the growth-company case: market prices future ROE expansion."""

    def test_below_hurdle_roe_expensive_pe_does_not_fire(self):
        """ROE≤Ke + P/E ABOVE sector median: shadow gate must NOT fire."""
        # eps_ttm = 5.0; at price=$150: P/E = 30×; sector median = 20×
        snap = _snap(net_income=50_000_000.0, shares_outstanding=10_000_000.0)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.03,          # ROE=3% < Ke → leg (a) fires
            current_price=150.0,      # P/E = $150 / $5 = 30×
            sector="Information Technology",
            sector_pe_values=[18.0, 20.0, 22.0],  # sector median 20×
        )
        assert not fires, (
            "Below-hurdle ROE but P/E above sector median must NOT fire the shadow gate "
            "(growth-company exemption: market prices future ROE expansion)"
        )

    def test_exactly_at_sector_median_does_not_fire(self):
        """P/E exactly equal to sector median (not strictly below): does NOT fire."""
        # eps_ttm = 5.0; at price=$100: P/E = 20×; sector median = 20×
        snap = _snap(net_income=50_000_000.0, shares_outstanding=10_000_000.0)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.03,
            current_price=100.0,      # P/E = 20× exactly
            sector="Information Technology",
            sector_pe_values=[18.0, 20.0, 22.0],  # median = 20×
        )
        assert not fires, (
            "P/E equal to sector median (not strictly below) must NOT fire shadow gate"
        )

    def test_no_sector_peers_does_not_fire(self):
        """When there are no sector P/E values, leg (c) cannot evaluate: does NOT fire."""
        snap = _snap(net_income=50_000_000.0)
        fires = _shadow_gate_fires(
            snap=snap,
            avg_3y_roe=0.03,
            current_price=50.0,
            sector="Information Technology",
            sector_pe_values=[],          # no peers → leg (c) cannot fire
        )
        assert not fires, "Shadow gate must NOT fire when no sector peer P/E values exist"


# ---------------------------------------------------------------------------
# S4 — live value_trap_risk warning still emits on old single-leg condition
# ---------------------------------------------------------------------------

class TestS4LiveWarningUnchanged:
    """The LIVE ``value_trap_risk`` warning must continue to emit whenever the
    Penman 2013 ROE≤Ke condition fires — regardless of P/E position.  The
    shadow gate DOES NOT gate the live warning.

    These tests exercise the full ``compute_fair_price_ensemble`` path to
    confirm the live ``valuation_warnings`` emission is byte-identical to
    pre-0.10.32 behaviour.
    """

    def _minimal_peer_panels(self) -> dict:
        return {"pe": {}, "pb": {}, "ev_ebitda": {}}

    def _minimal_universe_metrics(self, ticker: str) -> dict:
        return {ticker: {"pe_ttm": None, "pb_reported": None, "ev_ebitda_ttm": None}}

    def _minimal_historical_metrics(
        self,
        ticker: str,
        avg_3y_roe: float | None,
    ) -> dict:
        return {ticker: {"eps_3y_avg": None, "avg_3y_roe": avg_3y_roe, "fcf_5y": []}}

    def _run_ensemble(self, snap: FundamentalsSnapshot, avg_3y_roe: float | None) -> list[str]:
        """Return valuation_warnings from compute_fair_price_ensemble."""
        ticker = snap.ticker
        result, _ = compute_fair_price_ensemble(
            ticker=ticker,
            snap=snap,
            sector="Information Technology",
            sub_industry=None,
            industry=None,
            current_price=100.0,
            filing_lag_days_value=10,
            peer_panels=self._minimal_peer_panels(),
            universe_metrics=self._minimal_universe_metrics(ticker),
            historical_metrics=self._minimal_historical_metrics(ticker, avg_3y_roe),
        )
        return list(result.valuation_warnings)

    def test_live_warning_emits_when_roe_below_ke(self):
        """``value_trap_risk`` must appear in valuation_warnings when ROE≤Ke fires,
        even for a ticker whose P/E would be ABOVE the sector median (shadow exempt)."""
        snap = _snap(
            net_income=50_000_000.0,    # positive → P/E defined
            shares_outstanding=10_000_000.0,
            stockholders_equity=1_000_000_000.0,
        )
        # avg_3y_roe = 2% — well below any sector Ke, so ROE≤Ke fires.
        warnings = self._run_ensemble(snap, avg_3y_roe=0.02)
        assert "value_trap_risk" in warnings, (
            "Live value_trap_risk warning must emit when ROE≤Ke fires "
            "(regardless of P/E vs sector median)"
        )

    def test_live_warning_emits_on_loss_making_firm_when_roe_below_ke(self):
        """For a loss-making firm (net_income < 0), the live warning still emits
        when ROE≤Ke fires.  The shadow gate exempts loss-makers; the LIVE gate
        does not (it depends only on avg_3y_roe, not on current-period NI)."""
        # avg_3y_roe: even with current NI < 0, historical 3y average may still
        # be positive but below Ke.  Use 1% to ensure ROE≤Ke fires.
        snap = _snap(
            net_income=-10_000_000.0,  # current period loss
            shares_outstanding=10_000_000.0,
            stockholders_equity=500_000_000.0,
        )
        warnings = self._run_ensemble(snap, avg_3y_roe=0.01)
        assert "value_trap_risk" in warnings, (
            "Live value_trap_risk must still emit for loss-making firms when ROE≤Ke fires"
        )

    def test_live_warning_absent_when_roe_above_ke(self):
        """``value_trap_risk`` must NOT appear when ROE > Ke (RIM is applicable)."""
        snap = _snap(
            net_income=1_000_000_000.0,    # very high NI → high ROE
            shares_outstanding=10_000_000.0,
            stockholders_equity=500_000_000.0,
            goodwill=0.0,
            intangibles_net=0.0,
        )
        # avg_3y_roe = 30% — well above any sector Ke → RIM runs, no skip.
        warnings = self._run_ensemble(snap, avg_3y_roe=0.30)
        assert "value_trap_risk" not in warnings, (
            "value_trap_risk must NOT appear when ROE > Ke (no value-trap signal)"
        )

    def test_live_warning_absent_for_insufficient_history(self):
        """``value_trap_risk`` must NOT appear when avg_3y_roe is None (Issue #11).
        The RIM skips under insufficient_history_for_roe — that is not a value trap."""
        snap = _snap(stockholders_equity=500_000_000.0)
        warnings = self._run_ensemble(snap, avg_3y_roe=None)
        assert "value_trap_risk" not in warnings, (
            "value_trap_risk must NOT emit for insufficient ROE history (Issue #11 fix)"
        )
