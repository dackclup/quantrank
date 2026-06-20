"""Coverage tests for compute.scoring.earnings_quality — targeting uncovered branches.

Uncovered lines (baseline 89%):
  196    _annual_values: empty history (len == 0)
  205-206 _annual_values: TypeError/ValueError on row parse → skip
  208    _annual_values: non-finite value skipped
  257    check_accruals_momentum: non-finite TATA_now → early return
  276    check_accruals_momentum: non-finite TATA_then → early return
  300    _in_tiny_positive_band: None NI returns False
  340    check_loss_avoidance: snap.latest_period_end is None path (else branch)
  344    check_loss_avoidance: pe >= snap.latest_period_end history skip
  384    check_loss_avoidance_size_invariant: snap.latest_period_end is None
  407    check_loss_avoidance_size_invariant: pe >= snap.latest_period_end skip
  422    check_loss_avoidance_size_invariant: non-finite ni or ta → break
  425    check_loss_avoidance_size_invariant: non-finite ratio → break
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.earnings_quality import (
    _annual_values,
    _in_tiny_positive_band,
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
# _annual_values: various early-return paths (lines 196, 205-206, 208)
# ---------------------------------------------------------------------------


def test_annual_values_returns_empty_for_none_history():
    assert _annual_values(None, "net_income") == []


def test_annual_values_returns_empty_for_empty_df():
    assert _annual_values(pd.DataFrame(), "net_income") == []


def test_annual_values_returns_empty_for_missing_columns():
    """DataFrame without 'metric' or 'period_end' columns → empty list."""
    df = pd.DataFrame({"value": [100.0]})
    assert _annual_values(df, "net_income") == []


def test_annual_values_skips_row_with_bad_period_end():
    """A row with unparseable period_end is skipped (TypeError/ValueError guard)."""
    df = pd.DataFrame(
        [
            {"metric": "net_income", "value": 100.0, "period_end": "not-a-date"},
            {"metric": "net_income", "value": 200.0, "period_end": date(2024, 12, 31)},
        ]
    )
    result = _annual_values(df, "net_income")
    # Only the second row (valid date) is returned.
    assert len(result) == 1
    assert result[0][1] == 200.0


def test_annual_values_skips_non_finite_values():
    """Non-finite values (inf, nan) are excluded."""
    df = pd.DataFrame(
        [
            {"metric": "net_income", "value": float("inf"), "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": float("nan"), "period_end": date(2023, 12, 31)},
            {"metric": "net_income", "value": 100.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = _annual_values(df, "net_income")
    assert len(result) == 1
    assert result[0][1] == 100.0


def test_annual_values_skips_bad_float_cast():
    """Non-numeric string value → ValueError in float() → row skipped."""
    df = pd.DataFrame(
        [
            {"metric": "net_income", "value": "not_a_number", "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 50.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = _annual_values(df, "net_income")
    assert len(result) == 1
    assert result[0][1] == 50.0


# ---------------------------------------------------------------------------
# _in_tiny_positive_band: None ni path (line 300)
# ---------------------------------------------------------------------------


def test_in_tiny_positive_band_none_ni_returns_false():
    """None NI → cannot be in band → False."""
    assert _in_tiny_positive_band(None, 1_000_000.0) is False


def test_in_tiny_positive_band_nan_ni_returns_false():
    """NaN NI → not finite → False."""
    assert _in_tiny_positive_band(float("nan"), 1_000_000.0) is False


# ---------------------------------------------------------------------------
# check_accruals_momentum: non-finite TATA_now (line 257)
# ---------------------------------------------------------------------------


def test_accruals_momentum_returns_false_when_tata_now_non_finite():
    """If NI/TA arithmetic produces inf or nan, early return fired=False."""
    # total_assets very small causing div issue — but Python float handles that.
    # Instead we test NI=inf → TATA = inf → not finite.
    snap = _snap(
        net_income=float("inf"),  # not finite
        operating_cash_flow=100.0,
        total_assets=2_000.0,
    )
    result = check_accruals_momentum(snap, None)
    # tata_now = inf/2000 = inf → not finite → fired=False
    assert result.fired is False
    assert result.tata_now is None


# ---------------------------------------------------------------------------
# check_accruals_momentum: non-finite TATA_then (line 276)
# ---------------------------------------------------------------------------


def test_accruals_momentum_returns_false_when_tata_then_non_finite():
    """If the historical TATA is non-finite, the result is fired=False."""
    snap = _snap(
        net_income=100.0,
        operating_cash_flow=80.0,
        total_assets=1_000.0,
    )
    hist = _history(
        [
            {"metric": "net_income", "value": float("inf"), "period_end": date(2022, 12, 31)},
            {"metric": "operating_cash_flow", "value": 30.0, "period_end": date(2022, 12, 31)},
            {"metric": "total_assets", "value": 1_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_accruals_momentum(snap, hist)
    # tata_then = inf/1000 → not finite → fired=False, tata_then=None
    assert result.fired is False
    # tata_now should be computed (0.02)
    assert result.tata_now is not None


# ---------------------------------------------------------------------------
# check_loss_avoidance: no latest_period_end path (line 340-344)
# ---------------------------------------------------------------------------


def test_loss_avoidance_uses_history_only_when_no_latest_period_end():
    """When snap.latest_period_end is None, the function uses history alone."""
    snap = _snap(
        net_income=25_000_000.0,
        latest_period_end=None,  # no period end
    )
    hist = _history(
        [
            {"metric": "net_income", "value": 30_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 10_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "net_income", "value": 45_000_000.0, "period_end": date(2022, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    # Uses only the 3 history rows; all in [0, 50M] → fires
    assert result.fired is True
    assert result.consecutive_years == 3


def test_loss_avoidance_skips_same_period_history_rows():
    """History rows with pe >= snap.latest_period_end are skipped (line 344)."""
    snap = _snap(
        net_income=25_000_000.0,
        shares_outstanding=10_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            # Same period as snap → should be skipped
            {"metric": "net_income", "value": 50_000_000.0, "period_end": date(2025, 12, 31)},
            # Future → should be skipped
            {"metric": "net_income", "value": 100_000_000_000.0, "period_end": date(2026, 3, 31)},
            # Valid prior years:
            {"metric": "net_income", "value": 30_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 10_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance(snap, hist)
    # snap(2025) in band, 2024 in band, 2023 in band → 3 consecutive → fires
    # The same-period/future rows are skipped so don't break the streak.
    assert result.fired is True
    assert result.consecutive_years == 3


# ---------------------------------------------------------------------------
# check_loss_avoidance_size_invariant: latest_period_end None (line 384-407)
# ---------------------------------------------------------------------------


def test_loss_avoidance_size_invariant_works_without_latest_period_end():
    """When snap.latest_period_end is None, snap not prepended, history used directly."""
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=1_000_000_000.0,
        latest_period_end=None,  # excluded from snap prepend
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
    # 3 history years all in band (NI/TA ~0.003)
    assert result.consecutive_years == 3
    assert result.fired is True


def test_loss_avoidance_size_invariant_skips_same_period_rows():
    """History rows at or after snap.latest_period_end are skipped (line 407)."""
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=1_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            # Same period → should be skipped
            {"metric": "net_income", "value": 99_999_999.0, "period_end": date(2025, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2025, 12, 31)},
            # Valid prior:
            {"metric": "net_income", "value": 2_500_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
            {"metric": "net_income", "value": 1_000_000.0, "period_end": date(2023, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2023, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    # Snap (2025) + 2024 + 2023 all in band → 3 → fires
    assert result.fired is True
    assert result.consecutive_years == 3


def test_loss_avoidance_size_invariant_breaks_on_non_finite_ni():
    """Non-finite NI breaks the streak (line 422 guard)."""
    snap = _snap(
        net_income=3_000_000.0,
        total_assets=1_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    hist = _history(
        [
            # 2024: NI=inf → non-finite → streak breaks
            {"metric": "net_income", "value": float("inf"), "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_000_000_000.0, "period_end": date(2024, 12, 31)},
        ]
    )
    result = check_loss_avoidance_size_invariant(snap, hist)
    # snap in band (count=1), 2024 has inf NI → break → only 1 year
    assert result.consecutive_years == 1
    assert result.fired is False


def test_loss_avoidance_size_invariant_none_net_income_is_clean():
    """None net_income → snap not prepended → walker sees no rows → clean (0)."""
    # FundamentalsSnapshot coerces a NaN net_income to None, so exercise the None path.
    snap = _snap(
        net_income=None,
        total_assets=1_000_000_000.0,
        latest_period_end=date(2025, 12, 31),
    )
    result = check_loss_avoidance_size_invariant(snap, None)
    assert result.consecutive_years == 0
    assert result.fired is False
