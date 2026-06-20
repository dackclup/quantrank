"""Offline tests for the prices last-bar-date recency guard (PR-1 latent fix).

The mtime-based ``age_hours`` TTL is dead on GitHub Actions because
``actions/cache`` restore resets mtime to "now" each run.  The recency guard
in ``fetch_prices`` closes this: it checks the LAST BAR DATE of the cached
parquet.  A cache whose last bar is older than
``config.PRICES_CACHE_MAX_STALE_DAYS`` falls through to a live re-download
regardless of mtime.

Coverage:
- R1: fresh last-bar (today) + mtime-fresh  → returns cached, NO download.
- R2: stale last-bar (30 days old) + mtime-fresh → triggers exactly 1 refetch.
- R3: ``_latest_date`` on empty/None frame → returns None, no crash.
- R4: ``_latest_date`` on a bare ``datetime.date`` index (non-Timestamp) → date.
- R5: depth-check (min_start) path still works with a fresh last-bar cache
       (behaviour byte-identical to pre-guard path).
- R6: exact-threshold boundary — last-bar == today-7 stays cached (==7 is NOT >7);
       last-bar == today-8 triggers exactly 1 refetch (8 > 7). Pins the `>`
       operator so a future `>`→`>=` slip cannot silently regress.

All tests are offline (``_yf_download`` monkeypatched throughout).

NOTE: ``compute.ingest.prices`` imports ``yfinance`` at module level.
The stub below ensures this file collects in environments without yfinance.
"""

from __future__ import annotations

import datetime
import sys
import types

import pandas as pd

# ---------------------------------------------------------------------------
# yfinance stub — allows prices.py to import without yfinance installed
# ---------------------------------------------------------------------------


def _stub_yfinance() -> None:
    if "yfinance" in sys.modules:
        return
    yf_stub = types.ModuleType("yfinance")

    def _download(*args, **kwargs):  # noqa: ARG001
        return pd.DataFrame()

    yf_stub.download = _download
    sys.modules["yfinance"] = yf_stub


_stub_yfinance()

# ---------------------------------------------------------------------------
# Imports after stub registration
# ---------------------------------------------------------------------------

from compute.ingest import prices as prices_mod  # noqa: E402
from compute.ingest.prices import _latest_date, fetch_prices  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bday_frame(
    end: datetime.date,
    periods: int,
    close_start: float = 100.0,
) -> pd.DataFrame:
    """Minimal daily price DataFrame ending on *end* (exclusive bdate_range end)."""
    idx = pd.bdate_range(end=end, periods=periods)
    closes = [close_start + i * 0.5 for i in range(periods)]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1.0 for c in closes],
            "Low": [c - 1.0 for c in closes],
            "Close": closes,
            "Adj Close": closes,
            "Volume": [1_000_000] * periods,
        },
        index=idx,
    )


def _frame_last_bar_on(
    end: datetime.date,
    periods: int,
    close_start: float = 100.0,
) -> pd.DataFrame:
    """Like ``_bday_frame`` but GUARANTEES the final bar is exactly ``end``.

    ``pd.bdate_range(end=...)`` snaps a weekend / holiday ``end`` back to the
    prior business day, which silently shifts the last-bar date the recency
    guard (#498) compares against ``today``. For an EXACT calendar-day boundary
    test that is a latent weekend bug: ``today - 7`` landing on a Saturday
    becomes the prior Friday (``today - 8``), flipping the strict ``>`` edge and
    spuriously failing every weekend. Pinning the final index entry to ``end``
    keeps the boundary exact regardless of which weekday the suite runs on.
    """
    frame = _bday_frame(end=end, periods=periods, close_start=close_start)
    idx = frame.index.to_list()
    idx[-1] = pd.Timestamp(end)
    frame.index = pd.DatetimeIndex(idx)
    return frame


# ---------------------------------------------------------------------------
# R1 — Fresh last-bar (today) → cache returned immediately, no download
# ---------------------------------------------------------------------------


def test_R1_fresh_last_bar_returns_cached_no_download(tmp_path, monkeypatch) -> None:
    """R1: cached frame whose last bar is TODAY (calendar_days_stale = 0) must be
    returned directly without triggering ``_yf_download``.

    This is the byte-identical path for a healthy, up-to-date cache.
    """
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_STALE_DAYS", 7)

    today = datetime.date.today()
    frame = _bday_frame(end=today, periods=30)
    (tmp_path / "FRSH.parquet").write_bytes(frame.to_parquet())

    download_calls: list[str] = []

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        download_calls.append(ticker)
        return frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("FRSH")

    assert result is not None, "Fresh-last-bar cache must return a DataFrame"
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 30
    assert len(download_calls) == 0, (
        "Fresh last-bar: no download expected, "
        f"but _yf_download was called {len(download_calls)} time(s)"
    )


# ---------------------------------------------------------------------------
# R2 — Stale last-bar (30 days old) + mtime-fresh → triggers refetch
# ---------------------------------------------------------------------------


def test_R2_stale_last_bar_triggers_one_refetch(tmp_path, monkeypatch) -> None:
    """R2: cached frame whose last bar is 30 days ago (well past the 7-day floor)
    must fall through to ``_yf_download`` exactly once, even though the file's
    mtime looks fresh (GHA cache-restore scenario).

    This is the core latent bug fix: on GHA runners, mtime is reset to "now"
    on every ``actions/cache`` restore, so ``age_hours`` is always 0.  The only
    real freshness signal is the last bar date in the data itself.
    """
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_STALE_DAYS", 7)

    stale_end = datetime.date.today() - datetime.timedelta(days=30)
    stale_frame = _bday_frame(end=stale_end, periods=30)
    (tmp_path / "STALE.parquet").write_bytes(stale_frame.to_parquet())

    today = datetime.date.today()
    fresh_frame = _bday_frame(end=today, periods=30)
    download_calls: list[str] = []

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        download_calls.append(ticker)
        return fresh_frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("STALE")

    assert len(download_calls) == 1, (
        "Stale last-bar must trigger exactly 1 download; "
        f"got {len(download_calls)} call(s)"
    )
    assert result is not None
    # The returned frame is the fresh one from the refetch.
    last = _latest_date(result)
    assert last is not None
    assert last >= stale_end, (
        "Returned frame should be the freshly downloaded one, not the stale cache"
    )


# ---------------------------------------------------------------------------
# R3 — _latest_date on empty/None frame → None, no crash
# ---------------------------------------------------------------------------


def test_R3_latest_date_none_on_empty_frame() -> None:
    """R3: ``_latest_date`` must return ``None`` for empty and None frames without
    raising — the guard treats None as 'unknown, keep existing behaviour (return cached)'.
    """
    assert _latest_date(None) is None, "_latest_date(None) must return None"  # type: ignore[arg-type]
    assert _latest_date(pd.DataFrame()) is None, "_latest_date(empty) must return None"


# ---------------------------------------------------------------------------
# R4 — _latest_date on bare datetime.date index (non-Timestamp)
# ---------------------------------------------------------------------------


def test_R4_latest_date_with_bare_date_index() -> None:
    """R4: ``_latest_date`` must handle a bare ``datetime.date`` index (not a
    pandas Timestamp) and return the correct last date.

    Mirrors the ``_earliest_date`` isinstance branch.
    """
    dates = [
        datetime.date(2025, 1, 2),
        datetime.date(2025, 1, 3),
        datetime.date(2025, 6, 30),
    ]
    df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=dates)
    result = _latest_date(df)
    assert result == datetime.date(2025, 6, 30), (
        f"_latest_date must return the last date; got {result!r}"
    )


# ---------------------------------------------------------------------------
# R5 — depth-check (min_start) path still works correctly with fresh last-bar
# ---------------------------------------------------------------------------


def test_R5_min_start_depth_check_compatible_with_recency_guard(
    tmp_path, monkeypatch
) -> None:
    """R5: the recency guard must NOT break the existing depth-check (min_start)
    logic.  A cache entry that is both deep enough AND has a fresh last bar
    must be returned without download.

    This is the byte-identical regression guard: adding the recency guard
    layer must not cause the warm-cron path (deep + fresh last bar) to
    trigger spurious refetches.
    """
    cache_dir = tmp_path / "prices"
    cache_dir.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_STALE_DAYS", 7)

    today = datetime.date.today()
    # Deep frame: starts before the min_start floor AND has a today last bar.
    deep_frame = _bday_frame(end=today, periods=200)
    deep_frame.to_parquet(cache_dir / "DPR5.parquet")

    download_calls: list[str] = []

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        download_calls.append(ticker)
        return deep_frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    # Use min_start well inside the cached frame's window.
    min_start = today - datetime.timedelta(days=90)
    result = fetch_prices("DPR5", min_start=min_start)

    assert result is not None, "Deep + fresh cache must return a DataFrame"
    assert len(download_calls) == 0, (
        "Deep + fresh cache must NOT trigger a download; "
        f"got {len(download_calls)} call(s)"
    )


# ---------------------------------------------------------------------------
# R6 — Exact threshold boundary: ==7 stays cached, ==8 triggers refetch
# ---------------------------------------------------------------------------


def test_R6_boundary_exact_threshold(tmp_path, monkeypatch) -> None:
    """R6: the recency guard uses strict-greater-than (``>``), so the boundary
    must be exact:

    - last_bar == today - 7 days → ``calendar_days_stale == 7``, NOT > 7
      → cache returned, zero download calls.
    - last_bar == today - 8 days → ``calendar_days_stale == 8`` > 7
      → exactly 1 download triggered.

    This test pins the ``>`` operator so that a future ``>``→``>=`` slip
    (which would treat a 7-day-old cache as stale and trigger a spurious
    refetch on the first trading day after a weekend) fails loudly.
    """
    today = datetime.date.today()

    # ---- sub-case A: last_bar = today - 7 → calendar_days_stale == 7 (NOT > 7)
    cache_dir_a = tmp_path / "a"
    cache_dir_a.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir_a)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_STALE_DAYS", 7)

    end_7 = today - datetime.timedelta(days=7)
    frame_7 = _frame_last_bar_on(end=end_7, periods=30)
    (cache_dir_a / "BND7.parquet").write_bytes(frame_7.to_parquet())

    calls_a: list[str] = []
    fresh_frame = _bday_frame(end=today, periods=30)

    def fake_download_a(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        calls_a.append(ticker)
        return fresh_frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download_a)

    result_a = fetch_prices("BND7")

    assert result_a is not None, "Boundary==7 cache must return a DataFrame"
    assert len(calls_a) == 0, (
        "last_bar == today-7 (calendar_days_stale == 7, NOT > 7) must NOT "
        f"trigger a download; got {len(calls_a)} call(s)"
    )

    # ---- sub-case B: last_bar = today - 8 → calendar_days_stale == 8 (> 7)
    cache_dir_b = tmp_path / "b"
    cache_dir_b.mkdir()
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", cache_dir_b)

    end_8 = today - datetime.timedelta(days=8)
    frame_8 = _frame_last_bar_on(end=end_8, periods=30)
    (cache_dir_b / "BND8.parquet").write_bytes(frame_8.to_parquet())

    calls_b: list[str] = []

    def fake_download_b(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        calls_b.append(ticker)
        return fresh_frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download_b)

    result_b = fetch_prices("BND8")

    assert len(calls_b) == 1, (
        "last_bar == today-8 (calendar_days_stale == 8 > 7) must trigger "
        f"exactly 1 download; got {len(calls_b)} call(s)"
    )
    assert result_b is not None, "Refetched frame (8-day stale) must not be None"
