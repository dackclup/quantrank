"""Warehouse writer for the AI-pick portfolio artifact (Gap 2).

Reads ``frontend/public/data/portfolio/backtest_pit.json`` at warehouse-write
time and persists its content into two Parquet partitions under
``data/warehouse/portfolio/``:

  portfolio/year=<YYYY>/run_date=<ISO>/part-0.parquet
      One row per rebalance × holding with the basket composition.
      Forward-safe: any new fields in the holdings dict flow through the
      ``holding_json`` blob column.

  portfolio_manifest.parquet
      One row per run_date (append-or-update, same idempotence pattern as
      ``_manifest.parquet``).  Carries json-encoded run-level ``meta`` +
      ``nav`` so NOTHING from the artifact is lost.

Partition layout mirrors the snapshot writer for consistency:

    data/warehouse/portfolio/year=<YYYY>/run_date=<ISO>/part-0.parquet
    data/warehouse/portfolio_manifest.parquet

Graceful degradation
--------------------
- If the backtest_pit.json artifact is absent, log a warning and return 0.
- All I/O errors propagate to the caller (main.py Step-13.5 block wraps in
  try/except so they never block the cron).
- This module never raises on missing data — only on I/O / serialisation
  failures that the caller should see.

Schema constants
----------------
PORTFOLIO_PARTITION_COLUMNS  — canonical column list for the holdings Parquet.
PORTFOLIO_MANIFEST_COLUMNS   — canonical column list for the manifest Parquet.

Both sets are exposed for the warehouse_schema_check drift guard.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical column definitions (used by warehouse_schema_check)
# ---------------------------------------------------------------------------

# Holdings partition: one row per (rebalance_date × ticker).
# Scalar fields extracted from each holding dict; ``holding_json`` carries
# the full holding blob for forward safety.
PORTFOLIO_PARTITION_COLUMNS: tuple[str, ...] = (
    "run_date",           # str ISO — the compute run date (partition key)
    "rebalance_date",     # str ISO — the portfolio rebalance date
    "ticker",             # str
    "composite_score",    # float | None
    "sector",             # str | None
    "sigma_90d",          # float | None
    "mos_pct",            # float | None
    "weight_default",     # float | None  (weights_by_count[default_count] for this ticker)
    "adaptive_count",     # int | None    (rebalance-level adaptive_count)
    "holding_json",       # str  (json-encoded full holding dict, forward-safe)
    "rebalance_json",     # str (json-encoded non-holdings rebalance metadata)
)

# Portfolio manifest: one row per run_date.
PORTFOLIO_MANIFEST_COLUMNS: tuple[str, ...] = (
    "run_date",           # str ISO
    "artifact_path",      # str (relative posix path to the source JSON artifact)
    "rebalance_count",    # int | None
    "meta_json",          # str (json-encoded full meta dict)
    "nav_json",           # str (json-encoded full nav dict)
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PARQUET_COMPRESSION = "zstd"


def _json_encode(obj: Any) -> str | None:
    """JSON-encode obj; return None if obj is None."""
    if obj is None:
        return None
    try:
        return json.dumps(obj, default=str)
    except Exception:  # noqa: BLE001
        return json.dumps(str(obj))


def _load_backtest_artifact(artifact_path: Path) -> dict | None:
    """Load and parse backtest_pit.json.  Returns None when absent or unreadable."""
    if not artifact_path.exists():
        logger.warning(
            "portfolio_writer: artifact not found at %s — skipping portfolio write",
            artifact_path,
        )
        return None
    try:
        return json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "portfolio_writer: failed to read %s (%s) — skipping portfolio write",
            artifact_path,
            exc,
        )
        return None


def _build_holding_rows(
    artifact: dict,
    run_date: date,
) -> list[dict[str, Any]]:
    """Build one flat dict per rebalance × holding.

    Scalar fields extracted: ticker, composite_score, sector, sigma_90d,
    mos_pct.  The full holding dict is json-encoded into ``holding_json``
    so new fields flow through automatically.

    ``weight_default`` is populated from ``weights_by_count[default_count]``
    when available — this is the per-ticker weight under the default basket
    size (which equals adaptive_count when the adaptive rule fires, or
    ``meta.default_count`` otherwise).
    """
    rebalances: list[dict] = artifact.get("rebalances", [])
    meta: dict = artifact.get("meta", {})
    default_count: int | None = meta.get("default_count")
    run_date_str = run_date.isoformat()

    rows: list[dict[str, Any]] = []
    for rebalance in rebalances:
        rebalance_date: str = rebalance.get("date", "")
        adaptive_count: int | None = rebalance.get("adaptive_count")

        # Per-ticker weights from the default_count bucket (or adaptive_count).
        # weights_by_count is a dict: str(n) → {ticker: weight}.
        weights_by_count: dict = rebalance.get("weights_by_count", {})
        # Prefer the default_count bucket; fall back to adaptive if defined.
        weight_map: dict[str, float] = {}
        if default_count is not None and str(default_count) in weights_by_count:
            weight_map = weights_by_count[str(default_count)]
        elif adaptive_count is not None and str(adaptive_count) in weights_by_count:
            weight_map = weights_by_count[str(adaptive_count)]

        # Build the non-holdings portion of the rebalance for the json blob.
        rebalance_meta: dict = {
            k: v for k, v in rebalance.items() if k != "holdings"
        }

        holdings: list[dict] = rebalance.get("holdings", [])
        for holding in holdings:
            ticker: str | None = holding.get("ticker")
            row: dict[str, Any] = {
                "run_date": run_date_str,
                "rebalance_date": rebalance_date,
                "ticker": ticker,
                "composite_score": holding.get("composite_score"),
                "sector": holding.get("sector"),
                "sigma_90d": holding.get("sigma_90d"),
                "mos_pct": holding.get("mos_pct"),
                "weight_default": weight_map.get(ticker) if ticker else None,
                "adaptive_count": adaptive_count,
                "holding_json": _json_encode(holding),
                "rebalance_json": _json_encode(rebalance_meta),
            }
            rows.append(row)

    return rows


def _write_portfolio_partition(
    rows: list[dict[str, Any]],
    run_date: date,
    portfolio_dir: Path,
) -> None:
    """Write the holdings Parquet partition (overwrite-idempotent)."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    year_str = str(run_date.year)
    iso_str = run_date.isoformat()
    partition_dir = portfolio_dir / f"year={year_str}" / f"run_date={iso_str}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    part_path = partition_dir / "part-0.parquet"

    # Stable column ordering: canonical first, then any unexpected extras sorted.
    known_extra = sorted(
        {k for row in rows for k in row} - set(PORTFOLIO_PARTITION_COLUMNS)
    )
    sorted_cols = list(PORTFOLIO_PARTITION_COLUMNS) + known_extra

    # Normalise: every row gets every column.
    for row in rows:
        for col in sorted_cols:
            row.setdefault(col, None)

    df = pd.DataFrame(rows, columns=sorted_cols)

    # Schema: json columns → large_string; numeric → float64; rest → large_string.
    pa_fields: list[pa.Field] = []
    for col in sorted_cols:
        if col.endswith("_json") or col in ("run_date", "rebalance_date", "ticker", "sector"):
            pa_type = pa.large_string()
        elif col == "adaptive_count":
            pa_type = pa.float64()  # int|None — use float64 for nullable safety
        else:
            pa_type = pa.float64()
        pa_fields.append(pa.field(col, pa_type))

    pa_schema = pa.schema(pa_fields)
    table = pa.Table.from_pandas(df, schema=pa_schema, preserve_index=False)

    tmp_path = part_path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path, compression=_PARQUET_COMPRESSION)
    os.replace(tmp_path, part_path)

    logger.info(
        "warehouse portfolio: wrote %d holding rows → %s (%.1f KB)",
        len(rows),
        part_path,
        part_path.stat().st_size / 1024,
    )


def _update_portfolio_manifest(
    artifact: dict,
    artifact_path: Path,
    run_date: date,
    rebalance_count: int,
    portfolio_dir: Path,
) -> None:
    """Append or update the portfolio manifest row for run_date."""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    manifest_path = portfolio_dir.parent / "portfolio_manifest.parquet"
    iso_str = run_date.isoformat()

    new_row: dict[str, Any] = {
        "run_date": iso_str,
        "artifact_path": artifact_path.as_posix(),
        "rebalance_count": rebalance_count,
        "meta_json": _json_encode(artifact.get("meta")),
        "nav_json": _json_encode(artifact.get("nav")),
    }

    if manifest_path.exists():
        try:
            existing_df = pd.read_parquet(manifest_path)
            existing_df = existing_df[existing_df["run_date"] != iso_str]
            new_df = pd.concat([existing_df, pd.DataFrame([new_row])], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "portfolio manifest read failed (%s); rebuilding from scratch",
                exc,
            )
            new_df = pd.DataFrame([new_row])
    else:
        new_df = pd.DataFrame([new_row])

    manifest_cols = sorted(new_df.columns.tolist())
    new_df = new_df[manifest_cols]

    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    pa_fields: list[pa.Field] = []
    for col in manifest_cols:
        if col.endswith("_json") or col in ("run_date", "artifact_path"):
            pa_type = pa.large_string()
        else:
            pa_type = pa.float64()
        pa_fields.append(pa.field(col, pa_type))

    pa_schema = pa.schema(pa_fields)
    table = pa.Table.from_pandas(new_df, schema=pa_schema, preserve_index=False)
    pq.write_table(table, manifest_path, compression=_PARQUET_COMPRESSION)
    logger.info(
        "warehouse portfolio manifest updated → %s (%d runs)",
        manifest_path,
        len(new_df),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_portfolio_snapshot(
    run_date: date,
    warehouse_dir: Path,
    artifact_path: Path | None = None,
) -> int:
    """Write the AI-pick portfolio artifact to the warehouse.

    Parameters
    ----------
    run_date:
        Logical date of the compute run.  Drives the partition path and the
        portfolio manifest key.
    warehouse_dir:
        Root of the warehouse on disk (``config.WAREHOUSE_DIR``).
    artifact_path:
        Path to ``backtest_pit.json``.  When ``None``, defaults to
        ``<warehouse_dir>.parent / frontend/public/data/portfolio/backtest_pit.json``
        (i.e. ``PROJECT_ROOT/frontend/public/data/portfolio/backtest_pit.json``).

    Returns
    -------
    int
        Number of holding rows written.  0 when the artifact is absent or
        when the backtest has no rebalances.

    Raises
    ------
    Any I/O / serialisation exception propagates to the caller (``main.py``
    Step 13.5 try/except).  Missing artifact is NOT an exception — it is
    a graceful no-op (returns 0).
    """
    if artifact_path is None:
        # Resolve relative to PROJECT_ROOT: warehouse_dir is data/warehouse/
        # so PROJECT_ROOT = warehouse_dir.parent.parent
        project_root = warehouse_dir.parent.parent
        artifact_path = (
            project_root / "frontend" / "public" / "data" / "portfolio" / "backtest_pit.json"
        )

    artifact = _load_backtest_artifact(artifact_path)
    if artifact is None:
        return 0

    rebalances: list[dict] = artifact.get("rebalances", [])
    if not rebalances:
        logger.info("portfolio_writer: no rebalances in artifact — nothing to write")
        return 0

    rows = _build_holding_rows(artifact, run_date)
    if not rows:
        logger.info("portfolio_writer: no holding rows derived from artifact")
        return 0

    portfolio_dir = warehouse_dir / "portfolio"
    _write_portfolio_partition(rows, run_date, portfolio_dir)
    _update_portfolio_manifest(
        artifact=artifact,
        artifact_path=artifact_path,
        run_date=run_date,
        rebalance_count=len(rebalances),
        portfolio_dir=portfolio_dir,
    )

    return len(rows)
