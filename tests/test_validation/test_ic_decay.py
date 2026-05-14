"""Tests for compute.validation.ic_decay (Phase 4b §3).

Anchors McLean-Pontiff (2016) decay-detection behavior:

- Stable pillar with constant IC → no alert
- Pillar that drops to 30% of mean for 7 months → alert fires
- Edge: 5 months below threshold ≠ alert (just under duration_months=6)
- Pillar with zero / negative historical mean → no alert (the metric is
  meaningless against a never-positive baseline)
- emit_decay_report writes a well-formed JSON payload
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from compute.validation.ic_decay import (
    IC_DECAY_DURATION_MONTHS,
    IC_DECAY_THRESHOLD,
    ICDecayReport,
    check_all_pillars,
    check_pillar_decay,
    emit_decay_report,
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
    """Round-trip a synthetic report through emit + json.load."""
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
        ),
    ]
    out = tmp_path / "decay_report.json"
    emit_decay_report(reports, out)
    payload = json.loads(out.read_text())
    assert payload["threshold"] == IC_DECAY_THRESHOLD
    assert payload["duration_months"] == IC_DECAY_DURATION_MONTHS
    assert payload["anomalies_alerted"] == ["value"]
    assert len(payload["pillars"]) == 2
    assert payload["pillars"][0]["pillar"] == "value"
