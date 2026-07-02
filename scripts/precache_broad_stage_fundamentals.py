"""Phase 9.3 precache split — Stage 2/4: fundamentals + annual history.

Job 2 of 4 in the ``precache-broad-universe.yml`` workflow (see
``scripts/precache_broad_stage_prices.py`` module docstring for the full
gate-C1 background). This script is a THIN wrapper: it downloads the
survivor ticker frame job 1 uploaded, then calls the SAME Step-2/Step-3
orchestrator helpers ``run_weekly_compute`` calls
(``compute.orchestrator.fundamentals.fetch_all_fundamentals`` +
``compute.orchestrator.history.fetch_all_history``) so its on-disk cache
writes (``compute/cache/fundamentals/`` + ``compute/cache/
fundamentals_history/``) are byte-identical to what the ranked
``QR_UNIVERSE=broad_investable_us`` cron path would produce for the same
survivor tickers.

This script does NOT call ``compute.main.run_weekly_compute`` and does NOT
write any scoring output.

Input
-----
Reads the survivor frame (columns: ticker, cik, name, sector, cohort) from
``config.BROAD_UNIVERSE_PRECACHE_SURVIVOR_PATH`` — downloaded by the
workflow's ``actions/download-artifact`` step before this script runs.

Environment
-----------
``EDGAR_USER_AGENT``
    Required by the fundamentals/history fetchers (each degrades
    gracefully to ``None``/empty per ticker when unset — see
    ``compute/ingest/fundamentals.py``).
``QR_SKIP_BROAD_UNIVERSE``
    Set to ``1``/``true``/``yes`` to no-op immediately (exit 0).

Exit codes
----------
0
    Fundamentals + history fetch completed (or skipped via the env-var
    gate).
1
    Aborted: the survivor artifact is missing/empty, or an unexpected
    exception escaped the fetch calls.

Usage
-----
    python -m scripts.precache_broad_stage_fundamentals
"""

from __future__ import annotations

import logging
import os
import sys
import time

import pandas as pd

logger = logging.getLogger(__name__)


def _skip_gate() -> bool:
    from compute import config

    return os.environ.get(config.BROAD_UNIVERSE_SKIP_ENV_VAR, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _load_survivor_frame() -> pd.DataFrame:
    """Read the job-1 survivor artifact. Returns an empty frame on any failure."""
    from compute import config

    path = config.BROAD_UNIVERSE_PRECACHE_SURVIVOR_PATH
    if not path.exists():
        logger.error(
            "Survivor artifact not found at %s — was the download-artifact "
            "step wired correctly ahead of this script?",
            path,
        )
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read survivor artifact at %s", path)
        return pd.DataFrame()
    if df.empty or "ticker" not in df.columns:
        logger.error(
            "Survivor artifact at %s is empty or missing the 'ticker' column.", path
        )
        return pd.DataFrame()
    return df


def run_stage_fundamentals() -> int:
    """Fetch fundamentals snapshots + annual history for the survivor set.

    Returns the number of survivor tickers processed (0 on abort/skip).
    """
    from compute.orchestrator.fundamentals import fetch_all_fundamentals
    from compute.orchestrator.history import fetch_all_history

    df = _load_survivor_frame()
    if df.empty:
        return 0

    t0 = time.monotonic()
    logger.info(
        "[stage-fundamentals] Fetching fundamentals snapshots for %d survivor "
        "tickers (warms compute/cache/fundamentals/)…",
        len(df),
    )
    snapshots, fundamentals_latency = fetch_all_fundamentals(df)
    n_snap_ok = sum(1 for v in snapshots.values() if v is not None)
    logger.info(
        "[stage-fundamentals] Fundamentals coverage: %d / %d", n_snap_ok, len(df)
    )

    logger.info(
        "[stage-fundamentals] Fetching annual history for %d survivor tickers "
        "(warms compute/cache/fundamentals_history/)…",
        len(df),
    )
    histories = fetch_all_history(df)
    n_hist_ok = sum(1 for v in histories.values() if not v.empty)
    logger.info(
        "[stage-fundamentals] Annual history coverage: %d / %d", n_hist_ok, len(df)
    )

    wall_clock = time.monotonic() - t0
    p50 = (
        float(pd.Series(list(fundamentals_latency.values())).median())
        if fundamentals_latency
        else 0.0
    )
    print(
        f"precache_broad_stage_fundamentals summary: "
        f"survivors={len(df)} fundamentals_ok={n_snap_ok} history_ok={n_hist_ok} "
        f"fundamentals_latency_p50={p50:.2f}s wall_clock={wall_clock:.1f}s"
    )
    return len(df)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if _skip_gate():
        from compute import config

        logger.info(
            "[stage-fundamentals] %s=1 — skipping (no-op).",
            config.BROAD_UNIVERSE_SKIP_ENV_VAR,
        )
        return 0

    try:
        n = run_stage_fundamentals()
    except Exception:  # noqa: BLE001
        logger.exception("[stage-fundamentals] FATAL — unexpected exception")
        return 1

    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
