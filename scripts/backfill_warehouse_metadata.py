"""Warehouse metadata history backfill — Task 1.

Enumerates the git history of ``frontend/public/data/metadata.json`` and
materialises one row per historical cron-run into a committed, partitioned
store:

    data/warehouse/run_metadata/year=<YYYY>/run_date=<ISO>/part-0.parquet

Each row carries the full ``metadata_json`` blob (raw JSON verbatim) so all
historical fields survive, even those that don't exist in the current
``Metadata`` Pydantic model.  The store is forward-safe: future fields from
new cron runs flow through the blob column automatically.

Why a separate store from ``_manifest.parquet``
-----------------------------------------------
The snapshot ``_manifest.parquet`` is keyed by (run_date, snapshot-partition)
pairs.  Historical cron runs have no committed snapshot partition — they only
changed ``metadata.json``, not the full per-ticker Parquet snapshot.  Polluting
the manifest with phantom snapshot rows would corrupt the ``part_path`` pointer
and mislead any downstream reader.  The ``run_metadata/`` store is purely a
metadata-history panel — no snapshot pointer, no ``row_count`` fiction.

Partition layout
----------------
    data/warehouse/run_metadata/year=<YYYY>/run_date=<ISO>/part-0.parquet

Columns (minimum guaranteed set):
    run_date        str  ISO date derived from ``last_update_utc`` in the JSON,
                         falling back to the git committer date if absent.
    schema_version  str  ``meta.version`` (``None`` for blobs missing the field).
    universe        str  ``meta.universe`` (``None`` for blobs missing the field).
    source_commit   str  The 40-char git SHA.
    row_provenance  str  Always ``"metadata_backfill"``.
    metadata_json   str  Full JSON verbatim.

Idempotent: dedup by run_date — re-running the script replaces any existing
row for a given run_date rather than appending a duplicate.

Graceful: a malformed or absent ``metadata.json`` at any commit → warning + skip
that commit; the script always attempts the remaining commits.

Usage
-----
    python -m scripts.backfill_warehouse_metadata [--warehouse-dir PATH]

Requirements
------------
- Must be run from inside the git repository root (uses ``git log`` + ``git show``).
- Reads only the git object database — no network calls, no warm cache needed.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to the metadata file in the git tree (relative to repo root).
_METADATA_GIT_PATH: str = "frontend/public/data/metadata.json"

# Column definitions for the run_metadata partition.
RUN_METADATA_COLUMNS: tuple[str, ...] = (
    "run_date",        # str ISO
    "schema_version",  # str | None
    "universe",        # str | None
    "source_commit",   # str (40-char git SHA)
    "row_provenance",  # str — always "metadata_backfill"
    "metadata_json",   # str (raw verbatim JSON blob)
)

_PARQUET_COMPRESSION = "zstd"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_log_commits(metadata_path: str) -> list[dict[str, str]]:
    """Return [{sha, committer_date_iso}, ...] for all commits touching the file.

    Ordered newest-first (same as ``git log``).
    ``committer_date_iso`` is in ``YYYY-MM-DD`` format (UTC wall-clock date).
    """
    result = subprocess.run(
        [
            "git", "log",
            "--format=%H %cd",
            "--date=format:%Y-%m-%d",
            "--follow",
            "--",
            metadata_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    commits: list[dict[str, str]] = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2:
            logger.warning("backfill_warehouse_metadata: unexpected git log line: %r", line)
            continue
        sha, committer_date = parts
        commits.append({"sha": sha, "committer_date": committer_date})
    return commits


def _git_show_file(sha: str, file_path: str) -> str | None:
    """Read the content of ``file_path`` at commit ``sha``.

    Returns ``None`` when the file doesn't exist in that commit or the
    subprocess fails.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{sha}:{file_path}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "backfill_warehouse_metadata: git show %s:%s failed (%s)",
            sha, file_path, exc,
        )
        return None
    except subprocess.TimeoutExpired:
        logger.warning(
            "backfill_warehouse_metadata: git show %s:%s timed out",
            sha, file_path,
        )
        return None


# ---------------------------------------------------------------------------
# run_date derivation
# ---------------------------------------------------------------------------

def _derive_run_date(meta_dict: dict, committer_date_iso: str) -> str:
    """Derive the logical run_date for a historical metadata snapshot.

    Preference order:
    1. ``last_update_utc`` in the metadata JSON (ISO datetime string; extract
       the date part ``YYYY-MM-DD``).  This is the most accurate — it reflects
       the actual compute-run time, not the git commit time.
    2. ``committer_date_iso`` (the git commit date) — fallback when
       ``last_update_utc`` is absent or malformed.
    """
    last_update = meta_dict.get("last_update_utc")
    if last_update and isinstance(last_update, str):
        # Strip time component: "2026-06-24T22:00:00Z" → "2026-06-24"
        date_part = last_update[:10]
        try:
            date.fromisoformat(date_part)  # validates format
            return date_part
        except ValueError:
            logger.debug(
                "backfill_warehouse_metadata: malformed last_update_utc %r; "
                "falling back to committer_date",
                last_update,
            )
    return committer_date_iso


# ---------------------------------------------------------------------------
# Parquet writers
# ---------------------------------------------------------------------------

def _write_run_metadata_partition(
    rows: list[dict],
    run_date_str: str,
    run_metadata_dir: Path,
) -> None:
    """Write (overwrite-idempotent) the partition for one historical run_date."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    year_str = run_date_str[:4]
    partition_dir = run_metadata_dir / f"year={year_str}" / f"run_date={run_date_str}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    part_path = partition_dir / "part-0.parquet"
    tmp_path = part_path.with_suffix(".parquet.tmp")

    # Stable column ordering: canonical first, then any extra sorted.
    known_extra = sorted(
        {k for row in rows for k in row} - set(RUN_METADATA_COLUMNS)
    )
    sorted_cols = list(RUN_METADATA_COLUMNS) + known_extra

    for row in rows:
        for col in sorted_cols:
            row.setdefault(col, None)

    df = pd.DataFrame(rows, columns=sorted_cols)

    # All run_metadata columns are string or None.
    pa_fields = [pa.field(col, pa.large_string()) for col in sorted_cols]
    pa_schema = pa.schema(pa_fields)
    table = pa.Table.from_pandas(df, schema=pa_schema, preserve_index=False)

    pq.write_table(table, tmp_path, compression=_PARQUET_COMPRESSION)
    os.replace(tmp_path, part_path)

    logger.info(
        "run_metadata: wrote %d row(s) → %s (%.1f KB)",
        len(rows),
        part_path,
        part_path.stat().st_size / 1024,
    )


# ---------------------------------------------------------------------------
# Dedup helper: read existing run_dates from already-written partitions
# ---------------------------------------------------------------------------

def _existing_run_dates(run_metadata_dir: Path) -> set[str]:
    """Return ISO run_date strings for partitions already on disk."""
    existing: set[str] = set()
    if not run_metadata_dir.exists():
        return existing
    for part_path in run_metadata_dir.rglob("part-0.parquet"):
        # Partition path: run_metadata/year=YYYY/run_date=ISO/part-0.parquet
        run_date_dir = part_path.parent.name  # e.g. "run_date=2026-06-24"
        if run_date_dir.startswith("run_date="):
            existing.add(run_date_dir[len("run_date="):])
    return existing


# ---------------------------------------------------------------------------
# Core backfill
# ---------------------------------------------------------------------------

def run_backfill_metadata(
    *,
    warehouse_dir: Path,
    force: bool = False,
) -> dict:
    """Enumerate git history of metadata.json and write run_metadata partitions.

    Parameters
    ----------
    warehouse_dir:
        Root of the warehouse on disk (``config.WAREHOUSE_DIR``).
    force:
        When ``True``, overwrite existing partitions even if the run_date is
        already present.  Default ``False`` (idempotent skip).

    Returns
    -------
    dict
        Summary: ``{"commits_found": N, "written": M, "skipped": K, "errors": E}``.
    """
    run_metadata_dir = warehouse_dir / "run_metadata"
    run_metadata_dir.mkdir(parents=True, exist_ok=True)

    # Discover commits touching metadata.json.
    try:
        commits = _git_log_commits(_METADATA_GIT_PATH)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "backfill_warehouse_metadata: git log failed — run from the repo root: %s", exc
        )
        return {"commits_found": 0, "written": 0, "skipped": 0, "errors": 1}

    if not commits:
        logger.info(
            "backfill_warehouse_metadata: no commits found for %s — nothing to backfill",
            _METADATA_GIT_PATH,
        )
        return {"commits_found": 0, "written": 0, "skipped": 0, "errors": 0}

    logger.info(
        "backfill_warehouse_metadata: found %d commits for %s",
        len(commits), _METADATA_GIT_PATH,
    )

    # Pre-compute which run_dates are already on disk (for idempotent dedup).
    existing_run_dates: set[str] = set() if force else _existing_run_dates(run_metadata_dir)

    written = 0
    skipped = 0
    errors = 0

    # Track run_dates seen THIS run to handle multiple commits with the same
    # derived run_date (e.g. two cron runs on the same calendar day).
    # The newer commit (listed first by git log) wins; its run_date is already
    # in `seen_this_run` so later commits for the same day are skipped.
    # For idempotent re-runs the `existing_run_dates` check also covers this.
    seen_this_run: dict[str, str] = {}  # run_date → sha (first = newest)

    for commit in commits:
        sha = commit["sha"]
        committer_date = commit["committer_date"]

        # Fetch the file content at this commit.
        raw_json = _git_show_file(sha, _METADATA_GIT_PATH)
        if raw_json is None:
            logger.warning(
                "backfill_warehouse_metadata: could not read %s at %s — skipping",
                _METADATA_GIT_PATH, sha[:12],
            )
            errors += 1
            continue

        # Parse JSON.
        try:
            meta_dict = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.warning(
                "backfill_warehouse_metadata: malformed JSON at %s (%s) — skipping",
                sha[:12], exc,
            )
            errors += 1
            continue

        if not isinstance(meta_dict, dict):
            logger.warning(
                "backfill_warehouse_metadata: unexpected top-level type %s at %s — skipping",
                type(meta_dict).__name__, sha[:12],
            )
            errors += 1
            continue

        # Derive logical run_date.
        run_date_str = _derive_run_date(meta_dict, committer_date)

        # Dedup across commits processed in this run (newest-first, so first seen wins).
        if run_date_str in seen_this_run:
            logger.info(
                "backfill_warehouse_metadata: run_date %s already captured from sha %s "
                "(current sha %s is older — skipping)",
                run_date_str, seen_this_run[run_date_str][:12], sha[:12],
            )
            skipped += 1
            continue
        seen_this_run[run_date_str] = sha

        # Idempotent skip if already written (and not force).
        if run_date_str in existing_run_dates:
            logger.info(
                "backfill_warehouse_metadata: partition for %s already exists — skipping "
                "(sha=%s, use --force to overwrite)",
                run_date_str, sha[:12],
            )
            skipped += 1
            continue

        # Build the row.
        row: dict = {
            "run_date": run_date_str,
            "schema_version": meta_dict.get("version") or None,
            "universe": meta_dict.get("universe") or None,
            "source_commit": sha,
            "row_provenance": "metadata_backfill",
            "metadata_json": raw_json.strip(),  # verbatim, stripped of trailing newline
        }

        # Write partition (one row per run_date).
        try:
            _write_run_metadata_partition([row], run_date_str, run_metadata_dir)
            existing_run_dates.add(run_date_str)
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "backfill_warehouse_metadata: partition write failed for %s: %s — skipping",
                run_date_str, exc,
            )
            errors += 1

    result = {
        "commits_found": len(commits),
        "written": written,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("backfill_warehouse_metadata: DONE — %s", result)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0=ok, 1=error."""
    import argparse

    from compute import config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="python -m scripts.backfill_warehouse_metadata",
        description=(
            "Warehouse metadata history backfill (Task 1). "
            "Enumerates git history of frontend/public/data/metadata.json, "
            "extracts one row per historical cron-run, and writes committed "
            "Parquet partitions to data/warehouse/run_metadata/. "
            "Idempotent: existing run_date partitions are skipped unless --force. "
            "Graceful: malformed/absent metadata at any commit is skipped with a warning."
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
        "--force",
        action="store_true",
        help=(
            "Overwrite existing run_date partitions. "
            "Default: skip partitions that already exist on disk."
        ),
    )
    args = parser.parse_args(argv)

    warehouse_dir: Path = (
        Path(args.warehouse_dir) if args.warehouse_dir else config.WAREHOUSE_DIR
    )

    try:
        result = run_backfill_metadata(warehouse_dir=warehouse_dir, force=args.force)
    except Exception as exc:  # noqa: BLE001
        logger.error("backfill_warehouse_metadata: FATAL: %s", exc, exc_info=True)
        return 1

    print(
        f"backfill_warehouse_metadata: commits_found={result['commits_found']} "
        f"written={result['written']} "
        f"skipped={result['skipped']} "
        f"errors={result['errors']}"
    )

    # Return 1 only on fatal / partial errors that produced zero output.
    if result["errors"] > 0 and result["written"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
