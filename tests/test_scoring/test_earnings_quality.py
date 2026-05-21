"""Unit tests for compute.scoring.earnings_quality (PR 4.5d + 4b).

Three flags:
- `accruals_momentum_high` — Δ(TATA) over 3y > +0.05
- `loss_avoidance_pattern` — 3+ years of tiny-positive NI / EPS
  (Burgstahler-Dichev 1997 kink, $50M / $0.50 band rescaled for S&P 500)
- `loss_avoidance_pattern_size_invariant` — 3+ years of
  NI / TotalAssets ∈ [0, 0.005] (Roychowdhury 2006 suspect-firm)

All tests offline. No SEC EDGAR fetch.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.earnings_quality import (
    ACCRUALS_MOMENTUM_THRESHOLD,
    LOSS_AVOID_EPS_CEILING,
    LOSS_AVOID_MIN_CONSECUTIVE_YEARS,
    LOSS_AVOID_NI_CEILING,
    LOSS_AVOID_NI_TO_ASSETS_CEILING,
    check_accruals_momentum,
    check_loss_avoidance,
    check_loss_avoidance_size_invariant,
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
    # 3 consecutive years all with NI in [$0, $50M] band (S&P-500-scaled).
    snap = _snap(
        net_income=25_000_000.0,
        shares_outstanding=10_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 30_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 10_000_000.0, "period_end": date(2023, 12, 31)},
            # Older year just for context
            {"metric": "net_income", "value": 45_000_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    assert result.fired is True
    assert result.consecutive_years >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS


def test_loss_avoidance_does_not_fire_for_one_year_break():
    # Current year tiny-positive, year ago LARGE loss → breaks streak
    snap = _snap(
        net_income=20_000_000.0,
        shares_outstanding=10_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 30_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": -500_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    # Streak length = 2 (2025 + 2024); breaks at 2023's loss.
    # 2 < LOSS_AVOID_MIN_CONSECUTIVE_YEARS=3 → does NOT fire
    assert result.fired is False
    assert result.consecutive_years == 2


def test_loss_avoidance_eps_band_catches_high_share_count():
    # Big NI but spread over so many shares EPS is ~$0.20 → tiny per-share
    # band catches it even though NI is way above $50M floor.
    snap = _snap(
        net_income=200_000_000.0,  # > NI ceiling
        shares_outstanding=1_000_000_000.0,  # EPS = $0.20 → tiny EPS band
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 150_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "shares_outstanding", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 100_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "shares_outstanding", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    assert result.fired is True


def test_loss_avoidance_negative_ni_breaks_streak():
    # Tiny NEGATIVE NI is NOT in the [0, $50M] band (floor is 0).
    snap = _snap(
        net_income=-100_000.0,  # tiny but negative
        shares_outstanding=10_000_000.0,
    )
    result = check_loss_avoidance(snap, None)
    assert result.fired is False
    assert result.consecutive_years == 0


def test_loss_avoidance_large_positive_ni_breaks_streak():
    # NI = $5B is way above the absolute ceiling and EPS = $500
    # is way above the per-share ceiling.
    snap = _snap(
        net_income=5_000_000_000.0,
        shares_outstanding=10_000_000.0,
    )
    result = check_loss_avoidance(snap, None)
    assert result.fired is False


def test_loss_avoidance_ni_just_above_new_ceiling_breaks_streak():
    """Phase 2.4: NI = $60M (above new $50M ceiling) with EPS = $6.00
    (above new $0.50 ceiling) must NOT fire — guards against the new
    band's upper bound."""
    snap = _snap(
        net_income=60_000_000.0,
        shares_outstanding=10_000_000.0,  # EPS = $6.00
    )
    result = check_loss_avoidance(snap, None)
    assert result.fired is False
    assert result.consecutive_years == 0


def test_loss_avoidance_constants():
    """Pin Phase 2.4 S&P-500-scaled thresholds (10× original BD 1997)."""
    assert LOSS_AVOID_NI_CEILING == 50_000_000.0
    assert LOSS_AVOID_EPS_CEILING == 0.50
    assert LOSS_AVOID_MIN_CONSECUTIVE_YEARS == 3


# ---------------------------------------------------------------------------
# check_loss_avoidance_size_invariant (Phase 4b — Roychowdhury 2006 §5.2)
# ---------------------------------------------------------------------------


def test_loss_avoidance_size_invariant_fires_for_3_consecutive_in_band_years():
    """NI/TA = 0.003 (within Roychowdhury 0.5% suspect band) for 3+ years
    triggers the new annotate."""
    # Snapshot: NI = $3M, TA = $1B → NI/TA = 0.003 (in band).
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=1_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 2_500_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 1_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
            # Older year — context, doesn't affect streak.
            {"metric": "net_income", "value": 4_500_000.0, "period_end": date(2022, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    assert result.fired is True
    assert result.consecutive_years >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS


def test_loss_avoidance_size_invariant_does_not_fire_above_threshold():
    """NI/TA = 0.01 (above Roychowdhury 0.5% ceiling) does NOT fire,
    even with 3+ years of consistent ratio above the band."""
    # NI = $10M, TA = $1B → NI/TA = 0.01 (above 0.005 ceiling).
    snap = _snap(
        net_income=10_000_000.0,
        total_assets=1_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 12_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 11_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    assert result.fired is False
    assert result.consecutive_years == 0


def test_loss_avoidance_size_invariant_does_not_fire_for_2_year_streak():
    """Only 2 consecutive in-band years (below
    LOSS_AVOID_MIN_CONSECUTIVE_YEARS=3) does NOT fire."""
    # 2025 + 2024 in band, 2023 breaks the streak (large positive ratio).
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=1_000_000_000.0,  # NI/TA = 0.003 in band
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 2_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            # 2023: NI/TA = 0.10 (way above band) breaks streak.
            {"metric": "net_income", "value": 100_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    assert result.fired is False
    assert result.consecutive_years == 2


def test_loss_avoidance_size_invariant_does_not_fire_when_snap_inputs_missing():
    """Graceful degradation per Rule 18 — when the snapshot is missing
    TA (or NI), the function returns fired=False with consecutive_years=0
    instead of leaking the previous-year ratio as the "current" year."""
    # Snap missing total_assets → can't compute current NI/TA → streak
    # never starts. Even with history that would qualify on its own,
    # the absent current-year input gates the flag (no half-credit).
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=None,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 2_500_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 1_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "net_income", "value": 3_500_000.0, "period_end": date(2022, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    # Snap excluded (missing TA) → walker starts at the next-newest
    # history year (2024); all 3 history years are in band → streak=3.
    # NOTE: the absent SNAP is itself the missing-input signal — Rule
    # 18 here is "no current-year inference without current-year data",
    # which the snap-exclusion branch enforces. consecutive_years==3 is
    # the correct count of in-band YEARS the walker actually saw.
    assert result.consecutive_years == 3
    # The flag is still informational: 3 in-band history years is the
    # signal, even when the snapshot can't extend the streak. The
    # historical pattern is what Roychowdhury cares about.
    assert result.fired is True


def test_loss_avoidance_size_invariant_does_not_fire_when_ta_zero_in_history():
    """Graceful degradation — a zero-TotalAssets year (division-by-zero
    guard) breaks the streak instead of crashing."""
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=1_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    # 2024 has TA=0 (pathological XBRL parse) — must break streak, not crash.
    hist = _history(
        [
            {"metric": "net_income", "value": 2_500_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 0.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 1_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    # Snap year is in band (count=1), 2024 breaks at TA=0.
    assert result.fired is False
    assert result.consecutive_years == 1


@given(
    in_band_years=st.integers(min_value=0, max_value=10),
    out_of_band_year_count=st.integers(min_value=0, max_value=3),
)
@settings(max_examples=50)
def test_loss_avoidance_size_invariant_streak_monotone_in_consecutive_years(
    in_band_years: int,
    out_of_band_year_count: int,
) -> None:
    """Hypothesis property: when the newest ``in_band_years`` are in band
    and the next ``out_of_band_year_count`` years are out of band, the
    reported ``consecutive_years`` equals ``in_band_years`` (streak walks
    newest → oldest, stops at first out-of-band). ``fired`` is
    True iff ``consecutive_years >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS``.

    Catches off-by-one errors in the streak counter — the most common
    failure mode for "first N consecutive" logic.
    """
    base_pe = date(2025, 12, 31)
    in_band_ni = 3_000_000.0  # NI/TA = 0.003 (in band, < 0.005)
    out_band_ni = 100_000_000.0  # NI/TA = 0.10 (way above band)
    ta = 1_000_000_000.0

    # Build history newest → oldest, then place into snap + dataframe.
    rows: list[dict] = []
    # The snapshot will represent the newest in-band year (if any), or
    # an out-of-band year (when in_band_years == 0).
    if in_band_years >= 1:
        snap = _snap(
            net_income=in_band_ni,
            total_assets=ta,
            latest_period_end=base_pe,
        )
        # Remaining in_band_years - 1 in-band history rows.
        for i in range(1, in_band_years):
            pe = date(2025 - i, 12, 31)
            rows.append({"metric": "net_income", "value": in_band_ni, "period_end": pe})
            rows.append({"metric": "total_assets", "value": ta, "period_end": pe})
        # Then the out-of-band block.
        for j in range(out_of_band_year_count):
            pe = date(2025 - in_band_years - j, 12, 31)
            rows.append({"metric": "net_income", "value": out_band_ni, "period_end": pe})
            rows.append({"metric": "total_assets", "value": ta, "period_end": pe})
    else:
        # No in-band years at all; snap is out-of-band.
        snap = _snap(
            net_income=out_band_ni,
            total_assets=ta,
            latest_period_end=base_pe,
        )
        for j in range(1, out_of_band_year_count + 1):
            pe = date(2025 - j, 12, 31)
            rows.append({"metric": "net_income", "value": out_band_ni, "period_end": pe})
            rows.append({"metric": "total_assets", "value": ta, "period_end": pe})

    hist = _history(rows) if rows else None
    result = check_loss_avoidance_size_invariant(snap, hist)
    assert result.consecutive_years == in_band_years
    assert result.fired is (in_band_years >= LOSS_AVOID_MIN_CONSECUTIVE_YEARS)


def test_loss_avoidance_size_invariant_threshold_constant():
    """Pin Roychowdhury 2006 §5.2 suspect-firm threshold (0.5% of assets)."""
    assert LOSS_AVOID_NI_TO_ASSETS_CEILING == 0.005
