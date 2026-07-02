"""Tests for the Metadata.broad_universe_sector_resolved_pct wiring in
compute/main.py (Phase 9.4 PR-1, schema 0.10.45-phase9pilot).

Covers the gated aggregation block that turns the Step-8 loop's
``_yf_sector_resolved_by_ticker`` accumulator into the write-only
``Metadata.broad_universe_sector_resolved_pct`` canary.

A full ``run_weekly_compute`` invocation is impractical for offline CI (same
rationale as ``tests/test_ingest/test_sp1500_seam.py`` /
``tests/test_ingest/test_broad_universe_ranked.py``) — wiring-layer
assertions use ``inspect.getsource`` to pin the exact integration points,
while the arithmetic itself is exercised directly against the production
``_coverage_pct`` helper (imported, not copied — CLAUDE.md §Gotchas PR #310).

Test groups:
  BSC1  Source-level gating — the aggregation block is gated behind
        ``if config.QR_UNIVERSE == "broad_investable_us":`` and sits inside
        its own try/except so a failure degrades to None rather than
        blocking the cron.
  BSC2  Source-level wiring — the Metadata constructor call passes
        ``_broad_universe_sector_resolved_pct``, and the aggregation uses
        ``_coverage_pct(_yf_sector_resolved_by_ticker)`` (not a re-derived
        formula).
  BSC3  Coverage-math — ``_coverage_pct`` applied to a synthetic
        ``_yf_sector_resolved_by_ticker``-shaped dict produces the exact
        expected percentage (8 of 10 resolved → 80.0), mirroring the
        production formula this field is built from.
  BSC4  Schema/default — ``Metadata.broad_universe_sector_resolved_pct``
        defaults to None and round-trips through model_dump/model_validate.
"""

from __future__ import annotations

import inspect

from compute.main import _coverage_pct
from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# BSC1 — source-level gating
# ---------------------------------------------------------------------------


def test_BSC1_sector_canary_gated_on_broad_investable_us() -> None:
    """The sector-resolution canary aggregation block must be preceded by
    ``if config.QR_UNIVERSE == "broad_investable_us":`` immediately before
    the ``_coverage_pct(_yf_sector_resolved_by_ticker)`` call — never runs
    unconditionally like the Phase 9.1 probe fields."""
    import compute.main as main_mod

    src = inspect.getsource(main_mod.run_weekly_compute)
    call_pos = src.find("_coverage_pct(\n                _yf_sector_resolved_by_ticker")
    assert call_pos != -1, (
        "_coverage_pct(_yf_sector_resolved_by_ticker) call must be present in "
        "run_weekly_compute"
    )
    preceding = src[:call_pos]
    gate_pos = preceding.rfind('if config.QR_UNIVERSE == "broad_investable_us":')
    assert gate_pos != -1, (
        "_coverage_pct(_yf_sector_resolved_by_ticker) must be gated behind "
        'if config.QR_UNIVERSE == "broad_investable_us":'
    )


def test_BSC1_sector_canary_wrapped_in_own_try_except() -> None:
    """The gated block must be inside its OWN try/except so a bug here NEVER
    blocks the cron — the except clause must fall back to None."""
    import compute.main as main_mod

    src = inspect.getsource(main_mod.run_weekly_compute)
    gate_pos = src.find(
        'if config.QR_UNIVERSE == "broad_investable_us":\n        try:\n            '
        "_broad_universe_sector_resolved_pct = _coverage_pct("
    )
    assert gate_pos != -1, (
        "The gate must be immediately followed by a try: wrapping the "
        "_coverage_pct call"
    )
    after_gate = src[gate_pos : gate_pos + 2000]
    assert "except Exception as _sector_resolve_exc:" in after_gate
    assert "_broad_universe_sector_resolved_pct = None" in after_gate


def test_BSC1_sector_canary_variable_initialised_to_none() -> None:
    """``_broad_universe_sector_resolved_pct`` must be initialised to None
    before the gated block, so every non-broad_investable_us path (and a
    computation failure) leaves it at the documented None default."""
    import compute.main as main_mod

    src = inspect.getsource(main_mod.run_weekly_compute)
    assert "_broad_universe_sector_resolved_pct: float | None = None" in src


# ---------------------------------------------------------------------------
# BSC2 — source-level wiring: Metadata constructor + formula reuse
# ---------------------------------------------------------------------------


def test_BSC2_metadata_constructor_passes_sector_resolved_pct() -> None:
    """The Metadata(...) constructor call in run_weekly_compute must pass
    broad_universe_sector_resolved_pct=_broad_universe_sector_resolved_pct."""
    import compute.main as main_mod

    src = inspect.getsource(main_mod.run_weekly_compute)
    assert (
        "broad_universe_sector_resolved_pct=_broad_universe_sector_resolved_pct"
        in src
    )


def test_BSC2_uses_production_coverage_pct_helper_not_reimplemented() -> None:
    """The aggregation must call the shared ``_coverage_pct`` helper (the
    same formula exchange_coverage_pct / dividend_coverage_pct /
    security_type_coverage_pct use) rather than re-deriving the percentage
    inline — a drift-prevention guard (CLAUDE.md §Gotchas 'no verbatim-copy
    test helpers' extends symmetrically to production call sites)."""
    import compute.main as main_mod

    src = inspect.getsource(main_mod.run_weekly_compute)
    gate_pos = src.find('if config.QR_UNIVERSE == "broad_investable_us":')
    # There may be multiple occurrences of this exact gate text elsewhere
    # (e.g. the Phase 9.3 universe-selector); find the one immediately
    # preceding the sector-resolved-pct assignment.
    target_pos = src.find("_broad_universe_sector_resolved_pct = _coverage_pct(")
    assert target_pos != -1
    assert gate_pos != -1
    assert gate_pos < target_pos


# ---------------------------------------------------------------------------
# BSC3 — coverage-math against the production formula
# ---------------------------------------------------------------------------


def test_BSC3_coverage_pct_eight_of_ten_resolved_is_80_pct() -> None:
    """A synthetic _yf_sector_resolved_by_ticker-shaped dict with 8 of 10
    tickers resolved (non-None GICS-mapped sector) → 80.0%, using the exact
    production _coverage_pct formula this canary is built from."""
    synthetic = {
        "AAPL": "Information Technology",
        "MSFT": "Information Technology",
        "JPM": "Financials",
        "XOM": "Energy",
        "PG": "Consumer Staples",
        "JNJ": "Health Care",
        "NEE": "Utilities",
        "PLD": "Real Estate",
        # 2 unresolved (unmapped raw sector or absent yfinance data).
        "UNRESOLVED1": None,
        "UNRESOLVED2": None,
    }
    assert _coverage_pct(synthetic) == 80.0


def test_BSC3_coverage_pct_all_resolved_is_100_pct() -> None:
    synthetic = {"AAPL": "Information Technology", "MSFT": "Information Technology"}
    assert _coverage_pct(synthetic) == 100.0


def test_BSC3_coverage_pct_none_resolved_is_0_pct() -> None:
    synthetic = {"AAPL": None, "MSFT": None}
    assert _coverage_pct(synthetic) == 0.0


def test_BSC3_coverage_pct_empty_universe_is_none() -> None:
    """An empty broad-universe survivor set (edge case) → None, matching the
    ZeroDivisionError-avoiding guard shared with every other coverage field."""
    assert _coverage_pct({}) is None


# ---------------------------------------------------------------------------
# BSC4 — schema default + round-trip
# ---------------------------------------------------------------------------


def _minimal_metadata_kwargs(**overrides) -> dict:
    base = dict(
        version="0.10.45-phase9pilot",
        last_update_utc="2026-07-02T00:00:00+00:00",
        next_update_utc="2026-07-03T00:00:00+00:00",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="local",
        git_commit="abc123",
    )
    base.update(overrides)
    return base


def test_BSC4_metadata_field_defaults_to_none() -> None:
    """Metadata.broad_universe_sector_resolved_pct defaults to None when not
    explicitly passed — the byte-identical-on-every-other-path guarantee
    (sp500/sp900/sp1500 all leave this field unset)."""
    meta = Metadata(**_minimal_metadata_kwargs())
    assert meta.broad_universe_sector_resolved_pct is None


def test_BSC4_metadata_field_accepts_float_value_and_round_trips() -> None:
    """The field accepts a real float (e.g. from a broad_investable_us
    dispatch) and round-trips through model_dump_json/model_validate_json."""
    meta = Metadata(
        **_minimal_metadata_kwargs(
            universe="BROAD_INVESTABLE_US",
            universe_size=3545,
            broad_universe_sector_resolved_pct=80.0,
        )
    )
    assert meta.broad_universe_sector_resolved_pct == 80.0

    round_tripped = Metadata.model_validate_json(meta.model_dump_json())
    assert round_tripped.broad_universe_sector_resolved_pct == 80.0
