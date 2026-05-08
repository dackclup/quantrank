# RESEARCH_FINDINGS — Stretch Techniques for QuantRank Post-v1.0

> **Status**: forward-looking design document. Phase 3 (v1.0 milestone)
> ships the classical-only baseline first; everything below is the
> research-backed roadmap for Phases 4-8. Adopted as **Option B**
> 2026-05-08 with the original `WORKFLOW.md` Phase 4-7 plan as fallback
> ("Option A").
>
> Every claim below is hedged. The repo's existing disclaimer applies:
> educational and research only, not investment advice.

---

## 1. Why a research-backed roadmap

The original WORKFLOW.md plan (FinBERT news + LightGBM + HMM regime) was
sound but used circa-2020 references. The 2024-2025 quant-finance
literature has converged on a sharper toolkit:

- **Reproducibility crisis acknowledged.** Hou-Xue-Zhang (2020,
  *Replicating Anomalies*, RFS) showed ~65% of 452 published anomalies fail
  to replicate at standard significance levels. McLean-Pontiff (2016,
  *Does Academic Research Destroy Stock Return Predictability?*, JF) showed
  the average post-publication decay is ~58% of in-sample alpha.
- **Open factor zoos exist.** OSAP and JKP each maintain curated, replicated
  factor libraries — building on top of these is faster and more honest
  than rolling your own.
- **Better labels for ML.** López de Prado's Triple-Barrier labeling and
  Meta-Labeling (*Advances in Financial Machine Learning*, 2018) replaced
  fixed-horizon returns as the de-facto labeling scheme for tree-based
  rankers.
- **Calibrated uncertainty.** Conformal prediction (Vovk-Shafer-Gammerman)
  gives distribution-free 80% / 90% prediction intervals on top of any
  black-box predictor — crucial for honest score uncertainty in a public
  ranking app.
- **Earnings-call audio is now free.** OpenAI Whisper runs on free-tier
  GPU minutes (Kaggle / Colab); transcript-quality NLP signals are no
  longer paywalled.
- **Cohen-Malloy-Nguyen "Lazy Prices"** (2020, JF) showed 8-K text-change
  signals predict 1-month returns. Free, computable from EDGAR alone.

---

## 2. Phase-by-phase roadmap

### Phase 4 — Factor consolidation → v1.1 (replaces "Sentiment & alternative data" in original Option A)

**Goal**: replicate published anomalies on our universe, then dimension-reduce.

**Sources to integrate**:
- **OSAP** (Open Source Asset Pricing, Chen-Zimmermann 2021,
  *openassetpricing.com*) — ~210 anomalies, monthly factor returns + signals
  back to 1926. Free CSV download.
- **JKP** (Jensen-Kelly-Pedersen, Bryan Kelly's lab + AQR) — characteristic
  data + factor returns; cleaner construction than OSAP for some signals.
- **Qlib Alpha158** (Microsoft Qlib library) — 158 alpha factors, mostly
  technical / microstructure, batteries-included for daily US equities.
- **CRSP / Compustat** — paywalled gold standard. Out of scope for free
  tier; OSAP + JKP reconstructed equivalents are sufficient.

**Reduction**:
- **IPCA** (Instrumented Principal Components Analysis, Kelly-Pruitt-Su
  2019, *JFE*) — extract a small number of latent factors that capture
  most cross-sectional variance. Reduces 200+ characteristics to 5-10
  rotated factors with stable loadings.

**Library candidates**: `pyOSAP` (community port), `qlib` (Microsoft, MIT
license), custom IPCA (≤200 lines NumPy).

**Fallback to Option A**: if Qlib's data adapter is broken on free-tier
GitHub Actions runners, drop to the original "Sentiment & alt-data only"
Phase 4 (FinBERT news + Form 4 + Reddit).

### Phase 5 — ML meta-learner with López de Prado labels + Conformal calibration

**Goal**: replace point-prediction LightGBM with calibrated, leak-resistant labels.

**Techniques**:
- **Triple-Barrier method**: instead of fixed-horizon return labels, label
  each observation by which of three barriers (upper profit-taking, lower
  stop-out, time-out) is hit first. Reduces label noise and look-ahead.
- **Meta-Labeling**: a secondary classifier (`should we trade this signal?`)
  on top of a primary signal classifier. Improves precision at the cost of
  recall.
- **Combinatorial Purged Cross-Validation (CPCV)**: respects time
  ordering + decontaminates training/test overlap from event labels.
- **Conformal prediction** (Vovk-Shafer-Gammerman; `mapie` lib): produces
  marginal-coverage prediction intervals on top of any base model. Surface
  these as `score_uncertainty_80pct` in the JSON.

**Library candidates**: `lightgbm`, `mapie`, `mlfinlab` (López de Prado
algorithms; non-trivial license — verify before integration), or
hand-rolled triple-barrier (~50 lines).

**SHAP** stays as in original Option A.

**Fallback to Option A**: if `mapie` integration with LightGBM ranker is
flaky, drop conformal intervals; ship the López de Prado labeling only.

### Phase 6 — Sentiment v2 (FinBERT + Whisper + 8-K)

**Goal**: deeper text signals than headline-only FinBERT.

**Stack**:
- **FinBERT news** (`ProsusAI/finbert`, original Option A baseline) on
  yfinance/finnhub article bodies.
- **Whisper-transcribed earnings calls** (`openai/whisper-base.en` or
  Distil-Whisper). Earnings-call audio is free from sources like
  `seekingalpha.com` archives or `EarningsCall` subreddit feeds; Q&A
  sentiment differential (analyst vs management) is a known signal
  (Bochkay-Hales-Chava 2020).
- **8-K Lazy Prices factor** (Cohen-Malloy-Nguyen 2020, *JF*): year-on-year
  text-similarity score on annual / quarterly filings. Material changes →
  predicts 1-month returns. Computable from EDGAR alone using
  `edgartools` + `rapidfuzz` / `difflib`.
- **FNSPID** (*Financial News + Stock Price Integrated Dataset*, Dong et al.
  2024) — open dataset of 15.7M financial news articles aligned to 4,775
  stocks 1999-2023 for backtesting / pre-training. Free download from
  HuggingFace.

**Library candidates**: `transformers`, `whisper-cpp` (CPU inference),
`edgartools`, `praw`, `pytrends`, `rapidfuzz`.

**Fallback to Option A**: if Whisper inference time on free-tier runners
is intractable for 500 calls/quarter, ship FinBERT-only Phase 6 and defer
audio to a later release.

### Phase 7 — Regime + portfolio (Student-t HMM + NCO + TDA) → v1.5

**Goal**: heavier-tailed regime detection + sounder portfolio construction.

**Techniques**:
- **Student-t HMM**: replace Gaussian-emission HMM (default in `hmmlearn`)
  with t-emission to capture fat tails of equity returns. Custom EM ~150
  lines or use `dynamax` (JAX-based).
- **NCO — Nested Clustered Optimization** (López de Prado 2019, *JPM*):
  hierarchical risk parity that decomposes the covariance matrix via
  clustering, optimizes within clusters, then across. Out-of-sample more
  stable than Markowitz mean-variance on small samples. ~100-line port.
- **TDA — Topological Data Analysis** (persistent homology of return
  manifolds; Carlsson 2009, applied to finance by Gidea-Katz 2018):
  emerging signal for regime tagging, not a ranking driver. Optional
  research extension.

**Library candidates**: `hmmlearn`, `dynamax`, `riskfolio-lib` (NCO),
`giotto-tda` (TDA, optional).

**Fallback to Option A**: ship Gaussian HMM + simple equal-weight if NCO
turnover penalty makes weekly rebalancing too costly under our 30-60 bps
transaction model.

### Phase 8 — Universe expansion (S&P 1500)

Same as original Option A Phase 7. No research-backed delta — this is a
scale milestone.

---

## 3. Honest performance ceiling

> **Claim**: net of transaction costs, a fully built-out QuantRank with
> Phases 4-7 implemented could plausibly target **3-7% annualized alpha**
> vs SPY on the S&P 500 universe. Realistic mid-point: **2-4% net**, same
> envelope as `stock_ranking_knowledge.md` §28.
>
> **Hedge**: this is the *research-suggested upper bound* under ideal
> conditions, not a forecast. The literature is full of paper alpha that
> evaporated on implementation:

| Paper | Finding |
|---|---|
| McLean-Pontiff 2016, *JF* | Mean post-publication decay ≈ 58% across 97 published anomalies. Most factor strategies lose more than half their backtest alpha within 5 years of publication. |
| Hou-Xue-Zhang 2020, *RFS* | Of 452 anomalies tested with sensible micro-cap filters, ~65% fail replication at the 5% significance level. Tiny-cap / micro-cap dominated many "famous" results. |
| Harvey-Liu-Zhu 2016, *RFS* | t > 3.0 (not 2.0) is the right hurdle for new factors after multiple-testing correction. Most published factors do not clear it. |
| Bailey-Borwein-López de Prado-Zhu 2014 | **PBO** (probability of backtest overfitting) > 0.5 is depressingly common in published work. QuantRank's Phase 6 backtest harness will compute and report PBO honestly. |
| Novy-Marx 2014, *JFE* | Common quant practice (trading on z-score thresholds, post-hoc rebalancing) inflates Sharpe by ~30-50% vs out-of-sample reality. |

**Operational consequences**:
1. Every Phase 4-7 addition must produce evidence in our Phase 6 backtest
   harness (IC, IR, deflated Sharpe, PBO < 0.5) before being weighted into
   the production composite.
2. We refuse to claim alpha numbers without out-of-sample (post-2024) IC.
3. The frontend never displays a "predicted return" — only a 0-100
   composite score and pillar breakdowns.

---

## 4. Free heavy-compute strategy

GitHub Actions free tier is fine for Phases 1-3 (compute budget ~30 min
weekly). Phases 5-7 want occasional heavier compute (training, audio
transcription, factor backfill).

| Workload | Where | Why |
|---|---|---|
| Weekly inference + JSON write | **GitHub Actions** (`ubuntu-latest`) | Already wired; free unlimited on public repo. |
| ML training + walk-forward CV | **Kaggle Notebooks** (free GPU 30h/wk) or **Colab** | Free GPU/TPU; export trained model as artifact, commit `models/lgbm_v{date}.pkl` to repo. |
| Whisper transcription of earnings calls | **Modal** (free $30/mo credits) or **Kaggle** | CPU-only Whisper-base ≈ 5× real-time → ~500 calls/quarter feasible on Kaggle's 30h/wk. |
| OSAP / JKP factor backfill | **GitHub Actions** scheduled job, one-shot | Datasets are CSV downloads; 1-3 GB. Cache to compute/cache/factors/. |
| TDA persistence diagrams | **Colab** | `giotto-tda` benefits from a single beefy machine; not weekly. |
| FNSPID corpus download | **HuggingFace datasets** + cache | 15.7M articles ≈ 30 GB; download once, slice as needed. |

Trigger pattern across all of the above: a small `prepare_*.yml` workflow
in GitHub Actions hands off a payload to the heavier compute (Kaggle API,
Modal SDK), waits, downloads the result artifact, commits it to repo.
Models/data flow back to GitHub; the orchestrator never sees the heavy
compute directly.

---

## 5. Library matrix (pinned versions to validate per phase)

| Library | Phase | Notes |
|---|---|---|
| `qlib` | 4 | Microsoft, MIT. Verify Linux + Py3.11 wheels exist before adopt. |
| `pyOSAP` (or direct CSV download) | 4 | OSAP signal CSVs are stable; library is a convenience. |
| Custom IPCA (NumPy) | 4 | ~200 lines; Kelly-Pruitt-Su 2019 reference impl. |
| `lightgbm` | 5 | Already canonical. |
| `shap` | 5 | Tree explainer; Phase 5 §5.6. |
| `mapie` | 5 | Conformal prediction; MIT. |
| `mlfinlab` | 5 | López de Prado algorithms. **License check required** — Hudson & Thames non-commercial restrictions exist on some snapshots. Hand-roll triple-barrier if blocked. |
| `transformers` + `torch-cpu` | 6 | Already in the original Option A Phase 4 plan. |
| `whisper-cpp` or `openai-whisper` | 6 | CPU-only viable; GPU required for 500 calls/wk volume. |
| `edgartools` | 6 | Already integrated (Phase 2). |
| `rapidfuzz` | 6 | 8-K text similarity. |
| `dynamax` | 7 | JAX-based HMM family with t-emission. |
| `riskfolio-lib` | 7 | NCO portfolio construction. |
| `giotto-tda` | 7 | TDA — optional. |
| `arch` | 6/7 | Already canonical for GARCH + bootstrap. |
| `alphalens-reloaded` | 6 | Already in original Option A Phase 6. |

---

## 6. Decay caveats — what to monitor weekly

The two production traps for any quant ranking system:

1. **Factor crowding** (when too many funds chase the same anomaly, alpha
   evaporates). Monitor: rolling-3y IC of each pillar. If a pillar's IC
   trends below 0.01 for 6+ consecutive weeks, *down-weight automatically*
   in the next compute run via the regime-conditional weight estimator
   (Phase 7).
2. **Universe drift** (the S&P 500 itself changes; survivorship bias in
   backtests). Mitigation: every weekly run records the live S&P 500
   constituents to `compute/cache/universe/{run_date}.parquet`. Phase 6
   backtests must use point-in-time membership, not today's list.

McLean-Pontiff and Hou-Xue-Zhang are not abstract — they're operational
risks. The Phase 6 validation harness (IC / IR / PBO / deflated Sharpe)
exists specifically to guard against accepting a backtested win that
won't replicate.

---

## 7. What we are NOT promising

- We are not promising any specific alpha number to users.
- We are not building a trading system; we are building a research /
  educational ranking tool. The frontend disclaimer remains.
- We are not licensing paid data (Bloomberg, FactSet, S&P Capital IQ,
  Refinitiv, etc.). Everything stays free-tier or open-data.
- We are not claiming originality — most of Phases 4-7 is curated
  application of published research, not novel methodology.

---

## 8. References

- Bailey, D., Borwein, J., López de Prado, M., Zhu, Q. J. (2014). *The
  Probability of Backtest Overfitting*. Journal of Computational Finance.
- Carlsson, G. (2009). *Topology and Data*. Bull. Amer. Math. Soc.
- Chen, A. Y., Zimmermann, T. (2021). *Open Source Cross-Sectional Asset
  Pricing*. Critical Finance Review. — OSAP.
- Cohen, L., Malloy, C., Nguyen, Q. (2020). *Lazy Prices*. Journal of Finance.
- Dong, Z. et al. (2024). *FNSPID: A Comprehensive Financial News Dataset
  in Time Series*. arXiv preprint.
- Gidea, M., Katz, Y. (2018). *Topological data analysis of financial
  time series: landscapes of crashes*. Physica A.
- Harvey, C., Liu, Y., Zhu, H. (2016). *... and the Cross-Section of
  Expected Returns*. Review of Financial Studies.
- Hou, K., Xue, C., Zhang, L. (2020). *Replicating Anomalies*. Review of
  Financial Studies.
- Jensen, T. I., Kelly, B. T., Pedersen, L. H. (2023). *Is There a
  Replication Crisis in Finance?* Journal of Finance. — JKP factor library.
- Kelly, B. T., Pruitt, S., Su, Y. (2019). *Characteristics are
  covariances: A unified model of risk and return*. Journal of Financial
  Economics. — IPCA.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*.
  Wiley. — Triple-Barrier, Meta-Labeling, CPCV, PBO.
- López de Prado, M. (2019). *A Robust Estimator of the Efficient
  Frontier*. Journal of Portfolio Management. — NCO.
- McLean, R. D., Pontiff, J. (2016). *Does Academic Research Destroy Stock
  Return Predictability?* Journal of Finance.
- Novy-Marx, R. (2014). *Predicting anomaly performance with politics, the
  weather, global warming, sunspots, and the stars*. Journal of Financial
  Economics.
- Vovk, V., Shafer, G., Gammerman, A. (2005). *Algorithmic Learning in a
  Random World*. Springer. — Conformal prediction foundations.
- Yang, Y., Uy, M., Huang, A. (2020). *FinBERT: A Pretrained Language
  Model for Financial Communications*. arXiv. — FinBERT.

> Citations are for further reading; not endorsements. Some of these
> papers' results have themselves been challenged in the replication
> literature. Always read the most recent rebuttal before adopting.
