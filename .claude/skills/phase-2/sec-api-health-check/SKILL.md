---
name: sec-api-health-check
description: Probe SEC EDGAR's data.sec.gov endpoints with a known-cheap request
  (single CIK submissions JSON) and report latency + availability. Use at the
  start of compute jobs to abort early if SEC is degraded, or during
  fundamentals stage stuck-detection. Phase 4 priority.
---

# sec-api-health-check — STUB

## When to use

- Compute job startup gate: abort with clear message if SEC is down
- During fundamentals stage if p95 latency >30s (suggests throttling
  beyond what retry tightening can compensate for)
- Manual probe when investigating workflow_dispatch timeout

## What to flesh out (TODO when implementing)

- Endpoint probed: `https://data.sec.gov/submissions/CIK<10-digit>.json`
  (use AAPL CIK 0000320193 as the canary)
- Required header: `User-Agent: <EDGAR_USER_AGENT>`
- Latency thresholds:
  - <2s: healthy → proceed
  - 2-5s: warning → log, proceed with bumped retry budget
  - 5-15s: throttled → log, proceed with caution
  - >15s: degraded → abort with "SEC API degraded — reschedule"
- Optional: also probe companyfacts endpoint (heavier — 5MB payload)
- Cache the result for ~60s to avoid hammering the canary endpoint

## Acceptance criteria

- Probe completes in <20s even on degraded SEC (with timeout)
- Distinguishes 5xx (down) from 429 (rate-limited) from slow-200
- Returns structured result usable by orchestrator gate logic

## Related

- `/tmp/issue_drafts/issue_fundamentals_resilience_phase4.md` §d
- `compute/main.py` (would gate at top of `run_weekly_compute`)
- `phase-2/fundamentals-cache-warm` (alternative path when SEC is
  slow — read from warm cache)
