---
name: meta-label
description: Implement López de Prado meta-labeling — train a secondary
  classifier on top of the primary model (composite ranking) to predict
  whether the primary's signal will be profitable. Phase 5 ML stack.
---

# meta-label — STUB

## When to use

- Phase 5 ML meta-learner work, after triple-barrier-label provides
  the targets

## What to flesh out (TODO when implementing)

- Primary model: existing 10-pillar composite (already produces a
  rank for every ticker every week)
- Meta-features: a subset of the 158 Alpha158 features + IPCA
  factor exposures + recent realized return
- Meta-target: triple-barrier label (1 / -1 / 0)
- Training: rolling window, no leakage past asof date
- Output: a calibrated probability `p_profitable` per stock per week
- Module location: `compute/ml/meta_label.py`

## Acceptance criteria

- Out-of-sample AUC > 0.55 on the meta-target (low bar; 0.5 is
  random)
- Calibration: predicted probability ≈ realized rate (Platt or
  isotonic)
- No look-ahead bias (verified by lag check)

## Related

- López de Prado 2018 Ch.4
- `phase-5/triple-barrier-label`
- `phase-5/conformal-predict` (uncertainty quantification on top)
