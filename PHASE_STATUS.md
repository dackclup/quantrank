# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | ✅ DONE — 2026-05-07 |
| 1 | Universe + prices ingestion | ✅ DONE — 2026-05-08 |
| 2 | Fundamentals via SEC EDGAR | 🟡 in progress |
| 3 | Classical features + composite → **v1.0** | ⚪ not started |
| 4 | Sentiment & alternative data | ⚪ not started |
| 5 | ML meta-learner + SHAP | ⚪ not started |
| 6 | Regime detection + validation → **v1.5** | ⚪ not started |
| 7 | Universe expansion (S&P 1500) | ⚪ not started |

**Current focus**: Phase 2 — Fundamentals via SEC EDGAR (in progress, PR open)

**Next deliverable**: SEC EDGAR financials per ticker (point-in-time correct
via `filing_date`), feeding raw_metrics in `stocks/{TICKER}.json` and
generating per-stock detail pages.

**Live URL**: https://quantrank.vercel.app
**Verified production**: https://quantrank.vercel.app — 502 stocks ranked by
12-1 momentum, schema `0.2.0-phase1`, mobile-responsive table live.

## Phase 2 acceptance checklist

- [ ] All ~502 tickers have fundamental data attempts (≥80% with revenue + net_income)
- [ ] `filed_date` populated for every fundamental row in cache parquet
- [ ] Golden-value `@network` tests pass for AAPL/MSFT/GOOGL/JPM/XOM
- [ ] Stock detail pages render at `/stock/AAPL`, `/stock/MSFT`, etc.
- [ ] `FISV` → `FI` normalization working
- [ ] Cross-sectional null rate <5% on revenue, net_income, total_assets
- [ ] Compute time <30 min cache hit / <60 min cold
- [ ] Schema bumped to `0.3.0-phase2` in metadata.json
- [ ] CI green on the Phase 2 PR before merge

## Resolved housekeeping
- ✅ `EDGAR_USER_AGENT` secret added to GitHub Actions secrets
- 🟡 `FISV` → `FI` ticker rename — fixed in Phase 2 PR (TICKER_OVERRIDES in
  `compute/ingest/universe.py`)

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
