---
name: tier2-deferred-mode-check
description: Verify the _EIGHT_K_DEFENSES_ENABLED feature flag is False (Phase 3d
  deferral) and confirm both 8-K-derived flags (non_reliance_filing,
  auditor_change) are 0 across the universe. Use after merging the deferral
  commit and before every release until Phase 4 re-enables the wiring.
---

# tier2-deferred-mode-check — STUB

## When to use

- Pre-Mark-Ready check on PR-3d (the originating PR)
- Every workflow_dispatch run during Phase 3d (Section B of
  `verify-production-output`)
- When Phase 4 prepares to flip the flag — sanity check before flip

## What to flesh out (TODO when implementing)

- Read `compute/scoring/tier2.py` to confirm
  `_EIGHT_K_DEFENSES_ENABLED = False`
- Scan `frontend/public/data/stocks/*.json` for any
  `tier2_events.non_reliance_filing == True` or
  `tier2_events.auditor_change == True`
- Either condition firing → HALT, feature flag broken
- Also verify `risk_flags` does not contain `non_reliance_filing`
  for any ticker (would indicate veto leaked through)

## Acceptance criteria

- Hard contract: 0 fires of either 8-K flag in deferred mode
- Reports the flag value from the source code (not just from
  output) — distinguishes "flag is off" from "flag is on but data
  happens to be empty"

## Related

- `compute/scoring/tier2.py` (the feature flag location)
- `verify-production-output` Section B
- Phase 4 issue: `/tmp/issue_drafts/issue_8k_events_phase4.md`
