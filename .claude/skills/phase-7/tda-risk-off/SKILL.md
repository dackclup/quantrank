---
name: tda-risk-off
description: Apply Topological Data Analysis (persistent homology) to the
  cross-section of stock returns to detect topological-structure changes
  that precede risk-off regimes. Diagnostic / annotation only at first;
  may feed regime HMM in Phase 7.
---

# tda-risk-off — STUB

## When to use

- Phase 7 (v1.5) experimental regime work
- Complementary signal to the Student-t HMM — TDA captures
  geometric structure changes the HMM may miss

## What to flesh out (TODO when implementing)

- Library: `gudhi` or `ripser` for persistent homology
- Inputs: cross-section correlation matrix on a rolling window
- Method: compute persistent diagram → extract Betti numbers → look
  for regime-transition signatures (e.g., spike in number of
  persistent loops)
- Output: scalar "topological stress" index per week
- Module location: `compute/scoring/tda_risk.py`

## Acceptance criteria

- Reproduces a published TDA-finance example (e.g., Gidea-Katz 2018
  market crash detection)
- Out-of-sample stress index leads VIX by ≥1 week in known
  regime transitions (2008, 2020, etc.)
- Documented as experimental; DO NOT enter the active veto layer
  without further validation

## Related

- Gidea-Katz 2018 *Physica A*
- `phase-7/student-t-hmm-fit` (companion)
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique 2.X"
