"""Manual / dispatch entry point for the SEC filing pointer index (Slice 1).

Iterates a universe of tickers, enumerates each ticker's recent SEC filings
via ``compute.warehouse.filing_index.fetch_filing_index_rows``, and writes
the results to ``data/warehouse/filing_index/`` partitioned by run date.

Purpose
-------
The filing index is observability-first foundation work (Rule 18): it maps
each ticker → its recent 10-K / 10-Q / 8-K accession numbers and URLs.
This is a WRITE-ONLY research store — the static site never reads
``data/warehouse/`` and there is no scoring use in this slice.

This script exists SEPARATELY from the weekday cron (``compute/main.py``)
intentionally.  Cron wiring is deferred so we can first measure the per-run
EDGAR cost: enumerating ~1500 tickers' filing lists = ~1500 submissions-JSON
round-trips.  This mirrors the pattern of ``scripts/backfill_warehouse.py``
existing independently from Step-13.5 in main.py.

Output layout
-------------
    data/warehouse/filing_index/year=<YYYY>/run_date=<ISO>/part-0.parquet

The partition is overwritten idempotently on re-run.

Opt-out
-------
Set ``QR_SKIP_FILING_INDEX=1`` to be a no-op (exit 0 immediately).
This mirrors ``QR_SKIP_WAREHOUSE`` and ``QR_SKIP_DECAY_MONITOR``.

Network requirements
--------------------
Requires ``EDGAR_USER_AGENT`` env-var (``"Name email@example.com"``).
Without it every per-ticker fetch returns ``[]`` gracefully (warning logged,
no exception) and the run produces zero rows.

Parallelism
-----------
Uses ``concurrent.futures.ThreadPoolExecutor`` with
``config.EDGAR_MAX_WORKERS`` (8 workers) — the same value used by the weekly
compute Step-2 fundamentals fetch.  At ~1 HTTP round-trip per ticker × 8
workers the sustained rate is comfortably under EDGAR's 10 req/s ceiling.

Usage
-----
    python -m scripts.backfill_filing_index \\
        [--universe sp500|sp900|sp1500]   (default: QR_UNIVERSE env or sp500)
        [--run-date YYYY-MM-DD]           (default: today)
        [--out PATH]                      (default: data/warehouse/filing_index/)
        [--all-forms]                     (fetch ALL form types, not just 10-K/10-Q/8-K)
        [--dry-run]                       (enumerate without writing Parquet)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Env-var opt-out key — mirrors QR_SKIP_WAREHOUSE.
_SKIP_ENV_VAR = "QR_SKIP_FILING_INDEX"


# ---------------------------------------------------------------------------
# Universe loading
# ---------------------------------------------------------------------------

def _load_universe(universe: str) -> list[tuple[str, str | None]]:
    """Return [(ticker, cik_or_None), ...] for the requested universe.

    Uses the same universe loaders as ``compute/main.py``.  CIKs are
    included as hints to ``fetch_filing_index_rows`` so it can skip the
    extra Company(ticker).cik resolution round-trip.

    Falls back to an empty list on any failure (graceful degradation).
    """
    try:
        from compute.ingest import universe as _universe_mod

        univ_lower = universe.lower()
        if univ_lower in ("sp500",):
            df = _universe_mod.get_sp500_constituents()
        elif univ_lower in ("sp900",):
            df = _universe_mod.get_sp900_constituents()
        elif univ_lower in ("sp1500",):
            df = _universe_mod.get_sp1500_constituents()
        else:
            logger.warning("backfill_filing_index: unknown universe %r — using sp500", universe)
            df = _universe_mod.get_sp500_constituents()

        pairs: list[tuple[str, str | None]] = []
        for row in df.itertuples(index=False):
            ticker = str(getattr(row, "ticker", "")).strip()
            cik = str(getattr(row, "cik", "") or "").strip() or None
            if ticker:
                pairs.append((ticker, cik))
        logger.info(
            "backfill_filing_index: loaded %d tickers (universe=%s)", len(pairs), universe
        )
        return pairs
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "backfill_filing_index: failed to load universe %r: %s — aborting", universe, exc
        )
        return []


# ---------------------------------------------------------------------------
# Per-ticker worker
# ---------------------------------------------------------------------------

def _fetch_one(
    ticker: str,
    cik: str | None,
    *,
    all_forms: bool,
) -> tuple[str, list[dict]]:
    """Fetch filing rows for a single ticker.  Returns (ticker, rows).

    Wraps the underlying fetch in try/except so a per-ticker failure never
    propagates to the ThreadPoolExecutor and never blocks the overall run.
    """
    from compute.warehouse.filing_index import DEFAULT_FORM_TYPES, fetch_filing_index_rows

    form_types = None if all_forms else DEFAULT_FORM_TYPES
    try:
        rows = fetch_filing_index_rows(ticker, cik=cik, form_types=form_types)
        return ticker, rows
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "backfill_filing_index: fetch failed for %s: %s", ticker, exc
        )
        return ticker, []


# ---------------------------------------------------------------------------
# Main run logic
# ---------------------------------------------------------------------------

def run_filing_index_backfill(
    *,
    universe: str = "sp500",
    run_date: date,
    out_dir: Path,
    all_forms: bool = False,
    dry_run: bool = False,
) -> dict:
    """Enumerate filings for all universe tickers and write the index partition.

    Parameters
    ----------
    universe:
        Universe string: "sp500", "sp900", or "sp1500".
    run_date:
        Logical run date (drives the Parquet partition path).
    out_dir:
        Warehouse root directory (typically ``config.WAREHOUSE_DIR``
        = ``data/warehouse/``).  ``write_filing_index_partition`` appends
        ``filing_index/year=<YYYY>/run_date=<ISO>/part-0.parquet``
        internally — this parameter should be the warehouse root, not
        the filing_index sub-path.
    all_forms:
        When True, fetch ALL SEC form types.  Default is the
        ``DEFAULT_FORM_TYPES = {10-K, 10-Q, 8-K}`` subset.
    dry_run:
        When True, enumerate and log the count but do NOT write Parquet.

    Returns
    -------
    dict
        Summary: ``{n_tickers, n_filings, skipped, wall_clock_seconds}``.
    """
    from compute import config
    from compute.warehouse.writer import write_filing_index_partition

    t0 = time.monotonic()
    pairs = _load_universe(universe)
    if not pairs:
        logger.error("backfill_filing_index: empty universe — aborting")
        return {"n_tickers": 0, "n_filings": 0, "skipped": 0, "wall_clock_seconds": 0.0}

    logger.info(
        "backfill_filing_index: start universe=%s run_date=%s workers=%d all_forms=%s dry_run=%s",
        universe, run_date, config.EDGAR_MAX_WORKERS, all_forms, dry_run,
    )

    all_rows: list[dict] = []
    skipped = 0
    done = 0

    with ThreadPoolExecutor(max_workers=config.EDGAR_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_one, ticker, cik, all_forms=all_forms): ticker
            for ticker, cik in pairs
        }
        for future in as_completed(futures):
            ticker_name = futures[future]
            try:
                ticker_result, rows = future.result()
                if rows:
                    all_rows.extend(rows)
                else:
                    skipped += 1
                    logger.debug(
                        "backfill_filing_index: %s returned 0 rows", ticker_result
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "backfill_filing_index: future failed for %s: %s", ticker_name, exc
                )
                skipped += 1
            done += 1
            if done % 100 == 0:
                logger.info(
                    "backfill_filing_index: progress %d/%d tickers, %d rows so far",
                    done, len(pairs), len(all_rows),
                )

    wall_clock = time.monotonic() - t0
    n_tickers = len(pairs)
    n_filings = len(all_rows)

    if dry_run:
        logger.info(
            "backfill_filing_index: DRY-RUN done — n_tickers=%d n_filings=%d "
            "skipped=%d wall_clock=%.1fs",
            n_tickers, n_filings, skipped, wall_clock,
        )
    else:
        try:
            written = write_filing_index_partition(all_rows, run_date, out_dir)
            logger.info(
                "backfill_filing_index: wrote %d rows → %s",
                written, out_dir,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "backfill_filing_index: write failed: %s — rows collected but not persisted",
                exc, exc_info=True,
            )

    result = {
        "n_tickers": n_tickers,
        "n_filings": n_filings,
        "skipped": skipped,
        "wall_clock_seconds": round(wall_clock, 1),
    }

    # Canary summary — always printed to stdout so CI logs carry it even
    # when the caller discards the return value.
    print(
        f"backfill_filing_index summary: "
        f"n_tickers={n_tickers} n_filings={n_filings} "
        f"skipped={skipped} wall_clock={wall_clock:.1f}s"
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.backfill_filing_index",
        description=(
            "SEC filing pointer index builder (Slice 1). "
            "Enumerates each ticker's recent 10-K / 10-Q / 8-K filings from "
            "SEC EDGAR and writes a Parquet partition to "
            "data/warehouse/filing_index/. "
            "Observability-first (Rule 18): WRITE-ONLY, no scoring use, "
            "no cron wiring in this slice. "
            "Set QR_SKIP_FILING_INDEX=1 to be a no-op."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--universe",
        default=os.environ.get("QR_UNIVERSE", "sp500"),
        choices=["sp500", "sp900", "sp1500"],
        help=(
            "Universe to enumerate (default: $QR_UNIVERSE or sp500). "
            "sp1500 makes ~1500 EDGAR submissions-JSON round-trips — "
            "measure wall-clock on sp500 first."
        ),
    )
    parser.add_argument(
        "--run-date",
        default=date.today().isoformat(),
        help="Logical run date for the partition path (default: today).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Root output directory for the filing-index partitions. "
            "Default: data/warehouse/filing_index/ (under project root)."
        ),
    )
    parser.add_argument(
        "--all-forms",
        action="store_true",
        help=(
            "Fetch ALL SEC form types instead of the default "
            "{10-K, 10-Q, 8-K} subset."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate filings without writing any Parquet file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code 0=ok, 1=error."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Opt-out gate (mirrors QR_SKIP_WAREHOUSE / QR_SKIP_DECAY_MONITOR).
    if os.environ.get(_SKIP_ENV_VAR, "").strip() in ("1", "true", "True"):
        logger.info("backfill_filing_index: %s=1 — skipping (no-op)", _SKIP_ENV_VAR)
        return 0

    args = _parse_args(argv)

    try:
        run_date = date.fromisoformat(args.run_date)
    except ValueError as exc:
        logger.error("Invalid --run-date: %s", exc)
        return 1

    from compute import config

    out_dir: Path
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = config.WAREHOUSE_DIR

    try:
        run_filing_index_backfill(
            universe=args.universe,
            run_date=run_date,
            out_dir=out_dir,
            all_forms=args.all_forms,
            dry_run=args.dry_run,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("backfill_filing_index: FATAL: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
