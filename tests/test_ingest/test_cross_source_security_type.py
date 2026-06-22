"""Tests for fetch_yfinance_security_type + security-type cache semantics (Security-type PR-1).

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added to the
output schema", "when a new external-data source ships", and "when a bug is found" —
this file satisfies that policy for Security-type signal PR-1 (roadmap item #5 / 7b,
schema 0.10.30-phase8pilot, issue #541).

Tests
-----
CS_ST1 — warm-cache hit with quote_type=EQUITY → "Common stock" label returned
CS_ST2 — warm-cache hit with quote_type=ETF → "ETF" label returned
CS_ST3 — unknown code passes through verbatim (forward-safe)
CS_ST4 — cold cache → None, no live fetch
CS_ST5 — QR_SKIP_CROSS_SOURCE=1: warm stale cache → returns label; cold → None
CS_ST6 — old-format cache (no quote_type key, pre-0.10.30) → None (backward-compat)
CS_ST7 — security_type_label() mapping table: all known codes + unknown passthrough
CS_ST8 — _yf_fast_exchange returns (exchange_code, quote_type) 2-tuple; _exchange_cache_write
         stores both; subsequent _security_type_cache_read finds quote_type
CS_ST9 — fetch_yfinance_exchange live path writes quote_type to cache; subsequent
         fetch_yfinance_security_type is a pure cache-read (no second fast_info call)
CS_ST10 — graceful degradation: exception from fast_info → None; no raise into caller

Style mirrors tests/test_ingest/test_cross_source_dividend.py (the dividend PR-1 precedent).
No test is marked @network — all use synthetic tmp_path fixtures / monkeypatches.
No test uses @settings(deadline=None) — a slow test is itself a signal.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compute import config
from compute.ingest.cross_source import (
    _exchange_cache_write,
    _security_type_cache_read,
    _yf_fast_exchange,
    fetch_yfinance_exchange,
    fetch_yfinance_security_type,
    security_type_label,
)

# ---------------------------------------------------------------------------
# CS_ST1 — warm-cache hit with EQUITY → "Common stock"
# ---------------------------------------------------------------------------


def test_CS_ST1_warm_cache_equity_returns_common_stock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm cache with quote_type=EQUITY → security_type_label → "Common stock".

    fetch_yfinance_security_type is a PURE CACHE-READ — _yf_fast_exchange must
    never be called (confirmed via assertion).
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "AAPL.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3.5e12, "exchange": "NMS", "quote_type": "EQUITY"}),
        encoding="utf-8",
    )

    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fast:
        result = fetch_yfinance_security_type("AAPL")

    assert result == "Common stock", (
        f"EQUITY must map to 'Common stock', got {result!r}"
    )
    mock_fast.assert_not_called()


# ---------------------------------------------------------------------------
# CS_ST2 — warm-cache hit with ETF → "ETF"
# ---------------------------------------------------------------------------


def test_CS_ST2_warm_cache_etf_returns_etf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm cache with quote_type=ETF → "ETF".

    Verifies the ETF → "ETF" identity mapping (display label == raw code).
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "SPY.json"
    cache_file.write_text(
        json.dumps({"market_cap": 5e11, "exchange": "PCX", "quote_type": "ETF"}),
        encoding="utf-8",
    )

    result = fetch_yfinance_security_type("SPY")

    assert result == "ETF", f"ETF must map to 'ETF', got {result!r}"


# ---------------------------------------------------------------------------
# CS_ST3 — unknown code passes through verbatim (forward-safe)
# ---------------------------------------------------------------------------


def test_CS_ST3_unknown_code_passes_through_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unmapped quote_type code passes through as-is (forward-safe).

    If yfinance introduces a new instrument type (e.g. 'REIT', 'WARRANT'),
    it surfaces as the raw code rather than being silently dropped as None.
    This is the same philosophy as the exchange-code map passthrough.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "UNKNOWN.json"
    cache_file.write_text(
        json.dumps({"market_cap": 1e9, "quote_type": "WARRANT"}),
        encoding="utf-8",
    )

    result = fetch_yfinance_security_type("UNKNOWN")

    assert result == "WARRANT", (
        f"Unknown code 'WARRANT' must pass through verbatim, got {result!r}"
    )


# ---------------------------------------------------------------------------
# CS_ST4 — cold cache → None, no live fetch
# ---------------------------------------------------------------------------


def test_CS_ST4_cold_cache_returns_none_no_live_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cache file → None, _yf_fast_exchange never called.

    Confirms the PURE CACHE-READ contract: fetch_yfinance_security_type never
    triggers a live network round-trip even on a total cold-cache miss.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)
    # No cache file exists for this ticker.

    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fast:
        result = fetch_yfinance_security_type("TSLA")

    assert result is None, f"Cold cache must return None, got {result!r}"
    mock_fast.assert_not_called()


# ---------------------------------------------------------------------------
# CS_ST5 — QR_SKIP_CROSS_SOURCE=1 semantics
# ---------------------------------------------------------------------------


def test_CS_ST5a_skip_env_warm_stale_cache_returns_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + stale-but-present cache → returns the label.

    The escape hatch bypasses the 24h TTL gate and reads the cached value
    directly — allows the pre-merge-prod-sim to use an old cache.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")

    cache_file = tmp_path / "MSFT.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3e12, "exchange": "NMS", "quote_type": "EQUITY"}),
        encoding="utf-8",
    )

    result = fetch_yfinance_security_type("MSFT")

    assert result == "Common stock", (
        f"QR_SKIP_CROSS_SOURCE=1 + warm cache should return 'Common stock', got {result!r}"
    )


def test_CS_ST5b_skip_env_cold_cache_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + cold cache → None, no live fetch."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")
    # No cache file.

    result = fetch_yfinance_security_type("NVDA")

    assert result is None, (
        f"QR_SKIP_CROSS_SOURCE=1 + cold cache must return None, got {result!r}"
    )


# ---------------------------------------------------------------------------
# CS_ST6 — old-format cache (pre-0.10.30 backward-compat)
# ---------------------------------------------------------------------------


def test_CS_ST6_old_format_cache_no_quote_type_key_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache file without quote_type key (pre-0.10.30) → None.

    Backward-compat: pre-existing cache entries that were written before
    security-type PR-1 landed only have market_cap / exchange / shares /
    dividend fields.  The absence of 'quote_type' must yield None without
    raising — the transition state on the first cron after the PR lands.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "GOOGL.json"
    # Only pre-0.10.30 fields.
    cache_file.write_text(
        json.dumps(
            {
                "market_cap": 2e12,
                "shares_outstanding": 12_500_000_000.0,
                "exchange": "NMS",
                "dividend_yield_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )

    result = fetch_yfinance_security_type("GOOGL")
    assert result is None, (
        f"Pre-0.10.30 cache (no quote_type key) must yield None, got {result!r}"
    )

    # Internal reader contract.
    raw = _security_type_cache_read("GOOGL")
    assert raw is None, (
        f"_security_type_cache_read must return None for absent key, got {raw!r}"
    )


# ---------------------------------------------------------------------------
# CS_ST7 — security_type_label() mapping table
# ---------------------------------------------------------------------------


def test_CS_ST7_label_mapping_all_known_codes() -> None:
    """security_type_label() maps every known yfinance quote_type code correctly."""
    assert security_type_label("EQUITY") == "Common stock"
    assert security_type_label("ETF") == "ETF"
    assert security_type_label("MUTUALFUND") == "Fund"
    assert security_type_label("INDEX") == "Index"
    assert security_type_label("FUTURE") == "Future"
    assert security_type_label("CURRENCY") == "Currency"


def test_CS_ST7_label_mapping_unknown_passthrough() -> None:
    """Unknown codes pass through verbatim; None input returns None."""
    assert security_type_label("WARRANT") == "WARRANT"
    assert security_type_label("SOMECODE") == "SOMECODE"
    assert security_type_label(None) is None
    assert security_type_label("") is None


def test_CS_ST7_label_mapping_case_insensitive() -> None:
    """security_type_label is case-insensitive: 'equity' → 'Common stock'."""
    assert security_type_label("equity") == "Common stock"
    assert security_type_label("Equity") == "Common stock"
    assert security_type_label("etf") == "ETF"


# ---------------------------------------------------------------------------
# CS_ST8 — _yf_fast_exchange returns 2-tuple; _exchange_cache_write stores both
# ---------------------------------------------------------------------------


def _make_fast_info_mock(exchange: str | None, quote_type: str | None) -> MagicMock:
    """Return a MagicMock that mimics yf.Ticker(t).fast_info with .get() support."""
    fi = MagicMock()
    data = {}
    if exchange is not None:
        data["exchange"] = exchange
    if quote_type is not None:
        data["quoteType"] = quote_type
    fi.get = lambda key, default=None: data.get(key, default)
    # Also support getattr access (the fallback path in _yf_fast_exchange).
    fi.exchange = exchange
    fi.quoteType = quote_type
    return fi


def test_CS_ST8_yf_fast_exchange_returns_two_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_yf_fast_exchange returns (exchange_code, quote_type) 2-tuple.

    Verifies the return type change introduced in security-type PR-1 so the
    only caller (fetch_yfinance_exchange) can unpack both values in one shot.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    mock_ticker = MagicMock()
    mock_ticker.fast_info = _make_fast_info_mock("NMS", "EQUITY")

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = _yf_fast_exchange("AAPL")

    assert isinstance(result, tuple), (
        f"_yf_fast_exchange must return a 2-tuple, got {type(result)}"
    )
    assert len(result) == 2, f"Expected 2-tuple, got {len(result)}-tuple"
    exchange_code, quote_type = result
    assert exchange_code == "NMS", f"exchange_code must be 'NMS', got {exchange_code!r}"
    assert quote_type == "EQUITY", f"quote_type must be 'EQUITY', got {quote_type!r}"


def test_CS_ST8_exchange_cache_write_stores_quote_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_exchange_cache_write with quote_type writes both 'exchange' and 'quote_type' keys."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    _exchange_cache_write("AAPL", "NMS", quote_type="EQUITY")

    payload = json.loads((tmp_path / "AAPL.json").read_text(encoding="utf-8"))
    assert payload.get("exchange") == "NMS"
    assert payload.get("quote_type") == "EQUITY", (
        f"quote_type must be stored under 'quote_type' key, got {payload!r}"
    )


def test_CS_ST8_exchange_cache_write_no_quote_type_omits_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_exchange_cache_write(quote_type=None) must NOT write the 'quote_type' key."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    _exchange_cache_write("AMZN", "NMS", quote_type=None)

    payload = json.loads((tmp_path / "AMZN.json").read_text(encoding="utf-8"))
    assert "quote_type" not in payload, (
        "_exchange_cache_write(quote_type=None) must not write the key"
    )
    assert payload.get("exchange") == "NMS"


def test_CS_ST8_security_type_cache_read_finds_stored_quote_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After _exchange_cache_write stores quote_type, _security_type_cache_read finds it."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    _exchange_cache_write("MSFT", "NMS", quote_type="EQUITY")

    raw = _security_type_cache_read("MSFT")
    assert raw == "EQUITY", (
        f"_security_type_cache_read must return raw code 'EQUITY', got {raw!r}"
    )


# ---------------------------------------------------------------------------
# CS_ST9 — fetch_yfinance_exchange live path writes quote_type to cache;
#          subsequent fetch_yfinance_security_type is a pure cache-read
# ---------------------------------------------------------------------------


def test_CS_ST9_live_exchange_path_writes_quote_type_to_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch_yfinance_exchange live path stores both exchange + quote_type in one shot.

    After fetch_yfinance_exchange runs on a cold cache, calling
    fetch_yfinance_security_type must return the mapped label without
    triggering any additional network call.  This is the Step-8 loop
    production sequence.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    # _yf_fast_exchange returns a 2-tuple.
    mock_2tuple = ("NMS", "EQUITY")

    with patch(
        "compute.ingest.cross_source._yf_fast_exchange", return_value=mock_2tuple
    ) as mock_fast:
        exchange_code = fetch_yfinance_exchange("AAPL")

    assert exchange_code == "NMS", f"exchange_code must be 'NMS', got {exchange_code!r}"
    mock_fast.assert_called_once_with("AAPL")

    # Cache file must now contain both exchange and quote_type.
    cache_file = tmp_path / "AAPL.json"
    assert cache_file.exists(), "Cache file must be created after live fetch"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload.get("exchange") == "NMS"
    assert payload.get("quote_type") == "EQUITY", (
        f"quote_type must be written to cache alongside exchange, got {payload!r}"
    )

    # Now fetch_yfinance_security_type is a pure cache-read — no second live call.
    with patch("compute.ingest.cross_source._yf_fast_exchange") as mock_fast2:
        sec_type = fetch_yfinance_security_type("AAPL")

    assert sec_type == "Common stock", (
        f"Expected 'Common stock' from cached EQUITY, got {sec_type!r}"
    )
    mock_fast2.assert_not_called()


# ---------------------------------------------------------------------------
# CS_ST10 — graceful degradation: exception → None, no raise
# ---------------------------------------------------------------------------


def test_CS_ST10_corrupt_cache_file_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrupt JSON in the cache file → None, no exception raised.

    Confirms the graceful-degradation contract: a corrupt cache entry must not
    crash the Step-8 loop or the cron.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "BROKEN.json"
    cache_file.write_text("NOT VALID JSON {{{{", encoding="utf-8")

    result = fetch_yfinance_security_type("BROKEN")

    assert result is None, (
        f"Corrupt cache must return None without raising, got {result!r}"
    )


def test_CS_ST10_empty_quote_type_string_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache entry with quote_type='' (empty string) → None.

    An empty string is treated as absent (same pattern as exchange_code).
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "EMPTY.json"
    cache_file.write_text(
        json.dumps({"market_cap": 1e10, "quote_type": ""}),
        encoding="utf-8",
    )

    result = fetch_yfinance_security_type("EMPTY")
    assert result is None, (
        f"Empty quote_type string must return None, got {result!r}"
    )
