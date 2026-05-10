---
name: top5-rotation-audit
description: Audit the entered_top5 / exited_top5 boolean flags across all stocks
  and verify the rotation logic — flagged top-rank stocks lose their badge,
  next-in-line stocks earn it. Use after scoring or veto changes to confirm
  no rotation regression and document any composition churn vs prior run.
---

# top5-rotation-audit

## When to use

- After veto layer changes (new veto added, threshold tweaked,
  feature flag flipped)
- After composite weight changes
- Before / after merging a scoring-touching PR for parity check
- During production verification (Section D of `verify-production-output`)

## What it does

For the most recent compute output:

1. Identify the **raw top-5** by composite score (rank 1-5).
2. Identify the **effective top-5** — stocks with `entered_top5=true`
   anywhere in the universe (not just rank ≤5).
3. Identify the **exited set** — stocks with `exited_top5=true`.
4. Verify the rotation invariant:
   - For each stock in raw-top-5 with `risk_flags` containing any
     active veto: `entered_top5` MUST be false, `exited_top5` MUST
     be true (suppressed).
   - For each stock with `entered_top5=true` and rank > 5:
     a top-5-rank stock at the same effective position must be
     suppressed.
5. Report the delta vs prior run (if `--baseline-rankings=` provided).

## The rotation contract (SKILL.md Rule 16)

> **Flagged stocks (any active veto) keep their composite rank but
> cannot earn the `entered_top5` badge.** The next-in-line stock by
> composite (rank 6, 7, 8, …) inherits the badge instead. This is
> annotate-and-veto-Top-N — the score itself is preserved (no
> retroactive adjustment); only the user-visible "new in Top-5"
> signal is suppressed.

Implications:
- A stock at rank 1 with `altman_distress` still appears at rank 1
  in the rankings table — but with no `entered_top5` indicator.
- A stock at rank 6 (clean) replaces it as the "5th effective entrant"
  with `entered_top5=true`.
- The `exited_top5` flag only fires for the 5 **suppressed**
  top-rankers, not for stocks that genuinely dropped out of the
  effective top-5 due to score changes (those are tracked by
  composition diff vs baseline).

## Inputs

- `frontend/public/data/stocks/*.json` (current run)
- `frontend/public/data/rankings.json` (current run)
- (optional) `--baseline-rankings=<sha-or-path>` — prior run for diff

## Output

```
Top-5 rotation audit — v0.6.0-phase3d / commit <sha>

RAW TOP-5 (by composite, no veto suppression)
  #1 SPG    composite 74.81  | risk_flags=[sloan_accruals_top_decile]    | warnings=[data_quality_input_corruption]
  #2 NVDA   composite 73.07  | risk_flags=[sloan_accruals_top_decile]    | warnings=[extreme_graham_estimate, extreme_rim_estimate]
  #3 SNDK   composite 72.50  | risk_flags=[]                              | warnings=[value_trap_risk]
  #4 EOG    composite 71.02  | risk_flags=[]                              | warnings=[extreme_multiples_ev_ebitda_estimate]
  #5 CF     composite 70.17  | risk_flags=[]                              | warnings=[goodwill_heavy, value_trap_risk]

EFFECTIVE TOP-5 (entered_top5=true)
  #3 SNDK
  #4 EOG
  #5 CF
  #6 BKR    composite 69.85  | risk_flags=[]                              | warnings=[data_quality_input_corruption]
  #7 HST    composite 69.42  | risk_flags=[]                              | warnings=[]

SUPPRESSED (raw-top-5 with active veto, exited_top5=true)
  SPG  ← sloan_accruals_top_decile
  NVDA ← sloan_accruals_top_decile

ROTATION CONTRACT
  ✓ All suppressed stocks have exited_top5=true
  ✓ All entered stocks have entered_top5=true and rank ≤ 7
  ✓ Effective top-5 size = 5

CHURN vs baseline (run #11, commit <sha>)
  Effective top-5 unchanged: {SNDK, EOG, CF, BKR, HST}
  Suppressed set: {SPG, NVDA} (was {SPG, NVDA} — same)
  Composition delta: 0
```

## Hard contract checks

- `len([s for s in stocks if s.entered_top5])` MUST equal 5
- `len([s for s in stocks if s.exited_top5])` SHOULD equal the
  number of raw-top-5 stocks with active vetoes (typically 0-2)
- For every `entered_top5=true` stock at rank > 5, there must exist a
  rank ≤ 5 stock with at least one active veto

If any of these fail → bug in the rotation logic in
`compute/output/writer.py` or the upstream `compute/main.py`
top-5 selection.

## Edge cases

- **More than 5 raw-top-5 stocks have active vetoes**: rotation
  cascades — the effective top-5 includes ranks 6, 7, 8, … until 5
  clean stocks are found. Flag if this happens (suggests a too-aggressive
  veto layer for the universe).
- **First-ever run** (no baseline): churn diff is N/A; only the
  rotation contract checks fire.
- **Baseline file missing fields** (older schema): graceful degrade —
  skip churn diff, run contract checks only.

## Anti-patterns (do not do)

- Don't conflate "exited_top5" with "lost its rank". `exited_top5`
  fires only for suppressed-from-top-5 stocks, not for stocks that
  genuinely fell in composite ranking. Use a separate composite-rank
  diff for that.
- Don't double-count a stock in both entered and suppressed sets —
  they're disjoint by construction.
- Don't audit `valuation_warnings[]` as a veto. Warnings annotate;
  vetoes suppress. Only `risk_flags[]` entries can suppress
  `entered_top5`.

## Related

- `verify-production-output` Section D
- `defense-scorecard` — overall defense layer health
- `compute/output/writer.py::write_rankings_json` — implements the
  rotation logic
