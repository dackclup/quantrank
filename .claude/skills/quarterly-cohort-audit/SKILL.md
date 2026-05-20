---
name: quarterly-cohort-audit
description: Walk QuantRank's defense layer (active vetoes + annotates + method-applicability + informational flags) against academic priors on the most recent compute output — once per quarter. Surfaces flags that fire outside their expected band (over-firing → recalibration candidate; under-firing → dead-flag candidate), undocumented flags missing from CLAUDE.md's headline count, and delta vs the prior quarter's baseline. Output lands as a comment on issue #130 (the rolling cohort-audit thread). TRIGGER on ≥ 3 months since the last quarterly audit (last was 2026-05-20 on issue #130), when the user explicitly says "quarterly audit", "cohort audit", "Q2/Q3/Q4 audit", "annotate audit", "audit defense layer", or "is the defense layer drifting?", and before any phase that materially changes the scoring layer (Phase 2 calibration cleanup, Phase 4.5e new annotates, etc.) — establishes the baseline the new phase will be measured against. ALSO trigger when `verify-production-output` Section J shows an annotate flag fire count outside what the prior audit recorded as expected. SKIP for the routine weekly compute scan (use `verify-production-output` Section A-J for that), for a single-flag investigation (`defense-scorecard` is the focused tool), and for compute-internal regressions that aren't cohort-level (those are pytest's job).
---

# Quarterly Cohort Audit

A scheduled walk of QuantRank's defense layer against the academic
priors that motivated each flag. Catches the slow-drift failure mode
where a flag continues to fire but its fire rate has crept outside
the cohort the academic literature studied (e.g., Mayew 2015's
1-3% going-concern FP rate vs QuantRank's observed 10.8%).

Last audit: **2026-05-20** ([#130 comment](https://github.com/dackclup/quantrank/issues/130#issuecomment-4496605644))
discovered **10 undocumented flags** (defense layer headline count
17 → 27 reconciled in PR #154).

Next scheduled: **2026-08-19** (Q3 2026).

## Why quarterly

- Monthly is too frequent — flag fire rates don't drift fast enough
  to warrant the effort
- Yearly is too sparse — by then a recalibration window has usually
  passed (cohorts shift, S&P 500 reconstitutes)
- Quarterly aligns with SEC fiscal cadences (10-Q filings) so the
  fundamentals + 8-K cohort is naturally a quarter-aged window

## Inputs

- **Current run**: `frontend/public/data/` (`metadata.json` +
  `stocks/*.json` + `rankings.json`)
- **Prior-quarter baseline**: the tag closest to 3 months ago, e.g.,
  `v1.2.0-phase4.5` (2026-05-17) for the 2026-08-19 audit. Find via
  `git tag --list 'v*-phase*' --sort=-creatordate | head -10`.
- **Academic priors** — encoded per-flag in this skill below

## Process

### 1. Section J auto-tabulator

Run `verify-production-output/helper.py` and capture Section J output
(introduced PR #156). This is the annotate-flag inventory: every
`valuation_warnings` entry + every boolean-True `tier2_events` key
across the universe, counted + percent.

```bash
python .claude/skills/verify-production-output/helper.py 2>&1 | \
  sed -n '/Section J/,/Summary:/p' > /tmp/section_j_<DATE>.txt
```

### 2. Defense scorecard delta

```bash
# Use defense-scorecard skill to diff current vs prior-quarter baseline
# (per defense-scorecard SKILL.md TRIGGER: "before-and-after a phase")
```

Capture the per-flag delta table. Mark flags that moved >|2σ| or
> 20% relative change as audit-priority candidates.

### 3. Walk each flag against academic priors

Per-flag expected fire-rate bands (S&P 500 cohort, ~502 stocks):

| Flag | Academic source | Expected fire rate | Action if outside |
|---|---|---|---|
| `going_concern_disclosure` | Mayew 2015 | 1-3% | Tighten `_is_locally_negated` negation window if > 5% |
| `non_reliance_filing` | Schroeder 2024 (Item 4.02) | 0-2% (rare events) | Verify 365d lookback if > 3% |
| `auditor_change` | Cohen-Malloy-Nguyen 2020 (Item 4.01) | 1-5% (730d lookback) | Verify 730d lookback if > 6% |
| `restatement_history` | Hennes-Leone-Miller 2008 | 1-3% material restatements | Tighten "≥ 1 amendment" threshold to material-restatement-only if > 5% (issue #16 / epic #150 Phase 2.2) |
| `loss_avoidance_pattern` | Burgstahler-Dichev 1997 | 5-15% (their cohort, NOT large-cap S&P) | Currently 0% on S&P 500 (Phase 4.5d issue) — scale thresholds 10× or remove from FLAG_WEIGHTS (epic #150 Phase 2.4) |
| `accruals_momentum_high` | Sloan 1996 | ~10% (top decile by construction) | Healthy at 10% (top decile) |
| `sloan_accruals_top_decile` | Sloan 1996 | ~10% (top decile) | Healthy at 10%; over-firing on Financials is sector-relative threshold work (issue #7) |
| `net_issuance_top_decile` | Pontiff-Woodgate 2008 / Daniel-Titman 2006 | ~10% (top decile) | Healthy at 10% |
| `altman_distress` | Altman 1968 Z″ | 2-8% (S&P 500 is biased to non-distressed) | Healthy in band; spike > 12% suggests macro stress or data corruption |
| `beneish_manipulation_veto` | Beneish 1999 M-score | 1-5% (top-tier manipulation flag) | Healthy in band |
| `dechow_manipulation_veto` | Dechow 2011 F-score | 1-5% | Healthy in band |
| `beneish_high` | Beneish 1999 (annotate tier) | 5-15% (looser threshold) | Healthy |
| `dechow_high` | Dechow 2011 (annotate tier) | 5-15% | Healthy |
| `value_trap_risk` | Asness-Frazzini 2013 + project synthesis | < 10% expected | **Currently 35% on S&P 500** — issue #11 (`_avg_3y_roe` denominator bug; epic #150 Phase 2.6) |
| `goodwill_heavy` | Internal (Gu-Lev 2011 motivated) | 10-25% (S&P 500 has many large goodwill writedowns) | Healthy |
| `rem_suspect` | Roychowdhury 2006 | 3-10% | Healthy |
| `manipulation_triple_flag` | Project rollup | < 1% (high-bar) | Healthy if < 2% |
| `data_quality_input_corruption` | Internal sanity | < 2% (Step 7.5 guard) | Investigate if > 3% — fundamentals.py degradation |
| `cross_source_disagreement` | Internal | 3-8% | Healthy |
| `late_filing_notification` | Internal (NT 10-K/10-Q) | 0.5-3% | Healthy |
| `extreme_<method>_estimate` (×6 methods: dcf, rim, graham, multiples_pe, multiples_pb, multiples_ev_ebitda) | Method applicability | 5-20% per method (cohort varies by method) | Method-applicability signals; semantic split planned per epic #150 Phase 2.1 |

### 4. Undocumented-flag check

Compare flags emitted in current output vs flags enumerated in
`CLAUDE.md` §Phase status defense-layer headline count. Any flag
emitted but not declared = undocumented.

The 2026-05-20 audit found 10 such flags. Re-running this check is
the regression guard: if a new PR added a flag without updating
CLAUDE.md, this audit catches it.

```bash
# All distinct boolean flags in current output
python -c "
import json, pathlib
flags = set()
for p in pathlib.Path('frontend/public/data/stocks').glob('*.json'):
    s = json.loads(p.read_text())
    flags.update(s.get('valuation_warnings') or [])
    t2 = s.get('tier2_events') or {}
    flags.update(k for k, v in t2.items() if isinstance(v, bool) and v)
    flags.update(s.get('risk_flags') or [])
print('\n'.join(sorted(flags)))
" > /tmp/emitted_flags_<DATE>.txt

# Manual compare against CLAUDE.md §Phase status declared list
grep -E '`[a-z_]+`' CLAUDE.md | grep -oE '`[a-z_]+`' | sort -u
```

### 5. Write the audit comment

Post as a new comment on [issue #130](https://github.com/dackclup/quantrank/issues/130).
Template:

```markdown
# Q<N> 20XX cohort audit (<DATE>)

**Baseline tag**: `<LAST_TAG>` (<DATE_OF_TAG>)
**Current commit**: `<SHA[:7]>`
**Universe size**: <N> stocks

## Section J snapshot

<paste Section J output from step 1>

## Defense scorecard delta vs baseline

<paste defense-scorecard delta table from step 2>

## Flags outside expected band

| Flag | Expected | Observed | Action recommended |
|---|---|---|---|
| `<flag>` | <range> | <%> | <action> |

## Undocumented flags

(None — all emitted flags appear in CLAUDE.md §Phase status)
OR
(N flags found: `<flag1>`, `<flag2>`, ... — file follow-up issue to update CLAUDE.md)

## Recalibration candidates

- `<flag>` — <why> — epic <#> Phase <N> already plans to address
- `<flag>` — <why> — new candidate, file issue if confirmed

## Cohort health summary

- ✅ <X> flags healthy
- 🟡 <Y> flags warn (in expected band but trending)
- 🔴 <Z> flags outside band (recalibration needed)

Next audit: <DATE + 3 months>
```

### 6. File follow-up issues if needed

For each 🔴 flag, file a separate issue with:
- Title: `<flag_name> firing outside expected band (Q<N> 20XX audit)`
- Body: link to the audit comment, the observed vs expected, the
  proposed recalibration

These issues feed into the next phase's calibration cleanup work
(currently epic #150 Phase 2).

## Output ownership

This skill outputs to GitHub (issue #130 comment + optional follow-up
issues) — no local file artifact except the `/tmp/` working files
from steps 1+4. The audit trail lives in the issue thread, which is
the project's canonical place for cohort observability.

## Coordination

- Doesn't change the scoring layer — purely observational
- Feeds into the calibration cleanup work (Phase 2 of epic #150 et
  seq) by producing the issue inventory those phases consume
- Pairs with `defense-scorecard` (per-flag delta) and
  `verify-production-output` Section J (annotate inventory) — this
  skill is the *quarterly synthesis* of both
- Should run BEFORE the calibration phase begins so the phase's
  before/after measurement has a clean baseline
