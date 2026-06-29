"""Unit tests for compute.orchestrator.prices (PR #259-R2).

All tests are offline/synthetic: ``compute.orchestrator.prices.fetch_prices``
and ``compute.orchestrator.prices.compute_average_dollar_volume`` are
monkeypatched so no network calls occur.

Coverage
--------
A — ``_resolve_close_column``
    A1  Prefers "Adj Close" over "Close" when both present.
    A2  Falls back to "Close" when only "Close" is present.
    A3  Returns None when neither column is present.

B — ``_fetch_prices_one``
    B1  Happy path returns expected dict with _prices + _adv keys.
    B2  Returns None when fetch_prices returns None.
    B3  Returns None when the returned DataFrame is empty.
    B4  Returns None when no usable close column exists.
    B5  Returns None when the current price is NaN.
    B6  Returns None when the current price is zero or negative.
    B7  Computes price_change_1d_pct correctly for a 2-row series.
    B8  price_change_1d_pct is None for a single-row series.
    B9  cohort defaults to "sp500" when row has no "cohort" key.
    B10 cohort passes through the row value when set (e.g. "sp400").
    B11 _adv is included in the returned dict.
    B12 _adv is None when compute_average_dollar_volume returns None.

C — ``fetch_all_prices`` happy-path aggregation
    C1  Returns (rows, prices_by_ticker, adv_by_ticker) for 2 tickers.
    C2  _prices key is popped from rows (lives in prices_by_ticker only).
    C3  _adv key is popped from rows (lives in adv_by_ticker only).
    C4  prices_by_ticker is keyed by ticker and holds the DataFrame.
    C5  adv_by_ticker is keyed by ticker and holds the ADV float.
    C6  row dicts contain expected non-private keys.

D — ``fetch_all_prices`` failure/degradation
    D1  A per-ticker fetch that raises is caught, warned, and skipped;
        other tickers are still collected.
    D2  A ticker returning None from _fetch_prices_one is skipped;
        rows/prices/adv dicts do not contain it.
    D3  "_adv" missing from result dict degrades to None, not KeyError
        (pre-Slice-4 fixture compatibility).
    D4  All tickers failing → empty rows, empty prices_by_ticker, empty
        adv_by_ticker (no crash).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pandas as pd
import pytest

import compute.orchestrator.prices as prices_mod
from compute.orchestrator.prices import (
    _fetch_prices_one,
    _resolve_close_column,
    fetch_all_prices,
)

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_prices_df(
    *,
    n_rows: int = 5,
    close_start: float = 100.0,
    has_adj_close: bool = True,
    has_volume: bool = True,
) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame for offline tests."""
    idx = pd.bdate_range("2025-01-02", periods=n_rows)
    closes = [close_start + i for i in range(n_rows)]
    data: dict = {
        "Open": closes,
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
    }
    if has_adj_close:
        data["Adj Close"] = closes
    if has_volume:
        data["Volume"] = [1_000_000] * n_rows
    return pd.DataFrame(data, index=idx)


def _make_row(
    ticker: str = "AAPL",
    name: str = "Apple Inc.",
    sector: str = "IT",
    sub_industry: str | None = "Semiconductors",
    cik: str | None = "0000320193",
    cohort: str | None = None,
) -> pd.Series:
    """Return a minimal universe row as a pd.Series."""
    d: dict = {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "sub_industry": sub_industry,
        "cik": cik,
    }
    if cohort is not None:
        d["cohort"] = cohort
    return pd.Series(d)


def _make_universe(*tickers: str) -> pd.DataFrame:
    """Return a minimal universe DataFrame with the given tickers."""
    rows = [
        {
            "ticker": t,
            "name": f"{t} Inc.",
            "sector": "IT",
            "sub_industry": "Software",
            "cik": f"000{i:07d}",
            "cohort": "sp500",
        }
        for i, t in enumerate(tickers, start=1)
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Section A: _resolve_close_column
# ---------------------------------------------------------------------------


def test_A1_prefers_adj_close_when_both_present():
    """'Adj Close' wins over 'Close' when both columns exist."""
    df = _make_prices_df(has_adj_close=True)
    assert _resolve_close_column(df) == "Adj Close"


def test_A2_falls_back_to_close():
    """Falls back to 'Close' when 'Adj Close' is absent."""
    df = _make_prices_df(has_adj_close=False)
    assert _resolve_close_column(df) == "Close"


def test_A3_returns_none_when_no_close_column():
    """Returns None when neither 'Adj Close' nor 'Close' is present."""
    df = pd.DataFrame({"Open": [100.0], "Volume": [1_000_000]})
    assert _resolve_close_column(df) is None


# ---------------------------------------------------------------------------
# Section B: _fetch_prices_one
# ---------------------------------------------------------------------------


def test_B1_happy_path_returns_expected_dict(monkeypatch):
    """_fetch_prices_one returns a dict with all expected keys on success."""
    prices = _make_prices_df(n_rows=5)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1_234_567.0)

    row = _make_row()
    result = _fetch_prices_one(row)

    assert result is not None
    assert result["ticker"] == "AAPL"
    assert result["name"] == "Apple Inc."
    assert result["sector"] == "IT"
    assert result["industry"] == "Semiconductors"
    assert result["cik"] == "0000320193"
    assert isinstance(result["current_price"], float)
    assert result["current_price"] > 0
    assert "_prices" in result
    assert "_adv" in result


def test_B2_returns_none_when_fetch_prices_returns_none(monkeypatch):
    """Returns None when fetch_prices returns None (graceful degrade)."""
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: None)

    result = _fetch_prices_one(_make_row())
    assert result is None


def test_B3_returns_none_when_prices_empty(monkeypatch):
    """Returns None when fetch_prices returns an empty DataFrame."""
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: pd.DataFrame())

    result = _fetch_prices_one(_make_row())
    assert result is None


def test_B4_returns_none_when_no_close_column(monkeypatch):
    """Returns None when the prices frame has no 'Close' or 'Adj Close' column."""
    df = pd.DataFrame({"Open": [100.0], "Volume": [1_000_000]})
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: df)

    result = _fetch_prices_one(_make_row())
    assert result is None


def test_B5_returns_none_when_all_close_values_are_nan(monkeypatch):
    """Returns None when every close value is NaN.

    The production code runs ``.dropna()`` on the close series before reading
    ``iloc[-1]``, so a single trailing NaN is simply dropped (not exposed to
    the ``math.isnan`` guard).  When ALL close values are NaN, ``dropna()``
    yields an empty series and the ``if last.empty`` guard fires instead.
    This test exercises that empty-after-dropna path.
    """
    prices = _make_prices_df(n_rows=3)
    nan = float("nan")
    prices["Adj Close"] = [nan, nan, nan]
    prices["Close"] = prices["Adj Close"]
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: None)

    result = _fetch_prices_one(_make_row())
    assert result is None


def test_B6_returns_none_when_current_price_zero_or_negative(monkeypatch):
    """Returns None when the last close is zero (current <= 0 guard)."""
    prices = _make_prices_df(n_rows=2)
    prices["Adj Close"] = [100.0, 0.0]
    prices["Close"] = prices["Adj Close"]
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: None)

    result = _fetch_prices_one(_make_row())
    assert result is None


def test_B7_computes_price_change_1d_pct_correctly(monkeypatch):
    """1-day pct change is computed correctly from last two close values."""
    prices = _make_prices_df(n_rows=2, close_start=100.0)
    # Row 0: 100.0, Row 1: 101.0 → pct = (101-100)/100 × 100 = 1.0%
    prices["Adj Close"] = [100.0, 101.0]
    prices["Close"] = prices["Adj Close"]
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    result = _fetch_prices_one(_make_row())

    assert result is not None
    assert result["price_change_1d_pct"] == pytest.approx(1.0)


def test_B8_price_change_1d_pct_none_for_single_row(monkeypatch):
    """price_change_1d_pct is None when only one close row is available."""
    prices = _make_prices_df(n_rows=1, close_start=100.0)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    result = _fetch_prices_one(_make_row())

    assert result is not None
    assert result["price_change_1d_pct"] is None


def test_B9_cohort_defaults_to_sp500_when_absent(monkeypatch):
    """cohort defaults to 'sp500' when the row has no 'cohort' key."""
    prices = _make_prices_df(n_rows=2)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    row = _make_row(cohort=None)  # no cohort key
    result = _fetch_prices_one(row)

    assert result is not None
    assert result["cohort"] == "sp500"


def test_B10_cohort_passes_through_row_value(monkeypatch):
    """cohort is taken from the row when explicitly set (e.g. 'sp400')."""
    prices = _make_prices_df(n_rows=2)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    row = _make_row(cohort="sp400")
    result = _fetch_prices_one(row)

    assert result is not None
    assert result["cohort"] == "sp400"


def test_B11_adv_included_in_result(monkeypatch):
    """_adv is present in the returned dict and equals what compute_average_dollar_volume returns."""
    expected_adv = 5_000_000.0
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: expected_adv)

    result = _fetch_prices_one(_make_row())

    assert result is not None
    assert result["_adv"] == expected_adv


def test_B12_adv_is_none_when_compute_returns_none(monkeypatch):
    """_adv is None when compute_average_dollar_volume returns None (graceful degrade)."""
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda ticker: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: None)

    result = _fetch_prices_one(_make_row())

    assert result is not None
    assert result["_adv"] is None


# ---------------------------------------------------------------------------
# Section C: fetch_all_prices happy-path aggregation
# ---------------------------------------------------------------------------


def test_C1_returns_three_tuple_for_two_tickers(monkeypatch):
    """fetch_all_prices returns (rows, prices_by_ticker, adv_by_ticker) for 2 tickers."""
    prices = _make_prices_df(n_rows=3)

    def fake_fetch(ticker):
        return prices

    monkeypatch.setattr(prices_mod, "fetch_prices", fake_fetch)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    universe = _make_universe("AAPL", "MSFT")
    rows, prices_by_ticker, adv_by_ticker = fetch_all_prices(universe, max_workers=2)

    assert len(rows) == 2
    assert len(prices_by_ticker) == 2
    assert len(adv_by_ticker) == 2


def test_C2_prices_key_not_in_rows(monkeypatch):
    """_prices is NOT in row dicts — it was popped into prices_by_ticker."""
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    rows, _, _ = fetch_all_prices(_make_universe("AAPL"), max_workers=1)

    assert all("_prices" not in r for r in rows)


def test_C3_adv_key_not_in_rows(monkeypatch):
    """_adv is NOT in row dicts — it was popped into adv_by_ticker."""
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    rows, _, _ = fetch_all_prices(_make_universe("AAPL"), max_workers=1)

    assert all("_adv" not in r for r in rows)


def test_C4_prices_by_ticker_keyed_correctly(monkeypatch):
    """prices_by_ticker is keyed by ticker with the DataFrame as value."""
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    _, prices_by_ticker, _ = fetch_all_prices(_make_universe("TSLA"), max_workers=1)

    assert "TSLA" in prices_by_ticker
    assert isinstance(prices_by_ticker["TSLA"], pd.DataFrame)


def test_C5_adv_by_ticker_keyed_correctly(monkeypatch):
    """adv_by_ticker is keyed by ticker with the float ADV as value."""
    expected_adv = 7_654_321.0
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: expected_adv)

    _, _, adv_by_ticker = fetch_all_prices(_make_universe("NVDA"), max_workers=1)

    assert "NVDA" in adv_by_ticker
    assert adv_by_ticker["NVDA"] == expected_adv


def test_C6_rows_contain_expected_keys(monkeypatch):
    """Row dicts in the returned list contain the expected non-private keys."""
    prices = _make_prices_df(n_rows=3)
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    rows, _, _ = fetch_all_prices(_make_universe("AAPL"), max_workers=1)

    assert len(rows) == 1
    row = rows[0]
    for key in ("ticker", "name", "sector", "industry", "cik", "cohort",
                "current_price", "price_change_1d_pct"):
        assert key in row, f"Expected key '{key}' missing from row"


# ---------------------------------------------------------------------------
# Section D: fetch_all_prices failure / degradation
# ---------------------------------------------------------------------------


def test_D1_per_ticker_exception_is_caught_and_others_collected(monkeypatch, caplog):
    """A per-ticker fetch that raises is caught, warned, and skipped;
    the remaining ticker is still collected."""
    prices = _make_prices_df(n_rows=3)

    call_count = {"n": 0}

    def fake_fetch(ticker):
        call_count["n"] += 1
        return prices

    monkeypatch.setattr(prices_mod, "fetch_prices", fake_fetch)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    # Patch _fetch_prices_one to raise on FAIL_TICKER
    original_fetch_one = prices_mod._fetch_prices_one

    def patched_fetch_one(row):
        if row["ticker"] == "FAIL":
            raise RuntimeError("simulated fetch failure")
        return original_fetch_one(row)

    with patch.object(prices_mod, "_fetch_prices_one", side_effect=patched_fetch_one):
        with caplog.at_level(logging.WARNING, logger="compute.orchestrator.prices"):
            rows, prices_by_ticker, adv_by_ticker = fetch_all_prices(
                _make_universe("GOOD", "FAIL"), max_workers=2
            )

    assert len(rows) == 1
    assert rows[0]["ticker"] == "GOOD"
    assert "GOOD" in prices_by_ticker
    assert "FAIL" not in prices_by_ticker
    # Warning logged for the failing ticker
    assert any("Price fetch failed for FAIL" in r.message for r in caplog.records)


def test_D2_none_result_from_fetch_one_is_skipped(monkeypatch):
    """A ticker returning None from _fetch_prices_one is excluded from all outputs."""
    prices = _make_prices_df(n_rows=3)

    original_fetch_one = prices_mod._fetch_prices_one

    def patched_fetch_one(row):
        if row["ticker"] == "EMPTY":
            return None
        return original_fetch_one(row)

    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    with patch.object(prices_mod, "_fetch_prices_one", side_effect=patched_fetch_one):
        rows, prices_by_ticker, adv_by_ticker = fetch_all_prices(
            _make_universe("KEEP", "EMPTY"), max_workers=2
        )

    tickers_in_rows = {r["ticker"] for r in rows}
    assert "KEEP" in tickers_in_rows
    assert "EMPTY" not in tickers_in_rows
    assert "EMPTY" not in prices_by_ticker
    assert "EMPTY" not in adv_by_ticker


def test_D3_missing_adv_key_degrades_to_none(monkeypatch):
    """A result dict missing the '_adv' key degrades to None (pre-Slice-4 fixture compat)."""
    prices = _make_prices_df(n_rows=3)

    def patched_fetch_one(row):
        result = {
            "ticker": row["ticker"],
            "name": row["name"],
            "sector": row["sector"],
            "industry": row.get("sub_industry"),
            "cik": row.get("cik"),
            "cohort": row.get("cohort", "sp500"),
            "current_price": 100.0,
            "price_change_1d_pct": 1.0,
            "_prices": prices,
            # deliberately no "_adv" key — pre-Slice-4 fixture
        }
        return result

    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: prices)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: 1e6)

    with patch.object(prices_mod, "_fetch_prices_one", side_effect=patched_fetch_one):
        rows, prices_by_ticker, adv_by_ticker = fetch_all_prices(
            _make_universe("LEGACY"), max_workers=1
        )

    assert len(rows) == 1
    assert adv_by_ticker.get("LEGACY") is None


def test_D4_all_failing_returns_empty_collections(monkeypatch):
    """When every ticker fails, returns empty rows + empty dicts without crashing."""
    monkeypatch.setattr(prices_mod, "fetch_prices", lambda t: None)
    monkeypatch.setattr(prices_mod, "compute_average_dollar_volume", lambda df, n: None)

    rows, prices_by_ticker, adv_by_ticker = fetch_all_prices(
        _make_universe("BAD1", "BAD2", "BAD3"), max_workers=2
    )

    assert rows == []
    assert prices_by_ticker == {}
    assert adv_by_ticker == {}
