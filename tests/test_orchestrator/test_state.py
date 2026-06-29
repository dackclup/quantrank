"""Unit tests for compute.orchestrator.state (PR #259-R1).

Covers:
- MetricsCollector.reset_shares_fallback() zeroes the underlying global
- MetricsCollector.shares_fallback_stats reads the current global state
- Reads through MetricsCollector reflect increments made to the underlying
  module-global (thread-safe store in fundamentals.py)
- ComputeState default-constructs a MetricsCollector
- ComputeState.metrics is a MetricsCollector instance

All tests are offline / synthetic: they drive ``compute.ingest.fundamentals``
module-globals directly (or via the public accessors) to simulate what the
parallelised ``_build_snapshot`` increments do at runtime.  No network calls.
"""

from __future__ import annotations

import pytest

import compute.ingest.fundamentals as _fundamentals
from compute.orchestrator.state import ComputeState, MetricsCollector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_global(key: str, value: int) -> None:
    """Directly write a value into the module-level _FALLBACK_STATS dict.

    This simulates the locked increment that happens inside the threaded
    ``_build_snapshot`` calls during a live compute run.  Using the lock
    here so the helper is itself thread-safe even though the tests run
    single-threaded.
    """
    with _fundamentals._FALLBACK_STATS_LOCK:
        _fundamentals._FALLBACK_STATS[key] = value


def _reset_global() -> None:
    """Zero all counters in _FALLBACK_STATS via the public API."""
    _fundamentals.reset_fallback_stats()


@pytest.fixture(autouse=True)
def _restore_fallback_stats_global():
    """Snapshot + restore the shared ``_FALLBACK_STATS`` global around each test.

    These tests mutate the ``compute.ingest.fundamentals`` module-global to
    simulate the locked increments ``_build_snapshot`` performs at runtime.
    Without restoration a non-zero counter could leak into any later test in
    the same process that reads the global without resetting first.  Snapshot
    on entry, restore on exit so the global is left exactly as it was found.
    """
    with _fundamentals._FALLBACK_STATS_LOCK:
        saved = dict(_fundamentals._FALLBACK_STATS)
    try:
        yield
    finally:
        with _fundamentals._FALLBACK_STATS_LOCK:
            _fundamentals._FALLBACK_STATS.clear()
            _fundamentals._FALLBACK_STATS.update(saved)


# ---------------------------------------------------------------------------
# Section A: MetricsCollector construction
# ---------------------------------------------------------------------------

def test_A1_metrics_collector_default_constructs():
    """MetricsCollector must be instantiable with no arguments."""
    mc = MetricsCollector()
    assert isinstance(mc, MetricsCollector)


def test_A2_compute_state_default_constructs_metrics_collector():
    """ComputeState() must default-construct a MetricsCollector in .metrics."""
    state = ComputeState()
    assert isinstance(state.metrics, MetricsCollector)


def test_A3_compute_state_metrics_is_metrics_collector_type():
    """ComputeState.metrics field is exactly MetricsCollector, not a subtype."""
    state = ComputeState()
    assert type(state.metrics) is MetricsCollector


# ---------------------------------------------------------------------------
# Section B: reset_shares_fallback zeroes the underlying global
# ---------------------------------------------------------------------------

def test_B1_reset_clears_triggered():
    """reset_shares_fallback() zeroes the 'triggered' counter."""
    mc = MetricsCollector()
    _set_global("triggered", 5)
    mc.reset_shares_fallback()
    assert _fundamentals._FALLBACK_STATS["triggered"] == 0


def test_B2_reset_clears_all_six_counters():
    """reset_shares_fallback() zeroes all 6 shares-fallback counters at once."""
    mc = MetricsCollector()
    for key in ("triggered", "too_low", "dimensional_override",
                "per_class_override", "per_class_attempt", "mc_reconcile_failure"):
        _set_global(key, 99)

    mc.reset_shares_fallback()

    stats = _fundamentals._FALLBACK_STATS
    assert stats["triggered"] == 0
    assert stats["too_low"] == 0
    assert stats["dimensional_override"] == 0
    assert stats["per_class_override"] == 0
    assert stats["per_class_attempt"] == 0
    assert stats["mc_reconcile_failure"] == 0


def test_B3_reset_via_state_metrics():
    """ComputeState().metrics.reset_shares_fallback() has the same effect."""
    state = ComputeState()
    _set_global("triggered", 7)
    state.metrics.reset_shares_fallback()
    assert _fundamentals._FALLBACK_STATS["triggered"] == 0


# ---------------------------------------------------------------------------
# Section C: shares_fallback_stats reads reflect the underlying global
# ---------------------------------------------------------------------------

def test_C1_reads_triggered_after_increment():
    """shares_fallback_stats reflects a triggered counter increment."""
    mc = MetricsCollector()
    _reset_global()
    _set_global("triggered", 3)
    stats = mc.shares_fallback_stats
    assert stats["triggered"] == 3


def test_C2_reads_all_six_keys():
    """shares_fallback_stats dict must contain all six expected keys."""
    mc = MetricsCollector()
    _reset_global()
    stats = mc.shares_fallback_stats
    expected_keys = {
        "triggered", "too_low", "dimensional_override",
        "per_class_override", "per_class_attempt", "mc_reconcile_failure",
    }
    assert expected_keys == set(stats.keys())


def test_C3_returns_shallow_copy():
    """shares_fallback_stats returns a fresh copy — mutating the result
    must not affect the underlying module-global."""
    mc = MetricsCollector()
    _reset_global()
    copy1 = mc.shares_fallback_stats
    copy1["triggered"] = 999
    copy2 = mc.shares_fallback_stats
    assert copy2["triggered"] == 0, (
        "Mutating the returned dict must not affect the module-global"
    )


def test_C4_read_reflects_direct_global_change():
    """A direct increment to _FALLBACK_STATS is visible through shares_fallback_stats."""
    mc = MetricsCollector()
    _reset_global()
    _set_global("too_low", 12)
    _set_global("dimensional_override", 4)
    stats = mc.shares_fallback_stats
    assert stats["too_low"] == 12
    assert stats["dimensional_override"] == 4


def test_C5_reset_then_read_via_state():
    """Full lifecycle via ComputeState: reset → (simulated increment) → read."""
    state = ComputeState()
    state.metrics.reset_shares_fallback()
    # Simulate what _build_snapshot does inside the ThreadPool
    _set_global("triggered", 10)
    _set_global("per_class_attempt", 2)
    _set_global("per_class_override", 1)
    fb = state.metrics.shares_fallback_stats
    assert fb["triggered"] == 10
    assert fb["per_class_attempt"] == 2
    assert fb["per_class_override"] == 1
    assert fb["too_low"] == 0
    assert fb["dimensional_override"] == 0
    assert fb["mc_reconcile_failure"] == 0


# ---------------------------------------------------------------------------
# Section D: values match those readable via the public fundamentals API
# ---------------------------------------------------------------------------

def test_D1_collector_and_public_api_return_same_dict():
    """MetricsCollector.shares_fallback_stats must equal get_fallback_stats()."""
    mc = MetricsCollector()
    _reset_global()
    _set_global("triggered", 6)
    assert mc.shares_fallback_stats == _fundamentals.get_fallback_stats()


def test_D2_reset_via_collector_matches_public_reset():
    """After reset via collector, get_fallback_stats() must also read zeros."""
    mc = MetricsCollector()
    _set_global("triggered", 42)
    mc.reset_shares_fallback()
    assert _fundamentals.get_fallback_stats()["triggered"] == 0
