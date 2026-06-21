"""Gap-fill tests for compute.warehouse — PR #539 coverage review.

These tests extend the 35 existing tests in test_warehouse.py to close
the gaps identified in the PR-#539 coverage audit:

  G1  graceful-degradation: writer raises on bad path; cron guard swallows it
  G2  flatten edge cases: all-null PillarScores; fair_price empty dict vs None;
      ticker present in details but absent from summaries (summary=None path);
      unregistered flag silently absent from bool cols but preserved in raw JSON
  G3  assert_flags_known helper: positive (all registered) and negative (unknown)
  G4  Hypothesis property-based: column set invariance; flag-membership invariant;
      scalar round-trip (flatten → parquet → read back preserves values)
  G5  row_provenance guaranteed "live" even for corner-case inputs
  G6  manifest part_path is relative (not absolute), POSIX-style
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Synthetic model builders (mirrors test_warehouse.py — kept local so each
# file is self-contained and changes to the other file don't break this one)
# ---------------------------------------------------------------------------

def _ps_all_none():
    """PillarScores with every field set to None."""
    from compute.output.schemas import PillarScores
    return PillarScores(**{f: None for f in PillarScores.model_fields})


def _ps_all_set():
    """PillarScores with every field set to a float value."""
    from compute.output.schemas import PillarScores
    return PillarScores(**{f: 55.0 for f in PillarScores.model_fields})


def _raw_metrics_all_none():
    from compute.output.schemas import RawMetrics
    return RawMetrics(**{f: None for f in RawMetrics.model_fields})


def _data_quality():
    from compute.output.schemas import DataQuality
    kwargs = {f: None for f in DataQuality.model_fields}
    kwargs["missing_metrics"] = []
    kwargs["imputed_metrics"] = []
    return DataQuality(**kwargs)


def _make_detail(
    ticker: str = "AAPL",
    risk_flags: list[str] | None = None,
    valuation_warnings: list[str] | None = None,
    fair_price: dict | None = None,
    pillar_scores: Any = None,
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
        pillar_scores=pillar_scores if pillar_scores is not None else _ps_all_set(),
        raw_metrics=_raw_metrics_all_none(),
        data_quality=_data_quality(),
        risk_flags=risk_flags or [],
        valuation_warnings=valuation_warnings or [],
        index_membership="sp500",
        index_memberships=["sp500"],
        fair_price=fair_price,
    )


def _make_summary(ticker: str = "AAPL") -> Any:
    from compute.output.schemas import StockSummary
    return StockSummary(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector="Technology",
        rank=1,
        composite_score=55.0,
        current_price=100.0,
        index_membership="sp500",
        index_memberships=["sp500"],
    )


def _make_metadata() -> Any:
    from compute.output.schemas import Metadata
    return Metadata(
        version="0.10.29-phase8pilot",
        last_update_utc="2026-06-21T22:00:00Z",
        next_update_utc="2026-06-22T22:00:00Z",
        universe="SP900",
        universe_size=900,
        compute_run_id="test-gap-run",
        git_commit="abc1234",
    )


# ---------------------------------------------------------------------------
# G1 — Graceful-degradation: writer raises on unwritable path;
#       Step-13.5-equivalent guard swallows it without re-raising
# ---------------------------------------------------------------------------

class TestGracefulDegradationWriter:
    """G1: the writer propagates exceptions to its caller; the cron never blocks."""

    def test_writer_raises_on_unwritable_path(self):
        """G1: write_run_snapshot raises (does not silently return 0) on a bad path.

        The writer documents that it PROPAGATES exceptions to the caller; it is the
        caller (main.py Step 13.5) that swallows them.  This test locks that contract.
        """
        import pathlib

        from compute.warehouse.writer import write_run_snapshot

        # /dev/null is a file — mkdir inside it must fail with NotADirectoryError.
        bad_path = pathlib.Path("/dev/null/warehouse_unreachable")
        with pytest.raises(NotADirectoryError):
            write_run_snapshot(
                [_make_detail()],
                [_make_summary()],
                _make_metadata(),
                date(2026, 6, 21),
                bad_path,
            )

    def test_step_13_5_guard_swallows_writer_exception(self, tmp_path):
        """G1: cron guard pattern (try/except around write_run_snapshot) swallows
        the exception and returns None — the cron must NEVER block.

        This simulates the main.py Step-13.5 pattern inline without importing
        main.py (which has heavy module-level side effects).
        """
        from compute.warehouse.writer import write_run_snapshot

        bad_path = tmp_path / "__bad__" / "__also_bad__"
        # Make the path exist as a file so mkdir inside fails.
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        (bad_path).write_text("not a directory")

        result_holder: list[int | None] = []

        # Simulate the Step-13.5 guard logic.
        try:
            n = write_run_snapshot(
                [_make_detail()],
                [_make_summary()],
                _make_metadata(),
                date(2026, 6, 21),
                bad_path,  # bad_path is a file, not a dir → mkdir fails
            )
            result_holder.append(n)
        except Exception:  # noqa: BLE001
            result_holder.append(None)

        # The guard must NOT re-raise; result is None (exception path).
        assert result_holder == [None], (
            "Cron guard must swallow write errors and return None, not re-raise"
        )


# ---------------------------------------------------------------------------
# G2 — flatten edge cases
# ---------------------------------------------------------------------------

class TestFlattenEdgeCases:
    """G2: edge-case inputs to flatten_stock must never raise."""

    def test_all_null_pillar_scores(self):
        """G2: PillarScores with all fields None → pillar_* columns are all None."""
        from compute.warehouse.flatten import flatten_stock

        detail = _make_detail(pillar_scores=_ps_all_none())
        row = flatten_stock(detail, None)
        from compute.output.schemas import PillarScores
        for field in PillarScores.model_fields:
            assert row[f"pillar_{field}"] is None, (
                f"pillar_{field} should be None when PillarScores has all-null fields"
            )
        assert row["row_provenance"] == "live"

    def test_fair_price_empty_dict(self):
        """G2: fair_price={} (empty dict, not None) → fp_* columns all None,
        fair_price_json is a JSON object string (not 'null')."""
        from compute.warehouse.flatten import _FP_SCALAR_KEYS, flatten_stock

        row = flatten_stock(_make_detail(fair_price={}), None)
        for key in _FP_SCALAR_KEYS:
            assert row[f"fp_{key}"] is None, (
                f"fp_{key} must be None when fair_price is an empty dict"
            )
        # fair_price_json must be the JSON representation of {}, not "null"
        decoded = json.loads(row["fair_price_json"])
        assert decoded == {}

    def test_ticker_in_details_absent_from_summaries(self, tmp_path):
        """G2: detail whose ticker is absent from summaries list is still written.

        The writer falls back to summary=None for that ticker (flatten_stock handles
        summary=None by skipping summary-only fields).  The row count must equal
        len(details), not len(summaries).
        """
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        # ORPHAN has a detail but no matching summary.
        details = [_make_detail("AAPL"), _make_detail("ORPHAN")]
        summaries = [_make_summary("AAPL")]  # no ORPHAN

        n = write_run_snapshot(details, summaries, _make_metadata(), date(2026, 6, 21), tmp_path)
        assert n == 2, "Both rows must be written even when one ticker has no summary"

        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        table = pq.read_table(part_file)
        tickers = {r.as_py() for r in table.column("ticker")}
        assert "ORPHAN" in tickers
        assert "AAPL" in tickers

    def test_ticker_in_summaries_absent_from_details(self, tmp_path):
        """G2: summary whose ticker has no matching detail is simply unused.

        The writer only iterates details; extra summaries are silently ignored.
        Only the detail-count rows land in the partition.
        """
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        details = [_make_detail("AAPL")]
        summaries = [_make_summary("AAPL"), _make_summary("GHOST")]  # GHOST has no detail

        n = write_run_snapshot(details, summaries, _make_metadata(), date(2026, 6, 21), tmp_path)
        assert n == 1, "Only detail rows are written; extra summaries are ignored"

        part_file = (
            tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
        )
        table = pq.read_table(part_file)
        assert table.num_rows == 1
        assert table.column("ticker")[0].as_py() == "AAPL"

    def test_unregistered_flag_absent_from_bool_cols_preserved_in_json(self):
        """G2: an unregistered string in risk_flags is NOT emitted as a flag_<x>
        bool column (it would be a schema violation), but IS preserved verbatim in
        risk_flags_json so no information is silently lost."""
        from compute.warehouse.flatten import flatten_stock

        detail = _make_detail(risk_flags=["altman_distress", "__FUTURE_UNKNOWN_FLAG__"])
        row = flatten_stock(detail, None)

        # The unregistered flag must NOT have a bool column.
        assert "flag___FUTURE_UNKNOWN_FLAG__" not in row, (
            "Unregistered flags must not produce spurious bool columns"
        )
        # But it must survive in the raw JSON.
        decoded = json.loads(row["risk_flags_json"])
        assert "__FUTURE_UNKNOWN_FLAG__" in decoded, (
            "Unregistered flags must be preserved in risk_flags_json"
        )
        # Known flags still work correctly alongside the unregistered one.
        assert row["flag_altman_distress"] is True

    def test_unregistered_valuation_warning_absent_from_bool_cols_preserved_in_json(self):
        """G2: same contract for valuation_warnings — unregistered warn is not a
        bool column but does appear in valuation_warnings_json."""
        from compute.warehouse.flatten import flatten_stock

        detail = _make_detail(valuation_warnings=["goodwill_heavy", "__FUTURE_WARN__"])
        row = flatten_stock(detail, None)

        assert "warn___FUTURE_WARN__" not in row
        decoded = json.loads(row["valuation_warnings_json"])
        assert "__FUTURE_WARN__" in decoded
        assert row["warn_goodwill_heavy"] is True

    def test_row_provenance_live_with_all_null_pillar_scores(self):
        """G5: row_provenance = 'live' even when pillar scores are all None."""
        from compute.warehouse.flatten import flatten_stock

        row = flatten_stock(_make_detail(pillar_scores=_ps_all_none()), None)
        assert row["row_provenance"] == "live"

    def test_row_provenance_live_with_empty_fair_price(self):
        """G5: row_provenance = 'live' with fair_price={}."""
        from compute.warehouse.flatten import flatten_stock

        row = flatten_stock(_make_detail(fair_price={}), None)
        assert row["row_provenance"] == "live"


# ---------------------------------------------------------------------------
# G3 — assert_flags_known helper
# ---------------------------------------------------------------------------

class TestAssertFlagsKnown:
    """G3: assert_flags_known returns the right subset of unknown strings."""

    def test_all_registered_returns_empty_list(self):
        """G3 positive: a list of only registered flags → empty list (no unknowns)."""
        from compute.warehouse.flag_registry import KNOWN_RISK_FLAGS, assert_flags_known

        known_sample = list(KNOWN_RISK_FLAGS)[:3]
        assert assert_flags_known(known_sample) == []

    def test_unknown_flag_returned(self):
        """G3 negative: an unregistered string → returned in the list."""
        from compute.warehouse.flag_registry import assert_flags_known

        unknown = ["__DEFINITELY_UNREGISTERED__", "altman_distress"]
        result = assert_flags_known(unknown)
        assert "__DEFINITELY_UNREGISTERED__" in result
        assert "altman_distress" not in result

    def test_empty_list_returns_empty(self):
        """G3: empty input → empty result (never raises)."""
        from compute.warehouse.flag_registry import assert_flags_known

        assert assert_flags_known([]) == []

    def test_mix_of_risk_and_warn_flags_all_known(self):
        """G3: strings from BOTH registries are treated as known."""
        from compute.warehouse.flag_registry import (
            KNOWN_RISK_FLAGS,
            KNOWN_VALUATION_WARNINGS,
            assert_flags_known,
        )
        combined = list(KNOWN_RISK_FLAGS)[:2] + list(KNOWN_VALUATION_WARNINGS)[:2]
        assert assert_flags_known(combined) == []


# ---------------------------------------------------------------------------
# G4 — Hypothesis property-based invariants
# ---------------------------------------------------------------------------

# Strategy: pick a random non-empty subset of KNOWN_RISK_FLAGS
def _rf_strategy():
    from compute.warehouse.flag_registry import KNOWN_RISK_FLAGS
    flags = sorted(KNOWN_RISK_FLAGS)
    return st.lists(st.sampled_from(flags), min_size=0, max_size=len(flags), unique=True)


def _vw_strategy():
    from compute.warehouse.flag_registry import KNOWN_VALUATION_WARNINGS
    warns = sorted(KNOWN_VALUATION_WARNINGS)
    return st.lists(st.sampled_from(warns), min_size=0, max_size=len(warns), unique=True)


@given(
    risk_flags=_rf_strategy(),
    valuation_warnings=_vw_strategy(),
)
@settings(max_examples=40)
def test_flatten_column_set_invariant_production_path(risk_flags, valuation_warnings):
    """G4: the set of column names from flatten_stock is ALWAYS identical on the
    production path (detail + matching summary), regardless of which flags fire.

    This locks the 'stable schema' contract: consumers of the parquet file
    never see a row with a different column set than any other row.
    The canonical column set is derived from derive_canonical_columns() which
    also uses a synthetic detail+summary pair.
    """
    from compute.warehouse.flatten import flatten_stock
    from compute.warehouse.warehouse_schema_check import derive_canonical_columns

    canonical = set(derive_canonical_columns().keys())
    detail = _make_detail(risk_flags=risk_flags, valuation_warnings=valuation_warnings)
    summary = _make_summary(detail.ticker)
    row = flatten_stock(detail, summary)
    assert set(row.keys()) == canonical, (
        f"Column set differs from canonical for flags={risk_flags} warns={valuation_warnings}\n"
        f"Extra: {set(row.keys()) - canonical}\n"
        f"Missing: {canonical - set(row.keys())}"
    )


def test_flatten_summary_none_missing_summary_only_cols():
    """G4 (invariant): flatten_stock(detail, None) emits summary-only scalar columns
    as None so the column set is IDENTICAL to the production path (detail + summary).

    Previously (bug) those columns were absent on the summary=None path, which would
    have broken the Slice-2 backfill/replay reader expecting a consistent schema.
    The fix in flatten.py iterates StockSummary.model_fields regardless of whether
    a real summary is present and defaults to None when summary is None.

    This test now asserts the CORRECTED behavior: max_fair_price and
    margin_of_safety_pct MUST be present (and None-valued) even when summary=None.
    """
    from compute.warehouse.flatten import flatten_stock

    detail = _make_detail()
    row_no_summary = flatten_stock(detail, None)
    row_with_summary = flatten_stock(detail, _make_summary())

    # Both paths must emit these summary-only fields — None when no summary is given.
    assert "max_fair_price" in row_no_summary, (
        "max_fair_price must be present (as None) on the summary=None path "
        "so the column set is invariant across both paths."
    )
    assert row_no_summary["max_fair_price"] is None, (
        "max_fair_price must be None when summary=None"
    )
    assert "margin_of_safety_pct" in row_no_summary, (
        "margin_of_safety_pct must be present (as None) on the summary=None path "
        "so the column set is invariant across both paths."
    )
    assert row_no_summary["margin_of_safety_pct"] is None, (
        "margin_of_safety_pct must be None when summary=None"
    )
    # Confirm they also appear with a summary (with their real values or None).
    assert "max_fair_price" in row_with_summary
    assert "margin_of_safety_pct" in row_with_summary


@given(
    active_flags=_rf_strategy(),
)
@settings(max_examples=40)
def test_flatten_flag_membership_invariant(active_flags):
    """G4: exactly the flags in active_flags ∩ KNOWN_RISK_FLAGS are True;
    all others are False.  No flag bleeds across rows.
    """
    from compute.warehouse.flag_registry import KNOWN_RISK_FLAGS
    from compute.warehouse.flatten import flatten_stock

    row = flatten_stock(_make_detail(risk_flags=active_flags), None)
    active_set = set(active_flags)

    for flag in KNOWN_RISK_FLAGS:
        col = f"flag_{flag}"
        expected = flag in active_set
        assert row[col] is expected, (
            f"{col}: expected {expected}, got {row[col]} "
            f"(active_flags={active_flags})"
        )


@given(
    active_warns=_vw_strategy(),
)
@settings(max_examples=40)
def test_flatten_warn_membership_invariant(active_warns):
    """G4: exactly the warnings in active_warns ∩ KNOWN_VALUATION_WARNINGS are True."""
    from compute.warehouse.flag_registry import KNOWN_VALUATION_WARNINGS
    from compute.warehouse.flatten import flatten_stock

    row = flatten_stock(_make_detail(valuation_warnings=active_warns), None)
    active_set = set(active_warns)

    for warn in KNOWN_VALUATION_WARNINGS:
        col = f"warn_{warn}"
        expected = warn in active_set
        assert row[col] is expected, (
            f"{col}: expected {expected}, got {row[col]} "
            f"(active_warns={active_warns})"
        )


@given(
    composite=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    current_price=st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=30)
def test_flatten_scalar_values_in_memory(composite, current_price):
    """G4: scalar values survive flatten (in-memory only — no Parquet I/O).

    Verifies that composite_score and current_price pass through flatten_stock
    unchanged.  The Parquet serialization contract is covered by the dedicated
    non-Hypothesis test_flatten_scalar_parquet_round_trip below.

    I/O is intentionally absent here because deferred pyarrow imports on the
    first Hypothesis example exceed the default 200ms deadline when run in
    isolation — that startup cost is not a signal about the flatten logic.
    """
    from compute.output.schemas import StockDetail
    from compute.warehouse.flatten import flatten_stock

    detail = StockDetail(
        ticker="RT",
        name="RT Corp",
        sector="Technology",
        recommendation="neutral",
        rank=1,
        composite_score=composite,
        current_price=current_price,
        pillar_scores=_ps_all_set(),
        raw_metrics=_raw_metrics_all_none(),
        data_quality=_data_quality(),
        risk_flags=[],
        valuation_warnings=[],
        index_membership="sp500",
        index_memberships=["sp500"],
    )

    row = flatten_stock(detail, None)

    assert abs(row["composite_score"] - composite) < 1e-9, (
        f"composite_score not preserved: {composite!r} → {row['composite_score']!r}"
    )
    assert abs(row["current_price"] - current_price) < 1e-9, (
        f"current_price not preserved: {current_price!r} → {row['current_price']!r}"
    )
    assert row["row_provenance"] == "live"


def test_flatten_scalar_parquet_round_trip(tmp_path):
    """G4: scalar values survive flatten → Parquet write → read-back unchanged.

    Non-Hypothesis companion to test_flatten_scalar_values_in_memory.  Uses a
    fixed pair of (composite, current_price) so deferred pyarrow import startup
    cost does not interfere with Hypothesis deadline tracking.
    """
    import pyarrow.parquet as pq

    from compute.output.schemas import StockDetail
    from compute.warehouse.writer import write_run_snapshot

    composite = 73.5
    current_price = 142.50

    detail = StockDetail(
        ticker="RT",
        name="RT Corp",
        sector="Technology",
        recommendation="neutral",
        rank=1,
        composite_score=composite,
        current_price=current_price,
        pillar_scores=_ps_all_set(),
        raw_metrics=_raw_metrics_all_none(),
        data_quality=_data_quality(),
        risk_flags=[],
        valuation_warnings=[],
        index_membership="sp500",
        index_memberships=["sp500"],
    )

    write_run_snapshot([detail], [], _make_metadata(), date(2026, 6, 21), tmp_path)
    part = tmp_path / "snapshots" / "year=2026" / "run_date=2026-06-21" / "part-0.parquet"
    table = pq.read_table(part)
    assert table.num_rows == 1
    row = {col: table.column(col)[0].as_py() for col in table.schema.names}

    assert abs(row["composite_score"] - composite) < 1e-6, (
        f"composite_score round-trip failed: {composite!r} → {row['composite_score']!r}"
    )
    assert abs(row["current_price"] - current_price) < 1e-3, (
        f"current_price round-trip failed: {current_price!r} → {row['current_price']!r}"
    )
    assert row["row_provenance"] == "live"


# ---------------------------------------------------------------------------
# G6 — manifest part_path is relative, POSIX
# ---------------------------------------------------------------------------

class TestManifestPartPath:
    """G6: manifest part_path is a relative POSIX path, not an absolute one."""

    def test_manifest_part_path_is_relative(self, tmp_path):
        """G6: the part_path column in _manifest.parquet is relative to
        warehouse_dir, not an absolute filesystem path.

        This ensures the manifest is portable across machines and CI environments
        where the warehouse root may be at a different absolute path.
        """
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        write_run_snapshot(
            [_make_detail()],
            [_make_summary()],
            _make_metadata(),
            date(2026, 6, 21),
            tmp_path,
        )
        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        part_path = manifest["part_path"][0]

        # Must not start with "/" (i.e., must be relative).
        assert not part_path.startswith("/"), (
            f"manifest part_path should be relative, got: {part_path!r}"
        )
        # Must use POSIX separators (forward slash), not backslash.
        assert "\\" not in part_path, (
            f"manifest part_path must use POSIX separators, got: {part_path!r}"
        )
        # Sanity: the relative path must resolve to the actual parquet file.
        resolved = tmp_path / part_path
        assert resolved.exists(), (
            f"Resolved path {resolved} does not exist (part_path={part_path!r})"
        )

    def test_manifest_schema_version_matches_metadata(self, tmp_path):
        """G6: the schema_version column in the manifest matches meta.version."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        meta = _make_metadata()
        write_run_snapshot([_make_detail()], [_make_summary()], meta, date(2026, 6, 21), tmp_path)
        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        assert manifest["schema_version"][0] == meta.version

    def test_manifest_universe_matches_metadata(self, tmp_path):
        """G6: the universe column in the manifest matches meta.universe."""
        import pyarrow.parquet as pq

        from compute.warehouse.writer import write_run_snapshot

        meta = _make_metadata()
        write_run_snapshot([_make_detail()], [_make_summary()], meta, date(2026, 6, 21), tmp_path)
        manifest = pq.read_table(tmp_path / "_manifest.parquet").to_pydict()
        assert manifest["universe"][0] == meta.universe
