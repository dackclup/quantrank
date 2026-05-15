# CHANGELOG.md Scaffolding (Phase 4 planning stub)

**Status**: Planning. P0 infrastructure gap surfaced in 2026-05-15
audit. Phase 4 `schema-versioning/PLAN.md` + Phase 11 `case-studies/`
+ `public-api-docs/` all reference `CHANGELOG.md` but the file
doesn't exist yet.

## Purpose

Public CHANGELOG.md captures every release: what shipped, what broke
(if anything), what's deprecated. Critical for:

1. **3rd-party API consumers** (Phase 11 public-api-docs) — need to
   know what changed when pinning to a major version
2. **Case studies** (Phase 11 case-studies) — reference "this changed
   in v1.0.3 — see CHANGELOG.md"
3. **Schema versioning** (Phase 4 schema-versioning) — formal record
   of additive vs breaking changes
4. **Transparent governance** — anyone can audit what shipped when

## Format

Follow [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
convention — the de facto open-source standard:

```markdown
# Changelog

All notable changes to QuantRank are documented in this file.

Format follows [Keep a Changelog 1.1.0](https://keepachangelog.com).
Versioning follows [Semantic Versioning 2.0.0](https://semver.org).

## [Unreleased]

### Added
- (entries from main since last tag)

### Changed
- ...

### Deprecated
- ...

### Removed
- ...

### Fixed
- ...

## [1.0.3-fix] — 2026-05-14

### Fixed
- `_avg_3y_roe` per-year denominator (closes #11)
- Workflow cache miss after `_ANNUAL_TAGS` schema change (PR 4c.1)
- ...
```

## Auto-generation

Manual maintenance of CHANGELOG.md is fragile. Generate from PR titles
+ tag boundaries:

```python
# compute/changelog/build.py
def regenerate_changelog():
    """Parse `git log v1.0.0..v1.0.3-fix --first-parent --merges`
    + each merge commit's PR title.

    Group by section based on PR title prefix:
    - feat(...)   → Added
    - fix(...)    → Fixed
    - chore(...)  → Internal (skipped from public log)
    - docs(...)   → Documentation (own section)
    - perf(...)   → Performance (own section)
    """
```

Generated CHANGELOG goes through human review before tag push (catches
auto-generation errors).

## Architecture

```
CHANGELOG.md                          # The public file
compute/changelog/build.py            # Auto-generation
.github/workflows/changelog-check.yml # CI: ensure [Unreleased] section is non-empty before tag push
docs/CHANGELOG_GUIDE.md               # Contributor doc — how to format PR titles
```

## Effort

| Step | LOC | Days |
|---|---|---|
| Initial CHANGELOG.md with retro-fill from `v0.1.0` → `v1.0.3-fix` | ~600 markdown | 2 |
| Auto-generator `compute/changelog/build.py` | ~200 | 1.5 |
| CI workflow `changelog-check.yml` (block tag push if [Unreleased] empty) | ~50 | 0.5 |
| Contributor guide `docs/CHANGELOG_GUIDE.md` | ~100 markdown | 0.5 |
| Tests (golden-fixture PR title parsing) | ~120 | 1 |
| **Total** | **~1070 LOC + markdown** | **~5.5 days** |

## Decisions (locked 2026-05-15)

1. ~~Manual vs auto?~~ → **Hybrid** — auto-gen draft from PR titles,
   human reviews before tag push
2. ~~Which convention?~~ → **Keep a Changelog 1.1.0** (industry
   standard; readable; semver-aligned)
3. ~~Include internal `chore:` commits?~~ → **NO in public CHANGELOG**;
   they go in `docs/INTERNAL_CHANGELOG.md` if needed
4. ~~Retro-fill how far back?~~ → **From v0.1.0 forward** — full
   transparency from project start

## Dependencies

- Phase 4 `schema-versioning/PLAN.md` — formalizes which changes are
  patch / minor / major per semver
- Phase 4 `v1-to-v1-1-migration/PLAN.md` — describes additive-only
  v1.x policy → CHANGELOG enforces visibility
- `phase-status-bump` skill — currently updates PHASE_STATUS.md +
  SKILL.md + WORKFLOW.md in lockstep. Should also update CHANGELOG
  on phase / tag boundary.

## Out of scope

- Auto-translate CHANGELOG into Thai (Phase 10 §3 bilingual handles
  user-facing content; CHANGELOG is technical / contributor-facing
  English-only)
- Per-stock change history (which weekly compute changed which stock's
  recommendation) — separate stub `phase-11/per-stock-history/`
- Migration guides for major versions (v1.x → v2.x) — separate stub
  when the first major break ships
