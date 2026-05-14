# Schema Versioning Narrative (Phase 4 planning stub)

**Status**: Planning. Closes the audit-#7 gap: schema-version bumps were happening implicitly (`0.4.0 → 0.5.0 → 0.6.0`) without a documented contract.

## Purpose

Define when a schema change is patch / minor / major. Currently SKILL.md Table 2 lists prior version bumps but doesn't say WHY each was that magnitude. Codify the rule.

## The rule (semver applied to the JSON output schema)

The schema version lives at `metadata.version` (e.g., `0.6.0-phase3d`). Bump rules:

| Change type | Bump | Example |
|---|---|---|
| Bug fix in a metric's formula (corrects an objectively wrong value) | **patch** (`0.6.0` → `0.6.1`) | Audit #6 PE fix |
| Add a new optional field (default = None) | **patch** | `dechow_f_score` add in PR #45 |
| Add a new pillar (sentiment/ml flipping to populated) | **minor** (`0.6.x` → `0.7.0`) | Phase 5 ML pillar activation |
| Add a new defense flag (annotate-only) | **patch** | `beneish_high` in PR #43 |
| Promote a defense flag from annotate to active veto | **minor** | `data_quality_input_corruption` in PR #33 |
| Change composite weight on any pillar | **minor** | Phase 4+ factor consolidation |
| Change a defense threshold (e.g., Beneish cutoff) | **minor** | Hypothetical Beneish tuning |
| Remove a field | **major** (`0.x.x` → `1.0.0` → `2.0.0`) | n/a in v1.0 |
| Rename a field | **major** | n/a |
| Change a field's type (`float` → `int`) | **major** | n/a |

The phase suffix (`-phase3d`, `-phase4`) is informational — it tracks the human-readable phase, not semver. Two valid forms:
- `1.0.0` — final v1.0 release tag
- `1.0.0-phase3d` — pre-release; the phase suffix is metadata

## Drift detection

`schema_check` (already implemented at `compute/output/schema_check.py`) catches Pydantic ↔ TypeScript ↔ snapshot drift on every PR. Extend it post-v1.0 to also check:

1. **No field deletion** — read `frontend/lib/schema-snapshot.json` from the most recent `v*.0.0` tag; if any top-level field disappears in HEAD → exit 1
2. **No type narrowing** — if a field was `float | None` at last major and is now `float` (removed nullable) → exit 1 (consumers may assume None is valid)
3. **Phase suffix matches branch** — if HEAD's `metadata.version` includes `-phase4` but branch is on `main` post-Phase-4-tag → warn

```python
def check_breaking_changes_since_last_major():
    last_major = subprocess.run(
        ["git", "tag", "-l", "v*.0.0", "--sort=-v:refname"],
        capture_output=True, text=True
    ).stdout.split("\n")[0]
    if not last_major:
        return  # No major tag yet (pre-v1.0)
    
    old_snapshot = json.loads(subprocess.run(
        ["git", "show", f"{last_major}:frontend/lib/schema-snapshot.json"],
        capture_output=True, text=True
    ).stdout)
    new_snapshot = json.loads(Path("frontend/lib/schema-snapshot.json").read_text())
    
    for cls_name, old_fields in old_snapshot.items():
        new_fields = new_snapshot.get(cls_name, {})
        for field, old_type in old_fields.items():
            if field not in new_fields:
                raise SystemExit(
                    f"BREAKING: field {cls_name}.{field} was in {last_major} "
                    f"but is missing in HEAD. Either restore it or bump to "
                    f"a new major version."
                )
```

## Migration contract for consumers

Currently the QuantRank JSON is consumed by:
- The static-site frontend (same repo — moves in lockstep with schema)
- Hypothetically: third-party agents reading `rankings.json` via MCP / curl

For external consumers, the documented contract should be (add to README):

> **JSON Schema Stability**
> - Same major version: additive only. Existing fields keep their type and meaning
> - Minor version bump: a documented new field may appear; existing fields unchanged
> - Major version bump: see `CHANGELOG.md`; consumers should pin to a major

## Phase tag promotion timeline

Tag history (anticipated):

| Tag | Phase | Schema | When |
|---|---|---|---|
| `v0.1.0-phase0` … `v0.6.0-phase3d` | Pre-1.0 development | `0.x.y` | done |
| `v1.0.0` | Phase 3e.4 closing | `1.0.0` | imminent |
| `v1.0.x` | Phase 4 patch releases (perf, issue fixes) | `1.0.x` | post-v1.0 |
| `v1.1.0-phase4` | Phase 4 feature release | `1.1.0` | post Phase 4 features land |
| `v1.2.0-phase5` | ML pillar activated | `1.2.0` | Phase 5 |
| ... | ... | ... | ... |
| `v2.0.0` | First major break (composite formula change OR field removal) | `2.0.0` | TBD |

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| `schema_check` breaking-change extension | ~50 | 0.5 day |
| `CHANGELOG.md` scaffolding + first entry | ~30 | 0.25 day |
| README "JSON Schema Stability" section | ~20 | 0.25 day |
| Update SKILL.md Table 2 with this versioning rule | ~30 | 0.5 day |
| **Total** | **~130 LOC** | **~1.5 days** |

## Open questions

1. Should the phase suffix be stripped at major tags? `v1.0.0` (clean) vs `v1.0.0-phase3d` (audit trail)
2. How long to maintain backward-compat for deprecated fields — 1 minor cycle (~weeks) or 1 major cycle (~months/years)?
3. Should `schema_check` block CI on breaking changes, or just warn + require explicit `--allow-breaking` flag?
