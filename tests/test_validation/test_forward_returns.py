"""Tests for ``compute.validation.forward_returns``.

Phase 4.6 task #2b — forward-return loader from gitignored price cache.

The production cache (``compute/cache/prices/``) is gitignored — these
tests use synthetic parquet fixtures written to ``tmp_path`` and pass
``cache_dir=<tmp_path>`` through every public API.

This mirrors the strategy used in ``test_ranking_history.py`` (PR #278)
where the live-git smoke is paired with a synthetic monkeypatched edge
case battery.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from compute.validation.forward_returns import (
    ForwardReturnResult,
    compute_forward_return,
    compute_forward_return_detailed,
    compute_forward_returns_batch,
    coverage_report,
)

# ---------------------------------------------------------------- Fixtures


def _make_price_frame(
    start: date,
    n_days: int,
    *,
    base_price: float = 100.0,
    daily_return: float = 0.0,
    include_adj_close: bool = True,
    include_close_only: bool = False,
) -> pd.DataFrame:
    """Build a synthetic OHLCV frame with a business-day DatetimeIndex.

    ``daily_return`` is geometric: each successive close is
    ``prev_close × (1 + daily_return)``. This makes the expected forward
    return arithmetic and analytically derivable.
    """
    index = pd.bdate_range(start=start, periods=n_days)
    closes = [base_price * ((1.0 + daily_return) ** i) for i in range(n_days)]
    data = {
        "Open": closes,
        "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes],
        "Close": closes,
        "Volume": [1_000_000] * n_days,
    }
    if include_adj_close:
        data["Adj Close"] = closes
    if include_close_only:
        # Strip Adj Close for the fallback-path test
        data.pop("Adj Close", None)
    df = pd.DataFrame(data, index=index)
    return df


def _write_parquet(df: pd.DataFrame, cache_dir: Path, ticker: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{ticker}.parquet"
    df.to_parquet(path)
    return path


# ---------------------------------------------------------------- Happy path


def test_forward_return_flat_price_is_zero(tmp_path: Path) -> None:
    """Identity price → forward return = 0.0."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    _write_parquet(df, tmp_path, "FLAT")

    result = compute_forward_return("FLAT", date(2024, 1, 2), 6, cache_dir=tmp_path)
    assert result is not None
    assert result == pytest.approx(0.0, abs=1e-9)


def test_forward_return_geometric_growth_matches_expectation(tmp_path: Path) -> None:
    """1% daily growth over ~126 trading days → ~(1.01)^126 - 1."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.01)
    _write_parquet(df, tmp_path, "GROW")

    # 6 months ≈ 183 calendar days ≈ 130 trading rows after start.
    # We don't assert an exact integer; we assert it's within the
    # expected band (range bracket gives the test stability against
    # snap-to-trading-day off-by-one).
    result = compute_forward_return("GROW", date(2024, 1, 2), 6, cache_dir=tmp_path)
    assert result is not None
    # 1.01^126 ≈ 3.51 → return ≈ 2.51; 1.01^130 ≈ 3.65 → return ≈ 2.65
    # Wide-but-finite band keeps the test stable across pandas
    # business-day calendar quirks.
    assert 2.0 < result < 3.5


def test_forward_return_negative_drift_returns_negative(tmp_path: Path) -> None:
    """-1% daily drift → negative forward return."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=-0.01)
    _write_parquet(df, tmp_path, "DROP")

    result = compute_forward_return("DROP", date(2024, 1, 2), 6, cache_dir=tmp_path)
    assert result is not None
    assert result < 0
    # (0.99)^130 ≈ 0.27 → return ≈ -0.73; (0.99)^126 ≈ 0.28 → return ≈ -0.72
    assert -0.80 < result < -0.65


# ---------------------------------------------------------------- ForwardReturnResult


def test_detailed_result_carries_start_end_dates(tmp_path: Path) -> None:
    """compute_forward_return_detailed returns the actual trading dates used."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    _write_parquet(df, tmp_path, "DETAIL")

    result = compute_forward_return_detailed(
        "DETAIL", date(2024, 1, 2), 3, cache_dir=tmp_path
    )
    assert isinstance(result, ForwardReturnResult)
    assert result.ticker == "DETAIL"
    assert result.as_of_date == date(2024, 1, 2)
    assert result.horizon_months == 3
    assert result.start_date == date(2024, 1, 2)  # Tuesday — trades
    # End-date ≈ 90 calendar days later snapped to a business day
    assert result.end_date is not None
    assert result.start_date < result.end_date
    assert result.start_close == pytest.approx(100.0, abs=1e-9)
    assert result.end_close == pytest.approx(100.0, abs=1e-9)


# ---------------------------------------------------------------- Missing-data paths


def test_no_cached_parquet_returns_none(tmp_path: Path) -> None:
    """Ticker with no parquet → None + note='no cached parquet'."""
    result = compute_forward_return_detailed(
        "GHOST", date(2024, 1, 2), 6, cache_dir=tmp_path
    )
    assert result.forward_return is None
    assert "no cached parquet" in result.note


def test_missing_close_column_returns_none(tmp_path: Path) -> None:
    """Parquet exists but no Close / Adj Close → None + descriptive note."""
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "Volume": [1_000_000, 1_100_000],
        },
        index=pd.bdate_range(start=date(2024, 1, 2), periods=2),
    )
    _write_parquet(df, tmp_path, "NOCLOSE")

    result = compute_forward_return_detailed(
        "NOCLOSE", date(2024, 1, 2), 6, cache_dir=tmp_path
    )
    assert result.forward_return is None
    assert "no close column" in result.note


def test_close_fallback_when_adj_close_missing(tmp_path: Path) -> None:
    """If only Close exists, that's what gets used."""
    df = _make_price_frame(
        date(2024, 1, 2), 260, daily_return=0.0, include_close_only=True
    )
    assert "Adj Close" not in df.columns
    assert "Close" in df.columns
    _write_parquet(df, tmp_path, "CLOSEONLY")

    result = compute_forward_return_detailed(
        "CLOSEONLY", date(2024, 1, 2), 6, cache_dir=tmp_path
    )
    assert result.forward_return == pytest.approx(0.0, abs=1e-9)


def test_horizon_past_last_cached_row_returns_none(tmp_path: Path) -> None:
    """As-of near the END of the cache → horizon-end is censored."""
    df = _make_price_frame(date(2024, 1, 2), 60, daily_return=0.0)
    # Cache only spans Jan 2 → ~late March. 12-month horizon would land
    # in 2025 → censored.
    _write_parquet(df, tmp_path, "SHORT")

    result = compute_forward_return_detailed(
        "SHORT", date(2024, 1, 2), 12, cache_dir=tmp_path
    )
    assert result.forward_return is None
    assert "censored" in result.note or "past last cached" in result.note


def test_as_of_before_cache_start_returns_none(tmp_path: Path) -> None:
    """As-of pre-cache → no forward snap → None."""
    df = _make_price_frame(date(2024, 1, 2), 60, daily_return=0.0)
    _write_parquet(df, tmp_path, "LATE")

    result = compute_forward_return_detailed(
        "LATE", date(2020, 1, 2), 6, cache_dir=tmp_path
    )
    # 2020 → 2024 gap is way past the 5-day forward snap window
    assert result.forward_return is None
    assert "does not snap" in result.note


# ---------------------------------------------------------------- Weekend / snap


def test_as_of_on_saturday_snaps_to_next_monday(tmp_path: Path) -> None:
    """Sat 2024-01-06 → snaps forward to Mon 2024-01-08."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    _write_parquet(df, tmp_path, "WKND")

    result = compute_forward_return_detailed(
        "WKND", date(2024, 1, 6), 3, cache_dir=tmp_path
    )
    assert result.start_date == date(2024, 1, 8)  # Monday
    assert result.forward_return == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- Bad-price guards


def test_zero_start_close_returns_none(tmp_path: Path) -> None:
    """Zero start price → division by zero guarded → None."""
    index = pd.bdate_range(start=date(2024, 1, 2), periods=260)
    df = pd.DataFrame(
        {
            "Open": [0.0] + [100.0] * 259,
            "High": [0.0] + [101.0] * 259,
            "Low": [0.0] + [99.0] * 259,
            "Close": [0.0] + [100.0] * 259,
            "Adj Close": [0.0] + [100.0] * 259,
            "Volume": [1_000_000] * 260,
        },
        index=index,
    )
    _write_parquet(df, tmp_path, "ZERO")

    result = compute_forward_return_detailed(
        "ZERO", date(2024, 1, 2), 3, cache_dir=tmp_path
    )
    assert result.forward_return is None
    assert "non-positive" in result.note or "NaN" in result.note


def test_nan_end_close_returns_none(tmp_path: Path) -> None:
    """NaN at horizon-end → None + 'end_close NaN' note."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    # Punch a NaN exactly where the horizon will land. For 6m from
    # 2024-01-02 that's somewhere around 2024-07-02.
    target_end = pd.Timestamp(date(2024, 1, 2)) + pd.Timedelta(days=int(round(6 * 30.44)))
    # Snap target back to nearest bdate in our index
    closest = df.index[df.index <= target_end][-1]
    df.loc[closest, "Adj Close"] = np.nan
    df.loc[closest, "Close"] = np.nan
    _write_parquet(df, tmp_path, "NANEND")

    result = compute_forward_return_detailed(
        "NANEND", date(2024, 1, 2), 6, cache_dir=tmp_path
    )
    assert result.forward_return is None
    assert "end_close NaN" in result.note or "non-positive" in result.note


# ---------------------------------------------------------------- Input validation


def test_zero_horizon_raises() -> None:
    """horizon_months <= 0 → ValueError."""
    with pytest.raises(ValueError, match="horizon_months must be positive"):
        compute_forward_return("X", date(2024, 1, 2), 0)


def test_negative_horizon_raises() -> None:
    with pytest.raises(ValueError, match="horizon_months must be positive"):
        compute_forward_return("X", date(2024, 1, 2), -3)


# ---------------------------------------------------------------- Batch API


def test_batch_returns_dict_keyed_by_ticker(tmp_path: Path) -> None:
    """Batch wrapper preserves insertion order + maps to None for missing."""
    df_a = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    df_b = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.005)
    _write_parquet(df_a, tmp_path, "AAA")
    _write_parquet(df_b, tmp_path, "BBB")

    out = compute_forward_returns_batch(
        ["AAA", "BBB", "GHOST"],
        date(2024, 1, 2),
        6,
        cache_dir=tmp_path,
    )
    assert list(out.keys()) == ["AAA", "BBB", "GHOST"]
    assert out["AAA"] == pytest.approx(0.0, abs=1e-9)
    assert out["BBB"] is not None and out["BBB"] > 0
    assert out["GHOST"] is None


def test_batch_empty_iter_returns_empty_dict(tmp_path: Path) -> None:
    out = compute_forward_returns_batch([], date(2024, 1, 2), 6, cache_dir=tmp_path)
    assert out == {}


# ---------------------------------------------------------------- coverage_report


def test_coverage_report_classifies_each_failure_mode(tmp_path: Path) -> None:
    """coverage_report buckets each ticker into the right reason bucket."""
    # 1× ok
    df_ok = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    _write_parquet(df_ok, tmp_path, "OK")
    # 1× censored (short cache)
    df_short = _make_price_frame(date(2024, 1, 2), 30, daily_return=0.0)
    _write_parquet(df_short, tmp_path, "CENSORED")
    # 1× no_close
    df_noclose = pd.DataFrame(
        {"Open": [100.0, 101.0], "Volume": [1_000_000, 1_100_000]},
        index=pd.bdate_range(start=date(2024, 1, 2), periods=2),
    )
    _write_parquet(df_noclose, tmp_path, "NOCLOSE")
    # 1× missing cache file entirely
    # no write — just include in the tickers list

    report = coverage_report(
        ["OK", "CENSORED", "NOCLOSE", "GHOST"],
        date(2024, 1, 2),
        6,
        cache_dir=tmp_path,
    )
    assert report["total"] == 4
    assert report["ok"] == 1
    assert report["censored"] == 1
    assert report["no_close"] == 1
    assert report["no_cache"] == 1


def test_coverage_report_empty_universe(tmp_path: Path) -> None:
    report = coverage_report([], date(2024, 1, 2), 6, cache_dir=tmp_path)
    assert report["total"] == 0
    assert report["ok"] == 0


# ---------------------------------------------------------------- Index recovery


def test_non_datetime_index_is_coerced(tmp_path: Path) -> None:
    """Parquet round-trip can lose the DatetimeIndex; module coerces back."""
    df = _make_price_frame(date(2024, 1, 2), 260, daily_return=0.0)
    df_reset = df.reset_index().rename(columns={"index": "Date"}).set_index("Date")
    # Convert index to string-keyed (simulates the lost-DatetimeIndex case)
    df_reset.index = df_reset.index.astype(str)
    _write_parquet(df_reset, tmp_path, "STRIDX")

    result = compute_forward_return(
        "STRIDX", date(2024, 1, 2), 6, cache_dir=tmp_path
    )
    # Should successfully coerce index back to datetime and compute
    assert result == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- Live-cache smoke


def test_live_cache_smoke_if_present() -> None:
    """When the real price cache exists, verify the API runs end-to-end.

    Skipped silently if the gitignored cache isn't populated (the common
    case in CI / sandbox). On a warm dev machine this exercises the
    actual yfinance-written parquet shape.
    """
    from compute import config

    cache = config.PRICES_CACHE_DIR
    if not cache.exists():
        pytest.skip("No live price cache present — skipping smoke")

    aapl_path = cache / "AAPL.parquet"
    if not aapl_path.exists():
        pytest.skip("AAPL.parquet not in live cache — skipping smoke")

    # 6 months ago from any recent date should land inside the 5y cache
    as_of = date.today() - timedelta(days=400)
    result = compute_forward_return("AAPL", as_of, 6)
    # Either succeeds (warm cache) or returns None (date outside cache);
    # either way, no exception.
    assert result is None or isinstance(result, float)
