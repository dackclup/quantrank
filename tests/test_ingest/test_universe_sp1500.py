"""Tests for the S&P 1500 cutover — Slice 1: SP600 constituent fetcher + SP1500 loader.

All tests are offline (no network) — they use fixture HTML or synthetic
DataFrames to exercise the parsing, de-dup, and cohort-tag logic.

Coverage targets:
  1. _parse_sp600_html: fixture HTML, ticker normalisation, missing-CIK tolerance,
     Symbol/Ticker column variants, graceful handling of malformed input.
  2. fetch_sp600_constituents: cache hit/miss, graceful-degradation on network
     failure (returns empty DataFrame, never raises).
  3. get_sp1500_constituents: concat/dedup/cohort-tag with synthetic frames,
     dedup priority (sp500 > sp400 > sp600), cache written, CIK resolution loop.
  4. Network smoke test (gated @pytest.mark.network): live SP600 Wikipedia page
     returns ~600 rows with expected columns.
"""

from __future__ import annotations

import pandas as pd
import pytest

from compute.ingest import universe as universe_mod

# ---------------------------------------------------------------------------
# Fixture HTML for the S&P 600 Wikipedia page (minimal, offline)
# ---------------------------------------------------------------------------

SP600_FIXTURE_HTML_WITH_CIK = """
<html><body>
<table class="wikitable sortable">
<thead>
  <tr>
    <th>Ticker</th>
    <th>Company</th>
    <th>GICS Sector</th>
    <th>GICS Sub-Industry</th>
    <th>CIK</th>
  </tr>
</thead>
<tbody>
  <tr><td>SML1</td><td>SmallCap Alpha</td><td>Industrials</td><td>Aerospace &amp; Defense</td><td>11111</td></tr>
  <tr><td>SML2</td><td>SmallCap Beta</td><td>Financials</td><td>Banking</td><td>22222</td></tr>
  <tr><td>SML3</td><td>SmallCap Gamma</td><td>Health Care</td><td>Pharmaceuticals</td><td></td></tr>
</tbody>
</table>
</body></html>
"""

SP600_FIXTURE_HTML_SYMBOL_COL = """
<html><body>
<table class="wikitable sortable">
<thead>
  <tr>
    <th>Symbol</th>
    <th>Security</th>
    <th>GICS Sector</th>
  </tr>
</thead>
<tbody>
  <tr><td>SML4</td><td>SmallCap Delta</td><td>Energy</td></tr>
  <tr><td>SML5.A</td><td>SmallCap Epsilon</td><td>Materials</td></tr>
</tbody>
</table>
</body></html>
"""

SP600_FIXTURE_HTML_NO_TICKER = """
<html><body>
<table class="wikitable">
<thead>
  <tr><th>Name</th><th>Revenue</th></tr>
</thead>
<tbody>
  <tr><td>SomeCo</td><td>1B</td></tr>
</tbody>
</table>
</body></html>
"""

SP600_FIXTURE_HTML_MALFORMED = "<html><body><p>No table here</p></body></html>"


# ---------------------------------------------------------------------------
# Helper: build minimal synthetic DataFrames (mirrors sp900 test style)
# ---------------------------------------------------------------------------

def _make_sp500_df() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["AAPL", "MSFT", "SHARED"],
        "name": ["Apple Inc.", "Microsoft", "SharedCo"],
        "sector": ["IT", "IT", "Financials"],
        "sub_industry": [None, None, None],
        "cik": ["0000320193", "0000789019", "0000999000"],
        "wiki_ticker": ["AAPL", "MSFT", "SHARED"],
    })


def _make_sp400_df() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["MID1", "MID2", "SHARED_MID"],
        "name": ["MidCap One", "MidCap Two", "SharedMid"],
        "sector": ["Industrials", "Health Care", "Financials"],
        "sub_industry": [None, None, None],
        "cik": ["0001111111", None, "0002222222"],
        "wiki_ticker": ["MID1", "MID2", "SHARED_MID"],
    })


def _make_sp600_df(include_shared: bool = False) -> pd.DataFrame:
    rows = [
        {
            "ticker": "SML1",
            "name": "SmallCap Alpha",
            "sector": "Consumer Discretionary",
            "sub_industry": None,
            "cik": "0003333333",
            "wiki_ticker": "SML1",
        },
        {
            "ticker": "SML2",
            "name": "SmallCap Beta",
            "sector": "Industrials",
            "sub_industry": None,
            "cik": None,
            "wiki_ticker": "SML2",
        },
    ]
    if include_shared:
        # Simulates a ticker that also appears in sp500 or sp400
        rows.append({
            "ticker": "SHARED",
            "name": "SharedCo (600)",
            "sector": "Financials",
            "sub_industry": None,
            "cik": "0000999000",
            "wiki_ticker": "SHARED",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. _parse_sp600_html
# ---------------------------------------------------------------------------

class TestParseSp600Html:
    def test_parses_ticker_column(self) -> None:
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_WITH_CIK)
        assert "SML1" in df["ticker"].values
        assert "SML2" in df["ticker"].values
        assert "SML3" in df["ticker"].values

    def test_normalises_dot_in_ticker(self) -> None:
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_SYMBOL_COL)
        # SML5.A should normalise to SML5-A
        assert "SML5-A" in df["ticker"].values
        assert "SML4" in df["ticker"].values

    def test_required_columns_present(self) -> None:
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_WITH_CIK)
        for col in ("ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"):
            assert col in df.columns, f"Missing column: {col}"

    def test_cik_zero_padded_when_present(self) -> None:
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_WITH_CIK)
        sml1 = df[df["ticker"] == "SML1"].iloc[0]
        # 11111 → "0000011111"
        assert sml1["cik"] == "0000011111"
        sml2 = df[df["ticker"] == "SML2"].iloc[0]
        assert sml2["cik"] == "0000022222"

    def test_missing_cik_is_none(self) -> None:
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_WITH_CIK)
        sml3 = df[df["ticker"] == "SML3"].iloc[0]
        assert sml3["cik"] is None or (isinstance(sml3["cik"], float) and pd.isna(sml3["cik"]))

    def test_accepts_symbol_column_name(self) -> None:
        # S&P 600 Wikipedia may use "Symbol" rather than "Ticker"
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_SYMBOL_COL)
        assert len(df) == 2

    def test_no_ticker_column_raises(self) -> None:
        with pytest.raises(ValueError, match="Symbol.*Ticker|wikitable|ticker column"):
            universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_NO_TICKER)

    def test_empty_html_raises(self) -> None:
        with pytest.raises(ValueError):
            universe_mod._parse_sp600_html("<html><body></body></html>")

    def test_malformed_html_no_table_raises(self) -> None:
        with pytest.raises(ValueError):
            universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_MALFORMED)

    def test_deduplicates_tickers(self) -> None:
        html = """
        <html><body>
        <table class="wikitable">
          <tr><th>Ticker</th><th>Company</th><th>GICS Sector</th></tr>
          <tr><td>SML1</td><td>SmallCap Alpha</td><td>Industrials</td></tr>
          <tr><td>SML1</td><td>SmallCap Alpha Duplicate</td><td>Industrials</td></tr>
        </table>
        </body></html>
        """
        df = universe_mod._parse_sp600_html(html)
        assert df["ticker"].is_unique
        assert len(df[df["ticker"] == "SML1"]) == 1

    def test_sector_fallback_unknown(self) -> None:
        html = """
        <html><body>
        <table class="wikitable">
          <tr><th>Ticker</th><th>Company</th></tr>
          <tr><td>ZZZ</td><td>Zeta Co</td></tr>
        </table>
        </body></html>
        """
        df = universe_mod._parse_sp600_html(html)
        assert df.iloc[0]["sector"] == "Unknown"

    def test_row_count_approximately_600(self) -> None:
        """A realistic fixture HTML with 3 rows returns exactly 3 (parser is count-agnostic)."""
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_WITH_CIK)
        assert len(df) == 3

    def test_wiki_ticker_preserved(self) -> None:
        """wiki_ticker must hold the original (pre-normalise) value from Wikipedia."""
        df = universe_mod._parse_sp600_html(SP600_FIXTURE_HTML_SYMBOL_COL)
        sml5 = df[df["ticker"] == "SML5-A"].iloc[0]
        assert sml5["wiki_ticker"] == "SML5.A"


# ---------------------------------------------------------------------------
# 2. fetch_sp600_constituents — cache hit / miss / graceful degradation
# ---------------------------------------------------------------------------

class TestFetchSp600Constituents:
    def test_fetches_and_caches(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", lambda url: SP600_FIXTURE_HTML_WITH_CIK)

        df = universe_mod.fetch_sp600_constituents(force_refresh=True)
        assert len(df) == 3
        assert (tmp_path / "sp600.parquet").exists()

    def test_cache_hit_skips_network(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        cache_path = tmp_path / "sp600.parquet"
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        # Write a fake cache parquet first
        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", lambda url: SP600_FIXTURE_HTML_WITH_CIK)
        universe_mod.fetch_sp600_constituents(force_refresh=True)

        # Now replace the fetcher with one that would fail on a network call
        def boom(url: str) -> str:
            raise AssertionError("network fetch should not be called when cache is fresh")

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", boom)
        df2 = universe_mod.fetch_sp600_constituents(force_refresh=False)
        assert len(df2) == 3

    def test_graceful_degradation_on_network_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """On fetch failure, fetch_sp600_constituents must return an empty DataFrame, never raise."""
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        def fail_fetch(url: str) -> str:
            raise OSError("Wikipedia is down")

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", fail_fetch)

        df = universe_mod.fetch_sp600_constituents(force_refresh=True)
        # Must NOT raise — must return an empty DataFrame
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        # Required columns present even on empty result
        for col in ("ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"):
            assert col in df.columns, f"Empty-degradation DataFrame missing column: {col}"

    def test_graceful_degradation_on_parse_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """On parse failure (bad HTML), must return empty DataFrame, never raise."""
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        # Return malformed HTML that has no wikitable → _parse_sp600_html raises
        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", lambda url: SP600_FIXTURE_HTML_MALFORMED)

        df = universe_mod.fetch_sp600_constituents(force_refresh=True)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_force_refresh_bypasses_fresh_cache(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """force_refresh=True must re-fetch even when the cache parquet is young."""
        cache_path = tmp_path / "sp600.parquet"
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        call_count = {"n": 0}

        def counting_fetch(url: str) -> str:
            call_count["n"] += 1
            return SP600_FIXTURE_HTML_WITH_CIK

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", counting_fetch)

        # Prime the cache
        universe_mod.fetch_sp600_constituents(force_refresh=True)
        assert call_count["n"] == 1

        # force_refresh=True must re-fetch
        universe_mod.fetch_sp600_constituents(force_refresh=True)
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# 3. get_sp1500_constituents — concat / dedup / cohort-tag
# ---------------------------------------------------------------------------

class TestGetSp1500Constituents:
    def _build_sp1500(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
        sp500_df: pd.DataFrame | None = None,
        sp400_df: pd.DataFrame | None = None,
        sp600_df: pd.DataFrame | None = None,
        mock_cik: bool = True,
    ) -> pd.DataFrame:
        if sp500_df is None:
            sp500_df = _make_sp500_df()
        if sp400_df is None:
            sp400_df = _make_sp400_df()
        if sp600_df is None:
            sp600_df = _make_sp600_df()

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", tmp_path / "sp1500.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: sp500_df)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: sp400_df)
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", lambda **kw: sp600_df)

        if mock_cik:
            monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda ticker: None)

        return universe_mod.get_sp1500_constituents(force_refresh=True)

    def test_cohort_column_present(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        df = self._build_sp1500(monkeypatch, tmp_path)
        assert "cohort" in df.columns
        assert set(df["cohort"].unique()).issubset({"sp500", "sp400", "sp600"})

    def test_sp500_rows_tagged_correctly(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        df = self._build_sp1500(monkeypatch, tmp_path)
        assert (df[df["ticker"] == "AAPL"]["cohort"] == "sp500").all()
        assert (df[df["ticker"] == "MSFT"]["cohort"] == "sp500").all()

    def test_sp400_rows_tagged_correctly(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        df = self._build_sp1500(monkeypatch, tmp_path)
        assert (df[df["ticker"] == "MID1"]["cohort"] == "sp400").all()

    def test_sp600_rows_tagged_correctly(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        df = self._build_sp1500(monkeypatch, tmp_path)
        assert (df[df["ticker"] == "SML1"]["cohort"] == "sp600").all()
        assert (df[df["ticker"] == "SML2"]["cohort"] == "sp600").all()

    def test_dedup_sp500_wins_on_overlap_with_sp600(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """A ticker in both SP500 and SP600 must appear exactly once with cohort=sp500."""
        sp600_with_shared = _make_sp600_df(include_shared=True)  # SHARED also in sp500
        df = self._build_sp1500(monkeypatch, tmp_path, sp600_df=sp600_with_shared)
        shared_rows = df[df["ticker"] == "SHARED"]
        assert len(shared_rows) == 1, "SHARED ticker must appear exactly once"
        assert shared_rows.iloc[0]["cohort"] == "sp500", "SP500 must win over SP600"

    def test_dedup_sp400_wins_over_sp600_on_overlap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """A ticker in SP400 but NOT SP500 that also appears in SP600 keeps cohort=sp400."""
        sp400_with_mid = pd.DataFrame({
            "ticker": ["MID1", "SHARED_MID"],
            "name": ["MidCap One", "SharedMid"],
            "sector": ["Industrials", "Financials"],
            "sub_industry": [None, None],
            "cik": ["0001111111", "0002222222"],
            "wiki_ticker": ["MID1", "SHARED_MID"],
        })
        sp600_with_shared_mid = pd.DataFrame({
            "ticker": ["SML1", "SHARED_MID"],   # SHARED_MID in both sp400 + sp600
            "name": ["SmallCap Alpha", "SharedMid (600)"],
            "sector": ["Consumer Discretionary", "Financials"],
            "sub_industry": [None, None],
            "cik": ["0003333333", "0002222222"],
            "wiki_ticker": ["SML1", "SHARED_MID"],
        })
        df = self._build_sp1500(monkeypatch, tmp_path, sp400_df=sp400_with_mid, sp600_df=sp600_with_shared_mid)
        shared_rows = df[df["ticker"] == "SHARED_MID"]
        assert len(shared_rows) == 1, "SHARED_MID must appear exactly once"
        assert shared_rows.iloc[0]["cohort"] == "sp400", "SP400 must win over SP600"

    def test_no_duplicate_tickers(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        df = self._build_sp1500(monkeypatch, tmp_path)
        assert df["ticker"].is_unique, "SP1500 DataFrame must have unique tickers"

    def test_approximate_size(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        """3 sp500 + 3 sp400 + 2 sp600 (no overlap) = 8 total."""
        sp500_df = _make_sp500_df()    # 3 tickers: AAPL, MSFT, SHARED
        sp400_df = _make_sp400_df()    # 3 tickers: MID1, MID2, SHARED_MID
        sp600_df = _make_sp600_df()    # 2 tickers: SML1, SML2 (no overlap)
        df = self._build_sp1500(monkeypatch, tmp_path, sp500_df=sp500_df, sp400_df=sp400_df, sp600_df=sp600_df)
        assert len(df) == 8

    def test_cache_written(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        self._build_sp1500(monkeypatch, tmp_path)
        cache = tmp_path / "sp1500.parquet"
        assert cache.exists(), "SP1500 cache parquet must be written"

    def test_cache_read_on_second_call(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        """Second call with a warm cache must NOT call constituent fetchers again."""
        call_count = {"sp500": 0, "sp400": 0, "sp600": 0}

        def sp500_fn(**kw: object) -> pd.DataFrame:
            call_count["sp500"] += 1
            return _make_sp500_df()

        def sp400_fn(**kw: object) -> pd.DataFrame:
            call_count["sp400"] += 1
            return _make_sp400_df()

        def sp600_fn(**kw: object) -> pd.DataFrame:
            call_count["sp600"] += 1
            return _make_sp600_df()

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", tmp_path / "sp1500.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "get_sp500_constituents", sp500_fn)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", sp400_fn)
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", sp600_fn)
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda ticker: None)

        # First call — builds + writes cache
        universe_mod.get_sp1500_constituents(force_refresh=True)
        assert call_count["sp500"] == 1
        assert call_count["sp600"] == 1

        # Simulate all three constituent caches being fresh (touch the parquet files)
        (tmp_path / "sp500.parquet").write_bytes(b"fake")
        (tmp_path / "sp400.parquet").write_bytes(b"fake")
        (tmp_path / "sp600.parquet").write_bytes(b"fake")

        # Second call — should serve from sp1500 cache
        universe_mod.get_sp1500_constituents(force_refresh=False)
        assert call_count["sp500"] == 1, "SP500 should not be re-fetched on cache hit"
        assert call_count["sp600"] == 1, "SP600 should not be re-fetched on cache hit"

    def test_cik_resolution_called_for_null_cik_smallcaps(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Tickers with null CIK in SP600 must trigger _resolve_cik_for_midcap."""
        resolved: list[str] = []

        def fake_resolve(ticker: str) -> None:
            resolved.append(ticker)
            return None  # stay None (no network)

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", tmp_path / "sp1500.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: _make_sp500_df())
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: _make_sp400_df())
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", lambda **kw: _make_sp600_df())
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", fake_resolve)

        universe_mod.get_sp1500_constituents(force_refresh=True)
        # SML2 has null CIK in sp600 → must be passed to resolve
        assert "SML2" in resolved

    def test_cik_resolution_not_called_for_sp500_tickers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """SP500 tickers (which always have CIKs) must not trigger CIK resolve."""
        resolved: list[str] = []

        def fake_resolve(ticker: str) -> None:
            resolved.append(ticker)
            return None

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", tmp_path / "sp1500.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: _make_sp500_df())
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: _make_sp400_df())
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", lambda **kw: _make_sp600_df())
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", fake_resolve)

        universe_mod.get_sp1500_constituents(force_refresh=True)
        for sp500_ticker in ("AAPL", "MSFT", "SHARED"):
            assert sp500_ticker not in resolved, (
                f"{sp500_ticker} must not go through CIK resolution (sp500 always has CIK)"
            )

    def test_all_three_cohorts_in_result(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        """The result DataFrame must contain all three cohort values."""
        df = self._build_sp1500(monkeypatch, tmp_path)
        cohorts = set(df["cohort"].unique())
        assert "sp500" in cohorts
        assert "sp400" in cohorts
        assert "sp600" in cohorts

    def test_sp600_empty_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """If fetch_sp600_constituents returns empty (graceful degradation), must not crash."""
        empty_sp600 = pd.DataFrame(
            columns=["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"]
        )
        df = self._build_sp1500(monkeypatch, tmp_path, sp600_df=empty_sp600)
        # Should still return sp500 + sp400 rows
        assert "AAPL" in df["ticker"].values
        assert "MID1" in df["ticker"].values
        # No sp600 cohort rows
        assert "sp600" not in df["cohort"].values


# ---------------------------------------------------------------------------
# 4. @network: live SP600 Wikipedia page smoke test
# ---------------------------------------------------------------------------

@pytest.mark.network
def test_live_sp600_wikipedia_returns_expected_size() -> None:
    """Live smoke test: SP600 Wikipedia must return ~600 rows with expected columns.

    Gated by @pytest.mark.network — skips without --run-network flag and
    requires EDGAR_USER_AGENT to be set (same convention as the SP400 network test).
    """
    df = universe_mod.fetch_sp600_constituents(force_refresh=True)
    # S&P 600 has nominally 600 components; allow ±5% wiggle for Wikipedia lag
    assert 570 <= len(df) <= 630, (
        f"Expected ~600 SP600 constituents, got {len(df)}. "
        "Wikipedia page may have changed structure."
    )
    assert df["ticker"].is_unique, "SP600 tickers must be unique"
    for col in ("ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"):
        assert col in df.columns, f"Expected column '{col}' missing from live SP600 result"
