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

    assert len(df) == 4
    assert set(["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"]).issubset(df.columns)

    brk = df[df["wiki_ticker"] == "BRK.B"].iloc[0]
    assert brk["ticker"] == "BRK-B"
    assert brk["sector"] == "Financials"

    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["name"] == "Apple Inc."
    assert aapl["cik"] == "0000320193"


@pytest.mark.parametrize(
    "raw, expected",
    [
        # "(The)" suffix pattern (12 known S&P 500 entries 2026-05-14).
        ("Hartford (The)", "The Hartford"),
        ("Travelers Companies (The)", "The Travelers Companies"),
        ("Trade Desk (The)", "The Trade Desk"),
        ("Coca-Cola Company (The)", "The Coca-Cola Company"),
        ("Home Depot (The)", "The Home Depot"),
        ("Walt Disney Company (The)", "The Walt Disney Company"),
        ("Hershey Company (The)", "The Hershey Company"),
        ("Campbell's Company (The)", "The Campbell's Company"),
        ("J.M. Smucker Company (The)", "The J.M. Smucker Company"),
        ("Cooper Companies (The)", "The Cooper Companies"),
        ("Estée Lauder Companies (The)", "The Estée Lauder Companies"),
        ("Mosaic Company (The)", "The Mosaic Company"),
        # Inverted-prefix one-off override.
        ("Lilly (Eli)", "Eli Lilly"),
        # Names without any pattern should pass through unchanged.
        ("Apple Inc.", "Apple Inc."),
        ("Berkshire Hathaway Inc. (Class B)", "Berkshire Hathaway Inc. (Class B)"),
        ("Alphabet Inc. (Class C)", "Alphabet Inc. (Class C)"),
        ("3M", "3M"),
        ("IBM", "IBM"),
    ],
)
def test_normalize_company_name(raw: str, expected: str) -> None:
    assert universe_mod._normalize_company_name(raw) == expected


def test_parse_sp500_html_applies_name_normalization():
    """Wikipedia "(The)" suffix should disappear in the parsed DataFrame.

    The shipped sample fixture doesn't include a (The)-affected ticker, so we
    synthesize a small HTML table that mirrors the Wikipedia structure.
    """
    html = """
    <table class="wikitable">
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>
          <th>GICS Sub-Industry</th><th>CIK</th></tr>
      <tr><td>HIG</td><td>Hartford (The)</td><td>Financials</td>
          <td>Property &amp; Casualty Insurance</td><td>874766</td></tr>
      <tr><td>LLY</td><td>Lilly (Eli)</td><td>Health Care</td>
          <td>Pharmaceuticals</td><td>59478</td></tr>
    </table>
    """
    df = universe_mod.parse_sp500_html(html)
    assert df[df["ticker"] == "HIG"].iloc[0]["name"] == "The Hartford"
    assert df[df["ticker"] == "LLY"].iloc[0]["name"] == "Eli Lilly"


def test_parse_sp500_html_applies_ticker_overrides():
    """Stale Wikipedia symbols (e.g., FISV after the 2024 Fiserv rename) must
    be remapped via TICKER_OVERRIDES before they reach yfinance/EDGAR.
    """
    html = FIXTURE_HTML.read_text()
    df = universe_mod.parse_sp500_html(html)

    fi_row = df[df["wiki_ticker"] == "FISV"]
    assert len(fi_row) == 1
    assert fi_row.iloc[0]["ticker"] == "FI"
    assert "FISV" not in df["ticker"].values


def test_get_sp500_constituents_uses_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "universe.parquet"
    monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", cache_path)

    html = FIXTURE_HTML.read_text()
    monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", lambda *a, **kw: html)

    df1 = universe_mod.get_sp500_constituents()
    assert len(df1) == 4
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
