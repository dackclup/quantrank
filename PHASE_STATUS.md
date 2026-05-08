# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | ✅ DONE — 2026-05-07 |
| 1 | Universe + prices ingestion | ✅ DONE — 2026-05-08 |
| 2 | Fundamentals via SEC EDGAR | ✅ DONE — 2026-05-08 |
| 3 | Classical features + composite → **v1.0** | 🟡 in progress |
| 4 | Factor consolidation (OSAP + JKP + Qlib + IPCA) → **v1.1** | ⚪ not started |
| 5 | ML meta-learner (Triple-Barrier + Meta-Labeling + Conformal) + SHAP | ⚪ not started |
| 6 | Sentiment v2 (FinBERT + Whisper + 8-K Lazy Prices) | ⚪ not started |
| 7 | Regime + portfolio (Student-t HMM + NCO + TDA) → **v1.5** | ⚪ not started |
| 8 | Universe expansion (S&P 1500) | ⚪ not started |

**Current focus**: Phase 3 PR 3b — composite + risk overlay (wires pillar functions into orchestrator)

**Phase 3 sub-PR plan** (5 sub-PRs, mobile-friendly slicing):
- ✅ **3a — Pillar feature modules** — DONE 2026-05-08. Foundation only —
  7 feature modules, 30+ metrics, 50+ tests. No production output changes.
- 🟡 **3b — Composite + risk overlay** — NEXT. Wires the new pillar functions
  into `compute/main.py` via `compute/scoring/{normalize,pillars,composite,risk_overlay}.py`.
  Schema bumps to `0.4.0-phase3b`; first production Top-5 rotation.
- ⚪ 3c — Fair price ensemble + price history (separate `stocks/history/{TICKER}.json`).
- ⚪ 3d — Charts (Pillar Radar + Fair Price Bar + Price History) + about page.
- ⚪ 3e — README polish + tag **v1.0**.

**Next deliverable**: 30+ classical metrics per pillar, normalized
sector-relative, 8 pillar scores combining into a real composite, plus the
ensemble fair price (DCF + Graham + RIM + multiples) and risk overlay
vetoes. Tag **v1.0** at the end of Phase 3.

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
