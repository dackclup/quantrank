"""Step-2 parallel fundamentals snapshot fetch helper for the weekly compute orchestrator.

Extracted from ``compute.main`` as part of PR #259-R3 (incremental refactor
of ``run_weekly_compute``).  The logic here is a PURE CODE MOVE — no
behaviour change, no reordering of effects, same exception handling, same
dict keys.  Output is byte-identical to the inline loop it replaces.

Public surface
--------------
``fetch_all_fundamentals(df, *, max_workers, timeout)``
    Run the parallelised Step-2 loop and return
    ``(snapshots, fundamentals_latency)``.

Private helpers (moved verbatim from compute.main)
----------------------------------------------------
``_fundamentals_one(ticker, cik)`` — fetch + time one ticker's snapshot.

Thread-safety
-------------
``fetch_all_fundamentals`` spawns a ``ThreadPoolExecutor`` with
``max_workers`` threads; the per-ticker results are accumulated on the
main thread after each future completes, exactly as the original inline
loop did.  No new shared state is introduced.

Timeout handling
----------------
The ``timeout`` parameter (default ``_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS``
from ``compute.main``, passed in by the caller) is forwarded to
``fut.result(timeout=timeout)``.  The ``TimeoutError`` arm sets
``snap=None`` and ``elapsed=float(timeout)``; the broad ``Exception`` arm
sets ``snap=None`` and ``elapsed=0.0`` — both match the original inline
loop exactly.

IMPORTANT: ``_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS`` and
``import concurrent.futures as _cf`` MUST remain in ``compute.main``
because the Step-3 annual-history loop (main.py ~line 1485) also uses
them.  This module imports its own ``concurrent.futures`` for its own
``TimeoutError`` reference.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot, fetch_fundamentals

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helpers (moved verbatim from compute.main — DO NOT alter logic)
# ---------------------------------------------------------------------------


def _fundamentals_one(
    ticker: str, cik: str
) -> tuple[FundamentalsSnapshot | None, float]:
    """Fetch the snapshot for one ticker, timed.

    Returns (snapshot, elapsed_seconds). ``snapshot`` is ``None`` on
    any failure (logged, not raised). The elapsed is captured even on
    failure so the latency histogram covers stuck/erroring tickers.
    """
    t0 = time.perf_counter()
    snap: FundamentalsSnapshot | None = None
    try:
        snap = fetch_fundamentals(ticker, cik)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_fundamentals raised for %s/%s: %s", ticker, cik, e)
    elapsed = time.perf_counter() - t0
    logger.info(
        "fundamentals_fetch ticker=%s elapsed_seconds=%.2f status=%s",
        ticker,
        elapsed,
        "success" if snap is not None else "failure",
    )
    return snap, elapsed


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def fetch_all_fundamentals(
    df: pd.DataFrame,
    *,
    max_workers: int = config.EDGAR_MAX_WORKERS,
    timeout: int = 45,
) -> tuple[dict[str, FundamentalsSnapshot | None], dict[str, float]]:
    """Run the Step-2 parallel fundamentals snapshot fetch loop over *df*.

    Submits one ``_fundamentals_one`` task per row using a
    ``ThreadPoolExecutor``.  Results are accumulated as each future
    completes (``as_completed``).  A per-future try/except logs a warning
    and records ``snap=None``/``elapsed=...`` on failure — exactly as the
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
        ``fut.result(timeout=timeout)``.  Caller passes
        ``_FUNDAMENTALS_FUTURE_TIMEOUT_SECONDS`` from ``compute.main``
        (default 45) so the constant stays in main alongside the Step-3
        loop that also uses it.

    Returns
    -------
    snapshots : dict[str, FundamentalsSnapshot | None]
        Keyed by ticker; ``None`` on any failure.
    fundamentals_latency : dict[str, float]
        Keyed by ticker; elapsed seconds for each fetch attempt.
    """
    snapshots: dict[str, FundamentalsSnapshot | None] = {}
    fundamentals_latency: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_fundamentals_one, r["ticker"], str(r.get("cik") or "")): r["ticker"]
            for _, r in df.iterrows()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                snap, elapsed = fut.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Fundamentals task timed out (>%ds) for %s — skipping ticker.",
                    timeout,
                    ticker,
                )
                snap = None
                elapsed = float(timeout)
            except Exception as e:  # noqa: BLE001
                logger.warning("Fundamentals task raised for %s: %s", ticker, e)
                snap = None
                elapsed = 0.0
            snapshots[ticker] = snap
            fundamentals_latency[ticker] = elapsed
    return snapshots, fundamentals_latency
