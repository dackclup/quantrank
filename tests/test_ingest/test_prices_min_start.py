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

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
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

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
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

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
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

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
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
    """A2 anchor pin: running ``main([])`` (no --start) must hand run_backfill the
    CANONICAL fixed start — exercising the PRODUCTION parser, not a replica.
    Guards the rolling today-relative default from creeping back: if main()'s
    default reverted to ``today - 10y``, the asserted date would drift daily."""
    from unittest import mock

    from scripts import backfill_portfolio_pit as bf

    with mock.patch.object(bf, "run_backfill") as rb:
        rc = bf.main([])
    assert rc == 0
    assert rb.call_count == 1
    start_arg = rb.call_args.args[0]
    assert start_arg == bf.BACKTEST_CANONICAL_START
    assert start_arg == datetime.date(2016, 6, 1)


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


def test_A4_price_floor_covers_full_sigma_window() -> None:
    """A4 anchor pin: the price floor (canonical start - 185d buffer) must precede
    the first rebalance (2016-08-14) by AT LEAST 130 calendar days — the span that
    holds ~90 TRADING days, so the first leg's trailing sigma window is FULL (the
    pre-fix state computed it on ~45 trading days). A zero buffer would still pass
    a bare ordering assert; this pins the magnitude."""
    from scripts.backfill_portfolio_pit import (
        _SIGMA_LOOKBACK_BUFFER_DAYS,
        BACKTEST_CANONICAL_START,
    )

    floor = BACKTEST_CANONICAL_START - datetime.timedelta(
        days=_SIGMA_LOOKBACK_BUFFER_DAYS
    )
    first_rebalance = datetime.date(2016, 8, 14)
    assert (first_rebalance - floor).days >= 130, (
        f"sigma window short: floor {floor} is only "
        f"{(first_rebalance - floor).days}d before the first rebalance"
    )


def test_A5_prices_fetch_start_constant_pin() -> None:
    """Design-A anchor pin: the shared fixed price floor equals
    BACKTEST_CANONICAL_START (2016-06-01) - 185d = 2015-11-29, and the two
    layers' constants agree (scripts may import compute, never the reverse —
    the equality is asserted here, across the layering boundary)."""
    from compute import config
    from scripts.backfill_portfolio_pit import (
        _SIGMA_LOOKBACK_BUFFER_DAYS,
        BACKTEST_CANONICAL_START,
    )

    assert config.PRICES_FETCH_START == datetime.date(2015, 11, 29)
    assert (
        BACKTEST_CANONICAL_START
        - datetime.timedelta(days=_SIGMA_LOOKBACK_BUFFER_DAYS)
        == config.PRICES_FETCH_START
    )


def test_A6_fetch_prices_downloads_from_fixed_floor(tmp_path, monkeypatch) -> None:
    """Design-A wiring pin: a live download from fetch_prices passes
    start=config.PRICES_FETCH_START to _yf_download (the fixed floor, not the
    rolling period path) — the property that keeps the shared cache deep enough
    for the backfill's min_start backstop without any per-run refetch."""
    from compute import config

    monkeypatch.setattr(config, "PRICES_CACHE_DIR", tmp_path)
    seen: dict = {}

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        seen["start"] = start
        idx = pd.bdate_range("2015-11-30", periods=30)
        return pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)
    out = fetch_prices("TESTX")
    assert out is not None
    assert seen["start"] == config.PRICES_FETCH_START


def test_A7_yf_download_period_branch_without_start() -> None:
    """Direct _yf_download callers with start=None keep the period branch —
    asserted structurally: the signature accepts start=None and the period
    parameter remains (regression guard for test/tooling callers that bypass
    the fixed floor)."""
    import inspect

    sig = inspect.signature(prices_mod._yf_download)
    assert "start" in sig.parameters
    assert sig.parameters["start"].default is None
    assert "period" in sig.parameters
