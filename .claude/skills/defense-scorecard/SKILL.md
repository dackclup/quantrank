---
name: defense-scorecard
description: Tally defense-layer counts (active vetoes / numerical guards / annotate flags) from the latest compute output and diff against a prior baseline — per-flag delta + which stocks are flagged. TRIGGER: after `compute/scoring/risk_overlay.py` changes, a new defense lands, a feature-flag flip, PR review of scoring changes, or "are the vetoes still firing the same?" / "how many altman flags?" / "did the defense layer change?".
---

# defense-scorecard

A focused tally of the defense layer. QuantRank's defenses sit in three
tiers: active vetoes (suppress Top-5 entry), numerical guards
(constraints baked into compute), and annotate flags (surface in UI
without affecting score). When a defense changes shape, the population
counts should change in predictable ways — this skill makes those
counts auditable.

## Defense inventory (v0.6.0-phase3d)

### Active vetoes (3, 4th deferred)

| Flag | Paper | Notes |
|---|---|---|
| `altman_distress` | Altman 1968 / 2000 (Z″) | Bankruptcy risk; suppresses `entered_top5` |
| `sloan_accruals_top_decile` | Sloan 1996 *TAR* | Earnings quality, sector-neutral |
| `net_issuance_top_decile` | Pontiff-Woodgate 2008 *JF* | Dilution / issuance signal |
| `non_reliance_filing` 🟡 | Schroeder 2024 SSRN | DEFERRED to Phase 4 (8-K Item 4.02) |

### Numerical guards (5, internal — surface via downstream effects)

| Guard | Where | Behavior |
|---|---|---|
| Stale filing 120d / 180d | `compute/scoring/stale.py` | Annotate at 120d, veto at 180d |
| Outlier 5× / 0.2× current | `compute/valuation/ensemble.py` | Excluded from MAX, kept in MEDIAN |
| Terminal-g cap (≤ WACC − 100bp) | `compute/valuation/dcf.py` | DCF stability constraint |
| Sector exclusions | `compute/scoring/pillars.py` | Per-pillar / method skip list |
| Data-quality $10K/share ceiling | `compute/valuation/ensemble.py` Step 7.5 | Nulls all 6 methods + emits flag |

### Annotate flags (6 active, 1 deferred)

| Flag | Layer | Notes |
|---|---|---|
| `goodwill_heavy` | `valuation_warnings` | Goodwill / equity > threshold |
| `value_trap_risk` | `valuation_warnings` | High MoS + low Quality pillar |
| `extreme_<method>_estimate` | `valuation_warnings` | Per-method outlier (one of 6 methods) |
| `stale_filing_soft` | `risk_flags` | 120d ≤ filing_lag < 180d |
| `data_quality_input_corruption` | `valuation_warnings` | $10K/share ceiling fired |
| `going_concern_disclosure` | `tier2_events.going_concern_disclosure` | Mayew 2015 phrase scan |
| `auditor_change` 🟡 | `tier2_events.auditor_change` | DEFERRED Phase 4 (8-K Item 4.01) |

## Running

Pure inline-Python scan over the output JSON. From the repo root:

```python
import json, glob, collections

stocks = [json.load(open(f)) for f in sorted(glob.glob("frontend/public/data/stocks/*.json"))]

# Active vetoes (in risk_flags[])
risk_counter = collections.Counter()
for s in stocks:
    for f in s.get("risk_flags") or []:
        risk_counter[f] += 1

# Annotate flags (in valuation_warnings[] and tier2_events)
warn_counter = collections.Counter()
for s in stocks:
    for w in s.get("valuation_warnings") or []:
        warn_counter[w] += 1
    t2 = s.get("tier2_events") or {}
    if t2.get("going_concern_disclosure"): warn_counter["going_concern_disclosure"] += 1
    if t2.get("auditor_change"): warn_counter["auditor_change"] += 1

print("VETOES:", dict(risk_counter))
print("ANNOTATES:", dict(warn_counter))
```

For a baseline comparison, run the same scan against a checkout of an
earlier commit's `rankings.json` and diff the counters.

## Expected counts (S&P 500 baseline, Run #15 / commit 4805741)

| Flag | Count | Notes |
|---|---|---|
| `altman_distress` | 54 | ~10.8% — stable across runs |
| `sloan_accruals_top_decile` | 50 | ~10% — known to over-fire on financials (issue #7) |
| `net_issuance_top_decile` | 37 | ~7% — stable |
| `non_reliance_filing` | 0 | DEFERRED — must stay 0 until Phase 4 |
| `data_quality_input_corruption` | 8 | AMCR / BKR / CHTR / ERIE / PSKY / RTX / SPG / VTRS |
| `going_concern_disclosure` | 54 | ~10.8% — over FP target, see issue #16 |

Significant deviation from these baselines warrants investigation — see
the relevant per-flag debug skill (e.g., `phase-3b/sloan-debug/PLAN.md`)
for the diagnostic playbook.

## Hard contract checks

| Check | Phase 3d (current) | Phase 4+ (after re-enable) |
|---|---|---|
| Active veto count | 3 | 4 |
| `non_reliance_filing` count | 0 | > 0 |
| `going_concern_disclosure` rate | 1-10% | < 5% (after refinement) |

If a check fails, do not write off as flake — it means a defense layer
change landed without intent. Either the count moved or a feature flag
flipped. Investigate before declaring the run healthy.

## Why this skill exists

The defense layer is QuantRank's primary user-trust signal. A silent
regression (e.g., a refactor that accidentally removes the
`sloan_accruals_top_decile` flag from `risk_flags`) would let known-bad
stocks back into the effective Top-5. This skill is the gate that
catches such regressions before merge.

## Counting gotchas

- `data_quality_input_corruption` appears in `valuation_warnings[]` AND
  is internally tracked as a numerical guard. Count it once per
  category.
- `entered_top5: false` is a *consequence* of the veto layer suppression,
  not itself a defense flag. Do not include it in the scorecard.
- `extreme_<method>_estimate` is six distinct strings — `extreme_graham_estimate`,
  `extreme_multiples_pe_estimate`, etc. Aggregate or break out per
  method based on what the caller cares about.

## Related skills

- `verify-production-output` — Section E is a smaller version of this
  scorecard inside the broader A-H scan
- `top5-rotation-audit` — focused dive on how the veto suppression
  reshapes the user-visible Top-5
- `phase-3b/altman-debug`, `phase-3b/sloan-debug`, `phase-3b/nsi-debug`
  — per-flag triage when a count moves unexpectedly

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Tally QuantRank's defense layer counts (active vetoes / numerical
guards / annotate flags) from the most recent compute output and compare
against a prior run's baseline. Surfaces per-flag delta (altman_distress,
sloan_accruals_top_decile, net_issuance_top_decile, non_reliance_filing,
goodwill_heavy, value_trap_risk, extreme_<method>_estimate,
stale_filing_soft, data_quality_input_corruption, going_concern_disclosure,
auditor_change) and reports which stocks are flagged. TRIGGER after any
change to `compute/scoring/risk_overlay.py`, after a new defense
(Beneish, Dechow) lands, after a feature flag flip (e.g., Phase 4
re-enabling 8-K vetoes), or when the user asks "are the vetoes still
firing the same?" / "how many altman flags?" / "did the defense layer
change?". ALSO use during PR review to confirm a scoring change didn't
silently regress the defense layer. SKIP when the user wants the full
Section A-H production scan (use verify-production-output) or a deep
dive into Top-5 rotation specifically (use top5-rotation-audit).
