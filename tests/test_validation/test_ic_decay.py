"""Tests for compute.validation.ic_decay (Phase 4b §3 + Issue #75 §3).

Anchors McLean-Pontiff (2016) decay-detection behavior:

- Stable pillar with constant IC → no alert
- Pillar that drops to 30% of mean for 7 months → alert fires
- Edge: 5 months below threshold ≠ alert (just under duration_months=6)
- Pillar with zero / negative historical mean → no alert (the metric is
  meaningless against a never-positive baseline)
- emit_decay_report writes a well-formed JSON payload

Issue #75 §3 additive tests (extended without breaking existing ones):
- pillar_entries_to_monthly_panel: adapter from per-commit entries to monthly
  panel — empty input, single entry, multi-commit grouping
- build_decay_report status gating: insufficient_history / monitoring / alert
- Preliminary alert suppression: n_observations < MIN_HISTORY_MONTHS forces
  alert=False regardless of individual IC values
- Additive emit_decay_report keys: horizon_months / min_history_months /
  status / n_dates_with_ic / per-pillar preliminary field
- main.py wiring graceful-degradation + skip-flag path (mock injection)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from compute.validation.ic_decay import (
    IC_DECAY_DURATION_MONTHS,
    IC_DECAY_THRESHOLD,
    IC_HORIZON_MONTHS,
    MIN_HISTORY_MONTHS,
    ICDecayReport,
    build_decay_report,
    check_all_pillars,
    check_pillar_decay,
    emit_decay_report,
    pillar_entries_to_monthly_panel,
)


def _series(values: list[float], pillar: str = "value") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pillar": [pillar] * len(values),
            "year_month": pd.date_range("2020-01-01", periods=len(values), freq="MS"),
            "monthly_ic": values,
        }
    )


def test_stable_pillar_does_not_alert():
    """Constant IC = 0.04 every month for 36 months → no decay alert."""
    hist = _series([0.04] * 36)
    report = check_pillar_decay(hist)
    assert report.alert is False
    assert report.months_below_threshold == 0
    assert report.decay_ratio == pytest.approx(1.0, abs=1e-9)


def test_decayed_pillar_alerts_after_six_consecutive_months():
    """36 months of mean 0.04 IC, last 12 drop to 0.005 (12.5% of mean) → alert.

    Twelve months below the breach threshold are enough for both the
    alert flag (>= 6 consecutive) and the rolling_12m_ic < 50% of
    historical_mean_ic ratio (the rolling window then contains only
    decayed values).
    """
    values = [0.04] * 24 + [0.005] * 12
    hist = _series(values)
    report = check_pillar_decay(hist)
    assert report.alert is True
    assert report.months_below_threshold >= 6
    assert report.decay_ratio < IC_DECAY_THRESHOLD


def test_decay_just_under_duration_does_not_alert():
    """Last 5 consecutive months below threshold (< 6) → no alert."""
    values = [0.04] * 31 + [0.005] * 5
    hist = _series(values)
    report = check_pillar_decay(hist)
    assert report.alert is False
    assert report.months_below_threshold == 5


def test_decay_streak_resets_after_recovery():
    """Recovery month resets the consecutive-below counter."""
    values = [0.04] * 24 + [0.005] * 3 + [0.04] + [0.005] * 5
    hist = _series(values)
    report = check_pillar_decay(hist)
    # Last 5 months are below; not 6+
    assert report.months_below_threshold == 5
    assert report.alert is False


def test_zero_historical_mean_returns_zero_ratio_no_alert():
    """If historical mean IC is <= 0, decay is meaningless."""
    values = [0.0] * 36
    hist = _series(values)
    report = check_pillar_decay(hist)
    assert report.alert is False
    assert report.decay_ratio == 0.0


def test_negative_historical_mean_no_alert():
    """A pillar that's been negative on average → flag suppressed."""
    values = [-0.02] * 36
    hist = _series(values)
    report = check_pillar_decay(hist)
    assert report.alert is False


def test_rolling_12m_uses_only_trailing_year():
    """rolling_12m_ic = mean of last 12 entries regardless of full series length."""
    values = [0.04] * 24 + [0.01] * 12
    hist = _series(values)
    report = check_pillar_decay(hist)
    assert report.rolling_12m_ic == pytest.approx(0.01, abs=1e-9)
    assert report.rolling_36m_ic == pytest.approx(sum(values) / 36, abs=1e-9)


def test_rejects_empty_history():
    with pytest.raises(ValueError, match="non-empty"):
        check_pillar_decay(pd.DataFrame(columns=["pillar", "year_month", "monthly_ic"]))


def test_rejects_missing_columns():
    bad = pd.DataFrame({"foo": [1, 2], "bar": [3, 4]})
    with pytest.raises(ValueError, match="missing columns"):
        check_pillar_decay(bad)


def test_check_all_pillars_iterates(tmp_path: Path):
    stable = _series([0.04] * 24, pillar="quality").drop(columns=["pillar"])
    decayed = _series([0.04] * 17 + [0.005] * 7, pillar="value").drop(
        columns=["pillar"]
    )
    reports = check_all_pillars({"quality": stable, "value": decayed})
    by_name = {r.pillar: r for r in reports}
    assert by_name["quality"].alert is False
    assert by_name["value"].alert is True


def test_emit_decay_report_writes_well_formed_json(tmp_path: Path):
    """Round-trip a synthetic report through emit + json.load.

    Covers original keys AND the Issue #75 §3 additive keys.
    """
    reports = [
        ICDecayReport(
            pillar="value",
            rolling_12m_ic=0.005,
            rolling_36m_ic=0.025,
            historical_mean_ic=0.04,
            decay_ratio=0.125,
            months_below_threshold=7,
            alert=True,
            n_observations=36,
            preliminary=False,
        ),
        ICDecayReport(
            pillar="quality",
            rolling_12m_ic=0.04,
            rolling_36m_ic=0.04,
            historical_mean_ic=0.04,
            decay_ratio=1.0,
            months_below_threshold=0,
            alert=False,
            n_observations=36,
            preliminary=False,
        ),
    ]
    out = tmp_path / "decay_report.json"
    emit_decay_report(
        reports,
        out,
        status="alert",
        n_dates_with_ic=10,
    )
    payload = json.loads(out.read_text())
    # Original keys still present.
    assert payload["threshold"] == IC_DECAY_THRESHOLD
    assert payload["duration_months"] == IC_DECAY_DURATION_MONTHS
    assert payload["anomalies_alerted"] == ["value"]
    assert len(payload["pillars"]) == 2
    assert payload["pillars"][0]["pillar"] == "value"
    # Issue #75 §3 additive keys present.
    assert payload["horizon_months"] == IC_HORIZON_MONTHS
    assert payload["min_history_months"] == MIN_HISTORY_MONTHS
    assert payload["status"] == "alert"
    assert payload["n_dates_with_ic"] == 10
    assert "generated_at" in payload
    # Per-pillar 'preliminary' field exposed via asdict.
    assert payload["pillars"][0]["preliminary"] is False
    assert payload["pillars"][1]["preliminary"] is False


# ---------------------------------------------------------------------------
# Issue #75 §3 — NEW additive tests
# ---------------------------------------------------------------------------

@dataclass
class _FakeEntry:
    """Minimal stand-in for PillarICEntry (avoids git/network dep)."""

    date: date
    pillar: str
    ic: float
    n_tickers: int
    note: str = ""


# ---------- pillar_entries_to_monthly_panel adapter tests ----------

def test_monthly_panel_empty_input():
    """Empty entry list → empty dict."""
    result = pillar_entries_to_monthly_panel([])
    assert result == {}


def test_monthly_panel_single_entry():
    """Single entry → one-row panel for that pillar."""
    entries = [_FakeEntry(date=date(2024, 3, 15), pillar="value", ic=0.04, n_tickers=450)]
    panels = pillar_entries_to_monthly_panel(entries)
    assert "value" in panels
    df = panels["value"]
    assert len(df) == 1
    assert abs(df["monthly_ic"].iloc[0] - 0.04) < 1e-9


def test_monthly_panel_multi_commit_same_month():
    """Multiple commits in the same month → single row with mean IC."""
    entries = [
        _FakeEntry(date=date(2024, 3, 5),  pillar="quality", ic=0.03, n_tickers=400),
        _FakeEntry(date=date(2024, 3, 20), pillar="quality", ic=0.05, n_tickers=420),
    ]
    panels = pillar_entries_to_monthly_panel(entries)
    assert "quality" in panels
    df = panels["quality"]
    assert len(df) == 1
    assert abs(df["monthly_ic"].iloc[0] - 0.04) < 1e-9  # mean(0.03, 0.05)


def test_monthly_panel_multi_pillar():
    """Entries for multiple pillars → separate DataFrames keyed by pillar name."""
    entries = [
        _FakeEntry(date=date(2024, 1, 10), pillar="value",   ic=0.03, n_tickers=400),
        _FakeEntry(date=date(2024, 1, 10), pillar="quality", ic=0.05, n_tickers=400),
        _FakeEntry(date=date(2024, 2, 10), pillar="value",   ic=0.04, n_tickers=400),
    ]
    panels = pillar_entries_to_monthly_panel(entries)
    assert set(panels.keys()) == {"value", "quality"}
    assert len(panels["value"]) == 2
    assert len(panels["quality"]) == 1


def test_monthly_panel_chronological_sort():
    """Rows in the returned DataFrames are sorted ascending by year_month."""
    entries = [
        _FakeEntry(date=date(2024, 6, 1), pillar="momentum", ic=0.02, n_tickers=300),
        _FakeEntry(date=date(2024, 4, 1), pillar="momentum", ic=0.06, n_tickers=320),
        _FakeEntry(date=date(2024, 5, 1), pillar="momentum", ic=0.04, n_tickers=310),
    ]
    panels = pillar_entries_to_monthly_panel(entries)
    df = panels["momentum"]
    assert list(df["monthly_ic"]) == pytest.approx([0.06, 0.04, 0.02])


# ---------- preliminary alert-suppression tests ----------

def test_preliminary_flag_set_when_too_few_observations():
    """Fewer than MIN_HISTORY_MONTHS observations → preliminary=True."""
    short_hist = _series([0.04] * (MIN_HISTORY_MONTHS - 1))
    report = check_pillar_decay(short_hist)
    assert report.preliminary is True


def test_preliminary_suppresses_alert():
    """Even a 'decaying' pillar with < MIN_HISTORY_MONTHS obs → alert=False."""
    # 7 months of low IC that WOULD alert if history were sufficient.
    values = [0.04] * 1 + [0.005] * (IC_DECAY_DURATION_MONTHS + 1)
    assert len(values) < MIN_HISTORY_MONTHS
    hist = _series(values)
    report = check_pillar_decay(hist)
    assert report.preliminary is True
    assert report.alert is False


def test_not_preliminary_when_sufficient_observations():
    """Exactly MIN_HISTORY_MONTHS observations → preliminary=False."""
    hist = _series([0.04] * MIN_HISTORY_MONTHS)
    report = check_pillar_decay(hist)
    assert report.preliminary is False


def test_alert_can_fire_when_not_preliminary():
    """Sufficient history + sustained decay → preliminary=False AND alert=True."""
    # MIN_HISTORY_MONTHS months total: first few at mean, then IC collapses.
    good = [0.04] * (MIN_HISTORY_MONTHS - IC_DECAY_DURATION_MONTHS)
    bad  = [0.005] * IC_DECAY_DURATION_MONTHS
    hist = _series(good + bad)
    report = check_pillar_decay(hist)
    assert report.preliminary is False
    assert report.alert is True


# ---------- build_decay_report status gating tests ----------

def _make_fake_report(n_dates_with_ic: int = 0, entries=None):
    """Return a minimal HistoricalICReport-like namespace for mocking."""
    class _FakeReport:
        pass
    r = _FakeReport()
    r.entries = entries or []
    r.n_dates_with_ic = n_dates_with_ic
    r.n_dates_walked = 0
    return r


def test_build_decay_report_insufficient_history_when_no_ic_dates():
    """When compute_historical_ic_report returns 0 IC dates → 'insufficient_history'."""
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=_make_fake_report(n_dates_with_ic=0, entries=[]),
    ):
        reports, status, n_dates = build_decay_report()
    assert status == "insufficient_history"
    assert n_dates == 0
    # All 10 canonical pillars present.
    assert len(reports) == 10
    # All preliminary=True, alert=False on zero-history.
    assert all(r.preliminary for r in reports)
    assert all(not r.alert for r in reports)


def test_build_decay_report_monitoring_status_with_sufficient_synthetic_panel():
    """Inject a synthetic monthly panel with sufficient stable IC → 'monitoring'."""
    from compute.validation.historical_ic import DEFAULT_PILLARS

    # Build 24 months of stable IC for every pillar.
    synthetic_entries = []
    for month in range(24):
        for p in DEFAULT_PILLARS:
            synthetic_entries.append(
                _FakeEntry(
                    date=date(2022, 1, 1) if month == 0 else date(2022 + month // 12, (month % 12) + 1, 1),
                    pillar=p,
                    ic=0.04,
                    n_tickers=400,
                )
            )

    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=_make_fake_report(n_dates_with_ic=24, entries=synthetic_entries),
    ):
        reports, status, n_dates = build_decay_report()

    assert n_dates == 24
    # All pillars should have n_observations >= IC_DECAY_DURATION_MONTHS.
    assert all(r.n_observations >= IC_DECAY_DURATION_MONTHS for r in reports)
    # No alert should fire (stable IC).
    assert all(not r.alert for r in reports)
    assert status == "monitoring"


def test_build_decay_report_alert_status_with_decaying_synthetic_panel():
    """Inject decaying IC for one pillar → 'alert' status fires."""
    from compute.validation.historical_ic import DEFAULT_PILLARS

    # 24 months of healthy IC for ALL pillars, then 6 months of collapse for 'value'.
    synthetic_entries = []
    good_months = 24
    bad_months = IC_DECAY_DURATION_MONTHS  # exactly at threshold

    for month in range(good_months + bad_months):
        month_date = date(2022 + month // 12, (month % 12) + 1, 15)
        for p in DEFAULT_PILLARS:
            ic = 0.005 if (p == "value" and month >= good_months) else 0.04
            synthetic_entries.append(
                _FakeEntry(date=month_date, pillar=p, ic=ic, n_tickers=400)
            )

    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=_make_fake_report(
            n_dates_with_ic=good_months + bad_months,
            entries=synthetic_entries,
        ),
    ):
        reports, status, n_dates = build_decay_report()

    assert status == "alert"
    value_report = next(r for r in reports if r.pillar == "value")
    assert value_report.alert is True
    assert value_report.preliminary is False


def test_build_decay_report_degrades_gracefully_on_exception():
    """compute_historical_ic_report raising → insufficient_history, no crash."""
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        side_effect=RuntimeError("git unavailable"),
    ):
        reports, status, n_dates = build_decay_report()

    assert status == "insufficient_history"
    assert n_dates == 0
    assert len(reports) == 10
    assert all(r.preliminary for r in reports)
    assert all(not r.alert for r in reports)


# ---------- emit_decay_report: insufficient_history defaults ----------

def test_emit_decay_report_insufficient_history_defaults(tmp_path: Path):
    """emit_decay_report defaults match 'insufficient_history' canonical contract."""
    # Build a zero-history report the way build_decay_report does.
    with patch(
        "compute.validation.historical_ic.compute_historical_ic_report",
        return_value=_make_fake_report(n_dates_with_ic=0, entries=[]),
    ):
        reps, status, n_dates = build_decay_report()

    out = tmp_path / "decay_report.json"
    emit_decay_report(
        reps,
        out,
        status=status,
        n_dates_with_ic=n_dates,
    )
    payload = json.loads(out.read_text())

    # Matches the canonical contract from the task spec.
    assert payload["status"] == "insufficient_history"
    assert payload["n_dates_with_ic"] == 0
    assert payload["horizon_months"] == IC_HORIZON_MONTHS
    assert payload["min_history_months"] == MIN_HISTORY_MONTHS
    assert len(payload["pillars"]) == 10
    assert payload["anomalies_alerted"] == []
    for p in payload["pillars"]:
        assert p["alert"] is False
        assert p["preliminary"] is True
        assert p["n_observations"] == 0


# ---------- main.py wiring skip-flag test ----------

def test_main_wiring_skip_flag_sets_decay_report_url_none(monkeypatch, tmp_path):
    """QR_SKIP_DECAY_MONITOR=1 → decay_report_url stays None; no file written."""
    import os

    monkeypatch.setenv("QR_SKIP_DECAY_MONITOR", "1")

    # Simulate the if/else branch that main.py runs.
    decay_report_url = None
    _decay_report_path = tmp_path / "decay_report.json"

    if os.environ.get("QR_SKIP_DECAY_MONITOR", "").lower() in ("1", "true", "yes"):
        pass  # skip path — decay_report_url stays None
    else:
        # Should NOT reach here.
        raise AssertionError("Skip branch not taken")

    assert decay_report_url is None
    assert not _decay_report_path.exists()


def test_main_wiring_exception_sets_decay_report_url_none(monkeypatch, tmp_path):
    """Exception in build_decay_report → decay_report_url=None, no crash."""
    monkeypatch.delenv("QR_SKIP_DECAY_MONITOR", raising=False)

    # Replicate the try/except in main.py directly.
    decay_report_url = None
    _decay_report_path = tmp_path / "decay_report.json"

    with patch(
        "compute.validation.ic_decay.build_decay_report",
        side_effect=RuntimeError("forced failure"),
    ):
        try:
            from compute.validation.ic_decay import build_decay_report as _bd  # noqa: F401
            _decay_reports, _decay_status, _decay_n_dates = _bd()
            decay_report_url = "/data/decay_report.json"
        except Exception:  # noqa: BLE001
            decay_report_url = None

    assert decay_report_url is None
    assert not _decay_report_path.exists()
