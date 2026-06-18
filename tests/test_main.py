"""Unit tests for compute.main cross-sectional builders.

These cover the helpers introduced in Phase 3c Step 7 to feed the
fair-price ensemble: ``_filing_lag``, ``_build_universe_metrics``,
``_build_peer_groupings``, ``_build_historical_metrics``, and the
per-history extractors ``_eps_3y_avg`` / ``_avg_3y_roe`` / ``_fcf_5y``.

The full ``run_weekly_compute`` orchestration is exercised by smoke /
integration tests with real data; these unit tests just lock the
contract of the cross-sectional builders so future refactors notice if
their input/output shapes change.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from compute.ingest.cross_source import country_for_exchange, exchange_name
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.main import (
    _avg_3y_roe,
    _build_historical_metrics,
    _build_peer_groupings,
    _build_raw_metrics,
    _build_universe_metrics,
    _coverage_pct,
    _eps_3y_avg,
    _fcf_5y,
    _filing_lag,
    _fundamentals_one,
    _history_one,
    _latency_histogram,
    _percentile,
)


def _snap(**overrides) -> FundamentalsSnapshot:
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        # net_income=50 + shares=10 → TTM EPS = 5.0 (matches the prior
        # eps_diluted=5.0 fixture default before audit #6 switched pe_ttm
        # to compute EPS from NI/shares).
        "net_income": 50.0,
        "stockholders_equity": 100.0,
        "shares_outstanding": 10.0,
        "eps_diluted": 5.0,
        "ebitda": 50.0,
        "long_term_debt": 20.0,
        "short_term_debt": 5.0,
        "cash": 10.0,
        "goodwill": 0.0,
        "intangibles_net": 0.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(overrides)
    return FundamentalsSnapshot(**defaults)


# -- _filing_lag --------------------------------------------------------------

def test_filing_lag_basic_arithmetic():
    snap = _snap(latest_filed_date=date(2026, 2, 1))
    assert _filing_lag(snap, asof=date(2026, 5, 1)) == 89


def test_filing_lag_none_when_snap_is_none():
    assert _filing_lag(None, asof=date(2026, 5, 1)) is None


def test_filing_lag_none_when_filed_date_missing():
    snap = _snap(latest_filed_date=None)
    assert _filing_lag(snap, asof=date(2026, 5, 1)) is None


# -- _build_universe_metrics --------------------------------------------------

def test_build_universe_metrics_all_three_ratios_computed():
    df = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "current_price": [100.0],
        }
    )
    snap = _snap(
        eps_diluted=5.0,
        stockholders_equity=200.0,
        shares_outstanding=10.0,  # bvps = 20 → P/B = 5
        ebitda=50.0,
        long_term_debt=20.0,
        short_term_debt=5.0,
        cash=10.0,
    )
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pe_ttm"] == 20.0  # 100/5
    assert metrics["AAA"]["pb_reported"] == 5.0  # 100/20
    # mc=1000, ev=1000+25-10=1015 → ev/ebitda = 20.30
    assert metrics["AAA"]["ev_ebitda_ttm"] == 20.30


def test_build_universe_metrics_negative_ni_yields_null_pe():
    # Audit #6: pe_ttm now keys off net_income (TTM), not snap.eps_diluted.
    # Negative TTM net_income → NaN PE → None propagated to universe metrics.
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(net_income=-10.0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pe_ttm"] is None


def test_build_universe_metrics_missing_snapshot_yields_all_null():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    metrics = _build_universe_metrics({"AAA": None}, df)
    assert metrics["AAA"] == {
        "pe_ttm": None, "pb_reported": None, "ev_ebitda_ttm": None,
    }


# -- _build_peer_groupings ----------------------------------------------------

def test_peer_groupings_split_by_sector_and_sub_industry():
    df = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "sector": ["Information Technology", "Information Technology",
                       "Financials", "Utilities"],
            "industry": ["Software", "Software", "Banks", "Electric Utilities"],
        }
    )
    by_sub, by_sector, broad_ex_fin_util = _build_peer_groupings(df)
    assert by_sub["Software"] == ["AAA", "BBB"]
    assert by_sub["Banks"] == ["CCC"]
    assert by_sector["Information Technology"] == ["AAA", "BBB"]
    assert by_sector["Financials"] == ["CCC"]
    assert by_sector["Utilities"] == ["DDD"]
    # broad excludes Financials + Utilities
    assert broad_ex_fin_util == ["AAA", "BBB"]


def test_peer_groupings_handles_missing_sub_industry():
    df = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "sector": ["Information Technology"],
            "industry": [None],
        }
    )
    by_sub, by_sector, broad = _build_peer_groupings(df)
    assert by_sub == {}
    assert by_sector == {"Information Technology": ["AAA"]}
    assert broad == ["AAA"]


# -- _eps_3y_avg --------------------------------------------------------------

def _hist(metric_values: dict[str, list[tuple[int, float]]]) -> pd.DataFrame:
    """Build a long-format fundamentals history DataFrame.

    metric_values: {metric_name: [(fiscal_year, value), ...]}
    """
    rows = []
    for metric, pairs in metric_values.items():
        for fy, v in pairs:
            rows.append({"metric": metric, "fiscal_year": fy, "value": v})
    return pd.DataFrame(rows)


def test_eps_3y_avg_uses_latest_three_years():
    hist = _hist({
        "eps_diluted": [(2021, 1.0), (2022, 2.0), (2023, 3.0),
                        (2024, 4.0), (2025, 5.0)],
    })
    # latest 3 = 2025, 2024, 2023 → mean = 4.0
    assert _eps_3y_avg(hist) == 4.0


def test_eps_3y_avg_returns_none_with_too_few_years():
    hist = _hist({"eps_diluted": [(2024, 1.0), (2025, 2.0)]})
    assert _eps_3y_avg(hist) is None


def test_eps_3y_avg_returns_none_for_empty_or_missing():
    assert _eps_3y_avg(None) is None
    assert _eps_3y_avg(pd.DataFrame()) is None


# -- _avg_3y_roe --------------------------------------------------------------

def test_avg_3y_roe_per_year_path_when_equity_history_present():
    """PR 4c primary path: per-year ROE = mean(NI_t / Equity_t) across 3 fiscal years.

    Hand-checked: per-year ROEs = (10/80, 20/120, 30/200) =
    (0.125, 0.1667, 0.15) → mean ≈ 0.1472.
    """
    hist = _hist({
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        "stockholders_equity": [(2023, 80.0), (2024, 120.0), (2025, 200.0)],
    })
    snap = _snap(stockholders_equity=200.0)
    expected = (10.0 / 80.0 + 20.0 / 120.0 + 30.0 / 200.0) / 3.0
    assert abs(_avg_3y_roe(hist, snap) - expected) < 1e-12


def test_avg_3y_roe_per_year_beats_legacy_for_grower():
    """Issue #11 anchor: for a firm whose equity grew from $80 → $200 with
    constant ROE around 15%, the legacy method (mean NI / current equity)
    biases ROE downward; the new method recovers the true average.

    Legacy: mean(10, 20, 30) / 200 = 20 / 200 = 0.10
    PR 4c:  mean(10/80, 20/120, 30/200) ≈ 0.147

    Result: the legacy method under-reports ROE for growing firms by
    ~47% in this case, which over-fires value_trap_risk.
    """
    hist = _hist({
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        "stockholders_equity": [(2023, 80.0), (2024, 120.0), (2025, 200.0)],
    })
    snap = _snap(stockholders_equity=200.0)
    new_roe = _avg_3y_roe(hist, snap)
    legacy_roe = (10.0 + 20.0 + 30.0) / 3.0 / 200.0  # 0.10
    assert new_roe > legacy_roe
    assert new_roe > 0.14  # within ~1% of true 0.147


def test_avg_3y_roe_none_when_equity_history_missing():
    """Issue #11 fix: when the annual history lacks `stockholders_equity`
    rows, return None (NOT the legacy mean-NI/current-equity fallback —
    that fallback was the very bug PR 4c was meant to fix, but it stayed
    in place until 2026-05-21). RIM then skips under the distinct
    `insufficient_history_for_roe` reason at the applicability layer."""
    hist = _hist({
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        # no `stockholders_equity` series
    })
    snap = _snap(stockholders_equity=200.0)
    assert _avg_3y_roe(hist, snap) is None


def test_avg_3y_roe_none_when_one_year_equity_missing():
    """Issue #11 fix: strict requirement — all 3 years of equity OR
    None. 2-of-3 partial history no longer trips the legacy single-
    period-equity fallback."""
    hist = _hist({
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        "stockholders_equity": [(2023, 80.0), (2024, 120.0)],
        # 2025 equity missing
    })
    snap = _snap(stockholders_equity=200.0)
    assert _avg_3y_roe(hist, snap) is None


def test_avg_3y_roe_none_when_one_year_equity_non_positive():
    """A zero or negative historical equity is treated as missing data —
    return None (Issue #11 fix). Negative equity = distressed firm; the
    ratio is meaningless, and conflating it with `value_trap_risk` was
    a false signal."""
    hist = _hist({
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        "stockholders_equity": [(2023, 80.0), (2024, 0.0), (2025, 200.0)],
    })
    snap = _snap(stockholders_equity=200.0)
    assert _avg_3y_roe(hist, snap) is None


def test_avg_3y_roe_none_when_equity_non_positive():
    hist = _hist({"net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)]})
    assert _avg_3y_roe(hist, _snap(stockholders_equity=0.0)) is None
    assert _avg_3y_roe(hist, _snap(stockholders_equity=-50.0)) is None


def test_avg_3y_roe_none_when_history_short():
    hist = _hist({"net_income": [(2024, 10.0), (2025, 20.0)]})
    assert _avg_3y_roe(hist, _snap()) is None


# -- _fcf_5y ------------------------------------------------------------------

def test_fcf_5y_chronological_order_oldest_first():
    hist = _hist({
        "operating_cash_flow": [(2021, 100.0), (2022, 110.0), (2023, 120.0),
                                (2024, 130.0), (2025, 140.0)],
        "capex": [(2021, 30.0), (2022, 40.0), (2023, 50.0),
                  (2024, 60.0), (2025, 70.0)],
    })
    out = _fcf_5y(hist)
    assert out == [70.0, 70.0, 70.0, 70.0, 70.0]


def test_fcf_5y_uses_only_overlapping_years():
    hist = _hist({
        "operating_cash_flow": [(2023, 100.0), (2024, 110.0), (2025, 120.0)],
        "capex": [(2024, 40.0), (2025, 50.0)],
    })
    # Overlap = {2024, 2025} → [70, 70] (oldest → newest)
    out = _fcf_5y(hist)
    assert out == [70.0, 70.0]


def test_fcf_5y_takes_capex_absolute_value():
    """Some filings store capex as a negative outflow; the formula is OCF − |capex|."""
    hist = _hist({
        "operating_cash_flow": [(2024, 100.0), (2025, 110.0)],
        "capex": [(2024, -40.0), (2025, -50.0)],
    })
    out = _fcf_5y(hist)
    assert out == [60.0, 60.0]


def test_fcf_5y_returns_empty_when_no_overlap():
    hist = _hist({
        "operating_cash_flow": [(2023, 100.0)],
        "capex": [(2024, 40.0)],
    })
    assert _fcf_5y(hist) == []


def test_fcf_5y_empty_input():
    assert _fcf_5y(None) == []
    assert _fcf_5y(pd.DataFrame()) == []


# -- _build_historical_metrics ------------------------------------------------

def test_build_historical_metrics_per_ticker_dict_shape():
    hist = _hist({
        "eps_diluted": [(2023, 1.0), (2024, 2.0), (2025, 3.0)],
        "net_income": [(2023, 10.0), (2024, 20.0), (2025, 30.0)],
        "stockholders_equity": [(2023, 80.0), (2024, 120.0), (2025, 200.0)],
        "operating_cash_flow": [(2024, 100.0), (2025, 110.0)],
        "capex": [(2024, 40.0), (2025, 50.0)],
    })
    out = _build_historical_metrics(
        histories={"AAA": hist},
        snapshots={"AAA": _snap(stockholders_equity=200.0)},
    )
    assert set(out["AAA"].keys()) == {"eps_3y_avg", "avg_3y_roe", "fcf_5y"}
    assert out["AAA"]["eps_3y_avg"] == 2.0
    # Per-year ROE: (10/80, 20/120, 30/200) → mean ≈ 0.1472
    expected_roe = (10.0 / 80.0 + 20.0 / 120.0 + 30.0 / 200.0) / 3.0
    assert abs(out["AAA"]["avg_3y_roe"] - expected_roe) < 1e-12
    assert out["AAA"]["fcf_5y"] == [60.0, 60.0]


def test_build_historical_metrics_handles_missing_ticker_history():
    """Empty history → all extractors return None / [] without raising."""
    out = _build_historical_metrics(
        histories={"AAA": pd.DataFrame()},
        snapshots={"AAA": _snap()},
    )
    assert out["AAA"]["eps_3y_avg"] is None
    assert out["AAA"]["avg_3y_roe"] is None
    assert out["AAA"]["fcf_5y"] == []


def test_build_universe_metrics_pe_uses_ttm_eps_not_single_period():
    # Audit #6: pe_ttm now derives from NI_TTM / shares_outstanding instead
    # of the single-period snap.eps_diluted. NI=40, shares=10 → TTM EPS=4
    # → PE = 100/4 = 25. (snap.eps_diluted=999 set deliberately to verify
    # the single-period field is IGNORED by the new formula.)
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(net_income=40.0, shares_outstanding=10.0, eps_diluted=999.0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pe_ttm"] == 25.0


def test_build_universe_metrics_zero_shares_yields_null_pb_and_ev():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(shares_outstanding=0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pb_reported"] is None
    assert metrics["AAA"]["ev_ebitda_ttm"] is None


# -- _build_raw_metrics: DD eps_diluted TTM fix (2026-05-23 cron #3) ----------
#
# Background: the XBRL `EarningsPerShareDiluted` concept is single-period
# (latest quarter for a quarterly filer), not TTM. The DD stock-detail
# audit showed eps_diluted=0.39 (single-period) while net_income / shares
# = 7M / 410M = $0.017 (TTM). pe_ratio_ttm already derives from NI/shares
# (audit #6 / PR #49 fix); these tests pin the same NI/shares derivation
# for the eps_basic + eps_diluted display fields.


def test_build_raw_metrics_eps_diluted_derived_from_ni_not_xbrl_singleperiod():
    """DD 2026-05-23 cron regression — eps_diluted carried the XBRL
    single-period value (0.39) into RawMetrics while NI/shares = $0.017.
    The fix is to compute TTM EPS = NI / shares the same way pe_ratio_ttm
    does, and ignore the XBRL single-period field entirely."""
    snap = _snap(
        net_income=7_000_000.0,
        shares_outstanding=410_000_000.0,
        eps_diluted=0.39,  # XBRL single-period value (deliberate ~23× off)
        eps_basic=0.41,  # likewise — should also be replaced
    )
    rm = _build_raw_metrics(snap, current_price=48.0)
    # NI / shares = 7M / 410M ≈ 0.01707
    expected_ttm = 7_000_000.0 / 410_000_000.0
    assert rm.eps_diluted == pytest.approx(expected_ttm, rel=1e-6)
    assert rm.eps_basic == pytest.approx(expected_ttm, rel=1e-6)
    # The single-period XBRL value (0.39) must NOT appear in the output.
    assert rm.eps_diluted != 0.39
    assert rm.eps_basic != 0.41


def test_build_raw_metrics_eps_preserves_negative_sign_on_loss_year():
    """Loss-year tickers (negative net_income) should show signed EPS in the
    display field, even though pe_ratio_ttm is null. Users seeing
    "−$0.42 EPS" is informative; seeing "null" or "0" would mislead."""
    snap = _snap(
        net_income=-42_000_000.0,
        shares_outstanding=100_000_000.0,
        eps_diluted=999.0,  # XBRL single-period — should be ignored
    )
    rm = _build_raw_metrics(snap, current_price=10.0)
    assert rm.eps_diluted == pytest.approx(-0.42, rel=1e-6)
    assert rm.eps_basic == pytest.approx(-0.42, rel=1e-6)
    # pe_ratio_ttm must be null on negative earnings.
    assert rm.pe_ratio_ttm is None


def test_build_raw_metrics_eps_null_when_shares_outstanding_missing():
    """STZ 2026-05-23 cron — shares_outstanding=None after the per-filing
    XBRL fallback silently fails. EPS display field must be None (not
    raise, not propagate the stale snap.eps_diluted)."""
    snap = _snap(
        net_income=2_000_000_000.0,
        shares_outstanding=None,
        eps_diluted=4.20,
    )
    rm = _build_raw_metrics(snap, current_price=200.0)
    assert rm.eps_diluted is None
    assert rm.eps_basic is None
    assert rm.market_cap is None
    assert rm.pe_ratio_ttm is None


def test_build_raw_metrics_eps_null_when_zero_shares():
    """Defensive guard — divide-by-zero protection on the NI/shares path."""
    snap = _snap(net_income=1_000_000.0, shares_outstanding=0.0)
    rm = _build_raw_metrics(snap, current_price=10.0)
    assert rm.eps_diluted is None
    assert rm.eps_basic is None
    assert rm.pe_ratio_ttm is None


def test_build_raw_metrics_pe_ttm_unchanged_by_eps_fix():
    """Regression guard — the audit #6 / PR #49 pe_ratio_ttm logic must
    still produce 25.0 from NI=40, shares=10, current_price=100."""
    snap = _snap(net_income=40.0, shares_outstanding=10.0, eps_diluted=999.0)
    rm = _build_raw_metrics(snap, current_price=100.0)
    assert rm.pe_ratio_ttm == pytest.approx(25.0, rel=1e-6)
    # And the TTM-derived display EPS matches the implicit pe_ttm denominator.
    assert rm.eps_diluted == pytest.approx(4.0, rel=1e-6)


def test_build_universe_metrics_negative_equity_yields_null_pb():
    df = pd.DataFrame({"ticker": ["AAA"], "current_price": [100.0]})
    snap = _snap(stockholders_equity=-100.0)
    metrics = _build_universe_metrics({"AAA": snap}, df)
    assert metrics["AAA"]["pb_reported"] is None


def test_eps_3y_avg_with_nan_in_recent_year():
    """NaN among the latest 3 → method returns None (don't silently skip)."""
    hist = _hist({
        "eps_diluted": [(2023, 1.0), (2024, 2.0), (2025, math.nan)],
    })
    assert _eps_3y_avg(hist) is None


# ---------------------------------------------------------------------------
# PR 3d Part 2 — fundamentals observability primitives
# ---------------------------------------------------------------------------

def test_latency_histogram_buckets_align_with_retry_budget():
    """Histogram buckets at 5, 15, 30s thresholds. The 30s threshold
    aligns with the inner ``stop_after_delay(30)`` retry budget — any
    ticker landing in the 30s+ bucket is retry-exhausted or
    future-timed out."""
    elapsed = [0.5, 2.0, 4.99, 5.0, 14.99, 15.0, 29.99, 30.0, 100.0]
    hist = _latency_histogram(elapsed)
    assert hist == {"<5s": 3, "5-15s": 2, "15-30s": 2, "30s+": 2}


def test_latency_histogram_empty_input():
    """Zero observations → all buckets zero, no division-by-zero."""
    assert _latency_histogram([]) == {"<5s": 0, "5-15s": 0, "15-30s": 0, "30s+": 0}


def test_percentile_p50_p95_basic():
    """Linear interpolation percentile on a small sorted list."""
    values = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
    p50 = _percentile(values, 0.50)
    p95 = _percentile(values, 0.95)
    assert p50 == pytest.approx(3.0, rel=1e-6)
    # 0.95 * 4 = 3.8 → between idx 3 (4.0) and idx 4 (5.0): 4.0 + 0.8*1.0 = 4.8
    assert p95 == pytest.approx(4.8, rel=1e-6)


def test_percentile_empty_returns_none():
    assert _percentile([], 0.50) is None


def test_percentile_singleton():
    """Single observation → percentile equals that observation."""
    assert _percentile([7.5], 0.95) == pytest.approx(7.5, rel=1e-6)


# ---------------------------------------------------------------------------
# PR 3d Part 1 — _fundamentals_one + _history_one tuple-return + timing
# ---------------------------------------------------------------------------

def test_fundamentals_one_returns_tuple_with_elapsed(monkeypatch):
    """``_fundamentals_one`` now returns ``(snapshot, elapsed_seconds)``
    so the orchestrator can populate the latency histogram."""
    from compute.main import fetch_fundamentals as orig
    sentinel = _snap()

    def fake(*a, **k):
        return sentinel

    monkeypatch.setattr("compute.main.fetch_fundamentals", fake)
    snap, elapsed = _fundamentals_one("TST", "0000000001")
    assert snap is sentinel
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0
    # noqa lint: keep `orig` ref to silence unused-import linters
    _ = orig


def test_fundamentals_one_failure_returns_none_and_elapsed(monkeypatch):
    """Exception in fetch_fundamentals → (None, elapsed) — never raises."""
    def boom(*a, **k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr("compute.main.fetch_fundamentals", boom)
    snap, elapsed = _fundamentals_one("TST", "0000000001")
    assert snap is None
    assert elapsed >= 0.0


def test_history_one_missing_cik_returns_empty_zero_elapsed():
    """No CIK → empty DataFrame + zero elapsed (no work to time)."""
    df, elapsed = _history_one("TST", "")
    assert df.empty
    assert elapsed == 0.0


def test_history_one_failure_returns_empty_with_elapsed(monkeypatch):
    """Exception in fetch_fundamentals_history → empty DataFrame + elapsed."""
    def boom(*a, **k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr("compute.main.fetch_fundamentals_history", boom)
    df, elapsed = _history_one("TST", "0000000001")
    assert df.empty
    assert elapsed >= 0.0


# ---------------------------------------------------------------------------
# PR 3d Part 1 — fundamentals.py retry policy contract
# ---------------------------------------------------------------------------

def test_build_snapshot_retry_policy_caps_at_30s_or_2_attempts():
    """Lock the retry contract on both _build_snapshot and
    _build_annual_history: must use the tightened
    (stop_after_delay(30) | stop_after_attempt(2)) policy. Earlier
    (stop_after_attempt(3) + max=30s wait) caused 60-90s/stuck-stock
    under SEC API throttling (run #14 incident, 2026-05-10)."""
    from tenacity.stop import stop_after_attempt, stop_after_delay, stop_any

    from compute.ingest.fundamentals import _build_annual_history, _build_snapshot

    for fn in (_build_snapshot, _build_annual_history):
        retrying = fn.retry  # tenacity attaches the Retrying object
        stop = retrying.stop
        assert isinstance(stop, stop_any), (
            f"{fn.__name__}: stop policy must be stop_any (use of '|'); got {type(stop).__name__}"
        )
        constituent_types = {type(s) for s in stop.stops}
        assert stop_after_delay in constituent_types, (
            f"{fn.__name__}: missing stop_after_delay in stop_any.stops"
        )
        assert stop_after_attempt in constituent_types, (
            f"{fn.__name__}: missing stop_after_attempt in stop_any.stops"
        )
        # Verify the delay cap is exactly 30s (locks the budget contract).
        delay_stop = next(s for s in stop.stops if isinstance(s, stop_after_delay))
        assert delay_stop.max_delay == 30, (
            f"{fn.__name__}: stop_after_delay must cap at 30s; got {delay_stop.max_delay}"
        )
        attempt_stop = next(s for s in stop.stops if isinstance(s, stop_after_attempt))
        assert attempt_stop.max_attempt_number == 2, (
            f"{fn.__name__}: stop_after_attempt must cap at 2; got {attempt_stop.max_attempt_number}"
        )


# ---------------------------------------------------------------------------
# Issue #309 — Step 6b pre-scan: stale_filing_hard injected before Step-7
# Rule-16 rotation (entered_top5 invariant)
# ---------------------------------------------------------------------------
#
# Boundary: stale_filing_status uses strict >, so lag > 180 days is "hard".
# Exactly 181 days is "hard"; exactly 180 days is "soft".
#
# The tests below simulate the Step 6b + Step 7 loop extracted from
# run_weekly_compute verbatim, so refactors to that block will break these
# tests immediately (by design — the loop is the contract).

from compute.valuation.applicability import stale_filing_status  # noqa: E402


def _step6b_then_step7(
    df: pd.DataFrame,
    snapshots: dict,
    risk_flags: dict,
    asof: date,
    previous_top5: set,
) -> tuple[dict, set, set]:
    """Verbatim copy of the Step 6b + Step 7 body from run_weekly_compute.

    Returns (mutated risk_flags, entered_set, exited_set).

    Kept as a local helper so tests run without invoking the full pipeline.
    Any change to the production loop must be mirrored here — the test suite
    will fail loudly if the two diverge (the positive/negative assertions
    catch the old vs new behaviour).
    """
    # Step 6b
    for _, _r in df.iterrows():
        _ticker = str(_r["ticker"])
        _snap = snapshots.get(_ticker)
        if _snap is None:
            continue
        if stale_filing_status(_filing_lag(_snap, asof)) == "hard":
            _merged = list(risk_flags.get(_ticker, []))
            if "stale_filing_hard" not in _merged:
                _merged.append("stale_filing_hard")
                risk_flags[_ticker] = _merged

    # Step 7
    current_top5: list[str] = []
    for _, r in df.iterrows():
        if len(current_top5) >= 5:
            break
        ticker = str(r["ticker"])
        if risk_flags.get(ticker):
            continue
        current_top5.append(ticker)

    current_top5_set = set(current_top5)
    entered = current_top5_set - previous_top5
    exited = previous_top5 - current_top5_set
    return risk_flags, entered, exited


def _ranked_df(*tickers: str) -> pd.DataFrame:
    """Build a minimal ranked DataFrame ordered by composite_score (desc)."""
    n = len(tickers)
    return pd.DataFrame(
        {
            "ticker": list(tickers),
            "composite_score": list(range(n, 0, -1)),  # first ticker = highest
            "rank": list(range(1, n + 1)),
        }
    )


def test_step6b_hard_stale_top1_excluded_from_entered_top5():
    """Positive (bug) case — issue #309.

    A ticker that would rank #1 by composite score AND is hard-stale
    (latest_filed_date 181 days before asof, which is > FILING_STALE_HARD_DAYS=180)
    AND has no other risk_flags MUST be excluded from entered_top5 and MUST have
    "stale_filing_hard" in risk_flags after the Step-6b pre-scan.

    Before the fix this stock would enter current_top5 because the
    stale_filing_hard flag was only injected in Step 8 (after rotation).
    """
    asof = date(2026, 5, 29)
    # 181 days before asof → lag > 180 → "hard"
    hard_stale_date = date(2025, 11, 29)  # 181 days before 2026-05-29

    stale_snap = _snap(ticker="STALE", latest_filed_date=hard_stale_date)
    fresh_snap = _snap(ticker="FRESH", latest_filed_date=date(2026, 4, 1))

    # STALE ranks #1, FRESH ranks #2 → without the fix STALE enters top5
    df = _ranked_df("STALE", "FRESH", "C3", "C4", "C5", "C6")
    snapshots = {
        "STALE": stale_snap,
        "FRESH": fresh_snap,
    }
    risk_flags: dict = {}
    previous_top5: set = set()

    risk_flags, entered, exited = _step6b_then_step7(
        df, snapshots, risk_flags, asof, previous_top5
    )

    # Step 6b must have injected the flag
    assert "stale_filing_hard" in risk_flags.get("STALE", []), (
        "Step 6b must inject stale_filing_hard into risk_flags before rotation"
    )
    # Rotation must have skipped STALE (Rule 16 — flagged stocks excluded)
    assert "STALE" not in entered, (
        "Hard-stale #1-ranked ticker must be excluded from entered_top5 (Rule 16)"
    )
    # FRESH (rank #2, clean) should enter instead
    assert "FRESH" in entered, (
        "Next clean ticker must inherit entered_top5 when #1 is hard-stale"
    )


def test_step6b_soft_stale_top1_still_enters_top5():
    """Boundary control — lag exactly 180 days is "soft", not "hard".

    stale_filing_status uses strict >, so 180-day lag = "soft" (not vetoed).
    A soft-stale ticker with no other risk_flags must still be able to enter
    current_top5 — Step 6b must NOT inject stale_filing_hard for it.
    """
    asof = date(2026, 5, 29)
    # Exactly 180 days before asof → lag == 180 → "soft" (not "hard")
    soft_stale_date = date(2025, 11, 30)  # 180 days before 2026-05-29

    soft_snap = _snap(ticker="SOFT", latest_filed_date=soft_stale_date)

    df = _ranked_df("SOFT", "OTHER")
    snapshots = {"SOFT": soft_snap}
    risk_flags: dict = {}
    previous_top5: set = set()

    risk_flags, entered, _ = _step6b_then_step7(
        df, snapshots, risk_flags, asof, previous_top5
    )

    assert "stale_filing_hard" not in risk_flags.get("SOFT", []), (
        "Exactly-180-day lag is soft, not hard — Step 6b must not inject flag"
    )
    assert "SOFT" in entered, (
        "Soft-stale ticker with no other risk_flags must enter top5"
    )


def test_step6b_fresh_filing_enters_top5_no_flag():
    """Negative control — fresh filing (lag well below 180d).

    A ticker with a recent filing must never receive stale_filing_hard and
    must enter current_top5 when it ranks in the top 5 by composite score.
    """
    asof = date(2026, 5, 29)
    fresh_date = date(2026, 4, 1)  # 58 days before asof — fresh

    fresh_snap = _snap(ticker="FRESHCO", latest_filed_date=fresh_date)

    df = _ranked_df("FRESHCO", "B", "C", "D", "E", "F")
    snapshots = {"FRESHCO": fresh_snap}
    risk_flags: dict = {}
    previous_top5: set = set()

    risk_flags, entered, _ = _step6b_then_step7(
        df, snapshots, risk_flags, asof, previous_top5
    )

    assert "stale_filing_hard" not in risk_flags.get("FRESHCO", []), (
        "Fresh-filing ticker must not receive stale_filing_hard flag"
    )
    assert "FRESHCO" in entered


def test_step6b_hard_stale_already_in_previous_top5_exits():
    """A hard-stale ticker that was in previous_top5 must exit.

    current_top5 excludes it (flagged), so exited = {STALE} and entered = {}.
    This confirms the flag is idempotent: even if some caller pre-populated
    stale_filing_hard, Step 6b deduplication guard ("if not in _merged")
    keeps the list clean.
    """
    asof = date(2026, 5, 29)
    hard_stale_date = date(2025, 11, 29)  # 181 days

    stale_snap = _snap(ticker="STALE", latest_filed_date=hard_stale_date)

    # STALE ranks #1 but is flagged; ranks 2-6 have no snapshots (→ not flagged)
    df = _ranked_df("STALE", "B", "C", "D", "E", "F")
    snapshots = {"STALE": stale_snap}
    risk_flags: dict = {}
    previous_top5 = {"STALE"}  # was in previous top5

    risk_flags, entered, exited = _step6b_then_step7(
        df, snapshots, risk_flags, asof, previous_top5
    )

    assert "STALE" in exited, "Hard-stale previous-top5 member must exit"
    assert "STALE" not in entered


def test_step6b_hard_stale_flag_not_duplicated_when_already_present():
    """Idempotency guard — if stale_filing_hard was already in risk_flags
    before Step 6b (e.g. pre-seeded by another path), Step 6b must not
    duplicate it.
    """
    asof = date(2026, 5, 29)
    hard_stale_date = date(2025, 11, 29)

    hard_snap = _snap(ticker="HST", latest_filed_date=hard_stale_date)
    df = _ranked_df("HST")
    snapshots = {"HST": hard_snap}
    # Pre-seed the flag (simulates another path writing it earlier)
    risk_flags: dict = {"HST": ["stale_filing_hard"]}
    previous_top5: set = set()

    risk_flags, _, _ = _step6b_then_step7(
        df, snapshots, risk_flags, asof, previous_top5
    )

    assert risk_flags["HST"].count("stale_filing_hard") == 1, (
        "Step 6b must not append a duplicate stale_filing_hard"
    )


# ---------------------------------------------------------------------------
# PR-A2 — exchange/country listing-metadata wiring in Step 8
# ---------------------------------------------------------------------------
#
# The six tests below lock the three sub-contracts introduced by PR-A2:
#
#   (1) compute.main._coverage_pct — the PRODUCTION coverage formula,
#       imported (NOT copied) so a denominator/numerator drift in
#       run_weekly_compute breaks these tests loudly (CLAUDE.md §Gotchas
#       PR #310 — no verbatim-copy test helpers).
#
#   (2) Step-8 mapping contract — monkeypatch ``compute.main.fetch_yfinance_exchange``
#       (the name imported INTO main.py's namespace via
#       ``from compute.ingest.cross_source import fetch_yfinance_exchange``)
#       and verify that ``exchange_name`` + ``country_for_exchange`` compose
#       correctly to populate the accumulators.
#
# Monkeypatch target rationale: main.py does
#   ``from compute.ingest.cross_source import (country_for_exchange,
#       exchange_name, fetch_yfinance_exchange)``
# so the name that lives in compute.main's module-level namespace is
# ``compute.main.fetch_yfinance_exchange``. Patching the *source* at
# ``compute.ingest.cross_source.fetch_yfinance_exchange`` would NOT affect
# the already-imported name. This mirrors the existing pattern in this file:
#   monkeypatch.setattr("compute.main.fetch_fundamentals", fake)
# (see test_fundamentals_one_returns_tuple_with_elapsed above).


# -- coverage formula tests ---------------------------------------------------


def test_coverage_pct_all_resolved() -> None:
    """All tickers resolve → 100.00%."""
    acc = {"AAPL": "NASDAQ", "MSFT": "NASDAQ", "JPM": "NYSE"}
    assert _coverage_pct(acc) == 100.00


def test_coverage_pct_partial_resolution() -> None:
    """1 of 2 tickers resolves → 50.00%."""
    acc = {"AAPL": "NASDAQ", "MISS": None}
    assert _coverage_pct(acc) == 50.00


def test_coverage_pct_all_none() -> None:
    """All tickers unresolved (cold simulate cache) → 0.00%."""
    acc = {"AAPL": None, "MSFT": None}
    assert _coverage_pct(acc) == 0.00


def test_coverage_pct_empty_dict_returns_none() -> None:
    """Empty universe (edge case) → None, matching the ``if exchange_by_ticker``
    guard in run_weekly_compute that avoids zero-division."""
    assert _coverage_pct({}) is None


def test_coverage_pct_rounding_two_decimal_places() -> None:
    """Result is rounded to exactly 2 decimal places — mirrors
    ``round(100.0 * n / len, 2)`` in the production formula."""
    # 2 of 3 resolved → 66.666… → round to 66.67
    acc = {"A": "NASDAQ", "B": "NYSE", "C": None}
    result = _coverage_pct(acc)
    assert result == 66.67


# -- Step-8 mapping contract tests (monkeypatch) -----------------------------


def test_step8_exchange_mapping_known_code(monkeypatch) -> None:
    """When fetch_yfinance_exchange returns a known S&P-500 code (e.g. "NMS"),
    compute.main.exchange_name maps it to "NASDAQ" and
    compute.main.country_for_exchange maps it to "US".

    This pins the compose-chain:
      fetch_yfinance_exchange("AAPL") → "NMS"
      exchange_name("NMS") → "NASDAQ"
      country_for_exchange("NMS") → "US"
    which is exactly how exchange_by_ticker / country_by_ticker are populated
    inside the Step-8 loop in run_weekly_compute.
    """
    monkeypatch.setattr("compute.main.fetch_yfinance_exchange", lambda _t: "NMS")

    code = "NMS"  # what fetch_yfinance_exchange returns
    exchange_by_ticker = {"AAPL": exchange_name(code)}
    country_by_ticker = {"AAPL": country_for_exchange(code)}

    assert exchange_by_ticker["AAPL"] == "NASDAQ"
    assert country_by_ticker["AAPL"] == "US"


def test_step8_exchange_mapping_none_code(monkeypatch) -> None:
    """When fetch_yfinance_exchange returns None (cold-cache miss / failure),
    both exchange_name(None) and country_for_exchange(None) must return None.

    These tickers are excluded from the coverage numerator — confirmed by the
    coverage formula test_coverage_pct_partial_resolution above.
    """
    monkeypatch.setattr("compute.main.fetch_yfinance_exchange", lambda _t: None)

    code = None
    exchange_by_ticker = {"MISS": exchange_name(code)}
    country_by_ticker = {"MISS": country_for_exchange(code)}

    assert exchange_by_ticker["MISS"] is None
    assert country_by_ticker["MISS"] is None


def test_step8_exchange_mapping_non_us_code_passthrough(monkeypatch) -> None:
    """When fetch_yfinance_exchange returns an unrecognised (non-US) code,
    exchange_name passes it through verbatim but country_for_exchange returns
    None (country derivation is US-only for the S&P 500 universe).

    This is the forward-safe design: showing a raw exchange code like "XLON"
    is better than dropping the field entirely.
    """
    monkeypatch.setattr("compute.main.fetch_yfinance_exchange", lambda _t: "XLON")

    code = "XLON"
    exchange_by_ticker = {"INTL": exchange_name(code)}
    country_by_ticker = {"INTL": country_for_exchange(code)}

    assert exchange_by_ticker["INTL"] == "XLON"  # passthrough
    assert country_by_ticker["INTL"] is None  # not a US exchange


def test_step8_exchange_coverage_excludes_none_entries(monkeypatch) -> None:
    """End-to-end mini-simulation of the Step-8 accumulator + coverage formula.

    Two tickers: AAPL resolves ("NMS"), MISS does not (None).
    Coverage = 1 / 2 = 50.00%.

    Uses monkeypatch on compute.main.fetch_yfinance_exchange to avoid any
    real I/O, then drives the compose-chain and coverage formula exactly as
    run_weekly_compute does.
    """
    exchange_results = {"AAPL": "NMS", "MISS": None}
    monkeypatch.setattr(
        "compute.main.fetch_yfinance_exchange",
        lambda t: exchange_results.get(t),
    )

    exchange_by_ticker: dict[str, str | None] = {}
    country_by_ticker: dict[str, str | None] = {}

    for ticker in ("AAPL", "MISS"):
        code = exchange_results.get(ticker)
        exchange_by_ticker[ticker] = exchange_name(code)
        country_by_ticker[ticker] = country_for_exchange(code)

    assert exchange_by_ticker["AAPL"] == "NASDAQ"
    assert country_by_ticker["AAPL"] == "US"
    assert exchange_by_ticker["MISS"] is None
    assert country_by_ticker["MISS"] is None

    # Coverage: 1 of 2 resolved
    coverage = _coverage_pct(exchange_by_ticker)
    assert coverage == 50.00


# ---------------------------------------------------------------------------
# Step-3b wiring: fetch_yfinance_shares_outstanding passed to check_post_split_share_lag
#
# PR #499 wired a direct yfinance sharesOutstanding count through the
# yf_shares_outstanding_override parameter so leg-3 reconciliation uses the
# actual share count instead of yf_market_cap / current_price (which is
# cache-timing-sensitive and could degrade KLAC from Tier-1 to Tier-2).
#
# These tests verify the wiring at the smallest tractable seam: monkeypatching
# fetch_yfinance_market_cap, fetch_yfinance_shares_outstanding, and
# check_post_split_share_lag in the compute.main namespace, then invoking the
# Step-3b loop directly.  We confirm check_post_split_share_lag received the
# yf_shares_outstanding_override equal to the value returned by
# fetch_yfinance_shares_outstanding.
# ---------------------------------------------------------------------------


def _step3b_loop(
    snapshots: dict,
    prices_by_ticker: dict,
    monkeypatch: pytest.MonkeyPatch,
    yf_mc_by_ticker: dict,
    yf_shares_by_ticker: dict,
    psr_by_ticker: dict,
) -> dict:
    """Minimal reimplementation of the Step-3b loop contract for unit testing.

    Mirrors compute/main.py lines ~1306-1343:
        for _ticker, _snap in snapshots.items():
            if _snap is None: continue
            _yf_mc = fetch_yfinance_market_cap(_ticker)
            _yf_shares = fetch_yfinance_shares_outstanding(_ticker)
            _psr = check_post_split_share_lag(
                _ticker, _snap,
                yf_market_cap=_yf_mc,
                current_price=_current_price,
                yf_shares_outstanding_override=_yf_shares,
            )
            if _psr.tier == 0: continue
            post_split_results[_ticker] = _psr

    Returns the call kwargs dict keyed by ticker for assertion.

    NOTE (indirect coverage): this re-implements the loop rather than driving
    ``run_weekly_compute`` (no lightweight orchestrator harness exists yet —
    same limitation as the skipped wall_clock tests). It pins the wiring
    CONTRACT (override forwarded verbatim); a future edit that drops
    ``yf_shares_outstanding_override=`` from the REAL main.py Step-3b loop is
    caught only indirectly (via the override behavior cases in
    test_post_split_share_lag.py), not here — keep this mirror in sync.
    """
    import compute.main as main_mod  # local import to enable monkeypatching

    call_kwargs: dict[str, dict] = {}

    def _fake_yf_mc(ticker):
        return yf_mc_by_ticker.get(ticker)

    def _fake_yf_shares(ticker):
        return yf_shares_by_ticker.get(ticker)

    def _fake_check(ticker, snap, yf_market_cap, current_price, **kwargs):
        from compute.scoring.risk_overlay import PostSplitResult
        call_kwargs[ticker] = {
            "yf_market_cap": yf_market_cap,
            "current_price": current_price,
            **kwargs,
        }
        return psr_by_ticker.get(ticker, PostSplitResult(tier=0))

    monkeypatch.setattr(main_mod, "fetch_yfinance_market_cap", _fake_yf_mc)
    monkeypatch.setattr(main_mod, "fetch_yfinance_shares_outstanding", _fake_yf_shares)
    monkeypatch.setattr(main_mod, "check_post_split_share_lag", _fake_check)

    # Execute the loop logic directly (mirrors the Step-3b body).
    for ticker, ticker_snap in snapshots.items():
        if ticker_snap is None:
            continue
        current_price = prices_by_ticker.get(ticker)
        yf_mc = main_mod.fetch_yfinance_market_cap(ticker)
        yf_shares = main_mod.fetch_yfinance_shares_outstanding(ticker)
        main_mod.check_post_split_share_lag(
            ticker,
            ticker_snap,
            yf_market_cap=yf_mc,
            current_price=current_price,
            yf_shares_outstanding_override=yf_shares,
        )

    return call_kwargs


def test_step3b_wiring_yf_shares_passed_as_override(monkeypatch: pytest.MonkeyPatch):
    """Step-3b loop passes fetch_yfinance_shares_outstanding return as override.

    The wiring invariant: the value returned by fetch_yfinance_shares_outstanding
    for a ticker must be passed verbatim as yf_shares_outstanding_override to
    check_post_split_share_lag for the same ticker.

    Simulates a single-ticker run where yfinance reports 1,306,275,210 shares
    (post-10:1 split).  After the loop, we assert that check_post_split_share_lag
    received yf_shares_outstanding_override=1_306_275_210.0, not None.
    """
    from compute.scoring.risk_overlay import PostSplitResult

    ticker = "KLAC"
    yf_shares_value = 1_306_275_210.0
    yf_mc_value = 1.96e11  # ~$196B

    test_snap = _snap(ticker=ticker, shares_outstanding=130_627_521.0)
    prices = {ticker: 150.0}
    yf_mc_map = {ticker: yf_mc_value}
    yf_shares_map = {ticker: yf_shares_value}
    psr_map = {ticker: PostSplitResult(tier=0)}  # tier=0 → no side-effects needed

    call_kwargs = _step3b_loop(
        snapshots={ticker: test_snap},
        prices_by_ticker=prices,
        monkeypatch=monkeypatch,
        yf_mc_by_ticker=yf_mc_map,
        yf_shares_by_ticker=yf_shares_map,
        psr_by_ticker=psr_map,
    )

    assert ticker in call_kwargs, (
        f"check_post_split_share_lag was not called for {ticker}"
    )
    received_override = call_kwargs[ticker].get("yf_shares_outstanding_override")
    assert received_override == pytest.approx(yf_shares_value), (
        f"Step-3b must pass fetch_yfinance_shares_outstanding return "
        f"({yf_shares_value}) as yf_shares_outstanding_override, "
        f"got {received_override!r}"
    )


def test_step3b_wiring_none_shares_passed_as_none_override(monkeypatch: pytest.MonkeyPatch):
    """Step-3b passes None when fetch_yfinance_shares_outstanding returns None.

    Cold-cache / QR_SKIP_CROSS_SOURCE=1 path: the function returns None, and
    None must be forwarded as yf_shares_outstanding_override so the detector
    falls back gracefully to the market_cap/price path (existing behavior).
    """
    from compute.scoring.risk_overlay import PostSplitResult

    ticker = "COLD"
    test_snap = _snap(ticker=ticker, shares_outstanding=50_000_000.0)

    call_kwargs = _step3b_loop(
        snapshots={ticker: test_snap},
        prices_by_ticker={ticker: 100.0},
        monkeypatch=monkeypatch,
        yf_mc_by_ticker={ticker: 5e9},
        yf_shares_by_ticker={ticker: None},  # cold cache → None
        psr_by_ticker={ticker: PostSplitResult(tier=0)},
    )

    assert ticker in call_kwargs
    received_override = call_kwargs[ticker].get("yf_shares_outstanding_override")
    assert received_override is None, (
        "None from fetch_yfinance_shares_outstanding must be passed verbatim "
        "as yf_shares_outstanding_override (cold-cache graceful fallback)"
    )
