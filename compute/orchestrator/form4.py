"""Form-4 insider-transaction fetch helper for the weekly compute orchestrator.

Extracted from ``compute.main`` as part of PR #259-R4 (incremental refactor
of ``run_weekly_compute``).  The logic here is a PURE CODE MOVE — no
behaviour change, no reordering of effects, same exception handling, same
dict keys.  Output is byte-identical to the inline block it replaces.

Also absorbs spaghetti smell #9: the inner ``_fetch_one_form4`` closure was
defined inside ``run_weekly_compute``; it is now at module scope here.  The
closure only ever closed over module-level names (``fetch_recent_form4``,
``time``, ``logger``) so the move is clean — no loop/local captures.

Public surface
--------------
``fetch_all_form4(df, *, max_workers)``
    Run the Form-4 fetch block and return a 5-tuple:
    ``(form4_diagnostics, form4_latencies, form4_failures,
    form4_wall_clock_seconds, form4_negation_guard_downgrade_count)``.

Private helpers (moved verbatim from compute.main)
---------------------------------------------------
``_fetch_one_form4(ticker)`` — per-ticker worker; returns
    ``(diagnostic_dict, elapsed_seconds, is_failure)``.

Byte-identical guarantee
------------------------
All three execution paths — SKIP (``FORM4_FETCH_SKIP=1``), happy-path, and
outer-except — produce the same 5 output values as the original inline block:

* SKIP:       ``{}, [], [], None, None``
* happy-path: ``{ticker: diag, …}, [elapsed, …], [failed_ticker, …],
              round(wall_clock, 1), get_negation_downgrade_count()``
* outer-except: ``{}, [], [], None, None``

The same ``time.monotonic()`` + ``round(…, 1)`` wall-clock,
``reset_negation_downgrade_count()`` / ``get_negation_downgrade_count()``
negation counter semantics, and every log line text/level are preserved
exactly.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from compute import config
from compute.scoring.form4_insider import (
    fetch_recent_form4,
    get_negation_downgrade_count,
    reset_negation_downgrade_count,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helper (moved verbatim from compute.main — DO NOT alter logic)
# Smell #9 fix: was a closure inside run_weekly_compute; now at module scope.
# Safe to move: only closes over module-level names (fetch_recent_form4,
# time, logger) — no loop/local captures.
# ---------------------------------------------------------------------------


def _fetch_one_form4(ticker: str) -> tuple[dict, float, bool]:
    """Per-ticker Form-4 fetch worker. Returns (diagnostic_dict,
    elapsed_seconds, is_failure). Catches every exception inline so
    the ThreadPoolExecutor never sees a raised future — keeps the
    outer loop's failure semantics intact."""
    t0 = time.perf_counter()
    try:
        transactions = fetch_recent_form4(ticker)
        elapsed = time.perf_counter() - t0
        if transactions is None:
            return (
                {
                    "insider_count": 0,
                    "latest_filing_date": None,
                    "fetch_status": "failed",
                },
                elapsed,
                True,
            )
        distinct = len({t["insider_cik"] for t in transactions})
        latest = transactions[0]["filing_date"] if transactions else None
        return (
            {
                "insider_count": distinct,
                "latest_filing_date": latest,
                "fetch_status": "ok",
            },
            elapsed,
            False,
        )
    except Exception as _f4_e:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        logger.warning("form4 fetch failed for %s: %s", ticker, _f4_e)
        return (
            {
                "insider_count": 0,
                "latest_filing_date": None,
                "fetch_status": "failed",
            },
            elapsed,
            True,
        )


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def fetch_all_form4(
    df: pd.DataFrame,
    *,
    max_workers: int = config.EDGAR_MAX_WORKERS,
) -> tuple[dict[str, dict], list[float], list[str], float | None, int | None]:
    """Run the Form-4 insider-transaction fetch block over *df*.

    Preserves the exact three-path semantics of the original inline block:

    * ``FORM4_FETCH_SKIP`` env-var set → logs the skip message; all 5 outputs
      at their empty/None init values.
    * Happy path → ``ThreadPoolExecutor`` with ``max_workers`` threads; per-
      ticker ``_fetch_one_form4``; accumulates diagnostics/latencies/failures;
      sets wall-clock (``round(monotonic, 1)``) and negation-guard count.
    * Outer ``except`` → warns, resets all 5 to ``{}``, ``[]``, ``[]``,
      ``None``, ``None``.

    Parameters
    ----------
    df:
        Universe DataFrame (rows with at least a ``ticker`` column).
        Iterated via ``df.iterrows()``.
    max_workers:
        Thread-pool size.  Defaults to ``config.EDGAR_MAX_WORKERS``
        (currently 8 — empirical sweet-spot for the EDGAR 10 req/s ceiling).

    Returns
    -------
    form4_diagnostics : dict[str, dict]
        Per-ticker diagnostic dicts (``insider_count``, ``latest_filing_date``,
        ``fetch_status``).  Empty on SKIP or outer-except.
    form4_latencies : list[float]
        Per-ticker elapsed seconds.  Empty on SKIP or outer-except.
    form4_failures : list[str]
        Tickers that returned ``None`` or raised.  Empty on SKIP or outer-except.
    form4_wall_clock_seconds : float | None
        Round-1-decimal wall-clock for the entire loop.  ``None`` on SKIP or
        outer-except.
    form4_negation_guard_downgrade_count : int | None
        Count of 10b5-1 True → False negation downgrades accumulated across
        all worker threads.  ``None`` on SKIP or outer-except.
    """
    # Initialise all 5 outputs to their empty/None values (mirrors the
    # original inline block so the SKIP path and outer-except path both
    # return consistently — no value ever left undefined).
    form4_diagnostics: dict[str, dict] = {}
    form4_latencies: list[float] = []
    form4_failures: list[str] = []
    # Issue #287 PR A — wall-clock for the Form-4 loop. `None` semantics:
    # never assigned when FORM4_FETCH_SKIP=1 (loop didn't run) OR when the
    # outer try/except fired before the end marker. Populated to the
    # rounded float seconds on the happy path.
    form4_wall_clock_seconds: float | None = None
    _form4_wc_start: float | None = None
    # PR 6 (residual footgun #1 from PR 4-eq) — count of True → False
    # downgrades applied by the post-detector negation guard during cache
    # build (e.g. "10b5-1 plan terminated 2022" + "no 10b5-1 plan in
    # effect"). `None` semantics mirrors form4_wall_clock_seconds: None
    # when FORM4_FETCH_SKIP=1 OR when the outer try/except fired. On the
    # happy path the value is the integer count of downgrades across the
    # universe-wide cache-build. Warm-cache runs report 0 (no detector
    # ran this cron — cached `is_rule_10b5_one` is read as-is); cold-
    # cache runs populate the real cohort number for Q3 cohort audit.
    form4_negation_guard_downgrade_count: int | None = None

    # 2026-05-22 hotfix #3: env-var escape hatch for cold-cache CI
    # contexts (pre-merge-prod-sim). The Form-4 fetch is observability
    # only (form4_enabled=False; _FORM4_FLAGS_ENABLED=False) — it has
    # ZERO scoring impact, so the pre-merge-prod-sim's composite-diff
    # check does NOT need it. The 45-min CI cap on that workflow blew
    # 3x because the property→method parser fix made each filing.obj()
    # do its real HTTP round-trip on a never-populated form4 cache.
    # Weekly cron (compute-rankings.yml, default 360min budget) still
    # runs the full fetch + populates the cache for future sims.
    if os.environ.get("FORM4_FETCH_SKIP", "").lower() in ("1", "true", "yes"):
        logger.info(
            "Phase 4.5e PR 2 — Form-4 fetch SKIPPED via FORM4_FETCH_SKIP "
            "env var. All form4_* Metadata fields will be None / empty "
            "(observability-only signal; zero scoring impact). The "
            "weekly cron populates these fields at default budget."
        )
        # form4_diagnostics / form4_latencies / form4_failures remain
        # empty; the Metadata constructor's `if form4_diagnostics`
        # guards (lines 2092-2118) coerce each form4_* field to None.

    else:

        try:
            _f4_tickers = [str(_f4_r["ticker"]) for _, _f4_r in df.iterrows()]
            logger.info(
                "Phase 4.5e PR 2 — fetching Form-4 insider data for %d tickers "
                "with %d workers …",
                len(_f4_tickers),
                max_workers,
            )
            # Issue #287 PR A — wall-clock start marker (inside else+try so
            # FORM4_FETCH_SKIP=1 leaves form4_wall_clock_seconds=None).
            _form4_wc_start = time.monotonic()
            # PR 6 — reset the module-level negation-guard counter before
            # the fetch loop begins. Counter accumulates True → False
            # downgrades across all worker threads (thread-safe via
            # ``_negation_lock`` inside form4_insider). Read after the
            # ThreadPoolExecutor block completes and aliased to
            # ``form4_negation_guard_downgrade_count`` for Metadata.
            reset_negation_downgrade_count()
            with ThreadPoolExecutor(max_workers=max_workers) as _f4_ex:
                _f4_future_to_ticker = {
                    _f4_ex.submit(_fetch_one_form4, _t): _t for _t in _f4_tickers
                }
                for _f4_future in as_completed(_f4_future_to_ticker):
                    _f4_ticker = _f4_future_to_ticker[_f4_future]
                    try:
                        _f4_diag, _f4_elapsed, _f4_is_failure = _f4_future.result()
                        form4_diagnostics[_f4_ticker] = _f4_diag
                        form4_latencies.append(_f4_elapsed)
                        if _f4_is_failure:
                            form4_failures.append(_f4_ticker)
                    except Exception as _f4_e:  # noqa: BLE001
                        form4_failures.append(_f4_ticker)
                        form4_diagnostics[_f4_ticker] = {
                            "insider_count": 0,
                            "latest_filing_date": None,
                            "fetch_status": "failed",
                        }
                        logger.warning(
                            "form4 future raised for %s: %s", _f4_ticker, _f4_e
                        )
            # Issue #287 PR A — wall-clock end marker (success path).
            form4_wall_clock_seconds = round(
                time.monotonic() - _form4_wc_start, 1
            )
            # PR 6 — read the negation-guard counter accumulated across
            # all worker threads. Always populated on the happy path
            # (zero is a valid value — warm-cache cron OR cold-cache cron
            # with no negation-phrase footnotes in the universe).
            form4_negation_guard_downgrade_count = get_negation_downgrade_count()
            logger.info(
                "Form-4 fetch complete: %d ok, %d failures, p50=%.2fs p95=%.2fs, "
                "wall_clock=%ss, negation_downgrades=%d",
                len(form4_diagnostics) - len(form4_failures),
                len(form4_failures),
                float(np.median(form4_latencies)) if form4_latencies else 0.0,
                float(np.percentile(form4_latencies, 95)) if form4_latencies else 0.0,
                form4_wall_clock_seconds,
                form4_negation_guard_downgrade_count,
            )
        except Exception as _f4_outer_e:  # noqa: BLE001
            logger.warning(
                "Form-4 fetch loop failed entirely (%s); form4_diagnostics → empty.",
                _f4_outer_e,
            )
            form4_diagnostics = {}
            form4_latencies = []
            form4_failures = []
            # Issue #287 PR A — leave form4_wall_clock_seconds = None on failure.
            form4_wall_clock_seconds = None
            # PR 6 — leave negation-guard count = None on outer-try failure
            # (mirrors form4_wall_clock_seconds semantics).
            form4_negation_guard_downgrade_count = None

    return (
        form4_diagnostics,
        form4_latencies,
        form4_failures,
        form4_wall_clock_seconds,
        form4_negation_guard_downgrade_count,
    )
