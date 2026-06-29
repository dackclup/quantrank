"""Tests for the issue #16 restatement-history weight-demotion delta counter
(0.10.42-phase8pilot, Q3 2026 cohort audit).

The counter ``Metadata.restatement_history_weight_demote_delta_count`` is
derived in ``compute/main.py`` via ``_count_restatement_demote_delta``:

    count += 1  iff  "restatement_history" in vw  AND
                     "restatement_high_confidence" NOT in vw

where ``vw = set(summary.valuation_warnings)``.

These tests import the REAL helper from ``compute.main`` and exercise it
against minimal ``StockSummary`` fixtures.  Style follows the ``_filing()``
builder pattern from ``test_eight_k_events.py`` and the ``_summary()``
pattern from ``test_high_conviction_c1.py``.

Coverage:
  D1  plain-restater (bare flag only) → counted
  D2  irregularity ticker (both flags) → NOT counted (net delta = 0)
  D3  clean ticker (neither flag)     → NOT counted
  D4  mixed population: 2 plain + 1 irregularity + 1 clean → count = 2
  D5  high-confidence without bare flag → NOT counted (theoretical edge case)
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Import the REAL helper from compute.main — tests bind to the shipped code
# ---------------------------------------------------------------------------
from compute.main import _count_restatement_demote_delta
from compute.output.schemas import StockSummary

# ---------------------------------------------------------------------------
# Import-resolves guard: if the symbol is absent/renamed this fails loudly
# ---------------------------------------------------------------------------
assert callable(_count_restatement_demote_delta), (
    "_count_restatement_demote_delta must be importable and callable from compute.main"
)


# ---------------------------------------------------------------------------
# Minimal StockSummary builder — only valuation_warnings varies per test
# ---------------------------------------------------------------------------

def _summary(ticker: str, warnings: list[str]) -> StockSummary:
    """Build a minimal synthetic StockSummary with the given valuation_warnings.

    All required fields are given nominal constant values; only
    ``valuation_warnings`` is varied per test case.  Matches the builder
    pattern in ``test_high_conviction_c1.py``.
    """
    return StockSummary(
        rank=1,
        ticker=ticker,
        name="Test Corp",
        sector="Technology",
        composite_score=50.0,
        current_price=100.0,
        valuation_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# D1: plain-restater — counted
# ---------------------------------------------------------------------------


def test_D1_plain_restater_is_counted():
    """A ticker carrying ONLY ``restatement_history`` must appear in the
    demote-delta count.  This is the core behavioral contract of the
    issue #16 counter.
    """
    summaries = [_summary("TST", ["restatement_history"])]
    assert _count_restatement_demote_delta(summaries) == 1


# ---------------------------------------------------------------------------
# D2: irregularity ticker — NOT counted (net delta zero)
# ---------------------------------------------------------------------------


def test_D2_irregularity_both_flags_not_counted():
    """A confirmed-irregularity ticker carrying BOTH ``restatement_history``
    AND ``restatement_high_confidence`` must NOT be counted.

    Rationale: for irregularity tickers the weight rose 3.0→8.0 on the
    high-confidence flag, so the combined manipulation-index total remains
    8.0 (net delta = 0).  Including them would overstate the demotion scope.

    This test directly verifies the partition: no-usable-fundamentals vs
    present-but-corrupt (DQIC issue #18 governing precedent mentioned in
    CLAUDE.md §Gotchas).
    """
    summaries = [
        _summary("TST", ["restatement_history", "restatement_high_confidence"])
    ]
    assert _count_restatement_demote_delta(summaries) == 0


# ---------------------------------------------------------------------------
# D3: clean ticker — NOT counted
# ---------------------------------------------------------------------------


def test_D3_clean_ticker_not_counted():
    """A ticker with neither restatement flag must not appear in the count."""
    summaries = [_summary("CLEAN", ["goodwill_heavy", "value_trap_risk"])]
    assert _count_restatement_demote_delta(summaries) == 0


def test_D3_empty_warnings_not_counted():
    """A ticker with no valuation_warnings at all must not appear in the count."""
    summaries = [_summary("EMPTY", [])]
    assert _count_restatement_demote_delta(summaries) == 0


# ---------------------------------------------------------------------------
# D4: mixed population — only plain-restaters counted
# ---------------------------------------------------------------------------


def test_D4_mixed_population_counts_only_plain_restaters():
    """Population: 2 plain-restaters + 1 irregularity + 1 clean → count = 2.

    This is the realistic SP1500 scenario: ~268 plain-restaters, ~4 confirmed
    irregularities (0.27% base rate), rest clean.
    """
    summaries = [
        _summary("PLAIN1", ["restatement_history"]),
        _summary("PLAIN2", ["restatement_history", "late_filing_notification"]),
        _summary("IRREG",  ["restatement_history", "restatement_high_confidence"]),
        _summary("CLEAN",  ["goodwill_heavy"]),
    ]
    assert _count_restatement_demote_delta(summaries) == 2


def test_D4_empty_population_returns_zero():
    """Empty summaries list → count = 0."""
    assert _count_restatement_demote_delta([]) == 0


# ---------------------------------------------------------------------------
# D5: high-confidence without bare flag — NOT counted (theoretical edge case)
# ---------------------------------------------------------------------------


def test_D5_high_confidence_only_not_counted():
    """A ticker with ONLY ``restatement_high_confidence`` (but no bare flag)
    must NOT be counted.

    Theoretically this can't happen in production (high-confidence is a
    STRICT SUBSET of history — an amendment must have fired for the
    co-occurrence check to yield a result), but the predicate must still
    handle it correctly.
    """
    summaries = [_summary("TST", ["restatement_high_confidence"])]
    assert _count_restatement_demote_delta(summaries) == 0


# ---------------------------------------------------------------------------
# Invariant: count is always non-negative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("warnings", [
    [],
    ["restatement_history"],
    ["restatement_high_confidence"],
    ["restatement_history", "restatement_high_confidence"],
    ["goodwill_heavy", "value_trap_risk"],
])
def test_count_is_always_non_negative(warnings: list[str]):
    """The demote-delta count must never be negative for any single summary."""
    summaries = [_summary("TST", warnings)]
    assert _count_restatement_demote_delta(summaries) >= 0
