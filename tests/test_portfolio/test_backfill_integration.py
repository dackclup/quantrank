"""End-to-end wiring test for the PR-2b backfill orchestrator (synthetic data).

Runs ``run_backfill`` over a 3-ticker synthetic universe with mocked data
sources (universe / fundamentals_history / prices) but the REAL pillar pipeline,
composite, selection, inverse-vol weighting, NAV, and ``members_at`` — so the
integration the dev sandbox otherwise can't exercise (no caches / network) is
validated offline. Catches the wiring bugs the methodology-scientist flagged
(synthetic-snapshot field mapping, filed<=T history frame, price-at-T) by
asserting the orchestrator produces a well-formed ``backtest_pit.json``.
"""
from __future__ import annotations

import json
from datetime import date
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from scripts import backfill_portfolio_pit as bf

# Broad enough metric set that most pillars compute a real (non-neutral) score.
_METRICS = {
    "revenue": 100.0, "net_income": 10.0, "gross_profit": 40.0, "operating_income": 15.0,
    "cost_of_revenue": 60.0, "operating_cash_flow": 12.0, "capex": -3.0,
    "total_assets": 200.0, "total_liabilities": 120.0, "stockholders_equity": 80.0,
    "cash": 20.0, "current_assets": 60.0, "current_liabilities": 40.0,
    "long_term_debt": 50.0, "shares_outstanding": 5.0,
    "depreciation_and_amortization": 5.0, "interest_expense": 2.0,
    "inventory": 15.0, "accounts_receivable": 10.0,
}
_FILINGS = [(2020, "2021-02-15"), (2021, "2022-02-15"), (2022, "2023-02-15"), (2023, "2024-02-15")]


def _annual_history(scale: float) -> pd.DataFrame:
    rows = []
    for fy, filed in _FILINGS:
        growth = 1.0 + 0.10 * (fy - 2020)
        for metric, base in _METRICS.items():
            rows.append(
                {
                    "fiscal_year": fy,
                    "metric": metric,
                    "value": float(base * scale * growth),
                    "period_end": date(fy, 12, 31),
                    "filing_date": date.fromisoformat(filed),
                    "form_type": "10-K",
                }
            )
    return pd.DataFrame(rows)


def _prices(seed: int) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", "2024-06-30")
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx))))
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Adj Close": close, "Volume": 1.0e6},
        index=idx,
    )


@pytest.fixture
def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "AAA", "name": "Alpha", "sector": "Information Technology", "sub_industry": "x", "cik": "1"},
            {"ticker": "BBB", "name": "Beta", "sector": "Health Care", "sub_industry": "y", "cik": "2"},
            {"ticker": "CCC", "name": "Gamma", "sector": "Financials", "sub_industry": "z", "cik": "3"},
        ]
    )


def test_run_backfill_produces_wellformed_artifact(tmp_path, _universe) -> None:
    scale_by_cik = {"1": 1.0, "2": 1.4, "3": 0.7}

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(scale_by_cik.get(cik, 1.0))),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path)

    assert out.exists()
    payload = json.loads(out.read_text())

    # shape
    assert set(payload) >= {"meta", "rebalances", "nav"}
    meta = payload["meta"]
    assert meta["rebalance_count"] == len(payload["rebalances"]) > 0
    assert meta["veto_layer_replayed"] is False
    assert meta["sector_from_today"] is True
    assert meta["headline_count"] == bf.HEADLINE_COUNT
    assert meta["disclaimer"].startswith("Illustrative backtest")
    assert meta["incomplete_membership_count"] == 0  # all dates in coverage

    # rebalances: holdings well-formed, weights ~sum to 1 over the FULL pick set
    for reb in payload["rebalances"]:
        assert reb["members_complete"] is True
        assert reb["holdings"]
        for h in reb["holdings"]:
            assert {"ticker", "composite_score", "sector", "weight"} <= set(h)
            assert 0.0 <= h["weight"] <= 1.0
        wsum = sum(h["weight"] for h in reb["holdings"])
        # per-holding weights are round(6) for JSON cleanliness; summing up to 10
        # of them accumulates at most ~10 * 5e-7 rounding error.
        assert wsum == pytest.approx(1.0, abs=1e-5)

    # NAV: present, aligned, net never above gross (cost drag), starts at base 100
    nav = payload["nav"]
    n = len(nav["dates"])
    assert n > 0
    assert len(nav["portfolio_gross"]) == len(nav["portfolio_net"]) == n
    assert nav["portfolio_gross"][0] == pytest.approx(100.0)
    assert nav["portfolio_net"][-1] <= nav["portfolio_gross"][-1] + 1e-9
    assert len(nav["portfolio_net_conservative"]) == n
    # conservative net (higher cost) <= regular net
    assert nav["portfolio_net_conservative"][-1] <= nav["portfolio_net"][-1] + 1e-9


def test_run_backfill_skips_incomplete_membership(tmp_path, _universe) -> None:
    """A pre-coverage window (before EARLIEST_EVENT_DATE) yields no trusted legs."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(1)),
    ):
        out = bf.run_backfill(date(2018, 1, 1), date(2019, 6, 1), data_dir=tmp_path)

    meta = json.loads(out.read_text())["meta"]
    # every quarterly leg in this window is pre-2020 -> is_complete False -> skipped
    assert meta["rebalance_count"] == 0
    assert meta["incomplete_membership_count"] > 0
