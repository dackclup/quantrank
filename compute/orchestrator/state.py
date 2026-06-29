"""Per-run state dataclasses for the weekly compute orchestrator.

Design (PR #259, FACADE-FIRST scope)
======================================

``ComputeState`` is the container for all run-scoped accumulators that
currently live as scattered locals or module-globals inside
``run_weekly_compute``.  It is instantiated **once** at the top of
``run_weekly_compute`` and passed to (or accessed by) every sub-step.

``MetricsCollector`` is the run-scoped seat for run-level metrics.  For
R1 it owns only the **shares-fallback group** via a thin facade over the
EXISTING module-global in ``compute.ingest.fundamentals``.  The global
(``_FALLBACK_STATS`` + ``_FALLBACK_STATS_LOCK``) is NOT moved here —
keeping it in-place preserves thread-safety on the hot ingest path and
keeps the R1 diff byte-identical and risk-free.  ``MetricsCollector``
merely delegates to the already-locked public accessors.

Thread-safety contract
-----------------------
``MetricsCollector`` introduces **no new shared state**.  All counters
live in the existing locked ``_FALLBACK_STATS`` dict.  ``reset_shares_fallback``
calls ``fundamentals.reset_fallback_stats()`` which acquires the lock
internally; ``shares_fallback_stats`` calls ``fundamentals.get_fallback_stats()``
which also acquires the lock.  The collector itself holds no mutable
fields and is therefore safe to construct on the main thread and read
from anywhere after the ThreadPool drains.

Future slices (R2-R7)
----------------------
R2 will add the filing-precheck skip counter to ``MetricsCollector``.
R3-R7 will migrate per-ticker accumulators (exchange/country/dividend
coverage dicts, form4 latencies, etc.) into ``ComputeState`` fields and
decompose ``run_weekly_compute`` into sub-step helpers that receive the
state object instead of dozens of individual parameters.

Do NOT add mutable list/dict fields to ``ComputeState`` without a
thread-safe access pattern reviewed in the PR — the compute loop is
heavily parallel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricsCollector:
    """Run-scoped seat for run-level diagnostic metrics.

    R1 scope: delegates the shares-fallback group to the module-global in
    ``compute.ingest.fundamentals``.  The actual counting happens inside
    the ThreadPool-parallelised ``_build_snapshot`` under a lock; this
    collector only exposes the reset + read surface so ``run_weekly_compute``
    no longer needs to import the fundamentals accessors directly.

    Usage in run_weekly_compute::

        state = ComputeState()
        state.metrics.reset_shares_fallback()   # before the fetch loop
        # ... (parallelised fundamentals fetch) ...
        fb = state.metrics.shares_fallback_stats  # after the fetch loop
        triggered = fb["triggered"]
    """

    # ---------------------------------------------------------------------------
    # Shares-fallback facade
    # ---------------------------------------------------------------------------

    def reset_shares_fallback(self) -> None:
        """Reset the shares-fallback counters to zero.

        Delegates to ``compute.ingest.fundamentals.reset_fallback_stats()``
        which holds ``_FALLBACK_STATS_LOCK`` internally.  Call BEFORE the
        parallelised fundamentals fetch loop so this run's counts start at 0.
        """
        # Import locally to avoid a circular import at module load time
        # (fundamentals imports config; main imports both).  The local import
        # is cheap — Python caches sys.modules after the first load.
        from compute.ingest.fundamentals import reset_fallback_stats

        reset_fallback_stats()

    @property
    def shares_fallback_stats(self) -> dict[str, int]:
        """Return a shallow copy of the shares-fallback counters.

        Keys: ``triggered`` · ``too_low`` · ``dimensional_override`` ·
        ``per_class_override`` · ``per_class_attempt`` · ``mc_reconcile_failure``.

        Call AFTER the parallelised fundamentals fetch loop completes.
        The underlying ``get_fallback_stats()`` acquires the lock so the
        snapshot is consistent even if the pool thread joins late.
        """
        from compute.ingest.fundamentals import get_fallback_stats

        return get_fallback_stats()


@dataclass
class ComputeState:
    """Per-run state container for the weekly compute orchestrator.

    Instantiated once at the top of ``run_weekly_compute``; each sub-step
    reads or writes fields here instead of relying on function-local
    scattered locals.

    R1 fields
    ----------
    metrics : MetricsCollector
        Run-level diagnostic metrics.  R1 seats the shares-fallback group.
        R2 will add the filing-precheck skip counter; later slices add more.

    R2-R7 planned additions (do NOT add without the matching refactor PR)
    -----------------------------------------------------------------------
    * Filing-precheck skip counter (R2)
    * Per-ticker coverage dicts: exchange / country / dividend / security_type (R3)
    * Form-4 latencies + diagnostics (R4)
    * Prices / fundamentals intermediate frames (R5)
    * Valuation inputs: universe_metrics / peer_groupings / historical_metrics (R6)
    * Output accumulators: summaries / risk_flags / veto tallies (R7)
    """

    metrics: MetricsCollector = field(default_factory=MetricsCollector)
