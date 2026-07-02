"""Tests for fetch_yfinance_dividend + dividend-field cache semantics (Dividend signal PR-1).

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added to the
output schema", "when a new defense ships", and "when a bug is found" — this file satisfies
that policy for the Dividend signal PR-1 (roadmap item #5 / 7a, schema 0.10.27-phase8pilot)
and the dividend-yield scaling bug (yfinance now returns dividendYield already in percent;
the pre-fix code multiplied by 100 again producing e.g. 267.0 for KO).

Tests
-----
CS_DIV1 — warm-cache hit with dividend data → correct 3-tuple returned
CS_DIV2 — zero-yield cache entry → (0.0, False, None) and pays_dividend=False
CS_DIV3 — cold cache → (None, None, None), no live fetch
CS_DIV4 — QR_SKIP_CROSS_SOURCE=1: stale cache → returns values; cold → (None, None, None)
CS_DIV5 — old-format cache (no dividend keys, pre-0.10.27) → (None, None, None) (backward-compat)
CS_DIV6 — _yf_info_fetch 4-tuple: dividend fields written to cache alongside market_cap
           (the live path in fetch_yfinance_market_cap writes all 4 fields in one shot)
CS_DIV7 — _yf_info_fetch bug-fix contract (dividend-yield scaling):
  CS_DIV7A — yfinance returns 2.67 (KO) → dividend_yield_pct == 2.67 (no ×100)
  CS_DIV7B — yfinance returns 0.0 → dividend_yield_pct == 0.0
  CS_DIV7C — yfinance returns None / absent → dividend_yield_pct is None
  CS_DIV7D — yfinance returns 267.0 (the pre-fix bug output) → guard discards it, None

Style mirrors tests/test_ingest/test_cross_source_shares.py (the most recent cross_source
test in this module) — synthetic tmp_path fixtures, monkeypatch for YFINANCE_INFO_CACHE_DIR,
no @settings(deadline=None), no @network markers.

No test uses @settings(deadline=None) — a slow example is itself a signal.
No test is marked @network — all use synthetic tmp_path fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compute import config
from compute.ingest.cross_source import (
    _cache_write,
    _dividend_cache_read,
    _yf_info_fetch,
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
# dividendYield=0.0; no ×100 conversion applied — 0.0 is stored verbatim).
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

    dividend_yield_pct is stored as PERCENT (1.5) — yfinance now returns
    dividendYield already in percent (e.g. 1.5 = 1.5%); no ×100 conversion
    is applied in _yf_info_fetch.  _cache_write stores the value verbatim.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.delenv("QR_SKIP_CROSS_SOURCE", raising=False)

    # Simulate _yf_info_fetch returning (market_cap, shares_out,
    # yield_pct_as_percent, payout_ratio, sector, industry) — 6-tuple since
    # Phase 9.4 PR-1 (sector-resolution coverage canary).
    mocked_return = (3.5e12, 15_000_000_000.0, 1.5, 0.28, "Technology", "Consumer Electronics")

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


# ---------------------------------------------------------------------------
# CS_DIV7 — _yf_info_fetch dividend-yield scaling bug-fix contract
#
# Bug: the pre-fix code multiplied yfinance's `dividendYield` by 100.
# yfinance now returns the value already in percent (e.g. 2.67 for KO),
# so the ×100 multiplication produced 267.0 — implausible and misleading.
#
# Fix: no ×100 applied; values > 100 are discarded with a warning.
#
# These tests exercise `_yf_info_fetch` directly by patching `yf.Ticker`
# so the real logic runs (no mock of _yf_info_fetch itself).
# A regression to ×100 would make CS_DIV7A fail (2.67 → 267.0 ≠ 2.67),
# and CS_DIV7D would fail if the >100 guard were removed (267.0 ≠ None).
# ---------------------------------------------------------------------------


def _make_ticker_mock(info_dict: dict) -> MagicMock:
    """Return a MagicMock that mimics yf.Ticker(ticker) with .info = info_dict."""
    mock_ticker = MagicMock()
    mock_ticker.info = info_dict
    return mock_ticker


def test_CS_DIV7A_normal_percent_value_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance returns dividendYield=2.67 (KO) → dividend_yield_pct == 2.67 (no ×100).

    This is the primary post-fix regression guard: if ×100 were re-introduced,
    the result would be 267.0 and this assertion would fail.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    ko_info = {
        "marketCap": 2.58e11,
        "sharesOutstanding": 4.3e9,
        "dividendYield": 2.67,
        "payoutRatio": 0.73,
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(ko_info)):
        _, _, dividend_yield_pct, payout_ratio, _, _ = _yf_info_fetch("KO")

    assert dividend_yield_pct == pytest.approx(2.67), (
        f"Expected dividend_yield_pct=2.67 (no ×100), got {dividend_yield_pct}"
    )
    assert payout_ratio == pytest.approx(0.73)


def test_CS_DIV7B_zero_yield_non_payer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance returns dividendYield=0.0 → dividend_yield_pct == 0.0 (confirmed non-payer)."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    amzn_info = {
        "marketCap": 2.1e12,
        "sharesOutstanding": 1.06e10,
        "dividendYield": 0.0,
        "payoutRatio": None,
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(amzn_info)):
        _, _, dividend_yield_pct, payout_ratio, _, _ = _yf_info_fetch("AMZN")

    assert dividend_yield_pct == 0.0, (
        f"Expected dividend_yield_pct=0.0 for non-payer, got {dividend_yield_pct}"
    )
    assert payout_ratio is None


def test_CS_DIV7C_missing_dividend_key_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance returns no dividendYield key → dividend_yield_pct is None."""
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    info_no_div = {
        "marketCap": 3.1e12,
        "sharesOutstanding": 2.5e10,
        # dividendYield intentionally absent
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(info_no_div)):
        _, _, dividend_yield_pct, payout_ratio, _, _ = _yf_info_fetch("GOOGL")

    assert dividend_yield_pct is None, (
        f"Absent dividendYield must yield None, got {dividend_yield_pct}"
    )
    assert payout_ratio is None


def test_CS_DIV7D_implausible_gt100_guard_discards_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance returns dividendYield=267.0 (the pre-fix bug value) → guard returns None.

    This locks in the >100 implausibility guard: if yfinance ever reverts to
    returning a fraction (0.0267) and _yf_info_fetch mistakenly re-applies ×100,
    the result (2.67) passes through. But if it returns 267.0 directly (the
    specific bug value), the guard must discard it as implausible.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    bugged_info = {
        "marketCap": 2.58e11,
        "sharesOutstanding": 4.3e9,
        "dividendYield": 267.0,  # the value the pre-fix code would produce
        "payoutRatio": 0.73,
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(bugged_info)):
        _, _, dividend_yield_pct, _, _, _ = _yf_info_fetch("KO")

    assert dividend_yield_pct is None, (
        f"dividendYield=267.0 is implausible (>100) and must be discarded, got {dividend_yield_pct}"
    )


# ---------------------------------------------------------------------------
# CS_DIV8 — >100 clamp on CACHE-READ paths (regression for PR #533 follow-up)
#
# PR #533 fixed the live-path ×100 double-scaling bug in _yf_info_fetch.
# The follow-up added the same >100 clamp to the two cache-READ paths so
# a stale cache file written by the old buggy code (e.g. KO 267.0) can
# never surface an inflated value on a warm-cache hit.
#
# CS_DIV8A — _dividend_cache_read (normal TTL-gated path):
#   stale file with 267.0 → dividend_yield_pct clamped to None;
#   valid value 2.67 passes through unmodified (boundary-correct guard).
#
# CS_DIV8B — QR_SKIP_CROSS_SOURCE=1 force-hit branch:
#   stale file with 267.0 → dividend_yield_pct=None, pays_dividend=None;
#   both fields independently exercised to confirm the SKIP branch uses
#   the same clamp logic as the normal path.
# ---------------------------------------------------------------------------


def test_CS_DIV8A_cache_read_clamps_gt100_and_passes_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_dividend_cache_read: stale-bug value 267.0 → None; normal value 2.67 passes through.

    Locks in the >100 clamp added to _dividend_cache_read (PR #533 follow-up).
    A stale cache file written by the pre-#533 ×100 code (e.g. KO 267.0)
    must never surface an inflated yield on a warm TTL-gated cache hit.
    payout_ratio is returned normally regardless — only the implausible yield
    is discarded, not the entire cache entry.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    # --- case 1: implausible stale value (the exact KO bug value) → clamped ---
    cache_file = tmp_path / "KO.json"
    cache_file.write_text(
        json.dumps({"market_cap": 2.58e11, "dividend_yield_pct": 267.0, "payout_ratio": 0.73}),
        encoding="utf-8",
    )
    dy_clamped, pr_kept = _dividend_cache_read("KO")
    assert dy_clamped is None, (
        f"dividend_yield_pct=267.0 must be clamped to None by _dividend_cache_read, got {dy_clamped}"
    )
    assert pr_kept == pytest.approx(0.73), (
        f"payout_ratio must still be returned after yield clamp, got {pr_kept}"
    )

    # --- case 2: normal yield 2.67 (the correct post-fix KO value) → passes through ---
    cache_file.write_text(
        json.dumps({"market_cap": 2.58e11, "dividend_yield_pct": 2.67, "payout_ratio": 0.73}),
        encoding="utf-8",
    )
    dy_normal, pr_normal = _dividend_cache_read("KO")
    assert dy_normal == pytest.approx(2.67), (
        f"Normal dividend_yield_pct=2.67 must pass through unclamped, got {dy_normal}"
    )
    assert pr_normal == pytest.approx(0.73)


def test_CS_DIV8B_skip_branch_clamps_gt100_and_passes_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 branch: stale-bug value 267.0 → (None, None, 0.73).

    Locks in the >100 clamp in the QR_SKIP_CROSS_SOURCE force-hit branch of
    fetch_yfinance_dividend (PR #533 follow-up).  When the escape hatch is
    active a stale cache file with an inflated yield must still be discarded,
    so pays_dividend derives correctly (None, not True) and the payout_ratio
    is still returned.  Also verifies the normal value 2.67 passes through.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")

    cache_file = tmp_path / "KO.json"

    # --- case 1: implausible stale value → clamped; pays_dividend must be None ---
    cache_file.write_text(
        json.dumps({"market_cap": 2.58e11, "dividend_yield_pct": 267.0, "payout_ratio": 0.73}),
        encoding="utf-8",
    )
    dy, pays, pr = fetch_yfinance_dividend("KO")
    assert dy is None, (
        f"QR_SKIP branch: dividend_yield_pct=267.0 must be clamped to None, got {dy}"
    )
    assert pays is None, (
        f"pays_dividend must be None when yield is clamped to None, got {pays}"
    )
    assert pr == pytest.approx(0.73), (
        f"payout_ratio must still be returned after yield clamp, got {pr}"
    )

    # --- case 2: normal yield 2.67 passes through; pays_dividend=True ---
    cache_file.write_text(
        json.dumps({"market_cap": 2.58e11, "dividend_yield_pct": 2.67, "payout_ratio": 0.73}),
        encoding="utf-8",
    )
    dy_n, pays_n, pr_n = fetch_yfinance_dividend("KO")
    assert dy_n == pytest.approx(2.67), (
        f"Normal dividend_yield_pct=2.67 must pass through unclamped in QR_SKIP branch, got {dy_n}"
    )
    assert pays_n is True, f"pays_dividend must be True for yield 2.67, got {pays_n}"
    assert pr_n == pytest.approx(0.73)


# ---------------------------------------------------------------------------
# CS_DIV9 — payout_ratio > 20 clamp (sp1500 data-quality fix)
#
# First sp1500 cron (commit 177485d16) surfaced tickers with implausible
# payout_ratio values: SLG=153.75 (15375%), indicating yfinance is returning
# a percent-format value instead of the documented 0-1 fraction for companies
# with negative/near-zero earnings.
#
# Guard: any payout_ratio > 20.0 is discarded to None (logs a warning).
# Ceiling 20.0 is conservative: a legitimate REIT at 150% payout = 1.5;
# only the percent-format >2000% garbage is cut. Same pattern as the
# dividend_yield_pct > 100 guard added in #533.
#
# CS_DIV9A — live path (_yf_info_fetch): payout_ratio=153.75 → None;
#             normal value 1.5 (e.g. REIT) passes through.
#
# CS_DIV9B — cache-read path (_dividend_cache_read): stale file with
#             153.75 → payout_ratio=None; normal 0.73 passes through
#             (boundary-correct guard); dividend_yield_pct unaffected.
#
# CS_DIV9C — QR_SKIP_CROSS_SOURCE=1 force-hit branch: implausible value
#             clamped; normal value and pays_dividend both correct.
# ---------------------------------------------------------------------------


def test_CS_DIV9A_live_path_clamps_implausible_payout_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_yf_info_fetch: payout_ratio=153.75 (SLG-style) → None; 1.5 (REIT) passes through.

    Locks in the >20 guard added to _yf_info_fetch for the payout_ratio field.
    A percent-format value like 153.75 (15375% payout) must be discarded;
    a legitimate high-payout REIT ratio of 1.5 (150%) must pass through.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    # --- case 1: implausible percent-format value (SLG: 153.75) → clamped ---
    slg_info = {
        "marketCap": 4e9,
        "sharesOutstanding": 1.75e8,
        "dividendYield": 10.5,  # 10.5% yield — plausible
        "payoutRatio": 153.75,  # percent-format bug: should be 1.5375
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(slg_info)):
        _, _, _, payout_ratio, _, _ = _yf_info_fetch("SLG")
    assert payout_ratio is None, (
        f"payout_ratio=153.75 is implausible (>20) and must be discarded, got {payout_ratio}"
    )

    # --- case 2: normal high REIT payout ratio 1.5 (150%) → passes through ---
    reit_info = {
        "marketCap": 8e9,
        "sharesOutstanding": 5e8,
        "dividendYield": 5.0,
        "payoutRatio": 1.5,  # 150% payout — high but real (REIT distributes >100% of GAAP income)
    }
    with patch("yfinance.Ticker", return_value=_make_ticker_mock(reit_info)):
        _, _, _, payout_ratio_reit, _, _ = _yf_info_fetch("O")
    assert payout_ratio_reit == pytest.approx(1.5), (
        f"payout_ratio=1.5 (150% REIT) must pass through unclamped, got {payout_ratio_reit}"
    )


def test_CS_DIV9B_cache_read_clamps_gt20_and_passes_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_dividend_cache_read: stale file 153.75 → None; normal 0.73 passes through.

    Locks in the >20 clamp added to _dividend_cache_read. A stale cache file
    written when yfinance returned a percent-format payout_ratio must never
    surface an implausible value on a warm TTL-gated cache hit.
    dividend_yield_pct is returned correctly regardless.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)

    cache_file = tmp_path / "SLG.json"

    # --- case 1: implausible stale value → clamped; yield unaffected ---
    cache_file.write_text(
        json.dumps({"market_cap": 4e9, "dividend_yield_pct": 10.5, "payout_ratio": 153.75}),
        encoding="utf-8",
    )
    dy_kept, pr_clamped = _dividend_cache_read("SLG")
    assert pr_clamped is None, (
        f"payout_ratio=153.75 must be clamped to None by _dividend_cache_read, got {pr_clamped}"
    )
    assert dy_kept == pytest.approx(10.5), (
        f"dividend_yield_pct must still be returned after payout clamp, got {dy_kept}"
    )

    # --- case 2: normal value 0.73 passes through ---
    cache_file.write_text(
        json.dumps({"market_cap": 4e9, "dividend_yield_pct": 2.67, "payout_ratio": 0.73}),
        encoding="utf-8",
    )
    dy_normal, pr_normal = _dividend_cache_read("SLG")
    assert pr_normal == pytest.approx(0.73), (
        f"Normal payout_ratio=0.73 must pass through unclamped, got {pr_normal}"
    )
    assert dy_normal == pytest.approx(2.67)


def test_CS_DIV9C_skip_branch_clamps_gt20_and_passes_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QR_SKIP_CROSS_SOURCE=1 branch: payout_ratio=153.75 → None; 0.73 passes through.

    Locks in the >20 clamp in the QR_SKIP_CROSS_SOURCE force-hit branch of
    fetch_yfinance_dividend. When the escape hatch is active a stale cache file
    with an implausible payout must still be clamped. dividend_yield_pct and
    pays_dividend must be unaffected by the payout clamp.
    """
    monkeypatch.setattr(config, "YFINANCE_INFO_CACHE_DIR", tmp_path)
    monkeypatch.setenv("QR_SKIP_CROSS_SOURCE", "1")

    cache_file = tmp_path / "SLG.json"

    # --- case 1: implausible stale payout → clamped; yield + pays_dividend correct ---
    cache_file.write_text(
        json.dumps({"market_cap": 4e9, "dividend_yield_pct": 10.5, "payout_ratio": 153.75}),
        encoding="utf-8",
    )
    dy, pays, pr = fetch_yfinance_dividend("SLG")
    assert pr is None, (
        f"QR_SKIP branch: payout_ratio=153.75 must be clamped to None, got {pr}"
    )
    assert dy == pytest.approx(10.5), (
        f"dividend_yield_pct must be unaffected by payout clamp, got {dy}"
    )
    assert pays is True, (
        f"pays_dividend must be True (yield 10.5 > 0) regardless of payout clamp, got {pays}"
    )

    # --- case 2: normal payout 0.73 passes through; pays_dividend=True ---
    cache_file.write_text(
        json.dumps({"market_cap": 4e9, "dividend_yield_pct": 2.67, "payout_ratio": 0.73}),
        encoding="utf-8",
    )
    dy_n, pays_n, pr_n = fetch_yfinance_dividend("SLG")
    assert pr_n == pytest.approx(0.73), (
        f"Normal payout_ratio=0.73 must pass through unclamped in QR_SKIP branch, got {pr_n}"
    )
    assert dy_n == pytest.approx(2.67)
    assert pays_n is True
