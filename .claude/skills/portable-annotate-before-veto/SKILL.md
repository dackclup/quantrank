---
name: portable-annotate-before-veto
description: For every new defense / risk flag in a ranking or scoring
  system, ship it as `annotate` (informational metadata, no rank change)
  FIRST. Promote to `veto` (rank suppressor) only after ≥ 1 production
  cron of observation + threshold calibration + cohort-acceptance check.
  Prevents "fire-and-regret" patterns where a new flag with the wrong
  threshold instantly removes a large fraction of the universe from
  Top-N. Generic — drop-in for any project with a progressive-rollout
  defense / scoring layer. TRIGGER when adding a new rule that filters /
  scores / ranks production output, when previewing a "what if we vetoed
  on X" threshold sweep, or when a CR comment says "make this a veto" on
  a fresh annotate. SKIP for project-internal scoring tweaks that don't
  change rank output (pure additive features behind a sum-to-1 weight
  invariant).
---

# portable-annotate-before-veto

A failure-mode-driven pattern: new defense flags ship with a guess at
the threshold. Guessing wrong on a veto silently destroys the rank
output. Guessing wrong on an annotate is observable and reversible.
Portable — applies to any project that ranks, scores, or filters
production output through a layered defense.

## Pattern

### Two-stage rollout

**Stage 1 — Annotate (default for every new flag)**

The flag fires. The fire is recorded as metadata on the affected
output row. The rank / score / order of the output is **not changed**.

```python
# In the scoring layer:
output.metadata.fired_flags.append("new_defense_flag")
# output.rank is computed from the EXISTING composite — unchanged.
```

Effect: the next cron run surfaces "N rows fired the new flag" in
metadata. Operator inspects: does the fire rate match expectation?
Are the right rows flagged? Cohort acceptance is checkable from
diagnostic output, NOT from a regression in the rank.

**Stage 2 — Veto (promotion, requires ≥ 1 cron of clean fires)**

After the annotate has run on production data for ≥ 1 cron and the
fire rate / cohort look right, promote it. The flag now suppresses
the affected row from Top-N (or applies a rank penalty, or whatever
the "veto" semantics are in this project).

```python
# In the scoring layer (after promotion):
output.metadata.fired_flags.append("new_defense_flag")
output.rank_suppressed = True  # or apply penalty, or drop from Top-N
```

Promotion is a separate PR. The PR diff is a 1-line behavior change
(`rank_suppressed = True`); the new content (threshold definition,
cohort logic) shipped in the prior annotate PR and was already
exercised in production.

## Why

The auditor session pattern for any new defense is: "what if the
threshold is wrong?" An annotate-first rollout makes the answer
"we'll see in the next cron" instead of "Top-5 lost 30% of its
contents and we now have a hotfix PR."

For thresholds derived from historical data on the same universe,
the historical N may not match the live N (universe drift,
benchmark changes, sector reweights). The annotate stage catches
this without forcing a rollback.

## Trigger conditions

- Adding a new rule that filters / scores / ranks production output
- The rule uses a threshold derived from prior research / paper
  cohort (not the project's own production universe)
- The rule's fire rate is uncertain (could be 0% or 50%, both bad
  on a fresh veto)
- CR feedback says "make this a veto" on a freshly-shipped annotate

## Skip conditions

- Pure additive features behind a sum-to-1 weight invariant — they
  shift the score continuously, no rank-cliff risk
- Project-internal scoring tweaks that don't change production
  output (test fixtures, dev tooling, internal QA dashboards)
- Promoted-and-stable flags that are getting a threshold tune-up
  (already past the annotate stage; the tune-up may itself stage
  through annotate, but the binary annotate-vs-veto decision is
  settled)

## Promotion checklist

Before flipping `annotate` → `veto` in production:

- [ ] ≥ 1 production cron run with the annotate enabled
- [ ] Fire rate within expected range (compare to research cohort
      or prior-cohort baseline)
- [ ] Spot-check the flagged rows against intuition (does each
      flagged row deserve the veto?)
- [ ] Document the cohort delta in the promotion PR (research N vs
      production N, false-positive rate if observable)
- [ ] Rollback plan: the promotion PR's revert is a clean 1-line
      change

## QuantRank precedent

The Phase 4.5 defense cluster (PRs #89/#90/#91 + #93 + #95 + #97 +
#100) shipped 9 new flags. Active vetoes went from 5 to 7;
annotates went from 1 to 11. The 2 promotions (Beneish +
Dechow manipulation) had researched cohort thresholds known to
hold on S&P-500-size universes. The 7 annotate-only flags
(`restatement_history`, `late_filing_notification`, `rem_suspect`,
`accruals_momentum_high`, `loss_avoidance_pattern`, `manipulation_
triple_flag`, `auditor_change`) all needed S&P 500-scaled thresholds
that weren't safe to ship as vetoes immediately.

Concrete forcing precedent: `loss_avoidance_pattern` (4.5d) — the
Burgstahler-Dichev 1997 thresholds (NI ≤ \$5M / EPS ≤ \$0.05) fired
0% on S&P 500 large-caps. If shipped as a veto, this would have
been a no-op (best case) or a hotfix candidate (worst case if
universe drift created false positives later). As an annotate, the
0% fire rate is observable in the metadata and the promotion is
gated on a future S&P-500-scaled threshold revision.

See QuantRank's `SKILL.md` Rule 16 (Top-5 rank suppression
semantics) and `WORKFLOW.md` § "Annotate-first defense rollout" for
the project-specific lock.
