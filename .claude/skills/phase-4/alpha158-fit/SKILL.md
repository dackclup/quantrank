---
name: alpha158-fit
description: Compute the 158 Microsoft Qlib Alpha158 features for the QuantRank
  universe and add them to the feature set. Phase 4 factor consolidation —
  adds technical / momentum signals that complement the fundamental pillars.
---

# alpha158-fit — STUB

## When to use

- Phase 4 (v1.1 milestone)
- After IPCA factor work to evaluate whether Alpha158 features add
  marginal IC beyond the latent factors

## What to flesh out (TODO when implementing)

- Library: `qlib` (Microsoft's Quantitative Investment Platform) or
  port the 158 feature definitions to native pandas
  - Caveat: `qlib` has a heavy footprint — port may be lighter
- Inputs: OHLCV time series (we have `frontend/public/data/stocks/history/<TICKER>.json`
  with 252 days)
- Outputs: 158-column DataFrame indexed by (ticker, date)
- Module location: `compute/features/alpha158.py`

## Acceptance criteria

- 158 features computed without errors on the full universe
- Out-of-sample IC for shipped features > 0.02 (low bar — most decay)
- Per-feature description in module docstring (so users see what
  each feature represents)
- Tests covering the 5-10 most-cited features (e.g., RSI, MACD,
  Bollinger Band ratios)

## Related

- Microsoft Qlib documentation (`https://qlib.readthedocs.io/`)
- `compute/features/` (new module location)
- `phase-4/ipca-factor-fit` (companion)
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique 2.X"
