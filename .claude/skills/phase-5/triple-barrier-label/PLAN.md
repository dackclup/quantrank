---
name: triple-barrier-label
description: Label time-series price data using the López de Prado Triple Barrier
  Method (TBM) — first-touch upper / lower / time-decay barriers — for use as
  the supervised target in Phase 5 ML meta-learner training. Replaces naive
  fixed-horizon return labels.
---

# triple-barrier-label — STUB

## When to use

- Phase 5 ML meta-learner training data prep
- After `phase-4/alpha158-fit` ships features

## What to flesh out (TODO when implementing)

- Library: `mlfinlab` is AGPL — incompatible with Apache 2.0 repo
  license. Port the algorithm natively (~30 lines of pandas/numpy)
- Inputs: per-ticker OHLCV from
  `frontend/public/data/stocks/history/<TICKER>.json`
- Outputs: per-ticker labels (1 = upper barrier hit first, -1 =
  lower, 0 = time decay)
- Module location: `compute/ml/triple_barrier.py`

## Acceptance criteria

- Reproduces López de Prado Ch.3 example numerically
- Configurable upper/lower thresholds + time horizon
- No mlfinlab dependency (license compatibility)

## Related

- López de Prado 2018 *Advances in Financial Machine Learning*
  Ch. 3 (Triple Barrier) + Ch. 4 (Meta-Labeling)
- `phase-5/meta-label` (consumer of these labels)
- SKILL.md library matrix — note "mlfinlab AGPL warning"
