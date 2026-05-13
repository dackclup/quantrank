---
name: ipca-factor-fit
description: Fit Instrumented Principal Component Analysis (Kelly-Pruitt-Su 2019,
  2020) to the QuantRank universe — reduces the existing 8-pillar / N-feature
  set to ~5 latent factors that explain risk + return. Phase 4 factor consolidation.
---

# ipca-factor-fit — STUB

## When to use

- Phase 4 (v1.1 milestone) factor consolidation work
- After Phase 3 stabilizes (PR 3e merges, v1.0 tagged)

## What to flesh out (TODO when implementing)

- Library: probably `ipca` (PyPI) or custom JAX/numpy implementation
  if dependency footprint matters
- Inputs: per-ticker characteristics matrix (8 pillars + N features
  per stock per month)
- Outputs: K=5 factor loadings + factor returns time series
- Validation: in-sample R² + out-of-sample stability across rolling
  window
- Module location: `compute/features/ipca_factors.py`

## Acceptance criteria

- Reproduces KPS 2020 baseline R² on the same universe (≥30% in-sample)
- Factors interpretable (positive-Quality factor, etc.) — surface
  as a readable annotation on the rankings
- Out-of-sample IC > 0.05 on any shipped factor (Hou-Xue-Zhang 2020
  decay caveat applies — accept low IC, document it)

## Related

- Kelly-Pruitt-Su 2019 *RFS* / 2020 *JFE*
- `compute/features/` (new module location)
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique 2.X" (when added)
- SKILL.md Rule 14 — decay monitoring
