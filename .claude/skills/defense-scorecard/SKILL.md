---
name: defense-scorecard
description: Tally the defense layer counts (vetoes / numerical guards / annotate
  flags) from the most recent compute output and compare against a prior baseline.
  Use after risk-overlay changes, new defense additions, or feature-flag flips
  to confirm no regression in scoring + that new defenses fire as expected.
---

# defense-scorecard

## When to use

- After adding a new defense (e.g., PR 3e Beneish / Dechow)
- After flipping a feature flag (e.g., Phase 4 re-enabling 8-K vetoes)
- After scoring layer changes that could affect veto eligibility
  (composite weights, sector neutralization)
- Before / after merging a defense-touching PR for parity check

## What it does

Reads `frontend/public/data/stocks/*.json` and tallies:

1. **Active vetoes** — flags in `risk_flags[]` that suppress
   `entered_top5`. Currently (Phase 3d): 3 vetoes.
2. **Numerical guards** — defensive constraints baked into the
   compute layer (not output flags). Currently: 5 guards.
3. **Annotate flags** — `risk_flags[]` or `valuation_warnings[]`
   entries that surface in UI but don't suppress badges. Currently
   (Phase 3d): 6 annotate flags.

Per-flag counts vs baseline run.

## Defense inventory (as of v0.6.0-phase3d)

### Vetoes (3 active, 4th deferred)

| Flag | Source paper | Notes |
|---|---|---|
| `altman_distress` | Altman 1968 / 2000 (Z″ score) | Bankruptcy risk; suppresses Top-5 badge |
| `sloan_accruals_top_decile` | Sloan 1996 *TAR* | Earnings quality; sector-neutral within decile |
| `net_issuance_top_decile` | Pontiff-Woodgate 2008 *JF* | Dilution / issuance signal |
| `non_reliance_filing` 🟡 | Schroeder 2024 SSRN | DEFERRED to Phase 4 (8-K Item 4.02) |

### Numerical guards (5)

| Guard | Where | Behavior |
|---|---|---|
| Stale filing soft (120d) / hard (180d) | `compute/scoring/stale.py` | Annotate at 120d, veto at 180d |
| Outlier 5× / 0.2× current price | `compute/valuation/ensemble.py` | Excluded from MAX, kept in MEDIAN |
| Terminal-g cap (≤ WACC − 100bp) | `compute/valuation/dcf.py` | DCF stability constraint |
| Sector exclusions | `compute/scoring/pillars.py` | Per-pillar/method per-sector skip list |
| Data-quality $10K/share ceiling | `compute/valuation/ensemble.py` Step 7.5 | Nulls all 6 methods + emits flag |

### Annotate flags (6 active, 1 deferred)

| Flag | Layer | Notes |
|---|---|---|
| `goodwill_heavy` | valuation_warnings | Goodwill / equity > threshold |
| `value_trap_risk` | valuation_warnings | High MoS + low Quality pillar |
| `extreme_<method>_estimate` | valuation_warnings | Per-method outlier (one of 6) |
| `stale_filing_soft` | risk_flags | 120d ≤ filing_lag < 180d |
| `data_quality_input_corruption` | valuation_warnings | $10K/share ceiling fired |
| `going_concern_disclosure` | tier2_events.going_concern_disclosure | Mayew 2015 phrase scan |
| `auditor_change` 🟡 | tier2_events.auditor_change | DEFERRED Phase 4 (8-K Item 4.01) |

## Inputs

- `frontend/public/data/stocks/*.json` (current run)
- (optional) `--baseline-rankings=<path-to-prior-rankings.json>` —
  compare against the prior run

## Output

```
Defense scorecard — v0.6.0-phase3d / commit <sha>

VETOES (3 active, 1 deferred)
  altman_distress             54  (vs baseline 54, Δ=0)
  sloan_accruals_top_decile   50  (vs baseline 50, Δ=0)
  net_issuance_top_decile     37  (vs baseline 37, Δ=0)
  non_reliance_filing          0  (DEFERRED — _EIGHT_K_DEFENSES_ENABLED=False)

NUMERICAL GUARDS (5, internal — surfaces only via downstream effects)
  stale_filing_soft           N tickers @ 120-180d
  data_quality_input_corruption 8 tickers (AMCR/BKR/CHTR/ERIE/PSKY/RTX/SPG/VTRS)

ANNOTATE FLAGS (6 active, 1 deferred)
  goodwill_heavy              N
  value_trap_risk             N
  extreme_<method>_estimate   N (across 6 methods)
  stale_filing_soft           N
  data_quality_input_corruption 8
  going_concern_disclosure   54
  auditor_change              0 (DEFERRED)

Total tickers w/ ≥1 active veto: N (≈19% of universe in PR-3d run #15)
Effective Top-5 displacement: 2 (SPG/NVDA suppressed → BKR/HST entered)
```

## Hard contract checks

- Active veto count: 3 in Phase 3d / 4 in Phase 3e+
- `non_reliance_filing` count: 0 in Phase 3d (DEFERRED), >0 in Phase 4+
- `going_concern_disclosure` rate: 1-10% (Mayew expected 1-3%; current
  ~10.8% pending Phase 4 phrase-regex refinement)

## Anti-patterns (do not do)

- Don't double-count: `data_quality_input_corruption` appears in both
  `valuation_warnings[]` and the numerical-guard layer — count it ONCE
  in each section.
- Don't aggregate across runs: each scorecard reflects one run only.
  Use `--baseline-rankings=` for cross-run delta.
- Don't include `entered_top5: false` as a flag — that's a derivative
  of the veto suppression, not a separate defense.

## Related

- `verify-production-output` — Section E is a smaller version of
  this scorecard
- `top5-rotation-audit` — focused dive on entered/exited semantics
- `defense-playbook` reference — `docs/RESEARCH_FINDINGS.md` Defense
  Playbook section
