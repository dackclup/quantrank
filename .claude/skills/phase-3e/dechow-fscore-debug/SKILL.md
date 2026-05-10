---
name: dechow-fscore-debug
description: For a single ticker, compute Dechow F-Score (predicting probability
  of restatement / earnings misstatement) with intermediate components exposed.
  Use during Phase 3e Tier-3 implementation. Annotate-only, complements Beneish
  for accruals-quality signal.
---

# dechow-fscore-debug — STUB

## When to use

- Phase 3e Tier-3 implementation
- Triage of stocks flagged `dechow_f_high` annotate flag
- Comparing Dechow vs Beneish vs Altman for stocks flagged by
  multiple defenses

## What to flesh out (TODO when implementing)

- Implement: 7 Dechow components (RSST accruals, Δreceivables,
  Δinventory, soft assets %, Δcash sales, ΔROA, actual issuance)
- F-score = -7.893 + 0.79 * RSST + 2.518 * ΔRec + ...
- Probability of misstatement via logistic transformation
- Single-ticker probe: `python helper.py XYZ`

## Acceptance criteria

- Formula matches Dechow-Ge-Larson-Sloan 2011 *Contemporary Accounting Research*
- Annotate threshold: F-score > 1.85 → top-decile risk
- Validated against the Dechow paper's reported 28% restatement rate
  in top decile

## Related

- Dechow-Ge-Larson-Sloan 2011 *CAR*
- `compute/scoring/risk_overlay.py` (will add `compute_dechow_fscore`)
- `phase-3e/beneish-mscore-debug` (companion)
- Reason taxonomy: add `dechow_f_high` to `SKIP_REASONS`
