---
name: shap-explain
description: Compute SHAP (Shapley Additive Explanations) values per stock for
  the Phase 5 meta-label classifier so users can see WHY a stock got its
  predicted probability. Surfaces the top contributing features in the UI.
---

# shap-explain — STUB

## When to use

- Phase 5 after meta-label classifier ships
- User-trust-signal work — answers "why is XYZ predicted profitable?"

## What to flesh out (TODO when implementing)

- Library: `shap` (Lundberg)
- Per-stock per-week: top 5 features contributing to the
  meta-label probability (positive + negative)
- Output: `StockDetail.ml_shap_top_features: list[{feature, value, shap_value}]`
- Module location: `compute/ml/shap_explain.py`
- UI: extend the ml-section card with a "Why this prediction"
  expandable

## Acceptance criteria

- SHAP values are computed reproducibly (fixed random seed)
- Sum of all SHAP values + base_value = predicted probability
  (additivity invariant)
- Top-5 surfacing is human-readable (feature names in plain English,
  not column codes)

## Related

- Lundberg-Lee 2017 NIPS
- `phase-5/meta-label`
- `frontend/components/MlExplanationCard.tsx` (Phase 5 component)
