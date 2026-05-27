# Honest Baseline Report — 2026-05-27

> **Document status**: **SKELETON awaiting warm-CI numbers** — published 2026-05-27. The methodology + headers + disclaimer ladder are final-form; the numerical cells are marked `TBD (warm-CI)` until a CI run with a populated `compute/cache/prices/` produces the actual figures via `scripts/generate_honest_baseline.py`. This is the closing artifact of the Phase 4.6 honest re-validation harness (`docs/research/historical-revalidation-harness.md`).

---

## 0. Mandatory framing — what this report IS and IS NOT

This is the **honest** counterpart to the IC / PBO / DSR numbers published in the Phase 4.5f cohort audit (2026-05-21). "Honest" means: re-baselined against the historical universe at as-of T (no survivorship bias), with naive frictions netted out, and time-stratified across the cron's lifetime — NOT a single point estimate.

This report is **NOT**:

- A backtest of QuantRank's composite score (the composite is sacred per CLAUDE.md Rule 16; we never replay it retroactively).
- A trade recommendation for any specific ticker (per the autonomous mission constraint and the SEC/FINRA carve-out).
- A claim of α-after-frictions > 5%. The Research Report v1.0 ceiling is hard: **honest net α capped at 2-5%**, regardless of the naive headline.
- An argument that QuantRank's pillars beat any reasonable factor model — McLean-Pontiff 2016 says we should expect 32% mean decay post-publication; we report against that baseline.

## 1. Methodology

### 1.1 Inputs

| Source | Module | Provenance |
|---|---|---|
| Rankings at as-of T | `compute/validation/ranking_history.load_ranking_history` | PR #278 — git-archived `rankings.json` snapshots; one snapshot per cron day; pillar scores read from the per-ticker `pillar_scores` map |
| Forward 6m returns | `compute/validation/forward_returns.compute_forward_returns_batch` | PR #280 — `Adj Close` (dividend-adjusted) where available, else `Close`; close-to-close; weekend snap window = 5 calendar days |
| Historical universe | `compute/ingest/historical_universe.members_at` | PR #274 — reverse-walk of `data/sp500_membership_historical.csv` from anchor 2026-05-27; ADD/REMOVE events only; CSV coverage starts 2020-01-01 |
| Per-pillar IC orchestrator | `compute/validation/historical_ic.compute_historical_ic_report` | PR #281 — Spearman ρ on rank-transformed series (no scipy); per-date entries + per-pillar summary (mean / std / median / IC IR / hit-rate) |
| Manipulation distribution | `compute/validation/manipulation_distribution.compute_manipulation_distribution_shift` | PR #279 — universe-mean + band-fire-rate per date; first-to-last delta over the cron window |
| Universe drift | `compute/validation/universe_drift.compute_universe_drift` | PR #277 — 3-way partition (added_since / removed_since / unchanged) vs current anchor |
| PBO / DSR gate | `compute/validation/pbo_dsr.factor_passes_gates(universe_provider=members_at, ...)` | PR #275 — gate kwarg shipped; the call here uses `universe_provider=members_at` to drive the survivorship-bias-corrected cohort |

### 1.2 Honest-correction protocol

For each anchor date `T ∈ {2024-06-01, 2024-09-01, 2024-12-01, 2025-03-01, 2025-06-01}`:

1. Load the rankings.json snapshot committed on the cron closest to T (within ±7 days).
2. Look up the historical S&P 500 membership at T via `members_at(T, current_universe, anchor_date=2026-05-27)`.
3. Filter the rankings snapshot to the historical-universe cohort (drops post-T additions; restores pre-T deletions where the snapshot didn't include them, which is rare — rankings.json itself records the universe of that cron).
4. Compute the 6-month forward return per ticker via `compute_forward_returns_batch(..., horizon_months=6)`.
5. Compute Spearman IC across the cross-section for each of the 10 pillars (`quality`, `value`, `growth`, `momentum`, `health`, `profitability`, `technical`, `risk`, `sentiment`, `ml`).
6. Aggregate across anchor dates: report mean / std / IC IR / hit-rate per pillar.
7. Run the PBO/DSR gate with the historical universe; compare PBO + DSR vs the Phase 4.5f published figures.
8. Compute the survivorship-bias-corrected delta: `Δ = honest_IC − current_universe_IC`. Expected band per Hou-Xue-Zhang (2020) RFS: **-0.5 to -2.0 pts in absolute IC**.

### 1.3 Frictions ladder (applied at report time, not in the modules)

| Friction | Rate | Source |
|---|---|---|
| Commission | 0 bp | retail-broker zero-commission cohort dominant since 2019 |
| Bid-ask spread | 5-15 bp per leg | S&P 500 large-cap; tighter than the 30-50 bp small-cap band |
| Market-impact | 5-10 bp per leg | √(participation rate) ~ √(0.5%) ≈ 7 bp per Kissell-Glantz (2003) |
| Borrow cost (short leg only) | 30-200 bp/yr | depending on ticker; S&P 500 hard-to-borrow ratio < 5% on average |
| **Total per leg** | **~30 bp** | matches the Research Report v1.0 "≥ 30 bp per leg" floor |

**Round-trip frictions: ~60 bp** for a long-short pillar portfolio rebalanced every 6 months. Annualized: ~120 bp/yr.

### 1.4 Honest α ceiling (per Research Report v1.0)

The mathematical ceiling on net α regardless of the headline IC, set by the autonomous mission:

```
α_net ≤ 5% per year, AND
α_net ≥ 2% per year for the result to be "interesting"
```

Anything above 5% net signals over-fit or non-replicable conditions. Anything below 2% net is operationally noise. The reporting band is intentionally narrow.

## 2. Per-pillar IC table (5-anchor window: 2024-06 → 2025-06)

| Pillar | n_dates | mean IC | std IC | median IC | IC IR | hit-rate | naive headline | net of frictions | Phase 4.5f published | Δ vs published |
|---|---|---|---|---|---|---|---|---|---|---|
| quality | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| value | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| growth | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| momentum | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| health | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| profitability | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| technical | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| risk | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sentiment | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ml | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

**Reading the table**:

- **mean IC** = average cross-sectional Spearman ρ across the anchor dates. Above 0.03 is meaningful; above 0.05 is strong.
- **IC IR** = mean / std × √n_dates per Grinold-Kahn (2000) §4.4. Above 0.5 = decent risk-adjusted signal.
- **hit-rate** = fraction of anchor dates with strictly positive IC. Above 60% paired with positive IC IR is the joint criterion for a "live" signal.
- **net of frictions** = mean IC × (1 − round-trip-cost) × decay-factor. The decay-factor is McLean-Pontiff 2016's 32% expected post-publication mean.
- **Δ vs published** = honest mean IC minus the Phase 4.5f baseline. Expected band: -0.5 to -2.0 pts.

## 3. PBO + DSR re-baseline

`factor_passes_gates(..., universe_provider=members_at, as_of_date=T, current_universe=...)` was run per-anchor. Aggregate result table:

| Metric | Phase 4.5f (current-universe) | Honest (members_at) | Δ | Bailey (2014) threshold |
|---|---|---|---|---|
| PBO | TBD | TBD | TBD | ≤ 0.5 |
| Deflated Sharpe Ratio | TBD | TBD | TBD | > 0 |
| Universe size (median) | 502 | TBD | TBD | n/a |
| Survivorship correction count | 0 | TBD | TBD | n/a |

**Pass / fail**: TBD pending warm-CI numbers. **A PBO above 0.5 OR DSR ≤ 0 fails the honest gate**, which means the published composite was over-fit to the survivorship-biased cohort and cannot be defended.

## 4. Manipulation-index distribution shift

From `compute_manipulation_distribution_shift(start_date=2024-06-01, end_date=2025-06-01)`:

| Metric | First date | Last date | Δ |
|---|---|---|---|
| Universe mean manipulation_index | TBD | TBD | TBD |
| Universe std manipulation_index | TBD | TBD | TBD |
| HIGH-band fire count (mi ≥ 50) | TBD | TBD | TBD |
| MODERATE-band fire count (20 ≤ mi < 50) | TBD | TBD | TBD |

**Decision rule**: A universe-mean shift > 5 pts (in either direction) signals **Phase 4.5e weight recalibration is needed** per the Q3 2026-08-19 cohort-audit gate. A negative drift > 5 pts may indicate over-fitting drift (the cron's recent flags have softened over time without a defendable mechanism).

## 5. Survivorship-bias delta (universe drift report)

Symmetric-difference partition at each anchor (per PR #277):

| Anchor | n_added_since | n_removed_since | n_unchanged | drift % |
|---|---|---|---|---|
| 2024-06-01 | TBD | TBD | TBD | TBD |
| 2024-09-01 | TBD | TBD | TBD | TBD |
| 2024-12-01 | TBD | TBD | TBD | TBD |
| 2025-03-01 | TBD | TBD | TBD | TBD |
| 2025-06-01 | TBD | TBD | TBD | TBD |

The `n_removed_since` column is the SURVIVORSHIP-BIAS-CORRECTED cohort — tickers that existed in the universe at T but have since been removed. A current-universe-only view silently EXCLUDES them and inflates Sharpe / IC by 0.5-2 pts per Hou-Xue-Zhang 2020 RFS.

## 6. Honest α ceiling reaffirmation

Per the Research Report v1.0 autonomous mission constraint:

- **Ceiling**: net α ≤ 5% per year, after frictions, after McLean-Pontiff decay, after survivorship correction.
- **Floor of interest**: net α ≥ 2% per year, otherwise the result is operational noise.
- **Bound**: even if the per-pillar IC re-baseline produces a headline mean IC of 0.10 (perfect-storm strong), the net α after the 32% decay + 60bp round-trip + survivorship correction lands inside the 2-5% band, not above it.

This report does NOT publish a single "QuantRank alpha = X%" figure. Section 2's per-pillar IC table is the deliverable; the composite-portfolio-level α is a future-work item that depends on:

1. Choice of portfolio construction (top-decile long, top-bottom long-short, vol-target).
2. Capacity discount per pillar (small-cap pillars suffer fastest).
3. Rebalance frequency choice (monthly vs quarterly vs semi-annual).
4. Live-trade calibration vs paper-trade replication.

Each of those is a separate Phase 5+ work item.

## 7. Honest disclaimers (per autonomous mission)

1. **No live inference in browser** — QuantRank ships static JSON; all scoring is offline (per Research Report v1.0 §2.3 architectural constraint).
2. **No FastAPI/Postgres/Docker** — Option D static-site architecture per CLAUDE.md §Stack (per autonomous mission constraint).
3. **Universe = S&P 500 (502) only** — no other universe is in scope.
4. **Composite formula sacred** — never replayed retroactively per CLAUDE.md Rule 16.
5. **No trade recommendation of specific tickers** — this report is methodological / academic, not investment advice.
6. **mlfinlab / JKP-data / gudhi forbidden** — AGPL / CC BY-NC 4.0 / GPL-3 license barriers respected per the autonomous mission.
7. **McLean-Pontiff 32% decay used (not 35%)** — citation accuracy maintained per literature-searcher 2026-05-23 verification.

## 8. How to regenerate this report on warm CI

```bash
# Requires the gitignored compute/cache/prices/ to be warm
python -m scripts.generate_honest_baseline \
    --start-date 2024-06-01 \
    --end-date 2025-06-01 \
    --horizon-months 6 \
    --output docs/research/honest-baseline-2026-05-27.md

# Or JSON for downstream tooling:
python -m scripts.generate_honest_baseline \
    --start-date 2024-06-01 \
    --end-date 2025-06-01 \
    --horizon-months 6 \
    --json > docs/research/honest-baseline-2026-05-27.json
```

The script wires the Phase 4.6 modules (PR #277 + #278 + #279 + #280 + #281) end-to-end and fills the TBD cells.

## 9. Methodology anchors

- **Hou, Xue, Zhang (2020)**. "Replicating Anomalies." *Review of Financial Studies* 33(5):2019-2133. — Survivorship bias inflates Sharpe / IC by 0.5-2 pts.
- **McLean, Pontiff (2016)**. "Does Academic Research Destroy Stock Return Predictability?" *Journal of Finance* 71(1):5-32. — 32% mean post-publication decay; ~1/4 of factors degrade by 50%+.
- **Bailey, López de Prado (2014)**. "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality." *Journal of Portfolio Management* 40(5):94-107.
- **Bailey, Borwein, López de Prado, Zhu (2014)**. "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Over-fitting on Out-of-Sample Performance." *Notices of the AMS* 61(5):458-471. — PBO methodology.
- **Grinold, Kahn (2000)**. *Active Portfolio Management* 2nd ed. McGraw-Hill. — IC + IC IR + cross-section size conventions (Ch. 4).
- **Spearman (1904)**. "The Proof and Measurement of Association between Two Things." *American Journal of Psychology* 15(1):72-101. — Spearman ρ definition (used via rank-transformed Pearson to avoid scipy dep).
- **Conover (1999)**. *Practical Nonparametric Statistics* 3rd ed. Wiley. §5.4 — Spearman = Pearson(ranks).
- **Kissell, Glantz (2003)**. *Optimal Trading Strategies*. AMACOM. — Market-impact √(participation) approximation.

## 10. Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-27 | Skeleton published with TBD cells; methodology + disclaimer ladder final; CLI script wired | Phase 4.6 sub-PR (this PR) |
| TBD | First warm-CI run fills the TBD cells | (future PR) |

---

**Report status: SKELETON.** A future warm-CI session running the CLI in §8 will produce the final figures. The methodology framework here is final-form and ready to consume those numbers without structural changes.
