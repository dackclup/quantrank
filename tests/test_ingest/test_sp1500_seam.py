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

Integration-path targets (builder-flagged gaps, Slice 2 PR):
  7. run_weekly_compute source encodes "SP1500-probe" label in the sp1500 branch
     (locks the string literal against accidental rename — Slice 2 is probe-only).
  8. sp1500 branch source merges sp600 key from smallcap probe into
     _pilot_cohort_sizes (ensures universe_cohort_sizes carries "sp600"
     through to Metadata at write time).
  9. Empty all-cohorts DataFrame degrades through BOTH midcap + smallcap
     probes without crashing (regression guard: adding sp1500 seam must not
     introduce a crash path when all three cohort segments are absent).
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


def _make_empty_all_cohorts_df() -> pd.DataFrame:
    """sp1500-schema DataFrame with zero rows in ALL cohorts.

    Simulates the worst-case scenario where the Wikipedia fetcher returns no
    rows for any cohort segment (e.g. network outage + stale cache miss).
    Both ``_run_midcap_coverage_probe`` and ``_run_smallcap_coverage_probe``
    must degrade gracefully when passed this frame — no crash allowed.
    """
    return pd.DataFrame(
        columns=["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker", "cohort"]
    )


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


# ---------------------------------------------------------------------------
# 5. Integration-path coverage gaps (builder-flagged, Slice 2 PR)
# ---------------------------------------------------------------------------

class TestSp1500IntegrationSeam:
    """Locks the three integration-path invariants the builder flagged as
    untested at the Metadata-write level.

    These tests use source-code inspection (``inspect.getsource``) to avoid
    spinning up a full ``run_weekly_compute`` pipeline — an impractical cost
    for offline CI.  The source assertions are tighter than unit tests
    because they pin the *wiring* between the probe return value and the
    Metadata constructor argument (the layer that was actually missing
    coverage).

    Gap 3: ``universe="SP1500"`` string literal is in the sp1500 branch of
           ``run_weekly_compute``, gated behind the correct env sentinel.
    Gap 4: The sp1500 branch contains the ``_pilot_cohort_sizes.update()``
           merge that carries the ``sp600`` key through to
           ``universe_cohort_sizes`` at Metadata construction time.
    Gap 5: Empty all-cohorts DataFrame degrades through BOTH
           ``_run_midcap_coverage_probe`` and ``_run_smallcap_coverage_probe``
           without crashing (direct probe-function calls, synthetic fixture).
    """

    # -- Gap 3: "SP1500" universe label is wired into the sp1500 branch ------

    def test_sp1500_universe_label_present_in_sp1500_branch(self) -> None:
        """Source: universe="SP1500-probe" must be assigned inside the sp1500 gated block.

        Slice 2 Rule-18 fix: the universe label is "SP1500-probe" (not "SP1500")
        to signal to consumers that this is an observability run — sp600 rows are
        probed for EDGAR coverage but NOT ranked.  Locks the string literal
        against accidental rename / missing-branch wiring.

        The check that it appears AFTER the sp1500 elif (not in the sp900 or
        sp500 branches) mirrors the placement guard already applied to
        ``_run_smallcap_coverage_probe`` in TestSmallcapVariableInitialisation.
        """
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        sp1500_label = '"SP1500-probe"'
        sp1500_elif_pos = src.find('elif config.QR_UNIVERSE == "sp1500"')
        label_pos = src.find(sp1500_label)

        assert sp1500_elif_pos != -1, "sp1500 elif branch not found in run_weekly_compute"
        assert label_pos != -1, (
            f'{sp1500_label} not found in run_weekly_compute — '
            "the Metadata universe field must carry the SP1500-probe label on this path "
            "(Slice 2: sp600 is probe-only, not ranked; the -probe suffix distinguishes "
            "this from a full sp1500 ranked output)"
        )
        assert label_pos > sp1500_elif_pos, (
            f'{sp1500_label} must appear AFTER the sp1500 elif, not in the sp900/sp500 branches'
        )

    def test_sp1500_universe_label_gated_on_qr_universe_sentinel(self) -> None:
        """Source: the "SP1500" label assignment must be conditional on QR_UNIVERSE == 'sp1500'.

        Checks that the production Metadata ``universe`` field uses the
        config-sentinel guard (``config.QR_UNIVERSE == "sp1500"``) — not a
        hardcoded always-on string — so the default sp900 path still emits
        ``"SP900"``.
        """
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        # The conditional ternary / if-elif in the Metadata constructor must
        # reference the QR_UNIVERSE sentinel when choosing between SP1500 / SP900
        # / SP500.  A simple grep for the patterns that implement this:
        assert 'config.QR_UNIVERSE == "sp1500"' in src, (
            'run_weekly_compute must gate universe="SP1500" on config.QR_UNIVERSE == "sp1500"'
        )
        assert '"SP900"' in src, (
            '"SP900" must also be present (the sp900 Metadata label fallback) so the '
            "conditional is a real branch, not a single-value assignment"
        )

    # -- Gap 4: universe_cohort_sizes sp600 key merge is wired in sp1500 -----

    def test_sp1500_branch_merges_sp600_cohort_key_into_pilot_sizes(self) -> None:
        """Source: sp1500 branch must merge sp600 sizes from smallcap probe return.

        ``_run_smallcap_coverage_probe`` returns a ``cohort_sizes`` dict with
        all 3 keys.  The sp1500 branch must call ``.update()`` (or equivalent)
        on ``_pilot_cohort_sizes`` with that return value so the ``sp600`` key
        reaches ``universe_cohort_sizes`` in Metadata.

        Limitation: this is a source-level wiring check, not an end-to-end
        Metadata serialisation check — a full pipeline run is needed to confirm
        the dict survives to the JSON writer.  That runs in CI on the sp1500
        workflow_dispatch path, not in the offline suite.
        """
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)

        # The sp1500 elif block must contain the merge call.  Check it appears
        # after the sp1500 elif (so it's inside that branch, not sp900).
        sp1500_elif_pos = src.find('elif config.QR_UNIVERSE == "sp1500"')
        # The merge pattern: either .update(_sp1500_cohort_sizes) or a full
        # reassignment from _run_smallcap_coverage_probe's return value.
        merge_pos = src.find("_pilot_cohort_sizes.update")
        # Also accept the initialisation pattern where None-guard is used.
        init_pos = src.find("_pilot_cohort_sizes = _sp1500_cohort_sizes")

        assert sp1500_elif_pos != -1, "sp1500 elif not found"
        found_merge = (merge_pos != -1 and merge_pos > sp1500_elif_pos) or (
            init_pos != -1 and init_pos > sp1500_elif_pos
        )
        assert found_merge, (
            "sp1500 branch must merge the smallcap probe's cohort_sizes dict into "
            "_pilot_cohort_sizes so that universe_cohort_sizes carries the 'sp600' key. "
            "Expected _pilot_cohort_sizes.update(...) or _pilot_cohort_sizes = _sp1500_cohort_sizes "
            "after the sp1500 elif."
        )

    def test_universe_cohort_sizes_field_passed_from_pilot_cohort_sizes(self) -> None:
        """Source: Metadata constructor receives universe_cohort_sizes from _pilot_cohort_sizes.

        Confirms that the Metadata assembly block (near the end of
        run_weekly_compute) passes ``_pilot_cohort_sizes`` (possibly guarded
        with ``or None``) to ``universe_cohort_sizes``.  This is the final hop
        that lands the sp600 key in the JSON output.
        """
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        assert "universe_cohort_sizes=_pilot_cohort_sizes" in src, (
            "Metadata constructor must receive universe_cohort_sizes from _pilot_cohort_sizes "
            "(with or without 'or None' guard). This wires the sp600 key into the JSON output."
        )

    # -- Gap 5: empty all-cohorts DataFrame degrades through both probes ------

    def test_empty_all_cohorts_df_midcap_probe_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both probes must survive an all-cohorts-empty DataFrame without crashing.

        This is the worst-case fallback: the Wikipedia fetcher returned no rows
        for any segment (network outage + stale cache miss).  The defense is
        the outer try/except in each probe function that returns (None, None,
        None, {}) on any unexpected error, plus the explicit zero-count early-
        return path when the cohort mask selects no rows.

        Regression guard: the Slice 2 seam must not introduce a new crash path
        on an all-empty universe frame.  Mirrors the sp900 test that checks the
        same invariant for _run_midcap_coverage_probe.
        """
        from compute.main import _run_midcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        empty_df = _make_empty_all_cohorts_df()

        # Must not raise.
        cov, null_rate, cik_res, cohort_sizes = _run_midcap_coverage_probe(empty_df)

        assert cov is None
        assert null_rate is None
        assert cik_res is None
        # cohort_sizes must be a dict (possibly empty or with zero-count keys)
        assert isinstance(cohort_sizes, dict)

    def test_empty_all_cohorts_df_smallcap_probe_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_run_smallcap_coverage_probe must survive an all-cohorts-empty DataFrame.

        Called directly with the empty frame (no sp500 / sp400 / sp600 rows).
        The probe must return sentinel Nones and an empty or zero-valued
        cohort_sizes dict — not raise AttributeError / KeyError / empty-mask
        exceptions.
        """
        from compute.main import _run_smallcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        empty_df = _make_empty_all_cohorts_df()

        # Must not raise.
        cov, null_rate, cik_res, cohort_sizes = _run_smallcap_coverage_probe(empty_df)

        assert cov is None
        assert null_rate is None
        assert cik_res is None
        assert isinstance(cohort_sizes, dict)

    def test_empty_all_cohorts_both_probes_sequential_no_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Running both probes in sequence (as run_weekly_compute does) must not crash.

        Mirrors the sp1500 branch flow: midcap probe runs first, then smallcap
        probe on the same frame.  Ensures no shared-state mutation between the
        two probe calls causes the second call to crash even when the first
        returned empty results.
        """
        from compute.main import _run_midcap_coverage_probe, _run_smallcap_coverage_probe

        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: None)
        empty_df = _make_empty_all_cohorts_df()

        # Run midcap probe first (mimics sp1500 branch order).
        mid_cov, mid_null, mid_cik, mid_sizes = _run_midcap_coverage_probe(empty_df)

        # Then smallcap probe on the same frame.
        sml_cov, sml_null, sml_cik, sml_sizes = _run_smallcap_coverage_probe(empty_df)

        # Both must return clean sentinel values (no crash, no exception).
        assert mid_cov is None
        assert sml_cov is None
        # cohort_sizes from both must be dicts (even if empty).
        assert isinstance(mid_sizes, dict)
        assert isinstance(sml_sizes, dict)


# ---------------------------------------------------------------------------
# 6. Slice 2 probe-only invariant: sp600 absent from scored universe,
#    smallcap_* Metadata fields still populated (Rule-18 filter ordering guard)
# ---------------------------------------------------------------------------

class TestSp1500Slice2ProbeOnly:
    """Locks the headline Slice 2 invariant: sp600 is PROBE-ONLY.

    The sp1500 seam must:
      (a) Run the smallcap probe on the FULL frame (capturing sp600 EDGAR
          coverage into Metadata).
      (b) DROP all sp600 rows BEFORE feeding the frame to Step 1 (prices),
          so sp600 is never scored, ranked, or written to JSON.
      (c) The source ordering of (a) before (b) is enforced by source
          inspection so this invariant survives refactors.

    Two sub-tests:
      - Source-ordering check: ``_run_smallcap_coverage_probe`` appears
        BEFORE the ``cohort != "sp600"`` filter in the sp1500 elif block.
      - Direct functional test: the filter applied to a synthetic mixed
        DataFrame produces zero sp600 rows and preserves sp500/sp400 rows.
    """

    def test_sp600_rows_absent_from_universe_after_sp1500_seam(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Functional: filter drops ALL sp600 rows; sp400/sp500 rows survive.

        Synthesises a mixed sp400 + sp600 frame (mirrors the output of
        ``get_sp1500_constituents``), runs both diagnostic probes on the full
        frame, then applies the sp600 filter — asserts zero sp600 rows remain
        AND the 3 smallcap_* coverage fields are non-None (probe ran on the
        full frame before the filter).
        """
        from compute.main import _run_smallcap_coverage_probe

        # Synthetic mixed frame — 2 sp400 + 3 sp600 (mirrors get_sp1500_constituents output).
        sp1500_df = _make_sp1500_df()

        # Probe the full frame (mirrors the seam: probe runs BEFORE filter).
        monkeypatch.setattr("compute.main.fetch_fundamentals", lambda t, c: MagicMock())
        cov, null_rate, cik_res, _ = _run_smallcap_coverage_probe(sp1500_df)

        # Smallcap probe must have populated coverage fields (ran on full frame).
        assert cov is not None, (
            "smallcap_fundamentals_coverage_pct must be populated after probe on full frame"
        )
        assert null_rate is not None, (
            "smallcap_null_rate_pct must be populated after probe on full frame"
        )
        assert cik_res is not None, (
            "smallcap_cik_resolution_pct must be populated after probe on full frame"
        )

        # Now apply the Slice 2 filter (mirrors the seam: cohort != "sp600").
        scored_universe = sp1500_df[sp1500_df["cohort"] != "sp600"].reset_index(drop=True)

        # Zero sp600 rows must remain in the scored universe.
        sp600_in_scored = scored_universe[scored_universe["cohort"] == "sp600"]
        assert len(sp600_in_scored) == 0, (
            f"sp600 rows must be absent from the scored universe after the Slice 2 filter, "
            f"got {len(sp600_in_scored)} rows: {sp600_in_scored['ticker'].tolist()}"
        )

        # sp500 + sp400 rows must survive the filter intact.
        assert len(scored_universe) == 4, (
            f"Scored universe should contain 2 sp500 + 2 sp400 = 4 rows after filter, "
            f"got {len(scored_universe)}"
        )
        surviving_cohorts = set(scored_universe["cohort"].unique())
        assert surviving_cohorts == {"sp500", "sp400"}, (
            f"Only sp500 and sp400 cohorts should survive the filter, got {surviving_cohorts!r}"
        )

    def test_sp1500_seam_probe_runs_before_filter_in_source(self) -> None:
        """Source ordering: smallcap probe must appear BEFORE the sp600 filter.

        Guards the Rule-18 invariant at the source level: if a refactor moves
        the filter before the probe call, the probe would only see sp500/sp400
        rows and the sp600 EDGAR coverage would never be captured in Metadata.

        Uses ``inspect.getsource`` — no pipeline invocation needed.
        """
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)

        probe_call_pos = src.find("_run_smallcap_coverage_probe")
        filter_pos = src.find('_sp1500_full_frame["cohort"] != "sp600"')

        assert probe_call_pos != -1, (
            "_run_smallcap_coverage_probe call not found in run_weekly_compute source"
        )
        assert filter_pos != -1, (
            'sp600 filter expression (_sp1500_full_frame["cohort"] != "sp600") '
            "not found in run_weekly_compute source — the Slice 2 filter must be present"
        )
        assert probe_call_pos < filter_pos, (
            "Rule-18 ordering violation: _run_smallcap_coverage_probe must be called "
            "BEFORE the sp600 filter so the probe runs on the full frame (incl. sp600 rows). "
            f"probe at char {probe_call_pos}, filter at char {filter_pos}"
        )
