"""compute.orchestrator — per-run state container for run_weekly_compute.

PR #259-R1 (FACADE-FIRST, conservative): introduces ``ComputeState`` and
``MetricsCollector`` as the new home for run-scoped accumulators.  R1 is a
minimal first slice: it routes the shares-fallback metrics reset/read through
``MetricsCollector`` while keeping the actual thread-safe module-global in
``compute.ingest.fundamentals`` completely untouched.

R2-R7 will progressively migrate the remaining accumulators in
``run_weekly_compute`` into ``ComputeState`` fields as the function is
decomposed into sub-step helpers.
"""

from compute.orchestrator.state import ComputeState, MetricsCollector

__all__ = ["ComputeState", "MetricsCollector"]
