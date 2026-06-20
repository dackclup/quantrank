"""Coverage tests for compute.scoring.pillars — targeting uncovered branches.

Uncovered lines (baseline 88%):
  54-55,57  _safe: exception + None + non-finite returns math.nan
  66        _quality_metrics: None snapshot path
  86        _value_metrics: None snapshot path
  126       _health_metrics: None snapshot path
  140       _profitability_metrics: None snapshot path
  163       _technical_metrics: empty prices path
  180       _risk_metrics: None/empty prices path
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.pillars import (
    TickerInputs,
    _health_metrics,
    _profitability_metrics,
    _quality_metrics,
    _risk_metrics,
    _safe,
    _technical_metrics,
    _value_metrics,
    compute_all_pillars,
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
        "stockholders_equity": 800.0,
        "operating_income": 200.0,
        "long_term_debt": 500.0,
        "short_term_debt": 100.0,
        "gross_profit": 400.0,
        "cost_of_revenue": 600.0,
        "current_assets": 500.0,
        "current_liabilities": 250.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _prices(n: int = 300, daily_ret: float = 0.001) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = 100.0 * (1 + daily_ret) ** np.arange(n)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.02,
            "Low": closes * 0.98,
            "Close": closes,
            "Adj Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def _ticker_input(
    *,
    snapshot=None,
    prices=None,
    benchmark=None,
    sector="Information Technology",
    current_price=100.0,
) -> TickerInputs:
    return TickerInputs(
        snapshot=snapshot if snapshot is not None else _snap(),
        prices=prices if prices is not None else _prices(),
        benchmark_prices=benchmark,
        current_price=current_price,
        sector=sector,
    )


# ---------------------------------------------------------------------------
# _safe: exception + None + non-finite paths (lines 54-55, 57)
# ---------------------------------------------------------------------------


def test_safe_returns_nan_on_exception():
    def _raises():
        raise ValueError("boom")

    result = _safe(_raises)
    assert math.isnan(result)


def test_safe_returns_nan_when_fn_returns_none():
    result = _safe(lambda: None)
    assert math.isnan(result)


def test_safe_returns_nan_when_fn_returns_inf():
    result = _safe(lambda: float("inf"))
    assert math.isnan(result)


def test_safe_returns_nan_when_fn_returns_nan():
    result = _safe(lambda: float("nan"))
    assert math.isnan(result)


def test_safe_passes_args_through():
    result = _safe(lambda x, y: x + y, 3, 4)
    assert result == 7.0


# ---------------------------------------------------------------------------
# _quality_metrics: None snapshot → all NaN (line 66)
# ---------------------------------------------------------------------------


def test_quality_metrics_none_snapshot_all_nan():
    inp = TickerInputs(
        snapshot=None,
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _quality_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())
    assert set(metrics.keys()) == {"roe", "roic", "gross_profitability", "msci_q", "piotroski"}


# ---------------------------------------------------------------------------
# _value_metrics: None snapshot → all NaN (line 86)
# ---------------------------------------------------------------------------


def test_value_metrics_none_snapshot_all_nan():
    inp = TickerInputs(
        snapshot=None,
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _value_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())
    assert "pe" in metrics


# ---------------------------------------------------------------------------
# _health_metrics: None snapshot → all NaN (line 126)
# ---------------------------------------------------------------------------


def test_health_metrics_none_snapshot_all_nan():
    inp = TickerInputs(
        snapshot=None,
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _health_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())
    assert set(metrics.keys()) == {"current", "quick", "d_e", "ic", "altman_z"}


# ---------------------------------------------------------------------------
# _profitability_metrics: None snapshot → all NaN (line 140)
# ---------------------------------------------------------------------------


def test_profitability_metrics_none_snapshot_all_nan():
    inp = TickerInputs(
        snapshot=None,
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _profitability_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())
    assert "gm" in metrics


# ---------------------------------------------------------------------------
# _technical_metrics: empty prices → all NaN (line 163)
# ---------------------------------------------------------------------------


def test_technical_metrics_empty_prices_all_nan():
    inp = TickerInputs(
        snapshot=_snap(),
        prices=pd.DataFrame(),  # empty
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _technical_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())
    assert set(metrics.keys()) == {"rsi_dist50", "adx", "bb_pctb", "mfi"}


def test_technical_metrics_none_prices_all_nan():
    inp = TickerInputs(
        snapshot=_snap(),
        prices=None,  # None
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _technical_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())


# ---------------------------------------------------------------------------
# _risk_metrics: None/empty prices → all NaN (line 180)
# ---------------------------------------------------------------------------


def test_risk_metrics_empty_prices_all_nan():
    inp = TickerInputs(
        snapshot=_snap(),
        prices=pd.DataFrame(),  # empty
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _risk_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())
    assert set(metrics.keys()) == {"vol", "sharpe", "sortino", "calmar", "max_dd", "beta"}


def test_risk_metrics_none_prices_all_nan():
    inp = TickerInputs(
        snapshot=_snap(),
        prices=None,
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _risk_metrics(inp)
    assert all(math.isnan(v) for v in metrics.values())


def test_risk_metrics_beta_nan_when_no_benchmark():
    """beta stays NaN (not computed) when benchmark_prices is None."""
    inp = TickerInputs(
        snapshot=_snap(),
        prices=_prices(),
        benchmark_prices=None,  # no benchmark
        current_price=100.0,
        sector="Information Technology",
    )
    metrics = _risk_metrics(inp)
    assert math.isnan(metrics["beta"])


# ---------------------------------------------------------------------------
# compute_all_pillars: empty inputs → empty DataFrame
# ---------------------------------------------------------------------------


def test_compute_all_pillars_empty_inputs():
    out = compute_all_pillars({})
    assert out.empty


# ---------------------------------------------------------------------------
# Sector exclusions in _quality_metrics and _profitability_metrics
# ---------------------------------------------------------------------------


def test_quality_metrics_financials_excludes_roic_and_gross_profitability():
    """Financials sector → roic and gross_profitability excluded (NaN)."""
    inp = TickerInputs(
        snapshot=_snap(),
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Financials",
    )
    metrics = _quality_metrics(inp)
    assert math.isnan(metrics["roic"])
    assert math.isnan(metrics["gross_profitability"])


def test_profitability_metrics_financials_excludes_asset_turnover():
    """Financials sector → asset_turnover excluded (NaN)."""
    inp = TickerInputs(
        snapshot=_snap(),
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Financials",
    )
    metrics = _profitability_metrics(inp)
    assert math.isnan(metrics["asset_turnover"])


def test_value_metrics_financials_excludes_ev_ebitda():
    """Financials sector → ev_ebitda excluded (NaN)."""
    inp = TickerInputs(
        snapshot=_snap(ebitda=500.0),
        prices=_prices(),
        benchmark_prices=None,
        current_price=100.0,
        sector="Financials",
    )
    metrics = _value_metrics(inp)
    assert math.isnan(metrics["ev_ebitda"])
