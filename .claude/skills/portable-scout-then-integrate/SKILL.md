---
name: portable-scout-then-integrate
description: A 2-phase vendoring pattern for adopting an external library /
  data source. Phase 1 (scout PR) installs the dep, locks the public-API
  surface via a hardcoded manifest tuple, and ships smoke tests — without
  any production wiring. Phase 2 (integration PR) lands the production
  logic + observability surface. Generic — drop-in for any project
  evaluating a new third-party dep. TRIGGER when adopting a new pip / npm /
  cargo dep that will become load-bearing, when the dep has uncertain
  license / API stability / install footprint, or when the user says
  "scout this library" / "let's try X before committing". SKIP for
  utility-library deps (`requests`, `pyyaml`) with stable APIs and
  obvious licenses — overhead dominates.
---

# portable-scout-then-integrate

A vendoring pattern that separates "can we use this lib?" (cheap to
discard) from "we depend on this lib" (load-bearing). Portable —
no project-specific business logic embedded.

## Pattern

### Phase 1 — Scout PR (low-cost discovery)

1. **Pre-plan investigations** (5 questions, answered BEFORE writing
   any code):
   - PyPI / npm canonical package name + latest version
   - License (copy verbatim from `LICENSE.md` in the published
     artifact — don't trust READMEs that may lag)
   - Public API surface (extract from wheel source pre-install when
     possible — class names, method signatures, post-fit attributes)
   - Data requirements + minimum stable input size (from the
     maintainer's own test fixtures, not docs)
   - CI install footprint in MB (run `pip download --no-deps` and
     measure transitive bloat)
2. **Install the dep** in the appropriate optional-deps group
   (`[factors]`, `[ml]`, `[heavy]`) so contributors running the
   minimal install don't pull it
3. **Lock the public-API surface** with a hardcoded manifest tuple
   asserted at module load. See `portable-drift-detector-manifest`
   skill.
4. **Ship smoke tests** — one per public-API method, gated with
   `importorskip` so contributors without the optional dep still
   see the test suite pass
5. **NO production wiring** in this PR — keep the surface ≤ 200 LOC

### Phase 2 — Integration PR (load-bearing wiring)

Opens only after the scout PR has been audited + merged. Adds:

- Production call sites
- Observability `Metadata` field per the
  `portable-observability-before-wiring` skill
- Schema additions for any new output fields (Pydantic + TS + snapshot)
- Walk-forward / cross-validation if the dep produces a model

## Trigger conditions

- Adopting a new pip / npm / cargo dep that will be imported by
  production code (not just dev tooling)
- The dep has uncertain license / API stability / install footprint
- The user says "scout this library" / "let's try X before committing"
- The user describes a multi-PR adoption ("first ship the install,
  then the integration")

## Skip conditions

- Utility-library deps (`requests`, `pyyaml`, `python-dateutil`)
  with stable APIs and obvious licenses
- Library is already vendored elsewhere in the repo (just add the
  call site)
- The dep is dev-only (linter, formatter) — no scout overhead needed
- Phase 1 + Phase 2 will land in the same week with no opportunity
  for the scout PR to surface issues before integration

## Acceptance criteria for the scout PR

- Module-load assertion locks the API surface
- All public-API methods covered by ≥ 1 smoke test
- License verified verbatim from the published artifact
- CI install footprint disclosed in the PR body
- NO production wiring (a `grep` of the production code paths
  finds zero references to the new dep)

## QuantRank precedents

The 4 factor-library scouts in 2026-05-18..19 used this pattern:

- PR #110 (OSAP) → integration in PR #112 (Phase 4h)
- PR #114 (JKP scout) → integration deferred pending license review
- PR #119 (Qlib Alpha158 scout) → integration deferred to Phase 4j.1
- PR #121 (Kelly-Pruitt-Su IPCA scout) → integration deferred to
  Phase 4k.1

The scouts cost ~30 LOC each and surfaced the Qlib mlflow/cvxpy
transitive bloat (~180 MB) + the JKP CC-BY-NC license blocker
BEFORE the integration PR sunk effort into wiring that would later
be reverted.
