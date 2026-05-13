---
name: chronic-slow-ticker-special-case
description: Identify CIKs that consistently land in the 15-30s+ fundamentals
  latency bucket across multiple weekly runs and apply per-ticker special
  cases (longer cache TTL, off-cycle pre-fetch, alternate source). Phase 4
  resilience work after observability data accumulates.
---

# chronic-slow-ticker-special-case — STUB

## When to use

- After 4-6 weekly runs accumulate `fundamentals_slow_tickers`
  log entries
- During Phase 4 resilience tightening (after pre-cache + retry
  refinements ship)

## What to flesh out (TODO when implementing)

- Aggregate slow-tickers list across last N runs (parsed from
  workflow logs via `fundamentals-coverage-report` skill)
- A ticker is "chronic slow" if it appears in slow list for ≥3 of
  last 4 runs
- Per-chronic-slow ticker:
  - Manual investigation: why is SEC slow on this CIK? (filing
    volume? specific concept? entity merger?)
  - Special-case in `compute/cache/fundamentals/special_case.json`
    with longer TTL or alt-source override
- Annotate the rankings JSON with a `slow_fetch_special_case: true`
  flag for transparency

## Acceptance criteria

- p95 latency drops below 10s after special-cases applied
- No silent override — every special-case ticker is logged at
  compute startup
- Documented rationale per special-case (link to SEC filing or
  CIK note)

## Related

- `phase-3d/fundamentals-coverage-report`
- `phase-2/fundamentals-cache-warm`
- `/tmp/issue_drafts/issue_fundamentals_resilience_phase4.md` §b
