"""Tests for compute.ingest.cross_source (Phase 4b §1 + Issue #248 PR2a)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from compute import config
from compute.ingest.cross_source import (
    BUCKET_KEYS,
    bucket_delta,
    fetch_yfinance_market_cap,
    validate_market_cap,
)
from compute.ingest.fundamentals import FundamentalsSnapshot


def _snap(shares: float | None) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        ticker="ZZZ",
        cik="0000000001",
        latest_period_end="2025-12-31",
        latest_filed_date="2026-02-15",
        revenue=100_000_000.0,
        net_income=10_000_000.0,
        total_assets=200_000_000.0,
        total_liabilities=80_000_000.0,
        stockholders_equity=120_000_000.0,
        cash=20_000_000.0,
        operating_cash_flow=15_000_000.0,
        capex=5_000_000.0,
        eps_basic=1.0,
        eps_diluted=1.0,
        shares_outstanding=shares,
        goodwill=0.0,
    )


def test_validate_market_cap_disagrees_above_tolerance():
    """SEC = 100M × $50 = $5B; yfinance reports $4B = 20% delta → flag."""
    snap = _snap(shares=100_000_000.0)
    disagreement, delta = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=4_000_000_000.0
    )
    assert disagreement is True
    assert delta is not None and delta > config.CROSS_SOURCE_MARKET_CAP_TOLERANCE


def test_validate_market_cap_agrees_below_tolerance():
    """SEC = 100M × $50 = $5B; yfinance reports $4.9B = 2% delta → no flag."""
    snap = _snap(shares=100_000_000.0)
    disagreement, delta = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=4_900_000_000.0
    )
    assert disagreement is False
    assert delta is not None and delta <= config.CROSS_SOURCE_MARKET_CAP_TOLERANCE


def test_validate_market_cap_exactly_at_tolerance_does_not_flag():
    """5% delta exactly is NOT flagged (strict > check). Reasonable edge."""
    snap = _snap(shares=100_000_000.0)
    sec_mc = 5_000_000_000.0
    yf_at_tolerance = sec_mc * 0.95  # 5% below
    disagreement, delta = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=yf_at_tolerance
    )
    assert disagreement is False
    assert delta is not None and delta <= config.CROSS_SOURCE_MARKET_CAP_TOLERANCE


def test_validate_market_cap_quiet_skip_on_missing_snap():
    disagreement, delta = validate_market_cap(
        "ZZZ", None, current_price=50.0, yf_market_cap=1e9
    )
    assert disagreement is False
    assert delta is None


def test_validate_market_cap_quiet_skip_on_missing_shares():
    snap = _snap(shares=None)
    disagreement, delta = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=1e9
    )
    assert disagreement is False
    assert delta is None


def test_validate_market_cap_quiet_skip_on_zero_shares():
    snap = _snap(shares=0.0)
    disagreement, delta = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=1e9
    )
    assert disagreement is False
    assert delta is None


def test_validate_market_cap_quiet_skip_on_missing_price():
    snap = _snap(shares=100_000_000.0)
    disagreement, delta = validate_market_cap(
        "ZZZ", snap, current_price=None, yf_market_cap=1e9
    )
    assert disagreement is False
    assert delta is None


def test_validate_market_cap_quiet_skip_on_missing_yf():
    snap = _snap(shares=100_000_000.0)
    # yf_market_cap None + cache miss + no live fetch → quiet skip
    with patch(
        "compute.ingest.cross_source.fetch_yfinance_market_cap", return_value=None
    ):
        disagreement, delta = validate_market_cap("ZZZ", snap, current_price=50.0)
    assert disagreement is False
    assert delta is None


def test_validate_market_cap_custom_tolerance():
    """A 10% tolerance accepts a 7% delta that the 5% default would reject."""
    snap = _snap(shares=100_000_000.0)
    yf_mc_7pct_off = 5_000_000_000.0 * 0.93
    disagreement_default, delta_default = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=yf_mc_7pct_off
    )
    assert disagreement_default is True
    disagreement_wide, delta_wide = validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=yf_mc_7pct_off, tolerance=0.10
    )
    assert disagreement_wide is False
    # Both compute the same underlying delta value regardless of tolerance
    assert delta_default is not None and delta_wide is not None
    assert abs(delta_default - delta_wide) < 1e-12


def test_fetch_yfinance_market_cap_reads_from_cache(tmp_path: Path, monkeypatch):
    """Cache hit returns cached value without calling yfinance."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "AAPL.json"
    cache_file.write_text(json.dumps({"market_cap": 3.5e12}))

    with patch("compute.ingest.cross_source._yf_info_market_cap") as mock_yf:
        result = fetch_yfinance_market_cap("AAPL")
    assert result == 3.5e12
    mock_yf.assert_not_called()


def test_fetch_yfinance_market_cap_falls_back_to_live(tmp_path: Path, monkeypatch):
    """Cache miss invokes yfinance and writes the result back to cache."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    with patch(
        "compute.ingest.cross_source._yf_info_market_cap", return_value=2.0e12
    ) as mock_yf:
        result = fetch_yfinance_market_cap("AAPL")
    assert result == 2.0e12
    mock_yf.assert_called_once_with("AAPL")
    # Cache write should have occurred.
    cache_file = tmp_path / "AAPL.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text())["market_cap"] == 2.0e12


def test_fetch_yfinance_market_cap_returns_none_on_yfinance_failure(
    tmp_path: Path, monkeypatch
):
    """Quiet-failure: yfinance raises → return None, no cache write."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    with patch(
        "compute.ingest.cross_source._yf_info_market_cap",
        side_effect=Exception("network error"),
    ):
        result = fetch_yfinance_market_cap("AAPL")
    assert result is None
    assert not (tmp_path / "AAPL.json").exists()


@pytest.mark.parametrize(
    "garbage_market_cap",
    [None, 0, -1, "not_a_number"],
)
def test_fetch_yfinance_market_cap_rejects_garbage_values(
    tmp_path: Path, monkeypatch, garbage_market_cap
):
    """yfinance occasionally returns 0 / None / negative — treat as missing."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    info_response = {"marketCap": garbage_market_cap}
    with patch("compute.ingest.cross_source.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = info_response
        result = fetch_yfinance_market_cap("AAPL")
    assert result is None


# ---------------------------------------------------------------------------
# bucket_delta — 9-bucket observability classifier (Issue #248 PR2a)
# ---------------------------------------------------------------------------


def test_bucket_delta_none_unavailable():
    """None delta (missing input) maps to the sentinel 'unavailable' bucket."""
    assert bucket_delta(None) == "unavailable"


def test_bucket_delta_below_5pct():
    """Deltas strictly below 5% land in '<5'. Zero is the lowest possible delta."""
    assert bucket_delta(0.04) == "<5"
    assert bucket_delta(0.0) == "<5"


def test_bucket_delta_boundary_5pct():
    """0.05 (exactly 5%) is the floor of '5-25' per half-open [lower, upper) intervals."""
    assert bucket_delta(0.05) == "5-25"


def test_bucket_delta_25_50():
    """Deltas in [25%, 50%) land in '25-50'. Floor value 0.25 belongs to this bucket."""
    assert bucket_delta(0.30) == "25-50"
    assert bucket_delta(0.25) == "25-50"


def test_bucket_delta_50_75():
    """0.50 (exactly 50%) is the floor of '50-75'."""
    assert bucket_delta(0.50) == "50-75"


def test_bucket_delta_75_100():
    """Deltas in [75%, 100%) land in '75-100'. 0.99 is just below the 100% boundary."""
    assert bucket_delta(0.75) == "75-100"
    assert bucket_delta(0.99) == "75-100"


def test_bucket_delta_100_150_severe_threshold_band():
    """100% and 120% both land in '100-150' (the severe-disagreement observation band).

    The 100%/150% threshold will be calibrated from the first 0.10.3 cron histogram
    tail mass — these values sit at the two ends of the band under test.
    """
    assert bucket_delta(1.00) == "100-150"
    assert bucket_delta(1.20) == "100-150"


def test_bucket_delta_150_200():
    """Deltas in [150%, 200%) land in '150-200'. 1.99 is just below the 200% boundary."""
    assert bucket_delta(1.50) == "150-200"
    assert bucket_delta(1.99) == "150-200"


def test_bucket_delta_above_200_V_pattern():
    """2.00 (exactly 200%) opens '>200'. 2.76 (276%) is the V-pattern from the
    stock-detail-auditor dry-run (APP -1255% MoS = extreme_estimate_majority cohort).
    """
    assert bucket_delta(2.00) == ">200"
    assert bucket_delta(2.76) == ">200"


def test_bucket_keys_pinned():
    """Drift detector: BUCKET_KEYS order and membership must be exact.

    A rename, reorder, or addition forces a coordinated update across
    bucket_delta(), schemas.py docstring, and the verify-production-output
    helper Section L. Length == 9 is the second guard.
    """
    assert BUCKET_KEYS == (
        "<5",
        "5-25",
        "25-50",
        "50-75",
        "75-100",
        "100-150",
        "150-200",
        ">200",
        "unavailable",
    )
    assert len(BUCKET_KEYS) == 9


@given(
    st.one_of(
        st.none(),
        st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
)
def test_property_bucket_delta_total_partition_over_universe(d):
    """For every valid delta (float in [0, 10]) or None, bucket_delta() always
    returns a key that exists in BUCKET_KEYS. Verifies the 9-bucket classifier
    is total — no input escapes to an unlisted key.
    """
    result = bucket_delta(d)
    assert result in BUCKET_KEYS
