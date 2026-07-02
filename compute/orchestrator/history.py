"""Step-3 parallel annual-fundamentals-history fetch helper for the weekly
compute orchestrator.

Extracted from ``compute.main`` as a prerequisite for the Phase 9.3
broad-universe 4-job precache split (the ``scripts/precache_broad_stage_
fundamentals.py`` stage script needs to call this loop independently of
``run_weekly_compute``).  It mirrors the EXACT extraction pattern already
used for the sibling EDGAR-bound loops in
``compute/orchestrator/{prices,fundamentals,form4,tier2}.py`` (PRs
#259-R2..R5) — in particular ``fundamentals.py`` (Step 2), whose per-ticker
timing / timeout / exception-handling shape this module copies verbatim.

The logic here is a PURE CODE MOVE — no behaviour change, no reordering of
effects, same exception handling, same dict keys, same log text/levels.
Output is byte-identical to the inline Step-3 loop it replaces in
``compute.main``.

Public surface
--------------
``fetch_all_history(df, *, max_workers, timeout)``
    Run the parallelised Step-3 loop and return ``histories``
    (``dict[str, pd.DataFrame]``).

Private helper (moved verbatim from ``compute.main``)
-------------------------------------------------------
``_history_one(ticker, cik)`` — fetch + time one ticker's annual history.
Returns ``(history_df, elapsed_seconds)``; empty ``DataFrame`` on a missing
CIK or any failure.  The caller (``fetch_all_history``) discards the
elapsed component — same as the original inline loop, which bound it to
the throwaway ``_hist_elapsed`` name.

Thread-safety
-------------
``fetch_all_history`` spawns a ``ThreadPoolExecutor`` with ``max_workers``
threads; the per-ticker results are accumulated on the main thread after
each future completes, exactly as the original inline loop did.  No new
shared state is introduced.

Timeout handling
-----------------
The ``timeout`` parameter (default ``_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS``
from ``compute.main``, passed in by the caller — the constant STAYS in
``compute.main`` because Step 2's ``fetch_all_fundamentals`` call also
needs it, mirroring the R3 precedent) is forwarded to
``fut.result(timeout=timeout)``.  The ``TimeoutError`` arm sets
``histories[ticker] = pd.DataFrame()``; the broad ``Exception`` arm does
the same — both match the original inline loop exactly.

What stays in ``compute.main``
-------------------------------
The ``logger.info("Fetching annual fundamentals history…")`` line and the
``histories: dict[str, pd.DataFrame] = {}`` initializer stay in
``compute.main`` immediately before the call to ``fetch_all_history`` —
same fundamentals.py (R3) precedent: the step-orchestration-level "starting
this step" log fires in the same position, exactly once.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from compute import config
from compute.ingest.fundamentals import fetch_fundamentals_history

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helper (moved verbatim from compute.main — DO NOT alter logic)
# ---------------------------------------------------------------------------


def _history_one(ticker: str, cik: str) -> tuple[pd.DataFrame, float]:
    """Fetch annual history for one CIK, timed.

    Returns (history_df, elapsed_seconds). Empty DataFrame on missing
    CIK or any failure. Elapsed always captured.
    """
    t0 = time.perf_counter()
    if not cik:
        return pd.DataFrame(), 0.0
    df: pd.DataFrame = pd.DataFrame()
    try:
        df = fetch_fundamentals_history(cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals_history raised for cik=%s: %s", cik, e)
    elapsed = time.perf_counter() - t0
    logger.debug(
        "fundamentals_history_fetch ticker=%s elapsed_seconds=%.2f status=%s",
        ticker,
        elapsed,
        "success" if not df.empty else "empty",
    )
    return df, elapsed


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def fetch_all_history(
    df: pd.DataFrame,
    *,
    max_workers: int = config.EDGAR_MAX_WORKERS,
    timeout: int = 45,
) -> dict[str, pd.DataFrame]:
    """Run the Step-3 parallel annual-history fetch loop over *df*.

    Submits one ``_history_one`` task per row using a
    ``ThreadPoolExecutor``.  Results are accumulated as each future
    completes (``as_completed``).  A per-future timeout/exception both
    degrade to an empty ``DataFrame`` for that ticker — exactly as the
    original inline loop.

    Parameters
    ----------
    df:
        Universe DataFrame (rows with at least ``ticker`` and ``cik``
        columns).  Iterated via ``df.iterrows()``.
    max_workers:
        Thread-pool size.  Defaults to ``config.EDGAR_MAX_WORKERS``
        (currently 8, the empirical sweet-spot for the 10 req/s EDGAR
        ceiling — see ``compute/config.py``).
    timeout:
        Per-future timeout in seconds, forwarded to
        ``fut.result(timeout=timeout)``.  The caller passes
        ``_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS`` from ``compute.main``
        (default 45) so the constant stays in main alongside the Step-2
        fundamentals call that also uses it.

    Returns
    -------
    histories : dict[str, pd.DataFrame]
        Keyed by ticker; an empty ``DataFrame`` on any failure/timeout/
        missing-CIK (never ``None``, never a missing key — every row of
        *df* gets an entry).
    """
    histories: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                _history_one, r["ticker"], str(r.get("cik") or "")
            ): r["ticker"]
            for _, r in df.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                hist_df, _hist_elapsed = fut.result(timeout=timeout)
                histories[ticker] = hist_df
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "History task timed out (>%ds) for %s — skipping ticker.",
                    timeout,
                    ticker,
                )
                histories[ticker] = pd.DataFrame()
            except Exception as e:  # noqa: BLE001
                logger.warning("History task raised for %s: %s", ticker, e)
                histories[ticker] = pd.DataFrame()
    return histories
