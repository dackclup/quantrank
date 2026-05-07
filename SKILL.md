---
name: quantrank-app
description: Build, modify, or extend QuantRank — a static-site US equity ranking application that combines fundamental, technical, factor, sentiment, and ML analysis into a 0-100 composite StockRank with ensemble fair price. Architecture is GITHUB-ACTIONS-FIRST (no backend server, no database) — Python script computes scores weekly and outputs JSON files; Next.js static site reads JSON and renders the UI; everything deploys free via Vercel. Use when the user wants to create QuantRank from scratch, add new analysis pillars or metrics, improve scoring methodology, integrate new free data sources, build the GitHub Actions compute pipeline, design the JSON output schema, build the Next.js static frontend, set up scheduled refresh workflows, deploy to Vercel, or troubleshoot any part of this static ranking system.
---

# QuantRank — Build & Maintenance Skill

A skill for building and extending **QuantRank**, a static-site US equity stock ranking application that ranks stocks 1..N using 60+ classical analysis techniques plus advanced ML/NLP/regime-detection methods.

**Project knowledge file**: `stock_ranking_knowledge.md` (loaded into the project) is the authoritative reference for ALL formulas, data sources, normalization rules. **Always consult it before implementing any analysis technique** — never invent formulas.

**Workflow file**: `WORKFLOW.md` is the phase-by-phase build plan. Always check current phase before working.

---

## Core Project Goal

Build a **static web app** (no backend server, no database) that:
1. Pulls free-tier financial data for US stocks (S&P 500 → S&P 1500 in stages)
2. Computes 60+ classical metrics + advanced sentiment/ML/regime features
3. Normalizes them sector-relative into 8 pillar scores (0-100 each)
4. Combines via meta-learner into a final composite StockRank (0-100)
5. Computes ensemble Fair Price (DCF + Graham + Residual Income + multiples)
6. Surfaces top-5 SHAP explanations per stock
7. Outputs everything as JSON files committed to the repo
8. Refreshes weekly via GitHub Actions cron
9. Renders via Next.js static site deployed on Vercel
10. **Public GitHub repo** — fully reproducible, free GitHub Actions

---

## ⚠️ ARCHITECTURE: STATIC-SITE PATTERN (Option D)

**This is the most important rule. Read carefully.**

### What this app IS:
- A **GitHub Actions cron job** that runs Python weekly to compute rankings
- A **Next.js static site** that reads pre-computed JSON files
- A **public GitHub repo** with auto-committed JSON outputs
- Deployed to **Vercel free tier** with auto-deploy on push

### What this app is NOT:
- ❌ NOT a FastAPI/Flask/Express backend
- ❌ NOT using PostgreSQL/SQLite/MongoDB at runtime
- ❌ NOT making live API calls from the frontend
- ❌ NOT computing scores on user request
- ❌ NOT a real-time/intraday system

### Compute Flow:
```
[GitHub Actions cron, weekly Sunday 22:00 UTC]
    ↓
Python script → fetch data → compute features → output JSON
    ↓
Auto-commit JSON files to public/data/ in repo
    ↓
Push triggers Vercel auto-deploy
    ↓
[User opens site] → Next.js loads pre-computed JSON → renders UI
```

### Why this architecture:
- **Free forever**: Vercel hobby + GitHub Actions on public repo = $0
- **Mobile-friendly dev**: only 1 system to debug (the Python script + GH Actions logs)
- **Fast for users**: pre-computed JSON served via CDN, no DB queries
- **Simple**: no auth, no rate limiting, no API design needed

---

## Required Tech Stack

**DO NOT deviate without explicit approval.**

| Layer | Technology | Why |
|---|---|---|
| Compute Language | Python 3.11+ | All analysis libraries |
| Compute Runtime | GitHub Actions (ubuntu-latest) | Free unlimited on public repos |
| Frontend Framework | Next.js 14+ (App Router, Static Export) | Modern UX, free Vercel deploy |
| Frontend Styling | TailwindCSS | Utility-first, mobile-first |
| Charts | Recharts | React-native, lightweight |
| Data Storage | JSON files in `public/data/` | Committed to repo |
| Hosting | Vercel (frontend) + GitHub (data) | All free |
| Package Manager (Python) | `uv` (or `pip` if needed) | Fast |
| Package Manager (JS) | `npm` | Standard |

**Python libraries**:
```
yfinance, edgartools, fredapi, finnhub-python, praw, pytrends    # Data
pandas, numpy, scipy, statsmodels                                 # Core
ta, pandas-ta, arch, hmmlearn                                     # Analysis
lightgbm, scikit-learn, shap                                      # ML
transformers, torch                                               # FinBERT (optional, heavy)
tenacity, python-dotenv                                           # Utilities
pytest, ruff                                                      # Quality
```

---

## Mandatory Repository Structure

```
quantrank/
├── README.md                       # Public README with disclaimer
├── PHASE_STATUS.md                 # Current phase tracker
├── pyproject.toml                  # Python dependencies
├── .gitignore                      # Includes .env, __pycache__, node_modules
│
├── .github/workflows/
│   ├── compute-rankings.yml        # Sun 22:00 UTC: weekly compute
│   ├── compute-monthly.yml         # 1st of month: ML retrain
│   ├── ci.yml                      # Lint + test on PR
│   └── manual-trigger.yml          # workflow_dispatch for ad-hoc runs
│
├── compute/                        # Python compute pipeline (replaces backend)
│   ├── __init__.py
│   ├── config.py                   # Paths, defaults (no env vars in code)
│   ├── main.py                     # Entry: orchestrates full weekly run
│   │
│   ├── ingest/                     # Data fetchers — one module per source
│   │   ├── universe.py             # S&P 500 from Wikipedia
│   │   ├── prices.py               # yfinance OHLCV
│   │   ├── fundamentals.py         # edgartools (SEC EDGAR)
│   │   ├── insider.py              # edgartools Form 4 (Phase 4)
│   │   ├── institutional.py        # edgartools 13F (Phase 4)
│   │   ├── macro.py                # fredapi (Phase 5)
│   │   ├── news.py                 # finnhub + yfinance (Phase 4)
│   │   └── reddit.py               # PRAW (Phase 4)
│   │
│   ├── features/                   # Pure feature computation
│   │   ├── fundamental.py          # Piotroski, Altman Z, Beneish M
│   │   ├── value.py                # P/E, P/B, EV/EBITDA, Graham
│   │   ├── quality.py              # ROE, ROIC, MSCI 3-desc, QMJ
│   │   ├── growth.py               # CAGR, SGR, PRAT
│   │   ├── momentum.py             # 12-1, 6-1, 52w high, RSI
│   │   ├── technical.py            # MACD, ADX, ATR, Ichimoku
│   │   ├── health.py               # Current/Quick, D/E, IC
│   │   ├── risk.py                 # Sharpe, Sortino, MaxDD, GARCH
│   │   ├── sentiment.py            # FinBERT, Reddit (Phase 4)
│   │   ├── advanced_valuation.py   # EVA, CFROI, Tobin's Q (Phase 4)
│   │   ├── anomaly.py              # PEAD, IVOL, asset growth (Phase 4)
│   │   └── macro_regime.py         # HMM, sector rotation (Phase 5)
│   │
│   ├── scoring/
│   │   ├── normalize.py            # Winsorize, sector-rank, percentile
│   │   ├── pillars.py              # Aggregate features → 8 pillars
│   │   ├── composite.py            # Weighted sum → 0-100
│   │   ├── fair_price.py           # DCF + Graham + RIM + multiples
│   │   └── risk_overlay.py         # Beneish/Sloan/Z″ vetoes
│   │
│   ├── ml/                         # Phase 5
│   │   ├── train.py                # LightGBM walk-forward
│   │   ├── validate.py             # IC, IR, PBO
│   │   └── shap_explain.py         # Top-5 factors per stock
│   │
│   ├── output/                     # JSON writers
│   │   ├── writer.py               # Atomic JSON output to public/data/
│   │   └── schemas.py              # Pydantic models for JSON validation
│   │
│   └── cache/                      # Local dev cache (gitignored)
│
├── tests/
│   ├── test_features/              # Golden-value tests per metric
│   ├── test_scoring/
│   └── test_ingest/
│
├── frontend/                       # Next.js static site
│   ├── package.json
│   ├── next.config.js              # output: 'export' for static
│   ├── tailwind.config.ts
│   ├── app/
│   │   ├── layout.tsx              # Header + disclaimer banner
│   │   ├── page.tsx                # Ranking table (reads rankings.json)
│   │   ├── stock/[ticker]/page.tsx # generateStaticParams from JSON
│   │   ├── about/page.tsx          # Methodology, disclaimers
│   │   └── globals.css
│   ├── components/
│   │   ├── RankingTable.tsx
│   │   ├── PillarRadar.tsx
│   │   ├── FairPriceChart.tsx
│   │   ├── ScoreBadge.tsx
│   │   ├── MosBadge.tsx
│   │   └── ShapBars.tsx
│   ├── lib/
│   │   ├── data.ts                 # Helpers to read JSON at build time
│   │   └── types.ts                # TypeScript matches schemas.py
│   └── public/
│       └── data/                   # ⭐ JSON OUTPUT FROM COMPUTE
│           ├── metadata.json        # last_update, version, universe_size
│           ├── rankings.json        # array of 500 ranked stocks (summary)
│           └── stocks/
│               ├── AAPL.json        # full detail per ticker
│               ├── MSFT.json
│               └── ...
│
└── docs/
    ├── stock_ranking_knowledge.md   # THE reference (~1600 lines)
    ├── ARCHITECTURE.md              # This static-site pattern explained
    └── METHODOLOGY.md               # User-facing: how scoring works
```

---

## JSON Output Schema (Critical Contract)

The `compute/` and `frontend/` are decoupled by these JSON contracts. **Never break them.**

### `public/data/metadata.json`
```json
{
  "version": "1.0.0",
  "last_update_utc": "2026-05-11T22:00:00Z",
  "next_update_utc": "2026-05-18T22:00:00Z",
  "universe": "SP500",
  "universe_size": 503,
  "compute_run_id": "abc123def",
  "git_commit": "..."
}
```

### `public/data/rankings.json` (summary, ~1MB for 500 stocks)
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
      "health": 95, "sentiment": 70, "ml": 80, "risk": 88
    }
  },
  ...
]
```

### `public/data/stocks/{TICKER}.json` (full detail, ~10KB each)
```json
{
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "sector": "Information Technology",
  "industry": "Technology Hardware",
  "market_cap": 3400000000000,
  "current_price": 220.15,
  "rank": 1,
  "composite_score": 87.4,
  "pillar_scores": { ... },
  "raw_metrics": {
    "piotroski_f_score": 8,
    "altman_z_prime": 4.2,
    "beneish_m_score": -2.85,
    "pe_ratio": 28.5,
    "roe": 0.156,
    ...
  },
  "fair_price": {
    "median": 245.30,
    "max": 285.00,
    "margin_of_safety_pct": 10.3,
    "methods": [
      {"name": "DCF", "value": 240.50, "applicable": true},
      {"name": "Graham Number", "value": null, "applicable": false},
      {"name": "Residual Income", "value": 252.10, "applicable": true},
      {"name": "P/E × Forward EPS", "value": 235.40, "applicable": true},
      {"name": "EV/EBITDA peer", "value": 248.20, "applicable": true},
      {"name": "P/B × BVPS", "value": 250.30, "applicable": true}
    ]
  },
  "top5_factors": [
    {"feature": "roic", "shap_value": 0.12, "direction": "+"},
    {"feature": "gross_profitability", "shap_value": 0.09, "direction": "+"},
    {"feature": "momentum_12_1", "shap_value": 0.08, "direction": "+"},
    {"feature": "debt_to_ebitda", "shap_value": -0.06, "direction": "−"},
    {"feature": "fcf_yield", "shap_value": 0.05, "direction": "+"}
  ],
  "score_history": [
    {"date": "2026-05-04", "score": 86.1},
    {"date": "2026-05-11", "score": 87.4}
  ],
  "data_quality": {
    "missing_metrics": [],
    "imputed_metrics": ["analyst_revisions"],
    "filing_lag_days": 38
  }
}
```

---

## Core Behavior Rules

### Rule 1: Always reference the knowledge document
Before implementing any analysis technique, **read the relevant section of `stock_ranking_knowledge.md`**. Use the formula AS WRITTEN. Never reinvent or simplify without justification.

### Rule 2: Phase discipline
Work in **phases per `WORKFLOW.md`**. Do not skip ahead. Each phase produces a working deliverable.

### Rule 3: GitHub-Actions-first development
Since the user develops on mobile (no local Python/Node), **all testing/running happens in GitHub Actions**. This means:
- Every PR must have a CI workflow that catches errors before merge
- Use `workflow_dispatch` for ad-hoc compute runs from the GitHub mobile app UI
- Logs in GitHub Actions are the primary debugging tool
- Cache aggressively in Actions (`actions/cache@v4`) to avoid 6+ minute runs every time

### Rule 4: Free-tier first
Every API call must respect free-tier limits:
- Use `yfinance` first; fall back to FMP/SimFin only when necessary
- Cache to `compute/cache/` during dev runs (gitignored)
- Implement `tenacity` retry with exponential backoff on 429
- For weekly compute, all of S&P 500 should fit in <2000 free GH Actions minutes/month even with retries

### Rule 5: Point-in-time data discipline
**Look-ahead bias kills backtests.** Every fundamental MUST use `filing_date`, not `period_end`. 13F is lagged 45 days. Form 4 uses `transactionDate`. SEC EDGAR exposes both — always use the filing date.

### Rule 6: Sector-relative for fundamentals
Quality, Value, Growth, Profitability — **always rank within GICS sector**, never globally. Use absolute ranking only for Risk and Momentum. **Always exclude financials/utilities from Magic Formula and asset-turnover metrics.**

### Rule 7: Missing data → sector median
- `<50%` of pillar's metrics available → set pillar to neutral (50) and flag.
- Single metric NaN → impute as **sector median** (NEVER global median).
- Never propagate NaN; record imputed fields in `data_quality.imputed_metrics`.

### Rule 8: Test golden values
For every fundamental metric, write a unit test against a **known-correct value** for at least 1 ticker (e.g., AAPL Piotroski F-Score for FY2024 = X). This catches yfinance field-name changes early.

### Rule 9: JSON schema is sacred
The `frontend/` consumes JSON with strict expectations. **Never break the schema mid-development.** If you must change it:
1. Bump the `version` field in metadata.json.
2. Update `compute/output/schemas.py` (Pydantic).
3. Update `frontend/lib/types.ts` (TypeScript).
4. Update example JSON in this SKILL.md.
5. Test both compute output AND frontend rendering.

### Rule 10: No paid data, no real-money, no live trading
This app is for **research and educational ranking only**. The README and frontend MUST display this disclaimer. Never integrate live trading APIs.

### Rule 11: Trademark caution
Never use "Jitta" anywhere. The project name is **QuantRank**.

### Rule 12: Atomic JSON writes
Always write to a `.tmp` file then `os.rename()` to final path. Never write partial JSON. If compute fails halfway, the previous JSON must remain valid so the site doesn't break.

---

## When the user asks for...

### "Build the project from scratch"
1. Read `WORKFLOW.md` Phase 0.
2. Confirm: project name = QuantRank, repo = public, Vercel deploy.
3. Execute Phase 0 tasks. Update `PHASE_STATUS.md` at end.

### "Add a new metric"
1. Search `stock_ranking_knowledge.md` for the technique.
2. Identify pillar (per Section 21 / Quick Reference A).
3. Add function to `compute/features/<pillar>.py` with golden-value test.
4. Update pillar aggregation in `compute/scoring/pillars.py`.
5. Add field to `raw_metrics` in `compute/output/schemas.py`.
6. Update TypeScript types in `frontend/lib/types.ts`.
7. Run CI to verify.

### "Add a new data source"
1. Check Section 5 of knowledge doc — already covered?
2. New file in `compute/ingest/<source>.py` matching existing pattern (cache, retry).
3. Add API key (if needed) to GitHub Actions secrets — never commit.
4. Document rate limits in module docstring.

### "Improve accuracy"
1. Manage expectations per Section 28 (realistic = 2-4% net alpha).
2. Check what's NOT yet implemented — usually sentiment (Phase 4) or ML (Phase 5).
3. Don't add LSTM before LightGBM works.
4. Always validate via IC, IR, PBO before claiming improvement.

### "The site is broken / shows old data"
1. Check `PHASE_STATUS.md` for current phase.
2. Check latest GitHub Actions run — failed?
3. Check `public/data/metadata.json` — what's `last_update_utc`?
4. Check Vercel deployment logs.
5. Recovery: trigger `manual-trigger.yml` workflow via GitHub mobile app.

### "Deploy to production"
1. **One-time setup** (Phase 0):
   - Push repo to GitHub (public).
   - Connect repo to Vercel (auto-detects Next.js).
   - Set Vercel build settings: root = `frontend/`, output = `out/`.
   - First deploy will fail (no JSON yet) — that's expected.
2. **Trigger first compute**: GitHub Actions tab → `compute-rankings.yml` → Run workflow.
3. **Verify**: After ~10 min, JSON appears in `public/data/`, Vercel rebuilds, site goes live.
4. No backend deployment needed.

---

## Anti-Patterns to Refuse

| Anti-pattern | Why bad | Correct approach |
|---|---|---|
| Adding FastAPI/Flask backend | Architecture is static (Option D) | Output JSON from GitHub Actions |
| Adding PostgreSQL/SQLite | No runtime DB by design | Files in `public/data/` |
| Calling APIs from frontend | Defeats static-site purpose, cost money | Pre-compute, read JSON at build |
| Hardcoding API keys | Repo is public! | GitHub Actions secrets |
| Using `period_end` for backtest | Look-ahead bias | Use `filing_date` from EDGAR |
| Global z-score across financials + tech | Sector-distorting | Sector-relative percentile rank |
| Imputing NaN with 0 | Biases scores wildly | Sector median (Rule 7) |
| LSTM before LightGBM works | Overengineering | Tree-based first |
| Daily refresh in GitHub Actions | Wastes free minutes | Weekly only |
| Skipping golden-value tests | yfinance changes silently | Mandatory per metric |
| Claiming >10% alpha | Almost certainly overfit | Run PBO, deflated Sharpe |
| Live trading endpoints | Out of scope, regulatory risk | Read-only ranking display only |
| Partial JSON writes | Breaks frontend | Atomic write via temp file (Rule 12) |
| Using "Jitta" name | Trademark | "QuantRank" |

---

## Communication Style

The user develops on mobile and may not be a quant expert.
- **Formulas**: link to section in `stock_ranking_knowledge.md`, don't re-derive.
- **Realistic expectations**: cite Section 28 (~2-4% net alpha realistic).
- **Mobile constraints**: prefer GitHub Actions runs over local debugging suggestions.
- **Iteration**: each GH Actions run takes 3-10 min; budget time wisely.
- **Phase status**: always say "we are in Phase X; next deliverable is Y".

When user is excited about a new technique: "great — let's add it after Phase X stabilizes."

---

## End State Definition (v1.0)

QuantRank v1.0 ships when:
- [ ] Public GitHub repo `quantrank` exists
- [ ] Weekly GitHub Actions cron runs successfully
- [ ] S&P 500 universe ingested with ≥10 years of data
- [ ] All 8 pillars computed for every stock (Phases 1-3 done)
- [ ] Composite StockRank (0-100) per stock
- [ ] Fair Price ensemble (Median + Max) per stock
- [ ] JSON files in `public/data/` valid against schema
- [ ] Vercel-deployed Next.js site shows ranking table + detail page
- [ ] README has disclaimer + architecture diagram + methodology link
- [ ] Mobile responsive, Lighthouse >85
- [ ] Tag `v1.0` on GitHub

After v1.0: Phase 4 (sentiment) → Phase 5 (ML) → Phase 6 (regime + validation) → Phase 7 (universe expansion to S&P 1500).
