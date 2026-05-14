# Phase 4-8 Effort Estimates (audit-#7 backfill)

**Status**: Reference table. Per-PLAN backfills land progressively in
their respective stubs.

## Purpose

The 2026-05-14 planning audit found that all Phase 4-8 planning stubs at
`.claude/skills/phase-N/<name>/PLAN.md` had clear specs but **no
concrete effort estimates** (LOC + calendar time). This made scheduling
impossible. This doc backfills the estimates for all 28 Phase 4-8 stubs
in one place, sized at "rough order of magnitude — verify when each
stub gets promoted to a real skill."

Per-stub PLAN files should copy the row into their own "Effort
estimate" section when implementation actually begins; this doc stays
as the canonical cross-reference.

## Methodology

LOC scoped to **production code + tests**, NOT docs / planning. Time
estimates assume one experienced contributor working ~5 productive
hours/day.

Phase total ≠ sum of stubs — some stubs share infrastructure (e.g.,
Phase 5 ML stubs all use `backtest-infrastructure`).

## Phase 4 — Factor Consolidation + v1.0 polish

| Stub | LOC | Days | Notes |
|---|---|---|---|
| `8k-events-pre-cache` | ~150 | 1.5 | gate behind `_EIGHT_K_DEFENSES_ENABLED` flip; mostly cache-warming utility |
| `alpha158-fit` | ~400 | 4 | Qlib's Alpha158 feature set re-implementation. Vendoring vs. dependency decision pending |
| `chronic-slow-ticker-special-case` | ~80 | 0.5 | small ingest tweak for known-bad CIKs |
| `going-concern-phrase-refine` | ~120 | 1 | Option C (FinBERT) only if FP rate still > 5% post-Option-B |
| `ipca-factor-fit` | ~350 | 4 | 5-latent-factor IPCA fit; needs WRDS data OR free fallback. Complex |
| `loss-chance` | ~180 | 1.5 | new |
| `price-chart-enhancements` | ~180 (Phase 4.1) / +50 (4.2) / +200 (4.3) | 1 / 0.5 / 2 | 4.1 immediate, 4.2 5Y daily ingest, 4.3 intraday |
| `recommendation-badge` | ~230 | 2 | new |
| `v1-to-v1-1-migration` | ~100 | 1.5 | scaffolding (this doc + schema_check extension + changelog) |
| `schema-versioning` | ~130 | 1.5 | new — breaking-change CI guard |
| **Phase 4 subtotal** | **~2,000 LOC** | **~18 days** | |

Acceptance criteria from WORKFLOW.md Phase 4 section apply on top of these.

## Phase 5 — ML meta-learner + SHAP + Conformal

| Stub | LOC | Days | Notes |
|---|---|---|---|
| `backtest-infrastructure` (FOUNDATIONAL) | ~900 | 8-9 | new — purged + embargoed CV, Sharpe, DSR, PBO. ALL Phase 5 features depend on this |
| `triple-barrier-label` | ~150 | 1 | López de Prado 2018 Ch. 3. Re-implement under MIT |
| `meta-label` | ~400 | 4 | LightGBM LambdaRank wrapped in backtest harness |
| `shap-explain` | ~250 | 2-3 | SHAP TreeExplainer on the meta-label model |
| `conformal-predict` | ~300 | 3 | Inductive conformal prediction (Angelopoulos-Bates 2021) |
| **Phase 5 subtotal** | **~2,000 LOC** | **~18-19 days** | |

Hard dependency: backtest-infra MUST land first.

## Phase 6 — Sentiment v2

| Stub | LOC | Days | Notes |
|---|---|---|---|
| `finbert-score` | ~250 | 2-3 | FinBERT on 10-K/8-K text; vendoring decision (model size ~440MB) |
| `lazy-prices-detect` | ~200 | 2 | Cohen-Malloy-Nguyen 2020; text similarity year-over-year |
| `whisper-transcribe` | ~400 | 3-4 | earnings call audio → text; cost question (Whisper API or local) |
| **Phase 6 subtotal** | **~850 LOC** | **~7-9 days** | |

## Phase 7 — Regime + Portfolio v2

| Stub | LOC | Days | Notes |
|---|---|---|---|
| `student-t-hmm-fit` | ~300 | 3 | Student-t HMM regime model |
| `nco-portfolio-allocate` | ~250 | 2-3 | NCO portfolio construction (López de Prado 2018) |
| `tda-risk-off` | ~350 | 4 | Topological data analysis for risk-off signal |
| **Phase 7 subtotal** | **~900 LOC** | **~9-10 days** | |

## Phase 8 — Universe expansion

| Stub | LOC | Days | Notes |
|---|---|---|---|
| `microcap-skip` | ~50 | 0.5 | filter rule for too-small caps |
| `universe-expand-sp1500` | ~200 | 2 | universe ingest expansion |
| **Phase 8 subtotal** | **~250 LOC** | **~2.5 days** | |

## Grand total

| Phase | LOC | Days |
|---|---|---|
| Phase 4 | ~2,000 | ~18 |
| Phase 5 | ~2,000 | ~18-19 |
| Phase 6 | ~850 | ~7-9 |
| Phase 7 | ~900 | ~9-10 |
| Phase 8 | ~250 | ~2.5 |
| **v1.0 → v2.0 total** | **~6,000 LOC** | **~55-60 days** |

Calendar (full-time, single contributor): **~11-13 weeks**.

Calendar (mobile-only, 1-3 hrs/day per WORKFLOW.md): **~3-4 months**.

This aligns with WORKFLOW.md's headline "Phase Overview" table which
estimates "Option B to v2.0: 32-37 working days, calendar 7-8 weeks"
— that estimate counted only the core Option B work, not the full
v2.0 scope including UX trio + scaffolding. The +20-25 days here is
the difference between "core ML pipeline" and "complete v2.0 product
including UX, governance, observability."

## Caveats

1. All estimates **rough order of magnitude**. Variance ±30%.
2. Doesn't account for:
   - PR review iterations (typically +10-20%)
   - SEC EDGAR throttling cost on Phase 4-6 ingest extensions
   - License re-verification per `docs/RESEARCH_FINDINGS.md` (e.g.,
     re-checking if mlfinlab moves off AGPL)
3. Acceptance criteria in WORKFLOW.md per phase are the hard gates;
   these estimates assume those gates pass first try
4. Stubs that don't have an estimate here = not yet planned. File a
   PR to add the row.

## Maintenance

When a stub graduates from planning (PLAN.md) to active development
(SKILL.md), update its row here to the actual outcome. The diff
between estimate and actual feeds back into future calibration.
