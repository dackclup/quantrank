---
name: conformal-predict
description: Wrap the Phase 5 meta-label classifier with conformal prediction
  to produce calibrated prediction intervals (e.g., 90% prediction sets) per
  stock. Adds honest uncertainty quantification to the ML layer.
---

# conformal-predict — STUB

## When to use

- Phase 5 after meta-label classifier is trained
- Specifically when the user wants "we're 90% sure this stock is
  profitable" rather than just a point probability

## What to flesh out (TODO when implementing)

- Library: `mapie` (MAPIE — Model Agnostic Prediction Interval
  Estimator) or `crepes`
- Apply conformal layer to the meta-label classifier's
  probability output
- Output per stock: prediction interval (e.g., [0.45, 0.78]) at the
  configured confidence level
- Module location: `compute/ml/conformal.py`

## Acceptance criteria

- Empirical coverage matches nominal level on out-of-sample data
  (e.g., 90% of stocks where actual outcome falls within predicted
  interval)
- Interval width is informative (not all-or-nothing [0, 1])
- Surface in `StockDetail.ml_uncertainty` (Phase 5 schema bump)

## Related

- Vovk-Gammerman-Shafer *Algorithmic Learning in a Random World*
- `phase-5/meta-label`
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique" on conformal

## Supabase usage — calibration set + coverage tracking

Conformal prediction relies on a held-out calibration set. To
**validate empirical coverage matches nominal coverage over time**
(a critical drift indicator), store the (prediction, predicted
interval, realized outcome) tuples per calibration run. The Supabase
MCP connector is already registered (see `CLAUDE.md` §Connectors).

### Schema

```sql
create table conformal_calibration (
  calibration_run_id uuid,
  ticker text,
  asof_date date,
  predicted_probability numeric,
  predicted_interval_lower numeric,
  predicted_interval_upper numeric,
  nominal_coverage numeric,        -- e.g., 0.90 for 90% interval
  realized_outcome int,            -- 1 profitable | 0 not — resolved at horizon
  resolved_at timestamptz,
  primary key (calibration_run_id, ticker, asof_date)
);

create index conformal_resolved on conformal_calibration (resolved_at desc);
create index conformal_ticker on conformal_calibration (ticker, asof_date desc);
```

### Coverage validation query

```sql
-- Empirical vs nominal coverage over last 6 months
select nominal_coverage,
       avg(case
             when predicted_interval_lower <= realized_outcome
              and realized_outcome <= predicted_interval_upper
             then 1.0 else 0.0
           end) as empirical_coverage,
       count(*) as resolved_obs
from conformal_calibration
where resolved_at > now() - interval '6 months'
  and resolved_at is not null
group by nominal_coverage;
```

### Drift alarm

Empirical coverage should be within ±5% of nominal:

| Nominal | Acceptable empirical | Drift action |
|---|---|---|
| 0.90 | 0.85 – 0.95 | within band → OK |
| 0.90 | < 0.85 | intervals too narrow — re-fit on more recent data |
| 0.90 | > 0.95 | intervals too wide — re-fit (oversmoothed) |

A query that returns out-of-band coverage triggers a Phase-5
calibration-refresh flag in the next backtest cadence.

### Capacity / cost

- ~500 stocks × 1 calibration per month × ~5 years horizon resolution
  = ~30 000 rows
- Row size ~80 bytes → ~2.4 MB — trivial on free tier
