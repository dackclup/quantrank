"""Phase 9.3 precache split — Stage 3/4: Form-4 insider-transaction fetch.

Job 3 of 4 in the ``precache-broad-universe.yml`` workflow (see
``scripts/precache_broad_stage_prices.py`` module docstring for the full
gate-C1 background). This script is a THIN wrapper: it downloads the
survivor ticker frame job 1 uploaded, then calls the SAME Form-4
orchestrator helper ``run_weekly_compute`` calls
(``compute.orchestrator.form4.fetch_all_form4``) so its on-disk cache
writes (``compute/cache/edgar_form4/`` — the SLOW-TEXT bundle, run-id
keyed, per CLAUDE.md §Gotchas) are byte-identical to what the ranked
``QR_UNIVERSE=broad_investable_us`` cron path would produce for the same
survivor tickers.

Form-4 is historically the single most expensive EDGAR loop at scale
(~72 min cold at sp1500's ~1504 names per the precache-edgar.yml empirical
baseline) — this is why it gets its own dedicated job with the largest
timeout budget short of tier2.

This script does NOT call ``compute.main.run_weekly_compute`` and does NOT
write any scoring output. It deliberately does NOT set
``FORM4_FETCH_SKIP`` — unlike ``pre-merge-prod-sim.yml``, this job's whole
purpose is to warm the Form-4 cache, so the fetch must actually run.

Input
-----
Reads the survivor frame from
``config.BROAD_UNIVERSE_PRECACHE_SURVIVOR_PATH`` — downloaded by the
workflow's ``actions/download-artifact`` step before this script runs.

Environment
-----------
``EDGAR_USER_AGENT``
    Required by the Form-4 fetcher (degrades gracefully to a per-ticker
    failure when unset — see ``compute/scoring/form4_insider.py``).
``QR_SKIP_BROAD_UNIVERSE``
    Set to ``1``/``true``/``yes`` to no-op immediately (exit 0).

Exit codes
----------
0
    Form-4 fetch completed (or skipped via the env-var gate).
1
    Aborted: the survivor artifact is missing/empty, or an unexpected
    exception escaped the fetch call.

Usage
-----
    python -m scripts.precache_broad_stage_form4
"""

from __future__ import annotations

import logging
import os
import sys
import time

import numpy as np
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


def run_stage_form4() -> int:
    """Fetch Form-4 insider-transaction data for the survivor set.

    Returns the number of survivor tickers processed (0 on abort/skip).
    """
    from compute.orchestrator.form4 import fetch_all_form4

    df = _load_survivor_frame()
    if df.empty:
        return 0

    if os.environ.get("FORM4_FETCH_SKIP", "").strip().lower() in ("1", "true", "yes"):
        logger.warning(
            "[stage-form4] FORM4_FETCH_SKIP is set — this defeats the purpose "
            "of this precache stage (it exists solely to warm the Form-4 "
            "cache). Proceeding anyway; fetch_all_form4 will honour the skip "
            "and do nothing."
        )

    t0 = time.monotonic()
    logger.info(
        "[stage-form4] Fetching Form-4 insider data for %d survivor tickers "
        "(warms compute/cache/edgar_form4/)…",
        len(df),
    )
    (
        form4_diagnostics,
        form4_latencies,
        form4_failures,
        form4_wall_clock_seconds,
        form4_negation_guard_downgrade_count,
    ) = fetch_all_form4(df)

    wall_clock = time.monotonic() - t0
    p50 = float(np.median(form4_latencies)) if form4_latencies else 0.0
    p95 = float(np.percentile(form4_latencies, 95)) if form4_latencies else 0.0
    print(
        f"precache_broad_stage_form4 summary: "
        f"survivors={len(df)} ok={len(form4_diagnostics) - len(form4_failures)} "
        f"failures={len(form4_failures)} p50={p50:.2f}s p95={p95:.2f}s "
        f"negation_downgrades={form4_negation_guard_downgrade_count} "
        f"loop_wall_clock={form4_wall_clock_seconds}s wall_clock={wall_clock:.1f}s"
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
            "[stage-form4] %s=1 — skipping (no-op).", config.BROAD_UNIVERSE_SKIP_ENV_VAR
        )
        return 0

    try:
        n = run_stage_form4()
    except Exception:  # noqa: BLE001
        logger.exception("[stage-form4] FATAL — unexpected exception")
        return 1

    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
