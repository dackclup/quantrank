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


def test_run_backfill_produces_wellformed_artifact(tmp_path, _universe) -> None:
    scale_by_cik = {"1": 1.0, "2": 1.4, "3": 0.7}

    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(scale_by_cik.get(cik, 1.0))),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
            mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(1)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(1)),
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
    """A picked name with a 10-K/A filed AFTER its selection date raises the re-sourced
    canary — restatement_contamination_pct > 0 (vs the old companyfacts scan's 0.0)."""
    post_asof = [{"form": "10-K/A", "filing_date": "2099-01-01", "accession": "x", "filing_url": ""}]
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
    """The re-sourced canary: ANY amendment filed after as_of fires; before/empty/None don't."""
    amends = [{"form": "10-K/A", "filing_date": "2023-03-15"}]
    assert bf._restatement_at_risk(amends, "2022-06-01") is True    # filed after as_of
    assert bf._restatement_at_risk(amends, "2024-01-01") is False   # filed before as_of
    assert bf._restatement_at_risk([{"form": "10-Q/A", "filing_date": "2023-01-01"}], "2022-01-01") is True
    assert bf._restatement_at_risk([], "2022-06-01") is False       # no amendments
    assert bf._restatement_at_risk(None, "2022-06-01") is False     # unresolved -> not at-risk


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
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

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
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

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


def test_rule_version_carries_veto_replay_suffix() -> None:
    """``RULE_VERSION`` carries the ``+veto-replay`` suffix that marks artifacts
    where ``veto_layer_replayed=True``, so callers can distinguish the two datasets."""
    assert bf.RULE_VERSION.endswith("+veto-replay"), (
        f"Expected RULE_VERSION to end with '+veto-replay', got {bf.RULE_VERSION!r}"
    )


def test_meta_rule_version_in_artifact(tmp_path, _universe) -> None:
    """The artifact's ``meta.rule_version`` matches ``RULE_VERSION`` (i.e., carries
    the ``+veto-replay`` suffix)."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)
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
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

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
    out = bf._assemble_nav(rebalance_picks, prices_by_ticker, data_dir=tmp_path)

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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
        "max_picks": bf.MAX_PICKS,
    }, f"adaptive_rule mismatch: {rule}"


def test_disclaimer_mentions_adaptive_threshold_tokens(tmp_path, _universe) -> None:
    """The disclaimer must mention the adaptive threshold (65) and that holding count
    varies, as required by the adaptive-book disclosure. Asserts on meaningful tokens,
    not exact prose, so minor wording edits don't break the test."""
    with (
        mock.patch.object(bf, "get_sp500_constituents", return_value=_universe),
        mock.patch.object(bf, "fetch_fundamentals_history", side_effect=lambda cik: _annual_history(1.0)),
        mock.patch.object(bf, "fetch_prices", side_effect=lambda t: _prices(abs(hash(t)) % 1000)),
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
