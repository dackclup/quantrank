"""Tests for ``scripts.generate_honest_baseline`` CLI.

Phase 4.6 task #2f — honest-baseline closing report.

Tests the CLI shape + argparse + JSON payload structure. The
underlying orchestrators (`compute_historical_ic_report` +
`compute_manipulation_distribution_shift`) are exercised by their
own test files in this same directory; here we only verify the
CLI's wiring is correct.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import date

import pytest

from scripts import generate_honest_baseline as gen

# ---------------------------------------------------------------- _parse_date


def test_parse_date_accepts_iso() -> None:
    assert gen._parse_date("2024-06-01") == date(2024, 6, 1)


def test_parse_date_rejects_bad_format() -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="invalid date"):
        gen._parse_date("June 1, 2024")


# ---------------------------------------------------------------- argparse


def test_arg_parser_requires_start_and_end() -> None:
    parser = gen.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--start-date", "2024-01-01"])


def test_arg_parser_accepts_minimum_args() -> None:
    parser = gen.build_arg_parser()
    args = parser.parse_args([
        "--start-date", "2024-06-01",
        "--end-date", "2025-06-01",
    ])
    assert args.start_date == date(2024, 6, 1)
    assert args.end_date == date(2025, 6, 1)
    assert args.horizon_months == 6
    assert args.min_tickers == 30
    assert args.json is False
    assert args.text is False
    assert args.no_banner is False


def test_arg_parser_json_and_text_mutually_exclusive() -> None:
    parser = gen.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--start-date", "2024-06-01",
            "--end-date", "2025-06-01",
            "--json", "--text",
        ])


# ---------------------------------------------------------------- main / exit codes


def test_main_negative_horizon_exits_1() -> None:
    rc = gen.main([
        "--start-date", "2024-06-01",
        "--end-date", "2025-06-01",
        "--horizon-months", "-3",
        "--no-banner",
    ])
    assert rc == 1


def test_main_start_after_end_exits_1() -> None:
    rc = gen.main([
        "--start-date", "2025-06-01",
        "--end-date", "2024-06-01",
        "--no-banner",
    ])
    assert rc == 1


def test_main_far_future_window_exits_2_empty_report(monkeypatch) -> None:
    """Window with no rankings.json commits → exit code 2 (empty report)."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--no-banner",
            "--text",
        ])
    assert rc == 2


def test_main_text_mode_prints_disclaimer_banner(monkeypatch) -> None:
    """In text mode without --no-banner, the honest-baseline banner prints to stderr."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--text",
        ])
    assert "HONEST-BASELINE REPORT" in stderr.getvalue()
    assert "naive" in stderr.getvalue().lower() or "NAIVE" in stderr.getvalue()


def test_main_no_banner_flag_suppresses_banner() -> None:
    """--no-banner suppresses the stderr disclaimer block."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--text",
            "--no-banner",
        ])
    assert "HONEST-BASELINE REPORT" not in stderr.getvalue()


def test_main_json_mode_emits_valid_json(monkeypatch) -> None:
    """--json mode emits a JSON payload to stdout."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--json",
            "--no-banner",
        ])
    payload = json.loads(stdout.getvalue())
    assert "report_version" in payload
    assert "honest_alpha_ceiling" in payload
    assert "pillar_ic" in payload
    assert "manipulation_distribution" in payload
    assert "pbo_dsr" in payload


def test_main_json_payload_carries_alpha_ceiling() -> None:
    """The honest 2-5% α ceiling is hardcoded into every JSON payload."""
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--json",
            "--no-banner",
        ])
    payload = json.loads(stdout.getvalue())
    assert payload["honest_alpha_ceiling"]["lower_pct"] == 2.0
    assert payload["honest_alpha_ceiling"]["upper_pct"] == 5.0
    assert "Research Report v1.0" in payload["honest_alpha_ceiling"]["source"]


def test_main_json_payload_carries_disclaimer() -> None:
    """JSON payload includes the honest_baseline_disclaimer string."""
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--json",
            "--no-banner",
        ])
    payload = json.loads(stdout.getvalue())
    assert "honest_baseline_disclaimer" in payload
    assert "NAIVE" in payload["honest_baseline_disclaimer"]
    assert "McLean-Pontiff" in payload["honest_baseline_disclaimer"]


def test_main_json_default_includes_banner_in_payload() -> None:
    """Without --no-banner, JSON mode embeds __banner__ into the payload."""
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        gen.main([
            "--start-date", "2099-01-01",
            "--end-date", "2099-12-31",
            "--json",
        ])
    payload = json.loads(stdout.getvalue())
    assert "__banner__" in payload
    assert "HONEST-BASELINE" in payload["__banner__"]


# ---------------------------------------------------------------- _report_to_payload


def test_report_to_payload_shape() -> None:
    """Synthetic mini-reports → payload with all the expected sections."""
    from compute.validation.historical_ic import (
        HistoricalICReport,
        PillarICSummary,
    )
    from compute.validation.manipulation_distribution import ShiftReport

    ic_report = HistoricalICReport(
        start_date=date(2024, 6, 1),
        end_date=date(2025, 6, 1),
        horizon_months=6,
        n_dates_walked=5,
        n_dates_with_ic=4,
        entries=[],
        summary_by_pillar={
            "value": PillarICSummary(
                pillar="value", n_dates=4,
                mean=0.03, std=0.02, median=0.025,
                min_value=0.01, max_value=0.05,
                ic_ir=3.0, hit_rate=0.75,
            ),
        },
        note="synthetic",
    )
    manip_report = ShiftReport(
        start_date=date(2024, 6, 1),
        end_date=date(2025, 6, 1),
        n_dates=0,
        n_unique_tickers=0,
        per_date_summary={},
        mean_delta=None,
        std_delta=None,
        high_count_delta=None,
        high_count_first=None,
        high_count_last=None,
        note="empty",
    )

    payload = gen._report_to_payload(
        date(2024, 6, 1), date(2025, 6, 1), 6, ic_report, manip_report,
    )
    assert payload["pillar_ic"]["n_dates_walked"] == 5
    assert payload["pillar_ic"]["n_dates_with_ic"] == 4
    assert payload["pillar_ic"]["rows"][0]["pillar"] == "value"
    assert payload["pillar_ic"]["rows"][0]["mean_ic"] == pytest.approx(0.03, abs=1e-9)
    assert payload["pillar_ic"]["rows"][0]["ic_ir"] == pytest.approx(3.0, abs=1e-9)
    assert payload["manipulation_distribution"] is None
    assert payload["pbo_dsr"]["pbo"] is None
    assert payload["window"]["horizon_months"] == 6


def test_report_to_payload_with_populated_manipulation() -> None:
    """Manipulation report with deltas → payload mirrors the delta cells."""
    from compute.validation.historical_ic import (
        HistoricalICReport,
    )
    from compute.validation.manipulation_distribution import (
        DistributionSummary,
        ShiftReport,
    )

    ic_report = HistoricalICReport(
        start_date=date(2024, 6, 1),
        end_date=date(2025, 6, 1),
        horizon_months=6,
        n_dates_walked=0,
        n_dates_with_ic=0,
        entries=[],
        summary_by_pillar={},
        note="empty",
    )
    summary_first = DistributionSummary(
        n_tickers=500, n_non_null=480,
        mean=12.0, std=15.0, median=10.0,
        q25=5.0, q75=18.0, q95=40.0, max_value=85.0,
        low_count=300, moderate_count=150, high_count=30,
        top_3_tickers=(("AAA", 85.0),),
    )
    summary_last = DistributionSummary(
        n_tickers=500, n_non_null=485,
        mean=14.5, std=16.0, median=12.0,
        q25=6.0, q75=20.0, q95=45.0, max_value=90.0,
        low_count=290, moderate_count=160, high_count=35,
        top_3_tickers=(("BBB", 90.0),),
    )
    manip_report = ShiftReport(
        start_date=date(2024, 6, 1),
        end_date=date(2025, 6, 1),
        n_dates=2,
        n_unique_tickers=500,
        per_date_summary={
            date(2024, 6, 1): summary_first,
            date(2025, 6, 1): summary_last,
        },
        mean_delta=2.5,
        std_delta=1.0,
        high_count_delta=5,
        high_count_first=30,
        high_count_last=35,
        note="populated",
    )

    payload = gen._report_to_payload(
        date(2024, 6, 1), date(2025, 6, 1), 6, ic_report, manip_report,
    )
    md = payload["manipulation_distribution"]
    assert md is not None
    assert md["first_date_mean"] == pytest.approx(12.0)
    assert md["last_date_mean"] == pytest.approx(14.5)
    assert md["mean_delta"] == pytest.approx(2.5)
    assert md["high_count_first"] == 30
    assert md["high_count_last"] == 35
    assert md["high_count_delta"] == 5


# ---------------------------------------------------------------- HONEST_DISCLAIMER_BANNER


def test_disclaimer_banner_contains_required_phrases() -> None:
    """The banner must surface the 5 mission-mandatory claims."""
    banner = gen.HONEST_DISCLAIMER_BANNER
    assert "NAIVE" in banner
    assert "McLean-Pontiff" in banner
    assert "2-5%" in banner
    assert "Rule 16" in banner
    assert "S&P 500" in banner
