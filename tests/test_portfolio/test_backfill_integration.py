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
    assert meta["default_count"] == bf.DEFAULT_COUNT
    assert meta["disclaimer"].startswith("Illustrative backtest")
    assert meta["incomplete_membership_count"] == 0  # all dates in coverage

    # rebalances: ranked holdings + per-count inverse-vol weights (each basket sums ~1)
    for reb in payload["rebalances"]:
        assert reb["members_complete"] is True
        assert reb["holdings"]
        for h in reb["holdings"]:
            assert {"ticker", "composite_score", "sector", "sigma_90d"} <= set(h)
        wbc = reb["weights_by_count"]
        assert wbc  # at least the count-"1" basket
        for n_str, wmap in wbc.items():
            assert wmap
            for w in wmap.values():
                assert 0.0 <= w <= 1.0
            # count-N basket weights <= N of the ranked holdings (fewer if the leg had
            # < N names with a computable sigma)
            assert len(wmap) <= int(n_str)
            # per-holding weights are round(6); summing <= 10 accrues at most ~5e-6
            assert sum(wmap.values()) == pytest.approx(1.0, abs=1e-5)

    # NAV: a daily series PER holding count, all aligned to the shared dates; within
    # each count net <= gross and conservative <= net (cost drag); base 100 at the start
    nav = payload["nav"]
    n_dates = len(nav["dates"])
    assert n_dates > 0
    assert nav["default_count"] == bf.DEFAULT_COUNT
    assert str(bf.DEFAULT_COUNT) in nav["by_count"]  # the slider's landing count
    assert isinstance(nav["benchmark"], dict)  # empty here (synthetic run, no benchmarks.json)
    for series in nav["by_count"].values():
        assert len(series["gross"]) == len(series["net"]) == len(series["net_conservative"]) == n_dates
        first_gross = next(v for v in series["gross"] if v is not None)
        assert first_gross == pytest.approx(100.0)  # rebased start (None-padded if late)
        g_last = next(v for v in reversed(series["gross"]) if v is not None)
        net_last = next(v for v in reversed(series["net"]) if v is not None)
        cons_last = next(v for v in reversed(series["net_conservative"]) if v is not None)
        assert net_last <= g_last + 1e-9
        assert cons_last <= net_last + 1e-9


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


def test_run_backfill_skips_sigma_empty_rebalance(tmp_path, _universe) -> None:
    """A trusted (members-complete) leg where NO pick has a computable 90d sigma is
    silently skipped at the `weights_by_count` empty -> `continue` gate: rebalance_count
    AND incomplete_membership_count are BOTH 0 — a path distinct from the is_complete=False
    skip (so an all-zero result isn't misread as a membership-coverage gap)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(1)),
        # full prices (pillars score normally) but no name yields a sigma -> every leg's
        # weights_by_count is empty -> the `continue` fires for all of them.
        mock.patch.object(bf, "trailing_return_sigma", return_value=None),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path)

    meta = json.loads(out.read_text())["meta"]
    assert meta["rebalance_count"] == 0          # every leg skipped at the sigma gate
    assert meta["incomplete_membership_count"] == 0  # NOT the membership-degraded path


def _bday_frame(prices: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2022-01-03", periods=len(prices))
    return pd.DataFrame({"Close": prices, "Adj Close": prices}, index=idx)


def test_assemble_nav_builds_one_aligned_series_per_count(tmp_path) -> None:
    """`_assemble_nav` emits a NAV per count N, all aligned to shared dates; N=1 tracks
    its single name and the down-name drags the N=2 blend below the all-up N=1 line."""
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),       # steadily up
        "BBB": _bday_frame([100.0 - 0.2 * i for i in range(120)]),  # steadily down
    }
    # two quarterly rebalances on real business days inside the price window
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}, 2: {"AAA": 0.5, "BBB": 0.5}}),
        ("2022-03-14", {1: {"AAA": 1.0}, 2: {"AAA": 0.6, "BBB": 0.4}}),
    ]
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert out["default_count"] == bf.DEFAULT_COUNT
    assert set(out["by_count"]) == {"1", "2"}
    nd = len(out["dates"])
    assert nd > 0
    for s in out["by_count"].values():
        assert len(s["gross"]) == len(s["net"]) == nd  # every count aligned to dates

    g1 = out["by_count"]["1"]["gross"]
    g2 = out["by_count"]["2"]["gross"]
    assert g1[0] == pytest.approx(100.0)          # rebased start
    assert g1[-1] > g1[0]                          # 100% of the up-name rises
    assert g2[-1] < g1[-1]                          # the down-name drags the blend


def test_assemble_nav_snaps_weekend_rebalance_to_trading_day(tmp_path) -> None:
    """A rebalance dated on a weekend still fires — snapped to the next trading day —
    rather than being silently dropped (build_portfolio_nav needs a date in the calendar)."""
    prices_by_ticker = {"AAA": _bday_frame([100.0 + i for i in range(60)])}
    # 2022-01-08 is a Saturday; the next trading day is Monday 2022-01-10
    rebalance_picks = [("2022-01-08", {1: {"AAA": 1.0}})]
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert out["by_count"]  # the leg was NOT dropped
    assert out["dates"][0] == "2022-01-10"  # snapped Sat -> Mon
    assert out["by_count"]["1"]["gross"][0] == pytest.approx(100.0)


def test_snap_to_trading_day_falls_back_to_last_when_date_is_past_all_prices() -> None:
    """A rebalance dated after the last available trading day snaps to that last day
    (price data ends before the rebalance) rather than returning None or raising."""
    trading_days = ["2022-01-03", "2022-01-04", "2022-01-05", "2022-01-06", "2022-01-07"]
    assert bf._snap_to_trading_day("2099-06-30", trading_days) == "2022-01-07"


def test_snap_to_trading_day_returns_none_on_empty_dates() -> None:
    """The documented `None only if empty` guard — no trading days to snap to."""
    assert bf._snap_to_trading_day("2022-01-03", []) is None
