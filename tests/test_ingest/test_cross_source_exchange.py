"""Tests for exchange/country helpers added to compute.ingest.cross_source (PR-A1).

Coverage:
    - exchange_name(): every known code → display name, unknown passthrough, None/empty → None
    - country_for_exchange(): US codes → "US", unknown/None/empty → None
    - _exchange_cache_read / _exchange_cache_write round-trips (tmp_path + monkeypatched
      config.YFINANCE_INFO_CACHE_DIR), including merge-into-existing-file, TTL expiry,
      corrupt/missing file
    - fetch_yfinance_exchange(): QR_SKIP_CROSS_SOURCE=1 with cache present → returns
      cached value; with no cache → returns None; without skip-flag → normal cache path
    - @pytest.mark.network: live AAPL exchange maps to "NASDAQ" (NMS code)

No test uses @settings(deadline=None) — a slow example is itself a signal.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from compute import config
from compute.ingest.cross_source import (
    _EXCHANGE_NAME_BY_CODE,
    _US_EXCHANGE_CODES,
    _exchange_cache_read,
    _exchange_cache_write,
    country_for_exchange,
    exchange_name,
    fetch_yfinance_exchange,
)

# ---------------------------------------------------------------------------
# Pure-helper tests: exchange_name — no I/O, no mocks needed
# ---------------------------------------------------------------------------

# Every code defined in _EXCHANGE_NAME_BY_CODE → expected display name
_KNOWN_CODE_CASES: list[tuple[str, str]] = [
    ("NMS", "NASDAQ"),
    ("NGM", "NASDAQ"),
    ("NCM", "NASDAQ"),
    ("NyseArca", "NYSE Arca"),
    ("PCX", "NYSE Arca"),
    ("NYQ", "NYSE"),
    ("ASE", "NYSE American"),
    ("BATS", "Cboe BZX"),
    ("BTS", "Cboe BZX"),
]


@pytest.mark.parametrize("code, expected_name", _KNOWN_CODE_CASES)
def test_exchange_name_known_code(code: str, expected_name: str) -> None:
    """Every known S&P-500-universe exchange code maps to its canonical display name."""
    assert exchange_name(code) == expected_name


def test_cboe_bts_code_resolves_exchange_and_country() -> None:
    """Regression (2026-06-02 post-cron audit) — CBOE Global Markets self-lists
    on its own Cboe BZX venue, for which yfinance emits the terse ``BTS`` code
    (DISTINCT from ``BATS``). Before the fix, ``BTS`` passed through raw as the
    exchange name AND resolved to no country (absent from _US_EXCHANGE_CODES),
    so CBOE rendered a "BTS" chip with no US flag. Both must now resolve.
    """
    assert exchange_name("BTS") == "Cboe BZX"
    assert country_for_exchange("BTS") == "US"


def test_exchange_name_unknown_code_passes_through() -> None:
    """An unrecognized code (e.g. a London Stock Exchange code) passes through verbatim.

    The forward-safe design means showing raw codes is better than dropping them.
    """
    assert exchange_name("XLON") == "XLON"
    assert exchange_name("FOO") == "FOO"


def test_exchange_name_none_returns_none() -> None:
    """None input → None output (no display name possible)."""
    assert exchange_name(None) is None


def test_exchange_name_empty_string_returns_none() -> None:
    """Empty string is falsy → treated identically to None."""
    assert exchange_name("") is None


# ---------------------------------------------------------------------------
# Pure-helper tests: country_for_exchange
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", list(_EXCHANGE_NAME_BY_CODE.keys()))
def test_country_for_exchange_us_codes_return_us(code: str) -> None:
    """Every code in the known-exchange map returns 'US' as the country tag."""
    assert country_for_exchange(code) == "US"


def test_country_for_exchange_unknown_code_returns_none() -> None:
    """A foreign or unrecognized exchange code returns None (display layer shows '—')."""
    assert country_for_exchange("XLON") is None
    assert country_for_exchange("TYO") is None


def test_country_for_exchange_none_returns_none() -> None:
    """None input → None output."""
    assert country_for_exchange(None) is None


def test_country_for_exchange_empty_string_returns_none() -> None:
    """Empty string is falsy → None."""
    assert country_for_exchange("") is None


# ---------------------------------------------------------------------------
# Consistency invariant: _EXCHANGE_NAME_BY_CODE keys ↔ _US_EXCHANGE_CODES
# ---------------------------------------------------------------------------

def test_us_exchange_codes_matches_name_map_keys() -> None:
    """_US_EXCHANGE_CODES must be exactly the key-set of _EXCHANGE_NAME_BY_CODE.

    This invariant is load-bearing: country_for_exchange derives its 'US' logic
    from _US_EXCHANGE_CODES, while exchange_name uses _EXCHANGE_NAME_BY_CODE.
    If they drift, a new code could return a display name but the wrong country.
    """
    assert _US_EXCHANGE_CODES == frozenset(_EXCHANGE_NAME_BY_CODE.keys())


# ---------------------------------------------------------------------------
# Cache round-trip tests (_exchange_cache_read / _exchange_cache_write)
# ---------------------------------------------------------------------------

def test_exchange_cache_write_then_read(tmp_path: Path, monkeypatch) -> None:
    """Write an exchange code → read it back within TTL → same string returned."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    _exchange_cache_write("AAPL", "NMS")
    result = _exchange_cache_read("AAPL")
    assert result == "NMS"


def test_exchange_cache_write_merges_into_existing_market_cap(
    tmp_path: Path, monkeypatch
) -> None:
    """Writing an exchange code into a file that already has market_cap preserves it.

    The merge design allows one Ticker round-trip to populate both fields without
    overwriting a previously cached market_cap.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    # Pre-populate market_cap (simulating a prior fetch_yfinance_market_cap call)
    cache_file = tmp_path / "MSFT.json"
    cache_file.write_text(json.dumps({"market_cap": 3_000_000_000_000.0}))

    _exchange_cache_write("MSFT", "NMS")

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["exchange"] == "NMS"
    assert payload["market_cap"] == pytest.approx(3_000_000_000_000.0)


def test_exchange_cache_read_missing_file_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """A ticker with no cache file → None (cache miss)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    assert _exchange_cache_read("MISSING") is None


def test_exchange_cache_read_corrupt_json_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """A cache file containing invalid JSON → None (quiet-skip, not an exception)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "CORRUPT.json"
    cache_file.write_text("this is not json{{{", encoding="utf-8")
    assert _exchange_cache_read("CORRUPT") is None


def test_exchange_cache_read_expired_ttl_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """A cache file older than _CACHE_TTL_SECONDS → None (expired)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    _exchange_cache_write("TSLA", "NMS")

    cache_file = tmp_path / "TSLA.json"
    # Back-date mtime well past the TTL
    expired_mtime = time.time() - (config.YFINANCE_INFO_CACHE_MAX_AGE_HOURS * 3600 + 60)
    import os
    os.utime(cache_file, (expired_mtime, expired_mtime))

    assert _exchange_cache_read("TSLA") is None


def test_exchange_cache_read_file_without_exchange_key_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """A cache file with only market_cap (pre-PR-A1 file) → None for exchange.

    Backward-compat: old cache entries simply have no 'exchange' key.
    A subsequent fetch_yfinance_exchange call will re-populate it.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "GE.json"
    cache_file.write_text(json.dumps({"market_cap": 100_000_000_000.0}))
    assert _exchange_cache_read("GE") is None


def test_exchange_cache_write_on_nonexistent_dir_creates_it(
    tmp_path: Path, monkeypatch
) -> None:
    """The cache writer calls mkdir(parents=True, exist_ok=True) so a missing dir is created."""
    nested = tmp_path / "nested" / "yfinance_info"
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", nested)
    _exchange_cache_write("JPM", "NYQ")
    assert (nested / "JPM.json").exists()


def test_exchange_cache_write_preserves_no_extra_keys(
    tmp_path: Path, monkeypatch
) -> None:
    """The written payload contains 'exchange' and any previously existing key — no extras."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    _exchange_cache_write("V", "NYQ")
    payload = json.loads((tmp_path / "V.json").read_text(encoding="utf-8"))
    # Only the exchange key on a fresh write
    assert set(payload.keys()) == {"exchange"}
    assert payload["exchange"] == "NYQ"


# ---------------------------------------------------------------------------
# fetch_yfinance_exchange: QR_SKIP_CROSS_SOURCE path
# ---------------------------------------------------------------------------

def test_fetch_yfinance_exchange_skip_with_cache_returns_cached(
    tmp_path: Path, monkeypatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + cache present → returns cached code, no live fetch."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    # Write a stale file (TTL irrelevant under SKIP mode)
    cache_file = tmp_path / "AAPL.json"
    cache_file.write_text(json.dumps({"exchange": "NMS", "market_cap": 3e12}))

    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fetch:
        result = fetch_yfinance_exchange("AAPL")

    assert result == "NMS"
    mock_fetch.assert_not_called()


def test_fetch_yfinance_exchange_skip_without_cache_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + no cache → None (no live fetch attempted)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    # No cache file exists

    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fetch:
        result = fetch_yfinance_exchange("NVDA")

    assert result is None
    mock_fetch.assert_not_called()


def test_fetch_yfinance_exchange_skip_with_cache_missing_exchange_key_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + cache present but no 'exchange' key → None.

    A pre-PR-A1 cache entry for a ticker has only 'market_cap'; the skip path
    must return None instead of raising a TypeError on missing key.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    cache_file = tmp_path / "META.json"
    cache_file.write_text(json.dumps({"market_cap": 1.4e12}))

    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fetch:
        result = fetch_yfinance_exchange("META")

    assert result is None
    mock_fetch.assert_not_called()


def test_fetch_yfinance_exchange_skip_with_corrupt_cache_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + corrupt cache → None (quiet-skip, not an exception)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    cache_file = tmp_path / "WMT.json"
    cache_file.write_text("{{invalid json}}", encoding="utf-8")

    result = fetch_yfinance_exchange("WMT")
    assert result is None


# ---------------------------------------------------------------------------
# fetch_yfinance_exchange: normal (non-skip) cache-first path
# ---------------------------------------------------------------------------

def test_fetch_yfinance_exchange_cache_hit_no_live_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    """Fresh cache file with 'exchange' key → returns it without hitting yfinance."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)
    cache_file = tmp_path / "MSFT.json"
    cache_file.write_text(json.dumps({"exchange": "NMS"}))

    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fetch:
        result = fetch_yfinance_exchange("MSFT")

    assert result == "NMS"
    mock_fetch.assert_not_called()


def test_fetch_yfinance_exchange_cache_miss_calls_live_and_writes_cache(
    tmp_path: Path, monkeypatch
) -> None:
    """Cache miss → live fetch → result written back to cache."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    with patch(
        "compute.ingest.cross_source._yf_fast_exchange", return_value="NYQ"
    ) as mock_fetch:
        result = fetch_yfinance_exchange("JPM")

    assert result == "NYQ"
    mock_fetch.assert_called_once_with("JPM")
    written = json.loads((tmp_path / "JPM.json").read_text())
    assert written["exchange"] == "NYQ"


def test_fetch_yfinance_exchange_live_failure_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    """Persistent live fetch failure → None (quiet-skip, never raises)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    with patch(
        "compute.ingest.cross_source._yf_fast_exchange",
        side_effect=Exception("network error"),
    ):
        result = fetch_yfinance_exchange("AAPL")

    assert result is None
    # No partial file should be written on failure
    assert not (tmp_path / "AAPL.json").exists()


def test_fetch_yfinance_exchange_live_returns_none_not_written(
    tmp_path: Path, monkeypatch
) -> None:
    """If live fetch returns None (yfinance gap), nothing is cached and None returned."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    with patch("compute.ingest.cross_source._yf_fast_exchange", return_value=None):
        result = fetch_yfinance_exchange("BRK-A")

    assert result is None
    assert not (tmp_path / "BRK-A.json").exists()


# ---------------------------------------------------------------------------
# Network-gated live drift test — skipped unless --run-network
# ---------------------------------------------------------------------------

@pytest.mark.network
def test_live_fetch_yfinance_exchange_aapl_is_nasdaq(
    tmp_path: Path, monkeypatch
) -> None:
    """AAPL is listed on NASDAQ (NMS tier). Drift detector: if this fails, yfinance
    changed their exchange code for AAPL, or AAPL moved to a new venue.

    Max acceptable duration: ~5 s (yfinance fast_info is the lightweight scraper).
    """
    import time as _time

    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    t0 = _time.monotonic()
    raw_code = fetch_yfinance_exchange("AAPL")
    elapsed = _time.monotonic() - t0

    assert raw_code is not None, "Expected a non-None exchange code for AAPL"
    display = exchange_name(raw_code)
    assert display == "NASDAQ", (
        f"Expected AAPL to map to 'NASDAQ', got raw_code={raw_code!r}, display={display!r}"
    )
    assert elapsed < 30.0, f"Live exchange fetch took {elapsed:.1f}s — SEC throttling?"
