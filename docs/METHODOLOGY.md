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
- **10 active defenses** — 4 vetoes + 5 numerical guards + 7 annotate-only
  flags. Annotate-and-veto-Top-N philosophy: defenses **never modify the
  composite**, only suppress the entered-top-5 badge or null specific
  fair-price methods. _(Phase 3b/3c/3d)_
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

- **Median** = median of every applicable method's value. Robust by
  construction — a single absurd estimate doesn't drag the headline.
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

### Active vetoes (4) — suppress the entered-top-5 badge

| Veto | Rule | Source |
|---|---|---|
| `altman_distress` | Z″ < 1.10 | Altman 1968, Hotchkiss 2003 update for non-manufacturers |
| `sloan_accruals_top_decile` | Within-sector top decile of accruals/assets | Sloan 1996 |
| `net_issuance_top_decile` | Within-sector top decile of NSI over 365 days | Pontiff-Woodgate 2008 |
| `non_reliance_filing` | 8-K Item 4.02 within trailing 365 days | Schroeder 2024 SSRN |

### Numerical guards (5) — null specific fair-price methods + emit a warning

| Guard | Rule | Source |
|---|---|---|
| Stale filing | `latest_filed_date` > 120 days → soft annotate; > 180 days → null all 6 methods | Practitioner default |
| Outlier 5× / 0.2× | Method value outside `[0.2×, 5×]` of current price → exclude from MAX, keep in MEDIAN | Internal — see "Aggregation" |
| Terminal-g cap | DCF terminal growth ≤ `min(0.03, WACC − 100 bp)` | Damodaran 2012 |
| Sector exclusions | EV/EBITDA skipped for Financials; DCF skipped for Financials + Utilities; Quality pillar metrics gated by sector (`magic_formula`, `ebit_based_roic`, `gross_profitability`, `asset_turnover` per Greenblatt 2005) | Greenblatt; sector-method spec |
| Data-quality $10K ceiling | If any method computes > $10,000/share → null all 6 + emit `data_quality_input_corruption`. Catches upstream ingestion bugs (e.g., `shares_outstanding` in wrong units) before user-visible nonsense. | Internal — Step 7.5 (post-spot-check) |

### Annotate-only flags (7) — surfaced in `valuation_warnings` or `tier2_events`, no behavioral effect

- `goodwill_heavy` — TBVPS / BVPS_reported < 0.5 (cautions that
  reported book is misleading)
- `value_trap_risk` — RIM was skipped because ROE < cost of equity
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

Phase 3e adds `beneish_high` and `dechow_f_high`.

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

---

**Reminder**: this is a research / educational tool. Not investment advice. See
the disclaimer in the [README](../README.md).
