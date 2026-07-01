"""Phase-4h OSAP signal-replication pipeline for the weekly compute orchestrator.

Extracted from ``compute.main`` as part of PR #259-R6 (incremental refactor
of ``run_weekly_compute``). The logic here is a PURE CODE MOVE — no
behaviour change, no reordering of effects, same exception handling, same
deferred-import placement, same wall-clock, same log text/levels. Output is
byte-identical to the inline block it replaces.

Scope note
----------
This module owns ONLY the Phase-4h OSAP block (the ``osap_*`` accumulators
+ ``composite_osap_adjusted``). The sibling Phase-4j.1 Qlib Alpha158 block
(its own ``alpha158_*`` accumulators) and any IPCA block are SEPARATE
observability surfaces — they stay inline in ``compute.main`` and are NOT
touched by this module (a future refactor slice, if any).

``OsapGateDiagnostic`` (``compute/output/schemas.py``) is shared between
this OSAP block and the sibling Alpha158 block, so ``compute.main`` keeps
its own top-level import of that schema class — this module also imports
it directly for its own return-type annotation.

Deferred imports (Phase-4a pattern, preserved verbatim)
--------------------------------------------------------
``compute.ingest.osap`` pulls in ``openassetpricing`` at module load (only
installed via the ``.[factors]`` optional extra), so a top-level import
would break base-install test collection. The four OSAP-library imports
(``compute.features.osap_replicate``, ``compute.ingest.osap``,
``compute.scoring.osap_blend``, ``compute.validation.osap_validation``)
stay INSIDE the try block in :func:`run_osap_pipeline`, exactly as they
were inside the inline block in ``compute.main`` — moving them to this
module's top level would defeat the whole point of the deferred-import
pattern.

Public surface
--------------
``run_osap_pipeline(pillar_df, composite, asof_date)``
    Run the Phase-4h OSAP try/except pipeline and return an
    :class:`OsapPipelineResult` with the ~10 accumulators.

Byte-identical guarantee
------------------------
* happy-path: every field populated exactly as the original inline block
  would populate its local variables (same fetch → gate → IC → blend
  sequence, same log lines).
* outer ``except Exception as e``: every field reset to its empty/None/
  ``pd.Series(dtype=float)`` value, same warning log text.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import NamedTuple

import pandas as pd

from compute import config
from compute.output.schemas import OsapGateDiagnostic

logger = logging.getLogger(__name__)


class OsapPipelineResult(NamedTuple):
    """The ~10 Phase-4h OSAP accumulators, in the same order
    ``compute.main`` unpacks them into local names of the same name."""

    osap_signals_used: list[str]
    osap_excluded_signals: list[str]
    osap_signals_ic_12m: dict[str, float]
    osap_signal_map: dict[str, dict[str, float] | None]
    osap_signals_coverage_pct: dict[str, float]
    composite_osap_adjusted: pd.Series
    osap_signals_missing_from_dataset: list[str]
    osap_gate_diagnostics: dict[str, OsapGateDiagnostic]
    osap_signals_dropped_no_long_short_list: list[str]
    osap_wall_clock_seconds: float | None


def run_osap_pipeline(
    pillar_df: pd.DataFrame,
    composite: pd.Series,
    asof_date: date,
) -> OsapPipelineResult:
    """Run the Phase-4h OSAP signal-replication + PBO/DSR gate + Path-b
    blend pipeline.

    Observability-only this phase: Top-5 ranking still uses raw
    ``composite_score`` per SKILL.md Rule 16. The blend writes a
    ``composite_score_osap_adjusted`` per ticker into
    ``StockDetail.osap_blended_score`` for delta-attribution. Wrapped in
    try/except so OSAP fetch / library / network failure NEVER blocks
    weekly production — every OSAP-bearing field degrades to ``None`` on
    the schema (already ``| None = None`` in ``compute/output/schemas.py``).

    Parameters
    ----------
    pillar_df:
        The composite pillar-score DataFrame. Only ``pillar_df.index``
        (the ticker list) is consumed, as the per-ticker signal-map
        ``tickers=`` argument.
    composite:
        The raw composite-score ``pd.Series`` (indexed by ticker) —
        the blend input to ``apply_osap_blend``. Read-only; never
        mutated by this pipeline.
    asof_date:
        The run's as-of ``date`` — passed to ``fetch_osap_returns`` and
        ``compute_osap_signals`` to keep the cross-section point-in-time
        honest.

    Returns
    -------
    OsapPipelineResult
        The ~10 accumulators, in the same shape ``compute.main`` used to
        hold as local variables of the identical name.
    """
    osap_signals_used: list[str] = []
    osap_excluded_signals: list[str] = []
    osap_signals_ic_12m: dict[str, float] = {}
    osap_signal_map: dict[str, dict[str, float] | None] = {}
    osap_signals_coverage_pct: dict[str, float] = {}
    composite_osap_adjusted: pd.Series = pd.Series(dtype=float)
    # Phase 4h.2 Part 1 (issue #116) — manifest entries the OSAP fetch
    # returned no rows for. Populated inside the try block below; left
    # empty when the OSAP pipeline fails entirely (graceful-degradation
    # path leaves every osap_* metadata field None).
    osap_signals_missing_from_dataset: list[str] = []
    # Phase 4h.2 Part 1 (issue #116) — per-signal PBO/DSR/Sharpe/
    # rejection_reason diagnostics for every signal that reaches the
    # gate. Populated inside the try block from ``gate_results``.
    osap_gate_diagnostics: dict[str, OsapGateDiagnostic] = {}
    # Phase 4h.2 Part 2 (issue #116) — signals present in the OSAP
    # dataset but with <2 distinct port buckets (silent drop in
    # 0.9.0-0.9.1; visible here). Closes the 100-signal accounting
    # equation alongside ``osap_signals_missing_from_dataset`` and
    # ``osap_signals_used`` / ``osap_excluded_signals``.
    osap_signals_dropped_no_long_short_list: list[str] = []
    # Issue #287 PR A — wall-clock for the OSAP pipeline. Measures the
    # entire try block including the dataset fetch + gate + per-signal
    # IC compute + blend. `None` semantics: only set to None when the
    # outer except fires (full pipeline failure). On a QR_SKIP_OSAP
    # cache-hit fast return the wall-clock will be a small float (~0.5-2s)
    # — informative as "skipped fast" vs the cold ~120-300s download.
    _osap_wc_start = time.monotonic()
    osap_wall_clock_seconds: float | None = None
    try:
        # Phase 4a — deferred imports. `compute.ingest.osap` pulls in
        # `openassetpricing` at module load (only installed via the
        # `.[factors]` optional extra), so a top-level import would
        # break `tests/test_main.py` collection in base-install envs.
        # ImportError here is caught by the existing `except Exception`
        # below and falls through to the same graceful-degradation path
        # any other OSAP-pipeline failure takes (every osap_* field
        # already nullable per Rule 18).
        from compute.features.osap_replicate import (
            compute_long_short_returns,
            compute_osap_signals,
            coverage_by_signal,
            signals_dropped_no_long_short,
            signals_in_dataframe,
        )
        from compute.ingest.osap import fetch_osap_returns
        from compute.scoring.osap_blend import aggregate_osap_signals, apply_osap_blend
        from compute.validation.osap_validation import (
            compute_rolling_ic_12m,
            filter_accepted_signals,
            gate_osap_signals,
        )

        logger.info(
            "Phase 4h — fetching OSAP returns for %d-signal manifest "
            "(as_of=%s)",
            len(config.OSAP_SIGNALS_100),
            asof_date.isoformat(),
        )
        osap_returns_raw = fetch_osap_returns(
            signals=list(config.OSAP_SIGNALS_100),
            as_of=asof_date,
        )
        # Phase 4h.2 Part 1 — surface silent drops between manifest and
        # dataset (issue #116). 100 manifest signals, but production
        # observation has shown only ~22 reach the gate; the other ~78
        # silently disappeared at this filter step in 0.9.0-phase4h.
        # Now they land in metadata.osap_signals_missing_from_dataset.
        present_signals = signals_in_dataframe(osap_returns_raw)
        osap_signals_missing_from_dataset = sorted(
            set(config.OSAP_SIGNALS_100) - present_signals
        )
        if osap_signals_missing_from_dataset:
            logger.warning(
                "OSAP manifest signals not in dataset: %d/%d missing "
                "(first 5: %s)",
                len(osap_signals_missing_from_dataset),
                len(config.OSAP_SIGNALS_100),
                osap_signals_missing_from_dataset[:5],
            )
        # Phase 4h.2 Part 2 — signals with <2 port buckets (no LS pair).
        # Restrict to the requested manifest so the accounting equation
        # closes against OSAP_SIGNALS_100 (dataset rows for non-manifest
        # signals are filtered out by fetch_osap_returns).
        osap_signals_dropped_no_long_short_list = [
            s
            for s in signals_dropped_no_long_short(osap_returns_raw)
            if s in set(config.OSAP_SIGNALS_100)
        ]
        if osap_signals_dropped_no_long_short_list:
            logger.warning(
                "OSAP signals in dataset but with <2 port buckets "
                "(no LS pair possible): %d/%d dropped (first 5: %s)",
                len(osap_signals_dropped_no_long_short_list),
                len(config.OSAP_SIGNALS_100),
                osap_signals_dropped_no_long_short_list[:5],
            )
        osap_ls = compute_long_short_returns(osap_returns_raw)
        logger.info(
            "OSAP long-short rows: %d across %d signals",
            len(osap_ls),
            osap_ls["signalname"].nunique() if not osap_ls.empty else 0,
        )

        gate_results = gate_osap_signals(
            osap_ls,
            requested_signals=config.OSAP_SIGNALS_100,
        )
        # Phase 4h.2 Part 1 — persist per-signal gate decisions into
        # metadata (issue #116). Captures EVERY signal that reached the
        # gate (both accepted and rejected); accepted signals carry
        # ``rejection_reason=None`` while rejected carry one of the
        # canonical taxonomy values (``high_pbo`` / ``low_dsr`` /
        # ``insufficient_data`` / ``gate_failed``) per
        # ``compute/validation/osap_validation.py::GateResult``.
        osap_gate_diagnostics = {
            sig: OsapGateDiagnostic(
                pbo=result.pbo,
                dsr=result.dsr,
                sharpe=result.sharpe,
                rejection_reason=result.rejection_reason,
            )
            for sig, result in gate_results.items()
        }
        osap_signals_used, osap_excluded_signals = filter_accepted_signals(
            gate_results
        )
        logger.info(
            "OSAP PBO/DSR gate: %d accepted, %d excluded "
            "(of %d candidates)",
            len(osap_signals_used),
            len(osap_excluded_signals),
            len(gate_results),
        )

        # Rolling-12m Spearman IC per accepted signal — observability only,
        # NOT a gate decision (canonical full walk-forward + purged-embargo
        # CV is deferred to Phase 5 per defense-infrastructure/PLAN.md:270).
        for sig in osap_signals_used:
            ic = compute_rolling_ic_12m(osap_ls, sig)
            if ic is not None:
                osap_signals_ic_12m[sig] = round(float(ic), 4)

        # Per-ticker signal map (commit 2 proxy mode — every ticker gets
        # the market-wide cross-sectional rank). Only the accepted signal
        # subset is consumed; excluded signals never blend.
        if osap_signals_used:
            osap_filtered_returns = osap_returns_raw[
                osap_returns_raw["signalname"].isin(osap_signals_used)
            ]
            osap_signal_map = compute_osap_signals(
                osap_filtered_returns,
                tickers=list(pillar_df.index),
                as_of=asof_date,
                requested_signals=tuple(osap_signals_used),
            )
            osap_signals_coverage_pct = {
                sig: round(pct, 2)
                for sig, pct in coverage_by_signal(osap_signal_map).items()
            }

            # Path-b blend (commit 3) — applied OUTSIDE compute_composite()
            # so PHASE3_WEIGHTS sum-to-1.0 invariant at composite.py:43-45
            # stays intact. 50/50 default locked in
            # osap-integration/PLAN.md:168-170.
            osap_aggregate = aggregate_osap_signals(osap_signal_map)
            composite_osap_adjusted = apply_osap_blend(
                composite, osap_aggregate
            )
        else:
            logger.warning(
                "OSAP gate accepted 0 signals — skipping per-ticker map + "
                "blend; osap_blended_score will be None for every ticker"
            )
        # Issue #287 PR A — wall-clock end marker (success path).
        osap_wall_clock_seconds = round(time.monotonic() - _osap_wc_start, 1)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "OSAP pipeline failed (observability-only — production "
            "continues); StockDetail.osap_* + metadata.osap_* → None. "
            "Error: %s",
            e,
        )
        osap_signals_used = []
        osap_excluded_signals = []
        osap_signals_ic_12m = {}
        osap_signal_map = {}
        osap_signals_coverage_pct = {}
        composite_osap_adjusted = pd.Series(dtype=float)
        osap_signals_missing_from_dataset = []
        osap_gate_diagnostics = {}
        osap_signals_dropped_no_long_short_list = []
        # Issue #287 PR A — leave osap_wall_clock_seconds = None on failure.
        osap_wall_clock_seconds = None

    return OsapPipelineResult(
        osap_signals_used=osap_signals_used,
        osap_excluded_signals=osap_excluded_signals,
        osap_signals_ic_12m=osap_signals_ic_12m,
        osap_signal_map=osap_signal_map,
        osap_signals_coverage_pct=osap_signals_coverage_pct,
        composite_osap_adjusted=composite_osap_adjusted,
        osap_signals_missing_from_dataset=osap_signals_missing_from_dataset,
        osap_gate_diagnostics=osap_gate_diagnostics,
        osap_signals_dropped_no_long_short_list=osap_signals_dropped_no_long_short_list,
        osap_wall_clock_seconds=osap_wall_clock_seconds,
    )
