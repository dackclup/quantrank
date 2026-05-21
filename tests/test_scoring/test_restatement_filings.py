"""Unit tests for compute.scoring.restatement_filings (PR 4.5b).

Uses the ``filings_override`` inject path on both check_* entry points
to keep tests offline. Network-level fetcher tests live separately
under the ``@pytest.mark.network`` marker (deferred to a follow-up PR).
"""

from __future__ import annotations

from datetime import date

from compute import config
from compute.scoring.restatement_filings import (
    HIGH_CONFIDENCE_WINDOW_DAYS,
    HighConfidenceRestatementResult,
    LateFilingResult,
    RestatementHistoryResult,
    _filing_date_within,
    check_late_filing,
    check_restatement_history,
    compute_high_confidence_restatement,
    get_amendment_filing_dates,
)

# ---------------------------------------------------------------------------
# _filing_date_within helper
# ---------------------------------------------------------------------------


def test_filing_date_within_inside_window():
    asof = date(2026, 5, 16)
    # 100 days ago — well inside 365d
    assert _filing_date_within("2026-02-05", asof, 365) is True


def test_filing_date_within_at_boundary():
    asof = date(2026, 5, 16)
    # Exactly 365 days ago — inclusive lower bound
    assert _filing_date_within("2025-05-16", asof, 365) is True


def test_filing_date_within_outside_window():
    asof = date(2026, 5, 16)
    # 400 days ago — outside 365d
    assert _filing_date_within("2025-04-11", asof, 365) is False


def test_filing_date_within_future_date_rejected():
    asof = date(2026, 5, 16)
    # Future filing date — sanity guard, not a real case
    assert _filing_date_within("2026-08-01", asof, 365) is False


def test_filing_date_within_malformed_string():
    asof = date(2026, 5, 16)
    assert _filing_date_within("not-a-date", asof, 365) is False
    assert _filing_date_within("", asof, 365) is False


# ---------------------------------------------------------------------------
# check_restatement_history
# ---------------------------------------------------------------------------


def test_restatement_history_no_filings():
    result = check_restatement_history(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[],
    )
    assert isinstance(result, RestatementHistoryResult)
    assert result.fired is False
    assert result.count == 0
    assert result.latest_filing_date is None
    assert result.latest_filing_url is None


def test_restatement_history_one_filing_inside_window():
    result = check_restatement_history(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "0001234567-24-000123",
                "form": "10-K/A",
                "filing_date": "2024-03-15",
                "filing_url": "https://www.sec.gov/foo",
            }
        ],
    )
    assert result.fired is True
    assert result.count == 1
    assert result.latest_filing_date == "2024-03-15"
    assert result.latest_filing_url == "https://www.sec.gov/foo"


def test_restatement_history_recurrent_restater():
    # 3 amendments in trailing 5y — recurrent restater. Flag still fires
    # (binary), but count reflects the recurrence for UI use.
    result = check_restatement_history(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "a",
                "form": "10-K/A",
                "filing_date": "2025-08-10",
                "filing_url": "u3",
            },
            {
                "accession": "b",
                "form": "10-K/A",
                "filing_date": "2023-11-20",
                "filing_url": "u2",
            },
            {
                "accession": "c",
                "form": "10-Q/A",
                "filing_date": "2022-04-05",
                "filing_url": "u1",
            },
        ],
    )
    assert result.fired is True
    assert result.count == 3
    # Override list is sorted desc by filing_date in the cache writer,
    # which check_restatement_history relies on.
    assert result.latest_filing_date == "2025-08-10"


def test_restatement_history_filing_outside_window_excluded():
    # 6-year-old amendment — outside the 5y window, should NOT fire.
    result = check_restatement_history(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "old",
                "form": "10-K/A",
                "filing_date": "2020-01-15",
                "filing_url": "u",
            }
        ],
    )
    assert result.fired is False
    assert result.count == 0


def test_restatement_history_lookback_constant_5y_plus_leap_buffer():
    # Sanity-pin the config — 5y window is the Hennes-Leone-Miller 2008
    # cohort window. 1825 days = 5 × 365 (leap-day absorbed by inclusive
    # _filing_date_within bounds).
    assert config.RESTATEMENT_HISTORY_LOOKBACK_DAYS == 1825


def test_restatement_history_fetch_failure_returns_clean_result():
    # filings_override=None + no EDGAR_USER_AGENT set → fetcher returns
    # None. The check function must not raise; returns a fired=False
    # result so the caller can append nothing to valuation_warnings.
    # (We don't override; we rely on the fetcher's None-on-no-identity
    # behavior which the test env satisfies.)
    import os

    # Save + clear identity so the fetch path returns None
    saved = os.environ.pop("EDGAR_USER_AGENT", None)
    try:
        result = check_restatement_history(
            "NONEXISTENT-TICKER-XYZ",
            asof=date(2026, 5, 16),
        )
    finally:
        if saved is not None:
            os.environ["EDGAR_USER_AGENT"] = saved
    assert result.fired is False
    assert result.count == 0


# ---------------------------------------------------------------------------
# check_late_filing
# ---------------------------------------------------------------------------


def test_late_filing_no_filings():
    result = check_late_filing(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[],
    )
    assert isinstance(result, LateFilingResult)
    assert result.fired is False
    assert result.count == 0
    assert result.latest_form is None


def test_late_filing_nt_10k_inside_window():
    result = check_late_filing(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "0001234567-26-000001",
                "form": "NT 10-K",
                "filing_date": "2026-03-15",
                "filing_url": "https://www.sec.gov/12b25",
            }
        ],
    )
    assert result.fired is True
    assert result.count == 1
    assert result.latest_filing_date == "2026-03-15"
    assert result.latest_form == "NT 10-K"


def test_late_filing_nt_10q_inside_window():
    result = check_late_filing(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "x",
                "form": "NT 10-Q",
                "filing_date": "2026-04-01",
                "filing_url": "u",
            }
        ],
    )
    assert result.fired is True
    assert result.latest_form == "NT 10-Q"


def test_late_filing_old_filing_excluded():
    # 400-day-old late filing — outside the 365d window
    result = check_late_filing(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "old",
                "form": "NT 10-K",
                "filing_date": "2025-04-11",
                "filing_url": "u",
            }
        ],
    )
    assert result.fired is False


def test_late_filing_lookback_constant():
    # Sanity-pin the config — 365d window per Bartov-Lai-Yeung 2002.
    assert config.LATE_FILING_LOOKBACK_DAYS == 365


def test_late_filing_multiple_within_window_returns_latest():
    result = check_late_filing(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {
                "accession": "newer",
                "form": "NT 10-Q",
                "filing_date": "2026-04-15",
                "filing_url": "u_newer",
            },
            {
                "accession": "older",
                "form": "NT 10-K",
                "filing_date": "2025-08-01",
                "filing_url": "u_older",
            },
        ],
    )
    assert result.fired is True
    assert result.count == 2
    # Per fetch-path contract: input list is desc-sorted by filing_date,
    # so check_late_filing returns the latest as matching[0].
    assert result.latest_filing_date == "2026-04-15"
    assert result.latest_form == "NT 10-Q"


# ---------------------------------------------------------------------------
# Phase 2.2 of epic #150 — restatement_high_confidence (amendment ↔ Item 4.02)
# ---------------------------------------------------------------------------


def test_high_confidence_window_constant():
    """Pin the 90-day co-occurrence window per Schroeder 2024 SSRN §3.2."""
    assert HIGH_CONFIDENCE_WINDOW_DAYS == 90


def test_get_amendment_filing_dates_returns_parsed_iso_dates():
    dates = get_amendment_filing_dates(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {"accession": "a1", "form": "10-K/A", "filing_date": "2025-09-01"},
            {"accession": "a2", "form": "10-Q/A", "filing_date": "2024-03-15"},
        ],
    )
    assert dates == (date(2025, 9, 1), date(2024, 3, 15))


def test_get_amendment_filing_dates_drops_out_of_window_entries():
    dates = get_amendment_filing_dates(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {"accession": "in", "form": "10-K/A", "filing_date": "2025-09-01"},
            # >5y old — outside RESTATEMENT_HISTORY_LOOKBACK_DAYS
            {"accession": "out", "form": "10-K/A", "filing_date": "2018-01-01"},
        ],
    )
    assert dates == (date(2025, 9, 1),)


def test_get_amendment_filing_dates_drops_malformed_dates():
    dates = get_amendment_filing_dates(
        "TST",
        asof=date(2026, 5, 16),
        filings_override=[
            {"accession": "ok", "form": "10-K/A", "filing_date": "2025-09-01"},
            {"accession": "bad", "form": "10-K/A", "filing_date": "not-a-date"},
            {"accession": "missing", "form": "10-K/A"},  # no filing_date key
        ],
    )
    assert dates == (date(2025, 9, 1),)


def test_high_confidence_no_amendments_returns_false():
    result = compute_high_confidence_restatement([], [date(2025, 6, 1)])
    assert isinstance(result, HighConfidenceRestatementResult)
    assert result.fired is False
    assert result.co_occurrence_count == 0


def test_high_confidence_no_non_reliance_returns_false():
    result = compute_high_confidence_restatement([date(2025, 6, 1)], [])
    assert result.fired is False
    assert result.co_occurrence_count == 0


def test_high_confidence_amendment_within_90d_of_item_4_02_fires():
    """10-K/A on 2025-09-01 + Item 4.02 8-K on 2025-08-15 → 17 days
    apart → within 90d window → fires."""
    result = compute_high_confidence_restatement(
        amendment_dates=[date(2025, 9, 1)],
        non_reliance_dates=[date(2025, 8, 15)],
    )
    assert result.fired is True
    assert result.co_occurrence_count == 1
    assert result.latest_amendment_date == "2025-09-01"
    assert result.latest_non_reliance_date == "2025-08-15"


def test_high_confidence_amendment_outside_window_does_not_fire():
    """10-K/A on 2025-09-01 + Item 4.02 8-K on 2025-04-01 → 153 days
    apart → outside 90d window → no fire."""
    result = compute_high_confidence_restatement(
        amendment_dates=[date(2025, 9, 1)],
        non_reliance_dates=[date(2025, 4, 1)],
    )
    assert result.fired is False
    assert result.co_occurrence_count == 0


def test_high_confidence_item_4_02_after_amendment_within_window_fires():
    """Item 4.02 can also LAND AFTER the amendment (e.g., the 8-K is
    filed only when SEC inquires post-amendment). The window is
    symmetric ±90d."""
    result = compute_high_confidence_restatement(
        amendment_dates=[date(2025, 9, 1)],
        non_reliance_dates=[date(2025, 11, 15)],  # 75 days AFTER amd
    )
    assert result.fired is True


def test_high_confidence_counts_distinct_amendments_paired():
    """Two amendments in the same fiscal cleanup (10-K/A + 10-Q/A)
    can pair with the same Item 4.02 — count = 2 amendments."""
    result = compute_high_confidence_restatement(
        amendment_dates=[date(2025, 9, 1), date(2025, 9, 15)],
        non_reliance_dates=[date(2025, 8, 20)],
    )
    assert result.fired is True
    assert result.co_occurrence_count == 2
    # latest amendment is 2025-09-15
    assert result.latest_amendment_date == "2025-09-15"


def test_high_confidence_picks_nearest_item_4_02_for_each_amendment():
    """When two Item 4.02 filings are within the window of an
    amendment, the function pairs with the NEAREST one (smallest gap)."""
    result = compute_high_confidence_restatement(
        amendment_dates=[date(2025, 9, 1)],
        non_reliance_dates=[date(2025, 7, 1), date(2025, 8, 25)],
    )
    assert result.fired is True
    # nearest is 2025-08-25 (7 days vs 62 days)
    assert result.latest_non_reliance_date == "2025-08-25"


def test_high_confidence_custom_window_days_widens_match():
    """Window override works — same dates 150d apart fire with
    window_days=180 but not with default (90)."""
    amd = [date(2025, 9, 1)]
    nr = [date(2025, 4, 4)]  # 150 days earlier
    assert compute_high_confidence_restatement(amd, nr).fired is False
    assert compute_high_confidence_restatement(amd, nr, window_days=180).fired is True

