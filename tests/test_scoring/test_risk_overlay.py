"""Unit tests for compute.scoring.risk_overlay."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from compute.ingest.fundamentals import ALL_METRIC_KEYS, FundamentalsSnapshot
from compute.scoring.beneish import BENEISH_VETO_THRESHOLD
from compute.scoring.dechow_f import DECHOW_VETO_THRESHOLD
from compute.scoring.risk_overlay import (
    ALTMAN_DISTRESS_THRESHOLD,
    NSI_MIN_POPULATION,
    SLOAN_MIN_POPULATION,
    SLOAN_MIN_POPULATION_SECTOR,
    SLOAN_TOP_DECILE,
    _net_stock_issuance,
    _shares_at_lookback,
    _snapshot_has_no_usable_fundamentals,
    check_share_count_extraction_missing,
    compute_risk_flags,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    """Build a FundamentalsSnapshot with sensible defaults for the test.

    Defaults yield a healthy Altman Z″ (≈ comfortable safe zone) and a
    near-zero accruals ratio — overrides target one or both flags.
    """
    # Scaled to millions ($100M revenue / $10M NI baseline) — above the
    # _MIN_PLAUSIBLE_TTM_REVENUE = $50M threshold added in audit #5
    # (pre-v1.0 data-quality guard against XBRL tag mispicks).
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 100_000_000.0,
        "net_income": 10_000_000.0,
        "total_assets": 200_000_000.0,
        "total_liabilities": 100_000_000.0,
        "stockholders_equity": 100_000_000.0,
        "current_assets": 100_000_000.0,
        "current_liabilities": 50_000_000.0,
        "operating_cash_flow": 10_000_000.0,
        "retained_earnings": 50_000_000.0,
        "operating_income": 20_000_000.0,  # used as EBIT proxy in altman_z_double_prime
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
        retained_earnings=-200_000_000.0,
        operating_income=-50_000_000.0,
        stockholders_equity=-50_000_000.0,
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


def test_sloan_sector_relative_top_decile_when_sectors_supplied():
    # PR 4.5a.1 — when `sectors` is supplied and the sector population
    # meets SLOAN_MIN_POPULATION_SECTOR, Sloan top-decile is computed
    # WITHIN sector rather than across the full universe.
    # Build two sectors of SLOAN_MIN_POPULATION_SECTOR tickers each:
    #   - "Financials": elevated baseline accruals (structurally non-cash
    #     heavy); top ticker has the sector's highest accruals
    #   - "Technology": near-zero baseline accruals; top ticker has the
    #     sector's highest accruals
    # The Financials sector's median accruals exceed the Tech sector's
    # max, so cross-sectional top-decile would only flag a Financials
    # ticker. Within-sector decile must flag the top ticker IN EACH sector.
    snaps: dict[str, FundamentalsSnapshot] = {}
    sectors: dict[str, str] = {}
    n = SLOAN_MIN_POPULATION_SECTOR
    for i in range(n):
        # Financials: NI-CFO in [+50, +50+n*5] — high baseline
        snaps[f"F{i:02d}"] = _snap(
            net_income=100.0 + 50.0 + (i * 5.0),
            operating_cash_flow=100.0,
            total_assets=1000.0,
        )
        sectors[f"F{i:02d}"] = "Financials"
        # Technology: NI-CFO in [-10, -10+n*1] — low baseline
        snaps[f"T{i:02d}"] = _snap(
            net_income=100.0 - 10.0 + (i * 1.0),
            operating_cash_flow=100.0,
            total_assets=1000.0,
        )
        sectors[f"T{i:02d}"] = "Technology"
    flags = compute_risk_flags(snaps, sectors=sectors)
    # Top ticker in EACH sector should be flagged (within-sector decile).
    assert "sloan_accruals_top_decile" in flags[f"F{n-1:02d}"]
    assert "sloan_accruals_top_decile" in flags[f"T{n-1:02d}"]
    # Bottom ticker in each sector must NOT be flagged.
    assert "sloan_accruals_top_decile" not in flags["F00"]
    assert "sloan_accruals_top_decile" not in flags["T00"]


def test_sloan_sector_relative_skips_undersized_sector():
    # PR 4.5a.1 — sectors with fewer than SLOAN_MIN_POPULATION_SECTOR
    # tickers fall back to the cross-sectional threshold (or skip when
    # the total cross-sectional population also fails SLOAN_MIN_POPULATION).
    # Build one "Small" sector under the floor and one "Large" sector at
    # the floor. The Large sector should get per-sector treatment; the
    # Small sector falls back to cross-sectional.
    snaps: dict[str, FundamentalsSnapshot] = {}
    sectors: dict[str, str] = {}
    # Small sector — 3 tickers (below SLOAN_MIN_POPULATION_SECTOR=15)
    for i in range(3):
        snaps[f"S{i}"] = _snap(
            net_income=100.0 + (i * 100.0),
            operating_cash_flow=100.0,
            total_assets=1000.0,
        )
        sectors[f"S{i}"] = "Small"
    # Large sector — SLOAN_MIN_POPULATION_SECTOR tickers
    for i in range(SLOAN_MIN_POPULATION_SECTOR):
        snaps[f"L{i:02d}"] = _snap(
            net_income=100.0 + (i * 5.0),
            operating_cash_flow=100.0,
            total_assets=1000.0,
        )
        sectors[f"L{i:02d}"] = "Large"
    flags = compute_risk_flags(snaps, sectors=sectors)
    # Large sector top ticker — flagged by per-sector decile
    assert "sloan_accruals_top_decile" in flags[f"L{SLOAN_MIN_POPULATION_SECTOR-1:02d}"]
    # Small sector top ticker has very-high accruals so cross-sectional
    # fallback should still flag it (it's the highest in the combined
    # pool). The contract is "small sector falls back to cross-sectional"
    # not "small sector is silently ignored".
    assert "sloan_accruals_top_decile" in flags["S2"]


def test_sloan_sector_relative_floor_constant():
    # Sanity — floor must be high enough for a top-decile within a sector
    # to be meaningful. With n=15, top decile = floor(1.5) = 1 expected
    # flag per sector, which is the minimum useful signal.
    assert SLOAN_MIN_POPULATION_SECTOR >= 10
    # And must be ≥ SLOAN_MIN_POPULATION so per-sector path is stricter
    # than cross-sectional fallback.
    assert SLOAN_MIN_POPULATION_SECTOR >= SLOAN_MIN_POPULATION


def test_compute_risk_flags_handles_none_snapshot():
    # A None snapshot (complete EDGAR ingest failure) must not crash and
    # must produce exactly the ``fundamentals_unavailable`` direct veto.
    # Locking the partition: DQIC must NOT fire (``_data_quality_input_corruption(None)``
    # → False by contract, issue #18 / test_D3 — that invariant is unchanged).
    flags = compute_risk_flags({"NULL": None})
    assert "fundamentals_unavailable" in flags["NULL"]
    # Partition lock: DQIC must NOT co-fire on a None snapshot.
    assert "data_quality_input_corruption" not in flags["NULL"]
    # No other flags: snap is None short-circuits all downstream checks.
    assert flags["NULL"] == ["fundamentals_unavailable"]


def test_beneish_veto_fires_above_strict_threshold():
    # PR 4.5a.2 — when beneish_m_scores is supplied and a ticker's M is
    # above BENEISH_VETO_THRESHOLD (= -1.78), the `beneish_manipulation_veto`
    # flag fires (active veto, suppresses entered_top5).
    snaps = {"AAA": _snap(), "BBB": _snap()}
    m_scores = {
        "AAA": BENEISH_VETO_THRESHOLD + 0.5,  # well above veto threshold
        "BBB": BENEISH_VETO_THRESHOLD - 0.5,  # below threshold (annotate band)
    }
    flags = compute_risk_flags(snaps, beneish_m_scores=m_scores)
    assert "beneish_manipulation_veto" in flags["AAA"]
    assert "beneish_manipulation_veto" not in flags["BBB"]


def test_beneish_veto_skipped_when_score_is_none():
    # Banks / REITs / asset-light filers commonly fail AQI + DEPI ratios
    # so compute_beneish returns m_score=None. Such tickers must not
    # trigger the veto.
    snaps = {"BANK": _snap()}
    m_scores = {"BANK": None}
    flags = compute_risk_flags(snaps, beneish_m_scores=m_scores)
    assert "beneish_manipulation_veto" not in flags["BANK"]


def test_beneish_veto_strict_inequality():
    # Threshold must be strict (>) not (>=). A ticker sitting exactly AT
    # BENEISH_VETO_THRESHOLD should not fire (per `m > THRESHOLD` semantics
    # documented in beneish.py).
    snaps = {"EDGE": _snap()}
    m_scores = {"EDGE": BENEISH_VETO_THRESHOLD}
    flags = compute_risk_flags(snaps, beneish_m_scores=m_scores)
    assert "beneish_manipulation_veto" not in flags["EDGE"]


def test_beneish_veto_disabled_when_dict_not_supplied():
    # Backward-compat: callers (tests, future external users) that don't
    # supply beneish_m_scores must not see the veto fire — same pattern
    # as non_reliance_by_ticker.
    snaps = {"T1": _snap()}
    flags = compute_risk_flags(snaps)
    assert "beneish_manipulation_veto" not in flags["T1"]


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


# ---------------------------------------------------------------------------
# Issue #18 — data_quality_input_corruption promoted to active veto.
#
# The fix detects corruption from snapshot inputs (TBVPS > $10K/share
# ceiling, mirroring the ensemble's post-hoc check) so the veto fires
# BEFORE Top-5 rotation in compute.main. Previously SPG ranked #1 in
# Run #15 despite obvious corruption — only suppressed by coincidental
# Sloan co-firing. These tests lock the explicit suppression contract.
# ---------------------------------------------------------------------------


def _corrupt_snap(**kwargs) -> FundamentalsSnapshot:
    """Snapshot shaped like the SPG corruption case: huge equity ÷ tiny
    shares → TBVPS ≫ ceiling. Defaults are healthy; one shares override
    is what makes it 'corrupt'."""
    defaults = {
        "stockholders_equity": 76_000_000_000.0,  # $76B (real SPG-class)
        "shares_outstanding": 8_000.0,            # 8K shares (corrupted)
    }
    defaults.update(kwargs)
    return _snap(**defaults)


def test_D1_data_quality_corruption_fires_when_tbvps_exceeds_ceiling():
    """SPG-shape: $76B equity / 8K shares → TBVPS = $9.5M > $10K ceiling."""
    flags = compute_risk_flags({"SPG": _corrupt_snap()})
    assert "data_quality_input_corruption" in flags["SPG"]


def test_D2_data_quality_corruption_does_not_fire_for_normal_snapshot():
    """Default _snap has TBVPS = ~$1/share — far below the $10K ceiling."""
    flags = compute_risk_flags({"NORMAL": _snap()})
    assert "data_quality_input_corruption" not in flags["NORMAL"]


def test_D3_data_quality_corruption_does_not_fire_when_tbvps_uncomputable():
    """shares_outstanding=0 makes TBVPS undefined. We rely on other
    pathways (applicability gates) for null-fair-price; the veto
    itself stays silent.
    """
    snap_missing_shares = _snap(shares_outstanding=None)
    snap_zero_shares = _snap(shares_outstanding=0)
    flags = compute_risk_flags(
        {"M": snap_missing_shares, "Z": snap_zero_shares}
    )
    assert "data_quality_input_corruption" not in flags["M"]
    assert "data_quality_input_corruption" not in flags["Z"]


def test_D4_data_quality_corruption_fires_at_boundary_strict():
    """Strict `>` comparison: TBVPS == ceiling does NOT fire.

    Site-1 (here, in ``compute/scoring/risk_overlay.py``) is the canonical
    input-corruption guard. Site-2 (the former
    ``compute/valuation/ensemble.py::_has_corrupt_input`` output-level
    check) was retired per Issue #289 Option C (2026-05-28); the strict
    `>` invariant lives ONLY here now. Test fixtures sitting exactly at
    the ceiling pass through cleanly without veto.
    """
    from compute import config

    # TBVPS = ceiling exactly: equity = ceiling × shares.
    ceiling = config.FAIR_PRICE_DATA_QUALITY_CEILING
    snap_at = _snap(
        stockholders_equity=ceiling * 100.0,
        shares_outstanding=100.0,
        # zero goodwill + intangibles → TBVPS = equity/shares = ceiling exactly
    )
    snap_over = _snap(
        stockholders_equity=ceiling * 100.0 + 1.0,
        shares_outstanding=100.0,
    )
    flags = compute_risk_flags({"AT": snap_at, "OVER": snap_over})
    assert "data_quality_input_corruption" not in flags["AT"]
    assert "data_quality_input_corruption" in flags["OVER"]


def test_D5_corruption_veto_independent_of_other_flags():
    """A snapshot can fire data_quality alone (no Altman / Sloan / NSI).

    Without this guarantee, the Top-5 rotation skip would have to rely
    on a co-firing other veto — exactly the issue #18 production bug
    pattern. The veto must stand on its own.
    """
    flags = compute_risk_flags({"CORRUPT_ONLY": _corrupt_snap()})
    assert flags["CORRUPT_ONLY"] == ["data_quality_input_corruption"], (
        "Expected ONLY data_quality_input_corruption to fire on a "
        f"clean-but-corrupted snapshot, got: {flags['CORRUPT_ONLY']}"
    )


def test_D6_corruption_does_not_pollute_other_tickers():
    """One corrupted ticker doesn't flag healthy peers (no cross-section).

    The check is per-ticker by design — corruption is a snapshot-level
    signal, not a population statistic like Sloan / NSI.
    """
    flags = compute_risk_flags(
        {"CORRUPT": _corrupt_snap(), "HEALTHY": _snap()}
    )
    assert "data_quality_input_corruption" in flags["CORRUPT"]
    assert "data_quality_input_corruption" not in flags["HEALTHY"]
    assert flags["HEALTHY"] == []


# Audit #5 (pre-v1.0 stop-the-line) — three additional corruption patterns
# beyond the SPG-shape TBVPS-ceiling break:
#   D7: revenue < $50M  (XBRL tag mispick — AVB-style $7M "contract revenue")
#   D8: |NI| > |revenue| (HBAN-style partial-revenue tag with full NI)
#   D9: revenue > $50M + NI < revenue — healthy baseline


def test_D7_corruption_fires_for_implausibly_small_revenue():
    """AVB shipped with revenue=$7.1M (contract-only subset) before the
    audit. Threshold pegged at $50M — any S&P 500 company has at least
    $200M revenue; below $50M is a tag-pick bug not a real micro-cap.
    """
    avb_shape = _snap(revenue=7_135_000.0, net_income=1_212_000_000.0)
    flags = compute_risk_flags({"AVB": avb_shape})
    assert "data_quality_input_corruption" in flags["AVB"]


def test_D8_corruption_fires_when_ni_exceeds_revenue():
    """HBAN shipped with revenue=$1.68B (RevFromContract subset) and
    NI=$2.23B before the audit. NI > revenue is impossible except for
    rare one-time gains; the common cause is a partial-revenue tag with
    full NI.
    """
    hban_shape = _snap(
        revenue=1_683_000_000.0,
        net_income=2_225_000_000.0,
    )
    flags = compute_risk_flags({"HBAN": hban_shape})
    assert "data_quality_input_corruption" in flags["HBAN"]


def test_D9_corruption_silent_when_revenue_and_ni_plausible():
    """Baseline _snap has revenue=$100M, NI=$10M → above $50M floor +
    NI < revenue → no flag.
    """
    flags = compute_risk_flags({"NORMAL": _snap()})
    assert "data_quality_input_corruption" not in flags["NORMAL"]


def test_D10_corruption_silent_when_revenue_or_ni_missing():
    """Snapshot with revenue=None can't be evaluated for either new
    pattern; we defer to the existing TBVPS-only check rather than
    flagging on missing data.
    """
    incomplete = _snap(revenue=None, net_income=None)
    flags = compute_risk_flags({"INCOMPLETE": incomplete})
    assert "data_quality_input_corruption" not in flags["INCOMPLETE"]


def test_D11_corruption_fires_when_ni_negative_but_abs_exceeds_revenue():
    """Edge case: a huge one-time loss can produce |NI| > |revenue|.
    The guard catches this too — better to suppress a Top-5 entry than
    let a stale-tag bug masquerade as a real one-time loss.
    """
    snap_huge_loss = _snap(
        revenue=100_000_000.0,
        net_income=-150_000_000.0,
    )
    flags = compute_risk_flags({"LOSS": snap_huge_loss})
    assert "data_quality_input_corruption" in flags["LOSS"]


# ---------------------------------------------------------------------------
# Issue #176 — share_count_extraction_missing annotate (NEW 2026-05-21).
#
# Distinct from data_quality_input_corruption (VETO): this is an
# ANNOTATE-only detector that fires when the snapshot has revenue +
# total_assets populated but shares_outstanding is None. STZ 2026-05-14
# pattern. The veto path keeps its shares_outstanding=None silence
# contract (test_D3) — annotate-first per portable-annotate-before-veto.
# ---------------------------------------------------------------------------


def test_share_count_extraction_missing_fires_on_stz_signature():
    """STZ-shape: revenue + total_assets present, shares_outstanding=None."""
    stz_shape = _snap(
        revenue=9_755_500_000.0,
        total_assets=21_900_500_000.0,
        shares_outstanding=None,
    )
    assert check_share_count_extraction_missing(stz_shape) is True


def test_share_count_extraction_missing_silent_when_shares_present():
    """Healthy snapshot with positive shares_outstanding — must not fire."""
    healthy = _snap(shares_outstanding=180_000_000.0)
    assert check_share_count_extraction_missing(healthy) is False


def test_share_count_extraction_missing_silent_when_shares_zero():
    """``shares_outstanding == 0`` is a legitimate edge (not extraction
    failure) — the detector explicitly distinguishes ``None`` (missing)
    from ``0`` (zero). Mirrors the veto's silence contract on shares=0
    so the two pathways stay coherent."""
    snap_zero = _snap(shares_outstanding=0)
    assert check_share_count_extraction_missing(snap_zero) is False


def test_share_count_extraction_missing_silent_when_revenue_missing():
    """``revenue is None`` means the entire XBRL extraction broke (issue
    #15 throttling-resilience territory) — a different bug class. The
    annotate must not fire to keep its signal sharp."""
    full_blackout = _snap(
        revenue=None,
        net_income=None,
        total_assets=200_000_000.0,
        shares_outstanding=None,
    )
    assert check_share_count_extraction_missing(full_blackout) is False


def test_share_count_extraction_missing_silent_when_revenue_zero():
    """Revenue == 0 fails the ``> 0`` second-source confirmation guard."""
    no_rev = _snap(revenue=0.0, shares_outstanding=None)
    assert check_share_count_extraction_missing(no_rev) is False


def test_share_count_extraction_missing_silent_when_total_assets_missing():
    """``total_assets is None`` removes the balance-sheet second-source
    confirmation that the same filing extracted cleanly elsewhere; the
    detector defers to the "entire extraction broken" interpretation."""
    no_ta = _snap(
        revenue=100_000_000.0,
        total_assets=None,
        shares_outstanding=None,
    )
    assert check_share_count_extraction_missing(no_ta) is False


def test_share_count_extraction_missing_silent_when_total_assets_zero():
    """``total_assets == 0`` fails the ``> 0`` guard."""
    zero_ta = _snap(
        total_assets=0.0,
        shares_outstanding=None,
    )
    assert check_share_count_extraction_missing(zero_ta) is False


def test_share_count_extraction_missing_silent_when_snap_none():
    """Defensive: ``None`` snapshot (graceful-degradation path)."""
    assert check_share_count_extraction_missing(None) is False


def test_share_count_extraction_missing_asymmetry_none_vs_zero():
    """Lock the None-vs-0 asymmetry: ``shares_outstanding`` is the only
    input where ``None`` and ``0`` produce different decisions. This
    property is load-bearing — if it ever flips, the detector would
    start firing on legitimate edge cases (corporate restructurings,
    pre-IPO snapshots, etc.) that semantically differ from extraction
    failure."""
    same_other_fields = {
        "revenue": 100_000_000.0,
        "total_assets": 200_000_000.0,
    }
    none_shape = _snap(shares_outstanding=None, **same_other_fields)
    zero_shape = _snap(shares_outstanding=0, **same_other_fields)
    assert check_share_count_extraction_missing(none_shape) is True
    assert check_share_count_extraction_missing(zero_shape) is False


def test_dechow_veto_fires_above_strict_threshold():
    # PR 4.5a.3 — when dechow_f_scores is supplied and a ticker's F is
    # above DECHOW_VETO_THRESHOLD (= 3.0), the `dechow_manipulation_veto`
    # flag fires (active veto, suppresses entered_top5).
    snaps = {"AAA": _snap(), "BBB": _snap()}
    f_scores = {
        "AAA": DECHOW_VETO_THRESHOLD + 0.5,  # well above veto threshold
        "BBB": DECHOW_VETO_THRESHOLD - 0.5,  # below threshold (annotate band)
    }
    flags = compute_risk_flags(snaps, dechow_f_scores=f_scores)
    assert "dechow_manipulation_veto" in flags["AAA"]
    assert "dechow_manipulation_veto" not in flags["BBB"]


def test_dechow_veto_skipped_when_score_is_none():
    # compute_dechow_f returns f_score=None on any missing input —
    # tickers with incomplete fundamentals must not trigger the veto.
    snaps = {"X": _snap()}
    f_scores = {"X": None}
    flags = compute_risk_flags(snaps, dechow_f_scores=f_scores)
    assert "dechow_manipulation_veto" not in flags["X"]


def test_dechow_veto_strict_inequality():
    # Same `f > THRESHOLD` semantics as Beneish. Exact-threshold value
    # must NOT trigger.
    snaps = {"EDGE": _snap()}
    f_scores = {"EDGE": DECHOW_VETO_THRESHOLD}
    flags = compute_risk_flags(snaps, dechow_f_scores=f_scores)
    assert "dechow_manipulation_veto" not in flags["EDGE"]


def test_dechow_veto_disabled_when_dict_not_supplied():
    # Backward-compat: same pattern as Beneish + non_reliance — when
    # the inject dict is None, the veto path doesn't fire.
    snaps = {"T1": _snap()}
    flags = compute_risk_flags(snaps)
    assert "dechow_manipulation_veto" not in flags["T1"]


def test_dechow_and_beneish_vetos_independent():
    # Both vetoes can fire on the same ticker — they encode different
    # signals (Beneish 8-ratio model vs Dechow RSST-style accruals +
    # non-financial proxies). Confirming co-firing path.
    snaps = {"AAA": _snap()}
    m_scores = {"AAA": BENEISH_VETO_THRESHOLD + 0.5}
    f_scores = {"AAA": DECHOW_VETO_THRESHOLD + 0.5}
    flags = compute_risk_flags(
        snaps,
        beneish_m_scores=m_scores,
        dechow_f_scores=f_scores,
    )
    assert "beneish_manipulation_veto" in flags["AAA"]
    assert "dechow_manipulation_veto" in flags["AAA"]


# ---------------------------------------------------------------------------
# FDXF fix — empty-snap extension of ``fundamentals_unavailable`` veto.
#
# Three-way partition for the "no usable fundamentals" guard:
#   (a) snap is None → fundamentals_unavailable (original #487 OZK/PBF case)
#   (b) snap present but ALL core metrics None → fundamentals_unavailable (FDXF)
#   (c) snap present with normal data → no flag
#   (d) snap present with a corrupt present-field → data_quality_input_corruption
#       NOT fundamentals_unavailable (DQIC partition stays unchanged, test_D3 lock)
#
# The discriminator: "are there ANY usable fundamental fields?" (no →
# fundamentals_unavailable) vs "is a present field internally inconsistent?"
# (→ DQIC). The two are mutually exclusive by construction: DQIC requires a
# non-None numeric value; the empty-snap check requires ALL values to be None.
# ---------------------------------------------------------------------------


def _empty_snap() -> FundamentalsSnapshot:
    """Snapshot shaped like FDXF: ticker/cik present, ALL 34 metric fields None.

    Simulates a freshly spun-off company whose EDGAR CIK was resolved but
    which has filed no financial statements yet.  Every field in ALL_METRIC_KEYS
    remains at its default of None.
    """
    return FundamentalsSnapshot(ticker="FDXF", cik="0001234567")


def test_E1_fundamentals_unavailable_fires_when_snap_is_none():
    """Case (a): snap is None → fundamentals_unavailable, no DQIC.

    Original #487 OZK/PBF case.  Unchanged behaviour; re-pinned here as
    part of the 3-way partition lock so any future refactor can't regress
    Case (a) while fixing Case (b).
    """
    flags = compute_risk_flags({"OZK": None})
    assert "fundamentals_unavailable" in flags["OZK"]
    assert "data_quality_input_corruption" not in flags["OZK"]
    assert flags["OZK"] == ["fundamentals_unavailable"]


def test_E2_fundamentals_unavailable_fires_when_snap_present_but_all_null():
    """Case (b): snap is NOT None but every ALL_METRIC_KEYS field is None → fundamentals_unavailable.

    FDXF scenario: EDGAR returned a Company object (CIK resolved) but the
    freshly spun-off issuer has zero financial filings, so the snapshot
    carries no numeric data.  Without this fix the stock bypassed the
    ``snap is None`` guard and received a lean_bullish recommendation from
    neutral-50 pillar imputation.

    Assertions:
    - ``fundamentals_unavailable`` fires.
    - ``data_quality_input_corruption`` does NOT fire (DQIC requires a
      PRESENT field to evaluate — partition lock).
    - No other flags (the guard short-circuits the loop, same as Case a).
    """
    snap = _empty_snap()
    # Confirm the fixture is actually all-null (guards against helper drift).
    assert len(snap.missing_fields()) == len(ALL_METRIC_KEYS), (
        "Test fixture must have ALL metric fields null to simulate the FDXF empty-snap case"
    )
    flags = compute_risk_flags({"FDXF": snap})
    assert "fundamentals_unavailable" in flags["FDXF"], (
        "Empty-snap should fire fundamentals_unavailable (FDXF fix)"
    )
    assert "data_quality_input_corruption" not in flags["FDXF"], (
        "DQIC must NOT fire on an all-null snapshot (partition lock)"
    )
    assert flags["FDXF"] == ["fundamentals_unavailable"], (
        "Only fundamentals_unavailable should fire; loop short-circuits after the guard"
    )


def test_E3_fundamentals_unavailable_silent_for_normal_snap():
    """Case (c): snap present with normal data → fundamentals_unavailable does NOT fire.

    Confirms the fix doesn't widen the veto to any snapshot with some null
    fields — only a FULLY null snapshot triggers it.
    """
    flags = compute_risk_flags({"HEALTHY": _snap()})
    assert "fundamentals_unavailable" not in flags["HEALTHY"]


def test_E4_dqic_fires_not_fundamentals_unavailable_for_corrupt_present_field():
    """Case (d): snap present + corrupt field → DQIC fires, NOT fundamentals_unavailable.

    SPG-shape: $76B equity / 8K shares → TBVPS ≫ ceiling.  The snapshot
    has shares_outstanding present (just wrong), so DQIC fires and
    fundamentals_unavailable must NOT.  Partition is: field present but
    inconsistent → DQIC; field absent → fundamentals_unavailable.
    """
    corrupt = _snap(
        stockholders_equity=76_000_000_000.0,
        shares_outstanding=8_000.0,  # present but wrong
    )
    flags = compute_risk_flags({"SPG": corrupt})
    assert "data_quality_input_corruption" in flags["SPG"]
    assert "fundamentals_unavailable" not in flags["SPG"]


def test_E5_empty_snap_recommendation_is_cautious():
    """Empty-snap stock must derive recommendation=cautious via the flag.

    ``fundamentals_unavailable`` is in ``_CAUTIOUS_FORCING_RISK`` so
    ``derive_recommendation`` must return ``"cautious"`` regardless of
    composite (here set to the lean-bullish band to confirm the forcing
    override fires — the FDXF symptom was lean_bullish on composite ~51).
    """
    from compute.scoring.recommendation import LEAN_BULLISH_COMPOSITE_MIN, derive_recommendation

    rec = derive_recommendation(
        composite_score=LEAN_BULLISH_COMPOSITE_MIN + 5.0,
        risk_flags=["fundamentals_unavailable"],
        valuation_warnings=[],
        mos_pct=None,
    )
    assert rec == "cautious", (
        "Empty-snap ticker must receive recommendation=cautious via "
        "fundamentals_unavailable in _CAUTIOUS_FORCING_RISK"
    )


def test_E6_snapshot_has_no_usable_fundamentals_helper_true_for_empty():
    """Unit-test the helper predicate on the FDXF-shape fixture."""
    assert _snapshot_has_no_usable_fundamentals(_empty_snap()) is True


def test_E7_snapshot_has_no_usable_fundamentals_helper_false_for_normal():
    """Unit-test the helper predicate on a healthy snap (must not fire)."""
    assert _snapshot_has_no_usable_fundamentals(_snap()) is False


def test_E8_snapshot_has_no_usable_fundamentals_helper_false_for_partial():
    """Partial-data snap (only revenue non-None) → helper returns False.

    Conservatism invariant: ANY non-None field means the snapshot has at
    least some usable data and must NOT fire fundamentals_unavailable.
    """
    partial = FundamentalsSnapshot(
        ticker="PARTIAL", cik="0000000099", revenue=100_000_000.0
    )
    assert _snapshot_has_no_usable_fundamentals(partial) is False


def test_E9_empty_snap_does_not_co_fire_with_dqic():
    """Partition lock: an all-null snapshot can NEVER produce both
    fundamentals_unavailable AND data_quality_input_corruption in the
    same flag list.  They encode mutually exclusive input states.
    """
    snap = _empty_snap()
    flags = compute_risk_flags({"FDXF": snap})
    both_fire = (
        "fundamentals_unavailable" in flags["FDXF"]
        and "data_quality_input_corruption" in flags["FDXF"]
    )
    assert not both_fire, (
        "fundamentals_unavailable and data_quality_input_corruption must never "
        "co-fire on the same snapshot — they partition the input-absence vs "
        "field-present-but-corrupt cases."
    )
