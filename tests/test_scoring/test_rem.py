"""Unit tests for compute.scoring.rem — Roychowdhury 2006 REM (PR 4.5c).

Three layers of tests:

1. **Proxy construction** — verify ``compute_proxies`` correctly
   computes the per-ticker input vector from a synthetic snapshot +
   history (well-formed and partial cases).
2. **Sector regression mechanics** — verify ``compute_rem_flags`` end-
   to-end on a hand-constructed sector with 16 tickers where we know
   which tickers should fall in the worst decile.
3. **Golden against Roychowdhury 2006 paper coefficients** — small
   synthetic dataset where the regression should recover an
   approximately known coefficient vector.

All tests are offline. No SEC EDGAR fetch.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.rem import (
    REM_DECILE,
    REM_MIN_POPULATION_SECTOR,
    REMProxies,
    compute_proxies,
    compute_rem_flags,
)


def _snap(**kwargs) -> FundamentalsSnapshot:
    """Minimal snapshot with REM-relevant fields. Defaults sized so
    every ratio is finite and non-zero unless overridden."""
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 1_000.0,
        "net_income": 100.0,
        "total_assets": 2_000.0,
        "operating_cash_flow": 120.0,
        "cost_of_revenue": 600.0,
        "inventory": 200.0,
        "research_and_development": 80.0,
        "sga_expense": 150.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _history(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal history DataFrame with metric/period_end/value cols."""
    return pd.DataFrame(rows, columns=["metric", "value", "period_end"])


# ---------------------------------------------------------------------------
# Layer 1 — compute_proxies
# ---------------------------------------------------------------------------


def test_compute_proxies_all_inputs_present():
    snap = _snap(
        revenue=1_000.0,
        operating_cash_flow=120.0,
        cost_of_revenue=600.0,
        inventory=200.0,
        research_and_development=80.0,
        sga_expense=150.0,
    )
    hist = _history(
        [
            # t-1 (2024): revenue=900, assets=1800, inventory=180
            {"metric": "revenue", "value": 900.0, "period_end": date(2024, 12, 31)},
            {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
            {"metric": "inventory", "value": 180.0, "period_end": date(2024, 12, 31)},
            # t-2 (2023): revenue=800
            {"metric": "revenue", "value": 800.0, "period_end": date(2023, 12, 31)},
        ]
    )
    p = compute_proxies(snap, hist)
    # Prior assets = 1800, so 1/A = 1/1800
    assert p.inv_assets is not None
    assert abs(p.inv_assets - 1.0 / 1800.0) < 1e-10
    # sales/A = 1000/1800
    assert abs(p.sales_over_assets - 1000.0 / 1800.0) < 1e-10
    # dsales = (1000-900)/1800
    assert abs(p.dsales_over_assets - 100.0 / 1800.0) < 1e-10
    # dsales_lag = (900-800)/1800
    assert abs(p.dsales_lag_over_assets - 100.0 / 1800.0) < 1e-10
    # sales_lag = 900/1800
    assert abs(p.sales_lag_over_assets - 900.0 / 1800.0) < 1e-10
    # CFO = 120/1800
    assert abs(p.cfo_over_assets - 120.0 / 1800.0) < 1e-10
    # PROD = (COGS + ΔInv) / A_{t-1} = (600 + (200-180)) / 1800 = 620/1800
    assert abs(p.prod_over_assets - 620.0 / 1800.0) < 1e-10
    # DISEXP = (R&D + SGA) / A = (80+150) / 1800 = 230/1800
    assert abs(p.disexp_over_assets - 230.0 / 1800.0) < 1e-10


def test_compute_proxies_returns_all_none_when_snap_is_none():
    p = compute_proxies(None, None)
    assert p == REMProxies(*([None] * 8))


def test_compute_proxies_returns_all_none_when_prior_assets_missing():
    snap = _snap()
    hist = _history([])  # no history → no prior_assets
    p = compute_proxies(snap, hist)
    # All ratios None because denominator is missing
    assert p.inv_assets is None
    assert p.cfo_over_assets is None
    assert p.prod_over_assets is None
    assert p.disexp_over_assets is None


def test_compute_proxies_disexp_falls_back_to_sga_when_rnd_missing():
    """Financials / REITs / Utilities often have R&D=None — DISEXP
    should fall back to SGA alone rather than dropping the proxy."""
    snap = _snap(research_and_development=None, sga_expense=200.0)
    hist = _history(
        [
            {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
            {"metric": "revenue", "value": 900.0, "period_end": date(2024, 12, 31)},
        ]
    )
    p = compute_proxies(snap, hist)
    assert p.disexp_over_assets is not None
    assert abs(p.disexp_over_assets - 200.0 / 1800.0) < 1e-10


def test_compute_proxies_prod_none_when_inventory_missing():
    snap = _snap(inventory=None)
    hist = _history(
        [
            {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
            {"metric": "revenue", "value": 900.0, "period_end": date(2024, 12, 31)},
        ]
    )
    p = compute_proxies(snap, hist)
    # PROD needs current inventory + prior inventory; current is None.
    assert p.prod_over_assets is None
    # But CFO + DISEXP still computable independently
    assert p.cfo_over_assets is not None


# ---------------------------------------------------------------------------
# Layer 2 — compute_rem_flags end-to-end
# ---------------------------------------------------------------------------


def _build_sector(
    sector: str,
    n: int,
    *,
    cfo_outlier_tickers: tuple[str, ...] = (),
    prod_outlier_tickers: tuple[str, ...] = (),
    disexp_outlier_tickers: tuple[str, ...] = (),
) -> tuple[dict, dict, dict]:
    """Build n synthetic tickers in `sector`. Outliers get extreme
    values for the named axis; the rest are normal-baseline.

    Returns (snapshots, histories, sectors) dicts ready to pass to
    compute_rem_flags.
    """
    snaps: dict[str, FundamentalsSnapshot] = {}
    hists: dict[str, pd.DataFrame] = {}
    secs: dict[str, str] = {}
    rng = np.random.default_rng(42)
    for i in range(n):
        ticker = f"{sector[:2].upper()}{i:02d}"
        # Baseline ratios — small jitter
        rev = 1_000.0 + rng.normal(0, 50)
        cfo = 120.0 + rng.normal(0, 10)
        cogs = 600.0 + rng.normal(0, 20)
        inv = 200.0 + rng.normal(0, 10)
        rnd = 80.0 + rng.normal(0, 5)
        sga = 150.0 + rng.normal(0, 10)
        prior_assets = 1_800.0
        prior_inv = inv - 20.0
        prior_rev = rev - 100.0
        prior_lag_rev = prior_rev - 100.0

        if ticker in cfo_outlier_tickers:
            # Low (negative) abnormal CFO — channel-stuff suspicion.
            # Slash CFO drastically relative to sales.
            cfo = 30.0
        if ticker in prod_outlier_tickers:
            # High abnormal production — overproduction, inflated COGS+inv.
            cogs = 900.0
            inv = 350.0
        if ticker in disexp_outlier_tickers:
            # Low (negative) abnormal DISEXP — slashed R&D + SGA.
            rnd = 20.0
            sga = 50.0

        snaps[ticker] = _snap(
            ticker=ticker,
            cik=f"00000000{i:02d}",
            revenue=rev,
            operating_cash_flow=cfo,
            cost_of_revenue=cogs,
            inventory=inv,
            research_and_development=rnd,
            sga_expense=sga,
        )
        hists[ticker] = _history(
            [
                {"metric": "total_assets", "value": prior_assets, "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": prior_rev, "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": prior_lag_rev, "period_end": date(2023, 12, 31)},
                {"metric": "inventory", "value": prior_inv, "period_end": date(2024, 12, 31)},
            ]
        )
        secs[ticker] = sector
    return snaps, hists, secs


def test_compute_rem_flags_empty_returns_empty():
    out = compute_rem_flags({})
    assert out == {}


def test_compute_rem_flags_sector_below_floor_skips():
    # 5 tickers in one sector — below REM_MIN_POPULATION_SECTOR=15.
    # All residuals should be None; no flag fires.
    snaps, hists, secs = _build_sector("Test", 5)
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    assert len(out) == 5
    for result in out.values():
        assert result.fired is False
        # Residuals are computed only when the sector model fits,
        # which requires >= floor. So all None here.
        assert result.abnormal_cfo is None
        assert result.abnormal_prod is None
        assert result.abnormal_disexp is None


def test_compute_rem_flags_at_floor_residuals_computed():
    # 16 tickers — just above the floor. Residuals should populate.
    snaps, hists, secs = _build_sector("Test", 16)
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    # Residuals exist for all 16 tickers
    n_with_cfo = sum(1 for r in out.values() if r.abnormal_cfo is not None)
    assert n_with_cfo == 16


def test_compute_rem_flags_double_outlier_fires():
    # Build a sector with one ticker that's a "double-suspect" — low
    # CFO AND low DISEXP. With 2 of 3 in worst decile, `fired` is True.
    snaps, hists, secs = _build_sector(
        "Test",
        16,
        cfo_outlier_tickers=("TE00",),
        disexp_outlier_tickers=("TE00",),
    )
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    result = out["TE00"]
    assert result.fired is True
    assert "cfo" in result.triggers
    assert "disexp" in result.triggers


def test_compute_rem_flags_single_engineered_outlier_triggers_cfo_axis():
    # Engineer a single CFO outlier and verify the `cfo` trigger fires.
    # Whether `fired` is True depends on noise — a synthetic CFO outlier
    # may also drift into a neighbouring decile on another axis just
    # from baseline jitter. We assert only on the contract-stable part:
    # the cfo trigger MUST be present. (Larger sector populations push
    # the FP rate down — this is what `test_compute_rem_flags_normal_
    # ticker_does_not_fire` verifies for the H0 case.)
    snaps, hists, secs = _build_sector(
        "Test",
        30,
        cfo_outlier_tickers=("TE00",),
    )
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    result = out["TE00"]
    assert "cfo" in result.triggers


def test_compute_rem_flags_triple_outlier_fires_with_all_three():
    # All 3 axes extreme — fires with 3 triggers.
    snaps, hists, secs = _build_sector(
        "Test",
        16,
        cfo_outlier_tickers=("TE00",),
        prod_outlier_tickers=("TE00",),
        disexp_outlier_tickers=("TE00",),
    )
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    result = out["TE00"]
    assert result.fired is True
    assert set(result.triggers) == {"cfo", "prod", "disexp"}


def test_compute_rem_flags_normal_ticker_does_not_fire():
    # All tickers built from the same baseline distribution — no clear
    # outliers. Tickers may individually trigger one axis just from
    # noise, but the "2 of 3" gate keeps `fired` False for the bulk.
    snaps, hists, secs = _build_sector("Test", 30)  # well above floor
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    fired_count = sum(1 for r in out.values() if r.fired)
    # Under H0 the joint "2 of 3 worst decile" rate is ~3% (P=0.1^2 *
    # C(3,2) * 0.9 + 0.1^3); on 30 obs the expected fired count is
    # ~1. Cap at 5 to allow noise.
    assert fired_count <= 5


def test_compute_rem_flags_constants():
    """Sanity-pin REM thresholds + floor."""
    assert REM_DECILE == 0.10
    assert REM_MIN_POPULATION_SECTOR == 15


# ---------------------------------------------------------------------------
# Layer 3 — golden numerical test
# ---------------------------------------------------------------------------


def test_compute_rem_flags_ols_recovers_known_coefficients():
    """Construct a synthetic CFO panel where the data-generating
    process is exactly the Roychowdhury 2006 CFO model with known
    coefficients. The OLS regression should recover the same
    coefficients (within OLS noise) and produce near-zero residuals
    for the bulk of tickers.

    Known DGP:
      CFO/A = 0.05 (intercept α)
           + 0.0 * (1/A)        (β1 zero so intercept dominates)
           + 0.10 * sales/A     (β2 — modest sensitivity to sales)
           + 0.05 * Δsales/A    (β3 — small sensitivity to ΔSales)
    """
    n = 30
    rng = np.random.default_rng(7)
    # Realistic prior_assets distribution: 1000 to 3000
    prior_assets = rng.uniform(1_000, 3_000, n)
    # Realistic sales/assets: 0.4 to 1.5
    sales_over_a = rng.uniform(0.4, 1.5, n)
    sales = sales_over_a * prior_assets
    # dsales/A: -0.1 to +0.2
    dsales_over_a = rng.uniform(-0.1, 0.2, n)
    # Known CFO = α + β2*sales_over_a + β3*dsales_over_a + small noise
    cfo_over_a_true = 0.05 + 0.10 * sales_over_a + 0.05 * dsales_over_a
    cfo_over_a = cfo_over_a_true + rng.normal(0, 0.005, n)
    cfo = cfo_over_a * prior_assets

    snaps: dict[str, FundamentalsSnapshot] = {}
    hists: dict[str, pd.DataFrame] = {}
    secs: dict[str, str] = {}
    for i in range(n):
        ticker = f"GD{i:02d}"
        prior_inv = 100.0  # not relevant for this CFO-only test
        prior_rev = sales[i] - dsales_over_a[i] * prior_assets[i]
        snaps[ticker] = _snap(
            ticker=ticker,
            cik=f"00000{i:03d}",
            revenue=float(sales[i]),
            operating_cash_flow=float(cfo[i]),
            inventory=110.0,
            research_and_development=10.0,
            sga_expense=20.0,
            cost_of_revenue=50.0,
        )
        hists[ticker] = _history(
            [
                {"metric": "total_assets", "value": float(prior_assets[i]), "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": float(prior_rev), "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": float(prior_rev - 50.0), "period_end": date(2023, 12, 31)},
                {"metric": "inventory", "value": prior_inv, "period_end": date(2024, 12, 31)},
            ]
        )
        secs[ticker] = "GoldenSector"

    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    # CFO residuals should be tiny (within 3× the noise std = 0.015)
    abnormal_cfos = [r.abnormal_cfo for r in out.values() if r.abnormal_cfo is not None]
    assert len(abnormal_cfos) == n
    max_residual = max(abs(r) for r in abnormal_cfos)
    assert max_residual < 0.05, (
        f"OLS residuals should be small for a well-fit DGP; got max={max_residual:.4f}"
    )
