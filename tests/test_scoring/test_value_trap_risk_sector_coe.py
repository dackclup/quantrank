"""Tests for sector-adjusted cost of equity in the RIM value_trap_risk gate.

Covers:
- USE_SECTOR_COE=False (default): rim_fair_price behaves identically to baseline
- USE_SECTOR_COE=True (sim): cyclical-sector ticker with 3y-mean ROE between
  the flat 10% and a higher sector Ke is still FLAGGED (not a false-negative
  regression) — the flag should PERSIST for genuinely low-ROE tickers
- The only change under sector CoE is for tickers whose ROE sits *above*
  the sector Ke but *below* the flat 10% (e.g., Utilities ROE 8% vs Ke 6%)
- Sanity: a Utilities ticker with ROE > sector Ke (6%) but < flat 10% is
  UN-flagged under sector CoE (the target FP reduction from issue #67)
"""

from __future__ import annotations

import pytest

from compute.scoring.cost_of_equity import get_cost_of_equity
from compute.valuation.applicability import LagStatus, check_rim_applicability

# ---------------------------------------------------------------------------
# Helper — canonical LagStatus for tests (not stale)
# ---------------------------------------------------------------------------
_FRESH: LagStatus = "current"
_HARD_STALE: LagStatus = "hard"


# ---------------------------------------------------------------------------
# Baseline (flat CoE = 0.10)
# ---------------------------------------------------------------------------

def test_value_trap_fires_flat_coe_roe_below_threshold() -> None:
    """ROE 8% < flat 10% Ke → value_trap_risk fires under flat CoE."""
    result = check_rim_applicability(
        avg_3y_roe=0.08,
        tbvps=20.0,
        lag_status=_FRESH,
        cost_of_equity=0.10,
    )
    assert not result.applicable
    assert result.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_value_trap_does_not_fire_flat_coe_roe_above_threshold() -> None:
    """ROE 12% > flat 10% Ke → RIM is applicable under flat CoE."""
    result = check_rim_applicability(
        avg_3y_roe=0.12,
        tbvps=20.0,
        lag_status=_FRESH,
        cost_of_equity=0.10,
    )
    assert result.applicable


# ---------------------------------------------------------------------------
# Sector-CoE paths — Utilities (Ke = 6%)
# ---------------------------------------------------------------------------

def test_utilities_roe_above_sector_ke_unflagged() -> None:
    """Utilities ticker: ROE 8% > sector Ke 6% → no value_trap under sector CoE.

    This is the canonical FP-reduction case from issue #67 — a Utilities
    company with ROE between 6% and 10% was incorrectly flagged by the flat
    threshold. The sector-aware path should clear it.
    """
    utilities_ke = get_cost_of_equity("Utilities")
    assert utilities_ke == pytest.approx(0.06, abs=1e-9)
    result = check_rim_applicability(
        avg_3y_roe=0.08,   # above 6%, below flat 10%
        tbvps=30.0,
        lag_status=_FRESH,
        cost_of_equity=utilities_ke,
    )
    assert result.applicable, (
        "Utilities ticker with ROE 8% should NOT be value_trap under sector Ke 6%"
    )


def test_utilities_roe_below_sector_ke_still_flagged() -> None:
    """Utilities ticker: ROE 4% < sector Ke 6% → still value_trap under sector CoE."""
    utilities_ke = get_cost_of_equity("Utilities")
    result = check_rim_applicability(
        avg_3y_roe=0.04,
        tbvps=30.0,
        lag_status=_FRESH,
        cost_of_equity=utilities_ke,
    )
    assert not result.applicable
    assert result.reason == "value_trap_risk_roe_below_cost_of_equity"


# ---------------------------------------------------------------------------
# Sector-CoE paths — Energy (Ke = 12%)
# ---------------------------------------------------------------------------

def test_energy_roe_above_flat_but_below_sector_ke_flagged() -> None:
    """Energy ticker: ROE 11% > flat 10% but < sector Ke 12% → value_trap
    under sector CoE.

    This is the canonical TRUE-POSITIVE preservation case — a cyclical energy
    company with ROE 11% might appear clean under flat 10%, but energy's
    actual cost of capital (12%) correctly flags it as a value trap.
    This test guards against false-negative regression when USE_SECTOR_COE
    is flipped.
    """
    energy_ke = get_cost_of_equity("Energy")
    assert energy_ke == pytest.approx(0.12, abs=1e-9)
    result = check_rim_applicability(
        avg_3y_roe=0.11,   # above flat 10% but below Energy Ke 12%
        tbvps=25.0,
        lag_status=_FRESH,
        cost_of_equity=energy_ke,
    )
    assert not result.applicable
    assert result.reason == "value_trap_risk_roe_below_cost_of_equity"


def test_energy_roe_above_sector_ke_unflagged() -> None:
    """Energy ticker: ROE 15% > sector Ke 12% → RIM applicable under sector CoE."""
    energy_ke = get_cost_of_equity("Energy")
    result = check_rim_applicability(
        avg_3y_roe=0.15,
        tbvps=25.0,
        lag_status=_FRESH,
        cost_of_equity=energy_ke,
    )
    assert result.applicable


# ---------------------------------------------------------------------------
# Sanity — flag-off behavior (USE_SECTOR_COE=False default path)
# ---------------------------------------------------------------------------

def test_use_sector_coe_default_post_issue_67_flip() -> None:
    """Issue #67 (2026-05-28) — `USE_SECTOR_COE` flipped True after
    methodology-scientist Mode B verdict + cron #69 empirical
    confirmation (132 → 109 within target [80, 110] band).

    Pre-flip: this test asserted `not config.USE_SECTOR_COE` (data-
    collection-only default). Post-flip: assert it IS True so that an
    accidental revert surfaces as a test failure.

    The flat-CoE path remains accessible via direct
    `check_rim_applicability(..., cost_of_equity=config.COST_OF_EQUITY)`
    call — this test verifies that path still computes correctly,
    independent of the new production default. Flipping the flag back
    requires a separate methodology-scientist verdict; this assertion
    is the regression guard against silent reverts.
    """
    from compute import config  # noqa: PLC0415

    assert config.USE_SECTOR_COE, (
        "USE_SECTOR_COE flipped True 2026-05-28 (Issue #67 closure per "
        "methodology-scientist Mode B); flipping back requires a separate "
        "methodology-scientist verdict — this is a load-bearing default."
    )
    # Verify the flat path still computes the same answer when called
    # explicitly (used by the writer-side dual-counter pass that emits
    # `value_trap_risk_count_without_sector_coe` as monitoring baseline).
    result_flat = check_rim_applicability(
        avg_3y_roe=0.09,
        tbvps=15.0,
        lag_status=_FRESH,
        cost_of_equity=config.COST_OF_EQUITY,
    )
    assert not result_flat.applicable
    assert result_flat.reason == "value_trap_risk_roe_below_cost_of_equity"


# ---------------------------------------------------------------------------
# Hard-stale short-circuit — sector CoE doesn't affect stale-filing guard
# ---------------------------------------------------------------------------

def test_hard_stale_overrides_sector_coe_roe_check() -> None:
    """Hard-stale filing skips RIM regardless of ROE vs sector CoE."""
    result = check_rim_applicability(
        avg_3y_roe=0.20,   # high ROE — would pass any CoE gate
        tbvps=50.0,
        lag_status=_HARD_STALE,
        cost_of_equity=get_cost_of_equity("Utilities"),
    )
    assert not result.applicable
    assert result.reason == "stale_filing_hard"
