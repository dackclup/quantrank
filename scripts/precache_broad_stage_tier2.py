"""Phase 9.3 precache split — Stage 4/4: Tier-2 event-defense fetch (10-K + 8-K).

Job 4 of 4 in the ``precache-broad-universe.yml`` workflow (see
``scripts/precache_broad_stage_prices.py`` module docstring for the full
gate-C1 background). This script is a THIN wrapper: it downloads the
survivor ticker frame job 1 uploaded, then calls the SAME Step-4b
orchestrator helper ``run_weekly_compute`` calls
(``compute.orchestrator.tier2.fetch_all_tier2``) so its on-disk cache
writes (``compute/cache/edgar_10k_text/`` + ``compute/cache/edgar_8k/`` —
both SLOW-TEXT bundle paths) are byte-identical to what the ranked
``QR_UNIVERSE=broad_investable_us`` cron path would produce for the same
survivor tickers.

Tier-2 (10-K text + 8-K events) is the single most expensive EDGAR loop at
scale (~89 min cold at sp1500's ~1504 names per the precache-edgar.yml
empirical baseline) — this is why it gets its own dedicated job with the
LARGEST timeout budget of the four stages.

This script does NOT call ``compute.main.run_weekly_compute`` and does NOT
write any scoring output.

Input
-----
Reads the survivor frame from
``config.BROAD_UNIVERSE_PRECACHE_SURVIVOR_PATH`` — downloaded by the
workflow's ``actions/download-artifact`` step before this script runs.

Environment
-----------
``EDGAR_USER_AGENT``
    Required by the Tier-2 fetchers (each per-defense fetch degrades
    gracefully — see ``compute/scoring/tier2.py::fetch_tier2_for_ticker``,
    which returns a ``Tier2Result`` with ``fetch_succeeded=False`` rather
    than raising).
``QR_SKIP_BROAD_UNIVERSE``
    Set to ``1``/``true``/``yes`` to no-op immediately (exit 0).

Exit codes
----------
0
    Tier-2 fetch completed (or skipped via the env-var gate).
1
    Aborted: the survivor artifact is missing/empty, or an unexpected
    exception escaped the fetch call.

Usage
-----
    python -m scripts.precache_broad_stage_tier2
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


def run_stage_tier2() -> int:
    """Fetch Tier-2 event defenses (10-K + 8-K) for the survivor set.

    Returns the number of survivor tickers processed (0 on abort/skip).
    """
    from compute.orchestrator.tier2 import fetch_all_tier2

    df = _load_survivor_frame()
    if df.empty:
        return 0

    t0 = time.monotonic()
    logger.info(
        "[stage-tier2] Fetching Tier-2 event defenses for %d survivor tickers "
        "(warms compute/cache/edgar_10k_text/ + compute/cache/edgar_8k/)…",
        len(df),
    )
    tier2_results, tier2_wall_clock_seconds = fetch_all_tier2(df)
    n_ok = sum(1 for v in tier2_results.values() if v.fetch_succeeded)

    wall_clock = time.monotonic() - t0
    print(
        f"precache_broad_stage_tier2 summary: "
        f"survivors={len(df)} results={len(tier2_results)} ok={n_ok} "
        f"loop_wall_clock={tier2_wall_clock_seconds}s wall_clock={wall_clock:.1f}s"
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
            "[stage-tier2] %s=1 — skipping (no-op).", config.BROAD_UNIVERSE_SKIP_ENV_VAR
        )
        return 0

    try:
        n = run_stage_tier2()
    except Exception:  # noqa: BLE001
        logger.exception("[stage-tier2] FATAL — unexpected exception")
        return 1

    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
