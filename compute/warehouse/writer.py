"""Write a per-run point-in-time Parquet snapshot to the research warehouse.

This module is the ONLY Parquet-aware module in the warehouse package.
All callers go through ``write_run_snapshot``; nothing else imports pyarrow
or pandas directly for warehouse I/O.

Partition layout
----------------
    <warehouse_dir>/snapshots/year=<YYYY>/run_date=<ISO>/part-0.parquet
    <warehouse_dir>/_manifest.parquet

The snapshot partition is overwritten if it already exists (idempotent
re-run).  The manifest is an append-or-update single-row keyed by
``run_date``.

Stable column ordering
----------------------
All ``dict`` keys are sorted before building the DataFrame so the
Parquet schema is deterministic across runs and Python versions.

Graceful degradation
--------------------
This module never raises.  All write errors are returned as a raised
exception from within the function — callers wrap in try/except at the
``main.py`` call site.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compute.output.schemas import Metadata, StockDetail, StockSummary

from compute.warehouse.flatten import flatten_stock

logger = logging.getLogger(__name__)

# Parquet compression codec.  zstd gives the best size/speed ratio for
# our row-count (~900 rows per snapshot is tiny; metadata columns dominate).
_PARQUET_COMPRESSION = "zstd"


def _build_summary_index(summaries: list[StockSummary]) -> dict[str, StockSummary]:
    """Return a ticker → StockSummary lookup dict."""
    return {s.ticker: s for s in summaries}


def write_run_snapshot(
    details: list[StockDetail],
    summaries: list[StockSummary],
    meta: Metadata,
    run_date: date,
    warehouse_dir: Path,
) -> int:
    """Write one run's flat rows to the partitioned Parquet warehouse.

    Parameters
    ----------
    details:
        All per-stock StockDetail objects produced by the Step-8 loop.
    summaries:
        All StockSummary objects from the ranked list (used to enrich
        each detail row with summary-only fields).
    meta:
        The Metadata object for this run.  Used to populate the
        ``_manifest.parquet`` run-level row.
    run_date:
        The logical date of this compute run (typically ``date.today()``
        at cron start).  Drives the partition path and the manifest key.
    warehouse_dir:
        Root of the warehouse on disk.  Typically ``config.WAREHOUSE_DIR``
        (``data/warehouse/``).  Created if absent.

    Returns
    -------
    int
        Number of stock rows written (= ``len(details)``).

    Raises
    ------
    Any exception raised by pyarrow / pandas / filesystem propagates to
    the caller (``main.py`` Step 13.5) which wraps in try/except.
    """
    import pandas as pd  # deferred — not a hard import at module level
    import pyarrow as pa
    import pyarrow.parquet as pq

    summary_index = _build_summary_index(summaries)

    # --- 1. Build flat rows ---
    rows: list[dict] = []
    for detail in details:
        summary = summary_index.get(detail.ticker)
        row = flatten_stock(detail, summary)
        rows.append(row)

    if not rows:
        logger.warning("write_run_snapshot: no rows — skipping write")
        return 0

    # --- 2. Stable column ordering ---
    # All keys from row 0; additional keys from later rows are folded in
    # (shouldn't happen in practice since flatten_stock is deterministic,
    # but defensive against future partial fields).
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    sorted_cols = sorted(all_keys)

    # Normalise rows so every row has every key (None for missing).
    for row in rows:
        for col in sorted_cols:
            row.setdefault(col, None)

    # --- 3. Build DataFrame + PyArrow Table ---
    df = pd.DataFrame(rows, columns=sorted_cols)
    table = pa.Table.from_pandas(df, preserve_index=False)

    # --- 4. Write snapshot partition (overwrite if exists) ---
    year_str = str(run_date.year)
    iso_str = run_date.isoformat()
    partition_dir = warehouse_dir / "snapshots" / f"year={year_str}" / f"run_date={iso_str}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    part_path = partition_dir / "part-0.parquet"
    pq.write_table(
        table,
        part_path,
        compression=_PARQUET_COMPRESSION,
    )
    logger.info(
        "warehouse: wrote %d rows → %s (%.1f KB)",
        len(rows),
        part_path,
        part_path.stat().st_size / 1024,
    )

    # --- 5. Append/update manifest ---
    _update_manifest(warehouse_dir, run_date, meta, len(rows), part_path)

    return len(rows)


def _update_manifest(
    warehouse_dir: Path,
    run_date: date,
    meta: Metadata,
    row_count: int,
    part_path: Path,
) -> None:
    """Append or update the manifest row for ``run_date``.

    The manifest is a single flat Parquet file at
    ``<warehouse_dir>/_manifest.parquet`` with one row per run_date.
    On re-run the existing row is replaced (idempotent).

    Manifest columns (stable set):
        run_date: str (ISO)
        schema_version: str
        universe: str
        row_count: int
        part_path: str  (relative to warehouse_dir, POSIX)
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    manifest_path = warehouse_dir / "_manifest.parquet"
    iso_str = run_date.isoformat()

    new_row = {
        "run_date": iso_str,
        "schema_version": meta.version,
        "universe": meta.universe,
        "row_count": row_count,
        "part_path": part_path.relative_to(warehouse_dir).as_posix(),
    }

    if manifest_path.exists():
        try:
            existing_df = pd.read_parquet(manifest_path)
            # Drop any existing row for this run_date (idempotent).
            existing_df = existing_df[existing_df["run_date"] != iso_str]
            new_df = pd.concat(
                [existing_df, pd.DataFrame([new_row])],
                ignore_index=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "warehouse manifest read failed (%s); rebuilding from scratch",
                exc,
            )
            new_df = pd.DataFrame([new_row])
    else:
        new_df = pd.DataFrame([new_row])

    # Stable column ordering for the manifest too.
    manifest_cols = sorted(new_df.columns.tolist())
    new_df = new_df[manifest_cols]

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(new_df, preserve_index=False)
    pq.write_table(table, manifest_path, compression=_PARQUET_COMPRESSION)
    logger.info("warehouse: manifest updated → %s (%d runs)", manifest_path, len(new_df))
