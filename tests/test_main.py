"""Unit tests for compute.main cross-sectional builders.

These cover the helpers introduced in Phase 3c Step 7 to feed the
fair-price ensemble: ``_filing_lag``, ``_build_universe_metrics``,
``_build_peer_groupings``, ``_build_historical_metrics``, and the
per-history extractors ``_eps_3y_avg`` / ``_avg_3y_roe`` / ``_fcf_5y``.

The full ``run_weekly_compute`` orchestration is exercised by smoke /
integration tests with real data; these unit tests just lock the
contract of the cross-sectional builders so future refactors notice if
their input/output shapes change.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.main import (
    _avg_3y_roe,
    _build_historical_metrics,
    _build_peer_groupings,
    _build_universe_metrics,
    _eps_3y_avg,
    _fcf_5y,
    _filing_lag,
)


def _snap(**overrides) -> FundamentalsSnapshot:
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "stockholders_equity": 100.0,
        "shares_outstanding": 10.0,
        "eps_diluted": 5.0,
        "ebitda": 50.0,
        "long_term_debt": 20.0,
        "short_term_debt": 5.0,
        "cash": 10.0,
        "goodwill": 0.0,
        "intangibles_net": 0.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(overrides)
    return FundamentalsSnapshot(**defaults)


# -- _filing_lag --------------------------------------------------------------

def test_filing_lag_basic_arithmetic():
    snap = _snap(latest_filed_date=date(2026, 2, 1))
    assert _filing_lag(snap, asof=date(2026, 5, 1)) == 89


def test_filing_lag_none_when_snap_is_none():
    assert _filing_lag(None, asof=date(2026, 5, 1)) is None


def test_filing_lag_none_when_filed_date_missing():
    snap = _snap(latest_filed_date=None)
    assert _filing_lag(snap, asof=date(2026, 5, 1)) is None


# -- _build_universe_metrics --------------------------------------------------

def test_build_universe_metrics_all_three_ratios_computed():
    df = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "current_price": [100.0],
        }
    )
    snap = _snap(
        eps_diluted=5.0,
        stockholders_equity=200.0,
        shares_outstanding=10.0,  # bvps = 20 → P/B = 5
        ebitda=50.0,
        long_term_debt=20.0,
        short_term_debt=5.0,
        cash=10.0,
    )
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pe_ttm"] == 20.0  # 100/5
    assert metrics["AAA"]["pb_reported"] == 5.0  # 100/20
    # mc=1000, ev=1000+25-10=1015 → ev/ebitda = 20.30
    assert metrics["AAA"]["ev_ebitda_ttm"] == 20.30


def test_build_universe_metrics_negative_eps_yields_null_pe():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(eps_diluted=-1.0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pe_ttm"] is None


def test_build_universe_metrics_missing_snapshot_yields_all_null():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    metrics = _build_universe_metrics({"AAA": None}, df)
    assert metrics["AAA"] == {
        "pe_ttm": None, "pb_reported": None, "ev_ebitda_ttm": None,
    }


# -- _build_peer_groupings ----------------------------------------------------

def test_peer_groupings_split_by_sector_and_sub_industry():
    df = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "sector": ["Information Technology", "Information Technology",
                       "Financials", "Utilities"],
            "industry": ["Software", "Software", "Banks", "Electric Utilities"],
        }
    )
    by_sub, by_sector, broad_ex_fin_util = _build_peer_groupings(df)
    assert by_sub["Software"] == ["AAA", "BBB"]
    assert by_sub["Banks"] == ["CCC"]
    assert by_sector["Information Technology"] == ["AAA", "BBB"]
    assert by_sector["Financials"] == ["CCC"]
    assert by_sector["Utilities"] == ["DDD"]
    # broad excludes Financials + Utilities
    assert broad_ex_fin_util == ["AAA", "BBB"]


def test_peer_groupings_handles_missing_sub_industry():
    df = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "sector": ["Information Technology"],
            "industry": [None],
        }
    )
    by_sub, by_sector, broad = _build_peer_groupings(df)
    assert by_sub == {}
    assert by_sector == {"Information Technology": ["AAA"]}
    assert broad == ["AAA"]


# -- _eps_3y_avg --------------------------------------------------------------

def _hist(metric_values: dict[str, list[tuple[int, float]]]) -> pd.DataFrame:
    """Build a long-format fundamentals history DataFrame.

    metric_values: {metric_name: [(fiscal_year, value), ...]}
    """
    rows = []
    for metric, pairs in metric_values.items():
        for fy, v in pairs:
            rows.append({"metric": metric, "fiscal_year": fy, "value": v})
    return pd.DataFrame(rows)


def test_eps_3y_avg_uses_latest_three_years():
    hist = _hist({
        "eps_diluted": [(2021, 1.0), (2022, 2.0), (2023, 3.0),
                        (2024, 4.0), (2025, 5.0)],
    })
    # latest 3 = 2025, 2024, 2023 → mean = 4.0
    assert _eps_3y_avg(hist) == 4.0


def test_eps_3y_avg_returns_none_with_too_few_years():
    hist = _hist({"eps_diluted": [(2024, 1.0), (2025, 2.0)]})
    assert _eps_3y_avg(hist) is None


def test_eps_3y_avg_returns_none_for_empty_or_missing():
    assert _eps_3y_avg(None) is None
    assert _eps_3y_avg(pd.DataFrame()) is None


# -- _avg_3y_roe --------------------------------------------------------------

def test_avg_3y_roe_smoothed_ni_over_current_equity():
    hist = _hist({
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
    })
    snap = _snap(stockholders_equity=200.0)
    # avg NI = 20 → 20 / 200 = 0.10
    assert _avg_3y_roe(hist, snap) == 0.10


def test_avg_3y_roe_none_when_equity_non_positive():
    hist = _hist({"net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)]})
    assert _avg_3y_roe(hist, _snap(stockholders_equity=0.0)) is None
    assert _avg_3y_roe(hist, _snap(stockholders_equity=-50.0)) is None


def test_avg_3y_roe_none_when_history_short():
    hist = _hist({"net_income": [(2024, 10.0), (2025, 20.0)]})
    assert _avg_3y_roe(hist, _snap()) is None


# -- _fcf_5y ------------------------------------------------------------------

def test_fcf_5y_chronological_order_oldest_first():
    hist = _hist({
        "operating_cash_flow": [(2021, 100.0), (2022, 110.0), (2023, 120.0),
                                (2024, 130.0), (2025, 140.0)],
        "capex": [(2021, 30.0), (2022, 40.0), (2023, 50.0),
                  (2024, 60.0), (2025, 70.0)],
    })
    out = _fcf_5y(hist)
    assert out == [70.0, 70.0, 70.0, 70.0, 70.0]


def test_fcf_5y_uses_only_overlapping_years():
    hist = _hist({
        "operating_cash_flow": [(2023, 100.0), (2024, 110.0), (2025, 120.0)],
        "capex": [(2024, 40.0), (2025, 50.0)],
    })
    # Overlap = {2024, 2025} → [70, 70] (oldest → newest)
    out = _fcf_5y(hist)
    assert out == [70.0, 70.0]


def test_fcf_5y_takes_capex_absolute_value():
    """Some filings store capex as a negative outflow; the formula is OCF − |capex|."""
    hist = _hist({
        "operating_cash_flow": [(2024, 100.0), (2025, 110.0)],
        "capex": [(2024, -40.0), (2025, -50.0)],
    })
    out = _fcf_5y(hist)
    assert out == [60.0, 60.0]


def test_fcf_5y_returns_empty_when_no_overlap():
    hist = _hist({
        "operating_cash_flow": [(2023, 100.0)],
        "capex": [(2024, 40.0)],
    })
    assert _fcf_5y(hist) == []


def test_fcf_5y_empty_input():
    assert _fcf_5y(None) == []
    assert _fcf_5y(pd.DataFrame()) == []


# -- _build_historical_metrics ------------------------------------------------

def test_build_historical_metrics_per_ticker_dict_shape():
    hist = _hist({
        "eps_diluted": [(2023, 1.0), (2024, 2.0), (2025, 3.0)],
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        "operating_cash_flow": [(2024, 100.0), (2025, 110.0)],
        "capex": [(2024, 40.0), (2025, 50.0)],
    })
    out = _build_historical_metrics(
        histories={"AAA": hist},
        snapshots={"AAA": _snap(stockholders_equity=200.0)},
    )
    assert set(out["AAA"].keys()) == {"eps_3y_avg", "avg_3y_roe", "fcf_5y"}
    assert out["AAA"]["eps_3y_avg"] == 2.0
    assert out["AAA"]["avg_3y_roe"] == 0.10
    assert out["AAA"]["fcf_5y"] == [60.0, 60.0]


def test_build_historical_metrics_handles_missing_ticker_history():
    """Empty history → all extractors return None / [] without raising."""
    out = _build_historical_metrics(
        histories={"AAA": pd.DataFrame()},
        snapshots={"AAA": _snap()},
    )
    assert out["AAA"]["eps_3y_avg"] is None
    assert out["AAA"]["avg_3y_roe"] is None
    assert out["AAA"]["fcf_5y"] == []


def test_build_universe_metrics_pe_uses_diluted_eps():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(eps_diluted=4.0, eps_basic=999.0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pe_ttm"] == 25.0  # 100/4 from diluted, not basic


def test_build_universe_metrics_zero_shares_yields_null_pb_and_ev():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(shares_outstanding=0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pb_reported"] is None
    assert metrics["AAA"]["ev_ebitda_ttm"] is None


def test_build_universe_metrics_negative_equity_yields_null_pb():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(stockholders_equity=-100.0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pb_reported"] is None


def test_eps_3y_avg_with_nan_in_recent_year():
    """NaN among the latest 3 → method returns None (don't silently skip)."""
    hist = _hist({
        "eps_diluted": [(2023, 1.0), (2024, 2.0), (2025, math.nan)],
    })
    assert _eps_3y_avg(hist) is None
