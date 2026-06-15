"""Tests for Issue #378 — prices module smoke + ``fetch_prices`` offline contract.

RE-SCOPE DECISION (Issue #378 named ``fetch_prices_one`` which no longer
exists):
  - The public API is now ``fetch_prices`` (``compute/ingest/prices.py``) for
    the download/cache layer.
  - The day-over-day pct math (``price_change_1d_pct``) lives in
    ``compute.main._fetch_prices_one`` as an inline computation after the
    close series is resolved.
  - Tests are split accordingly:
    * This file: ``fetch_prices`` offline smoke (mocked ``_yf_download``).
    * ``tests/test_main.py`` extension: ``_pct_1d`` edge cases for the
      price_change_1d_pct math (see test_main.py::test_price_change_1d_pct_*).

``test_prices_min_start.py`` already covers the ``min_start`` depth-check
contract (P1-P4 + A1-A8); this file adds orthogonal coverage:
  - Smoke: happy-path offline fetch returns a DataFrame.
  - Empty/None response → None returned.
  - Cache miss → download triggered exactly once.

NOTE on environment: ``compute.ingest.prices`` has a top-level
``import yfinance as yf``.  Since ``yfinance`` is an optional dep (not
installed in every environment), we stub it in ``sys.modules`` at module
load so this file collects without the package.  The functions under test
(``fetch_prices``, the cache layer, ``_yf_download`` monkeypatch path)
only call the real yfinance via ``_yf_download`` — which we always
monkeypatch in these tests, so the stub is never called.
"""

from __future__ import annotations

import sys
import types

import pandas as pd

# ---------------------------------------------------------------------------
# yfinance stub — allows prices.py to import without yfinance installed
# ---------------------------------------------------------------------------


def _stub_yfinance():
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
from compute.ingest.prices import fetch_prices  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bday_frame(start: str, periods: int, close_start: float = 100.0) -> pd.DataFrame:
    """Minimal daily price DataFrame with a 'Close' column."""
    idx = pd.bdate_range(start, periods=periods)
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


# ---------------------------------------------------------------------------
# Smoke: happy-path offline fetch
# ---------------------------------------------------------------------------


def test_fetch_prices_returns_dataframe_on_cache_hit(tmp_path, monkeypatch) -> None:
    """fetch_prices returns a DataFrame when a fresh cache entry exists.

    No yfinance download should occur (download_calls stays empty).
    """
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    frame = _bday_frame("2025-01-02", 30)
    (tmp_path / "SMOK.parquet").write_bytes(frame.to_parquet())

    download_calls: list = []

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        download_calls.append(ticker)
        return frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("SMOK")

    assert result is not None, "fetch_prices must return a DataFrame on cache hit"
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 30
    assert len(download_calls) == 0, "Cache hit must not trigger a download"


def test_fetch_prices_download_called_on_cache_miss(tmp_path, monkeypatch) -> None:
    """When no cache entry exists, ``_yf_download`` is called exactly once
    and the result is returned (and cached).
    """
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    frame = _bday_frame("2015-12-01", 20)
    download_calls: list = []

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        download_calls.append(ticker)
        return frame

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("MISS")

    assert len(download_calls) == 1, "Cache miss must trigger exactly one download"
    assert result is not None
    assert len(result) == len(frame)
    # Cache was written:
    assert (tmp_path / "MISS.parquet").exists()


def test_fetch_prices_returns_none_on_empty_download(tmp_path, monkeypatch) -> None:
    """When ``_yf_download`` returns an empty DataFrame, ``fetch_prices``
    must return ``None`` (graceful degrade — empty response is not usable).
    """
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        return pd.DataFrame()  # empty

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("EMPTY")

    assert result is None, (
        "fetch_prices must return None when _yf_download returns an empty DataFrame"
    )


def test_fetch_prices_returns_none_on_download_exception(tmp_path, monkeypatch) -> None:
    """When ``_yf_download`` raises (network error / yfinance failure after
    retries), ``fetch_prices`` must return ``None`` (graceful degrade).
    """
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_DIR", tmp_path)
    monkeypatch.setattr(prices_mod.config, "PRICES_CACHE_MAX_AGE_HOURS", 48)

    def fake_download(ticker: str, period: str, *, start=None) -> pd.DataFrame:
        raise ConnectionError("yfinance network failure")

    monkeypatch.setattr(prices_mod, "_yf_download", fake_download)

    result = fetch_prices("ERR")

    assert result is None, (
        "fetch_prices must return None when _yf_download raises"
    )
