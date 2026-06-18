"""Tests for leg-3 robustness fix in compute.ingest.cross_source (PR #499).

Coverage:
    - fetch_yfinance_shares_outstanding: warm-cache read returns shares_outstanding
      from the yfinance_info/<ticker>.json file (no live fetch triggered).
    - fetch_yfinance_shares_outstanding: QR_SKIP_CROSS_SOURCE=1 + cold cache → None,
      no exception, _yf_info_fetch never called.
    - fetch_yfinance_shares_outstanding: old-format cache (no shares_outstanding key)
      → None (backward-compat with pre-0.10.25 cache entries).
    - _cache_write merge semantics: (a) shares_outstanding=None → key absent in file;
      (b) _exchange_cache_write after _cache_write → shares_outstanding survives the
      merge (exchange write must not clobber the shares_outstanding field).

No test uses @settings(deadline=None) — a slow example is itself a signal.
No test is marked @network — all use synthetic tmp_path fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from compute import config
from compute.ingest.cross_source import (
    _cache_write,
    _exchange_cache_write,
    _shares_outstanding_cache_read,
    fetch_yfinance_shares_outstanding,
)

# ---------------------------------------------------------------------------
# CS_SO1 — warm-cache read: returns shares_outstanding, no live fetch
#
# When the yfinance_info/<ticker>.json file has both market_cap and
# shares_outstanding (written by an earlier fetch_yfinance_market_cap call),
# fetch_yfinance_shares_outstanding must be a pure cache read at zero network
# cost.  We confirm _yf_info_fetch is never called.
# ---------------------------------------------------------------------------


def test_CS_SO1_warm_cache_read_returns_shares_outstanding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm cache with shares_outstanding key → value returned, no live fetch.

    Simulates the common case: fetch_yfinance_market_cap already ran in the
    same Step-3b loop iteration and wrote both market_cap + shares_outstanding
    into the cache file.  This function must be a pure zero-cost cache read.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    # Write a warm cache file with both fields (mirrors _cache_write output).
    cache_file = tmp_path / "KLAC.json"
    cache_file.write_text(
        json.dumps({"market_cap": 1e11, "shares_outstanding": 1_306_275_210.0}),
        encoding="utf-8",
    )

    # Guard: _yf_info_fetch must not be called (it would hit the network).
    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_shares_outstanding("KLAC")

    assert result == pytest.approx(1_306_275_210.0), (
        f"Expected 1306275210.0 from warm cache, got {result}"
    )
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_SO2 — QR_SKIP_CROSS_SOURCE=1 + cold cache → None, no fetch
#
# When the escape hatch is set and the cache file is absent, the function
# must return None without attempting a live yfinance call.  Used by the
# pre-merge-prod-sim to skip the serial yfinance loop.
# ---------------------------------------------------------------------------


def test_CS_SO2_skip_env_cold_cache_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 with no cache file → None, _yf_info_fetch not called."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    # No cache file exists for this ticker.

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_shares_outstanding("TSLA")

    assert result is None, (
        "QR_SKIP_CROSS_SOURCE=1 + cold cache must return None"
    )
    mock_fetch.assert_not_called()


def test_CS_SO2_skip_env_warm_cache_returns_shares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + warm cache with shares_outstanding → stale value returned.

    The stale-tolerant path bypasses the 24h TTL gate and returns the cached
    value directly — same semantics as fetch_yfinance_market_cap under SKIP.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    cache_file = tmp_path / "NVDA.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3e12, "shares_outstanding": 24_440_000_000.0}),
        encoding="utf-8",
    )

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_shares_outstanding("NVDA")

    assert result == pytest.approx(24_440_000_000.0)
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_SO3 — old-format cache (no shares_outstanding key) → None
#
# Cache files written before the leg-3 fix (PR #499) contain only market_cap
# (and possibly exchange). The shares_outstanding key is absent.  The function
# must return None rather than raise, so the caller falls back to the
# market_cap/price path for leg 3.
# ---------------------------------------------------------------------------


def test_CS_SO3_old_format_cache_no_shares_key_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache file with only market_cap (pre-0.10.25 format) → None for shares.

    Backward-compat: _shares_outstanding_cache_read must return None when
    the 'shares_outstanding' key is absent — it was never written by the
    older _yf_info_market_cap path.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "AAPL.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3.5e12}),  # only market_cap, no shares_outstanding
        encoding="utf-8",
    )

    result = fetch_yfinance_shares_outstanding("AAPL")
    assert result is None, (
        "Cache file without 'shares_outstanding' key must return None "
        "(backward-compat with pre-0.10.25 cache files)"
    )


def test_CS_SO3_shares_outstanding_cache_read_absent_key_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_shares_outstanding_cache_read returns None when the key is absent."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "GE.json"
    cache_file.write_text(json.dumps({"market_cap": 1e11, "exchange": "NYQ"}))

    result = _shares_outstanding_cache_read("GE")
    assert result is None


# ---------------------------------------------------------------------------
# CS_SO4 — _cache_write merge semantics
#
# (a) shares_outstanding=None → key NOT written to the file.
#     The function contract says: "when shares_outstanding is None it is NOT
#     written" — important because None would poison a later read.
#
# (b) _exchange_cache_write after _cache_write → shares_outstanding SURVIVES.
#     The exchange write is a merge-write (reads existing JSON, adds/updates
#     'exchange', rewrites) — it must not clobber a previously written
#     'shares_outstanding' field from _cache_write.
# ---------------------------------------------------------------------------


def test_CS_SO4a_cache_write_none_shares_key_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_cache_write(shares_outstanding=None) must NOT write the key to the file.

    A None shares_outstanding means the field was not returned by yfinance
    (e.g. old API, None field); writing it would poison the cache with a
    sentinel value that later reads would reject anyway.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    _cache_write("MSFT", market_cap=3e12, shares_outstanding=None)

    payload = json.loads((tmp_path / "MSFT.json").read_text(encoding="utf-8"))
    assert "shares_outstanding" not in payload, (
        "_cache_write(shares_outstanding=None) must not write the key to the file"
    )
    assert payload.get("market_cap") == pytest.approx(3e12)


def test_CS_SO4b_exchange_write_does_not_clobber_shares_outstanding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_exchange_cache_write after _cache_write → shares_outstanding SURVIVES.

    Scenario: _cache_write writes {market_cap, shares_outstanding}; then
    _exchange_cache_write is called (mirrors the main.py Step 8 / exchange
    fetch path).  The exchange write must merge, not replace, so the
    shares_outstanding field is preserved.

    This is the key invariant the PR #499 merge-write pattern defends.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    # Step 1: write both fields via _cache_write.
    _cache_write("JPM", market_cap=5e11, shares_outstanding=2_900_000_000.0)

    # Verify the initial write captured shares_outstanding.
    payload_before = json.loads((tmp_path / "JPM.json").read_text(encoding="utf-8"))
    assert payload_before.get("shares_outstanding") == pytest.approx(2_900_000_000.0)

    # Step 2: exchange write (merge) must not destroy shares_outstanding.
    _exchange_cache_write("JPM", "NYQ")

    payload_after = json.loads((tmp_path / "JPM.json").read_text(encoding="utf-8"))
    assert payload_after.get("shares_outstanding") == pytest.approx(2_900_000_000.0), (
        "_exchange_cache_write must preserve 'shares_outstanding' written by _cache_write"
    )
    assert payload_after.get("market_cap") == pytest.approx(5e11), (
        "_exchange_cache_write must preserve 'market_cap' (basic merge invariant)"
    )
    assert payload_after.get("exchange") == "NYQ", (
        "_exchange_cache_write must write the exchange field"
    )


def test_CS_SO4b_cache_write_merge_preserves_existing_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_cache_write when the file already has an 'exchange' key must preserve it.

    Reverse direction of the same merge invariant: exchange arrived first
    (from fetch_yfinance_exchange), then _cache_write is called.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    # Pre-seed with an exchange key (simulating an earlier exchange fetch).
    cache_file = tmp_path / "V.json"
    cache_file.write_text(json.dumps({"exchange": "NYQ"}))

    # Now write market_cap + shares_outstanding.
    _cache_write("V", market_cap=5e11, shares_outstanding=1_800_000_000.0)

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload.get("exchange") == "NYQ", (
        "_cache_write must preserve existing 'exchange' key (merge semantics)"
    )
    assert payload.get("shares_outstanding") == pytest.approx(1_800_000_000.0)
    assert payload.get("market_cap") == pytest.approx(5e11)
