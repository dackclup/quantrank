"""Tests for the per-ticker deterministic TTL jitter (issue #469).

Covers:
- D1: _ttl_jitter_seconds is deterministic — same ticker yields same value.
- D2: jitter is bounded in [0, EDGAR_8K_CACHE_TTL_JITTER_SECONDS).
- D3: cohort spread — 50 S&P tickers populate >= 10 distinct hour-buckets.
- D4: effective-TTL behaviour — age slightly over base_TTL is FRESH for a
  high-jitter ticker but STALE for a zero-jitter ticker (monkeypatched).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from compute import config
from compute.scoring import eight_k_events
from compute.scoring.eight_k_events import _ttl_jitter_seconds

# ---------------------------------------------------------------------------
# Representative S&P 500 tickers for spread / cohort tests
# ---------------------------------------------------------------------------

_SP500_SAMPLE: tuple[str, ...] = (
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "BRK-B", "LLY",
    "JPM", "V", "XOM", "UNH", "TSLA", "MA", "JNJ", "PG", "HD", "AVGO", "CVX",
    "MRK", "ABBV", "COST", "WMT", "KO", "BAC", "PEP", "CSCO", "TMO", "MCD",
    "ACN", "CRM", "ABT", "WFC", "DIS", "TXN", "CMCSA", "NKE", "VZ", "BMY",
    "INTC", "ORCL", "RTX", "NEE", "QCOM", "HON", "PM", "AMGN", "CAT", "GE",
)
assert len(_SP500_SAMPLE) == 50


# ---------------------------------------------------------------------------
# D1 — Determinism: same ticker → same value, regardless of call count.
# ---------------------------------------------------------------------------

def test_D1_jitter_is_deterministic():
    """_ttl_jitter_seconds must return the identical value on repeated calls
    for the same ticker (no PYTHONHASHSEED dependency, no random state)."""
    for ticker in _SP500_SAMPLE[:10]:
        first = _ttl_jitter_seconds(ticker)
        for _ in range(4):
            assert _ttl_jitter_seconds(ticker) == first, (
                f"Non-deterministic result for {ticker!r}"
            )


# ---------------------------------------------------------------------------
# D2 — Bounds: result in [0, EDGAR_8K_CACHE_TTL_JITTER_SECONDS).
# ---------------------------------------------------------------------------

def test_D2_jitter_bounded_within_jitter_window():
    """Every jitter value must fall in [0, EDGAR_8K_CACHE_TTL_JITTER_SECONDS)."""
    jitter_window = config.EDGAR_8K_CACHE_TTL_JITTER_SECONDS
    assert jitter_window > 0, "Jitter window constant must be positive"
    for ticker in _SP500_SAMPLE:
        val = _ttl_jitter_seconds(ticker)
        assert 0 <= val < jitter_window, (
            f"Jitter {val} out of [{0}, {jitter_window}) for ticker {ticker!r}"
        )


# ---------------------------------------------------------------------------
# D3 — Non-degenerate spread: >= 10 distinct hour-buckets across 50 tickers.
# ---------------------------------------------------------------------------

def test_D3_cohort_populates_multiple_hour_buckets():
    """De-sync is only effective if jitter values are spread across the
    24-hour window.  We bucket by hour (integer division of seconds by 3600)
    and assert >= 10 distinct buckets are populated by 50 tickers."""
    hour_buckets: set[int] = set()
    for ticker in _SP500_SAMPLE:
        seconds = _ttl_jitter_seconds(ticker)
        hour_buckets.add(seconds // 3600)

    assert len(hour_buckets) >= 10, (
        f"Expected >= 10 distinct hour-buckets across {len(_SP500_SAMPLE)} tickers, "
        f"got {len(hour_buckets)}: {sorted(hour_buckets)}"
    )


# ---------------------------------------------------------------------------
# D4 — Effective-TTL behaviour with cache entries at base_TTL + 1s age.
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch):
    """Redirect EDGAR_8K_CACHE_DIR to a tmp dir for cache-layer tests."""
    cache_dir = tmp_path / "edgar_8k_jitter_test"
    monkeypatch.setattr(config, "EDGAR_8K_CACHE_DIR", cache_dir)
    return cache_dir


def _write_cache_entry(cache_dir: Path, ticker: str, age_seconds: int) -> None:
    """Write a synthetic cache entry whose fetched_at is `age_seconds` in the past."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
    payload = {
        "fetched_at": fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 730,
        "filings": [],
    }
    path = cache_dir / f"{ticker}.json"
    path.write_text(json.dumps(payload))


def test_D4_age_just_over_base_ttl_fresh_for_high_jitter_ticker(
    isolated_cache, monkeypatch
):
    """A cache entry at age = base_TTL + 1s is still FRESH for a ticker
    whose computed jitter is > 1s.

    We monkeypatch _ttl_jitter_seconds to return a controlled value so the
    test is deterministic regardless of the actual SHA-256 hash of any
    particular ticker string.
    """
    base_ttl = config.EDGAR_8K_CACHE_TTL_SECONDS
    entry_age = base_ttl + 1  # 1 second past the bare base TTL

    # Monkeypatch: this ticker gets jitter = 3600s (1 hour), so its effective
    # TTL = base_ttl + 3600.  entry_age = base_ttl + 1 < effective_ttl → FRESH.
    HIGH_JITTER = 3600
    monkeypatch.setattr(
        eight_k_events, "_ttl_jitter_seconds", lambda ticker: HIGH_JITTER
    )
    _write_cache_entry(isolated_cache, "HIGH_JITTER_TICKER", entry_age)
    result = eight_k_events._cache_read("HIGH_JITTER_TICKER", 730)
    assert result is not None, (
        "Cache entry should be FRESH when age < base_ttl + jitter "
        f"(age={entry_age}s, effective_ttl={base_ttl + HIGH_JITTER}s)"
    )


def test_D4b_age_just_over_base_ttl_stale_for_zero_jitter_ticker(
    isolated_cache, monkeypatch
):
    """A cache entry at age = base_TTL + 1s is STALE for a ticker whose
    jitter is 0 — the base TTL is the only budget.
    """
    base_ttl = config.EDGAR_8K_CACHE_TTL_SECONDS
    entry_age = base_ttl + 1  # 1 second past the bare base TTL

    # Monkeypatch: this ticker gets jitter = 0 → effective_ttl = base_ttl.
    monkeypatch.setattr(
        eight_k_events, "_ttl_jitter_seconds", lambda ticker: 0
    )
    _write_cache_entry(isolated_cache, "ZERO_JITTER_TICKER", entry_age)
    result = eight_k_events._cache_read("ZERO_JITTER_TICKER", 730)
    assert result is None, (
        "Cache entry should be STALE when age > base_ttl + 0 jitter "
        f"(age={entry_age}s, effective_ttl={base_ttl}s)"
    )


# ---------------------------------------------------------------------------
# D5 — Zero / negative jitter_window guard: returns 0, no ZeroDivisionError.
# ---------------------------------------------------------------------------

def test_D5_zero_jitter_window_returns_zero(monkeypatch):
    """If EDGAR_8K_CACHE_TTL_JITTER_SECONDS is ever set to 0, the helper
    must return 0 cleanly (no ZeroDivisionError from the modulo)."""
    monkeypatch.setattr(config, "EDGAR_8K_CACHE_TTL_JITTER_SECONDS", 0)
    assert _ttl_jitter_seconds("AAPL") == 0
