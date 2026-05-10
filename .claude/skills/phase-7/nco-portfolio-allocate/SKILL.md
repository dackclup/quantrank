---
name: nco-portfolio-allocate
description: Implement Nested Clustered Optimization (NCO, López de Prado 2019)
  for portfolio weight allocation across the QuantRank Top-N. Replaces the
  current "Top-5 with equal weights" implicit allocation with a regime-aware
  optimizer that respects the covariance structure.
---

# nco-portfolio-allocate — STUB

## When to use

- Phase 7 (v1.5) portfolio construction work
- After regime HMM signal is available
- Migrates QuantRank from "ranking + Top-N badge" to
  "ranking + recommended weights"

## What to flesh out (TODO when implementing)

- Library: native implementation per López de Prado 2019, or
  `RiskMetrics`-style covariance shrinkage as input
- Method: hierarchical clustering on the correlation matrix +
  intra-cluster optimization + inter-cluster optimization
- Inputs: top-N stock list + their return covariance matrix
  (estimated from price history)
- Outputs: per-stock weight summing to 1.0
- Module location: `compute/scoring/nco_portfolio.py`

## Acceptance criteria

- Reproduces López de Prado 2019 numerical example
- Weights respect covariance — concentrated names get less weight
  than diversified names
- Out-of-sample Sharpe ratio compares favorably to equal-weight
  baseline (low bar — both are simple)
- Surface as `StockSummary.suggested_weight: float | None`

## Related

- López de Prado 2019 — NCO + machine learning portfolio
- Phase 7 schema bump
- `phase-7/student-t-hmm-fit` (regime-conditional weighting)
- SKILL.md Rule 15 — performance ceiling honesty (no claims of
  ">5% net" without 10y WF)
