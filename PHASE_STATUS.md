# QuantRank — Phase Status

| # | Phase | Status |
|---|---|---|
| 0 | Scaffolding + first deploy | 🟡 in progress |
| 1 | Universe + prices ingestion | ⚪ not started |
| 2 | Fundamentals via SEC EDGAR | ⚪ not started |
| 3 | Classical features + composite → **v1.0** | ⚪ not started |
| 4 | Sentiment & alternative data | ⚪ not started |
| 5 | ML meta-learner + SHAP | ⚪ not started |
| 6 | Regime detection + validation → **v1.5** | ⚪ not started |
| 7 | Universe expansion (S&P 1500) | ⚪ not started |

**Current focus**: Phase 0 — scaffolding + first Vercel deploy

**Next deliverable**: Empty Vercel-deployed site at the project URL showing the
"QuantRank — coming soon" placeholder, plus a green CI run.

**Live URL**: _set after Vercel hookup_

## Phase 0 acceptance checklist

- [x] Public GitHub repo exists
- [ ] Directory tree per `SKILL.md` "Mandatory Repository Structure" — done in this PR
- [ ] `ci.yml` green on first push
- [ ] `compute-rankings.yml` succeeds when manually dispatched (no-op stub)
- [ ] Vercel project connected, first deploy "Ready"
- [ ] `frontend/public/data/metadata.json` placeholder visible at the site URL
- [x] `PHASE_STATUS.md` committed
- [x] `README.md` has disclaimer + architecture diagram + methodology link

> Update this file at the end of every phase. The next phase's prompt to
> Claude Code starts with: _"Read PHASE_STATUS.md. We're in Phase X."_
