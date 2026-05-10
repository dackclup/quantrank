---
name: schema-check
description: Verify that compute/output/schemas.py (Pydantic) and frontend/lib/types.ts
  (TypeScript) are in sync via the schema-snapshot guard. Run anytime either side
  changes — adds, removes, or renames a field on StockSummary / StockDetail /
  Metadata / RawMetrics / DataQuality / PillarScores. CI fails on drift; this
  skill catches it locally before push.
---

# schema-check

## When to use

After any change to:

- `compute/output/schemas.py` (Pydantic models)
- `frontend/lib/types.ts` (TypeScript interfaces)
- `frontend/lib/schema-snapshot.json` (the canonical bridge)

Or proactively before opening / pushing a PR that touches the
output schema layer.

## What it does

Wraps `python -m compute.output.schema_check` and reports drift
between the live Pydantic models and the on-disk
`frontend/lib/schema-snapshot.json`. Auto-updates the snapshot if
requested.

The schema snapshot guard exists because **Pydantic and TypeScript
are not auto-synced** — every new field requires touching both
`schemas.py` and `types.ts`. CI fails on drift via the snapshot
diff. This skill is the local pre-CI check.

## Modes

### 1. Verify (default, read-only)

```bash
python -m compute.output.schema_check
```

Exit 0 = in sync. Exit 1 = drift detected; the diff is printed to
stderr.

### 2. Update snapshot

After you've changed `schemas.py` AND mirrored the change in
`types.ts`, regenerate the snapshot:

```bash
python -m compute.output.schema_check --update-snapshot
```

This rewrites `frontend/lib/schema-snapshot.json` from the current
Pydantic models. Commit the snapshot file along with the schema +
types changes — they belong in the same commit.

## Workflow when adding a field

1. Add the field to `compute/output/schemas.py` (Pydantic)
2. Mirror the type in `frontend/lib/types.ts` (TypeScript)
3. Run the verifier:
   ```bash
   python -m compute.output.schema_check
   ```
   Should report drift on the new field.
4. Update the snapshot:
   ```bash
   python -m compute.output.schema_check --update-snapshot
   ```
5. Verify clean:
   ```bash
   python -m compute.output.schema_check
   # → "✓ Schema snapshot in sync (.../schema-snapshot.json)."
   ```
6. Stage all three (schemas.py, types.ts, schema-snapshot.json) in
   the same commit.

## Workflow when CI fails on schema drift

Common cause: someone added a field on one side but not the other,
or forgot to regenerate the snapshot.

1. Pull the failing commit locally.
2. Run `python -m compute.output.schema_check` — read the diff.
3. The diff tells you which side is out of sync:
   - "+ field on Python, missing from snapshot" → either type the
     field in `types.ts` and regen, OR remove the field from
     `schemas.py` if it was added by mistake.
   - "- field in snapshot, missing from Python" → restore the field
     to `schemas.py` if it should still exist, OR regen if the
     removal is intentional.
4. Apply the fix, regen, commit, push.

## Edge cases

- **Type changes** (e.g., `int | None` → `float | None`): the
  snapshot picks this up. Update `types.ts` to match (`number | null`
  on both sides — TypeScript doesn't distinguish int vs float).
- **Optional vs required**: Pydantic `default=None` → `<field> | null`
  in TypeScript with `required: false` in the snapshot.
- **Nested dicts** (e.g., `tier2_events: dict | None`): the snapshot
  records `dict | None` but doesn't enforce sub-shape. The sub-shape
  contract lives in `frontend/lib/types.ts::Tier2Events` and is
  exercised by `tests/test_scoring/test_tier2.py::test_B4_dict_shape_matches_typescript_interface`.

## Anti-patterns (do not do)

- Do NOT edit `schema-snapshot.json` by hand. It's a generated file.
  Always regenerate via `--update-snapshot`.
- Do NOT skip the verify step. The CI guard exists for a reason —
  catching drift in dev is much cheaper than the CI red-light + fix
  + re-push cycle.
- Do NOT regenerate the snapshot without first changing types.ts.
  That just papers over drift instead of fixing it.

## Related

- `verify-production-output` — Section A reads the version + new
  fields from this layer
- The reason taxonomy in `compute/output/schemas.py` is also schema —
  but it's not currently snapshotted. (Phase 4 candidate: snapshot
  the `SKIP_REASONS` set so the 21→24 migration in PR-3d is
  guarded.)
