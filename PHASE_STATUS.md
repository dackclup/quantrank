# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | ✅ DONE — 2026-05-07 |
| 1 | Universe + prices ingestion | 🟡 in progress |
| 2 | Fundamentals via SEC EDGAR | ⚪ not started |
| 3 | Classical features + composite → **v1.0** | ⚪ not started |
| 4 | Sentiment & alternative data | ⚪ not started |
| 5 | ML meta-learner + SHAP | ⚪ not started |
| 6 | Regime detection + validation → **v1.5** | ⚪ not started |
| 7 | Universe expansion (S&P 1500) | ⚪ not started |

**Current focus**: Phase 1 — Universe + Prices Ingestion (in progress, PR open)

**Next deliverable**: `rankings.json` with 500 S&P stocks ranked by momentum;
working ranking table on the live site.

**Live URL**: https://quantrank.vercel.app

## Phase 1 acceptance checklist

- [ ] `compute-rankings.yml` runs in <15 min on first try
- [ ] `frontend/public/data/rankings.json` exists with ~500 stocks ranked by momentum
- [ ] `metadata.json` reflects accurate timestamp + schema `0.2.0-phase1`
- [ ] Vercel URL shows working sortable/filterable table after auto-redeploy
- [ ] Mobile view of ranking table is readable
- [ ] CI green on the Phase 1 PR before merge

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
