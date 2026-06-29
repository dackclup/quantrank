"""Tests for Phase 9.1 — ``compute/ingest/broad_universe.py``.

Coverage (all offline — no network, no disk-cache writes):

BU1  fetch_broad_universe_candidates with a mocked SEC company_tickers.json
     payload returns a DataFrame with the expected columns (ticker / name /
     exchange) and the correct rows after name/format exclusions.

BU2  P1-G1 look-ahead guard (methodology-REQUIRED):
     screen_broad_universe_investability EXCLUDES a ticker that fails the
     trailing-30d ADV floor even when its full-history average volume is HIGH.
     This proves the screen reads the TRAILING window, not full-sample average.

BU3  QR_SKIP_BROAD_UNIVERSE=1 returns an all-None result dict without error
     (the _run_broad_universe_probe escape hatch in main.py; tested here at
     the broad_universe module level via the env-var the probe reads).

BU4  An empty candidate pool (zero rows) returns the all-None dict without
     error (graceful degradation through screen_broad_universe_investability).

BU5  Name exclusions in _candidates_from_live_json: ETF/FUND name keywords
     and non-equity ticker suffixes (-P, -W, -UN, -R) are dropped; plain
     equity tickers survive.

BU6  _candidates_from_bundled applies the exchange filter (only Nasdaq/NYSE/
     CBOE pass through) in addition to the name/format exclusions.

BU7  screen_broad_universe_investability correctly counts price-fail vs
     adv-fail vs pass, and the pass-rate arithmetic is self-consistent.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from compute import config

# ---------------------------------------------------------------------------
# Private imports under test
# ---------------------------------------------------------------------------
from compute.ingest.broad_universe import (
    _candidates_from_bundled,
    _candidates_from_live_json,
    screen_broad_universe_investability,
)

# ---------------------------------------------------------------------------
# Helpers — synthetic price DataFrames
# ---------------------------------------------------------------------------

_ADV_LOOKBACK = config.ADV_LOOKBACK_DAYS   # 30 (trading days)
_ADV_FLOOR    = config.ADV_FLOOR_USD        # $5_000_000.0
_PRICE_FLOOR  = config.BROAD_UNIVERSE_PRICE_FLOOR_USD  # $5.0


def _price_df(
    n_rows: int = 40,
    close: float = 50.0,
    volume: float = 200_000.0,
) -> pd.DataFrame:
    """Minimal OHLCV DataFrame — enough for ``compute_average_dollar_volume``."""
    idx = pd.bdate_range("2025-01-02", periods=n_rows)
    return pd.DataFrame(
        {
            "Open":   [close] * n_rows,
            "High":   [close + 1.0] * n_rows,
            "Low":    [close - 1.0] * n_rows,
            "Close":  [close] * n_rows,
            "Volume": [volume] * n_rows,
        },
        index=idx,
    )


def _high_adv_close_but_low_trailing_adv(
    lookback: int = _ADV_LOOKBACK,
    n_history: int = 200,
    history_close: float = 100.0,
    history_volume: float = 1_000_000.0,  # $100M/day historically
    trailing_close: float = 100.0,
    trailing_volume: float = 40_000.0,     # $4M/day trailing → below $5M floor
) -> pd.DataFrame:
    """Build a DataFrame where full-history ADV is HIGH but trailing-30d ADV is LOW.

    Historical rows have volume=1_000_000 (ADV ≈ $100M/day).
    The final ``lookback`` rows have volume=40_000 (ADV ≈ $4M/day).
    This is the look-ahead guard scenario: a naive full-sample average would
    pass the screen; a correct trailing-window average must FAIL it.
    """
    n_history_rows = n_history - lookback
    idx = pd.bdate_range("2024-01-02", periods=n_history)
    closes  = [history_close]  * n_history_rows + [trailing_close]  * lookback
    volumes = [history_volume] * n_history_rows + [trailing_volume] * lookback
    return pd.DataFrame(
        {
            "Open":   closes,
            "High":   [c + 1.0 for c in closes],
            "Low":    [c - 1.0 for c in closes],
            "Close":  closes,
            "Volume": volumes,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# BU1 — fetch_broad_universe_candidates mocked via live JSON path
# ---------------------------------------------------------------------------

_MOCK_SEC_JSON_PAYLOAD: dict = {
    "0": {"ticker": "AAPL", "title": "Apple Inc.", "cik_str": "320193"},
    "1": {"ticker": "MSFT", "title": "Microsoft Corp.", "cik_str": "789019"},
    "2": {"ticker": "BAD-PA", "title": "Preferred Line", "cik_str": "999001"},
    "3": {"ticker": "ETFCO", "title": "ETFCO Fund", "cik_str": "999002"},
    "4": {"ticker": "SPACQ", "title": "SPACQ Acquisition Corp", "cik_str": "999003"},
}


def test_BU1_fetcher_with_mocked_sec_json_returns_expected_columns(monkeypatch, tmp_path):
    """fetch_broad_universe_candidates backed by a mocked SEC JSON payload returns
    a DataFrame with columns ticker / name / exchange and the correct equity rows.

    Patched paths:
    - ``_load_bundled_company_tickers`` → returns None (forces live-JSON path)
    - ``_fetch_sec_company_tickers_json``  → returns the synthetic payload above
    - ``config.BROAD_UNIVERSE_CACHE``      → points to a temp path (no cache hit)
    """
    from compute.ingest import broad_universe as bu_mod

    # Redirect the on-disk cache to a path that doesn't exist yet (no cache hit).
    cache_path = tmp_path / "broad_universe-test.parquet"
    monkeypatch.setattr(config, "BROAD_UNIVERSE_CACHE", cache_path)

    with (
        patch.object(bu_mod, "_load_bundled_company_tickers", return_value=None),
        patch.object(bu_mod, "_fetch_sec_company_tickers_json",
                     return_value=_MOCK_SEC_JSON_PAYLOAD),
    ):
        df = bu_mod.fetch_broad_universe_candidates(force_refresh=True)

    # Required columns
    assert "ticker" in df.columns, "DataFrame must have 'ticker' column"
    assert "name" in df.columns,   "DataFrame must have 'name' column"
    assert "exchange" in df.columns, "DataFrame must have 'exchange' column"

    # Equity tickers should survive
    tickers = set(df["ticker"].tolist())
    assert "AAPL" in tickers, "AAPL (plain equity) must survive exclusions"
    assert "MSFT" in tickers, "MSFT (plain equity) must survive exclusions"

    # Excluded tickers must NOT appear
    assert "BAD-PA" not in tickers, "Preferred-share suffix -PA must be excluded"
    assert "ETFCO" not in tickers,  "ETF/FUND name keyword must be excluded"
    assert "SPACQ" not in tickers,  "SPAC/Acquisition name keyword must be excluded"

    # Live-JSON path tags exchange as 'unknown'
    assert (df["exchange"] == "unknown").all(), (
        "Live-JSON path must tag exchange='unknown' (no exchange column in SEC JSON)"
    )


# ---------------------------------------------------------------------------
# BU2 — P1-G1 look-ahead guard (methodology-REQUIRED)
# ---------------------------------------------------------------------------

def test_BU2_screen_excludes_ticker_with_low_trailing_adv_despite_high_history():
    """P1-G1 look-ahead guard: the screen reads the TRAILING window, not full-sample.

    Scenario:
      - Ticker "TRAP" has 200 days of price history.
      - The first 170 days have volume = 1,000,000 (ADV ≈ $100M/day historically).
      - The final 30 days (the trailing window) have volume = 40,000
        (ADV ≈ $4M/day, BELOW the $5M floor).
      - Last close = $100 (above $5 price floor).

    Full-sample average ADV would be huge; trailing-30d ADV is ~$4M → MUST FAIL.
    A buggy implementation that reads full-sample volume would pass the ticker.
    This test is the deterministic guard against that bug.
    """
    candidates = pd.DataFrame({
        "ticker":   ["TRAP"],
        "name":     ["Trap Corp"],
        "exchange": ["Nasdaq"],
    })

    prices_by_ticker = {
        "TRAP": _high_adv_close_but_low_trailing_adv(
            lookback=_ADV_LOOKBACK,
            n_history=200,
            history_volume=1_000_000.0,   # historically $100M/day
            trailing_volume=40_000.0,      # trailing $4M/day → BELOW $5M floor
        ),
    }

    result = screen_broad_universe_investability(
        candidates=candidates,
        prices_by_ticker=prices_by_ticker,
    )

    # The ticker must NOT pass — trailing ADV is $4M < $5M floor.
    assert result["broad_universe_screened_count"] == 0, (
        "P1-G1 look-ahead guard: TRAP must be EXCLUDED because its trailing-30d "
        "ADV ($4M) is below the $5M floor, even though its historical ADV is huge."
    )
    # ADV fail pct must be 100% (1 ticker, 1 fails ADV)
    assert result["broad_universe_adv_fail_pct"] == 100.0, (
        "With exactly 1 ticker and 1 ADV failure the adv_fail_pct must be 100.0"
    )

    # Sanity: the price did NOT fail (close=$100 >= $5 floor)
    assert result["broad_universe_price_fail_pct"] == 0.0, (
        "Last close $100 clears the $5 price floor; price_fail_pct must be 0.0"
    )


# ---------------------------------------------------------------------------
# BU3 — QR_SKIP_BROAD_UNIVERSE=1 escape hatch
# ---------------------------------------------------------------------------

def test_BU3_skip_env_var_returns_all_none(monkeypatch):
    """When QR_SKIP_BROAD_UNIVERSE=1 the probe returns the all-None dict.

    Tests that _run_broad_universe_probe in main.py respects the escape
    hatch by exercising it at the module boundary: we call
    screen_broad_universe_investability with the env-var set via the probe
    function that actually gates on the env-var.
    """
    from compute.main import _run_broad_universe_probe

    monkeypatch.setenv(config.BROAD_UNIVERSE_SKIP_ENV_VAR, "1")

    result = _run_broad_universe_probe(prices_by_ticker={})

    _ALL_NONE_KEYS = {
        "broad_universe_raw_count",
        "broad_universe_candidate_count",
        "broad_universe_screened_count",
        "broad_universe_price_fail_pct",
        "broad_universe_adv_fail_pct",
        "broad_universe_coverage_pct",
    }
    assert set(result.keys()) == _ALL_NONE_KEYS, (
        f"Unexpected keys in result: {set(result.keys()) - _ALL_NONE_KEYS}"
    )
    for key, val in result.items():
        assert val is None, (
            f"QR_SKIP_BROAD_UNIVERSE=1: expected result[{key!r}] = None, got {val!r}"
        )


# ---------------------------------------------------------------------------
# BU4 — empty candidate pool
# ---------------------------------------------------------------------------

def test_BU4_empty_candidate_pool_returns_all_none():
    """An empty candidate pool (zero rows) returns the all-None dict without error.

    screen_broad_universe_investability must gracefully degrade to all-None
    counts/rates when passed an empty DataFrame — no ZeroDivisionError,
    no IndexError, no crash.
    """
    empty_candidates = pd.DataFrame(columns=["ticker", "name", "exchange"])

    result = screen_broad_universe_investability(
        candidates=empty_candidates,
        prices_by_ticker={},
    )

    assert result["broad_universe_raw_count"] == 0
    assert result["broad_universe_candidate_count"] == 0
    assert result["broad_universe_screened_count"] is None, (
        "screened_count must be None (not 0) when candidate pool is empty"
    )
    assert result["broad_universe_price_fail_pct"] is None
    assert result["broad_universe_adv_fail_pct"] is None
    assert result["broad_universe_coverage_pct"] is None


# ---------------------------------------------------------------------------
# BU5 — _candidates_from_live_json name/format exclusions
# ---------------------------------------------------------------------------

_LIVE_JSON_PAYLOAD: dict = {
    "0": {"ticker": "CLEAN",   "title": "Clean Corp",           "cik_str": "100001"},
    # Preferred-share suffix: -P (bare) — pattern: -P[A-Z]?$
    "1": {"ticker": "XYZ-P",   "title": "Xyz Preferred",        "cik_str": "100002"},  # excluded (-P)
    "2": {"ticker": "XYZ-PA",  "title": "Xyz Preferred A",      "cik_str": "100003"},  # excluded (-PA)
    # ETF name keyword
    "3": {"ticker": "SPYCO",   "title": "S&P 500 ETF Trust",    "cik_str": "100004"},  # excluded (ETF)
    # FUND name keyword
    "4": {"ticker": "FDCO",    "title": "Growth Fund A",        "cik_str": "100005"},  # excluded (FUND)
    # SPAC / Acquisition name keyword
    "5": {"ticker": "BLKQ",    "title": "BLK Acquisition Corp", "cik_str": "100006"},  # excluded (ACQUISITION)
    # Warrant suffix -W (pattern: -W[A-Z]?$)
    "6": {"ticker": "MRG-W",   "title": "Merger Warrant",       "cik_str": "100007"},  # excluded (-W)
    # Unit suffix -U (pattern: -U$)
    "7": {"ticker": "UNIT-U",  "title": "Unit Trust",           "cik_str": "100008"},  # excluded (-U)
    # Another clean equity
    "8": {"ticker": "GOOD",    "title": "Good Corp",            "cik_str": "100009"},
}


def test_BU5_live_json_name_and_format_exclusions():
    """_candidates_from_live_json applies ETF/FUND/SPAC name exclusions and
    non-equity ticker-suffix exclusions, passing through plain equity tickers.

    The non-equity suffix patterns (from ``_NONEQUITY_TICKER_PAT``) all require
    a leading hyphen: ``-P[A-Z]?$``, ``-W[A-Z]?$``, ``-U$``, ``-UN$`` etc.
    Test tickers are constructed to match those exact patterns.
    """
    df = _candidates_from_live_json(_LIVE_JSON_PAYLOAD)

    tickers = set(df["ticker"].tolist())

    # Equities that must survive
    assert "CLEAN" in tickers, "Plain equity CLEAN must survive"
    assert "GOOD"  in tickers, "Plain equity GOOD must survive"

    # Non-equities that must be excluded
    assert "XYZ-P"   not in tickers, "-P preferred suffix must be excluded"
    assert "XYZ-PA"  not in tickers, "-PA preferred suffix must be excluded"
    assert "SPYCO"   not in tickers, "ETF name keyword must be excluded"
    assert "FDCO"    not in tickers, "FUND name keyword must be excluded"
    assert "BLKQ"    not in tickers, "ACQUISITION name keyword must be excluded"
    assert "MRG-W"   not in tickers, "-W warrant suffix must be excluded"
    assert "UNIT-U"  not in tickers, "-U unit suffix must be excluded"

    # Required columns
    assert "ticker"  in df.columns
    assert "name"    in df.columns
    assert "cik_str" in df.columns


# ---------------------------------------------------------------------------
# BU6 — _candidates_from_bundled exchange filter
# ---------------------------------------------------------------------------

def _bundled_df() -> pd.DataFrame:
    """Synthetic bundled parquet DataFrame with ticker/title/exchange columns."""
    return pd.DataFrame({
        "ticker":   ["AAPL",    "MSFT",   "OTC1",   "PINK1",    "CBOE1",  "SPAC-PA"],
        "title":    ["Apple",   "Microsoft", "OTC Corp", "Pink Corp", "CboeCoX", "Spac Pref"],
        "exchange": ["Nasdaq",  "NYSE",   "OTC",    "Pink",     "CBOE",   "Nasdaq"],
    })


def test_BU6_bundled_exchange_filter_allows_only_eligible_exchanges():
    """_candidates_from_bundled passes only tickers on Nasdaq/NYSE/CBOE."""
    df = _candidates_from_bundled(_bundled_df())

    tickers = set(df["ticker"].tolist())

    assert "AAPL"  in tickers, "Nasdaq ticker AAPL must pass"
    assert "MSFT"  in tickers, "NYSE ticker MSFT must pass"
    assert "CBOE1" in tickers, "CBOE ticker CBOE1 must pass"

    assert "OTC1"  not in tickers, "OTC exchange must be excluded"
    assert "PINK1" not in tickers, "Pink exchange must be excluded"

    # SPAC-PA: Nasdaq exchange BUT has -PA suffix → excluded via ticker format
    assert "SPAC-PA" not in tickers, "-PA non-equity suffix must be excluded"

    assert "ticker"   in df.columns
    assert "name"     in df.columns
    assert "exchange" in df.columns


# ---------------------------------------------------------------------------
# BU7 — screen arithmetic self-consistency
# ---------------------------------------------------------------------------

def test_BU7_screen_arithmetic_is_self_consistent():
    """screen_broad_universe_investability result fields are internally consistent.

    Scenario: 5 candidates, all with price data.
      - PASS1, PASS2: close=$100, volume=100_000 → ADV=$10M (pass both floors)
      - PFAIL:        close=$2,   volume=100_000 → fails price floor ($2 < $5)
      - AFAIL:        close=$100, volume=20_000  → fails ADV floor ($2M < $5M)
      - PASS3:        close=$50,  volume=120_000 → ADV=$6M (pass both)
    """
    candidates = pd.DataFrame({
        "ticker":   ["PASS1", "PASS2", "PFAIL", "AFAIL", "PASS3"],
        "name":     ["Pass1 Corp", "Pass2 Corp", "Pfail Corp", "Afail Corp", "Pass3 Corp"],
        "exchange": ["Nasdaq"] * 5,
    })

    prices_by_ticker = {
        "PASS1": _price_df(close=100.0, volume=100_000.0),
        "PASS2": _price_df(close=100.0, volume=100_000.0),
        "PFAIL": _price_df(close=2.0,   volume=100_000.0),   # price below $5
        "AFAIL": _price_df(close=100.0, volume=20_000.0),    # ADV $2M < $5M
        "PASS3": _price_df(close=50.0,  volume=120_000.0),   # ADV $6M — passes
    }

    result = screen_broad_universe_investability(
        candidates=candidates,
        prices_by_ticker=prices_by_ticker,
    )

    assert result["broad_universe_raw_count"] == 5
    assert result["broad_universe_candidate_count"] == 5
    assert result["broad_universe_coverage_pct"] == 100.0, (
        "All 5 candidates have price data → coverage_pct must be 100.0"
    )

    # 1 price-fail out of 5 with prices = 20.0%
    assert result["broad_universe_price_fail_pct"] is not None
    assert abs(result["broad_universe_price_fail_pct"] - 20.0) < 0.01, (
        f"Expected price_fail_pct=20.0, got {result['broad_universe_price_fail_pct']}"
    )

    # adv_fail_pct denominator is n_with_prices (all 5 have prices = n_screened=5).
    # 1 adv-fail out of 5 with prices = 20.0%.
    # (Note: the screener counts adv_fail over n_screened=n_with_prices, not over
    # the price-passing subset — see broad_universe.py "n_screened = n_with_prices".)
    assert result["broad_universe_adv_fail_pct"] is not None
    assert abs(result["broad_universe_adv_fail_pct"] - 20.0) < 0.01, (
        f"Expected adv_fail_pct=20.0 (1 adv-fail / 5 with-prices), "
        f"got {result['broad_universe_adv_fail_pct']}"
    )

    # 3 pass both floors (PASS1, PASS2, PASS3)
    assert result["broad_universe_screened_count"] == 3, (
        f"Expected screened_count=3, got {result['broad_universe_screened_count']}"
    )
