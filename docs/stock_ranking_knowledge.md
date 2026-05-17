# Stock Ranking App — Complete Knowledge Base
**A unified, code-ready reference for building a state-of-the-art US equity ranking application**

> This document is the consolidated project knowledge for an LLM coding agent (Claude Code) to implement a multi-pillar, multi-discipline stock ranking system. Contains:
> - **Parts I-V (Sections 1-29)**: Classical fundamental/technical/factor/risk techniques — 60+ academically-grounded techniques
> - **Part VI (Sections 30-35)**: ⭐ NEW — Research-backed stretch additions for Option B roadmap (Phase 4+)
>
> All implementable with **free or low-cost data sources** for **weekly/monthly refresh**.

> **Companion docs**: `SKILL.md` (architecture rules), `WORKFLOW.md` (phase plan), `RESEARCH_FINDINGS.md` (Option B research detail with full citations).

---

## ⚠️ READ FIRST: Honest Performance Ceiling

Before building anything, internalize these realistic numbers:

| Path | Net Alpha vs SPY | Sharpe Lift | CAGR | Time |
|---|---|---|---|---|
| **Buy & hold SPY** | 0% | baseline | ~10% | passive |
| **Option A (DIY, Parts I-V only)** | 2-4% | +0.2 to +0.4 | 12-13% | ~5-6 wk |
| **Option B (research-backed, +Part VI)** | 3-7% | +0.3 to +0.5 | 13-17% | ~7-8 wk |

**Wide confidence interval**: [0%, +5%] on any 3-year window. ~25-30% probability of negative alpha in any given 3-year period due to factor crowding, regime change, post-publication decay.

**Sources**: McLean & Pontiff (2016, JoF) — 35% post-publication decay; Hou-Xue-Zhang (2020, RFS) — 65% of anomalies fail at NYSE-breakpoint hurdle; Avramov-Cheng-Metzker (2023, MS) — ML alpha mostly disappears in S&P 1500 large-cap universe; Falck-Rej-Thesmar (2022, QF) — ~50% Sharpe drop post-publication.

**Anything claiming >7% net alpha should trigger overfit suspicion.** See Section 28 + Section 35 caveats.

---

## Table of Contents

**PART I-V — CLASSICAL TECHNIQUES (Sections 1-29)**
- Sections 1-11: Fundamental, Technical, Factor, Valuation analysis
- Sections 12-20: Sentiment, ML, Advanced Quant, Macro/Regime, Behavioral
- Sections 21-24: Composite scoring, validation
- Sections 25-29: Implementation, accuracy expectations, caveats

**PART VI — RESEARCH-BACKED ADDITIONS (Sections 30-35) ⭐ NEW**
- Section 30: Why Option B
- Section 31: Factor Consolidation Layer (Phase 4) — OSAP, JKP, Qlib, IPCA
- Section 32: ML Enhancements (Phase 5) — Triple-Barrier, Meta-Labeling, Conformal
- Section 33: Sentiment v2 (Phase 6) — Whisper, 8-K, Lazy Prices
- Section 34: Regime + Portfolio v2 (Phase 7) — Student-t HMM, TDA, NCO
- Section 35: Honest Decay & Replication Caveats

---

# 1. FUNDAMENTAL ANALYSIS TECHNIQUES

## 1.1 Piotroski F-Score (Stanford, Joseph Piotroski 2000)

**Origin:** Joseph Piotroski, "Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers" (Journal of Accounting Research, 2000), while at University of Chicago Booth (now Stanford GSB).

**Score range:** 0–9 (integer). Each criterion = 1 point if true, else 0.

| # | Category | Criterion | Formula | Inputs |
|---|----------|-----------|---------|--------|
| 1 | Profitability | Positive Net Income | NI > 0 | Income stmt |
| 2 | Profitability | Positive ROA | NI / Total Assets > 0 | IS + BS |
| 3 | Profitability | Positive Operating Cash Flow | CFO > 0 | Cash flow stmt |
| 4 | Profitability | Accruals (Quality of Earnings) | CFO / Total Assets > ROA | CF + IS + BS |
| 5 | Leverage | Decrease in Long-Term Debt Ratio | LT Debt_t / TA_t < LT Debt_{t-1} / TA_{t-1} | BS |
| 6 | Liquidity | Increase in Current Ratio | CR_t > CR_{t-1} | BS |
| 7 | Funding | No New Shares Issued | Shares_t ≤ Shares_{t-1} | BS |
| 8 | Operating | Increase in Gross Margin | (Rev_t − COGS_t)/Rev_t > prior year | IS |
| 9 | Operating | Increase in Asset Turnover | Rev_t / TA_{t−1} > Rev_{t−1}/TA_{t−2} | IS + BS |

**Interpretation:** 8–9 strong, 4–6 neutral, 0–2 weak. Originally designed for high book-to-market (value) stocks.

**Normalization to 0-100:** `score_100 = (F_Score / 9) × 100`.

**Strengths:** Discrete, explainable, bankruptcy-resistant. **Limitations:** Backward-looking; less useful for growth/tech firms; needs at least 2 years of data.

---

## 1.2 Altman Z-Score (NYU Stern, Edward Altman 1968)

**Original public manufacturing formula:**

> **Z = 1.2·X₁ + 1.4·X₂ + 3.3·X₃ + 0.6·X₄ + 1.0·X₅**

Where:
- X₁ = Working Capital / Total Assets
- X₂ = Retained Earnings / Total Assets
- X₃ = EBIT / Total Assets
- X₄ = Market Value of Equity / Total Liabilities
- X₅ = Sales / Total Assets

**Zones:** Z > 2.99 = Safe; 1.81 ≤ Z ≤ 2.99 = Grey; Z < 1.81 = Distress.

**Z″-Score (Non-manufacturers, public/private) — RECOMMENDED for general US screener (excludes industry-distorting X₅):**

> **Z″ = 6.56·X₁ + 3.26·X₂ + 6.72·X₃ + 1.05·X₄**

**Zones (Altman 2003 update for non-manufacturers, *Corporate Financial Distress and Bankruptcy*, 3rd ed., Wiley):** Safe > 2.6; Grey 1.1–2.6; Distress < 1.1.

> **Note**: Earlier versions of this document listed the zones as
> "Safe > 2.90; Grey 1.23–2.90; Distress < 1.23". Those values were
> mistakenly carried over from the original 1968 Z-score.
> The 1.10 distress cutoff is from Altman & Hotchkiss (2003) and is
> what `compute/scoring/risk_overlay.py:ALTMAN_DISTRESS_THRESHOLD = 1.10`
> implements.

**Z′-Score (private manufacturer):** 0.717·X₁ + 0.847·X₂ + 3.107·X₃ + 0.42·X₄ + 0.998·X₅ (uses book value of equity in X₄).

**0–100 normalization:** Clip Z to [0, 6], then `score = min(Z, 6) / 6 × 100` (or use sigmoid: `100/(1+exp(−(Z−2.5)))`).

**Strengths:** Robust, 50-year track record. **Limitations:** Original calibrated to manufacturers; financials and asset-light tech firms need Z″; abnormally high market cap (X₄) can mask weak fundamentals.

---

## 1.3 Beneish M-Score (Indiana Kelley, Messod Beneish 1999)

Detects probability of earnings manipulation using 8 ratios (`t` = current year, `t−1` = prior year).

> **M = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI**

| Variable | Formula |
|---|---|
| **DSRI** Days Sales Receivables Index | (AR_t/Sales_t) / (AR_{t-1}/Sales_{t-1}) |
| **GMI** Gross Margin Index | GM_{t-1} / GM_t |
| **AQI** Asset Quality Index | [1−(CA_t+PP&E_t+Sec_t)/TA_t] / [1−(CA_{t-1}+PP&E_{t-1}+Sec_{t-1})/TA_{t-1}] |
| **SGI** Sales Growth Index | Sales_t / Sales_{t−1} |
| **DEPI** Depreciation Index | (Dep_{t-1}/(Dep_{t-1}+PP&E_{t-1})) / (Dep_t/(Dep_t+PP&E_t)) |
| **SGAI** SG&A Index | (SGA_t/Sales_t) / (SGA_{t-1}/Sales_{t-1}) |
| **TATA** Total Accruals to Total Assets | (NI − CFO) / TA |
| **LVGI** Leverage Index | (LTD_t+CL_t)/TA_t / (LTD_{t-1}+CL_{t-1})/TA_{t-1} |

**Threshold:** M > −1.78 ⇒ likely manipulator (some sources use −2.22 as a more conservative threshold). M < −2.22 ⇒ unlikely.

**0–100 normalization (inverted, since lower = better):** `score = clip((−1.78 − M) / 2 × 50 + 50, 0, 100)`.

**Strengths:** Famously flagged Enron pre-collapse. **Limitations:** Probabilistic, not deterministic; high false-positive rate; requires 2 years of detailed data; coefficients calibrated to 1982-1992 US data.

---

## 1.4 Magic Formula (Joel Greenblatt, "The Little Book that Beats the Market", 2005)

Two ranks combined:

> **ROC (Greenblatt) = EBIT / (Net Working Capital + Net Fixed Assets)**
> **Earnings Yield (Greenblatt) = EBIT / Enterprise Value**
> EV = Market Cap + Total Debt − Cash & Equivalents

**Procedure:**
1. Universe: market cap > $50M-$100M; **exclude financials, utilities, foreign ADRs**.
2. Rank all stocks by ROC (high to low) → Rank_ROC.
3. Rank all stocks by Earnings Yield (high to low) → Rank_EY.
4. **Magic Formula Score = Rank_ROC + Rank_EY** → lowest combined number wins.

**0–100 normalization:** `score = 100 × (1 − combined_rank / max_combined_rank)`.

**Strengths:** Minimal data needs; backtested ~30% annualized 1988-2004 in Greenblatt's book; ~3% alpha in independent backtests (Martin, 2020). **Limitations:** Ignores debt structure for ROC; backtests have data-snooping risks; excludes whole sectors.

---

## 1.5 Graham Number & Defensive Investor Criteria (Benjamin Graham, *The Intelligent Investor* 1949)

**Graham Number (max defensive price):**

> **Graham Number = √(22.5 × EPS × BVPS) = √(15 × P/E_max × 1.5 × P/B_max × EPS × BVPS)**

The 22.5 = 15 (max P/E) × 1.5 (max P/B). Use **3-year average EPS** as Graham specified.

**Buy if** Current Price < Graham Number. **Margin of Safety % = (GN − Price) / GN.**

**Defensive Investor 7 Criteria:**
1. **Adequate size:** Sales > $500M (inflation-adjusted from Graham's $100M).
2. **Strong financial condition:** Current Ratio ≥ 2; LT Debt < Net Current Assets.
3. **Earnings stability:** Positive EPS for 10 consecutive years.
4. **Dividend record:** Uninterrupted dividends for 20 years.
5. **Earnings growth:** ≥ 33% growth in 3-yr avg EPS over last 10 years.
6. **Moderate P/E:** ≤ 15 (using 3-yr avg EPS).
7. **Moderate P/B:** P/E × P/B ≤ 22.5.

**Graham Formula (growth-adjusted intrinsic value, 1962/1973 — use cautiously):**

> **V = EPS × (8.5 + 2g) × 4.4 / Y** where g = 7-10yr expected growth %, Y = current AAA corporate bond yield.

Graham himself warned this is illustrative, not predictive. Many modern adaptations replace 4.4 with current rate.

**0–100 normalization:** `score = clip(MoS%, −100, 100) / 2 + 50`.

**Limitations:** Does not work for asset-light/negative-earnings/high-growth firms.

---

## 1.6 Peter Lynch PEG Ratio (*One Up on Wall Street*, 1989)

> **PEG = (P/E) / Earnings Growth Rate (%)**

Lynch's heuristics:
- PEG < 0.5 = strong buy
- 0.5 ≤ PEG < 1.0 = attractive
- PEG ≈ 1.0 = fairly valued
- PEG > 2.0 = overvalued

**Dividend-adjusted PEG:** PEG = P/E / (Growth + Dividend Yield).

**Inputs:** Use forward P/E with 3-5yr expected growth, or trailing P/E with 5yr historical EPS CAGR.

**0–100 normalization (inverted):** `score = clip(100 × (2 − PEG) / 2, 0, 100)`.

**Limitations:** Highly sensitive to growth estimate; meaningless for negative earnings; cyclical EPS distorts PEG.

---

## 1.7 Discounted Cash Flow (Simplified 2-Stage)

**Free Cash Flow to Firm (FCFF) DCF:**

> **Enterprise Value = Σ_{t=1..N} FCF_t / (1+WACC)^t + TV / (1+WACC)^N**
> **Equity Value = EV − Net Debt + Cash**
> **Fair Price/Share = Equity Value / Shares Outstanding**

**Terminal Value (Gordon Growth):**

> **TV = FCF_{N+1} / (WACC − g) = FCF_N × (1+g) / (WACC − g)**

Where g = perpetual growth rate (typically 2-3%, capped at long-term GDP growth).

**Inputs:**
- FCF = Operating Cash Flow − CapEx (from cash flow statement)
- WACC = (E/V)·Re + (D/V)·Rd·(1−Tax). For free-tier simplicity, use **discount rate = 10%** as a default proxy.
- Cost of equity (Re) via CAPM: `Re = Rf + β × (Rm − Rf)`. Use Rf = 10yr Treasury yield, Rm − Rf = 5-6%.

**Free-tier proxy approach:** Project FCF growth at historical 5-yr CAGR (capped at 15%) for 5 years, then 3% perpetual. Discount at 10%. This works with yfinance `cashflow` and `info['totalDebt']`.

**Reverse DCF:** Solve for the implied growth rate `g` that makes DCF = current market price. Useful sanity check on what growth rate is "priced in."

---

## 1.8 Dividend Discount Model (DDM) — Gordon Growth

> **P₀ = D₁ / (r − g) = D₀ × (1+g) / (r − g)**

Multi-stage version sums explicit-period dividends + terminal value. Only meaningful for stable dividend payers (utilities, consumer staples).

---

## 1.9 Free Cash Flow Yield, Earnings Yield, ROIC, Owner Earnings

| Metric | Formula | Source |
|---|---|---|
| **FCF Yield** | FCF / Market Cap (or FCF/EV) | CF stmt + price |
| **Earnings Yield** | EPS / Price = 1/(P/E) | IS + price |
| **ROIC** | NOPAT / Invested Capital = EBIT(1−t) / (Total Debt + Equity − Cash) | IS + BS |
| **Owner Earnings** (Buffett 1986 letter) | Net Income + D&A + Other Non-cash − Maintenance CapEx ± ΔWC | IS + CF |
| **P/Owner Earnings** | Price / OE per share | derived |

**Maintenance CapEx proxy (Bruce Greenwald method):** PP&E/Sales 5-yr avg × ΔSales = Growth CapEx; Maintenance CapEx = Total CapEx − Growth CapEx.

**Simplified Owner Earnings:** `OE = Operating Cash Flow − CapEx` (this equals FCF, an acceptable approximation).

---

# 2. TECHNICAL ANALYSIS INDICATORS

All inputs are OHLCV from yfinance daily prices. Recommended Python library: **`ta`** (technical-analysis-library-in-python) or **`pandas_ta`**, both pure-Python.

## 2.1 RSI (Wilder, 14-period default)

```
RS = Avg Gain / Avg Loss (Wilder's smoothing)
RSI = 100 − 100/(1+RS)
```

**Interpretation:** > 70 overbought, < 30 oversold. **0-100 score (already 0-100; for ranking favor mid-range or use −|RSI−50|).**

## 2.2 MACD

```
MACD Line = EMA(12) − EMA(26)
Signal Line = EMA(MACD, 9)
Histogram = MACD − Signal
```

**Signals:** MACD crossing above Signal = bullish; histogram > 0 and rising = strengthening trend.

## 2.3 Moving Averages — Golden/Death Cross

- SMA_n = Σ Close / n
- EMA_n = Close_t × α + EMA_{t−1} × (1−α), α = 2/(n+1)
- **Golden Cross:** SMA_50 crosses above SMA_200 (bullish long-term).
- **Death Cross:** SMA_50 crosses below SMA_200 (bearish).

**Trend score (0-100):** `100 × (Price − SMA_200) / SMA_200`, clipped to [−50, +50] then shifted to [0, 100].

## 2.4 Bollinger Bands (20, 2)

```
Middle = SMA(Close, 20)
Upper = Middle + 2·σ_20
Lower = Middle − 2·σ_20
%B = (Close − Lower) / (Upper − Lower)
Bandwidth = (Upper − Lower) / Middle
```

%B > 1 above upper band; < 0 below lower band.

## 2.5 Stochastic Oscillator

```
%K = 100 × (Close − Low_14) / (High_14 − Low_14)
%D = SMA(%K, 3)
```

> 80 overbought, < 20 oversold.

## 2.6 ADX (Wilder, 14)

```
+DM = max(High_t − High_{t-1}, 0) when High Δ > Low Δ else 0
−DM = max(Low_{t-1} − Low_t, 0) when Low Δ > High Δ else 0
TR = max(High−Low, |High−PrevClose|, |Low−PrevClose|)
+DI = 100 × Smoothed(+DM)/ATR, −DI = 100 × Smoothed(−DM)/ATR
DX = 100 × |+DI − −DI| / (+DI + −DI)
ADX = Wilder-smoothed DX over 14 periods
```

**ADX Interpretation:** < 20 weak/no trend; 20-25 emerging; 25-50 strong; > 50 very strong (regardless of direction).

## 2.7 OBV (Granville)

```
If Close_t > Close_{t-1}: OBV_t = OBV_{t-1} + Volume_t
If Close_t < Close_{t-1}: OBV_t = OBV_{t-1} − Volume_t
Else: OBV_t = OBV_{t-1}
```

Score by OBV slope or divergence with price.

## 2.8 Money Flow Index (volume-weighted RSI, default 14)

```
Typical Price (TP) = (High + Low + Close) / 3
Raw Money Flow = TP × Volume
Positive MF = sum of RMF on up-days; Negative MF = sum on down-days
Money Ratio = Positive MF / Negative MF
MFI = 100 − 100/(1 + Money Ratio)
```

> 80 overbought, < 20 oversold.

## 2.9 ATR (Wilder, 14)

```
TR = max(High−Low, |High−PrevClose|, |Low−PrevClose|)
ATR = Wilder smoothing of TR over 14 periods
```

Use for volatility-based position sizing and stop placement.

## 2.10 Ichimoku Cloud

```
Tenkan-sen (Conversion) = (High_9 + Low_9) / 2
Kijun-sen (Base)        = (High_26 + Low_26) / 2
Senkou Span A           = (Tenkan + Kijun) / 2,   plotted +26 forward
Senkou Span B           = (High_52 + Low_52) / 2, plotted +26 forward
Chikou Span (Lagging)   = Close,                  plotted −26 backward
The "Cloud" (Kumo)      = area between Span A & Span B
```

**Bullish:** Price above cloud + Tenkan > Kijun + Span A > Span B + Chikou above past price.

**Composite Tech Score (0-100):** Average of normalized RSI, MACD-histogram-sign, ADX strength, % above SMA200, and Ichimoku state.

---

# 3. QUANTITATIVE / FACTOR INVESTING

## 3.1 CAPM (Sharpe 1964)

> **E[R_i] − R_f = β_i × (E[R_m] − R_f)**

β_i = Cov(R_i, R_m) / Var(R_m) — estimate via OLS regression of stock excess returns on market excess returns over 36-60 months.

## 3.2 Fama-French 3-Factor (1993, U Chicago / Dartmouth)

> **R_i − R_f = α + β·(R_m − R_f) + s·SMB + h·HML + ε**

- **SMB (Small Minus Big):** small-cap return minus large-cap return.
- **HML (High Minus Low):** high B/M ("value") minus low B/M ("growth").

## 3.3 Carhart 4-Factor (1997, "On Persistence in Mutual Fund Performance")

> **R_i − R_f = α + β·MKT + s·SMB + h·HML + w·UMD + ε**

- **UMD / WML / MOM (Up Minus Down):** Top-30% prior 12-month returns minus bottom 30%, **skipping the most recent month** to avoid short-term reversal.

## 3.4 Fama-French 5-Factor (2015)

> **R_i − R_f = α + β·MKT + s·SMB + h·HML + r·RMW + c·CMA + ε**

- **RMW (Robust Minus Weak):** profitable minus unprofitable, where "profitability" = (Revenue − COGS − Interest − SG&A) / Book Equity.
- **CMA (Conservative Minus Aggressive):** firms with low asset growth minus high asset growth.

**Implementation tip:** Download monthly factor returns from **Ken French's data library** (free, mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html). Run OLS regression per stock to get factor loadings; interpret loadings as "factor tilts."

## 3.5 AQR Quality Minus Junk (Asness, Frazzini, Pedersen 2014)

QMJ defines **Quality = average of four sub-scores, each itself a z-score average of sub-components**:

1. **Profitability:** Gross profit/assets, ROE, ROA, CFO/assets, gross margin, low accruals.
2. **Growth:** 5-year average growth in profitability metrics above.
3. **Safety:** Low beta, low idiosyncratic volatility, low leverage, low bankruptcy risk (low O-Score), low ROE volatility.
4. **Payout:** Net equity issuance (negative is good), net debt issuance (negative is good), dividend payout.

QMJ portfolio = top 30% Quality long, bottom 30% short. **Free QMJ factor returns:** download from aqr.com Datasets (no key required).

## 3.6 MSCI Quality Index Methodology (3-descriptor composite)

Equally-weighted z-scores of:
1. **ROE** = Net Income / Book Equity (positive z-score = better)
2. **Debt-to-Equity** = Total Debt / Book Equity (negative z-score so lower is better)
3. **Earnings Variability** = Std Dev of YoY EPS growth, last 5 years (negative z-score)

**Process:** winsorize at 5th/95th percentile, compute z-scores, average → Quality Z-Score → optionally convert to percentile.

## 3.7 Value Factor — Multiple Definitions

| Metric | Formula | Notes |
|---|---|---|
| P/E | Price / TTM EPS | Most common |
| P/B | Price / Book Value per Share | Original Fama-French value definition |
| P/S | Price / Sales | Useful for unprofitable firms |
| EV/EBITDA | EV / EBITDA | Capital-structure neutral |
| EV/Sales | EV / Revenue | Robust to capital structure & profitability |
| EV/FCF | EV / Free Cash Flow | Cash-quality value |
| Earnings Yield (Greenblatt) | EBIT/EV | Magic Formula version |
| Shiller P/E (CAPE) | Price / 10-yr avg inflation-adjusted EPS | Index-level only |

**Composite Value Score:** Average percentile rank across 4-6 of these (sector-relative).

## 3.8 Momentum Factor

- **12-1 Momentum:** cumulative return from month t-12 to t-1 (skip last month).
- **6-1 Momentum:** prior 6 months excluding most recent.
- **52-week High proximity:** Price / 52-Week High.

**Score:** percentile rank of 12-1 momentum across universe.

## 3.9 Low Volatility Factor

Compute **σ_252** (1-year rolling daily-return standard deviation, annualized × √252). Rank ascending — lowest volatility scores highest. Empirically, lowest-vol quintile has historically produced higher Sharpe than highest-vol (Baker, Bradley, Wurgler 2011).

## 3.10 Profitability Factor

Use **Gross Profitability** (Novy-Marx 2013): GP / Total Assets = (Revenue − COGS) / TA. This was a key insight — gross profit, not net income, is the most robust profitability predictor of returns.

---

# 4. RISK METRICS

All assume daily returns r_t and annualization factor √252.

| Metric | Formula |
|---|---|
| **Sharpe Ratio** | (R̄_p − R_f) / σ_p, annualized |
| **Sortino Ratio** | (R̄_p − R_f) / σ_downside, where σ_downside uses only r_t < 0 (or < target) |
| **Treynor Ratio** | (R̄_p − R_f) / β_p |
| **Information Ratio** | (R̄_p − R̄_b) / σ(R_p − R_b) where b = benchmark |
| **Beta** | Cov(R_p, R_m) / Var(R_m), 36-60 month regression |
| **Calmar Ratio** | Annualized Return / |Max Drawdown| |
| **Maximum Drawdown** | min over t of [(P_t − running_max(P)) / running_max(P)] |
| **Standard Deviation of Returns** | σ × √252 |
| **VaR (Historical, 95%)** | 5th percentile of historical return distribution |
| **CVaR / Expected Shortfall (95%)** | Mean of returns ≤ VaR(95%) |

**Sharpe interpretation:** > 1 good, > 2 very good, > 3 excellent (annualized). **Calmar:** > 1 strong; widely used for trend-following / leveraged strategies.

**0-100 risk score:** A "low risk" composite can be `100 × (1 − percentile_rank(σ_252))` averaged with `100 × percentile_rank(Sharpe)`.

---

# 5. VALUATION MODELS — ENSEMBLE

## 5.1 DCF with Terminal Value
See section 1.7. Always run a sensitivity table: vary discount rate ±2% and terminal growth ±1%.

## 5.2 Relative Valuation
Multiples × benchmark = price. Compare each ratio (P/E, P/B, P/S, EV/EBITDA, EV/Sales) against:
- 5-year company median ("auto-correlation")
- Sector median (industry-relative)
- Market median (S&P 500)

**Fair price from multiples:** `Implied Price = (Sector_Median_PE × Company_EPS)`, then average across multiple ratios.

## 5.3 Reverse DCF
Solve for `g` such that DCF(g, WACC=10%) = current price. If implied g > 12-15% perpetual, the market is pricing in aggressive expectations.

## 5.4 Residual Income Model

> **V₀ = B₀ + Σ_{t=1..∞} (E_t − r·B_{t-1}) / (1+r)^t = B₀ + Σ (ROE_t − r) × B_{t-1} / (1+r)^t**

Where B = book value, E = earnings, r = cost of equity.

**Two-stage RIM:** Forecast residual income for 5 years explicitly + terminal RI capitalized as perpetuity. Best when ROE > cost of equity (firm creates value); meaningless for capital-light businesses.

## 5.5 Sum-of-the-Parts (SOTP)
For conglomerates: value each segment using sector-appropriate multiple (e.g., software EV/Sales, consumer EV/EBITDA), sum, deduct corporate overhead and net debt. Hard to fully automate; flag firms where revenue concentration in one segment > 80% to skip SOTP.

---

# 6. GROWTH METRICS

| Metric | Formula |
|---|---|
| **Revenue CAGR (n yr)** | (Rev_t / Rev_{t-n})^(1/n) − 1 |
| **EPS CAGR (n yr)** | (EPS_t / EPS_{t-n})^(1/n) − 1 (handle negatives via diff or log-protected) |
| **FCF CAGR** | Same on FCF |
| **Sustainable Growth Rate (SGR)** | ROE × (1 − Payout Ratio) = ROE × Retention |
| **PRAT model SGR** | Profit Margin × Retention × Asset Turnover × Equity Multiplier |
| **Internal Growth Rate** | ROA × Retention (no external financing) |
| **PEG** | (P/E) / EPS Growth Rate (%) |

Use 3-year and 5-year windows. **Score = average percentile rank across 3 growth windows.**

---

# 7. PROFITABILITY & EFFICIENCY

| Metric | Formula |
|---|---|
| Gross Margin | (Revenue − COGS) / Revenue |
| Operating Margin | EBIT / Revenue |
| Net Margin | Net Income / Revenue |
| ROE | Net Income / Avg Equity |
| ROA | Net Income / Avg Total Assets |
| ROIC | NOPAT / (Debt + Equity − Cash) |
| Asset Turnover | Revenue / Avg Total Assets |
| **Cash Conversion Cycle** | DIO + DSO − DPO |
| DIO | Avg Inventory / COGS × 365 |
| DSO | Avg AR / Revenue × 365 |
| DPO | Avg AP / COGS × 365 |

**Trend dimensions:** rather than a single year, use 5-year average and slope of each ratio. Rising margins/ROIC = quality improving.

---

# 8. FINANCIAL HEALTH

| Metric | Formula | Healthy Threshold |
|---|---|---|
| Current Ratio | Current Assets / Current Liabilities | ≥ 1.5 |
| Quick Ratio | (Cash + ST Inv + AR) / CL | ≥ 1.0 |
| Debt-to-Equity | Total Debt / Equity | < 1.0 (varies by sector) |
| Debt-to-Assets | Total Debt / Total Assets | < 0.6 |
| Interest Coverage | EBIT / Interest Expense | > 5× |
| Debt-to-EBITDA | Total Debt / EBITDA | < 3× investment grade |
| Net Debt / FCF | (Total Debt − Cash) / FCF | < 5× |

---

# 9. SCORING & RANKING METHODOLOGIES

## 9.1 Z-Score Normalization
For each metric `x` across the cross-section:
> **z_i = (x_i − μ) / σ**

After **winsorization** at 5th/95th percentile to handle outliers (per MSCI methodology). For "lower is better" metrics (D/E, P/E, volatility), use `z = −(x − μ)/σ`.

## 9.2 Percentile Rank (RECOMMENDED for Jitta-style apps)
> **percentile_i = rank(x_i) / N × 100**

**Strengths:** robust to outliers; produces 0-100 directly; easy to interpret. **Stockopedia's StockRanks** use this approach.

## 9.3 Sigmoid / Min-Max Scaling
- Min-Max: `(x − min)/(max − min) × 100`. Sensitive to outliers — only use after winsorization.
- Sigmoid: `100 / (1 + exp(−k·z))`. Smooth bounded output.

## 9.4 Composite Construction
Two-level hierarchy is standard:
- **Level 1 (Pillar Score):** Average percentile ranks of all metrics within a pillar (e.g., 6 value metrics → 1 Value Score).
- **Level 2 (Composite):** Weighted average of pillar scores.

**Recommended initial weights (Stockopedia/QVM-style):**
- Quality 33% / Value 33% / Momentum 34% (QVM)
- Or: Quality 25% / Value 25% / Growth 15% / Momentum 15% / Health 10% / Risk 10% (Jitta-like)

## 9.5 Missing Data
- If < 50% of a pillar's metrics are available → set pillar to neutral (50) and flag.
- For individual metric NaN → impute as sector median (NOT global median).
- Never propagate NaN; always log which fields were imputed.

## 9.6 Sector-Relative vs Absolute
**ALWAYS compute Quality/Value/Growth ranks within sector (GICS sector or industry).** Banks have systematically different ROE, leverage, P/B than tech firms. Use absolute scoring only for Risk (volatility, drawdown) and Momentum.

---

# 10. FAIR PRICE / TARGET PRICE — ENSEMBLE METHOD

This is the core of a Jitta-like app. Compute multiple fair-price estimates, then aggregate.

| Method | When Applicable |
|---|---|
| **DCF (Gordon Growth)** | Positive FCF + reasonable forecast |
| **Graham Number** | Positive EPS + Book Value, traditional sectors |
| **Residual Income Model** | Positive ROE > cost of equity |
| **DDM** | Stable dividend payer |
| **Multiple-based:** P/E × forward EPS | Always |
| **Multiple-based:** EV/EBITDA × EBITDA − Net Debt | Always for non-financials |
| **Multiple-based:** P/B × BVPS | Banks, capital-intensive |
| **Multiple-based:** P/S × Sales | Unprofitable / growth firms |

**Aggregation (recommended):**
1. Compute each applicable fair price; tag inapplicable (e.g., negative EPS → skip Graham).
2. Drop top and bottom values (trimmed mean) if you have ≥ 5 estimates.
3. **Fair Price = trimmed mean** OR median of applicable methods.
4. **Maximum Fair Price = 95th percentile / max of methods** (optimistic upper bound, like Jitta's "Fair Price").

**Margin of Safety:**
> **MoS % = (Fair Price − Current Price) / Fair Price × 100**

- MoS > 30% = strong buy zone (Graham's recommended)
- MoS 0–30% = fair to attractive
- MoS < 0% = overvalued

**Buy Score (0-100):** `clip(50 + MoS%, 0, 100)`.

---

# 11. DATA SOURCES & FREE-TIER REALITIES

## 11.1 yfinance (Yahoo Finance, unofficial Python)
- **Cost:** Free, unlimited, no key.
- **Best for:** Daily/intraday OHLCV history (decades), basic info (sector, market cap, beta, P/E), annual & quarterly income statement / balance sheet / cash flow via `Ticker.income_stmt`, `.balance_sheet`, `.cashflow`, `.quarterly_*`.
- **Available fields:** TotalRevenue, GrossProfit, OperatingIncome, NetIncome, EBITDA, BasicEPS, DilutedEPS, TotalAssets, CurrentAssets, CurrentLiabilities, TotalDebt, StockholdersEquity, OperatingCashFlow, CapitalExpenditure, FreeCashFlow, etc.
- **Caveats:** Unofficial; field names changed several times in 2023-2024; some methods (recommendations, sustainability) frequently break. Plan for retry/fallback. Not for real-money production trading systems.

## 11.2 Financial Modeling Prep (FMP) Free Tier
- **Cost:** Free, **250 calls/day**, US-only on free.
- **Endpoints (free):** `/income-statement/{symbol}`, `/balance-sheet-statement/{symbol}`, `/cash-flow-statement/{symbol}`, `/ratios/{symbol}`, `/key-metrics/{symbol}`, `/historical-price-full/{symbol}`, `/profile/{symbol}`, `/quote/{symbol}`, plus 250+ more.
- **Best for:** Pre-calculated ratios and key metrics (saves you from computing them); cleaner data than Yahoo.
- **Caveat:** 250 calls/day burns fast — fetching profile + 3 statements + ratios = 5 calls per ticker, so ~50 stocks/day. Cache aggressively to disk.

## 11.3 Alpha Vantage Free Tier
- **Cost:** Free, **25 calls/day, 5/min**.
- **Endpoints:** TIME_SERIES_DAILY/_ADJUSTED, INTRADAY, OVERVIEW (fundamentals), INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, EARNINGS, plus 50+ pre-computed technical indicators (RSI, MACD, BBANDS, ADX, ATR, MFI, OBV, STOCH, etc.).
- **Best for:** Pre-computed technical indicators if you don't want to build them. **Realtime/15-min delayed quotes are PREMIUM only** since this is exchange-regulated.
- **Caveat:** 25/day is very tight — only practical for daily refresh of a small watchlist or for fetching a single feature broadly (e.g., one batch download of OVERVIEW for a few key tickers).

## 11.4 SimFin Free Tier
- **Cost:** Free Python API & bulk CSV; subscription required for >5-year history and intraday data.
- **Best for:** Bulk download of standardized fundamentals across the entire US market in one CSV. Excellent for cross-sectional ranking when you need ~3,000 stocks at once.
- **Coverage:** Strong on US (~5,000 stocks), expanding globally; primarily annual/quarterly income statement, balance sheet, cash flow, and 7,000+ pre-calculated daily ratios.

## 11.5 SEC EDGAR XBRL API (data.sec.gov)
- **Cost:** Completely free, no API key, no rate limit (just need a User-Agent header with your email).
- **Endpoints:** `/api/xbrl/companyfacts/CIK{cik}.json` (all reported XBRL facts for a company) and `/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json`.
- **Best for:** Authoritative ground truth — every line item ever reported in a 10-K/10-Q since 2009 is here, machine-readable, free. Recommended for serious fundamentals.
- **Library:** `edgartools` Python package wraps EDGAR access cleanly.
- **Caveat:** Raw XBRL has firm-specific extensions; reconciling to a standard chart of accounts requires effort. Use `edgartools` to abstract this.


---

# 12. SENTIMENT ANALYSIS & ALTERNATIVE DATA

## 12.1 FinBERT (Financial Sentiment via Transformers)
- **Source**: ProsusAI/finbert on HuggingFace (free, MIT-style)
- **Use**: Classify news headlines/articles as positive/negative/neutral
- **Inputs**: yfinance news, Finnhub free tier, NewsAPI free
- **Phase**: 6 (Sentiment v2)

## 12.2 VADER + Loughran-McDonald Dictionary
- **VADER**: Generic social media sentiment
- **L-M Dictionary**: Finance-specific positive/negative word lists (cite Loughran-McDonald 2011, JoF)
- **Use**: Lightweight alternative to FinBERT for headline sentiment

## 12.3 SEC Form 4 (Insider Transactions)
- **Source**: SEC EDGAR free
- **Library**: edgartools
- **Signals**: CFO/CEO P-coded purchases > $100k, cluster buys (3+ insiders, 90 days)
- **Documented alpha**: ~5-10% top decile (Cohen-Malloy-Pomorski 2012, JoF)

## 12.4 13F Institutional Holdings
- **Source**: SEC EDGAR (lagged 45 days)
- **Use**: Track smart money concentration, hedge fund crowding
- **Caveat**: 45-day lag limits real-time use

## 12.5 Reddit / StockTwits / WSB
- **Library**: PRAW (Reddit), public StockTwits API
- **Caveat**: NO documented alpha at S&P 500 scale (megacap)
- **Phase 6**: SKIP for megacap; Phase 8 revisit for small-cap

## 12.6 Options Put-Call Ratio
- **Source**: Cboe CSV (free)
- **Use**: Sentiment indicator; high PCR = bearish

## 12.7 Google Trends
- **Library**: pytrends (free)
- **Use**: Attention proxy; works better for retail names

---

# 13. MACHINE LEARNING PIPELINE

## 13.1 LightGBM LambdaRank (Primary Ranker)
- **Use**: Cross-sectional rank prediction
- **Why**: Tree-based handles non-linear factor interactions; fast on CPU
- **Phase**: 5

## 13.2 Walk-Forward Validation
- **Methodology**: Train 36mo / Validate 6mo / Test 1mo, rolling forward
- **Embargo**: 5 trading days between train and test (López de Prado 2018)
- **Purging**: Remove labels spanning train-test boundary

## 13.3 SHAP Explainability
- **Library**: shap (free, MIT)
- **Use**: Top-5 contributing factors per stock, displayed in detail page

## 13.4 Isolation Forest (Anomaly Detection)
- **Use**: Flag stocks with unusual feature patterns (potential errors or genuine outliers)

## 13.5 HDBSCAN Clustering
- **Use**: Find similar stocks, sector-agnostic peer groups

---

# 14. ADVANCED QUANT — PORTFOLIO CONSTRUCTION

## 14.1 Hierarchical Risk Parity (HRP)
- **Paper**: López de Prado (2016) "Building Diversified Portfolios that Outperform Out of Sample"
- **Library**: PyPortfolioOpt (free, MIT)
- **Why**: Robust to noisy correlation matrices, no matrix inversion

## 14.2 Black-Litterman
- **Use**: Combine market equilibrium with QuantRank views
- **Library**: PyPortfolioOpt

## 14.3 Ledoit-Wolf Shrinkage
- **Use**: Stabilize covariance matrix estimation
- **Library**: scikit-learn

## 14.4 Markowitz / Risk Parity
- **Use**: Standard mean-variance and equal-risk-contribution baselines

## 14.5 Kelly Criterion (Fractional)
- **Use**: Position sizing based on edge × odds
- **Cap at 1.0**: Avoid over-leveraging
- **Half-Kelly recommended**: Reduces drawdown variance

---

# 15. MACRO & REGIME DETECTION

## 15.1 FRED Macro Stack (free, no key with fredapi)
Key series:
- T10Y2Y (yield curve)
- VIX, VIX9D, VIX3M
- BAMLH0A0HYM2 (HY OAS — credit spreads)
- UNRATE, INDPRO, CPIAUCSL, FEDFUNDS
- USREC (NBER recession indicator)

## 15.2 Hidden Markov Models (HMM)
- **Library**: hmmlearn (Gaussian HMM)
- **States**: 3 (bull / neutral / bear)
- **Use**: Tilt factor weights conditionally

## 15.3 Chen-Roll-Ross Macro Factors
- **Inputs**: Inflation surprise, term spread, default spread, industrial production growth
- **Use**: Macro factor exposure scoring

## 15.4 Sector Rotation
- **Methodology**: Track sector relative momentum over business cycle phases
- **Late-cycle**: Energy, materials lead
- **Recession**: Staples, healthcare, utilities lead

## 15.5 Equity Duration
- **Concept**: Long-duration stocks (low current FCF, high terminal value) hurt by rate hikes
- **Proxy**: P/E or 1 / earnings yield

---

# 16. MICROSTRUCTURE / VOLUME / FLOW

## 16.1 OBV / MFI / CMF (already in Section 2)
- Money flow indicators

## 16.2 Volume Profile / VWAP Distance
- Distance from VWAP as mean-reversion signal

## 16.3 Short Interest
- **Source**: Finra free CSV, or finnhub.io free
- **Signal**: High SI + price rising = squeeze potential

## 16.4 Dark Pool Volume
- **Source**: Finra ATS Transparency Data (free)
- **Use**: Institutional accumulation/distribution

---

# 17. ADVANCED VALUATION

## 17.1 EVA (Economic Value Added)
- Formula: NOPAT − (WACC × Capital)
- **Use**: True economic profit (vs accounting profit)

## 17.2 CFROI (Cash Flow Return on Investment)
- Formula: Gross Cash Flow / Gross Investment
- **Use**: Sector-neutral return metric (HOLT methodology)

## 17.3 Tobin's Q
- Formula: Market Value / Replacement Cost
- **Q > 1**: Stock trades above replacement cost (overvalued by Tobin's measure)

## 17.4 Real Options Valuation
- Apply to growth stocks with significant optionality (R&D pipelines, etc.)

---

# 18. BEHAVIORAL & ANOMALY FACTORS

## 18.1 Post-Earnings Announcement Drift (PEAD)
- **Paper**: Bernard-Thomas 1989, 1990
- **Use**: Standardized Unexpected Earnings (SUE) → 60-day drift signal

## 18.2 Idiosyncratic Volatility (IVOL)
- **Paper**: Ang-Hodrick-Xing-Zhang 2006
- **Use**: Low IVOL outperforms (anomaly)

## 18.3 MAX (Lottery Effect)
- **Paper**: Bali-Cakici-Whitelaw 2011
- **Use**: Stocks with high MAX returns underperform

## 18.4 Asset Growth
- **Paper**: Cooper-Gulen-Schill 2008
- **Use**: High asset growth firms underperform

## 18.5 Net Stock Issuance
- **Use**: Issuing firms underperform; buyback firms outperform

## 18.6 Stambaugh-Yu-Yuan Composite (SEE PART VI)
- **Section 31.2**: 11-anomaly composite
- **Used in Part VI Phase 4**

---

# 19. ADVANCED RISK ANALYSIS

## 19.1 GARCH(1,1) / GJR-GARCH
- **Library**: arch (free)
- **Use**: Conditional volatility forecasting

## 19.2 VaR / CVaR
- **Methodology**: Historical, parametric, Cornish-Fisher
- **Caveat**: Historical fails in regime change (2008, 2020)

## 19.3 Skewness / Kurtosis
- Higher moments of return distribution

## 19.4 Ulcer Index, Pain Index
- Drawdown-aware risk metrics

## 19.5 Omega Ratio
- Probability-weighted upside vs downside

---

# 20. CORPORATE EVENTS & CATALYSTS

## 20.1 8-K Filings (SEE PART VI Section 33.3)
- Item-level event analysis

## 20.2 DEF 14A (Proxy Statements)
- **Source**: SEC EDGAR
- **Use**: Executive compensation, governance scores

## 20.3 Form ADV
- **Use**: Investment adviser concentration

---

# 21. COMPOSITE SCORE CONSTRUCTION

## 21.1 Pillar Weighting (v1.0 default)
| Pillar | Weight |
|---|---|
| Quality | 22% |
| Value | 18% |
| Growth | 10% |
| Momentum | 10% |
| Health | 8% |
| Profitability | 5% |
| Technical | 4% |
| Risk | 3% |
| Sentiment | 10% (placeholder until Phase 6) |
| ML | 10% (placeholder until Phase 5) |

**Phase 3 active composite**: Scale active pillar weights to sum to 1.0 (redistribute sentiment + ml pro-rata).

## 21.2 Normalization
1. Winsorize raw metrics at 5th/95th percentile (sector-wise)
2. Compute sector-relative percentile rank (preferred over z-score)
3. Linear map [0, 100]
4. Aggregate within pillar (mean of valid metrics)
5. <50% pillar metrics → set pillar to neutral 50, flag in data_quality

## 21.3 Risk Overlay (Vetoes)
Hard floors on composite if any of:
- Beneish M-Score > -1.78 (likely manipulator)
- Altman Z″ < 1.10 (distress zone)
- Sloan Accruals top decile (earnings quality red flag)
- Z-score on Net Stock Issuance top decile

---

# 22. BACKTESTING & VALIDATION FRAMEWORK

## 22.1 Information Coefficient (IC)
- Spearman rank correlation of predicted vs realized returns
- Target: |IC| ≥ 0.02 OOS

## 22.2 Information Ratio (IR)
- Mean IC / Std IC
- Target: IR ≥ 0.5

## 22.3 alphalens (free, Quantopian heritage)
- Library for factor analysis tearsheets

## 22.4 Combinatorially Symmetric Cross-Validation (CSCV)
- **Paper**: Bailey-Borwein-López de Prado-Zhu (2014)
- **Use**: Compute Probability of Backtest Overfitting (PBO)

## 22.5 PBO (Probability of Backtest Overfitting)
- Hard veto threshold: PBO > 50%
- Quantifies multiple-testing bias

## 22.6 Block Bootstrap
- Use 6-12 month overlapping blocks
- Compute Sharpe and IC confidence intervals

## 22.7 Newey-West HAC
- Lag = floor(4·(T/100)^(2/9))
- Use for monthly factor returns t-stats

## 22.8 Deflated Sharpe Ratio
- **Paper**: Bailey-López de Prado (2014)
- Adjusts for selection bias when picking best of N candidates

---

# 23. ENSEMBLE & META-LEARNING

## 23.1 Linear Combination of Pillars
- Phase 3 baseline

## 23.2 LightGBM Meta-Learner (Phase 5)
- Treats pillar scores as features
- Trains on historical realized returns

## 23.3 Stacking / Blending
- Combine multiple ML models with logistic meta-learner
- Phase 5 optional

---

# 24. PERFORMANCE METRICS FOR THE APP

## 24.1 Top Decile vs SPY
- Equal-weight Top 30 from QuantRank
- Compare to SPY total return

## 24.2 Sharpe Ratio
- (Mean excess return) / Std
- Target: 0.7-1.0 (Option B)

## 24.3 Max Drawdown / Calmar
- Worst peak-to-trough; CAGR / |MaxDD|

## 24.4 Information Ratio vs SPY
- Annualized active return / tracking error

## 24.5 Hit Rate
- % of months top decile beats SPY
- Target: 55-60%

---

# 25. DATA CACHING & REFRESH CADENCE

## 25.1 Cache Layers
1. **L1: Memory** (within compute run)
2. **L2: Disk parquet** (compute/cache/, gitignored)
3. **L3: Repo committed** (public/data/, with PIT discipline)

## 25.2 Refresh Cadence
- **Daily**: Skip (waste of GH Actions minutes)
- **Weekly Sunday 22:00 UTC**: Main compute cron
- **Monthly 1st**: ML retrain (Kaggle)
- **Quarterly**: Whisper transcription, deep model re-validation (Modal)

## 25.3 Atomic Writes (Rule 12 in SKILL)
- Always write to .tmp file, then os.rename() to final path

---

# 26. RATE-LIMIT MANAGEMENT

## 26.1 yfinance
- Unlimited but unofficial; use tenacity exponential backoff

## 26.2 SEC EDGAR
- No rate limit; require User-Agent header with email

## 26.3 FRED
- 120 requests/minute via fredapi

## 26.4 Finnhub free
- 60 calls/minute

## 26.5 Reddit (PRAW)
- 60 requests/minute authenticated

---

# 27. SUGGESTED DATABASE SCHEMA

(For QuantRank static-site: NO database. JSON files in public/data/ instead.)

### metadata.json
```json
{
  "version": "1.0.0",
  "last_update_utc": "2026-XX-XXTXX:XX:XXZ",
  "universe": "SP500",
  "universe_size": 503,
  "phase": 3,
  "roadmap": "Option B"
}
```

### rankings.json (summary array)
Per stock: rank, ticker, name, sector, composite_score, current_price, fair_price, max_fair_price, margin_of_safety_pct, pillar_scores, confidence_interval_95

### stocks/{TICKER}.json (full detail)
ticker, raw_metrics (all features), pillar_scores, fair_price_methods (DCF/Graham/RIM/multiples), risk_overlay (Beneish/Sloan/Z″), data_quality (filing_date, missing_metrics, imputed_metrics), shap_top5_factors

---

# 28. REALISTIC ACCURACY EXPECTATIONS

## 28.1 Published vs Realistic Returns

| Strategy | In-sample paper | OOS realistic |
|---|---|---|
| Magic Formula | ~30% CAGR | ~11% CAGR (Martin 2020) |
| Piotroski F | ~23% top decile | ~8-12% top decile |
| Momentum 12-1 | ~12% annual | ~5-8% annual (post-2000) |
| QMJ | ~4-5% alpha | ~2-3% alpha |
| Composite of all | "very high" | 2-4% net alpha realistic |

## 28.2 Decay Reality
- McLean-Pontiff: ~50% post-publication decay
- Falck-Rej-Thesmar: Newer factors decay faster
- See Section 35 for full decay analysis

## 28.3 What Free Data CAN'T Deliver
- Point-in-time CRSP/Compustat (paid: $30k/yr)
- IBES analyst estimates (paid)
- Intraday TAQ (paid)
- Real-time news (paid)
- Alt-data (satellite, credit card, etc.) — paid

## 28.4 Honest Performance Hierarchy

| Net Alpha | Verdict |
|---|---|
| 0-2% | Honest baseline |
| 2-4% | Option A target |
| 3-7% | Option B target |
| 7-10% | Suspicious (likely overfit) |
| >10% | Reject (overfit) |

---

# 29. CAVEATS & PITFALLS

## 29.1 Survivorship Bias
- Use historical S&P 500 constituents (Wikipedia table) not current
- Free data has weak delisted-stock coverage
- Mitigation: explicit acknowledgment + use OSAP/JKP returns where possible

## 29.2 Look-Ahead Bias
- ALWAYS use filing_date, not period_end (Rule 5 in SKILL)
- 13F lagged 45 days
- Form 4: use transactionDate

## 29.3 Sector Distortion
- ALWAYS rank within GICS sector for fundamentals
- Exclude financials/utilities from Magic Formula and asset-turnover

## 29.4 Multiple Testing
- 100 candidate strategies → best one is biased upward by ~20-30% Sharpe
- Mitigation: Deflated Sharpe, PBO

## 29.5 Regime Change Risk
- 2008, 2020, 2022 = factor failure modes
- Mitigation: HMM gating, conformal prediction

## 29.6 Free Data Fragility
- yfinance breaks ~1-2x/year
- Mitigation: fallback sources (Stooq, Tiingo free)

## 29.7 Trademark
- NEVER use "Jitta" — trademark
- Project name: QuantRank

## 29.8 No Live Trading
- App is research/educational only
- README must display disclaimer

---

## Recommended Architecture for the Ranking App

```
┌─────────────────────────────────────────────────┐
│  1. DATA LAYER                                  │
│  • SEC EDGAR (long-term fundamentals, free)     │
│  • SimFin bulk CSV (current fundamentals)       │
│  • yfinance (prices, real-time refresh)         │
│  • FMP (filling gaps, ratios)                   │
│  • Cache to SQLite/Parquet                      │
└─────────────────────────────────────────────────┘
            │
┌─────────────────────────────────────────────────┐
│  2. METRIC COMPUTATION LAYER                    │
│  • Fundamental: F-Score, Z-Score, M-Score,      │
│    Magic Formula, Graham Number, ROIC, OE       │
│  • Technical: RSI, MACD, ADX, ATR, % above SMA  │
│  • Risk: σ, β, Sharpe, MaxDD, VaR              │
│  • Growth: 3/5-yr CAGR of Revenue/EPS/FCF       │
│  • Quality: MSCI 3-descriptor + AQR QMJ proxy   │
└─────────────────────────────────────────────────┘
            │
┌─────────────────────────────────────────────────┐
│  3. NORMALIZATION LAYER                         │
│  • Winsorize 5th/95th                           │
│  • Sector-relative percentile rank (preferred)  │
│  • Handle missing → sector median               │
└─────────────────────────────────────────────────┘
            │
┌─────────────────────────────────────────────────┐
│  4. PILLAR AGGREGATION (each 0-100)             │
│  Quality | Value | Growth | Momentum |          │
│  Health  | Risk  | Sentiment (optional)         │
└─────────────────────────────────────────────────┘
            │
┌─────────────────────────────────────────────────┐
│  5. COMPOSITE STOCKRANK + FAIR PRICE OVERLAY    │
│  • Weighted sum of pillars                      │
│  • Ensemble fair price (DCF + Graham + RIM +    │
│    multiples) → MoS %                           │
│  • Final 0-100 with optional MoS bonus          │
└─────────────────────────────────────────────────┘
```

---

## Caveats

- **Backtest skepticism.** All strategies cited (Magic Formula 30% CAGR, Piotroski's 23% return, QMJ alpha, etc.) come from in-sample studies. Independent out-of-sample replications consistently produce **lower** returns: Martin (2020) found Magic Formula delivered ~11% vs S&P's 8.7% in 2003–2015, far below Greenblatt's claims. Treat all historical numbers as upper bounds.
- **Free-data quality varies.** yfinance breaks periodically; field names shift; some quarters are missing. Always cross-check at least one fundamental against SEC EDGAR ground truth before relying on it for production scoring.
- **Sector exclusions matter.** Magic Formula explicitly excludes financials/utilities. Altman's Z-score X₅ distorts asset-light tech firms (use Z″). Graham Number breaks for negative book value or earnings. Build sector-aware applicability flags into every metric.
- **Forward-looking estimates require care.** PEG, DCF, and reverse-DCF all need a growth assumption. Free APIs do not provide reliable analyst consensus growth — using historical CAGR as proxy biases against firms whose growth is accelerating or decelerating.
- **The MSCI Quality methodology, AQR's QMJ, and Fama-French factor weights** referenced here are reconstructions based on publicly available research; the actual proprietary index methodologies may use additional descriptors and refinements not disclosed publicly.
- **Real-time vs delayed data:** Alpha Vantage and most free tiers serve **delayed (15–20 min) US equity prices only**. Real-time prices are exchange-regulated and require paid tiers.
- **VaR and CVaR using the historical method** assume the past distribution will repeat — they fail spectacularly during regime changes (2008, 2020). Pair with stress tests.
- **Owner Earnings is an estimate**, not a GAAP figure. Maintenance CapEx is genuinely unobservable; the Greenwald PP&E/Sales method or simply using D&A as a proxy are both crude. Report a range, not a point.
- **Composite scores tempt over-confidence.** A stock with StockRank 99 is not "twice as good" as one at 50. Treat ranks as ordinal screens, not cardinal predictions, and always pair quantitative ranking with qualitative due diligence.
- **Dates and constants in this document** (e.g., risk-free proxy of 10-yr Treasury, 22.5 in Graham formula, 5–7% MRP) need periodic updating. Build the WACC/risk-free into a config file rather than hardcoding.
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

# Quick Reference — Updated Tables

## A. Pillar → Metrics Mapping (Updated for Option B)

| Pillar | DIY Metrics (Phase 0-3) | + OSAP/JKP/Qlib (Phase 4+) |
|---|---|---|
| **Quality** | Piotroski F, ROE, ROIC, Gross Profitability, MSCI 3-desc | + JKP Quality theme + OSAP profitability cluster |
| **Value** | P/E, P/B, P/S, EV/EBITDA, EV/FCF, Earnings Yield, Graham, Tobin's Q | + JKP Value theme + OSAP value signals |
| **Growth** | Rev/EPS/FCF CAGR, SGR, Analyst revisions | + OSAP growth signals |
| **Momentum** | 12-1, 6-1, 3-1, residual, 52w-high distance | + JKP Momentum theme + Qlib momentum features |
| **Health** | Current/Quick, D/E, IC, Altman Z″, Net Debt/FCF | + OSAP distress signals |
| **Profitability** | Gross/Op/Net margins, ROA, AT, CCC | + JKP Profitability theme |
| **Technical** | RSI, MACD, ADX, ATR, Bollinger | + Qlib Alpha158 (158 features) ⭐ |
| **Sentiment** | FinBERT news, Insider Form 4, options PCR | + Whisper VDQ + 8-K events + Lazy Prices ⭐ |
| **ML** | LightGBM LambdaRank | + Triple-Barrier + Meta-Labeling + Conformal ⭐ |
| **Risk** | σ, β, Sharpe, MaxDD, GARCH, IVOL | + IPCA latent factors as risk model ⭐ |
| **Macro/Regime** | HMM Gaussian, yield curve, sector rotation | + Student-t HMM + TDA risk-off gate ⭐ |

## B. Library Matrix (Phase 4+ Option B)

| Library | License | Phase | Compute | Status |
|---|---|---|---|---|
| openassetpricing | MIT-style | 4 | CPU | ✅ Free |
| ipca | MIT | 4 | CPU | ✅ Free |
| pyqlib | MIT | 4 | CPU/Kaggle | ✅ Free |
| mlfinlab | AGPL-3.0 | 5 | CPU | ⚠️ Verify license |
| mapie | BSD-3-Clause | 5 | CPU | ✅ Free |
| sentence-transformers | Apache 2.0 | 6 | CPU/GPU | ✅ Free |
| openai-whisper | MIT | 6 | GPU (Modal) | ✅ Free |
| skfolio | BSD-3-Clause | 7 | CPU | ✅ Free |
| gtda | AGPL-3 | 7 | CPU | ⚠️ Verify license |

## C. Free Heavy Compute Strategy

| Platform | Quota | Use Case | Phase |
|---|---|---|---|
| GitHub Actions | Unlimited public, 2000 min/mo private | Orchestration, light scoring | All |
| Kaggle Notebooks | 30 GPU-hr/wk T4/P100, 9hr session | Heavy ML training, Llama-3 fine-tune | 5+ |
| Modal | $30/mo credits, ~50 T4-hrs | Whisper + LLM batch inference | 6+ |
| Google Colab Free | T4 dynamic, ~12hr session | Prototyping, FinBERT inference | All |
| HuggingFace Spaces | 16GB CPU always-on | Static-site dashboard | All |
| Paperspace Gradient Free | M4000, 6hr | Backup capacity | 5+ |
| Lightning AI Studio | Limited | Experimentation | 5+ |

---

**END OF KNOWLEDGE BASE**

This document provides everything needed to build QuantRank from scratch with both Option A (DIY, 2-4% alpha) and Option B (research-backed, 3-7% alpha) paths. All techniques are mathematically specified with realistic caveats and honest decay expectations.

For Phase 4+ specifics, also read `RESEARCH_FINDINGS.md`. For phase-by-phase tasks, read `WORKFLOW.md`. For architecture rules, read `SKILL.md`.
