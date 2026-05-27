# Research Report v1.0 — Calibration against QuantRank state
**Date**: 2026-05-27 · **Branch**: `claude/research-v1-planning` · **Base**: origin/main `6564999`

## Methodology

Walked the v1.0 deep-research recommendations report (uploaded
2026-05-27 by user) against current QuantRank state at
`PHASE_STATUS.md` §"Current state" (schema `0.10.5-phase4.5e`, defense
layer 33 declared = 7 vetoes + 26 annotates, tag `v1.3.0-phase4.5e`).

Three classification buckets per recommendation:
- ✅ **DONE** — already in `compute/scoring/` or `compute/ingest/`
- 🟡 **ACTIONABLE** — clear scope, license-clean, fits architecture
- ❌ **BLOCKED** — out of scope per user constraint or architecture conflict

## Findings — Recommendation × QuantRank state

### Section 1 — Factor combinations

| Report rec | QuantRank state | Verdict |
|---|---|---|
| JKP 13-theme refactor of 8 pillars | 8 pillars present (`compute/scoring/pillars.py`) but labeled `quality/value/growth/momentum/health/profitability/technical/risk` — NOT JKP-aligned. `profitability` + `quality` are partially redundant; JKP `tangency-portfolio` evidence subsumes `profitability` into `quality` | 🟡 ACTIONABLE — Phase 4.6 |
| Add `debt_issuance` pillar (Daniel-Titman 2006 + Pontiff-Woodgate 2008) | `net_issuance_top_decile` already an active veto (in `risk_overlay.py`) — but as a DEFENSE flag, not a positive PILLAR ranking signal | 🟡 ACTIONABLE — refactor existing veto into 2-sided signal |
| Add `investment` pillar (Cooper-Gulen-Schill 2008) | Not present | 🟡 ACTIONABLE |
| Quality (QMJ Asness 2019) | Already a pillar | ✅ DONE — refine definition in 4.6 |
| Value (B/M, E/P, CF/P composite) | Already a pillar | ✅ DONE |
| Momentum (12-1) | Already a pillar | ✅ DONE — high turnover caveat acknowledged |
| Residual momentum (Blitz 2011) | Not present; current `momentum` likely is total-return | 🟡 ACTIONABLE — but lower priority than JKP refactor |
| BAB / low-beta | `risk` pillar present | ⚠️ KEEP but note Novy-Marx-Velikov 2022 caveat in PLAN — BAB itself is microcap-driven, current `risk` pillar uses different signal anchor |
| Mispricing factors (Stambaugh-Yuan 2017) | Implicit in `manipulation_index` rollup | ✅ partially DONE |
| Climate / Green factor | Not present | ❌ SKIP (Pastor-Stambaugh-Taylor 2022 says future α negative) |

### Section 2 — ML methods

| Report rec | QuantRank state | Verdict |
|---|---|---|
| XGBoost meta-learner | Not present | 🟡 ACTIONABLE — Phase 5 |
| Triple-Barrier labeling | Not present; user constraint **NO mlfinlab (AGPL)** — must implement custom | 🟡 ACTIONABLE — Phase 5 (custom Python) |
| Conformal Prediction (MAPIE) | Not present | 🟡 ACTIONABLE — Phase 5 |
| SHAP feature attribution | Not present | 🟡 ACTIONABLE — Phase 5 |
| Combinatorial Purged CV | Not present; `pbo_dsr.factor_passes_gates()` exists but uses k-fold | 🟡 ACTIONABLE — Phase 5 validation |
| LSTM / Transformer | Per report Section 2.3 — SKIP (Gu-Kelly-Xiu: trees ≥ NN; CI GPU absent) | ❌ SKIP |

### Section 3 — Sentiment + Alternative Data

| Report rec | QuantRank state | Verdict |
|---|---|---|
| Lazy Prices (Cohen-Malloy-Nguyen 2020) 10-K text similarity | Not present (Phase 6 planned but `lazy-prices-detect/` stub only) | 🟡 ACTIONABLE — Phase 6 |
| Earnings call sentiment (FinBERT) | Not present | ❌ DEFER — Shobayo 2024 shows LR ≥ FinBERT; user said skip Phase 6 sentiment beyond Lazy Prices |
| Opportunistic insider classification (Cohen-Malloy-Pomorski 2012) | `form4_signals.py` has `insider_sell_cluster` + `c_suite_unusual_sell` annotates + 10b5-1 contamination filter; **opportunistic vs routine classification partially done** via the {S,D} transaction-code filter (PR #222) | ✅ partially DONE — extend with Larcker 3-flag below |
| Larcker 10b5-1 three-red-flags (Larcker-Lynch 2021 CGRI) | NOT present — current filter only suppresses 10b5-1 trades from opportunistic cohort, doesn't flag the 3-red-flag pattern (short cooling-off / single-trade / pre-earnings) | 🟡 ACTIONABLE — Phase 4.5e follow-on |
| Patent KPSS | Not present | ❌ DEFER — report Phase 9, low IC (~1-2%) |
| Reddit / WSB | Not present | ❌ SKIP (user constraint + ToS risk) |
| SEC EDGAR access logs (Drake-Roulstone-Thornock) | Not present | ❌ DEFER — 100GB+ data, high CI complexity |

### Section 4 — Regime detection

| Report rec | QuantRank state | Verdict |
|---|---|---|
| Student-t HMM 2-state | Not present | 🟡 ACTIONABLE — Phase 7 |
| TDA persistent homology | Not present | ❌ SKIP (user constraint + no peer-reviewed OOS 2022-2025) |

### Section 5 — Portfolio construction

| Report rec | QuantRank state | Verdict |
|---|---|---|
| NCO (López de Prado 2020) | Not present; current frontend shows ranking, no portfolio weights | 🟡 ACTIONABLE — Phase 7 |
| Leverage | N/A | ❌ SKIP (user constraint) |

### Section 6 — Defense layer

| Report rec | QuantRank state | Verdict |
|---|---|---|
| Larcker 3-flag 10b5-1 | NOT present | 🟡 ACTIONABLE — Phase 4.5e follow-on |
| Lazy Prices "changer" annotate | NOT present | 🟡 covered by Phase 6 Lazy Prices pillar |
| Auditor change | Already `auditor_change` annotate (PR #79) | ✅ DONE |
| SEC AAER / enforcement | Not present | 🟡 DEFER — manual SEC enforcement data |
| Short interest | Not present | 🟡 DEFER — paid feed (S3, Markit) |
| Whistleblower SEC tips | Not present | ❌ SKIP — rare + manual |

### Section 7 — Validation methodology

| Report rec | QuantRank state | Verdict |
|---|---|---|
| Combinatorial Purged CV | Not present; k-fold only | 🟡 ACTIONABLE — Phase 5 |
| Multiple-Hypothesis (Harvey-Liu-Zhu 2016 t>3.0 + BH FDR) | Not present | 🟡 ACTIONABLE — Phase 5 |
| Deflated Sharpe Ratio | Present (`pbo_dsr.py` PR #60) | ✅ DONE |
| **Survivorship bias fix** — historical S&P 500 membership | **NOT present** — `compute/ingest/universe.py` uses current 502 from Wikipedia scrape | 🟡 ACTIONABLE — **P0 per user pipeline** |
| Bootstrap confidence intervals | Not present | 🟡 DEFER — bundle with Phase 5 |
| Live forward test ≥ 12 months | Inherent — cron has been running since 2026-05-08 | ⚠️ Track |

## Final priority list (user pipeline order)

1. **Survivorship-bias fix** — P0, Section 7.4 of report. Static CSV approach (Wikipedia revision history scrape deferred — sandbox internet unreliable; static CSV with citation is acceptable per user pipeline). Phase 4.6 prefix.
2. **JKP-aligned 8-pillar refactor** — Phase 4.6. SCHEMA-BREAKING (MAJOR bump). Largest single PR. Replicate JKP TAXONOMY (concept, not data — CC BY-NC 4.0 excludes data use).
3. **Larcker 10b5-1 three-red-flags** — Phase 4.5e follow-on. Small additive extension of existing `form4_signals.py`.
4. **Lazy Prices pillar #9** — Phase 6. SEC EDGAR full-text + sklearn TF-IDF.
5. **Phase 5 ML meta-learner** — Largest scope; 6-8 weeks per report.

## Execution scope honesty

**Realistic single-session budget**: 1 (maybe 2) features end-to-end + 5 PLAN.md files + this calibration log + draft PRs.

The report itself estimates **20-25 weeks @ part-time** for all 5 features. Compressing into a single Claude Code session is impossible while preserving the user's "ห้าม half-done" + validation-gate rigor. **Decision**: execute Feature 1 (Survivorship-bias) fully; file PLAN.md drafts for 2-5; defer execution to subsequent sessions with explicit user authorization per feature.

## License posture verified

- `xgboost` / `lightgbm`: Apache 2.0 ✅ (Phase 5)
- `mapie`: Apache 2.0 ✅ (Phase 5 conformal)
- `shap`: MIT ✅ (Phase 5 attribution)
- `hmmlearn`: BSD-3 ✅ (Phase 7 regime)
- `PyPortfolioOpt`: MIT ✅ (Phase 7 NCO base; NCO itself custom ~200 LOC)
- `ripser.py`: MIT ✅ (Phase 7 TDA — but report says SKIP)
- `scikit-learn`: BSD-3 ✅ (Phase 6 TF-IDF)
- `mlfinlab`: AGPL ❌ — user-confirmed exclusion, all Triple-Barrier custom
- `gudhi`: GPL-3 ❌ — use ripser.py if TDA needed
- `finRL` / `qlib`: AGPL-style ❌ — exclusion
- `JKP factor returns data` (jkpfactors.com): CC BY-NC 4.0 ❌ — TAXONOMY-only (no copyright on concept), data replicated from Compustat/yfinance

## Hard-rule alignment check vs report

- Rule 16 (composite formula sacred) — JKP refactor MUST preserve formula semantics, only rename + remap pillar inputs
- Rule 9 (schema triple) — JKP refactor is MAJOR breaking change; need atomic Pydantic ↔ TS ↔ snapshot bump
- Rule 18 (observability-before-wiring) — all 5 features have observability surface that ships first
- McLean-Pontiff 32% decay (not 35%) — calibration confirmed in report
- Universe: S&P 500 only — Phase 8 expansion explicitly out of scope this session

## Stopping criteria invoked

After Feature 1 (Survivorship-bias) completes → assess remaining
context budget. If > 30% remaining, attempt Feature 3 (Larcker
10b5-1) which is the smallest scope. Features 2, 4, 5 ship as
PLAN.md-only drafts in this branch.
