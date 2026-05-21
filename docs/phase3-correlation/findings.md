# Phase 3 findings — flag correlation analysis

Epic [#150](https://github.com/dackclup/quantrank/issues/150) Phase 3.
Companion to [`summary.md`](summary.md) (raw firing rates + pair tables)
and [`heatmap.png`](heatmap.png) (visual φ-matrix). This doc
**interprets** the numbers and lists actionable conclusions for the
downstream recalibration phases (2.2, 2.5 follow-up) + the post-Phase-2.4
quarterly cohort audit (next: 2026-08-19).

## Methodology recap

- **Universe**: 502 S&P 500 constituents
- **Flag count**: 25 active (firing ≥ 1 stock); 0 dead
- **Metric**: φ-coefficient (Matthews correlation for boolean variables)
- **Redundancy threshold**: |φ| ≥ 0.30 (Cohen 1988 medium effect)
- **Diversity threshold**: |φ| ≤ 0.05 AND both base-rates ≥ 5%
- **Baseline**: production output as of commit
  [`5dfe6287`](https://github.com/dackclup/quantrank/commit/5dfe6287)
  (rankings 2026-05-20, pre-Phase-2.4 — `loss_avoidance_pattern` had
  not yet been rescaled to S&P 500 thresholds)

## Headline findings

### 1. The defense layer is mostly orthogonal — diversity is real

The 35-pair diversity-confirmed list dwarfs the 15-pair redundancy
list. **`altman_distress` is orthogonal to nearly every other flag**
in the layer (φ ≈ 0 with `goodwill_heavy`, `restatement_history`,
`sloan_accruals_top_decile`, `net_issuance_top_decile`,
`accruals_momentum_high`, `beneish_high`, `extreme_*_estimate` family).
The financial-distress signal Altman 1968 captures is genuinely
distinct from the manipulation + valuation-outlier signals layered on
top of it. **Implication**: keep `altman_distress` as a high-weight
veto; do not merge into any composite manipulation index.

### 2. `restatement_history` is independent of the manipulation cluster — safe to recalibrate

The Phase 2.2 plan (tighten `restatement_history` to "amendment + Item
4.02 within 90d" for ~30% → ~70% PPV) was at risk of double-counting
the Sloan / Beneish manipulation signals. The data says no:

| Pair | φ | Interpretation |
|---|---:|---|
| `restatement_history` ↔ `sloan_accruals_top_decile` | +0.008 | Orthogonal |
| `restatement_history` ↔ `accruals_momentum_high` | +0.003 | Orthogonal |
| `restatement_history` ↔ `beneish_high` | (not in top 35 — implies |φ| > 0.05 but still moderate) | Mildly correlated |
| `restatement_history` ↔ `altman_distress` | -0.009 | Orthogonal |

**Conclusion**: Phase 2.2 can proceed without worrying about redundant
stacking. Recalibrated `restatement_history` would carry unique signal.

> **Update 2026-05-21**: Phase 2.2 landed as a parallel-surface
> annotate (`restatement_high_confidence`) rather than tightening
> the existing flag in place — see
> [PR #165](https://github.com/dackclup/quantrank/pull/165). The
> orthogonality finding above still holds: the new flag is
> additive to the existing layer, not a replacement (the
> cohort acceptance check after ≥ 1 production cron decides
> retire-or-split for the bare `restatement_history` flag).

### 3. Warning-band ↔ active-veto pairs are correlated by design — not a redundancy

| Pair | φ | Status |
|---|---:|---|
| `dechow_high` ↔ `dechow_manipulation_veto` | +0.706 | **By design** — warning band is the precursor band |
| `beneish_high` ↔ `beneish_manipulation_veto` | +0.640 | **By design** — same |

These are NOT redundancy candidates — they are intentionally nested
tiers (Tier-3 soft annotate → Tier-2 active veto) per
`manipulation_index.py` provenance comments. The Phase 2.5 weight
docstrings (`BENEISH_HIGH_WEIGHT = 3.0` ≈ half of `BENEISH_VETO_WEIGHT
= 20.0`, calibrated via half-PPV) are validated by these correlations
— the band-veto handoff is working as designed.

### 4. `manipulation_triple_flag` ≡ `dechow_high` at current sample size

`manipulation_triple_flag` (φ = +1.000 with `dechow_high`) fires on
exactly the same 2 stocks as `dechow_high` — both at 0.4% base rate.
At this cohort size, φ = 1.0 is partly an artifact (tiny n) but it
does flag a real issue: **the triple-gate (`Sloan` + `Beneish-high`
+ `Dechow-high` co-fire) is currently dominated by the Dechow signal**.

Interpretation: when the universe grows or thresholds shift, the triple
gate should re-acquire independent signal. For now, the
`TRIPLE_FLAG_WEIGHT = 10.0` engineering-bonus weight (Phase 2.5
gut-feel label) is essentially double-counting Dechow at this base rate.

**Watch in next quarterly audit** (2026-08-19): if
`manipulation_triple_flag` stays φ-locked to `dechow_high`, downgrade
the `TRIPLE_FLAG_WEIGHT` to 0 or fold into `DECHOW_VETO_WEIGHT`.

### 5. `accruals_momentum_high` ↔ `sloan_accruals_top_decile`: moderate, justified

| Pair | φ | Note |
|---|---:|---|
| `accruals_momentum_high` ↔ `sloan_accruals_top_decile` | +0.305 | Moderate overlap; expected per Phase 2.5 docstring |

The Phase 2.5 provenance label for `ACCRUALS_MOMENTUM_WEIGHT`
("Sloan anomaly extended over 4 quarters") is **validated** — the
moderate (not extreme) correlation says momentum captures a related
but not identical signal. The `5.0` annotate weight is defensible.

### 6. The `extreme_*_estimate` family clusters — but `valuation_methods_applicable` already handles this

Three pairs ≥ 0.3 inside the extreme-valuation family:

| Pair | φ |
|---|---:|
| `extreme_graham_estimate` ↔ `extreme_rim_estimate` | +0.515 |
| `extreme_rim_estimate` ↔ `goodwill_heavy` | +0.445 |
| `extreme_graham_estimate` ↔ `goodwill_heavy` | +0.417 |
| `extreme_multiples_ev_ebitda_estimate` ↔ `extreme_multiples_pe_estimate` | +0.409 |

The shared signal is "stock's fundamentals are far from typical → most
valuation methods flag it as an outlier." This is exactly the signal
[PR #161](https://github.com/dackclup/quantrank/pull/161) surfaced as
the positive-framed scalar `valuation_methods_applicable`. **No new
work needed**: consumers should prefer that scalar over counting the
individual `extreme_*_estimate` flags. The individual flags stay in
`valuation_warnings` for per-method debugging, not for filtering.

### 7. `value_trap_risk` ⟂ `extreme_rim_estimate` (negatively correlated)

φ = -0.315: value-trap stocks are LESS likely to have RIM outlier
estimates. Reading: when a stock looks like a value trap (low growth,
low ROE, low MoS), RIM converges to a plausible estimate — RIM's
residual-income mechanic handles slow-growers gracefully. The other
methods (Graham, DCF, multiples) more often disagree on those stocks
because they extrapolate growth differently.

**Implication**: RIM is the right anchor method for value-trap-suspect
stocks. The current ensemble weighting (treat all 6 methods equally
post-outlier-removal) under-leverages this. Future Phase 4j+ (IPCA
factors) could surface a "sector-stable estimator" gate that picks RIM
when `value_trap_risk` fires.

## Rare-but-firing flags (n < 5 each)

5 flags with < 1% firing rate, excluded from the heatmap:

- `dechow_high` (0.4%) — Tier-3 soft annotate
- `manipulation_triple_flag` (0.4%) — joint gate
- `late_filing_notification` (0.4%) — NT-10K / NT-10Q signal
- `dechow_manipulation_veto` (0.2%) — active veto
- `non_reliance_filing` (0.2%) — 8-K Item 4.02

All 5 are intentionally rare (high-confidence / late-stage signals).
None are dead. Re-examine in Q3 2026 audit if base rates haven't moved.

## Post-Phase-2.4 follow-up

The current baseline does NOT include `loss_avoidance_pattern` firing
data — Phase 2.4's threshold rescale ($5M → $50M, $0.05 → $0.50)
[merged in PR #163](https://github.com/dackclup/quantrank/pull/163) has
not yet been applied to a production cron run. **Re-run this analysis
post-2026-05-25** (next weekly cron) with `loss_avoidance_pattern`
included; expected base rate ~5-15% per Burgstahler-Dichev 1997 cohort
priors.

## Decision matrix for Phase 2.x downstream PRs

| Action | Decision | Evidence |
|---|---|---|
| Phase 2.2 — `restatement_high_confidence` annotate ([PR #165](https://github.com/dackclup/quantrank/pull/165)) | 🟡 **In flight** | Orthogonal to manipulation cluster (§2) — additive surface; bare-flag retire/split decision waits on cohort data |
| Phase 2.5 — downgrade `TRIPLE_FLAG_WEIGHT` | ⏳ **Watch** Q3 audit | φ = +1.0 with `dechow_high` may be small-n artifact (§4) |
| Phase 2.5 — keep `ACCRUALS_MOMENTUM_WEIGHT = 5.0` | ✅ **Keep** | Moderate (φ = +0.305), not redundant with Sloan (§5) |
| Phase 2.5 — drop individual `extreme_*_estimate` annotates | ❌ **Don't drop** | Per-method debugging value preserved; downstream uses `valuation_methods_applicable` (§6) |
| Phase 4i/4j/4k — JKP/Qlib/IPCA factor adds | 🎯 **Orthogonality target** | Compare new factors against `altman_distress` and `restatement_history` baseline (§1, §2) |

## Reproduce

```bash
python scripts/phase3_flag_correlation.py \
    --data-dir frontend/public/data/stocks \
    --output-dir docs/phase3-correlation
```

Re-run after every quarterly cohort audit + after each Phase 2.x
recalibration PR lands. Diff `firing_rates.csv` and
`redundancy_candidates.csv` between baselines to track drift.
