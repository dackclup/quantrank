"""Tests for ``compute.portfolio.pit_fundamentals`` — the anti-look-ahead guardrail.

These pin the methodology-scientist's mandatory PR-2b guardrail: at a historical
rebalance date T the fundamentals fed to the pillars must be ONLY what was filed
on or before T (original 10-Ks, not later amendments). The load-bearing case is
``test_leak_probe`` — a fantastic value filed just after T must NOT be used.
"""
from __future__ import annotations

from compute.portfolio.pit_fundamentals import (
    pit_history_rows,
    pit_snapshot_fields,
    select_pit_annual_values,
)


def _row(metric, fy, value, filing_date, form_type="10-K"):
    return {
        "metric": metric,
        "fiscal_year": fy,
        "value": value,
        "filing_date": filing_date,
        "form_type": form_type,
    }


def test_select_excludes_filings_after_as_of() -> None:
    rows = [
        _row("revenue", 2022, 100.0, "2023-02-15"),
        _row("revenue", 2023, 200.0, "2024-02-15"),  # filed AFTER as_of
    ]
    out = select_pit_annual_values(rows, as_of="2023-06-30")
    assert out["revenue"] == 100.0  # the 2023 FY (filed 2024) is invisible at T


def test_select_excludes_amendments() -> None:
    rows = [
        _row("revenue", 2022, 100.0, "2023-02-15", form_type="10-K"),
        _row("revenue", 2022, 90.0, "2023-09-01", form_type="10-K/A"),  # restatement
    ]
    out = select_pit_annual_values(rows, as_of="2024-01-01")
    assert out["revenue"] == 100.0  # original 10-K, not the 10-K/A restatement


def test_select_takes_most_recent_fiscal_year() -> None:
    rows = [
        _row("net_income", 2020, 10.0, "2021-02-15"),
        _row("net_income", 2022, 30.0, "2023-02-15"),
        _row("net_income", 2021, 20.0, "2022-02-15"),
    ]
    out = select_pit_annual_values(rows, as_of="2023-06-30")
    assert out["net_income"] == 30.0  # FY2022, the largest eligible fiscal year


def test_select_tiebreak_prefers_later_filing() -> None:
    rows = [
        _row("revenue", 2022, 100.0, "2023-02-15"),
        _row("revenue", 2022, 105.0, "2023-03-01"),  # same FY, later original filing
    ]
    out = select_pit_annual_values(rows, as_of="2024-01-01")
    assert out["revenue"] == 105.0


def test_leak_probe_future_blockbuster_is_ignored() -> None:
    """A fantastic value filed ONE DAY after T must not change the as-of-T view."""
    base = [_row("net_income", 2022, 50.0, "2023-02-28")]
    as_of = "2023-06-30"
    clean = select_pit_annual_values(base, as_of)
    leaked = select_pit_annual_values(
        base + [_row("net_income", 2023, 9999.0, "2023-07-01")],  # T + 1 day
        as_of,
    )
    assert clean == leaked == {"net_income": 50.0}


def test_none_and_nan_values_skipped() -> None:
    rows = [
        _row("revenue", 2023, None, "2024-02-15"),
        _row("revenue", 2022, float("nan"), "2023-02-15"),
        _row("revenue", 2021, 80.0, "2022-02-15"),
    ]
    out = select_pit_annual_values(rows, as_of="2024-06-30")
    assert out == {"revenue": 80.0}


def test_derived_free_cash_flow_and_ebitda() -> None:
    rows = [
        _row("operating_cash_flow", 2022, 100.0, "2023-02-15"),
        _row("capex", 2022, -30.0, "2023-02-15"),  # negative outflow convention
        _row("operating_income", 2022, 60.0, "2023-02-15"),
        _row("depreciation_and_amortization", 2022, 15.0, "2023-02-15"),
    ]
    out = pit_snapshot_fields(rows, as_of="2024-01-01")
    assert out["free_cash_flow"] == 70.0  # 100 - |−30|
    assert out["ebitda"] == 75.0  # 60 + 15


def test_supplied_fcf_not_overwritten() -> None:
    rows = [
        _row("free_cash_flow", 2022, 42.0, "2023-02-15"),
        _row("operating_cash_flow", 2022, 100.0, "2023-02-15"),
        _row("capex", 2022, 30.0, "2023-02-15"),
    ]
    out = pit_snapshot_fields(rows, as_of="2024-01-01")
    assert out["free_cash_flow"] == 42.0  # the filed value wins over the derivation


def test_pit_history_rows_returns_only_eligible() -> None:
    rows = [
        _row("revenue", 2021, 80.0, "2022-02-15"),
        _row("revenue", 2022, 100.0, "2023-02-15"),
        _row("revenue", 2023, 200.0, "2024-02-15"),  # future
        _row("revenue", 2020, 70.0, "2021-09-01", form_type="10-K/A"),  # amendment
    ]
    kept = pit_history_rows(rows, as_of="2023-06-30")
    fys = sorted(r["fiscal_year"] for r in kept)
    assert fys == [2021, 2022]  # future + amendment dropped, both eligible years kept
