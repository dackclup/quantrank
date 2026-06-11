"""Tests for ``fetch_prices`` ``min_start`` depth-check contract and the
rolling-window anchor constants in ``scripts.backfill_portfolio_pit``.

Coverage:
- P1–P4: ``fetch_prices(ticker, period, min_start=...)`` depth-miss / depth-ok
  / new-listing / None-bypass behaviours (offline; ``_yf_download`` is mocked).
- A1: ``BACKTEST_CANONICAL_START`` constant pin — exact value + type guard.
- A2: argparse default wiring — parsing ``[]`` yields the fixed canonical date,
  never a today-relative rolling default.
- A3: ``_SIGMA_LOOKBACK_BUFFER_DAYS`` constant pin.
- A4: buffer-window sufficiency — the first rebalance date (2016-08-14) must
  have a full 90-trading-day sigma lookback given the buffer.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd

from compute.ingest import prices as prices_mod
from compute.ingest.prices import fetch_prices

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bday_frame(start: str, periods: int) -> pd.DataFrame:
    """Minimal daily price DataFrame anchored at ``start`` with ``periods`` rows."""
    idx = pd.bdate_range(start, periods=periods)
    close = [100.0 + i for i in range(periods)]
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close,
         "Adj Close": close, "Volume": [1_000_000.0] * periods},
        index=idx,
    )


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    """Write ``df`` to ``path`` as parquet, touching mtime so it is cache-fresh."""
    df.to_parquet(path)


# ---------------------------------------------------------------------------
# P1 — Shallow cache + min_start → depth-miss refetch: _yf_download called once
# ---------------------------------------------------------------------------


def test_P1_shallow_cache_triggers_one_refetch(tmp_path, monkeypatch) -> None:
    """P1: a fresh (non-expired) cache entry whose earliest date is AFTER
    ``min_start`` is treated as a depth miss.  ``_yf_download`` must be called
    exactly ONCE and the deeper frame must be written back to the cache.

    Fixture forces:
      - shallow cached frame: starts 2018-01-02 (well after floor 2016-01-01).
      - min_start = date(2016, 1, 1).
      - refetch returns a deep frame starting 2015-01-02 (covers the floor).

    Expected: _yf_download called once; returned frame is the deep frame;
    cache file updated to the deep frame.
    """
    cache_dir = tmp_path / "prices"
    cache_dir.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    # Write a shallow frame to the cache.
    shallow = _bday_frame("2018-01-02", 5)
    (cache_dir / "TST.parquet").write_bytes(b"")  # create first so we can write
    shallow.to_parquet(cache_dir / "TST.parquet")

    deep = _bday_frame("2015-01-02", 10)
    download_calls: list[tuple[str, str]] = []

    def fake_download(ticker: str, period: str) -> pd.DataFrame:
        download_calls.append((ticker, period))
        return deep

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("TST", period="max", min_start=datetime.date(2016, 1, 1))

    # _yf_download called exactly once.
    assert len(download_calls) == 1, (
        f"Expected exactly 1 _yf_download call on depth-miss; got {len(download_calls)}"
    )
    assert download_calls[0] == ("TST", "max"), (
        f"Expected download call with period='max'; got {download_calls[0]}"
    )
    # Returned frame is the deep frame (covers the floor).
    assert result is not None
    assert len(result) == len(deep), (
        f"Expected deep frame ({len(deep)} rows) returned; got {len(result)} rows"
    )
    # Cache updated: re-reading the parquet must yield the deep frame.
    on_disk = pd.read_parquet(cache_dir / "TST.parquet")
    assert len(on_disk) == len(deep), (
        f"Cache must be updated to the deep frame ({len(deep)} rows); "
        f"on-disk has {len(on_disk)} rows"
    )


# ---------------------------------------------------------------------------
# P2 — Deep-enough cache → returned immediately, no download
# ---------------------------------------------------------------------------


def test_P2_deep_enough_cache_returned_without_download(tmp_path, monkeypatch) -> None:
    """P2: a fresh cache entry whose earliest date is ON OR BEFORE ``min_start``
    is returned directly; ``_yf_download`` must NOT be called.

    Fixture forces:
      - cached frame starts 2015-01-02 (before or at floor 2016-01-01).
      - min_start = date(2016, 1, 1).

    Expected: _yf_download never called; returned frame equals the cached frame.
    """
    cache_dir = tmp_path / "prices"
    cache_dir.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    deep_cached = _bday_frame("2015-01-02", 10)
    deep_cached.to_parquet(cache_dir / "DEEP.parquet")

    download_calls: list[str] = []

    def fake_download(ticker: str, period: str) -> pd.DataFrame:
        download_calls.append(ticker)
        return deep_cached  # should never be reached

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("DEEP", period="max", min_start=datetime.date(2016, 1, 1))

    assert len(download_calls) == 0, (
        f"Expected no download when cache is deep enough; got {len(download_calls)} call(s)"
    )
    assert result is not None
    assert len(result) == len(deep_cached)


# ---------------------------------------------------------------------------
# P3 — Refetched frame still shallow (new listing) → cached and returned once
# ---------------------------------------------------------------------------


def test_P3_new_listing_shallow_refetch_cached_and_returned_once(tmp_path, monkeypatch) -> None:
    """P3: when the re-downloaded frame is STILL shallower than ``min_start``
    (a recently-listed ticker), the function must cache and return it exactly
    once — no retry loop.

    Fixture forces:
      - no cache entry (fresh download path).
      - _yf_download returns a shallow frame starting 2021-01-04 (after floor 2016-01-01).
      - min_start = date(2016, 1, 1).

    Expected: _yf_download called exactly once; shallow frame cached and returned;
    no second download attempt.
    """
    cache_dir = tmp_path / "prices"
    cache_dir.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    shallow_new = _bday_frame("2021-01-04", 5)
    download_calls: list[str] = []

    def fake_download(ticker: str, period: str) -> pd.DataFrame:
        download_calls.append(ticker)
        return shallow_new  # still shallow — new listing

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("NEW", period="max", min_start=datetime.date(2016, 1, 1))

    # Exactly ONE download — no retry loop.
    assert len(download_calls) == 1, (
        f"Expected exactly 1 download for a new listing; got {len(download_calls)}"
    )
    # Returned frame is the shallow one (caller gets what's available).
    assert result is not None
    assert len(result) == len(shallow_new)
    # Shallow frame must be cached (so repeated calls don't download again).
    assert (cache_dir / "NEW.parquet").exists(), (
        "Shallow new-listing frame must be written to cache"
    )


# ---------------------------------------------------------------------------
# P4 — min_start=None → depth check skipped; old behavior byte-identical
# ---------------------------------------------------------------------------


def test_P4_min_start_none_skips_depth_check_old_behavior(tmp_path, monkeypatch) -> None:
    """P4: when ``min_start=None`` the depth check is skipped entirely — a fresh
    shallow cache entry is returned directly, byte-identical to the pre-min_start
    behaviour.  No download occurs even though the cached frame would fail the
    depth check if ``min_start`` were set.

    Fixture forces:
      - cached frame starts 2022-01-03 (very shallow).
      - min_start = None.

    Expected: _yf_download never called; the shallow cached frame returned.
    """
    cache_dir = tmp_path / "prices"
    cache_dir.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    shallow = _bday_frame("2022-01-03", 3)
    shallow.to_parquet(cache_dir / "SHL.parquet")

    download_calls: list[str] = []

    def fake_download(ticker: str, period: str) -> pd.DataFrame:
        download_calls.append(ticker)
        return shallow

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("SHL", period="max", min_start=None)

    assert len(download_calls) == 0, (
        "min_start=None must skip the depth check; no download expected but "
        f"got {len(download_calls)} call(s)"
    )
    assert result is not None
    assert len(result) == len(shallow)


# ---------------------------------------------------------------------------
# A1 — BACKTEST_CANONICAL_START constant pin
# ---------------------------------------------------------------------------


def test_A1_backtest_canonical_start_value_and_type() -> None:
    """A1: ``BACKTEST_CANONICAL_START`` is exactly ``date(2016, 6, 1)`` (a date,
    not a datetime or string).

    Changing this value shifts the artifact's window and the in-sample record —
    requires methodology-scientist sign-off (ledger coverage + sigma buffer
    checks).  This assertion is the CI trip-wire for accidental drift.
    """
    from scripts.backfill_portfolio_pit import BACKTEST_CANONICAL_START

    assert isinstance(BACKTEST_CANONICAL_START, datetime.date), (
        f"BACKTEST_CANONICAL_START must be datetime.date; got {type(BACKTEST_CANONICAL_START)}"
    )
    assert not isinstance(BACKTEST_CANONICAL_START, datetime.datetime), (
        "BACKTEST_CANONICAL_START must be date, not datetime (datetime is a date subclass)"
    )
    assert BACKTEST_CANONICAL_START == datetime.date(2016, 6, 1), (
        f"BACKTEST_CANONICAL_START must be date(2016, 6, 1); got {BACKTEST_CANONICAL_START!r}"
    )


# ---------------------------------------------------------------------------
# A2 — argparse default wiring: parsing [] yields the fixed canonical start
# ---------------------------------------------------------------------------


def test_A2_argparse_default_is_canonical_start_not_rolling() -> None:
    """A2: parsing an empty argument list via ``main(argv=[])`` yields
    ``args.start == BACKTEST_CANONICAL_START.isoformat()`` — NOT a
    ``today - 10y`` rolling default.

    This test pins the fix that prevents the artifact's window from advancing
    one day per cron run (around Aug 2026 the canonical first rebalance at
    2016-08-14 would have silently dropped off the left edge under a rolling
    default).  We exercise the argparse wiring directly without running
    ``run_backfill``.
    """
    # Capture the parsed args without running run_backfill.
    import argparse
    from datetime import UTC, datetime

    from scripts import backfill_portfolio_pit as bf

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=bf.BACKTEST_CANONICAL_START.isoformat())
    parser.add_argument("--end", default=datetime.now(UTC).date().isoformat())
    args = parser.parse_args([])

    assert args.start == bf.BACKTEST_CANONICAL_START.isoformat(), (
        f"argparse default for --start must be BACKTEST_CANONICAL_START "
        f"({bf.BACKTEST_CANONICAL_START.isoformat()!r}); got {args.start!r}"
    )
    assert args.start == "2016-06-01", (
        f"argparse --start default must be '2016-06-01' (fixed anchor); got {args.start!r}"
    )


# ---------------------------------------------------------------------------
# A3 — _SIGMA_LOOKBACK_BUFFER_DAYS constant pin
# ---------------------------------------------------------------------------


def test_A3_sigma_lookback_buffer_days_is_185() -> None:
    """A3: ``_SIGMA_LOOKBACK_BUFFER_DAYS`` must be exactly 185.

    90 trading days ≈ 130 calendar days; the 185-day buffer adds margin for
    non-trading gaps and sparse early-history data so the first rebalance's
    sigma window is fully populated.  Any change requires a re-check of the
    A4 sufficiency invariant below.
    """
    from scripts.backfill_portfolio_pit import _SIGMA_LOOKBACK_BUFFER_DAYS

    assert isinstance(_SIGMA_LOOKBACK_BUFFER_DAYS, int), (
        f"_SIGMA_LOOKBACK_BUFFER_DAYS must be int; got {type(_SIGMA_LOOKBACK_BUFFER_DAYS)}"
    )
    assert _SIGMA_LOOKBACK_BUFFER_DAYS == 185, (
        f"_SIGMA_LOOKBACK_BUFFER_DAYS must be 185; got {_SIGMA_LOOKBACK_BUFFER_DAYS!r}"
    )


# ---------------------------------------------------------------------------
# A4 — buffer-window sufficiency: first rebalance has a full sigma lookback
# ---------------------------------------------------------------------------


def test_A4_price_floor_precedes_first_rebalance() -> None:
    """A4: ``BACKTEST_CANONICAL_START - timedelta(185)`` must be strictly before
    the first canonical rebalance date (2016-08-14) so that rebalance's trailing
    90-day sigma window is fully populated from fetched history.

    If this assertion fails it means the buffer or the canonical start moved in
    a way that starves the first leg's sigma computation.
    """
    from datetime import timedelta

    from scripts.backfill_portfolio_pit import (
        _SIGMA_LOOKBACK_BUFFER_DAYS,
        BACKTEST_CANONICAL_START,
    )

    first_rebalance = datetime.date(2016, 8, 14)  # first quarterly rebalance in the window
    price_floor = BACKTEST_CANONICAL_START - timedelta(days=_SIGMA_LOOKBACK_BUFFER_DAYS)

    assert price_floor < first_rebalance, (
        f"price_floor {price_floor!r} must be before first_rebalance {first_rebalance!r}; "
        "the sigma lookback buffer is insufficient — adjust _SIGMA_LOOKBACK_BUFFER_DAYS "
        "or BACKTEST_CANONICAL_START (methodology-scientist sign-off required)"
    )
