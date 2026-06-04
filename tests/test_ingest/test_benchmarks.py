"""Tests for the Phase 7.0 benchmark index fetch (``compute.ingest.prices``).

Offline — ``fetch_prices`` is monkeypatched so no network / @network marker is
needed. The live SPY/QQQ/DIA/IWM fetch is exercised by the weekly cron.
"""
from __future__ import annotations

import pandas as pd

from compute.ingest import prices


def test_benchmark_tickers_manifest() -> None:
    # Phase 7 benchmark selector universe — SPY (S&P 500) is the β baseline +
    # default benchmark; QQQ / DIA / IWM are display-only comparison indices.
    # Locks the set so a silent reorder / drop is caught (lightweight manifest).
    assert prices.BENCHMARK_TICKERS == ("SPY", "QQQ", "DIA", "IWM")


def test_fetch_benchmarks_returns_per_symbol(monkeypatch) -> None:
    calls: list[str] = []

    def fake_fetch_prices(ticker, period=prices.config.PRICES_PERIOD):
        calls.append(ticker)
        if ticker == "IWM":
            return None  # one symbol fails → graceful per-symbol None
        return pd.DataFrame({"Close": [1.0, 2.0]})

    monkeypatch.setattr(prices, "fetch_prices", fake_fetch_prices)
    out = prices.fetch_benchmarks()

    assert set(out.keys()) == set(prices.BENCHMARK_TICKERS)
    assert out["IWM"] is None
    assert out["SPY"] is not None
    assert calls == list(prices.BENCHMARK_TICKERS)


def test_fetch_benchmarks_swallows_exception(monkeypatch) -> None:
    """A raising fetch must NOT propagate — the cron can't block on a benchmark."""

    def boom(ticker, period=prices.config.PRICES_PERIOD):
        raise RuntimeError("network down")

    monkeypatch.setattr(prices, "fetch_prices", boom)
    out = prices.fetch_benchmarks()  # must not raise

    assert set(out.keys()) == set(prices.BENCHMARK_TICKERS)
    assert all(v is None for v in out.values())
