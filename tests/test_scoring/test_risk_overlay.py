"""Unit tests for compute.scoring.risk_overlay."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.risk_overlay import (
    ALTMAN_DISTRESS_THRESHOLD,
    NSI_MIN_POPULATION,
    SLOAN_MIN_POPULATION,
    SLOAN_TOP_DECILE,
    _net_stock_issuance,
    _shares_at_lookback,
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


# --- Defense #1: Net Stock Issuance (Pontiff-Woodgate 2008 JF) ----------------
#
# NSI = ln(shares_t / shares_{t-12m}). Within-sector top decile triggers flag.
# Pure-helper tests on _shares_at_lookback + _net_stock_issuance precede the
# integration tests so a failure points at the smallest unit.


_NSI_TODAY = date(2026, 5, 9)  # deterministic clock for all NSI tests


def _history_with_shares(prior_shares: float, *, years_ago: int = 1) -> pd.DataFrame:
    """Build a minimal annual history DataFrame containing one shares_outstanding row."""
    period_end = _NSI_TODAY - timedelta(days=365 * years_ago)
    return pd.DataFrame(
        [
            {
                "fiscal_year": _NSI_TODAY.year - years_ago,
                "metric": "shares_outstanding",
                "value": prior_shares,
                "period_end": period_end,
                "filing_date": period_end + timedelta(days=60),
                "form_type": "10-K",
            }
        ]
    )


def test_shares_at_lookback_returns_correct_value():
    history = _history_with_shares(1_000_000.0)
    out = _shares_at_lookback(history, asof_days=365, today=_NSI_TODAY)
    assert out == 1_000_000.0


def test_shares_at_lookback_skips_too_recent_rows():
    # A row only 30 days old must NOT satisfy a 365d lookback (cutoff = 182d).
    history = _history_with_shares(1_000_000.0)
    history.loc[0, "period_end"] = _NSI_TODAY - timedelta(days=30)
    out = _shares_at_lookback(history, asof_days=365, today=_NSI_TODAY)
    assert out is None


def test_shares_at_lookback_handles_empty_or_missing():
    assert _shares_at_lookback(None, 365, today=_NSI_TODAY) is None
    assert _shares_at_lookback(pd.DataFrame(), 365, today=_NSI_TODAY) is None
    no_metric_col = pd.DataFrame([{"value": 1e6, "period_end": _NSI_TODAY}])
    assert _shares_at_lookback(no_metric_col, 365, today=_NSI_TODAY) is None


def test_shares_at_lookback_rejects_non_positive_value():
    history = _history_with_shares(0.0)
    assert _shares_at_lookback(history, 365, today=_NSI_TODAY) is None


def test_net_stock_issuance_zero_when_shares_unchanged():
    snap = _snap(shares_outstanding=1_000_000.0)
    history = _history_with_shares(1_000_000.0)
    nsi = _net_stock_issuance(snap, history, today=_NSI_TODAY)
    assert nsi == 0.0


def test_net_stock_issuance_positive_under_dilution():
    snap = _snap(shares_outstanding=1_150_000.0)  # +15% YoY
    history = _history_with_shares(1_000_000.0)
    nsi = _net_stock_issuance(snap, history, today=_NSI_TODAY)
    # ln(1.15) ≈ 0.1398
    assert 0.13 < nsi < 0.15


def test_net_stock_issuance_nan_when_history_missing():
    import math

    snap = _snap(shares_outstanding=1_000_000.0)
    nsi = _net_stock_issuance(snap, None, today=_NSI_TODAY)
    assert math.isnan(nsi)


def test_nsi_top_decile_within_sector_flags_diluter():
    # 12 tickers in one sector. Eleven have stable shares; one (T11) dilutes
    # 15%. The diluter must land in the top decile and earn the flag.
    snaps: dict[str, FundamentalsSnapshot] = {}
    histories: dict[str, pd.DataFrame] = {}
    sectors: dict[str, str] = {}
    for i in range(11):
        ticker = f"T{i:02d}"
        snaps[ticker] = _snap(shares_outstanding=1_000_000.0)
        histories[ticker] = _history_with_shares(1_000_000.0)
        sectors[ticker] = "Information Technology"
    snaps["T11"] = _snap(shares_outstanding=1_150_000.0)  # +15% YoY
    histories["T11"] = _history_with_shares(1_000_000.0)
    sectors["T11"] = "Information Technology"

    flags = compute_risk_flags(
        snaps, histories=histories, sectors=sectors, today=_NSI_TODAY
    )
    assert "net_issuance_top_decile" in flags["T11"]
    # The 11 stable-shares tickers must NOT be flagged (NSI = 0 for all of them).
    for i in range(11):
        assert "net_issuance_top_decile" not in flags[f"T{i:02d}"]


def test_nsi_skipped_when_sectors_not_provided():
    # Without sectors, NSI defaults to NOT firing (we don't degrade to
    # cross-sectional — that was the lesson from issue #7's Sloan over-fire
    # on REITs/banks). 12 tickers, one with massive dilution → no flag.
    snaps = {f"T{i:02d}": _snap(shares_outstanding=1_000_000.0) for i in range(11)}
    snaps["T11"] = _snap(shares_outstanding=2_000_000.0)
    histories = {t: _history_with_shares(1_000_000.0) for t in snaps}
    flags = compute_risk_flags(snaps, histories=histories, today=_NSI_TODAY)
    for t in snaps:
        assert "net_issuance_top_decile" not in flags[t]


def test_nsi_skipped_when_sector_below_min_population():
    # Sector with fewer than NSI_MIN_POPULATION members → NSI flag suppressed
    # entirely for that sector even if the math would put a ticker in the
    # top decile.
    assert NSI_MIN_POPULATION >= 5
    snaps: dict[str, FundamentalsSnapshot] = {}
    histories: dict[str, pd.DataFrame] = {}
    sectors: dict[str, str] = {}
    for i in range(NSI_MIN_POPULATION - 1):
        ticker = f"S{i:02d}"
        snaps[ticker] = _snap(shares_outstanding=1_000_000.0 * (1.0 + 0.02 * i))
        histories[ticker] = _history_with_shares(1_000_000.0)
        sectors[ticker] = "Energy"
    flags = compute_risk_flags(
        snaps, histories=histories, sectors=sectors, today=_NSI_TODAY
    )
    for t in snaps:
        assert "net_issuance_top_decile" not in flags[t]


def test_compute_risk_flags_backward_compat_without_new_kwargs():
    # The PR-3b signature (snapshots only) must still work — Step 1 of PR-3c
    # added kwargs. Existing callers see no behavior change.
    flags = compute_risk_flags({"HEALTHY": _snap()})
    assert flags["HEALTHY"] == []


# -- Defense #9 — non_reliance_filing 4th veto (PR 3d Step 4) ---------------

def test_C1_non_reliance_inject_true_appends_flag():
    """Inject path: non_reliance_by_ticker={ticker: True} → flag appears."""
    snaps = {"TST": _snap()}
    flags = compute_risk_flags(snaps, non_reliance_by_ticker={"TST": True})
    assert "non_reliance_filing" in flags["TST"]


def test_C2_non_reliance_inject_false_omits_flag():
    """Inject path: non_reliance_by_ticker={ticker: False} → no flag."""
    snaps = {"TST": _snap()}
    flags = compute_risk_flags(snaps, non_reliance_by_ticker={"TST": False})
    assert "non_reliance_filing" not in flags["TST"]


def test_C3_non_reliance_missing_from_inject_dict_omits_flag():
    """Inject path with empty dict — same as False (default)."""
    snaps = {"TST": _snap()}
    flags = compute_risk_flags(snaps, non_reliance_by_ticker={})
    assert "non_reliance_filing" not in flags["TST"]


def test_C4_non_reliance_default_path_no_env_yields_no_flag(monkeypatch):
    """Default path: no inject kwarg → calls check_non_reliance(ticker)
    which without EDGAR_USER_AGENT returns ItemFlag(fired=False) — no
    flag appended. Existing PR-3c tests rely on this contract.
    """
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    # Point cache at a fresh tmp dir so we know we hit identity-fail path,
    # not a stale cache.
    import tempfile

    from compute import config
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path
        monkeypatch.setattr(config, "EDGAR_8K_CACHE_DIR", Path(tmpdir) / "edgar_8k")
        # Reset module-level identity flag — different test runs might
        # have set it in earlier tests. (Forgivable side-effect; PR 3d
        # Step 5 will own the production identity setup.)
        from compute.scoring import eight_k_events
        monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
        flags = compute_risk_flags({"TST": _snap()})
        assert "non_reliance_filing" not in flags["TST"]


def test_C5_non_reliance_does_not_affect_existing_flags():
    """A ticker that should fire altman / sloan / NSI plus non_reliance
    sees ALL four flags — they are additive."""
    snaps = {
        "BAD": _snap(
            stockholders_equity=10.0,  # tiny equity → low Z″
            total_liabilities=200.0,
            retained_earnings=-50.0,
            operating_income=-10.0,
            current_assets=10.0,
            current_liabilities=100.0,
        ),
    }
    flags = compute_risk_flags(snaps, non_reliance_by_ticker={"BAD": True})
    assert "altman_distress" in flags["BAD"]
    assert "non_reliance_filing" in flags["BAD"]


def test_C6_inject_dict_does_not_pollute_other_tickers():
    """non_reliance_by_ticker={A: True} should NOT add the flag to B."""
    snaps = {"A": _snap(), "B": _snap()}
    flags = compute_risk_flags(snaps, non_reliance_by_ticker={"A": True})
    assert "non_reliance_filing" in flags["A"]
    assert "non_reliance_filing" not in flags["B"]
