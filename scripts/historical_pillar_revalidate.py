"""Historical pillar revalidation CLI — Phase 4.6 honest baseline scaffolding.

Phase 4.6 task #2 first unit. Quick CLI that reports the universe drift
between today and a historical as-of date. Future revisions layer on
per-pillar IC / PBO / DSR baselines pulled from git-archived
``rankings.json`` snapshots.

Usage:
    python -m scripts.historical_pillar_revalidate --as-of 2024-06-01
    python -m scripts.historical_pillar_revalidate --as-of 2023-01-01 --json
    python -m scripts.historical_pillar_revalidate --as-of 2020-01-01

Exit codes:
    0  — drift report produced cleanly
    1  — degraded (is_complete=False) — operator must investigate
    2  — usage / argument error
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date

from compute.ingest.universe import get_sp500_constituents
from compute.validation.universe_drift import (
    compute_universe_drift,
    format_drift_report,
)

logger = logging.getLogger(__name__)


def _parse_iso_date(s: str) -> _date:
    try:
        return _date.fromisoformat(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--as-of must be ISO YYYY-MM-DD, got {s!r}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="historical_pillar_revalidate",
        description=(
            "Phase 4.6 universe-drift report for honest re-validation. "
            "Compares today's S&P 500 to the constituent set at any "
            "historical as-of date (per the CSV in data/sp500_membership_historical.csv)."
        ),
    )
    parser.add_argument(
        "--as-of",
        required=True,
        type=_parse_iso_date,
        help="ISO date (YYYY-MM-DD) to query historical membership at.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit report as JSON to stdout (default: human-readable text).",
    )
    parser.add_argument(
        "--no-fetch-universe",
        action="store_true",
        help=(
            "Skip the Wikipedia fetch and use a tiny hardcoded current-"
            "universe (CI-friendly + smoke-testable without network). "
            "Drift counts will be artificially small."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.no_fetch_universe:
        current_universe = frozenset({"AAPL", "MSFT", "NVDA", "TSLA", "SMCI", "META", "GOOGL"})
        logger.info(
            "Using hardcoded 7-ticker current-universe (smoke mode); pass --as-of older "
            "than 2020-01-01 to see degraded-mode handling."
        )
    else:
        try:
            df = get_sp500_constituents()
        except Exception as exc:  # noqa: BLE001 — graceful degradation
            logger.error("Universe fetch failed (%s). Re-run with --no-fetch-universe for offline.", type(exc).__name__)
            return 2
        current_universe = frozenset(df["ticker"].tolist())

    report = compute_universe_drift(args.as_of, current_universe)

    if args.json:
        out = {
            "as_of_date": report.as_of_date.isoformat(),
            "anchor_date": report.anchor_date.isoformat(),
            "current_size": report.current_size,
            "universe_size_at_as_of": report.universe_size_at_as_of,
            "added_since_count": len(report.added_since),
            "removed_since_count": len(report.removed_since),
            "unchanged_count": len(report.unchanged),
            "added_since": sorted(report.added_since),
            "removed_since": sorted(report.removed_since),
            "is_complete": report.is_complete,
            "events_applied": report.events_applied,
            "note": report.note,
        }
        print(json.dumps(out, indent=2))
    else:
        print(format_drift_report(report))

    return 0 if report.is_complete else 1


if __name__ == "__main__":
    sys.exit(main())
