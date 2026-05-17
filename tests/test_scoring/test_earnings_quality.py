"""Unit tests for compute.scoring.earnings_quality (PR 4.5d).

Two flags:
- `accruals_momentum_high` — Δ(TATA) over 3y > +0.05
- `loss_avoidance_pattern` — 3+ years of tiny-positive NI / EPS
  (Burgstahler-Dichev 1997 kink)

All tests offline. No SEC EDGAR fetch.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.earnings_quality import (
    ACCRUALS_MOMENTUM_THRESHOLD,
    LOSS_AVOID_EPS_CEILING,
    LOSS_AVOID_MIN_CONSECUTIVE_YEARS,
    LOSS_AVOID_NI_CEILING,
    check_accruals_momentum,
    check_loss_avoidance,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 1_000.0,
        "net_income": 100.0,
        "total_assets": 2_000.0,
        "operating_cash_flow": 120.0,
        "shares_outstanding": 1_000_000.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _history(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["metric", "value", "period_end"])


# ---------------------------------------------------------------------------
# check_accruals_momentum
# ---------------------------------------------------------------------------


def test_accruals_momentum_no_snap_returns_false():
    result = check_accruals_momentum(None, None)
    assert result.fired is False
    assert result.delta_tata is None


def test_accruals_momentum_no_history_returns_false():
    snap = _snap()
    result = check_accruals_momentum(snap, None)
    assert result.fired is False
    # tata_now should be computable (uses snap only) but tata_then None.
    assert result.tata_now is not None
    assert result.tata_then is None


def test_accruals_momentum_fires_when_tata_jumps():
    # Current: TATA = (NI - CFO) / TA = (200 - 50) / 1000 = 0.15
    snap = _snap(
        net_income=200.0,
        operating_cash_flow=50.0,
        total_assets=1_000.0,
    )
    # 3y ago: TATA = (50 - 30) / 1000 = 0.02
    # ΔTATA = 0.15 - 0.02 = 0.13 > 0.05 → fires
    hist = _history(
        [
            {"metric": "net_income", "value": 50.0, "period_end": date(2022, 12, 31)},
            {"metric": "operating_cash_flow", "value": 30.0, "period_end": date(2022, 12, 31)},
            {"metric": "total_assets", "value": 1_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_accruals_momentum(snap, hist)
    assert result.fired is True
    assert result.delta_tata is not None
    assert result.delta_tata > ACCRUALS_MOMENTUM_THRESHOLD
    assert abs(result.tata_now - 0.15) < 1e-6
    assert abs(result.tata_then - 0.02) < 1e-6


def test_accruals_momentum_does_not_fire_for_stable_tata():
    # Both periods: TATA ≈ 0.02 → Δ ≈ 0 → does not fire.
    snap = _snap(
        net_income=100.0,
        operating_cash_flow=80.0,
        total_assets=1_000.0,
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 100.0, "period_end": date(2022, 12, 31)},
            {"metric": "operating_cash_flow", "value": 80.0, "period_end": date(2022, 12, 31)},
            {"metric": "total_assets", "value": 1_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_accruals_momentum(snap, hist)
    assert result.fired is False


def test_accruals_momentum_does_not_fire_when_tata_improves():
    # Current TATA lower than 3y ago — accruals IMPROVING, not deteriorating.
    snap = _snap(
        net_income=100.0,
        operating_cash_flow=120.0,  # CFO > NI = healthy
        total_assets=1_000.0,
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 200.0, "period_end": date(2022, 12, 31)},
            {"metric": "operating_cash_flow", "value": 50.0, "period_end": date(2022, 12, 31)},
            {"metric": "total_assets", "value": 1_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_accruals_momentum(snap, hist)
    assert result.fired is False
    assert result.delta_tata < 0  # Improvement = negative delta


def test_accruals_momentum_skipped_when_zero_total_assets():
    snap = _snap(total_assets=0.0)
    result = check_accruals_momentum(snap, None)
    assert result.fired is False
    assert result.tata_now is None


def test_accruals_momentum_threshold_constant():
    # Pin the threshold so a future tweak surfaces explicitly.
    assert ACCRUALS_MOMENTUM_THRESHOLD == 0.05


# ---------------------------------------------------------------------------
# check_loss_avoidance
# ---------------------------------------------------------------------------


def test_loss_avoidance_no_snap_returns_false():
    result = check_loss_avoidance(None, None)
    assert result.fired is False
    assert result.consecutive_years == 0


def test_loss_avoidance_fires_for_3_consecutive_tiny_ni_years():
    # 3 consecutive years all with NI in [$0, $5M] band.
    snap = _snap(
        net_income=2_500_000.0,
        shares_outstanding=10_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 3_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 1_000_000.0, "period_end": date(2023, 12, 31)},
            # Older year just for context
            {"metric": "net_income", "value": 4_500_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    assert result.fired is True
    assert result.consecutive_years >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS


def test_loss_avoidance_does_not_fire_for_one_year_break():
    # Current year tiny-positive, year ago LARGE loss → breaks streak
    snap = _snap(
        net_income=2_000_000.0,
        shares_outstanding=10_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 3_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": -50_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    # Streak length = 2 (2025 + 2024); breaks at 2023's loss.
    # 2 < LOSS_AVOID_MIN_CONSECUTIVE_YEARS=3 → does NOT fire
    assert result.fired is False
    assert result.consecutive_years == 2


def test_loss_avoidance_eps_band_catches_high_share_count():
    # Big NI but spread over so many shares EPS is ~$0.02 → tiny per-share
    # band catches it even though NI is way above $5M floor.
    snap = _snap(
        net_income=20_000_000.0,  # > NI ceiling
        shares_outstanding=1_000_000_000.0,  # EPS = $0.02 → tiny band
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 15_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "shares_outstanding", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 10_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "shares_outstanding", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    assert result.fired is True


def test_loss_avoidance_negative_ni_breaks_streak():
    # Tiny NEGATIVE NI is NOT in the [0, $5M] band (floor is 0).
    snap = _snap(
        net_income=-100_000.0,  # tiny but negative
        shares_outstanding=10_000_000.0,
    )
    result = check_loss_avoidance(snap, None)
    assert result.fired is False
    assert result.consecutive_years == 0


def test_loss_avoidance_large_positive_ni_breaks_streak():
    # NI = $500M is way above the absolute ceiling and EPS = $50
    # is way above the per-share ceiling.
    snap = _snap(
        net_income=500_000_000.0,
        shares_outstanding=10_000_000.0,
    )
    result = check_loss_avoidance(snap, None)
    assert result.fired is False


def test_loss_avoidance_constants():
    """Sanity-pin Burgstahler-Dichev 1997 thresholds."""
    assert LOSS_AVOID_NI_CEILING == 5_000_000.0
    assert LOSS_AVOID_EPS_CEILING == 0.05
    assert LOSS_AVOID_MIN_CONSECUTIVE_YEARS == 3
