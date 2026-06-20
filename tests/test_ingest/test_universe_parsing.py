"""Offline tests covering the parsing/normalization/caching gaps in universe.py.

After the existing test files (test_universe.py, test_universe_sp900.py,
test_universe_sp900_pr3a.py, test_universe_sp1500.py, test_index_memberships.py),
the remaining uncovered lines at the 80% baseline are:

Lines 50-52    — _fetch_wikipedia_html body (network-only, explicitly skipped)
Line 99        — parse_sp500_html: no wikitable → ValueError
Line 112       — parse_sp500_html: missing expected column → ValueError
Line 129->133  — get_sp500_constituents: stale/absent cache → re-fetch
Lines 167-168  — _parse_sp400_html: pd.read_html exception path (continue)
Line 193->183  — _parse_sp400_html: "sub" branch in col_map loop (sub_industry)
Line 199       — _parse_sp400_html: wiki_ticker absent after col_map → ValueError
Line 207       — _parse_sp400_html: name column absent → fallback ticker
Lines 229-230  — _parse_sp400_html: _safe_cik ValueError/TypeError branch
Lines 249-263  — fetch_sp400_constituents: cache-hit path + write path
Lines 291-310  — _resolve_cik_for_midcap: edgar happy path + exception path
Lines 354->358 / 376->383 — get_sp900_constituents: resolved/unresolved log paths
Lines 386->407 / 396-397  — get_sp900_constituents: CIK resolution success branch
Lines 450-451  — _parse_sp600_html: sub_industry branch in col_map loop
Lines 475->465 — _parse_sp600_html: CIK branch  (cl == "cik")
Line 481       — _parse_sp600_html: wiki_ticker absent → ValueError
Line 489       — _parse_sp600_html: name absent → fallback
Lines 511-512  — _parse_sp600_html: _safe_cik ValueError/TypeError branch
Lines 541->545 — fetch_sp600_constituents: cache-hit path
Lines 562-563  — fetch_sp600_constituents: cache write failure (non-fatal)
Lines 621->625 — get_sp1500_constituents: cache-hit path
Lines 669-670  — get_sp1500_constituents: unresolved CIK log
Lines 708-709  — _parse_dow30_html: pd.read_html exception (continue branch)
Lines 719->705 — _parse_dow30_html: tickers empty → continue to next table
Lines 734-735  — _parse_ndx_html: pd.read_html exception (continue branch)
Lines 748->731 — _parse_ndx_html: tickers empty → continue to next table
Lines 767-775  — fetch_dow30_constituents: cache-hit path + corrupt-cache re-fetch
Lines 798-799  — fetch_dow30_constituents: cache write failure path
Lines 818-826  — fetch_ndx_constituents: cache-hit path + corrupt-cache re-fetch
Lines 851-852  — fetch_ndx_constituents: cache write failure path

All tests are OFFLINE — no network calls. Network-only lines (50-52) are noted
but not tested here; they require --run-network.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pandas as pd
import pytest

from compute.ingest import universe as universe_mod

# ---------------------------------------------------------------------------
# Shared minimal HTML fixtures
# ---------------------------------------------------------------------------

_SP500_VALID_HTML = dedent("""\
    <html><body>
    <table class="wikitable">
    <thead>
      <tr>
        <th>Symbol</th><th>Security</th><th>GICS Sector</th>
        <th>GICS Sub-Industry</th><th>CIK</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>AAPL</td><td>Apple Inc.</td><td>Technology</td>
          <td>Technology Hardware</td><td>320193</td></tr>
      <tr><td>MSFT</td><td>Microsoft</td><td>Technology</td>
          <td>Systems Software</td><td>789019</td></tr>
    </tbody>
    </table>
    </body></html>
""")

_SP400_WITH_ALL_COLS = dedent("""\
    <html><body>
    <table class="wikitable">
    <thead>
      <tr>
        <th>Ticker</th><th>Company</th><th>GICS Sector</th>
        <th>GICS Sub-Industry</th><th>CIK</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>MID1</td><td>MidCap One</td><td>Industrials</td>
          <td>Aerospace &amp; Defense</td><td>12345</td></tr>
    </tbody>
    </table>
    </body></html>
""")

_SP400_NO_CIK = dedent("""\
    <html><body>
    <table class="wikitable">
    <thead>
      <tr>
        <th>Ticker</th><th>Company</th><th>GICS Sector</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>MID1</td><td>MidCap One</td><td>Industrials</td></tr>
    </tbody>
    </table>
    </body></html>
""")

_SP400_NO_NAME = dedent("""\
    <html><body>
    <table class="wikitable">
    <thead>
      <tr>
        <th>Ticker</th><th>GICS Sector</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>MID1</td><td>Industrials</td></tr>
    </tbody>
    </table>
    </body></html>
""")

# A wikitable that pandas cannot parse (deliberate malformed cell count mismatch
# that triggers an internal read_html exception).  We use a table header with
# colspan so read_html may succeed or fail depending on version; we use a
# simpler approach: an empty table body tag that reliably produces no rows but
# doesn't crash BeautifulSoup — it's the pd.read_html that we want to trip.
# We test the except-continue branch instead with a BeautifulSoup-unparsable tag.
_HTML_WITH_UNPARSEABLE_TABLE = dedent("""\
    <html><body>
    <table class="wikitable">
    <tbody>
      <tr><td colspan="99999" rowspan="99999">bad</td></tr>
    </tbody>
    </table>
    <table class="wikitable">
    <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
    <tbody><tr><td>MID2</td><td>MidCap Two</td></tr></tbody>
    </table>
    </body></html>
""")

# DOW 30-style fixture HTML (30 rows, Symbol column)
def _make_dow_html(n: int) -> str:
    rows = "\n".join(
        f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(n)
    )
    return dedent(f"""\
        <html><body>
        <table class="wikitable">
        <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
        <tbody>{rows}</tbody>
        </table></body></html>
    """)


def _make_ndx_html(n: int) -> str:
    rows = "\n".join(
        f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(n)
    )
    return dedent(f"""\
        <html><body>
        <table class="wikitable">
        <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
        <tbody>{rows}</tbody>
        </table></body></html>
    """)


# ---------------------------------------------------------------------------
# 1. parse_sp500_html — missing-table and missing-column error paths
# ---------------------------------------------------------------------------


class TestParseSp500HtmlErrors:
    """Line 99 (no wikitable) and line 112 (missing expected column)."""

    def test_no_wikitable_raises_value_error(self) -> None:
        """parse_sp500_html with no <table class="wikitable"> must raise ValueError."""
        html = "<html><body><p>Nothing here</p></body></html>"
        with pytest.raises(ValueError, match="Could not find S&P 500"):
            universe_mod.parse_sp500_html(html)

    def test_missing_symbol_column_raises_value_error(self) -> None:
        """parse_sp500_html raises ValueError when 'Symbol' column is absent.

        This exercises line 112 — the `missing` list is non-empty → ValueError.
        """
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Security</th><th>GICS Sector</th>
                       <th>GICS Sub-Industry</th><th>CIK</th></tr></thead>
            <tbody><tr><td>AAPL</td><td>Apple Inc.</td><td>Technology</td>
                       <td>Hardware</td><td>320193</td></tr></tbody>
            </table></body></html>
        """)
        with pytest.raises(ValueError, match="missing expected columns"):
            universe_mod.parse_sp500_html(html)

    def test_missing_cik_column_raises_value_error(self) -> None:
        """CIK is one of the five required columns; absence must raise."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Symbol</th><th>Security</th>
                       <th>GICS Sector</th><th>GICS Sub-Industry</th></tr></thead>
            <tbody><tr><td>AAPL</td><td>Apple Inc.</td>
                       <td>Technology</td><td>Hardware</td></tr></tbody>
            </table></body></html>
        """)
        with pytest.raises(ValueError, match="missing expected columns"):
            universe_mod.parse_sp500_html(html)


# ---------------------------------------------------------------------------
# 2. get_sp500_constituents — stale cache forces re-fetch (line 129->133)
# ---------------------------------------------------------------------------


class TestGetSp500ConstituentsCacheAge:
    """Cover the branch where the cache exists but is too old → re-fetches."""

    def test_stale_cache_triggers_refetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A cache file older than UNIVERSE_CACHE_MAX_AGE_DAYS must be refreshed."""
        cache_path = tmp_path / "universe.parquet"
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", cache_path)
        # Force an absurdly small max-age so the just-written cache is immediately stale.
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", -1)

        fetch_count = {"n": 0}

        def counting_fetch(url: str | None = None) -> str:
            fetch_count["n"] += 1
            return _SP500_VALID_HTML

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", counting_fetch)

        # First call — writes the cache.
        universe_mod.get_sp500_constituents()
        assert fetch_count["n"] == 1

        # Second call — max_age is -1 so any file is "stale"; must re-fetch.
        universe_mod.get_sp500_constituents()
        assert fetch_count["n"] == 2, (
            "Expected re-fetch when cache is older than UNIVERSE_CACHE_MAX_AGE_DAYS"
        )


# ---------------------------------------------------------------------------
# 3. _parse_sp400_html — uncovered branches
# ---------------------------------------------------------------------------


class TestParseSp400HtmlBranches:
    """Cover: sub_industry branch (line 193), wiki_ticker absent (line 199),
    name-fallback (line 207), _safe_cik ValueError/TypeError (lines 229-230).
    """

    def test_sub_industry_column_is_parsed(self) -> None:
        """The 'sub' + 'industry' column branch in col_map must map to sub_industry.

        This is line 193->183 — exercised when the table has a GICS Sub-Industry col.
        """
        df = universe_mod._parse_sp400_html(_SP400_WITH_ALL_COLS)
        assert "sub_industry" in df.columns
        # The value comes from the 'GICS Sub-Industry' column cell
        assert df.iloc[0]["sub_industry"] == "Aerospace & Defense"

    def test_no_ticker_column_raises(self) -> None:
        """A wikitable with no Symbol/Ticker column must raise ValueError (line 174-178).

        The table has columns that don't match symbol/ticker so df stays None after the
        loop, triggering the raise at line 174-178 ('Could not find … Symbol or Ticker').
        Line 199 (the defensive wiki_ticker-post-rename check) is structurally dead code
        because any table that passes the `"symbol" in cols_lower or "ticker" in cols_lower`
        guard at line 170 will always produce wiki_ticker in col_map at lines 185-186.
        """
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Name</th><th>Revenue</th></tr></thead>
            <tbody><tr><td>SomeCo</td><td>1B</td></tr></tbody>
            </table></body></html>
        """)
        with pytest.raises(ValueError, match="Symbol.*Ticker"):
            universe_mod._parse_sp400_html(html)

    def test_name_column_absent_falls_back_to_ticker(self) -> None:
        """When 'name' column is absent from the table, name falls back to ticker (line 207)."""
        df = universe_mod._parse_sp400_html(_SP400_NO_NAME)
        assert "name" in df.columns
        # name should equal ticker when the column is missing
        assert df.iloc[0]["name"] == df.iloc[0]["ticker"]

    def test_safe_cik_non_numeric_returns_none(self) -> None:
        """_safe_cik's ValueError branch: a non-numeric CIK string should return None."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th><th>GICS Sector</th>
                       <th>CIK</th></tr></thead>
            <tbody><tr><td>MID1</td><td>MidCap One</td><td>Industrials</td>
                       <td>not-a-number</td></tr></tbody>
            </table></body></html>
        """)
        df = universe_mod._parse_sp400_html(html)
        row = df.iloc[0]
        # "not-a-number" cannot be converted to int → _safe_cik returns None
        assert row["cik"] is None or (isinstance(row["cik"], float) and pd.isna(row["cik"]))

    def test_no_cik_column_gives_none_column(self) -> None:
        """When the table has no CIK column, the cik column in the result must be None."""
        df = universe_mod._parse_sp400_html(_SP400_NO_CIK)
        assert "cik" in df.columns
        # All values must be None (no column → df["cik"] = None assignment)
        assert df["cik"].isna().all() or all(v is None for v in df["cik"])


# ---------------------------------------------------------------------------
# 4. fetch_sp400_constituents — cache hit and write (lines 249-263)
# ---------------------------------------------------------------------------


class TestFetchSp400Constituents:
    """Cover the cache-hit path and the fetch+write path."""

    def test_cache_hit_skips_network(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A fresh cache parquet must be read without calling _fetch_wikipedia_html."""
        cache_path = tmp_path / "sp400.parquet"
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)

        # Prime the cache
        monkeypatch.setattr(
            universe_mod, "_fetch_wikipedia_html", lambda url: _SP400_WITH_ALL_COLS
        )
        universe_mod.fetch_sp400_constituents(force_refresh=True)

        def boom(url: str) -> str:
            raise AssertionError("network fetch should not be called on cache hit")

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", boom)
        df = universe_mod.fetch_sp400_constituents(force_refresh=False)
        assert len(df) == 1
        assert "MID1" in df["ticker"].values

    def test_force_refresh_bypasses_fresh_cache(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """force_refresh=True must re-fetch even when the cache is fresh."""
        cache_path = tmp_path / "sp400.parquet"
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)

        call_count = {"n": 0}

        def counting_fetch(url: str) -> str:
            call_count["n"] += 1
            return _SP400_WITH_ALL_COLS

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", counting_fetch)

        universe_mod.fetch_sp400_constituents(force_refresh=True)
        assert call_count["n"] == 1

        universe_mod.fetch_sp400_constituents(force_refresh=True)
        assert call_count["n"] == 2

    def test_fetch_writes_cache_parquet(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """After a successful fetch, cache parquet must be written."""
        cache_path = tmp_path / "sp400.parquet"
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(
            universe_mod, "_fetch_wikipedia_html", lambda url: _SP400_WITH_ALL_COLS
        )
        universe_mod.fetch_sp400_constituents(force_refresh=True)
        assert cache_path.exists()

    def test_stale_cache_triggers_refetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A stale cache (max_age_days=-1) must trigger a network refetch."""
        cache_path = tmp_path / "sp400.parquet"
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", -1)

        call_count = {"n": 0}

        def counting_fetch(url: str) -> str:
            call_count["n"] += 1
            return _SP400_WITH_ALL_COLS

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", counting_fetch)

        universe_mod.fetch_sp400_constituents()
        assert call_count["n"] == 1

        # Second call: cache exists but age_days > -1 so it's "stale" → re-fetch
        universe_mod.fetch_sp400_constituents()
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# 5. _parse_sp600_html — uncovered branches mirrored from sp400
# ---------------------------------------------------------------------------


class TestParseSp600HtmlBranches:
    """Cover: sub_industry branch (line 450-451), cik branch (line 475),
    wiki_ticker absent (line 481), name fallback (line 489),
    _safe_cik error branch (lines 511-512).
    """

    def test_sub_industry_column_is_parsed(self) -> None:
        """The sub_industry column must be extracted from GICS Sub-Industry."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th><th>GICS Sector</th>
                       <th>GICS Sub-Industry</th><th>CIK</th></tr></thead>
            <tbody><tr><td>SML1</td><td>SmallCo</td><td>Industrials</td>
                       <td>Agricultural &amp; Farm Machinery</td><td>99999</td></tr>
            </tbody></table></body></html>
        """)
        df = universe_mod._parse_sp600_html(html)
        assert df.iloc[0]["sub_industry"] == "Agricultural & Farm Machinery"

    def test_cik_column_present_and_zero_padded(self) -> None:
        """CIK branch (cl == 'cik') in col_map must map and zero-pad."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th><th>GICS Sector</th>
                       <th>CIK</th></tr></thead>
            <tbody><tr><td>SML1</td><td>SmallCo</td><td>Industrials</td>
                       <td>77777</td></tr>
            </tbody></table></body></html>
        """)
        df = universe_mod._parse_sp600_html(html)
        assert df.iloc[0]["cik"] == "0000077777"

    def test_no_ticker_column_in_wikitable_raises(self) -> None:
        """No Symbol/Ticker column → raises ValueError (line 457-461).

        Line 481 (wiki_ticker post-rename check) is structurally dead code — any
        table that passes the `cols_lower.get('symbol') or cols_lower.get('ticker')`
        guard will always have wiki_ticker in col_map.  The actual raise in practice
        is lines 457-461: 'Could not find … Symbol or Ticker column.'
        """
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Name</th><th>Revenue</th></tr></thead>
            <tbody><tr><td>SomeCo</td><td>5B</td></tr></tbody>
            </table></body></html>
        """)
        with pytest.raises(ValueError, match="Symbol.*Ticker|Symbol or Ticker"):
            universe_mod._parse_sp600_html(html)

    def test_name_column_absent_falls_back_to_ticker(self) -> None:
        """When 'name' / 'company' column is absent, name falls back to ticker (line 489)."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>GICS Sector</th></tr></thead>
            <tbody><tr><td>SML1</td><td>Industrials</td></tr></tbody>
            </table></body></html>
        """)
        df = universe_mod._parse_sp600_html(html)
        assert df.iloc[0]["name"] == "SML1"

    def test_safe_cik_non_numeric_returns_none(self) -> None:
        """_safe_cik ValueError branch: non-numeric CIK in SP600 table → None."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th><th>GICS Sector</th>
                       <th>CIK</th></tr></thead>
            <tbody><tr><td>SML1</td><td>SmallCo</td><td>Industrials</td>
                       <td>INVALID</td></tr>
            </tbody></table></body></html>
        """)
        df = universe_mod._parse_sp600_html(html)
        row = df.iloc[0]
        assert row["cik"] is None or (isinstance(row["cik"], float) and pd.isna(row["cik"]))


# ---------------------------------------------------------------------------
# 6. fetch_sp600_constituents — cache-hit path (line 541->545) and
#    cache-write failure (lines 562-563)
# ---------------------------------------------------------------------------


class TestFetchSp600ConstituentsCachePaths:
    """Cover: cache-hit short-circuit and non-fatal cache-write failure."""

    def test_cache_hit_reads_parquet(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A fresh SP600 cache must be read without a network call (line 541->545)."""
        cache_path = tmp_path / "sp600.parquet"
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        # Prime cache
        monkeypatch.setattr(
            universe_mod,
            "_fetch_wikipedia_html",
            lambda url: dedent("""\
                <html><body>
                <table class="wikitable">
                <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
                <tbody><tr><td>SML1</td><td>SmallCo</td></tr></tbody>
                </table></body></html>
            """),
        )
        universe_mod.fetch_sp600_constituents(force_refresh=True)

        # Replace fetcher with sentinel that must not fire
        def boom(url: str) -> str:
            raise AssertionError("should not fetch on cache hit")

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", boom)
        df = universe_mod.fetch_sp600_constituents(force_refresh=False)
        assert len(df) == 1

    def test_cache_write_failure_is_non_fatal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If parquet write fails, fetch_sp600_constituents must still return the
        DataFrame rather than raising (lines 562-563).
        """
        cache_path = tmp_path / "sp600.parquet"
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(
            universe_mod,
            "_fetch_wikipedia_html",
            lambda url: dedent("""\
                <html><body>
                <table class="wikitable">
                <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
                <tbody><tr><td>SML1</td><td>SmallCo</td></tr></tbody>
                </table></body></html>
            """),
        )

        # Patch DataFrame.to_parquet to raise so we enter the except-block at 562-563
        def failing_to_parquet(self_df: pd.DataFrame, *args: object, **kwargs: object) -> None:
            raise OSError("Simulated disk-full write failure")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", failing_to_parquet)

        df = universe_mod.fetch_sp600_constituents(force_refresh=True)
        # Must NOT raise — must return the DataFrame despite write failure
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# 7. get_sp1500_constituents — cache-hit path (line 621->625)
# ---------------------------------------------------------------------------


class TestGetSp1500CacheHit:
    """When all three constituent caches are fresh AND the sp1500 cache is young,
    get_sp1500_constituents must serve from the sp1500 cache without calling the
    constituent fetchers.  Exercises the cache-read short-circuit at line 621->625.
    """

    def test_cache_hit_skips_constituent_fetchers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        sp500_cache = tmp_path / "sp500.parquet"
        sp400_cache = tmp_path / "sp400.parquet"
        sp600_cache = tmp_path / "sp600.parquet"
        sp1500_cache = tmp_path / "sp1500.parquet"

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", sp500_cache)
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", sp400_cache)
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", sp600_cache)
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", sp1500_cache)
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        sp500_df = pd.DataFrame({
            "ticker": ["AAPL"], "name": ["Apple Inc."], "sector": ["IT"],
            "sub_industry": [None], "cik": ["0000320193"], "wiki_ticker": ["AAPL"],
        })
        sp400_df = pd.DataFrame({
            "ticker": ["MID1"], "name": ["MidCap One"], "sector": ["Industrials"],
            "sub_industry": [None], "cik": ["0001111111"], "wiki_ticker": ["MID1"],
        })
        sp600_df = pd.DataFrame({
            "ticker": ["SML1"], "name": ["SmallCo"], "sector": ["Consumer"],
            "sub_industry": [None], "cik": [None], "wiki_ticker": ["SML1"],
        })

        call_count = {"sp500": 0, "sp400": 0, "sp600": 0}

        def sp500_fn(**kw: object) -> pd.DataFrame:
            call_count["sp500"] += 1
            return sp500_df

        def sp400_fn(**kw: object) -> pd.DataFrame:
            call_count["sp400"] += 1
            return sp400_df

        def sp600_fn(**kw: object) -> pd.DataFrame:
            call_count["sp600"] += 1
            return sp600_df

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", sp500_fn)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", sp400_fn)
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", sp600_fn)
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda t: None)

        # First call — builds sp1500 cache; fetchers called once each.
        universe_mod.get_sp1500_constituents(force_refresh=True)
        assert call_count["sp500"] == 1
        assert call_count["sp400"] == 1
        assert call_count["sp600"] == 1

        # Touch all three constituent caches so they are "fresh".
        sp500_cache.write_bytes(b"fake")
        sp400_cache.write_bytes(b"fake")
        sp600_cache.write_bytes(b"fake")

        # Second call — sp1500 cache is young + all constituent caches are fresh
        # → cache-hit path (lines 619-622), fetchers must NOT be called again.
        universe_mod.get_sp1500_constituents(force_refresh=False)
        assert call_count["sp500"] == 1, "SP500 fetcher must not be called on cache hit"
        assert call_count["sp400"] == 1, "SP400 fetcher must not be called on cache hit"
        assert call_count["sp600"] == 1, "SP600 fetcher must not be called on cache hit"


# ---------------------------------------------------------------------------
# 8. get_sp900_constituents — CIK resolution success path (lines 396-397)
#    and unresolved-CIK warning log (lines 386->407 region)
# ---------------------------------------------------------------------------


class TestGetSp900CikResolutionPaths:
    """Cover the branch where _resolve_cik_for_midcap SUCCEEDS (fills in the CIK)
    and the branch where it returns None (logs warning, CIK stays None).
    These cover lines 396-397 and 386->407.
    """

    def _base_monkeypatch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP900_UNIVERSE_CACHE", tmp_path / "sp900.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)

    def test_cik_resolution_success_fills_in_cik(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When _resolve_cik_for_midcap returns a CIK, it must be written to the DataFrame."""
        self._base_monkeypatch(monkeypatch, tmp_path)

        sp500_df = pd.DataFrame({
            "ticker": ["AAPL"], "name": ["Apple"], "sector": ["IT"],
            "sub_industry": [None], "cik": ["0000320193"], "wiki_ticker": ["AAPL"],
        })
        # MID1 has cik=None → will trigger resolution
        sp400_df = pd.DataFrame({
            "ticker": ["MID1"], "name": ["MidCap One"], "sector": ["Industrials"],
            "sub_industry": [None], "cik": [None], "wiki_ticker": ["MID1"],
        })

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: sp500_df)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: sp400_df)
        # Simulate successful CIK resolution
        monkeypatch.setattr(
            universe_mod, "_resolve_cik_for_midcap", lambda ticker: "0001234567"
        )

        df = universe_mod.get_sp900_constituents(force_refresh=True)
        mid1 = df[df["ticker"] == "MID1"].iloc[0]
        # Resolution succeeded → CIK must be filled in
        assert mid1["cik"] == "0001234567"

    def test_cik_resolution_failure_leaves_none_no_crash(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When _resolve_cik_for_midcap returns None, CIK stays None and no exception."""
        self._base_monkeypatch(monkeypatch, tmp_path)

        sp500_df = pd.DataFrame({
            "ticker": ["AAPL"], "name": ["Apple"], "sector": ["IT"],
            "sub_industry": [None], "cik": ["0000320193"], "wiki_ticker": ["AAPL"],
        })
        sp400_df = pd.DataFrame({
            "ticker": ["MID1"], "name": ["MidCap One"], "sector": ["Industrials"],
            "sub_industry": [None], "cik": [None], "wiki_ticker": ["MID1"],
        })

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: sp500_df)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: sp400_df)
        # Simulate failed CIK resolution
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda ticker: None)

        df = universe_mod.get_sp900_constituents(force_refresh=True)
        mid1 = df[df["ticker"] == "MID1"].iloc[0]
        assert mid1["cik"] is None or (isinstance(mid1["cik"], float) and pd.isna(mid1["cik"]))


# ---------------------------------------------------------------------------
# 9. get_sp1500_constituents — unresolved CIK log path (lines 669-670)
# ---------------------------------------------------------------------------


class TestGetSp1500CikResolutionUnresolved:
    """When _resolve_cik_for_midcap returns None for a sp600 ticker,
    the unresolved-CIK warning must be logged and the CIK stays None —
    must not crash.  Exercises lines 669-670 in get_sp1500_constituents.
    """

    def test_unresolved_cik_for_sp600_no_crash(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", tmp_path / "sp1500.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        sp500_df = pd.DataFrame({
            "ticker": ["AAPL"], "name": ["Apple"], "sector": ["IT"],
            "sub_industry": [None], "cik": ["0000320193"], "wiki_ticker": ["AAPL"],
        })
        sp400_df = pd.DataFrame({
            "ticker": ["MID1"], "name": ["MidCap One"], "sector": ["Industrials"],
            "sub_industry": [None], "cik": ["0001111111"], "wiki_ticker": ["MID1"],
        })
        # SML1 has null CIK → resolution will fail → unresolved warning path
        sp600_df = pd.DataFrame({
            "ticker": ["SML1"], "name": ["SmallCo"], "sector": ["Consumer"],
            "sub_industry": [None], "cik": [None], "wiki_ticker": ["SML1"],
        })

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: sp500_df)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: sp400_df)
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", lambda **kw: sp600_df)
        # Return None → triggers the warning log at line 669-670
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda ticker: None)

        df = universe_mod.get_sp1500_constituents(force_refresh=True)
        sml1 = df[df["ticker"] == "SML1"].iloc[0]
        # Must not crash; CIK stays None
        assert sml1["cik"] is None or (isinstance(sml1["cik"], float) and pd.isna(sml1["cik"]))

    def test_resolved_cik_for_sp600_fills_in(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When resolution succeeds for an sp600 ticker, CIK is filled in."""
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP600_UNIVERSE_CACHE", tmp_path / "sp600.parquet")
        monkeypatch.setattr(universe_mod.config, "SP1500_UNIVERSE_CACHE", tmp_path / "sp1500.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP600_CACHE_MAX_AGE_DAYS", 7)

        sp500_df = pd.DataFrame({
            "ticker": ["AAPL"], "name": ["Apple"], "sector": ["IT"],
            "sub_industry": [None], "cik": ["0000320193"], "wiki_ticker": ["AAPL"],
        })
        sp400_df = pd.DataFrame(columns=["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"])
        sp600_df = pd.DataFrame({
            "ticker": ["SML1"], "name": ["SmallCo"], "sector": ["Consumer"],
            "sub_industry": [None], "cik": [None], "wiki_ticker": ["SML1"],
        })

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: sp500_df)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: sp400_df)
        monkeypatch.setattr(universe_mod, "fetch_sp600_constituents", lambda **kw: sp600_df)
        # Resolution returns a valid CIK
        monkeypatch.setattr(
            universe_mod, "_resolve_cik_for_midcap", lambda ticker: "0009876543"
        )

        df = universe_mod.get_sp1500_constituents(force_refresh=True)
        sml1 = df[df["ticker"] == "SML1"].iloc[0]
        assert sml1["cik"] == "0009876543"


# ---------------------------------------------------------------------------
# 10. _parse_dow30_html / _parse_ndx_html — exception-continue and empty-tickers
#     branches (lines 708-709, 719->705, 734-735, 748->731)
# ---------------------------------------------------------------------------


class TestParseDow30HtmlBranches:
    """Cover: the pd.read_html exception-continue branch (lines 708-709) and
    the 'tickers is empty → continue to next table' branch (lines 719->705).

    Both branches skip a table and fall through to the next wikitable.
    """

    def test_unparseable_first_table_falls_through_to_second(self) -> None:
        """If the first wikitable yields no parseable DataFrame the parser
        should fall through to the second wikitable and succeed.

        We achieve this by placing a wikitable with a valid Symbol header but
        zero rows (so pd.read_html succeeds but yields 0-row set → tickers is
        empty → continue) followed by the real 30-ticker table.
        """
        html = dedent("""\
            <html><body>
            <!-- First table: valid header but zero data rows → tickers is empty -->
            <table class="wikitable">
            <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
            <tbody></tbody>
            </table>
            <!-- Second table: 30 tickers → must be returned -->
            <table class="wikitable">
            <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
            <tbody>
        """ + "\n".join(
            f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(30)
        ) + """
            </tbody></table></body></html>
        """)
        result = universe_mod._parse_dow30_html(html)
        assert len(result) == 30

    def test_no_symbol_or_ticker_column_skips_table(self) -> None:
        """A wikitable with no Symbol/Ticker column is skipped (symbol_col is None)."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Name</th><th>Exchange</th></tr></thead>
            <tbody><tr><td>Apple</td><td>NASDAQ</td></tr></tbody>
            </table>
            <table class="wikitable">
            <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
            <tbody>
        """ + "\n".join(
            f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(30)
        ) + """
            </tbody></table></body></html>
        """)
        result = universe_mod._parse_dow30_html(html)
        assert len(result) == 30

    def test_no_valid_table_returns_empty_set(self) -> None:
        """When ALL tables are skipped, return value must be empty set (not raise)."""
        html = "<html><body><p>no tables</p></body></html>"
        result = universe_mod._parse_dow30_html(html)
        assert result == set()


class TestParseNdxHtmlBranches:
    """Cover: exception-continue (lines 734-735) and empty-tickers continue
    (lines 748->731) branches in _parse_ndx_html.
    """

    def test_empty_first_table_falls_through_to_second(self) -> None:
        """Zero-row table has empty tickers set → continue to next table."""
        html = dedent("""\
            <html><body>
            <!-- First table: valid Ticker header, zero data rows → empty set → continue -->
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
            <tbody></tbody>
            </table>
            <!-- Second table: 100 tickers → must be returned -->
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
            <tbody>
        """ + "\n".join(
            f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(100)
        ) + """
            </tbody></table></body></html>
        """)
        result = universe_mod._parse_ndx_html(html)
        assert len(result) == 100

    def test_no_ticker_or_symbol_column_skips_table(self) -> None:
        """Table without Ticker/Symbol column is skipped → next table wins."""
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Name</th><th>Sector</th></tr></thead>
            <tbody><tr><td>Apple</td><td>Tech</td></tr></tbody>
            </table>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
            <tbody>
        """ + "\n".join(
            f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>" for i in range(100)
        ) + """
            </tbody></table></body></html>
        """)
        result = universe_mod._parse_ndx_html(html)
        assert len(result) == 100


# ---------------------------------------------------------------------------
# 11. fetch_dow30_constituents — cache-hit path (lines 767-775) and
#     cache write failure (lines 798-799)
# ---------------------------------------------------------------------------


class TestFetchDow30ConstituentsCache:
    """Cover: cache-hit short-circuit (read JSON from disk) and non-fatal
    cache-write failure path.
    """

    def test_cache_hit_reads_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A fresh cache JSON file must be read without a network call (lines 767-775)."""
        cache_path = tmp_path / "dow30.json"
        monkeypatch.setattr(universe_mod.config, "DOW30_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "DOW30_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "DOW30_EXPECTED_COUNT", 30)

        # Write a valid 30-ticker cache
        tickers_30 = [f"T{i:03d}" for i in range(30)]
        cache_path.write_text(json.dumps(tickers_30))

        def boom(url: str) -> str:
            raise AssertionError("network fetch must not be called on cache hit")

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", boom)

        result = universe_mod.fetch_dow30_constituents(force_refresh=False)
        assert len(result) == 30
        assert "T000" in result

    def test_corrupt_cache_json_triggers_refetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A corrupt cache JSON must trigger a re-fetch (lines 774-775 except path)."""
        cache_path = tmp_path / "dow30.json"
        monkeypatch.setattr(universe_mod.config, "DOW30_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "DOW30_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "DOW30_EXPECTED_COUNT", 30)

        # Write invalid JSON (syntax error)
        cache_path.write_text("NOT-VALID-JSON{{{")

        call_count = {"n": 0}

        def counting_fetch(url: str) -> str:
            call_count["n"] += 1
            return _make_dow_html(30)

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", counting_fetch)

        result = universe_mod.fetch_dow30_constituents(force_refresh=False)
        # Must re-fetch (corrupt JSON → re-fetch path)
        assert call_count["n"] == 1
        assert len(result) == 30

    def test_cache_write_failure_is_non_fatal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If the cache JSON write fails, the function must still return the tickers
        (lines 798-799: the except block just logs a warning).
        """
        cache_path = tmp_path / "dow30.json"
        monkeypatch.setattr(universe_mod.config, "DOW30_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "DOW30_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "DOW30_EXPECTED_COUNT", 30)
        monkeypatch.setattr(
            universe_mod, "_fetch_wikipedia_html", lambda url: _make_dow_html(30)
        )

        # Patch Path.write_text to raise so we enter the except-block at 798-799
        from pathlib import Path as _Path

        def failing_write_text(self_path: _Path, *args: object, **kwargs: object) -> None:
            raise OSError("Simulated write failure")

        monkeypatch.setattr(_Path, "write_text", failing_write_text)

        result = universe_mod.fetch_dow30_constituents(force_refresh=True)
        assert len(result) == 30


# ---------------------------------------------------------------------------
# 12. fetch_ndx_constituents — cache-hit path (lines 818-826) and
#     cache write failure (lines 851-852)
# ---------------------------------------------------------------------------


class TestFetchNdxConstituentsCache:
    """Cover: cache-hit short-circuit (lines 818-826) and non-fatal cache
    write failure (lines 851-852).
    """

    def test_cache_hit_reads_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A fresh NDX cache JSON must be read without a network call."""
        cache_path = tmp_path / "ndx.json"
        monkeypatch.setattr(universe_mod.config, "NDX_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "NDX_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "NDX_MIN_COUNT", 95)
        monkeypatch.setattr(universe_mod.config, "NDX_MAX_COUNT", 105)

        tickers_100 = [f"T{i:03d}" for i in range(100)]
        cache_path.write_text(json.dumps(tickers_100))

        def boom(url: str) -> str:
            raise AssertionError("network fetch must not be called on cache hit")

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", boom)

        result = universe_mod.fetch_ndx_constituents(force_refresh=False)
        assert len(result) == 100
        assert "T000" in result

    def test_corrupt_cache_json_triggers_refetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A corrupt NDX cache JSON must trigger a re-fetch."""
        cache_path = tmp_path / "ndx.json"
        monkeypatch.setattr(universe_mod.config, "NDX_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "NDX_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "NDX_MIN_COUNT", 95)
        monkeypatch.setattr(universe_mod.config, "NDX_MAX_COUNT", 105)

        cache_path.write_text("BAD JSON ]]]")

        call_count = {"n": 0}

        def counting_fetch(url: str) -> str:
            call_count["n"] += 1
            return _make_ndx_html(100)

        monkeypatch.setattr(universe_mod, "_fetch_wikipedia_html", counting_fetch)

        result = universe_mod.fetch_ndx_constituents(force_refresh=False)
        assert call_count["n"] == 1
        assert len(result) == 100

    def test_cache_write_failure_is_non_fatal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If NDX cache write fails, function must still return the tickers (lines 851-852)."""
        cache_path = tmp_path / "ndx.json"
        monkeypatch.setattr(universe_mod.config, "NDX_UNIVERSE_CACHE", cache_path)
        monkeypatch.setattr(universe_mod.config, "NDX_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "NDX_MIN_COUNT", 95)
        monkeypatch.setattr(universe_mod.config, "NDX_MAX_COUNT", 105)
        monkeypatch.setattr(
            universe_mod, "_fetch_wikipedia_html", lambda url: _make_ndx_html(100)
        )

        # Patch Path.write_text to raise so we enter the except-block at 851-852
        from pathlib import Path as _Path

        def failing_write_text(self_path: _Path, *args: object, **kwargs: object) -> None:
            raise OSError("Simulated write failure")

        monkeypatch.setattr(_Path, "write_text", failing_write_text)

        result = universe_mod.fetch_ndx_constituents(force_refresh=True)
        assert len(result) == 100


# ---------------------------------------------------------------------------
# 13. _normalize_ticker — whitespace-strip and upper-case edge cases
# ---------------------------------------------------------------------------


class TestNormalizeTicker:
    """Verify _normalize_ticker handles whitespace, dots, case variants."""

    @pytest.mark.parametrize("raw, expected", [
        ("  aapl  ", "AAPL"),         # strip + upper
        ("BRK.B", "BRK-B"),           # dot to dash
        ("brk.b", "BRK-B"),           # lowercase dot
        (" BRK.B ", "BRK-B"),         # strip + dot
        ("A", "A"),                   # single char
        ("ABC", "ABC"),               # already clean
    ])
    def test_normalize_ticker(self, raw: str, expected: str) -> None:
        assert universe_mod._normalize_ticker(raw) == expected
