# WORKFLOW — QuantRank Build Plan
**Phase-by-phase guide for building QuantRank from scratch via Claude Code on mobile**

> Companion to `SKILL.md` and `stock_ranking_knowledge.md`. Each phase produces a **working, testable deliverable visible at the public Vercel URL**. Designed for mobile-only development (Claude Code app + GitHub mobile + Vercel mobile).

---

## How This Workflow Adapts to Mobile-Only Dev

You cannot run Python or Node locally. All execution happens in **GitHub Actions** (compute) and **Vercel** (frontend deploy). This means:

1. **No "run it locally" steps** — every test runs in CI on push.
2. **`workflow_dispatch` everywhere** — manual trigger from GitHub mobile app for debugging.
3. **Smaller commits, more pushes** — iterate via CI logs.
4. **Visual verification = Vercel preview URL** on every PR.
5. **`PHASE_STATUS.md`** in repo tracks where you are. Update after every phase.

---

## Tools You'll Use Daily

| Tool | What for |
|---|---|
| **Claude Code (mobile app)** | Edit code, commit, push to GitHub |
| **GitHub mobile app** | View Actions logs, trigger workflow_dispatch, review PRs |
| **Vercel mobile app** | View deployment status + preview URL |
| **Mobile browser** | Open Vercel preview URL to see live site |

---

## Phase Overview (7 Phases to v1.0, 3 more for v1.x)

| Phase | Goal | Deliverable | Est. effort (full-time) |
|---|---|---|---|
| 0 | Project scaffolding + first deploy | Empty site live on Vercel | 1 day |
| 1 | Universe + prices ingestion | rankings.json with stub scores | 2 days |
| 2 | Fundamentals from SEC EDGAR | Real data flowing into JSON | 3 days |
| 3 | Classical features + composite | Working v1.0 with 30+ metrics | 5 days |
| **v1.0 SHIPS** | | **Tag v1.0** | |
| 4 | Sentiment + alt-data | FinBERT news + insider Form 4 | 4 days |
| 5 | ML meta-learner + SHAP | LightGBM ranker + explainability | 3 days |
| 6 | Regime + validation | HMM weights + backtest report | 4 days |
| 7 | Universe expansion | S&P 1500 | 2 days |

**To v1.0**: ~11 working days. Realistic calendar (full-time): 2-3 weeks.

---

# PHASE 0 — Scaffolding + First Deploy

**Goal**: Empty `quantrank` repo on GitHub, deployed to Vercel, showing "Hello World" — proves the pipeline works before adding any analysis.

## Tasks

### 0.1 Create GitHub repo
On GitHub mobile or web:
- Repo name: `quantrank`
- Visibility: **Public** (free unlimited GitHub Actions)
- License: MIT
- Add Python `.gitignore`
- Initialize with README

### 0.2 Tell Claude Code to clone & set up structure
Initial prompt:
> "We're starting Phase 0 of QuantRank. Read SKILL.md and WORKFLOW.md. Create the full directory structure per SKILL.md. Add stub README, .gitignore, pyproject.toml, package.json, all empty __init__.py files. Add a stub PHASE_STATUS.md. Add the four .github/workflows/ files (ci.yml, compute-rankings.yml, compute-monthly.yml, manual-trigger.yml) — these can be near-empty for now but valid YAML. Push to main."

### 0.3 Set up Python deps in `pyproject.toml`
Use `[project]` table with these dependencies (Phase 0 only needs basics):
```toml
[project]
name = "quantrank-compute"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pandas>=2.2",
  "numpy>=1.26",
  "pydantic>=2.6",
  "tenacity>=8.2",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.4"]
```
More deps added per phase to keep CI fast.

### 0.4 Initial Next.js app
In `frontend/`:
- `package.json` with Next.js 14, React 18, Tailwind, Recharts
- `next.config.js` with `output: 'export'` (static export)
- `app/page.tsx` with a placeholder "QuantRank — coming soon"
- Create stub `public/data/metadata.json` with placeholder values

### 0.5 GitHub Actions: ci.yml (most important)
This runs on every PR/push to main:
```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request:
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e .[dev]
      - run: ruff check .
      - run: pytest -v
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - working-directory: frontend
        run: npm ci && npm run build
```

### 0.6 Stub `compute-rankings.yml` (cron, but no-op for now)
```yaml
name: Compute Rankings
on:
  schedule: [{ cron: "0 22 * * 0" }]  # Sunday 22:00 UTC
  workflow_dispatch:
jobs:
  compute:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e .
      - run: echo "Phase 0 stub — real compute in Phase 1+"
```

### 0.7 Connect Vercel
On Vercel mobile/web:
- Import the `quantrank` GitHub repo
- Framework preset: Next.js
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `out`
- Deploy

You'll get a URL like `quantrank-xxx.vercel.app` showing "QuantRank — coming soon".

### 0.8 PHASE_STATUS.md
```markdown
# QuantRank Phase Status

- [x] Phase 0: Scaffolding + first deploy ✅ (DATE)
- [ ] Phase 1: Universe + prices
- [ ] Phase 2: Fundamentals
- [ ] Phase 3: Classical features → v1.0
- [ ] Phase 4: Sentiment & alt-data
- [ ] Phase 5: ML meta-learner
- [ ] Phase 6: Regime + validation
- [ ] Phase 7: Universe expansion

**Current focus**: Phase 1 — Universe + prices ingestion
**Live URL**: https://quantrank-xxx.vercel.app
```

## Phase 0 Acceptance Criteria
- [ ] Repo exists at `github.com/<user>/quantrank` (public)
- [ ] CI workflow green on first push
- [ ] Site live at Vercel URL showing placeholder
- [ ] `compute-rankings.yml` succeeds when triggered manually (no-op stub)
- [ ] PHASE_STATUS.md committed

---

# PHASE 1 — Universe + Prices Ingestion

**Goal**: GitHub Actions fetches S&P 500 prices, computes a stub composite (just based on momentum), outputs valid `rankings.json`, and the frontend displays a real ranking table.

**Knowledge ref**: Section 5 (Free Data Stack), Section 25 (Caching), Section 7.3 (momentum).

## Tasks

### 1.1 Add deps to pyproject.toml
```toml
yfinance = ">=0.2.40"
pandas-ta = ">=0.3"
beautifulsoup4 = ">=4.12"  # for Wikipedia scrape
lxml = ">=5.0"
```

### 1.2 Universe fetcher
`compute/ingest/universe.py`:
- Function `get_sp500_constituents() -> pd.DataFrame` scraping `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
- Returns: `ticker, name, sector, sub_industry, cik`
- Cache to `compute/cache/universe.parquet` (gitignored)

### 1.3 Price fetcher
`compute/ingest/prices.py`:
- `fetch_prices(ticker: str, period: str = "5y") -> pd.DataFrame`
- Use `yf.download(ticker, period=period, auto_adjust=False, progress=False)`
- Wrap with `tenacity.retry` (3 attempts, exp backoff)
- Returns OHLCV DataFrame

### 1.4 Stub features
`compute/features/momentum.py`:
- `momentum_12_1(prices: pd.DataFrame) -> float`: cumulative return month t-12 to t-1
- This is the only feature in Phase 1 — proves the pipeline.

### 1.5 Output schemas
`compute/output/schemas.py`:
```python
from pydantic import BaseModel
from typing import Optional

class StockSummary(BaseModel):
    rank: int
    ticker: str
    name: str
    sector: str
    composite_score: float
    current_price: float
    fair_price: Optional[float] = None
    max_fair_price: Optional[float] = None
    margin_of_safety_pct: Optional[float] = None
    pillar_scores: dict[str, float]

class Metadata(BaseModel):
    version: str
    last_update_utc: str
    universe: str
    universe_size: int
    git_commit: str
```

### 1.6 Main orchestrator
`compute/main.py`:
```python
def run_weekly_compute():
    universe = get_sp500_constituents()
    results = []
    for _, row in universe.iterrows():
        prices = fetch_prices(row["ticker"])
        mom = momentum_12_1(prices)
        results.append({
            "ticker": row["ticker"],
            "name": row["name"],
            "sector": row["sector"],
            "current_price": float(prices["Close"].iloc[-1]),
            "momentum_12_1": mom,
        })
    df = pd.DataFrame(results)
    df["composite_score"] = df["momentum_12_1"].rank(pct=True) * 100
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    write_rankings_json(df)
    write_metadata_json(...)
```

### 1.7 JSON writer with atomic writes
`compute/output/writer.py`:
```python
def atomic_write_json(path: Path, data: dict | list):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(path)
```

### 1.8 Update `compute-rankings.yml`
```yaml
- run: pip install -e .
- run: python -m compute.main
- name: Commit JSON outputs
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add public/data/
    git diff --cached --quiet || git commit -m "chore: update rankings $(date -u +%Y-%m-%d)"
    git push
```
Add `permissions: { contents: write }` to workflow.

### 1.9 Frontend reads real JSON
`frontend/app/page.tsx`:
```tsx
import rankings from "@/public/data/rankings.json";
import metadata from "@/public/data/metadata.json";

export default function HomePage() {
  return <RankingTable data={rankings} lastUpdate={metadata.last_update_utc} />;
}
```
`components/RankingTable.tsx`: simple sortable table with rank, ticker, name, sector, score.

### 1.10 Trigger first run
On GitHub mobile: Actions tab → "Compute Rankings" → "Run workflow". Watch logs (~10 min for 500 tickers with retries).

## Phase 1 Acceptance Criteria
- [ ] `compute-rankings.yml` runs in <15 min on first try
- [ ] `public/data/rankings.json` exists with 500 stocks ranked by momentum
- [ ] `metadata.json` reflects accurate timestamp
- [ ] Vercel URL shows working table after auto-redeploy
- [ ] Mobile view of ranking table is readable

---

# PHASE 2 — Fundamentals via SEC EDGAR

**Goal**: Pull real annual + quarterly financials, point-in-time correct (`filing_date`).

**Knowledge ref**: Section 5 (SEC EDGAR), Section 27 (schema), Rule 5 (point-in-time).

## Tasks

### 2.1 Add deps
```toml
edgartools = ">=2.30"
```

### 2.2 EDGAR fetcher
`compute/ingest/fundamentals.py`:
```python
from edgar import Company, set_identity
import os
set_identity(os.environ["EDGAR_USER_AGENT"])  # "Your Name email@example.com"

def fetch_fundamentals(ticker: str) -> pd.DataFrame:
    company = Company(ticker)
    facts = company.get_facts()
    # extract: Revenues, NetIncomeLoss, Assets, Liabilities,
    #          StockholdersEquity, Cash, OperatingCashFlow, CapEx
    # MUST keep both period_end AND filed_date columns
    return df
```

### 2.3 GitHub Actions secret
On GitHub mobile: Settings → Secrets and variables → Actions → New secret:
- `EDGAR_USER_AGENT` = `"Your Name email@example.com"` (SEC requires email)

Update `compute-rankings.yml`:
```yaml
env:
  EDGAR_USER_AGENT: ${{ secrets.EDGAR_USER_AGENT }}
```

### 2.4 Cache strategy
EDGAR doesn't update fundamentals daily — cache aggressively:
- Use `actions/cache@v4` with key based on quarter:
```yaml
- uses: actions/cache@v4
  with:
    path: compute/cache/fundamentals
    key: fundamentals-${{ hashFiles('public/data/metadata.json') }}-q${{ steps.quarter.outputs.q }}
```
- Per-ticker cache file: `compute/cache/fundamentals/{cik}.parquet`
- Re-fetch only if last cached `filed_date` < 45 days ago

### 2.5 Golden value tests
`tests/test_features/test_fundamentals.py`:
```python
def test_aapl_fy2024_revenue():
    df = fetch_fundamentals("AAPL")
    fy2024 = df[df["period_end"] == "2024-09-28"]
    assert abs(fy2024["revenue"].iloc[0] - 391_035_000_000) / 391_035_000_000 < 0.01
```
Pick 5 reference tickers (AAPL, MSFT, GOOGL, JPM, XOM).

### 2.6 Update main orchestrator
After prices, fetch fundamentals for each ticker, attach to dataframe. JSON output now has more raw_metrics.

### 2.7 Update detail JSON
Each `public/data/stocks/{TICKER}.json` now has:
```json
{
  "raw_metrics": {
    "revenue_ttm": 391035000000,
    "net_income_ttm": 93736000000,
    "total_assets": 364980000000,
    ...
  }
}
```

### 2.8 Generate per-stock detail pages
`frontend/app/stock/[ticker]/page.tsx`:
```tsx
export async function generateStaticParams() {
  const rankings = await import("@/public/data/rankings.json");
  return rankings.default.map((s) => ({ ticker: s.ticker }));
}
```
Renders simple detail page showing ticker, name, sector, raw_metrics table.

## Phase 2 Acceptance Criteria
- [ ] All 500 tickers have ≥5 years annual fundamentals
- [ ] `filing_date` populated for every row
- [ ] Golden-value tests pass for 5 reference tickers
- [ ] Stock detail pages exist at `/stock/AAPL` etc.
- [ ] Cross-sectional null rate <5% on revenue, net income, total assets

---

# PHASE 3 — Classical Features + Composite → v1.0

**Goal**: All 30+ classical metrics implemented, 8 pillar scores, full composite, fair price ensemble. **Tag v1.0.**

**Knowledge ref**: Sections 6-11 (formulas), Sections 21 (normalization), Section 10 (fair price ensemble).

## Tasks

### 3.1 Implement features per pillar
For EACH pillar, follow this pattern:
1. Create `compute/features/<pillar>.py` with one pure function per metric.
2. Each function: takes DataFrame of raw data, returns Series indexed by ticker.
3. Write unit test with golden value (look up known correct value).
4. Add to schema.

**Quality** (`compute/features/quality.py`): Piotroski F-Score, ROE, ROIC, Gross Profitability, MSCI 3-descriptor.

**Value** (`compute/features/value.py`): P/E, P/B, P/S, EV/EBITDA, EV/FCF, Earnings Yield (Greenblatt), Graham Number, Tobin's Q.

**Growth** (`compute/features/growth.py`): Revenue/EPS/FCF CAGR (3y, 5y), Sustainable Growth Rate.

**Momentum** (`compute/features/momentum.py`): 12-1, 6-1, 3-1, 52w-high distance, RSI, MACD signal.

**Health** (`compute/features/health.py`): Current/Quick Ratio, D/E, Interest Coverage, Altman Z″, Debt/EBITDA.

**Risk** (`compute/features/risk.py`): σ_252, β (vs SPY), Sharpe, Sortino, MaxDD, Calmar.

**Technical** (`compute/features/technical.py`): ADX, ATR, Bollinger %B, OBV slope, MFI.

**Profitability** (`compute/features/profitability.py`): GM/OM/NM, ROA, Asset Turnover, Cash Conversion Cycle.

### 3.2 Sector exclusions config
`compute/scoring/sector_rules.py`:
```python
SECTOR_BLACKLIST = {
    "magic_formula": {"Financials", "Utilities", "Real Estate"},
    "asset_turnover": {"Financials"},
    "altman_z_x5": "Information Technology"  # use Z″ instead
}
```

### 3.3 Normalization layer
`compute/scoring/normalize.py`:
- `winsorize(s, lower=0.05, upper=0.95)`
- `sector_neutralize(s, sectors)` — subtract sector median
- `cross_sectional_rank(s)` → 0-100

### 3.4 Pillar aggregation
`compute/scoring/pillars.py`:
- Compute pillar score = avg of normalized member metrics
- Output: DataFrame indexed by ticker, 8 columns (quality, value, growth, momentum, health, risk, technical, profitability)
- For Phase 3 (no sentiment/ML yet), redistribute their weights:

```python
# Phase 3 weights (sentiment + ML will come later)
PHASE3_WEIGHTS = {
    "quality": 0.30,        # was 0.25, +0.05 from sentiment
    "value": 0.25,          # was 0.20, +0.05 from sentiment
    "growth": 0.13,         # was 0.10, +0.03 from sentiment+ML
    "momentum": 0.13,       # was 0.10, +0.03
    "health": 0.10,         # was unweighted, now explicit
    "risk": 0.05,
    "technical": 0.04,
}
# Total: 1.00
```

### 3.5 Composite + risk overlay
`compute/scoring/composite.py`:
- Weighted sum → 0-100
`compute/scoring/risk_overlay.py`:
- Beneish M-Score > -1.78 → cap composite at 60
- Sloan accruals top decile → -10 points
- Altman Z″ < 1.23 → cap composite at 50

### 3.6 Fair Price ensemble
`compute/scoring/fair_price.py`:
- `dcf_two_stage(fcf_history, wacc=0.10, terminal_g=0.025) -> float`
- `graham_number(eps_3yr_avg, bvps) -> float`
- `residual_income(book_value, roe_forecast, cost_of_equity=0.10) -> float`
- `multiples_based(metric, peer_median, divisor) -> float`
- `ensemble_fair_price(estimates: list) -> dict` → median + 95th percentile

### 3.7 Final JSON output (full schema)
Now `rankings.json` and `stocks/{TICKER}.json` match the full schemas in SKILL.md.

### 3.8 Frontend polish
- `RankingTable`: sortable columns, sector filter, search, pagination (50/page), color-coded score badges
- `app/stock/[ticker]/page.tsx`: pillar radar chart (Recharts RadarChart), fair price chart (current/fair/max bar), raw metrics table, MoS badge
- `app/about/page.tsx`: methodology summary, disclaimer
- Mobile-responsive throughout
- Dark mode via Tailwind `dark:` classes (optional)

### 3.9 README polish
Add to README.md:
- Architecture diagram (ascii or mermaid)
- Setup section ("just clone and push, GitHub Actions does the rest")
- Disclaimer (large, visible)
- Methodology link
- Tech stack
- Live URL

### 3.10 Tag v1.0
```bash
git tag v1.0
git push origin v1.0
```

## Phase 3 / v1.0 Acceptance Criteria
- [ ] All 30+ classical metrics implemented; golden value tests pass
- [ ] StockRank computed for all S&P 500 weekly
- [ ] Top-10 are sensible (high ROE, low D/E, decent momentum)
- [ ] Bottom-10 are sensible (distressed, low quality)
- [ ] Risk vetoes catch known bad cases
- [ ] Fair Price exists for all stocks with ≥3 applicable methods
- [ ] Mobile site has table + detail page + radar + fair price
- [ ] Lighthouse mobile score >85
- [ ] README professional with disclaimer
- [ ] **v1.0 tag pushed**

---

# PHASE 4 — Sentiment & Alternative Data

**Goal**: Add Sentiment pillar (15% weight) backed by FinBERT news + Form 4 + Reddit.

**Knowledge ref**: Section 12.

⚠️ **Heads up**: This phase adds heavy ML deps (transformers, torch ~2GB). GitHub Actions runs will go from ~10 min to ~25 min. Cache aggressively.

## Tasks

### 4.1 Add deps (carefully)
```toml
[project.optional-dependencies]
sentiment = [
  "transformers>=4.40",
  "torch>=2.2 --index-url https://download.pytorch.org/whl/cpu",
  "praw>=7.7",
  "finnhub-python>=2.4",
]
```
Use CPU-only torch to save 1.5GB.

### 4.2 GitHub Actions cache for HF models
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/huggingface
    key: hf-finbert-v1
```

### 4.3 News ingestion
`compute/ingest/news.py`:
- `yfinance Ticker.news` (free, no key)
- `finnhub /company-news` (free 60/min, set `FINNHUB_API_KEY` secret)
- Dedupe by URL hash
- Cache scored articles by hash so FinBERT runs once per article

### 4.4 FinBERT scoring
`compute/features/sentiment.py`:
```python
from transformers import pipeline
finbert = pipeline("sentiment-analysis",
                    model="ProsusAI/finbert", top_k=None)

def score_text(text: str) -> dict:
    out = finbert(text[:512])
    probs = {x["label"]: x["score"] for x in out[0]}
    return {**probs, "score": probs["positive"] - probs["negative"]}
```
Aggregate weekly per ticker: weighted mean by recency (half-life 3 days).

### 4.5 Insider Form 4
`compute/ingest/insider.py` using `edgartools`:
- Pull last 90 days of Form 4 for each ticker
- Compute net insider buy $, role-weighted (CEO/CFO=3, Director=2, 10%=1)
- Cluster buying score (≥2 distinct insiders within 30 days)

### 4.6 Reddit (PRAW)
GitHub secrets needed:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` = `"quantrank/1.0 by <username>"`

`compute/ingest/reddit.py`:
- Pull r/wallstreetbets, r/stocks, r/investing daily (Phase 4 = weekly OK)
- Extract tickers via regex + S&P 500 whitelist
- Compute mention_count, acceleration, bullish_ratio (FinBERT on context)

### 4.7 Sentiment pillar aggregation
`compute/scoring/pillars.py`:
- 50% news FinBERT (recency-weighted)
- 30% insider Form 4 cluster
- 20% Reddit acceleration

### 4.8 Restore weights
Add sentiment pillar back at 15%, redistribute from quality/value:
```python
WEIGHTS_V14 = {
    "quality": 0.25, "value": 0.20, "growth": 0.10, "momentum": 0.10,
    "health": 0.10, "risk": 0.05, "technical": 0.05, "sentiment": 0.15,
}  # Total: 1.00
```

### 4.9 Update JSON schema
Add `sentiment` to `pillar_scores`. Add `news_summary` to detail JSON:
```json
"sentiment_breakdown": {
  "news_finbert": 72,
  "insider_buying": 85,
  "reddit_attention": 60,
  "article_count_7d": 12
}
```

## Phase 4 Acceptance Criteria
- [ ] Sentiment pillar populated for stocks with ≥3 articles in 7 days
- [ ] No-news stocks → sentiment = 50 + flagged in `data_quality`
- [ ] FinBERT scores cached (re-runs are fast)
- [ ] Insider cluster signals visible (e.g., recent CEO buys boost rank)
- [ ] Total compute time still <30 min weekly

---

# PHASE 5 — ML Meta-Learner + SHAP

**Goal**: LightGBM ranker on all features → ML pillar (10%); SHAP top-5 in UI.

**Knowledge ref**: Section 13.

## Tasks

### 5.1 Add deps
```toml
ml = [
  "lightgbm>=4.3",
  "scikit-learn>=1.4",
  "shap>=0.45",
]
```

### 5.2 Historical training data
This is the trickiest phase. Need to backfill features for past dates:
- Re-run feature computation for each Sunday in last 5 years
- Cache results in `compute/cache/historical_features/{date}.parquet`
- Compute forward 1m return as target
- This backfill is a separate one-time workflow (`backfill-history.yml` with `workflow_dispatch`)

### 5.3 LightGBM training
`compute/ml/train.py`:
```python
import lightgbm as lgb
model = lgb.LGBMRanker(
    objective="lambdarank",
    num_leaves=31, learning_rate=0.03, n_estimators=500,
    min_child_samples=200, feature_fraction=0.7, bagging_fraction=0.8,
)
model.fit(X_train, y_train, group=group_train)
```
- Walk-forward: train years 1-5, predict year 6, roll
- Save monthly versioned: `models/lgbm_v{YYYYMMDD}.pkl`

### 5.4 Validation
`compute/ml/validate.py`:
- IC, IR per fold (mean IC ≥ 0.02 required)
- Decile spread with Newey-West t-stat
- IC decay at 1, 5, 21, 63 days
- **Hard fail**: if mean IC < 0.02, don't deploy new model

### 5.5 ML pillar score
At each Sunday compute, latest model predicts current cross-section → percentile rank → 0-100.

### 5.6 SHAP per stock
```python
import shap
explainer = shap.TreeExplainer(model)
shap_vals = explainer.shap_values(X_today)
# top-5 features by abs(shap_value), with sign
```
Persist top-5 to `top5_factors` in detail JSON.

### 5.7 Frontend SHAP bars
`components/ShapBars.tsx` — horizontal bar chart showing each factor's contribution (+/- color-coded).

### 5.8 Monthly retrain workflow
`compute-monthly.yml`:
```yaml
on:
  schedule: [{ cron: "0 3 1 * *" }]  # 1st of month, 03:00 UTC
  workflow_dispatch:
```
Runs training + validation. If new model improves IC, commits `models/lgbm_v{date}.pkl`. Otherwise keeps old.

### 5.9 Restore ML weight
```python
WEIGHTS_V15 = {
    "quality": 0.22, "value": 0.18, "growth": 0.10, "momentum": 0.10,
    "health": 0.08, "risk": 0.05, "technical": 0.04,
    "sentiment": 0.13, "ml": 0.10,
}
```

## Phase 5 Acceptance Criteria
- [ ] Historical backfill completed (5 years of weekly features)
- [ ] Mean IC ≥ 0.02 on out-of-sample folds
- [ ] PBO < 0.5 (will compute fully in Phase 6)
- [ ] SHAP top-5 visible in UI per stock
- [ ] Monthly retrain workflow successful

---

# PHASE 6 — Regime Detection + Validation Framework

**Goal**: HMM gates pillar weights by regime; full backtest harness with PBO.

**Knowledge ref**: Sections 15, 22, 23.

## Tasks

### 6.1 Add deps
```toml
quant = [
  "fredapi>=0.5",
  "hmmlearn>=0.3",
  "arch>=7.0",
  "alphalens-reloaded>=0.4",  # alphalens fork
]
```

### 6.2 Macro ingestion
`compute/ingest/macro.py`:
- GitHub secret: `FRED_API_KEY`
- Pull T10Y2Y, VIXCLS, BAMLH0A0HYM2, UNRATE weekly

### 6.3 HMM regime
`compute/features/macro_regime.py`:
- 3-state Gaussian HMM on (SPY returns, VIX change, term spread change)
- Label states by mean return: bull, neutral, bear
- Persist current state to `public/data/metadata.json`

### 6.4 Regime-conditional weights
`compute/scoring/composite.py`:
- Estimate `IR(pillar | regime)` from rolling 3-yr history
- Weights per Sunday: `w_i = max(IR_i^r, 0) / Σ`
- Apply gentle tilts (±20% from neutral defaults)

### 6.5 Backtest harness
`compute/backtest/run_backtest.py`:
- Equal-weight top decile vs SPY
- 40 bps round-trip cost
- Output: IC, IR, decile spread, alpha, Sharpe, MaxDD, Calmar, turnover, deflated Sharpe

### 6.6 PBO via CSCV
`compute/backtest/cscv.py` — port López de Prado snippet (~30 lines):
- Split returns into S=16 blocks
- C(16,8) = 12,870 train/test combos
- PBO = % of times best in-sample is below median OOS
- Hard requirement: PBO < 0.5

### 6.7 Backtest report
- `compute/backtest/report.py` outputs `public/data/backtest_report.json`
- New page `frontend/app/backtest/page.tsx` shows IC time series, decile spread, PBO

### 6.8 Tag v1.5
```bash
git tag v1.5
git push origin v1.5
```

## Phase 6 Acceptance Criteria
- [ ] HMM regime updates weekly, visible in metadata
- [ ] Pillar weights actually shift across regimes
- [ ] Backtest report shows IC, IR, PBO
- [ ] Net-of-cost top-decile alpha reported honestly (>2% target, but report whatever)
- [ ] PBO < 0.5
- [ ] **v1.5 tag pushed**

---

# PHASE 7 — Universe Expansion

**Goal**: Expand from S&P 500 → S&P 1500 (or Russell 2000 if data permits).

## Tasks

### 7.1 Source larger universe
- S&P 1500 = SP500 + S&P 400 (mid-cap) + S&P 600 (small-cap)
- Wikipedia has constituents for all three

### 7.2 Performance considerations
- 1500 stocks × all features will push GH Actions toward time limit (6 hours hard cap on free public, but soft pain at ~30 min)
- Parallelize ticker processing with `concurrent.futures.ThreadPoolExecutor`
- Add `--universe` CLI flag: `python -m compute.main --universe SP500|SP1500`

### 7.3 Frontend pagination
Now showing 1500 stocks → must paginate / virtualize the table. Use `@tanstack/react-virtual`.

### 7.4 Data quality monitoring
- Smaller stocks have worse data — track null rates per universe segment
- Display in `data_quality` per stock

## Phase 7 Acceptance Criteria
- [ ] S&P 1500 ranked weekly
- [ ] Compute time <90 min
- [ ] Frontend handles 1500-row table smoothly on mobile
- [ ] Null rate <10% in mid-cap segment, <20% in small-cap

---

# Maintenance Cycle (Post-v1.5)

| Task | Cadence | Notes |
|---|---|---|
| Pillar weight retune | Quarterly | Use last 12 months IR |
| ML hyperparameter retune | Quarterly | Optuna on training fold only |
| Free data source rotation | As needed | Watch yfinance breaks |
| Disclaimers + methodology page updates | Quarterly | Keep accurate |
| GitHub Actions minutes monitoring | Monthly | Public repo = unlimited but be efficient |

## When to STOP adding features
After v1.5 + Phase 7, **resist scope creep** unless:
1. Mean IC has plateaued/declined for 2+ quarters AND
2. New addition has academic evidence of incremental IC > 0.01 AND
3. Free data exists.

Most "improvements" past v1.5 are noise + maintenance burden.

---

# Mobile Workflow Cheat Sheet

| Situation | Do this on mobile |
|---|---|
| Starting work session | Open Claude Code → "What phase are we in? Read PHASE_STATUS.md" |
| After Claude Code commit | Open GitHub mobile app → check Actions tab → wait for green |
| Failed Actions run | GitHub mobile → Actions → tap failed run → read logs → tell Claude Code error |
| Want to manually trigger compute | GitHub mobile → Actions → "Compute Rankings" → "Run workflow" |
| Want to see live site | Vercel mobile app → tap latest deploy → "Visit" |
| Backtest looks "too good" | "Run PBO and deflated Sharpe before trusting any number >5%" |
| Adding a metric | Tell Claude Code section number from knowledge doc |
| Stuck on yfinance error | Tell Claude Code: "yfinance broke again, check field names per Section 11.1 of knowledge" |

---

# Initial Prompts to Give Claude Code

## Session 1: Phase 0 kickoff
> Read SKILL.md, WORKFLOW.md, and stock_ranking_knowledge.md. We're starting Phase 0 of QuantRank. Execute Phase 0 task 0.2 onward: create the full directory structure per SKILL.md, including all stub files, the four .github/workflows YAMLs, pyproject.toml with Phase 0 deps only, frontend/ Next.js skeleton with `output: 'export'`, stub PHASE_STATUS.md, and a README with disclaimer. Push to main when CI is green. List anything I need to do manually (Vercel hookup, secrets, etc.).

## Session 2: After Phase 0 lands, Phase 1
> Phase 0 is done; site is live with placeholder. Now do Phase 1 tasks 1.1-1.10. Output rankings.json with momentum-only stub composite. Update RankingTable component to render real JSON. Verify by triggering compute-rankings.yml manually.

## Subsequent sessions
> Read PHASE_STATUS.md. We're in Phase X. Continue from task X.Y.

---

**End of WORKFLOW.md** — combined with `SKILL.md` and `stock_ranking_knowledge.md`, this is everything Claude Code needs to build QuantRank from your phone.
