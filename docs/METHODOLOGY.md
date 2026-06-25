# Methodology

> Full user-facing methodology ships with **v1.0** (end of Phase 3). This page
> is the working draft; sections marked _(Phase 3c)_ or _(Phase 3d)_ are
> live in production as of schema `0.6.0-phase3d` (2026-05-10).

QuantRank produces, per stock:

- **Composite StockRank** — a single 0–100 score. _(Phase 3b)_
- **8 pillar sub-scores** — quality, value, growth, momentum, health,
  profitability, technical, risk. (`sentiment` + `ml` are placeholders
  redistributed pro-rata until Phases 5–6.) _(Phase 3b)_
- **Fair-price ensemble** — median of 6 valuation methods + outlier-excluded
  max. _(Phase 3c)_
- **Margin of safety** — `(median − current) / median × 100`. _(Phase 3c)_
- **33 declared boolean flags** — 7 active vetoes + 26 annotate-only flags
  (declared; ~27 currently emit, the rest reserved) — plus 5 numerical guards
  and the `manipulation_index` rollup that composes the annotate set
  into a single 0–100 severity dial. Annotate-and-veto-Top-N philosophy:
  defenses **never modify the composite**, only suppress the entered-top-5
  badge or null specific fair-price methods. _(Phase 3b/3c/3d, expanded
  through Phase 4.5a–4.5e)_
- **Top-5 SHAP factors** — why the score is what it is. _(Phase 5+)_

## How scoring works

1. **Ingest** — pull free-tier data (yfinance, SEC EDGAR; FRED, Finnhub,
   Reddit in later phases).
2. **Features** — compute 60+ classical metrics across 8 pillars. Phase 4
   layers in OSAP / JKP / Qlib / IPCA latent factors.
3. **Normalize** — winsorize at 5/95, then sector-relative percentile rank
   for fundamentals (absolute rank for risk and momentum). Sector medians
   impute missing values (Rule 7).
4. **Aggregate** — average each pillar's normalized member metrics.
5. **Composite** — weighted sum across pillars (weights below). Sentiment
   + ML weights redistribute pro-rata until those pillars go live.
6. **Defense layer** _(annotate-and-veto-Top-N, never scoring inputs;
   Phase 3b/3c)_ — applied **after** composite scoring so flags surface in
   the UI without touching the rank order. See "Defense layer" below.
7. **Fair-price ensemble** _(Phase 3c)_ — 6 methods, median + max +
   margin-of-safety. See "Fair-price ensemble" below.

## Composite weights (10 pillars, sum = 1.00)

| Pillar | Weight | Status |
|---|---|---|
| quality | 0.22 | active |
| value | 0.18 | active |
| growth | 0.10 | active |
| momentum | 0.10 | active |
| health | 0.08 | active |
| profitability | 0.05 | active (Phase 3) |
| technical | 0.04 | active (Phase 3) |
| risk | 0.03 | active |
| sentiment | 0.10 | placeholder (Phase 6) |
| ml | 0.10 | placeholder (Phase 5) |

For Phase 3, sentiment + ml are null; their 0.20 weight is redistributed
pro-rata across the active pillars (effective weights divided by 0.80).

## Fair-price ensemble _(Phase 3c)_

Six methods are computed per stock, then aggregated to a single
**median** fair price + a separate **max excluding outliers**. The
median is the headline number on the rankings page; the max gives an
"if the optimistic methods are right" upper bound on the detail page.
Per-method results — including skip reasons — are surfaced for
transparency.

### The six methods

| Method | What it computes | Anchor |
|---|---|---|
| **Graham** | `√(22.5 × eps_3y_avg × TBVPS)` | Defensive valuation; uses a 3-year average EPS and **tangible** book value (`equity − goodwill − intangibles_net`). Rejects growth premia. |
| **Multiples — P/E** | `peer_PE_median × eps_ttm` | Sector / sub-industry peer median P/E with a 4-tier walk (sub_industry → industry → sector → broad-ex-Fin-Util) and 5/95 winsorization to limit a single peer's leverage. |
| **Multiples — P/B** | `peer_PB_median × bvps_reported` | Reported book value per share; same 4-tier walk. |
| **Multiples — EV/EBITDA** | `peer_EVEBITDA_median × ebitda − net_debt`, then `/ shares` | Enterprise-value method; nets debt back out to per-share equity. |
| **Residual income (RIM)** | `TBVPS + Σ (ROE − Ke) × B / (1+Ke)^t` (Penman 2013) | Constant-ROE 5-year forecast with conservative zero-terminal-value truncation. Skipped when ROE < cost of equity (`value_trap_risk`). |
| **DCF** | Two-stage: 5y flat-FCF explicit + Gordon terminal | FCF normalized via positives-only median over a 5-year window. Terminal-g hard cap = `min(0.03, WACC − 100 bp)`. Skipped for Financials + Utilities (where FCF is structurally distorted). |

Tangible BVPS (`equity − goodwill − intangibles_net`) is shared by Graham
and RIM. The full netting (intangibles, not just goodwill) is per Penman
2013 §"Conservative residual income".

### Aggregation

- **Median** = median of every applicable method's value. Robust to a
  **single** outlier (Huber 1981 §1.4 — the median tolerates a minority of
  extreme estimates) **but NOT "robust by construction" for even-n.** With
  an even applicable-method count the median is the *mean of the 3rd+4th
  order statistics*, so a **minority of 2** extreme-flagged estimates still
  drags it (the FFIV pattern: Graham+RIM collapsing on a goodwill-heavy
  software name pulled the median to −23.6% MoS, vs +15.8% on the
  non-extreme subset), and a **majority**-extreme count passes the
  breakdown point and collapses the median entirely (the APP −1257%
  pattern). The #177 shadow `median_trimmed` field (PR-A, schema 0.10.24)
  *measures* this even-n drag; a two-regime trim of extreme-flagged methods
  from the central estimate is gated behind the Q3 2026-08-19 forward-OOS
  validation (V55.1 condition (2) via a measured shadow record, not a
  synthetic backfill holdout — see PHASE_STATUS_INFLIGHT.md). Until then
  the live `median` keeps ALL applicable values.
- **Max** = largest method value **excluding** outliers (defined as
  `value > 5 × current_price` OR `value < 0.2 × current_price`). The
  outlier guard is Defense #4; the spec is "exclude from MAX, keep in
  MEDIAN" because the median's robustness already handles dispersion
  while the max should not anchor user expectations of upside on a
  pathological estimate.
- **Low / high** = min and max of all applicable values (no outlier
  exclusion). Surfaced for diagnostics.
- **Margin of safety (MoS)** = `(median − current) / median × 100`.
  Sign convention: positive = median above market = potential
  undervaluation. Rendering is clamped to `[−99%, +500%]` in the UI;
  underlying value is preserved in the JSON for downstream analysis.

### Why median, not mean

Both fair-price estimates and trailing returns have heavy tails. A
single Graham estimate of $27 on a $293 stock (the AAPL spot-check
pattern) would drag a mean toward zero; the median is unmoved. We
also compute the max separately so the "Graham was conservative,
RIM was right" upside scenario is still surfaced. This dispersion is
information — the difference between a Graham floor and a RIM ceiling
is itself a signal about how growth-loaded the stock is.

**The even-n limit (#177).** "The median is unmoved" holds for a *single*
outlier; it does NOT hold when 2+ of an even applicable-method count are
extreme-flagged (see §Aggregation — the median of 6 is the mean of the
two middle order statistics, so a minority drag is real, and a majority
collapses it). The trimmed-median diagnostic (`median_trimmed`, PR-A)
quantifies the residual even-n drag per stock; the behavioral correction
(trimming extreme-flagged methods from the central estimate) is
Q3-2026-08-19-gated on a forward-OOS shadow record.

### Why dispersion matters

A stock where Graham, multiples, RIM, and DCF all cluster within ±20% of
each other is a high-confidence valuation. A stock with $27 / $194 / $209
spread (AAPL pattern) means the methods disagree on whether to capitalize
growth — which is a separate signal from the median itself. The
fair-price card on the detail page surfaces all six values so the reader
can judge that dispersion directly.

### Sign convention for MoS

Following Damodaran (2012, *Investment Valuation*, 3rd ed.) we use
`(intrinsic − current) / intrinsic` so positive = undervalued. This
matches the textbook formula; some practitioners use the inverse
(`current / intrinsic − 1`) which has identical sign but a different
magnitude.

## Defense layer _(Phase 3b/3c/3d)_

QuantRank treats fraud detection and data-quality protection as a
**separate, explicit layer** that runs after composite scoring. The
core philosophy (Rule 16):

> Defenses **annotate**; only the Top-5 badge layer **vetoes**.

The composite score is unchanged regardless of which flags fire. This
matters because it makes the score interpretable independently of the
defense set, lets the user see "this stock is high-rank but has flags X,
Y, Z", and prevents defense overhaul from invalidating the historical
composite.

### Active vetoes (7) — suppress the entered-top-5 badge

| Veto | Rule | Source |
|---|---|---|
| `altman_distress` | Z″ < 1.10 | Altman 1968, Hotchkiss 2003 update for non-manufacturers |
| `sloan_accruals_top_decile` | Within-sector top decile of accruals/assets | Sloan 1996 *TAR* |
| `net_issuance_top_decile` | Within-sector top decile of NSI over 365 days | Pontiff-Woodgate 2008 / Daniel-Titman 2006 *JF* |
| `non_reliance_filing` | 8-K Item 4.02 within trailing 365 days | Schroeder 2024 SSRN |
| `beneish_manipulation_veto` _(Phase 4.5a)_ | Beneish M-score > −1.78 (full 8-ratio) | Beneish 1999 *FAJ* |
| `dechow_manipulation_veto` _(Phase 4.5a)_ | Dechow F-score > 3.0 (Model 1, simplified RSST→TATA proxy) | Dechow et al. 2011 *CAR* |
| `data_quality_input_corruption` _(Phase 3c)_ | TBVPS > $10,000/share (snapshot inputs, fires in `risk_overlay.py`) OR any fair-price method output > $10,000/share (`ensemble.py`) → null all 6 methods; suppresses `entered_top5` via the upstream snapshot path | Internal — Step 7.5 sanity guard catching upstream `shares_outstanding` corruption |

### Numerical guards (5) — null specific fair-price methods + emit a warning

| Guard | Rule | Source |
|---|---|---|
| Stale filing | `latest_filed_date` > 120 days → soft annotate; > 180 days → null all 6 methods | Practitioner default |
| Outlier 5× / 0.2× | Method value outside `[0.2×, 5×]` of current price → exclude from MAX, keep in MEDIAN | Internal — see "Aggregation" |
| Terminal-g cap | DCF terminal growth ≤ `min(0.03, WACC − 100 bp)` | Damodaran 2012 |
| Sector exclusions | EV/EBITDA skipped for Financials; DCF skipped for Financials + Utilities; Quality pillar metrics gated by sector (`magic_formula`, `ebit_based_roic`, `gross_profitability`, `asset_turnover` per Greenblatt 2005) | Greenblatt; sector-method spec |
| Data-quality $10K ceiling | If any method computes > $10,000/share → null all 6 + emit `data_quality_input_corruption`. Catches upstream ingestion bugs (e.g., `shares_outstanding` in wrong units) before user-visible nonsense. | Internal — Step 7.5 (post-spot-check) |

### Annotate-only flags (24) — surfaced in `valuation_warnings` or `tier2_events`, no behavioral effect

- `goodwill_heavy` — TBVPS / BVPS_reported < 0.5 (cautions that
  reported book is misleading)
- `low_liquidity` _(S&P 1500 Slice 4)_ — trailing 30-day mean dollar
  volume (price × volume) < `ADV_FLOOR_USD` ($5M). Anchor: Amihud 2002
  *J. Financial Markets* (dollar volume is the ILLIQ denominator;
  Amihud-Mendelson 1986, Kyle 1985 price-impact). The $5M figure is a
  calibration convention at the conservative end of the institutional
  ADDV-floor band — NOT a paper-table cutoff. Annotate-only (in
  `valuation_warnings`, not `risk_flags`): rank-neutral, no `cautious`,
  no Top-5 suppression, no `manipulation_index` weight. Fires on ~5 sp600
  small-caps per sp1500 cron (the cron default flipped to sp1500
  2026-06-21); was dormant on the prior sp900 universe.

  **Pre-registered annotate→veto promotion (issue #544, methodology-scientist
  RATIFY-WITH-CONDITIONS 2026-06-23 — DOCS-ONLY, not yet wired).** The $5M
  `ADV_FLOOR_USD` annotate cutoff was re-derived against the realized sp600
  ADV distribution (n=602: p0.5 ≈ $4.64M, p1 ≈ $5.05M, p2.5 ≈ $6.30M, median
  ≈ $31.5M; the $5M floor sits at ≈ sp600 p0.8). Promotion plan: keep $5M as
  the broad **annotate** and add a separate, stricter **veto** floor
  `ADV_VETO_FLOOR_USD = $3M` at the **Q3 2026-08-19 cohort audit** — a $3M
  veto flips only the genuinely un-tradeable tail (BFS/CENT/SBSI) to
  `cautious` + Top-5 suppression, while the $4.6-5.0M band (SMP/CPF) retains
  the softer annotate. The veto is an **investability filter, NOT an alpha
  claim** — illiquidity carries a return *premium* (Amihud 2002), so the
  hard-suppress asserts "un-tradeable for this audience", an owner-policy
  decision (sign-off required, not a silent auto-promote). Acceptance bands
  the promotion must clear (lock before 2026-08-19):
  - **B1 · Firing rate** — sp1500 `low_liquidity_annotate_count` ∈ [3, 15]
    (≤ 1.0% of sp1500 / ≤ 2.5% of sp600). Observed: 5 (0.33%).
  - **B2 · Population stability** — fired-set ticker churn ≤ 30% cron-over-cron.
    Observed: 0% across 5 sp1500 crons ({BFS, CENT, CPF, SBSI, SMP}).
  - **B3 · Top-N blast radius** — ZERO fired names within rank ≤ 10 OR in the
    AI-pick basket at promotion (HARD gate). Observed: 0 (closest BFS, rank 257).
  - **B4 · Coverage** — `average_dollar_volume` non-null ≥ 99% of sp1500.
    Observed: 99.93% (1503/1504).
  - **B5 · Cron count** — ≥ 8 full-sp1500 crons of firing data at promotion.
    Observed: 5 as of 2026-06-23 (~3 more weekday crons → mid-July).
- `value_trap_risk` — RIM skipped because ROE < cost of equity (Penman
  2013) AND trailing P/E below the sector-peer median (LSV 1994 cheap
  leg) — two-factor gate live since #586 PR-2; loss-making /
  undefined-P/E firms are EXEMPT
- `extreme_<method>_estimate` — one of the 6 methods (`graham`,
  `multiples_pe`, `multiples_pb`, `multiples_ev_ebitda`, `rim`, `dcf`)
  produced an outlier value outside the `[0.2×, 5×]` band of current
  price (excluded from MAX, kept in MEDIAN). Surfaces per-method as a
  separate warning.
- `stale_filing_soft` — filing > 120d but ≤ 180d
- `data_quality_input_corruption` — also surfaced as the `reason`
  on every method when the $10K ceiling fires
- `going_concern_disclosure` _(Phase 3d)_ — going-concern phrase
  found in the most recent 10-K MD&A. Mayew-Sethuraman-Venkatachalam
  2015 *TAR* shows mere mention is the predictive signal even when
  paired with management's denial. False-positive rate is non-trivial
  (firms cite the language when describing peers or historical events);
  acceptable here because the flag does not veto. Implementation:
  `compute/scoring/going_concern.py` with a 14-phrase Loughran-McDonald
  dictionary subset (CC BY 4.0).
- `auditor_change` _(Phase 3d)_ — 8-K Item 4.01 within trailing 730
  days. Reg S-K Item 304 disclosure. False-positive rate too high for
  veto: audit-firm restructuring fires the same item, and many
  changes are benign rotation. Surfaced for human review on the
  detail page.
- `accruals_momentum_high` _(Phase 4.5d)_ — Δ(TATA) over the trailing
  3 fiscal years > +0.05, where `TATA = (NetIncome − OperatingCashFlow)
  / TotalAssets` (Sloan 1996 *TAR* 71(3) §IV accruals backbone).
  Trajectory variant of the snapshot-only `sloan_accruals_top_decile`
  veto — catches a year-over-year escalation in accrual reliance that
  a single-snapshot top-decile filter misses. Calibration anchor:
  Beneish 1999 *FAJ* Δ(M-score) > +0.5 maps via the TATA coefficient
  β_TATA = 4.679 → ΔTATA > 0.107; we use +0.05 as the practitioner
  one-ratio adaptation when shortening from the 8-ratio Beneish
  signal. Xie 2001 *TAR* §IV established that accrual persistence
  amplifies the Sloan anomaly, motivating the trajectory variant.
  Threshold provenance: **GUT-FEEL** (one-ratio adaptation; PPV not
  yet measured on the QuantRank universe). Cohort-acceptance check
  queued for Q3 2026-08-19.
- `loss_avoidance_pattern` _(Phase 4.5d, rescaled PR #163)_ —
  `NetIncome ∈ [$0, $50M]` OR `EPS ∈ [$0, $0.50]` for 3+ consecutive
  fiscal years. Burgstahler-Dichev 1997 *JAE* 24(1) §3 Table 2
  kink-at-zero "small positive earnings" cohort signature, with bands
  rescaled 10× from the original $5M / $0.05 1990s Compustat cutoffs
  to match the S&P 500's larger firm-size distribution (mean NI > $1B,
  mean EPS > $5; pre-rescale firing rate was 0/502). Ships side-by-
  side with the size-invariant Roychowdhury sibling below. Threshold
  provenance: **LITERATURE-ANCHORED** on the kink-at-zero signature;
  **GUT-FEEL** on the 10× rescale magnitude (engineering choice
  pending cohort acceptance). Q3 2026-08-19 decision: retire the
  absolute-$ variant, keep both, or split weights vs the size-
  invariant sibling.
- `loss_avoidance_pattern_size_invariant` _(Phase 4b)_ —
  `NI / TotalAssets ∈ [0, 0.005]` (0.5% of assets) for 3+
  consecutive fiscal years. Roychowdhury 2006 *JAE* §5.2
  suspect-firm definition (reaffirmed by Donelson-McInnis-Mergenthaler
  2013 *TAR* as the canonical small-profit cohort cutoff). Size-
  invariant sibling of the absolute-$ `loss_avoidance_pattern` flag;
  catches chronically thin-margin large caps the BD 1997 dollar
  band misses (e.g., where NI > $50M but NI/TA stays near zero
  because the asset base is multi-billion). Annotate-only — both
  flags ship side-by-side pending the Q3 2026-08-19 quarterly-audit
  decision.
- `rem_suspect` _(Phase 4.5c, PR #95)_ — Composite of three real-
  activities earnings-management proxies: abnormal CFO, abnormal
  Production, abnormal Discretionary Expenses (cuts to advertising /
  R&D / SG&A). Roychowdhury 2006 *JAE* 42(3) §5.2 establishes the
  three-proxy battery as the canonical REM signature; firms managing
  earnings via real activities (rather than accruals) understate CFO
  + DiscExp and overstate Production relative to sector-cohort
  norms. Donelson-McInnis-Mergenthaler 2013 *TAR* reaffirms the
  proxy set against the post-SOX cohort. Distinct from the
  `loss_avoidance_pattern_size_invariant` sibling: that flag
  identifies cohort *membership* (chronic small positives),
  `rem_suspect` identifies the *mechanism* (which abnormal
  accounting moves are being used within the cohort). Threshold
  provenance: **LITERATURE-ANCHORED** (Roychowdhury 2006 three-
  proxy cohort cutoffs); φ-correlation with the two loss-avoidance
  flags watch-listed for the Q3 2026-08-19 quarterly audit per
  PR #164 baseline analysis.
- `beneish_high` _(Phase 3e)_ — Beneish M-score `∈ [−2.22, −1.78]`
  (warning band immediately below the active-veto threshold of
  −1.78). Beneish 1999 *FAJ* §"The Detection of Earnings
  Manipulation" identifies M > −1.78 as the manipulation-candidate
  threshold (76% manipulator capture, 17.5% FP); Beneish-Lee-Nichols
  2013 *FAJ* §4 reports the warning-band PPV at ~35-40% vs ~75%
  above the veto threshold. Annotate-only — the veto sibling
  `beneish_manipulation_veto` already covers the high-PPV tail.
  Threshold provenance: **LITERATURE-ANCHORED** (Beneish 1999 cohort
  cutoff; warning-band width matches Beneish-Lee-Nichols 2013).
- `dechow_high` _(Phase 3e)_ — Dechow F-score `∈ [2.45, 3.0]`
  (warning band immediately below the active-veto threshold of 3.0).
  Dechow-Ge-Larson-Sloan 2011 *CAR* 28(1) Table 9 reports the
  warning-band PPV at ~25-30% vs ~50% above the veto threshold. The
  veto sibling `dechow_manipulation_veto` already covers F > 3.0
  cases (AAER ground truth). Threshold provenance:
  **LITERATURE-ANCHORED** (DGLS 2011 cohort calibration);
  φ-correlation with `accruals_momentum_high` watch-listed for Q3
  cohort audit per PR #164 baseline analysis.
- `manipulation_triple_flag` _(Phase 4.5a.3 joint-gate)_ — Co-fires
  when `sloan_accruals_top_decile` AND `beneish_high` AND
  `dechow_high` all fire on the same ticker. The three quant
  defenses share an accruals / discretionary-items backbone
  (Sloan 1996, Beneish 1999, Dechow 2011) → joint-gate isolates the
  multi-signal regime where any single 20-pt veto already saturates
  1/5 of the manipulation-index cap. PR #164 Phase 3 correlation
  analysis flagged this gate as a redundancy-candidate with
  `dechow_high` at current sample size (φ ≈ 0.6+); retain pending
  Q3 2026-08-19 cohort decision. Threshold provenance: **GUT-FEEL**
  (no academic source prescribes a joint-gate weight; tuned to push
  triple-flag stocks past the 60-pt mid-band of the manipulation
  index rollup).
- `restatement_history` _(Phase 4.5d, bare flag)_ — Any 10-K/A or
  10-Q/A amendment filing in the trailing 5-year window. Hennes-
  Leone-Miller 2008 *TAR* 83(6) §"The Importance of Distinguishing
  Errors from Irregularities" splits amendments roughly 80/20
  between clerical errors (non-malicious) and irregularities
  (fraud); bare-flag material-restatement PPV ~30%. Lower-confidence
  sibling of `restatement_high_confidence` (next bullet). Threshold
  provenance: **LITERATURE-ANCHORED on the cite, GUT-FEEL on the 5y
  window** (practitioner default; HLM 2008 §3 used a 5y panel).
  Next-PR decision (retire bare flag or split weights) waits on the
  Q3 2026-08-19 cohort acceptance check.
- `restatement_high_confidence` _(Phase 2.2, PR #165)_ — Joint
  occurrence of a 10-K/A or 10-Q/A amendment AND an 8-K Item 4.02
  (non-reliance) filing within 90 days. Hennes-Leone-Miller 2008
  *TAR* §4 "irregularity signature" — the co-occurrence isolates
  the fraud-class subset of restatements (PPV ~70% per HLM hand-
  classified cohort) from the broader error-class amendments.
  Schroeder 2024 SSRN §3.2 validates the 90-day co-occurrence window
  as the typical lag from Item 4.02 disclosure to amended-filing
  landing. Strict superset of `restatement_history` — both flags
  fire together; the manipulation-index weight is a **delta** (+3.0
  on top of the bare flag's 5.0) per PR #165 review fix. Threshold
  provenance: **LITERATURE-ANCHORED** (HLM 2008 irregularity
  signature; 90d window per Schroeder 2024 SSRN).
- `late_filing_notification` _(Phase 4.5d)_ — NT-10K or NT-10Q form
  filed (SEC Rule 12b-25 notice of inability to file on time) in
  the lookback window. Bartov & Konchitchki 2017 *Accounting
  Horizons* 31(4) "SEC Filings, Regulatory Deadlines, and Capital
  Market Consequences" documents a significantly negative 5-day
  stock price reaction (NT-10Q: −2.93%; NT-10K: −1.96%) that
  continues drifting downward in post-filing months; the penalty
  amplifies when the filer subsequently misses the grace-period
  extended deadline. The authors interpret the late filing as
  market-detected information about deeper operating problems.
  Weaker leading indicator than a realized 10-K/A amendment, but
  precedes the restatement filing itself (often by 6-18 months) so
  the annotate surfaces a near-term audit-risk signal before the
  bare `restatement_history` flag catches up. Threshold provenance:
  **GUT-FEEL** — no PPV figure replicated on the QuantRank universe;
  weight matches the `restatement_history` sibling on the "late
  filing is a weaker leading indicator of restatement filing"
  assumption pending Q3 2026-08-19 cohort confirmation. _(Citation
  corrected on 2026-05-26 from the prior hallucinated `Bartov-Lai-
  Yeung 2002 *JAR*` attribution per literature-searcher verification.)_
- `insider_sell_cluster` _(Phase 4.5e PR3, PR #222)_ — ≥ 3 distinct
  insiders selling ≥ $1M cohort-aggregate in opportunistic
  transactions (Form 4 transaction codes `{S, D}`) within a 30-day
  rolling window. Cohen-Malloy-Pomorski 2012 *JFE* 103(2) §III.A
  "Decoding Inside Information" partitions Form 4 transactions into
  opportunistic vs compensation-mechanical via the transaction-code
  taxonomy — codes `{A, M, F, G}` are vesting / option-exercise /
  gift transfers and carry no information signal; the opportunistic
  subset (`{S, D}`) drives the ~10% annualized abnormal-return
  spread CMP documents. Rule 10b5-1 pre-scheduled trades
  (Jagolinzer 2009 *MS* §3.2 expected 40-60% FP rate) are filtered
  via the document-level `<aff10b5One>` boolean and the footnote-
  text regex set added in PR #224. Current weight 5.0 — downgraded
  from RESERVED 10.0 per methodology-scientist Mode B 2026-05-23
  (Bushman-Smith 2003 *JAR* documents 30-50% post-SOX signal
  degradation on insider-sell anomalies; conservative weight
  pending Q3 cohort PPV acceptance). Threshold provenance:
  **LITERATURE-ANCHORED** on the transaction-code partition +
  distinct-insider count (CMP 2012 §III); **GUT-FEEL-acceptable**
  on the $1M cohort floor and 30-day window (compresses CMP's
  calendar-quarter into Jagolinzer 2009's high-information regime;
  no paper anchors an absolute dollar floor).
- `c_suite_unusual_sell` _(Phase 4.5e PR3, PR #222)_ — ≥ 2 distinct
  CEO / CFO / President insiders selling in the same 30-day window
  (narrow-regex match — deliberately excludes COO / CTO / CMO /
  CHRO which are operational rather than financial-information
  roles). Jeng-Metrick-Zeckhauser 2003 *JAR* 41(3) §V documents
  that top-officer sales carry materially stronger signal than
  broad-insider sales, driven by the asymmetric financial-
  information access; Jagolinzer 2009 §5.2 NEO subsample reports
  an 80% predictability drop when 10b5-1 scheduled trades are
  excluded vs the full population. Strict superset of
  `insider_sell_cluster` when the $1M cohort floor is also met →
  combined weight = 5.0 + 3.0 = 8.0 pts (≈ `REM_SUSPECT_WEIGHT`),
  with **delta-not-total semantics** mirroring PR #165's
  `RESTATEMENT_HIGH_CONFIDENCE_WEIGHT` (the +3.0 is the
  irregularity premium on top of the bare cluster signal, not a
  re-counted total). Threshold provenance: **LITERATURE-ANCHORED**
  on the role partition + distinct-officer count (JMZ 2003 §V;
  Jagolinzer 2009 §5.2); **GUT-FEEL-acceptable** on the 30-day
  window (inherits the `insider_sell_cluster` calibration).
- `share_count_extraction_missing` _(Issue #176)_ —
  `shares_outstanding is None AND revenue > 0 AND total_assets > 0`.
  Operational data-quality annotate (not a literature-anchored
  manipulation defense): surfaces tickers where the XBRL fact-name
  manifest in `compute.ingest.fundamentals._FUNDAMENTALS_REQUIRED_ATTRS`
  missed a share-class-scoped fact, cascading to null `market_cap` +
  null EPS + null P/E without otherwise breaking the snapshot. STZ
  2026-05-14 cron was the trigger case (Constellation Brands Class A /
  Class B). Annotate-only — kept distinct from the
  `data_quality_input_corruption` veto's existing
  `shares_outstanding=None` silence contract (issue #18 / test_D3) so
  legitimately uncomputable TBVPS still degrades to a null fair-price
  rather than a Top-5 ban. Promotion to veto deferred to the Q3
  2026-08-19 cohort audit after firing-rate confirmation.
- `extreme_estimate_majority` _(Issue #177 + Issue #587 RE-BASE-WITH-FLOOR)_
  — fires when a majority of applicable ensemble methods are extreme
  (Defense #4 5×/0.2× per-method outlier guard). Two firing branches:

  **Baseline (3-of-6 rule):** ≥ `config.EXTREME_MAJORITY_THRESHOLD = 3` of
  the 6 fair-price methods fired `extreme_*_estimate`. The ensemble's
  median is a 50% trimmed estimator over 6 samples and tolerates only
  ⌊5/2⌋ = 2 outliers before degrading (Huber 1981 *Robust Statistics*
  §1.4 breakdown-point); at 3+ outliers the median collapses toward the
  low-cluster (Damodaran 2019 *Investment Valuation* 3rd ed. Ch. 18 —
  discard methods whose inputs fall outside their domain of applicability).
  APP/DDOG/AXON/TSLA pattern from the 2026-05-14 cron: 4-5 methods
  extreme-low against the current price, ensemble median ~$36 vs
  current ~$482.

  **Low-applicability floor** _(Issue #587, 0.10.32-phase8pilot,
  methodology-scientist RE-BASE-WITH-FLOOR ratified)_: in the
  low-applicability regime (n_applicable ≤
  `config.EXTREME_MAJORITY_LOWAPP_MAX = 3`, the S&P 1500 small-cap tail),
  also fires when `n_extreme ≥ config.EXTREME_MAJORITY_LOWAPP_MIN = 2`
  AND n_extreme is a strict majority of applicable methods
  (`n_extreme > n_applicable − n_extreme`). This closes the false-negative
  dead-zone exposed by the S&P 1500 cutover: GFF (MoS −1143.9%) and SMTC
  (−938.7%) each had 2 of 3 applicable methods extreme — a breakdown
  event by applicable-based majority logic, but invisible to the 3-of-6
  baseline rule. The `n_extreme ≥ 2` floor kills the 1-of-2 false-positive
  (one extreme of two applicable is not an n=2-median breakdown event per
  Huber 1981 §1.4). The `n_applicable ≤ 3` ceiling confines the new
  behaviour to the low-applicability tail so S&P 500 tickers (5-6
  applicable) remain byte-identical. Provenance: GUT-FEEL with Huber 1981
  §1.4 breakdown-point rationale — low-applicability RECALIBRATION, not a
  new literature cutoff. Aligns the live annotate with the already-shipped
  `median_trimmed` shadow's applicable-based majority logic. Delta measured
  on cron 8c89a5af0: 56 → 72 fires, 16-ticker delta (GFF, SMTC, DD, NRG,
  LGIH, GEV, BILL, TTWO, HASI, HIMS, CRWD, MSGS, NABL, CHTR, COKE, EMBC).
  Veto promotion deferred to Q3 2026-08-19 cohort audit.

  `n_applicable` in the firing condition = total count of methods with
  `applicable=True` AND `value is not None` (includes outliers). This is
  the correct denominator for the breakdown-point arithmetic — the
  applicable-method count is the relevant sample size N for Huber §1.4,
  not the fixed 6-method total (which treats inapplicable methods as
  contributing to robustness when they cannot).

  Annotate-only per Rule 16; the actual median-exclusion logic +
  `fair_price.methods_excluded_from_median` field land in a follow-up PR
  after ≥ 1 cron's firing-rate observation. The 5×/0.2× per-method bands
  themselves are GUT-FEEL only — a separate recalibration PR is queued
  for the Q3 2026-08-19 quarterly cohort audit.
- `multi_class_aggregate_shares_suspected` _(Issue #261 PR-A, PR #264)_
  — fires when two or more S&P 500 tickers share the same CIK AND each
  ticker's `market_cap > 10%` of universe-median
  (`config.MARKET_CAP_FLOOR_RATIO = 0.10`). Catches the SEC `companyfacts`
  aggregate-shares overcount pattern where multi-class issuers (GOOG / GOOGL
  / NWS / NWSA / FOX / FOXA) get the same per-class share count returned
  via the aggregate XBRL endpoint, inflating `market_cap` by 2-4×. Expected
  steady-state firing ≈ 6 tickers (Alphabet + News Corp + Fox pairs). Pure
  data-quality detector — no academic prior; identity-equation check per
  Damodaran 2019 *Investment Valuation* 3rd ed. Ch. 16 (per-class market
  cap = per-class shares × per-class price). PR #269 (Issue #261 PR-B)
  ships the structural per-class XBRL extraction fix for GOOG/GOOGL via
  `MULTI_CLASS_OVERCOUNT_ALLOWLIST` keyed to the filer-specific class-member
  dimension; the annotate continues to fire as the safety net for any
  multi-class filer NOT yet on the allowlist.
- `valuation_output_anomalous` _(Issue #262 PR #265, renamed from
  Site-2 emission of `data_quality_input_corruption`; Issue #289 PR
  retired the Site-2 trigger 2026-05-28)_ — historically emitted when
  ANY of the 6 fair-price ensemble methods produced an output >
  $10K/share. Issue #289 methodology-scientist Mode B verdict (Penman
  2013 §7.4 + Damodaran 2019 Ch. 18 + Huber 1981 §1.4) confirmed the
  Site-2 path was structurally redundant with Defense #4
  (`extreme_*_estimate` per-method outlier guard) + Issue #177
  `extreme_estimate_majority` (Huber breakdown-point); empirical PPV
  on the 2026-05-28 cron #69 was 0/1 = 0% (NVR false positive).
  Site-2 trigger DELETED; the annotate continues to emit via
  writer-parity from `compute/main.py` when the Site-1
  `data_quality_input_corruption` veto fires (MTB / CPT / MRNA /
  HBAN cohort per PR #265 — preserves the UI explanation chip in
  `FairPriceCard.tsx`). Pure data-quality detector — no academic prior.
  Site-1's three patterns (TBVPS > $10K / TTM revenue < $50M /
  |NI| > |revenue|) catch the upstream units-bug class at the source
  per Penman 2013 §7.4 defend-at-source principle.

### Annotate-vs-veto philosophy

| Question | Answer |
|---|---|
| Does a flag change the composite score? | **Never.** Rule 16. |
| Does a flag affect rank order? | **Never.** |
| Does a flag suppress the entered-top-5 badge? | Vetoes only. Annotate-only flags are visible but have no behavioral effect. |
| Does a flag null fair-price methods? | Numerical guards do (per-method or all-6). Annotate-only flags don't. |
| Can the user override flags? | Not in v1.0. Phase 4+ may add a "show flagged stocks" toggle. |

## Tier-2 events _(Phase 3d)_

Tier-2 events extend the defense layer with regulatory-disclosure
pattern matching. Two SEC EDGAR data sources, three defenses:

| Source | Defense | Mode | Lookback |
|---|---|---|---|
| 10-K MD&A text | `going_concern_disclosure` | Annotate-only | 400 days (covers 1y filing cadence + buffer) |
| 8-K Item 4.02 | `non_reliance_filing` | **Hard veto** (joins altman / sloan / NSI) | 365 days (Schroeder 2024 SSRN cohort window) |
| 8-K Item 4.01 | `auditor_change` | Annotate-only | 730 days (Reg S-K Item 304 horizon) |

**Cache strategy**: 90-day TTL for 10-K text (annual filing cadence —
an 89-day stale cache hit returns the same filing we'd fetch fresh);
7-day TTL for 8-K filings (recent events refresh weekly, sticky once
filed). Both caches gitignored under `compute/cache/edgar_8k/` and
`compute/cache/edgar_10k_text/`.

**Failure semantics**: any individual fetch failure (rate-limit,
network error, ticker-not-found, missing `EDGAR_USER_AGENT`) returns
`False`/`None`. The orchestrator never raises — one bad ticker
cannot crash the run. Population-level success surfaces in
`Metadata.tier2_coverage_pct` (percentage of universe where **both**
the 10-K and 8-K fetch returned data).

**Implementation modules**:

- `compute/scoring/going_concern.py` — Defense #8. Pre-compiled
  per-phrase regex with `\b` word-boundary anchoring and
  `[\s\-]+` whitespace/hyphen flex. 14 curated phrases.
- `compute/scoring/eight_k_events.py` — Defenses #9 + #10.
  `ItemFlag` frozen dataclass + `check_non_reliance` /
  `check_auditor_change` consumers. Cache layer inlined; one
  fetch (730-day lookback) serves both checks.
- `compute/scoring/tier2.py` — Orchestrator. `Tier2Result` frozen
  dataclass + `fetch_tier2_for_ticker` (parallel-safe, never
  raises) + `tier2_events_dict` (display-payload builder) +
  `coverage_pct` (population-level metric).
- `compute/ingest/filing_text.py` — 10-K text fetch + 90-day cache.
  Atomic write via tmp + os.replace; sanitized ticker filename
  (path-traversal-safe).

**Why annotate-vs-veto split**: Item 4.02 (non-reliance on previously
issued statements) is a high-precision restatement signal —
Schroeder 2024 SSRN finds ~50% of 4.02 filings precede formal
restatement within 12 months. Worth a hard veto. Item 4.01 (auditor
change), by contrast, fires for benign reasons too — auditor
rotation, audit-firm restructuring, post-merger consolidations —
so the FP rate is too high to suppress entered-top-5. The same
Reg S-K Item 304 disclosure mandate applies to both dismissal and
resignation, so we can't filter on cause without parsing prose;
annotate-only is the conservative choice.

## Sanity tests _(Phase 3c)_

`metadata.mos_trailing_ic_smoke` is a **same-day** Spearman rank
correlation between `margin_of_safety_pct` and trailing 1-year return,
computed across the cross-section. **It is not a backtest.** We are not
claiming the ensemble predicts future returns — we are checking that
today's MoS has *some* relationship to recent return drift, as a
sanity smoke against the ensemble producing pure noise.

We chose Spearman over Pearson because:

- 143 of 502 stocks have `mos_pct` outside `[−99%, +500%]` (Step 7
  verification, 2026-05-09); a few extremes would dominate Pearson.
- 12-month equity returns are similarly heavy-tailed (NVDA / TSLA / PLTR
  spikes vs. mean reversion).
- Spearman is rank-based and robust to monotonic transforms.

The function returns `None` (not a misleading number) when fewer than
30 valid pairs are available, when all `mos_pct` values are identical,
or when all returns are identical. Stocks with the
`data_quality_input_corruption` warning are explicitly skipped (their
`mos_pct` is null anyway, but the explicit skip prevents future
regressions).

A non-trivial correlation (positive **or** negative) is informative.
Near-zero says "the field is essentially uncorrelated with recent
return drift" — also informative, but a hint that the ensemble might
need re-tuning. **Real predictive validation is Phase 4+** (PBO,
deflated Sharpe, walk-forward IC).

## The full formula reference

See [`./stock_ranking_knowledge.md`](./stock_ranking_knowledge.md) for the
complete ~1600-line reference covering every formula, normalization rule, and
data source. That file is the authoritative source — never reinvent formulas.

## Known limitations

Honest accounting of what QuantRank's analytical layer does and does not
guarantee. Read this before treating any score as an absolute claim about
a stock's quality.

### Survivorship bias (universe construction)

The universe is the **current** S&P 500 constituents list, scraped from
Wikipedia (`compute/ingest/universe.py`). It is **not point-in-time** —
companies delisted from the index in the past 5 years (~10-15 per year
per S&P annual turnover) are not in the dataset.

Consequence: every cross-sectional statistic — pillar percentile ranks,
sector medians, the "loss_chance_pct" estimate — is computed against a
universe that **survived to today**. Baseline distributions are
inflated upward relative to a true point-in-time universe. A backtest
on this data would be optimistically biased.

For point-in-time historical membership we would need CRSP / SHARADAR
(paid data); current scope keeps the static-site model free.

### Score semantics (cross-sectional normalization)

Pillar scores (Quality, Value, etc., 0–100) are **percentile ranks
within the current universe**, not absolute quality measures. "Quality
92" means "top 8% quality among current S&P 500 sector peers", not
"high-quality company in an absolute sense". The same company could
score differently if the universe changes (e.g., index reconstitution,
delisting renormalizes remaining peers).

The composite_score (0–100) is similarly a rank-based blend; it is a
**ranking signal**, not an absolute value claim.

### Pillar correlation (no orthogonalization)

The 8-pillar blend assumes pillars carry independent signal, but at
least one pair is correlated by construction:

- **Quality** (ROE, ROIC, Gross Profitability, Piotroski) and
  **Profitability** (ROA, Gross Margin, Net Margin, Asset Turnover)
  both measure return-on-something. A high-ROE firm scores high on
  both — effective double-counting of the same underlying signal.

The current pipeline does **not** apply orthogonalization or
correlation correction (`compute/scoring/normalize.py` averages
metrics within each pillar; the composite averages pillars). Effective
weight on ROE-like signals in the current 8-pillar configuration
(after sentiment + ml redistribute pro-rata) is ~33%, higher than the
nominal Quality+Profitability sum of 27%.

Phase 4i (JKP integration) plans "13 quasi-orthogonal theme clusters"
to address this; not yet shipped.

### `extreme_*_estimate` flags are method-applicability signals

The 6-method fair-price ensemble (`compute/valuation/ensemble.py`)
emits `extreme_dcf_estimate`, `extreme_rim_estimate`,
`extreme_multiples_<method>_estimate` etc. when a method produces a
value > 5× or < 0.2× current price. These fire on 10–15% of the
universe per the 2026-05-20 quarterly audit (issue #130).

**These flags indicate "the method doesn't apply to this stock"**,
not "this stock is suspect":
- `extreme_dcf_estimate` → DCF fails for negative-FCF firms (tech,
  biotech, REITs)
- `extreme_rim_estimate` → RIM fails for negative-book-value firms
  (buyback-heavy mature firms)
- `extreme_multiples_pb_estimate` → P/B fails for asset-light tech

The current pipeline aggregates these flags into `manipulation_index`
(`compute/scoring/loss_chance.py:74-75`, weight 1.0 each, cap 5.0)
which then deducts up to 10 composite points via
`composite_score_adjusted`. This conflates method-applicability with
manipulation risk; Phase 2 of the foundation reconciliation roadmap
(issue #150) splits these surfaces.

### Pillar weight rationale (empirical, not academic-derived)

The pillar weights (`compute/scoring/composite.py:17-28`):
quality 0.22, value 0.18, growth 0.10, momentum 0.10, health 0.08,
profitability 0.05, technical 0.04, risk 0.03 — are **empirically
chosen**, not directly traceable to academic literature. The
relative ordering follows multi-factor academic precedent (quality +
value dominate, momentum + risk are smaller contributors), but the
specific values are project-team judgment, not e.g. Fama-French
factor weights.

The sum-to-1.0 invariant lock (`composite.py:43-45`) prevents
accidental drift; the choice of specific values remains a design
decision pending Phase 5 ML meta-learner work that could re-calibrate
empirically from out-of-sample performance.

### Top-decile vetoes are mathematical certainties

Two active vetoes — `sloan_accruals_top_decile` and
`net_issuance_top_decile` — fire on the top 10% of the universe **by
construction** (decile cutoff is relative, not academic threshold).
This means ~10% of the universe is always Top-5-suppressed regardless
of whether the firm is a genuine manipulation candidate.

Phase 3 of the foundation reconciliation roadmap (issue #150)
proposes converting these to joint gates ("top-decile AND
(Beneish-high OR Dechow-high OR restatement_history)") to reduce
false-positive suppression.

### Known calibration drift

Quarterly cohort audit (issue #130, last refresh 2026-05-21 from
2026-05-20 production cron):

- `value_trap_risk` — **TWO-FACTOR LSV gate live since #586 PR-2
  (`0.10.34-phase8pilot`)**. The legacy single-leg gate (RIM skip on
  `avg_3y_roe ≤ Ke` alone, Penman 2013) over-fired at **35.06% → 36.4%**
  on the S&P 1500 — a data-scientist probe (#586) showed the over-fire
  was dominated by loss-making IT/HC growth names (ROE structurally
  negative, the opposite of an LSV cheap-and-deteriorating trap). The
  ratified amendment adds the **LSV 1994 "cheap" leg**: the warning now
  fires iff `ROE ≤ Ke` (Penman quality screen, the RIM method-skip is
  UNCHANGED) **AND** trailing P/E (`eps_ttm > 0`) is below the sector-peer
  median P/E; loss-making / undefined-P/E firms are **EXEMPT**. First
  sp1500 cron (shadow-confirmed in PR-1 #588, flipped live in PR-2):
  **10.3%** (155/1504), squarely in the reconciled **5-12% LSV-1994
  band** (the prior "15-25%" figure was the single-leg tolerance and is
  superseded). **Asness-Frazzini 2013** ("The Devil in HML's Details")
  was confirmed (literature-searcher) to carry **no value-trap content**
  and is dropped from the anchor list. φ(`value_trap_risk` ×
  `goodwill_heavy`) = 0.059 → the multiple leg adds orthogonal
  information, not goodwill redundancy (Q3 2026-08-19 audit re-confirms).
- `going_concern_disclosure` **1.0%** fire rate on 2026-05-20 cron
  (within Mayew 2015 expected 1-3% band, down from 10.8% pre-Phase-4h).
  Mechanism not yet code-confirmed — issue #16 negation-lookbehind may
  have been side-effect-fixed by the Tier-2 8-K scan integration.
  Verify root cause + decide whether to close issue #16 at Q3 audit.
- `loss_avoidance_pattern` **0% fire rate even after Phase 2.4 10×
  threshold rescale** (PR #163, 2026-05-20). Thresholds bumped
  `$5M / $0.05` → `$50M / $0.50` to match S&P 500 scale, but production
  still emits 0 firings — S&P 500 firms with NI ≤ $50M for 3+
  consecutive years remain structurally rare. Phase 4b (2026-05-21)
  closed the size-invariance follow-up by shipping the sibling
  annotate `loss_avoidance_pattern_size_invariant` — fires when
  `NI / TotalAssets ∈ [0, 0.005]` for 3+ consecutive years,
  Roychowdhury 2006 *JAE* §5.2 suspect-firm definition (reaffirmed
  by Donelson-McInnis-Mergenthaler 2013 *TAR*). Roychowdhury cohort
  single-year suspect rate ~8-12%; with the 3-year persistence
  filter the S&P 500 expected firing rate is ~1.5-4% (~8-20 tickers,
  materially > 0/502 the absolute-$ flag fires on). Both flags ship
  side-by-side annotate-only — composite rank unaffected — pending
  the Q3 2026-08-19 quarterly-audit decision (retire one, keep both,
  or split weights vs `rem_suspect` which shares the Roychowdhury
  paper anchor but fires on abnormal CFO/Production/DiscExp WITHIN
  the suspect cohort rather than cohort membership for 3+ years).
- `restatement_history` **11.75% → 11.8%** fire rate (immaterial-
  amendment noise). Phase 2.2 ships the `restatement_high_confidence`
  irregularity signature (10-K/A + 8-K Item 4.02 co-occurrence within
  90 days, PR #165) as a higher-PPV complement. Bare `restatement_history`
  retained at weight 5; combined weight 8 when high_confidence fires
  (Hennes-Leone-Miller 2008 *TAR* irregularity PPV ~70% vs bare ~30%).
  Decision on whether to retire bare flag deferred to ≥ 1 production
  cron of cohort acceptance data.

These are tracked under issue #150 Phase 2.

## Realistic expectations

Per Section 28 of the knowledge doc: net-of-cost top-decile alpha of **2–4%
realistic**, with mean information coefficient around 0.02–0.05. Anything
claiming much more is almost certainly overfit. We validate via PBO
(probability of backtest overfitting) and deflated Sharpe ratio (Phase 4+).

**Defense system honest limits** (per `RESEARCH_FINDINGS.md` §"Honest Limitations"):
- Beneish M-Score: ~30% false-positive rate in broad market, ~25-40% false-negative
- McLean-Pontiff anomaly decay: 26% out-of-sample + 32% post-publication = 58% cumulative
- Madoff-style total fabrication is undetectable by any quantitative system
- Marginal AAER capture < 5% beyond 4 fraud signals — defense set freezes at v1.0;
  rotate (don't stack) post-v2.0

**Anchor: `mclean_pontiff_decay`** — McLean, R.D. and Pontiff, J. (2016). "Does Academic
Research Destroy Stock Return Predictability?" *Journal of Finance* 71(1), 5-32.
97 published anomalies: alpha decays 26% out-of-sample + an additional 32% post-publication
(58% cumulative). Governs the IC-decay monitor (`compute/validation/ic_decay.py`) and the
Proposal F IC half-life fitting (`Metadata.pillar_ic_half_life_months`). Also the comparison
anchor for the Di Mascio (2022) power-law model selected in Proposal F: Di Mascio, A. (2022).
"The Decay of Factor Alpha." SSRN Working Paper 4023689 §4 — power-law fits explain alpha decay
slightly better than exponential (median adj-R² 0.48 vs 0.43 across 80 factors). Promoted from
inline §"Realistic expectations" prose to this canonical anchor 2026-06-24 (Proposal F).

---

**Reminder**: this is a research / educational tool. Not investment advice. See
the disclaimer in the [README](../README.md).
