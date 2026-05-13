---
name: pillar-imputation-check
description: Verify the NaN pillar imputation layer (50.0 = neutral per SKILL.md
  Rule 7) — count tickers with imputed pillars, list which pillars were imputed,
  and confirm the imputation didn't artificially shift composite scores. Use
  after pillar feature changes or when stocks with sparse fundamentals appear
  unexpectedly high in the rankings.
---

# pillar-imputation-check — STUB

## When to use

- After adding / modifying pillar feature modules
  (`compute/scoring/pillars.py` or `compute/features/*.py`)
- When a stock with known data-quality issues appears unexpectedly
  high in the rankings (suggests the imputation layer is hiding the
  data gap)
- During verification, as a follow-up to `verify-production-output`
  Section A coverage check

## What to flesh out (TODO when implementing)

- Read `frontend/public/data/stocks/*.json` →
  `data_quality.imputed_metrics` per ticker
- Histogram: number of tickers per imputed-pillar count (0, 1, 2,
  3+)
- Per-pillar imputation rate (% of universe imputed for each)
- Composite-score impact estimate: avg composite for imputed-N=0
  vs N=3+ groups
- Flag tickers with ≥3 imputed pillars + composite ≥70

## Acceptance criteria

- Reports per-pillar imputation rate
- Highlights anomalously-high-composite imputed stocks
- Distinguishes Phase 3+ Rule 7 imputation (active 8 pillars) from
  Phase 5+ permanently-null pillars (sentiment + ml)

## Related

- `compute/scoring/pillars.py`
- `compute/scoring/composite.py::neutralize_pillar_scores`
- `SKILL.md` Rule 7 — NaN pillar = 50.0 imputed
