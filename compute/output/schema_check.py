"""Schema snapshot guard (Phase 3c Step 9).

Generates a canonical JSON snapshot of all output Pydantic schemas and
compares against ``frontend/lib/schema-snapshot.json``. CI fails if
snapshots drift, forcing the PR author to either:

  (a) update the TypeScript types in ``frontend/lib/types.ts`` to match,
      then run ``python -m compute.output.schema_check --update-snapshot``,
      OR
  (b) revert the schema change.

This is the single source of truth for Python ↔ TypeScript schema parity.
It does **not** verify TypeScript types directly (that's ``tsc``'s job);
it verifies that **someone consciously updated both sides** when a schema
field changed. Catching the drift at CI time prevents the rankings.json
output from going out of sync with the frontend's expected shape.

CLI usage:

  # Verify in-sync (used by CI):
  python -m compute.output.schema_check
    → exit 0 if in-sync, 1 if drift, 2 on unexpected error

  # Regenerate after intentional schema change:
  python -m compute.output.schema_check --update-snapshot
    → writes ``frontend/lib/schema-snapshot.json`` and exits 0
"""

from __future__ import annotations

import json
import sys
import types
import typing
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from compute import config
from compute.output.schemas import (
    DataQuality,
    Metadata,
    PillarBaseline,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)

SNAPSHOT_PATH: Path = config.PROJECT_ROOT / "frontend" / "lib" / "schema-snapshot.json"

TRACKED_MODELS: list[type[BaseModel]] = [
    DataQuality,
    Metadata,
    PillarBaseline,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
]


def _normalize_type(annotation: Any) -> str:
    """Return a stable, human-readable string for a type annotation.

    Examples:
      ``float | None``     → ``"float | None"``
      ``list[str]``        → ``"list[str]"``
      ``dict | None``      → ``"dict | None"``
      ``PillarScores``     → ``"PillarScores"``
      ``Any``              → ``"Any"``

    Custom classes are reported by their ``__name__`` so a rename in
    ``schemas.py`` surfaces as a snapshot diff.
    """
    if annotation is type(None):
        return "None"
    if annotation is Any:
        return "Any"
    if isinstance(annotation, type):
        return annotation.__name__

    # Union types — both ``X | Y`` (types.UnionType) and ``Union[X, Y]``.
    origin = typing.get_origin(annotation)
    if isinstance(annotation, types.UnionType) or origin is typing.Union:
        args = [_normalize_type(a) for a in typing.get_args(annotation)]
        return " | ".join(args)

    # Generic types: list[str], dict[str, int], etc.
    if origin is not None:
        args = typing.get_args(annotation)
        origin_name = (
            origin.__name__ if hasattr(origin, "__name__") else str(origin)
        )
        if not args:
            return origin_name
        formatted_args = ", ".join(_normalize_type(a) for a in args)
        return f"{origin_name}[{formatted_args}]"

    return str(annotation)


def _normalize_default(field_info: Any) -> Any:
    """Return a JSON-serializable representation of a field's default.

    - Required fields              → ``"<required>"`` sentinel.
    - ``default_factory=list``     → ``"<factory:list>"``
    - ``default_factory=PillarScores`` → ``"<factory:PillarScores>"``
    - JSON-serializable scalars    → returned as-is (None, bool, int, float, str).
    - Anything else                → ``f"<repr:{value!r}>"`` so diffs surface
      changes without crashing the JSON write.
    """
    if field_info.is_required():
        return "<required>"
    if (
        getattr(field_info, "default_factory", None) is not None
        and field_info.default_factory is not None
    ):
        factory = field_info.default_factory
        name = getattr(factory, "__name__", repr(factory))
        return f"<factory:{name}>"
    default = field_info.default
    if default is PydanticUndefined:
        return "<required>"
    if default is None or isinstance(default, (bool, int, float, str)):
        return default
    return f"<repr:{default!r}>"


def generate_snapshot() -> dict[str, dict[str, dict[str, Any]]]:
    """Return canonical snapshot of all tracked Pydantic models.

    Shape::

        {
          "<ModelName>": {
            "<field_name>": {
              "type": "<normalized type str>",
              "required": <bool>,
              "default": <JSON-safe value or sentinel str>
            },
            ...
          },
          ...
        }

    Both top-level model keys and per-model field keys are sorted
    alphabetically so the JSON output is deterministic across runs.
    """
    snapshot: dict[str, dict[str, dict[str, Any]]] = {}
    for model in TRACKED_MODELS:
        fields: dict[str, dict[str, Any]] = {}
        for field_name, field_info in model.model_fields.items():
            fields[field_name] = {
                "type": _normalize_type(field_info.annotation),
                "required": field_info.is_required(),
                "default": _normalize_default(field_info),
            }
        snapshot[model.__name__] = dict(sorted(fields.items()))
    return dict(sorted(snapshot.items()))


def _format_diff(stored: dict, fresh: dict) -> str:
    """Build a human-readable diff between two snapshots.

    The output is grouped by model and lists added / removed / changed
    fields. Designed for the CI failure log so the PR author can
    immediately see which schema changed.
    """
    lines: list[str] = []
    stored_models = set(stored.keys())
    fresh_models = set(fresh.keys())

    for m in sorted(stored_models - fresh_models):
        lines.append(f"- model REMOVED: {m}")
    for m in sorted(fresh_models - stored_models):
        lines.append(f"+ model ADDED:   {m}")

    for m in sorted(stored_models & fresh_models):
        s_fields = stored[m]
        f_fields = fresh[m]
        s_keys = set(s_fields.keys())
        f_keys = set(f_fields.keys())

        added = sorted(f_keys - s_keys)
        removed = sorted(s_keys - f_keys)
        changed: list[str] = []
        for k in sorted(s_keys & f_keys):
            if s_fields[k] != f_fields[k]:
                changed.append(k)

        if not (added or removed or changed):
            continue

        lines.append(f"\n[{m}]")
        for k in removed:
            lines.append(f"  - field REMOVED: {k}  (was: {s_fields[k]})")
        for k in added:
            lines.append(f"  + field ADDED:   {k}  (now: {f_fields[k]})")
        for k in changed:
            lines.append(f"  ~ field CHANGED: {k}")
            lines.append(f"      stored: {s_fields[k]}")
            lines.append(f"      fresh:  {f_fields[k]}")

    return "\n".join(lines) if lines else "<no diff>"


def check_snapshot() -> tuple[bool, str | None]:
    """Compare the on-disk snapshot against the live schemas.

    Returns
    -------
    (in_sync, diff_message)
        ``in_sync`` is True iff the stored JSON matches a freshly
        generated snapshot. ``diff_message`` is None when in-sync,
        otherwise a human-readable diff string suitable for the CI log.
    """
    if not SNAPSHOT_PATH.exists():
        return False, (
            f"Snapshot file does not exist at {SNAPSHOT_PATH}. "
            f"Run `python -m compute.output.schema_check --update-snapshot` "
            f"to create it."
        )
    try:
        stored = json.loads(SNAPSHOT_PATH.read_text())
    except json.JSONDecodeError as e:
        return False, f"Snapshot file is not valid JSON: {e}"
    fresh = generate_snapshot()
    if stored == fresh:
        return True, None
    return False, _format_diff(stored, fresh)


def update_snapshot() -> Path:
    """Overwrite ``SNAPSHOT_PATH`` with a freshly generated snapshot.

    Returns the written path. Used by the ``--update-snapshot`` CLI
    flag after an intentional schema change.
    """
    fresh = generate_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(fresh, indent=2) + "\n")
    return SNAPSHOT_PATH


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes: 0 in-sync, 1 drift, 2 unexpected error."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if "--update-snapshot" in args:
            path = update_snapshot()
            print(f"Snapshot updated: {path}")
            return 0
        ok, diff = check_snapshot()
        if ok:
            print(f"✓ Schema snapshot in sync ({SNAPSHOT_PATH}).")
            return 0
        print("✗ Schema snapshot drift detected:\n")
        print(diff)
        print()
        print("Resolution:")
        print("  1. If the schema change is intentional: update the matching")
        print("     TypeScript types in frontend/lib/types.ts, then run")
        print("     `python -m compute.output.schema_check --update-snapshot`")
        print("     and commit the new snapshot.")
        print("  2. If the schema change was unintentional: revert it.")
        return 1
    except Exception as e:  # noqa: BLE001  (CLI surface — bubble all errors)
        print(f"Schema check failed unexpectedly: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
