---
name: conformal-predict
description: Wrap the Phase 5 meta-label classifier with conformal prediction
  to produce calibrated prediction intervals (e.g., 90% prediction sets) per
  stock. Adds honest uncertainty quantification to the ML layer.
---

# conformal-predict — STUB

## When to use

- Phase 5 after meta-label classifier is trained
- Specifically when the user wants "we're 90% sure this stock is
  profitable" rather than just a point probability

## What to flesh out (TODO when implementing)

- Library: `mapie` (MAPIE — Model Agnostic Prediction Interval
  Estimator) or `crepes`
- Apply conformal layer to the meta-label classifier's
  probability output
- Output per stock: prediction interval (e.g., [0.45, 0.78]) at the
  configured confidence level
- Module location: `compute/ml/conformal.py`

## Acceptance criteria

- Empirical coverage matches nominal level on out-of-sample data
  (e.g., 90% of stocks where actual outcome falls within predicted
  interval)
- Interval width is informative (not all-or-nothing [0, 1])
- Surface in `StockDetail.ml_uncertainty` (Phase 5 schema bump)

## Related

- Vovk-Gammerman-Shafer *Algorithmic Learning in a Random World*
- `phase-5/meta-label`
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique" on conformal
