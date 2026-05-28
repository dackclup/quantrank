---
name: quantrank-app
description: Build, modify, or extend QuantRank — a static-site US equity ranking application that combines fundamental, technical, factor, sentiment, and ML analysis into a 0-100 composite StockRank with ensemble fair price. Architecture is GITHUB-ACTIONS-FIRST (no backend server, no database) — Python script computes scores weekly and outputs JSON files; Next.js static site reads JSON and renders the UI; everything deploys free via Vercel. Roadmap is OPTION B (research-backed) with Option A as fallback. Use when the user wants to create QuantRank from scratch, add new analysis pillars or metrics, improve scoring methodology, integrate new free data sources, build the GitHub Actions compute pipeline, design the JSON output schema, build the Next.js static frontend, set up scheduled refresh workflows, deploy to Vercel, or troubleshoot any part of this static ranking system.
---

# QuantRank — Build & Maintenance Skill

A skill for building and extending **QuantRank**, a static-site US equity stock ranking application that ranks stocks 1..N using 60+ classical analysis techniques plus advanced ML/NLP/regime-detection methods, augmented by **research-backed peer-reviewed libraries** (Option B roadmap).

**Project knowledge files** (loaded into the project):
- `stock_ranking_knowledge.md` — authoritative reference for ALL classical formulas, data sources, normalization rules. **Always consult before implementing any analysis technique** — never invent formulas.
- `WORKFLOW.md` — phase-by-phase build plan (9 phases, 0-8). Always check current phase before working.
- `RESEARCH_FINDINGS.md` — research-backed stretch additions for Phase 4-8 (Option B roadmap).

## Contents

- [Core Project Goal](#core-project-goal)
- [Architecture: Static-Site Pattern](#️-architecture-static-site-pattern-option-d)
- [Required Tech Stack](#required-tech-stack)
- [Roadmap Strategy](#roadmap-strategy-option-b-with-option-a-fallback)
- [Repository Structure](#repository-structure)
- [JSON Output Schema](#json-output-schema-critical-contract) — includes schema-version table
- [**Core Behavior Rules**](#core-behavior-rules) — Rules 1-18, the canonical rulebook
- [When the user asks for…](#when-the-user-asks-for)
- [Anti-Patterns to Refuse](#anti-patterns-to-refuse)
- [Communication Style](#communication-style)
- [End State Definition](#end-state-definition)

### Rules at a glance

| # | Rule | Most-cited from |
|---|---|---|
| 1 | Always reference the knowledge documents | — |
| 2 | Phase discipline | WORKFLOW.md |
| 3 | GitHub-Actions-first development | — |
| 4 | Free-tier first + license verification | THIRD_PARTY_NOTICES.md |
| 5 | Point-in-time data discipline | — |
| 6 | Sector-relative for fundamentals | — |
| 7 | Missing data → sector median | — |
| 8 | Test golden values | — |
| 9 | JSON schema is sacred | CLAUDE.md §Conventions |
| 10 | No paid data, no real-money, no live trading | — |
| 11 | Trademark caution | — |
| 12 | Atomic JSON writes | — |
| 13 | Fallback discipline (Option B specific) | — |
| 14 | Decay monitoring (Option B specific) | — |
| 15 | Performance ceiling honesty | — |
| 16 | **Defense layer is annotate-and-veto-Top-N** | CLAUDE.md §Conventions · `.claude/skills/top5-rotation-audit/SKILL.md` |
| 17 | Frontend design system + threshold-symbolic tests | `.claude/skills/frontend-design-system/SKILL.md` |
| 18 | **Observability-before-wiring** | CLAUDE.md §Conventions · WORKFLOW.md · `.claude/skills/portable-observability-before-wiring/SKILL.md` |

---

## Core Project Goal

Build a **static web app** (no backend server, no database) that:
1. Pulls free-tier financial data for US stocks (S&P 500 → S&P 1500 in stages)
2. Computes 60+ classical metrics + advanced sentiment/ML/regime features
3. **Phase 4+: Augments with peer-reviewed library factors** (OSAP, JKP, Qlib Alpha158, IPCA)
4. Normalizes them sector-relative into 8 pillar scores (0-100 each)
5. Combines via meta-learner into a final composite StockRank (0-100)
6. Computes ensemble Fair Price (DCF + Graham + Residual Income + multiples)
7. Surfaces top-5 SHAP explanations per stock
8. Outputs everything as JSON files committed to the repo
9. Refreshes weekly via GitHub Actions cron
10. Renders via Next.js static site deployed on Vercel
11. **Public GitHub repo** — fully reproducible, free GitHub Actions

---

## ⚠️ ARCHITECTURE: STATIC-SITE PATTERN (Option D)

**This is the most important rule. Read carefully.**

### What this app IS:
- A **GitHub Actions cron job** that runs Python weekly to compute rankings
- A **Next.js static site** that reads pre-computed JSON files
- A **public GitHub repo** with auto-committed JSON outputs
- Deployed to **Vercel free tier** with auto-deploy on push
- **Phase 5+: Hybrid compute** — heavy ML training on Kaggle/Modal, light scoring on GitHub Actions

### What this app is NOT:
- ❌ NOT a FastAPI/Flask/Express backend
- ❌ NOT using PostgreSQL/SQLite/MongoDB at runtime
- ❌ NOT making live API calls from the frontend
- ❌ NOT computing scores on user request
- ❌ NOT a real-time/intraday system

### Compute Flow (Phase 0-3):
```
[GitHub Actions cron, Mon-Fri 22:00 UTC — PR 4f, was weekly Sunday]
    ↓
Python script → fetch data → compute features → output JSON
    ↓
Auto-commit JSON files to public/data/ in repo
    ↓
Push triggers Vercel auto-deploy
    ↓
[User opens site] → Next.js loads pre-computed JSON → renders UI
```

### Compute Flow (Phase 5+ with heavy ML):
```
[GitHub Actions weekly cron]
    ↓
Light pipeline (ingestion + scoring) → JSON
    ↓
[Kaggle Notebooks monthly]
    ↓
Heavy training (LightGBM, autoencoder, FinBERT batch) → models
    ↓
[Modal $30/mo credits, quarterly]
    ↓
Whisper transcription + Llama-3 MD&A inference → embeddings
    ↓
All artifacts → repo public/data/ → Vercel deploy
```

### Why this architecture:
- **Free forever**: Vercel hobby + GitHub Actions on public repo + Kaggle/Modal free tiers = $0
- **Mobile-friendly dev**: Claude Code app + GitHub mobile + Vercel mobile = full workflow
- **Fast for users**: pre-computed JSON served via CDN, no DB queries
- **Simple**: no auth, no rate limiting, no API design needed

---

## Required Tech Stack

**DO NOT deviate without explicit approval.** Canonical stack list
lives in [`CLAUDE.md`](CLAUDE.md) §Stack — Python 3.11+ · Next.js 14.2
· GitHub Actions · Vercel · SEC EDGAR + yfinance. Below covers only
the phase-specific additions + license caveats that the long-form
rulebook needs.

### Phase 4+ stretch additions (Option B)

| Layer | Tech | Why |
|---|---|---|
| Heavy ML Training | Kaggle Notebooks (30 GPU-hr/wk) | Free T4/P100 |
| LLM Inference | Modal ($30/mo credits) | ~50 GPU-hrs T4 free |
| Audio Transcription | OpenAI Whisper (open source) | Free local/Modal inference |
| Factor Library | OSAP + JKP + Qlib + IPCA | Peer-reviewed replicated factors |

**Optional-dep additions by phase** (gated behind `[project.optional-dependencies]`):

| Phase | Deps | License |
|---|---|---|
| 4 (factor scout) | `openassetpricing` · `ipca` · `pyqlib` | MIT (OSAP / IPCA / Qlib) |
| 4i.1 (JKP integration) | uses CSV downloads, no pip dep | **CC BY-NC 4.0** — see #115 |
| 5 (ML meta-learner) | `mapie` (conformal) | BSD-3-Clause |
| 6 (Sentiment v2) | `sentence-transformers` · `openai-whisper` | Apache-2.0 / MIT |
| 7 (Portfolio v2) | `skfolio` · `gtda` | BSD-3-Clause / AGPL-3.0 (verify) |
| 4.5e + Phase 5+ | `supabase` (cross-run state) | Apache-2.0 |

**Supabase note**: connector is registered (`mcp__supabase__*` in
Claude Code) but the Python client is **deferred** — add `supabase`
to `pyproject.toml` only inside the implementation PR that first
wires a real table call. See `CLAUDE.md` §Connectors.

**mlfinlab is BANNED** — all-rights-reserved (Hudson & Thames commercial
license). Reimplement Triple-Barrier + Meta-Labeling + Purged CV from
López de Prado 2018 directly under MIT. Algorithms are not patented.

---

## Roadmap Strategy: Option B with Option A Fallback

### Active Plan: Option B (Research-Backed)
- **Phases 0-3** unchanged from original WORKFLOW.md → ship v1.0
- **Phase 4 NEW**: Factor Consolidation (OSAP + JKP + Qlib + IPCA)
- **Phase 5 ENHANCED**: ML + Triple-Barrier + Meta-Labeling + Conformal Prediction
- **Phase 6 ENHANCED**: Sentiment v2 (Whisper + 8-K events + Lazy Prices)
- **Phase 7 ENHANCED**: Regime v2 (Student-t HMM + TDA + NCO)
- **Phase 8**: Universe expansion to S&P 1500

### Fallback Plan: Option A (Original WORKFLOW.md)
Triggers reverting to Option A per-phase if:
- Library integration > 1 week of blockers
- License conflict (e.g., mlfinlab AGPL incompatibility)
- Heavy compute setup fails (Kaggle/Modal access issues)
- Validation shows no alpha lift from research addition

Each phase has explicit fallback triggers in WORKFLOW.md.

### Performance Expectations

| Path | Net Alpha vs SPY | Sharpe Lift | Time |
|---|---|---|---|
| Option A (original) | 2-4% | +0.2 to +0.4 | ~5-6 weeks |
| Option B (research) | 3-7% | +0.3 to +0.5 | ~7-8 weeks |

**Honest hedge**: 3-7% is research-suggested upper bound; 2-4% is realistic floor. Wide confidence interval [0%, +5%] on any single 3-year window. Some research papers cited may have decay, replication issues, or in-sample bias — see RESEARCH_FINDINGS.md caveats.

---

## Repository Structure

[`CLAUDE.md`](CLAUDE.md) §Layout has the live top-level path table.
[`AGENTS.md`](AGENTS.md) §Project structure has the granular tree
with file-purpose annotations. This file's role: lock the
**module-level breakdown** that future phases must align with.

| Path | Purpose | Phase introduced |
|---|---|---|
| `compute/ingest/` | Data fetchers (EDGAR / yfinance / FRED / 13F / 8-K / OSAP / JKP / Qlib) | 1-6 |
| `compute/features/` | Pure feature computation (fundamental / value / quality / growth / momentum / technical / health / risk / sentiment / anomaly / macro_regime / IPCA / Alpha158 / lazy_prices / vdq / tda_regime) | 1-7 |
| `compute/scoring/` | Normalize · pillars · composite · risk_overlay · Tier-2 events · going_concern · Beneish · Dechow | 2-4 |
| `compute/valuation/` | 6-method fair-price ensemble (DCF · RIM · Graham · Multiples · Tangible Book · …) | 3 |
| `compute/ml/` | LightGBM walk-forward · IC validation · SHAP · Triple-Barrier · Meta-Labeling · Conformal · Autoencoder | 5 |
| `compute/portfolio/` | HRP · NCO · Black-Litterman | 7 |
| `compute/output/` | Pydantic schemas · JSON writers · schema-snapshot guard | 0 |
| `compute/main.py` | Weekly orchestrator | 0 |
| `compute/cache/` | 🚫 gitignored | — |
| `.github/workflows/` | `compute-rankings.yml` (cron) · `compute-monthly.yml` · `ci.yml` · `manual-trigger.yml` · `pre-merge-prod-sim.yml` | 0+ |
| `frontend/` | Next.js static export (App Router; per-stock pages) | 0 |
| `tests/` | pytest suite (offline + `@network` gated) | 0+ |
| `docs/` | `stock_ranking_knowledge.md` · `RESEARCH_FINDINGS.md` · `ARCHITECTURE.md` · `METHODOLOGY.md` · `archived/PHASE_0_3_WORKFLOW.md` | — |
| `.claude/skills/` | 45 invocation-triggerable skills + `phase-N/` planning docs | — |

---

## JSON Output Schema (Critical Contract)

The `compute/` and `frontend/` are decoupled by these JSON contracts. **Never break them.**

Schema versions:

| Schema | Phase | What changed |
|--------|-------|--------------|
| `0.1.0-phase0` | Phase 0 | Placeholder JSON only — frontend skeleton ships, no compute output yet. |
| `0.2.0-phase1` | Phase 1 | Universe (S&P 500 from Wikipedia) + per-stock prices via yfinance. Single momentum-only ranking field. |
| `0.3.0-phase2` | Phase 2 | SEC EDGAR fundamentals snapshot per stock — `revenue`, `net_income`, full balance sheet, EPS basic/diluted, shares outstanding. Filing-lag tracking. |
| `0.4.0-phase3b` | Phase 3b | 8-pillar composite (`quality, value, growth, momentum, health, profitability, technical, risk`) + risk overlay annotations. 2 active vetoes (`altman_distress`, `sloan_accruals_top_decile`). NaN imputation = sector median; null pillars (`sentiment`, `ml`) redistributed pro-rata. |
| `0.5.0-phase3c` | Phase 3c | **Fair-price ensemble (6 methods)**: Graham, P/E / P/B / EV-EBITDA multiples (4-tier peer walk + 5/95 winsorization), RIM (Penman 2013), DCF (2-stage, terminal-g ≤ WACC − 100 bp). Aggregation: median (all applicable) + max (excludes outliers > 5× / < 0.2× current). **Per-stock 1y price-history files** (`stocks/history/{TICKER}.json`, OHLCV column-major). **3rd veto** (`net_issuance_top_decile`, Pontiff-Woodgate 2008). **5 numerical guards**: stale-filing (120d soft / 180d hard), outlier 5×, terminal-g cap, sector exclusions, data-quality $10K/share ceiling (Defense #7, added mid-PR after a production spot-check surfaced upstream `shares_outstanding` corruption). **5+ annotate-only flags**: `goodwill_heavy`, `value_trap_risk`, `extreme_<method>_estimate` (×6 method slots — `<method>` is one of `graham`, `multiples_pe`, `multiples_pb`, `multiples_ev_ebitda`, `rim`, `dcf`; in practice 2–3 fire per stock), `stale_filing_soft`, `data_quality_input_corruption`. New schema fields: `StockSummary.{fair_price, max_fair_price, margin_of_safety_pct, valuation_warnings}`; `StockDetail.{fair_price (full ensemble dict), valuation_warnings, has_history, tangible_book_value}`; `RawMetrics.goodwill`; `Metadata.mos_trailing_ic_smoke`. **CI snapshot guard** (`frontend/lib/schema-snapshot.json`) makes Python ↔ TypeScript drift impossible to merge. Reason taxonomy: 21 stable identifiers. |
| `0.6.0-phase3d` | Phase 3d | **Tier-2 event defenses + UI polish**: going-concern phrase scan over the most recent 10-K MD&A (`compute/scoring/going_concern.py`; Mayew-Sethuraman-Venkatachalam 2015 *TAR* + Loughran-McDonald financial dictionary CC BY 4.0; 14 curated phrases with `\b`-anchored regex). 8-K Item 4.02 "Non-Reliance" hard veto (`compute/scoring/eight_k_events.py`; Schroeder 2024 SSRN — ~50% of 4.02 filings precede formal restatement; 365-day lookback). 8-K Item 4.01 auditor-change soft annotate (same module; Reg S-K Item 304; 730-day lookback). **4th active veto** (`non_reliance_filing`). **Tier-2 orchestrator** (`compute/scoring/tier2.py`) shares one EDGAR fetch per ticker between the veto path and the display path. **10-K text cache** (`compute/ingest/filing_text.py`; 90-day TTL on disk). New schema fields: `StockDetail.tier2_events`; `Metadata.tier2_coverage_pct`. New UI: `Tier2EventCard` (severity-coded events with HARD VETO red / Annotate amber pills + filing links), `PillarRadarChart` (8-pillar polar radar), `FairPriceBarChart` (6-method horizontal bars + outlier graying). Reason taxonomy: 24 stable identifiers (was 21). |
| **`0.6.0-phase3d` @ tag `v1.0.0`** (DONE 2026-05-14) | Phase 3e + audit #6 | **v1.0 ship.** No data-schema delta vs PR 3d — only additive optional fields (`StockDetail.beneish_m_score`, `StockDetail.dechow_f_score`). Git release tag is `v1.0.0`; metadata.version stays `0.6.0-phase3d`. **Tier-3 Beneish M-score** (PR #43, Beneish 1999 *FAJ* full 8-ratio, M > −2.22 → `beneish_high` ANNOTATE-only). **Tier-3 Dechow F-score** (PR #45, Dechow et al. 2011 *CAR* Model 1 with simplified RSST→TATA proxy per paper footnote 13, F > 2.45 → `dechow_high` ANNOTATE-only). **Honest Limitations README section** (PR #46). **Audit #6 deep-clean** (PRs #47-49 + #51 + #56 cache key v2): replaced 9 `_NORMALIZED_LATEST` flow items with `_TTM_FLOW_TAGS` + `_try_ttm_max_fresh` helper (catches NVDA-style stale concepts + AVB-style REIT subset patterns + WMT-style stale-DEI shares + 19 PE-NaN tickers); `pe_ratio` formula switched from single-period `eps_diluted` to `NI_TTM / shares` (universe median PE dropped **77.8 → 23.2** industry-correct); revenue / NI chains expanded for utilities (DUK `RegulatedAndUnregulatedOperatingRevenue`), banks (WFC/GS `RevenuesNetOfInterestExpense`), tech (CRWD Including-tax variant), BKNG (`NetIncomeLossAvailableToCommonStockholdersBasic`). **`non_reliance_filing` veto deferred** behind `_EIGHT_K_DEFENSES_ENABLED = False` — re-enable in Phase 4. **CI hardening**: workflow rebase-then-push commit step (PR #55) catches "main moved during compute" race. **Phase 4 UX trio + P1 audit backfill** all planning-only stubs at `.claude/skills/phase-4/<name>/PLAN.md`. **Production verification on commit `b5bc65f3` / workflow run #32**: 502 universe · 99.2% fair-price coverage · 1.0% going-concern FP rate · 3 data-quality edge cases (BRK-B / ERIE / NVR multi-class) · 646 offline tests + 17 @network. Reason taxonomy: 24 stable + 2 Tier-3 (`beneish_high`, `dechow_high`). |
| `0.7.0-phase4g` | Phase 4g | **8-K Tier-2 event defenses re-enabled** (PR #79, merged 2026-05-15 on `c35c6d40`, closes [issue #14](https://github.com/dackclup/quantrank/issues/14)). Flipped `compute/scoring/tier2._EIGHT_K_DEFENSES_ENABLED = True` after the PR 3d workflow-timeout deferral (root cause cleared by PR #58 cache layers + PR 3d tenacity tightening). `non_reliance_filing` (Item 4.02 hard veto, 365d lookback, Schroeder 2024 SSRN — ~50% of 4.02 filings precede formal restatement) returns to the active layer as the **5th active veto**. `auditor_change` (Item 4.01 annotate, 730d lookback, Reg S-K Item 304, Cohen-Malloy-Nguyen 2020 type) joins the Tier-2 annotate surface. No data-schema-shape delta — only the feature-flag flip + reason-taxonomy expansion. |
| `0.7.1-phase4g` | Phase 4g | **`price_change_1d_pct` additive field** (squash-merged via PR #80, commit `1509f707`). New optional `float \| None` field on `StockSummary` + `StockDetail` — day-over-day percent change from the prior trading-day close. Computed once in `compute/main.py:_fetch_prices_one` from the last two valid yfinance closes; null for newly-IPO'd tickers (only one close available). Lets the ranking-table mobile cards render a change pill without lazy-fetching 502 per-stock history JSONs. Per `phase-4/schema-versioning/PLAN.md`: "Add a new optional field (default = None) → patch". Production metadata.version stays `0.7.0-phase4g` until next weekly compute. |
| `0.7.1-phase4g` (no schema delta) | Phase 4.5a-4.5d wave | **Earnings-manipulation defense cluster — sub-PRs 4.5a + 4.5b + 4.5c + 4.5d shipped 2026-05-16/17** (PRs #89/#90/#91 + #93 + #95 + #97). **No data-schema-shape delta** — all 9 new flag identifiers are strings appended to existing `risk_flags: list[str]` (active vetoes) + `valuation_warnings: list[str]` (annotates) arrays. Active vetoes **5 → 7**: + `beneish_manipulation_veto` (Beneish 1999, M > −1.78) + `dechow_manipulation_veto` (Dechow 2011, F > 3.0). Annotates added: `manipulation_triple_flag` (4.5a joint gate, 2 fired: SMCI · WAT), `restatement_history` (4.5b, 59 fired / 11.8% — Hennes-Leone-Miller 2008 *TAR*), `late_filing_notification` (4.5b, 2 fired: HAS · Q — Bartov-Lai-Yeung 2002 *JAR*), `rem_suspect` (4.5c, 16 fired / 3.2% — Roychowdhury 2006 *JAE* 3-proxy REM via per-sector OLS), `accruals_momentum_high` (4.5d, 50 fired / 10.0% — Sloan 1996 / Beneish 1999 Δ(TATA) > +0.05 over 3y), `loss_avoidance_pattern` (4.5d, 0 fired — Burgstahler-Dichev 1997 cohort thresholds too tight for S&P 500 large-cap universe, file as follow-up). Also closes [issue #7](https://github.com/dackclup/quantrank/issues/7) (Sloan over-firing on Financials: 21.3% → 11.7%, sector spread 7.7× → 1.4×). 2 new cache dirs (`compute/cache/edgar_amendments/` + `compute/cache/edgar_late_filings/`, 7d TTL each). Test suite **646 → 831 offline**. Reason taxonomy: 24 stable + 2 Tier-3 + 2 new vetoes + 6 new annotates = **34 stable identifiers**. |
| **`0.10.10-phase4.6`** (PR #300 — in flight 2026-05-28) | Issue #67 follow-up — per-sector `value_trap_risk` delta instrumentation | **PATCH bump** for new `Metadata.value_trap_risk_delta_by_sector: dict[str, int] \| None` field per methodology-scientist Mode B Q2 verdict (deferred from PR #294). Keyed by GICS sector name; values are `without_sector_coe[sector] - with_sector_coe[sector]` — positive = sector dropped flags after `USE_SECTOR_COE = True` flip (Damodaran 2019 Ch. 8.4 predicts Utilities / Real Estate / Consumer Staples positive; Information Technology / Energy negative). Computed every cron regardless of `USE_SECTOR_COE` so Q3 2026-08-19 cohort audit has visible per-sector shape. Tests 1367 → 1369 (+2 schema-contract). ZERO scoring change; field nullable per Rule 18. |
| **`0.10.9-phase4.6`** (PR #297 merged 2026-05-28 `ecb60e64`) | Issue #287 PR A — durable timeout + per-loop wall-clocks | **PATCH bump** for 4 new `Metadata.*_wall_clock_seconds: float \| None` fields (`tier2`, `form4`, `osap`, `cross_source`). Paired with `.github/workflows/compute-rankings.yml` `timeout-minutes: 150 → 195` + cache-restore canary step (10 cache dirs, ~30s) that surfaces cache eviction before any SEC fetch begins. 4 distinct defensive patterns: Tier-2 outer try/except wraps ThreadPoolExecutor (None on interpreter failure); Form-4 start INSIDE the `else:` branch (None when `FORM4_FETCH_SKIP=1` per Issue #287 PR B gate); OSAP start before try (None in except; QR_SKIP_OSAP still populates a small float because it bypasses freshness gate only); Step 8 always populated. Wall-clock fields semantically distinct from `fundamentals_latency_p95_seconds` — those measure per-ticker p95 (tenacity-cascade detector); these measure total loop duration (budget-overrun + cache-eviction detector). Empirically validated on cron Run #71 (`368dccd9`, 2026-05-28 08:44 UTC): all 4 fields populated correctly, total ~8.2 min instrumented under 195m ceiling. Companion PR #298 cache-v5 bump closes the silent-failure gap surfaced by this PR's Rule 18 instrumentation (PR #292 Branch 3 fix never fired due to warm-cache replay short-circuit). |
| **`0.10.8-phase4.6`** (PR #292 merged 2026-05-28 `e9aaab31`) | Issue #288 — GOOG/GOOGL XBRL concept-name omission fix | **PATCH bump** for new Rule 18 disambiguator `Metadata.multi_class_per_class_attempt_count`. PR #269 (`5bf38c12`) per-class XBRL override never fired in production since landing — `_fetch_shares_from_per_filing_xbrl` queried only 2 of the 3 needed XBRL concepts (`us-gaap:CommonStockSharesOutstanding` was the missing one; Alphabet files per-class share counts under this concept). Fix adds the missing concept to the tuple; counter disambiguates "branch never reached" (attempt=0) vs "XBRL returned None" (attempt>0, override=0). GOOG/GOOGL display `market_cap` corrected from ~$4.66T/$4.71T to ~$2.09T/~$2.59T per class on cron Run #72+ (cache-v5 bump per PR #298 forces fresh fetch); composite/rankings UNAFFECTED. Annotate-only safety net (`multi_class_aggregate_shares_suspected`) continues to fire. 4 new regression tests authored by `test-engineer`. |
| **`0.10.7-phase4.6` @ tag `v1.4.0-phase4.6`** (PR #283 release 2026-05-27 `bbca9cac`) | Phase 4.6 honest re-validation harness | **MINOR bump** for Phase 4.6 additive `Metadata` fields landing across PRs #274-#282 (universe-provenance + survivorship-bias historical S&P 500 membership per Hou-Xue-Zhang 2020 RFS + ranking history time-series loader via git-archive + forward-return loader from gitignored price cache + per-pillar Spearman IC orchestrator via rank-then-Pearson, no scipy dep + manipulation-index distribution shift report). `scripts/generate_honest_baseline.py` CLI added with McLean-Pontiff 2016 32%-decay banner pinned in 5-phrase mandatory disclaimer. ZERO scoring / Top-5 / composite delta — all additive observability + offline-validation modules. |
| **`0.10.6-phase4.5e`** (PR #269 merged 2026-05-26 `5bf38c12`) | Issue #261 PR-B — per-class XBRL extraction | **Structural fix for GOOG/GOOGL `$4.6T` overcount.** New `config.MULTI_CLASS_OVERCOUNT_ALLOWLIST: dict[str,str]` mapping ticker → exact XBRL class-member string (`GOOGL → "us-gaap:CommonClassAMember"`, `GOOG → "goog:CapitalClassCMember"` ← **filer-specific namespace gotcha** per edgar-debugger probe). `_fetch_shares_from_per_filing_xbrl` extended with `target_class_member` parameter; new elif branch in `_build_snapshot` fires when ticker is on allowlist + primary is plausible aggregate-shape. 2 new `Metadata` fields: `multi_class_per_class_override_count` (expected ~2 = GOOG + GOOGL) + `multi_class_mc_reconcile_failure_count` (Rule-18 defensive). PATCH — additive. ZERO behavior change for 500 non-allowlist tickers. |
| **`0.10.5-phase4.5e`** (PR #264 merged 2026-05-26 `d9c62292`) | Issue #261 PR-A — multi-class CIK-collision annotate | **New `multi_class_aggregate_shares_suspected` annotate** + Rule 18 `Metadata.multi_class_aggregate_shares_suspected_count: int \| None`. Fires when two or more tickers share the same CIK AND each ticker's market_cap > 10% of universe-median (`MARKET_CAP_FLOOR_RATIO = 0.10`). Annotate-only; composite rank unchanged. Defense layer 32 → 33 declared. Expected steady-state firing ≈ 6 (GOOG / GOOGL / NWS / NWSA / FOX / FOXA). PATCH — additive `Metadata` field only. Companion PR #265 renamed Site-2 DQIC emission to `valuation_output_anomalous` without schema delta. |
| **`0.10.4-phase4.5e`** (PR #257 merged 2026-05-24) | Issue #248 PR2b — multi-class dimensional override | **Per-filing XBRL dimensional override** for known multi-class issuers (V / NWS / NWSA / FOX / FOXA / BRK-B / STZ allowlist via `config.MULTI_CLASS_SHARE_ALLOWLIST`). When `companyfacts` returns a plausible primary `shares_outstanding` but the ticker is on the allowlist, peek per-filing XBRL; if the dimensional sum across all classes exceeds primary, the summed value is the truth (Damodaran 2019 Ch. 16). Rule 18: `Metadata.shares_fallback_dimensional_override_count: int \| None`. PATCH — additive observability field. |
| **`0.10.3-phase4.5e`** (PR #256 merged 2026-05-24) | Issue #246 PR2a — cross-source observability | **Cross-source disagreement observability surface.** 4 new optional `Metadata` fields land simultaneously: `cross_source_disagreement_count`, `cross_source_delta_histogram` (9-bucket universe-wide distribution), plus `shares_fallback_triggered_count` + `shares_fallback_too_low_count` (separates ERIE-class too-low path from STZ-class None path, retrofit for PR #253). Plus 1 new optional `StockSummary.cross_source_delta: float \| None`. PATCH — all additive, nullable on legacy snapshots. Gates the PR2b severe-threshold decision with empirical 1-cron data. |
| **`0.10.2-phase4.5e`** (PR #224 merged 2026-05-23) | Phase 4.5e PR 4-eq — 10b5-1 filter | **10b5-1 contamination filter** on `_is_opportunistic_sell` (Jagolinzer 2009 §3.2 — 40-60% FP reduction). Accessed via footnote-text pattern scan (`detect_10b5_1_plan` regex). `footnotes` added to `_NON_DERIVATIVE_TX_REQUIRED_ATTRS` + `_OWNERSHIP_REQUIRED_ATTRS` + new `_FOOTNOTES_REQUIRED_ATTRS`. Rule 18: `Metadata.form4_rule10b5_one_excluded_count: int \| None`. PATCH — additive. Tests 1144 → 1160+. Defense emitted flags UNCHANGED at 32 (filter is signal-quality, not new flag). |
| **`0.10.1-phase4.5e`** (PR #222 merged 2026-05-23) | Phase 4.5e PR 3 — insider-cluster annotates | **Two new annotate-only flags**: `insider_sell_cluster` (≥ 3 distinct insiders, opportunistic `{S,D}` codes, 30d rolling, CMP 2012) + `c_suite_unusual_sell` (≥ 2 CEO/CFO/President insiders, same window, JMZ 2003). Reserved weights downgraded from `RESERVED` constants to active `FLAG_WEIGHTS` entries (5.0 + 3.0 delta). Rule 18: `Metadata.insider_sell_cluster_firing_count` + `c_suite_unusual_sell_firing_count`. PATCH — additive `Metadata` fields only. Defense layer 30 → 32. Tests 1115 → 1144. |
| **`0.10.0-phase4.5e`** (PR #205 merged 2026-05-22) | Phase 4.5e PR 2 — Form-4 observability | **MINOR bump** (multiple additive fields land simultaneously per semver convention). 7 new `Metadata` fields: `form4_enabled` · `form4_coverage_pct` · `form4_fetch_latency_p50_seconds` · `form4_fetch_latency_p95_seconds` · `form4_universe_insider_count_median` · `form4_tickers_with_recent_activity` · `form4_fetch_failures`. 1 new `StockDetail` field: `form4_diagnostics`. New verify-helper Section K. ZERO scoring impact; `_FORM4_FLAGS_ENABLED` stays False. Supersedes the 0.9.8 PATCH after rebase. |
| **`0.9.8-phase4h.8`** (PR #204 merged 2026-05-22) | Issue #67 — sector-adjusted CoE | **GICS-keyed Damodaran sector-CoE dict** (11 sectors) behind `config.USE_SECTOR_COE = False` gate. Rule 18: `Metadata.sector_coe_enabled` + `value_trap_risk_count_without_sector_coe` + `value_trap_risk_count_with_sector_coe`. PATCH. Tests +35. Backward-compatible — all new fields optional, flag OFF by default. |
| **`0.9.7-phase4h.7`** (PR #183 merged 2026-05-21) | Issue #177 — `extreme_estimate_majority` | **New `extreme_estimate_majority` annotate** + Rule 18 `Metadata.extreme_estimate_majority_count: int \| None`. Fires when ≥ `EXTREME_MAJORITY_THRESHOLD = 3` of 6 valuation methods emit `extreme_*_estimate` — Huber 1981 §1.4 breakdown-point rationale. Annotate-only pending ≥ 1 cron firing-rate data. PATCH. Defense layer 29 → 30. Tests 1049 → 1059. |
| **`0.9.6-phase4h.6`** (PR #181 merged 2026-05-21) | Issue #176 — `share_count_extraction_missing` | **New `share_count_extraction_missing` annotate** + Rule 18 `Metadata.share_count_extraction_missing_count: int \| None`. Fires when `shares_outstanding is None AND revenue > 0 AND total_assets > 0`. PATCH. Defense layer 28 → 29. Tests 1031 → 1040. PR #182 (same day) adds per-filing XBRL fallback recovery — no schema change. |
| **`0.9.5-phase4h.5`** (PR #180 merged 2026-05-21) | Phase 4b — `loss_avoidance_pattern_size_invariant` | **New `loss_avoidance_pattern_size_invariant` annotate** + Rule 18 `Metadata.loss_avoidance_size_invariant_firing_count: int \| None`. Fires when `NI / TotalAssets ∈ [0, 0.005]` for 3+ consecutive fiscal years — Roychowdhury 2006 *JAE* Table 1 §5.2 suspect-firm cutoff. PATCH. Defense layer 27 → 28 emitted boolean flags. Tests 1024 → 1031. Backward-compatible — additive field, no consumer migration. |
| **`0.9.4-phase4h.4`** (PR #161 merged 2026-05-20) | Epic #150 Phase 2.1 | **`valuation_methods_applicable` schema surfacing.** PATCH bump per "additive optional field" convention. 1 new optional field on `StockDetail` (and nested in `fair_price` dict): `valuation_methods_applicable: int` — counted as the positive-framed inverse of `extreme_*_estimate` warnings emitted in `compute/valuation/ensemble.py`. Surfaces the method-applicability signal explicitly at the schema-snapshot level so downstream filtering / audits can use it without deriving from the warning list. Additive only — no consumer migration; `loss_chance.py` and `FairPriceBarChart.tsx` keep reading `extreme_*_estimate` for back-compat. Defense layer headline 27 (PR #154 reconcile). |
| **`0.9.3-phase4h.3`** (PR #160 merged 2026-05-20) | Epic #150 Phase 1.6 | **Explicit `tier2_enabled: bool` field on `Metadata`.** PATCH bump. Sourced from `compute/scoring/tier2._EIGHT_K_DEFENSES_ENABLED` at writer time; verify-helper Section B now branches on the explicit flag instead of inferring from `tier2_coverage_pct > 5%`, with legacy-snapshot fallback. Closes the last open AC item carried forward from issue #117 (PR #149 deferred) and issue #155. **No new veto, no rank change** — observability schema clean-up only. Defense layer unchanged at 17 declared / 27 emitted (per PR #154 reconcile). |
| **`0.9.2-phase4h.2`** (PR #124 merged 2026-05-19) | Phase 4h.2 Part 2 | **Multi-port OSAP adapter + accounting-balance diagnostic surface** (issue #116). PATCH bump per the "additive optional field" convention. 1 new optional `Metadata` field: `osap_signals_dropped_no_long_short: list[str] \| None` — closes the 100-signal accounting equation (`missing + dropped_no_LS + gated + used == 100`). Root-cause fix: `compute_long_short_returns` rewritten with per-signal `min(port)` / `max(port)` inference instead of hardcoded `port=01/10`, recovering ~56 quintile / tercile signals that 0.9.0–0.9.1 silently dropped. **No new veto, no rank change** — Top-5 still ranks raw `composite_score` per Rule 16. Defense layer stays at **17**. DSR sign-inversion investigation (100% `low_dsr` rejection) deferred to Phase 4h.2 Part 3 follow-up. |
| **`0.9.1-phase4h.2`** (PR #118 merged 2026-05-19) | Phase 4h.2 Part 1 | **Observability follow-up to Phase 4h** (issue #116). PATCH bump per `phase-4/schema-versioning/PLAN.md` ("Add a new optional field (default = None) → patch"). 2 new optional `Metadata` fields land: `osap_signals_missing_from_dataset: list[str] \| None` (surfaces the silent-drop bug — 78/100 manifest signals missing from dataset surface in the first 0.9.0-phase4h production run) + `osap_gate_diagnostics: dict[str, OsapGateDiagnostic] \| None` where the new `OsapGateDiagnostic` Pydantic model carries `pbo`/`dsr`/`sharpe`/`rejection_reason` (all nullable per the "all 4 fields explicit `= None` defaults" lock). Set-diff helper lives at `compute/features/osap_replicate.py::signals_in_dataframe` (mirrors `coverage_by_signal` shape one function above — pure helper, no I/O). Wired into `compute/main.py` inside the existing OSAP try/except so graceful degradation continues to set every osap_* field to `None` on fetch failure. **No new veto, no rank change** — observability-only; Top-5 still ranks raw `composite_score` per Rule 16. Defense layer unchanged at **17**. Part 2 (threshold calibration + manifest reconciliation) deferred until ≥1 week of production diagnostic data accumulates. Test suite **911 → 924 offline** (Part 1 adds 13 across 3 commits: 7 schema round-trip/backward-compat + 4 helper + 2 gate-diagnostic round-trip). Reason taxonomy unchanged at 34 stable identifiers. |
| **`0.9.0-phase4h`** (PR #112 merged 2026-05-19) | Phase 4h | **OSAP signal replication + PBO/DSR hard gate + Path-b composite × OSAP blend** (5-commit cluster on branch `claude/resume-quantrank-phase-4.5-Zh0pO`: 06bdac76 schema-foundation, b79983f6 osap_replicate proxy + 100-signal manifest, a6760d91 osap_blend Path-b, df4d9bd2 osap_validation PBO/DSR gate + rolling-12m-IC, [TBD] compute/main.py wiring + @network e2e). **Minor bump** — 6 new optional fields land simultaneously: `StockDetail.osap_signals: dict[str, float] \| None` + `StockDetail.osap_blended_score: float \| None`; `Metadata.osap_signals_used: list[str] \| None`, `Metadata.osap_excluded_signals: list[str] \| None`, `Metadata.osap_signals_ic_12m: dict[str, float] \| None`, `Metadata.osap_signals_coverage_pct: dict[str, float] \| None`. **OSAP blend stays OUTSIDE `compute_composite()`** — `PHASE3_WEIGHTS` sum-to-1.0 invariant (`compute/scoring/composite.py:43-45`) intact; Path-b formula `blended = (1 - weight) × composite_score + weight × osap_signal_aggregate`, default `weight=0.5` locked at `osap-integration/PLAN.md:168-170`. **Hard gate** = PBO ≤ 0.5 AND DSR > 0 via PR #60's `factor_passes_gates`; rolling-12m Spearman IC is observability-only (full walk-forward CV deferred to Phase 5 per `defense-infrastructure/PLAN.md:270`). **No new veto** (Top-5 still ranks raw `composite_score` per Rule 16; `osap_blended_score` is informational); defense layer stays at **17**. **Universe-gap policy** — tickers with no OSAP coverage pass `composite_score` through unchanged (no impute, distinct from pillar `neutralize_missing=True`). **NaN policy in PBO cohort** — zero-fill (not mean-fill, not dropna) preserves Bailey 2014 `n_trials = cohort_size` multiple-testing correction; sparse signals naturally lose on DSR (low Sharpe → DSR rejection). **OSAP failure is observability-only** — wrapped in try/except in `compute/main.py` so live-fetch / package failure NEVER blocks weekly production; all 6 new fields degrade to `None`. Test suite **856 → 906 offline + 18 → 19 `@network`** (commits 2-5 added 50 tests; e2e network test added in commit 5). Reason taxonomy unchanged at 34 stable identifiers. Tag `v1.1.0-phase4` (or `v1.3.0` for the 4.5e+4h combined release) deferred until 4i/4j/4k also merge. |
| **`0.8.0-phase4.5f`** | Phase 4.5f | **Manipulation Composite + soft composite penalty + UI** (PR #100 merged 2026-05-17 on commit `b1588b2a`; production verified on commit `e57f09cb`, run #51, warm-cache 5m14s). **Minor bump** because 5 new optional fields land simultaneously + new UI surface ships + tag `v1.2.0-phase4.5` coordinates with the data-version bump (semver coupling). Additive optional fields: `StockSummary.manipulation_index: float \| None`, `StockSummary.composite_score_adjusted: float \| None`, `StockDetail.manipulation_index`, `StockDetail.composite_score_adjusted`, `StockDetail.manipulation_components: dict[str, bool] \| None`. **`manipulation_index`** is a 0-100 rollup over the 4.5a-d flag set via a per-flag additive weight table in `compute/scoring/manipulation_index.py::FLAG_WEIGHTS` (active vetoes 15-20 pts · joint-gate 10 · annotates 5-8 · Tier-3 soft 3); clipped to `[0, 100]`. **`composite_score_adjusted`** applies the soft penalty `composite − 0.5 × (index / 100) × 20` (max 10-pt deduction at index = 100); the original `composite_score` field is preserved untouched per Rule 9 audit trail. **Rank source stays the raw composite per Rule 16** — the adjusted value is informational only, surfaced on the new detail-page `ManipulationRiskCard` (3-band outlined-light: emerald LOW / amber MODERATE / rose HIGH) with the in-line qualifier "Composite penalty: −X.XX pts (informational; rank uses raw composite)". Production: 158/502 (31.5%) fire the card (HIGH 2: SMCI=84 · WAT=64; MODERATE 60; LOW 96). **Phase 4.5e reserved-slot weights declared** (`INSIDER_SELL_CLUSTER_WEIGHT_RESERVED = 10`, `C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED = 5`) — the 4.5e PR uncomments 2 entries in `FLAG_WEIGHTS`, no calibration cascade. Test suite **831 → 856 offline**. Reason taxonomy: 34 stable identifiers (unchanged — `manipulation_index` is a derivation, not a new flag). Tag **`v1.2.0-phase4.5`** ready to cut. |

> Phase 4+ schemas are tracked in [`WORKFLOW.md`](WORKFLOW.md) "Defense
> Roadmap" until shipped. The table above documents shipped schemas
> only — the roadmap doc is the single source of truth for unshipped
> work and avoids drift between two places.

### `public/data/metadata.json`
```json
{
  "version": "1.0.0",
  "last_update_utc": "2026-05-11T22:00:00Z",
  "next_update_utc": "2026-05-18T22:00:00Z",
  "universe": "SP500",
  "universe_size": 503,
  "compute_run_id": "abc123def",
  "git_commit": "...",
  "phase": 3,
  "roadmap": "Option B"
}
```

### `public/data/rankings.json` (summary)
```json
[
  {
    "rank": 1,
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "sector": "Information Technology",
    "composite_score": 87.4,
    "current_price": 220.15,
    "fair_price": 245.30,
    "max_fair_price": 285.00,
    "margin_of_safety_pct": 10.3,
    "pillar_scores": {
      "quality": 92, "value": 65, "growth": 78, "momentum": 84,
      "health": 95, "sentiment": 70, "ml": 80, "risk": 88,
      "technical": 75, "profitability": 90
    },
    "confidence_interval_95": [78.2, 92.1]
  }
]
```

### `public/data/stocks/{TICKER}.json` (full detail)
*(Same structure as before with additions for Phase 4+ research features. See WORKFLOW.md for full detail.)*

---

## Core Behavior Rules

### Rule 1: Always reference the knowledge documents
Before implementing any analysis technique:
- Phase 0-3: Read `stock_ranking_knowledge.md`
- Phase 4+: Read `RESEARCH_FINDINGS.md` for stretch additions
- Use formulas AS WRITTEN. Never reinvent without justification.

### Rule 2: Phase discipline
Work in **phases per `WORKFLOW.md`**. Do not skip ahead. Each phase produces a working deliverable. **Phase 4 starts only after v1.0 ships.**

### Rule 3: GitHub-Actions-first development
The user develops on mobile (no local Python/Node), so all testing/running happens in GitHub Actions / Kaggle / Modal. CI must catch errors before merge. Use `workflow_dispatch` for ad-hoc runs. Logs are primary debugging tool.

### Rule 4: Free-tier first + license verification
Every API/library must respect free-tier limits AND have compatible license:
- Verify OSS license before integration (especially mlfinlab AGPL)
- Cache aggressively to `compute/cache/` (gitignored)
- Implement `tenacity` retry with exponential backoff
- Phase 4+: Verify current data availability before integration (sources change)

### Rule 5: Point-in-time data discipline
**Look-ahead bias kills backtests.** Every fundamental MUST use `filing_date`, not `period_end`. 13F is lagged 45 days. Form 4 uses `transactionDate`. SEC EDGAR exposes both — always use the filing date. **Phase 4+ OSAP/JKP signals are pre-built with proper PIT discipline; verify any reconstructions match.**

### Rule 6: Sector-relative for fundamentals
Quality, Value, Growth, Profitability — **always rank within GICS sector**, never globally. Use absolute ranking only for Risk and Momentum. **Always exclude financials/utilities from Magic Formula and asset-turnover metrics.**

### Rule 7: Missing data → sector median
- `<50%` of pillar's metrics available → set pillar to neutral (50) and flag.
- Single metric NaN → impute as **sector median** (NEVER global median).
- Never propagate NaN; record imputed fields in `data_quality.imputed_metrics`.

### Rule 8: Test golden values
For every fundamental metric, write a unit test against a **known-correct value** for at least 1 ticker. **Phase 4+: Validate library outputs against published paper results within 5% tolerance.**

### Rule 9: JSON schema is sacred
The `frontend/` consumes JSON with strict expectations. **Never break the schema mid-development.** Bump version per phase per Schema versions table above.

### Rule 10: No paid data, no real-money, no live trading
This app is for **research and educational ranking only**. README and frontend MUST display this disclaimer. Never integrate live trading APIs.

### Rule 11: Trademark caution
Never use "Jitta" anywhere. The project name is **QuantRank**.

### Rule 12: Atomic JSON writes
Always write to a `.tmp` file then `os.rename()` to final path. Never write partial JSON.

### Rule 13: Fallback discipline (Option B specific)
Per-phase fallback triggers documented in WORKFLOW.md. If hit:
- Log decision in PHASE_STATUS.md
- Revert that phase to Option A
- Continue with subsequent phases on Option B
- Do not silently abandon research additions; document why

### Rule 14: Decay monitoring (Option B specific)
For research-backed factors (Phase 4+):
- Track rolling 24-month IC per signal
- Alert when slope < 0 with t < -2
- McLean-Pontiff suggests 35% post-publication decay; budget for it
- Re-validate quarterly against published paper t-stats

### Rule 15: Performance ceiling honesty
Never claim alpha > 5% net without:
- 10+ years walk-forward validation
- Embargoed/purged CV
- Deflated Sharpe < 0.5
- PBO < 50%
- Out-of-sample period including 2020 + 2022 regime stress

### Rule 16: Defense layer is annotate-and-veto-Top-N (NEW 2026-05-09)

Risk overlays and fraud-detection signals **never modify the composite
score**. They operate in three modes only:

1. **VETO** — exclude flagged stock from `entered_top5` badge (composite
   rank unchanged). **7 active at Phase 4.5a (2026-05-16)**: Altman Z″
   distress (`altman_distress`), Sloan accruals top decile within sector
   (`sloan_accruals_top_decile`, sector-relative since PR #89), Net
   Stock Issuance top decile (Pontiff-Woodgate 2008,
   `net_issuance_top_decile`), `data_quality_input_corruption` (promoted
   PR #33), `non_reliance_filing` (re-enabled PR #79, 8-K Item 4.02,
   Schroeder 2024 SSRN — 365d lookback), `beneish_manipulation_veto`
   (Beneish 1999, M > −1.78 PPV-crossover, PR #90),
   `dechow_manipulation_veto` (Dechow et al. 2011, F > 3.0 4× baseline,
   PR #91).
2. **GUARD** — return null + flag (e.g., null fair_price for stale
   filings). 5 numerical guards at v1.0.
3. **ANNOTATE** — warning only, no score change. 8+ flags at v1.0 +
   `recommendation` (PR 4d) + `loss_chance_pct` (PR 4e) — both
   pure derivations from existing fields, no new ingest.

**Why never scoring inputs**: empirical evidence (Beneish-Vorst 2021;
McLean-Pontiff 2016) shows fraud-detection FP rates ≥30% in broad market
and anomaly returns decay 58% cumulative. Penalizing the score
introduces more error than it removes.

**Defense freeze post-v2.0**: Do NOT add new defenses unless an existing
defense's IC has decayed > 50% for 6+ months AND the new addition has
academic evidence of incremental IC > 0.01. Marginal AAER capture < 5%
beyond 4 fraud signals (Beneish-Vorst 2021). **Rotate, don't stack.**

Full defense schedule and bibliography in
`docs/RESEARCH_FINDINGS.md` §"Defense Playbook".

### Rule 17: Frontend design system + threshold-symbolic tests (NEW 2026-05-15)

Two pattern locks landed during PRs 4d / 4e and apply to every Phase
4+ UI / scoring contribution:

1. **Outlined-light chip family, no `dark:` variants** — every new
   pill / badge / chip (sector, score-tier, MoS bucket, recommendation,
   loss-chance) uses the **Pattern B** outlined-light style codified in
   `.claude/skills/frontend-design-system/SKILL.md` Rule 2. Solid-bg
   chips are an anti-pattern. **Never add `dark:` Tailwind variants** —
   `globals.css` forces `color-scheme: light` but Tailwind `dark:`
   triggers on system `prefers-color-scheme: dark`, producing invisible
   text against the forced-light background (the PR #70 regression).
   Light-mode only; trigger the design-system skill before any new UI.

2. **Tests reference thresholds symbolically, not by literal value** —
   pure-function scorers like `derive_recommendation` and
   `derive_loss_chance` expose their thresholds as module-level
   constants (`BULLISH_COMPOSITE_MIN`, `BULLISH_MOS_MIN_PCT`, etc.).
   Tests **must** import the constants and assert against
   `constant ± 1.0` style boundaries — never against hard-coded
   numbers. This insulates the test suite from threshold tuning: when
   the constant moves, tests stay green if the function still respects
   the constant. PR 4d's calibration revision (composite 70 → 60, MoS
   20 → -10 after the S&P 500 distribution simulation surfaced 0%
   Strong Buy and 54% Sell) broke 5 hard-coded tests and was the
   forcing function for this rule.

### Rule 18: Observability-before-wiring (NEW 2026-05-20)

Every integration PR that consumes a NEW external data source ships
the diagnostic `Metadata` surface BEFORE the production logic uses
the data. The diagnostic exposes WHICH inputs were dropped and WHY
at each filter / gate / NaN-strip point; production wiring lands
≥ 1 cron later, after the accounting equation
`len(input_universe) == sum(len(diagnostic_buckets))` is verified
on real data. The Phase 4h → 4h.2 retrofit (PRs #112 → #118 → #124)
is the forcing precedent: a 30-minute additional Phase 4h scope
would have saved the ~10-hour 2-PR debugging cycle. Detail +
mandatory checklist in `WORKFLOW.md` §Observability-Before-Wiring
Pattern.

---

## When the user asks for...

### "Build the project from scratch"
1. Read `WORKFLOW.md` Phase 0.
2. Confirm: project name = QuantRank, repo = public, Vercel deploy.
3. Execute Phase 0 tasks. Update `PHASE_STATUS.md` at end.

### "Add a new metric (Phase 0-3)"
1. Search `stock_ranking_knowledge.md` for the technique.
2. Identify pillar (per Section 21 / Quick Reference A).
3. Add function to `compute/features/<pillar>.py` with golden-value test.
4. Update pillar aggregation in `compute/scoring/pillars.py`.
5. Add field to `raw_metrics` in `compute/output/schemas.py`.
6. Update TypeScript types in `frontend/lib/types.ts`.
7. Run CI to verify.

### "Add a research-backed feature (Phase 4+)"
1. Read `RESEARCH_FINDINGS.md` for the technique.
2. Verify license compatibility (especially AGPL libraries).
3. Verify current data source availability (re-check URLs).
4. Add module to appropriate `compute/` directory.
5. Validate output against published paper results (5% tolerance).
6. If validation fails → trigger fallback to Option A for that phase.
7. Document in PHASE_STATUS.md.

### "Add a new data source"
1. Check Section 5 of knowledge doc — already covered?
2. Phase 4+: Check RESEARCH_FINDINGS.md data sources.
3. New file in `compute/ingest/<source>.py` matching existing pattern.
4. Add API key (if needed) to GitHub Actions secrets.
5. Document rate limits and license in module docstring.

### "Improve accuracy"
1. Manage expectations per Section 28 (realistic = 2-4% Option A, 3-7% Option B).
2. Check current phase. Don't add Phase 6 features in Phase 4.
3. Don't add LSTM before LightGBM works.
4. **Phase 4+**: Prioritize OSAP/JKP factor library over DIY signals.
5. Always validate via IC, IR, PBO before claiming improvement.

### "The site is broken / shows old data"
1. Check `PHASE_STATUS.md` for current phase.
2. Check latest GitHub Actions run — failed?
3. Check `public/data/metadata.json` — what's `last_update_utc`?
4. Check Vercel deployment logs.
5. Recovery: trigger `manual-trigger.yml` workflow.

### "Deploy to production"
1. **One-time setup** (Phase 0):
   - Push repo to GitHub (public).
   - Connect repo to Vercel (auto-detects Next.js).
   - Set Vercel build settings: root = `frontend/`, output = `out/`.
2. **Trigger first compute**: GitHub Actions → `compute-rankings.yml` → Run workflow.
3. **Verify**: After ~10 min, JSON appears, Vercel rebuilds, site goes live.

### "Set up Phase 5+ heavy compute"
1. Connect Kaggle account (free) → generate API token.
2. Add `KAGGLE_USERNAME`, `KAGGLE_KEY` to GitHub secrets.
3. Connect Modal account (free $30/mo credits).
4. Add `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` to GitHub secrets.
5. Set up workflow to trigger Kaggle from GH Action via `kaggle kernels push`.
6. Outputs: Kaggle Dataset → re-pull into repo via API.

---

## Anti-Patterns to Refuse

| Anti-pattern | Why bad | Correct approach |
|---|---|---|
| Adding FastAPI/Flask backend | Architecture is static (Option D) | Output JSON from GitHub Actions |
| Adding PostgreSQL/SQLite | No runtime DB by design | Files in `public/data/` |
| Calling APIs from frontend | Defeats static-site purpose, costs money | Pre-compute, read JSON at build |
| Hardcoding API keys | Repo is public! | GitHub Actions secrets |
| Using `period_end` for backtest | Look-ahead bias | Use `filing_date` from EDGAR |
| Global z-score across financials + tech | Sector-distorting | Sector-relative percentile rank |
| Imputing NaN with 0 | Biases scores wildly | Sector median (Rule 7) |
| LSTM before LightGBM works | Overengineering | Tree-based first |
| Daily refresh in GitHub Actions | Wastes free minutes | Weekly only |
| Skipping golden-value tests | yfinance changes silently | Mandatory per metric |
| Claiming >7% alpha | Almost certainly overfit | Run PBO, deflated Sharpe |
| Live trading endpoints | Out of scope, regulatory risk | Read-only ranking display only |
| Partial JSON writes | Breaks frontend | Atomic write via temp file |
| Using "Jitta" name | Trademark | "QuantRank" |
| Skipping research additions in Phase 4+ without fallback log | Loses Option B value | Document fallback in PHASE_STATUS |
| AGPL libs without license check | Legal risk | Verify before integration |
| Reddit/StockTwits for megacap | No documented alpha at S&P 500 scale | Skip, focus on insider Form 4 |
| Russell 2000 microcaps in Phase 8 | Free data quality collapses | Stop at S&P 1500 |
| LSTM/TFT instead of PatchTST | Outdated SOTA | Use PatchTST/iTransformer |
| Larger LLMs (>13B) for sentiment | Disproportionate cost | FinBERT or Llama-3 8B max |

---

## Communication Style

The user develops on mobile and may not be a quant expert.
- **Formulas (Phase 0-3)**: link to section in `stock_ranking_knowledge.md`.
- **Research additions (Phase 4+)**: link to section in `RESEARCH_FINDINGS.md` + paper citation.
- **Realistic expectations**: cite Section 28 + RESEARCH_FINDINGS caveats.
- **Mobile constraints**: prefer GitHub Actions/Kaggle/Modal runs over local debugging.
- **Iteration**: each GH Actions run takes 3-30 min depending on phase; budget time.
- **Phase status**: always say "we are in Phase X; next deliverable is Y; fallback to Option A is Z if blocker hits."
- **Honesty**: acknowledge when training-time familiarity may be stale; recommend re-verification.

When user is excited about a new technique: "great — let's add it after Phase X stabilizes. Read RESEARCH_FINDINGS.md to see if it's already in the Option B roadmap."

---

## End State Definition

### v1.0 (Phase 3 complete)
- [ ] Public GitHub repo `quantrank` exists
- [ ] Weekly GitHub Actions cron runs successfully
- [ ] S&P 500 universe ingested with ≥10 years of data
- [ ] All 8 pillars computed for every stock
- [ ] Composite StockRank (0-100) per stock
- [ ] Fair Price ensemble (Median + Max) per stock
- [ ] JSON files in `public/data/` valid against schema
- [ ] Vercel-deployed Next.js site shows ranking table + detail page
- [ ] README has disclaimer + architecture diagram + methodology link
- [ ] Mobile responsive, Lighthouse >85
- [ ] Tag `v1.0` on GitHub

### v2.0 (Phase 8 complete) — MAXIMUM FREE TIER
- [ ] All v1.0 criteria
- [ ] OSAP + JKP + Qlib factor libraries integrated (Phase 4)
- [ ] IPCA latent factors (Phase 4)
- [ ] LightGBM + Triple-Barrier + Meta-Labeling + Conformal (Phase 5)
- [ ] Whisper + 8-K events + Lazy Prices sentiment (Phase 6)
- [ ] Student-t HMM + TDA + NCO (Phase 7)
- [ ] S&P 1500 universe (Phase 8)
- [ ] Backtest report with PBO < 50%, Deflated Sharpe documented
- [ ] Tag `v2.0` on GitHub
- [ ] Honest performance: 3-7% net alpha vs SPY (with wide CI)

After v2.0: Maintenance mode. No further phase additions unless empirically validated alpha gain.
