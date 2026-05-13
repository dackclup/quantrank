---
name: student-t-hmm-fit
description: Fit a Student-t Hidden Markov Model on market regime indicators
  (VIX, term spread, credit spread) to identify risk-on vs risk-off regimes.
  Phase 7 portfolio-level overlay — affects composite weighting in different
  regimes.
---

# student-t-hmm-fit — STUB

## When to use

- Phase 7 (v1.5) regime + portfolio work
- After Phase 4-6 stabilize the per-ticker signals

## What to flesh out (TODO when implementing)

- Library: `hmmlearn` (Gaussian HMM) — extend with Student-t emission
  for fat-tail handling, OR use `pyhsmm` (Hierarchical HMM with
  built-in Student-t)
- Inputs: VIX time series + term spread (10y-3m) + credit spread
  (BAA-AAA OAS)
- States: 2-3 regimes (risk-on / risk-off / transition)
- Output: per-week regime probability + suggested composite weight
  adjustment
- Module location: `compute/scoring/regime_hmm.py`

## Acceptance criteria

- Regime persistence — average duration > 4 weeks (not high-frequency
  noise)
- Out-of-sample regime predictions stable (no rapid flipping)
- Documented impact on composite weighting (e.g., reduce momentum
  weight in risk-off regimes)

## Related

- Hamilton 1989 *Econometrica*
- Phase 7 schema: `Metadata.current_regime: "risk_on" | "risk_off" | "transition"`
- `phase-7/nco-portfolio-allocate` (consumer of regime signal)
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique 2.X"
