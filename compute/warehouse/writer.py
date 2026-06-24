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
    import pandas as pd
    import pyarrow as pa

    from compute.output.schemas import Metadata, StockDetail, StockSummary

from compute.warehouse.filing_index import FILING_INDEX_COLUMNS
from compute.warehouse.flatten import flatten_stock

logger = logging.getLogger(__name__)

# Parquet compression codec.  zstd gives the best size/speed ratio for
# our row-count (~900 rows per snapshot is tiny; metadata columns dominate).
_PARQUET_COMPRESSION = "zstd"

# Nullable-bool fields typed by NAME rather than value inspection.
# These are ``bool | None`` Pydantic fields on StockDetail that flatten_stock
# emits into the row dict.  When all rows in a snapshot have None for such a
# field (e.g. pays_dividend on a universe with no dividend data yet), the
# value-inspection branch in build_locked_schema would infer float64 instead
# of bool — corrupting the schema the moment the first non-None value lands.
# Listing them by name avoids that flip.  Add any future ``bool | None``
# StockDetail fields here when they are added to schemas.py.
_NULLABLE_BOOL_COLUMNS_BY_NAME: frozenset[str] = frozenset(
    {
        "pays_dividend",
    }
)


def build_locked_schema(df: pd.DataFrame) -> pa.Schema:
    """Build a stable PyArrow schema for a warehouse snapshot / backfill DataFrame.

    Resolves a pyarrow type for every column in ``df``, producing a Schema
    that can be passed to ``pa.Table.from_pandas(..., schema=schema)`` so
    that the resulting Parquet file has deterministic dtypes across runs,
    even when some columns are entirely null in a given snapshot.

    Type-resolution priority (per column):
      1. ``flag_*`` / ``warn_*`` → ``bool`` (always non-null in live rows;
         nullable in pit_replay rows where forward-only flags are None).
      2. ``*_json`` → ``large_string`` (nullable str).
      3. Column name is in ``_NULLABLE_BOOL_COLUMNS_BY_NAME`` → ``bool``
         (covers ``bool | None`` fields like ``pays_dividend`` where
         value-inspection fails when all rows are null).
      4. pandas bool dtype → ``bool``.
      5. object dtype with ≥ 1 non-null value, all Python bools → ``bool``.
      6. integer or float dtype → ``float64``.
      7. object dtype, all-null → ``float64`` (unknown numeric; cast to
         DOUBLE so the schema is stable if real values land later).
      8. everything else → ``large_string`` (str / mixed catch-all).

    Parameters
    ----------
    df:
        The snapshot DataFrame.  Its columns must already be in the desired
        stable order before calling this function.

    Returns
    -------
    pa.Schema
        A fully typed pyarrow schema with one field per column of ``df``.
    """
    import pandas as pd
    import pyarrow as pa

    pa_fields: list[pa.Field] = []
    for col in df.columns:
        s = df[col]
        if col.startswith("flag_") or col.startswith("warn_"):
            pa_type = pa.bool_()
        elif col.endswith("_json"):
            pa_type = pa.large_string()
        elif col in _NULLABLE_BOOL_COLUMNS_BY_NAME:
            pa_type = pa.bool_()
        elif pd.api.types.is_bool_dtype(s):
            pa_type = pa.bool_()
        elif s.dtype == object:
            non_null = s.dropna()
            if len(non_null) > 0 and all(isinstance(v, bool) for v in non_null):
                pa_type = pa.bool_()
            elif s.isna().all():
                pa_type = pa.float64()
            else:
                pa_type = pa.large_string()
        elif pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s):
            pa_type = pa.float64()
        else:
            pa_type = pa.large_string()
        pa_fields.append(pa.field(col, pa_type))

    return pa.schema(pa_fields)


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

    # Cast all-null (or mixed-numeric) columns to float64 so that columns
    # which happen to be all-null in this snapshot (e.g. pillar_sentiment,
    # pillar_ml, fp_dcf when the relevant Phase is not yet wired) are written
    # as DOUBLE rather than INTEGER.  Without this, pandas infers int64 for
    # all-null columns and the parquet schema flips to DOUBLE once real values
    # land — breaking any typed consumer that read the first snapshot.
    #
    # ``build_locked_schema`` is the single source of truth for parquet column
    # dtypes — it is also called by the backfill writer so both paths share
    # the same dtype discipline.
    pa_schema = build_locked_schema(df)
    table = pa.Table.from_pandas(df, schema=pa_schema, preserve_index=False)

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

    Manifest columns (stable set — backward-compat; new columns are additive):
        run_date: str (ISO)
        schema_version: str
        universe: str
        row_count: int
        part_path: str  (relative to warehouse_dir, POSIX)
        metadata_json: str  (json-encoded full Metadata model — Gap 1)
            Forward-safe: new Metadata fields flow through automatically
            without needing a column-list edit on each schema bump.
            Added additively so readers of old manifests can simply
            expect the column to be absent and degrade to None.
    """
    import json

    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    manifest_path = warehouse_dir / "_manifest.parquet"
    iso_str = run_date.isoformat()

    # json-encode the full Metadata for forward-safe run-level capture (Gap 1).
    try:
        metadata_json_str: str | None = json.dumps(meta.model_dump(mode="json"))
    except Exception as _enc_exc:  # noqa: BLE001
        logger.warning(
            "warehouse manifest: metadata serialisation failed (%s); "
            "metadata_json will be null for this run",
            _enc_exc,
        )
        metadata_json_str = None

    new_row = {
        "run_date": iso_str,
        "schema_version": meta.version,
        "universe": meta.universe,
        "row_count": row_count,
        "part_path": part_path.relative_to(warehouse_dir).as_posix(),
        "metadata_json": metadata_json_str,
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


# ---------------------------------------------------------------------------
# Filing index writer
# ---------------------------------------------------------------------------

def write_filing_index_partition(
    rows: list[dict],
    run_date: date,
    warehouse_dir: Path,
) -> int:
    """Write one run_date's filing-index rows to the Hive-partitioned store.

    Partition layout mirrors the snapshot writer::

        <warehouse_dir>/filing_index/year=<YYYY>/run_date=<ISO>/part-0.parquet

    Write is atomic: rows are written to a ``.tmp`` file then ``os.replace``d
    into the final path so a partial write never leaves a corrupt partition.
    The partition is overwritten idempotently on re-run.

    Parameters
    ----------
    rows:
        List of row dicts from ``filing_index.fetch_filing_index_rows``.
        Each dict must contain the keys declared in
        ``filing_index.FILING_INDEX_COLUMNS``.  Extra keys are silently
        carried through; missing keys are filled with ``None``.
    run_date:
        Logical run date.  Drives the partition path.
    warehouse_dir:
        Root of the warehouse on disk (typically ``config.WAREHOUSE_DIR``).
        Created if absent.

    Returns
    -------
    int
        Number of rows written.  0 when ``rows`` is empty (no file written).

    Raises
    ------
    Any exception from pyarrow / pandas / filesystem propagates to the caller
    (``scripts/backfill_filing_index.py`` wraps each ticker in try/except).
    """
    import os as _os

    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not rows:
        logger.warning("write_filing_index_partition: no rows for %s — skipping", run_date)
        return 0

    # Stable column ordering: FILING_INDEX_COLUMNS first (canonical), then
    # any extra columns in sorted order so the schema is deterministic.
    known_extra = sorted(
        {k for row in rows for k in row} - set(FILING_INDEX_COLUMNS)
    )
    sorted_cols = list(FILING_INDEX_COLUMNS) + known_extra

    # Normalise rows so every row has every column (None for absent keys).
    for row in rows:
        for col in sorted_cols:
            row.setdefault(col, None)

    df = pd.DataFrame(rows, columns=sorted_cols)

    # Filing-index schema: all columns are string | None (filing metadata is
    # uniformly text).  PyArrow large_string is forward-safe for long URLs.
    pa_fields = [pa.field(col, pa.large_string()) for col in sorted_cols]
    pa_schema = pa.schema(pa_fields)
    table = pa.Table.from_pandas(df, schema=pa_schema, preserve_index=False)

    year_str = str(run_date.year)
    iso_str = run_date.isoformat()
    partition_dir = (
        warehouse_dir / "filing_index" / f"year={year_str}" / f"run_date={iso_str}"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    part_path = partition_dir / "part-0.parquet"
    tmp_path = part_path.with_suffix(".parquet.tmp")

    pq.write_table(table, tmp_path, compression=_PARQUET_COMPRESSION)
    _os.replace(tmp_path, part_path)

    logger.info(
        "warehouse filing_index: wrote %d rows → %s (%.1f KB)",
        len(rows),
        part_path,
        part_path.stat().st_size / 1024,
    )
    return len(rows)
