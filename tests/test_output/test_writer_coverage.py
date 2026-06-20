"""Coverage tests for compute.output.writer — targeting uncovered branches.

Uncovered lines (baseline 82%):
  96-97    write_stock_history: None values in column list branch
  100-102  write_stock_history: TypeError/ValueError on float cast → None
  123-125  write_stock_history: atomic write fails → returns False
  233      write_benchmarks_json: empty close_col not in df.columns
  255-257  write_benchmarks_json: sym not in series_by_sym → null array
  265-267  write_benchmarks_json: TypeError/ValueError → None in col list
  281-283  write_benchmarks_json: atomic write failure → (None, coverage_pct)
  292-301  read_previous_top5: file exists, can't parse → empty set;
           read rankings and pick top 5 tickers
"""

from __future__ import annotations

import json

import pandas as pd

from compute.output.writer import (
    read_previous_top5,
    write_benchmarks_json,
    write_stock_history,
)


def _ohlcv_df(n_rows: int) -> pd.DataFrame:
    idx = pd.date_range(end="2026-05-01", periods=n_rows, freq="B")
    return pd.DataFrame(
        {
            "Open": [100.0] * n_rows,
            "High": [101.0] * n_rows,
            "Low": [99.0] * n_rows,
            "Close": [100.5] * n_rows,
            "Adj Close": [100.5] * n_rows,
            "Volume": [1_000_000] * n_rows,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# write_stock_history: _column_to_list None branch (line 96-97)
# ---------------------------------------------------------------------------


def test_write_stock_history_handles_none_in_column(tmp_path):
    """A column containing Python None (not NaN) serializes to null."""
    df = _ohlcv_df(5)
    # Inject None into the Open column (object dtype after assignment).
    opens = df["Open"].tolist()
    opens[2] = None
    df = df.copy()
    df["Open"] = opens
    ok = write_stock_history(ticker="NONE_TEST", prices_df=df, output_dir=tmp_path)
    assert ok is True
    payload = json.loads(
        (tmp_path / "stocks" / "history" / "NONE_TEST.json").read_text()
    )
    assert payload["opens"][2] is None
    assert payload["opens"][0] == 100.0


# ---------------------------------------------------------------------------
# write_stock_history: _column_to_list TypeError → None (lines 100-102)
# ---------------------------------------------------------------------------


def test_write_stock_history_handles_non_numeric_volume(tmp_path):
    """Non-numeric volume values (e.g. 'N/A') are safely serialized as null."""
    df = _ohlcv_df(5)
    volumes = df["Volume"].tolist()
    volumes[1] = "N/A"  # non-numeric string
    df = df.copy()
    df["Volume"] = volumes
    ok = write_stock_history(ticker="STR_VOL", prices_df=df, output_dir=tmp_path)
    assert ok is True
    payload = json.loads(
        (tmp_path / "stocks" / "history" / "STR_VOL.json").read_text()
    )
    # "N/A" can't be float() → caught by except → None
    assert payload["volumes"][1] is None
    assert isinstance(payload["volumes"][0], int)  # normal int


# ---------------------------------------------------------------------------
# write_stock_history: _column_to_list non-finite → None (line 103-105)
# ---------------------------------------------------------------------------


def test_write_stock_history_handles_inf_in_close(tmp_path):
    """Inf values in closes serialize to null (non-finite guard)."""
    df = _ohlcv_df(5)
    closes = df["Adj Close"].tolist()
    closes[3] = float("inf")
    df = df.copy()
    df["Adj Close"] = closes
    df["Close"] = closes
    ok = write_stock_history(ticker="INF_TEST", prices_df=df, output_dir=tmp_path)
    assert ok is True
    payload = json.loads(
        (tmp_path / "stocks" / "history" / "INF_TEST.json").read_text()
    )
    assert payload["closes"][3] is None


# ---------------------------------------------------------------------------
# write_stock_history: uses "Close" when "Adj Close" absent (line 79-80)
# ---------------------------------------------------------------------------


def test_write_stock_history_uses_close_fallback(tmp_path):
    """When 'Adj Close' is absent, 'Close' is used (branch at line 79)."""
    idx = pd.date_range(end="2026-05-01", periods=10, freq="B")
    df = pd.DataFrame(
        {
            "Open": [100.0] * 10,
            "High": [101.0] * 10,
            "Low": [99.0] * 10,
            "Close": [100.5] * 10,  # no Adj Close
            "Volume": [1_000_000] * 10,
        },
        index=idx,
    )
    ok = write_stock_history(ticker="CLOSE_FB", prices_df=df, output_dir=tmp_path)
    assert ok is True
    payload = json.loads(
        (tmp_path / "stocks" / "history" / "CLOSE_FB.json").read_text()
    )
    assert payload["closes"][0] == 100.5


# ---------------------------------------------------------------------------
# write_stock_history: atomic write failure → returns False (lines 123-125)
# ---------------------------------------------------------------------------


def test_write_stock_history_returns_false_on_write_failure(tmp_path, monkeypatch):
    """An IOError during atomic_write_json is caught and returns False."""
    from compute.output import writer

    def _boom(path, data):
        raise OSError("simulated disk full")

    monkeypatch.setattr(writer, "atomic_write_json", _boom)
    df = _ohlcv_df(5)
    ok = write_stock_history(ticker="FAIL", prices_df=df, output_dir=tmp_path)
    assert ok is False


# ---------------------------------------------------------------------------
# write_benchmarks_json: close_col not in df.columns (line 233)
# ---------------------------------------------------------------------------


def test_write_benchmarks_json_null_pads_df_without_adj_or_close(tmp_path):
    """A benchmark df with neither 'Adj Close' nor 'Close' yields a null-padded series.

    The writer counts it as no-coverage (50% with one good sym) but still emits the
    symbol key as an all-None array aligned to the date axis (not dropped).
    """
    bad_df = pd.DataFrame(
        {"NotClose": [100.0, 101.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    good_df = pd.DataFrame(
        {"Adj Close": [470.0, 472.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    path, coverage = write_benchmarks_json(
        {"SPY": good_df, "BAD": bad_df}, tmp_path
    )
    # BAD has no usable price column → not counted; SPY is kept: coverage = 1/2 = 50%
    assert coverage == 50.0
    payload = json.loads(path.read_text())
    assert "spy" in payload
    # "bad" appears null-padded (aligned to the date axis), NOT dropped.
    assert payload["bad"] == [None, None]


# ---------------------------------------------------------------------------
# write_benchmarks_json: sym not in series_by_sym → null array (lines 255-257)
# ---------------------------------------------------------------------------


def test_write_benchmarks_json_null_array_for_empty_series(tmp_path):
    """A benchmark with None DataFrame gets a null-padded array of the union length."""
    spy = pd.DataFrame(
        {"Adj Close": [470.0, 472.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    path, coverage = write_benchmarks_json({"SPY": spy, "QQQ": None}, tmp_path)
    payload = json.loads(path.read_text())
    assert payload["qqq"] == [None, None]
    assert payload["spy"] == [470.0, 472.0]


# ---------------------------------------------------------------------------
# write_benchmarks_json: TypeError/ValueError in col list (lines 265-267)
# ---------------------------------------------------------------------------


def test_write_benchmarks_json_handles_non_numeric_close_value(tmp_path):
    """Non-numeric value in close series serializes to null (line 265-267)."""
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    # Inject a non-numeric value; object dtype forces the try/except path.
    series = pd.Series(["ok_but_string", 472.0, 471.0], index=idx, dtype=object)
    spy_df = pd.DataFrame({"Adj Close": series}, index=idx)
    path, coverage = write_benchmarks_json({"SPY": spy_df}, tmp_path)
    assert path is not None
    payload = json.loads(path.read_text())
    # First element is a string → float("ok_but_string") → ValueError → None
    assert payload["spy"][0] is None
    assert payload["spy"][1] == 472.0


# ---------------------------------------------------------------------------
# write_benchmarks_json: atomic write failure (lines 281-283)
# ---------------------------------------------------------------------------


def test_write_benchmarks_json_returns_none_on_write_failure(tmp_path, monkeypatch):
    """If atomic_write_json raises, returns (None, coverage_pct)."""
    from compute.output import writer

    def _boom(path, data):
        raise OSError("simulated disk full")

    monkeypatch.setattr(writer, "atomic_write_json", _boom)
    spy = pd.DataFrame(
        {"Adj Close": [470.0, 472.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    path, coverage = write_benchmarks_json({"SPY": spy}, tmp_path)
    assert path is None
    assert coverage == 100.0  # SPY had data, so coverage is 100%


# ---------------------------------------------------------------------------
# read_previous_top5: file exists but can't parse → empty set (lines 298-300)
# ---------------------------------------------------------------------------


def test_read_previous_top5_returns_empty_for_missing_file(tmp_path):
    """No rankings.json → empty set (first run)."""
    result = read_previous_top5(tmp_path)
    assert result == set()


def test_read_previous_top5_returns_empty_on_corrupt_json(tmp_path):
    """Corrupt JSON → empty set (graceful degradation)."""
    rankings = tmp_path / "rankings.json"
    rankings.write_text("this is not json {{{")
    result = read_previous_top5(tmp_path)
    assert result == set()


def test_read_previous_top5_returns_top_5_tickers(tmp_path):
    """Valid rankings.json → set of the first 5 tickers."""
    rows = [
        {"rank": i, "ticker": f"T{i:03d}", "composite_score": 100 - i}
        for i in range(1, 11)
    ]
    (tmp_path / "rankings.json").write_text(json.dumps(rows))
    result = read_previous_top5(tmp_path)
    assert result == {"T001", "T002", "T003", "T004", "T005"}
    # Ticker at rank 6 is NOT in the set.
    assert "T006" not in result


def test_read_previous_top5_handles_fewer_than_5_rows(tmp_path):
    """When rankings has fewer than 5 rows, all are returned."""
    rows = [{"rank": i, "ticker": f"T{i}"} for i in range(1, 4)]
    (tmp_path / "rankings.json").write_text(json.dumps(rows))
    result = read_previous_top5(tmp_path)
    assert result == {"T1", "T2", "T3"}


def test_read_previous_top5_skips_non_dict_rows(tmp_path):
    """Non-dict rows in the list are silently skipped (isinstance guard)."""
    rows = [
        {"rank": 1, "ticker": "AAPL"},
        "not a dict",           # skipped
        None,                    # skipped
        {"rank": 4, "ticker": "MSFT"},
        {"rank": 5, "ticker": "GOOG"},
    ]
    (tmp_path / "rankings.json").write_text(json.dumps(rows))
    result = read_previous_top5(tmp_path)
    # Only the first 5 elements are read; 2 are valid dicts, 2 skipped, 1 valid.
    assert "AAPL" in result
    assert "MSFT" in result
    assert "GOOG" in result


def test_read_previous_top5_skips_rows_without_ticker_key(tmp_path):
    """Rows missing the 'ticker' key are silently skipped."""
    rows = [
        {"rank": 1, "ticker": "AAPL"},
        {"rank": 2, "name": "No ticker here"},  # no 'ticker' key → skipped
        {"rank": 3, "ticker": "MSFT"},
    ]
    (tmp_path / "rankings.json").write_text(json.dumps(rows))
    result = read_previous_top5(tmp_path)
    assert "AAPL" in result
    assert "MSFT" in result
    # The row without 'ticker' doesn't appear.
    assert len(result) == 2


# ---------------------------------------------------------------------------
# write_backtest_pit_json: basic round-trip
# ---------------------------------------------------------------------------


def test_write_backtest_pit_json_round_trip(tmp_path):
    """write_backtest_pit_json writes to portfolio/backtest_pit.json atomically."""
    from compute.output.writer import write_backtest_pit_json

    payload = {"meta": {"version": "test"}, "nav": {"dates": ["2024-01-01"]}}
    out = write_backtest_pit_json(payload, tmp_path)
    assert out == tmp_path / "portfolio" / "backtest_pit.json"
    assert json.loads(out.read_text()) == payload
