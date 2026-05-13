---
name: outlier-detection-debug
description: For a single ticker, report which fair-price methods were tagged
  outlier (>5× or <0.2× current price) and how that affected median vs max.
  Use to verify the outlier guard isn't masking a legitimate signal or letting
  an extreme value slip through.
---

# outlier-detection-debug — STUB

## When to use

- A ticker's `fair_price.max` and `fair_price.median` differ by an
  unexpected magnitude
- A method shows in `valuation_warnings: extreme_<method>_estimate`
  but the value seems plausible
- After modifying the outlier threshold (currently 5× / 0.2×)

## What to flesh out (TODO when implementing)

- Single-ticker probe: `python helper.py NVDA`
- Output: 6 methods × (raw value, current price, ratio, outlier=Y/N)
- Median / max computation showing inclusion/exclusion
- Edge cases: zero or negative method values (clamp to 0 in the bar
  geometry but raw value preserved)

## Acceptance criteria

- Distinguishes "outlier excluded from MAX" (still in MEDIAN) from
  "totally suppressed" (e.g., $10K ceiling fired)
- Reports the specific bound that fired (5× vs 0.2×)

## Related

- `compute/valuation/ensemble.py::compute_fair_price_ensemble`
- Defense #4 — multi-method outlier guard
- `phase-3c/ensemble-method-debug`
