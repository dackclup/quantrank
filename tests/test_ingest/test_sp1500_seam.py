"""Tests for S&P 1500 cutover Slice 2 — universe seam + smallcap coverage probe.

All tests are offline (no network) — they use synthetic DataFrames to
exercise the sp1500 branch in run_weekly_compute's universe selector and the
``_run_smallcap_coverage_probe`` function.

Coverage targets:
  1. _run_smallcap_coverage_probe: returns (coverage_pct, null_rate_pct,
     cik_resolution_pct, cohort_sizes) with sp500/sp400/sp600 keys.
  2. Empty sp600 cohort → graceful degradation (None coverage fields).
  3. Exception in fetch_fundamentals → counted as null, not crash.
  4. Metadata fields populate under sp1500, are None otherwise.
  5. universe_cohort_sizes carries sp600 key when QR_UNIVERSE=sp1500.
  6. Source-check: _pilot_smallcap_* initialised to None before the probe
     block in run_weekly_compute (guards against uninitialised leakage).
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers — synthetic DataFrames
# ---------------------------------------------------------------------------

def _make_sp1500_df() -> pd.DataFrame:
    """Minimal sp1500 frame: 2 sp500 + 2 sp400 + 3 sp600 tickers."""
    return pd.DataFrame({
        "ticker":       ["AAPL", "MSFT", "MID1", "MID2", "SML1", "SML2", "SML3"],
        "name":         ["Apple", "Microsoft", "MidOne", "MidTwo", "SmlOne", "SmlTwo", "SmlThree"],
        "sector":       ["IT", "IT", "Industrials", "Health Care", "Consumer Disc.", "Financials", "Energy"],
        "sub_industry": [None] * 7,
        "cik":          ["0000320193", "0000789019", "0001111111", None, "0003333333", None, "0004444444"],
        "wiki_ticker":  ["AAPL", "MSFT", "MID1", "MID2", "SML1", "SML2", "SML3"],
        "cohort":       ["sp500", "sp500", "sp400", "sp400", "sp600", "sp600", "sp600"],
    })


def _make_sp1500_df_no_sp600() -> pd.DataFrame:
    """sp1500 frame with NO sp600 rows (simulates graceful-degradation on empty fetch)."""
    return pd.DataFrame({
        "ticker":       ["AAPL", "MSFT", "MID1"],
        "name":         ["Apple", "Microsoft", "MidOne"],
        "sector":       ["IT", "IT", "Industrials"],
        "sub_industry": [None, None, None],
        "cik":          ["0000320193", "0000789019", "0001111111"],
        "wiki_ticker":  ["AAPL", "MSFT", "MID1"],
        "cohort":       ["sp500", "sp500", "sp400"],
    })


# ---------------------------------------------------------------------------
# 1. _run_smallcap_coverage_probe — core behaviour
# ---------------------------------------------------------------------------

class TestRunSmallcapCoverageProbe:

    def test_returns_coverage_and_null_rate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """2/3 sp600 snapshots succeed → coverage ≈ 66.67%, null ≈ 33.33%."""
        from compute.ingest.fundamentals import FundamentalsSnapshot
        from compute.main import _run_smallcap_coverage_probe

        mock_snap = MagicMock(spec=FundamentalsSnapshot)

        def fake_fetch(ticker: str, cik: str):
            return None if ticker == "SML3" else mock_snap

        monkeypatch.setattr("compute.main.fetch_fundamentals", fake_fetch)

        sp1500_df = _make_sp1500_df()
        cov, null_rate, cik_res, cohort_sizes = _run_smallcap_coverage_probe(sp1500_df)

        assert cov is not None
        assert abs(cov - 66.67) < 0.1, f"Expected ~66.67%, got {cov}"
        assert null_rate is not None
        assert abs(null_rate - 33.33) < 0.1, f"Expected ~33.33%, got {null_rate}"

    def test_cohort_sizes_carries_all_three_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cohort_sizes must include sp500, sp400, and sp600 keys."""
        from compute.main import _run_smallcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        sp1500_df = _make_sp1500_df()
        _, _, _, cohort_sizes = _run_smallcap_coverage_probe(sp1500_df)

        assert cohort_sizes.get("sp500") == 2
        assert cohort_sizes.get("sp400") == 2
        assert cohort_sizes.get("sp600") == 3

    def test_cik_resolution_pct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SML1 + SML3 have CIK; SML2 is None → 2/3 = 66.67%."""
        from compute.main import _run_smallcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        sp1500_df = _make_sp1500_df()
        _, _, cik_res, _ = _run_smallcap_coverage_probe(sp1500_df)

        assert cik_res is not None
        assert abs(cik_res - 66.67) < 0.1, f"Expected ~66.67%, got {cik_res}"

    def test_all_null_snapshots(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All sp600 fetches return None → coverage=0, null_rate=100."""
        from compute.main import _run_smallcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        sp1500_df = _make_sp1500_df()
        cov, null_rate, _, _ = _run_smallcap_coverage_probe(sp1500_df)

        assert cov == 0.0
        assert null_rate == 100.0

    def test_exception_in_fetch_counted_as_null(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch_fundamentals raising must count as null, not crash the probe."""
        from compute.main import _run_smallcap_coverage_probe

        def raise_fetch(ticker: str, cik: str):
            raise RuntimeError("EDGAR timeout")

        monkeypatch.setattr("compute.main.fetch_fundamentals", raise_fetch)
        sp1500_df = _make_sp1500_df()
        cov, null_rate, _, _ = _run_smallcap_coverage_probe(sp1500_df)

        assert cov == 0.0
        assert null_rate == 100.0

    def test_does_not_call_fetch_for_sp500_or_sp400_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The smallcap probe must call fetch_fundamentals ONLY for sp600 rows."""
        from compute.main import _run_smallcap_coverage_probe

        fetched: list[str] = []

        def track_fetch(ticker: str, cik: str):
            fetched.append(ticker)
            return None

        monkeypatch.setattr("compute.main.fetch_fundamentals", track_fetch)
        sp1500_df = _make_sp1500_df()
        _run_smallcap_coverage_probe(sp1500_df)

        for large_mid_ticker in ("AAPL", "MSFT", "MID1", "MID2"):
            assert large_mid_ticker not in fetched, (
                f"Probe must NOT call fetch_fundamentals for non-sp600 ticker {large_mid_ticker}"
            )
        # All sp600 tickers must have been fetched.
        for small_ticker in ("SML1", "SML2", "SML3"):
            assert small_ticker in fetched, f"Probe must call fetch for sp600 ticker {small_ticker}"


# ---------------------------------------------------------------------------
# 2. Graceful degradation — empty sp600 cohort
# ---------------------------------------------------------------------------

class TestSmallcapProbeGracefulDegradation:

    def test_empty_sp600_returns_none_coverage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If no sp600 rows exist (degraded fetcher), probe returns None for coverage fields."""
        from compute.main import _run_smallcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        df_no_sp600 = _make_sp1500_df_no_sp600()
        cov, null_rate, cik_res, cohort_sizes = _run_smallcap_coverage_probe(df_no_sp600)

        assert cov is None
        assert null_rate is None
        assert cik_res is None
        # cohort_sizes should still populate what's there.
        assert cohort_sizes.get("sp500") == 2
        assert cohort_sizes.get("sp400") == 1
        # sp600 key must exist with count 0 (from the loop), or simply absent/0.
        assert cohort_sizes.get("sp600", 0) == 0

    def test_probe_does_not_crash_on_unexpected_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The outer try/except in the probe must prevent any exception from crashing main."""
        from compute.main import _run_smallcap_coverage_probe

        # Corrupt the DataFrame so iterrows raises (simulates any internal error).
        bad_df = "not_a_dataframe"  # type: ignore[assignment]
        cov, null_rate, cik_res, cohort_sizes = _run_smallcap_coverage_probe(bad_df)  # type: ignore[arg-type]

        # Must not raise; returns None sentinels.
        assert cov is None
        assert null_rate is None
        assert cik_res is None
        assert cohort_sizes == {}


# ---------------------------------------------------------------------------
# 3. Metadata fields — sp1500 vs sp900/sp500 paths
# ---------------------------------------------------------------------------

class TestMetadataSmallcapFields:

    def test_smallcap_fields_accept_none(self) -> None:
        """Metadata model must accept None for all three smallcap fields (sp500/sp900 path)."""
        from compute.output.schemas import Metadata

        meta = Metadata(
            version="0.10.27-phase8pilot",
            last_update_utc="2026-06-20T00:00:00+00:00",
            next_update_utc="2026-06-21T00:00:00+00:00",
            universe="SP900",
            universe_size=902,
            compute_run_id="local",
            git_commit="abc123",
            smallcap_fundamentals_coverage_pct=None,
            smallcap_null_rate_pct=None,
            smallcap_cik_resolution_pct=None,
        )
        assert meta.smallcap_fundamentals_coverage_pct is None
        assert meta.smallcap_null_rate_pct is None
        assert meta.smallcap_cik_resolution_pct is None

    def test_smallcap_fields_accept_float_values(self) -> None:
        """Metadata model must accept non-None float values (sp1500 path)."""
        from compute.output.schemas import Metadata

        meta = Metadata(
            version="0.10.27-phase8pilot",
            last_update_utc="2026-06-20T00:00:00+00:00",
            next_update_utc="2026-06-21T00:00:00+00:00",
            universe="SP1500",
            universe_size=1498,
            compute_run_id="local",
            git_commit="abc123",
            universe_cohort_sizes={"sp500": 502, "sp400": 400, "sp600": 596},
            smallcap_fundamentals_coverage_pct=72.5,
            smallcap_null_rate_pct=27.5,
            smallcap_cik_resolution_pct=88.0,
        )
        assert meta.smallcap_fundamentals_coverage_pct == 72.5
        assert meta.smallcap_null_rate_pct == 27.5
        assert meta.smallcap_cik_resolution_pct == 88.0
        assert meta.universe == "SP1500"

    def test_universe_cohort_sizes_has_sp600_key(self) -> None:
        """Under sp1500, universe_cohort_sizes must accept a dict with sp600 key."""
        from compute.output.schemas import Metadata

        meta = Metadata(
            version="0.10.27-phase8pilot",
            last_update_utc="2026-06-20T00:00:00+00:00",
            next_update_utc="2026-06-21T00:00:00+00:00",
            universe="SP1500",
            universe_size=1498,
            compute_run_id="local",
            git_commit="abc123",
            universe_cohort_sizes={"sp500": 502, "sp400": 400, "sp600": 596},
        )
        assert "sp600" in meta.universe_cohort_sizes  # type: ignore[operator]
        assert meta.universe_cohort_sizes["sp600"] == 596  # type: ignore[index]


# ---------------------------------------------------------------------------
# 4. Source-check: pilot variables initialised to None before the probe block
# ---------------------------------------------------------------------------

class TestSmallcapVariableInitialisation:
    """Guard the invariant that _pilot_smallcap_* variables are explicitly
    initialised to None before the probe block in run_weekly_compute.

    This prevents a non-sp1500 path from accidentally leaking uninitialised
    values into Metadata (mirrors the sp900 guard in test_universe_sp900.py).
    """

    def test_pilot_smallcap_variables_initialised_to_none(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)

        for var in (
            "_pilot_smallcap_coverage_pct",
            "_pilot_smallcap_null_rate_pct",
            "_pilot_smallcap_cik_resolution_pct",
        ):
            assert var in src, (
                f"Variable {var!r} not found in run_weekly_compute — it must be declared"
            )
            # Verify it is initialised to None
            assert f"{var}: float | None = None" in src or f"{var} = None" in src, (
                f"Variable {var!r} must be initialised to None before the probe block"
            )

    def test_sp1500_branch_guarded_by_qr_universe(self) -> None:
        """The sp1500 branch must be gated behind QR_UNIVERSE == 'sp1500'."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        assert 'config.QR_UNIVERSE == "sp1500"' in src, (
            "run_weekly_compute must gate the sp1500 path with "
            'config.QR_UNIVERSE == "sp1500"'
        )

    def test_smallcap_probe_not_called_on_sp900_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_run_smallcap_coverage_probe must NOT be called when QR_UNIVERSE=sp900."""
        import compute.main as main_mod

        # Guard: this test only asserts on source; it does not run the full pipeline.
        src = inspect.getsource(main_mod.run_weekly_compute)
        # The sp900 branch must NOT invoke _run_smallcap_coverage_probe.
        # We check that _run_smallcap_coverage_probe only appears inside the
        # sp1500 block by checking it's NOT in the sp900 if-block prefix text.
        # Simple heuristic: the sp900 branch ends at the sp1500 elif; the
        # function name must appear AFTER the elif keyword.
        sp1500_elif_pos = src.find('elif config.QR_UNIVERSE == "sp1500"')
        smallcap_probe_pos = src.find("_run_smallcap_coverage_probe")
        assert sp1500_elif_pos != -1, "sp1500 elif branch not found in run_weekly_compute"
        assert smallcap_probe_pos != -1, "_run_smallcap_coverage_probe not found in run_weekly_compute"
        assert smallcap_probe_pos > sp1500_elif_pos, (
            "_run_smallcap_coverage_probe must appear AFTER the sp1500 elif "
            "(i.e. inside the sp1500 block, not the sp900 block)"
        )
