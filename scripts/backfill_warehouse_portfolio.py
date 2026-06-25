"""Warehouse portfolio history backfill — Task 2.

Thin wrapper that calls the EXISTING ``compute.warehouse.portfolio_writer.write_portfolio_snapshot``
against the current ``frontend/public/data/portfolio/backtest_pit.json`` so the
full rebalance history (2016→today) is materialised into the committed warehouse
NOW rather than waiting for the next weekday cron.

Output
------
    data/warehouse/portfolio/year=<YYYY>/run_date=<ISO>/part-0.parquet
    data/warehouse/portfolio_manifest.parquet

The output is the same schema as what the cron would write; it is
reproducible-from-artifact (not fabricated scoring data), so committing it
alongside the forward cron partitions is legitimate.

Idempotence
-----------
``write_portfolio_snapshot`` already deduplicates by ``run_date`` in the
portfolio manifest (append-or-update, same pattern as ``_manifest.parquet``).
Re-running this script for the same ``run_date`` replaces the existing partition.

.gitignore
----------
``!data/warehouse/portfolio/**/*.parquet`` and
``!data/warehouse/portfolio_manifest.parquet`` are already whitelisted by
PR #597's .gitignore additions.  No change needed here.

Usage
-----
    python -m scripts.backfill_warehouse_portfolio [--run-date YYYY-MM-DD]
                                                    [--warehouse-dir PATH]
                                                    [--artifact-path PATH]
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0=ok, 1=error."""
    import argparse

    from compute import config
    from compute.warehouse.portfolio_writer import write_portfolio_snapshot

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="python -m scripts.backfill_warehouse_portfolio",
        description=(
            "Warehouse portfolio history backfill (Task 2). "
            "Calls write_portfolio_snapshot against the current backtest_pit.json "
            "to materialise the full rebalance history into the committed warehouse. "
            "Idempotent: same run_date replaces the existing portfolio partition."
        ),
    )
    parser.add_argument(
        "--run-date",
        default=date.today().isoformat(),
        help=(
            "Logical run date for the warehouse partition key "
            f"(default: today, {date.today().isoformat()})."
        ),
    )
    parser.add_argument(
        "--warehouse-dir",
        default=None,
        help=(
            "Root of the warehouse on disk. "
            f"Default: {config.WAREHOUSE_DIR} (config.WAREHOUSE_DIR)."
        ),
    )
    parser.add_argument(
        "--artifact-path",
        default=None,
        help=(
            "Path to backtest_pit.json. "
            "Default: frontend/public/data/portfolio/backtest_pit.json "
            "(resolved relative to the project root)."
        ),
    )
    args = parser.parse_args(argv)

    # Resolve run_date.
    try:
        run_date = date.fromisoformat(args.run_date)
    except ValueError as exc:
        logger.error("Invalid --run-date: %s", exc)
        return 1

    # Resolve warehouse_dir.
    warehouse_dir: Path = (
        Path(args.warehouse_dir) if args.warehouse_dir else config.WAREHOUSE_DIR
    )

    # Resolve artifact_path.
    artifact_path: Path | None = Path(args.artifact_path) if args.artifact_path else None

    logger.info(
        "backfill_warehouse_portfolio: run_date=%s warehouse_dir=%s artifact_path=%s",
        run_date, warehouse_dir, artifact_path or "(default)",
    )

    try:
        n_rows = write_portfolio_snapshot(
            run_date=run_date,
            warehouse_dir=warehouse_dir,
            artifact_path=artifact_path,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("backfill_warehouse_portfolio: FATAL: %s", exc, exc_info=True)
        return 1

    if n_rows == 0:
        logger.warning(
            "backfill_warehouse_portfolio: 0 rows written "
            "(artifact absent, empty rebalances, or no holdings). "
            "Check that backtest_pit.json exists at the expected path."
        )
        # Return 0 — graceful no-op is not an error (mirrors portfolio_writer contract).
        print("backfill_warehouse_portfolio: 0 rows written (artifact absent or empty).")
        return 0

    print(f"backfill_warehouse_portfolio: wrote {n_rows} holding rows (run_date={run_date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
