# v1.0 → v1.1 Migration Path (Phase 4 planning stub)

**Status**: Planning. Promote to top-level skill when Phase 4 implementation begins.

## Purpose

Audit gap (2026-05-14): planning docs cover Phase 0-3 (v1.0) and individual Phase 4-8 features in detail, but the **transition** between v1.0 (a sealed release tag) and v1.1 (Phase 4 work) is implicit. This PLAN closes that gap.

## What v1.0 promises (the contract)

When `v1.0` (Phase 3e.4) is tagged, the public surface is:

| Surface | Contract |
|---|---|
| `frontend/public/data/metadata.json` | Schema version `0.6.0-phase3d` (or `1.0.0` if bumped at tag). Field set frozen — no removals or renames in v1.1 |
| `frontend/public/data/rankings.json` | StockSummary array. Field set frozen |
| `frontend/public/data/stocks/<TICKER>.json` | StockDetail. Field set frozen; **additive changes allowed** (new optional fields with `\| None` default) |
| `frontend/lib/types.ts` | TypeScript types match Pydantic 1:1 (`schema_check` enforces) |
| Composite score formula | 8-pillar Phase 3 weights (quality 0.22 / value 0.18 / growth 0.10 / momentum 0.10 / health 0.08 / profitability 0.05 / technical 0.04 / risk 0.03 + sentiment/ml 0.20 redistributed). Frozen |
| Defense layer | Altman / Sloan / NSI / going-concern (active) + Beneish / Dechow (annotate). Threshold constants frozen |
| Vercel static URL | `quantrank-dackclups-projects.vercel.app` (or custom domain when set) — stable |

**v1.1 may NOT**:
- Remove or rename any v1.0 field
- Change composite weights without bumping to v1.2+
- Change defense thresholds without academic justification + release-note disclosure

**v1.1 MAY**:
- Add optional fields with `None` defaults
- Add new defense flags (annotate-only)
- Add new pillars (additive — sentiment/ml flipping from null to populated is the canonical example)
- Change UI/UX (frontend independent of schema)

## What ships in v1.1 (Phase 4 scope)

Per WORKFLOW.md Phase 4 + the Phase 4 UX trio:

### Compute layer
- OSAP signals integration (~100 of 319 signals — academic factor consolidation)
- JKP factor returns
- Qlib Alpha158 features
- IPCA 5 latent factors
- 8-K Tier-2 defenses re-enabled (`_EIGHT_K_DEFENSES_ENABLED = True`)
- Going-concern phrase scan refined (Option C if FP rate still > 5%)
- `_avg_3y_roe` per-year equity fix (issue #11)
- Workflow cache improvements (10-K text + history + prices + universe)

### UI/UX layer (the trio)
- **recommendation-badge** — adds `StockDetail.recommendation` field (additive ✓)
- **loss-chance** — adds `StockDetail.loss_chance_pct` field (additive ✓)
- **price-chart-enhancements** — frontend-only, no schema change

### Schema version
- `0.6.0-phase3d` → `1.1.0-phase4` (or `1.0.1` if only the 3 UX trio fields land)
- Snapshot regeneration is the canary

## Sequencing

Suggested PR order (top of v1.1 cycle):

1. **PR 4a — Workflow cache improvements** (1-2 days)
   - Add cache steps for 10-K text + history + prices + universe in `compute-rankings.yml`
   - Tag: `v1.0.1-perf` (patch release)
2. **PR 4b — `_avg_3y_roe` per-year equity** (1 day, issue #11)
   - Add `stockholders_equity` to `_ANNUAL_TAGS`
   - Rewrite `_avg_3y_roe` to use per-year equity
   - Tag: `v1.0.2-issue-11`
3. **PR 4c — recommendation-badge** (~230 LOC, 1-2 days)
4. **PR 4d — loss-chance** (~180 LOC, 1-2 days)
5. **PR 4e — price-chart-enhancements** (depends on 4c — recommendation field)
6. **PR 4f — 8-K Tier-2 re-enable** (gated by going-concern FP rate ≤ 5%)
7. **PRs 4g-...** — OSAP / JKP / Qlib / IPCA (factor consolidation, multi-week)
8. **Tag**: `v1.1.0-phase4` when all of above pass acceptance

## Deprecation & breaking-change policy

Phase 4 is **strict additive only**. If any change requires removing or renaming a v1.0 field:
1. Add new field alongside the old one
2. Mark old field with `# DEPRECATED in v1.X — remove in v2.0` comment in `schemas.py`
3. Keep both populated for at least one minor version cycle (1-2 months)
4. Remove only at the next major bump (v2.0)

This protects any external consumer of the JSON (third-party agents reading `rankings.json`).

## Rollback procedure

If a Phase 4 PR ships a regression:
1. **Revert the bot commit** that wrote the bad data (`git revert <chore-commit-sha> && git push origin main`)
2. **Revert the feature PR** (`gh pr revert <PR-number>` or manual)
3. Trigger `workflow_dispatch` on the reverted main → fresh JSON output
4. File post-mortem issue documenting what slipped past CI

The "annotate-and-veto-Top-N" pattern means even a buggy new annotation flag doesn't corrupt rankings — it just adds informational warnings to the JSON. Hard regressions (composite formula change, schema break) need full revert.

## Test plan

- [ ] Tag `v1.0` is reachable (`git tag -l v1.0` returns it)
- [ ] First v1.1 PR doesn't bump major version
- [ ] Field-deletion CI guard (proposed): `schema_check` extended to fail if a v1.0 field disappears from `types.ts`. Implement in PR 4a alongside cache improvements
- [ ] Vercel preview of v1.1 main + v1.0 tag side-by-side renders identically until UX trio lands

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| Field-deletion CI guard (schema_check extension) | ~30 | 0.5 day |
| Release-notes template for each minor version | ~50 | 0.5 day |
| Documentation update (this PLAN → top-level skill) | ~20 | 0.5 day |
| **Total scaffolding** | **~100 LOC** | **~1.5 days** |

The migration scaffolding itself is small. The Phase 4 features it enables are large.

## Open questions

1. Schema version naming: jump straight to `v1.1.0-phase4` or stair-step via `v1.0.1` / `v1.0.2` patch releases?
2. Field-deletion CI guard: implement as part of `schema_check` (Python) or as a separate workflow step (yaml diff against `v1.0` tag)?
3. Vercel deployment strategy during v1.1 development: keep `v1.0` tag pinned at a frozen preview URL, or always deploy main?
