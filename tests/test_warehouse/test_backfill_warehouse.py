"""Offline tests for the compute.warehouse backfill (Slice 2).

All tests run without network access and without SEC EDGAR.  They use
synthetic data built entirely in-process.

Coverage targets
----------------
B1  No look-ahead: a fundamental filed at T+1 never appears in the T row.
    Uses synthetic annual rows with explicit filing-dates.

B2  Survivorship: a ticker removed from the index after date D is PRESENT
    in the as-of cross-section for dates <= D and ABSENT after D.
    Uses a synthetic membership ledger (monkeypatched _load_events).

B3  Forward-only flags are NULL (not False) in pit_replay rows; the 6
    replayed vetoes are True/False in those rows.

B4  row_provenance == "pit_replay" for backfill rows.

B5  replay_completeness is present, in [0, 1], and < 1.0 (some flags NULL).

B6  Live-path regression: flatten_stock with default params (no null_flags)
    produces the same bool True/False for all flag/warn columns as before
    Slice-2 changes — the live path is byte-identical to Slice-1.

B7  _weekly_run_dates returns Fridays between start and end (inclusive).

B8  FORWARD_ONLY_FLAGS is a subset of KNOWN_RISK_FLAGS | KNOWN_VALUATION_WARNINGS.

B9  flag_registry sanity-check at import time: unregistered forward-only entry
    raises ValueError (module-level guard).

B10 _pit_snapshot returns None fields for a future filing (look-ahead guard).
    Specifically: a value with filing_date = T+1 must NOT appear in the
    snapshot for as_of = T.

B11 _write_backfill_partition creates year=/run_date= partition layout.

B12 Idempotent write: running _write_backfill_partition twice for the same
    run_date overwrites (not appends).

B13 replay_completeness = 1.0 when null_flags=frozenset() (no nulls).

B14 Verify that flatten_stock with null_flags=FORWARD_ONLY_FLAGS leaves
    the 6 replayed vetoes as True/False and forward-only flags as None.

B15 No silent False in pit_replay rows: every flag_* and warn_* column for
    flags in FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES must be
    None (not False) in a pit_replay row produced by backfill_warehouse.py.
    This is the core "no false negatives in replay" regression guard.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Synthetic model builders (reused / extended from test_warehouse.py)
# ---------------------------------------------------------------------------

def _make_pillar_scores():
    from compute.output.schemas import PillarScores
    return PillarScores(quality=60.0, value=55.0, growth=70.0, momentum=65.0,
                        health=50.0, profitability=75.0, technical=80.0, risk=45.0)


def _make_raw_metrics():
    from compute.output.schemas import RawMetrics
    return RawMetrics(**{f: None for f in RawMetrics.model_fields})


def _make_data_quality():
    from compute.output.schemas import DataQuality
    overrides = {
        "missing_metrics": [],
        "imputed_metrics": [],
    }
    return DataQuality(**{f: overrides.get(f, None) for f in DataQuality.model_fields})


def _make_detail(
    ticker: str = "AAPL",
    risk_flags: list[str] | None = None,
    valuation_warnings: list[str] | None = None,
) -> Any:
    from compute.output.schemas import StockDetail
    return StockDetail(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector="Technology",
        recommendation="neutral",
        rank=1,
        composite_score=55.0,
        current_price=100.0,
        pillar_scores=_make_pillar_scores(),
        raw_metrics=_make_raw_metrics(),
        data_quality=_make_data_quality(),
        risk_flags=risk_flags or [],
        valuation_warnings=valuation_warnings or [],
        index_membership="sp500",
        index_memberships=["sp500"],
    )


def _make_pit_annual_rows(
    metric: str,
    value: float,
    fiscal_year: int,
    filing_date_str: str,
    form_type: str = "10-K",
) -> dict:
    """Build one synthetic annual row in the backfill_portfolio_pit format."""
    return {
        "metric": metric,
        "fiscal_year": fiscal_year,
        "value": value,
        "filing_date": filing_date_str,
        "form_type": form_type,
    }


# ---------------------------------------------------------------------------
# B7 — _weekly_run_dates
# ---------------------------------------------------------------------------

class TestWeeklyRunDates:
    """B7: _weekly_run_dates returns Fridays in [start, end]."""

    def test_returns_fridays(self):
        from scripts.backfill_warehouse import _weekly_run_dates
        dates = _weekly_run_dates(date(2024, 1, 1), date(2024, 1, 31))
        for d in dates:
            assert d.weekday() == 4, f"{d} is not a Friday"

    def test_non_empty_for_valid_range(self):
        from scripts.backfill_warehouse import _weekly_run_dates
        dates = _weekly_run_dates(date(2024, 1, 1), date(2024, 2, 28))
        assert len(dates) >= 4, "Expected at least 4 Fridays in 2 months"

    def test_empty_for_inverted_range(self):
        from scripts.backfill_warehouse import _weekly_run_dates
        dates = _weekly_run_dates(date(2024, 2, 1), date(2024, 1, 1))
        assert dates == [], "Expected no dates when start > end"

    def test_cadence_is_weekly(self):
        from scripts.backfill_warehouse import _weekly_run_dates
        dates = _weekly_run_dates(date(2024, 1, 1), date(2024, 2, 28))
        for i in range(1, len(dates)):
            diff = (dates[i] - dates[i - 1]).days
            assert diff == 7, f"Expected 7-day gap, got {diff}"

    def test_first_date_on_or_after_start(self):
        from scripts.backfill_warehouse import _weekly_run_dates
        start = date(2024, 1, 3)  # Wednesday
        dates = _weekly_run_dates(start, date(2024, 1, 31))
        assert dates[0] >= start
        assert dates[0].weekday() == 4  # Friday

    def test_all_dates_within_range(self):
        from scripts.backfill_warehouse import _weekly_run_dates
        start = date(2024, 1, 1)
        end = date(2024, 3, 31)
        dates = _weekly_run_dates(start, end)
        for d in dates:
            assert start <= d <= end


# ---------------------------------------------------------------------------
# B8 — FORWARD_ONLY_FLAGS is a valid subset
# ---------------------------------------------------------------------------

class TestForwardOnlyFlagsRegistry:
    """B8: FORWARD_ONLY_FLAGS subset-check; B9: unregistered entry guard."""

    def test_forward_only_is_subset_of_all_known(self):
        """B8: every forward-only flag is in KNOWN_RISK_FLAGS | KNOWN_VALUATION_WARNINGS."""
        from compute.warehouse.flag_registry import (
            FORWARD_ONLY_FLAGS,
            KNOWN_RISK_FLAGS,
            KNOWN_VALUATION_WARNINGS,
        )
        all_known = KNOWN_RISK_FLAGS | KNOWN_VALUATION_WARNINGS
        unregistered = FORWARD_ONLY_FLAGS - all_known
        assert unregistered == frozenset(), (
            f"FORWARD_ONLY_FLAGS contains unregistered entries: {sorted(unregistered)}"
        )

    def test_forward_only_non_empty(self):
        """B8: FORWARD_ONLY_FLAGS is non-empty (we have genuine forward-only flags)."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        assert len(FORWARD_ONLY_FLAGS) > 0

    def test_replay_flags_not_in_forward_only(self):
        """B8: the 6 replayed vetoes must NOT be in FORWARD_ONLY_FLAGS."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        replayed = {
            "data_quality_input_corruption",
            "altman_distress",
            "sloan_accruals_top_decile",
            "net_issuance_top_decile",
            "beneish_manipulation_veto",
            "dechow_manipulation_veto",
        }
        overlap = replayed & FORWARD_ONLY_FLAGS
        assert overlap == set(), (
            f"Replayed vetoes must NOT be in FORWARD_ONLY_FLAGS: {overlap}"
        )

    def test_non_reliance_filing_is_forward_only(self):
        """B8: non_reliance_filing is forward-only (no 8-K history in PIT data)."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        assert "non_reliance_filing" in FORWARD_ONLY_FLAGS

    def test_low_liquidity_is_forward_only(self):
        """B8: low_liquidity uses live ADV — not PIT-replayable."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        assert "low_liquidity" in FORWARD_ONLY_FLAGS


# ---------------------------------------------------------------------------
# B3 / B4 / B5 — flatten_stock pit_replay behavior
# ---------------------------------------------------------------------------

class TestFlattenStockPitReplay:
    """B3: forward-only flags are NULL; B4: row_provenance; B5: replay_completeness."""

    def test_B4_row_provenance_pit_replay(self):
        """B4: row_provenance='pit_replay' when passed explicitly."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        assert row["row_provenance"] == "pit_replay"

    def test_B3_forward_only_flags_are_none(self):
        """B3: forward-only flag columns are None (not False) in pit_replay rows."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        for flag in FORWARD_ONLY_FLAGS:
            col = f"flag_{flag}"
            if col in row:
                assert row[col] is None, f"{col} should be None in pit_replay, got {row[col]}"
            warn_col = f"warn_{flag}"
            if warn_col in row:
                assert row[warn_col] is None, f"{warn_col} should be None in pit_replay, got {row[warn_col]}"

    def test_B3_replayed_vetoes_are_bool(self):
        """B3: the 6 replayed vetoes are True/False (never None) in pit_replay rows."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        replayed = [
            "data_quality_input_corruption",
            "altman_distress",
            "sloan_accruals_top_decile",
            "net_issuance_top_decile",
            "beneish_manipulation_veto",
            "dechow_manipulation_veto",
        ]
        detail = _make_detail(risk_flags=["altman_distress"])
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        for flag in replayed:
            col = f"flag_{flag}"
            assert col in row, f"Missing column {col}"
            assert isinstance(row[col], bool), (
                f"{col} should be bool in pit_replay, got {type(row[col])}"
            )
        assert row["flag_altman_distress"] is True
        assert row["flag_sloan_accruals_top_decile"] is False

    def test_B5_replay_completeness_present_and_in_range(self):
        """B5: replay_completeness is in [0, 1] for pit_replay rows."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        assert "replay_completeness" in row, "replay_completeness column missing"
        rc = row["replay_completeness"]
        assert rc is not None, "replay_completeness should not be None for pit_replay"
        assert 0.0 <= rc <= 1.0, f"replay_completeness={rc} not in [0, 1]"

    def test_B5_replay_completeness_less_than_one(self):
        """B5: replay_completeness < 1.0 (some flags are NULL) for FORWARD_ONLY_FLAGS rows."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        rc = row["replay_completeness"]
        assert rc < 1.0, (
            f"replay_completeness={rc} should be < 1.0 when FORWARD_ONLY_FLAGS has nulls"
        )

    def test_B13_replay_completeness_one_when_no_nulls(self):
        """B13: replay_completeness == 1.0 when null_flags=frozenset() (no nulls)."""
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=frozenset(), row_provenance="pit_replay")
        rc = row["replay_completeness"]
        assert rc == 1.0, f"Expected 1.0 with empty null_flags, got {rc}"


# ---------------------------------------------------------------------------
# B6 — Live-path regression: flatten_stock default behavior unchanged
# ---------------------------------------------------------------------------

class TestFlattenStockLivePathRegression:
    """B6: default flatten_stock call (no null_flags) is byte-identical to Slice-1."""

    def test_B6_default_row_provenance_is_live(self):
        """B6: row_provenance is 'live' by default (no args change needed)."""
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        assert row["row_provenance"] == "live"

    def test_B6_all_flags_are_bool_by_default(self):
        """B6: all flag_*/warn_* columns are bool (never None) by default."""
        from compute.warehouse.flag_registry import KNOWN_RISK_FLAGS, KNOWN_VALUATION_WARNINGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail(risk_flags=["altman_distress"])
        row = flatten_stock(detail, None)
        for flag in KNOWN_RISK_FLAGS:
            col = f"flag_{flag}"
            assert col in row, f"Missing {col}"
            assert isinstance(row[col], bool), f"{col} not bool: {type(row[col])}"
        for warn in KNOWN_VALUATION_WARNINGS:
            col = f"warn_{warn}"
            assert col in row, f"Missing {col}"
            assert isinstance(row[col], bool), f"{col} not bool: {type(row[col])}"

    def test_B6_replay_completeness_is_none_for_live(self):
        """B6: replay_completeness is None for live rows (not applicable)."""
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None)
        assert row["replay_completeness"] is None, (
            f"Expected None for live row, got {row['replay_completeness']}"
        )

    def test_B6_live_flag_true_when_flag_in_list(self):
        """B6: flag_altman_distress=True when risk_flags=['altman_distress'] (live)."""
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(risk_flags=["altman_distress"]), None)
        assert row["flag_altman_distress"] is True
        assert row["flag_beneish_manipulation_veto"] is False

    def test_B6_live_warn_true_when_warn_in_list(self):
        """B6: warn_stale_filing_soft=True when valuation_warnings=['stale_filing_soft'] (live)."""
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(valuation_warnings=["stale_filing_soft"]), None)
        assert row["warn_stale_filing_soft"] is True
        assert row["warn_goodwill_heavy"] is False


# ---------------------------------------------------------------------------
# B1 — No look-ahead: filed T+1 rows must not appear in T snapshot
# ---------------------------------------------------------------------------

class TestNolookahead:
    """B1: pit fundamentals filed after run_date must not appear in the PIT snapshot."""

    def test_B1_future_filing_excluded(self):
        """B1: a row with filing_date > as_of is excluded by pit_snapshot_fields."""
        from compute.portfolio.pit_fundamentals import pit_snapshot_fields

        as_of = "2020-06-01"
        rows = [
            # Filed BEFORE as_of — should appear.
            _make_pit_annual_rows("revenue", 1000.0, 2019, "2020-01-15"),
            # Filed AFTER as_of — must NOT appear.
            _make_pit_annual_rows("revenue", 2000.0, 2020, "2020-07-01"),
            _make_pit_annual_rows("net_income", 500.0, 2019, "2020-01-15"),
        ]
        fields = pit_snapshot_fields(rows, as_of)
        # revenue from the 2019 annual (filed 2020-01-15) should be 1000
        assert fields.get("revenue") == 1000.0, (
            f"Expected revenue=1000 from filed-before row, got {fields.get('revenue')}"
        )

    def test_B1_no_eligible_rows_returns_empty(self):
        """B1: when all rows are future-filed, pit_snapshot_fields returns empty dict."""
        from compute.portfolio.pit_fundamentals import pit_snapshot_fields

        as_of = "2019-01-01"
        rows = [
            _make_pit_annual_rows("revenue", 999.0, 2019, "2020-06-01"),  # Future
            _make_pit_annual_rows("net_income", 100.0, 2019, "2020-07-01"),  # Future
        ]
        fields = pit_snapshot_fields(rows, as_of)
        assert "revenue" not in fields, "Future filing should not appear in PIT snapshot"
        assert "net_income" not in fields

    def test_B1_amendment_excluded(self):
        """B1: 10-K/A amendments are excluded by form_type filter."""
        from compute.portfolio.pit_fundamentals import pit_snapshot_fields

        as_of = "2020-06-01"
        rows = [
            # Original 10-K (eligible)
            _make_pit_annual_rows("revenue", 1000.0, 2019, "2020-01-15", form_type="10-K"),
            # Amendment 10-K/A (should be excluded)
            _make_pit_annual_rows("revenue", 1500.0, 2019, "2020-03-10", form_type="10-K/A"),
        ]
        fields = pit_snapshot_fields(rows, as_of)
        # Must use the original 10-K value, not the amendment.
        assert fields.get("revenue") == 1000.0, (
            f"Amendment (10-K/A) must be excluded; expected 1000, got {fields.get('revenue')}"
        )

    def test_B1_latest_eligible_fiscal_year_wins(self):
        """B1: the most recent fiscal year with filing_date <= as_of wins."""
        from compute.portfolio.pit_fundamentals import pit_snapshot_fields

        as_of = "2022-06-01"
        rows = [
            _make_pit_annual_rows("revenue", 800.0, 2018, "2019-02-01"),
            _make_pit_annual_rows("revenue", 1200.0, 2020, "2021-03-01"),
            _make_pit_annual_rows("revenue", 1500.0, 2021, "2022-02-15"),  # Latest
            _make_pit_annual_rows("revenue", 1800.0, 2022, "2022-08-01"),  # Future
        ]
        fields = pit_snapshot_fields(rows, as_of)
        assert fields.get("revenue") == 1500.0, (
            f"Expected revenue=1500 (FY2021 filed 2022-02-15), got {fields.get('revenue')}"
        )


# ---------------------------------------------------------------------------
# B2 — Survivorship: members_at returns correct set for historical dates
# ---------------------------------------------------------------------------

class TestSurvivorship:
    """B2: members_at is PIT-correct for the synthetic membership ledger."""

    def _make_synthetic_events(self):
        """Return a tuple of synthetic MembershipEvents for use with monkeypatch."""
        from compute.ingest.historical_universe import MembershipEvent
        return (
            # TICKER_A: present from before our test window
            # TICKER_B: added 2019-06-01, removed 2022-01-01
            MembershipEvent(
                effective_date=date(2019, 6, 1),
                ticker="TICKER_B",
                action="ADD",
                name="Ticker B Corp",
                source_url="",
            ),
            MembershipEvent(
                effective_date=date(2022, 1, 1),
                ticker="TICKER_B",
                action="REMOVE",
                name="Ticker B Corp",
                source_url="",
            ),
        )

    def test_B2_removed_ticker_present_before_removal(self):
        """B2: TICKER_B present in 2020-06-01 cross-section (removed 2022-01-01)."""
        from compute.ingest.historical_universe import members_at

        synthetic_events = self._make_synthetic_events()
        # Current universe: TICKER_A + TICKER_C (TICKER_B was removed)
        current = {"TICKER_A", "TICKER_C"}
        anchor = date(2024, 1, 1)

        with patch("compute.ingest.historical_universe._load_events", return_value=synthetic_events):
            result = members_at(date(2020, 6, 1), current_universe=current, anchor_date=anchor)

        # TICKER_B was added 2019-06-01 and removed 2022-01-01 → present on 2020-06-01.
        assert "TICKER_B" in result.tickers, (
            "TICKER_B should be in universe on 2020-06-01 (removed 2022-01-01)"
        )

    def test_B2_removed_ticker_absent_after_removal(self):
        """B2: TICKER_B absent in 2023-01-01 cross-section (removed 2022-01-01)."""
        from compute.ingest.historical_universe import members_at

        synthetic_events = self._make_synthetic_events()
        current = {"TICKER_A", "TICKER_C"}
        anchor = date(2024, 1, 1)

        with patch("compute.ingest.historical_universe._load_events", return_value=synthetic_events):
            result = members_at(date(2023, 1, 1), current_universe=current, anchor_date=anchor)

        # TICKER_B removed 2022-01-01 → absent on 2023-01-01.
        assert "TICKER_B" not in result.tickers, (
            "TICKER_B should NOT be in universe on 2023-01-01 (removed 2022-01-01)"
        )

    def test_B2_current_ticker_always_present(self):
        """B2: TICKER_A (always in current universe, no events) is present at any date."""
        from compute.ingest.historical_universe import members_at

        synthetic_events = self._make_synthetic_events()
        current = {"TICKER_A", "TICKER_C"}
        anchor = date(2024, 1, 1)

        for as_of in [date(2019, 1, 1), date(2021, 6, 1), date(2023, 6, 1)]:
            with patch("compute.ingest.historical_universe._load_events", return_value=synthetic_events):
                result = members_at(as_of, current_universe=current, anchor_date=anchor)
            assert "TICKER_A" in result.tickers, f"TICKER_A missing on {as_of}"


# ---------------------------------------------------------------------------
# B10 — _pit_snapshot look-ahead guard
# ---------------------------------------------------------------------------

class TestPitSnapshotLookahead:
    """B10: _pit_snapshot returns None for fields only available after as_of."""

    def test_B10_future_metric_not_in_snapshot(self):
        """B10: a metric with filing_date T+1 must not appear in the T snapshot."""
        from scripts.backfill_warehouse import _pit_snapshot

        as_of = "2020-01-01"
        rows = [
            # Filed BEFORE as_of (eligible).
            _make_pit_annual_rows("net_income", 500.0, 2018, "2019-06-01"),
            # Filed AFTER as_of (must be excluded).
            _make_pit_annual_rows("revenue", 5000.0, 2019, "2020-06-01"),
        ]
        # Provide a dummy CIK — the function only filters rows.
        snap = _pit_snapshot("TEST", "0000012345", rows, as_of)
        # net_income from 2018 (filed 2019-06-01 <= as_of) should be available.
        assert snap.net_income == 500.0, f"Expected net_income=500, got {snap.net_income}"
        # revenue from 2019 (filed 2020-06-01 > as_of) should NOT be available.
        assert snap.revenue is None, f"Expected revenue=None (future filing), got {snap.revenue}"


# ---------------------------------------------------------------------------
# B11 / B12 — _write_backfill_partition layout + idempotency
# ---------------------------------------------------------------------------

class TestWriteBackfillPartition:
    """B11: year=/run_date= layout; B12: idempotent write."""

    def test_B11_partition_layout(self, tmp_path):
        """B11: _write_backfill_partition writes year=YYYY/run_date=ISO/part-0.parquet."""
        from scripts.backfill_warehouse import _write_backfill_partition

        run_date = date(2020, 6, 5)
        rows = [{"ticker": "AAPL", "composite_score": 70.0, "row_provenance": "pit_replay"}]
        n = _write_backfill_partition(rows, run_date, tmp_path)
        assert n == 1

        expected = tmp_path / "year=2020" / "run_date=2020-06-05" / "part-0.parquet"
        assert expected.exists(), f"Expected partition at {expected}"

    def test_B12_idempotent_overwrite(self, tmp_path):
        """B12: re-running same run_date overwrites the partition (not appends)."""
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse import _write_backfill_partition

        run_date = date(2020, 6, 5)
        _write_backfill_partition(
            [{"ticker": "AAPL", "composite_score": 70.0, "row_provenance": "pit_replay"}],
            run_date, tmp_path,
        )
        _write_backfill_partition(
            [{"ticker": "MSFT", "composite_score": 65.0, "row_provenance": "pit_replay"},
             {"ticker": "GOOG", "composite_score": 60.0, "row_provenance": "pit_replay"}],
            run_date, tmp_path,
        )
        part_file = tmp_path / "year=2020" / "run_date=2020-06-05" / "part-0.parquet"
        table = pq.read_table(part_file)
        # Second write had 2 rows — idempotent overwrite.
        assert table.num_rows == 2, f"Expected 2 rows after second write, got {table.num_rows}"
        tickers = [r.as_py() for r in table.column("ticker")]
        assert "AAPL" not in tickers, "First write's ticker should be overwritten"
        assert "MSFT" in tickers

    def test_B11_empty_rows_returns_zero(self, tmp_path):
        """B11: empty rows returns 0 (no partition written)."""
        from scripts.backfill_warehouse import _write_backfill_partition

        run_date = date(2020, 6, 5)
        n = _write_backfill_partition([], run_date, tmp_path)
        assert n == 0
        expected = tmp_path / "year=2020" / "run_date=2020-06-05" / "part-0.parquet"
        assert not expected.exists(), "No partition should be created for empty rows"


# ---------------------------------------------------------------------------
# B3 extended — replay_completeness diagnostic via full flatten round-trip
# ---------------------------------------------------------------------------

class TestReplayCompletenessRoundtrip:
    """B3/B5 extended: replay_completeness survives a write + read cycle."""

    def test_replay_completeness_survives_parquet_roundtrip(self, tmp_path):
        """B5 extended: replay_completeness is readable after Parquet write+read."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        detail = _make_detail(risk_flags=["altman_distress"])
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        assert row["replay_completeness"] is not None

        run_date = date(2020, 6, 5)
        _write_backfill_partition([row], run_date, tmp_path)

        part_file = tmp_path / "year=2020" / "run_date=2020-06-05" / "part-0.parquet"
        table = pq.read_table(part_file)
        assert "replay_completeness" in table.schema.names
        rc = table.column("replay_completeness")[0].as_py()
        assert rc is not None
        assert 0.0 <= rc < 1.0

    def test_live_row_replay_completeness_is_none_after_roundtrip(self, tmp_path):
        """B6 extended: live row's replay_completeness=None survives Parquet write+read."""
        import pyarrow.parquet as pq

        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        detail = _make_detail()
        row = flatten_stock(detail, None)  # default = live
        assert row["replay_completeness"] is None

        run_date = date(2020, 6, 12)
        _write_backfill_partition([row], run_date, tmp_path)

        part_file = tmp_path / "year=2020" / "run_date=2020-06-12" / "part-0.parquet"
        table = pq.read_table(part_file)
        rc = table.column("replay_completeness")[0].as_py()
        assert rc is None


# ---------------------------------------------------------------------------
# B14 — flatten_stock with FORWARD_ONLY_FLAGS: specific column behavior
# ---------------------------------------------------------------------------

class TestFlattenStockForwardOnlyDetail:
    """B14: detailed column-level check of null_flags= behavior."""

    def test_B14_non_reliance_is_null_in_replay(self):
        """B14: flag_non_reliance_filing is None in pit_replay rows."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        assert row.get("flag_non_reliance_filing") is None

    def test_B14_low_liquidity_warn_is_null_in_replay(self):
        """B14: warn_low_liquidity is None in pit_replay rows."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        assert row.get("warn_low_liquidity") is None

    def test_B14_data_quality_corruption_is_bool_in_replay(self):
        """B14: flag_data_quality_input_corruption is bool (replayed veto) in pit_replay."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        row = flatten_stock(_make_detail(), None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        val = row.get("flag_data_quality_input_corruption")
        assert isinstance(val, bool), f"Expected bool, got {type(val)}: {val}"

    def test_B14_altman_distress_true_when_in_risk_flags(self):
        """B14: flag_altman_distress=True even in pit_replay when the flag is set."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        detail = _make_detail(risk_flags=["altman_distress"])
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")
        assert row["flag_altman_distress"] is True

    def test_B14_column_set_same_for_live_and_pit_replay(self):
        """B14: column set is IDENTICAL for live and pit_replay rows (same schema)."""
        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        live_row = flatten_stock(_make_detail(), None)
        replay_row = flatten_stock(
            _make_detail(), None,
            null_flags=FORWARD_ONLY_FLAGS,
            row_provenance="pit_replay",
        )
        assert set(live_row.keys()) == set(replay_row.keys()), (
            f"Column set mismatch: live={sorted(live_row.keys())[:5]}... "
            f"replay={sorted(replay_row.keys())[:5]}..."
        )


# ---------------------------------------------------------------------------
# _pit_filing_lag helper
# ---------------------------------------------------------------------------

class TestPitFilingLag:
    """Unit tests for _pit_filing_lag (no-look-ahead filing staleness)."""

    def test_returns_none_when_no_eligible_rows(self):
        from scripts.backfill_warehouse import _pit_filing_lag
        result = _pit_filing_lag([], "2020-06-01", date(2020, 6, 1))
        assert result is None

    def test_returns_days_from_latest_eligible_10k(self):
        from scripts.backfill_warehouse import _pit_filing_lag
        rows = [
            _make_pit_annual_rows("revenue", 100.0, 2019, "2020-01-15"),  # 10-K eligible
            _make_pit_annual_rows("revenue", 200.0, 2020, "2020-08-01"),  # future — excluded
        ]
        as_of = "2020-06-01"
        as_of_date = date(2020, 6, 1)
        result = _pit_filing_lag(rows, as_of, as_of_date)
        expected = (date(2020, 6, 1) - date(2020, 1, 15)).days
        assert result == expected, f"Expected {expected} days lag, got {result}"

    def test_excludes_10ka_amendments(self):
        from scripts.backfill_warehouse import _pit_filing_lag
        rows = [
            _make_pit_annual_rows("revenue", 100.0, 2019, "2020-01-15", form_type="10-K"),
            _make_pit_annual_rows("revenue", 100.0, 2019, "2020-02-20", form_type="10-K/A"),
        ]
        as_of = "2020-06-01"
        as_of_date = date(2020, 6, 1)
        result = _pit_filing_lag(rows, as_of, as_of_date)
        expected = (date(2020, 6, 1) - date(2020, 1, 15)).days
        assert result == expected, f"Expected lag from original 10-K, got {result}"


# ---------------------------------------------------------------------------
# NULL-discipline Parquet roundtrip: forward-only flag columns read back as
# Python None (not False) after write + read.
# ---------------------------------------------------------------------------

class TestNullFlagParquetRoundtrip:
    """Verify that NULL-valued flag/warn columns survive the Parquet write+read
    cycle as Python None, not as False.

    This guards against a silent type-coercion bug where a nullable boolean
    column is cast to a non-nullable bool column during write, silently
    changing NULL → False and thereby corrupting the NULL-discipline
    guarantee that downstream ML models rely on.
    """

    def test_forward_only_risk_flag_reads_back_as_none(self, tmp_path):
        """NULL-discipline: flag_fundamentals_unavailable (forward-only risk flag)
        reads back as None (not False) after _write_backfill_partition round-trip."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")

        # Pre-condition: the in-memory row must already have None for the column.
        assert row.get("flag_fundamentals_unavailable") is None, (
            "flag_fundamentals_unavailable must be None in-memory before write"
        )

        run_date = date(2021, 3, 5)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2021" / "run_date=2021-03-05" / "part-0.parquet"
        table = pq.read_table(part)
        val = table.column("flag_fundamentals_unavailable")[0].as_py()
        assert val is None, (
            f"flag_fundamentals_unavailable must read back as None after Parquet round-trip, "
            f"got {val!r} (type {type(val).__name__})"
        )

    def test_forward_only_valuation_warn_reads_back_as_none(self, tmp_path):
        """NULL-discipline: warn_stale_filing_soft (forward-only valuation warning)
        reads back as None (not False) after _write_backfill_partition round-trip."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")

        # Pre-condition: stale_filing_soft is forward-only → must be None in-memory.
        assert row.get("warn_stale_filing_soft") is None, (
            "warn_stale_filing_soft must be None in-memory before write"
        )

        run_date = date(2021, 3, 12)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2021" / "run_date=2021-03-12" / "part-0.parquet"
        table = pq.read_table(part)
        val = table.column("warn_stale_filing_soft")[0].as_py()
        assert val is None, (
            f"warn_stale_filing_soft must read back as None after Parquet round-trip, "
            f"got {val!r} (type {type(val).__name__})"
        )

    def test_non_forward_only_flag_reads_back_as_bool(self, tmp_path):
        """NULL-discipline contrast: a non-forward-only replayed flag (altman_distress)
        reads back as bool (True/False) — never None — after round-trip."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import FORWARD_ONLY_FLAGS
        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        detail = _make_detail(risk_flags=["altman_distress"])
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")

        # Pre-condition: altman_distress is a replayed veto → must be True in-memory.
        assert row.get("flag_altman_distress") is True

        run_date = date(2021, 3, 19)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2021" / "run_date=2021-03-19" / "part-0.parquet"
        table = pq.read_table(part)
        val = table.column("flag_altman_distress")[0].as_py()
        assert isinstance(val, bool), (
            f"flag_altman_distress (replayed veto) must read back as bool, got {type(val).__name__}"
        )
        assert val is True

    def test_all_forward_only_flags_null_in_parquet(self, tmp_path):
        """NULL-discipline: EVERY forward-only flag column reads back as None
        from Parquet — no column is silently coerced to False."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import (
            FORWARD_ONLY_FLAGS,
            KNOWN_RISK_FLAGS,
            KNOWN_VALUATION_WARNINGS,
        )
        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        detail = _make_detail()
        row = flatten_stock(detail, None, null_flags=FORWARD_ONLY_FLAGS, row_provenance="pit_replay")

        run_date = date(2021, 3, 26)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2021" / "run_date=2021-03-26" / "part-0.parquet"
        table = pq.read_table(part)
        col_names = set(table.schema.names)
        schema_dict = {name: table.column(name)[0].as_py() for name in col_names}

        failures: list[str] = []
        for flag in FORWARD_ONLY_FLAGS:
            # Each forward-only flag maps to either flag_<x> or warn_<x>.
            if flag in KNOWN_RISK_FLAGS:
                col = f"flag_{flag}"
            elif flag in KNOWN_VALUATION_WARNINGS:
                col = f"warn_{flag}"
            else:
                continue  # should not happen; B8 already guards this
            if col not in schema_dict:
                failures.append(f"{col}: column missing from parquet schema")
            elif schema_dict[col] is not None:
                failures.append(
                    f"{col}: expected None in parquet, got {schema_dict[col]!r} "
                    f"(type {type(schema_dict[col]).__name__})"
                )
        assert failures == [], (
            "Forward-only flag columns must all be None in Parquet:\n" +
            "\n".join(f"  {f}" for f in failures)
        )


# ---------------------------------------------------------------------------
# Live-path regression: flatten_stock with NO kwargs is byte-identical to the
# Slice-1 column set. This is a targeted B6 extension that writes a live row
# to Parquet and reads it back, confirming the serialization path is unchanged.
# ---------------------------------------------------------------------------

class TestLivePathRegressionParquet:
    """B6 extended: live path (no kwargs) column set and bool semantics survive
    a Parquet write + read cycle, guarding that Slice-2 additions to flatten_stock
    did not change the live serialization output."""

    def test_live_row_flag_columns_are_bool_after_parquet_roundtrip(self, tmp_path):
        """B6: flag_*/warn_* columns in a live row read back as bool (not None, not int)
        after a _write_backfill_partition round-trip."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import KNOWN_RISK_FLAGS, KNOWN_VALUATION_WARNINGS
        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        # Live row: all flags are True/False; no null_flags= arg.
        detail = _make_detail(risk_flags=["altman_distress", "sloan_accruals_top_decile"])
        row = flatten_stock(detail, None)  # live path — no kwargs
        assert row["row_provenance"] == "live"

        run_date = date(2021, 4, 2)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2021" / "run_date=2021-04-02" / "part-0.parquet"
        table = pq.read_table(part)
        col_names = set(table.schema.names)

        failures: list[str] = []
        for flag in KNOWN_RISK_FLAGS:
            col = f"flag_{flag}"
            if col not in col_names:
                failures.append(f"{col}: missing from parquet schema")
                continue
            val = table.column(col)[0].as_py()
            if not isinstance(val, bool):
                failures.append(f"{col}: expected bool, got {type(val).__name__}: {val!r}")
        for warn in KNOWN_VALUATION_WARNINGS:
            col = f"warn_{warn}"
            if col not in col_names:
                failures.append(f"{col}: missing from parquet schema")
                continue
            val = table.column(col)[0].as_py()
            if not isinstance(val, bool):
                failures.append(f"{col}: expected bool, got {type(val).__name__}: {val!r}")

        assert failures == [], (
            "Live-path flag/warn columns must all be bool after Parquet roundtrip:\n" +
            "\n".join(f"  {f}" for f in failures)
        )

    def test_live_row_replay_completeness_null_after_parquet_roundtrip(self, tmp_path):
        """B6: live row's replay_completeness is None after Parquet write + read."""
        import pyarrow.parquet as pq

        from compute.warehouse.flatten import flatten_stock
        from scripts.backfill_warehouse import _write_backfill_partition

        row = flatten_stock(_make_detail(), None)  # live path
        assert row["replay_completeness"] is None

        run_date = date(2021, 4, 9)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2021" / "run_date=2021-04-09" / "part-0.parquet"
        table = pq.read_table(part)
        rc = table.column("replay_completeness")[0].as_py()
        assert rc is None, (
            f"Live row replay_completeness must be None after Parquet roundtrip, got {rc!r}"
        )


# ---------------------------------------------------------------------------
# B15 — No silent False: every flag/warn column for FORWARD_ONLY_FLAGS |
# BACKFILL_UNCOMPUTED_ANNOTATES must be None (not False) in a pit_replay row.
#
# This is the core "no false negatives in replay" regression guard.
# The backfill_warehouse._replay_one_date() call passes
# null_flags=FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES to
# flatten_stock; this test confirms that wiring produces None (not False)
# for every flag in the union set.
# ---------------------------------------------------------------------------

class TestNoSilentFalseInReplay:
    """B15: pit_replay rows must have NULL (not False) for every flag in
    FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES.

    Regression guard for the Slice-2 defect where BACKFILL_UNCOMPUTED_ANNOTATES
    flags were silently written as False because flatten_stock only received
    FORWARD_ONLY_FLAGS as null_flags.  False is a confirmed-negative — which
    these flags were never evaluated to produce.
    """

    def _make_replay_row(self, risk_flags=None, valuation_warnings=None):
        """Build a pit_replay row using the same null_flags union as the backfill."""
        from compute.warehouse.flag_registry import (
            BACKFILL_UNCOMPUTED_ANNOTATES,
            FORWARD_ONLY_FLAGS,
        )
        from compute.warehouse.flatten import flatten_stock

        detail = _make_detail(
            risk_flags=risk_flags or [],
            valuation_warnings=valuation_warnings or [],
        )
        # Exact same call as _replay_one_date in backfill_warehouse.py.
        return flatten_stock(
            detail,
            None,
            null_flags=FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES,
            row_provenance="pit_replay",
        )

    def test_B15_no_flag_or_warn_is_silent_false_for_nulled_set(self):
        """B15: for a pit_replay row, every flag_* and warn_* column whose
        flag name is in FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES
        must be None — never False (a silent confirmed-negative)."""
        from compute.warehouse.flag_registry import (
            BACKFILL_UNCOMPUTED_ANNOTATES,
            FORWARD_ONLY_FLAGS,
            KNOWN_RISK_FLAGS,
            KNOWN_VALUATION_WARNINGS,
        )

        row = self._make_replay_row()
        null_set = FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES

        failures: list[str] = []
        for flag in null_set:
            if flag in KNOWN_RISK_FLAGS:
                col = f"flag_{flag}"
            elif flag in KNOWN_VALUATION_WARNINGS:
                col = f"warn_{flag}"
            else:
                # Should not happen; B8 already guards registry membership.
                failures.append(f"{flag}: not in either known registry")
                continue
            val = row.get(col)
            if val is not False:
                # None is good; anything that is not False passes.
                # (True would be a genuine value — unreachable when the flag
                # was never computed, but would still satisfy the NULL guard.)
                continue
            failures.append(
                f"{col}: expected None (not evaluated), got False "
                f"(silent confirmed-negative)"
            )

        assert failures == [], (
            "pit_replay rows must not contain silent False for uncomputed flags:\n"
            + "\n".join(f"  {f}" for f in failures)
        )

    def test_B15_all_12_backfill_uncomputed_annotates_are_null(self):
        """B15: each of the 12 BACKFILL_UNCOMPUTED_ANNOTATES is NULL (not False)
        in a pit_replay row produced with the correct null_flags union."""
        from compute.warehouse.flag_registry import BACKFILL_UNCOMPUTED_ANNOTATES

        expected_12 = {
            "restatement_history",
            "restatement_high_confidence",
            "late_filing_notification",
            "rem_suspect",
            "accruals_momentum_high",
            "loss_avoidance_pattern",
            "loss_avoidance_pattern_size_invariant",
            "beneish_high",
            "dechow_high",
            "manipulation_triple_flag",
            "share_count_extraction_missing",
            "valuation_output_anomalous",
        }
        # Confirm the constant contains exactly the expected 12 members.
        assert BACKFILL_UNCOMPUTED_ANNOTATES == frozenset(expected_12), (
            f"BACKFILL_UNCOMPUTED_ANNOTATES does not match expected 12 members.\n"
            f"  Extra  : {sorted(BACKFILL_UNCOMPUTED_ANNOTATES - frozenset(expected_12))}\n"
            f"  Missing: {sorted(frozenset(expected_12) - BACKFILL_UNCOMPUTED_ANNOTATES)}"
        )

        row = self._make_replay_row()
        failures: list[str] = []
        for flag in BACKFILL_UNCOMPUTED_ANNOTATES:
            col = f"warn_{flag}"
            val = row.get(col)
            if val is not None:
                failures.append(
                    f"{col}: expected None, got {val!r} (type {type(val).__name__})"
                )
        assert failures == [], (
            "All 12 BACKFILL_UNCOMPUTED_ANNOTATES must be None in pit_replay rows:\n"
            + "\n".join(f"  {f}" for f in failures)
        )

    def test_B15_replayed_vetoes_still_bool_not_null(self):
        """B15 contrast: the 6 genuinely-replayed vetoes must be True/False
        (not None) even when the full null_flags union is passed — they are
        NOT in the union set."""
        replayed_vetoes = {
            "data_quality_input_corruption",
            "altman_distress",
            "sloan_accruals_top_decile",
            "net_issuance_top_decile",
            "beneish_manipulation_veto",
            "dechow_manipulation_veto",
        }
        # Confirm none of the replayed vetoes are in BACKFILL_UNCOMPUTED_ANNOTATES.
        from compute.warehouse.flag_registry import (
            BACKFILL_UNCOMPUTED_ANNOTATES,
            FORWARD_ONLY_FLAGS,
        )
        null_set = FORWARD_ONLY_FLAGS | BACKFILL_UNCOMPUTED_ANNOTATES
        overlap = replayed_vetoes & null_set
        assert overlap == set(), (
            f"Replayed vetoes must NOT be in null_flags union: {overlap}"
        )

        row = self._make_replay_row(risk_flags=["altman_distress"])
        for flag in replayed_vetoes:
            col = f"flag_{flag}"
            val = row.get(col)
            assert isinstance(val, bool), (
                f"{col} must be bool in pit_replay (replayed veto), got {type(val).__name__}: {val!r}"
            )
        assert row["flag_altman_distress"] is True
        assert row["flag_sloan_accruals_top_decile"] is False

    def test_B15_live_row_uncomputed_annotates_are_bool(self):
        """B15 contrast: in LIVE rows, BACKFILL_UNCOMPUTED_ANNOTATES columns
        are True/False (not None) — the live path evaluates all flags."""
        from compute.warehouse.flag_registry import BACKFILL_UNCOMPUTED_ANNOTATES
        from compute.warehouse.flatten import flatten_stock

        # Live path: no null_flags.
        detail = _make_detail()
        row = flatten_stock(detail, None)  # default = live, null_flags=None
        assert row["row_provenance"] == "live"

        failures: list[str] = []
        for flag in BACKFILL_UNCOMPUTED_ANNOTATES:
            col = f"warn_{flag}"
            val = row.get(col)
            if not isinstance(val, bool):
                failures.append(
                    f"{col}: expected bool in live row, got {type(val).__name__}: {val!r}"
                )
        assert failures == [], (
            "In live rows, BACKFILL_UNCOMPUTED_ANNOTATES columns must be bool:\n"
            + "\n".join(f"  {f}" for f in failures)
        )

    def test_B15_parquet_roundtrip_null_discipline_for_uncomputed_annotates(
        self, tmp_path
    ):
        """B15 Parquet roundtrip: BACKFILL_UNCOMPUTED_ANNOTATES columns survive
        write+read as None — not silently coerced to False by PyArrow."""
        import pyarrow.parquet as pq

        from compute.warehouse.flag_registry import BACKFILL_UNCOMPUTED_ANNOTATES
        from scripts.backfill_warehouse import _write_backfill_partition

        row = self._make_replay_row()
        run_date = date(2022, 1, 7)
        _write_backfill_partition([row], run_date, tmp_path)

        part = tmp_path / "year=2022" / "run_date=2022-01-07" / "part-0.parquet"
        table = pq.read_table(part)
        col_names = set(table.schema.names)

        failures: list[str] = []
        for flag in BACKFILL_UNCOMPUTED_ANNOTATES:
            col = f"warn_{flag}"
            if col not in col_names:
                failures.append(f"{col}: missing from Parquet schema")
                continue
            val = table.column(col)[0].as_py()
            if val is not None:
                failures.append(
                    f"{col}: expected None after Parquet roundtrip, "
                    f"got {val!r} (type {type(val).__name__})"
                )
        assert failures == [], (
            "BACKFILL_UNCOMPUTED_ANNOTATES columns must be None after Parquet roundtrip:\n"
            + "\n".join(f"  {f}" for f in failures)
        )
