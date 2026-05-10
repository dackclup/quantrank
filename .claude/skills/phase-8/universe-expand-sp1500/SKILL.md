---
name: universe-expand-sp1500
description: Expand the universe from S&P 500 (current) to S&P 1500 (S&P 500 +
  S&P 400 mid-caps + S&P 600 small-caps). Phase 8 final scaling. Compute time
  triples; needs all Phase 4-7 resilience work shipped first.
---

# universe-expand-sp1500 — STUB

## When to use

- Phase 8 (final scaling) work — only after Phase 4-7 stabilize
- Specifically requires Phase 4 fundamentals pre-cache + 8-K
  pre-cache to make the 3× universe size feasible within the
  workflow timeout budget

## What to flesh out (TODO when implementing)

- Universe source: Wikipedia S&P 1500 component list
  (or CRSP / Quandl if richer data needed)
- Cache layer: scale-up of `compute/ingest/universe.py`
- Workflow timeout: bump to 180 min if needed (currently 90 min for
  S&P 500 with PR-3d's tightening)
- Schema: no changes (already supports any universe via
  `Metadata.universe`)
- UI: rankings page may need pagination tweaks beyond the current
  PAGE_SIZE=50 (with 1500 stocks, ~30 pages)

## Acceptance criteria

- Compute completes in <90 min cold-cache
- All defenses still fire correctly (some thresholds may need
  re-calibration on the wider universe — small caps differ from
  large caps in fundamentals distribution)
- Universe expansion is reversible (single config flip back to
  SP500)

## Related

- `compute/ingest/universe.py`
- `compute/config.py::UNIVERSE`
- `phase-8/microcap-skip` (companion — Russell 2000 microcaps NOT
  added per SKILL.md anti-pattern)
- SKILL.md anti-patterns block — "No Russell 2000 microcaps"
