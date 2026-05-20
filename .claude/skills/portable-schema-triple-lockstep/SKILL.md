---
name: portable-schema-triple-lockstep
description: Three-file lockstep for any Python ↔ TypeScript application
  exchanging JSON. Pydantic schema (`schemas.py`), TypeScript types
  (`types.ts`), and a canonical snapshot file (`snapshot.json`) move
  together; a CI guard fails the build on drift. Generic — drop-in for any
  full-stack app with a JSON contract crossing the Python/TS boundary.
  TRIGGER when adding/removing/renaming a field on any model that
  serializes to JSON consumed by a TypeScript client, when changing a
  field's nullability, or when CI fails with a schema-drift error. SKIP
  for internal-only Python models that don't cross the JSON boundary, or
  for projects that already use code-gen (e.g., gRPC, OpenAPI generators)
  to enforce the contract.
---

# portable-schema-triple-lockstep

A failure-mode-driven pattern: schemas drift, JSON consumers
silently accept wrong shapes, bugs ship to production. This skill
codifies the 3-file invariant + CI guard that catches drift before
merge. Portable — works in any Python/TS monorepo.

## Pattern

The "triple":

1. **Pydantic schema** (`compute/output/schemas.py` or equivalent) —
   the source of truth for what gets written to JSON
2. **TypeScript types** (`frontend/lib/types.ts` or equivalent) —
   the source of truth for what the UI accepts
3. **Canonical snapshot** (`schema-snapshot.json` or equivalent) —
   the source of truth for what BOTH sides agree to

Workflow:

1. Edit Pydantic schema (`schemas.py`)
2. Mirror the change in TypeScript (`types.ts`) by hand —
   nullability, optional, field name, type all preserved
3. Run a snapshot-generator script (`schema_check --update-snapshot`)
   that walks the Pydantic models and emits the canonical snapshot
4. CI guard runs the same generator in dry-run mode and compares
   against the committed snapshot; any drift fails the build with
   a specific diff message
5. Reviewer reading the PR can verify all three sides moved
   together without re-reading the entire diff

## CI guard implementation

```python
# tools/check_schema_snapshot.py (or similar)
def main() -> int:
    expected = build_snapshot_from_pydantic()  # walk Pydantic models
    actual = json.loads(SNAPSHOT_PATH.read_text())
    diff = compare(expected, actual)
    if diff:
        print(format_drift_report(diff))
        return 1
    print("✓ Schema snapshot in sync")
    return 0
```

The guard runs as a CI step BEFORE pytest (early failure = fast
feedback). Authors run it locally with `--update-snapshot` to
regenerate after editing schemas.py + types.ts.

## Trigger conditions

- Adding / removing / renaming a field on any Pydantic model that
  serializes to JSON consumed by a TypeScript client
- Changing a field's nullability (`Optional[X]` ↔ `X`)
- Changing a field's type (`int` → `float`, `str` → `Literal[...]`)
- CI fails with a schema-drift error
- A new nested model is introduced

## Skip conditions

- Internal-only Python models that don't cross the JSON boundary
  (config dataclasses, cache structs)
- Projects with code-gen pipelines (gRPC + protobuf, OpenAPI +
  `openapi-generator`) — the generator IS the lockstep
- Projects where the UI consumes JSON via `any` types (the
  contract isn't enforced at compile time anyway)

## Common drift modes the guard catches

- Adding a Pydantic field without mirroring in `types.ts` → snapshot
  has the new field, `types.ts` doesn't → tsc errors when the JSON
  arrives at runtime, but the CI snapshot guard catches it earlier
- Renaming a Pydantic field — Pydantic accepts old JSON via alias,
  but `types.ts` consumer breaks silently — the snapshot guard
  surfaces the rename as a field rename in the diff
- Changing nullability — `field: str` → `field: str | None` —
  TypeScript consumers without optional-chaining will crash

## QuantRank precedents

- `compute/output/schemas.py` + `frontend/lib/types.ts` +
  `frontend/lib/schema-snapshot.json` are the project's triple
- The CI guard is `python -m compute.output.schema_check`, run
  before pytest in `.github/workflows/ci.yml`
- Phase 4h.2 Part 2 (PR #124) added a new optional Metadata field
  and exercised all 3 sides of the triple — the snapshot
  regeneration step caught a mirror-mismatch before the PR opened
