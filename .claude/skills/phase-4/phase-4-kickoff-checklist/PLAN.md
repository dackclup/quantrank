# Phase 4 Kickoff Checklist (Phase 4 planning stub)

**Status**: Planning. Closes P0 audit gap (2026-05-14): the audit found that several Phase 4 UX decisions and library version locks were unresolved at v1.0 close. This PLAN is a single-document **decision registry** that captures everything an implementer needs to know before opening PR 4a.

## Purpose

A pre-flight checklist for the engineer (or future-Claude) starting Phase 4. Each item is either:
1. **DECISION LOCKED** — final answer, with rationale + reference
2. **VERIFY ON ENTRY** — re-check at Phase 4 entry (license status, library versions)
3. **OPEN** — explicit punt to a downstream PR with its own decision moment

The audit found these were scattered across 6+ PLANs and the WORKFLOW. Consolidating here.

---

## §1: UX terminology decisions (LOCKED 2026-05-14)

Three Phase 4 UX features had Option A/B/C/D mitigation tables for legal-naming concerns. **All three are now locked**:

| Feature | Locked option | Terminology | Why |
|---|---|---|---|
| `recommendation-badge` | **Option B** | `Bullish / Lean Bullish / Neutral / Cautious` | Same UX color affordance; avoids FINRA/SEC-regulated "Strong Buy / Buy / Hold / Sell" terminology; matches README "model output, not advice" framing |
| `loss-chance` | **Option D** | `Loss Chance %` + small "heuristic" footnote/tooltip | Preserves user's requested intuition; honest qualifier prevents implying backtest-calibrated probability; cross-links to Honest Limitations |
| `price-chart-enhancements` target line source | `fair_price.max` | (data field, not UX text) | Per `price-chart-enhancements/PLAN.md` "Mapping fields → chart elements" table; conservative vs `fair_price.high` (which includes outliers); both `Bullish` AND `Lean Bullish` tickers get the line per "Strong Buy / Buy" → Option B equivalent |

These locks override the Open Questions sections in the three feature PLANs. Each feature PLAN must be updated in PR 4 (this PR) to:
- Replace its "Recommended" pick with "**LOCKED** (per `phase-4-kickoff-checklist/PLAN.md`)"
- Remove now-resolved Open Questions
- Update code examples + Tailwind classes to use locked terminology

## §2: Schema versioning policy (LOCKED 2026-05-14)

Per `schema-versioning/PLAN.md` open questions:

| Question | Locked answer |
|---|---|
| Strip phase suffix at major tags? | **Yes** — `v1.0.0` clean. Phase suffix lives in changelog, not the version string. (`v1.0.0-phase3d` was the pre-release form; final tag is clean `v1.0.0`.) |
| Deprecated field retention? | **One minor cycle** — if v1.1 deprecates a field, keep both populated through v1.2; remove at v2.0. Matches v1-to-v1-1-migration/PLAN.md "additive-only" pattern (no v1.x removals at all). |
| `schema_check` breaking-change gate? | **CI-blocking** with `--allow-breaking` flag escape hatch — fails by default; requires explicit `--allow-breaking` to merge a removal/rename. Forces explicit acknowledgment + release notes. |

## §3: Migration & PR sequencing (LOCKED 2026-05-14)

Per `v1-to-v1-1-migration/PLAN.md`:

```
PR 4a — Workflow cache improvements         → tag v1.0.1-perf
PR 4b — Defense infrastructure (3 sections) → tag v1.0.2-defense
PR 4c — _avg_3y_roe per-year equity (#11)   → tag v1.0.3-fix
PR 4d — recommendation-badge                → tag v1.1.0-rc1 (first feature; schema additive)
PR 4e — loss-chance                         → tag v1.1.0-rc2
PR 4f — price-chart-enhancements (4.1)      → tag v1.1.0-rc3 (depends on 4d)
PR 4g — 8-K Tier-2 re-enable (#14)          → tag v1.1.0-rc4 (FP-rate gated; see §6)
PR 4h — OSAP integration                    → tag v1.1.0-rc5
PR 4i — JKP integration                     → tag v1.1.0-rc6
PR 4j — Qlib Alpha158                       → tag v1.1.0-rc7
PR 4k — IPCA factor                         → tag v1.1.0-rc8
PR 4l — Phase 4 acceptance criteria pass    → tag v1.1.0-phase4 (final)
```

The `-rc` series during Phase 4 makes intermediate progress observable (each PR gets its own preview tag). Final `v1.1.0-phase4` lands when WORKFLOW.md Phase 4 Acceptance Criteria all pass.

## §4: Library version locks (VERIFY ON PHASE 4 ENTRY)

Re-check these at PR 4a open:

| Library | Current pin (last verified) | Phase 4 expectation | Action if changed |
|---|---|---|---|
| `edgartools` | `2.30.x` | Bump to latest 2.x if API stable | Run integration tests; if break → file separate PR |
| `pandas` | `2.2.x` | Stay on 2.2 | Don't bump to 3.0 mid-Phase-4 |
| `pydantic` | `2.6.x` | Stay on 2.6 | Don't bump to 3.0 mid-Phase-4 |
| `yfinance` | `0.2.55` (locked in PR #44) | **DO NOT BUMP** | yfinance breaking changes are common; locked pin protects Phase 1 ingest |
| `Next.js` | `14.2.x` | Bump to 16.x in chore PR (per issue #41/#31) | **Separate PR**, not Phase 4 work |
| `openassetpricing` | `>=0.1` (Phase 4 new) | Pin to first stable version after install | Test against current release |
| `pyqlib` | `>=0.9` (Phase 4 new) | Pin to first stable | Heavy install; benchmark CI first |
| `ipca` | `>=0.2` (Phase 4 new) | Pin to first stable | Small install |
| `pypbo` | `>=0.2` (Phase 4 new, per `defense-infrastructure/PLAN.md`) | Pin to first stable | Tiny |

Phase 4 entry checklist:
- [ ] `pip-audit` clean (no known CVEs in current pins)
- [ ] `pip list --outdated` reviewed (note: don't auto-bump majors)
- [ ] `requirements.txt` + `pyproject.toml` in sync after any pin update

## §5: License re-verification (VERIFY ON PHASE 4 ENTRY)

Per RESEARCH_FINDINGS.md §"License Audit". Re-verify each before integration:

| Library | License | Phase 4 status | Re-verify by |
|---|---|---|---|
| `openassetpricing` | MIT | ✅ green | Check PyPI page on PR 4h open |
| JKP factor returns CSV | CC BY-NC 4.0 | ✅ green (non-commercial OK) | Check jkpfactors.com terms on PR 4i open |
| `bkelly-lab/ipca` | MIT | ✅ green | PR 4k |
| `pyqlib` | MIT | ✅ green | PR 4j |
| `pypbo` | MIT | ✅ green | PR 4b |
| `mlfinlab` | **All-rights-reserved** | ❌ BLOCKED — do not depend | n/a (Phase 5 already plans reimplementation) |

If any drops from "green" → file a blocking issue + revert to fallback (Option A — DIY only for that pillar).

## §6: 8-K Tier-2 re-enable gate (LOCKED 2026-05-14)

`_EIGHT_K_DEFENSES_ENABLED = False` was set at Phase 3 because going-concern FP rate was 10.8% (Mayew 2015 published target: 1-3%). After PR #48 + universe-wide cache refresh: **FP rate dropped to 1.0%** (verified at workflow run #32).

Gate for PR 4g (re-enable 8-K Tier-2 defenses):
- [ ] Going-concern FP rate ≤ **5%** measured on latest production rankings.json (formal threshold; replaces "informal target" of prior cycle)
- [ ] No regression in Tier-1 defense activation counts (Altman / Sloan / NSI ±10%)
- [ ] 8-K event-driven path runs to completion in CI without timeout (currently disabled means the path is dormant; re-enable surfaces any latent bugs)

If FP rate >5% at PR 4g entry → defer the flip; iterate on `going-concern-phrase-refine/PLAN.md` (Option C FinBERT) first.

## §7: Phase 4 acceptance metric (LOCKED 2026-05-14)

WORKFLOW.md Phase 4 Acceptance Criteria currently has:

> [ ] Composite alpha lift ≥ 0.3% on backtest (vs Phase 3 baseline)

This criterion is **unreachable in Phase 4** because backtest infrastructure is Phase 5 foundational work (per `backtest-infrastructure/PLAN.md`). Locked replacement:

> [ ] **Each library factor passes IC > 0.01 on walk-forward rolling 12-month evaluation** (per `defense-infrastructure/PLAN.md` §3)

This is a **per-factor** gate, not a composite gate. It's testable without full walk-forward + purged + embargoed CV (which lands in Phase 5).

Full composite alpha lift gate moves to **Phase 5 acceptance criteria** when backtest infrastructure is in place.

WORKFLOW.md §"Phase 4 Acceptance Criteria" must be updated in this PR (4) to reflect the change. See `WORKFLOW.md` change list below.

## §8: Defense Acceptance Matrix (LOCKED 2026-05-14)

Consolidating defense gates scattered across `WORKFLOW.md`, `SKILL.md` Rule 13, `defense-infrastructure/PLAN.md`, and individual feature PLANs:

| Defense | Mode | Activation gate | Veto status |
|---|---|---|---|
| Altman Z″ < 1.1 | Active veto | Standard Phase 0 spec | ✅ blocks Top-N badge |
| Sloan accruals top decile | Active veto | Standard Phase 0 spec | ✅ blocks Top-N badge |
| Net issuance top decile | Active veto | Standard Phase 0 spec | ✅ blocks Top-N badge |
| Going-concern (10-K phrase) | Active veto | Mayew 2015 reimplementation | ✅ blocks Top-N badge |
| `data_quality_input_corruption` | Active veto | Audit #6 (PR #48 expansion) | ✅ blocks Top-N badge |
| Beneish M-score (Phase 3e) | Annotate-only | `beneish_high` valuation_warning | ⚠️ warns, no veto |
| Dechow F-score (Phase 3e) | Annotate-only | `dechow_high` valuation_warning | ⚠️ warns, no veto |
| Cross-source disagreement (Phase 4b) | Annotate-only | 5% market-cap delta | ⚠️ warns, no veto |
| IC-decay alert (Phase 4b) | Monitor + manual review | 6-month threshold breach (live 2026-06-13, #75 §3) | ❌ no production veto; `decay_report.json` + `/analysis` surface; `alert` suppressed until ≥12 monthly IC pts/pillar |
| PBO + DSR (Phase 4b) | Pre-integration gate | PBO ≤ 0.5 AND DSR > 0 per factor | ✅ veto factor from being added to composite |

**Promotion path**: a Phase 4+ Annotate flag may promote to Active Veto when:
1. False-positive rate ≤ 5% measured against latest universe
2. Academic citation supports the threshold (per `WORKFLOW.md` "When to Add a Defense")
3. Sector-specific exclusions documented (e.g., Sloan + Financials)
4. Schema bumps to next **minor** (per `schema-versioning/PLAN.md`)

`beneish_high` and `dechow_high` are candidates for promotion in Phase 4 if FP rates check out. Defer the decision to a focused PR after PR 4g — not part of this kickoff.

## §9: WORKFLOW.md change list (executed in this PR)

1. **Replace** "Composite alpha lift ≥ 0.3%" with "Each library factor IC > 0.01 walk-forward" (§7 above)
2. **Add** formal going-concern FP rate gate ≤5% for PR 4g (§6 above)
3. **Add** Defense Acceptance Matrix section (§8 above; new subsection under Phase 4)
4. **Add** cross-references to the 6 new Phase 4 PLANs:
   - `osap-integration/PLAN.md`
   - `jkp-integration/PLAN.md`
   - `workflow-cache-improvements/PLAN.md`
   - `defense-infrastructure/PLAN.md`
   - `phase-4-kickoff-checklist/PLAN.md` (this file)
   - `issue-remapping/PLAN.md`

## §10: Open issues triage (per `issue-remapping/PLAN.md`)

See `issue-remapping/PLAN.md` for the full mapping of GitHub issues #7 / #10 / #11 / #14 / #15 / #16 / #17 / #18 / #31 / #41 to Phase 4 PRs or deferred phases.

Summary:
- **Close immediately**: #10 (fixed in PR #49 audit #6 work)
- **Map to Phase 4 PRs**: #7 / #11 / #14 / #15 / #16 / #17 / #18
- **Defer to chore PR (not Phase 4)**: #31 / #41 (Next.js 14→16 bump; cosmetic; separate)

## Implementer's pre-flight checklist (run before PR 4a open)

- [ ] Read this PLAN end-to-end
- [ ] Run `python -m compute.output.schema_check` (currently passing — no drift since PR #57)
- [ ] Run `pytest tests/ -m "not network"` (currently 526 passing — should match)
- [ ] Run `cd frontend && npx --no -- next build && npx --no -- tsc --noEmit` (should be clean)
- [ ] Verify v1.0.0 tag exists: `git tag -l v1.0.0` returns `v1.0.0`
- [ ] Re-verify library licenses per §5 above
- [ ] Re-verify library versions per §4 above
- [ ] Open PR 4a branch: `git checkout -b feat/phase-4a-cache-improvements`

## Effort

This PLAN doesn't have implementation effort — it's a documentation deliverable. Time to write + iterate: ~3 hours. LOC: ~400 (docs only).

The downstream PRs it enables are estimated in:
- `docs/PHASE_4_8_EFFORT_BACKFILL.md` (rough)
- Each PLAN's own "Effort estimate" section (refined per-feature)

## Open questions (none — all locked above)

This PLAN's purpose is to close open questions, not generate them.
