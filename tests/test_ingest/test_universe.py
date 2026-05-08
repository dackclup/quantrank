"""Tests for the S&P 500 universe scraper.

Default tests use a small bundled HTML fixture (offline, deterministic). A
network smoke test against the live Wikipedia page is opt-in via --run-network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compute.ingest import universe as universe_mod

FIXTURE_HTML = Path(__file__).parent.parent / "fixtures" / "sp500_sample.html"


def test_parse_sp500_html_normalizes_brk_b():
    html = FIXTURE_HTML.read_text()
    df = universe_mod.parse_sp500_html(html)

    assert len(df) == 3
    assert set(["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"]).issubset(df.columns)

    brk = df[df["wiki_ticker"] == "BRK.B"].iloc[0]
    assert brk["ticker"] == "BRK-B"
    assert brk["sector"] == "Financials"

    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["name"] == "Apple Inc."
    assert aapl["cik"] == "0000320193"


def test_get_sp500_constituents_uses_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "universe.parquet"
    monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", cache_path)

    html = FIXTURE_HTML.read_text()
    monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", lambda *a, **kw: html)

    df1 = universe_mod.get_sp500_constituents()
    assert len(df1) == 3
    assert cache_path.exists()

    # Second call should not refetch — replace the fetcher with a sentinel that would fail.
    def boom():
        raise AssertionError("network fetch should not be called when cache is fresh")

    monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", lambda *a, **kw: boom())
    df2 = universe_mod.get_sp500_constituents()
    assert df2.equals(df1)


@pytest.mark.network
def test_live_wikipedia_returns_full_universe():
    df = universe_mod.get_sp500_constituents(force_refresh=True)
    assert len(df) >= 480
    assert df["ticker"].is_unique
    # Spot-check known tickers.
    assert "AAPL" in df["ticker"].values
