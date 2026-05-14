"""Tests for compute.ingest.cross_source (Phase 4b §1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from compute import config
from compute.ingest.cross_source import (
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
    assert validate_market_cap("ZZZ", snap, current_price=50.0, yf_market_cap=4_000_000_000.0) is True


def test_validate_market_cap_agrees_below_tolerance():
    """SEC = 100M × $50 = $5B; yfinance reports $4.9B = 2% delta → no flag."""
    snap = _snap(shares=100_000_000.0)
    assert validate_market_cap("ZZZ", snap, current_price=50.0, yf_market_cap=4_900_000_000.0) is False


def test_validate_market_cap_exactly_at_tolerance_does_not_flag():
    """5% delta exactly is NOT flagged (strict > check). Reasonable edge."""
    snap = _snap(shares=100_000_000.0)
    sec_mc = 5_000_000_000.0
    yf_at_tolerance = sec_mc * 0.95  # 5% below
    assert validate_market_cap("ZZZ", snap, current_price=50.0, yf_market_cap=yf_at_tolerance) is False


def test_validate_market_cap_quiet_skip_on_missing_snap():
    assert validate_market_cap("ZZZ", None, current_price=50.0, yf_market_cap=1e9) is False


def test_validate_market_cap_quiet_skip_on_missing_shares():
    snap = _snap(shares=None)
    assert validate_market_cap("ZZZ", snap, current_price=50.0, yf_market_cap=1e9) is False


def test_validate_market_cap_quiet_skip_on_zero_shares():
    snap = _snap(shares=0.0)
    assert validate_market_cap("ZZZ", snap, current_price=50.0, yf_market_cap=1e9) is False


def test_validate_market_cap_quiet_skip_on_missing_price():
    snap = _snap(shares=100_000_000.0)
    assert validate_market_cap("ZZZ", snap, current_price=None, yf_market_cap=1e9) is False


def test_validate_market_cap_quiet_skip_on_missing_yf():
    snap = _snap(shares=100_000_000.0)
    # yf_market_cap None + cache miss + no live fetch → quiet skip
    with patch(
        "compute.ingest.cross_source.fetch_yfinance_market_cap", return_value=None
    ):
        assert validate_market_cap("ZZZ", snap, current_price=50.0) is False


def test_validate_market_cap_custom_tolerance():
    """A 10% tolerance accepts a 7% delta that the 5% default would reject."""
    snap = _snap(shares=100_000_000.0)
    yf_mc_7pct_off = 5_000_000_000.0 * 0.93
    assert validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=yf_mc_7pct_off
    ) is True
    assert validate_market_cap(
        "ZZZ", snap, current_price=50.0, yf_market_cap=yf_mc_7pct_off, tolerance=0.10
    ) is False


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
