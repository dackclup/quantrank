"""Coverage tests for compute.scoring.rem — targeting uncovered branches.

Uncovered lines/branches (baseline 87%):
  166     _prior_year_value: 'metric'/'period_end' missing from columns
  168     _prior_year_value: rows for the metric are empty
  178     _prior_year_value: all candidates have period_end > cutoff
  185     _prior_year_value: val is None
  188-189 _prior_year_value: TypeError / ValueError on float cast
  191     _prior_year_value: non-finite float
  219     compute_proxies: snap.latest_period_end is None
  235->238 compute_proxies: snap.revenue is None → sales_a None
  239->242 compute_proxies: prior_sales is None → dsales_a None
  243->250 compute_proxies: dsales_lag_a computation guards
  251->255 compute_proxies: sales_lag_a None when prior_sales None
  256->263 compute_proxies: CFO is None
  281->289 compute_proxies: DISEXP both rnd and sga None
  341     _fit_one_model: underdetermined (shape[0] <= shape[1])
  344-346 _fit_one_model: LinAlgError path
  359     _fit_sector_models: ticker with no sector
  368->367 _fit_sector_models: no cfo_y data collected
  388->387 compute_rem_flags pass-2: sector not in sector_models
  410->409 compute_rem_flags pass-2: prod model guard
  439     _residual: actual is None
  442     _residual: inputs contain None
  471     compute_rem_flags: ticker with no sector (pass 2 skip)
  473     compute_rem_flags: sec not in sector_models (pass 2 skip)
  490     compute_rem_flags: prod_r path (residual stored)
  582     _within_sector_decile: empty residuals → {}
  590->588 _within_sector_decile: sector group below floor → skipped
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.rem import (
    REM_MIN_POPULATION_SECTOR,
    REMProxies,
    _fit_one_model,
    _prior_year_value,
    _residual,
    _within_sector_decile,
    compute_proxies,
    compute_rem_flags,
)

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _snap(**kwargs) -> FundamentalsSnapshot:
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
    return pd.DataFrame(rows, columns=["metric", "value", "period_end"])


def _standard_history() -> pd.DataFrame:
    return _history(
        [
            {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
            {"metric": "revenue", "value": 900.0, "period_end": date(2024, 12, 31)},
            {"metric": "revenue", "value": 800.0, "period_end": date(2023, 12, 31)},
            {"metric": "inventory", "value": 180.0, "period_end": date(2024, 12, 31)},
        ]
    )


# ---------------------------------------------------------------------------
# _prior_year_value: branch coverage (lines 166, 168, 178, 185, 188-189, 191)
# ---------------------------------------------------------------------------


def test_prior_year_value_history_missing_columns_returns_none():
    """history has no 'metric' or 'period_end' columns → None (line 166)."""
    hist = pd.DataFrame({"foo": [1.0], "bar": ["2024-12-31"]})
    result = _prior_year_value(hist, "revenue", date(2025, 12, 31))
    assert result is None


def test_prior_year_value_metric_not_in_rows_returns_none():
    """Metric name not present → rows.empty → None (line 168)."""
    hist = _history(
        [{"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)}]
    )
    result = _prior_year_value(hist, "revenue", date(2025, 12, 31))
    assert result is None


def test_prior_year_value_all_candidates_after_cutoff_returns_none():
    """All rows have period_end > cutoff (snap_period_end - 180d) → None (line 178)."""
    period = date(2025, 12, 31)
    # period_end 2025-09-30 is only ~90 days before cutoff (2025-06-04) — within 180d
    hist = _history(
        [{"metric": "revenue", "value": 900.0, "period_end": date(2025, 9, 30)}]
    )
    result = _prior_year_value(hist, "revenue", period)
    assert result is None


def test_prior_year_value_val_is_none_returns_none():
    """value field is None → return None (line 185)."""
    hist = _history(
        [{"metric": "revenue", "value": None, "period_end": date(2024, 12, 31)}]
    )
    result = _prior_year_value(hist, "revenue", date(2025, 12, 31))
    assert result is None


def test_prior_year_value_val_non_castable_returns_none():
    """value cannot be cast to float → TypeError path → None (lines 188-189)."""
    hist = _history(
        [{"metric": "revenue", "value": "not-a-number", "period_end": date(2024, 12, 31)}]
    )
    result = _prior_year_value(hist, "revenue", date(2025, 12, 31))
    assert result is None


def test_prior_year_value_val_inf_returns_none():
    """value is inf → non-finite → None (line 191)."""
    hist = _history(
        [{"metric": "revenue", "value": float("inf"), "period_end": date(2024, 12, 31)}]
    )
    result = _prior_year_value(hist, "revenue", date(2025, 12, 31))
    assert result is None


def test_prior_year_value_val_nan_returns_none():
    """value is NaN → non-finite → None (line 191)."""
    hist = _history(
        [{"metric": "revenue", "value": float("nan"), "period_end": date(2024, 12, 31)}]
    )
    result = _prior_year_value(hist, "revenue", date(2025, 12, 31))
    assert result is None


# ---------------------------------------------------------------------------
# compute_proxies: branch coverage (lines 219, 235->238, 239->242, 243->250,
#                  251->255, 256->263, 281->289)
# ---------------------------------------------------------------------------


def test_compute_proxies_returns_none_when_period_is_none():
    """snap.latest_period_end is None → all fields None (line 219)."""
    snap = _snap(latest_period_end=None)
    p = compute_proxies(snap, _standard_history())
    assert p.inv_assets is None
    assert p.cfo_over_assets is None


def test_compute_proxies_sales_a_none_when_revenue_none():
    """snap.revenue is None → sales_a stays None (branch 235->238)."""
    snap = _snap(revenue=None)
    hist = _standard_history()
    p = compute_proxies(snap, hist)
    assert p.sales_over_assets is None
    # dsales also None since sales_a is None
    assert p.dsales_over_assets is None


def test_compute_proxies_dsales_none_when_prior_sales_none():
    """prior_sales is None → dsales_a stays None (branch 239->242)."""
    snap = _snap(revenue=1_000.0)
    # history has assets but NO revenue row → prior_sales=None
    hist = _history(
        [
            {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
        ]
    )
    p = compute_proxies(snap, hist)
    # sales_a is set (snap.revenue present), but dsales_a is None
    assert p.sales_over_assets is not None
    assert p.dsales_over_assets is None


def test_compute_proxies_sales_lag_none_when_prior_sales_none():
    """prior_sales is None → sales_lag_a stays None (branch 251->255)."""
    snap = _snap(revenue=1_000.0)
    hist = _history(
        [
            {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
        ]
    )
    p = compute_proxies(snap, hist)
    assert p.sales_lag_over_assets is None


def test_compute_proxies_cfo_none_when_operating_cash_flow_none():
    """snap.operating_cash_flow is None → cfo_a stays None (branch 256->263)."""
    snap = _snap(operating_cash_flow=None)
    p = compute_proxies(snap, _standard_history())
    assert p.cfo_over_assets is None


def test_compute_proxies_disexp_none_when_both_rnd_and_sga_none():
    """Both R&D and SGA are None → disexp_a stays None (branch 281->289)."""
    snap = _snap(research_and_development=None, sga_expense=None)
    p = compute_proxies(snap, _standard_history())
    assert p.disexp_over_assets is None


# ---------------------------------------------------------------------------
# _fit_one_model: underdetermined (line 341), LinAlgError (lines 344-346)
# ---------------------------------------------------------------------------


def test_fit_one_model_underdetermined_returns_none():
    """When n == k (shape[0] <= shape[1]) → underdetermined → None (line 341)."""
    # n=16 observations, but x has 15 features → n <= k+1 (with intercept col)
    n = REM_MIN_POPULATION_SECTOR + 1  # 16 — just above floor
    y = [float(i) for i in range(n)]
    # 16 features → x_with_intercept has 17 columns vs 16 rows
    x = [[float(j) for j in range(n)] for _ in range(n)]
    result = _fit_one_model(y, x)
    assert result is None


def test_fit_one_model_below_floor_returns_none():
    """n < REM_MIN_POPULATION_SECTOR → early return None."""
    y = [1.0, 2.0]
    x = [[0.5, 0.1], [0.6, 0.2]]
    result = _fit_one_model(y, x)
    assert result is None


def test_fit_one_model_linAlgError_returns_none():
    """LinAlgError during lstsq → log warning + return None (lines 344-346)."""
    n = REM_MIN_POPULATION_SECTOR + 5  # 20 > floor
    y = [1.0] * n
    x = [[1.0] for _ in range(n)]
    with patch("numpy.linalg.lstsq", side_effect=np.linalg.LinAlgError("singular")):
        result = _fit_one_model(y, x)
    assert result is None


# ---------------------------------------------------------------------------
# _fit_sector_models: ticker with no sector (line 359)
# ---------------------------------------------------------------------------


def test_fit_sector_models_ticker_without_sector_is_skipped():
    """Ticker absent from `sectors` dict → skipped, no KeyError (line 359)."""
    from compute.scoring.rem import _fit_sector_models

    proxies = {
        "UNKNOWN": REMProxies(
            cfo_over_assets=0.05,
            prod_over_assets=0.3,
            disexp_over_assets=0.1,
            inv_assets=0.001,
            sales_over_assets=0.5,
            dsales_over_assets=0.05,
            dsales_lag_over_assets=0.04,
            sales_lag_over_assets=0.48,
        )
    }
    sectors: dict[str, str] = {}  # UNKNOWN has no sector
    result = _fit_sector_models(proxies, sectors)
    # No sector keys in output since the only ticker was skipped
    assert result == {}


# ---------------------------------------------------------------------------
# _residual: actual is None (line 439), inputs contain None (line 442)
# ---------------------------------------------------------------------------


def test_residual_returns_none_when_actual_is_none():
    """actual is None → return None (line 439)."""
    coefs = np.array([0.1, 0.2, 0.3])
    result = _residual(None, [0.5, 0.6], coefs)
    assert result is None


def test_residual_returns_none_when_coefs_is_none():
    """coefs is None → return None (line 439)."""
    result = _residual(0.5, [0.5, 0.6], None)
    assert result is None


def test_residual_returns_none_when_inputs_contain_none():
    """Any None in inputs → return None (line 442)."""
    coefs = np.array([0.1, 0.2, 0.3])
    result = _residual(0.5, [0.5, None], coefs)
    assert result is None


def test_residual_shape_mismatch_returns_none():
    """Shape mismatch between [1]+inputs and coefs → return None."""
    # coefs has 4 elements; x=[1,a,b] has 3
    coefs = np.array([0.1, 0.2, 0.3, 0.4])
    result = _residual(0.5, [0.5, 0.6], coefs)
    assert result is None


def test_residual_correct_computation():
    """Verify residual = actual - predicted for a trivial model."""
    # coefs = [intercept, beta] = [0.1, 0.5]
    # predicted = 0.1*1 + 0.5*0.4 = 0.1 + 0.2 = 0.3
    # actual = 0.5 → residual = 0.2
    coefs = np.array([0.1, 0.5])
    result = _residual(0.5, [0.4], coefs)
    assert result is not None
    assert abs(result - 0.2) < 1e-10


# ---------------------------------------------------------------------------
# compute_rem_flags: pass-2 skip when ticker has no sector (lines 471, 473)
# ---------------------------------------------------------------------------


def test_compute_rem_flags_ticker_without_sector_gets_none_residuals():
    """Ticker absent from sectors dict → residuals None in result (line 471)."""
    snap = _snap()
    out = compute_rem_flags({"TST": snap}, histories={"TST": _standard_history()}, sectors={})
    result = out["TST"]
    assert result.abnormal_cfo is None
    assert result.abnormal_prod is None
    assert result.abnormal_disexp is None
    assert result.fired is False


def test_compute_rem_flags_ticker_sector_not_in_models_gets_none_residuals():
    """Ticker has a sector but it's not in sector_models → skip residual (line 473).

    This happens when the sector is below REM_MIN_POPULATION_SECTOR so no model is fit.
    The ticker still has a sector label but the sector_models dict won't contain it.
    """
    snap = _snap()
    # Only 1 ticker in sector → well below floor → no model fit
    out = compute_rem_flags(
        {"TST": snap},
        histories={"TST": _standard_history()},
        sectors={"TST": "SmallSector"},
    )
    result = out["TST"]
    assert result.abnormal_cfo is None
    assert result.abnormal_prod is None
    assert result.abnormal_disexp is None
    assert result.fired is False


# ---------------------------------------------------------------------------
# compute_rem_flags: prod_r stored path (line 490)
# ---------------------------------------------------------------------------


def _build_sector_with_prod(n: int = 20) -> tuple[dict, dict, dict]:
    """Build n tickers with full production model inputs."""
    snaps: dict[str, FundamentalsSnapshot] = {}
    hists: dict[str, pd.DataFrame] = {}
    secs: dict[str, str] = {}
    rng = np.random.default_rng(99)
    for i in range(n):
        ticker = f"PR{i:02d}"
        rev = 1_000.0 + rng.normal(0, 50)
        cfo = 120.0 + rng.normal(0, 10)
        cogs = 600.0 + rng.normal(0, 20)
        inv = 200.0 + rng.normal(0, 10)
        rnd = 80.0 + rng.normal(0, 5)
        sga = 150.0 + rng.normal(0, 10)
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
                {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": rev - 100.0, "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": rev - 200.0, "period_end": date(2023, 12, 31)},
                {"metric": "inventory", "value": inv - 20.0, "period_end": date(2024, 12, 31)},
            ]
        )
        secs[ticker] = "TechSector"
    return snaps, hists, secs


def test_compute_rem_flags_prod_residuals_are_computed():
    """When all prod inputs present and sector >= floor, prod_r stored (line 490)."""
    snaps, hists, secs = _build_sector_with_prod(n=20)
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    n_with_prod = sum(1 for r in out.values() if r.abnormal_prod is not None)
    assert n_with_prod == 20


# ---------------------------------------------------------------------------
# _within_sector_decile: empty residuals (line 582), below floor (line 590->588)
# ---------------------------------------------------------------------------


def test_within_sector_decile_empty_residuals_returns_empty():
    """Empty residuals dict → empty output dict (line 582)."""
    result = _within_sector_decile({}, {}, 0.10)
    assert result == {}


def test_within_sector_decile_sector_below_floor_excluded():
    """Sector with < REM_MIN_POPULATION_SECTOR tickers is excluded (line 590->588)."""
    # Build 5 residuals in one sector (below floor of 15)
    residuals = {f"T{i}": float(i) for i in range(5)}
    sectors = {f"T{i}": "SmallSector" for i in range(5)}
    result = _within_sector_decile(residuals, sectors, 0.10)
    # SmallSector has 5 tickers < 15 floor → should NOT appear in output
    assert "SmallSector" not in result
    assert result == {}


def test_within_sector_decile_sector_above_floor_included():
    """Sector with >= REM_MIN_POPULATION_SECTOR tickers is included."""
    n = REM_MIN_POPULATION_SECTOR + 1  # 16
    residuals = {f"T{i}": float(i) for i in range(n)}
    sectors = {f"T{i}": "LargeSector" for i in range(n)}
    result = _within_sector_decile(residuals, sectors, 0.10)
    assert "LargeSector" in result
    # 10th percentile of 0..15 = 1.5
    assert result["LargeSector"] == pytest.approx(1.5, abs=0.01)


# ---------------------------------------------------------------------------
# _fit_sector_models: no valid cfo data collected (branch 368->367)
# ---------------------------------------------------------------------------


def test_fit_sector_models_no_valid_cfo_data_produces_none_cfo_coefs():
    """All tickers in sector have cfo_over_assets=None → cfo_coefs=None (branch 368->367)."""
    from compute.scoring.rem import _fit_sector_models

    n = REM_MIN_POPULATION_SECTOR + 5  # 20 — above floor
    proxies: dict[str, REMProxies] = {}
    sectors: dict[str, str] = {}
    for i in range(n):
        ticker = f"ZZ{i:02d}"
        proxies[ticker] = REMProxies(
            cfo_over_assets=None,  # missing for all tickers
            prod_over_assets=0.3,
            disexp_over_assets=0.1,
            inv_assets=0.001,
            sales_over_assets=0.5,
            dsales_over_assets=0.05,
            dsales_lag_over_assets=0.04,
            sales_lag_over_assets=0.48,
        )
        sectors[ticker] = "TestSec"
    result = _fit_sector_models(proxies, sectors)
    assert "TestSec" in result
    assert result["TestSec"].cfo_coefs is None
    # n_cfo should be 0
    assert result["TestSec"].n_cfo == 0


# ---------------------------------------------------------------------------
# compute_rem_flags pass-2: sector not in sector_models (branches 388->387, 410->409)
# ---------------------------------------------------------------------------


def test_compute_rem_flags_no_prod_inputs_all_prod_residuals_none():
    """All prod inputs missing → prod_coefs=None → prod residuals None for all."""
    n = REM_MIN_POPULATION_SECTOR + 5  # 20
    snaps: dict[str, FundamentalsSnapshot] = {}
    hists: dict[str, pd.DataFrame] = {}
    secs: dict[str, str] = {}
    rng = np.random.default_rng(77)
    for i in range(n):
        ticker = f"NP{i:02d}"
        rev = 1_000.0 + rng.normal(0, 50)
        snaps[ticker] = _snap(
            ticker=ticker,
            cik=f"0000000{i:03d}",
            revenue=rev,
            operating_cash_flow=120.0,
            cost_of_revenue=None,  # makes prod_over_assets None for all
            inventory=None,        # also makes prod_over_assets None
            research_and_development=80.0,
            sga_expense=150.0,
        )
        hists[ticker] = _history(
            [
                {"metric": "total_assets", "value": 1_800.0, "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": rev - 100.0, "period_end": date(2024, 12, 31)},
                {"metric": "revenue", "value": rev - 200.0, "period_end": date(2023, 12, 31)},
            ]
        )
        secs[ticker] = "NoProdSector"
    out = compute_rem_flags(snaps, histories=hists, sectors=secs)
    # All prod residuals should be None since prod_coefs is None
    for result in out.values():
        assert result.abnormal_prod is None
