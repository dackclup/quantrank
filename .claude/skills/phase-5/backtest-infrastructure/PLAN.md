# Backtest Infrastructure (Phase 5 planning stub)

**Status**: Planning. Closes the audit-#7 gap: Phase 5 ML PLANs (meta-label, conformal, triple-barrier, shap) reference rolling-window validation but no PLAN exists for the infrastructure they share.

## Purpose

Phase 5 introduces ML layers that NEED validation discipline:
- LightGBM LambdaRank meta-learner
- Triple-Barrier labels (López de Prado 2018 Ch. 3)
- Conformal Prediction intervals (Angelopoulos-Bates 2021)
- SHAP explanations

Without rolling-window backtest infrastructure, these layers can't be **validated** before they touch the production composite. This PLAN specifies the shared infra all four ML stubs depend on.

## Spec

A reusable backtest harness that:
1. Walks forward in time using purged + embargoed splits (López de Prado Ch. 7)
2. Computes IC, Sharpe, max drawdown, calibration metrics per fold
3. Surfaces a deflated Sharpe ratio (Bailey-López de Prado 2014)
4. Computes the probability of backtest overfitting (Bailey et al. 2016 PBO)
5. Emits a `backtest_report.json` per ML feature for review

## Architecture

| Layer | Module | Purpose |
|---|---|---|
| Time-series cross-validation | `compute/backtest/walk_forward.py` | Yield purged + embargoed (train, test) date splits |
| Label construction | `compute/backtest/triple_barrier.py` (per `phase-5/triple-barrier-label/PLAN.md`) | Generate up / down / horizon labels from price series |
| Metrics | `compute/backtest/metrics.py` | IC (rank IC + Pearson), Sharpe, deflated Sharpe, max DD, calibration |
| PBO | `compute/backtest/pbo.py` | Probability of backtest overfitting per Bailey 2016 |
| Report writer | `compute/backtest/report.py` | Emit `backtest_report_<feature>.json` |
| Runner | `compute/backtest/__main__.py` | `python -m compute.backtest --feature meta_label` |

LOC estimate: ~600-800 LOC. This is the foundation; individual Phase 5 features consume it.

## Walk-forward design

Per López de Prado 2018 Ch. 7:

```
Timeline:  ┌─train─┐ embargo ┌─test─┐ ...
           Year N    1 month   Year N+1

Repeat sliding the window forward by 1 month or 1 quarter.

For each split:
  1. Fit model on train data
  2. Predict on test data
  3. Compute fold metrics
  4. Aggregate across folds
```

**Purge**: any sample whose label-horizon overlaps the test set's date range is removed from train (prevents look-ahead via label leakage).

**Embargo**: a buffer (e.g., 1-3 weeks) between train and test prevents close-in autocorrelation from leaking signal.

## Metrics

Per ML feature, the backtest reports:

| Metric | Spec | Target |
|---|---|---|
| Rank IC (per fold) | Spearman corr(prediction, future_return) | > 0.02 mean, > 0.5 win rate |
| Pearson IC (per fold) | Pearson corr | informational |
| Sharpe (long-short portfolio) | Mean(returns) / Std(returns) × √252 | > 0.7 |
| Deflated Sharpe | Bailey-López de Prado 2014 — corrects for backtest data-snooping | > 0.5 |
| Max drawdown | peak-to-trough | < 25% |
| Probability of backtest overfitting | Bailey et al. 2016 (PBO) | < 0.5 |
| Calibration (for conformal) | Coverage of predicted intervals | within ±5% of nominal |

A feature **fails** if Deflated Sharpe < 0 OR PBO > 0.5. The feature is **excluded** from the composite until fixed.

## Phase 5 ML feature integration

Each Phase 5 ML PLAN consumes this infra:

| Phase 5 stub | Backtest infra usage |
|---|---|
| `triple-barrier-label/PLAN.md` | Implements the label generator (`compute/backtest/triple_barrier.py`) |
| `meta-label/PLAN.md` | LightGBM LambdaRank — runs through `walk_forward.py` |
| `shap-explain/PLAN.md` | SHAP runs on the meta-label model — no separate backtest |
| `conformal-predict/PLAN.md` | Conformal calibration sets — needs the walk-forward splits but uses calibration metrics |

Hard dependency: **this PLAN must implement first**, then the 4 Phase 5 stubs can implement in parallel.

## Cost considerations

A full walk-forward backtest over 5 years of S&P 500 with monthly rebalance × ~10 ML feature variations:

| Step | Compute time | Notes |
|---|---|---|
| Single fold (train + test) | ~30 sec | LightGBM is fast |
| ~60 folds (5y × 12 months) | ~30 min | per feature variation |
| ~10 feature variations | ~5 hours | per backtest sweep |
| Full hyperparameter sweep | ~50 hours | optional, monthly run |

GitHub Actions free tier: 6 hr/job. Backtest needs to be a **separate workflow** (`backtest-monthly.yml`) not the weekly compute workflow. Run on a schedule (1st of month, 03:00 UTC — already in `compute-monthly.yml` skeleton).

## What this PLAN doesn't cover

- **Live production inference** (already in the per-ticker compute loop)
- **Hyperparameter search** (separate stub if needed — Phase 5+)
- **Cross-feature interactions** (Phase 6+ ensemble integration)

## Test plan

- [ ] Synthetic walk-forward test: known-good return series → IC ~1.0
- [ ] Purge test: label horizon overlap correctly removed
- [ ] Embargo test: 0-day embargo + 30-day embargo produce different splits
- [ ] PBO test: random labels → PBO ~0.5 (no signal)
- [ ] Deflated Sharpe: Bailey-López de Prado 2014 example matches paper

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| Walk-forward CV harness | ~200 | 2 days |
| Metrics (IC + Sharpe + DD + DSR + PBO) | ~200 | 2 days |
| Triple-barrier label generator | ~150 | 1 day (overlaps `triple-barrier-label/PLAN.md`) |
| Report writer + runner | ~100 | 1 day |
| Backtest workflow (`backtest-monthly.yml`) | ~50 | 0.5 day |
| Tests (golden + synthetic) | ~200 | 2 days |
| **Total** | **~900 LOC** | **~8-9 days** |

This is THE foundation for Phase 5. Budget accordingly.

## Open questions

1. Should we vendor mlfinlab (AGPL 2018) or re-implement? Per `docs/RESEARCH_FINDINGS.md`: **re-implement** — AGPL incompatible with project license. Triple-Barrier + DSR + PBO are all paper-implementable in <100 LOC each.
2. Storage: where do backtest reports live? Proposed: `frontend/public/data/backtest/<feature>.json` — same Vercel-served pattern as production data
3. Cadence: monthly (default) vs quarterly vs ad-hoc per PR?
4. Failure threshold: hard-block (PBO > 0.5 → CI fail) or annotate-only (warn + record)?
