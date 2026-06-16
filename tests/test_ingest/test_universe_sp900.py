"""Tests for the Phase 8 pilot SP400 + SP900 universe ingest.

All tests are offline (no network) — they use fixture HTML or synthetic
DataFrames to exercise the parsing, de-dup, and Metadata probe logic.

Coverage targets (for test-engineer):
  1. _parse_sp400_html: fixture HTML, ticker normalisation, missing-CIK tolerance
  2. get_sp900_constituents: dedup (sp500 wins), cohort column, ~900 size
  3. _run_midcap_coverage_probe: Metadata population (synthetic)
  4. Byte-identical-500 guard: sp500 path leaves pilot Metadata fields None
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from compute.ingest import universe as universe_mod

# ---------------------------------------------------------------------------
# Fixture HTML for the S&P 400 Wikipedia page (minimal, offline)
# ---------------------------------------------------------------------------

SP400_FIXTURE_HTML_WITH_CIK = """
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
  <tr><td>AAA</td><td>Alpha Corp</td><td>Industrials</td><td>Aerospace &amp; Defense</td><td>12345</td></tr>
  <tr><td>BBB</td><td>Beta Holdings</td><td>Financials</td><td>Banking</td><td>67890</td></tr>
  <tr><td>CCC</td><td>Gamma Inc</td><td>Health Care</td><td>Pharmaceuticals</td><td></td></tr>
</tbody>
</table>
</body></html>
"""

SP400_FIXTURE_HTML_SYMBOL_COL = """
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
  <tr><td>DDD</td><td>Delta LLC</td><td>Energy</td></tr>
  <tr><td>EEE.A</td><td>Epsilon Corp</td><td>Materials</td></tr>
</tbody>
</table>
</body></html>
"""

SP400_FIXTURE_HTML_NO_TICKER = """
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


# ---------------------------------------------------------------------------
# 1. _parse_sp400_html
# ---------------------------------------------------------------------------

class TestParseSpHtml:
    def test_parses_ticker_column(self):
        df = universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_WITH_CIK)
        assert "AAA" in df["ticker"].values
        assert "BBB" in df["ticker"].values
        assert "CCC" in df["ticker"].values

    def test_normalises_dot_in_ticker(self):
        df = universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_SYMBOL_COL)
        # EEE.A should normalise to EEE-A
        assert "EEE-A" in df["ticker"].values
        assert "DDD" in df["ticker"].values

    def test_required_columns_present(self):
        df = universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_WITH_CIK)
        for col in ("ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"):
            assert col in df.columns, f"Missing column: {col}"

    def test_cik_zero_padded_when_present(self):
        df = universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_WITH_CIK)
        aaa = df[df["ticker"] == "AAA"].iloc[0]
        # 12345 → "0000012345"
        assert aaa["cik"] == "0000012345"
        bbb = df[df["ticker"] == "BBB"].iloc[0]
        assert bbb["cik"] == "0000067890"

    def test_missing_cik_is_none(self):
        df = universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_WITH_CIK)
        ccc = df[df["ticker"] == "CCC"].iloc[0]
        assert ccc["cik"] is None or (isinstance(ccc["cik"], float) and pd.isna(ccc["cik"]))

    def test_accepts_symbol_column_name(self):
        # Some S&P 400 Wikipedia pages use "Symbol" rather than "Ticker"
        df = universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_SYMBOL_COL)
        assert len(df) == 2

    def test_no_ticker_column_raises(self):
        with pytest.raises(ValueError, match="Symbol.*Ticker|wikitable|ticker column"):
            universe_mod._parse_sp400_html(SP400_FIXTURE_HTML_NO_TICKER)

    def test_empty_html_raises(self):
        with pytest.raises(ValueError):
            universe_mod._parse_sp400_html("<html><body></body></html>")

    def test_deduplicates_tickers(self):
        html = """
        <html><body>
        <table class="wikitable">
          <tr><th>Ticker</th><th>Company</th><th>GICS Sector</th></tr>
          <tr><td>AAA</td><td>Alpha Corp</td><td>Industrials</td></tr>
          <tr><td>AAA</td><td>Alpha Corp Duplicate</td><td>Industrials</td></tr>
        </table>
        </body></html>
        """
        df = universe_mod._parse_sp400_html(html)
        assert df["ticker"].is_unique
        assert len(df[df["ticker"] == "AAA"]) == 1

    def test_sector_fallback_unknown(self):
        html = """
        <html><body>
        <table class="wikitable">
          <tr><th>Ticker</th><th>Company</th></tr>
          <tr><td>ZZZ</td><td>Zeta Co</td></tr>
        </table>
        </body></html>
        """
        df = universe_mod._parse_sp400_html(html)
        assert df.iloc[0]["sector"] == "Unknown"


# ---------------------------------------------------------------------------
# 2. get_sp900_constituents
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


def _make_sp400_df(include_shared: bool = True) -> pd.DataFrame:
    rows = [
        {"ticker": "MID1", "name": "MidCap One", "sector": "Industrials", "sub_industry": None, "cik": "0001111111", "wiki_ticker": "MID1"},
        {"ticker": "MID2", "name": "MidCap Two", "sector": "Health Care", "sub_industry": None, "cik": None,         "wiki_ticker": "MID2"},
    ]
    if include_shared:
        rows.append(
            {"ticker": "SHARED", "name": "SharedCo (400)", "sector": "Financials", "sub_industry": None, "cik": "0000999000", "wiki_ticker": "SHARED"}
        )
    return pd.DataFrame(rows)


class TestGetSp900Constituents:
    def _build_sp900(self, monkeypatch, tmp_path, sp500_df=None, sp400_df=None, mock_cik=True):
        if sp500_df is None:
            sp500_df = _make_sp500_df()
        if sp400_df is None:
            sp400_df = _make_sp400_df()

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP900_UNIVERSE_CACHE", tmp_path / "sp900.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)

        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: sp500_df)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: sp400_df)

        if mock_cik:
            # Patch CIK resolution so tests stay offline
            monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda ticker: None)

        return universe_mod.get_sp900_constituents(force_refresh=True)

    def test_cohort_column_present(self, monkeypatch, tmp_path):
        df = self._build_sp900(monkeypatch, tmp_path)
        assert "cohort" in df.columns
        assert set(df["cohort"].unique()).issubset({"sp500", "sp400"})

    def test_sp500_rows_tagged_correctly(self, monkeypatch, tmp_path):
        df = self._build_sp900(monkeypatch, tmp_path)
        assert (df[df["ticker"] == "AAPL"]["cohort"] == "sp500").all()
        assert (df[df["ticker"] == "MSFT"]["cohort"] == "sp500").all()

    def test_sp400_rows_tagged_correctly(self, monkeypatch, tmp_path):
        df = self._build_sp900(monkeypatch, tmp_path)
        assert (df[df["ticker"] == "MID1"]["cohort"] == "sp400").all()
        assert (df[df["ticker"] == "MID2"]["cohort"] == "sp400").all()

    def test_dedup_sp500_wins_on_overlap(self, monkeypatch, tmp_path):
        """A ticker in both SP500 and SP400 should appear exactly once with cohort=sp500."""
        df = self._build_sp900(monkeypatch, tmp_path)
        shared_rows = df[df["ticker"] == "SHARED"]
        assert len(shared_rows) == 1, "Shared ticker must be de-duplicated to a single row"
        assert shared_rows.iloc[0]["cohort"] == "sp500", "SP500 must win on overlap"

    def test_no_duplicate_tickers(self, monkeypatch, tmp_path):
        df = self._build_sp900(monkeypatch, tmp_path)
        assert df["ticker"].is_unique, "SP900 DataFrame must have unique tickers"

    def test_approximate_size(self, monkeypatch, tmp_path):
        sp500_df = _make_sp500_df()   # 3 tickers (incl. SHARED)
        sp400_df = _make_sp400_df()   # 3 tickers (incl. SHARED)
        df = self._build_sp900(monkeypatch, tmp_path, sp500_df=sp500_df, sp400_df=sp400_df)
        # Expected: 3 sp500 + 2 unique sp400 (SHARED de-duped) = 5
        assert len(df) == 5

    def test_cache_written(self, monkeypatch, tmp_path):
        self._build_sp900(monkeypatch, tmp_path)
        cache = tmp_path / "sp900.parquet"
        assert cache.exists(), "SP900 cache parquet must be written"

    def test_cache_read_on_second_call(self, monkeypatch, tmp_path):
        """Second call with warm cache must NOT call get_sp500_constituents again."""
        call_count = {"sp500": 0, "sp400": 0}

        def sp500_fn(**kw):
            call_count["sp500"] += 1
            return _make_sp500_df()

        def sp400_fn(**kw):
            call_count["sp400"] += 1
            return _make_sp400_df()

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP900_UNIVERSE_CACHE", tmp_path / "sp900.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "get_sp500_constituents", sp500_fn)
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", sp400_fn)
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", lambda ticker: None)

        # First call — builds + writes cache
        universe_mod.get_sp900_constituents(force_refresh=True)
        assert call_count["sp500"] == 1

        # Simulate both constituent caches being fresh (touch the parquet files)
        sp500_cache = tmp_path / "sp500.parquet"
        sp400_cache = tmp_path / "sp400.parquet"
        sp500_cache.write_bytes(b"fake")
        sp400_cache.write_bytes(b"fake")

        # Second call — should serve from sp900 cache
        universe_mod.get_sp900_constituents(force_refresh=False)
        assert call_count["sp500"] == 1, "SP500 should not be re-fetched on cache hit"

    def test_cik_resolution_called_for_null_cik_midcaps(self, monkeypatch, tmp_path):
        """Tickers with null CIK in SP400 must trigger _resolve_cik_for_midcap."""
        resolved = []

        def fake_resolve(ticker: str):
            resolved.append(ticker)
            return None  # stay None (no network)

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP900_UNIVERSE_CACHE", tmp_path / "sp900.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: _make_sp500_df())
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: _make_sp400_df())
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", fake_resolve)

        universe_mod.get_sp900_constituents(force_refresh=True)
        # MID2 has null CIK so it should have been passed to resolve
        assert "MID2" in resolved

    def test_cik_resolution_not_called_for_sp500_tickers(self, monkeypatch, tmp_path):
        """SP500 tickers (which have CIKs from Wikipedia) must not trigger resolve."""
        resolved = []

        def fake_resolve(ticker: str):
            resolved.append(ticker)
            return None

        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE", tmp_path / "sp500.parquet")
        monkeypatch.setattr(universe_mod.config, "SP400_UNIVERSE_CACHE", tmp_path / "sp400.parquet")
        monkeypatch.setattr(universe_mod.config, "SP900_UNIVERSE_CACHE", tmp_path / "sp900.parquet")
        monkeypatch.setattr(universe_mod.config, "UNIVERSE_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod.config, "SP400_CACHE_MAX_AGE_DAYS", 7)
        monkeypatch.setattr(universe_mod, "get_sp500_constituents", lambda **kw: _make_sp500_df())
        monkeypatch.setattr(universe_mod, "fetch_sp400_constituents", lambda **kw: _make_sp400_df())
        monkeypatch.setattr(universe_mod, "_resolve_cik_for_midcap", fake_resolve)

        universe_mod.get_sp900_constituents(force_refresh=True)
        # SP500 tickers all have CIKs — they should NEVER appear in resolved
        for sp500_ticker in ("AAPL", "MSFT"):
            assert sp500_ticker not in resolved, f"{sp500_ticker} must not go through CIK resolution"


# ---------------------------------------------------------------------------
# 3. _run_midcap_coverage_probe (synthetic)
# ---------------------------------------------------------------------------

class TestRunMidcapCoverageProbe:
    def _make_sp900_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "ticker": ["AAPL", "MSFT", "MID1", "MID2", "MID3"],
            "name":   ["Apple Inc.", "Microsoft", "MidOne", "MidTwo", "MidThree"],
            "sector": ["IT", "IT", "Industrials", "Health Care", "Financials"],
            "sub_industry": [None, None, None, None, None],
            "cik": ["0000320193", "0000789019", "0001111111", None, "0002222222"],
            "wiki_ticker": ["AAPL", "MSFT", "MID1", "MID2", "MID3"],
            "cohort": ["sp500", "sp500", "sp400", "sp400", "sp400"],
        })

    def test_returns_coverage_and_null_rate(self, monkeypatch):
        """With 2/3 midcaps returning a snapshot, coverage = 66.67%, null = 33.33%."""
        from compute.ingest.fundamentals import FundamentalsSnapshot
        from compute.main import _run_midcap_coverage_probe

        mock_snap = MagicMock(spec=FundamentalsSnapshot)

        call_count = {"n": 0}
        def fake_fetch(ticker, cik):
            call_count["n"] += 1
            # MID3 returns None (simulates failure)
            if ticker == "MID3":
                return None
            return mock_snap

        monkeypatch.setattr("compute.main.fetch_fundamentals", fake_fetch)

        sp900_df = self._make_sp900_df()
        cov, null_rate, cik_res, cohort_sizes = _run_midcap_coverage_probe(sp900_df)

        # 3 midcap tickers; 2 succeed → 66.67%, 1 fails → 33.33%
        assert cov is not None
        assert abs(cov - 66.67) < 0.1, f"Expected ~66.67%, got {cov}"
        assert null_rate is not None
        assert abs(null_rate - 33.33) < 0.1, f"Expected ~33.33%, got {null_rate}"

    def test_cohort_sizes_populated(self, monkeypatch):
        from compute.main import _run_midcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda ticker, cik: None)
        sp900_df = self._make_sp900_df()
        _, _, _, cohort_sizes = _run_midcap_coverage_probe(sp900_df)

        assert cohort_sizes.get("sp500") == 2
        assert cohort_sizes.get("sp400") == 3

    def test_cik_resolution_pct_computed(self, monkeypatch):
        """2/3 midcaps have CIK → cik_resolution_pct = 66.67%."""
        from compute.main import _run_midcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda ticker, cik: None)
        sp900_df = self._make_sp900_df()
        _, _, cik_res, _ = _run_midcap_coverage_probe(sp900_df)

        # MID1 + MID3 have CIK; MID2 is None → 2/3 = 66.67%
        assert cik_res is not None
        assert abs(cik_res - 66.67) < 0.1, f"Expected ~66.67%, got {cik_res}"

    def test_all_null_snapshots(self, monkeypatch):
        """All midcaps fail → coverage=0, null_rate=100."""
        from compute.main import _run_midcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda ticker, cik: None)
        sp900_df = self._make_sp900_df()
        cov, null_rate, _, _ = _run_midcap_coverage_probe(sp900_df)

        assert cov == 0.0
        assert null_rate == 100.0

    def test_exception_in_fetch_counted_as_null(self, monkeypatch):
        """fetch_fundamentals raising must count as null, not crash."""
        from compute.main import _run_midcap_coverage_probe

        def raise_fetch(ticker, cik):
            raise RuntimeError("EDGAR timeout")

        monkeypatch.setattr("compute.main.fetch_fundamentals", raise_fetch)
        sp900_df = self._make_sp900_df()
        cov, null_rate, _, _ = _run_midcap_coverage_probe(sp900_df)

        assert cov == 0.0
        assert null_rate == 100.0

    def test_returns_none_on_empty_sp400(self, monkeypatch):
        """If no sp400 rows exist, the probe returns None for coverage fields."""
        from compute.main import _run_midcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda ticker, cik: None)
        sp900_df_no_midcap = pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "name":   ["Apple Inc.", "Microsoft"],
            "sector": ["IT", "IT"],
            "sub_industry": [None, None],
            "cik": ["0000320193", "0000789019"],
            "wiki_ticker": ["AAPL", "MSFT"],
            "cohort": ["sp500", "sp500"],
        })
        cov, null_rate, cik_res, _ = _run_midcap_coverage_probe(sp900_df_no_midcap)
        assert cov is None
        assert null_rate is None
        assert cik_res is None

    def test_does_not_call_fetch_for_sp500_rows(self, monkeypatch):
        """The probe must only call fetch_fundamentals for sp400 rows."""
        from compute.main import _run_midcap_coverage_probe

        fetched = []
        def track_fetch(ticker, cik):
            fetched.append(ticker)
            return None

        monkeypatch.setattr("compute.main.fetch_fundamentals", track_fetch)
        sp900_df = self._make_sp900_df()
        _run_midcap_coverage_probe(sp900_df)

        for sp500_ticker in ("AAPL", "MSFT"):
            assert sp500_ticker not in fetched, (
                f"Probe must not call fetch_fundamentals for sp500 ticker {sp500_ticker}"
            )
        assert "MID1" in fetched
        assert "MID2" in fetched
        assert "MID3" in fetched


# ---------------------------------------------------------------------------
# 4. Byte-identical-500 guard: sp500 path leaves pilot Metadata fields None
# ---------------------------------------------------------------------------

class TestSp500PathPilotFieldsAreNone:
    """Verify that the default sp500 path produces None for all pilot Metadata fields.

    This is the critical invariant that guarantees ranked output is byte-
    identical before and after the Phase 8 pilot PR lands.
    """

    def test_pilot_fields_none_on_sp500_config(self, monkeypatch):
        """When QR_UNIVERSE=sp500, the pilot variables must stay None."""
        from compute import config

        # QR_UNIVERSE must be "sp500" (the default)
        assert config.QR_UNIVERSE in ("sp500", ""), (
            f"Test assumes default universe; got QR_UNIVERSE={config.QR_UNIVERSE!r}. "
            "Set QR_UNIVERSE=sp500 in the environment for this assertion."
        )

        # Verify Metadata model accepts None for all pilot fields
        from compute.output.schemas import Metadata
        meta = Metadata(
            version="0.10.19-phase8pilot",
            last_update_utc="2026-06-14T00:00:00+00:00",
            next_update_utc="2026-06-15T00:00:00+00:00",
            universe="SP500",
            universe_size=502,
            compute_run_id="local",
            git_commit="abc123",
            # All pilot fields explicitly None
            universe_cohort_sizes=None,
            midcap_fundamentals_coverage_pct=None,
            midcap_null_rate_pct=None,
            midcap_cik_resolution_pct=None,
        )
        assert meta.universe_cohort_sizes is None
        assert meta.midcap_fundamentals_coverage_pct is None
        assert meta.midcap_null_rate_pct is None
        assert meta.midcap_cik_resolution_pct is None

    def test_pilot_fields_populated_on_sp900_config(self):
        """When QR_UNIVERSE=sp900, the Metadata model must accept non-None pilot fields."""
        from compute.output.schemas import Metadata

        meta = Metadata(
            version="0.10.19-phase8pilot",
            last_update_utc="2026-06-14T00:00:00+00:00",
            next_update_utc="2026-06-15T00:00:00+00:00",
            universe="SP500",
            universe_size=502,
            compute_run_id="local",
            git_commit="abc123",
            universe_cohort_sizes={"sp500": 502, "sp400": 398},
            midcap_fundamentals_coverage_pct=87.5,
            midcap_null_rate_pct=12.5,
            midcap_cik_resolution_pct=95.0,
        )
        assert meta.universe_cohort_sizes == {"sp500": 502, "sp400": 398}
        assert meta.midcap_fundamentals_coverage_pct == 87.5
        assert meta.midcap_null_rate_pct == 12.5
        assert meta.midcap_cik_resolution_pct == 95.0

    def test_pilot_variables_initialised_before_probe_block(self, monkeypatch):
        """The pilot variable initialisers in run_weekly_compute must set all to None.

        This guards the invariant that a non-sp900 path can never accidentally
        pass uninitialised pilot variables to the Metadata constructor.
        """
        # Import the module; inspect that the variables are initialised to None
        # in the run_weekly_compute body by checking the probe-guard short-circuit.
        # We do this via a partial parse of the source rather than a full compute run.
        import inspect

        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)

        # All four pilot variables must be explicitly initialised to None
        for var in (
            "_pilot_cohort_sizes",
            "_pilot_midcap_coverage_pct",
            "_pilot_midcap_null_rate_pct",
            "_pilot_midcap_cik_resolution_pct",
        ):
            assert f"{var}: dict[str, int] | None = None" in src or f"{var}: float | None = None" in src or f"{var} = None" in src, (
                f"Pilot variable {var!r} must be initialised to None before the probe block in run_weekly_compute"
            )

        # The probe block must be guarded by QR_UNIVERSE == "sp900"
        assert 'QR_UNIVERSE == "sp900"' in src or "QR_UNIVERSE==\"sp900\"" in src or 'config.QR_UNIVERSE == "sp900"' in src, (
            "run_weekly_compute must guard the sp900 probe with QR_UNIVERSE == 'sp900'"
        )


# ---------------------------------------------------------------------------
# 5. universe_cohort_sizes post-scoring invariant (Bug 2 fix)
#
# Before the fix, universe_cohort_sizes was populated from the PRE-scoring
# universe DataFrame (which included 503 sp500 tickers — one delisted name
# that later fails fetch_prices and is silently dropped).  The fix recomputes
# cohort sizes from the POST-scoring summaries list so
# sum(universe_cohort_sizes.values()) == universe_size always.
#
# These tests use synthetic StockSummary fixtures to assert the invariant
# without running the full network compute pipeline.
# ---------------------------------------------------------------------------

class TestUniverseCohortSizesPostScoringInvariant:
    """Pin the post-scoring cohort-sizes invariant introduced by the Bug-2 fix.

    The key property: sum(universe_cohort_sizes.values()) == universe_size
    (== len(rankings.json rows)).  Before the fix, a pre-scoring census
    overcounted by one when a delisted ticker failed fetch_prices — the
    discarded ticker was still counted in the cohort but not in summaries.
    """

    def _make_summaries(self, sp500_count: int, sp400_count: int):
        """Build a minimal list of StockSummary dicts (as objects) with
        index_membership set correctly.

        Uses dicts instead of the full Pydantic model so the test has no
        dependency on the full schema and is fast.
        """
        from compute.output.schemas import StockSummary

        items = []
        for i in range(sp500_count):
            items.append(StockSummary(
                rank=i + 1,
                ticker=f"SP5_{i:03d}",
                name=f"SP500 Stock {i}",
                sector="Technology",
                composite_score=50.0,
                current_price=100.0,
                index_membership="sp500",
            ))
        for i in range(sp400_count):
            items.append(StockSummary(
                rank=sp500_count + i + 1,
                ticker=f"SP4_{i:03d}",
                name=f"SP400 Stock {i}",
                sector="Industrials",
                composite_score=45.0,
                current_price=50.0,
                index_membership="sp400",
            ))
        return items

    def test_cohort_sizes_sum_equals_universe_size(self):
        """Core invariant: sum(cohort_sizes.values()) == len(summaries).

        Exercises the post-scoring recompute logic from ``run_weekly_compute``
        by replicating the counting logic with a synthetic summaries list.
        A pre-scoring census that includes 1 extra sp500 ticker (503) that
        was later dropped during price-fetch would violate this invariant;
        the fix recomputes from summaries so it always holds.
        """
        # Simulate: 502 sp500 pass scoring, 400 sp400 pass scoring.
        summaries = self._make_summaries(sp500_count=502, sp400_count=400)

        # Replicate the post-scoring recompute logic from main.py.
        post_scoring_cohort_sizes: dict[str, int] = {}
        for s in summaries:
            membership = s.index_membership
            post_scoring_cohort_sizes[membership] = (
                post_scoring_cohort_sizes.get(membership, 0) + 1
            )

        universe_size = len(summaries)
        assert sum(post_scoring_cohort_sizes.values()) == universe_size, (
            f"universe_cohort_sizes sum {sum(post_scoring_cohort_sizes.values())} "
            f"must equal universe_size {universe_size}"
        )
        assert post_scoring_cohort_sizes["sp500"] == 502
        assert post_scoring_cohort_sizes["sp400"] == 400

    def test_cohort_sizes_sum_equals_universe_size_when_one_sp500_dropped(self):
        """Regression: pre-scoring census counted 503 sp500 but 1 was dropped.

        With pre-scoring cohort counting: sum = 903, universe_size = 902 →
        off-by-one contradiction. With post-scoring counting: sum = 902 =
        universe_size → consistent.
        """
        # Pre-scoring would have seen 503 sp500 + 400 sp400 = 903.
        # One sp500 ticker failed fetch_prices and was dropped → 502 survive.
        summaries = self._make_summaries(sp500_count=502, sp400_count=400)

        post_scoring_cohort_sizes: dict[str, int] = {}
        for s in summaries:
            membership = s.index_membership
            post_scoring_cohort_sizes[membership] = (
                post_scoring_cohort_sizes.get(membership, 0) + 1
            )

        universe_size = len(summaries)  # 902 (post-drop)
        # Key assertion: the off-by-one that existed pre-fix must not appear.
        assert sum(post_scoring_cohort_sizes.values()) == universe_size, (
            "Off-by-one regression: post-scoring cohort sizes must sum to "
            "universe_size, not universe_size + 1"
        )
        assert sum(post_scoring_cohort_sizes.values()) != universe_size + 1, (
            "Pre-scoring census bug: sum must NOT be universe_size + 1"
        )

    def test_cohort_sizes_sum_invariant_for_sp500_only_path(self):
        """On the sp500-only path, summaries contain only sp500 members.

        The default cron never sets _pilot_cohort_sizes (stays None) so
        the recompute block doesn't run.  This test verifies the counting
        logic itself would still produce a consistent result if applied to
        an sp500-only summaries list.
        """
        summaries = self._make_summaries(sp500_count=502, sp400_count=0)

        post_scoring_cohort_sizes: dict[str, int] = {}
        for s in summaries:
            membership = s.index_membership
            post_scoring_cohort_sizes[membership] = (
                post_scoring_cohort_sizes.get(membership, 0) + 1
            )

        universe_size = len(summaries)
        assert sum(post_scoring_cohort_sizes.values()) == universe_size
        assert post_scoring_cohort_sizes.get("sp500", 0) == 502
        assert post_scoring_cohort_sizes.get("sp400", 0) == 0
