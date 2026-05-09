# Methodology

> Full user-facing methodology ships with **v1.0** (end of Phase 3). This page
> currently sketches the intended structure.

QuantRank produces, per stock:

- **Composite StockRank** — a single 0–100 score.
- **8 pillar sub-scores** — quality, value, growth, momentum, health, sentiment, ML, risk.
- **Ensemble fair price** — median + 95th-percentile across DCF, Graham, residual income, and peer-multiple methods.
- **Margin of safety** — `(fair − current) / fair`.
- **Top-5 SHAP factors** — why the score is what it is (Phase 5+).

## How scoring works

1. **Ingest** — pull free-tier data (yfinance, SEC EDGAR, FRED, Finnhub, Reddit).
2. **Features** — compute 60+ classical metrics + advanced sentiment / ML / regime features.
3. **Normalize** — winsorize, then sector-relative percentile rank for fundamentals (absolute rank for risk and momentum).
4. **Aggregate** — average each pillar's normalized member metrics.
5. **Composite** — weighted sum across pillars; weights shift slightly by macro regime (Phase 7).
6. **Defense layer (annotate-and-veto-Top-N, never scoring inputs)** —
   - **Vetoes** (3 by v1.0): exclude flagged stock from Top-5 badge —
     Altman Z″ < 1.10, Sloan accruals top decile, Net Stock Issuance top decile.
   - **Numerical guards** (4 by v1.0): null fair_price + flag — stale
     filing > 180d, multi-method outlier > 5×, terminal g constraint,
     Quality sector exclusions.
   - **Annotate-only flags** (5+ by v1.0): goodwill_heavy, value_trap_risk,
     going_concern, auditor_change, beneish_high, dechow_f_high — surfaced
     in UI without modifying composite.
   - Full defense schedule in
     [`RESEARCH_FINDINGS.md`](RESEARCH_FINDINGS.md) §"Defense Playbook".
7. **Fair price** — ensemble of DCF, Graham, residual income, and
   peer-multiple methods (median + max). Tangible BVPS used in Graham
   and RIM (full intangibles netting).

## The full formula reference

See [`../stock_ranking_knowledge.md`](../stock_ranking_knowledge.md) for the
complete ~1600-line reference covering every formula, normalization rule, and
data source. That file is the authoritative source — never reinvent formulas.

## Realistic expectations

Per Section 28 of the knowledge doc: net-of-cost top-decile alpha of **2-4%
realistic**, with mean information coefficient around 0.02-0.05. Anything
claiming much more is almost certainly overfit. We validate via PBO (probability
of backtest overfitting) and deflated Sharpe ratio (Phase 4+).

**Defense system honest limits** (per `RESEARCH_FINDINGS.md` §"Honest Limitations"):
- Beneish M-Score: ~30% false-positive rate in broad market, ~25-40% false-negative
- McLean-Pontiff anomaly decay: 26% out-of-sample + 32% post-publication = 58% cumulative
- Madoff-style total fabrication is undetectable by any quantitative system
- Marginal AAER capture < 5% beyond 4 fraud signals — defense set freezes at v1.0; rotate (don't stack) post-v2.0

---

**Reminder**: this is a research / educational tool. Not investment advice. See
the disclaimer in the [README](../README.md).
