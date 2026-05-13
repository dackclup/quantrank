---
name: beneish-mscore-debug
description: For a single ticker, compute Beneish M-Score (8-ratio earnings
  manipulation indicator) with all intermediate ratios visible. Use during
  Phase 3e Tier-3 implementation and post-merge to triage stocks flagged
  beneish_high (annotate-only, ≥-1.78 threshold per Beneish 1999).
---

# beneish-mscore-debug — STUB

## When to use

- Phase 3e Tier-3 implementation
- Triage of stocks flagged `beneish_high` annotate flag
- Comparison vs Altman to differentiate distress (Altman) from
  manipulation (Beneish)

## What to flesh out (TODO when implementing)

- Implement: 8 Beneish ratios (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI,
  TATA) + composite M-score
- Single-ticker probe: `python helper.py ENRN`
- Output: 8 intermediate ratios + M-score + threshold band
- Per-ratio interpretation (e.g., DSRI > 1.46 → receivables growing
  faster than sales)

## Acceptance criteria

- M-score formula matches Beneish 1999 (5-ratio variant) or 2013
  (8-ratio with TATA)
- Threshold of -1.78 for "manipulation likely" annotate flag
- Validated against known cases (Enron 1999, Worldcom 2001)

## Related

- Beneish 1999 *FAJ* — 5-variable M-score
- Beneish 2013 — full 8-variable variant
- `compute/scoring/risk_overlay.py` (will add `compute_beneish_mscore`)
- Reason taxonomy: add `beneish_high` to `SKIP_REASONS` (24 → 25)
