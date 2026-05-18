---
name: shap-explain
description: Compute SHAP (Shapley Additive Explanations) values per stock for
  the Phase 5 meta-label classifier so users can see WHY a stock got its
  predicted probability. Surfaces the top contributing features in the UI.
---

# shap-explain — STUB

## When to use

- Phase 5 after meta-label classifier ships
- User-trust-signal work — answers "why is XYZ predicted profitable?"

## What to flesh out (TODO when implementing)

- Library: `shap` (Lundberg)
- Per-stock per-week: top 5 features contributing to the
  meta-label probability (positive + negative)
- Output: `StockDetail.ml_shap_top_features: list[{feature, value, shap_value}]`
- Module location: `compute/ml/shap_explain.py`
- UI: extend the ml-section card with a "Why this prediction"
  expandable

## Acceptance criteria

- SHAP values are computed reproducibly (fixed random seed)
- Sum of all SHAP values + base_value = predicted probability
  (additivity invariant)
- Top-5 surfacing is human-readable (feature names in plain English,
  not column codes)

## Related

- Lundberg-Lee 2017 NIPS
- `phase-5/meta-label`
- `frontend/components/MlExplanationCard.tsx` (Phase 5 component)

## Supabase usage — SHAP value history

Per-stock-per-week SHAP values are large: top-5 features × ~500
stocks × ~52 weeks/year ≈ 130 000 rows/year. `StockDetail.ml_shap_top_features`
holds the **current week** (UI render) but cannot answer:

- "Did NVDA's `earnings_quality` SHAP value drift over 6 months?"
- "Which features have the most volatile SHAP contribution
  universe-wide?" (signal stability)
- "When did `manipulation_index` first become a top-5 SHAP feature
  for any S&P 500 stock?" (feature-emergence timeline)

Supabase stores the **full per-week-per-feature history**. The
Supabase MCP connector is already registered (see `CLAUDE.md`
§Connectors).

### Schema

```sql
create table shap_values (
  ticker text,
  asof_date date,
  feature_name text,
  feature_value numeric,
  shap_value numeric,
  base_value numeric,
  predicted_probability numeric,
  primary key (ticker, asof_date, feature_name)
);

create index shap_ticker_date on shap_values (ticker, asof_date desc);
create index shap_feature_date on shap_values (feature_name, asof_date desc);
create index shap_value_magnitude on shap_values (abs(shap_value) desc);
```

### Drift detection queries

```sql
-- SHAP volatility per feature over last 6 months (universe-wide)
select feature_name,
       stddev(shap_value) as shap_volatility,
       avg(abs(shap_value)) as mean_abs_contribution,
       count(distinct ticker) as ticker_coverage
from shap_values
where asof_date > now() - interval '6 months'
group by feature_name
order by shap_volatility desc
limit 20;

-- Per-ticker SHAP drift (e.g., NVDA's earnings_quality contribution)
select asof_date, shap_value
from shap_values
where ticker = 'NVDA'
  and feature_name = 'earnings_quality'
  and asof_date > now() - interval '12 months'
order by asof_date;
```

### Pattern

- `StockDetail.ml_shap_top_features` continues to hold the
  current-week top-5 (UI render via static JSON)
- Supabase holds the full history (analyst drift queries +
  feature-stability audit)
- Write path: after `compute/ml/shap_explain.py` produces SHAP
  values for the week, batch `INSERT` to Supabase BEFORE writing
  the per-stock JSON

### Capacity / cost

- Top-5 features × 500 stocks × 52 weeks = 130 000 rows/year
- Row size ~120 bytes → ~16 MB/year — comfortable on free tier for
  multiple years
