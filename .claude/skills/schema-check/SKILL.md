---
name: schema-check
description: Run `python -m compute.output.schema_check` to verify `schemas.py` ↔ `types.ts` via `schema-snapshot.json`; regenerate the snapshot when a change is mirrored on both sides. TRIGGER: any edit to schemas.py or types.ts, CI schema-drift failure, pre-push on schema-touching PRs, or "did I update both sides?" / "is the schema in sync?".
---

# schema-check

The Pydantic models in `compute/output/schemas.py` and the TypeScript
interfaces in `frontend/lib/types.ts` describe the same JSON wire format
from opposite sides. They are not auto-synced — every new field on the
Python side needs a manual mirror on the TypeScript side. The
schema-snapshot guard at `frontend/lib/schema-snapshot.json` is the
canonical bridge; CI fails on drift.

This skill is the local pre-CI check that catches drift before push.

## Two modes

### Verify (read-only)

```bash
python -m compute.output.schema_check
```

Exit 0 means the live Pydantic models match the on-disk snapshot. Exit 1
means drift — the diff prints to stderr telling you which side is out of
sync.

### Update the snapshot

After you've changed `schemas.py` AND mirrored the change in `types.ts`,
regenerate the snapshot:

```bash
python -m compute.output.schema_check --update-snapshot
```

This rewrites `schema-snapshot.json` from the current Pydantic models.
Commit the snapshot in the same commit as the schemas.py + types.ts
changes — they belong together so reviewers can see the three-way change
in one diff.

## Workflow when adding a field

1. Add the field to `compute/output/schemas.py` (Pydantic)
2. Mirror the type in `frontend/lib/types.ts` (TypeScript)
3. Run the verifier — should report drift on the new field
4. Run with `--update-snapshot` — should report "✓ in sync"
5. Verify clean (re-run the read-only check)
6. Stage all three files in the same commit

## Workflow when CI fails on schema drift

A teammate pushed a Python schema change but forgot the TypeScript mirror
(or vice versa). To fix:

1. Pull the failing commit locally
2. Run `python -m compute.output.schema_check` to read the diff
3. Apply the missing side:
   - "+ field on Python, missing from snapshot" → add to `types.ts` then
     `--update-snapshot`
   - "- field in snapshot, missing from Python" → either restore the
     field on the Python side, or regenerate if removal was intentional
4. Stage + commit + push

## Type mapping cheat sheet

| Python type | TypeScript type |
|---|---|
| `int \| None` / `float \| None` | `number \| null` |
| `str \| None` | `string \| null` |
| `bool` | `boolean` |
| `list[T]` | `T[]` |
| `dict \| None` (untyped) | `Record<string, unknown> \| null` or a dedicated interface |

TypeScript does not distinguish `int` from `float` — both map to
`number`. Pydantic `default=None` ≡ TypeScript `<field> \| null` with
`required: false` in the snapshot.

## Nested-dict caveat

Some fields like `StockDetail.tier2_events: dict | None` aren't fully
typed at the Pydantic level. The snapshot records `dict | None` but
doesn't enforce sub-shape. The sub-shape contract lives in
`frontend/lib/types.ts::Tier2Events` and is exercised by
`tests/test_scoring/test_tier2.py::test_B4_dict_shape_matches_typescript_interface`.
When introducing a nested dict, prefer typing it as a dedicated
Pydantic + TypeScript pair so the snapshot picks up the structure.

## Why this skill exists

Pydantic-to-TypeScript drift causes silent UI breakage. A new
`Metadata.fundamentals_latency_p95_seconds` field on Python that's not
mirrored in TypeScript means the field renders as `undefined` at
runtime — TypeScript can't narrow it because the type doesn't include
it. The snapshot guard catches this in CI; this skill catches it in
local dev so the CI red-light never fires.

## Anti-patterns

- Hand-editing `schema-snapshot.json`. The file is generated. Always go
  through `--update-snapshot`.
- Regenerating the snapshot before mirroring `types.ts`. That papers
  over drift instead of fixing it.
- Bumping the schema version in `pyproject.toml` here. Version bumps
  belong with the actual scoring / shape change, not the schema check.

## Related skills

- `verify-production-output` — Section A reads the version + new fields
  from this layer at runtime
- `phase-status-bump` — when the schema version moves, the docs that
  cite it also need to move; that skill keeps them aligned

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Run `python -m compute.output.schema_check` to verify that the
Pydantic models in `compute/output/schemas.py` agree with the TypeScript
types in `frontend/lib/types.ts` via the canonical snapshot at
`frontend/lib/schema-snapshot.json`. Also regenerate the snapshot when a
schema change has been mirrored on both sides. TRIGGER any time
`schemas.py` is edited (added / removed / renamed field on StockSummary,
StockDetail, Metadata, RawMetrics, DataQuality, or PillarScores), any
time `types.ts` is edited, when CI fails with a schema-drift error,
before pushing a PR that touches output schemas, or whenever the user
asks "did I update both sides?" / "is the schema in sync?" — even
without naming the snapshot file. SKIP for unrelated Pydantic models
inside `compute/` that aren't part of the JSON output surface.
