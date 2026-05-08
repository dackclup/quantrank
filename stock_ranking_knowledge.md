# Stock Ranking App — Complete Knowledge Base
**A unified, code-ready reference for building a state-of-the-art US equity ranking application**

> This document is the consolidated project knowledge for an LLM coding agent (Claude Code) to implement a multi-pillar, multi-discipline stock ranking system. It combines (A) classical fundamental/technical/factor/risk techniques and (B) advanced ML, NLP, alternative-data, regime-detection, and validation techniques — all implementable with **free or low-cost data sources** for **weekly/monthly refresh**.

---

## Table of Contents

**PART I — APP CONCEPT & ARCHITECTURE**
1. [App Overview & Output](#part-i-1)
2. [Recommended Tech Stack](#part-i-2)
3. [End-to-End Architecture](#part-i-3)
4. [Pillar Weighting & Scoring Philosophy](#part-i-4)
5. [Free Data Stack Summary](#part-i-5)

**PART II — CLASSICAL ANALYSIS TECHNIQUES (60+)**
6. [Fundamental Analysis](#part-ii-6)
7. [Technical Indicators](#part-ii-7)
8. [Quantitative / Factor Investing](#part-ii-8)
9. [Risk Metrics](#part-ii-9)
10. [Valuation Models — Ensemble Fair Price](#part-ii-10)
11. [Growth, Profitability, Financial Health](#part-ii-11)

**PART III — ADVANCED TECHNIQUES**
12. [Sentiment Analysis & Alternative Data](#part-iii-12)
13. [Machine Learning Pipeline](#part-iii-13)
14. [Advanced Quant — HRP, Black-Litterman, Kelly](#part-iii-14)
15. [Macro & Regime Detection](#part-iii-15)
16. [Microstructure / Volume / Flow](#part-iii-16)
17. [Advanced Valuation (EVA, CFROI, Tobin's Q)](#part-iii-17)
18. [Behavioral & Anomaly Factors](#part-iii-18)
19. [Advanced Risk Analysis](#part-iii-19)
20. [Corporate Events & Catalysts](#part-iii-20)

**PART IV — SCORING, RANKING, VALIDATION**
21. [Composite Score Construction](#part-iv-21)
22. [Backtesting & Validation Framework](#part-iv-22)
23. [Ensemble & Meta-Learning](#part-iv-23)
24. [Performance Metrics for the App](#part-iv-24)

**PART V — IMPLEMENTATION GUIDE**
25. [Data Caching & Refresh Cadence](#part-v-25)
26. [Rate-Limit Management](#part-v-26)
27. [Suggested Database Schema](#part-v-27)
28. [Realistic Accuracy Expectations](#part-v-28)
29. [Caveats & Pitfalls](#part-v-29)

**PART VI — RESEARCH-BACKED STRETCH ADDITIONS (Phase 4+)** ⭐
30. [Why Option B (Research-Backed Roadmap)](#part-vi-30)
31. [Factor Consolidation Layer (Phase 4)](#part-vi-31)
32. [ML Enhancements (Phase 5)](#part-vi-32)
33. [Sentiment v2 (Phase 6)](#part-vi-33)
34. [Regime + Portfolio v2 (Phase 7)](#part-vi-34)
35. [Honest Decay & Replication Caveats](#part-vi-35)

---

# PART I — APP CONCEPT & ARCHITECTURE

<a id="part-i-1"></a>
## 1. App Overview & Output

### 1.1 Purpose
Build a stock-ranking application for **US equities** (S&P 500 → S&P 1500 → Russell 3000 universe) that combines **classical fundamental analysis, technical indicators, factor investing, sentiment analysis, machine learning, regime detection, and risk metrics** into a single 0–100 composite **StockRank**, plus an ensemble **Fair Price** estimate.

### 1.2 Core Outputs (Per Stock)
| Output | Description | Range |
|---|---|---|
| **Rank** | Position in universe (1 = best) | 1 to N |
| **Composite Score** | Final ranking score | 0–100 |
| **Pillar Sub-scores** | Quality, Value, Growth, Momentum, Health, Sentiment, ML, Risk | 0–100 each |
| **Fair Price (median)** | Ensemble fair value | $ |
| **Maximum Fair Price** | 95th-percentile of methods | $ |
| **Margin of Safety %** | (Fair − Current)/Fair | % |
| **Top-5 SHAP factors** | Why the score is what it is | text/values |

### 1.3 Refresh Cadence
- **Daily**: prices, news sentiment, insider Form 4
- **Weekly**: composite score recompute, regime detection
- **Monthly**: full feature recompute, ML retrain
- **Quarterly**: 13F holdings update, hyperparameter retune

---

<a id="part-i-2"></a>
## 2. Recommended Tech Stack

| Layer | Recommendation | Rationale |
|---|---|---|
| **Language** | Python 3.11+ | Universal in quant/finance |
| **Backend Framework** | FastAPI | Async, OpenAPI docs, fast |
| **Database** | PostgreSQL (production) / SQLite (dev) | Time-series + relational mix |
| **Cache Layer** | Parquet files + Redis (optional) | Fast columnar reads |
| **Frontend** | Next.js (React) + TailwindCSS + Recharts | Modern UX, charting |
| **Deployment** | GitHub repo → Railway/Render/Fly.io (backend), Vercel (frontend) | Free tiers exist |
| **Scheduling** | GitHub Actions (cron) or APScheduler | Free, code-as-config |
| **ML Stack** | scikit-learn, LightGBM, XGBoost, SHAP | Tree-based primary |
| **NLP Stack** | transformers (FinBERT), VADER | Domain-tuned |
| **Quant Stack** | pandas, numpy, statsmodels, arch (GARCH), hmmlearn (regimes) | Standard |
| **Portfolio Stack** | PyPortfolioOpt, riskfolio-lib | HRP, Black-Litterman |
| **Backtest** | vectorbt or backtrader, alphalens (factor analysis) | Fast vectorized |
| **Data Sources** | yfinance, edgartools, fredapi, finnhub, PRAW, pytrends | All free |

---

<a id="part-i-3"></a>
## 3. End-to-End Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                       1. DATA INGESTION LAYER                         │
│  • yfinance        → Prices, OHLCV, basic info (daily)                │
│  • edgartools      → 10-K/Q, 8-K, Form 4, 13F (event-driven)         │
│  • fredapi         → Macro indicators (daily)                         │
│  • finnhub         → News + sentiment, insider, fundamentals (daily) │
│  • PRAW (Reddit)   → r/wallstreetbets sentiment (daily)              │
│  • pytrends        → Google Trends search interest (weekly)          │
│  • SimFin / FMP    → Standardized fundamentals (gap-filling)         │
│  ↓                                                                    │
│  Cache: SQLite/Parquet by source+ticker+date                         │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  2. FEATURE COMPUTATION LAYER                          │
│                                                                        │
│  FUNDAMENTAL (from financial statements):                             │
│  • Piotroski F-Score, Altman Z-Score, Beneish M-Score                │
│  • Magic Formula (ROC, EY), Graham Number, PEG                       │
│  • DCF, DDM, Residual Income, Owner Earnings                         │
│  • EVA, CFROI, Tobin's Q, Sloan Accruals                             │
│  • Margin trends, ROIC, Cash Conversion Cycle                        │
│                                                                        │
│  TECHNICAL (from prices):                                              │
│  • RSI, MACD, Bollinger Bands, ADX, ATR, Ichimoku                    │
│  • OBV, MFI, CMF, VWAP, Force Index                                  │
│  • SMA50/200, Golden Cross, % above SMA200                           │
│                                                                        │
│  FACTOR (cross-sectional):                                            │
│  • Value (P/E, P/B, P/S, EV/EBITDA, EV/FCF)                          │
│  • Quality (ROE, D/E, Earnings Variability — MSCI 3-descriptor)      │
│  • Momentum (12-1, 6-1, residual, 52w-high distance)                 │
│  • Low-Vol (σ_252, idiosyncratic vol)                                │
│  • Profitability (Gross Profitability — Novy-Marx)                    │
│                                                                        │
│  SENTIMENT / ALTERNATIVE:                                              │
│  • FinBERT on news + 8-K + earnings call transcripts                 │
│  • Reddit / StockTwits sentiment + mention acceleration              │
│  • Insider Form 4 (CEO/CFO weighted, cluster buying)                 │
│  • 13F smart-money flow (45-day lag)                                 │
│  • Short interest, options PCR, IV skew                              │
│  • Google Trends search acceleration                                  │
│                                                                        │
│  RISK:                                                                │
│  • σ, β, Sharpe, Sortino, MaxDD, Calmar                              │
│  • VaR/CVaR (historical), GARCH(1,1) vol forecast                    │
│  • Skewness, Kurtosis, Ulcer Index                                   │
│                                                                        │
│  MACRO/REGIME:                                                        │
│  • Yield curve, credit spreads, VIX                                   │
│  • HMM 3-state regime (bull/neutral/bear)                            │
│  • Sector rotation phase (early/mid/late/recession)                  │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  3. NORMALIZATION LAYER                               │
│  • Winsorize at 5th/95th percentile                                   │
│  • Sector-neutralize (subtract sector median)                         │
│  • Cross-sectional percentile rank → 0–100                           │
│  • Missing data → sector median (NEVER global mean)                   │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│              4. PILLAR AGGREGATION (each 0–100)                       │
│  Quality | Value | Growth | Momentum | Health | Sentiment | ML | Risk│
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│        5. ML META-LEARNER (LightGBM LambdaRank + SHAP)                │
│  Input: all pillar scores + raw features                              │
│  Target: cross-sectional rank of forward 1m/3m return                │
│  Output: predicted rank → percentile → 0–100                          │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│   6. REGIME-CONDITIONAL META-COMPOSITE                                │
│  Weights of pillars adjusted by HMM regime state                      │
│  Final composite = Σ w_i(regime) × pillar_i                          │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│              7. RISK OVERLAYS                                          │
│  • Beneish M-Score / Sloan accruals → veto top-rank if high           │
│  • Isolation Forest anomaly filter                                    │
│  • Liquidity floor (avg vol > $1M/day)                                │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│       8. FAIR PRICE ENSEMBLE                                          │
│  • DCF (Gordon Growth) + Graham Number + Residual Income             │
│  • Multiples (P/E, EV/EBITDA, P/B, P/S)                              │
│  • Trimmed mean → Fair Price; max → Maximum Fair Price                │
│  • Margin of Safety = (Fair − Current)/Fair                           │
└──────────────────────────────────────────────────────────────────────┘
            ↓
┌──────────────────────────────────────────────────────────────────────┐
│              9. OUTPUT: RANKED TABLE + UI                             │
│  ticker | rank | score | sub-scores | fair$ | max-fair$ | MoS% | top5 SHAP
└──────────────────────────────────────────────────────────────────────┘
```

---

<a id="part-i-4"></a>
## 4. Pillar Weighting & Scoring Philosophy

### 4.1 Default Pillar Weights (Starting Point)

| Pillar | Weight | Rationale |
|---|---|---|
| **Fundamental Quality** | 25% | Long-term anchor; low decay |
| **Value** | 20% | Margin of safety |
| **Growth** | 10% | Forward potential |
| **Momentum** | 10% | Short-term lift |
| **Sentiment / Alt-data** | 15% | Edge vs. classical |
| **ML composite** | 10% | Captures interactions |
| **Macro / Regime** | 5% | Risk-on / risk-off modulator |
| **Risk (low-risk bias)** | 5% | Tail-risk reduction |

These weights should be **re-tuned quarterly** by the meta-learner using recent IR (Information Ratio) of each pillar.

### 4.2 Sector-Relative vs. Absolute
- **Sector-relative**: Quality, Value, Growth, Profitability — banks have systematically different ROE/leverage/P/B from tech firms.
- **Absolute**: Momentum, Risk metrics (volatility, drawdown), Sentiment.
- **Always exclude financials/utilities from Magic Formula and asset-turnover metrics.**

### 4.3 Missing Data Policy
- If <50% of pillar's metrics are available → set pillar to neutral (50) and flag.
- Single metric NaN → impute as **sector median** (NEVER global median).
- Never propagate NaN; always log which fields were imputed.

---

<a id="part-i-5"></a>
## 5. Free Data Stack Summary

| Source | Library | Free Limits | Best Use |
|---|---|---|---|
| **yfinance** | `yfinance` | Unlimited (best-effort, unofficial) | Prices, OHLCV, basic fundamentals, options chains, holders, news |
| **SEC EDGAR** | `edgartools` | Free, no key (UA email) | 10-K/Q, 8-K, Form 4 (insider), 13F (institutional), DEF 14A |
| **FRED** | `fredapi` | Free with key (generous) | All US macro: rates, CPI, UNRATE, INDPRO, VIX, spreads |
| **Finnhub** | `finnhub-python` | 60 calls/min free | News + sentiment, insider transactions, earnings, IPO calendar |
| **Financial Modeling Prep** | REST | 250 calls/day free | Pre-calculated ratios, key metrics, fundamentals |
| **Alpha Vantage** | `alpha_vantage` | 25 calls/day, 5/min | Pre-computed technical indicators |
| **SimFin** | `simfin` | Free CSV/API (5-yr limit) | Bulk standardized fundamentals |
| **Polygon.io** | `polygon-api-client` | 5 calls/min free | Aggregates, splits, dividends |
| **Tiingo** | `tiingo` | 50/hr free | EOD prices, news |
| **NewsAPI** | `newsapi-python` | 100/day free | News headlines |
| **GDELT** | BigQuery | 1 TB/mo free | Global news + tone analysis |
| **Reddit** | `praw` | Generous | r/wallstreetbets, r/stocks sentiment |
| **StockTwits** | REST | Free | User-tagged Bull/Bear sentiment |
| **Google Trends** | `pytrends` | Heavy throttling | Search-interest acceleration |
| **HuggingFace** | `transformers` | Free models | FinBERT, Longformer for transcripts |
| **Cboe** | CSV download | Free | Historical PCR, VIX |
| **Ken French Data** | CSV download | Free | Fama-French factor returns SMB, HML, RMW, CMA, UMD |
| **AQR Datasets** | CSV download | Free | QMJ factor returns |

**ETL strategy**: Incremental updates with disk cache (Parquet), TTL per source, exponential backoff on 429, persistent SQLite for filings.

---

# PART II — CLASSICAL ANALYSIS TECHNIQUES

<a id="part-ii-6"></a>
## 6. Fundamental Analysis

### 6.1 Piotroski F-Score (Stanford, Piotroski 2000)

Score 0–9 (integer); each criterion = 1 point if true.

| # | Category | Criterion | Formula |
|---|----------|-----------|---------|
| 1 | Profitability | Positive Net Income | NI > 0 |
| 2 | Profitability | Positive ROA | NI / Total Assets > 0 |
| 3 | Profitability | Positive Operating Cash Flow | CFO > 0 |
| 4 | Profitability | Quality of Earnings | CFO / TA > ROA |
| 5 | Leverage | Decrease in LT Debt Ratio | LTD_t/TA_t < LTD_{t−1}/TA_{t−1} |
| 6 | Liquidity | Increase in Current Ratio | CR_t > CR_{t−1} |
| 7 | Funding | No New Shares Issued | Shares_t ≤ Shares_{t−1} |
| 8 | Operating | Increase in Gross Margin | GM_t > GM_{t−1} |
| 9 | Operating | Increase in Asset Turnover | (Rev/TA)_t > (Rev/TA)_{t−1} |

**Interpretation**: 8–9 strong, 4–6 neutral, 0–2 weak.
**0–100 normalization**: `(F_Score / 9) × 100`.
**Strengths**: Discrete, explainable. **Limits**: Backward-looking; less useful for growth/tech.

### 6.2 Altman Z-Score (NYU Stern, Altman 1968)

**Original (public manufacturing):**
> **Z = 1.2·X₁ + 1.4·X₂ + 3.3·X₃ + 0.6·X₄ + 1.0·X₅**

Where: X₁ = WC/TA, X₂ = RE/TA, X₃ = EBIT/TA, X₄ = MV(Equity)/Total Liab, X₅ = Sales/TA.
**Zones**: >2.99 Safe, 1.81–2.99 Grey, <1.81 Distress.

**Z″-Score (RECOMMENDED for general US screener — non-manufacturers):**
> **Z″ = 6.56·X₁ + 3.26·X₂ + 6.72·X₃ + 1.05·X₄**

Safe >2.90, Grey 1.23–2.90, Distress <1.23.

**0–100 normalization**: `min(Z, 6) / 6 × 100` or sigmoid `100/(1+exp(−(Z−2.5)))`.

### 6.3 Beneish M-Score (Indiana Kelley, Beneish 1999)

> **M = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI**

| Variable | Formula |
|---|---|
| DSRI | (AR_t/Sales_t) / (AR_{t−1}/Sales_{t−1}) |
| GMI | GM_{t−1} / GM_t |
| AQI | [1−(CA+PP&E+Sec)/TA]_t / same_{t−1} |
| SGI | Sales_t / Sales_{t−1} |
| DEPI | Dep%_{t−1} / Dep%_t |
| SGAI | (SGA/Sales)_t / (SGA/Sales)_{t−1} |
| TATA | (NI − CFO) / TA |
| LVGI | (LTD+CL)/TA_t / same_{t−1} |

**Threshold**: M > −1.78 ⇒ likely manipulator. M < −2.22 ⇒ unlikely.
**0–100 normalization (inverted)**: `clip((−1.78 − M)/2 × 50 + 50, 0, 100)`.
**Famously flagged Enron pre-collapse.** Use as **risk overlay/veto**, not alpha.

### 6.4 Magic Formula (Greenblatt 2005)

> **ROC = EBIT / (Net Working Capital + Net Fixed Assets)**
> **Earnings Yield = EBIT / Enterprise Value**
> EV = Market Cap + Total Debt − Cash

**Procedure**:
1. Universe: market cap > $50M; **exclude financials, utilities, foreign ADRs**.
2. Rank by ROC (high→low) and by EY (high→low).
3. Magic Formula Score = Rank_ROC + Rank_EY (lowest = best).

**0–100**: `100 × (1 − combined_rank/max_combined_rank)`.

### 6.5 Graham Number & Defensive Investor (Graham 1949)

> **Graham Number = √(22.5 × EPS × BVPS)**

Use **3-year average EPS**.
**Buy if** Current Price < Graham Number. **MoS % = (GN − Price)/GN.**

**Defensive Investor 7 Criteria**:
1. Sales > $500M
2. Current Ratio ≥ 2; LT Debt < Net Current Assets
3. Positive EPS for 10 consecutive years
4. Uninterrupted dividends for 20 years
5. ≥33% growth in 3-yr avg EPS over last 10 yrs
6. P/E ≤ 15 (3-yr avg EPS)
7. P/E × P/B ≤ 22.5

**Graham Formula (growth-adjusted, illustrative)**:
> **V = EPS × (8.5 + 2g) × 4.4 / Y** (g = 7-10yr expected growth %, Y = AAA bond yield)

### 6.6 Peter Lynch PEG Ratio

> **PEG = (P/E) / Earnings Growth Rate (%)**

- PEG <0.5 strong buy, 0.5–1.0 attractive, ≈1.0 fair, >2.0 overvalued.
- Dividend-adjusted: PEG = P/E / (Growth + Div Yield).

**0–100 (inverted)**: `clip(100 × (2 − PEG) / 2, 0, 100)`.

### 6.7 Discounted Cash Flow (Simplified 2-Stage)

> **EV = Σ_{t=1..N} FCF_t / (1+WACC)^t + TV / (1+WACC)^N**
> **TV = FCF_N × (1+g) / (WACC − g)**
> **Equity Value = EV − Net Debt; Fair Price = Equity Value / Shares**

**Inputs**:
- FCF = Operating Cash Flow − CapEx
- WACC ≈ 10% default; or via CAPM: rE = Rf + β×(Rm−Rf), Rf = FRED `DGS10`, ERP = 5–6%
- g (perpetual) = 2–3% (cap at GDP growth)
- Project: 5 yrs at historical CAGR (cap 15%) → 3% perpetual

**Reverse DCF**: solve for `g` such that DCF = current price → "implied growth priced in."

### 6.8 Dividend Discount Model (Gordon Growth)

> **P₀ = D₁ / (r − g) = D₀ × (1+g) / (r − g)**

Only meaningful for stable dividend payers (utilities, consumer staples).

### 6.9 Free Cash Flow Yield, Earnings Yield, ROIC, Owner Earnings

| Metric | Formula |
|---|---|
| FCF Yield | FCF / Market Cap (or FCF/EV) |
| Earnings Yield | EPS / Price = 1/(P/E) |
| ROIC | NOPAT / (Total Debt + Equity − Cash); NOPAT = EBIT(1−t) |
| Owner Earnings (Buffett) | NI + D&A + Other Non-cash − Maintenance CapEx ± ΔWC |
| P/Owner Earnings | Price / OE per share |

**Simplified Owner Earnings**: `OE ≈ Operating Cash Flow − CapEx` (= FCF).

---

<a id="part-ii-7"></a>
## 7. Technical Indicators

All inputs: OHLCV from yfinance daily prices. Library: `ta` or `pandas_ta`.

### 7.1 RSI (14)
```
RS = Avg Gain / Avg Loss (Wilder smoothing)
RSI = 100 − 100/(1+RS)
```
>70 overbought, <30 oversold.

### 7.2 MACD
```
MACD = EMA(12) − EMA(26)
Signal = EMA(MACD, 9)
Histogram = MACD − Signal
```

### 7.3 Moving Averages (Golden/Death Cross)
- SMA_n, EMA_n
- Golden Cross: SMA_50 crosses above SMA_200 (bullish)
- Death Cross: SMA_50 crosses below SMA_200 (bearish)
- **Trend score (0–100)**: `100 × (Price − SMA_200)/SMA_200`, clipped [−50,+50] then shifted.

### 7.4 Bollinger Bands (20, 2)
```
Middle = SMA(20); Upper/Lower = Middle ± 2σ_20
%B = (Close − Lower)/(Upper − Lower)
```

### 7.5 Stochastic Oscillator
```
%K = 100 × (Close − Low_14)/(High_14 − Low_14)
%D = SMA(%K, 3)
```
>80 overbought, <20 oversold.

### 7.6 ADX (Wilder, 14) — Trend Strength
```
+DI, −DI from directional movement
DX = 100 × |+DI − −DI|/(+DI + −DI)
ADX = Wilder-smoothed DX over 14 periods
```
<20 weak/no trend; 25–50 strong; >50 very strong.

### 7.7 OBV (Granville)
Cumulative volume signed by close direction. Score by slope or divergence with price.

### 7.8 Money Flow Index (Volume-Weighted RSI, 14)
```
TP = (H+L+C)/3; RMF = TP × Volume
MFI = 100 − 100/(1 + Pos_MF/Neg_MF)
```
>80 overbought, <20 oversold.

### 7.9 ATR (Wilder, 14)
For volatility-based stops/sizing.

### 7.10 Ichimoku Cloud
```
Tenkan = (H_9+L_9)/2; Kijun = (H_26+L_26)/2
Span A = (Tenkan+Kijun)/2 [+26 forward]
Span B = (H_52+L_52)/2 [+26 forward]
```
**Bullish**: price above cloud + Tenkan>Kijun + Span A>Span B.

**Composite Tech Score (0–100)**: avg of normalized RSI, MACD-hist sign, ADX strength, % above SMA200, Ichimoku state.

---

<a id="part-ii-8"></a>
## 8. Quantitative / Factor Investing

### 8.1 CAPM (Sharpe 1964)
> **E[R_i] − R_f = β_i × (E[R_m] − R_f)**, β = Cov(R_i, R_m)/Var(R_m), 36–60mo OLS

### 8.2 Fama-French 3-Factor (1993)
> **R_i − R_f = α + β·MKT + s·SMB + h·HML + ε**

- SMB: small minus big
- HML: high B/M (value) minus low B/M (growth)

### 8.3 Carhart 4-Factor (1997)
Adds **UMD (Up Minus Down)**: top-30% prior 12-month returns minus bottom 30%, **skipping last month**.

### 8.4 Fama-French 5-Factor (2015)
Adds:
- **RMW (Robust Minus Weak)**: profitable minus unprofitable
- **CMA (Conservative Minus Aggressive)**: low asset growth minus high asset growth

**Implementation**: download monthly factor returns from **Ken French's data library** (free); run OLS regression per stock for factor loadings.

### 8.5 AQR Quality Minus Junk (Asness, Frazzini, Pedersen 2014)

Quality = average of 4 z-scored sub-scores:
1. **Profitability**: GP/A, ROE, ROA, CFO/A, gross margin, low accruals
2. **Growth**: 5-yr avg growth in profitability metrics
3. **Safety**: low β, low IVOL, low leverage, low O-Score, low ROE volatility
4. **Payout**: net equity issuance (negative=good), net debt issuance, dividend payout

**Free QMJ factor returns**: download from aqr.com Datasets.

### 8.6 MSCI Quality Index (3-Descriptor Composite)

Equally-weighted z-scores of:
1. **ROE** (positive z = better)
2. **D/E** (negative z so lower = better)
3. **Earnings Variability** (Std of YoY EPS growth, 5 yrs; negative z)

Process: winsorize 5/95th, z-score, average → Quality Z.

### 8.7 Value Factor — Multiple Definitions

| Metric | Use |
|---|---|
| P/E | Most common |
| P/B | Original Fama-French |
| P/S | Useful for unprofitable firms |
| EV/EBITDA | Capital-structure neutral |
| EV/Sales | Robust |
| EV/FCF | Cash-quality |
| Earnings Yield (EBIT/EV) | Magic Formula |
| Shiller P/E (CAPE) | Index level only |

**Composite Value**: avg percentile rank across 4–6 of these (sector-relative).

### 8.8 Momentum Factor
- 12-1 momentum (cumulative return month t−12 to t−1)
- 6-1 momentum
- 52-week high proximity (Price / 52w High)
- **Residual momentum**: residuals from regression of returns on Fama-French factors (cleaner)

### 8.9 Low Volatility Factor
σ_252 (1-yr daily-return std × √252). Lowest-vol quintile historically higher Sharpe (Baker, Bradley, Wurgler 2011).

### 8.10 Profitability Factor (Novy-Marx 2013)
**Gross Profitability = (Revenue − COGS) / Total Assets**. Most robust profitability predictor — gross profit, not net income.

---

<a id="part-ii-9"></a>
## 9. Risk Metrics

All assume daily returns r_t and annualization factor √252.

| Metric | Formula |
|---|---|
| **Sharpe** | (R̄_p − R_f)/σ_p, annualized |
| **Sortino** | (R̄_p − R_f)/σ_downside |
| **Treynor** | (R̄_p − R_f)/β_p |
| **Information Ratio** | (R̄_p − R̄_b)/σ(R_p − R_b) |
| **Beta** | Cov(R_p, R_m)/Var(R_m), 36–60mo |
| **Calmar** | Annualized Return / |MaxDD| |
| **Maximum Drawdown** | min[(P_t − running_max(P))/running_max(P)] |
| **σ × √252** | Annualized vol |
| **VaR (Historical 95%)** | 5th percentile of return distribution |
| **CVaR (95%)** | Mean of returns ≤ VaR(95%) |

**Sharpe**: >1 good, >2 very good, >3 excellent. **Calmar**: >1 strong.

**0–100 risk score (low-risk bias)**:
`100 × (1 − percentile_rank(σ_252))` averaged with `100 × percentile_rank(Sharpe)`.

---

<a id="part-ii-10"></a>
## 10. Valuation Models — Ensemble Fair Price

### 10.1 Methods to Combine

| Method | Applicable When |
|---|---|
| DCF (Gordon Growth) | Positive FCF + reasonable forecast |
| Graham Number | Positive EPS + Book Value, traditional sectors |
| Residual Income Model | Positive ROE > cost of equity |
| DDM | Stable dividend payer |
| P/E × forward EPS | Always |
| EV/EBITDA × EBITDA − Net Debt | Always for non-financials |
| P/B × BVPS | Banks, capital-intensive |
| P/S × Sales | Unprofitable / growth firms |

### 10.2 Residual Income Model
> **V₀ = B₀ + Σ (ROE_t − r) × B_{t−1} / (1+r)^t**

Best when ROE > cost of equity. Forecast 5 yrs explicitly + terminal capitalization.

### 10.3 Aggregation Procedure
1. Compute each applicable fair price; tag inapplicable (e.g., negative EPS → skip Graham).
2. Drop top and bottom values (trimmed mean) if ≥5 estimates.
3. **Fair Price** = trimmed mean (or median).
4. **Maximum Fair Price** = 95th percentile / max of methods (Jitta-style optimistic upper bound).

### 10.4 Margin of Safety
> **MoS % = (Fair Price − Current Price) / Fair Price × 100**

- MoS >30% = strong buy zone
- 0–30% = fair to attractive
- <0% = overvalued

**Buy Score (0–100)**: `clip(50 + MoS%, 0, 100)`.

### 10.5 Reverse DCF
Solve for g such that DCF(g, WACC=10%) = current price. If implied g >12–15% perpetual, market is pricing aggressive expectations.

---

<a id="part-ii-11"></a>
## 11. Growth, Profitability, Financial Health

### 11.1 Growth Metrics
| Metric | Formula |
|---|---|
| Revenue CAGR (n yr) | (Rev_t / Rev_{t−n})^(1/n) − 1 |
| EPS CAGR | Same on EPS (handle negatives via log) |
| FCF CAGR | Same on FCF |
| Sustainable Growth Rate | ROE × (1 − Payout) = ROE × Retention |
| PRAT model SGR | Profit Margin × Retention × Asset Turnover × Equity Multiplier |
| Internal Growth Rate | ROA × Retention |
| PEG | (P/E) / EPS Growth % |

Use 3-yr and 5-yr windows. **Score** = avg percentile rank across windows.

### 11.2 Profitability & Efficiency
| Metric | Formula |
|---|---|
| Gross Margin | (Rev − COGS)/Rev |
| Operating Margin | EBIT/Rev |
| Net Margin | NI/Rev |
| ROE | NI / Avg Equity |
| ROA | NI / Avg TA |
| ROIC | NOPAT / (Debt+Equity−Cash) |
| Asset Turnover | Rev / Avg TA |
| Cash Conversion Cycle | DIO + DSO − DPO |
| DIO | Avg Inv / COGS × 365 |
| DSO | Avg AR / Rev × 365 |
| DPO | Avg AP / COGS × 365 |

**Trend dimensions**: 5-yr average + slope. Rising margins/ROIC = quality improving.

### 11.3 Financial Health
| Metric | Healthy Threshold |
|---|---|
| Current Ratio | ≥1.5 |
| Quick Ratio | ≥1.0 |
| Debt-to-Equity | <1.0 (sector-dep) |
| Debt-to-Assets | <0.6 |
| Interest Coverage | >5× |
| Debt-to-EBITDA | <3× (investment grade) |
| Net Debt / FCF | <5× |

---

# PART III — ADVANCED TECHNIQUES

<a id="part-iii-12"></a>
## 12. Sentiment Analysis & Alternative Data

### 12.1 News Sentiment with FinBERT (PRIMARY NLP)

**Model**: `ProsusAI/finbert` (BERT pre-trained on financial corpora). Outputs softmax over {positive, neutral, negative}.

**Score**: `s = P(pos) − P(neg)` ∈ [−1, 1].

**Inputs**: news headlines + first paragraph; earnings call paragraphs; 8-K text.
**Free sources**: yfinance `Ticker.news`, Finnhub `/company-news`, GDELT 2.0, NewsAPI, SEC 8-K via edgartools.

**Python**:
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
finbert = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer, top_k=None)
scores = finbert("Apple beat earnings expectations and raised guidance.")
```

**Aggregation**: weighted mean by recency (exp decay, half-life 3 days), per ticker per week.
**0–100**: cross-sectional percentile rank.

**Limits**: 512-token cap (use Longformer for full transcripts); ~50ms/article CPU; corpora pre-2020.
**Lift**: weekly IC ~0.02–0.04 (academic).

### 12.2 VADER / Loughran-McDonald (Lightweight)
- VADER (`vaderSentiment`): general text
- Loughran-McDonald financial dictionary (free CSV from Notre Dame): SEC filings
Use as fast first-pass / sanity-check; FinBERT dominates accuracy.

### 12.3 Reddit r/wallstreetbets Sentiment

**Algorithm**:
1. Pull top/hot/new posts and comments daily via `praw.Reddit(...)`.
2. Extract candidate tickers via regex `\$?[A-Z]{2,5}\b`, filter against known ticker list.
3. Per-ticker features:
   - `mention_count`
   - `unique_authors`
   - `score_weighted_mentions`
   - `bullish_ratio` (from VADER/FinBERT on context)
   - `acceleration` = mentions_today / mean_7d
4. Blacklist: `PUTS`, `CALLS`, `YOLO`, `HOLD`, etc.

**Caveat**: WSB sentiment is reflexive — extreme positive often precedes mean reversion. Treat as **attention/crowding** feature.

**Lift**: mention-count *acceleration* strongest sub-feature; 5-day forward IC ~0.03 on small/mid-cap.

### 12.4 StockTwits Sentiment
Free streaming endpoint with user-tagged Bullish/Bearish (cleaner than free-text):
`https://api.stocktwits.com/api/2/streams/symbol/{TICKER}.json`

Aggregate: `bullish_share = bull/(bull+bear)`; level + WoW change.

### 12.5 SEC Form 4 Insider Trading

**Why**: insider open-market purchases (transaction code "P") are among the most consistent positive predictors (Lakonishok-Lee 2001, Cohen-Malloy-Pomorski 2012). Sales are noisy.

**Implementation**:
```python
from edgar import Company, get_filings
filings = get_filings(form="4", year=2026, quarter=2)
for f in filings:
    obj = f.obj()  # Form4 object
    df = obj.to_dataframe()
```

**Score (rolling 90 days)**:
- `net_insider_buy_$ = Σ(P) − Σ(S non-10b5-1)`
- Weight by role: CEO/CFO=3, Director=2, 10% owner=1
- `cluster_buying_score`: distinct insiders buying within 30 days (≥2 = strong)
- Normalize by market cap → cross-sectional percentile.

**Lift**: cluster buying = 5–10% annualized alpha in long-only top decile.

### 12.6 13F Institutional Holdings

Quarterly parse for "smart money" managers (Berkshire, Pershing Square, Baupost, Renaissance, Tiger Global, Coatue, Akre, etc.).

Per ticker:
- `smart_money_count_change`
- `smart_money_$_added`
- `whale_concentration`: top-10 13F-filers' aggregate / shares out

```python
from edgar import Company
report = Company("BRK.A").get_filings(form="13F-HR")[0].obj()
holdings = report.holdings  # DataFrame: Ticker, Value, Shares, Status
```

**45-day lag** for backtesting (filings late).

### 12.7 Short Interest & Squeeze Metrics

Free: yfinance `Ticker.info` (`sharesShort`, `shortRatio`, `shortPercentOfFloat`); Finnhub free historical.

- `short_pct_float` (>20% raises squeeze odds)
- `days_to_cover` = short_int / avg daily volume
- `short_ratio_change_2w`

Use **change** as sentiment signal (rising = bearish; high level + price strength = potential squeeze).

### 12.8 Options Flow / Put-Call Ratio

Free: CBOE daily total/equity/index PCR (CSV); yfinance options chain.

- `pcr_volume` = put_vol / call_vol
- `pcr_oi` = put_oi / call_oi
- `iv_skew` = IV(25Δ put) − IV(25Δ call)
- `unusual_options_activity` = today_vol / 30d_avg

PCR <0.7 bullish, >1.0 bearish; extremes contrarian.

### 12.9 Google Trends (pytrends)

```python
from pytrends.request import TrendReq
pt = TrendReq()
pt.build_payload(["AAPL", "Apple stock"], timeframe="today 12-m")
df = pt.interest_over_time()
```

**Feature**: `search_acceleration = (this_week − mean_12w) / std_12w`.
Heavy throttling — cache aggressively.

### 12.10 Earnings Call Transcript Sentiment

**Source**: Seeking Alpha (legal/fragile), Motley Fool transcripts, IR pages, API Ninjas. Use Longformer (`allenai/longformer-base-4096`) for full transcripts (>512 tokens) or chunk + average.

**Features**:
- `qa_section_sentiment` (Q&A more honest than prepared)
- `complexity` (Gunning Fog/Flesch-Kincaid; rising = red flag post-Enron)
- `forward_looking_count` ("expect/anticipate/guidance" dictionary)
- `hedging_word_count` (Loughran-McDonald uncertainty)

---

<a id="part-iii-13"></a>
## 13. Machine Learning Pipeline

### 13.1 Gradient Boosted Trees (PRIMARY ML — RECOMMENDED)

**Why first**: outperform LSTM/Transformers on typical equity feature sets at daily/weekly horizons. Handle mixed scales, missing values, non-linearities. Provide free SHAP interpretability.

**Target**: cross-sectional rank of forward return (1m, 3m). For ranking, use LightGBM `objective="lambdarank"`, group = trading date.

**Features**: all 60 classical metrics + advanced features = ~150 features.

**Pre-process**:
1. Winsorize at 1/99 percentiles
2. Cross-sectionally rank (or z-score by sector)
3. Train

**Hyperparameters (starting point)**:
```python
params = {
    'num_leaves': 31,
    'learning_rate': 0.03,
    'n_estimators': 500,
    'min_child_samples': 200,
    'reg_alpha': 0.1,
    'reg_lambda': 0.1,
    'feature_fraction': 0.7,
    'bagging_fraction': 0.8,
    'objective': 'lambdarank'
}
```
Use Optuna for tuning **only on training fold** to avoid leakage.

### 13.2 Walk-Forward Validation

```python
from sklearn.model_selection import TimeSeriesSplit
splits = TimeSeriesSplit(n_splits=10, test_size=21)  # 21 trading days per test
```

**Procedure**:
- Initial train: 5 years
- Step forward 1 month
- Refit; predict next month
- Evaluate IC, IR, decile spread per fold; aggregate

### 13.3 LSTM / GRU / Temporal Fusion Transformer

Use only when sequence dependence beyond ~20 lags adds value (rare for weekly fundamental). Libraries: `pytorch-forecasting` (TFT, DeepAR, N-BEATS), `darts`. **Defer until tree-based pipeline is live and validated.**

### 13.4 Anomaly Detection

```python
from sklearn.ensemble import IsolationForest
iso = IsolationForest(contamination=0.01)
flagged = iso.fit_predict(X_features)
```

Flag stocks behaving unusually (return, volume, vol z-scores). Use as **risk filter** (avoid recently-anomalous at top of ranking), not alpha.

### 13.5 Clustering for Peer Discovery

Cluster stocks by return-correlation distance (`1 − corr`) using HDBSCAN or hierarchical agglomerative; alternative: cluster by feature-vector. Use clusters for **peer-relative valuations** (P/E vs. cluster median) — often more powerful than sector-relative.

### 13.6 Feature Engineering Best Practices

- **Cross-sectional ranking** every feature each rebalance date → uniform [0,1]
- **Sector neutralization**: subtract sector median before ranking
- **Market-cap neutralization**: residualize feature against log(market cap) by OLS
- **Z-score winsorization** at 3σ before any non-rank feature
- **Lag policy**: fundamentals lagged ≥45 days post fiscal period end; macro 1 day; price-derived 0 day
- **Stationary transforms**: changes/ratios of fundamentals, not raw levels

### 13.7 Common Pitfalls — Hard-Code Against

| Pitfall | Mitigation |
|---|---|
| Look-ahead bias | "As-of" snapshots; SEC EDGAR filing dates, not period-end |
| Survivorship bias | Historical S&P 500 constituents from Wikipedia history |
| Selection bias | Define universe at time t with info available at t |
| P-hacking | Pre-register hypotheses; require IC>0 in ≥70% of yrs OOS; PBO |
| Multiple testing | Bonferroni / Benjamini-Hochberg correction |
| Newey-West needed | `OLS().fit(cov_type='HAC', cov_kwds={'maxlags':12})` |
| Train-test leak | Strict time-cut; do not standardize across full sample |

### 13.8 SHAP for Explainability

```python
import shap
explainer = shap.TreeExplainer(lgbm_model)
shap_values = explainer.shap_values(X_today)
top5 = np.argsort(np.abs(shap_values[idx]))[-5:]
```

Surface top-5 contributing features per stock in UI.

---

<a id="part-iii-14"></a>
## 14. Advanced Quant — HRP, Black-Litterman, Kelly

### 14.1 Hierarchical Risk Parity (López de Prado 2016) — RECOMMENDED

**Algorithm**:
1. Compute correlation `ρ`. Distance `d_ij = sqrt(0.5(1−ρ_ij))`.
2. Hierarchical clustering (single linkage) → tree.
3. Quasi-diagonalize covariance by tree order.
4. Recursive bisection: allocate inverse-variance proportional.

```python
from pypfopt import HRPOpt
hrp = HRPOpt(returns=daily_returns_df)
weights = hrp.optimize(linkage_method="single")
```

**Why**: avoids covariance inversion, far more stable than Markowitz under estimation error. Standard in modern quant.

### 14.2 Black-Litterman Model

Blend market prior (CAPM-implied) with ranking system's predictions (treated as views).

```python
from pypfopt import BlackLittermanModel, risk_models, EfficientFrontier
S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
delta = 2.5
prior = delta * S @ market_caps_normalized
viewdict = {"AAPL": 0.15, "TSLA": -0.05}
bl = BlackLittermanModel(S, pi=prior, absolute_views=viewdict,
                          omega="idzorek", view_confidences=[0.6, 0.4])
posterior_ret = bl.bl_returns()
ef = EfficientFrontier(posterior_ret, S)
w = ef.max_sharpe()
```

### 14.3 Ledoit-Wolf Shrinkage Covariance

Always use shrinkage when N (assets) ~ T (observations):
```python
from sklearn.covariance import LedoitWolf
S = LedoitWolf().fit(returns_matrix).covariance_
```

### 14.4 Markowitz / Max-Sharpe / Min-Var

```python
from pypfopt import EfficientFrontier
ef = EfficientFrontier(mu, S)
w_max_sharpe = ef.max_sharpe()
w_min_vol = ef.min_volatility()
```

### 14.5 Risk Parity (Equal Risk Contribution)

```python
import riskfolio as rp
port = rp.Portfolio(returns=returns)
port.assets_stats(method_mu='hist', method_cov='ledoit')
w = port.rp_optimization(model='Classic', rm='MV', rf=0)
```

### 14.6 Kelly Criterion

- Binary: `f* = p/L − q/G`
- Continuous (single asset): `f* = μ/σ²`
- Portfolio: `f* = Σ⁻¹ μ`

**Use fractional Kelly (¼ to ½)** in production — full Kelly too aggressive given parameter estimation error.

### 14.7 Multi-Factor Composite Construction

Build composite per category, then combine:
- **Value**: rank avg of P/E, P/B, EV/EBITDA, FCF yield, div yield (5)
- **Quality**: ROE, ROIC, gross margin, accruals (inverted), Piotroski (5)
- **Momentum**: 12-1, 6-1, 3-1, residual, 52w-high distance (5)
- **Low-Vol**: 252-day vol, idiosyncratic vol, β (3)
- **Growth**: rev/EPS CAGR 3y, fwd revisions (3)
- **Sentiment**: news, Reddit, options, insider (4)

Z-score within each category, average → one factor per category. Combine via meta-learner weights.

### 14.8 Factor Timing / Rotation

Conditional on macro regime: value tends to outperform in rising-rate; momentum in trending; quality in late-cycle.

**Implementation**: estimate factor return ~ regime indicator with rolling window; weight factors by recent IR within current regime. Use **gentle tilts (±20% from neutral)**, not bets — factor timing's added value is debated.

---

<a id="part-iii-15"></a>
## 15. Macro & Regime Detection

### 15.1 FRED Macro Stack (Free with API Key)

| Code | Series | Use |
|---|---|---|
| `T10Y2Y` | 10Y–2Y spread | Recession indicator |
| `T10Y3M` | 10Y–3M | NY Fed favorite |
| `BAMLH0A0HYM2` | HY OAS | Credit-stress regime |
| `VIXCLS` | VIX close | Vol regime |
| `UNRATE` | Unemployment | Late-cycle |
| `INDPRO` | Industrial production | Chen-Roll-Ross |
| `CPIAUCSL` | CPI | Inflation factor |
| `FEDFUNDS` | Fed funds | Discount-rate factor |
| `USREC` | NBER recession | Backtest regime |

```python
from fredapi import Fred
fred = Fred(api_key=KEY)
spread = fred.get_series('T10Y2Y')
```

### 15.2 Hidden Markov Models for Regime Detection

```python
from hmmlearn.hmm import GaussianHMM
features = pd.concat([spy_returns, vix_change, term_spread_change], axis=1).dropna()
hmm = GaussianHMM(n_components=3, covariance_type='full', n_iter=1000).fit(features)
states = hmm.predict(features)
```

Label states by mean return: high-mean-low-vol = bull, low-mean-high-vol = bear, otherwise neutral.

**Use**: as ML feature (one-hot regime); as gate for factor weights; as risk filter (reduce exposure in bear).

### 15.3 Chen-Roll-Ross (1986) Macro Factor Model

Macro factors: industrial production growth, unexpected inflation (CPI − consensus), term spread innovation, default-spread innovation. Estimate stock betas via 60-month rolling regression; expected return = Σ βᵢ × λᵢ. Cross-section deviation between actual and predicted return = mispricing signal.

### 15.4 Sector Rotation Logic

Classify regime via HMM + yield curve + ISM PMI proxy, then tilt sector weights:
- **Early recovery**: Tech, Cyclicals
- **Mid cycle**: Industrials, Materials
- **Late cycle**: Energy, Staples
- **Recession**: Healthcare, Utilities

### 15.5 Equity Duration (Interest-Rate Sensitivity)

`Duration ≈ −ΔP/P / Δy`. Estimate via 3-yr rolling regression of weekly returns on 10Y yield change. Long-duration equities suffer in rising-rate regimes. Use as risk factor.

---

<a id="part-iii-16"></a>
## 16. Microstructure / Volume / Flow

All available in `ta` and `pandas-ta`:

| Indicator | Library | Interpretation |
|---|---|---|
| VWAP | `ta.volume.VolumeWeightedAveragePrice` | Price vs. VWAP = institutional sentiment |
| A/D Line | `ta.volume.AccDistIndexIndicator` | Divergence with price → reversal |
| Chaikin Money Flow (20) | `ta.volume.ChaikinMoneyFlowIndicator` | >0 buying pressure |
| Volume-Price Trend | `ta.volume.VolumePriceTrendIndicator` | Cumulative volume × % return |
| Force Index | `ta.volume.ForceIndexIndicator` | Strength of move |
| Ease of Movement | `ta.volume.EaseOfMovementIndicator` | Price moves on low vol = easy |
| NVI / PVI | `pandas_ta.nvi`, `pvi` | Smart vs. uninformed money proxy |
| Relative Volume | `volume / 20d_avg_volume` | Attention spike |

Score each → 0–100 percentile cross-sectionally, average within "Volume/Flow" category.

---

<a id="part-iii-17"></a>
## 17. Advanced Valuation (EVA, CFROI, Tobin's Q)

### 17.1 Economic Value Added (EVA)
> **EVA = NOPAT − (WACC × Invested Capital)**

- NOPAT = EBIT × (1 − effective tax rate)
- Invested Capital ≈ Total Debt + Equity − Cash
- WACC via CAPM (rf from FRED `DGS10`, ERP=5.5%)

**Score**: `EVA / Invested Capital` cross-sectional rank → 0–100.

### 17.2 Market Value Added (MVA)
> **MVA = MarketCap + Total Debt − Invested Capital**

Cumulative value creation by management.

### 17.3 CFROI (Cash Flow Return on Investment)

Approximation: `(EBITDA + R&D) / (Gross PP&E + Working Capital)`. Compare to WACC.

### 17.4 Tobin's Q
> **q ≈ (MarketCap + Total Debt) / Total Assets**

q < 1 cheap; q > 1 expensive (high-growth premium).

### 17.5 Damodaran Intrinsic Value

Two-stage FCFF DCF with explicit fade to terminal industry margin/growth = risk-free + 2%. Damodaran publishes industry betas, ERP, country-risk premia, R&D capitalization rules — free at `pages.stern.nyu.edu/~adamodar/`.

### 17.6 Implied Cost of Capital (ICC)

Reverse-engineer the discount rate that makes residual-income or DCF model match current price given consensus EPS. Gebhardt-Lee-Swaminathan (2001) or Easton (2004) PEG. Forward expected-return measure superior to historical β-based CAPM.

### 17.7 Sloan Accruals Anomaly

> **Accruals = (NI − CFO) / Avg Total Assets**

**Higher accruals → lower future returns**. Sloan (1996) hedge spread ~10% annually historically; decayed but still significant.

Use **rank ascending** (low accruals = high score). Subtract from base score (penalty) when high.

### 17.8 Dechow F-Score (Fraud Detection)

Logit using accruals quality, change in receivables, change in inventory, % soft assets, change in cash sales, change in ROA, actual issuance. Use alongside Beneish — they catch slightly different fraud patterns.

---

<a id="part-iii-18"></a>
## 18. Behavioral & Anomaly Factors

| Anomaly | Construction | Sign | Notes |
|---|---|---|---|
| **PEAD** | SUE = (actual − consensus EPS)/std(SUE_4q); long top quintile 60d | + | Decaying; enhance with NLP |
| **Earnings surprise momentum** | SUE × EAR(3-day reaction) interaction | + | George-Hwang style |
| **Analyst revisions** | Δ(consensus EPS)/|EPS| over 4w | + | yfinance has analyst data |
| **52-week high** | Price / 52w_high | + | Anchoring bias |
| **Lottery / MAX effect** | Avg of 5 highest daily returns last month | − | Avoid lottery stocks |
| **Idiosyncratic volatility** | Std of CAPM residuals 60d | − | IVOL puzzle |
| **Asset growth** | (TA_t − TA_{t−1})/TA_{t−1} | − | High asset growth → low returns |
| **Net stock issuance** | log(SharesOut_t/SharesOut_{t−1}) | − | Robust survivor anomaly |
| **CapEx / Assets** | CapEx / Avg TA | − | Over-investment penalty |
| **Investment-to-assets** | (ΔPPE + ΔInv)/TA | − | q-theory grounded |
| **Profitability persistence** | Std of ROA last 5 yrs (low = persistent) | + (low std) | Quality |
| **Quality persistence** | Avg Piotroski over 5 yrs | + | Buffett-like |
| **Composite mispricing (Stambaugh-Yu-Yuan)** | Avg rank of 11 anomalies | + | Strong long-short spread |

Within each: cross-sectional rank → 0–100, then combine via equal-weight or recent-IR weighting.

---

<a id="part-iii-19"></a>
## 19. Advanced Risk Analysis

| Metric | Implementation | Interpretation |
|---|---|---|
| **Conditional VaR (ES)** | `np.mean(returns[returns ≤ np.quantile(returns, α)])` | Expected loss given VaR exceeded |
| **Drawdown details** | `quantstats.stats.drawdown_details(returns)` | Worst-case stress |
| **Skewness / Kurtosis** | `scipy.stats.skew/kurtosis` | Tail-risk shape |
| **Downside Deviation** | std of returns below MAR | Sortino numerator |
| **Ulcer Index** | sqrt(mean(drawdown_pct²)) over 14d | Stress of holding |
| **Pain Index** | mean(\|drawdown\|) | Avg pain |
| **Omega Ratio** | Σ max(r−θ,0) / Σ max(θ−r,0) | Threshold-based |
| **GARCH(1,1)** | `arch.arch_model(r, vol='Garch', p=1, q=1).fit()` | Time-varying vol |
| **GJR-GARCH** | asymmetric leverage | Better for equities |

```python
from arch import arch_model
am = arch_model(returns*100, vol='Garch', p=1, o=1, q=1, dist='t')
res = am.fit(disp='off')
sigma_forecast = res.forecast(horizon=21).variance.iloc[-1]
```

Use forecasted volatility in Sharpe/Kelly inputs and as a feature.

---

<a id="part-iii-20"></a>
## 20. Corporate Events & Catalysts

| Event | Source | Treatment |
|---|---|---|
| Earnings date | yfinance, Finnhub | Drift signal (PEAD); higher vol pre-event |
| Beat/miss | Finnhub `/stock/earnings` | SUE feature |
| Dividend / buyback | yfinance `Ticker.actions`, 8-K | Buyback yield = +shareholder yield |
| M&A target | 8-K item 1.01, news | Risk-arb; consider excluding from base |
| Insider buying | Form 4 | + score |
| 8-K material events | edgartools `form="8-K"` + item filter | Item 4.02 (restatement) = strong negative |
| Spin-offs | edgartools form-10 | Often overlooked; +alpha academic |
| Index inclusion | News + index publisher | +flow upon addition |

For each catalyst within trailing 90 days, compute event-window CAR and add as features.

---

# PART IV — SCORING, RANKING, VALIDATION

<a id="part-iv-21"></a>
## 21. Composite Score Construction

### 21.1 Z-Score Normalization
> **z_i = (x_i − μ) / σ** after winsorization at 5th/95th percentile

For "lower-is-better" metrics (D/E, P/E, vol): `z = −(x−μ)/σ`.

### 21.2 Percentile Rank (RECOMMENDED for ranking apps)
> **percentile_i = rank(x_i) / N × 100**

Robust to outliers; produces 0–100 directly; easy to interpret. Used by Stockopedia, Jitta-style platforms.

### 21.3 Sigmoid / Min-Max
- Min-Max: `(x − min)/(max − min) × 100` — sensitive to outliers; only after winsorization
- Sigmoid: `100 / (1 + exp(−k·z))` — smooth bounded

### 21.4 Two-Level Composite
- **Level 1 (Pillar Score)**: avg percentile rank of metrics within pillar
- **Level 2 (Composite)**: weighted avg of pillar scores

**Recommended weights** (already in §4.1):

| Pillar | Weight |
|---|---|
| Quality | 25% |
| Value | 20% |
| Growth | 10% |
| Momentum | 10% |
| Sentiment | 15% |
| ML | 10% |
| Macro | 5% |
| Risk | 5% |

### 21.5 Sector-Relative Computation
**Always compute Quality/Value/Growth ranks within sector (GICS).** Use absolute scoring only for Risk and Momentum.

---

<a id="part-iv-22"></a>
## 22. Backtesting & Validation Framework

### 22.1 Information Coefficient (IC)

`IC_t = spearmanr(predicted_rank_t, forward_return_{t+h})`

Report:
- **Mean IC** (>0.02 monthly = decent; >0.05 strong)
- **IC IR** = mean(IC) / std(IC) (annualized × √12)
- **% positive IC periods** (>55% good)
- **IC decay** plot at horizons 1, 5, 21, 63 days

### 22.2 Quintile/Decile Spread

Sort stocks into 5 or 10 buckets by predicted score; equal-weight; monthly returns. Top-bottom spread, **t-stat with Newey-West**, Sharpe of long-short.

### 22.3 alphalens

```python
from alphalens.utils import get_clean_factor_and_forward_returns
from alphalens.tears import create_full_tear_sheet
factor_data = get_clean_factor_and_forward_returns(
    factor=score_series, prices=prices_wide, quantiles=5, periods=(1,5,21))
create_full_tear_sheet(factor_data, by_group=False)
```

### 22.4 Walk-Forward Optimization
Train years 1–5, test year 6; roll. Re-tune hyperparameters in each window using only past data.

### 22.5 Combinatorially Symmetric CV (CSCV) and PBO

Bailey, Borwein, López de Prado, Zhu — CSCV splits T into S equal blocks, uses every C(S,S/2) split into train/test, computes performance rank, then **PBO** = probability that the best in-sample is below median out-of-sample.

**PBO < 0.5 desired.** Implementations: `pbo` (R) or port the López de Prado snippet (~30 lines NumPy).

### 22.6 Monte Carlo & Bootstrap

- **Block bootstrap** (`arch.bootstrap.CircularBlockBootstrap`) preserves autocorrelation
- **Monte Carlo** of strategy: simulate 10,000 reorderings of trade outcomes for p-value of Sharpe

### 22.7 Transaction Cost Modeling

- Spread cost: ~0.05–0.10% liquid US large-cap, 0.20–0.50% small-cap
- Market impact: `0.5 × σ × sqrt(trade_size / ADV)` (square-root law)
- Weekly/monthly rebalance with top-decile S&P 500 round-trip ~30–60 bps

### 22.8 Statistical Significance

- **Newey-West HAC** for time-series factor returns: `OLS().fit(cov_type='HAC', cov_kwds={'maxlags':12})`
- **Deflated Sharpe** (Bailey & López de Prado 2014): adjusts Sharpe for skew, kurtosis, number of trials

---

<a id="part-iv-23"></a>
## 23. Ensemble & Meta-Learning

### 23.1 Stacked Generalization

**Layer 1 base learners** (each → 0–100 per ticker per date):
- M1: Fundamental composite (60 classical + EVA/CFROI/Tobin/Beneish/Sloan)
- M2: Technical/Volume composite
- M3: Sentiment/alt-data composite
- M4: LightGBM trained on all features
- M5: Macro/regime-adjusted score

**Layer 2 meta-learner**: logistic regression or shallow tree on **out-of-fold predictions** of M1–M5 → final score. Critical: out-of-fold (not in-sample) to avoid leakage.

### 23.2 Dynamic Regime-Conditional Weights

Estimate `IR(M_i | regime_r)` from rolling 3-year history. At each rebalance:
> w_i = max(IR_i^r, 0) / Σ max(IR_j^r, 0)

Recompute weekly.

### 23.3 Bayesian Model Averaging (Lighter)

Posterior weights ∝ likelihood × prior. Lightweight: weight by `exp(IR/τ)` (softmax) where τ controls sharpness.

### 23.4 Meta-Labeling (López de Prado)

Primary model → BUY/SELL signal. Triple-barrier labels training data: hit upper (TP) → +1, lower (SL) → −1, vertical (timeout) → 0. Secondary classifier (XGBoost) predicts probability the primary signal is correct → bet sizing.

```python
import mlfinlab as ml
events = ml.filters.cusum_filter(close, threshold=daily_vol.mean()*0.5)
t1 = ml.labeling.add_vertical_barrier(events, close, num_days=21)
triple = ml.labeling.get_events(close, events, pt_sl=[1,1], target=daily_vol, t1=t1)
labels = ml.labeling.get_bins(triple, close)
```

### 23.5 Alpha Decay & Crowding Diagnostics

- **Decay**: rolling 24-mo IC per signal; alert when slope < 0 with t < −2
- **Crowding proxy**: high short interest in long leg + high mutual-fund overlap (13F) + high return correlation with peer "factor ETFs" (MTUM, QUAL, USMV, IVE)

---

<a id="part-iv-24"></a>
## 24. Performance Metrics for the App

Every scheduled run, log:

| Metric | Definition | Target |
|---|---|---|
| Spearman IC (1m, 3m) | Rank correlation rank vs forward return | >0.04 / >0.06 |
| IR | mean(IC)/std(IC)·√12 | >0.5 |
| Top-decile vs. bottom spread | Equal-weighted | t > 2.5 (NW) |
| Hit rate | % top-N beating SPY 1m | >55% |
| Top-N annualized alpha | CAPM α | >2% post-cost |
| Top-decile Calmar | CAGR / |MaxDD| | >0.5 |
| Sharpe | excess / σ | >1.0 (after cost) |
| Sortino | excess / downside-σ | >1.5 |
| MaxDD | Peak-to-trough | <30% |
| Turnover | Σ|Δw|/2 monthly | track; <50%/m |
| Deflated Sharpe | Bailey-LdP | >0 |
| PBO | CSCV-based | <0.5 |

Persist every run's outputs in versioned table with run hash → auditable.

---

# PART V — IMPLEMENTATION GUIDE

<a id="part-v-25"></a>
## 25. Data Caching & Refresh Cadence

| Data | Cadence | Cache layer |
|---|---|---|
| Prices/volume | Daily | parquet by month |
| Fundamentals | After each filing | SQLite indexed by CIK+filing-date |
| 13F | Quarterly (45-day lag) | parquet |
| Form 4 | Daily | parquet |
| Macro (FRED) | Daily | small CSVs |
| News | Daily | SQLite, FinBERT scores cached by article hash |
| Reddit | Daily | parquet |
| Google Trends | Weekly | parquet |
| ML model retrain | Monthly | pickled models versioned by date |
| HMM regime | Weekly | small pickle |
| Composite scores | Weekly | parquet (versioned) |

---

<a id="part-v-26"></a>
## 26. Rate-Limit Management Strategies

- One ticker = one batch task; orchestrate with `asyncio` + semaphore for free APIs
- Persist `last_pulled_at` per (source, ticker); skip if within TTL
- Implement circuit breaker on 429 with exponential backoff (`tenacity` library)
- Pre-compute heavy embeddings (FinBERT) once; only score new articles
- Use HuggingFace `pipeline(device=0)` if GPU available; else batch CPU calls of size 32
- Reduce universe (S&P 500 → S&P 1500 → Russell 3000) in stages as bandwidth allows

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=60))
def fetch_with_backoff(url):
    ...
```

---

<a id="part-v-27"></a>
## 27. Suggested Database Schema

### Core Tables

```sql
-- Universe and metadata
CREATE TABLE securities (
    ticker TEXT PRIMARY KEY,
    cik TEXT,
    name TEXT,
    sector TEXT,
    industry TEXT,
    market_cap REAL,
    listed_date DATE,
    delisted_date DATE
);

-- Daily price data
CREATE TABLE prices_daily (
    ticker TEXT,
    date DATE,
    open REAL, high REAL, low REAL, close REAL,
    adj_close REAL, volume INTEGER,
    PRIMARY KEY (ticker, date)
);

-- Fundamentals (point-in-time)
CREATE TABLE fundamentals (
    ticker TEXT,
    period_end DATE,
    filing_date DATE,  -- USE THIS for backtests, not period_end
    revenue REAL, net_income REAL, ebit REAL, ebitda REAL,
    total_assets REAL, total_debt REAL, equity REAL,
    cfo REAL, capex REAL, fcf REAL,
    eps_basic REAL, eps_diluted REAL,
    shares_outstanding REAL,
    -- ... ~50 fields
    PRIMARY KEY (ticker, period_end)
);

-- Form 4 insider transactions
CREATE TABLE insider_transactions (
    ticker TEXT,
    insider_name TEXT,
    role TEXT,
    transaction_date DATE,
    filed_date DATE,
    transaction_code TEXT,  -- 'P'=purchase, 'S'=sale
    shares REAL,
    price REAL,
    value_usd REAL
);

-- News + sentiment (cached FinBERT)
CREATE TABLE news_sentiment (
    article_hash TEXT PRIMARY KEY,
    ticker TEXT,
    date TIMESTAMP,
    source TEXT,
    headline TEXT,
    p_positive REAL,
    p_neutral REAL,
    p_negative REAL,
    finbert_score REAL  -- p_pos - p_neg
);

-- Composite scores (versioned)
CREATE TABLE stock_ranks (
    run_date DATE,
    run_hash TEXT,
    ticker TEXT,
    rank INTEGER,
    composite_score REAL,
    quality_score REAL,
    value_score REAL,
    growth_score REAL,
    momentum_score REAL,
    health_score REAL,
    sentiment_score REAL,
    ml_score REAL,
    risk_score REAL,
    fair_price REAL,
    max_fair_price REAL,
    margin_of_safety REAL,
    top5_factors TEXT,  -- JSON
    PRIMARY KEY (run_date, ticker)
);
```

---

<a id="part-v-28"></a>
## 28. Realistic Accuracy Expectations

Compared to a strong **classical-only multi-factor baseline** (Piotroski + Magic Formula + 12-1 momentum + low-vol):

| Source of Lift | Expected Annualized Alpha |
|---|---|
| FinBERT news + insider Form 4 | +1–2% |
| ML composite (LightGBM with cross-sectional ranks) | +1–2% |
| Regime-conditional weighting + HRP construction | +0.5–1% |
| **Combined upper bound (gross)** | **~4–6%** |
| **Net of transaction costs** | **~2–4%** |
| Sharpe lift | +0.2–0.4 |

> **Anything claiming >10% alpha should be treated as overfit** until validated on a fresh 3-year out-of-sample period and CSCV PBO < 0.4.

### Mean IC Expectations (Individual Factors)
- Strong: 0.04–0.06
- Decent: 0.02–0.04
- Suspicious: >0.10 (likely overfit)

---

<a id="part-v-29"></a>
## 29. Caveats & Pitfalls

### 29.1 Data Quality
- **yfinance** breaks periodically; field names shift; some quarters missing. Cross-check fundamentals against SEC EDGAR ground truth.
- **Sector exclusions matter**: Magic Formula excludes financials/utilities; Z-score's X₅ distorts asset-light tech (use Z″); Graham Number breaks for negative book/EPS.
- **Free-data quality varies**: SimFin, FMP free, edgartools (XBRL) more reliable for backtests but each has coverage holes pre-2010.

### 29.2 Survivorship & Look-Ahead
- **Survivorship bias** is everywhere in free data; truly clean source is CRSP (paid). Reconstruct delisted tickers from SEC EDGAR (companies that stopped filing).
- **Look-ahead is silent killer**: Form 4 must use `transactionDate`; 13F lagged 45 days; 10-K filing date not period-end. SEC EDGAR exposes both.

### 29.3 Backtest Overoptimism
- All cited strategies (Magic Formula 30% CAGR, Piotroski 23%, QMJ alpha) are **in-sample**. Independent OOS replications typically produce **~3× lower** returns. Treat historical numbers as upper bounds.
- Most published anomalies have **decayed post-publication**.

### 29.4 NLP / ML Specific
- **FinBERT trained on pre-2020 corpora**; periodically benchmark on labeled validation.
- **Reddit/StockTwits are reflexive** — never use as single-factor strategy.
- **HMM regime states not stable** across refits; persist model and use state-mapping logic.

### 29.5 Forward-Looking Estimates
- PEG, DCF, reverse-DCF need growth assumptions. Free APIs lack reliable analyst consensus — historical CAGR proxy biases against accelerating/decelerating firms.

### 29.6 Risk Metrics
- **VaR/CVaR (historical)** assume past distribution repeats — fail in regime changes (2008, 2020). Pair with stress tests.
- **Owner Earnings is an estimate**, not GAAP. Maintenance CapEx unobservable; report range.

### 29.7 Composite Scores
- StockRank 99 is not "twice as good" as 50. Treat ranks as **ordinal screens, not cardinal predictions**.
- Always pair quantitative ranking with qualitative DD.

### 29.8 Reconstruction Assumptions
- MSCI Quality, AQR QMJ, Fama-French weights are **public reconstructions** — actual proprietary methodologies may use additional descriptors not disclosed.

### 29.9 Real-Time Data
- Alpha Vantage and most free tiers serve **delayed (15–20 min)** US equity prices. Real-time requires paid tiers.

### 29.10 Configuration
- Risk-free proxy (10-yr Treasury), 22.5 in Graham formula, 5–7% MRP need **periodic updating**. Build into config file, not hardcoded.

---

# PART VI — RESEARCH-BACKED STRETCH ADDITIONS (Phase 4+)

## 30. Why Option B (Research-Backed Roadmap)

### Why DIY factors hit a ceiling fast

If you implement Sections 6-11 perfectly, you'll have ~30 hand-coded metrics that match academic factors. Problem: most of these factors are **already in published peer-reviewed factor libraries** that have:
- Been replicated against original t-stats
- Been point-in-time corrected
- Been cleaned of survivorship bias
- Been documented for license/usage

**Building your own implementation from scratch reintroduces noise.** Better path: use the library factors as inputs, then add your own composite logic.

### What Option B adds

```
DIY Layer (Phase 0-3):     30 metrics → 8 pillars → composite
                           = 2-4% net alpha realistic ceiling
                           
+ Library Factor Layer:     319 OSAP signals + 153 JKP factors + 
                           158 Qlib Alpha158 features
                           
+ ML Enhancement Layer:     Triple-Barrier + Meta-Labeling + 
                           Conformal Prediction
                           
+ Sentiment v2 Layer:       Whisper + 8-K events + Lazy Prices
                           
+ Regime v2 Layer:          Student-t HMM + TDA + NCO
                           = 3-7% net alpha realistic ceiling ⭐
```

### Sources for upgrade rationale

- McLean & Pontiff (2016, JoF) — anomalies decay post-publication; library replications correct for this
- Chen & Zimmermann (2022, CFR) — Open Source Cross-Sectional Asset Pricing replicated 319 anomalies
- Jensen, Kelly & Pedersen (2023, JoF) — "Is There a Replication Crisis in Finance?" — 153 factors survive corrections
- Kelly, Pruitt & Su (2019, JFE) — IPCA dominates Fama-French in pricing errors
- Gu, Kelly & Xiu (2020, RFS; 2021, JoE) — autoencoder asset pricing models, ML in asset pricing
- Cohen, Malloy & Nguyen (2020, JoF) — "Lazy Prices" — 30-60 bps/month from MD&A YoY similarity
- López de Prado (2018) — Triple-Barrier + Meta-Labeling improves precision
- Sang, Kim & Verdi (2024, JAR) — Vocal Delivery Quality independent of text sentiment

---

## 31. Factor Consolidation Layer (Phase 4)

### 31.1 Chen-Zimmermann Open Source Asset Pricing (OSAP)

**Source**: openassetpricing.com (October 2025 release)
**License**: Free CSV/parquet downloads; signal recompute requires WRDS
**Coverage**: 319 cross-sectional anomalies, all peer-reviewed
**Library**: `pip install openassetpricing` (Peng Li wrapper)

**Use case**: Treat each signal as a feature. Cross-sectionally rank, feed into LightGBM.

```python
import openassetpricing as oap
signals = oap.get_signals_long()  # Long-format DataFrame
```

**Key signals not in DIY plan**: Asness/Frazzini Quality minus Junk extensions, Stambaugh-Yuan Mispricing 11-factor composite, Daniel-Hirshleifer-Sun behavioral factors, Hou-Xue-Zhang q5 factors.

**Re-verification**: Check openassetpricing.com for current release; signal list expanded over time.

### 31.2 Jensen-Kelly-Pedersen (JKP) Factor Library

**Source**: jkpfactors.com
**License**: CC BY-NC 4.0 (non-commercial)
**Coverage**: 153 factors organized in 13 theme clusters
**Format**: Monthly long-short factor returns CSV (free); stock-level needs WRDS

**Theme clusters** (use to reduce dimension):
1. Accruals
2. Debt Issuance
3. Investment
4. Low Leverage
5. Low Risk
6. Momentum
7. Profit Growth
8. Profitability
9. Quality
10. Seasonality
11. Size
12. Skewness
13. Value

**Use case**: Use cluster-level factor returns as macro signals; avoid double-counting collinear signals.

### 31.3 Microsoft Qlib Alpha158

**Source**: github.com/microsoft/qlib
**License**: MIT
**Coverage**: 158 hand-crafted technical features

**Published benchmarks** (CSI300 China A-share, illustrative):
- LightGBM Rank IC ≈ 0.0482, ICIR ≈ 1.57
- HIST GNN Rank IC ≈ 0.0628
- Alpha360 (raw OHLCV alternative) similar performance

**Use case**: Drop-in replacement for hand-coded technical indicators (Section 7).

```python
from qlib.contrib.data.handler import Alpha158
handler = Alpha158(...)
features = handler.fetch(...)
```

**Re-verification**: Test on free GitHub Actions runner; may need pre-compute on Kaggle.

### 31.4 IPCA — Instrumented Principal Component Analysis

**Paper**: Kelly, Pruitt & Su (2019, JFE "Characteristics are Covariances")
**Library**: `pip install ipca` (github.com/bkelly-lab/ipca)
**License**: MIT

**What it does**: Estimates a 5-factor latent model where loadings are time-varying and instrumented by characteristics. Substantially fewer parameters than ML black-box models.

**Use case**: Take OSAP/JKP signals as instruments → output 5 latent factor exposures → use as ML features.

```python
from ipca import InstrumentedPCA
ipca = InstrumentedPCA(n_factors=5, intercept=True)
ipca.fit(X=characteristics_panel, y=returns_panel, indices=panel_index)
factor_exposures = ipca.predict_panel(...)
```

**Expected lift over Fama-French**: +0.5-1.5% alpha when used as residual return signal.

---

## 32. ML Enhancements (Phase 5)

### 32.1 Triple-Barrier Method

**Paper**: López de Prado (2018) — Advances in Financial ML
**Library**: `pip install mlfinlab` ⚠️ AGPL-3.0 (verify license)

**What**: Replaces fixed-horizon return labels with three barriers — take-profit, stop-loss, time barrier — scaled by daily volatility. Captures path-dependent outcomes.

```python
import mlfinlab as ml
events = ml.filters.cusum_filter(close, threshold=daily_vol.mean()*0.5)
t1 = ml.labeling.add_vertical_barrier(events, close, num_days=21)
triple = ml.labeling.get_events(close, events, pt_sl=[1,1], target=daily_vol, t1=t1)
labels = ml.labeling.get_bins(triple, close)
```

**Why better than fixed labels**: Doesn't reward signals that work after stops would have triggered.

### 32.2 Meta-Labeling

**Concept**: Two-model architecture
- Primary model (LightGBM): predicts BUY/HOLD signal
- Secondary model (XGBoost or LightGBM): predicts probability primary is correct

**Use**: Position sizing — large position only when secondary confidence is high.

**Documented impact**: Singh & Joubert (2019) — meaningful precision/recall improvements; better drawdown profile.

### 32.3 Conformal Prediction

**Paper**: Chernozhukov et al. (2021, PNAS) — Distributional Conformal Prediction
**Library**: `pip install mapie` (BSD-3-Clause, fully compatible)

**What**: Distribution-free prediction intervals with valid coverage under heteroskedasticity.

```python
from mapie.regression import MapieRegressor
mapie = MapieRegressor(estimator=lgbm, method="cv_plus", cv=5)
mapie.fit(X_train, y_train)
y_pred, y_pis = mapie.predict(X_test, alpha=0.1)  # 90% intervals
```

**Use case**: Size positions by interval width — narrow interval = high confidence = larger size.

**Expected lift**: +0.1-0.3% alpha + Sharpe lift +0.1 via better risk allocation.

### 32.4 Conditional Autoencoder Asset Pricing (Optional)

**Paper**: Gu, Kelly & Xiu (2021, JoE) — Autoencoder Asset Pricing Models
**Repo**: github.com/rongwang0824/Autoencoder-Asset-Pricing-Models

**What**: Nonlinear generalization of IPCA. Autoencoder bottleneck = latent factors; loadings parameterized by NN over characteristics.

**Compute**: Trains in <1hr on Colab T4.

**Expected lift over LightGBM-only**: +0.2-0.5% alpha + better tail behavior.

---

## 33. Sentiment v2 (Phase 6)

### 33.1 Whisper Earnings Call Audio

**Source**: openai-whisper (open source, free)
**Compute**: Modal $30/mo credits = ~50 GPU-hrs T4 free monthly
**Audio source**: Free from IR websites + Seeking Alpha public archive

**Pipeline**:
1. Scrape audio URLs from IR websites (legal, public)
2. Transcribe with Whisper-medium (fast, accurate)
3. Extract Wav2Vec2 features for vocal delivery quality

### 33.2 Vocal Delivery Quality (VDQ)

**Paper**: Sang, Kim & Verdi (2024, J. of Accounting Research) — "Vocal delivery quality in earnings conference calls"
**Earlier**: Mayew & Venkatachalam (2012, JoF), Cao et al. (2023, RAS — "CEO vocal cues")

**What**: Audio features (pitch, intensity, jitter, shimmer) capture executive uncertainty/confidence independently of text sentiment.

**Documented alpha**: +0.2-0.4% as orthogonal signal to FinBERT text.

```python
import whisper
import torchaudio
# Whisper for transcription
model = whisper.load_model("medium")
result = model.transcribe(audio_path)
transcript = result["text"]
# Wav2Vec2 for vocal features
# (extract pitch contour, energy, etc.)
```

### 33.3 8-K Item-Level Events

**Source**: SEC EDGAR free
**Library**: edgartools

**Items with documented signed CARs**:
- **Item 1.01** (Material Definitive Agreement / M&A): mostly positive for target, small for acquirer
- **Item 4.02** (Non-Reliance Restatement): -2.6% to -5.4% CAR (Schroeder 2024)
- **Item 5.02** (Mgmt Change): mixed signal, sign depends on context
- **Item 1.05** (Cybersecurity): negative
- **Item 2.05** (Costs of Exit/Disposal): negative

**Implementation**: Parse 8-K via edgartools, classify item, compute event-window CAR feature.

### 33.4 Lazy Prices (MD&A YoY Similarity)

**Paper**: Cohen, Malloy & Nguyen (2020, JoF) — "Lazy Prices"
**Library**: sentence-transformers (free)
**Documented alpha**: 30-60 bps/month long-short

**What**: Stocks whose 10-K MD&A language changes substantially from prior year underperform — the change signals new risks management is "burying" in lengthy prose.

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer('all-MiniLM-L6-v2')
emb_y1 = model.encode(mda_text_year1)
emb_y2 = model.encode(mda_text_year2)
similarity = cosine_similarity([emb_y1], [emb_y2])[0][0]

# Lower similarity = more change = lower expected return
```

### 33.5 SKIP for Megacap

**Research finding**: Reddit/StockTwits/WSB sentiment **has no documented alpha at S&P 500 scale**. The alpha exists for small-caps only.

**Action**:
- Phase 6 (S&P 500 scope): SKIP Reddit/StockTwits
- Phase 8 (S&P 1500 scope): Revisit for small-cap segment

---

## 34. Regime + Portfolio v2 (Phase 7)

### 34.1 Student-t HMM (vs Gaussian)

**Why**: Lee 2026 (KAIST) — Student-t emission better captures fat-tailed crisis returns.

**Implementation**: Custom emission distribution in hmmlearn or Pyro/PyMC.

### 34.2 Topological Data Analysis (TDA)

**Paper**: Gidea & Katz (2018), Akingbade et al. (2023)
**Library**: `gtda` (giotto-tda) ⚠️ AGPL-3 — verify

**What**: Persistent homology on rolling correlation matrices. Detects topological "phase transitions" before crashes.

**Use**: Risk-off gate (not return signal). Reduce exposure when persistence landscapes shift.

### 34.3 Nested Clustered Optimization (NCO)

**Paper**: López de Prado (2019)
**Library**: `pip install skfolio` (BSD-3-Clause, compatible)

**What**: Hierarchical optimization. Cluster assets first, optimize within clusters, then between clusters. More stable than HRP under noisy correlations.

```python
from skfolio.optimization import NestedClustersOptimization
from skfolio.cluster import HierarchicalClustering

nco = NestedClustersOptimization(
    inner_estimator=...,
    outer_estimator=...,
    clustering_estimator=HierarchicalClustering(),
)
nco.fit(returns)
weights = nco.weights_
```

**Expected Sharpe lift over HRP**: +0.05-0.15.

---

## 35. Honest Decay & Replication Caveats

### 35.1 The Decay Reality

McLean-Pontiff (2016, JoF):
- 26% decay in-sample to OOS
- 32% additional decay post-publication
- Combined: ~50% decay realistic

Falck-Rej-Thesmar (2022, QF):
- Newer factors decay 5pp/year MORE than older ones
- Post-2018 factors should be expected to decay faster

Chen-Lou-Robotti (2023, JFQA):
- 90th percentile anomaly post-2005: ~10.5 bps/month gross
- Post-cost: 93% decay → near zero

**Implication**: Budget 35-50% decay on any research-backed factor. Don't expect published numbers to replicate.

### 35.2 Replication Crisis Mitigation

JKP (2023, JoF) — "Is There a Replication Crisis in Finance?":
- Most factors DO survive multiple-testing corrections
- BUT magnitudes are materially smaller than originals
- Theme clustering reduces multiple testing burden

**Mitigation strategies**:
1. Use library replications (OSAP, JKP) — they've already corrected
2. Validate own implementations against published t-stats (5% tolerance)
3. Decay monitoring: rolling 24-month IC, alert if slope < 0
4. Quarterly re-validation against original papers

### 35.3 What We Are NOT Promising

**Honest disclaimers for users**:
- Not a guarantee of profit
- Not a substitute for fundamental research
- Not real-time / not intraday
- Not for short-term trading
- 25-30% probability of negative alpha in any 3-year window
- Past performance ≠ future results
- Backtest performance > live performance (always)
- Some factors will decay over time
- License compatibility may change

### 35.4 Performance Honesty Hierarchy

| Net Alpha vs SPY | Verdict |
|---|---|
| 0-2% | Honest baseline; expect this most of the time |
| 2-4% | Strong execution + benign regime; Option A target |
| 3-7% | Option B target; requires research-backed pipeline |
| 7-10% | Suspicious; likely overfit or in-sample bias |
| >10% | Overfit. Reject. |

### 35.5 Validation Discipline (Hard Vetoes)

Before shipping ANY research-backed phase:
- ✅ Mean IC OOS ≥ 0.02
- ✅ PBO < 0.5
- ✅ Deflated Sharpe > 0
- ✅ Compute time < 6 hrs (or moved to Kaggle/Modal)
- ✅ Net alpha vs SPY ≥ 0% post-cost
- ✅ License compatibility verified
- ✅ Replication QC ≥ 50% match published

If ANY criterion fails → Option A fallback for that phase.

---

# Quick Reference — Summary Tables

## A. Pillar → Metrics Mapping

| Pillar | Key Metrics |
|---|---|
| **Quality** | Piotroski F, ROE, ROIC, Gross Profitability, MSCI 3-desc, Quality persistence |
| **Value** | P/E, P/B, P/S, EV/EBITDA, EV/FCF, Earnings Yield, Graham Number, Tobin's Q |
| **Growth** | Rev/EPS/FCF CAGR (3y, 5y), Sustainable Growth Rate, Analyst revisions |
| **Momentum** | 12-1, 6-1, 3-1 momentum, Residual momentum, 52w-high distance, RSI, MACD |
| **Health** | Current/Quick Ratio, D/E, Interest Coverage, Altman Z″, Net Debt/FCF |
| **Sentiment** | FinBERT news, Reddit acceleration, StockTwits bull%, Insider Form 4 cluster, Options PCR, Google Trends |
| **ML** | LightGBM LambdaRank composite |
| **Risk (low-risk bias)** | σ_252, β, Sharpe (positive), MaxDD, GARCH vol forecast, IVOL |
| **Macro/Regime** | HMM state, yield curve position, sector rotation phase |

## B. Risk Vetoes (override top-rank)

- Beneish M-Score > −1.78 (likely manipulator)
- Sloan accruals top decile (earnings quality red flag)
- Altman Z″ < 1.23 (distress zone)
- Item 4.02 8-K filing in last 90 days (restatement)
- Isolation Forest anomaly flag

## C. Free Data Source Cheat Sheet

| Need | First choice | Fallback |
|---|---|---|
| Prices | yfinance | Tiingo, Polygon |
| Fundamentals | edgartools (SEC) | SimFin, FMP |
| News | Finnhub | yfinance, NewsAPI |
| Macro | FRED | World Bank |
| Insider | edgartools (Form 4) | Finnhub |
| 13F | edgartools | WhaleWisdom (paid) |
| Sentiment NLP | FinBERT (HF) | VADER |
| Reddit | PRAW | — |
| Trends | pytrends | — |
| Options | yfinance + CBOE | ORATS (paid) |
| Factor returns | Ken French / AQR | — |

## D. Critical Python Libraries

```python
# Data
import yfinance as yf
from edgar import Company, get_filings
from fredapi import Fred
import finnhub
import praw
from pytrends.request import TrendReq

# Analysis
import pandas as pd, numpy as np
import ta, pandas_ta
from arch import arch_model
from hmmlearn.hmm import GaussianHMM
import statsmodels.api as sm

# ML
import lightgbm as lgb
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import TimeSeriesSplit
from transformers import pipeline
import shap

# Portfolio
from pypfopt import HRPOpt, BlackLittermanModel, EfficientFrontier, risk_models
import riskfolio as rp

# Backtest
import alphalens
import vectorbt as vbt
import quantstats as qs
```

---

**END OF KNOWLEDGE BASE**

This document provides everything an LLM coding agent needs to build a state-of-the-art US equity stock ranking application from scratch using only free or low-cost data sources. All techniques are mathematically specified, with Python implementation hints and known limitations clearly stated.
