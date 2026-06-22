# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | ✅ DONE — 2026-05-07 |
| 1 | Universe + prices ingestion | ✅ DONE — 2026-05-08 |
| 2 | Fundamentals via SEC EDGAR | ✅ DONE — 2026-05-08 |
| 3 | Classical features + composite + **defenses** → **v1.0** | ✅ **DONE — 2026-05-14** (v1.0.0 tagged + GitHub release) |
| 4 | Factor consolidation (OSAP + JKP + Qlib + IPCA) → **v1.1** | 🟡 IN PROGRESS — 4a-4g + 4c.1/4c.2/4c.3 + PR 4b §1+§2 all merged; **PR #112 (Phase 4h)** shipped OSAP signal replication + PBO/DSR gate + Path-b 50/50 blend (schema bump `0.8.0-phase4.5f` → `0.9.0-phase4h`, no new veto — annotate-only blend, Top-5 still ranks raw composite per Rule 16); **Phase 4h.2 Part 1** (PR #118 merged) shipped observability follow-up — schema PATCH bump `0.9.0-phase4h` → `0.9.1-phase4h.2`; 2 new optional `Metadata` fields surface (a) silent-drop list (78/100 manifest entries missing from dataset) + (b) per-signal `OsapGateDiagnostic`. Part 2 opens after ≥1 week of production diagnostic data; **Phase 4i scout (JKP)** shipped via PR #114 (CC BY-NC 4.0 — license-review-required for integration PR per #115); **Phase 4j scout (Qlib Alpha158)** shipped via PR #119 — `pyqlib` MIT-licensed install + 158-feature manifest + 6 offline tests, NO `@network` test (Qlib's data pipeline is local-bin only — no remote CDN to hit, structurally different from 4h/4i); **Phase 4k scout (IPCA)** shipped via PR #121 — `ipca` MIT-licensed install + 8-method `INSTRUMENTED_PCA_PUBLIC_API` drift detector + 6 offline tests, NO `@network` test (IPCA is pure sklearn-style local computation, 4th distinct structural shape: panel decomposition into Gamma + Factors); all 4 factor scouts now done → eligible for v1.1.0-phase4 tag readiness audit (gated on 4h.2 Part 2 / 4i.1 / 4j.1 / 4k.1 integration PRs); **Phase 4h.2 Part 2 merged via PR #124 (2026-05-19)** — multi-port OSAP adapter (`compute/features/osap_replicate.py::compute_long_short_returns` per-signal `min(port)`/`max(port)` inference, recovering ~56 quintile / tercile signals that the 0.9.0–0.9.1 hardcoded port=01/10 filter silently dropped) + new `Metadata.osap_signals_dropped_no_long_short` field closing the 100-signal accounting equation + schema PATCH bump `0.9.1-phase4h.2` → `0.9.2-phase4h.2`; PR 4b §3 IC-decay output deferred to Phase 5; **v1.1 tag gate RE-SCOPED 2026-06-10** — 4j.1 observability DONE (#426), 4i.1 (JKP) **dropped from the hard gate** (license #115 unresolved since 2026-05-14; WORKFLOW fallback clause invoked), 4k.1 (IPCA) additive/non-blocking; new gate = 4h.1 full OSAP replication (#113) + the 4j.2 Qlib blend decision on ≥ 1 cron of `alpha158_*` IC evidence (§Next deliverables item 5) |
| **4.5** | **Earnings-manipulation defense cluster** → **v1.2** | ✅ **DONE 2026-05-17** — **tag [`v1.2.0-phase4.5`](https://github.com/dackclup/quantrank/releases/tag/v1.2.0-phase4.5) cut** at commit `6d414a9b`. 6 sub-PRs (#89/#90/#91 + #93 + #95 + #97 + #100). Active vetoes **5 → 7**; defense layer **9 → 17** (= 7 vetoes + 10 annotates). 4.5f adds `manipulation_index` (0-100 rollup) + `composite_score_adjusted` (soft penalty, max 10 pts, informational only) + `ManipulationRiskCard` UI + schema bump **`0.7.1-phase4g` → `0.8.0-phase4.5f`**. Production verified run #51 (`b1588b2a`, 5m14s warm-cache): card fires on 158/502 (31.5%); HIGH band 2 (SMCI=84 · WAT=64), MODERATE 60, LOW 96. 4.5e Form-4 insider clustering **deferred to v1.3.0** — reserved-slot weights already declared in `FLAG_WEIGHTS`. |
| 5 | ML meta-learner (Triple-Barrier + Meta-Labeling + Conformal) + SHAP | ⚪ not started — **GATED (re-scope 2026-06-10)** on (a) the Phase 7.0c PIT veto-replay verdict + (b) the data-integrity hardening sprint (§Next deliverables items 1 + 3) + (c) a Supabase client-wiring pre-PR |
| 6 | Sentiment v2 (FinBERT + 8-K + Lazy Prices; **Whisper deferred → Phase 6.1**, re-scope 2026-06-10) | ⚪ not started — TEXT-ONLY scope locked, §6.0 priority order (Lazy Prices → 8-K → FinBERT); Whisper needs Modal paid infra + ~250m ≈ the 240m cron ceiling |
| 7 | Regime + portfolio (Student-t HMM + NCO + TDA) → **v1.5** | 🟡 PARTIAL — **Phase 7.0 SHIPPED** (AI-pick portfolio home + 5y→10y PIT backtest + watchlist + cron auto-refresh; #416-#420 / #424 / #428 / #440); remainder re-scoped as **Phase 7.1** (re-scope 2026-06-10), gated on the 7.0c veto-replay baseline + a longer fit window (single-macro-cycle HMM/TDA = overfit risk) |
| 8 | Universe expansion (S&P 1500) | 🟡 IN PROGRESS — **staged re-scope (2026-06-10)**: S&P 900 pilot (500 + 400 mid-caps) first. Landed: #467 scout · #468 off-cycle pre-cache (#249, hard prerequisite — EDGAR ~1 req/s → cold 1500-ticker fundamentals ≈ 125m vs the 240m ceiling) · #479 obs probe · #480 dispatch input · **#482 integration slice (ranks all ~903 on `QR_UNIVERSE=sp900`)** · **#486 precache-900 Phase A (edgar_form4 fast→slow-text + universe dispatch input)**. Cron default stays `sp500` (gated); next = `universe: sp900` validation dispatch → precache-900 Phase B (cache-v10) + frontend PR 4 → one-line cron flip → midcaps live · **precache-900 Phase B — DONE 2026-06-16 (#492)**: cache-v9-fast→cache-v10-fast bump in all 4 workflows, cron-default flip sp500→sp900, sim QR_UNIVERSE=sp900 explicit, sp400/sp900 universe parquets added to fast path blocks; cron now ranks S&P 900 by default · **#493 multi-index membership (Dow 30 / NDX 100 overlap tabs, schema 0.10.23) — DONE 2026-06-17** · **#494 Russell 1000 (RUI) overlap tab via market-cap proxy, NO schema bump — DONE 2026-06-17**; overlap tabs data-active (first sp900 cron post-#494 `768c35f16` carries russell1000/dow30/ndx tags). **S&P 900 pilot milestone COMPLETE 2026-06-19** — frontend PR 4 (midcap badge) shipped #490 (`MidcapChip` + per-index SPX/MID/ALL tabs) + ≥ 2 green sp900 crons confirmed (3 scheduled crons 6/16-6/18 green). **S&P 1500 cutover underway 2026-06-20** — Slices **1** (scout #514) · **2** (sp1500 seam + smallcap coverage probe, schema 0.10.28, #519) · **4** (`low_liquidity` <$5M ADV annotate, schema 0.10.29, defense 35→36, #527) · **5** (precache `cache-v11-fast` cold-seed + sp1500 dispatch, cron default unchanged, #520) **MERGED**; Slice **3** (Bonferroni shadow) **DEFERRED** to the Slice-8 calibration; first manual `QR_UNIVERSE=sp1500` run committed `chore: update rankings` (label `SP1500-probe`) populating the `smallcap_*` coverage Metadata. **Slice 6 (SmallcapChip + SML tab — frontend-only) MERGED (#531)**. **Slice 7 (cron-default flip sp900→sp1500) MERGED 2026-06-21 (#534 squash `8301b82cb`)** — weekday cron + Saturday precache now default `QR_UNIVERSE=sp1500`; `pre-merge-prod-sim.yml` pinned to sp1500; `compute/main.py` sp600 probe-only filter lifted → full ~1504 names ranked; `Metadata.universe` = `"SP1500"`; cohort-size recompute gate widened to `in ("sp900","sp1500")`; NO schema bump (stays 0.10.29); defense UNCHANGED at 36; validation 1504 names / cold ~174 min (< 240 ceiling) / warm ~45 min (< 90) / smallcap coverage 99.67% / null 0.33% / cik 100%; opus cohort-gate + security workflow review PASSED. **Next = Slice 8 (v2.0 — gated on ≥ 1-2 green sp1500 crons: Bonferroni shadow calibration + virtualized 1500-row table + liquidity-veto promotion decision)**. RUT/RUA/COMP remain SOON pending new small-cap / broad ingest; SML tab data-active once sp600 lands in `rankings.json` |

## Current state (2026-06-22)

| Field | Value |
|---|---|
| Schema | **`0.10.31-phase8pilot`** (#565 squash `2c9dc1371`, merged 2026-06-22 — S&P 1500 cutover Slice 8 / roadmap 7b: Security-type (Type) HeroAttributeTile ingest PR-1 (issue #541): `StockDetail.security_type` from yfinance `fast_info.quote_type` + `Metadata.security_type_coverage_pct` coverage canary; obs-first Rule 18, NO UI wiring; rankings byte-identical; defense UNCHANGED at 36; +17 tests). Prior **`0.10.30-phase8pilot`** (#564 squash `62dbf4f89`, merged 2026-06-22 — Slice 8 Bonferroni multi-test shadow counter (issue #542): 3 new `Metadata.bonferroni_shadow_*` fields; `compute/scoring/bonferroni_shadow.py`; `m = valid_count`; provisional threshold −1.94 placeholder; SHADOW/OBSERVABILITY-ONLY — live scores/rankings byte-identical; defense UNCHANGED at 36; 20 tests). Prior **`0.10.29-phase8pilot`** (#527 squash `2e45a33bf`, merged 2026-06-20 — S&P 1500 cutover Slice 4: `low_liquidity` ANNOTATE flag (<$5M trailing-30d ADV, Amihud 2002; rank-neutral — `valuation_warnings`, not `risk_flags`) + `compute_average_dollar_volume()` + `StockDetail.average_dollar_volume` + `Metadata.low_liquidity_annotate_count`; defense 35→36; rankings/scores byte-identical; dormant on sp900, lights up on sp600). Prior **`0.10.28-phase8pilot`** (#519 squash `5e49dca0a`, merged 2026-06-20 — S&P 1500 cutover Slice 2: `sp1500` universe seam + `_run_smallcap_coverage_probe`; 3 new `Metadata.smallcap_*` fields; sp600 PROBE-ONLY (label `SP1500-probe`, NOT ranked); defense UNCHANGED at 35). Prior **`0.10.27-phase8pilot`** (#512 squash `78fd608423`, merged 2026-06-20 — Dividend signal PR-1: 3 new `StockDetail` dividend fields (`dividend_yield_pct`/`pays_dividend`/`payout_ratio`) + `Metadata.dividend_coverage_pct` coverage canary; `_yf_info_fetch` 2→4-tuple; rankings byte-identical; defense UNCHANGED at 35). Prior **`0.10.26-phase8pilot`** (#501 squash `72ee8667d`, merged 2026-06-19 — cross-source share-count-corruption SHADOW observability PR-1: 4 new `Metadata.cross_source_corruption_*` fields; `grade_cross_source_corruption` + dual-ratio corroboration; MUTATES NOTHING, rankings byte-identical; defense layer UNCHANGED at 35). Prior **`0.10.25-phase8pilot`** (#499 squash `816cda0ea`, merged 2026-06-18 — `post_split_share_lag` HYBRID defense: Tier-1 CORRECT annotate + Tier-2 veto `post_split_share_lag_unreconciled` + folded leg-3 override (direct yfinance `sharesOutstanding`); new `compute/ingest/splits.py`; `RawMetrics.shares_outstanding_pre_split_raw` + 3 `Metadata.*` counters; defense 34→35). Prior **`0.10.24-phase8pilot`** (#496/PR-A, trimmed-median shadow diagnostic #177) · **`0.10.23-phase8pilot`** (#493 + #494 — additive `index_memberships: list[str]`; Dow 30 / NDX 100 overlap tabs; #494 appends `"russell1000"` via market-cap proxy, NO schema bump). Prior #487 OZK/PBF flip-blocker (`0.10.22`, `fundamentals_unavailable` direct veto). Cron default `sp1500` (since #534 2026-06-21 — Slice 7 cron flip; ranks full ~1504 names; prior `sp900` since #492 2026-06-16). Lineage: 0.10.18 #456 → 0.10.21 #482 → 0.10.22 #487 → 0.10.23 #493 → 0.10.24 #496 → 0.10.25 #499 → 0.10.26 #501 → 0.10.27 #512 → 0.10.28 #519 → 0.10.29 #527 → 0.10.30 #564 → 0.10.31 #565. Full table: SKILL.md §schema-version) |
| Defense layer | **36 declared boolean flags** (9 active vetoes incl. `fundamentals_unavailable` #487 + `post_split_share_lag_unreconciled` #499 + 27 annotates incl. the paired `post_split_share_lag` #499 + `low_liquidity` #527 + reserved slots; ~28 currently emit; `USE_SECTOR_COE = True` post-PR #294 flip) · plus 5 numerical guards + `manipulation_index` rollup |
| Active vetoes | **9** — `altman_distress` · `sloan_accruals_top_decile` · `net_issuance_top_decile` · `non_reliance_filing` · `beneish_manipulation_veto` · `dechow_manipulation_veto` · `data_quality_input_corruption` · `fundamentals_unavailable` · `post_split_share_lag_unreconciled` |
| Latest release tag | [**`v1.4.0-phase4.6`**](https://github.com/dackclup/quantrank/releases/tag/v1.4.0-phase4.6) — 2026-05-27 at `a820caee` (Phase 4.6 honest re-validation harness). **v2.0.0-phase8 release PR pending** — all Phase 8 acceptance gates met; `release-captain` owns the cut (HOLD until ≥1 green scheduled sp1500 cron) |
| Post-tag production patches | PR #292 → #302 cluster (2026-05-28/29) — list relocated to §Chronological history |
| Prior release tag | [**`v1.3.0-phase4.5e`**](https://github.com/dackclup/quantrank/releases/tag/v1.3.0-phase4.5e) — 2026-05-26 at `5db3b978` (Phase 4.5e Form-4 cluster + LedgerCraft reskin; defense layer headline 32 → 33) |
| Production run | `65bfd335` (2026-06-11 cron — FIRST run on the #458 cache-v7 family; RATIFY-B manifest verification pending on this artifact). Prior validated baseline: `368dccd9` cron Run #71 (detail relocated to §Chronological history) |
| Universe | **~1504 stocks** (S&P 1500 = ~503 sp500 large-cap + ~399 sp400 mid-cap + ~602 sp600 small-cap; cron default `sp1500` since Slice 7 2026-06-21 (#534); `sp900`/`sp500`-only via manual dispatch) |
| Skill inventory | **45** invocation-triggerable (44 + the vendored `impeccable` symlink) + `phase-N/` planning docs — index: `.claude/skills/README.md` |
| Subagent inventory | **25** in 5 tiers (5 opus + 20 sonnet; 23 `effort: max`, 2 `high`) — roster + routing matrix: `.claude/agents/README.md` |

**In flight** (not yet merged on `main`; per-PR detail lives in
[`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) — append there, not here):
- **v2.0 release PR** (`claude/release-v2.0.0-phase8`) — `pyproject` 1.4.0→2.0.0 + `docs/release-notes/v2.0.0-phase8.md` + this Mode C doc reconciliation; all Phase 8 WORKFLOW.md acceptance gates met; `release-captain` owns the `v2.0.0-phase8` tag (DRAFT; HOLD the tag until ≥1 green scheduled sp1500 cron). `low_liquidity` veto promotion (#544, KEEP-ANNOTATE for v2.0) + Bonferroni provisional-threshold re-derivation (#542) deferred post-v2.0.
- **Merged since last Mode C** (#538 reconciled 0.10.29 / Slice 7, 2026-06-21): **#565** (Security-type ingest PR-1, schema 0.10.30→**0.10.31**) · **#564** (Bonferroni shadow, schema 0.10.29→**0.10.30**) · **#548** (infinite-scroll table, §8.3 gate) · **#549** (Dividend tile PR-2) · **#539/#547/#570** (research warehouse Slices 1/2 + dtype fix) · **#552** (drop free-text post-split warning) · **#553** (timeout 240→270) · **#554** (payout_ratio guard) · **#555** (XBRL balance-tag fix HASI/LGIH/GPK) · **#537** (Sold rows) · **#533** (dividend ×100 fix) · **#546** (docs roadmap groom) · **#556/#557/#559/#560/#575** (dependabot + CI Node 20→22).

**Next deliverables** (re-scoped 2026-06-11; prior items 1-2 — 7.0c gate (a)
+ issue #441 — are DONE, closed entries relocated to §Chronological history):

1. **Data-integrity hardening sprint (~1-2w)** — close the silent share-count /
   extraction corruption cluster before any new ML/factor work trains on the
   composite: #248 (V shares ~4× off, NO veto fired) · #374 (warm-cache
   per-class bypass — source fix #456 + cache-v7 #458 landed, verification on
   the 2026-06-11 artifact pending) · #376 (BF-B) · #379 (GEV spinoff) · #375
   (SNDK reverse-split) · #247/#289 (NVR DQIC gap / empty fair price). **Phase
   5 entry gate (b)**. Closed by #485: #385 (APA OilAndGasRevenue + cache-v9) ·
   #261 (CLOSE-AS-CORRECT via #456).
2. **Phase 4.5e PR 5 — cluster weight promotion 5.0 → 7.0** — UNBLOCKED (#287
   PR B merged as #431); needs ≥ 1 cron's `form4_rule10b5_one_excluded_count`
   confirming the Aboody et al. 2010 §3.2 −30..−45% band + ≥ 4 crons
   accumulating ahead of the Q3 2026-08-19 cohort audit; vesting-residual risk
   still argues against full 10.0 restoration.
3. **v1.1.0-phase4 tag — RE-GATED** — JKP 4i.1 dropped from the hard gate
   (license #115); gate = OSAP 4h.1 (#113) + the 4j.2 Qlib blend decision on
   ≥ 1 real cron of `Metadata.alpha158_*` IC evidence (PBO ≤ 0.5 + DSR > 0);
   4k.1 IPCA (#122) additive, non-blocking.
4. **Phase 5 — ML meta-learner** (~10-12w; the #75 IC-decay writer now ships
   observability-first — Phase 5's walk-forward monthly-IC panel makes its
   `alert` meaningful) — GATED on item 1 + the 7.0c composite-signal
   follow-through + a Supabase
   client-wiring pre-PR (CLAUDE.md §Connectors). Entry gates: WORKFLOW.md
   §Phase 5.
5. **Stock-attribute data — Dividend + Security-type tiles** (display-only,
   parallel-safe; fill the two reserved `HeroAttributeTiles` slots, never touch
   ranking/scoring/defense; one MINOR schema bump per signal;
   observability-before-wiring `Metadata.*_coverage_pct` cron first):
   - **7a. Dividend signal** — add a `dividend` block to the per-stock schema
     (Pydantic `StockDetail` + TS `types.ts` + snapshot, the triple-lockstep).
     Source: yfinance already in the stack — `yf.Ticker(t).info["dividendYield"]`
     / `["payoutRatio"]` (the `Ticker.info` API surface already used by
     `compute/ingest/cross_source.py:129` for `marketCap` + cached under
     `YFINANCE_INFO_CACHE_DIR`; dividend ingest extends that SAME pattern —
     `prices.py` only does `yf.download()` OHLCV, so it's the wrong anchor),
     no new dependency. Ship the diagnostic `Metadata.dividend_coverage_pct`
     FIRST (observability-before-wiring, Rule 18) — confirm the field
     populates on a real cron before the `HeroAttributeTiles` "Dividend" tile
     reads it. Fields to consider: `dividend_yield_pct`, `pays_dividend: bool`,
     optional `payout_ratio`. Tile auto-promotes out of the reserved state
     once `value` is non-null. **Methodology note**: dividend yield is
     descriptive metadata, NOT a new scoring pillar or veto — keep it out of
     the composite unless a separate `financial-engineer` +
     `methodology-scientist` design says otherwise.
   - **7b. Security-type signal** — the `Type` tile (Common stock / ADR /
     REIT / etc.). Source: yfinance `yf.Ticker(t).fast_info.quote_type`
     (NOT `.info["quoteType"]` — that key is retired into `fast_info` on
     current yfinance; and `.info["legalType"]` is funds-only, `None` for
     equities — don't use it), AND for ADR/foreign-issuer detection the SEC
     route `dei:DocumentType == "20-F"` in the XBRL filing (the standard
     foreign-private-issuer annual-report form) or the EDGAR submissions JSON
     `entityType` field (already fetched by `compute/ingest/sec_health.py`).
     The universe is S&P 500 so ADRs are rare but present. Same schema-triple
     + observability-first discipline. Smaller than 7a (a categorical label,
     no numeric).
   Both are **annotate/display-only** — they fill the two reserved
   `HeroAttributeTiles` slots, they do NOT touch ranking, scoring, or the
   defense layer. Sequence each behind a `Metadata.*_coverage_pct` diagnostic
   cron before flipping the tile to read live data (the Phase 4h → 4h.2
   observability-before-wiring precedent). Schema bumps: one MINOR per signal.
   Display-only, parallel-safe — proceeds alongside items 1-3.
   **Status (2026-06-21)**: 7a data + observability legs MERGED (#512 fields
   + `Metadata.dividend_coverage_pct`; #533 fixed the `×100` double-scaling +
   added a `>100` reversion guard). Tracked: **#543** (7a tile wiring — gated
   on ≥ 1 post-#533 sp1500 cron of CORRECTED `dividend_coverage_pct`) ·
   **#541** (7b Security-type obs-first ingest PR-1).
6. **S&P 1500 cutover — Slice 8 / v2.0** (the active universe step) — compute
   layer COMPLETE (Slices 1/2/4/5/6/7 merged; the weekday cron ranks the full
   ~1504 names since #534). The hardening tail is tracked by **epic #545** →
   **#540** (frontend: virtualize the ~1500-row ranking table for mobile — the
   open WORKFLOW.md acceptance gate) · **#542** (Bonferroni multi-test shadow
   counter — Slice 3, deferred) · **#544** (`low_liquidity` annotate → veto
   promotion decision — gated on ≥ 1 sp600 cron firing-rate data + methodology
   ratification). Exit → `v2.0.x` tag after ≥ 1-2 green sp1500 crons.
7. **v1.5.0 release tag** — gated on item 2 (cluster weight promotion)
   landing + post-revert cron data accumulating ahead of the Q3 2026-08-19
   cohort audit; or a `v1.4.x` patch sooner if a structural fix lands alone.

Phase 6 = TEXT-ONLY (→ 6.1) · Phase 7 remainder = 7.1 (gated on the 7.0c
baseline + a longer fit window) · Phase 8 = staged S&P 900 pilot (#249
pre-cache DONE — #468) — detail in WORKFLOW.md.

**Open issues** (as of 2026-06-10, post-roadmap-re-scope; grouped by track): **Data-integrity sprint cluster (item 3)** — #248 (V shares ~4×) · #374 (per-class override warm-cache bypass) · #376 (BF-B) · #379 (GEV) · #375 (SNDK) · #385 (APA revenue) — CLOSED #485 · #261 (multi-class overcount) — CLOSE-AS-CORRECT #485 · #247 + #289 (NVR DQIC → `risk_flags` gap / empty fair price). **Scoring fix (item 2)** — #441 (DONE — closed by #449: the MAD acceptance gate failed at ρ ≈ 0.83 ≫ 0.30 → momentum echo → REMOVE the construct + the dead `macd_hist` slot, schema `0.10.17`). **Factor track** — #113 (OSAP 4h.1, in the v1.1 gate) · #115 (JKP license — dropped from the v1.1 gate 2026-06-10) · #120 (Qlib — 4j.1 observability DONE #426; re-scoped to the 4j.2 blend decision) · #122 (IPCA 4k.1, non-blocking) · #75 (IC-decay writer — CLOSED, wired 2026-06-13 §3). **Ops / infra** — #15 (throttle resilience) · #41 (Next.js 14 → 16 CVEs — zero exploitability on static-export) · #207 (form4 tenacity retry) — CLOSED #485 · #208 — CLOSED #485 / #218 / #377 — CLOSED #485 / #378 — CLOSED #485 (test + verify-helper gaps) · #249 DONE (#468, 2026-06-12 — precache-edgar.yml operational; first Saturday run verified 2026-06-13) · #259 (orchestrator package extract) · #287 (PR A merged #297 + PR B merged #431 — close-candidate once a cron confirms `form4_wall_clock_seconds` populates). **Process / research** — #130 (Q3 cohort audit 2026-08-19) · #137 (9arm-skills license, deadline 2026-06-17) · #150 (foundation reconciliation) · #260 (TMCS, Phase-6-gated).

---

## Chronological history

## 2026-06-22 — S&P 1500 cutover Slice 8 complete; schema 0.10.31; v2.0-ready

All Phase 8 acceptance criteria (WORKFLOW.md §8 checklist) are met. The Slice 8 hardening cluster landed in a batch merge 2026-06-22, closing the last open gates before the `v2.0.0-phase8` tag. Two additive schema bumps (#564 Bonferroni 0.10.29→0.10.30, #565 Security-type 0.10.30→0.10.31) plus a set of no-schema-bump frontend / ingest / warehouse / CI merges.

- **#564 / issue #542** (squash `62dbf4f89`): feat(compute): **Bonferroni multi-test shadow counter** — schema `0.10.29` → **`0.10.30-phase8pilot`**. 3 new `Metadata` fields (all `int | None`): `bonferroni_shadow_live_fire_count` (M > −2.22) · `bonferroni_shadow_provisional_fire_count` (M > −1.94) · `bonferroni_shadow_flip_count` (live-but-not-provisional). New `compute/scoring/bonferroni_shadow.py`; `m = valid_count` data-driven (NOT hardcoded 1500); `α* = 0.05/valid_count` logged. Provisional threshold −1.94 is an ARBITRARY PLACEHOLDER between live −2.22 and soft-veto −1.78 — re-derivation from empirical sp1500 M-score SD DEFERRED post-v2.0. SHADOW/OBSERVABILITY-ONLY — live scores/rankings/flags BYTE-IDENTICAL; defense UNCHANGED at 36. 20 new tests. methodology RATIFY-SHADOW; quantrank-reviewer + schema-sentinel PASS.
- **#565 / issue #541** (squash `2c9dc1371`): feat(compute): **Security-type (Type) HeroAttributeTile ingest PR-1** — schema `0.10.30` → **`0.10.31-phase8pilot`**. `StockDetail.security_type` (yfinance `fast_info.quote_type`, `_QUOTE_TYPE_LABEL` map) + `Metadata.security_type_coverage_pct` coverage canary. `_yf_fast_exchange` widened to a 2-tuple; `fetch_yfinance_security_type` pure cache-read. obs-first Rule 18 — NO UI wiring (Type tile stays 'Coming soon' until a UI PR-2 gated on ≥1 sp1500 cron). Rankings byte-identical; defense UNCHANGED at 36; +17 tests.
- **#548 / issue #540** (squash `e0ea07dc1`): feat(frontend): **infinite-scroll the ~1500-row ranking table** (WORKFLOW.md §8.3 acceptance gate). IntersectionObserver-based append — deliberately NOT true `@tanstack/react-virtual` windowing (conflicts with the FLIP-search-scoped invariant for ~1500 lightweight rows). Frontend-only.
- **#549 / issue #543** (squash `a7fd57b18`): feat(frontend): **Dividend tile PR-2** — HeroAttributeTiles Dividend tile reads live `dividend_yield_pct` (gate cleared: cron #121 confirmed corrected values + `dividend_coverage_pct`). Frontend-only.
- **#539 / #547 / #570** (squashes `b2e899159` / `bca926d9d` / `0b11f6415`): feat(compute): **research warehouse Slices 1/2** — per-run PIT Parquet snapshot writer (`compute/warehouse/`, WRITE-ONLY, cron-committed, NOT the schema triple, `QR_SKIP_WAREHOUSE=1` skips) + maximum-history PIT backfill (`scripts/backfill_warehouse.py`, SP500-only, 11 FORWARD_ONLY_FLAGS written NULL, gitignored artifact) + per-method `fp_*` columns + numeric parquet dtype lock.
- **#555** (squash `100f0f549`): fix(ingest): **XBRL balance-sheet tag selection** — three-tier `_try_balance_tags` (instant period_type + 10-K/Q form filter + USD unit) replacing the bare `get_fact()` call that let 8-K/S-type duration facts beat 10-K consolidated balances. Fixes HASI ($1000→$2.5B), LGIH ($25M→$2.1B), GPK ($10.8M→$8.4B liabilities). Lands corrected on the next cold fundamentals fetch. NO schema bump.
- **#554** (squash `c38829362`): fix(ingest): **payout_ratio format-reversion guard** (`>20 → None`), mirroring the #533 `dividend_yield_pct > 100` guard. Display-field-only; rankings byte-identical.
- **#553** (squash `dbf59ed26`): ci(compute): **timeout-minutes 240→270** across the cron / precache / pre-merge-sim workflows for S&P 1500 scale.
- **#552** (squash `70b5f60fd`): fix(compute): drop the free-text post-split `valuation_warning` + correct stale DQIC docstrings.
- **#537** (squash `a1a0bbc49`): feat(frontend): append rotated-out **Sold rows** to the Current-picks table.
- **#533** (squash `3df2ba5f8`): fix(ingest): **`dividend_yield_pct` ×100 double-scaling removal** + `>100` reversion guard.
- **Dependabot/CI** (#556 upload-artifact 4→7 · #557 checkout 6→7 · #559 npm minor/patch group · #560 @types/node · #575 CI Node 20→22): standard bumps, no logic change.
- **v2.0 readiness**: all WORKFLOW.md §8 acceptance gates met except the tag itself. The `v2.0.0-phase8` release PR (`claude/release-v2.0.0-phase8`) carries `pyproject` 1.4.0→2.0.0 + `docs/release-notes/v2.0.0-phase8.md` + this doc reconciliation; `release-captain` cuts the tag (mobile flow) after ≥1 green scheduled sp1500 cron. Deferred post-v2.0: `low_liquidity` veto promotion (#544, KEEP-ANNOTATE) + Bonferroni provisional-threshold re-derivation (#542).

## 2026-06-21 — S&P 1500 cutover Slice 7: cron-default flip sp900→sp1500 (#534) + Slice 6 SML tab (#531)

The final compute-layer gate of the S&P 1500 cutover. After Slices 1 (scout) / 2 (seam+probe) / 4 (ADV annotate) / 5 (precache v11) / 6 (SML tab) merged, Slice 7 lifts the sp900 cron default and starts ranking the full ~1504-name S&P 1500 universe on every scheduled run — the 902 → ~1504 production cutover.

- **#534** (squash `8301b82cb`, branch `claude/sp1500-slice7-cron-flip`): ci(compute): **S&P 1500 cutover Slice 7 — cron-default flip sp900→sp1500**. The weekday cron (`compute-rankings.yml`) + Saturday precache (`precache-edgar.yml`) now default `QR_UNIVERSE=sp1500`; `pre-merge-prod-sim.yml` pinned to sp1500 for simulate parity. `compute/main.py` lifts the Slice-2 probe-only sp600 filter — the cron now RANKS the full S&P 1500 (~1504 names: ~503 sp500 + ~399 sp400 + ~602 sp600); `Metadata.universe` emits `"SP1500"` (no longer `SP1500-probe`). Post-scoring cohort-size recompute gate widened to `in ("sp900","sp1500")` (sum-invariant fix — opus-review FAIL caught + fixed + locked by an sp1500 fixture); smallcap coverage probe + russell1000-proxy sp600 guard retained. **NO schema bump** (stays `0.10.29-phase8pilot`); **defense layer UNCHANGED at 36**. Validation: ranked-1500 simulate = 1504 names / cold ~174 min (< 240-min cron ceiling); warm probe (#120) 31 min → warm ranked extrapolated ~45 min (< 90); smallcap coverage 99.67% / null 0.33% / cik 100%. opus cohort-gate review + security workflow review both PASSED.
- **#531** (branch `claude/sp1500-slice6-sml-tab`): feat(frontend): **S&P 1500 cutover Slice 6** — `SmallcapChip` (violet) + SML (S&P 600) tab activation in `RankingView`/`RankingTable`/`StockListCard`, mirroring the MidcapChip + MID-tab pattern. Frontend-only, NO schema bump. Data-driven dormancy: SML tab + chip light up automatically once sp600 rows appear in `rankings.json` after the Slice 7 cron flip — no further frontend code change needed.
- **Next universe step**: Slice 8 (v2.0) — gated on ≥ 1-2 green sp1500 crons: Bonferroni shadow calibration (Slice 3, deferred) + virtualized 1500-row table (8.3 frontend) + liquidity-veto promotion decision.

## 2026-06-20 — S&P 1500 cutover Slices 2 / 4 / 5 (#519 · #527 · #520) + coverage tests (#525 · #528)

The next universe step after the S&P 900 pilot. Three substantive slices landed on `main` (schema `0.10.27` → `0.10.29`, defense 35 → 36); Slice 3 (Bonferroni shadow) was DEFERRED to the Slice-8 calibration. The first manual `QR_UNIVERSE=sp1500` Compute Rankings run committed a `chore: update rankings` to `main` (universe label `SP1500-probe`) populating the new `smallcap_*` coverage Metadata.

- **#519** (squash `5e49dca0a`, branch `claude/sp1500-slice2-seam-probe`): feat(compute): **S&P 1500 cutover Slice 2** — `sp1500` universe seam in `compute/main.py` + `_run_smallcap_coverage_probe` (observability-first, Rule 18). 3 additive `Metadata` fields (all `| None`): `smallcap_fundamentals_coverage_pct` / `smallcap_null_rate_pct` / `smallcap_cik_resolution_pct`, measured over the sp600 cohort BEFORE any ranked exposure. `universe_cohort_sizes` gains an `"sp600"` key under `QR_UNIVERSE=sp1500`; `Metadata.universe` emits `"SP1500"` (label `SP1500-probe`). **sp600 is PROBE-ONLY** — filtered from the scored frame, NOT ranked; `derive_index_memberships` guards sp600 from the russell1000 market-cap proxy. Cron STAYS sp900; sp1500 only under manual dispatch — rankings byte-identical. Also folded a WORKFLOW.md §8.6 Beneish Bonferroni **sign-fix** (−2.22 → −2.50 was backwards — a stricter FWER cutoff moves UP toward 0) + **Slice 3 (Bonferroni shadow) DEFERRED** to the Slice-8 calibration. Schema `0.10.27` → **`0.10.28-phase8pilot`**. **Defense layer UNCHANGED at 35** (9 active vetoes). +21 tests; schema triple lockstep passed.
- **#520** (squash `b2bffde3e`, branch `claude/sp1500-slice5-precache-v11`): ci(precache): **S&P 1500 cutover Slice 5** — `cache-v10-fast` → `cache-v11-fast` cold-seed bump across 4 workflows (`compute-rankings.yml` · `precache-edgar.yml` · `pre-merge-prod-sim.yml` · `backfill-portfolio.yml`) + `sp1500` `workflow_dispatch` option + sp600/sp1500 parquet cache paths. WHY the key bump: the fast bundle's exact-quarter-key save-skip means sp600 data written under a warm v10 sp900 key would be silently dropped (FROZEN-IMMUTABLE-within-a-quarter gotcha) — identical mechanism to the v9→v10 precache-900 Phase B bump (#492). **Cron default UNCHANGED (stays sp900)**; slow-text bundle key unchanged. NO schema bump.
- **#527** (squash `2e45a33bf`, branch `claude/sp1500-slice4-adv-liquidity`): feat(scoring+schema): **S&P 1500 cutover Slice 4** — `low_liquidity` ANNOTATE flag (<$5M ADV, rank-neutral, obs-first). Fires when trailing-30d mean dollar volume < `ADV_FLOOR_USD` ($5M, `ADV_LOOKBACK_DAYS=30`; Amihud 2002 *J. Financial Markets* §2 illiquidity family). RANK-NEUTRAL: emitted into `valuation_warnings`, NOT `risk_flags` — no `cautious`, no Top-5 suppression, no fair-price null (`portable-annotate-before-veto` + Rule 18). New `StockDetail.average_dollar_volume: float | None` + `Metadata.low_liquidity_annotate_count: int | None`. New pure `compute_average_dollar_volume(df, lookback_days)` in `compute/ingest/prices.py` (never raises, `None` on any failure); `compute/main.py` computes ADV in `_fetch_prices_one` (zero extra I/O — reuses the cached OHLCV frame). **Rankings/composite scores byte-identical**; **dormant (~0 fires) on sp900** (every S&P 900 name clears $5M ADV), lights up only on sp600. Schema `0.10.28` → **`0.10.29-phase8pilot`**; **defense layer 35 → 36** (new annotate; 9 active vetoes UNCHANGED, annotates 26 → 27). methodology-scientist RATIFY-SHADOW; veto promotion deferred pending ≥ 1 cron of firing-rate data + ratification. +20 tests; schema triple lockstep passed.
- **#525** (squash `c51ddd55e`): test(ingest): offline coverage for the PIT parquet readers (`historical_8k` 63 → 88%, `historical_sector` 60 → 90%). Test-only; no schema / defense touch.
- **#528** (squash `8be261fd8`): test(ingest): offline coverage for `universe.py` scrape parsing (80 → 93%). Test-only; no schema / defense touch.
- **Next universe step** (as of these slices; superseded by the 2026-06-21 entry above): Slice 6 (SML tab/chip — #531, MERGED) → Slice 7 (cron flip to sp1500 — #534, MERGED 2026-06-21) → Slice 8 (v2.0 — Bonferroni shadow calibration + virtualized 1500-row table + liquidity-veto promotion decision).

## 2026-06-20 — Dividend signal PR-1: observability-first display metadata (#512)

- **#512** (squash `78fd608423`, branch `claude/dividend-signal-obs`): feat(ingest+schema): Dividend signal observability (PR-1, display-only metadata). Roadmap item #5 / 7a. Schema `0.10.26-phase8pilot` → **`0.10.27-phase8pilot`** (additive PATCH — 4 new optional fields, all default `None`, backward-compatible under `extra="forbid"`).
  - **What shipped**: 3 new `StockDetail` fields — `dividend_yield_pct: float | None` (PERCENT, ×100 from yfinance fraction `dividendYield`), `pays_dividend: bool | None` (`True iff dividend_yield_pct > 0`), `payout_ratio: float | None` (0-1 fraction) — plus `Metadata.dividend_coverage_pct: float | None` (Rule-18 coverage canary modeled on `exchange_coverage_pct`).
  - **Implementation**: `compute/ingest/cross_source.py` — `_yf_info_fetch` 2-tuple → 4-tuple; new `fetch_yfinance_dividend(ticker)` pure cache-read off the warm `yfinance_info` cache already populated by `fetch_yfinance_market_cap` (zero new network round-trips). `compute/main.py` Step-8 per-ticker dividend populate + post-loop `dividend_coverage_pct` aggregation.
  - **Invariant gates**: rankings/pillar scores/risk_flags/recommendation/vetoes **byte-identical** (no scoring consumer reads the new fields). **Defense layer UNCHANGED at 35 declared / 9 active vetoes**. Rule 18 observability-before-wiring: `dividend_coverage_pct` is the canary — the `HeroAttributeTiles` "Dividend" UI tile is a SEPARATE follow-up gated on ≥ 1 cron confirming coverage.
  - Schema triple lockstep updated in sync (`schema_check` passes); +25 tests; `tsc --noEmit` + `next build` green. CI took 3 cycles: the R6 weekend-flaky prices-recency test (inherited from #498) was resolved by deferring to main's #515 fix; two `PHASE_STATUS_INFLIGHT.md` append-collisions (parallel #510/#511/#513 then #514/#515) resolved keep-both. pre-merge-prod-sim movers (V/KLAC/BRK-B/PBF) are all sim-env artifacts (cold-cache can't reproduce #499 split-correction / #487 fundamentals-unavailable / dual-class), NOT regressions.
  - **Next**: await first cron carrying `dividend_coverage_pct`; then the `HeroAttributeTiles` "Dividend" tile PR (7a PR-2). Security-type tile (7b) proceeds in parallel.

## 2026-06-20 — parallel no-schema-bump merges: #514 · #515 · #518 · #521

Four PRs merged on `main` alongside the #512 dividend bump (2026-06-19/20), none touching the schema triple or the defense layer (schema stayed at the then-current `0.10.27-phase8pilot`; defense 35 declared / 9 active vetoes — the S&P 1500 cutover slices that later moved it to `0.10.29` / defense 36 are logged in the 2026-06-20 S&P 1500 section above). Logged here for chronological completeness; per-PR detail in `PHASE_STATUS_INFLIGHT.md`.

- **#514** (squash `08a74c099`): feat(ingest): **S&P 1500 cutover Slice 1** — `fetch_sp600_constituents` + an S&P 1500 universe-loader scout in `compute/ingest/universe.py` (+ S&P 600 config constants). SCOUT ONLY — no `compute/main.py` wiring, so the weekday cron still ranks S&P 900; the S&P 600 small-cap ingest + virtualized 1500-row table + Bonferroni / liquidity guards are the remaining cutover work. No schema bump; +567 tests.
- **#515** (squash `a766bd1eb`): fix(test): weekend-robust boundary in `test_R6` prices-recency guard — the `_frame_last_bar_on` helper pins the cached frame's last bar to an exact calendar date so the strict-`>` boundary test stops spuriously failing on weekend CI runs (the latent #498 test bug). This session's own R6 fix on the #512 branch deferred to #515. Test-only.
- **#518** (squash `7952c1dd1`): test+tooling: **pytest-cov** coverage tooling (baseline 85%) + P-low coverage tests (`pyproject.toml` coverage config + `test_main` / `test_risk_overlay_coverage` / `test_applicability_coverage`). Dev-tooling + tests only; no production code path changed.
- **#521** (squash `92c69ce51`): chore(ui): **design-kit alignment polish pass** — token / spacing alignment across ~12 frontend components (Chip · FairPriceCard · HeroAttributeTiles · PillarRadarChart · RecommendationBadge · …) per the LedgerCraft design system. Frontend-only; no schema / compute touch.

## 2026-06-19 — cross-source share-count-corruption SHADOW observability PR-1 (#501)

- **#501** (squash `72ee8667d`, branch `claude/cross-source-corruption-obs`): feat(scoring+schema) cross-source share-count-corruption shadow observability — PR-1 (Rule 18 obs-first). Motivated by the post-cron #114 audit that revealed COKE as a false-negative and BKNG as a false-positive under the #499 `post_split_share_lag` defense: those cases arise from a broader class of `cross_source_delta` corruption (`|sec_mc − yf_mc| / sec_mc`) not bounded by the 100d/2× split window. New `grade_cross_source_corruption()` pure function + `compute_cross_source_corruption_shadow()` aggregator in `compute/scoring/risk_overlay.py`; `CorruptionGradeResult` dataclass (NO_FIRE / CORRECT_CANDIDATE / VETO_CANDIDATE); `DELTA_CORRUPTION_THRESHOLD=0.50` (Ince-Porter 2006 histogram anchor) + `INTEGER_RATIO_TOLERANCE=0.10` in `compute/config.py`. Dual-ratio corroboration: both `mc_ratio` and `share_ratio` must round to the same integer for CORRECT_CANDIDATE (COKE gold fixture: mc_ratio≈7.07→7 ≠ share_ratio=10→10 → VETO_CANDIDATE + ratio_disagreement=True). 4 new `Metadata` fields (all `| None`): `cross_source_corruption_correct_candidate_count` / `_veto_candidate_count` / `_ratio_disagreement_count` / `_inferred_ratio_by_ticker`. Schema `0.10.25` → **`0.10.26-phase8pilot`**. **Defense layer UNCHANGED at 35** (9 active vetoes, 26 annotates) — PR-1 is shadow counters only; the new `share_count_corrected_cross_source` annotate + `share_count_corruption_unreconciled` veto are GATED for PR-2. methodology-scientist RATIFIED-WITH-CONDITIONS; quantrank-reviewer READY-TO-PUSH; 2094 tests; the `round(R)` integer-recovery has a GUT-FEEL provenance label — the corroborating yfinance `.splits` event + methodology re-anchor Q3 2026-08-19 are hard PR-2 gates.
- **cron #115 shadow read-out (2026-06-19, first cron carrying the #501 `cross_source_corruption_*` fields)** — `veto_candidate_count=8`, `correct_candidate_count=1` (`inferred_ratio_by_ticker={"DVN":2.0}`), `ratio_disagreement_count=5`. The methodology-ratified PR-2 VETO go-band was [1,5]; 8 lands in the [6,9] INVESTIGATE band. data-pipeline-engineer INVESTIGATE verdict: **6 of 8 VETO_CANDIDATEs are STRUCTURAL FALSE POSITIVES** — IBKR (Up-C holding-co), NSA (REIT OP-units), VNOM (MLP→C-Corp), BX (LP units), RYAN (Up-C LLC), BRK-B (dual-class, already config-deferred) — yfinance vs EDGAR report different share bases BY DESIGN; the sp500-calibrated grader can't tell "EDGAR wrong" from "yfinance different denominator." Root cause: the sp900 expansion (sp400 midcaps) added a higher density of OP-unit / MLP / Up-C / dual-class structures. Only COKE (yf-marketCap-stale, already `beneish_manipulation_veto`-suppressed, rank 98) + CVNA (already `post_split_share_lag_unreconciled`-vetoed → double-coverage) are "real." φ(VETO,DQIC)=−0.01, φ(VETO,`post_split_share_lag_unreconciled`)=0.25 (both <0.5; the 0.25 is the CVNA double-coverage). **DISPOSITION: cross-source corruption VETO (PR-2) DEFERRED to Q3 2026-08-19** — observability-first did its job (the shadow surfaced the structural-FP rate BEFORE a veto would have suppressed 6 valid tickers in production); PR-1 shadow KEPT as the diagnostic. Q3 prerequisites before any promotion: (a) generalize a structural-FP suppression (Up-C / OP-unit / MLP / dual-class, extending `MULTI_CLASS_OVERCOUNT_ALLOWLIST`); (b) recalibrate the go-band [1,5]→[1,3]; (c) scope-delineate cross-source vs `post_split_share_lag_unreconciled` (CVNA); (d) probe the DVN 2× root cause before any CORRECT mutation. Also flagged: **COKE EDGAR-vs-yfinance stale-direction ambiguity** (cron #114 stock-detail-auditor read EDGAR pre-split / scoring-side corrupt; cron #115 data-pipeline-engineer read yfinance-marketCap-stale / EDGAR-correct) — reconcile before any COKE correction/veto. #499 `post_split` re-validated on cron #115 (3 = 1 applied + 2 veto, stable). The PR-2 wiring design (financial-engineer DESIGN-READY) + methodology RATIFY-WITH-CONDITIONS are preserved for the Q3 build once the grader FP-suppression lands.

## 2026-06-18 — post_split_share_lag HYBRID defense (#499) + trimmed-median diagnostic (#496) + prices recency guard (#498) + Path C amendment (#497)

- **#499** (squash `816cda0ea`, branch `claude/confident-thompson-y58bhe`): `post_split_share_lag` HYBRID corporate-action defense. yfinance auto-split-adjusts prices but EDGAR `shares_outstanding` lags to the next 10-Q/10-K → post-split price × pre-split shares corrupts P/E / market_cap. Detection (3 legs): split ≤ `POST_SPLIT_WINDOW_DAYS`=100d · ratio ≥ `POST_SPLIT_MIN_RATIO`=2.0× · reconciliation `|yf_implied/EDGAR − ratio|/ratio` ≤ `POST_SPLIT_RATIO_TOLERANCE`=0.10. **Tier-1 CORRECT** (`post_split_share_lag`, annotate in `valuation_warnings` — NOT `risk_flags`, so a corrected ticker stays Top-5-eligible): `corrected_shares = EDGAR × ratio` at `main.py` Step 3b before scoring; raw kept in `RawMetrics.shares_outstanding_pre_split_raw` (Rule 9). **Tier-2 VETO** (`post_split_share_lag_unreconciled`, the 9th active veto): legs 1+2 fire, leg-3 fails → `cautious` + null fair-price, before DQIC. Folded-in **leg-3 override**: `main.py` passes the direct yfinance `sharesOutstanding` (`fetch_yfinance_shares_outstanding`, cache-read off the existing market_cap `.info` round-trip) so leg-3 compares share counts directly (cache-timing-robust). New `compute/ingest/splits.py`. Schema `0.10.24` → **`0.10.25-phase8pilot`**; defense layer **34 → 35** (9 active vetoes). methodology-scientist RATIFIED HYBRID (FP ~0); data-pipeline-engineer live-probe verified KLAC→Tier-1 (corrected 1,306.28M) / CVNA→Tier-2 (dual-class) / COKE→Tier-0; quantrank-reviewer READY-TO-PUSH (base + increment); 2079 offline tests. LIVE RANKING CHANGE next cron: KLAC P/E 6.68→~66.8, rank-2 de-inflates.
- **#496 / PR-A** (squash, 2026-06-18): trimmed-median shadow diagnostic (Issue #177) — **`0.10.24-phase8pilot`**. Shadow `FairPriceEnsemble.median_trimmed` + `methods_excluded_from_median` + `Metadata.median_trim_delta_count`; live `median`/`mos_pct` byte-identical (observability-first Rule 18). 33 tickers (3.8%) would flip MoS sign; behavioral flip DEFERRED to Q3 (Path C). Defense layer UNCHANGED at 34.
- **#497** (squash, 2026-06-18): docs(methodology) Path C amendment — #177 trimmed-median flip DEFERRED to Q3 2026-08-19 via a forward-OOS shadow record + `BASKET_RULE_N_TRIALS` 15→16. NO schema change.
- **#498** (squash, 2026-06-18): fix(ingest) prices.py last-bar-date recency guard — `PRICES_CACHE_MAX_STALE_DAYS=7` forces a refetch when the cached frame's last bar is > 7 calendar days old (GHA `actions/cache` resets mtime → the old `age_hours` TTL was dead, same class as #471). NO schema change.

## 2026-06-17 — multi-index membership: Dow 30 / NASDAQ 100 overlap tabs (#493) + Russell 1000 (RUI) proxy (#494)

- **#493** (squash `1650b1e59`, branch `claude/confident-thompson-y58bhe`): additive `index_memberships: list[str]` on `StockSummary` + `StockDetail` (`default_factory=list`, backward-compat under `extra="forbid"`). Contains cohort ("sp500"|"sp400") PLUS "dow30"/"ndx" for overlap members. `universe.py` adds `fetch_dow30_constituents` / `fetch_ndx_constituents` (Wikipedia, 7-day cache, graceful-degradation, sanity bands Dow==30 / NDX 95-105) + `derive_index_memberships`. Frontend: `RankingView.tsx` DJI / NDX tabs (data-driven). `index_membership` (singular) UNCHANGED. Schema `0.10.22-phase8pilot` → **`0.10.23-phase8pilot`**. Defense layer 34 UNCHANGED.
- **#494** (squash `f4da5a299`, same branch): Russell 1000 (RUI) overlap tab via market-cap proxy — `derive_index_memberships` appends `"russell1000"` iff `market_cap is not None and market_cap > 0`. **NO schema bump** (SCHEMA_VERSION stays `0.10.23-phase8pilot`); the list field already exists. Every S&P 900 constituent is a Russell 1000 member by construction (S&P 400 floor > Russell 1000 cutoff), so the RUI tab ≈ All-stocks by design. RUT/RUA stay SOON (need small-cap / S&P 600 ingest). Tests 54 → 63.
- First production cron post-#494 (`768c35f16`, "update rankings 2026-06-17") — first sp900 cron carrying russell1000 / dow30 / ndx tags; overlap tabs now data-active. Validated counts: russell1000 **900 / 902** (2 no-market-cap names correctly excluded), dow30 30, ndx 88, 0 rows with empty `index_memberships`.
- **Next**: ✅ **S&P 900 pilot milestone COMPLETE 2026-06-19** — ≥ 2 green sp900 crons confirmed (3 scheduled crons 6/16-6/18 green) + frontend PR 4 (midcap badge) shipped #490. Next universe step = **S&P 1500 cutover** (S&P 600 small-cap ingest). RUT/RUA/SML/COMP remain SOON pending new small-cap / broad ingest.

## 2026-06-16 — precache-900 Phase B: cron-default flip sp500→sp900 (#492)

- All gates cleared: sp900 validation run #107 PASSED pre-registered defense bands
  (NSI fired-share tilt **1.461× — IN-BAND, < 1.6× alarm**; Sloan 10.42%
  universe-wide / 1.032× sp400 tilt — IN-BAND; Section A-L 0 fail).
  Methodology RATIFIED PROCEED-WITH-DOC. FDXF empty-snap blocker fixed + merged (#491).
- `cache-v9-fast` → `cache-v10-fast` bump in all 4 workflows in lockstep; cron-default
  flip `|| 'sp500'` → `|| 'sp900'` (compute-rankings + precache-edgar); pre-merge-prod-sim
  now sets explicit `QR_UNIVERSE: sp900`; `compute/config.py` code default stays `sp500`.
  sp400/sp900 universe parquets added to fast `path:` blocks. Schema triple untouched;
  defense layer unchanged at 34. Tests 31→33.
- **NSI tilt methodology note:** the sp400 NSI raw-rate ratio was 2.31× — NOT the
  pre-registered metric. The pre-registered metric is the **fired-share tilt = 1.461×**,
  IN-BAND (< 1.6× alarm). The rate-ratio elevation is consistent with Fama-French 2008
  (NSI monotonically stronger in smaller caps). Future Q3 cohort audits MUST compare the
  fired-share tilt, NOT the raw-rate ratio, to avoid a false alarm.

### Relocated from §Current state (2026-06-11 token drain — verbatim)

The merged-PR lists + stale table prose below were MOVED here unchanged from
§Current state (the forced-read session-start section) on 2026-06-11; newest
first. Closed next-deliverables entries (7.0c gate (a) + issue #441) follow
the lists.

**Recently merged** (Phase 7.0 + cron + Phase 4j.1 cluster, #416 → #449, 2026-06-04 → 2026-06-10):
- PR #449 — refactor(scoring): issue #441 close-out — REMOVE MAD + the dead `macd_hist` slot (pre-registered gate FAILED on the first real cron: ρ 0.834 / 0.807 ≫ the 0.30 line = momentum echo; methodology-scientist RATIFY-REMOVE; schema `0.10.16 → 0.10.17`; technical pillar = honest 4-metric mean; NO 5th input without a fresh pre-registration)
- PR #448 — docs(roadmap): roadmap-fit re-scope, user-confirmed 8-point re-sequencing (veto-replay → Phase 5 gate · data-integrity sprint · v1.1 re-gate sans JKP · Phase 6 text-only · 7.1 rename · Phase 8 staging) + drift sweep
- PR #447 — feat(scoring): MAD factor diagnostics, issue #441 PR-1 (3 `Metadata.mad_*` fields, schema `0.10.15 → 0.10.16`; pillar UNTOUCHED — dead `macd_hist` stays until the fix+wiring PR; feeds the PR-2 wiring gate `abs(ρ) < 0.30` + coverage ≥ 90%)
- `3dbe2581` (direct) — feat(home): AI-pick chart overlay, P/L since entry, quarterly/half-year ticks, editable capital
- PR #446 — chore(agents): 5 judgment-gate subagents `model: opus` → `model: fable` (floating alias) + `check_model_pin.py` allow-list + docs lockstep
- PR #444 — fix(chart): show all year labels on mobile portrait (rotated x-axis)
- PR #443 — ci(cron): raise folded PIT-backtest step cap 40→55m + job ceiling 225→240m (post-#440 headroom)
- PR #442 — feat(scoring): MAD factor construct — technical pillar PR-1 scout (unwired; follow-ups + the dead-`macd_hist` bug tracked in #441)
- PR #440 — feat(backtest): extend AI-pick PIT backtest 5y → 10y (membership ledger 2016+ via fja05680 snapshot-diff; `cache-v6-fast` bump)
- PR #431 — ci(cron): revert emergency `FORM4_FETCH_SKIP=1` (Issue #287 PR B) — unblocks Form-4 gate-data accumulation for Phase 4.5e PR 5
- PR #429 — chore(output): orphan per-stock-JSON prune for de-listed/renamed tickers (EPAM + BK→BNY; `prune_orphan_stock_files` + safety floor; 502/502 restored; no schema change)
- PR #428 — feat(frontend): Phase 7.0 personal browser-local Watchlist (`/portfolio` stub → real localStorage watchlist; FRONTEND-ONLY, no schema change)
- PR #427 — perf(cron): split tier2 cache (fast + slow-text run-id key) + per-stage timing summary
- PR #426 — feat(features): Phase 4j.1 Qlib Alpha158 observability surface (schema `0.10.14 → 0.10.15`; 9 `Metadata.alpha158_*` + reused PBO/DSR gate; observability-only, Δscore = 0)
- PR #425 — ci(cron): trading-day NYSE-holiday gate
- PR #424 — ci(cron): auto-refresh the PIT backtest inside the weekly cron
- PR #416 → #420 — feat: Phase 7.0 AI-pick portfolio home + 5y PIT backtest (schema `0.10.13 → 0.10.14` `benchmark_coverage_pct`)
- _PRs #374 → #415 await a housekeeping-drain reconcile into this log — their append-only detail lives in [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md)._

**Earlier merged** (PR #331 → PR #373, 2026-05-31 → 2026-06-02):
- PR #373 `93c98a2` — fix(audit): Commit A — 12-item deep-audit MUST-FIX sweep (dark-mode chips · font-mono · aria-label · loose-null ×2 · ring-amber-200 · script-injection · schema pointer · ~27 emit count · PR-A2 ref)
- PR #372 `858cf21` — feat(frontend): detail-page two-level spacing + attr-tiles float fix
- PR #371 `8014916` — feat(frontend): ranking-table warm empty-state (SearchX + nudge + fade-in)
- PR #370 `64a72f9` — feat(frontend): bolder home-page header — 4-tier hierarchy + emerald universe-count accent
- PR #369 `f9c5f47` — feat(frontend): global `.press` utility — `scale(0.97)` press feedback on 23 controls
- PR #368 `9a0a1a8` — fix(frontend): `ScoreGauge` + `ScoreBadge` tier word → canonical TIERS (fixes 81-ticker wrong-word mismatch)
- PR #367 `08baab4` — perf(frontend): `PriceHistoryChartLazy` — Recharts code-splits from stock-detail First Load (214→110 kB, −49%)
- PR #366 `cd14811` — polish(frontend): drift sweep — chip `font-medium` · `font-mono tabular-nums` · `bg-amber-50` · `ring-200` · `tracking-wider`
- PR #365 `e2050f0` — fix(frontend): `FilterDrawer` in-drawer active-filter removable chips (remove-ONE path)
- PR #364 `6b57f57` — fix(frontend): a11y minors — `MoSBadge` `role="img"` + "(vs fair value)" · pillar `sr-only` median · hero "Data as of {date}"
- PR #363 `e8a8268` — fix(frontend): pillar tier labels → canonical TIERS vocabulary + 25/40/55/70 boundaries
- PR #362 `c29fe86` — fix(frontend): hero loss-chance full 5-band `{ tone, dot, label }` object + band WORD caption
- PR #361 `e757028` — fix(frontend): restore daily-change `CurrentPriceLine` to detail + demote `FairPriceCard`
- PR #360 `545a1a0` — fix(frontend): soften alarm-red dots → `bg-rose-500` + correct pillar-bar comment
- PR #359 `fbe32bf` — fix(frontend): loss-chance band from `Math.round(pct)` + empty-state recovery + nits
- PR #358 `24c9be7` — feat(frontend): URL-serialized filter state — shareable/bookmarkable via `filter-url.ts`
- PR #357 `183305e` — feat(frontend): "Supporting data" `<details>` progressive disclosure
- PR #356 `dd56dc1` — fix(frontend): WCAG-AA secondary text (`slate-500/400` app-wide) + `FilterDrawer` chip `min-h-[44px]`
- PR #355 `93231b7` — fix(frontend): a11y punch-down — `FilterDrawer` focus-trap · `min-h-[44px]` ×23 · warning-card severity headings
- PR #354 `d5c933e` — docs(design): regenerate DESIGN.md + sidecar
- PR #353 `ef83c4a` — docs(skill): un-stale `frontend-design-system` Rule 4 dark-mode
- PR #352 `339fef5` — feat(frontend): calm daily-change chip + honest gauge-accent comments
- PR #351 `2978748` — feat(frontend): country + exchange hero chips (PR-B; `country-flag-icons ^1.6.17`)
- PR #350 `c47445f` — docs(design): add `impeccable` PRODUCT.md + DESIGN.md context
- PR #349 `809cd4d` — feat(compute): wire `country` + `exchange` into `main.py` (PR-A2; coverage observability)
- PR #348 `65af2ec` — chore(skills): vendor `impeccable` skill (Apache-2.0)
- PR #347 `5f39d64` — feat(ingest): `country` + `exchange` listing metadata (PR-A1; schema `0.10.11→0.10.12`)
- PR #346 `9575d22` — chore(gitignore): ignore `impeccable` skill local artifacts
- PR #345 `983195b` — fix(frontend): `PillarRadarChart` mobile reflow (bar full-width on narrow viewports)
- PR #344 `b773bbf` — feat(frontend): `HeroAttributeTiles` 4-box grid (`lucide-react`; Size + Sector live, 2 reserved)
- PR #342 `fb74a7b` — feat(frontend): static `RecommendationBadge` + `HeroMetric` count-up client leaf
- PR #341 `4079ad2` — feat(frontend): price-chart 5Y → `aggregateMonthly()` (60 pts vs 260-pt daily downsample)
- PR #340 `e1b169b` — fix(frontend): detail reading-order — radar above warning group + revert hero veto chip
- PR #339 `2ade490` — fix(frontend): de-dup fair-price pair — drop `FairPriceCard` per-method table
- PR #338 `add85f4` — docs(gotchas): background-run hygiene (`Agent run_in_background` orphan + Bash zombie)
- PR #337 `abf1e17` — feat(frontend): `RiskSummaryCard` merge (RANK GATES vs MANIPULATION INDEX de-dup)
- PR #336 `5155caa` — chore(agents): `effort: max` on all 20 subagents + `check_model_pin.py` CI guard
- PR #335 `0b9add5` — fix(frontend): hero "N/100" · `MoSBadge` real % · fair-price chevron fix
- PR #334 `18c4507` — fix(frontend): nav chevrons + spacing + kill `RankingTable` mounting flash
- PR #333 `bd2c15d` — docs(gotchas): PR #332 hero invariants (container-query + sign-aware MoS)
- PR #332 `43838c6` — feat(frontend): stock-detail hero rework — sign-aware MoS · container-query split · drop price line
- PR #331 `3cb95eb` — feat(agents): add `financial-engineer` (20th subagent) + drain #311–#330 doc drift

**Earlier** (PR #303 → PR #330, 2026-05-29 → 2026-05-31):
- PR #330 `ba218ff` — feat(frontend): motion + price-chart polish (ONE `ease-in-out` + `max-width` transition)
- PR #329 `9ee1b32` — feat(frontend): price-chart intro sweep (line + crosshair draw left→right)
- PR #328 `c80b5e8` — fix(frontend): move brand to header when sidebar collapsed; chevron-only rail
- PR #327 `0303e9f` — docs: CLAUDE.md §Phase status drain (#311–#326) + 2 §Gotchas
- PR #326 `b82b845` — fix(frontend): sidebar refresh flash + crosshair debounce remount + pre-paint + 2 flaky-test guards
- PR #325 `732853c` — feat(frontend): fluid responsive scaling (clamp root font-size) + density audit
- PR #324 `6ca174f` — fix(frontend): tap moves crosshair to tap point
- PR #323 `4f7edf1` — fix(frontend): chart reference-line + chip polish + `overflow-x: clip` §Gotcha
- PR #322 `fd04527` — fix(frontend): price-chart crosshair full rework (park-at-latest · touch scrub · flush right)
- PR #321 `3640a8e` — fix(frontend): sidebar footer version chip v1.2 → v1.4.0
- PR #320 `22cd579` — fix(frontend): keep mobile sidebar drawer full when desktop collapsed pref is set
- PR #319 `a49f21c` — docs: fix stale skill-count (45 → 46) + LESSONS_LEARNED
- PR #318 `79c0aac` — docs: add `docs/LESSONS_LEARNED.md`
- PR #317 `fc886de` — fix(frontend): stack detail hero below `lg`
- PR #316 `89c5ee0` — docs(skill): add `web-animation-design` (skill count 45 → 46)
- PR #315 `aeca318` — fix(frontend): responsive + a11y audit (320px hero · focus rings · touch targets)
- PR #314 `a5e756b` — docs(frontend): fix stale `.gauge-arc` comment
- PR #313 `c5251f7` — fix(frontend): animation audit + play-every-visit + gauge keyframe sweep
- PR #312 `e602485` — feat(frontend): app-wide tasteful motion (gauge sweep · row stagger · veto pulse)
- PR #311 `10c6221` — docs: reconcile cross-doc drift after 6-PR session (#303–#310)
- PR #310 `a941e2e` — fix(scoring): inject `stale_filing_hard` before Top-5 rotation (latent Rule-16 fix, closes #309)
- PR #308 `e77efbf` — fix(frontend): RiskFlagsCard footer over-claim + `stale_filing_hard` key + "Risk Flags" header
- PR #307 `bb1d7fd` — feat(agents): Phase B — opus-4.8 orchestrator + `## Handoff` contract on 19 agents + Flow 7
- PR #306 `6ce7c1b` — fix(frontend): render `risk_flags[]` vetoes on stock detail (closes #305)
- PR #304 `e070db6` — feat(agents): add `expert-user-explorer` (19th subagent)
- PR #303 `847c21b` — feat(scoring): Phase 4.5e PR 6 — Form-4 10b5-1 negation guard (schema `0.10.10→0.10.11`)

**Earlier** (PR #286 → PR #302, 2026-05-28; **14 PRs landed same day post-v1.4.0 release**):
- PR #302 `c956f06a` — chore(valuation): PR #293 follow-up — Site-2 dead-code removal (`_has_corrupt_input` + `_data_quality_corrupt_result`; cron Run #71 retention gate confirmed clean; NET −56 prod lines / −84 test lines)
- PR #301 `978cab65` — chore(docs): end-of-day 2026-05-28 .md sweep — fix 8 MUST-FIX + 6 SHOULD-FIX cross-doc drifts (PHASE_STATUS.md schema row + SKILL.md table + WORKFLOW.md tag)
- PR #300 `5fa9a443` — feat(scoring): Issue #67 follow-up — per-sector `value_trap_risk` delta instrumentation (schema `0.10.9 → 0.10.10-phase4.6`; methodology-scientist Mode B Q2 verdict deferred from PR #294)
- PR #299 `3ec4b29e` — chore(docs): end-of-day housekeeping — drain 3 INFLIGHT markers + bump pointers (drains PR #295/#297/#298)
- PR #298 `030675e9` — fix(ci): Issue #288 follow-up — bump workflow cache key `cache-v4 → cache-v5` (closes the GOOG/GOOGL silent-failure gap; PR #292 Branch 3 fix code was correct but warm-cache replay short-circuited it; surfaced by PR #297 Rule 18 disambiguator)
- PR #297 `ecb60e64` — feat(perf): Issue #287 PR A — durable timeout + per-loop wall-clocks (schema `0.10.8 → 0.10.9-phase4.6`; `compute-rankings.yml` `timeout-minutes: 150 → 195` + cache-restore canary step; 4 new `Metadata.*_wall_clock_seconds` fields with 4 distinct defensive patterns; pre-push 3-reviewer gate green)
- PR #296 `e85dfbcf` — docs(context): add root `CONTEXT.md` pointer + reconcile `docs/agents/domain.md` (single-file orientation bridge for upstream tools expecting CONTEXT.md; multi-file analog remains canonical)
- PR #295 `2d2ec83e` — chore(docs): post-session-housekeeping — drain 6 INFLIGHT markers + bump pointers
- PR #294 `0ddb6b81` — feat(valuation): Issue #67 — flip `USE_SECTOR_COE = True` (Damodaran 2019 Ch. 8.4 11-sector Ke; methodology-scientist Mode B APPROVED; `value_trap_risk` 132 → 109 cohort drop, within target [80, 110] band)
- PR #293 `95e638bf` — fix(valuation): Issue #289 — retire Site-2 DQIC ceiling (NVR FP; methodology-scientist Option C; Site-1 + Defense #4 `extreme_*_estimate` + Issue #177 Huber-breakdown layer cover the remaining corruption + breakdown cases)
- PR #292 `e9aaab31` — fix(ingest): Issue #288 — GOOG/GOOGL XBRL concept-name omission (`market_cap` 2.2× inflated since PR #269; schema `0.10.7 → 0.10.8-phase4.6` for Rule 18 disambiguator)
- PR #291 `cb9114bb` — docs(agents): AGENTS.md substance refresh (production-verified run pointer cron #51 → cron #69; open-issues list 4 → 11 entries)
- PR #290 `dea8e3ad` — chore(cleanup): post-cron-#69 — BK orphan removal + 3 doc drifts (security-reviewer W1+W2 + edgartools 2.30 → 5.31)
- PR #286 `27361047` — chore(docs): housekeeping PR-B — drain INFLIGHT + bump pointers post-v1.4.0
- (3 issues filed: #287 FORM4 revert + durable 5-loop timeout · #288 GOOG/GOOGL XBRL · #289 NVR DQIC; all closed same day via PR #297 / #298 / #292 / #293)

**Earlier** (PR #264 → PR #285, 2026-05-26 → 2026-05-27):
- PR #285 `8f373758` — docs(release): codify mobile-only operator convention for tag releases (CLAUDE.md §Gotchas + release-tag SKILL.md + release-captain agent)
- PR #284 `a820caee` — fix(test): `test_compute_shift_live_repo_recent_window` resilient to shallow clones (CI `actions/checkout@v6` fetch-depth=1 default)
- PR #283 `bbca9cac` — chore(release): **v1.4.0-phase4.6** — Honest re-validation harness (`pyproject.toml` 1.3.0 → 1.4.0 + release notes)
- PR #282 `c7cdd881` — feat(validation): Phase 4.6 task #2f — `scripts/generate_honest_baseline.py` CLI + skeleton report with McLean-Pontiff 2016 32%-decay banner
- PR #281 `858e8666` — feat(validation): Phase 4.6 task #2c — `compute/validation/historical_ic.py` per-pillar Spearman IC orchestrator (rank-then-Pearson, no scipy dep)
- PR #280 `1ef962cd` — feat(validation): Phase 4.6 task #2b — `compute/validation/forward_returns.py` reader for gitignored price cache
- PR #279 `6a712e82` — feat(validation): Phase 4.6 task #2e — `compute/validation/manipulation_distribution.py` 3-band shift report
- PR #278 `e169aba6` — feat(validation): Phase 4.6 task #2a — `compute/validation/ranking_history.py` time-series loader (via git-archive)
- PR #277 `b70ea971` — feat(validation): Phase 4.6 task #2 — `compute/validation/universe_drift.py` harness
- PR #276 `7480734b` — feat(main): Phase 4.6 writer wiring — populate universe-provenance Metadata in forward cron
- PR #275 `78ab1d7d` — feat(validation): Phase 4.6 — wire `universe_provider` into pbo_dsr gates
- PR #274 `f2888844` — feat(universe): Phase 4.6 — survivorship-bias fix (historical S&P 500 membership per Hou-Xue-Zhang 2020 RFS)
- PR #273 `cfa1f709` — docs(research): calibration findings + 5 PLAN drafts from Research Report v1.0
- PR #272 `65649993` — docs(phase-5): outline PLAN.md for Supabase hybrid (sub-PR 5.0 scaffold)
- PR #271 `75b6c682` — docs(workflow): Agentic 6-Phase Cadence distilled into WORKFLOW.md + CLAUDE.md
- PR #270 `1bf5bb81` — chore(gitignore): ignore `graphify-out/` build artifacts
- PR #269 `5bf38c12` — feat(ingest): Issue #261 PR-B — per-class XBRL extraction (GOOG/GOOGL $4.6T overcount structural fix; `MULTI_CLASS_OVERCOUNT_ALLOWLIST` + filer-namespace `goog:CapitalClassCMember` gotcha; schema `0.10.5 → 0.10.6-phase4.5e`)
- PR #268 `f79548f0` — docs(skill): `good-code-bad-code-review` reference catalog (Miler/milerdev; skill count 44 → 45; REFERENCE-LINK posture, no vendored content)
- PR #267 `a70978af` — docs: Phase B post-v1.3.0 housekeeping (pointer backfill + drain 11 stale INFLIGHT markers)
- PR #266 `5db3b978` — chore(release): **v1.3.0-phase4.5e** — Form-4 insider clustering + LedgerCraft frontend
- PR #265 `e6013bae` — fix(scoring): Issue #262 — rename DQIC site-2 emission to `valuation_output_anomalous` + writer-parity for veto cohort UI explainability
- PR #264 `d9c62292` — feat(scoring): Issue #261 PR-A — `multi_class_aggregate_shares_suspected` annotate (CIK-collision detector; schema `0.10.4 → 0.10.5-phase4.5e`; flags 32 → 33 declared)

**Earlier** (PR #170 → PR #237, 2026-05-21 → 2026-05-24):
- PR #237 `1ff6c114` — docs: PHASE_STATUS_INFLIGHT.md side-file to break parallel-PR collision pattern
- PR #236 `08d75636` — feat(frontend): B2+B3+B4 combined — full LedgerCraft alignment series complete (10 files)
- PR #235 `2b588c83` — feat(frontend): B1 score-tier palette restraint (teal/orange → emerald/amber)
- PR #234 `1a9501c0` — feat(frontend): A3 LedgerCraft table + frame polish
- PR #233 `dc615aeb` — feat(frontend): A2 LedgerCraft chip-family squaring (`rounded-full` → `rounded-sm`)
- PR #232 `5517b983` — feat(frontend): A1 LedgerCraft sector-chip neutralization (`SECTOR_COLORS` → neutral steel)
- PR #230 `4c0d92f5` — docs(form4)+ci(simulate): correct `<rule10b5_1>` → `<aff10b5One>` + permanent 45-min simulate fix
- PR #229 `dacf293b` — security(W2+W4): workflow-perm narrowing + log-bash secret scrub
- PR #228 `b5ff8cc1` — feat(agents): explicit MCP-tools listing for `vercel-preview-auditor` + `ci-triage-engineer`
- PR #227 `105d79ec` — test(form4_signals): PR-#224 review-nit polish (2 of 3 quantrank-reviewer WARNs)
- PR #226 `d67e1051` — docs+agent: post-Dependabot-wave doc fixes (W1 FORM4_FETCH_SKIP + W3 injection guard)
- PR #225 `2b343bb0` — feat(agents): add `ci-triage-engineer` + `vercel-preview-auditor` + `literature-searcher` (15 → 18)
- PR #224 `98e761ef` — feat(scoring): Phase 4.5e PR 4-eq — Form-4 10b5-1 contamination filter (`0.10.1 → 0.10.2-phase4.5e`)
- PR #223 `23ce42f1` — feat(orchestrator): delegate-first identity + `UserPromptSubmit` hook + patterns table
- PR #222 `79bb5aec` — feat(scoring): Phase 4.5e PR 3 — `insider_sell_cluster` + `c_suite_unusual_sell` annotates (`0.10.0 → 0.10.1-phase4.5e`; flags 30 → 32)
- PR #221 `eba0fde8` — feat(verify+auditor): OSAP proxy contract codification, Section L helper (closes #217 + #218)
- PR #220 `92265167` — fix(ingest): DD `eps_diluted` TTM derivation + STZ fallback logger.warning
- PR #219 `ef256ddd` — chore(agents): reset sonnet sub-agent thoroughness — lift artificial spawn caps
- PR #216–#215–#213–#212–#211 — feat(frontend): LedgerCraft Phase 3b dark mode + 3c sidebar + 3a spreadsheet polish + Phase 1 + 2 token adoption
- PR #210 `0f552ba1` — fix(form4): handle edgartools 5.x `Filing.obj` as method (P0 silent-drop hotfix)
- PR #205 `e8823e07` — feat(form4): Phase 4.5e PR 2 — `Metadata.form4_*` observability surface (`0.9.8 → 0.10.0-phase4.5e`, MINOR)
- PR #204 — feat(scoring): sector-keyed cost_of_equity behind config flag, 3 Rule 18 `Metadata` fields (`0.9.7 → 0.9.8-phase4h.8`; closes #67 prep)
- PR #203 `278da499` — feat(skills): cross-session branch-collision detector (closes #125 item 6; skill count 42 → 43)
- PR #201 `54092fa2` — chore(ci): add `tailwindcss` to dependabot ignore (blocks v4 engine-rewrite major)
- PR #195 `8c22cee9` — chore(ci): extend dependabot ignore list — block `eslint`/`typescript`/`recharts`/`eslint-config-next` majors
- PR #194 `72f8a33c` — chore(deps-npm): bump next `14.2.15 → 14.2.35` + postcss override (closes 8 advisories, partial #41)
- PR #185 `cfcbe407` — chore(ci): add `.github/dependabot.yml` — weekly dep updates for 3 ecosystems
- PR #184 `83b942d0` — docs(methodology): refresh annotate section 10 → 18 bullets (Phase 2.x)
- PR #183 `b881d544` — feat(defense): add `extreme_estimate_majority` annotate, schema `0.9.7-phase4h.7`; flags 29 → 30
- PR #182 `a6129011` — fix(ingest): per-filing XBRL fallback recovers STZ-style dimensional `shares_outstanding` (closes #176)
- PR #181 `998cd530` — feat(defense): add `share_count_extraction_missing` annotate, schema `0.9.6-phase4h.6`; flags 28 → 29
- PR #180 `a24a57d4` — feat(defense): add `loss_avoidance_pattern_size_invariant` annotate, schema `0.9.5-phase4h.5`; flags 27 → 28
- PR #179 — fix(main): defer OSAP imports to unblock `test_main` collection in base-install (Phase 4a)
- PR #178 `7ac4ac3f` — chore(agents): trim 6 largest agent prompts 2925 → 2525 lines (−13.7%)
- PR #175 `ebcd4918` — feat(agents): lean auto-routing policy + 15th agent `stock-detail-auditor`
- PR #172 `e9acaca7` — fix(frontend): 6 `frontend-design-reviewer` FAILs — palette + loose-null + chip family
- PR #171 `842f68dd` — docs: Phase 2 doc-drift reconcile — 5 files match current implementation
- PR #170 — Phase 1 ops hardening: `compute-monthly.yml` perm + EDGAR_MAX_WORKERS doc + going-concern FP stat

**Closed next-deliverables entries (relocated):**

1. **Phase 7.0c — PIT veto-layer replay** (**PROMOTED to top**) — replay the 7 active vetoes inside `scripts/backfill_portfolio_pit.py` (flip `veto_layer_replayed` False → True) + one backfill dispatch. The cheapest highest-information experiment left: the shipped 10Y backtest shows the RAW composite underperforming SPX at every N=1-10, so "does the defense layer rescue the signal?" must be answered BEFORE Phase 5's ~10-12w ML track is funded. The recorded verdict is **Phase 5 entry gate (a)**.
2. **Issue #441 — DONE (closed by the MAD close-out PR #449, 2026-06-10)** — the pre-registered acceptance gate FAILED on the first real cron (`mad_mom12_corr` 0.834 / `mad_mom3_corr` 0.807 ≫ |ρ| < 0.30 at 99.6% coverage → momentum echo; methodology-scientist RATIFY-REMOVE, one cron decision-grade at ~20 SE). MAD (`mad_scalefree` + diagnostics) removed AND the dead `macd_hist` pillar slot deleted with it (schema `0.10.17`) — the `isinstance(macd, dict)` check on a float return made it always-NaN/skipna-dropped, so the technical pillar was already (and is now honestly) a 4-metric mean. The MAD PR-2 wiring + its IC-baseline rationale are moot; no 5th technical input without a fresh pre-registration (short-term reversal Jegadeesh 1990 / idio-vol Ang-Hodrick-Xing-Zhang 2006 are the screened candidates).

**Drained Current-state table prose (schema lineage / patches / run baseline):**

| Schema | **`0.10.17-phase4.6`** (current on `main` — issue #441 close-out: the 3 `Metadata.mad_*` MAD-factor diagnostics REMOVED after the pre-registered acceptance gate FAILED on the first real cron (`mad_mom12_corr` 0.834 / `mad_mom3_corr` 0.807 ≫ |ρ| < 0.30 → momentum echo; methodology-scientist RATIFY-REMOVE) + the dead `macd_hist` pillar slot deleted (technical pillar now an honest 4-metric mean). Prior `0.10.16` #447 issue-#441 PR-1 added those 3 diagnostics feeding the now-closed PR-2 wiring gate; prior `0.10.15` #426 Phase 4j.1 added 9 `Metadata.alpha158_*` Qlib observability fields; #416 added `Metadata.benchmark_coverage_pct` (`0.10.14`). Prior **`0.10.13-phase4.6`** — PATCH bump: listing-metadata canary `Metadata.country_coverage_pct: float | None` + CBOE `BTS → Cboe BZX` fix in `cross_source._EXCHANGE_NAME_BY_CODE`. The 2026-06-02 post-cron audit disproved the 0.10.12 "country tracks exchange 1:1" assumption — exchange passes unknown codes through as covered while country resolves only known US codes, so they diverge on a raw passthrough (CBOE's `BTS`: exchange 100% / country 99.8%). Prior: PR #303 merged 2026-05-29 `847c21b` — `0.10.12-phase4.6` Phase 4.5e PR 6 Form-4 10b5-1 negation guard; supersedes PR #300's `0.10.10` per-sector delta + PR #297's `0.10.9` wall-clocks + PR #292's `0.10.8` Rule 18 disambiguator.) |
| Post-tag production patches | PR #292 (`e9aaab31`, schema `0.10.7 → 0.10.8-phase4.6`, GOOG/GOOGL XBRL fix) · PR #293 (`95e638bf`, Site-2 DQIC retirement, NVR FP) · PR #294 (`0ddb6b81`, sector-CoE flip `USE_SECTOR_COE = True`, Issue #67 closure) · PR #295 (`2d2ec83e`, post-session housekeeping drain 6 INFLIGHT + pointer bumps) · PR #296 (`e85dfbcf`, add root CONTEXT.md pointer + reconcile `docs/agents/domain.md`) · PR #297 (`ecb60e64`, schema `0.10.8 → 0.10.9-phase4.6`, Issue #287 PR A durable timeout + 4 `*_wall_clock_seconds` fields) · PR #298 (`030675e9`, cache-key `v4 → v5` to flush stale parquet so PR #292 GOOG/GOOGL fix actually fires; closes Issue #288 silent-failure gap) · PR #299 (`3ec4b29e`, end-of-day INFLIGHT drain of #295/#297/#298) · PR #300 (`5fa9a443`, schema `0.10.9 → 0.10.10-phase4.6`, Issue #67 follow-up per-sector delta) · PR #301 (`978cab65`, end-of-day .md sweep — 8 MUST-FIX + 6 SHOULD-FIX cross-doc drifts) · PR #302 (`c956f06a`, PR #293 follow-up Site-2 dead-code removal — `_has_corrupt_input` + `_data_quality_corrupt_result` removed after cron Run #71 confirmed clean) |
| Production run | `368dccd9` (2026-05-28 cron Run #71, 14m 32s warm cache, post-PR #298 cache-v5 bump; empirically validated PR #297 wall-clock fields — `tier2_wc=10.6s`, `form4_wc=null` per FORM4_FETCH_SKIP, `osap_wc=347.1s`, `cross_source_wc=133.2s`. Smoking gun for Issue #288 cache-replay bypass: `multi_class_per_class_attempt_count=0` + `fundamentals_latency_p50_seconds=0.0`) |


**Tooling note (2026-05-17, post-v1.2)**: Claude Code MCP connectors
added for Vercel + Supabase + Sentry (Sentry SDK wiring deferred to
Phase 5+ onboarding). Section I verification ladder updated in
`.claude/skills/verify-production-output/SKILL.md` to use Vercel MCP
as first-line deploy-health check before the 4-ticker Playwright
matrix. See `CLAUDE.md` §Connectors for the registered table.

**Earlier phase history below** — keep this header section under
20 lines and let the per-phase blocks own the detail.

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

- ✅ **4g — Re-enable 8-K Tier-2 event defenses** (PR #79, merged
  2026-05-15 on commit `c35c6d40`). Closes
  [issue #14](https://github.com/dackclup/quantrank/issues/14).
  Flipped `compute/scoring/tier2._EIGHT_K_DEFENSES_ENABLED = True`
  after the PR 3d workflow-timeout deferral (root cause cleared by
  PR #58 cache layers + PR 3d Part 1 tenacity tightening).
  `non_reliance_filing` (Item 4.02 hard veto, 365d lookback,
  Schroeder 2024 SSRN — ~50% of 4.02 filings precede formal
  restatement) returns to the active layer as the **5th active
  veto**. `auditor_change` (Item 4.01 annotate, 730d lookback, Reg
  S-K Item 304, Cohen-Malloy-Nguyen 2020 type) joins the Tier-2
  annotate surface. Schema bump `0.6.0-phase3d` → `0.7.0-phase4g`.
  Subsequent additive `price_change_1d_pct` field on
  `StockSummary` + `StockDetail` bumped `SCHEMA_VERSION` constant
  to `0.7.1-phase4g` (production metadata still on `0.7.0` until
  next weekly compute).

### PR 4b status (mostly shipped — issue #75 partially closed)

**The bulk of PR 4b landed in PR #60 (2026-05-14, pre-v1.0 — tag
target was `v1.0.2-defense`); the §3 IC-decay production wiring + the
`/analysis` transparency surface landed 2026-06-13 (observability-first,
issue #75 §3).** All 8 acceptance criteria on issue #75 are now
satisfied — the issue is closed by that PR.

| Sub-section | Status | Module | Notes |
|---|---|---|---|
| **§1 Cross-source validator** | ✅ **DONE** (PR #60) | `compute/ingest/cross_source.py` | SEC-derived market cap vs yfinance `.info` with 5% tolerance per `config.CROSS_SOURCE_MARKET_CAP_TOLERANCE`. Wired into `compute/main.py` per-ticker loop after Beneish + Dechow. **Production verification (run #45, 2026-05-16)**: 23/502 tickers flagging `cross_source_disagreement` = 4.6%, within the < 5% sanity bound. Cache at `compute/cache/yfinance_info/` with 24h TTL. |
| **§2 PBO + DSR library** | ✅ **DONE** (PR #60) | `compute/validation/pbo_dsr.py` | Bailey-Borwein-Lopez de Prado-Zhu 2014 CSCV (S=8 or 16) + Bailey-LdP DSR. Pure-numpy reimpl (avoids `mlfinlab` commercial license + 50MB scipy install). Beasley-Springer-Moro 1990 inverse normal CDF + hand-rolled sample skew/kurtosis. Property/behavioral tests anchor the numerics per PLAN §2's acceptance gate: pure-noise returns → PBO ∈ (0.30, 0.70) (Bailey-Borwein-LdP-Zhu 2014 §3.3), strong-signal returns → PBO < 0.45, and the BSM inverse-normal-CDF verified against a reference within 1e-3 — **not** a Bailey-2014 Table-1 golden fixture (Table 1 reports CSCV distributions, not a single reproducible PBO scalar; the earlier "Table 1 within 5%" claim here was inaccurate, corrected in this PR). Entry point `factor_passes_gates()` ready for 4h/4i/4j/4k to call at signal-acceptance time. |
| **§3 IC-decay monitor** | ✅ **DONE** (wired 2026-06-13, observability-first) | `compute/validation/ic_decay.py` | Rolling 12m + 36m IC per pillar + 50%-drop / 6-month sustained-alert logic (McLean-Pontiff 2016). Now production-wired: `build_decay_report` walks `historical_ic` (bounded 39-mo) → calendar-month panel → `check_all_pillars` → `emit_decay_report` → `frontend/public/data/decay_report.json` every cron (skip-safe `QR_SKIP_DECAY_MONITOR`, try/except graceful-degrade), surfaced via schema-additive `Metadata.decay_report_url` on the `/analysis` page (honest 3-state UI). `alert` SUPPRESSED until ≥12 monthly IC points/pillar (`preliminary`), so the current `status="insufficient_history"` shows "accumulating baseline", not a fake all-clear. Monitor-only — NEVER vetoes / changes scores. NOTE: the cron checks out shallow (`fetch-depth: 1`), so the git-walk sees only the tip commit and the report stays `insufficient_history` until the checkout is deepened (follow-up #478); Phase 5's walk-forward panel is the longer-term densification source. |

**Next deliverable**: With PR 4b §1+§2+§3 all ✅ (issue #75 closed),
the live tracks are:

1. **4h / 4i / 4j / 4k factor integrations** (OSAP / JKP / Qlib /
   IPCA) — each gated by the now-complete `pbo_dsr.factor_passes_
   gates()` harness. Sequencing per
   `v1-to-v1-1-migration/PLAN.md`. Tag `v1.1.0-phase4` after all
   four merge.
2. **Phase 4.5a.1 — sector-relative Sloan** (folds in
   [issue #7](https://github.com/dackclup/quantrank/issues/7)).
   Replaces cross-sectional top-decile Sloan veto with a within-
   GICS-sector top-decile gate. Removes the known over-fire on
   Financials + REITs whose non-cash earnings are structural,
   not manipulative. ~80 LOC + AAER backtest. **First sub-PR
   of the Phase 4.5 manipulation-defense cluster** (see §"Phase
   4.5 plan" below for the full 4.5a-4.5f roadmap).

These two tracks run in parallel — they touch disjoint code
paths (`compute/scoring/` for 4.5a.1, `compute/ingest/factors/`
for 4h-4k) and share the PR 4b §2 PBO/DSR gate.

**Phase 4.5 (manipulation-defense cluster, v1.2 target) follows
v1.1.0 and runs in parallel where the touched files are
disjoint — see "Phase 4.5 plan" section below.**

## Phase 4.5 plan — Earnings-Manipulation Defense Cluster (v1.2)

After PR 4b lands the validation infrastructure (PBO/DSR backtest
gate + IC-decay monitor + AAER cohort fixtures), the next research
priority is hardening QuantRank's earnings-manipulation defense.
The v1.0 + 4g layer covers **5 active vetoes + 2 Tier-2 annotates +
2 Tier-3 forensic models** — strong on Sloan accruals + 8-K
disclosure events, weaker on Real Earnings Management, restatement
history, insider signals, and earnings-quality time-series.

Each sub-PR is validated against the **SEC AAER 2000-2024 cohort**
(~600 confirmed manipulators per Dechow et al. 2011 dataset +
ongoing) via the PR 4b PBO/DSR harness. **PBO ≤ 0.5 AND DSR > 0
required to accept**; reject any flag that fails. Each
sub-PR also runs against the Audit Analytics free-tier
restatement subset (~1,200 firms 2000-2024) for second-source
validation.

### 4.5a — Manipulation quick wins ✅ **DONE 2026-05-16** (+2 active veto + 1 badge)

**3 sub-PRs all merged**: 4.5a.1 (PR #89) + 4.5a.2 (PR #90) + 4.5a.3
(PR #91). Production-verified on run #47 (commit `8cdf4886`):

| Sub-PR | Delivered | Production effect (run #47) |
|---|---|---|
| **4.5a.1** | Sloan accruals top-decile **within sector** (closes [issue #7](https://github.com/dackclup/quantrank/issues/7)). `SLOAN_MIN_POPULATION_SECTOR=15` floor; cross-sectional fallback for under-floor sectors. | Financials Sloan rate **21.3% → 11.7%** (Δ −9.6pp). Cross-sector spread **7.7× → 1.4×**. Total Sloan flagged 51 → 56 (under-firing sectors now correctly at ~10%). |
| **4.5a.2** | `beneish_manipulation_veto` active-veto path at `BENEISH_VETO_THRESHOLD = -1.78` (Beneish 1999 Table 4 PPV crossover). Existing `beneish_high` annotate at M > −2.22 unchanged. | **11 new active-veto tickers**: SMCI · WAT · PODD · WDC · NVDA · CAT · PLTR · SNDK · BG · STX · LLY. |
| **4.5a.3** | `dechow_manipulation_veto` active-veto path at `DECHOW_VETO_THRESHOLD = 3.0` (Dechow 2011 Table 7 4× baseline crossover). + `manipulation_triple_flag` joint-gate annotate when Sloan + Beneish-high + Dechow-high co-fire. | **1 Dechow veto**: SMCI (F=6.65). **2 triple_flag tickers**: SMCI + WAT. SMCI carries the triple-stack (Sloan + Beneish + Dechow). |

**End-state defense layer**: 9 → **11 layers** (5 → 7 active vetoes;
4 → 5 annotate flags). Tier-3 forensic count unchanged (still 2 —
Beneish + Dechow operating at two thresholds each). Reason
taxonomy: 24 stable + 2 Tier-3 + 2 new veto IDs + 1 new joint flag
= **29 stable identifiers**.

**No schema delta** — all new flag identifiers are strings in
existing `risk_flags: list[str]` + `valuation_warnings: list[str]`
arrays. `SCHEMA_VERSION` stays `0.7.1-phase4g`.

References: Sloan 1996 *TAR*, Beneish 1999 *FAJ*, Dechow et al.
2011 *CAR*.

### 4.5a — Manipulation quick wins (original plan, kept below for reference)

⏬ Original plan text below — execution captured in the table above. ⏬

- **Sector-relative Sloan** — top-decile within GICS sector instead
  of cross-sectional. Closes [issue #7](https://github.com/dackclup/quantrank/issues/7).
  Removes the known over-fire on Financials + REITs whose non-cash
  earnings are structural (not manipulative).
- **Beneish soft-veto** — promote `beneish_high` from annotate to
  active veto when M > −1.78 (tighter than the existing −2.22
  annotate threshold). Original annotate flag stays for the −2.22
  to −1.78 band.
- **Dechow soft-veto** — same pattern for F > 3.0 (was annotate at
  F > 2.45).
- **`manipulation_triple_flag` badge** — joint gate that fires only
  when Beneish + Sloan + Dechow flag simultaneously. Rare, high-
  confidence. UI-only badge, doesn't suppress Top-N on top of the
  individual vetoes already doing that.

References: Sloan 1996 *TAR*, Beneish 1999 *FAJ*, Dechow et al.
2011 *CAR*. Effort: ~180 LOC + AAER backtest, 3 sub-PRs (`4.5a.1` /
`4.5a.2` / `4.5a.3`) that ship in parallel.

### 4.5b — Disclosure-driven catches ✅ **DONE 2026-05-16** (+2 annotate)

**PR #93 merged**. Production-verified run #48 (commit `849b7ca8`,
workflow 2h08m cold-cache populating the new `edgar_amendments`
+ `edgar_late_filings` dirs):

| Flag | Lookback | Production fire | Tickers (sample) |
|---|---|---|---|
| **`restatement_history`** | 5y 10-K/A + 10-Q/A | **60 / 502 (12.0%)** — within expected 6-16% | AMD · DIS · CVX · BSX · EBAY · ELV · AON · DASH · DVN · ALB · APTV · AXON · BLDR · ADM · AES · AMP · CPAY · CNP · CRH · COHR + 40 more (large mature firms, mostly amendments for standard adoption / segment reclassification) |
| **`late_filing_notification`** | 365d Form 12b-25 (NT 10-K + NT 10-Q) | **2 / 502 (0.4%)** — slightly under expected 1-4% | HAS (Hasbro) · Q |

New module `compute/scoring/restatement_filings.py` (~390 LOC) +
17 offline tests (~270 LOC) + 2 new cache dirs (7d TTL, mirrors
8-K pattern) + workflow YAML cache paths. Per-CIK JSON cache
shape: `{fetched_at, lookback_days, filings: [{accession, form,
filing_date, filing_url}]}`. Workflow time impact: cold cache run
2h08m (was 1h30m); warm runs return to ~1h30m once both caches
populate.

References: Hennes-Leone-Miller 2008 *TAR*, Bartov-Lai-Yeung 2002
*JAR*. Both flags **ANNOTATE-only** — base rates sector-agnostic
but moderate, no veto without sector adjustment.

### 4.5b — Disclosure-driven catches (original plan, kept below for reference)

⏬ Original plan text below — execution captured in the table above. ⏬

Both use existing SEC EDGAR access, no new fetch surface. Effort:
~270 LOC + tests, ~7 days.

### 4.5c — Real Earnings Management ✅ **DONE 2026-05-17** (PR #95, +1 annotate)

**Shipped**: `rem_suspect` annotate via per-sector OLS regressions on
3 abnormal proxies (CFO, Production, Discretionary Expenses).
Production verified run #49 (commit `65097703`, warm-cache 6m25s):

| Metric | Value |
|---|---|
| Fire rate | **16 / 502 (3.2%)** — within H0-to-correlation expected 2.8-7% |
| Tickers fired | SMCI · WAT · ADM · TSN · HRL · STLD · FSLR · JBL · COHR · LII · LDOS · POOL · OMC · WY · TECH · RVTY |
| Orthogonality check | NVDA / PLTR (Beneish-veto fired) **NOT** in REM list — confirms 4.5c captures real-manipulation signal orthogonal to accrual targets |
| Real-world coverage | ADM (2024 SEC investigation) · SMCI (2024 investigation) · TSN / HRL (periodic accounting scrutiny) · FSLR (solar channel-stuffing history) |

Module: `compute/scoring/rem.py` (~420 LOC, pure-numpy OLS via
`np.linalg.lstsq`, no sklearn/statsmodels dep). 14 offline tests
including golden numerical test recovering known-DGP coefficients
from a 30-ticker synthetic panel. `REM_MIN_POPULATION_SECTOR = 15`
floor (matches 4.5a.1 Sloan). DISEXP simplification: omits
Advertising (rarely XBRL-tagged), uses `R&D + SGA` per Roychowdhury
2006 footnote 7.

References: Roychowdhury 2006 *JAE* 42(3), 335-370.

### 4.5c — Real Earnings Management (original plan, kept below for reference)

⏬ Original plan text below — execution captured in the table above. ⏬

Beneish + Dechow + Sloan all target *accrual* manipulation. **Real**
manipulation — cutting R&D, channel stuffing, deferring
maintenance, manipulating production schedules — is invisible to
those models.

Roychowdhury 2006 *JAE* (REM): three abnormal proxies per ticker,
each modelled against sector-industry quintile baselines:

- `abnormal_CFO` = actual − model(Sales, ΔSales)
- `abnormal_production` = actual − model(Sales, ΔSales, ΔSales_t−1)
- `abnormal_discretionary_expenses` = actual − model(Sales_t−1)

Flag `rem_suspect` fires if **2 of 3 proxies sit in the worst decile
within sector**. Uses XBRL data already in cache (no new fetches).
Effort: ~250 LOC + sector-relative thresholds + golden tests
against Roychowdhury paper Table 6, ~10 days.

### 4.5d — Earnings-quality time-series ✅ **DONE 2026-05-17** (PR #97, +2 annotate)

**Shipped**: 2 annotate-only flags derived from per-ticker fundamentals
history. Production verified run #50 (commit `c3b29af4`, workflow run
`25982432928`, warm-cache **6m24s**):

| Flag | Production fire | Expected | Status |
|---|---|---|---|
| **`accruals_momentum_high`** | **50 / 502 (10.0%)** | 3-8% | ⚠️ slightly hot — Δ(TATA) > +0.05 over trailing 3y; the 0.05 threshold (calibrated from Beneish 1999 β_TATA = 4.679 ⇒ ΔM > 0.5 ⇔ ΔTATA > 0.107, halved as the standard practitioner adaptation when shortening to one ratio) is loose enough to catch some normal-cycle noise. Within acceptable annotate-only band. |
| **`loss_avoidance_pattern`** | **0 / 502 (0.0%)** | 1-3% | ⚠️ universe mismatch — Burgstahler-Dichev 1997 *JAE* cohort thresholds (NI ∈ [$0, $5M] OR EPS ∈ [$0.00, $0.05] for 3+ consecutive years) are too tight for the S&P 500 large-cap universe. Smallest constituent NI > $5M; smallest EPS > $0.05. Filed as Phase 4.5 follow-up — consider S&P-500-scaled thresholds (NI ≤ $25M / EPS ≤ $0.25) or accept zero-fire as `entered_top5` floor-only guard. |

**Module**: `compute/scoring/earnings_quality.py` (~250 LOC,
`AccrualsMomentumResult` + `LossAvoidanceResult` dataclasses +
`check_accruals_momentum` + `check_loss_avoidance` + 2 helpers).
**Tests**: 13 offline (total suite now **831 offline + 17 @network**,
was 818 after 4.5c). No new ingest — both flags read from existing
`compute/ingest/fundamentals.py` annual history. No new cache dirs.

**Design substitution**: Original 4.5d plan called for
`m_score_deteriorating` (Δ(Beneish M) > +0.5 over 3y). Substituted
**`accruals_momentum_high`** (Δ(TATA) > +0.05 over 3y) as a
practical equivalent — TATA is the only Beneish component that's a
level (not a ratio of ratios) and Sloan 1996 established it as the
standalone accruals signal. Avoids the bookkeeping cost of building
3 historical 8-ratio Beneish snapshots from XBRL history that often
has gaps for prior years.

References: Sloan 1996 *TAR* 71(3), 289-315; Burgstahler-Dichev
1997 *JAE* 24(1), 99-126; Beneish 1999 *FAJ*.

### 4.5d — Earnings-quality time-series + Burgstahler kink (original plan, kept below for reference)

⏬ Original plan text below — execution captured in the block above. ⏬

- **`m_score_deteriorating`** — Δ(Beneish M-score) > +0.5 over
  trailing 3y = manipulation gathering steam. Snapshot M-score
  today misses the trajectory entirely.
- **`loss_avoidance_pattern`** — Burgstahler-Dichev 1997 *JAE* kink
  at zero. Firms reporting tiny-positive earnings (NI ∈ [0, $5M]
  OR EPS ∈ [0, $0.05]) for **3+ consecutive years** = avoiding
  loss thresholds, classical manipulation pattern.

Effort: ~180 LOC + 3-year history requirement (already on disk
post-PR 4f 5y daily ingest), ~7 days.

### 4.5e — SEC Form 4 insider clustering (~3 weeks, +2 annotate)

Cohen-Malloy-Pomorski 2012 *RFS* — cluster of insider sells before
bad news has 7-10% abnormal return predictive power.

- **`insider_sell_cluster`** — 3+ insiders selling within 30d
  before next earnings announcement.
- **`c_suite_unusual_sell`** — CEO/CFO selling > 5x annual comp
  within 90d (comp sourced from DEF 14A — Phase 4.5e or
  deferred to Phase 5/6 if DEF 14A parser unavailable; fallback
  uses prior-year total transaction volume as comp proxy).

New Form 4 parser needed (no existing ingest); touches a new SEC
form class so the ingest layer needs minor refactoring. Effort:
~300 LOC parser + ~120 LOC clustering detector + tests, ~12 days.

### 4.5f — Manipulation Composite + composite penalty + UI ✅ **DONE 2026-05-17** (PR #100, +1 annotate + 5 schema fields + 1 UI surface)

**Shipped**: 0-100 manipulation rollup + soft composite penalty + new
detail-page card. Production verified run #51 (commit `e57f09cb`,
workflow `25983422610`, warm-cache **5m14s**):

| Field | Value |
|---|---|
| Schema | **`0.8.0-phase4.5f`** (bumped from `0.7.1-phase4g`) |
| `manipulation_index` populated | 502/502 (100%) |
| Card fires (`manipulation_index > 0`) | **158/502 (31.5%)** |
| HIGH band (≥ 50) | 2 (SMCI=84 · WAT=64) |
| MODERATE (20-50) | 60 |
| LOW (0-20) | 96 |
| Max penalty observed | 8.40 pts (SMCI: 50.36 → 41.96) |
| Fundamentals p95 | 14.7s (improved from 18.72s in run #50) |

**Module**: `compute/scoring/manipulation_index.py` (~250 LOC, three
pure functions: `compute_manipulation_index` + `compute_adjusted_composite`
+ `manipulation_components`). Tests: 25 new offline (suite **831 →
856 + 17 @network**). Weight table additive; **Phase 4.5e flags
declared as reserved-slot constants** (`INSIDER_SELL_CLUSTER_WEIGHT_RESERVED`
+ `C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED`) so the 4.5e PR is a
one-line uncomment + entry addition in `FLAG_WEIGHTS`, no calibration
cascade.

**Schema fields added** (additive optional):
- `StockSummary.manipulation_index: float | None`
- `StockSummary.composite_score_adjusted: float | None`
- `StockDetail.manipulation_index: float | None`
- `StockDetail.composite_score_adjusted: float | None`
- `StockDetail.manipulation_components: dict[str, bool] | None`

**Rank-source contract**: rank stays the **raw** `composite_score`
per SKILL.md Rule 16 ("composite rank unchanged"). `composite_score_adjusted`
is informational only — surfaced on the new `ManipulationRiskCard`
detail-page surface with the in-line qualifier "Composite penalty:
−X.XX pts (informational; rank uses raw composite)". Penalize-the-rank
flips can re-open in Phase 5 once walk-forward backtest IC evidence
is in.

**Frontend** (`frontend/components/ManipulationRiskCard.tsx`):
3-band outlined-light chip family (emerald LOW · amber MODERATE ·
rose HIGH), per-flag drill-down with human labels + `[raw_flag_id]`
in mono. Card returns null when `manipulation_index == null || <= 0`
(`== null` catches both legacy-data `undefined` + explicit `null`).

**Live UI spot-check** (new Section I per verify-production-output
SKILL.md update this same wave): 4 tickers via Playwright against
`https://quantrank.vercel.app`. SMCI rendered 84/100 rose-tint with
all 7 components; WAT 64/100 rose with 6; NVDA 48/100 amber with 4;
CF (rank #1) 3/100 emerald with 1 (`beneish_high`). Visual hierarchy,
penalty text, and the in-line rank-contract qualifier all confirmed
in production rendering — no design-system regressions vs the
existing Tier2EventCard / FairPriceCard rhythm.

References: SKILL.md Rule 16 (annotate-and-veto-Top-N), Beneish-Vorst
2021 (FP-rate motivation for keeping penalty informational only).

### 4.5f — Manipulation Composite + composite penalty + UI (original plan, kept below for reference)

⏬ Original plan text below — execution captured in the block above. ⏬

Roll up 4.5a-4.5e into a single 0-100 **`manipulation_index`** and
wire it as:

1. **`StockDetail.manipulation_index`** schema field (additive,
   patch bump within v0.x → 0.8.0-phase4.5f)
2. **Composite-score penalty** —
   `composite_score_adjusted = composite_score − 0.5 ×
   (manipulation_index / 100) × 20`
   so a max-100 manipulation index removes **10 composite points**
   from the displayed score (current `composite_score` field
   preserved untouched for the audit trail per SKILL.md Rule 9).
3. **UI Manipulation pillar card** on detail page — same visual
   weight as the existing 8-pillar radar chart entries.
4. **README "Honest Limitations"** update covering the new
   defenses and what they still miss (pre-disclosure sophisticated
   fraud, off-balance-sheet SPEs, working-paper-level audit data).

Schema bump 0.7.x → **0.8.0-phase4.5f**. Effort: ~250 LOC + UI +
schema-snapshot regen, ~5 days.

### Phase 4.5 timeline summary

| Sub-PR | Effort | New flags | Status |
|---|---|---|---|
| 4.5a | 1-2w | +2 veto / +1 badge | ✅ DONE 2026-05-16 |
| 4.5b | 1w | +2 annotate | ✅ DONE 2026-05-16 |
| 4.5c | 2w | +1 annotate (sector-relative) | ✅ DONE 2026-05-17 |
| 4.5d | 2w | +2 annotate | ✅ DONE 2026-05-17 |
| 4.5e | 3w | +2 annotate (new Form 4 parser) | ⚪ (deferred — runs after v1.2.0 ships) |
| 4.5f | 1w | composite penalty + UI + schema bump | ✅ DONE 2026-05-17 |

Total: **~10-11 working weeks** for 4.5a-4.5f. Combined with PR 4b
(6 weeks) the manipulation-defense + validation-infra cluster
runs **~16-17 weeks** end-to-end.

**Defense layer after 4.5**: **7 active vetoes + 8 annotate flags +
3 forensic models = 18 layers** (was 9 after 4g).

**Tag plan**: `v1.2.0-phase4.5` after 4.5f ships.

**Sequencing**: PR 4b → 4.5a + 4.5b + 4.5c in parallel → 4.5d →
4.5e → 4.5f → tag. **Factor integrations (4h/4i/4j/4k) can ship
in parallel with 4.5** — they touch disjoint code paths and use
the same PR 4b PBO/DSR harness as their gate.

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
