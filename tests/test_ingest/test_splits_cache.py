"""Offline unit tests for the yfinance split-event cache layer in
``compute.ingest.splits``.

Cache strategy summary (from splits.py module docstring):
- TTL is **mtime-based** (``time.time() - path.stat().st_mtime``), NOT
  last-bar-date.  Split events are date-stamped and stable, so file-mtime
  TTL is the correct freshness mechanism here (unlike prices.py #498).
- ``_CACHE_TTL_SECONDS = config.YFINANCE_INFO_CACHE_MAX_AGE_HOURS * 3600``
  (24h × 3600 = 86400 seconds).
- Cache lives at ``compute/cache/yfinance_splits/<TICKER>.json``.
- Graceful degradation: any fetch/read failure returns ``None``.

Coverage:
- S1: Fresh mtime (age < TTL) → returns events WITHOUT calling the live
      ``_yf_fetch_splits`` fetcher.
- S2: Expired mtime (age > TTL) → falls through to live re-fetch, writes
      new cache entry, returns fresh events.
- S3: Corrupt JSON cache file → ``_cache_read`` returns ``None`` without
      raising; subsequent live fetch runs normally.
- S4: ``_cache_write`` → ``_cache_read`` round-trip: written events survive
      JSON serialisation and are decoded back to identical ``SplitEvent``
      instances (atomic-rename path).
- S5: Warm cache → ``_yf_fetch_splits`` is NEVER invoked (verifies the
      short-circuit in ``fetch_splits``).
- S6: ``QR_SKIP_SPLITS=1`` with a **present-but-stale** cache → returns
      the stale events (TTL check is bypassed, no live fetch attempted).
- S7: ``QR_SKIP_SPLITS=1`` with **no cache** → returns ``None`` immediately
      without touching ``_yf_fetch_splits``.
- S8: Empty list (no splits found) round-trips cleanly; ``fetch_splits``
      returns ``[]`` (not ``None``) — callers distinguish "empty list =
      clean fetch, no events" from "None = fetch error".

All tests are offline: ``_yf_fetch_splits`` is monkeypatched throughout
so no yfinance network calls are made.
"""

from __future__ import annotations

import json
import os
import sys
import time
import types
from datetime import date
from pathlib import Path

import pytest


def _stub_yfinance() -> None:
    if "yfinance" in sys.modules:
        return
    yf_stub = types.ModuleType("yfinance")

    class _FakeTicker:
        def __init__(self, ticker: str) -> None:  # noqa: ARG002
            self.splits = None

    yf_stub.Ticker = _FakeTicker
    sys.modules["yfinance"] = yf_stub


_stub_yfinance()

# ---------------------------------------------------------------------------
# Imports after stub registration
# ---------------------------------------------------------------------------

from compute.ingest import splits as splits_mod  # noqa: E402
from compute.ingest.splits import (  # noqa: E402
    SplitEvent,
    _cache_read,
    _cache_write,
    fetch_splits,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TICKER = "KLAC"
_SPLIT_DAY = date(2026, 6, 12)
_RATIO = 10.0

_SAMPLE_EVENTS: list[SplitEvent] = [
    SplitEvent(split_date=_SPLIT_DAY, ratio=_RATIO),
]


def _write_fresh_cache(cache_dir: Path, ticker: str, events: list[SplitEvent]) -> Path:
    """Write a synthetic cache entry with NOW mtime (within TTL)."""
    path = cache_dir / f"{ticker}.json"
    payload = {
        "splits": [
            {"date": e.split_date.isoformat(), "ratio": e.ratio}
            for e in events
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _backdate_mtime(path: Path, age_seconds: float) -> None:
    """Set mtime to ``age_seconds`` in the past so cache reads interpret it as stale."""
    now = time.time()
    past = now - age_seconds
    os.utime(path, (past, past))


# ---------------------------------------------------------------------------
# S1 — Fresh mtime → cache hit, no live fetch
# ---------------------------------------------------------------------------


def test_S1_fresh_cache_returns_events_without_live_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S1: a cache file whose mtime is well within the 24h TTL must be
    returned by ``_cache_read`` without invoking ``_yf_fetch_splits``.

    This is the warm-cron path: every ticker within 24h should be served
    from disk, never adding to the yfinance rate-limit budget.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    _write_fresh_cache(cache_dir, _TICKER, _SAMPLE_EVENTS)
    # mtime is "now" → age ≈ 0 seconds → well within 86400s TTL.

    fetch_calls: list[str] = []

    def fake_yf_fetch(ticker: str) -> list[SplitEvent]:
        fetch_calls.append(ticker)
        return []

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", fake_yf_fetch)

    result = fetch_splits(_TICKER)

    assert result is not None, "Fresh cache must return a list, not None"
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].split_date == _SPLIT_DAY
    assert result[0].ratio == _RATIO
    assert len(fetch_calls) == 0, (
        f"Fresh cache hit must not call _yf_fetch_splits, "
        f"but it was called {len(fetch_calls)} time(s)"
    )


# ---------------------------------------------------------------------------
# S2 — Expired mtime → live re-fetch triggered, cache refreshed
# ---------------------------------------------------------------------------


def test_S2_expired_cache_triggers_live_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2: a cache file whose mtime is beyond the 24h TTL must fall through
    to ``_yf_fetch_splits`` exactly once, and the returned events must
    be the live-fetched ones.

    This locks the in-process mtime-TTL code path. NOTE per #501: the
    splits cache is NOT in any GHA bundle — in CI/cron it is cold-every-run
    live fetch (mtime-TTL is dead under ``actions/cache`` restore, same
    class as #471/#498). So this test exercises the LOCAL / in-run TTL
    logic via ``os.utime`` backdating, not a cross-run freshness guarantee.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    stale_events = [SplitEvent(split_date=date(2020, 1, 1), ratio=2.0)]
    cache_file = _write_fresh_cache(cache_dir, _TICKER, stale_events)
    # Backdate mtime by 86401 seconds (24h + 1s → just past the TTL).
    ttl = splits_mod._CACHE_TTL_SECONDS
    _backdate_mtime(cache_file, ttl + 1)

    fresh_events = [SplitEvent(split_date=_SPLIT_DAY, ratio=_RATIO)]
    fetch_calls: list[str] = []

    def fake_yf_fetch(ticker: str) -> list[SplitEvent]:
        fetch_calls.append(ticker)
        return fresh_events

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", fake_yf_fetch)

    result = fetch_splits(_TICKER)

    assert len(fetch_calls) == 1, (
        f"Expired cache must trigger exactly 1 live fetch; "
        f"got {len(fetch_calls)} call(s)"
    )
    assert result is not None
    assert result[0].split_date == _SPLIT_DAY, (
        "Returned events must be from the live fetch, not the stale cache"
    )
    # Cache file must have been refreshed (mtime is now recent).
    new_age = time.time() - cache_file.stat().st_mtime
    assert new_age < 5.0, (
        f"Cache file mtime must be updated after re-fetch; age={new_age:.1f}s"
    )


# ---------------------------------------------------------------------------
# S3 — Corrupt JSON → _cache_read returns None gracefully
# ---------------------------------------------------------------------------


def test_S3_corrupt_json_cache_returns_none_no_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S3: a cache file containing invalid JSON must cause ``_cache_read``
    to return ``None`` without raising an exception.

    Graceful-degradation contract: cache corruption silently triggers a
    live re-fetch (the ``except (OSError, json.JSONDecodeError)`` guard
    in ``_cache_read`` covers this).
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    corrupt_path = cache_dir / f"{_TICKER}.json"
    corrupt_path.write_text("not valid JSON {{{{", encoding="utf-8")
    # mtime is fresh so it wouldn't expire — only corruption causes None.

    result = _cache_read(_TICKER)

    assert result is None, (
        "_cache_read must return None on corrupt JSON, not raise"
    )


def test_S3b_corrupt_json_fetch_splits_triggers_live_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S3b: when ``_cache_read`` returns None due to corruption,
    ``fetch_splits`` must proceed to live fetch and return those events.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    corrupt_path = cache_dir / f"{_TICKER}.json"
    corrupt_path.write_text("{broken", encoding="utf-8")

    fetch_calls: list[str] = []

    def fake_yf_fetch(ticker: str) -> list[SplitEvent]:
        fetch_calls.append(ticker)
        return _SAMPLE_EVENTS

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", fake_yf_fetch)

    result = fetch_splits(_TICKER)

    assert len(fetch_calls) == 1, (
        "Corrupt cache must fall through to one live fetch"
    )
    assert result is not None
    assert result[0].split_date == _SPLIT_DAY


# ---------------------------------------------------------------------------
# S4 — _cache_write → _cache_read round-trip
# ---------------------------------------------------------------------------


def test_S4_cache_write_read_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4: ``_cache_write`` followed by ``_cache_read`` must return
    SplitEvent instances identical to the originals.

    Verifies:
    - ISO date serialisation/deserialisation is lossless.
    - Ratio float round-trips exactly.
    - Atomic rename succeeded (no .tmp file left over).
    - ``_cache_read`` correctly assembles ``SplitEvent`` dataclasses.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    events_in = [
        SplitEvent(split_date=date(2026, 6, 12), ratio=10.0),
        SplitEvent(split_date=date(2020, 8, 31), ratio=4.0),
    ]

    _cache_write(_TICKER, events_in)

    # Verify no .tmp file lingers (atomic rename complete).
    tmp_path_file = cache_dir / f"{_TICKER}.json.tmp"
    assert not tmp_path_file.exists(), "Atomic rename must remove the .tmp file"

    # Verify the final file exists.
    final_path = cache_dir / f"{_TICKER}.json"
    assert final_path.exists(), "Cache file must exist after _cache_write"

    events_out = _cache_read(_TICKER)

    assert events_out is not None, "_cache_read must succeed immediately after _cache_write"
    assert len(events_out) == len(events_in), (
        f"Round-trip must preserve event count: expected {len(events_in)}, got {len(events_out)}"
    )
    # Compare field-by-field (SplitEvent is a frozen dataclass).
    for original, restored in zip(events_in, events_out, strict=True):
        assert restored.split_date == original.split_date, (
            f"Date round-trip failed: {original.split_date!r} → {restored.split_date!r}"
        )
        assert restored.ratio == original.ratio, (
            f"Ratio round-trip failed: {original.ratio} → {restored.ratio}"
        )


# ---------------------------------------------------------------------------
# S5 — Warm cache → _yf_fetch_splits NEVER invoked
# ---------------------------------------------------------------------------


def test_S5_warm_cache_yf_fetch_never_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5: the complete ``fetch_splits`` path with a warm (fresh-mtime)
    cache must NOT invoke ``_yf_fetch_splits`` even once.

    This mirrors the D1 test in test_eight_k_ttl_jitter.py — the outer
    public API is what callers use, and the network guard must hold at
    that level.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    _write_fresh_cache(cache_dir, _TICKER, _SAMPLE_EVENTS)

    yf_invocations: list[str] = []

    def sentinel_fetch(ticker: str) -> list[SplitEvent]:
        yf_invocations.append(ticker)
        raise AssertionError("_yf_fetch_splits must not be called on a warm cache")

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", sentinel_fetch)

    result = fetch_splits(_TICKER)

    assert yf_invocations == [], (
        f"_yf_fetch_splits invoked {len(yf_invocations)} time(s) on a warm cache; "
        "must be 0"
    )
    assert result is not None
    assert len(result) == len(_SAMPLE_EVENTS)


# ---------------------------------------------------------------------------
# S6 — QR_SKIP_SPLITS=1 with present (stale-mtime) cache → stale events returned
# ---------------------------------------------------------------------------


def test_S6_qr_skip_splits_present_stale_cache_returns_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6: when ``QR_SKIP_SPLITS=1`` is set, a cache file that is present
    but would normally be considered stale (age > TTL) must be returned
    AS-IS without calling ``_yf_fetch_splits``.

    This is the CI pre-merge-prod-sim path: no live fetch is permitted in
    the sim budget, so a present-but-stale cache (= some events) is returned
    AS-IS in preference to None (= miss-treated as "no split"). Per #501 the
    splits cache is NOT bundled, so in real CI the file is simply absent
    (cold) and S7 covers that branch; this test pins the present-stale case.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)
    monkeypatch.setenv("QR_SKIP_SPLITS", "1")

    stale_events = [SplitEvent(split_date=date(2025, 3, 1), ratio=3.0)]
    cache_file = _write_fresh_cache(cache_dir, _TICKER, stale_events)
    # Backdate so normal TTL check would reject it.
    ttl = splits_mod._CACHE_TTL_SECONDS
    _backdate_mtime(cache_file, ttl + 3600)  # 1h beyond TTL

    fetch_calls: list[str] = []

    def no_network_fetch(ticker: str) -> list[SplitEvent]:
        fetch_calls.append(ticker)
        raise AssertionError("Network fetch must not run when QR_SKIP_SPLITS=1")

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", no_network_fetch)

    result = fetch_splits(_TICKER)

    assert len(fetch_calls) == 0, (
        "QR_SKIP_SPLITS=1 must not invoke _yf_fetch_splits"
    )
    assert result is not None, (
        "QR_SKIP_SPLITS=1 with present (stale) cache must return events, not None"
    )
    assert len(result) == 1
    assert result[0].split_date == date(2025, 3, 1)


# ---------------------------------------------------------------------------
# S7 — QR_SKIP_SPLITS=1 with NO cache → returns None immediately
# ---------------------------------------------------------------------------


def test_S7_qr_skip_splits_cold_cache_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S7: when ``QR_SKIP_SPLITS=1`` is set and there is no cache file at
    all, ``fetch_splits`` must return ``None`` immediately.

    Contract from the module docstring: "A genuinely cold cache → None
    returned; no live fetch."  The flag suppresses the live-fetch fallback
    that would normally run on a cache miss.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)
    monkeypatch.setenv("QR_SKIP_SPLITS", "1")

    fetch_calls: list[str] = []

    def no_network_fetch(ticker: str) -> list[SplitEvent]:
        fetch_calls.append(ticker)
        raise AssertionError("Network fetch must not run when QR_SKIP_SPLITS=1 + cold cache")

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", no_network_fetch)

    result = fetch_splits("COLD_TICKER")

    assert result is None, (
        "QR_SKIP_SPLITS=1 with no cache file must return None, not an empty list"
    )
    assert len(fetch_calls) == 0


# ---------------------------------------------------------------------------
# S8 — Empty events list round-trips cleanly; fetch_splits returns [] not None
# ---------------------------------------------------------------------------


def test_S8_empty_events_list_roundtrips_and_is_not_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S8: a ticker with no historical splits should yield an empty list
    (not None) from ``fetch_splits``.

    Callers MUST distinguish:
    - ``[]`` (empty list) = successful fetch that found no events.
    - ``None``            = fetch error / graceful degradation.

    This test verifies:
    (a) ``_cache_write(ticker, [])`` then ``_cache_read`` returns ``[]``,
        not ``None``.
    (b) ``fetch_splits`` with a warmed empty-list cache returns ``[]``
        without touching the live fetcher.
    """
    cache_dir = tmp_path / "yfinance_splits"
    cache_dir.mkdir()
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", cache_dir)

    # Write an empty-list cache entry.
    _cache_write(_TICKER, [])

    # Round-trip: _cache_read must return [] (not None).
    cached = _cache_read(_TICKER)
    assert cached is not None, "_cache_read must return [] for empty splits, not None"
    assert cached == [], f"Expected empty list, got {cached!r}"

    # fetch_splits must also return [] (not None) for the same warm cache.
    fetch_calls: list[str] = []

    def no_live_fetch(ticker: str) -> list[SplitEvent]:
        fetch_calls.append(ticker)
        return []

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", no_live_fetch)

    result = fetch_splits(_TICKER)

    assert result is not None, (
        "fetch_splits must return [] (not None) when the ticker has no splits"
    )
    assert result == []
    assert len(fetch_calls) == 0, (
        "Warm empty-list cache must not trigger a live fetch"
    )
