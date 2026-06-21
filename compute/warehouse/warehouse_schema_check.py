"""Warehouse flat-column drift guard.

Derives the canonical flat-column list + dtypes from the Pydantic models
(via ``flatten_stock``) and compares against the committed JSON snapshot at
``data/warehouse/warehouse_schema.json``.

On drift: exits 1 and prints the diff so CI immediately surfaces a column
added/removed/renamed without an explicit snapshot update.

CLI usage
---------
    # Verify in-sync (CI gate):
    python -m compute.warehouse.warehouse_schema_check
      → exit 0 if in-sync, 1 if drift, 2 on unexpected error

    # Regenerate after intentional schema change:
    python -m compute.warehouse.warehouse_schema_check --update
      → writes ``data/warehouse/warehouse_schema.json`` and exits 0

Design notes
------------
- The canonical column set is derived by calling ``flatten_stock`` on a
  **synthetic StockDetail + StockSummary** so no live SEC data is needed.
- Dtypes are inferred as Python-type strings (``"str"``, ``"int"``,
  ``"float"``, ``"bool"``, ``"NoneType"``).  For columns that can hold
  multiple types (e.g. ``float | None``) we record ``"float | None"`` so
  callers know the column is nullable.
- The snapshot JSON is a stable, sorted ``{"columns": {name: dtype}}``
  dict.  Column ORDER in the JSON is alphabetical so diffs are minimal.
- ``flag_*`` and ``warn_*`` bool columns are validated against the
  ``KNOWN_RISK_FLAGS`` + ``KNOWN_VALUATION_WARNINGS`` registries so a new
  flag that lands in the pipeline but isn't registered here fails fast.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from compute import config
from compute.output.schemas import (
    DataQuality,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)
from compute.warehouse.flag_registry import (
    KNOWN_RISK_FLAGS,
    KNOWN_VALUATION_WARNINGS,
)
from compute.warehouse.flatten import flatten_stock

SNAPSHOT_PATH: Path = config.PROJECT_ROOT / "data" / "warehouse" / "warehouse_schema.json"


# ---------------------------------------------------------------------------
# Synthetic model builders
# ---------------------------------------------------------------------------

def _make_synthetic_detail() -> StockDetail:
    """Return a minimal but structurally valid StockDetail for schema derivation."""

    ps = PillarScores(
        **{f: 50.0 for f in PillarScores.model_fields}
    )
    rm = RawMetrics(
        **{f: None for f in RawMetrics.model_fields}
    )
    # missing_metrics and imputed_metrics require list[str], not None.
    dq_kwargs: dict[str, Any] = {
        f: None for f in DataQuality.model_fields
    }
    dq_kwargs["missing_metrics"] = []
    dq_kwargs["imputed_metrics"] = []
    dq = DataQuality(**dq_kwargs)

    # Build StockDetail with all optional/nullable fields set to None or
    # sensible defaults so flatten_stock produces every possible column.
    # We deliberately set scalar fields to None and list fields to [] so that
    # the flatten output covers every possible column name (including *_json).
    scalar_fields: dict[str, Any] = {}
    for field_name, field_info in StockDetail.model_fields.items():
        if field_name in {"pillar_scores", "raw_metrics", "data_quality"}:
            continue
        # Detect list-typed fields by checking the annotation.
        ann = field_info.annotation
        ann_str = str(ann)
        if "list" in ann_str.lower():
            scalar_fields[field_name] = []
        else:
            scalar_fields[field_name] = None

    # Required non-nullable scalar fields need real values.
    scalar_fields["ticker"] = "TEST"
    scalar_fields["name"] = "Test Corp"
    scalar_fields["sector"] = "Technology"
    scalar_fields["recommendation"] = "neutral"
    scalar_fields["rank"] = 1
    scalar_fields["composite_score"] = 50.0
    scalar_fields["current_price"] = 100.0
    scalar_fields["index_membership"] = "sp500"
    # Non-nullable bool fields with defaults.
    scalar_fields["has_history"] = False
    scalar_fields["entered_top5"] = False
    scalar_fields["exited_top5"] = False

    return StockDetail(
        pillar_scores=ps,
        raw_metrics=rm,
        data_quality=dq,
        **scalar_fields,
    )


def _make_synthetic_summary() -> StockSummary:
    """Return a minimal but structurally valid StockSummary for schema derivation."""
    # Only pass the truly required (non-defaulted) fields; let Pydantic use
    # Field(default_factory=...) for all optional/list fields.
    return StockSummary(
        ticker="TEST",
        name="Test Corp",
        sector="Technology",
        rank=1,
        composite_score=50.0,
        current_price=100.0,
    )


# ---------------------------------------------------------------------------
# Column dtype inference
# ---------------------------------------------------------------------------

def _infer_dtype(value: Any) -> str:
    """Return a stable type string for a column value."""
    if value is None:
        return "NoneType"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


# ---------------------------------------------------------------------------
# Canonical column derivation
# ---------------------------------------------------------------------------

def derive_canonical_columns() -> dict[str, str]:
    """Return {column_name: dtype_hint} for the warehouse flat schema.

    The dtype is ``"bool"`` for flag_*/warn_* columns, ``"str | None"`` for
    *_json columns, and the inferred Python type for scalar columns.

    Sorted alphabetically for stable JSON output.
    """
    detail = _make_synthetic_detail()
    summary = _make_synthetic_summary()
    row = flatten_stock(detail, summary)

    cols: dict[str, str] = {}
    for col, val in sorted(row.items()):
        if col.startswith("flag_") or col.startswith("warn_"):
            cols[col] = "bool"
        elif col.endswith("_json"):
            cols[col] = "str | None"
        else:
            cols[col] = _infer_dtype(val)

    return cols


# ---------------------------------------------------------------------------
# Snapshot read/write
# ---------------------------------------------------------------------------

def _load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not read snapshot {SNAPSHOT_PATH}: {exc}", file=sys.stderr)
        return {}


def _write_snapshot(columns: dict[str, str]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {"columns": columns}
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Snapshot written to {SNAPSHOT_PATH} ({len(columns)} columns)")


# ---------------------------------------------------------------------------
# Flag registry cross-check
# ---------------------------------------------------------------------------

def _check_flag_registry(columns: dict[str, str]) -> list[str]:
    """Return a list of drift messages for flag/warn columns vs registries."""
    errors: list[str] = []
    flag_cols = {c[len("flag_"):] for c in columns if c.startswith("flag_")}
    warn_cols = {c[len("warn_"):] for c in columns if c.startswith("warn_")}

    unregistered_flags = flag_cols - KNOWN_RISK_FLAGS
    for f in sorted(unregistered_flags):
        errors.append(f"flag_{f}: not in KNOWN_RISK_FLAGS registry")

    missing_flags = KNOWN_RISK_FLAGS - flag_cols
    for f in sorted(missing_flags):
        errors.append(f"KNOWN_RISK_FLAGS['{f}']: missing flag_{f} column in flatten output")

    unregistered_warns = warn_cols - KNOWN_VALUATION_WARNINGS
    for w in sorted(unregistered_warns):
        errors.append(f"warn_{w}: not in KNOWN_VALUATION_WARNINGS registry")

    missing_warns = KNOWN_VALUATION_WARNINGS - warn_cols
    for w in sorted(missing_warns):
        errors.append(f"KNOWN_VALUATION_WARNINGS['{w}']: missing warn_{w} column in flatten output")

    return errors


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Return exit code: 0=ok, 1=drift/errors, 2=unexpected exception."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Warehouse flat-column drift guard",
        prog="python -m compute.warehouse.warehouse_schema_check",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate the snapshot file instead of comparing.",
    )
    args = parser.parse_args(argv)

    try:
        columns = derive_canonical_columns()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to derive canonical columns: {exc}", file=sys.stderr)
        return 2

    # Always validate flag registry parity first.
    registry_errors = _check_flag_registry(columns)
    if registry_errors:
        print("Flag registry drift detected:", file=sys.stderr)
        for msg in registry_errors:
            print(f"  {msg}", file=sys.stderr)
        print(
            "\nFix: update KNOWN_RISK_FLAGS / KNOWN_VALUATION_WARNINGS in "
            "compute/warehouse/flag_registry.py to match the emitted columns.",
            file=sys.stderr,
        )
        return 1

    if args.update:
        _write_snapshot(columns)
        return 0

    # Compare against committed snapshot.
    snapshot = _load_snapshot()
    committed_cols: dict[str, str] = snapshot.get("columns", {})

    added = {k: v for k, v in columns.items() if k not in committed_cols}
    removed = {k: v for k, v in committed_cols.items() if k not in columns}
    changed = {
        k: (committed_cols[k], columns[k])
        for k in columns
        if k in committed_cols and columns[k] != committed_cols[k]
    }

    if not added and not removed and not changed:
        print(f"OK: warehouse schema in sync ({len(columns)} columns, {SNAPSHOT_PATH})")
        return 0

    print("DRIFT: warehouse flat-column schema has changed.", file=sys.stderr)
    if added:
        print(f"  Added ({len(added)}): {sorted(added)}", file=sys.stderr)
    if removed:
        print(f"  Removed ({len(removed)}): {sorted(removed)}", file=sys.stderr)
    if changed:
        for col, (old, new) in sorted(changed.items()):
            print(f"  Changed dtype: {col}: {old!r} → {new!r}", file=sys.stderr)
    print(
        "\nFix: run `python -m compute.warehouse.warehouse_schema_check --update` "
        "to regenerate data/warehouse/warehouse_schema.json, then commit the diff.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
