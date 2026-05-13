---
name: sector-neutralization-debug
description: For each pillar, report the per-sector mean / median / std of pillar
  scores to verify within-sector neutralization is working. Use after any change
  to pillar weighting or sector exclusion logic to catch regressions where one
  sector's pillar mean drifts far from 50 (the post-neutralization target).
---

# sector-neutralization-debug — STUB

## When to use

- After modifying sector exclusion lists in `compute/scoring/pillars.py`
- After Phase 4 sector-bucket rebalancing
- During regression testing — verify Real Estate sector mean stays
  near 50 (post-PR-3b verification — Real Estate mean=49.33,
  refuting a sector-bias hypothesis)

## What to flesh out (TODO when implementing)

- Per-pillar × per-sector aggregation
- Output: 11 sectors × 8 active pillars matrix of (mean, median, std)
- Highlight cells with |mean - 50| > 5 (potential neutralization failure)
- Also report which sectors are excluded from which pillars
  (currently: Financials/Utilities/Real Estate from Quality + EV/EBITDA)

## Acceptance criteria

- Per-sector pillar means within ±3 of 50 for non-excluded
  combinations
- Excluded sectors clearly marked as "skipped" rather than included
  with raw values
- Detects within-sector top-decile veto skew (e.g., Sloan firing
  disproportionately on financials — Phase 4 issue #7)

## Related

- `compute/scoring/composite.py::neutralize_pillar_scores`
- Phase 4 issue #7 (Sloan over-firing on financials)
- `defense-scorecard` for the cross-sector veto count
