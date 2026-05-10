# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | ✅ DONE — 2026-05-07 |
| 1 | Universe + prices ingestion | ✅ DONE — 2026-05-08 |
| 2 | Fundamentals via SEC EDGAR | ✅ DONE — 2026-05-08 |
| 3 | Classical features + composite + **defenses** → **v1.0** | 🟡 in progress (3a/3b/3c done; 3d/3e remain) |
| 4 | Factor consolidation (OSAP + JKP + Qlib + IPCA) → **v1.1** | ⚪ not started |
| 5 | ML meta-learner (Triple-Barrier + Meta-Labeling + Conformal) + SHAP | ⚪ not started |
| 6 | Sentiment v2 (FinBERT + Whisper + 8-K Lazy Prices) | ⚪ not started |
| 7 | Regime + portfolio (Student-t HMM + NCO + TDA) → **v1.5** | ⚪ not started |
| 8 | Universe expansion (S&P 1500) | ⚪ not started |

**Current focus**: Phase 3 PR 3d (charts + Tier-2 defenses) — PR 3c merged.

**Phase 3 sub-PR plan** (5 sub-PRs, defense-augmented 2026-05-09 per
[`docs/RESEARCH_FINDINGS.md`](docs/RESEARCH_FINDINGS.md) §"Defense Playbook"):
- ✅ **3a — Pillar feature modules** — DONE 2026-05-08. Foundation only —
  7 feature modules, 30+ metrics, 50+ tests. No production output changes.
- ✅ **3b — Composite + risk overlay** — DONE 2026-05-08. 4 new scoring
  modules (normalize, pillars, composite, risk_overlay), 33 new tests,
  schema bump to `0.4.0-phase3b`. First 8-pillar production Top-5; 80%
  rotation from the prior momentum-only baseline (4 of 5 entrants new).
  Risk overlay is **annotate-only** — flagged stocks keep their composite
  rank, the flag only suppresses the `entered_top5` badge. Sector-bucket
  bias hypothesis disproved (Real Estate sector mean 49.33 — near bottom).
  Sloan over-firing on growers + financials filed as
  [issue #7](https://github.com/dackclup/quantrank/issues/7) for Phase 4.
  Active vetoes: 2 (`altman_distress`, `sloan_accruals_top_decile`).
- ✅ **3c — Fair price ensemble + price history + Tier-1 defenses** —
  DONE 2026-05-09. Schema bump to `0.5.0-phase3c`. Tag
  **v0.5.0-phase3c** (post-merge). ~12 commits, 7 sub-modules,
  292 new tests, 2 production verifications (workflow runs #9 + #10).
  - Fair price: 6 methods — Graham (TBVPS + 3y EPS), P/E / P/B /
    EV-EBITDA multiples (4-tier peer walk with 5/95 winsorization),
    RIM (Penman 2013), DCF (2-stage, terminal-g cap) → median + max
  - Price history: per-stock `stocks/history/{TICKER}.json` (252
    rows, OHLCV column-major, lazy-loaded by detail page chart)
  - **7 research-validated defenses** delivered (1 more than the
    original 6 — Defense #7 added mid-PR after the Step 7 production
    spot-check surfaced ~11 tickers with corrupted shares_outstanding):
    1. Net Stock Issuance veto (Pontiff-Woodgate 2008 *JF*) — 3rd veto
    2. Tangible BVPS = equity − goodwill − intangibles (full netting)
    3. Stale filing: 120d soft flag + 180d hard veto
    4. Multi-method outlier guard at 5× / 0.2× current price
       (excludes from MAX, kept in MEDIAN)
    5. Terminal g ≤ WACC − 100bp constraint in DCF
    6. Sector exclusions → Quality pillar metrics + EV/EBITDA
       fair-price method (Financials/Utilities/Real Estate per metric)
    7. **Data-quality sanity ceiling — $10K/share** (Step 7.5 added):
       any method computing > $10K nulls all 6 methods + emits a
       single `data_quality_input_corruption` warning. Catches
       ingestion bugs at the ensemble layer before user-visible
       nonsense like BKR fair_price = $105M reaches the UI.
  - New schema fields: `StockSummary.{fair_price, max_fair_price,
    margin_of_safety_pct, valuation_warnings}`; `StockDetail.{fair_price,
    valuation_warnings, has_history, tangible_book_value}`;
    `RawMetrics.goodwill`; `Metadata.mos_trailing_ic_smoke`.
  - **Schema-snapshot guard** added (Step 9): CI fails on
    Pydantic ↔ TypeScript drift via `frontend/lib/schema-snapshot.json`.
  - Frontend (Step 10): Fair-price + MoS columns in the rankings
    table, lazy-loaded 1y price chart on detail pages, FairPriceCard
    with per-method breakdown + warning chips, MoS clamping per
    Issue 3 acceptance criteria.

  **Production verification (commit `6bca592`, run #10):**
  - Universe: 502 S&P 500 stocks, schema `0.5.0-phase3c`
  - Coverage: 487 / 502 (97.0%) non-null fair_price (target ≥ 80%)
  - Top-5 composition unchanged from PR-3b baseline {SNDK, EOG, CF,
    BKR, HST} — PR 3c is semantically additive.
  - F1 anomalies (`fair_price > 10× current`): 9 → 1 (only TSN
    below the $10K ceiling, handled by Defense #4 outlier guard).
  - Sanity guard fired for 8 tickers (BKR, SPG, AMCR, CHTR, ERIE,
    PSKY, RTX, VTRS). Risk-flag totals (54 / 50 / 37) identical
    to PR-3b (no scoring regression). NVDA + AAPL byte-identical
    fair-price spot-checks vs Step 7.
  - Reason taxonomy: 21 stable identifiers (was 17 pre-3c).
  - 3 follow-up issue drafts staged at `/tmp/issue_drafts/` —
    file via `gh issue create` after PR 3c merges.
- ⚪ **3d — Charts + Tier-2 defenses** — Stock detail Pillar Radar +
  Fair Price Bar + Price History charts; About page; risk_flags +
  valuation_warnings UI badges. ~520 LOC, 1.5-2 days. Plus:
  - Going-concern phrase scan in 10-K Item 7
    (Loughran-McDonald academic dictionary)
  - 8-K Item 4.02 hard veto (12-month window) — restatement signal
  - 8-K Item 4.01 auditor change soft flag
- ⚪ **3e — Tier-3 defenses + README polish + tag v1.0** — ~370 LOC, 1 day.
  - Beneish M-Score full 8-ratio (annotate-only, sector-relative)
  - Dechow F-Score (parallel signal to Beneish, annotate-only)
  - **Honest Limitations section** in README (frauds we cannot catch,
    realistic FP/FN rates, decay reality, free-data fragility)
  - README architecture diagram + methodology link
  - Tag **v1.0** push

**v1.0 ETA**: ~2-3 days from 2026-05-09 — PR 3c shipped, only PR 3d
(~520 LOC, 1.5-2 days) and PR 3e (~370 LOC, 1 day) remain.

**Defense scorecard — current vs v1.0 target**:

| Layer | Now (post-3c) | At v1.0 (post-3e) |
|---|---|---|
| Vetoes | 3 (Altman Z″, Sloan accruals, NSI) | 3 (unchanged) + 1 hard event veto (8-K 4.02) |
| Numerical guards | 5 (stale_filing, outlier_5×, terminal_g, sector_exclusion, **data_quality_input_corruption**) | 5 (unchanged) |
| Annotate-only flags | 5+ (goodwill_heavy, value_trap_risk, extreme_<method>_estimate, stale_filing_soft, data_quality_input_corruption surface) | 8+ (adds going_concern, auditor_change, beneish_high, dechow_f_high) |

(Defense #7 — `data_quality_input_corruption` — was added mid-PR-3c at
Step 7.5 after the production spot-check on commit `c13e4f7` surfaced
the upstream `shares_outstanding` ingestion bug; not in the original
6-defense plan.)

**Next deliverable**: PR 3d charts + Tier-2 event defenses (going-concern
phrase scan, 8-K Item 4.02 hard veto, 8-K Item 4.01 auditor-change soft
flag). Tag **v1.0** at the end of PR 3e with all defenses live and
Honest Limitations documented.

## Phase 3c verified production stats — 2026-05-09

- Universe size: **502 stocks** (S&P 500)
- Schema: `0.5.0-phase3c`
- Compute time: **27m 10s** (workflow run #10, commit `6bca592`)
- Fair-price coverage: **487 / 502 (97.0%)**
- Tests: **118 → 409** (+291 in PR 3c)
- Reason taxonomy: 21 stable identifiers
- 3 follow-up issue drafts staged at `/tmp/issue_drafts/`

## Phase 3c acceptance checklist — ✅ all met (2026-05-09)

- [x] Fair-price ensemble: 6 methods, median + max + low + high + mos_pct
- [x] Multi-tier peer median (sub_industry → industry → sector → broad)
- [x] Tangible BVPS (full goodwill + intangibles netting)
- [x] 7 defenses active: NSI, Tangible BVPS, stale-filing, outlier-5×,
      terminal-g cap, sector exclusions, data-quality $10K ceiling
- [x] Per-stock 1y price-history JSON (252 rows OHLCV column-major)
- [x] Annotate-only philosophy (Rule 16) — composite untouched in PR 3c
- [x] Schema-snapshot CI guard prevents Python ↔ TS drift
- [x] mos_trailing_ic_smoke sanity check (NOT a backtest)
- [x] Frontend rendering: rankings table fair_price + MoS, detail-page
      chart + FairPriceCard, MoS clamping per Issue 3
- [x] 2 production verification rounds (workflow runs #9 + #10)
- [x] Top-5 composition unchanged from PR-3b baseline (semantically
      additive confirmed)

## Roadmap — Option B (research-backed) — adopted 2026-05-08

Post-v1.0 phases now incorporate published quant-finance research. Detailed
references and library pinnings live in
[`docs/RESEARCH_FINDINGS.md`](docs/RESEARCH_FINDINGS.md); per-phase task
breakdowns in [`WORKFLOW.md`](WORKFLOW.md) under "Research-Backed Additions".

| # | Phase | Headline upgrade |
|---|---|---|
| 4 | Factor consolidation → **v1.1** | Replicate OSAP / JKP / Qlib Alpha158 factor zoo; reduce to a parsimonious latent set via IPCA (Kelly-Pruitt-Su 2019). |
| 5 | ML meta-learner | LightGBM ranker + López de Prado's **Triple-Barrier** labeling and **Meta-Labeling**; **Conformal prediction** for calibrated 80% prediction intervals. |
| 6 | Sentiment v2 | FinBERT news (Phase 4 baseline); add **Whisper** transcription of earnings calls + **8-K "Lazy Prices"** factor (Cohen-Malloy-Nguyen 2020). |
| 7 | Regime + portfolio → **v1.5** | **Student-t HMM** for heavy-tailed regime states; **NCO** (López de Prado) for hierarchical risk parity sizing; optional **TDA** (persistence diagrams) regime tagging. |
| 8 | Universe expansion | S&P 1500 (mid + small cap). |

**Fallback — Option A** (original `WORKFLOW.md` Phase 4-7 baseline): if any
research-backed addition hits a blocker (library unmaintained, data licence
restriction, free-tier compute insufficient, golden-value validation fails),
revert that phase to its Option-A scope. Triggers and decision points are
listed in `WORKFLOW.md` "Research-Backed Additions → Fallback rules".

**Honest performance ceiling** (from `docs/RESEARCH_FINDINGS.md`):
~3-7% **net** annualized alpha vs SPY is a *research-suggested upper bound*
for this combination of techniques on free-tier data. McLean-Pontiff (2016)
shows ~58% post-publication anomaly decay; Hou-Xue-Zhang (2020) shows ~65%
of the factor zoo fails replication. Real-world result for QuantRank will
likely land 2-4% net alpha after costs — same realistic envelope already
documented in `stock_ranking_knowledge.md` §28.

**Phase 3 composite weights (10 pillars, sum = 1.00)**:

| Pillar | Weight | Status |
|---|---|---|
| quality | 0.22 | active |
| value | 0.18 | active |
| growth | 0.10 | active |
| momentum | 0.10 | active |
| health | 0.08 | active |
| profitability | 0.05 | active (NEW key) |
| technical | 0.04 | active (NEW key) |
| risk | 0.03 | active |
| sentiment | 0.10 | placeholder, redistributed in Phase 4 |
| ml | 0.10 | placeholder, redistributed in Phase 5 |

For Phase 3, sentiment + ml stay null; their 0.20 weight is redistributed
pro-rata across the active pillars (effective weights divided by 0.80).

**Live URL**: https://quantrank.vercel.app
**Verified production (Phase 2, 2026-05-08)**: https://quantrank.vercel.app
— 501 S&P 500 stocks ranked, schema `0.3.0-phase2`, real SEC EDGAR
fundamentals on every detail page.

## Phase 2 verified production stats
- Universe size: **501 stocks** (502 minus FI — see limitations below)
- Schema: `0.3.0-phase2`
- Compute time: **22m 1s** (well under 60 min cold target)
- Fundamentals coverage: **99.8%** (501 / 502)
- First production data live at https://quantrank.vercel.app/

## Phase 2 acceptance checklist — ✅ all met (2026-05-08)

- [x] All ~502 tickers have fundamental data attempts (≥80% with revenue + net_income) — 99.8% coverage
- [x] `filed_date` populated for every fundamental row in cache parquet
- [x] Golden-value `@network` tests pass for AAPL/MSFT/GOOGL/JPM/XOM
- [x] Stock detail pages render at `/stock/AAPL`, `/stock/MSFT`, etc.
- [x] `FISV` → `FI` normalization working (verified: `/stock/FISV/` → 404)
- [x] Cross-sectional null rate <5% on revenue, net_income, total_assets
- [x] Compute time <30 min cache hit / <60 min cold (22m 1s actual cold)
- [x] Schema bumped to `0.3.0-phase2` in metadata.json
- [x] CI green on the Phase 2 PR before merge

## Phase 2 known limitations
- **FI (Fiserv) excluded from rankings** due to insufficient yfinance price
  history (renamed from FISV in 2024 → only ~18 months of bars under the new
  ticker, and `momentum_12_1` needs ≥12 months). The override logic correctly
  drops FISV; FI just can't be scored yet. Will resolve naturally as data
  accumulates, or a hybrid FISV→FI history splice can be added in Phase 3+.
- **Other tickers with corporate actions in the last 12 months may hit the
  same issue.** Consider adding an orchestrator log line in Phase 3:
  `"X tickers excluded due to insufficient history: %s"` for visibility in
  GitHub Actions logs.

## Resolved housekeeping
- ✅ `EDGAR_USER_AGENT` secret added to GitHub Actions secrets (Phase 2 setup)
- ✅ `FISV` → `FI` ticker rename — fixed in Phase 2 PR #4 (`TICKER_OVERRIDES`
  in `compute/ingest/universe.py`)

## Phase 1 acceptance checklist — ✅ all met (2026-05-08)

- [x] `compute-rankings.yml` runs in <15 min on first try (verified: 2m 56s)
- [x] `frontend/public/data/rankings.json` exists with ~500 stocks ranked by momentum (502 stocks)
- [x] `metadata.json` reflects accurate timestamp + schema `0.2.0-phase1`
- [x] Vercel URL shows working table after auto-redeploy (verified live at quantrank.vercel.app)
- [x] Mobile view of ranking table is readable (cards layout, search/filter/sort/pagination working)
- [x] CI green on this PR before merge (CI #6, #7 green)

## Phase 0 acceptance checklist — ✅ all met (2026-05-07)

- [x] Public GitHub repo exists
- [x] Directory tree per `SKILL.md` "Mandatory Repository Structure"
- [x] `ci.yml` green on first push (PR #1, squash merged to main)
- [x] `compute-rankings.yml` succeeds when manually dispatched (run #2, 23s)
- [x] Vercel project connected, production deploy live at https://quantrank.vercel.app
- [x] `frontend/public/data/metadata.json` placeholder visible at the site URL
- [x] `PHASE_STATUS.md` committed
- [x] `README.md` has disclaimer + architecture diagram + methodology link

> Update this file at the end of every phase. The next phase's prompt to
> Claude Code starts with: _"Read PHASE_STATUS.md. We're in Phase X."_
