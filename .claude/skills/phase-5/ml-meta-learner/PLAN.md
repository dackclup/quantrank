# Phase 5 — ML Meta-Learner (PLAN)

> **Status**: PLAN — largest single scope (6-8 weeks per Research Report
> v1.0 §2.2). Defer execution; PLAN gates dedicated session series.
> **Conflict note**: was originally "Phase 5 Supabase hybrid" per PR
> #272 outline — that PLAN remains under `.claude/skills/phase-5/
> supabase-hybrid/PLAN.md`. Phase numbering needs resolution: this PLAN
> assumes the user pipeline's "Phase 5 = ML meta-learner" interpretation
> (per Research Report v1.0). If Supabase hybrid stays as Phase 5, this
> ML work is **Phase 6 (ML)** in the alternate numbering. Decision
> deferred to user.

## Goal

Per Research Report v1.0 §2 + Gu-Kelly-Xiu 2020 RFS 33(5):2223-2273
("Empirical Asset Pricing via Machine Learning"), build a secondary
META-LEARNER that takes the 9 pillar scores (post-JKP refactor) + 33
defense flags + market regime indicators as features, and outputs a
calibrated probability that the primary composite_score's BUY-rank
is correct for a 6M / 12M / 18M horizon.

**Critical**: this is META-LABELING per López de Prado AFML Ch. 3 — it
does NOT replace the composite score, it provides:
1. Position-sizing input (Kelly-fractional)
2. Confidence interval (via conformal prediction)
3. Explainability (SHAP) per stock

**Primary signal**: existing 8-pillar composite_score (Rule 16 sacred).
**Secondary signal**: this meta-learner.

## Files changed

- `compute/ml/__init__.py` (NEW)
- `compute/ml/triple_barrier.py` (NEW) — López de Prado AFML Ch. 3 CUSUM filter + vertical/horizontal barrier labeler. Custom Python ~150 LOC. **NO mlfinlab** (AGPL).
- `compute/ml/meta_labeling.py` (NEW) — XGBoost classifier wrapper; predicts P(triple-barrier label = +1 | features). Output for position sizing.
- `compute/ml/cv.py` (NEW) — Combinatorial Purged Cross-Validation. Custom ~150 LOC, sklearn TimeSeriesSplit base + purge/embargo.
- `compute/ml/conformal.py` (NEW) — MAPIE wrapper for prediction intervals (90% coverage).
- `compute/ml/shap_attribution.py` (NEW) — SHAP per-stock top-10 feature contribution.
- `compute/ml/training.py` (NEW) — orchestrator: load historical data, label via triple-barrier, train XGBoost, calibrate with MAPIE, serialize via joblib.
- `compute/ml/inference.py` (NEW) — load serialized model, predict on current snapshot, output to JSON.
- `compute/validation/multiple_testing.py` (NEW) — Benjamini-Hochberg FDR + Harvey-Liu-Zhu t>3.0 threshold.
- `compute/output/schemas.py` — `StockDetail.ml_meta_probability: float | None`, `ml_meta_interval_lo/hi: float | None`, `shap_top10: list[dict] | None`; `Metadata.ml_meta_*` (training date, OOS Sharpe, PBO, DSR).
- `compute/main.py` — wire inference per-ticker loop after composite.
- `pyproject.toml` — add deps: `xgboost>=2.0` (Apache 2.0), `mapie>=0.8` (Apache 2.0), `shap>=0.45` (MIT), `joblib>=1.4` (BSD-3).
- `.github/workflows/ml-retrain.yml` (NEW) — monthly retrain workflow with `workflow_dispatch` manual trigger.
- `frontend/lib/types.ts` + snapshot — triple lockstep
- `frontend/components/MLConfidenceCard.tsx` (NEW) — surface ML probability + interval + top-3 SHAP factors
- `tests/test_ml/*` (NEW) — ≥ 60 tests across all modules

## Schema delta

MINOR bump: `0.x.y` → `0.x+1.0-phase-ml`. Multiple additive fields,
non-breaking.

## Defense mode

N/A — ML meta-learner is a SECONDARY signal layered on top of
composite. Does NOT replace composite (Rule 16 sacred). Used for:
1. Position sizing (not rank)
2. Confidence interval display
3. SHAP explanation

## Tests

≥ 60 tests across:
- Triple-Barrier: CUSUM filter correctness, vertical/horizontal/time barrier hit-events, sample uniqueness weights
- Meta-Labeling: XGBoost classifier on synthetic separable / non-separable data
- CPCV: number of paths = C(N, k) per López de Prado; purge correctness
- Conformal: marginal coverage ≥ 90% on held-out
- SHAP: feature ordering stable across runs (deterministic with fixed seed)
- Multiple testing: BH FDR matches scipy reference implementation

## Production verification

- OOS Sharpe ≥ 0.5 above buy-and-hold S&P 500 baseline (NOT vs composite — vs SPY)
- PBO ≤ 0.5 + DSR > 0
- Benjamini-Hochberg FDR < 0.05 per feature
- Training time on GitHub Actions free tier (6h CPU, 14GB RAM): S&P 500 × 25 years × ~200 features ≈ 5-15 min XGBoost train. Verified before merge.
- Model artifact size: < 50MB → ship via Git LFS or split serialization

## Fallback triggers

- OOS Sharpe < 0.5 → defer ML; ship composite-only. Avramov-Cheng-Metzker 2023 caveat: ML α concentrated in microcaps; S&P 500 long-only expected α only 0.5-1.5%/yr.
- Training time > 5h on free tier → reduce universe to Top-100 by composite_score_adjusted (user pipeline authorization), or reduce features by SHAP-importance.
- MAPIE coverage < 80% on held-out → switch to quantile regression (sklearn GBM with quantile loss) as fallback.

## Acceptance checklist

- [ ] All 5 ML modules pure Python, no AGPL deps
- [ ] CPCV implementation matches López de Prado AFML Ch. 12 spec
- [ ] BH FDR < 0.05 for any new pillar+ML feature surface
- [ ] OOS Sharpe ≥ 0.5 vs SPY on rolling 5-year window
- [ ] Model retrain workflow `ml-retrain.yml` documented; monthly cadence
- [ ] `ml_meta_probability` surface in JSON + UI
- [ ] SHAP top-10 per stock + bias-checked (no protected-class features)
- [ ] `dependency-auditor`: PASS on xgboost/mapie/shap/joblib licenses
- [ ] `methodology-scientist`: LITERATURE-ANCHORED per Gu-Kelly-Xiu 2020, López de Prado AFML, Bailey-López de Prado 2014 DSR, Harvey-Liu-Zhu 2016 t-threshold

## License posture

- xgboost / lightgbm: Apache 2.0 ✅
- mapie: Apache 2.0 ✅
- shap: MIT ✅
- joblib: BSD-3 ✅
- **mlfinlab: AGPL ❌ — all Triple-Barrier / Meta-Labeling / Purged-CV custom**

## Performance honesty

Avramov-Cheng-Metzker 2023 Management Science 69(5) caveat:
> "Investments based on deep learning signals extract profitability
> from difficult-to-arbitrage stocks and during high limits-to-
> arbitrage market states. In particular, excluding microcaps,
> distressed stocks, or episodes of high market volatility considerably
> attenuates profitability."

**Realistic α contribution in S&P 500 long-only = 0.5-1.5%/yr**, NOT
the 3-5% paper claim of Gu-Kelly-Xiu on full CRSP universe. Disclaim
this in README + PR description.

## Estimated effort

**6-8 weeks focused dev** per Research Report v1.0 §Executive Summary.
Largest single PR scope; CI compute envelope is real concern. Defer
to dedicated session series after JKP refactor + survivorship-bias
fix + Lazy Prices land.
