"""Step-4b Tier-2 event-defense fetch helper for the weekly compute orchestrator.

Extracted from ``compute.main`` as part of PR #259-R5 (incremental refactor
of ``run_weekly_compute``).  The logic here is a PURE CODE MOVE — no
behaviour change, no reordering of effects, same exception handling, same
log text/levels.  Output is byte-identical to the inline block it replaces.

Name-collision note
--------------------
This module (``compute.orchestrator.tier2``) is DISTINCT from
``compute.scoring.tier2`` (the Tier-2 events orchestrator that defines
``fetch_tier2_for_ticker``, ``Tier2Result``, ``tier2_events_dict``, and
``coverage_pct``).  This module IMPORTS ``fetch_tier2_for_ticker`` and
``Tier2Result`` FROM ``compute.scoring.tier2`` — it does not redefine or
modify anything in ``compute/scoring/tier2.py``.

Public surface
--------------
``fetch_all_tier2(df, *, max_workers)``
    Run the Step-4b parallel Tier-2 fetch loop and return
    ``(tier2_results, tier2_wall_clock_seconds)``.

What stays in ``compute.main``
-------------------------------
The coverage-percentage calculation (``tier2_coverage_pct_calc`` aka
``coverage_pct`` from ``compute.scoring.tier2``) and its summary log line
are NOT moved here — they read the returned ``tier2_results`` dict and
belong with the downstream Step-5 risk-flag injection that also consumes
it (``non_reliance_by_ticker``, the per-ticker ``tier2_events`` display
dict, ``Metadata.tier2_coverage_pct`` / ``tier2_wall_clock_seconds``).

Byte-identical guarantee
------------------------
* happy-path: ``{ticker: Tier2Result, …}, round(wall_clock, 1)``
* per-future raise: the failing ticker is skipped (warned, not added to
  the dict); all other tickers still collected normally.
* outer-except (e.g. an interpreter-level failure before the executor
  block completes): ``tier2_results`` as accumulated so far (possibly
  empty), ``tier2_wall_clock_seconds = None``.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from compute import config
from compute.scoring.tier2 import Tier2Result, fetch_tier2_for_ticker

logger = logging.getLogger(__name__)


def fetch_all_tier2(
    df: pd.DataFrame,
    *,
    max_workers: int = config.EDGAR_MAX_WORKERS,
) -> tuple[dict[str, Tier2Result], float | None]:
    """Run the Step-4b Tier-2 event-defense fetch block over *df*.

    Fetched in parallel ahead of risk-flag computation so the resulting
    non_reliance veto can be injected into ``compute_risk_flags`` (avoiding
    a duplicate EDGAR fetch inside the risk-overlay layer). See
    ``compute/scoring/tier2.py``.

    ``fetch_tier2_for_ticker`` catches every per-defense exception
    internally, so a failed fetch surfaces as a ``Tier2Result`` with
    ``fetch_succeeded=False`` (not an exception). The defensive try/except
    below covers only the unexpected case (e.g., interpreter-level bug); a
    missing-ticker entry in ``tier2_results`` just means no veto and an
    empty tier2_events display dict for that ticker.

    Parameters
    ----------
    df:
        Universe DataFrame (rows with at least a ``ticker`` column).
        Iterated via ``df.iterrows()``.
    max_workers:
        Thread-pool size.  Defaults to ``config.EDGAR_MAX_WORKERS``.

    Returns
    -------
    tier2_results : dict[str, Tier2Result]
        Per-ticker Tier-2 results. Missing entries mean the fetch failed
        (skipped) for that ticker; possibly empty on outer-except.
    tier2_wall_clock_seconds : float | None
        Round-1-decimal wall-clock for the entire loop. ``None`` if the
        outer try/except fires before the end marker is reached.
    """
    logger.info("Fetching Tier-2 event defenses (10-K + 8-K) for %d tickers…", len(df))
    tier2_results: dict[str, Tier2Result] = {}
    # Issue #287 PR A — wall-clock start marker.
    _tier2_wc_start = time.monotonic()
    tier2_wall_clock_seconds: float | None = None
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(fetch_tier2_for_ticker, r["ticker"]): r["ticker"]
                for _, r in df.iterrows()
            }
            for fut in as_completed(futures):
                ticker = futures[fut]
                try:
                    tier2_results[ticker] = fut.result()
                except Exception as e:  # noqa: BLE001
                    logger.warning("Tier-2 task raised for %s: %s", ticker, e)
                    # Skip this ticker — downstream uses .get() with safe defaults.
        tier2_wall_clock_seconds = round(time.monotonic() - _tier2_wc_start, 1)
    except Exception as _t2_outer_e:  # noqa: BLE001
        # Defensive: an interpreter-level failure before the end marker
        # keeps `tier2_wall_clock_seconds = None` (skipped semantic).
        logger.warning("Tier-2 loop failed entirely: %s", _t2_outer_e)

    return tier2_results, tier2_wall_clock_seconds
