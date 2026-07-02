"""Tests for the sector-resolution coverage canary (Phase 9.4 PR-1).

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added to the
output schema", "when a new defense ships" (this is a Rule-18 observability surface,
same class as the dividend/security-type precedents), and "when a bug is found" — this
file satisfies that policy for Phase 9.4 PR-1 (sector-resolution coverage canary,
schema 0.10.45-phase9pilot).

Covers three new production surfaces in ``compute/ingest/cross_source.py``:

  - ``_yf_info_fetch``            — widened 4-tuple → 6-tuple, appending RAW
                                     ``sector`` / ``industry`` strings.
  - ``map_yfinance_sector_to_gics`` — maps the RAW yfinance sector vocabulary
                                     (11 categories) to the 11-key GICS
                                     vocabulary used by ``SECTOR_COST_OF_EQUITY``.
  - ``fetch_yfinance_sector``     — pure cache-read mirroring
                                     ``fetch_yfinance_dividend`` /
                                     ``fetch_yfinance_security_type``.

Tests
-----
CS_SEC1 — _yf_info_fetch returns a 6-tuple; sector/industry extracted correctly
CS_SEC2 — _yf_info_fetch: non-string / NaN sector or industry → None (guard,
          mirrors the dividend_yield_pct / payout_ratio format-reversion precedent)
CS_SEC3 — _yf_info_fetch: absent sector/industry keys → None
CS_SEC4 — map_yfinance_sector_to_gics: all 11 mappings (5 verbatim + 6 renamed)
CS_SEC5 — map_yfinance_sector_to_gics: unmapped/unknown string → None
CS_SEC6 — map_yfinance_sector_to_gics: None / empty string → None
CS_SEC7 — RATCHET: set(_YF_SECTOR_TO_GICS.values()) == set(SECTOR_COST_OF_EQUITY.keys())
CS_SEC8 — fetch_yfinance_sector: warm-cache hit returns the raw string
CS_SEC9 — fetch_yfinance_sector: cold-cache miss → None, no live fetch
CS_SEC10 — fetch_yfinance_sector: corrupt cache → graceful None
CS_SEC11 — fetch_yfinance_sector: QR_SKIP_CROSS_SOURCE=1 stale-tolerant path
           (warm stale cache → value; cold cache → None)
CS_SEC12 — fetch_yfinance_sector: old-format cache (no sector key) → None
           (backward-compat, pre-0.10.45 cache entries)
CS_SEC13 — live path (fetch_yfinance_market_cap) writes sector + industry to
           cache alongside market_cap, so a subsequent fetch_yfinance_sector
           call is a pure cache-read (no second network round-trip)

Style mirrors tests/test_ingest/test_cross_source_security_type.py (the most
recent cross_source signal-PR precedent) + tests/test_ingest/
test_cross_source_dividend.py CS_DIV7 (the _yf_info_fetch bug-fix contract
pattern). Synthetic tmp_path fixtures, monkeypatch for
YFINANCE_INFO_CACHE_DIR, no @settings(deadline=None), no @network markers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compute import config
from compute.ingest.cross_source import (
    _YF_SECTOR_TO_GICS,
    _cache_write,
    _sector_cache_read,
    _yf_info_fetch,
    fetch_yfinance_market_cap,
    fetch_yfinance_sector,
    map_yfinance_sector_to_gics,
)
from compute.scoring.cost_of_equity import SECTOR_COST_OF_EQUITY


def _make_ticker_mock(info_dict: dict) -> MagicMock:
    """Return a MagicMock that mimics yf.Ticker(ticker) with .info = info_dict."""
    mock_ticker = MagicMock()
    mock_ticker.info = info_dict
    return mock_ticker


# ---------------------------------------------------------------------------
# CS_SEC1 — _yf_info_fetch returns a 6-tuple; sector/industry extracted
# ---------------------------------------------------------------------------


def test_CS_SEC1_yf_info_fetch_returns_six_tuple_with_sector_industry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance .info with sector="Technology" / industry="Consumer Electronics"
    → the 6-tuple's 5th/6th elements carry those RAW values verbatim (no GICS
    mapping applied inside _yf_info_fetch — that's a separate step)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    aapl_info = {
        "marketCap": 3.5e12,
        "sharesOutstanding": 1.5e10,
        "dividendYield": 0.5,
        "payoutRatio": 0.15,
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(aapl_info)):
        result = _yf_info_fetch("AAPL")

    assert isinstance(result, tuple) and len(result) == 6, (
        f"_yf_info_fetch must return a 6-tuple, got {result!r}"
    )
    _, _, _, _, sector, industry = result
    assert sector == "Technology", f"Expected sector='Technology', got {sector!r}"
    assert industry == "Consumer Electronics", (
        f"Expected industry='Consumer Electronics', got {industry!r}"
    )


# ---------------------------------------------------------------------------
# CS_SEC2 — non-string / NaN sector or industry → None (format-reversion guard,
# same class as the dividend_yield_pct / payout_ratio precedents #533/#554)
# ---------------------------------------------------------------------------


def test_CS_SEC2_non_string_sector_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance returns sector as a float (NaN-style corruption) → None, not
    the raw float — mirrors the isinstance(str) guard pattern used for
    dividend_yield_pct / payout_ratio."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    bad_info = {
        "marketCap": 1e9,
        "sector": float("nan"),
        "industry": 12345,
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(bad_info)):
        _, _, _, _, sector, industry = _yf_info_fetch("BAD")

    assert sector is None, f"Non-string sector must yield None, got {sector!r}"
    assert industry is None, f"Non-string industry must yield None, got {industry!r}"


def test_CS_SEC2_empty_string_sector_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance returns sector="" (empty string) → None, treated as absent."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    empty_info = {"marketCap": 1e9, "sector": "", "industry": ""}
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(empty_info)):
        _, _, _, _, sector, industry = _yf_info_fetch("EMPTY")

    assert sector is None
    assert industry is None


# ---------------------------------------------------------------------------
# CS_SEC3 — absent sector/industry keys → None
# ---------------------------------------------------------------------------


def test_CS_SEC3_missing_sector_key_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance .info has no 'sector' / 'industry' keys at all → None, None."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    no_sector_info = {"marketCap": 2e9, "sharesOutstanding": 1e8}
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(no_sector_info)):
        _, _, _, _, sector, industry = _yf_info_fetch("NOSECTOR")

    assert sector is None
    assert industry is None


# ---------------------------------------------------------------------------
# CS_SEC4 — map_yfinance_sector_to_gics: all 11 mappings
# ---------------------------------------------------------------------------


def test_CS_SEC4_all_five_verbatim_mappings() -> None:
    """The 5 yfinance sector names that match GICS verbatim map to themselves."""
    assert map_yfinance_sector_to_gics("Communication Services") == "Communication Services"
    assert map_yfinance_sector_to_gics("Energy") == "Energy"
    assert map_yfinance_sector_to_gics("Industrials") == "Industrials"
    assert map_yfinance_sector_to_gics("Real Estate") == "Real Estate"
    assert map_yfinance_sector_to_gics("Utilities") == "Utilities"


def test_CS_SEC4_all_six_renamed_mappings() -> None:
    """The 6 yfinance sector names that are RENAMED under GICS map correctly."""
    assert map_yfinance_sector_to_gics("Basic Materials") == "Materials"
    assert map_yfinance_sector_to_gics("Consumer Cyclical") == "Consumer Discretionary"
    assert map_yfinance_sector_to_gics("Consumer Defensive") == "Consumer Staples"
    assert map_yfinance_sector_to_gics("Financial Services") == "Financials"
    assert map_yfinance_sector_to_gics("Healthcare") == "Health Care"
    assert map_yfinance_sector_to_gics("Technology") == "Information Technology"


# ---------------------------------------------------------------------------
# CS_SEC5 — unmapped/unknown string → None
# ---------------------------------------------------------------------------


def test_CS_SEC5_unmapped_string_returns_none() -> None:
    """An unrecognized sector string (not one of yfinance's 11 categories) →
    None — NOT a passthrough (unlike security_type_label / exchange_name,
    the sector map is a closed 11-category vocabulary; an unmapped value is
    the drift TELL this canary exists to surface)."""
    assert map_yfinance_sector_to_gics("Not A Real Sector") is None
    assert map_yfinance_sector_to_gics("Information Technology") is None, (
        "The already-GICS-named string is NOT a yfinance raw key — must not "
        "accidentally pass through as an identity mapping"
    )


# ---------------------------------------------------------------------------
# CS_SEC6 — None / empty string → None
# ---------------------------------------------------------------------------


def test_CS_SEC6_none_input_returns_none() -> None:
    assert map_yfinance_sector_to_gics(None) is None


def test_CS_SEC6_empty_string_input_returns_none() -> None:
    assert map_yfinance_sector_to_gics("") is None


# ---------------------------------------------------------------------------
# CS_SEC7 — RATCHET: the 11-key GICS target vocabulary must exactly match
# SECTOR_COST_OF_EQUITY's keys (error→regression ratchet, CLAUDE.md §Gotchas
# 2026-06-26). If either side is edited without the other, this test fails —
# converting a probabilistic (LLM review) catch into a deterministic one.
# ---------------------------------------------------------------------------


def test_CS_SEC7_gics_target_vocabulary_matches_sector_cost_of_equity_keys() -> None:
    """set(_YF_SECTOR_TO_GICS.values()) must exactly equal
    set(SECTOR_COST_OF_EQUITY.keys()) — pins the taxonomy so the two
    vocabularies can never silently drift apart."""
    mapped_targets = set(_YF_SECTOR_TO_GICS.values())
    coe_keys = set(SECTOR_COST_OF_EQUITY.keys())
    assert mapped_targets == coe_keys, (
        f"GICS mapping targets {mapped_targets} must exactly match "
        f"SECTOR_COST_OF_EQUITY keys {coe_keys} — symmetric difference: "
        f"{mapped_targets.symmetric_difference(coe_keys)}"
    )
    assert len(mapped_targets) == 11, (
        f"Expected exactly 11 GICS sectors, got {len(mapped_targets)}"
    )


# ---------------------------------------------------------------------------
# CS_SEC8 — fetch_yfinance_sector: warm-cache hit
# ---------------------------------------------------------------------------


def test_CS_SEC8_warm_cache_returns_raw_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm cache with sector="Technology" → fetch_yfinance_sector returns the
    RAW string verbatim (NOT GICS-mapped — callers map separately)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "AAPL.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3.5e12, "sector": "Technology", "industry": "Consumer Electronics"}),
        encoding="utf-8",
    )

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_sector("AAPL")

    assert result == "Technology", f"Expected raw 'Technology', got {result!r}"
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_SEC9 — cold-cache miss → None, no live fetch
# ---------------------------------------------------------------------------


def test_CS_SEC9_cold_cache_returns_none_no_live_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No cache file → None. Confirms the PURE CACHE-READ contract:
    fetch_yfinance_sector never triggers a live network round-trip."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch:
        result = fetch_yfinance_sector("TSLA")

    assert result is None
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# CS_SEC10 — corrupt cache → graceful None
# ---------------------------------------------------------------------------


def test_CS_SEC10_corrupt_cache_file_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrupt JSON in the cache file → None, no exception raised — a bad
    cache entry must not crash the Step-8 loop or the cron."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "BROKEN.json"
    cache_file.write_text("NOT VALID JSON {{{{", encoding="utf-8")

    result = fetch_yfinance_sector("BROKEN")

    assert result is None, f"Corrupt cache must return None without raising, got {result!r}"


# ---------------------------------------------------------------------------
# CS_SEC11 — QR_SKIP_CROSS_SOURCE=1 stale-tolerant path
# ---------------------------------------------------------------------------


def test_CS_SEC11a_skip_env_warm_stale_cache_returns_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + stale-but-present cache → returns the raw
    sector string (bypasses the TTL gate, mirrors the dividend/security-type
    sibling readers)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")

    cache_file = tmp_path / "MSFT.json"
    cache_file.write_text(
        json.dumps({"market_cap": 3e12, "sector": "Technology"}),
        encoding="utf-8",
    )

    result = fetch_yfinance_sector("MSFT")

    assert result == "Technology", (
        f"QR_SKIP_CROSS_SOURCE=1 + warm cache should return 'Technology', got {result!r}"
    )


def test_CS_SEC11b_skip_env_cold_cache_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 + cold cache → None, no live fetch."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")

    result = fetch_yfinance_sector("NVDA")

    assert result is None, (
        f"QR_SKIP_CROSS_SOURCE=1 + cold cache must return None, got {result!r}"
    )


# ---------------------------------------------------------------------------
# CS_SEC12 — old-format cache (pre-0.10.45 backward-compat)
# ---------------------------------------------------------------------------


def test_CS_SEC12_old_format_cache_no_sector_key_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache file without the 'sector' key (pre-0.10.45) → None.

    Backward-compat: cache entries written before Phase 9.4 PR-1 landed only
    have market_cap / exchange / dividend / quote_type fields. Absence of
    'sector' must yield None without raising."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    cache_file = tmp_path / "GOOGL.json"
    cache_file.write_text(
        json.dumps(
            {
                "market_cap": 2e12,
                "shares_outstanding": 1.25e10,
                "exchange": "NMS",
                "dividend_yield_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )

    result = fetch_yfinance_sector("GOOGL")
    assert result is None, (
        f"Pre-0.10.45 cache (no sector key) must yield None, got {result!r}"
    )

    # Internal reader contract.
    sector, industry = _sector_cache_read("GOOGL")
    assert sector is None
    assert industry is None


# ---------------------------------------------------------------------------
# CS_SEC13 — live path writes sector + industry to cache alongside market_cap
# ---------------------------------------------------------------------------


def test_CS_SEC13_live_path_writes_sector_fields_to_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fetch_yfinance_market_cap's cold-cache live path (which calls
    _yf_info_fetch, now a 6-tuple) writes sector + industry to the cache
    alongside market_cap, so a subsequent fetch_yfinance_sector call is a
    pure cache-read with zero additional network round-trips."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    mocked_return = (3.5e12, 1.5e10, 0.5, 0.15, "Technology", "Consumer Electronics")

    with patch(
        "compute.ingest.cross_source._yf_info_fetch", return_value=mocked_return
    ) as mock_fetch:
        mc = fetch_yfinance_market_cap("AAPL")

    assert mc == pytest.approx(3.5e12)
    mock_fetch.assert_called_once_with("AAPL")

    cache_file = tmp_path / "AAPL.json"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload.get("sector") == "Technology", (
        f"sector must be written to cache alongside market_cap, got {payload!r}"
    )
    assert payload.get("industry") == "Consumer Electronics"

    # Now fetch_yfinance_sector is a pure cache-read — no second live call.
    with patch("compute.ingest.cross_source._yf_info_fetch") as mock_fetch2:
        sector = fetch_yfinance_sector("AAPL")

    assert sector == "Technology"
    mock_fetch2.assert_not_called()


def test_CS_SEC13_cache_write_none_sector_key_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_cache_write(sector=None, industry=None) must NOT write those keys —
    keeps the cache clean when yfinance returns no sector data."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    _cache_write("GOOGL", market_cap=2e12, sector=None, industry=None)

    payload = json.loads((tmp_path / "GOOGL.json").read_text(encoding="utf-8"))
    assert "sector" not in payload, "_cache_write(sector=None) must not write the key"
    assert "industry" not in payload, "_cache_write(industry=None) must not write the key"
