"""Phase 9.3 precache split — Stage 1/4: price screen + survivor selection.

Part of the 4-job ``precache-broad-universe.yml`` workflow (owner-authorised
fix for the gate-C1 finding: a single-job cold run of the
``QR_UNIVERSE=broad_investable_us`` ranked path was CANCELLED at GitHub
Actions' hard 6-hour per-job ceiling with no cache saved). This script is
job 1 of 4 — it is a THIN wrapper: it loads the Broad Investable US
candidate pool, fetches prices for the full pool (warming
``compute/cache/prices/``), applies the investability screen, and uploads
the surviving ticker frame so jobs 2-4 (fundamentals+history / form4 /
tier2) can fetch EDGAR data for exactly the same ~3,545-name survivor set
the real ranked cron run would score — never the full ~6,883-name
candidate pool.

This script does NOT call ``compute.main.run_weekly_compute`` and does NOT
write any scoring output (no ``rankings.json`` / ``metadata.json``). It
calls the SAME orchestrator helpers ``run_weekly_compute`` calls
(``compute.orchestrator.prices.fetch_all_prices``,
``compute.ingest.broad_universe.select_broad_universe_survivors``) so its
on-disk cache writes are byte-identical to what the ranked path would
produce for the same tickers.

Output
------
Writes the survivor frame (columns: ticker, cik, name, sector, cohort) to
``config.BROAD_UNIVERSE_PRECACHE_SURVIVOR_PATH``. The workflow uploads this
file as a ``actions/upload-artifact`` artifact; jobs 2-4 download it and
read it back with ``pandas.read_parquet``.

Environment
-----------
``EDGAR_USER_AGENT``
    Required by ``fetch_broad_universe_candidates`` (hard-raises if unset —
    see ``compute/ingest/broad_universe.py::_fetch_sec_company_tickers_json``).
``QR_SKIP_BROAD_UNIVERSE``
    Set to ``1``/``true``/``yes`` to no-op immediately (exit 0). Mirrors the
    same escape hatch ``_run_broad_universe_probe`` /
    ``select_broad_universe_survivors`` honour in ``compute.main`` — useful
    for a manual dry-run of the workflow skeleton without hitting SEC.

Exit codes
----------
0
    Survivor frame written successfully (or skipped via the env-var gate).
1
    Aborted: too few priced tickers or too few survivors
    (``config.MIN_VALID_TICKERS`` floor, mirroring
    ``run_weekly_compute``'s abort-without-writing convention) — the
    non-zero exit fails the GitHub Actions step, which skips the
    downstream ``needs: [price-screen]`` jobs rather than burning CI
    minutes on an empty/garbage survivor set.

Usage
-----
    python -m scripts.precache_broad_stage_prices
"""

from __future__ import annotations

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)


def _skip_gate() -> bool:
    """Mirror ``BROAD_UNIVERSE_SKIP_ENV_VAR`` gate used elsewhere (Rule 18)."""
    from compute import config

    return os.environ.get(config.BROAD_UNIVERSE_SKIP_ENV_VAR, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def run_stage_prices() -> int:
    """Fetch the broad-universe candidate pool, price it, screen survivors.

    Returns the number of survivors written (0 on abort/skip — callers map
    this through ``main()`` to a process exit code).
    """
    from compute import config
    from compute.ingest.broad_universe import (
        candidates_to_universe_frame,
        fetch_broad_universe_candidates,
        select_broad_universe_survivors,
    )
    from compute.orchestrator.prices import fetch_all_prices

    t0 = time.monotonic()

    logger.info("[stage-prices] Fetching Broad Investable US candidate pool…")
    candidates = fetch_broad_universe_candidates()
    universe = candidates_to_universe_frame(candidates)
    logger.info(
        "[stage-prices] Candidate universe size: %d (pre-screen)", len(universe)
    )
    if universe.empty:
        logger.error(
            "[stage-prices] Candidate universe is empty — aborting without "
            "writing a survivor artifact."
        )
        return 0

    logger.info(
        "[stage-prices] Fetching prices for %d candidates (warms compute/cache/prices/)…",
        len(universe),
    )
    rows, prices_by_ticker, _adv_by_ticker = fetch_all_prices(universe)
    logger.info("[stage-prices] Priced %d / %d candidates", len(rows), len(universe))

    if len(rows) < config.MIN_VALID_TICKERS:
        logger.error(
            "[stage-prices] Only %d candidates priced — below minimum of %d. "
            "Aborting without writing a survivor artifact.",
            len(rows),
            config.MIN_VALID_TICKERS,
        )
        return 0

    survivors = select_broad_universe_survivors(
        candidates=universe, prices_by_ticker=prices_by_ticker
    )
    logger.info(
        "[stage-prices] Investability screen: %d / %d priced candidates survived",
        len(survivors),
        len(rows),
    )

    if len(survivors) < config.MIN_VALID_TICKERS:
        logger.error(
            "[stage-prices] Only %d survivors — below minimum of %d. "
            "Aborting without writing a survivor artifact.",
            len(survivors),
            config.MIN_VALID_TICKERS,
        )
        return 0

    survivor_frame = (
        universe[universe["ticker"].isin(survivors)]
        .loc[:, ["ticker", "cik", "name", "sector", "cohort"]]
        .reset_index(drop=True)
    )

    out_path = config.BROAD_UNIVERSE_PRECACHE_SURVIVOR_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    survivor_frame.to_parquet(out_path, index=False)

    wall_clock = time.monotonic() - t0
    print(
        f"precache_broad_stage_prices summary: "
        f"candidates={len(universe)} priced={len(rows)} "
        f"survivors={len(survivor_frame)} wall_clock={wall_clock:.1f}s "
        f"artifact={out_path}"
    )
    return len(survivor_frame)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if _skip_gate():
        from compute import config

        logger.info(
            "[stage-prices] %s=1 — skipping (no-op).", config.BROAD_UNIVERSE_SKIP_ENV_VAR
        )
        return 0

    try:
        n = run_stage_prices()
    except Exception:  # noqa: BLE001
        logger.exception("[stage-prices] FATAL — unexpected exception")
        return 1

    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
