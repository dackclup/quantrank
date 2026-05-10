---
name: microcap-skip
description: Verify the universe expansion (Phase 8) does NOT include Russell
  2000 microcaps — per SKILL.md anti-pattern. Microcaps have insufficient
  liquidity, sparse fundamentals coverage, and known-bad SEC filing latency
  that would degrade the entire ranking layer.
---

# microcap-skip — STUB

## When to use

- During Phase 8 universe expansion work
- Whenever the universe config changes — sanity check that the
  expansion stayed within S&P 1500 and didn't accidentally add
  Russell 2000

## What to flesh out (TODO when implementing)

- Read the current universe (from `compute/cache/universe/`)
- Cross-reference against Russell 2000 component list
- Flag any overlapping tickers
- Hard exit (CI failure) if overlap detected
- Run as part of the universe-load step in `compute/main.py`

## Acceptance criteria

- Zero overlap between current universe and Russell 2000
- Documented exception list (if any S&P 1500 stocks are also in R2K
  due to dual classification, document the rationale per ticker)

## Why this matters (per SKILL.md anti-patterns)

- **Liquidity**: R2K microcaps have median daily volume <$1M, well
  below the $10M floor we'd want for a tradable signal
- **Fundamentals coverage**: ~30% of R2K stocks have incomplete or
  delayed XBRL filings (vs <5% in S&P 500)
- **Filing latency**: small-cap filings have 60+ day median lag
  vs ~30 day for large caps; defenses depending on recent filing
  data degrade
- **No academic precedent**: the research papers we cite
  (Mayew 2015, Pontiff-Woodgate 2008, Sloan 1996, etc.) all
  validate on S&P 500 / S&P 1500 — extending to R2K is
  out-of-sample without justification

## Related

- `phase-8/universe-expand-sp1500` (companion)
- SKILL.md anti-patterns block
- `compute/config.py::UNIVERSE`
