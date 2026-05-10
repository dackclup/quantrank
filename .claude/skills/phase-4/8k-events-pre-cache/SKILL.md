---
name: 8k-events-pre-cache
description: Implement the off-cycle 8-K events pre-cache workflow that warms
  the cache so Phase 3d's deferred Defenses #9/#10 can be re-enabled without
  hitting the 45-min weekly compute timeout. Phase 4 priority — prerequisite
  for flipping _EIGHT_K_DEFENSES_ENABLED to True.
---

# 8k-events-pre-cache — STUB

## When to use

- Phase 4 implementation of the architectural fix for the PR-3d
  workflow timeout incident
- After Phase 4 fundamentals pre-cache pattern is validated and
  ready to copy

## What to flesh out (TODO when implementing)

- New workflow: `.github/workflows/eight-k-pre-cache.yml`
- Schedule: `cron: "0 5 * * *"` (5am UTC, after fundamentals pre-cache)
- Per-ticker: regex-extract items from raw 8-K HTML (already done in
  PR-3d perf hotfix commit `12ad7ff`), write to
  `compute/cache/edgar_8k/<ticker>.json` (existing 7-day TTL cache shape)
- Failure mode: skip stuck tickers, log slow tickers
- Coverage report on completion

## Acceptance criteria

- Weekly compute reads ≥99% of universe from warm 8-K cache
- Pre-cache job completes in <30 min cold, <10 min warm
- Once warm, Defense #9 (4.02 hard veto) and Defense #10 (4.01
  annotate) can re-enable safely
- `_EIGHT_K_DEFENSES_ENABLED = True` in `compute/scoring/tier2.py`

## Related

- `/tmp/issue_drafts/issue_8k_events_phase4.md`
- `compute/scoring/eight_k_events.py::_filing_to_dict` (the regex
  extraction already lives here — just needs a cron-driven caller)
- `phase-2/fundamentals-cache-warm` (sister pattern)
- `phase-3d/tier2-deferred-mode-check` (sanity check before flipping)
