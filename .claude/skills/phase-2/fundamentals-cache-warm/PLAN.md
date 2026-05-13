---
name: fundamentals-cache-warm
description: Pre-warm the fundamentals cache (compute/cache/fundamentals/*.parquet)
  for the full universe in an off-cycle job, so the weekly compute reads warm
  cache rather than hitting SEC EDGAR live. Phase 4 priority — addresses the
  PR-3d run #14 SEC throttling incident at the architectural level.
---

# fundamentals-cache-warm — STUB

## When to use

- Phase 4 implementation: scheduled nightly cache warm
- After a stale cache wipe (e.g., Q boundary)
- Manual pre-warm before a known-throttled SEC window

## What to flesh out (TODO when implementing)

- Workflow file: `.github/workflows/fundamentals-pre-cache.yml`
- Schedule: `cron: "0 4 * * *"` (4am UTC, off-cycle from compute)
- Universe iteration with retry tightening (already in
  `compute/ingest/fundamentals.py` after PR-3d Part 1)
- Cache shape unchanged from existing `compute/cache/fundamentals/`
- Coverage report on completion
- Failure-mode handling: skip stuck tickers, log slow tickers
  for `chronic-slow-ticker-special-case` skill

## Acceptance criteria

- Weekly compute reads ≥95% of universe from warm cache
- Pre-cache job completes in <60 min cold, <15 min warm
- No SEC rate-limit violations (10 req/s ceiling)
- Surfaces chronic-slow tickers via histogram

## Related

- `/tmp/issue_drafts/issue_fundamentals_resilience_phase4.md`
- `compute/ingest/fundamentals.py::_build_snapshot`
- `phase-4/chronic-slow-ticker-special-case`
