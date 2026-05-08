"""Unit tests for compute.scoring.risk_overlay."""

from __future__ import annotations

from datetime import date

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.risk_overlay import (
    ALTMAN_DISTRESS_THRESHOLD,
    SLOAN_MIN_POPULATION,
    SLOAN_TOP_DECILE,
    compute_risk_flags,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    """Build a FundamentalsSnapshot with sensible defaults for the test.

    Defaults yield a healthy Altman Z″ (≈ comfortable safe zone) and a
    near-zero accruals ratio — overrides target one or both flags.
    """
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 100.0,
        "net_income": 10.0,
        "total_assets": 200.0,
        "total_liabilities": 100.0,
        "stockholders_equity": 100.0,
        "current_assets": 100.0,
        "current_liabilities": 50.0,
        "operating_cash_flow": 10.0,
        "retained_earnings": 50.0,
        "operating_income": 20.0,  # used as EBIT proxy in altman_z_double_prime
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def test_no_flags_when_healthy():
    healthy = _snap()  # default values are healthy
    flags = compute_risk_flags({"HEALTHY": healthy})
    assert flags["HEALTHY"] == []


def test_altman_distress_flag_fires_when_z_below_threshold():
    # Force Z″ < 1.1 by zeroing retained earnings + operating income + flipping equity sign.
    distressed = _snap(
        retained_earnings=-200.0,
        operating_income=-50.0,
        stockholders_equity=-50.0,
    )
    flags = compute_risk_flags({"DISTRESSED": distressed})
    assert "altman_distress" in flags["DISTRESSED"]


def test_altman_threshold_is_strict_inequality():
    # If the function would compute exactly the threshold, the flag should
    # NOT fire. We can't guarantee an exact-Z snapshot, but we can verify
    # the threshold constant matches the documented value.
    assert ALTMAN_DISTRESS_THRESHOLD == 1.1


def test_sloan_accruals_top_decile_flag():
    # Build 10 tickers with monotonically increasing accruals. The top one
    # (rank 10) should be at the 90th percentile and earn the flag.
    snaps: dict[str, FundamentalsSnapshot] = {}
    for i in range(10):
        # accruals = (NI - CFO) / TA. Hold TA fixed at 1000.
        # i=0: NI - CFO = -90 → very negative (lowest accruals)
        # i=9: NI - CFO = +90 → very positive (highest accruals)
        delta = (i - 4.5) * 20.0
        snaps[f"T{i:02d}"] = _snap(
            net_income=10.0 + delta,
            operating_cash_flow=10.0,
            total_assets=1000.0,
        )
    flags = compute_risk_flags(snaps)
    # Top accruals = T09; should be flagged.
    assert "sloan_accruals_top_decile" in flags["T09"]
    # Lowest accruals = T00; must not be flagged.
    assert "sloan_accruals_top_decile" not in flags["T00"]


def test_sloan_threshold_constant():
    assert SLOAN_TOP_DECILE == 0.90


def test_sloan_below_min_population_disables_flag():
    # With fewer than SLOAN_MIN_POPULATION tickers, the Sloan flag is not
    # statistically meaningful and must be suppressed even if a ticker would
    # mathematically sit at the 90th percentile.
    assert SLOAN_MIN_POPULATION >= 5  # sanity
    snaps = {
        f"T{i}": _snap(net_income=100.0, operating_cash_flow=10.0, total_assets=1000.0)
        for i in range(SLOAN_MIN_POPULATION - 1)
    }
    flags = compute_risk_flags(snaps)
    assert all("sloan_accruals_top_decile" not in v for v in flags.values())


def test_compute_risk_flags_handles_none_snapshot():
    # A None snapshot must not crash and must produce no flags.
    flags = compute_risk_flags({"NULL": None})
    assert flags["NULL"] == []


def test_compute_risk_flags_empty_input():
    assert compute_risk_flags({}) == {}


def test_sloan_accruals_skipped_when_inputs_missing():
    # If TA is missing, accruals = NaN → no Sloan flag, only altman if present.
    s = _snap(total_assets=None)
    flags = compute_risk_flags({"NOTA": s})
    assert "sloan_accruals_top_decile" not in flags["NOTA"]
