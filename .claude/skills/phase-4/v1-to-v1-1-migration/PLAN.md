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

## Sequencing (LOCKED 2026-05-14)

Per `phase-4-kickoff-checklist/PLAN.md` §3 — PR order + schema-bump staircase:

| PR | Scope | Tag | Schema bump |
|---|---|---|---|
| 4a | Workflow cache improvements (per `workflow-cache-improvements/PLAN.md`) | `v1.0.1-perf` | **patch** — no schema change |
| 4b | Defense infrastructure: cross-source + PBO+DSR + IC-decay (per `defense-infrastructure/PLAN.md`) | `v1.0.2-defense` | **patch** — adds `cross_source_disagreement` risk flag (additive) |
| 4c | `_avg_3y_roe` per-year equity fix (issue #11) | `v1.0.3-fix` | **patch** — bug fix only |
| 4d | recommendation-badge (`StockDetail.recommendation` field, Option B locked) | `v1.1.0-rc1` | **minor** — first feature; field additive |
| 4e | loss-chance (`StockDetail.loss_chance_pct` field, Option D locked) | `v1.1.0-rc2` | **minor** — field additive |
| 4f | price-chart-enhancements (4.1 phase, depends on 4d) | `v1.1.0-rc3` | **patch** — no schema change (frontend-only) |
| 4g | 8-K Tier-2 re-enable (gated by going-concern FP rate ≤ 5%) | `v1.1.0-rc4` | **patch** — no schema change |
| 4h | OSAP integration (per `osap-integration/PLAN.md`) | `v1.1.0-rc5` | **minor** — adds `osap_signals` + `osap_blended_pillars` |
| 4i | JKP integration (per `jkp-integration/PLAN.md`) | `v1.1.0-rc6` | **minor** — adds `jkp_theme_exposures` + `jkp_blended_pillars` |
| 4j | Qlib Alpha158 (per `alpha158-fit/PLAN.md`) | `v1.1.0-rc7` | **minor** — adds Alpha158 feature dict |
| 4k | IPCA factor (per `ipca-factor-fit/PLAN.md`) | `v1.1.0-rc8` | **minor** — adds IPCA exposures dict |
| 4l | Final defense tuning (#7) + Phase 4 acceptance close | `v1.1.0-phase4` | **(final)** |

Schema-bump staircase rationale: `v1.0.1` / `v1.0.2` / `v1.0.3` are non-feature patch releases (perf / defense infra / bug fix — no new user-visible JSON fields). First user-facing additive feature (`recommendation` field at PR 4d) jumps to `v1.1.0-rc1`. Rest of Phase 4 stays on the `v1.1.0-rcN` series until Phase 4 acceptance criteria pass, then tag clean `v1.1.0-phase4`.

Per `phase-4-kickoff-checklist/PLAN.md` §2 decision: phase suffix stripped at major tags; here we keep phase suffix at Phase 4 close (`v1.1.0-phase4`) because it's a **minor** tag, not a major. Major (`v2.0`) cleans the suffix.

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

## Decisions (formerly open questions — locked 2026-05-14)

1. ~~Stair-step or direct?~~ → **Stair-step locked**: `v1.0.1-perf` → `v1.0.2-defense` → `v1.0.3-fix` → `v1.1.0-rcN` series → `v1.1.0-phase4`. Per the Sequencing table above. Stair-step makes intermediate progress observable (each PR gets its own preview tag) and matches `phase-4-kickoff-checklist/PLAN.md` §3
2. ~~Field-deletion CI guard implementation?~~ → **Extend `schema_check` (Python) locked**, NOT a separate workflow step. Per `schema-versioning/PLAN.md`'s `check_breaking_changes_since_last_major()` function. Single tool, single failure mode, easier debugging
3. ~~Vercel deployment strategy?~~ → **Always deploy main locked**. `v1.0` tag remains reachable via git but does NOT get a frozen preview URL — Vercel deploys whatever's on main. Simpler ops; tag is the contract, deployment is current
