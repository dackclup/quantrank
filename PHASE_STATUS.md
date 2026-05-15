# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | ✅ DONE — 2026-05-07 |
| 1 | Universe + prices ingestion | ✅ DONE — 2026-05-08 |
| 2 | Fundamentals via SEC EDGAR | ✅ DONE — 2026-05-08 |
| 3 | Classical features + composite + **defenses** → **v1.0** | ✅ **DONE — 2026-05-14** (v1.0.0 tagged + GitHub release) |
| 4 | Factor consolidation (OSAP + JKP + Qlib + IPCA) → **v1.1** | 🟡 IN PROGRESS — 4a-4f + 4c.1/4c.2/4c.3 merged (2026-05-14 → 2026-05-15); 4g 8-K Tier-2 re-enable next |
| 5 | ML meta-learner (Triple-Barrier + Meta-Labeling + Conformal) + SHAP | ⚪ not started |
| 6 | Sentiment v2 (FinBERT + Whisper + 8-K Lazy Prices) | ⚪ not started |
| 7 | Regime + portfolio (Student-t HMM + NCO + TDA) → **v1.5** | ⚪ not started |
| 8 | Universe expansion (S&P 1500) | ⚪ not started |

**Current focus**: Phase 4 in flight — **4a → 4e merged** (cache +
ROE fix + UX trio backend) across PRs #58-72; **4f price-chart-enhancements
implementation** next per locked sequencing in
[`.claude/skills/phase-4/v1-to-v1-1-migration/PLAN.md`](.claude/skills/phase-4/v1-to-v1-1-migration/PLAN.md).
Production data still on schema `0.6.0-phase3d` (4d / 4e additive
schema fields didn't bump the constant — `recommendation` + `loss_chance_pct`
ride at the existing version per `v1-to-v1-1-migration/PLAN.md`'s
additive-only-within-major rule). Run #32 `b5bc65f3` was the v1.0.0
shipping snapshot; latest production run is `e47fa37e` (2026-05-15
weekly compute reflecting 4d + 4e fields).

**Phase 4 sub-PR progress** (2026-05-14 → 2026-05-15):

- ✅ **4a — Workflow cache improvements** (PR #58). 10-K text +
  fundamentals_history + prices + universe parquet cache steps in
  `compute-rankings.yml`. Steady-state weekly compute target ~10 min
  warm (vs ~30-50 min cold). Cache-key v1 → v2 → v3 → v4 evolution
  across 4a + 4c.1 + 4c.3 as schema additions invalidated each prior
  generation.
- ✅ **4b — `_avg_3y_roe` denominator fix** (issue #11). Average
  equity across all 3 periods instead of single-period snapshot.
  Triggered the value_trap_risk re-fire that 4c.1 cache bump captured.
- ✅ **4c / 4c.1 / 4c.2 / 4c.3 — value_trap_risk + name normalization**
  (PRs #62 / #63 / #66 / #8dc643d6 / #16423995). 4c reduced
  value_trap_risk flagged count from 197 → 196 on warm cache (issue:
  parquets pre-dated `_ANNUAL_TAGS` `stockholders_equity` addition);
  4c.1 bumped cache key v3→v4 to force refetch; 4c.2 normalized
  Wikipedia ticker names but ran against stale universe.parquet;
  4c.3 renamed universe.parquet → universe-v2.parquet to surgically
  invalidate that one cache without breaking the others.
- ✅ **4d — Recommendation badge** (PR #68, polish PRs #69 / #70).
  4-tier outlined-light chip (Strong Buy / Buy / Hold / Sell display;
  bullish / lean_bullish / neutral / cautious internal IDs) on
  overview + detail pages plus a filter control. Pure-function
  `derive_recommendation` in `compute/scoring/recommendation.py` with
  calibration constants locked to S&P 500 distribution (composite ≥60
  + clean + MoS ≥-10 → bullish; thresholds tightened from original
  ≥70 / ≥20 spec after simulation showed 0% Strong Buy). Production:
  26 Strong Buy / 147 Buy / 216 Hold / 113 Sell. `frontend-design-system`
  SKILL drafted from this PR's chip-style audit findings.
- ✅ **4e — Loss Chance % heuristic chip** (PR #72, spacing fix #71).
  Adds `loss_chance_pct` (5-95% clipped) on rankings table + detail
  page in a 5-band gradient outlined-light chip directly after the
  MoS display. Pure-function `derive_loss_chance` in
  `compute/scoring/loss_chance.py` with asymmetric MoS contribution
  (baseline 40, MoS scale 0.35, cap_neg=35 / cap_pos=20, composite
  scale 2.0). Explicitly framed as a heuristic — small italic
  "heuristic" qualifier + tooltip — pending Phase 5 Triple-Barrier
  + Conformal Prediction infrastructure for true calibrated
  probability.
- ✅ **Phase 9 / 10 / 11 roadmap expansion** (PR #73, merged
  2026-05-15). Adds 13 planning stubs spanning free alt-data
  (FRED, SEC Form 4 / 13F, NewsAPI, Reddit, Wikipedia), beginner UX
  (next-intl TH/EN bilingual, localStorage watchlist, Recharts SPY
  overlay, Radix tooltip), and community + transparency (Claude
  Haiku 4.5 stock-story LLM via vendored `claude-api` skill).
  Includes 5 P0 audit-close stubs (changelog-scaffolding,
  dividend-history, earnings-calendar, stock-story-llm, SPY benchmark
  overlay extension). Pure planning — no compute / schema changes.

- ✅ **4f — Price chart enhancements** (PR #76, merged 2026-05-15
  on commit `17323346`). 14 commits, +527 / -85 LOC, 10 files.
  Phase 4.1 + 4.2 shipped together; 4.3 (intraday 1D/5D) deferred
  per locked PLAN §3. **No schema delta** — additive frontend +
  writer slice constant + cron schedule change.
  - **Time-period selector** (`PriceTimePeriodSelector.tsx` new) —
    7 buttons; 1M / 6M / YTD / 1Y / 5Y enabled, 1D / 5D disabled
    with tooltip
  - **Fair-price dashed line** at `fair_price.median` — every
    ticker with non-null median
  - **Target-price solid line** at `fair_price.max` — **every
    recommendation tier** (locked decision per user spot-check —
    Hold / Sell tickers benefit from the upper-bound reference)
  - **Off-chart annotation chips** — color-coded by direction:
    green when reference > current price (upside), red when
    reference < current (overvalued). No "(below/above range)"
    qualifier
  - **Current price + USD label + period change indicator**
    (Google Finance pattern) — `$XX.XX USD +YY.YY (+ZZ%) ↑ <period>`
  - **Dynamic trend color** — line + area fill green on positive
    period change, rose on negative
  - **Gradient area fill** — 22% opacity → 0% Google-style wash
  - **Y-axis hidden** — clutter removed; tooltip + chips cover the
    exact prices
  - **X-axis format** — MM-YY (1M / 6M / YTD / 1Y) / YYYY (5Y)
  - **Inline legend** — Price (matches trend color) / Fair value /
    Target
  - **Hero card 3-column row refactor** — `flex justify-evenly`
    + centered content + chip overflow fix (Loss Chance qualifier
    moved out of chip → caption below), label font bumped
    `text-[10px]` → `text-xs`
  - **5Y daily ingest** — `HISTORY_TAIL_DAYS` 252 → 1260; total
    `stocks/history/` 16 MB → 74 MB; per-file 31 KB → 155 KB
  - **Daily Mon-Fri cron** — `compute-rankings.yml` `"0 22 * * 0"`
    → `"0 22 * * 1-5"`; price staleness ≤ 24 h on trading days
    (was ≤ 7 days)
  - **`_next_business_day_offset()` helper** — `next_update_utc`
    metadata reflects actual next cron run (Fri → Mon +3d, Sat → Mon
    +2d, Sun → Mon +1d, Mon-Thu → next day +1d)
  - Closes issue #77 (hero card baseline misalignment + Loss Chance
    overflow)

  **PR 4f production verification (commit `17323346`, run #25917615337,
  5m14s warm cache):**
  - Universe: **502** stocks; schema `0.6.0-phase3d` (unchanged)
  - Fair-price coverage: **498 / 502 (99.2%)** ✅
  - Tier-2 coverage: **100%** ✅
  - `fundamentals_latency_p95`: **14.41s** (improved from 16.86s)
  - Top-5: CF · HST · NVDA · EIX · LII — rotation invariant 2
    entered / 2 exited
  - `data_quality_input_corruption`: 3 (BRK-B / ERIE / NVR — baseline)
  - Defense scorecard: 4 active vetoes + 1 deferred behind feature
    flag (`non_reliance_filing`, Phase 4g re-enable)
  - `going_concern_disclosure`: 5 tickers (1.0% FP rate, Mayew 2015
    baseline 1-3%)
  - `tier2_coverage_pct`: 100%
  - `next_update_utc`: `2026-05-18T12:29:31Z` = **+3 days** (Friday
    compute → Monday next run, per `_next_business_day_offset()`)
  - History files: **1260 rows × 502 stocks** (5y daily) ✅
  - **Section A-H verify: 0 failures, 0 warnings**

**Next deliverable**: **PR 4g — re-enable 8-K Tier-2 event defenses**
per [issue #14](https://github.com/dackclup/quantrank/issues/14).
Wire `non_reliance_filing` (Item 4.02 hard veto) + `auditor_change`
(Item 4.01 annotate) back into the active layer after the PR 3d
deferral. Sequencing: 4g (8-K re-enable) → 4b (defense-infrastructure
hard gate, issue #75) → 4h / 4i / 4j / 4k (OSAP / JKP / Qlib / IPCA
factor integrations) → tag `v1.1.0-phase4`.

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
- ✅ **3d — Tier-2 event defenses + UI polish** —
  DONE 2026-05-10. Schema bump to `0.6.0-phase3d`. Tag
  **v0.6.0-phase3d** (post-merge). 8 commits, 6 sub-modules,
  91 new non-network tests (409 → 500) + 3 `@network` tests
  added. Adds the **4th active veto**
  (`non_reliance_filing`).
  - **Defense #8** — going-concern phrase scan
    (`compute/scoring/going_concern.py`). Mayew-Sethuraman-
    Venkatachalam 2015 *TAR* + Loughran-McDonald financial
    dictionary subset (CC BY 4.0). 14 curated phrases; pre-compiled
    regex with `\b` word-boundaries + `[\s\-]+` whitespace/hyphen
    flex. Annotate-only.
  - **Defense #9** — 8-K Item 4.02 hard veto
    (`compute/scoring/eight_k_events.py`). Schroeder 2024 SSRN
    finds ~50% of 4.02 filings precede formal restatement.
    365-day lookback. Joins altman / sloan / NSI as the 4th veto.
  - **Defense #10** — 8-K Item 4.01 auditor change (same module).
    Reg S-K Item 304 disclosure. 730-day lookback. Annotate-only —
    audit-firm restructuring fires the same item, FP rate too high
    for veto.
  - **Tier-2 orchestrator** (`compute/scoring/tier2.py`) shares
    one EDGAR fetch per ticker between the veto path
    (`risk_overlay.compute_risk_flags`'s `non_reliance_by_ticker`
    inject) and the display path (`StockDetail.tier2_events`).
  - **10-K text fetcher** (`compute/ingest/filing_text.py`) — 90-day
    on-disk cache, atomic write, sanitized ticker filename.
  - **Frontend** — 3 new components: `Tier2EventCard` (severity-
    coded events), `PillarRadarChart` (8-pillar polar radar),
    `FairPriceBarChart` (6-method horizontal bars + outlier graying).
  - New schema fields: `StockDetail.tier2_events`,
    `Metadata.tier2_coverage_pct`. Reason taxonomy: 24 stable
    identifiers (was 21 in PR 3c).

  **Production verification — DRAFT (filled in at Step 10):**
  - Universe: 502 S&P 500 stocks, schema `0.6.0-phase3d`
  - Compute time: TBD (set after `workflow_dispatch`)
  - Fair-price coverage: TBD
  - Tier-2 coverage (`tier2_coverage_pct`): TBD
  - Tests: 500 (current count; final after Step 9 commits)
  - Reason taxonomy: 24 stable identifiers
  - Defense scorecard: 4 vetoes / 5 guards / 7 annotate-only flags
- ✅ **3e — Tier-3 defenses + Honest Limitations + tag v1.0** —
  DONE 2026-05-14. **Tag `v1.0.0` cut + GitHub Release published.**
  9 PRs merged (#43 / #45 / #46 ship-track + #47 / #48 / #49 / #51 audit
  #6 deep-clean ingest fixes + #52 / #54 Phase 4 UX trio planning docs
  + #55 workflow rebase-then-push + #56 P1 audit backfill).
  - **Beneish M-score** (`compute/scoring/beneish.py`, PR #43) — full
    8-ratio Beneish 1999 *FAJ*. M > −2.22 → `beneish_high` warning
    (ANNOTATE-only). 29 unit tests. PPE field added to snapshot for
    AQI + DEPI ratios.
  - **Dechow F-score** (`compute/scoring/dechow_f.py`, PR #45) —
    Model 1 (7 financial-statement variables). F > 2.45 → `dechow_high`
    warning (ANNOTATE-only). 31 unit tests. RSST simplified to TATA
    proxy + Δcash_sales → % revenue change (both per Dechow 2011
    footnote 13 / coefficient-magnitude analysis).
  - **Honest Limitations README section** (PR #46) — 126 lines covering
    4 fraud classes we can't catch, FP/FN rates per defense, decay
    reality (58% cumulative McLean-Pontiff 2016), free-data fragility,
    diminishing returns at 4 signals (Beneish-Vorst 2021).
  - **Audit #6 deep-clean ingest** (PRs #47-49 + #51 + #56 cache key
    v2 bump) — surfaced 5 layered bugs in `_NORMALIZED_LATEST` / TTM
    flow items / shares_outstanding / PE formula / annual history
    tag chains. All fixed. Median PE dropped **77.8 → 23.2** (industry-
    correct). 12/12 critical tickers verified: NVDA $215.9B (was
    $10.9B), AVB $3.1B (was $7M), META 2.564B shares (was None), WMT
    7.97B post-split shares (was 3.42B), BKNG NI $6.2B (was None), WFC
    $85B / GS $60B / DUK $33B revenue all populated.
  - **Phase 4 UX trio planning** (PRs #52 / #54, planning-only) —
    recommendation-badge (Strong Buy / Buy / Hold / Sell + filter),
    loss-chance (heuristic %), price-chart-enhancements (1D/5D/1M/6M/
    YTD/1Y/5Y + fair-price line + target-price line). All deferred to
    Phase 4 implementation; PLANs at
    `.claude/skills/phase-4/<name>/PLAN.md`.
  - **P1 audit backfill** (PR #56) — closes 4 planning gaps:
    `v1-to-v1-1-migration/PLAN.md` (deprecation contract + PR
    sequencing), `schema-versioning/PLAN.md` (semver applied to JSON
    schema), `phase-5/backtest-infrastructure/PLAN.md` (purged + embargoed
    CV harness — Phase 5 ML foundational), `docs/PHASE_4_8_EFFORT_BACKFILL.md`
    (~6,000 LOC, ~55-60 days v1.0 → v2.0).
  - **CI hardening** (PRs #50, #55) — SEC Filing Roadmap section in
    WORKFLOW.md + rebase-then-push commit step (catches "main moved
    during compute" race that bit run #30 at 52m).

  **v1.0 production verification (commit `b5bc65f3`, run #32):**
  - Universe: 502 S&P 500 stocks, schema `0.6.0-phase3d` (data-schema
    version held at the PR-3d level since PR-3e added no fields; the
    Git release tag is `v1.0.0`, the data version stays consistent
    with the prior PR's contract per the schema-versioning rule)
  - Fair-price coverage: **498 / 502 (99.2%)** — improved from PR 3d's
    97.0% as the audit-#6 fixes restored ~12 tickers' inputs
  - Going-concern FP rate: **1.0%** (Mayew 2015 baseline 1-3%) — Option
    B MD&A restriction holds
  - data_quality_input_corruption: 3 true edge cases (BRK-B / ERIE /
    NVR — all multi-class shares quirks documented in audit #6)
  - Median PE: **23.2** (universe-wide, industry-correct)
  - Beneish coverage: **31.9%** populated · Dechow coverage: **31.3%**
  - 12 critical-ticker fixes: all confirmed clean
  - Top-5: CF · HST · NVDA · EIX · LII — symmetric rotation (2 entered
    APA/GILD = 2 exited EIX/NVDA from prior week)
  - Tests: **646 offline** (excluding 17 `@network`)
  - Section A-H verify: 0 failures, 1 soft warning

**🎉 v1.0.0 SHIPPED 2026-05-14** — git tag + GitHub Release published
with full annotation. Production live at https://quantrank.vercel.app
(or the dackclup deployment URL). Phase 3 closed.

**Defense scorecard — v1.0.0 final**:

| Layer | Count | Composition |
|---|---|---|
| Vetoes (suppress `entered_top5`) | **4 active** | altman_distress · sloan_accruals_top_decile · net_issuance_top_decile · data_quality_input_corruption (promoted in PR #33) |
| Vetoes (deferred behind feature flag) | 1 | `non_reliance_filing` — `_EIGHT_K_DEFENSES_ENABLED = False`. Re-enable in Phase 4 |
| Numerical guards | **5** | stale_filing (120d soft + 180d hard) · outlier 5× / 0.2× · terminal_g ≤ WACC−100bp · sector_exclusion (Quality + EV/EBITDA) · data_quality $10K/share ceiling |
| Tier-2 ANNOTATE-only | **1 active + 1 deferred** | `going_concern_disclosure` (Mayew 2015, MD&A-restricted Option B). Deferred: `auditor_change` (Phase 4) |
| Tier-3 ANNOTATE-only (NEW in PR 3e) | **2** | `beneish_high` (Beneish 1999 8-ratio) · `dechow_high` (Dechow et al. 2011) |
| Valuation warnings (informational) | **8+** | goodwill_heavy · value_trap_risk · extreme_<method>_estimate (×6 method slots) · stale_filing_soft |

**Next deliverable**: Phase 4 first chore is **4a workflow cache
improvements** — add cache steps for 10-K text + fundamentals_history
+ prices + universe to `compute-rankings.yml` so subsequent workflow
runs drop from ~50 min cold to ~5-10 min warm. PR pre-planned in
`v1-to-v1-1-migration/PLAN.md` §"Sequencing".

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

## Phase 3d verified production stats — final (2026-05-14 via v1.0 audit)

- Universe size: **502 stocks** (S&P 500)
- Schema: `0.6.0-phase3d`
- Compute time: ~30-50 min cold / ~30 min warm (per workflow runs
  #15-32 during the audit-#6 cycle)
- Fair-price coverage: **498 / 502 (99.2%)** post audit-#6
- Tier-2 coverage (`tier2_coverage_pct`): 100% (all 502 tickers attempted)
- Tests: **646 offline + 17 @network** at v1.0
- Reason taxonomy: 24 stable identifiers + Tier-3 additions

## Phase 3d acceptance checklist — ✅ all met (2026-05-14)

- [x] Defense #8 going-concern phrase scan (`compute/scoring/going_concern.py`)
- [x] Defense #9 8-K Item 4.02 hard veto (`compute/scoring/eight_k_events.py`,
      currently deferred behind `_EIGHT_K_DEFENSES_ENABLED = False`)
- [x] Defense #10 8-K Item 4.01 auditor change (same module, also deferred)
- [x] Tier-2 orchestrator avoids duplicate EDGAR fetch (one fetch shared)
- [x] 10-K text fetcher with 90-day on-disk cache
- [x] Schema additions wired to TypeScript + snapshot guard regenerated
- [x] CI green on Steps 1-8 commits
- [x] Vercel preview spot-checked on NVDA / AAPL / BKR
- [x] `workflow_dispatch` produces clean run (verified workflow #32)
- [x] `tier2_coverage_pct` populated in Metadata (100%)
- [x] At least 1 stock fires `going_concern_disclosure` flag — 5 fire
      (1.0% of universe, matching Mayew 2015 1-3% baseline)
- [x] Top-5 composition stable rotation week-over-week
- [x] Vercel preview shows `Tier2EventCard` for any flagged stocks
- [x] PR description updated with final scope summary
- [x] Ready for Review + merge

## Phase 3e verified production stats — final (2026-05-14)

- Universe size: **502 stocks** (S&P 500)
- Schema: `0.6.0-phase3d` (no schema delta in 3e — Tier-3 added via
  additive `beneish_m_score` + `dechow_f_score` fields on StockDetail)
- Git release tag: **`v1.0.0`** (`b5bc65f3`)
- Compute time: ~30-50 min (cold cache after audit-#6 cache-key v2 bump
  forced full refresh)
- Fair-price coverage: **498 / 502 (99.2%)**
- Going-concern FP rate: **1.0%** (Mayew 2015 baseline 1-3%) — Option B
  MD&A restriction holds across the v1.0 production data
- Beneish M-score populated: **160 / 502 (31.9%)**, 26 fire `beneish_high`
- Dechow F-score populated: **157 / 502 (31.3%)**, 2 fire `dechow_high`
- data_quality_input_corruption: 3 stocks (BRK-B / ERIE / NVR — true
  multi-class edge cases, all documented)
- Median PE: **23.2** (industry-correct, was 77.8 pre-audit-#6 bug)
- Tests: **646 offline + 17 @network**
- Reason taxonomy: 24 stable + 2 Tier-3 (`beneish_high`, `dechow_high`)
- Top-5 (final composition for v1.0): CF · HST · NVDA · EIX · LII
- Top-5 rotation invariant: symmetric (2 entered = 2 exited)
- Section A-H verify: **0 failures, 1 soft warning**

## Phase 3e acceptance checklist — ✅ all met (2026-05-14)

- [x] Beneish M-Score 8-ratio module (`compute/scoring/beneish.py`)
- [x] Beneish wired into per-ticker loop (`compute/main.py`) — ANNOTATE-only
- [x] Dechow F-Score 7-variable module (`compute/scoring/dechow_f.py`)
- [x] Dechow wired into per-ticker loop — ANNOTATE-only
- [x] `beneish_m_score` + `dechow_f_score` added to StockDetail schema
- [x] TS types mirror + snapshot regenerated
- [x] 60 unit tests across the two modules + threshold + edge cases
- [x] Honest Limitations section in README (frauds we can't catch + FP/FN
      rates + decay reality + diminishing returns)
- [x] Production workflow validated (`b5bc65f3`, run #32)
- [x] Median PE in industry-correct range (23.2)
- [x] All 12 critical-ticker fixes verified (NVDA / AVB / META / WMT /
      BKNG / GS / WFC / DUK / CRWD / AAPL / TSLA / CPT)
- [x] Audit #6 deep-clean of `_NORMALIZED_LATEST` + PE formula + shares
      fallback + revenue / NI chain expansion
- [x] Schema-snapshot CI guard remains in sync
- [x] `verify-production-output` Section A-H: 0 failures
- [x] Tag `v1.0.0` pushed + GitHub Release published

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
