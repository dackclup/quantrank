# QuantRank

> **Open-source stock ranking for ~1,500 US equities — eight fundamental
> and price-based pillars combined into a single 0–100 composite score,
> recomputed after every US trading day. A research tool, not advice.**

QuantRank ranks the S&P 1500 — the S&P 500 large-caps plus the S&P 400
mid-caps and S&P 600 small-caps. Each stock gets a score on eight pillars
(value, quality, profitability, growth, health, momentum, technical, risk)
built from SEC filings and market data. The pillars roll up into one
composite rank. A defense layer of risk flags then checks each name for
accounting red flags — the kind documented in academic fraud research —
and marks suspicious ones "cautious" rather than letting them quietly top
the list.

Alongside the rank, every stock gets a fair-price estimate: six valuation
methods (Graham number, three sector-relative multiples, residual income,
and discounted cash flow) reduced to a median, with a margin of safety
against the current price. When the inputs look corrupt, the pipeline
prints nothing rather than a confident wrong number.

The whole thing is a static web app. A Python pipeline runs in GitHub
Actions on a Mon-Fri cron (after US market close), computes every score,
and writes JSON files into the repo. A Next.js static site reads those
files at build time and is served from Vercel's free tier. No backend.
No database. No live API calls from the browser. Every score traces to a
git commit, so any ranking you see can be reproduced and audited.

**What it's for:** screening and research. QuantRank tells you which
stocks score well on its model and why — it does not tell you what to buy.
Historical performance shown anywhere in the app comes from a backtest,
and a backtest is not a live track record. Read the disclaimer below
before doing anything else.

---

## ⚠️ Disclaimer — please read

**QuantRank is for educational and research purposes only.**

- Nothing here is investment advice, a recommendation, or an offer to buy or sell securities.
- Scores and "fair prices" are model outputs derived from public data. They can be wrong, stale, or misleading.
- **Do not use these scores for real-money trading decisions.**
- Past performance does not predict future results.
- The author is not a registered investment adviser.
- This project does not connect to a brokerage and never will.

**Honest limits of quantitative analysis** — full breakdown in the
[Honest Limitations](#honest-limitations) section below. The short version:

- Quantitative fraud detection has irreducible false-positive (~30% in
  broad market) and false-negative (~25-40%) rates. Defense flags
  indicate elevated risk, **not** confirmed fraud.
- Madoff-style fabrication (where revenue, cash, and counter-parties are
  all fictitious) is **undetectable** by any system based on filed
  financials.
- Published anomalies typically decay 30-60% post-publication
  (McLean-Pontiff 2016).

If you're not comfortable losing 100% of any capital you might allocate based
on quantitative models, do not use this app for investing.

---

## Honest Limitations

QuantRank ships academic-quality defenses across two waves:

- **v1.0 layer** (Phase 3a-3e + 4g): Altman Z″, Sloan accruals, net-
  stock-issuance, going-concern phrase scan, 8-K Item 4.02 non-
  reliance veto, Beneish M-score, Dechow F-score, tangible-book
  sanity guard.
- **Phase 4.5 manipulation cluster** (4.5a-4.5f): sector-relative
  Sloan, Beneish + Dechow soft-veto thresholds, `manipulation_triple_
  flag` joint gate, restatement-history scan (10-K/A 5y), late-filing
  notification (Form 12b-25 1y, Bartov & Konchitchki 2017
  *Accounting Horizons* — citation corrected 2026-05-26 from the
  prior hallucinated Bartov-Lai-Yeung 2002 *JAR* attribution),
  Roychowdhury 2006 Real Earnings Management 3-proxy, accruals
  momentum (Δ TATA over 3y), Burgstahler-Dichev 1997 loss-avoidance
  kink (thresholds 10× rescaled in Phase 2.4 / PR #163 to $50M /
  $0.50 for the S&P 500 universe), and the **`manipulation_index`
  0-100 rollup** with a soft 10-point composite penalty (PR 4.5f,
  tag `v1.2.0`).
- **Phase 4.5e Form-4 insider clustering** (PR #222, 2026-05-23):
  two new annotate flags from SEC Form 4 insider-trade data —
  `insider_sell_cluster` (≥ 3 distinct insiders, opportunistic
  transaction codes `{S, D}`, ≥ $1M cohort-aggregate, 30-day
  rolling window; Cohen-Malloy-Pomorski 2012 *JFE*) and
  `c_suite_unusual_sell` (≥ 2 distinct CEO/CFO/President insiders
  in the same window; Jeng-Metrick-Zeckhauser 2003 *JAR* §V).
  PR #224 added the 10b5-1 pre-scheduled-trade contamination
  filter via the document-level `<aff10b5One>` boolean +
  footnote-text regex per Jagolinzer 2009 (40-60% FP rate
  reduction). Combined weight 5+3 = 8 pts under the delta-not-
  total semantic when both fire on the strict-superset path.
- **Phase 2.2 high-confidence irregularity signature** (PR #165,
  2026-05-21): `restatement_high_confidence` annotate fires when a
  10-K/A or 10-Q/A amendment co-occurs with an 8-K Item 4.02 "non-
  reliance" filing within 90 days — Hennes-Leone-Miller 2008 *TAR*
  irregularity signature with PPV ~70% vs bare `restatement_history`'s
  ~30%. Bare flag retained at weight 5; combined weight 8 when
  high_confidence fires.
- **Issue #11 closure** (PR #166, 2026-05-21): `_avg_3y_roe` removes
  the legacy single-period-equity fallback that preserved the original
  Issue #11 bug for ~30% of the universe even after PR 4c added the
  per-year denominator path. New `insufficient_history_for_roe` skip
  reason distinguishes "missing input data" from a real value-trap
  signal, so the ensemble no longer emits spurious `value_trap_risk`
  warnings when RIM is skipped for incomplete equity history.

Despite all this, several classes of manipulation and several
structural realities remain outside what any filed-financials-based
screener can address. Each release ships with the honest accounting
below — readers should weight QuantRank's outputs accordingly.

### Frauds we cannot catch

Pure financial-statement screeners can only detect manipulation that
leaves a footprint in the filed numbers. Four manipulation classes
leave no detectable footprint:

1. **Madoff-style total fabrication.** When revenue, cash, customers,
   and bank confirmations are all fictitious, the screener has no
   anchor to a real economy to compare against. Detection requires
   forensic accounting + bank cross-confirmation outside SEC EDGAR's
   reach.
2. **Off-shore related-party round-trips.** Wirecard's Asian "third-
   party acquirers" recorded as customers + suppliers cancel out on the
   consolidated balance sheet. The ratios all behave normally because
   the cash never existed but the offsetting fiction is symmetric.
3. **Audit-firm complicity.** When the audit itself is fraudulent
   (Arthur Andersen / Enron pattern), the 10-K is a primary source for
   manipulated numbers — no quantitative cross-check inside the same
   document can break the loop.
4. **Post-acquisition baseline reset.** Fraud disguised by an
   acquisition that resets the accounting baseline (Tyco-pattern roll-
   ups) — the year-over-year ratios all reset with the acquisition, so
   prior-period manipulation gets washed out of the comparison window.

### Realistic error rates

Every defense layer ships with documented false-positive and false-
negative rates from the academic literature. v1.0 uses these
unmodified — no proprietary "tuning":

| Defense | False positive rate | False negative rate | Source |
|---|---|---|---|
| Beneish M-score (M > −2.22) | ~30% broad market, ~15-20% S&P 500 | ~25-40% | Beneish 1999, Beneish 2022 |
| Dechow F-score (F > 2.45) | ~27% broad market | ~27% (sensitivity 73%) | Dechow et al. 2011 |
| Going-concern phrase scan | ~1-3% (post-MD&A restriction) | ~10-15% | Mayew-Sethuraman-Venkatachalam 2015 |
| Altman Z″ < 1.10 (distress) | ~5-10% manufacturing | ~20% (FE-heavy sectors) | Altman 1968, Altman 2017 |
| Sloan accruals top-decile | ~10% (sector-confounded) | n/a (definitional) | Sloan 1996 |
| Net stock issuance top-decile | ~10% (definitional) | n/a (definitional) | Pontiff-Woodgate 2008 |

**All defense flags are risk stratifiers, not fraud verdicts.** A
flagged stock is a "look harder" signal, not a "this is fraud" signal.
Multiple flags compounding (e.g., Beneish + Dechow + going-concern
simultaneously) is the actionable pattern.

### Anomaly decay reality

Academic factor research has a well-documented decay curve:

- **Out-of-sample drop**: ~26% lower returns vs the original in-sample
  period (McLean-Pontiff 2016).
- **Post-publication drop**: an additional ~32% lower (publication-
  informed trading erodes the edge).
- **Cumulative**: ~58% of the original effect, on average, by year 5
  post-publication.

This applies to most of QuantRank's classical signals (value, momentum,
quality, low-vol). The methodology page tracks expected vs realized IC
where comparable; the rolling-IC decay monitor will land in Phase 4+.

### Free-data fragility

QuantRank uses only free data sources, which trade cost for fragility:

- **yfinance is an unofficial scraper** — multiple 2023-2024 incidents
  broke fundamental endpoints without warning. Daily-close prices have
  been the most reliable surface; pre-market and after-hours data are
  not.
- **SEC EDGAR XBRL has documented 2025 taxonomy drift** — the
  `CostOfGoodsAndServicesSold` vs `CostOfRevenue` split, the
  `IntangibleAssetsNetExcludingGoodwill` vs `OtherIntangibleAssetsNet`
  variant — every Phase 3 PR added a fallback chain for one of these.
  Some filers report values only under tags the parser doesn't know
  about yet, and the data goes missing silently.
- A cross-source validator (Phase 4) catches large discrepancies but
  not small systematic biases.

### Diminishing returns on stacking defenses

Beneish-Vorst 2021 measured marginal AAER capture across an ensemble of
fraud signals:

- Beneish + Dechow + Sloan + going-concern = ~4 signals
- Adding a 5th signal (e.g., Bao-Ke 2020 ML) captures **less than 5%
  additional AAERs** beyond the first 4
- Adding more produces proportionally more false positives without
  proportional true positives

QuantRank's v1.0 defense set was intentionally fixed at this
"diminishing-returns inflection point." Phase 4.5 (v1.2) extended
the layer specifically for **structural-disclosure signals** that
the accrual-targeting v1.0 set misses — restatement history, late-
filing notifications, real (vs accrual) earnings management,
loss-avoidance patterns. These complement rather than stack on top
of the v1.0 accrual signals (Beneish + Sloan + Dechow), so the
marginal-AAER curve flattens differently from the Beneish-Vorst
2021 estimate. Future versions will **rotate signals based on IC
decay** rather than continuing to add layers. Treat the post-4.5
defense list as ceiling, not floor.

**What `manipulation_index` does and does not do**: the 4.5f rollup
combines the above flags into a single 0-100 risk score with a
soft 10-point composite penalty. The penalty is **informational
only** — the displayed ranking still uses the raw composite score
per the annotate-and-veto-Top-N pattern (SKILL.md Rule 16). This is
intentional: penalizing the rank introduces more error than it
removes when fraud-detection FP rates run 15-30% (Beneish-Vorst
2021), so the penalty exists as a UI signal for users, not as a
correction to the canonical composite.

### What QuantRank is — and is not

**QuantRank is**:
- A risk-stratifier and screener built from public filings + free data
- An educational research tool with transparent methodology
- A pre-computed JSON pipeline tied to a git commit (every score is
  reproducible)

**QuantRank is not**:
- A fraud guarantor — flags indicate elevated risk, not confirmed fraud
- A backtested live-trading strategy — anomaly decay is real and
  unpredictable in direction
- A registered investment adviser — the author is not, and this is not
  investment advice
- A connection to any brokerage — and will not become one

See [`docs/RESEARCH_FINDINGS.md`](docs/RESEARCH_FINDINGS.md) for the
academic bibliography backing each defense layer.

---

## Architecture

```mermaid
flowchart LR
    A[GitHub Actions cron<br/>Mon-Fri 22:00 UTC] -->|run daily| B[Python compute pipeline]
    B -->|fetch| C[(yfinance / SEC EDGAR<br/>FRED / Finnhub / Reddit)]
    B -->|write| D[JSON files in<br/>frontend/public/data/]
    D -->|git push| E[GitHub repo]
    E -->|webhook| F[Vercel build]
    F -->|next build --output export| G[Static HTML/CSS/JS on CDN]
    H[User browser] -->|fetch| G
```

**Why this design (Option D — static site):**
- **Free forever**: public GitHub repo = unlimited Actions minutes; Vercel hobby tier = unlimited static hosting.
- **One system to debug**: only the Python script + the GitHub Actions logs.
- **Fast for users**: pre-computed JSON served via CDN — no DB queries, no rate limits.
- **Reproducible**: every score is tied to a git commit.

This is **not** a FastAPI/Flask backend, **not** a database, and **not** a
live-data system. See `SKILL.md` for the full architecture rules.

---

## Tech stack

| Layer | Tool |
|---|---|
| Compute language | Python 3.11+ |
| Compute runtime | GitHub Actions (`ubuntu-latest`) |
| Frontend framework | Next.js 14 (App Router, static export) |
| Styling | Tailwind CSS |
| Charts | Recharts |
| Data storage | JSON files in `frontend/public/data/` |
| Hosting | Vercel (frontend) + GitHub (data) |
| Free data sources | yfinance, edgartools, fredapi, finnhub-python, PRAW |
| ML | LightGBM + SHAP (Phase 5+) |

---

## Setup

You don't need to run anything locally. The whole app builds in CI.

1. **Push** this repo to GitHub as a **public** repository.
2. **Connect Vercel**:
   - vercel.com → "Add New Project" → import the repo.
   - Framework preset: **Next.js**.
   - Root directory: `frontend`.
   - Build command: `npm run build`.
   - Output directory: `out`.
   - Production branch: `main`.
   - Click Deploy.
3. **Trigger first compute** (after Phase 1 lands): GitHub → Actions → "Compute Rankings" → "Run workflow".
4. **Done.** From now on, every Sunday at 22:00 UTC the pipeline refreshes the JSON, commits it, and Vercel auto-deploys.

### Required GitHub secrets — by phase

| Phase | Secret | Why |
|---|---|---|
| 0 | _none_ | Stub workflow only |
| 1 | _none_ | yfinance + Wikipedia are unauthenticated |
| 2 | `EDGAR_USER_AGENT` | SEC requires `"<Your Name> <email>"` for EDGAR access |
| 4 | `FINNHUB_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | News + Reddit sentiment |
| 6 | `FRED_API_KEY` | Macro / regime detection |

Add secrets at: **Repo → Settings → Secrets and variables → Actions → New repository secret**.

---

## Project status

See [`PHASE_STATUS.md`](./PHASE_STATUS.md) for the current build phase and
acceptance checklist.

## Methodology

See [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) for the user-facing
methodology summary, and [`docs/stock_ranking_knowledge.md`](./docs/stock_ranking_knowledge.md)
for the full formula reference (~1600 lines covering fundamental, technical,
factor, sentiment, ML, regime, and validation techniques).

Architecture rules: [`SKILL.md`](./SKILL.md) and [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).
Phase-by-phase build plan: [`WORKFLOW.md`](./WORKFLOW.md).

---

## License

MIT — see [`LICENSE`](./LICENSE).
