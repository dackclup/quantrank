---
name: mos-display-clamp-check
description: Verify the MoS% display clamping logic in frontend/lib/format.ts —
  ensures extreme MoS values (e.g., -99% for crashed methods, +500% for outlier
  methods) render as "< -99%" / "> +500%" rather than raw numbers, matching
  Issue 3 acceptance criteria from PR-3c.
---

# mos-display-clamp-check — STUB

## When to use

- After modifying `frontend/lib/format.ts::formatMosPct`
- After PR review flags a stock with raw MoS like "-9847%" appearing
  in the UI
- Regression check during PR-3d UI polish iterations

## What to flesh out (TODO when implementing)

- Read `frontend/public/data/stocks/*.json` →
  `margin_of_safety_pct`
- Histogram of raw values: <-99, -99 to 0, 0 to 100, 100 to 500, >500
- Cross-check display strings: render via `formatMosPct` and verify
  clamping triggers at the right boundaries
- Verify tooltip surfaces the unclamped raw value

## Acceptance criteria

- All extreme raw MoS values render with "< -99%" / "> +N%" prefix
- Tooltip exposes raw value to hover
- No raw "-9847%" string appears in any rendered card

## Related

- `frontend/lib/format.ts::formatMosPct` + `mosColorClass`
- `frontend/lib/types.ts::StockSummary.margin_of_safety_pct`
- `/tmp/issue_drafts/issue_mos_display_clamping.md` (PR-3c
  follow-up)
