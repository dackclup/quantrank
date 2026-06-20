"""Tests for fetch_yfinance_dividend + dividend-field cache semantics (Dividend signal PR-1).

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added to the
output schema" and "when a new defense ships" — this file satisfies that policy for the
Dividend signal PR-1 (roadmap item #5 / 7a, schema 0.10.27-phase8pilot).

Tests
-----
CS_DIV1 — warm-cache hit with dividend data → correct 3-tuple returned
CS_DIV2 — zero-yield cache entry → (0.0, False, None) and pays_dividend=False
CS_DIV3 — cold cache → (None, None, None), no live fetch
CS_DIV4 — QR_SKIP_CROSS_SOURCE=1: stale cache → returns values; cold → (None, None, None)
CS_DIV5 — old-format cache (no dividend keys, pre-0.10.27) → (None, None, None) (backward-compat)
CS_DIV6 — _yf_info_fetch 4-tuple: dividend fields written to cache alongside market_cap
           (the live path in fetch_yfinance_market_cap writes all 4 fields in one shot)

Style mirrors tests/test_ingest/test_cross_source_shares.py (the most recent cross_source
test in this module) — synthetic tmp_path fixtures, monkeypatch for YFINANCE_INFO_CACHE_DIR,
no @settings(deadline=None), no @network markers.

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
    _dividend_cache_read,
    fetch_yfinance_dividend,
    fetch_yfinance_market_cap,
)

# ---------------------------------------------------------------------------
# CS_DIV1 — warm-cache hit with positive dividend data
#
# The yfinance_info/<ticker>.json was previously written by
# fetch_yfinance_market_cap (which calls _yf_info_fetch and caches all 4
# fields including dividend_yield_pct + payout_ratio).
# fetch_yfinance_dividend is a PURE CACHE-READ off that file — confirmed by
# asserting _yf_info_fetch is never called.
# ---------------------------------------------------------------------------


def test_CS_DIV1_warm_cache_returns_correct_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm cache with dividend_yield_pct=2.0 and payout_ratio=0.45 → (2.0, True, 0.45).

    pays_dividend must be True because dividend_yield_pct > 0.
    dividend_yield_pct is stored as a PERCENT (2.0 = 2%) — verify the cache
    value is read verbatim and not re-scaled.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "AAPL.json"
    cache_file.write_text(
        json.dumps(
            {"market_cap": 1e10, "dividend_yield_pct": 2.0, "payout_ratio": 0.45}
        ),
        encoding="utf-8",
    )

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_dividend("AAPL")

    assert result == (2.0, True, 0.45), (
        f"Expected (2.0, True, 0.45), got {result}"
    )
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_DIV2 — zero-yield non-payer
#
# dividend_yield_pct=0.0 is a confirmed non-payer (yfinance returned
# dividendYield=0.0 which the _yf_info_fetch converts to 0.0 * 100 = 0.0).
# pays_dividend must be False (not None — we have a confirmed reading).
# payout_ratio is None (no payout data when there is no dividend).
# ---------------------------------------------------------------------------


def test_CS_DIV2_zero_yield_returns_false_pays_dividend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache with dividend_yield_pct=0.0 → (0.0, False, None).

    The tri-state pays_dividend=False distinguishes "confirmed non-payer"
    from "data missing" (pays_dividend=None). This drives the frontend badge.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "AMZN.json"
    # No payout_ratio key — many growth stocks have NaN/None here.
    cache_file.write_text(
        json.dumps({"market_cap": 2e12, "dividend_yield_pct": 0.0}),
        encoding="utf-8",
    )

    yield_pct, pays, payout = fetch_yfinance_dividend("AMZN")

    assert yield_pct == 0.0, f"Expected yield_pct=0.0, got {yield_pct}"
    assert pays is False, (
        "pays_dividend must be False when dividend_yield_pct == 0.0 "
        f"(confirmed non-payer), got {pays}"
    )
    assert payout is None, (
        f"payout_ratio must be None when absent from cache, got {payout}"
    )


# ---------------------------------------------------------------------------
# CS_DIV3 — cold cache: no cache file → (None, None, None), no live fetch
#
# fetch_yfinance_dividend NEVER triggers a live yfinance fetch.
# Callers that need live data must call fetch_yfinance_market_cap first.
# ---------------------------------------------------------------------------


def test_CS_DIV3_cold_cache_returns_none_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cache file → (None, None, None), _yf_info_fetch never called.

    Confirms the PURE CACHE-READ contract: fetch_yfinance_dividend never
    triggers a live network round-trip even on a total cold-cache miss.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)
    # No cache file exists for this ticker.

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_dividend("TSLA")

    assert result == (None, None, None), (
        f"Cold cache must return (None, None, None), got {result}"
    )
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_DIV4 — QR_SKIP_CROSS_SOURCE=1 semantics
#
# Stale-tolerant read (same pattern as fetch_yfinance_market_cap /
# fetch_yfinance_shares_outstanding):
# (a) warm stale cache → return values (bypasses the 24h TTL check)
# (b) cold cache → (None, None, None) (no live fetch even under SKIP)
# ---------------------------------------------------------------------------


def test_CS_DIV4a_skip_env_warm_stale_cache_returns_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + stale-but-present cache → returns dividend values.

    The escape hatch bypasses the 24h TTL gate and reads the cached values
    directly — allows the pre-merge-prod-sim to use an old cache.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")

    cache_file = tmp_path / "MSFT.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3e12, "dividend_yield_pct": 0.8, "payout_ratio": 0.25}),
        encoding="utf-8",
    )

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_dividend("MSFT")

    assert result == (0.8, True, 0.25), (
        f"QR_SKIP_CROSS_SOURCE=1 + warm cache should return (0.8, True, 0.25), got {result}"
    )
    mock_fetch.assert_not_called()


def test_CS_DIV4b_skip_env_cold_cache_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + cold cache → (None, None, None), no live fetch.

    No cache file at all → the escape hatch must return (None, None, None)
    without attempting a live yfinance call. Mirrors the share_outstanding
    cold-cache escape behaviour for consistent semantics across the same
    yfinance_info cache.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    # No cache file.

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_dividend("NVDA")

    assert result == (None, None, None), (
        f"QR_SKIP_CROSS_SOURCE=1 + cold cache must return (None, None, None), got {result}"
    )
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_DIV5 — old-format cache (pre-0.10.27 backward-compat)
#
# Cache entries written before the dividend fields were added contain only
# market_cap (and possibly exchange / shares_outstanding). The
# dividend_yield_pct and payout_ratio keys are simply absent.
# _dividend_cache_read must return (None, None) → fetch_yfinance_dividend
# must return (None, None, None) without raising.
# ---------------------------------------------------------------------------


def test_CS_DIV5_old_format_cache_no_dividend_keys_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache file without dividend keys (pre-0.10.27) → (None, None, None).

    Backward-compat: _dividend_cache_read must return (None, None) and
    fetch_yfinance_dividend must return (None, None, None) when neither
    dividend_yield_pct nor payout_ratio are present in the cache JSON.

    This is the transition state during the first cron after the PR lands:
    old cache entries (written by the pre-0.10.27 _yf_info_fetch that only
    stored market_cap + shares_outstanding + exchange) don't have dividend
    fields yet, so dividend_coverage_pct will be 0% until the cache expires
    and is repopulated by the new _yf_info_fetch.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "GOOGL.json"
    # Only pre-0.10.27 fields.
    cache_file.write_text(
        json.dumps(
            {"market_cap": 2e12, "shares_outstanding": 12_500_000_000.0, "exchange": "NMS"}
        ),
        encoding="utf-8",
    )

    # Public function contract.
    result = fetch_yfinance_dividend("GOOGL")
    assert result == (None, None, None), (
        "Pre-0.10.27 cache (no dividend keys) must yield (None, None, None), "
        f"got {result}"
    )

    # Internal reader contract.
    cache_result = _dividend_cache_read("GOOGL")
    assert cache_result == (None, None), (
        f"_dividend_cache_read must return (None, None) for absent keys, got {cache_result}"
    )


# ---------------------------------------------------------------------------
# CS_DIV6 — _yf_info_fetch 4-tuple: dividend fields written to cache
#
# When fetch_yfinance_market_cap runs on a cold-cache ticker it calls
# _yf_info_fetch (the 4-tuple: market_cap, shares_outstanding,
# dividend_yield_pct, payout_ratio) and writes ALL fields in ONE
# _cache_write call. This test verifies that:
#   (a) market_cap is returned correctly from the live path
#   (b) the cache file contains both dividend_yield_pct and payout_ratio
#       alongside market_cap, so a subsequent fetch_yfinance_dividend call
#       can find them without a second network round-trip.
# ---------------------------------------------------------------------------


def test_CS_DIV6_live_path_writes_dividend_fields_to_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch_yfinance_market_cap live path writes dividend_yield_pct + payout_ratio.

    Scenario: cold cache, _yf_info_fetch returns a 4-tuple with dividend
    data.  After fetch_yfinance_market_cap returns, the cache file must
    contain both dividend fields so fetch_yfinance_dividend can be called
    next without triggering a second network call.

    dividend_yield_pct is stored as PERCENT (1.5) — _yf_info_fetch already
    multiplied yfinance's fractional dividendYield (0.015) × 100 = 1.5.
    _cache_write receives the already-converted value and stores it verbatim.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    # Simulate _yf_info_fetch returning (market_cap, shares_out, yield_pct_as_percent, payout_ratio).
    mocked_return = (3.5e12, 15_000_000_000.0, 1.5, 0.28)

    with patch(
        "compute.ingest.cross_source._yf_info_fetch", return_value=mocked_return
    ) as mock_fetch:
        mc = fetch_yfinance_market_cap("AAPL")

    assert mc == pytest.approx(3.5e12), f"market_cap must be propagated correctly, got {mc}"
    mock_fetch.assert_called_once_with("AAPL")

    cache_file = tmp_path / "AAPL.json"
    assert cache_file.exists(), "Cache file must be created after live fetch"

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload.get("market_cap") == pytest.approx(3.5e12)
    assert "dividend_yield_pct" in payload, (
        "dividend_yield_pct must be written to the cache alongside market_cap"
    )
    assert payload["dividend_yield_pct"] == pytest.approx(1.5), (
        f"Expected dividend_yield_pct=1.5 (PERCENT stored verbatim), got {payload.get('dividend_yield_pct')}"
    )
    assert "payout_ratio" in payload, (
        "payout_ratio must be written to the cache alongside market_cap"
    )
    assert payload["payout_ratio"] == pytest.approx(0.28), (
        f"Expected payout_ratio=0.28, got {payload.get('payout_ratio')}"
    )


def test_CS_DIV6_cache_write_none_dividend_key_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_cache_write(dividend_yield_pct=None, payout_ratio=None) must NOT write the keys.

    If yfinance returned no dividend data (non-dividend ticker with dividendYield=NaN),
    the cache must remain clean — absent keys not poisoned with None values
    that later reads would silently mishandle.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    _cache_write("GOOGL", market_cap=2e12, shares_outstanding=None,
                 dividend_yield_pct=None, payout_ratio=None)

    payload = json.loads((tmp_path / "GOOGL.json").read_text(encoding="utf-8"))
    assert "dividend_yield_pct" not in payload, (
        "_cache_write(dividend_yield_pct=None) must not write the key"
    )
    assert "payout_ratio" not in payload, (
        "_cache_write(payout_ratio=None) must not write the key"
    )
    assert payload.get("market_cap") == pytest.approx(2e12)
