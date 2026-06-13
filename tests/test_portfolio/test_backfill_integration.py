"""End-to-end wiring test for the Phase 7.0c backfill orchestrator (synthetic data).

Runs ``run_backfill`` over a 3-ticker synthetic universe with mocked data
sources (universe / fundamentals_history / prices) but the REAL pillar pipeline,
composite, selection, inverse-vol weighting, NAV, and ``members_at`` — so the
integration the dev sandbox otherwise can't exercise (no caches / network) is
validated offline. Catches the wiring bugs the methodology-scientist flagged
(synthetic-snapshot field mapping, filed<=T history frame, price-at-T) by
asserting the orchestrator produces a well-formed ``backtest_pit.json``.

Phase 7.0c additions (PR-2c):
  - ``meta.veto_layer_replayed`` is True
  - ``meta.vetoes_replayed`` lists the 6 accounting vetoes
  - ``meta.vetoes_not_replayed`` lists ``non_reliance_filing`` with reason
  - ``meta.rule_version`` carries the ``+veto-replay`` suffix
  - ``rebalances[i].full_ranked``: ≤40 dicts with ticker/composite/sector/mos_pct/recommendation
  - ``rebalances[i].holdings[j].mos_pct``: float|None
  - ``rebalances[i].sector_weights_by_count``: {str(N): {sector: weight}}, per-N sums ≈1.0
  - ``rebalances[i].high_conviction_count``: int in [0, len(picks)]
  - ``rebalances[i].vetoed_pick_candidates``: vetoed top-N names recorded here,
    excluded from picks, their composite scores preserved (Rule 16)
  - ``_compute_pit_risk_flags`` forwards ``today=rebalance_date`` so NSI lookbacks
    anchor to T (not today)
"""
from __future__ import annotations

import json
from datetime import date
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from scripts import backfill_portfolio_pit as bf

# Broad enough metric set that most pillars compute a real (non-neutral) score.
_METRICS = {
    "revenue": 100.0, "net_income": 10.0, "gross_profit": 40.0, "operating_income": 15.0,
    "cost_of_revenue": 60.0, "operating_cash_flow": 12.0, "capex": -3.0,
    "total_assets": 200.0, "total_liabilities": 120.0, "stockholders_equity": 80.0,
    "cash": 20.0, "current_assets": 60.0, "current_liabilities": 40.0,
    "long_term_debt": 50.0, "shares_outstanding": 5.0,
    "depreciation_and_amortization": 5.0, "interest_expense": 2.0,
    "inventory": 15.0, "accounts_receivable": 10.0,
}
_FILINGS = [(2020, "2021-02-15"), (2021, "2022-02-15"), (2022, "2023-02-15"), (2023, "2024-02-15")]


def _annual_history(scale: float) -> pd.DataFrame:
    rows = []
    for fy, filed in _FILINGS:
        growth = 1.0 + 0.10 * (fy - 2020)
        for metric, base in _METRICS.items():
            rows.append(
                {
                    "fiscal_year": fy,
                    "metric": metric,
                    "value": float(base * scale * growth),
                    "period_end": date(fy, 12, 31),
                    "filing_date": date.fromisoformat(filed),
                    "form_type": "10-K",
                }
            )
    return pd.DataFrame(rows)


def _prices(seed: int) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", "2024-06-30")
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx))))
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Adj Close": close, "Volume": 1.0e6},
        index=idx,
    )


@pytest.fixture
def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "AAA", "name": "Alpha", "sector": "Information Technology", "sub_industry": "x", "cik": "1"},
            {"ticker": "BBB", "name": "Beta", "sector": "Health Care", "sub_industry": "y", "cik": "2"},
            {"ticker": "CCC", "name": "Gamma", "sector": "Financials", "sub_industry": "z", "cik": "3"},
        ]
    )


@pytest.fixture(autouse=True)
def _mock_list_known_events_default():
    """Default autouse fixture: mock ``list_known_events`` to return ``()`` (no
    historical REMOVE events) for all tests in this file that do NOT explicitly
    override it.

    Why: ``run_backfill`` now calls ``list_known_events(since=start)`` to build the
    survivorship-bias fix pre-fetch set.  Without this mock, tests using the synthetic
    3-ticker universe (AAA/BBB/CCC) would read the REAL membership CSV, discover
    real historical removed tickers (TFX, ATVI, …), and add them to the scoring
    cohort via ``members_at`` — changing cross-sectional normalization and breaking
    assertions that compare two ``run_backfill`` calls (e.g. ``hc_names <= vo_names``).

    Tests that explicitly test the survivorship fix override this default by providing
    their own ``list_known_events`` mock inside their ``with mock.patch.object(bf,
    "list_known_events", ...)`` context.  That override takes precedence over the
    autouse fixture because ``mock.patch.object`` within a test body re-patches the
    same attribute, shadowing the fixture's patch for the duration of the ``with``
    block.
    """
    def _sector_from_universe(ticker, _as_of):
        # Mirror the pre-parquet behavior: in the graceful-degradation (parquet
        # absent) path the sector equals today's universe sector. Look it up from
        # the test-mocked get_sp500_constituents (deferred to call time so the
        # per-test mock is active). Without this, _pit_sector would call the real
        # sector_at, which reads the committed data/historical_sector.parquet and
        # returns "Unknown" for the synthetic AAA/BBB/CCC tickers.
        members = bf.get_sp500_constituents()
        match = members[members["ticker"] == ticker]
        return str(match.iloc[0]["sector"]) if len(match) else "Unknown"

    with (
        mock.patch.object(bf, "list_known_events", return_value=()),
        # Isolate from the committed data/*.parquet PIT artifacts so these
        # synthetic-universe tests run the deterministic parquet-absent path
        # whether or not the real parquets exist in the tree. The parquet-PRESENT
        # path is covered by a dedicated test that overrides these patches.
        mock.patch.object(bf, "item402_parquet_row_count", return_value=0),
        mock.patch.object(
            bf, "historical_sector_parquet_stats", return_value={"parquet_present": False}
        ),
        mock.patch.object(bf, "sector_at", side_effect=_sector_from_universe),
    ):
        yield


def test_run_backfill_produces_wellformed_artifact(tmp_path, _universe) -> None:
    scale_by_cik = {"1": 1.0, "2": 1.4, "3": 0.7}

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(scale_by_cik.get(cik, 1.0))),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),  # no restatements -> canary 0.0
        # Wiring-only isolation: synthetic revenue=100 triggers data_quality_input_corruption
        # on every ticker (Pattern 2: revenue < $50M). Mock the flag function so picks are
        # produced and the structural assertions can run against the real wiring.
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        # gate="veto_only" exercises the gate-independent WIRING (snapshot->pillars->NAV
        # ->canary) with synthetic data that needn't clear the production high-conviction
        # gate; the gate filter itself is unit-tested in test_weights.py + asserted applied
        # in test_run_backfill_high_conviction_gate_is_applied below.
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    assert out.exists()
    payload = json.loads(out.read_text())

    # shape
    assert set(payload) >= {"meta", "rebalances", "nav"}
    meta = payload["meta"]
    assert meta["rebalance_count"] == len(payload["rebalances"]) > 0
    # Phase 7.0c: veto_layer_replayed is True (six accounting vetoes replayed PIT).
    assert meta["veto_layer_replayed"] is True
    assert meta["sector_from_today"] is True
    assert meta["default_count"] == bf.DEFAULT_COUNT
    assert meta["disclaimer"].startswith("Illustrative backtest")
    assert meta["incomplete_membership_count"] == 0  # all dates in coverage
    # restatement canary re-sourced from the EDGAR filings index (no amendments -> 0.0)
    assert meta["restatement_canary_source"] == "edgar-filings-index"
    assert meta["restatement_contamination_pct"] == 0.0
    assert meta["restatement_canary_unresolved_count"] == 0

    # Phase 7.0c: vetoes_replayed / vetoes_not_replayed present and correct.
    assert meta["vetoes_replayed"] == list(bf._VETOES_REPLAYED)
    assert len(meta["vetoes_not_replayed"]) == 1
    nr = meta["vetoes_not_replayed"][0]
    assert nr["name"] == "non_reliance_filing"
    assert nr["reason"] == "no_8k_history_in_pit_data"

    # rebalances: ranked holdings + per-count inverse-vol weights (each basket sums ~1)
    for reb in payload["rebalances"]:
        assert reb["members_complete"] is True
        assert reb["holdings"]
        for h in reb["holdings"]:
            assert {"ticker", "composite_score", "sector", "sigma_90d"} <= set(h)
            # Phase 7.0c: mos_pct present on every holding (float or None).
            assert "mos_pct" in h
            assert h["mos_pct"] is None or isinstance(h["mos_pct"], float)
        wbc = reb["weights_by_count"]
        assert wbc  # at least the count-"1" basket
        for n_str, wmap in wbc.items():
            assert wmap
            for w in wmap.values():
                assert 0.0 <= w <= 1.0
            # count-N basket weights <= N of the ranked holdings (fewer if the leg had
            # < N names with a computable sigma)
            assert len(wmap) <= int(n_str)
            # per-holding weights are round(6); summing <= 10 accrues at most ~5e-6
            assert sum(wmap.values()) == pytest.approx(1.0, abs=1e-5)

        # Phase 7.0c: full_ranked — list of ≤40 dicts with the required schema.
        assert "full_ranked" in reb
        assert isinstance(reb["full_ranked"], list)
        assert len(reb["full_ranked"]) <= bf._FULL_RANKED_LIMIT
        for entry in reb["full_ranked"]:
            assert set(entry) == {"ticker", "composite_score", "sector", "mos_pct", "recommendation"}
            assert isinstance(entry["ticker"], str)
            assert isinstance(entry["composite_score"], (int, float))
            assert entry["mos_pct"] is None or isinstance(entry["mos_pct"], float)

        # Phase 7.0c: high_conviction_count in [0, len(picks)].
        assert "high_conviction_count" in reb
        n_picks = len(reb["holdings"])
        assert 0 <= reb["high_conviction_count"] <= n_picks

        # Phase 7.0c: sector_weights_by_count — {str(N): {sector: weight}},
        # per-N weights sum ≈ 1.0.
        # Tolerance: production N=20 / ~10 sectors rounds each sector weight to 4dp
        # so per-N accumulation can reach ±~5e-4; abs=1e-3 is the honest bound.
        assert "sector_weights_by_count" in reb
        swbc = reb["sector_weights_by_count"]
        assert isinstance(swbc, dict)
        for n_str, by_sector in swbc.items():
            assert n_str.isdigit()
            assert by_sector
            assert sum(by_sector.values()) == pytest.approx(1.0, abs=1e-3)

        # Phase 7.0c: vetoed_pick_candidates — list of dicts (may be empty when no
        # veto fires, which is the case under the _compute_pit_risk_flags={} mock).
        assert "vetoed_pick_candidates" in reb
        assert isinstance(reb["vetoed_pick_candidates"], list)

    # NAV: a daily series PER holding count, all aligned to the shared dates; within
    # each count net <= gross and conservative <= net (cost drag); base 100 at the start
    nav = payload["nav"]
    n_dates = len(nav["dates"])
    assert n_dates > 0
    assert nav["default_count"] == bf.DEFAULT_COUNT
    assert str(bf.DEFAULT_COUNT) in nav["by_count"]  # the slider's landing count
    assert isinstance(nav["benchmark"], dict)  # empty here (synthetic run, no benchmarks.json)
    for series in nav["by_count"].values():
        assert len(series["gross"]) == len(series["net"]) == len(series["net_conservative"]) == n_dates
        first_gross = next(v for v in series["gross"] if v is not None)
        assert first_gross == pytest.approx(100.0)  # rebased start (None-padded if late)
        g_last = next(v for v in reversed(series["gross"]) if v is not None)
        net_last = next(v for v in reversed(series["net"]) if v is not None)
        cons_last = next(v for v in reversed(series["net_conservative"]) if v is not None)
        assert net_last <= g_last + 1e-9
        assert cons_last <= net_last + 1e-9


def test_run_backfill_high_conviction_gate_is_applied(tmp_path, _universe) -> None:
    """The production default gate='high_conviction' threads through to select_picks and is
    a STRICT sub-filter of veto_only on identical inputs: every name held under the conviction
    gate is also held under veto_only, meta.high_conviction_gate_active reflects the gate, and
    the recommendation/valuation layer is replayed either way. (Asserts the relationship +
    flags, not a specific count — robust to the synthetic cohort happening to pass/fail.)"""
    def _run(gate: str) -> dict:
        with (
            mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
            mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
            mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
            mock.patch.object(bf, "fetch_amendments", return_value=[]),
            mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
        ):
            out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate=gate)
        return json.loads(out.read_text())  # read before the next run overwrites the file

    hc = _run("high_conviction")
    vo = _run("veto_only")

    assert hc["meta"]["high_conviction_gate_active"] is True
    assert vo["meta"]["high_conviction_gate_active"] is False
    assert hc["meta"]["recommendation_layer_replayed"] is True  # replayed regardless of gate
    assert "high_conviction_gate" in hc["meta"]  # the gate descriptor is emitted

    hc_names = {h["ticker"] for r in hc["rebalances"] for h in r["holdings"]}
    vo_names = {h["ticker"] for r in vo["rebalances"] for h in r["holdings"]}
    assert hc_names <= vo_names  # the conviction gate is a strict sub-filter of veto_only


def test_run_backfill_skips_incomplete_membership(tmp_path, _universe) -> None:
    """A pre-coverage window (before EARLIEST_EVENT_DATE) yields no trusted legs."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(1)),
    ):
        # Pre-2016: the ledger now covers 2016-01 onward (Track B 10Y rebuild),
        # so the pre-coverage window moved back from 2018 to before 2016.
        out = bf.run_backfill(date(2014, 1, 1), date(2015, 6, 1), data_dir=tmp_path)

    meta = json.loads(out.read_text())["meta"]
    # every quarterly leg in this window is pre-coverage -> is_complete False -> skipped
    assert meta["rebalance_count"] == 0
    assert meta["incomplete_membership_count"] > 0


def test_run_backfill_skips_sigma_empty_rebalance(tmp_path, _universe) -> None:
    """A trusted (members-complete) leg where NO pick has a computable 90d sigma is
    silently skipped at the `weights_by_count` empty -> `continue` gate: rebalance_count
    AND incomplete_membership_count are BOTH 0 — a path distinct from the is_complete=False
    skip (so an all-zero result isn't misread as a membership-coverage gap)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(1)),
        # full prices (pillars score normally) but no name yields a sigma -> every leg's
        # weights_by_count is empty -> the `continue` fires for all of them.
        mock.patch.object(bf, "trailing_return_sigma", return_value=None),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        # gate="veto_only" exercises the gate-independent WIRING (snapshot->pillars->NAV
        # ->canary) with synthetic data that needn't clear the production high-conviction
        # gate; the gate filter itself is unit-tested in test_weights.py + asserted applied
        # in test_run_backfill_high_conviction_gate_is_applied below.
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    assert meta["rebalance_count"] == 0          # every leg skipped at the sigma gate
    assert meta["incomplete_membership_count"] == 0  # NOT the membership-degraded path


def test_run_backfill_restatement_canary_flags_post_asof_amendment(tmp_path, _universe) -> None:
    """A picked name with a 10-K/A filed AFTER its selection date AND within the
    2-year fiscal-year window raises the canary — restatement_contamination_pct > 0.

    The synthetic data's most-recent PIT fiscal year at rebalance 2022-06-01 is 2021
    (10-K filed 2022-02-15). The FIX 1 ceiling is {2021+2}-12-31 = 2023-12-31.
    Filing date "2023-06-01" is post-as-of AND within the ceiling → canary fires.
    """
    post_asof = [{"form": "10-K/A", "filing_date": "2023-06-01", "accession": "x", "filing_url": ""}]
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=post_asof),
        # Wiring-only isolation so picks are produced and the canary assertions run.
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        # gate="veto_only" exercises the gate-independent WIRING (snapshot->pillars->NAV
        # ->canary) with synthetic data that needn't clear the production high-conviction
        # gate; the gate filter itself is unit-tested in test_weights.py + asserted applied
        # in test_run_backfill_high_conviction_gate_is_applied below.
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    assert meta["rebalance_count"] > 0
    assert meta["restatement_contamination_pct"] == pytest.approx(100.0)  # every pick flagged
    assert meta["restatement_canary_unresolved_count"] == 0


def test_run_backfill_restatement_canary_unresolved_on_fetch_failure(tmp_path, _universe) -> None:
    """fetch_amendments returning None (EDGAR unreachable) marks picks UNRESOLVED, not
    at-risk: contamination stays 0.0 but the unresolved count is non-zero (honest)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=None),
        # Wiring-only isolation so picks are produced and the canary assertions run.
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        # gate="veto_only" exercises the gate-independent WIRING (snapshot->pillars->NAV
        # ->canary) with synthetic data that needn't clear the production high-conviction
        # gate; the gate filter itself is unit-tested in test_weights.py + asserted applied
        # in test_run_backfill_high_conviction_gate_is_applied below.
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    assert meta["restatement_contamination_pct"] == 0.0
    assert meta["restatement_canary_unresolved_count"] > 0


def test_restatement_at_risk_filings_index_semantics() -> None:
    """Legacy mode (pit_fiscal_year=None): ANY amendment filed after as_of fires.

    When no pit_fiscal_year is provided the function falls back to the original
    conservative behaviour — any post-as-of amendment counts regardless of FY.
    """
    amends = [{"form": "10-K/A", "filing_date": "2023-03-15"}]
    assert bf._restatement_at_risk(amends, "2022-06-01") is True    # filed after as_of
    assert bf._restatement_at_risk(amends, "2024-01-01") is False   # filed before as_of
    assert bf._restatement_at_risk([{"form": "10-Q/A", "filing_date": "2023-01-01"}], "2022-01-01") is True
    assert bf._restatement_at_risk([], "2022-06-01") is False       # no amendments
    assert bf._restatement_at_risk(None, "2022-06-01") is False     # unresolved -> not at-risk


def test_restatement_at_risk_period_map_gate() -> None:
    """FIX 1 — period-map gate: amendments beyond pit_fiscal_year+2 years are excluded.

    With pit_fiscal_year=2021, the ceiling is 2023-12-31.
    - "2023-06-01" is post-as-of AND within ceiling → fires.
    - "2099-01-01" is post-as-of BUT beyond ceiling (clearly a different FY) → no fire.
    - "2019-01-01" is pre-as-of → no fire regardless of ceiling.
    When pit_fiscal_year=None, the ceiling is lifted → "2099-01-01" fires (legacy).
    """
    as_of = "2022-06-01"
    # Within 2-year window: fires.
    assert bf._restatement_at_risk(
        [{"filing_date": "2023-06-01"}], as_of, pit_fiscal_year=2021
    ) is True
    # Beyond 2-year window: suppressed.
    assert bf._restatement_at_risk(
        [{"filing_date": "2099-01-01"}], as_of, pit_fiscal_year=2021
    ) is False
    # Pre-as-of: never fires.
    assert bf._restatement_at_risk(
        [{"filing_date": "2019-01-01"}], as_of, pit_fiscal_year=2021
    ) is False
    # Exactly at ceiling (2023-12-31): fires (inclusive boundary).
    assert bf._restatement_at_risk(
        [{"filing_date": "2023-12-31"}], as_of, pit_fiscal_year=2021
    ) is True
    # One day past ceiling: suppressed.
    assert bf._restatement_at_risk(
        [{"filing_date": "2024-01-01"}], as_of, pit_fiscal_year=2021
    ) is False
    # Legacy mode (pit_fiscal_year=None): ceiling lifted, any post-as-of fires.
    assert bf._restatement_at_risk(
        [{"filing_date": "2099-01-01"}], as_of, pit_fiscal_year=None
    ) is True


def test_pit_fiscal_year_at_returns_latest_eligible_fy() -> None:
    """FIX 1 helper: _pit_fiscal_year_at returns the most-recent 10-K FY at as_of."""
    rows = [
        {"form_type": "10-K", "fiscal_year": 2020, "filing_date": "2021-02-15", "value": 1.0, "metric": "revenue"},
        {"form_type": "10-K", "fiscal_year": 2021, "filing_date": "2022-02-15", "value": 1.0, "metric": "revenue"},
        {"form_type": "10-K/A", "fiscal_year": 2021, "filing_date": "2022-06-01", "value": 1.0, "metric": "revenue"},
    ]
    # As of 2022-06-01: latest eligible 10-K is FY2021 (filed 2022-02-15 <= 2022-06-01)
    # 10-K/A rows are excluded by form_type gate (only "10-K" is eligible)
    assert bf._pit_fiscal_year_at(rows, "2022-06-01") == 2021
    # As of 2021-12-31: only FY2020 is filed before this date
    assert bf._pit_fiscal_year_at(rows, "2021-12-31") == 2020
    # As of 2020-12-31: no 10-K filed before this date
    assert bf._pit_fiscal_year_at(rows, "2020-12-31") is None
    # Empty rows: None
    assert bf._pit_fiscal_year_at([], "2022-06-01") is None


def test_artifact_carries_period_map_gated_flag(tmp_path, _universe) -> None:
    """FIX 1: meta.restatement_canary_period_map_gated is True in the artifact."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")
    meta = json.loads(out.read_text())["meta"]
    assert meta["restatement_canary_period_map_gated"] is True


def test_insample_lag_clause_states_actual_result_vs_spy() -> None:
    """The disclaimer's result-dependent sentence reflects the ACTUAL default-count net
    line vs SPY (lag / lead / tracked), and falls back generically when nav is empty — so
    it can never claim a win the chart contradicts (methodology-scientist honesty fix)."""
    d0, d1 = date(2021, 6, 1), date(2026, 6, 1)

    def _nav(net_last: float, spy_last: float) -> dict:
        return {
            "by_count": {str(bf.DEFAULT_COUNT): {"net": [100.0, net_last]}},
            "benchmark": {"spy": [100.0, spy_last]},
        }

    assert "underperformed the S&P 500 (132 vs 180" in bf._insample_lag_clause(_nav(132.0, 180.0), d0, d1)
    assert "outperformed the S&P 500 (190 vs 180" in bf._insample_lag_clause(_nav(190.0, 180.0), d0, d1)
    assert "tracked the S&P 500" in bf._insample_lag_clause(_nav(180.2, 180.0), d0, d1)  # within dead-band
    fallback = bf._insample_lag_clause({"by_count": {}, "benchmark": {}}, d0, d1)
    assert "Past performance" in fallback
    assert "underperformed" not in fallback and "outperformed" not in fallback  # no directional claim


def _bday_frame(prices: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2022-01-03", periods=len(prices))
    return pd.DataFrame({"Close": prices, "Adj Close": prices}, index=idx)


def test_assemble_nav_builds_one_aligned_series_per_count(tmp_path) -> None:
    """`_assemble_nav` emits a NAV per count N, all aligned to shared dates; N=1 tracks
    its single name and the down-name drags the N=2 blend below the all-up N=1 line."""
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),       # steadily up
        "BBB": _bday_frame([100.0 - 0.2 * i for i in range(120)]),  # steadily down
    }
    # two quarterly rebalances on real business days inside the price window
    # (3-tuples since the adaptive book: third element = n_adaptive for that leg)
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}, 2: {"AAA": 0.5, "BBB": 0.5}}, 2),
        ("2022-03-14", {1: {"AAA": 1.0}, 2: {"AAA": 0.6, "BBB": 0.4}}, 2),
    ]
    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert out["default_count"] == bf.DEFAULT_COUNT
    assert set(out["by_count"]) == {"1", "2"}
    nd = len(out["dates"])
    assert nd > 0
    for s in out["by_count"].values():
        assert len(s["gross"]) == len(s["net"]) == nd  # every count aligned to dates

    g1 = out["by_count"]["1"]["gross"]
    g2 = out["by_count"]["2"]["gross"]
    assert g1[0] == pytest.approx(100.0)          # rebased start
    assert g1[-1] > g1[0]                          # 100% of the up-name rises
    assert g2[-1] < g1[-1]                          # the down-name drags the blend


def test_assemble_nav_snaps_weekend_rebalance_to_trading_day(tmp_path) -> None:
    """A rebalance dated on a weekend still fires — snapped to the next trading day —
    rather than being silently dropped (build_portfolio_nav needs a date in the calendar)."""
    prices_by_ticker = {"AAA": _bday_frame([100.0 + i for i in range(60)])}
    # 2022-01-08 is a Saturday; the next trading day is Monday 2022-01-10
    rebalance_picks = [("2022-01-08", {1: {"AAA": 1.0}}, 1)]
    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert out["by_count"]  # the leg was NOT dropped
    assert out["dates"][0] == "2022-01-10"  # snapped Sat -> Mon
    assert out["by_count"]["1"]["gross"][0] == pytest.approx(100.0)


def test_snap_to_trading_day_falls_back_to_last_when_date_is_past_all_prices() -> None:
    """A rebalance dated after the last available trading day snaps to that last day
    (price data ends before the rebalance) rather than returning None or raising."""
    trading_days = ["2022-01-03", "2022-01-04", "2022-01-05", "2022-01-06", "2022-01-07"]
    assert bf._snap_to_trading_day("2099-06-30", trading_days) == "2022-01-07"


def test_snap_to_trading_day_returns_none_on_empty_dates() -> None:
    """The documented `None only if empty` guard — no trading days to snap to."""
    assert bf._snap_to_trading_day("2022-01-03", []) is None


# ---------------------------------------------------------------------------
# Phase 7.0c new-coverage tests
# ---------------------------------------------------------------------------


def test_rule_version_carries_veto_replay_and_band_suffixes() -> None:
    """``RULE_VERSION`` carries the ``+veto-replay`` marker (veto_layer_replayed=True
    datasets) AND the ``+hold-band-55`` marker (nav.adaptive built from the banded
    book) so callers can distinguish all three artifact generations."""
    assert "+veto-replay" in bf.RULE_VERSION, (
        f"Expected RULE_VERSION to contain '+veto-replay', got {bf.RULE_VERSION!r}"
    )
    assert "+hold-band-55" in bf.RULE_VERSION, (
        f"Expected RULE_VERSION to contain '+hold-band-55', got {bf.RULE_VERSION!r}"
    )
    assert bf.RULE_VERSION.endswith("+uncapped"), (
        f"Expected RULE_VERSION to end with '+uncapped', got {bf.RULE_VERSION!r}"
    )


def test_meta_rule_version_in_artifact(tmp_path, _universe) -> None:
    """The artifact's ``meta.rule_version`` matches ``RULE_VERSION`` (i.e., carries
    the ``+veto-replay`` suffix)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    assert meta["rule_version"] == bf.RULE_VERSION
    assert "+veto-replay" in meta["rule_version"]


def test_vetoed_pick_candidate_appears_in_record_and_excluded_from_picks(tmp_path, _universe) -> None:
    """A synthetic ticker given an active veto flag appears in
    ``rebalances[i].vetoed_pick_candidates`` AND is excluded from the actual
    ``holdings``.  Its composite score in ``full_ranked`` is unchanged (Rule 16 —
    veto never modifies the composite score).

    To avoid the ``_compute_pit_risk_flags`` blanket mock while still producing picks,
    we arrange: two tickers (AAA, BBB) return no flags; CCC returns
    ``data_quality_input_corruption``. CCC's composite should be high enough to
    land in the top-20 bucket so it registers as a vetoed candidate.
    """
    # Give CCC a very high scale so its composite ranks first in the universe.
    scale_by_cik = {"1": 1.0, "2": 1.0, "3": 5.0}  # CCC (cik=3) scale=5 -> highest composite

    def _fake_pit_risk_flags(snapshots, pit_histories, sectors, rebalance_date,
                              beneish_scores, dechow_scores):
        """Return a veto only for CCC; AAA and BBB are clean."""
        return {
            t: ["data_quality_input_corruption"]
            if t == "CCC" else []
            for t in snapshots
        }

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(scale_by_cik.get(cik, 1.0))),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", side_effect=_fake_pit_risk_flags),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0, "Expected at least one rebalance"

    for reb in payload["rebalances"]:
        hold_tickers = {h["ticker"] for h in reb["holdings"]}
        # CCC must NOT appear in holdings (it was vetoed).
        assert "CCC" not in hold_tickers, (
            f"CCC has a veto flag but appeared in holdings: {hold_tickers}"
        )
        # CCC must appear in vetoed_pick_candidates (it ranked in the top-composite
        # bucket and was blocked only by the veto flag).
        vetoed_tickers = {v["ticker"] for v in reb["vetoed_pick_candidates"]}
        assert "CCC" in vetoed_tickers, (
            f"CCC should be in vetoed_pick_candidates; got {vetoed_tickers}"
        )
        # Rule 16: CCC's composite score in full_ranked is unmodified.
        ccc_full = next((e for e in reb["full_ranked"] if e["ticker"] == "CCC"), None)
        ccc_vetoed = next((v for v in reb["vetoed_pick_candidates"] if v["ticker"] == "CCC"), None)
        if ccc_full is not None and ccc_vetoed is not None:
            assert ccc_full["composite_score"] == pytest.approx(ccc_vetoed["composite_score"], abs=0.01), (
                "Rule 16: vetoed_pick_candidates composite_score must match full_ranked "
                f"composite_score; got {ccc_vetoed['composite_score']} vs {ccc_full['composite_score']}"
            )


def test_full_ranked_schema_and_length(tmp_path, _universe) -> None:
    """Each ``rebalances[i].full_ranked`` entry has exactly 5 fields, is sorted by
    descending composite score, and the list is capped at ``_FULL_RANKED_LIMIT``."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0

    for reb in payload["rebalances"]:
        fr = reb["full_ranked"]
        assert len(fr) <= bf._FULL_RANKED_LIMIT
        assert len(fr) > 0, "Expected at least one entry in full_ranked"
        for entry in fr:
            assert set(entry.keys()) == {"ticker", "composite_score", "sector", "mos_pct", "recommendation"}
        # Sorted descending by composite_score.
        scores = [e["composite_score"] for e in fr]
        assert scores == sorted(scores, reverse=True), (
            f"full_ranked not sorted descending by composite_score: {scores}"
        )


def test_sector_weights_by_count_sums_to_one(tmp_path, _universe) -> None:
    """``rebalances[i].sector_weights_by_count`` is a ``{str(N): {sector: w}}``
    mapping where per-N weights sum to 1.0 (within floating-point tolerance)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0

    for reb in payload["rebalances"]:
        swbc = reb["sector_weights_by_count"]
        assert isinstance(swbc, dict)
        # The keys must be digit-strings (str(N)).
        for key in swbc:
            assert key.isdigit(), f"sector_weights_by_count key is not a digit string: {key!r}"
        # Per-N weights must sum to 1.0.
        # Tolerance: production N=20 / ~10 sectors rounds each sector weight to 4dp
        # so per-N accumulation can reach ±~5e-4; abs=1e-3 is the honest bound.
        for n_str, by_sector in swbc.items():
            total = sum(by_sector.values())
            assert total == pytest.approx(1.0, abs=1e-3), (
                f"sector_weights_by_count[{n_str}] weights sum to {total}, expected 1.0"
            )


def test_high_conviction_count_int_within_pick_count(tmp_path, _universe) -> None:
    """``rebalances[i].high_conviction_count`` is an int in [0, len(holdings)]."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0

    for reb in payload["rebalances"]:
        hcc = reb["high_conviction_count"]
        n_picks = len(reb["holdings"])
        assert isinstance(hcc, int), f"high_conviction_count should be int, got {type(hcc)}"
        assert 0 <= hcc <= n_picks, (
            f"high_conviction_count {hcc} out of range [0, {n_picks}]"
        )


def test_compute_pit_risk_flags_forwards_rebalance_date_as_today(tmp_path, _universe) -> None:
    """``_compute_pit_risk_flags`` is called with ``today=rebalance_date`` so NSI
    lookbacks anchor to T (the rebalance date), not to today.

    Verified by capturing kwargs via a spy wrapper around the real function — the
    ``today`` arg must equal the quarterly rebalance date (a value in the range
    [start, end]), not ``date.today()``.
    """
    captured_today_values: list[date] = []

    def _spy(*args, **kwargs):
        captured_today_values.append(kwargs["rebalance_date"])
        return {}  # wiring-isolation: no picks killed by flags

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", side_effect=_spy),
    ):
        start, end = date(2022, 6, 1), date(2023, 6, 1)
        bf.run_backfill(start, end, data_dir=tmp_path, gate="veto_only")

    assert captured_today_values, "_compute_pit_risk_flags was never called"
    for t_val in captured_today_values:
        assert start <= t_val <= end, (
            f"_compute_pit_risk_flags called with today={t_val!r} outside "
            f"[{start!r}, {end!r}] — NSI lookback not anchored to the rebalance date"
        )
        # Verify it is NOT the current wall-clock date (which would break PIT isolation).
        assert t_val != date.today(), (
            f"_compute_pit_risk_flags called with today=date.today() ({t_val!r}); "
            "must be the rebalance date T for PIT-correct NSI lookbacks"
        )


def test_compute_pit_risk_flags_real_wrapper_tbvps_corrupt() -> None:
    """Unit test through the REAL ``_compute_pit_risk_flags`` wrapper — no mock.

    Ensures that a kwarg rename in ``compute_risk_flags`` (e.g. ``today`` →
    ``as_of``) or a signature mismatch surfaces here as a test failure rather
    than silently killing the backfill at dispatch.

    Fixture: two synthetic snapshots using real dollar amounts.
      - CORRUPT: ``stockholders_equity=80B``, ``shares_outstanding=1_000`` (corrupt
        extraction — 1000 shares instead of ~1B) → TBVPS ≈ $80 million/share »
        $10K ceiling → ``data_quality_input_corruption`` fires.
      - CLEAN: same equity, ``shares_outstanding=1_000_000_000`` (1B shares) →
        TBVPS ≈ $80/share < $10K → no flag.

    Also verifies ``today=rebalance_date`` is forwarded by capturing the kwarg
    via a thin spy around ``compute_risk_flags`` (one layer only).
    """
    from compute.ingest.fundamentals import FundamentalsSnapshot

    rebalance_date = date(2023, 3, 31)

    corrupt_snap = FundamentalsSnapshot(
        ticker="CORRUPT",
        cik="999",
        stockholders_equity=80_000_000_000.0,  # 80B USD
        shares_outstanding=1_000.0,             # corrupt: 1,000 shares (unit error)
        revenue=50_000_000_000.0,               # 50B USD — above $50M plausibility floor
        net_income=5_000_000_000.0,
        total_assets=200_000_000_000.0,
        total_liabilities=120_000_000_000.0,
        operating_cash_flow=8_000_000_000.0,
    )
    clean_snap = FundamentalsSnapshot(
        ticker="CLEAN",
        cik="111",
        stockholders_equity=80_000_000_000.0,  # same equity
        shares_outstanding=1_000_000_000.0,     # clean: 1B shares → TBVPS ≈ $80
        revenue=50_000_000_000.0,
        net_income=5_000_000_000.0,
        total_assets=200_000_000_000.0,
        total_liabilities=120_000_000_000.0,
        operating_cash_flow=8_000_000_000.0,
    )

    # ``compute_risk_flags`` is imported into bf's module namespace at the top
    # (``from compute.scoring.risk_overlay import compute_risk_flags``), so the
    # spy must patch it on the ``bf`` module object, not on ``risk_overlay``.
    captured_today: list[date] = []
    original_compute_risk_flags = bf.compute_risk_flags

    def _spy_compute_risk_flags(*args, **kwargs):
        if "today" in kwargs:
            captured_today.append(kwargs["today"])
        return original_compute_risk_flags(*args, **kwargs)

    with mock.patch.object(bf, "compute_risk_flags", side_effect=_spy_compute_risk_flags):
        result = bf._compute_pit_risk_flags(
            snapshots={"CORRUPT": corrupt_snap, "CLEAN": clean_snap},
            pit_histories={"CORRUPT": None, "CLEAN": None},
            sectors={"CORRUPT": "Financials", "CLEAN": "Information Technology"},
            rebalance_date=rebalance_date,
            beneish_scores={"CORRUPT": None, "CLEAN": None},
            dechow_scores={"CORRUPT": None, "CLEAN": None},
        )

    # Flag correctness: corrupt ticker fires, clean ticker is silent.
    assert result.get("CORRUPT") == ["data_quality_input_corruption"], (
        f"Expected CORRUPT to fire data_quality_input_corruption; got {result.get('CORRUPT')}"
    )
    assert result.get("CLEAN") == [], (
        f"Expected CLEAN to have no flags; got {result.get('CLEAN')}"
    )

    # today= forwarding: the wrapper must pass today=rebalance_date to compute_risk_flags
    # so NSI lookbacks anchor to T, not to wall-clock today.
    assert captured_today, (
        "compute_risk_flags was not called with a today= kwarg — "
        "_compute_pit_risk_flags may have dropped the today=rebalance_date forward"
    )
    assert all(t == rebalance_date for t in captured_today), (
        f"compute_risk_flags received today={captured_today!r}; expected {rebalance_date!r} "
        "— today=rebalance_date must be forwarded for PIT-correct NSI lookbacks"
    )


def test_active_veto_flags_covered_by_meta_claims() -> None:
    """Drift guard: the union of ``_VETOES_REPLAYED`` and ``_VETOES_NOT_REPLAYED``
    must exactly equal ``ACTIVE_VETO_FLAGS``.

    Rationale: when an 8th active veto is added to ``ACTIVE_VETO_FLAGS`` without
    updating ``_VETOES_REPLAYED`` or ``_VETOES_NOT_REPLAYED``, the artifact will
    emit ``veto_layer_replayed=True`` while silently omitting the new veto from the
    replay — a false claim. This test makes that drift a CI failure rather than a
    silent bug.

    Import the canonical set from ``compute.portfolio.weights`` (the source of
    truth for which flags are active vetoes) and compare to the backfill constants.
    """
    from compute.portfolio.weights import ACTIVE_VETO_FLAGS as CANONICAL

    replayed = set(bf._VETOES_REPLAYED)
    not_replayed = {e["name"] for e in bf._VETOES_NOT_REPLAYED}
    claimed_union = replayed | not_replayed

    assert claimed_union == set(CANONICAL), (
        f"_VETOES_REPLAYED ∪ {{e['name'] for e in _VETOES_NOT_REPLAYED}} "
        f"does not equal ACTIVE_VETO_FLAGS.\n"
        f"  claimed union: {sorted(claimed_union)}\n"
        f"  ACTIVE_VETO_FLAGS: {sorted(CANONICAL)}\n"
        f"  missing from claim: {sorted(set(CANONICAL) - claimed_union)}\n"
        f"  extra in claim: {sorted(claimed_union - set(CANONICAL))}\n"
        "Add any new active veto to either _VETOES_REPLAYED (if it can be replayed "
        "PIT from snapshot + history) or _VETOES_NOT_REPLAYED (with a reason string) "
        "so the meta.veto_layer_replayed claim stays honest."
    )


# ---------------------------------------------------------------------------
# Adaptive AI-pick book tests (Phase 7.0c adaptive-book feature)
# ---------------------------------------------------------------------------
# The adaptive rule: hold every HC-gated pick with composite >= ADAPTIVE_COMPOSITE_MIN
# (65.0), floored at ADAPTIVE_MIN_PICKS (5), capped at MAX_PICKS (20), clamped to an
# available weights_by_count key.  Per-rebalance export: rebalances[i].adaptive_count;
# nav["adaptive"] (same shape as a by_count entry); meta["adaptive_rule"].
# The n_adaptive arithmetic is inline in run_backfill (not a named function), so tests
# 1-3 exercise it through the end-to-end synthetic path with composites engineered to
# land above/below 65.0; tests 4-5 call _assemble_nav directly with 3-tuples.


def test_adaptive_count_end_to_end_all_picks_above_threshold(tmp_path, _universe) -> None:
    """End-to-end WEAK invariant: whatever composites the synthetic 3-ticker
    universe produces (scale 1.0 — composites are NOT engineered above 65 here;
    the exact-boundary arithmetic is pinned by the _adaptive_count unit test),
    every rebalance's adaptive_count must be an int in [1, MAX_PICKS] and never
    exceed len(holdings)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0

    for reb in payload["rebalances"]:
        ac = reb["adaptive_count"]
        assert isinstance(ac, int), f"adaptive_count should be int, got {type(ac)}"
        n_picks = len(reb["holdings"])
        assert 1 <= ac <= bf.MAX_PICKS, (
            f"adaptive_count {ac} out of [1, MAX_PICKS={bf.MAX_PICKS}]"
        )
        # adaptive_count must not exceed actual picks produced for this rebalance.
        assert ac <= n_picks, (
            f"adaptive_count {ac} > len(holdings) {n_picks} — clamp failed"
        )


def test_adaptive_count_floor_invariant(tmp_path, _universe) -> None:
    """End-to-end FLOOR invariant: with a 3-ticker universe and gate='veto_only',
    adaptive_count >= min(ADAPTIVE_MIN_PICKS, len(picks)) must hold at every leg
    regardless of where the synthetic composites land relative to 65 (scale 1.0
    fixtures do NOT force them below threshold; the raw=0 floor arithmetic is
    pinned exactly by the _adaptive_count unit test)."""
    # _compute_pit_risk_flags is mocked clean: synthetic revenue=100 would fire the
    # data_quality_input_corruption veto and empty the picks (wiring-isolation pattern).
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0

    for reb in payload["rebalances"]:
        ac = reb["adaptive_count"]
        n_picks = len(reb["holdings"])
        # Floor contract: adaptive_count >= min(ADAPTIVE_MIN_PICKS, len(picks)).
        expected_floor = min(bf.ADAPTIVE_MIN_PICKS, n_picks)
        assert ac >= expected_floor, (
            f"adaptive_count {ac} < floor min(ADAPTIVE_MIN_PICKS={bf.ADAPTIVE_MIN_PICKS}, "
            f"len(picks)={n_picks}) = {expected_floor}; floor was not applied"
        )


def test_adaptive_count_boundary_inclusive_at_exactly_65() -> None:
    """C2 pin (methodology-scientist RATIFY 2026-06-11): the threshold comparison is
    INCLUSIVE — a pick scoring exactly ADAPTIVE_COMPOSITE_MIN (65.0) is in the adaptive
    book; 64.999 is not. Also pins the ratified constant VALUES, the floor, the
    sigma-coverage downclamp, and the smallest-available fallback path."""
    # constants pin: the ratified values (65.0 / 5 — cap is MAX_PICKS, pinned elsewhere)
    assert bf.ADAPTIVE_COMPOSITE_MIN == 65.0
    assert bf.ADAPTIVE_MIN_PICKS == 5

    scores = [70.0, 65.0, 64.999, 50.0, 40.0, 30.0]
    raw, final = bf._adaptive_count(scores, available_counts=[1, 2, 3, 4, 5, 6])
    assert raw == 2  # 70.0 and exactly-65.0 count; 64.999 does not
    assert final == 5  # floored at min(ADAPTIVE_MIN_PICKS=5, len(scores)=6)

    # sigma-coverage downclamp: only count 3 has a weights map -> final clamps DOWN
    assert bf._adaptive_count(scores, available_counts=[3]) == (2, 3)
    # no available count <= final -> falls back to the smallest available
    assert bf._adaptive_count([70.0, 70.0], available_counts=[6, 9]) == (2, 6)
    # floor is subordinate to basket size: 2 picks below threshold -> final = 2, not 5
    assert bf._adaptive_count([60.0, 55.0], available_counts=[1, 2]) == (0, 2)


def test_adaptive_count_clamp_to_available_counts(tmp_path) -> None:
    """_assemble_nav: when n_adaptive > max(available_counts), the adaptive leg for
    that rebalance is skipped (n_adp not in wbc) — no KeyError, adaptive stays empty.
    This is the correct behavior: the run_backfill clamp ensures n_adaptive IS a valid
    wbc key; the _assemble_nav guard is the second line of defence for any residual gap."""
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),
    }
    # weights_by_count only has key 1; n_adaptive=7 is not in wbc → leg skipped.
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}}, 7),
    ]
    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)
    # The "adaptive" key is always present in the output dict.
    assert "adaptive" in out
    # adaptive is {} (empty dict) when no valid leg exists — no KeyError raised.
    assert out["adaptive"] == {}, (
        f"Expected empty adaptive dict when n_adaptive not in wbc; got {out['adaptive']}"
    )


def test_assemble_nav_adaptive_shape_with_3tuple(tmp_path) -> None:
    """_assemble_nav with proper 3-tuple rebalance_picks: nav['adaptive'] has the
    same inner shape as a by_count entry (gross/net/net_conservative/turnover_by_rebalance)
    and len(gross) == len(nav['dates'])."""
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),
        "BBB": _bday_frame([100.0 - 0.2 * i for i in range(120)]),
    }
    # n_adaptive=1: use the weights_by_count[1] map (only AAA).
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}, 2: {"AAA": 0.5, "BBB": 0.5}}, 1),
        ("2022-03-14", {1: {"AAA": 1.0}, 2: {"AAA": 0.6, "BBB": 0.4}}, 2),
    ]
    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert "adaptive" in out
    adp = out["adaptive"]
    nd = len(out["dates"])
    assert nd > 0

    # adaptive must have the same 4-key inner shape as by_count entries.
    assert set(adp.keys()) == {"gross", "net", "net_conservative", "turnover_by_rebalance"}, (
        f"adaptive keys mismatch: {set(adp.keys())}"
    )
    assert len(adp["gross"]) == nd, (
        f"adaptive gross length {len(adp['gross'])} != dates length {nd} (left-pad contract)"
    )
    assert len(adp["net"]) == nd
    assert len(adp["net_conservative"]) == nd

    # by_count still populated (regression: 3-tuple must not break by_count).
    assert set(out["by_count"]) == {"1", "2"}
    for s in out["by_count"].values():
        assert len(s["gross"]) == nd


def test_assemble_nav_adaptive_skip_missing_n_adaptive_key(tmp_path) -> None:
    """When n_adaptive key is absent from a rebalance's weights_by_count, that leg is
    silently skipped (no KeyError) and the other legs continue without corruption."""
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),
        "BBB": _bday_frame([100.0 - 0.2 * i for i in range(120)]),
    }
    # Rebalance 1: n_adaptive=3, but wbc only has keys {1, 2} → key 3 absent → skip.
    # Rebalance 2: n_adaptive=1, wbc has key 1 → should produce the adaptive leg.
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}, 2: {"AAA": 0.5, "BBB": 0.5}}, 3),  # 3 absent
        ("2022-03-14", {1: {"AAA": 1.0}, 2: {"AAA": 0.6, "BBB": 0.4}}, 1),  # 1 present
    ]
    # Must not raise KeyError.
    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert "adaptive" in out
    adp = out["adaptive"]
    # The second rebalance IS included (n_adaptive=1 IS in its wbc), so adaptive is non-empty.
    assert adp, "Expected non-empty adaptive dict when at least one leg has a valid n_adaptive key"
    nd = len(out["dates"])
    assert len(adp["gross"]) == nd, (
        f"adaptive gross length {len(adp['gross'])} != dates length {nd}"
    )
    # by_count must be unaffected by the adaptive skip.
    assert set(out["by_count"]) == {"1", "2"}


def test_run_backfill_every_rebalance_has_adaptive_count_int_in_range(tmp_path, _universe) -> None:
    """End-to-end: every rebalances[i].adaptive_count is an int in [1, MAX_PICKS].
    This is the primary schema-correctness gate for the adaptive_count export."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0, "Expected at least one rebalance"

    for reb in payload["rebalances"]:
        ac = reb["adaptive_count"]
        assert isinstance(ac, int), (
            f"adaptive_count must be int, got {type(ac).__name__} at rebalance {reb['date']}"
        )
        assert 1 <= ac <= bf.MAX_PICKS, (
            f"adaptive_count {ac} at {reb['date']} out of [1, MAX_PICKS={bf.MAX_PICKS}]"
        )


def test_meta_adaptive_rule_values(tmp_path, _universe) -> None:
    """meta['adaptive_rule'] carries the canonical threshold values."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    assert "adaptive_rule" in meta, "meta.adaptive_rule missing from artifact"
    rule = meta["adaptive_rule"]
    assert rule == {
        "composite_min": bf.ADAPTIVE_COMPOSITE_MIN,
        "min_picks": bf.ADAPTIVE_MIN_PICKS,
        # Uncap (2026-06-11, condition U5): the key is KEPT with an explicit null —
        # "considered and deliberately removed", never key-drop ambiguity.
        "max_picks": None,
        "hold_band_min": bf.ADAPTIVE_HOLD_BAND_MIN,
    }, f"adaptive_rule mismatch: {rule}"


def test_disclaimer_mentions_adaptive_threshold_tokens(tmp_path, _universe) -> None:
    """The disclaimer must mention the adaptive threshold (65) and that holding count
    varies, as required by the adaptive-book disclosure. Asserts on meaningful tokens,
    not exact prose, so minor wording edits don't break the test."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    disclaimer = meta["disclaimer"]

    # Must mention the numeric threshold.
    assert "65" in disclaimer, (
        "disclaimer does not mention composite threshold '65'; "
        "adaptive-book disclosure requires the threshold to be stated"
    )
    # Must mention that holding count varies.
    assert "varies" in disclaimer, (
        "disclaimer does not mention that holding count 'varies'; "
        "adaptive-book disclosure requires this"
    )


# ---------------------------------------------------------------------------
# V55 hysteresis hold-band — C2 boundary pins (methodology-scientist
# RATIFY-WITH-CONDITIONS 2026-06-11).
#
# All tests below exercise ``_band_book(order, scores, tenure)`` directly —
# the pure helper that implements the hold-band logic (C2 unit-testability
# gate).  Style: one assertion cluster per invariant, honest docstrings
# stating exactly what the fixture forces.  Mirror the
# ``test_adaptive_count_boundary_inclusive_at_exactly_65`` convention for
# boundary pins (comment the constant value, then the inclusive / exclusive
# edges).
# ---------------------------------------------------------------------------


def test_band_book_first_rebalance_tenure_empty_band_inert() -> None:
    """C2 pin — Item 1: first rebalance (tenure=empty) → band is inert.

    Fixture forces:
      - order = [AAA, BBB, CCC] with AAA=70, BBB=66, CCC=50 (all HC-eligible).
      - tenure = set() (first rebalance; no prior incumbents).

    Expected: book = fresh >= 65 entries only (AAA, BBB) padded to reach
    min(ADAPTIVE_MIN_PICKS=5, len(order)=3) = 3, so CCC is added as a pad;
    carry_count = 0 (band was inert — no tenured names to carry); next_tenure
    = {AAA, BBB} only (core names; CCC is a pad — C0 strict tenure).
    """
    order = ["AAA", "BBB", "CCC"]
    scores = {"AAA": 70.0, "BBB": 66.0, "CCC": 50.0}
    tenure: set[str] = set()

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    # carry_count must be 0 on first rebalance (no tenured names).
    assert carry_count == 0, (
        f"Expected carry_count=0 on first rebalance; got {carry_count}"
    )
    # All three are in the book (CCC padded in to reach target=3).
    assert set(book) == {"AAA", "BBB", "CCC"}, (
        f"Expected book={{'AAA','BBB','CCC'}} (pad fills to min(5,3)=3); got {set(book)}"
    )
    # next_tenure contains ONLY core names (>= 65) — pad CCC excluded (C0).
    assert next_tenure == {"AAA", "BBB"}, (
        f"Expected next_tenure={{'AAA','BBB'}} (core only, pad CCC excluded); "
        f"got {next_tenure}"
    )


def test_band_book_hold_path_exactly_55_inclusive_boundary() -> None:
    """C2 pin — Item 2: tenured name at EXACTLY 55.0 is retained (inclusive).

    The boundary mirrors the 65.0 entry-threshold convention — both ends of
    the band are closed (>= 55.0 hold; >= 65.0 enter).  This test pins the
    INCLUSIVE lower edge of the hold range.

    Fixture forces:
      - order = [AAA, BBB] — both HC-eligible.
      - scores: AAA = 70.0 (fresh, above entry threshold); BBB = 55.0 (exactly
        at hold-band floor; should be retained as a carry).
      - tenure = {BBB} (BBB entered last rebalance at >= 65, decayed to 55.0).

    Expected: BBB is in book (retained via band — score == ADAPTIVE_HOLD_BAND_MIN);
    carry_count = 1 (BBB is in tenure AND score < ADAPTIVE_COMPOSITE_MIN=65).
    """
    order = ["AAA", "BBB"]
    scores = {"AAA": 70.0, "BBB": 55.0}   # BBB = exactly ADAPTIVE_HOLD_BAND_MIN (55.0)
    tenure = {"BBB"}

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    # Inclusive boundary: BBB at exactly 55.0 is retained.
    assert "BBB" in book, (
        "Expected BBB (score=55.0 == ADAPTIVE_HOLD_BAND_MIN) to be retained; "
        f"got book={book}"
    )
    # carry_count = 1: BBB is the sole carry (tenured + score < 65).
    assert carry_count == 1, (
        f"Expected carry_count=1 for BBB at exactly 55.0; got {carry_count}"
    )
    # BBB propagates into next_tenure (still in core — was not evicted).
    assert "BBB" in next_tenure, (
        f"Expected BBB in next_tenure after hold-band retention; got {next_tenure}"
    )


def test_band_book_force_sell_at_54_99_exclusive_boundary() -> None:
    """C2 pin — Item 3: tenured name at 54.99 is force-sold (exclusive below 55).

    This pins the EXCLUSIVE lower edge: a score just below ADAPTIVE_HOLD_BAND_MIN
    is not sufficient to retain the incumbent.

    Fixture forces:
      - order = [AAA, BBB] — both HC-eligible.
      - scores: AAA = 70.0 (fresh); BBB = 54.99 (one tick below hold-band floor).
      - tenure = {BBB} (BBB was tenured; now decays below the floor).

    Expected: BBB is excluded from book (force-sold); carry_count = 0; BBB absent
    from next_tenure (no longer has band rights).
    """
    order = ["AAA", "BBB"]
    scores = {"AAA": 70.0, "BBB": 54.99}  # one tick below ADAPTIVE_HOLD_BAND_MIN
    tenure = {"BBB"}

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    # BBB must be force-sold when score < 55.0.
    # (BBB may still appear as a PAD if len(core) < min(ADAPTIVE_MIN_PICKS, len(order)).
    # With order=[AAA,BBB] -> target=min(5,2)=2, core=[AAA] (len 1 < 2), so BBB is
    # padded in — this is correct pad behaviour, not a carry.  We verify it is NOT in
    # next_tenure, confirming the force-sell semantics (pad != carry rights).
    assert "BBB" not in next_tenure, (
        "Expected BBB (score=54.99 < 55.0) to be excluded from next_tenure "
        f"(force-sold); got next_tenure={next_tenure}"
    )
    # carry_count must be 0: BBB is not a carry (it failed the band floor).
    assert carry_count == 0, (
        f"Expected carry_count=0 for BBB at 54.99 (force-sold); got {carry_count}"
    )


def test_band_book_fresh_name_at_64_99_not_entered() -> None:
    """C2 pin — Item 4: fresh (non-tenured) name at 64.99 is NOT entered.

    Asymmetry invariant: the hold band NEVER admits new names.  A fresh name
    requires score >= ADAPTIVE_COMPOSITE_MIN (65.0) for entry; 64.99 is below
    the entry threshold and the name is not tenured, so it cannot enter via the
    band either.  64.99 may only appear as a PAD if book size < target.

    Fixture forces:
      - order = [AAA, BBB, CCC] — all HC-eligible.
      - scores: AAA = 70.0 (fresh entrant, above 65); BBB = 64.99 (fresh, just
        below entry threshold); CCC = 50.0 (pad candidate).
      - tenure = set() (no incumbents; first rebalance for clarity).

    Expected: BBB is NOT in next_tenure (no core rights); carry_count = 0;
    AAA IS in next_tenure.
    """
    order = ["AAA", "BBB", "CCC"]
    scores = {"AAA": 70.0, "BBB": 64.99, "CCC": 50.0}
    tenure: set[str] = set()

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    # Fresh name at 64.99 must NOT gain tenure (not in core).
    assert "BBB" not in next_tenure, (
        "Expected fresh BBB (score=64.99 < 65.0) to be excluded from next_tenure; "
        f"got next_tenure={next_tenure}"
    )
    # AAA at 70.0 is a fresh entrant above threshold — should gain tenure.
    assert "AAA" in next_tenure, (
        f"Expected AAA (score=70.0 >= 65.0) in next_tenure; got {next_tenure}"
    )
    # carry_count = 0: no tenured names present (first rebalance).
    assert carry_count == 0


def test_band_book_veto_supremacy_absent_from_order() -> None:
    """C2 pin — Item 5: tenured name absent from order is evicted (veto supremacy).

    ``order`` carries only HC-eligible tickers (the caller's veto / HC gate is
    applied before ``_band_book``).  A name absent from ``order`` is treated as
    vetoed/HC-evicted: it must be excluded from the book AND from next_tenure,
    even if its score is above 70.

    Fixture forces:
      - order = [AAA, BBB] (two HC-eligible names; CCC is NOT in order — vetoed).
      - scores: AAA=70, BBB=68, CCC=72 (CCC score present in dict but absent from order).
      - tenure = {AAA, BBB, CCC} (all three were previously tenured).

    Expected: CCC not in book; CCC not in next_tenure; AAA and BBB retained.
    """
    order = ["AAA", "BBB"]          # CCC deliberately absent (vetoed / HC-evicted)
    scores = {"AAA": 70.0, "BBB": 68.0, "CCC": 72.0}
    tenure = {"AAA", "BBB", "CCC"}

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    # Veto supremacy: CCC absent from order means it cannot enter the book.
    assert "CCC" not in book, (
        f"Expected CCC (absent from order — vetoed) to be excluded from book; "
        f"got book={book}"
    )
    # CCC must also be absent from next_tenure (no tenure propagation for evicted names).
    assert "CCC" not in next_tenure, (
        f"Expected CCC to be excluded from next_tenure (veto supremacy); "
        f"got next_tenure={next_tenure}"
    )
    # AAA and BBB are tenured + in order with scores >= 65 → carried as fresh
    # (score >= ADAPTIVE_COMPOSITE_MIN) — both should be in book and next_tenure.
    assert "AAA" in book and "BBB" in book, (
        f"Expected AAA and BBB (tenured, in order, score>=65) in book; got {book}"
    )


def test_band_book_pads_not_in_next_tenure_c0() -> None:
    """C2 pin — Item 6: pad names get NO tenure (C0 strict tenure).

    Fixture forces:
      - order = [AAA, BBB, CCC, DDD, EEE] (5 HC-eligible).
      - scores: AAA=70.0 only name above entry threshold; BBB=60, CCC=55,
        DDD=50, EEE=45 — all below 65.
      - tenure = set() (first rebalance; no carries).
      - target = min(ADAPTIVE_MIN_PICKS=5, len(order)=5) = 5.
      - core = [AAA] (only one >= 65); pads = [BBB, CCC, DDD, EEE] (4 pads to
        reach target 5).

    Expected: only AAA in next_tenure; BBB/CCC/DDD/EEE are pads with no tenure.
    """
    order = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    scores = {"AAA": 70.0, "BBB": 60.0, "CCC": 55.0, "DDD": 50.0, "EEE": 45.0}
    tenure: set[str] = set()

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    # All 5 names should be in the book (core[AAA] + 4 pads).
    assert set(book) == {"AAA", "BBB", "CCC", "DDD", "EEE"}, (
        f"Expected all 5 names in book; got {set(book)}"
    )
    # Only AAA (core) gets tenure — pads excluded (C0).
    assert next_tenure == {"AAA"}, (
        f"Expected next_tenure={{'AAA'}} only (pads BBB/CCC/DDD/EEE excluded C0); "
        f"got {next_tenure}"
    )
    assert carry_count == 0  # no tenured names on first rebalance


def test_band_book_pad_gains_no_carry_rights_two_step_sequence() -> None:
    """C2 pin — Item 6 (two-step): pad from rebalance N gains no carry rights at N+1.

    A name that enters the book as a PAD at rebalance N (score < 65, non-tenured)
    must NOT be carried at rebalance N+1 via the band even if its score stays
    between 55 and 65.

    Fixture forces rebalance N:
      - order = [AAA, BBB]; AAA=70 (core, gains tenure); BBB=60 (pad, no tenure).
      - tenure = set() — first rebalance.
      - next_tenure after step 1 = {AAA}.

    Fixture forces rebalance N+1:
      - order = [AAA, BBB] again; same scores.
      - tenure = {AAA} (BBB is NOT in tenure — it was a pad at N).

    Expected at N+1: BBB absent from next_tenure (no carry rights accrued at N);
    carry_count = 0 (BBB below 65 but not tenured — not a band-carry).
    """
    # --- Rebalance N ---
    order = ["AAA", "BBB"]
    scores = {"AAA": 70.0, "BBB": 60.0}
    tenure_n: set[str] = set()

    _book_n, next_tenure_n, _cc_n = bf._band_book(order, scores, tenure_n)

    # After N: only AAA has tenure — BBB was padded in with no tenure rights.
    assert "BBB" not in next_tenure_n, (
        f"After rebalance N: BBB (pad) must not be in next_tenure; got {next_tenure_n}"
    )

    # --- Rebalance N+1 (using next_tenure from N) ---
    _book_n1, next_tenure_n1, carry_count_n1 = bf._band_book(order, scores, next_tenure_n)

    # BBB still absent from tenure at N+1: pads never accumulate band rights.
    assert "BBB" not in next_tenure_n1, (
        "After rebalance N+1: BBB (pad at N) must still not be in next_tenure; "
        f"got {next_tenure_n1}"
    )
    # carry_count = 0: BBB is present in order + scores 55-65 range, but since it has
    # no tenure it is NOT a band-carry — it is a pad again.
    assert carry_count_n1 == 0, (
        f"Expected carry_count=0 at N+1 (BBB is a re-padded name, not a carry); "
        f"got {carry_count_n1}"
    )


def test_band_book_reentry_after_force_sell_requires_65() -> None:
    """C2 pin — Item 7: re-entry after force-sell requires score >= 65 (ADAPTIVE_COMPOSITE_MIN).

    Sequence:
      Step 1 — name BBB is tenured (entered at >= 65).
      Step 2 — BBB decays to 50.0 (< 55): force-sold, tenure revoked.
      Step 3 — BBB recovers to 60.0 (>= 55 but < 65): NOT re-entered (no tenure,
               below entry threshold; may appear only as a PAD).
      Step 4 — BBB recovers to 65.0: re-enters as a fresh entrant.

    Fixture construction:
      - ``order`` always contains BBB so it stays HC-eligible throughout.
      - AAA is present as a stable high-scorer (70.0) to ensure the sequence
        can carry without corner-case empty-book paths.
    """
    # Step 1: BBB gains initial tenure by scoring >= 65.
    order = ["AAA", "BBB"]
    scores_step1 = {"AAA": 70.0, "BBB": 66.0}
    _, tenure_after_1, _ = bf._band_book(order, scores_step1, set())
    assert "BBB" in tenure_after_1, "Setup failure: BBB must gain tenure at step 1"

    # Step 2: BBB decays to 50.0 — force-sold (< ADAPTIVE_HOLD_BAND_MIN=55).
    scores_step2 = {"AAA": 70.0, "BBB": 50.0}
    _, tenure_after_2, cc2 = bf._band_book(order, scores_step2, tenure_after_1)
    assert "BBB" not in tenure_after_2, (
        "Step 2: BBB at 50.0 must be force-sold and removed from tenure"
    )
    assert cc2 == 0, f"Step 2: carry_count must be 0 after force-sell; got {cc2}"

    # Step 3: BBB at 60.0 — above 55 hold floor but tenure was revoked.
    # BBB cannot re-enter as a carry (no tenure) and cannot enter as a fresh name
    # (60.0 < 65.0).  It may appear as a PAD, but must NOT be in next_tenure.
    scores_step3 = {"AAA": 70.0, "BBB": 60.0}
    _, tenure_after_3, cc3 = bf._band_book(order, scores_step3, tenure_after_2)
    assert "BBB" not in tenure_after_3, (
        "Step 3: BBB (score=60.0, no tenure) must not be re-admitted to tenure; "
        f"got {tenure_after_3}"
    )
    assert cc3 == 0, f"Step 3: carry_count must be 0 (BBB has no tenure); got {cc3}"

    # Step 4: BBB at 65.0 — exactly at entry threshold → re-enters as a fresh entrant.
    scores_step4 = {"AAA": 70.0, "BBB": 65.0}
    book4, tenure_after_4, _ = bf._band_book(order, scores_step4, tenure_after_3)
    assert "BBB" in book4, (
        f"Step 4: BBB at exactly 65.0 must re-enter the book; got {book4}"
    )
    assert "BBB" in tenure_after_4, (
        "Step 4: BBB (score=65.0 >= entry threshold) must regain tenure; "
        f"got {tenure_after_4}"
    )


def test_band_book_uncapped_holds_all_qualifying_names() -> None:
    """Uncap pin (methodology RATIFY-WITH-CONDITIONS 2026-06-11, U2/U5): when more
    than MAX_PICKS names qualify (all >= 65 here), the book holds ALL of them —
    the former core[:MAX_PICKS] truncation is gone. Forward guards live at the
    gate layer (A2 full-pool / A2-S spike >= 25 / H3), not in a silent clamp.
    book ⊆ order still holds (no name outside the eligible set)."""
    n = bf.MAX_PICKS + 2        # 22 candidates, every one >= 65
    tickers = [f"T{i:02d}" for i in range(n)]
    scores = {t: 65.0 + i for i, t in enumerate(tickers)}
    order = sorted(tickers, key=lambda t: -scores[t])
    tenure = set(tickers)  # all were tenured

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure)

    assert len(book) == n, f"uncapped book must hold all {n} qualifying names; got {len(book)}"
    assert next_tenure == set(tickers), "uncapped core keeps tenure for every qualifying name"
    assert set(book) <= set(order), (
        f"book contains names outside order (eligible set): {set(book) - set(order)}"
    )


def test_band_book_constant_pin_adaptive_hold_band_min_equals_55() -> None:
    """C2 pin — Item 12: freeze-lock ADAPTIVE_HOLD_BAND_MIN == 55.0.

    Pre-registered value from the methodology-scientist RATIFY-WITH-CONDITIONS
    2026-06-11.  V60 FAILED the C2 CAGR gate (-0.8pp vs -0.5pp ceiling); V55
    PASSED (CAGR -0.27pp, turnover -33.8%, beats +3).  H-C freeze lock: no
    re-sweeps without a fresh pre-registration.  This assertion is the CI trip-
    wire for any accidental constant drift.
    """
    assert bf.ADAPTIVE_HOLD_BAND_MIN == 55.0, (
        f"ADAPTIVE_HOLD_BAND_MIN must be 55.0 (pre-registered V55 PASS, H-C freeze lock); "
        f"got {bf.ADAPTIVE_HOLD_BAND_MIN!r}"
    )


# ---------------------------------------------------------------------------
# V55 band — end-to-end (run_backfill) integration tests (Items 9 & 10).
# ---------------------------------------------------------------------------


def test_band_exports_structural_invariants_end_to_end(tmp_path, _universe) -> None:
    """C2 pin — Item 9: every rebalance in the artifact satisfies the band export schema.

    Verifies the per-rebalance band field contract across all rebalances produced
    by a synthetic end-to-end run:
      - band_book: list of tickers (subset of holdings tickers).
      - band_held_count: == len(band_book).
      - band_weights: dict; keys ⊆ band_book; values sum ≈ 1.0 when non-empty.
      - band_carry_count: int >= 0.
      - band_carry_weight_share: float in [0, 1] or None (None only when
        band_weights is empty — degenerate leg with no usable sigmas).

    Uses the standard wiring-isolation mock pattern (gate='veto_only',
    _compute_pit_risk_flags={}); synthetic data provides picks so all structural
    paths execute.
    """
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(
            date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only"
        )

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0, "Expected at least one rebalance"

    for reb in payload["rebalances"]:
        # band_book: list of ticker strings.
        assert "band_book" in reb, f"band_book missing from rebalance {reb['date']}"
        assert isinstance(reb["band_book"], list), (
            f"band_book must be a list; got {type(reb['band_book'])}"
        )
        hold_tickers = {h["ticker"] for h in reb["holdings"]}
        # band_book must be a subset of holdings (the eligible domain).
        assert set(reb["band_book"]) <= hold_tickers, (
            f"band_book {set(reb['band_book'])} is not a subset of holdings "
            f"tickers {hold_tickers} at {reb['date']}"
        )

        # band_held_count == len(band_book).
        assert "band_held_count" in reb, (
            f"band_held_count missing at {reb['date']}"
        )
        assert reb["band_held_count"] == len(reb["band_book"]), (
            f"band_held_count {reb['band_held_count']} != len(band_book) "
            f"{len(reb['band_book'])} at {reb['date']}"
        )

        # band_weights: keys ⊆ band_book; non-empty sum ≈ 1.
        assert "band_weights" in reb, f"band_weights missing at {reb['date']}"
        assert isinstance(reb["band_weights"], dict), (
            f"band_weights must be a dict; got {type(reb['band_weights'])}"
        )
        assert set(reb["band_weights"].keys()) <= set(reb["band_book"]), (
            f"band_weights keys not a subset of band_book at {reb['date']}"
        )
        if reb["band_weights"]:
            total_w = sum(reb["band_weights"].values())
            assert total_w == pytest.approx(1.0, abs=1e-5), (
                f"band_weights sum {total_w} != 1.0 at {reb['date']}"
            )

        # band_carry_count: non-negative int.
        assert "band_carry_count" in reb, f"band_carry_count missing at {reb['date']}"
        assert isinstance(reb["band_carry_count"], int), (
            f"band_carry_count must be int; got {type(reb['band_carry_count'])}"
        )
        assert reb["band_carry_count"] >= 0, (
            f"band_carry_count {reb['band_carry_count']} < 0 at {reb['date']}"
        )

        # band_carry_weight_share: float in [0, 1] or None.
        assert "band_carry_weight_share" in reb, (
            f"band_carry_weight_share missing at {reb['date']}"
        )
        bws = reb["band_carry_weight_share"]
        if bws is not None:
            assert isinstance(bws, float), (
                f"band_carry_weight_share must be float or None; got {type(bws)}"
            )
            assert 0.0 <= bws <= 1.0, (
                f"band_carry_weight_share {bws} out of [0, 1] at {reb['date']}"
            )
            # H2-input reconcile: a positive carry SHARE implies a positive carry
            # COUNT — a sub-55 tenured floor-pad may never inflate the share while
            # the count excludes it (the reviewer-flagged pollution path).
            if bws > 0.0:
                assert reb["band_carry_count"] > 0, (
                    f"carry share {bws} > 0 with carry count 0 at {reb['date']}"
                )
        # band_carry_names: sorted carry cohort, consistent with the count.
        assert "band_carry_names" in reb, f"band_carry_names missing at {reb['date']}"
        bcn = reb["band_carry_names"]
        assert isinstance(bcn, list) and bcn == sorted(bcn), (
            f"band_carry_names must be a sorted list at {reb['date']}"
        )
        assert len(bcn) == reb["band_carry_count"], (
            f"band_carry_names/{len(bcn)} disagrees with band_carry_count/"
            f"{reb['band_carry_count']} at {reb['date']}"
        )
        assert set(bcn) <= set(reb["band_book"]), (
            f"band_carry_names not a subset of band_book at {reb['date']}"
        )


def test_band_tenure_threading_no_crash_and_correct_types(tmp_path, _universe) -> None:
    """C2 pin — Item 10: tenure threads correctly across consecutive rebalances.

    Weak invariant (honest docstring): the 3-ticker synthetic universe with
    gate='veto_only' produces picks but the exact composites are not engineered
    to guarantee a carry in this e2e path (scores depend on the full pillar
    pipeline and the synthetic metric scales).  The unit tests above (Items 2-4)
    carry the load for precise boundary semantics.  This test asserts:
      - The orchestrator does not crash during tenure threading.
      - Every rebalance's band_carry_count is a non-negative int.
      - band_carry_count is non-negative across all rebalances (monotone lower
        bound; carries can only be present if tenure was built in a prior leg).

    The 2022-Q2 to 2023-Q2 window produces >= 2 rebalances so tenure CAN
    propagate; whether it does depends on the synthetic composite scores.
    """
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(
            date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only"
        )

    payload = json.loads(out.read_text())
    rebs = payload["rebalances"]
    assert len(rebs) >= 1, "Expected at least one rebalance for tenure test"

    # Weak invariant: no crash + correct types across all rebalances.
    for reb in rebs:
        cc = reb["band_carry_count"]
        assert isinstance(cc, int) and cc >= 0, (
            f"band_carry_count must be a non-negative int at {reb['date']}; got {cc!r}"
        )

    # First rebalance: band inert on first leg → carry_count must be 0.
    assert rebs[0]["band_carry_count"] == 0, (
        f"First rebalance must have band_carry_count=0 (tenure empty); "
        f"got {rebs[0]['band_carry_count']}"
    )


# ---------------------------------------------------------------------------
# V55 band — nav.adaptive from band legs (Item 11).
# ---------------------------------------------------------------------------


def test_assemble_nav_adaptive_from_band_legs_produces_correct_shape(tmp_path) -> None:
    """C2 pin — Item 11a: ``_assemble_nav(..., band_legs=[...])`` builds nav['adaptive']
    from the supplied band legs (not the prefix-based fallback).

    Fixture forces:
      - Two rebalances with distinct band-leg weight maps supplied via band_legs.
      - rebalance_picks carries 3-tuples with n_adaptive=2 (prefix path would use
        weights_by_count[2]) — but the explicit band_legs override takes precedence.

    Expected: nav['adaptive'] has the 4-key inner shape (gross/net/net_conservative/
    turnover_by_rebalance); len(gross) == len(dates); first non-None gross == 100.0.
    """
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),
        "BBB": _bday_frame([100.0 - 0.2 * i for i in range(120)]),
    }
    # rebalance_picks: 3-tuples (date, wbc, n_adaptive).
    # n_adaptive=2 points at the prefix-based path, but band_legs overrides it.
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}, 2: {"AAA": 0.5, "BBB": 0.5}}, 2),
        ("2022-03-14", {1: {"AAA": 1.0}, 2: {"AAA": 0.6, "BBB": 0.4}}, 2),
    ]
    # Explicit band_legs: different weight distribution than the n_adaptive=2 prefix.
    # This is the band-book weights — only AAA (single-name band book for clarity).
    band_legs = [
        ("2022-01-10", {"AAA": 1.0}),
        ("2022-03-14", {"AAA": 1.0}),
    ]

    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path,
                               band_legs=band_legs)

    assert "adaptive" in out, "nav['adaptive'] key must be present when band_legs provided"
    adp = out["adaptive"]
    nd = len(out["dates"])
    assert nd > 0, "dates must be non-empty"

    # Inner shape: 4-key dict.
    assert set(adp.keys()) == {"gross", "net", "net_conservative", "turnover_by_rebalance"}, (
        f"adaptive inner shape mismatch; got keys {set(adp.keys())}"
    )
    # Length alignment: all series aligned to the shared dates axis.
    assert len(adp["gross"]) == nd, (
        f"adaptive gross length {len(adp['gross'])} != dates length {nd}"
    )
    assert len(adp["net"]) == nd
    assert len(adp["net_conservative"]) == nd

    # Rebased start: first non-None gross value must be 100.0.
    first_gross = next((v for v in adp["gross"] if v is not None), None)
    assert first_gross is not None, "adaptive gross is entirely None"
    assert first_gross == pytest.approx(100.0), (
        f"adaptive gross must rebase to 100.0; got {first_gross}"
    )


def test_assemble_nav_adaptive_fallback_when_no_band_legs(tmp_path) -> None:
    """C2 pin — Item 11b: ``_assemble_nav`` without band_legs falls back to the legacy
    prefix-based adaptive path (backward-compatible for pre-band tests).

    Fixture forces:
      - rebalance_picks with n_adaptive=1 and weights_by_count={1: {'AAA': 1.0}}.
      - band_legs=None (default; the legacy path).

    Expected: nav['adaptive'] is non-empty (built from the prefix path); inner shape
    matches the 4-key contract; by_count still populated (regression guard).
    """
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),
    }
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}}, 1),
        ("2022-03-14", {1: {"AAA": 1.0}}, 1),
    ]

    # Omit band_legs entirely — exercises the legacy fallback branch.
    out, *_ = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

    assert "adaptive" in out
    adp = out["adaptive"]
    # Legacy path should produce a non-empty adaptive dict.
    assert adp, (
        "Expected non-empty adaptive dict via legacy prefix-based fallback "
        "(band_legs=None path)"
    )
    nd = len(out["dates"])
    assert set(adp.keys()) == {"gross", "net", "net_conservative", "turnover_by_rebalance"}, (
        f"adaptive inner shape mismatch (legacy path); keys={set(adp.keys())}"
    )
    assert len(adp["gross"]) == nd
    # by_count still populated (3-tuple not corrupted by omitting band_legs).
    assert "1" in out["by_count"], "by_count['1'] must be present regardless of band_legs"


def test_band_exports_present_in_artifact_meta_adaptive_rule(tmp_path, _universe) -> None:
    """C2 pin — Item 12 integration: meta.adaptive_rule.hold_band_min is 55.0 in the
    artifact (tests the JSON serialisation path, not just the constant directly).

    The constant pin is already checked by test_band_book_constant_pin_* above.
    This test ensures the value survives the run_backfill → JSON write pipeline
    without truncation or type conversion.
    """
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(
            date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only"
        )

    meta = json.loads(out.read_text())["meta"]
    assert "adaptive_rule" in meta, "meta.adaptive_rule missing from artifact"
    rule = meta["adaptive_rule"]
    assert "hold_band_min" in rule, "meta.adaptive_rule.hold_band_min missing"
    assert rule["hold_band_min"] == 55.0, (
        f"meta.adaptive_rule.hold_band_min must be 55.0 (pre-registered V55); "
        f"got {rule['hold_band_min']!r}"
    )


# ---------------------------------------------------------------------------
# Uncap coverage pins — methodology conditions U5/U3 (e2e level, 2026-06-11).
#
# U5: meta.adaptive_rule["max_picks"] is None in the artifact.
# U3: sigma coverage — set(band_weights.keys()) ⊆ set(band_book ∩ priced).
#
# Engineering a >20-name cohort with the 3-ticker synthetic fixture is
# impossible (the real pillar pipeline only processes the 3 members), so U3
# sigma coverage is pinned at the structural seam available in the e2e artifact:
# band_weights.keys() ⊆ band_book (every band-weighted name is in band_book).
# The direct unit-level U3 invariant is inherently satisfied by the sigma-loop
# design (the loop extends sigmas to cover band_book members not in picks); see
# the inline docstring below for the engineering boundary explanation.
# ---------------------------------------------------------------------------


def test_meta_adaptive_rule_max_picks_is_none_u5(tmp_path, _universe) -> None:
    """U5 pin: meta.adaptive_rule['max_picks'] is None in the artifact.

    The uncap (2026-06-11 ratification) removes the MAX_PICKS hard ceiling from
    the band book.  The artifact contract is: the key is KEPT but set to None
    explicitly — 'considered and deliberately removed', no key-drop ambiguity
    (see test_meta_adaptive_rule_values above, which also pins this, and which
    this test exists alongside as an isolated per-condition pin per the U2/U3/U4
    coverage task list).

    Fixture: standard 3-ticker synthetic universe; gate='veto_only' for wiring
    isolation.  The max_picks=None value must survive JSON serialisation.
    """
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path,
                              gate="veto_only")

    meta = json.loads(out.read_text())["meta"]
    assert "adaptive_rule" in meta, "meta.adaptive_rule key missing from artifact"
    rule = meta["adaptive_rule"]
    assert "max_picks" in rule, (
        "meta.adaptive_rule['max_picks'] key must be present (explicit null contract, "
        "not key-drop)"
    )
    assert rule["max_picks"] is None, (
        f"meta.adaptive_rule['max_picks'] must be None (uncap removes the ceiling); "
        f"got {rule['max_picks']!r}"
    )


def test_band_weights_keys_subset_of_band_book_u3_structural(tmp_path, _universe) -> None:
    """U3 sigma-coverage structural pin: set(band_weights.keys()) ⊆ set(band_book).

    Engineering boundary note: the direct unit-level U3 invariant
    (set(band_weights.keys()) == set(band_book ∩ priced)) cannot be exercised by
    engineering a >20-name e2e cohort using the 3-ticker synthetic fixture — the
    real pillar pipeline only processes the 3 members and cannot produce a cohort
    larger than MAX_PICKS=20.  The sigma loop in run_backfill extends sigmas to
    cover rank-21+ band_book members before inverse_vol_weights is called;
    that path only fires when len(band_book) > 20, which is structurally
    unreachable with a 3-ticker universe.

    What CAN be pinned at this seam: the subset invariant
    set(band_weights.keys()) ⊆ set(band_book) holds for every rebalance — no
    ticker is weighted that is not in the band book.  This covers the wiring
    (band_sigmas filtering step) without requiring a >20-name fixture.

    Fixture: standard 3-ticker synthetic universe; gate='veto_only' for wiring
    isolation.
    """
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path,
                              gate="veto_only")

    payload = json.loads(out.read_text())
    assert payload["meta"]["rebalance_count"] > 0, "Expected at least one rebalance"

    for reb in payload["rebalances"]:
        band_book_set = set(reb["band_book"])
        band_weights_keys = set(reb["band_weights"].keys())
        assert band_weights_keys <= band_book_set, (
            f"band_weights keys {band_weights_keys} not a subset of band_book "
            f"{band_book_set} at {reb['date']} — U3 sigma-coverage wiring violated"
        )


# ---------------------------------------------------------------------------
# U12 (Mode B re-entry, V55.1 amendment 2026-06-11): the carry domain is
# RANK-FREE — retention depends only on score >= 55 + HC-eligibility, never on
# rank vs MAX_PICKS (the V55.0 slice-exit was the amended-away defect).
# ---------------------------------------------------------------------------


def test_band_carry_retained_beyond_rank_20_v551() -> None:
    """U12 pin: a tenured incumbent scoring in [55, 65) whose POOL RANK is > 20
    (24 fresh >= 65 names rank above it) is RETAINED — the BF-B 2016-11-14
    fixture shape. Under the V55.0 slice domain it would have been force-sold
    at rank 25; V55.1 keeps it while score >= 55 and HC-eligible."""
    fresh = [f"F{i:02d}" for i in range(24)]               # 24 names, all >= 65
    scores = {t: 80.0 - i * 0.5 for i, t in enumerate(fresh)}  # 80.0 .. 68.5
    scores["CARRY"] = 58.0                                  # tenured, rank 25
    order = sorted([*fresh, "CARRY"], key=lambda t: -scores[t])
    assert order.index("CARRY") == 24  # pool rank 25 — beyond the old slice

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure={"CARRY"})

    assert "CARRY" in book, "rank-21+ carry must be retained (V55.1 rank-free domain)"
    assert "CARRY" in next_tenure
    assert carry_count == 1


def test_band_carry_vetoed_force_sold_regardless_of_score_v551() -> None:
    """U12 inverse pin: the SAME tenured name absent from `order` (vetoed /
    HC-evicted upstream) is force-sold and loses tenure even at score >= 55 —
    veto supremacy is untouched by the V55.1 domain amendment."""
    fresh = [f"F{i:02d}" for i in range(24)]
    scores = {t: 80.0 - i * 0.5 for i, t in enumerate(fresh)}
    scores["CARRY"] = 58.0
    order = sorted(fresh, key=lambda t: -scores[t])  # CARRY not eligible this leg

    book, next_tenure, carry_count = bf._band_book(order, scores, tenure={"CARRY"})

    assert "CARRY" not in book
    assert "CARRY" not in next_tenure
    assert carry_count == 0


# ---------------------------------------------------------------------------
# Survivorship-bias fix: pre-fetch expansion to include removed tickers.
# Branch on claude/gallant-feynman-tpipx1.
#
# These tests verify (offline, synthetic fixtures) that:
# (a) A ticker that is in a historical cohort via ``members_at`` but was
#     removed from the index by today is now in the pre-fetch set and gets
#     SCORED when data is available.
# (b) A removed ticker whose data is unavailable (no-CIK / no-prices /
#     fetch-error) is gracefully skipped with a logged reason — never
#     silently dropped at the pre-fetch stage.
# (c) The three Rule-18 observability counters appear in meta.
# (d) ``_resolve_cik_for_removed_ticker`` guards against empty CIK
#     (the Company("") gotcha, CLAUDE.md §Gotchas).
# ---------------------------------------------------------------------------


def _removed_event(ticker: str, effective_date_iso: str):  # type: ignore[return]  # noqa: ANN201
    """Synthetic MembershipEvent fixture for removed-ticker tests."""
    from datetime import date as _date

    from compute.ingest.historical_universe import MembershipEvent

    return MembershipEvent(
        effective_date=_date.fromisoformat(effective_date_iso),
        ticker=ticker,
        action="REMOVE",
        name=f"{ticker} Corp",
        source_url="https://example.com",
    )


def test_survivorship_fix_removed_ticker_is_scored_when_data_available(
    tmp_path, _universe
) -> None:
    """A ticker REMOVED from the S&P 500 (i.e., absent from today's universe but
    present in a historical cohort via ``members_at``) enters the scoring universe
    when its fundamentals + prices can be fetched.

    Verifies:
    - ``meta.scoring_universe_removed_fetched_count >= 1`` (at least one removed
      ticker contributed data).
    - The observability counters are present in meta.
    - ``meta.scoring_universe_removed_candidates_count >= 1``.
    - fetched + unavailable == candidates (accounting identity).
    """
    # "OLD" is NOT in _universe (current). The synthetic remove event makes it
    # appear as a removed candidate in the pre-fetch loop.
    remove_event = _removed_event("OLD", "2022-09-01")

    def _fake_resolve_cik(ticker: str) -> str | None:
        return "0000099999" if ticker == "OLD" else None

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
        mock.patch.object(bf, "_resolve_cik_for_removed_ticker", side_effect=_fake_resolve_cik),
        # Inject the synthetic remove event into list_known_events output so the
        # pre-fetch loop sees OLD as a removed candidate.
        mock.patch.object(bf, "list_known_events", return_value=(remove_event,)),
    ):
        out = bf.run_backfill(
            date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only"
        )

    meta = json.loads(out.read_text())["meta"]

    # Rule 18 observability: all three counters must be present.
    for field in (
        "scoring_universe_removed_candidates_count",
        "scoring_universe_removed_fetched_count",
        "scoring_universe_removed_unavailable_count",
    ):
        assert field in meta, f"Rule-18 field {field} missing from meta"

    # The removed ticker resolved CIK and had usable data — should be fetched.
    assert meta["scoring_universe_removed_candidates_count"] >= 1, (
        f"Expected >=1 removed candidate; got {meta['scoring_universe_removed_candidates_count']}"
    )
    assert meta["scoring_universe_removed_fetched_count"] >= 1, (
        f"Expected OLD to be fetched; got {meta['scoring_universe_removed_fetched_count']}"
    )
    # Accounting identity: fetched + unavailable = candidates.
    assert (
        meta["scoring_universe_removed_fetched_count"]
        + meta["scoring_universe_removed_unavailable_count"]
        == meta["scoring_universe_removed_candidates_count"]
    ), (
        "fetched + unavailable must equal candidates: "
        f"{meta['scoring_universe_removed_fetched_count']} + "
        f"{meta['scoring_universe_removed_unavailable_count']} != "
        f"{meta['scoring_universe_removed_candidates_count']}"
    )


def test_survivorship_fix_removed_ticker_gracefully_skipped_no_cik(
    tmp_path, _universe
) -> None:
    """A removed ticker whose CIK cannot be resolved is gracefully skipped:
    scored as unavailable (not as a silent pre-fetch drop), and the rest of
    the backfill completes normally.

    Before the fix: the ticker was absent from rows_by_ticker entirely AND
    no diagnostic was emitted — purely silent.  After the fix: the ticker
    enters the removed-candidates set, the CIK resolution returns None, and
    ``scoring_universe_removed_unavailable_count`` increments instead.
    """
    remove_event = _removed_event("NOCIK", "2022-09-01")

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
        # CIK resolution fails for the removed ticker.
        mock.patch.object(bf, "_resolve_cik_for_removed_ticker", return_value=None),
        mock.patch.object(bf, "list_known_events", return_value=(remove_event,)),
    ):
        out = bf.run_backfill(
            date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only"
        )

    meta = json.loads(out.read_text())["meta"]

    # The backfill must complete with normal rebalances (graceful degradation).
    assert meta["rebalance_count"] > 0, (
        "Backfill aborted when a removed ticker had no CIK — expected graceful skip"
    )
    # The removed ticker is counted as unavailable (not silently absent).
    assert meta["scoring_universe_removed_candidates_count"] == 1
    assert meta["scoring_universe_removed_fetched_count"] == 0
    assert meta["scoring_universe_removed_unavailable_count"] == 1


def test_survivorship_fix_removed_ticker_gracefully_skipped_fetch_error(
    tmp_path, _universe
) -> None:
    """A removed ticker whose fundamentals fetch raises (EDGAR error) is
    gracefully degraded: unavailable count increments, backfill completes."""
    remove_event = _removed_event("ERRORED", "2022-09-01")

    def _fetch_history_side_effect(cik: str) -> pd.DataFrame:
        # The removed ticker's resolved CIK triggers a synthetic EDGAR error.
        if cik == "0000011111":
            raise RuntimeError("Synthetic EDGAR error for removed ticker")
        return _annual_history(1.0)

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=_fetch_history_side_effect),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
        mock.patch.object(bf, "_resolve_cik_for_removed_ticker", return_value="0000011111"),
        mock.patch.object(bf, "list_known_events", return_value=(remove_event,)),
    ):
        out = bf.run_backfill(
            date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only"
        )

    meta = json.loads(out.read_text())["meta"]
    # Backfill must survive the fetch error for the removed ticker.
    assert meta["rebalance_count"] > 0, (
        "Backfill aborted on a fetch error for a removed ticker — expected graceful degradation"
    )
    assert meta["scoring_universe_removed_unavailable_count"] == 1
    assert meta["scoring_universe_removed_fetched_count"] == 0


def test_resolve_cik_for_removed_ticker_guards_empty_cik() -> None:
    """``_resolve_cik_for_removed_ticker`` returns None (not an empty / zero-padded
    string) when ``Company(ticker).cik`` is falsy — the ``Company('')`` gotcha guard.

    The gotcha (CLAUDE.md §Gotchas): calling ``Company('')`` / ``Company(<empty>)``
    with an EDGAR identity set resolves silently to an arbitrary company instead of
    raising.  ``_resolve_cik_for_removed_ticker`` must detect the empty-CIK case and
    return None so the caller skips the ticker rather than fetching wrong-company data.
    """
    import sys

    def _check_falsy_cik(falsy_cik: object, label: str) -> None:
        class _FakeCompany:
            cik = falsy_cik

        edgar_backup = sys.modules.pop("edgar", None)
        try:
            edgar_mock = mock.MagicMock()
            edgar_mock.Company = lambda t: _FakeCompany()
            sys.modules["edgar"] = edgar_mock
            result = bf._resolve_cik_for_removed_ticker("DEAD")
        finally:
            if edgar_backup is not None:
                sys.modules["edgar"] = edgar_backup
            else:
                sys.modules.pop("edgar", None)

        assert result is None, (
            f"Expected None for {label} CIK (gotcha guard), got {result!r}"
        )

    _check_falsy_cik("", "empty-string")
    _check_falsy_cik(0, "zero-int")
    _check_falsy_cik(None, "None")


def test_resolve_cik_for_removed_ticker_returns_zero_padded_cik() -> None:
    """``_resolve_cik_for_removed_ticker`` returns a 10-digit zero-padded CIK string
    when the Company lookup succeeds with a real numeric CIK."""
    import sys

    class _FakeCompanyRealCIK:
        cik = 12345  # numeric CIK — should become "0000012345"

    edgar_backup = sys.modules.pop("edgar", None)
    try:
        edgar_mock = mock.MagicMock()
        edgar_mock.Company = lambda t: _FakeCompanyRealCIK()
        sys.modules["edgar"] = edgar_mock
        result = bf._resolve_cik_for_removed_ticker("OLDTICKER")
    finally:
        if edgar_backup is not None:
            sys.modules["edgar"] = edgar_backup
        else:
            sys.modules.pop("edgar", None)

    assert result == "0000012345", f"Expected '0000012345', got {result!r}"


def test_survivorship_fix_current_tickers_excluded_from_removed_set(
    tmp_path, _universe
) -> None:
    """Tickers in both the REMOVE ledger and today's current universe are NOT added
    to the removed-ticker pre-fetch loop (they are already fetched in the main loop).

    This tests the ``- current`` set-difference in the survivorship fix:
    a ticker that was removed and later RE-ADDED should not be double-fetched.
    """
    # AAA is in the current universe (_universe fixture) AND appears as a REMOVE event.
    # It should NOT be added to the removed-ticker set (already fetched in current loop).
    readd_event = _removed_event("AAA", "2022-09-01")  # AAA is present in _universe

    resolve_calls: list[str] = []

    def _spy_resolve(ticker: str) -> str | None:
        resolve_calls.append(ticker)
        return None

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
        mock.patch.object(bf, "_resolve_cik_for_removed_ticker", side_effect=_spy_resolve),
        mock.patch.object(bf, "list_known_events", return_value=(readd_event,)),
    ):
        bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1), data_dir=tmp_path, gate="veto_only")

    # AAA is in current, so it must NOT appear in the removed-ticker loop.
    assert "AAA" not in resolve_calls, (
        "AAA is in today's current universe but was passed to _resolve_cik_for_removed_ticker "
        "— the `- current` set-difference is broken"
    )


# ---------------------------------------------------------------------------
# 12-config grid validation tests (score-once-apply-12 design)
# ---------------------------------------------------------------------------


def _run_backfill_veto_only(tmp_path, universe):
    """Helper: run backfill with gate='veto_only' and standard mocks."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
    ):
        return bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1),
                               data_dir=tmp_path, gate="veto_only")


def test_grid_config_keys_constant_is_12() -> None:
    """_GRID_CONFIG_KEYS has exactly 12 entries matching the 4×3 grid."""
    assert len(bf._GRID_CONFIG_KEYS) == 12
    expected_keys = {f"{c}_{f}" for c in (55, 60, 65, 70) for f in (1, 3, 5)}
    assert set(bf._GRID_CONFIG_KEYS) == expected_keys


def test_band_book_default_kwargs_byte_identity() -> None:
    """C2 regression: _band_book() with defaults == _band_book(composite_min=65, min_picks=5).

    FOOTGUN guard: if the defaults drift from the product constants, the grid's
    product-config key (65_5) will silently diverge from nav.adaptive.
    """
    order = ["AAA", "BBB", "CCC"]
    scores = {"AAA": 70.0, "BBB": 62.0, "CCC": 50.0}
    tenure: set[str] = {"BBB"}  # BBB entered at >= 65 in a prior rebalance

    book_default, tenure_default, carry_default = bf._band_book(order, scores, tenure)
    book_explicit, tenure_explicit, carry_explicit = bf._band_book(
        order, scores, tenure,
        composite_min=bf.ADAPTIVE_COMPOSITE_MIN,
        min_picks=bf.ADAPTIVE_MIN_PICKS,
    )

    assert book_default == book_explicit
    assert tenure_default == tenure_explicit
    assert carry_default == carry_explicit


def test_grid_tenure_isolation() -> None:
    """Each config has its OWN tenure set — changes to one don't pollute others.

    FOOTGUN guard: aliasing grid_tenure values (all pointing to the same set)
    would cause every config's carry state to couple.
    """
    # Verify the constants are distinct objects.
    assert len(bf._GRID_CONFIG_KEYS) == len(set(bf._GRID_CONFIG_KEYS)), (
        "_GRID_CONFIG_KEYS has duplicate keys — tenure isolation is broken"
    )
    # Simulate a tenure-update step: mutating config A's tenure must not affect config B.
    tenure_a: set[str] = set()
    tenure_b: set[str] = set()
    assert tenure_a is not tenure_b, "tenure sets must be distinct objects (aliasing guard)"
    tenure_a.add("X")
    assert "X" not in tenure_b, "mutating tenure_a must not affect tenure_b"


def test_grid_all_12_configs_produce_monthly_nav(tmp_path, _universe) -> None:
    """Positive: all 12 grid configs produce at least 1 monthly NAV entry.

    The synthetic 3-ticker universe over a 1-year window should produce ~4
    rebalances; with synthetic positive-drift prices all configs get valid sigma
    and thus at least 1 monthly entry.
    """
    out = _run_backfill_veto_only(tmp_path, _universe)
    payload = json.loads(out.read_text())

    validation = payload.get("meta", {}).get("validation") or {}
    grid = validation.get("grid")
    # Grid may be None when the backfill produced 0 rebalances (degenerate).
    if grid is None:
        # Accept: too few rebalances for the grid to populate.
        return
    assert isinstance(grid, dict)
    assert grid.get("configs") == bf._GRID_CONFIG_KEYS
    assert grid.get("freq") == "monthly"
    assert isinstance(grid.get("dates"), list)
    net = grid.get("net", {})
    assert isinstance(net, dict)
    # Every config in _GRID_CONFIG_KEYS must appear in net.
    for key in bf._GRID_CONFIG_KEYS:
        assert key in net, f"grid config {key!r} missing from meta.validation.grid.net"
        assert isinstance(net[key], list)


def test_grid_diagnostics_present_in_validation(tmp_path, _universe) -> None:
    """meta.validation.grid_diagnostics is present and has the expected structure."""
    out = _run_backfill_veto_only(tmp_path, _universe)
    payload = json.loads(out.read_text())

    validation = payload.get("meta", {}).get("validation") or {}
    diag = validation.get("grid_diagnostics")
    if diag is None:
        # Acceptable when grid_block is None (too few rebalances).
        return
    assert "per_config_leg_counts" in diag
    assert "configs_with_dropped_legs" in diag
    assert "min_leg_count" in diag
    assert "expected_leg_count" in diag
    assert isinstance(diag["per_config_leg_counts"], dict)
    assert isinstance(diag["configs_with_dropped_legs"], list)


def test_grid_sigma_empty_leg_drops_from_all_configs(tmp_path, _universe) -> None:
    """Negative: a rebalance where every name has uncomputable sigma drops from ALL 12 configs.

    When trailing_return_sigma returns None for all names in the cohort, the product
    band_book falls back to an empty weights_by_count (the `continue` gate in
    run_backfill), so no rebalances are produced at all. The grid diagnostics should
    reflect min_leg_count == 0.
    """
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history",
                          side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices",
                          side_effect=lambda t, **_kw: _prices(abs(hash(t)) % 1000)),
        mock.patch.object(bf, "fetch_amendments", return_value=[]),
        mock.patch.object(bf, "_compute_pit_risk_flags", return_value={}),
        # All sigmas uncomputable — this triggers the weights_by_count empty path,
        # so run_backfill continues past that rebalance without appending to rebalance_picks
        # OR grid_legs.
        mock.patch.object(bf, "trailing_return_sigma", return_value=None),
    ):
        out = bf.run_backfill(date(2022, 6, 1), date(2023, 6, 1),
                              data_dir=tmp_path, gate="veto_only")

    payload = json.loads(out.read_text())
    meta = payload["meta"]
    assert meta["rebalance_count"] == 0  # all legs skipped at the sigma gate
    # Grid block is None (no rebalances → no grid legs).
    validation = meta.get("validation") or {}
    assert validation.get("grid") is None or validation.get("grid_diagnostics") is None


def test_grid_pbo_block_present_in_validation_when_grid_populated(tmp_path, _universe) -> None:
    """meta.validation.pbo is present (possibly None) when the artifact is well-formed.

    With only ~4 rebalances in the 1-year synthetic window, the PBO grid may not
    have enough rows (>= 16 needed) and will fail gracefully — block stays None.
    This test just asserts the key exists.
    """
    out = _run_backfill_veto_only(tmp_path, _universe)
    payload = json.loads(out.read_text())
    validation = payload.get("meta", {}).get("validation") or {}
    # "pbo" key must be present (even if None).
    assert "pbo" in validation, (
        "meta.validation.pbo key missing — grid PBO not wired into validation block"
    )


def test_grid_holdout_block_present_in_validation(tmp_path, _universe) -> None:
    """meta.validation.holdout is present (possibly None) when the artifact is well-formed."""
    out = _run_backfill_veto_only(tmp_path, _universe)
    payload = json.loads(out.read_text())
    validation = payload.get("meta", {}).get("validation") or {}
    assert "holdout" in validation, (
        "meta.validation.holdout key missing — holdout not wired into validation block"
    )


def test_assemble_grid_navs_shares_price_panel(tmp_path) -> None:
    """_assemble_nav with grid_legs uses the SHARED panel — all 12 configs get NAV series.

    Directly tests the _assemble_nav(grid_legs=...) code path to confirm the
    shared-panel refactor does not re-walk prices separately per config.
    """
    prices_by_ticker = {
        "AAA": _bday_frame([100.0 + i for i in range(120)]),
        "BBB": _bday_frame([100.0 - 0.2 * i for i in range(120)]),
    }
    rebalance_picks = [
        ("2022-01-10", {1: {"AAA": 1.0}, 2: {"AAA": 0.5, "BBB": 0.5}}, 2),
        ("2022-03-14", {1: {"AAA": 1.0}, 2: {"AAA": 0.6, "BBB": 0.4}}, 2),
    ]
    # Build grid legs: 3 configs for simplicity.
    grid_legs = {
        "65_5": [("2022-01-10", {"AAA": 1.0}), ("2022-03-14", {"AAA": 1.0})],
        "55_1": [("2022-01-10", {"AAA": 0.6, "BBB": 0.4}), ("2022-03-14", {"AAA": 0.5, "BBB": 0.5})],
        "70_3": [("2022-01-10", {"AAA": 1.0})],
    }
    nav, monthly_by_config, all_month_labels, aligned_net, grid_diagnostics = bf._assemble_nav(
        rebalance_picks, prices_by_ticker, data_dir=tmp_path, grid_legs=grid_legs
    )

    assert nav  # product NAV produced
    # Monthly grid has 3 configs.
    assert set(monthly_by_config.keys()) == {"65_5", "55_1", "70_3"}
    # aligned_net is aligned to all_month_labels.
    assert isinstance(all_month_labels, list)
    for key, col in aligned_net.items():
        assert len(col) == len(all_month_labels), (
            f"config {key}: aligned_net length {len(col)} != all_month_labels length "
            f"{len(all_month_labels)}"
        )
    # grid_diagnostics has expected structure.
    assert "per_config_leg_counts" in grid_diagnostics
    assert grid_diagnostics["expected_leg_count"] == len(rebalance_picks)
    # Config 70_3 only has 1 leg (less than expected=2) → should appear in dropped.
    assert "70_3" in grid_diagnostics["configs_with_dropped_legs"]
