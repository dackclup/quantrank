---
name: fundamentals-coverage-report
description: Extract the fundamentals latency histogram and slow-ticker list from
  workflow logs (or local run logs) and produce a readable Section G report.
  Drill-down companion to verify-production-output Section G when the metadata
  fields alone (p50/p95/coverage_pct) aren't enough to diagnose throttling.
---

# fundamentals-coverage-report — STUB

## When to use

- After a workflow_dispatch where p95 latency is concerning (>15s)
- During Phase 4 pre-cache work — identifies chronically-slow
  CIKs to pre-cache with longer TTL
- Diagnostic when fundamentals_coverage_pct drops below 95%

## What to flesh out (TODO when implementing)

- Parse workflow log lines:
  - `fundamentals_fetch ticker=X elapsed_seconds=N status=Y`
    (per-stock log added in PR-3d Part 2)
  - `fundamentals_latency_histogram: {<5s: N, 5-15s: N, 15-30s: N, 30s+: N}`
  - `fundamentals_slow_tickers (>=15s, top 20): [(ticker, elapsed), ...]`
- Aggregate: histogram + top-20 slow + median + p95 + outlier list
- Identify chronic-slow tickers: present in slow list across ≥3
  recent runs

## Acceptance criteria

- Works on workflow log text (downloaded via `gh run view --log`)
  AND on local compute logs
- Surfaces a "Phase 4 special-case candidate" list of CIKs that are
  consistently slow

## Related

- `compute/main.py` (the log emit points added in PR-3d Part 2)
- `phase-4/chronic-slow-ticker-special-case`
- `/tmp/issue_drafts/issue_fundamentals_resilience_phase4.md`
