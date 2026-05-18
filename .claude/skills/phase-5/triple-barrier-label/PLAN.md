---
name: triple-barrier-label
description: Label time-series price data using the López de Prado Triple Barrier
  Method (TBM) — first-touch upper / lower / time-decay barriers — for use as
  the supervised target in Phase 5 ML meta-learner training. Replaces naive
  fixed-horizon return labels.
---

# triple-barrier-label — STUB

## When to use

- Phase 5 ML meta-learner training data prep
- After `phase-4/alpha158-fit` ships features

## What to flesh out (TODO when implementing)

- Library: `mlfinlab` is AGPL — incompatible with Apache 2.0 repo
  license. Port the algorithm natively (~30 lines of pandas/numpy)
- Inputs: per-ticker OHLCV from
  `frontend/public/data/stocks/history/<TICKER>.json`
- Outputs: per-ticker labels (1 = upper barrier hit first, -1 =
  lower, 0 = time decay)
- Module location: `compute/ml/triple_barrier.py`

## Acceptance criteria

- Reproduces López de Prado Ch.3 example numerically
- Configurable upper/lower thresholds + time horizon
- No mlfinlab dependency (license compatibility)

## Related

- López de Prado 2018 *Advances in Financial Machine Learning*
  Ch. 3 (Triple Barrier) + Ch. 4 (Meta-Labeling)
- `phase-5/meta-label` (consumer of these labels)
- SKILL.md library matrix — note "mlfinlab AGPL warning"

## Supabase usage — barrier event log (optional)

Triple-barrier labels are deterministic given the input price series
+ thresholds, so persistence is not strictly required — labels can
always be recomputed from `frontend/public/data/stocks/history/<TICKER>.json`.
Storing the per-fold label distribution in Supabase is **optional**
and worth doing only if the analyst workflow benefits.

### Schema (optional)

```sql
create table barrier_events (
  ticker text,
  asof_date date,
  label int,                       -- 1 (upper hit) | -1 (lower hit) | 0 (time decay)
  upper_threshold numeric,
  lower_threshold numeric,
  horizon_days int,
  primary key (ticker, asof_date, horizon_days)
);

create index barrier_events_label on barrier_events (label, asof_date);
```

### Use cases that justify storage

- **Label distribution sanity check** — "What fraction of AAPL labels
  are 0 (time decay) over 5 years? Is the horizon too short?":

  ```sql
  select label, count(*) * 1.0 / sum(count(*)) over () as share
  from barrier_events
  where ticker = 'AAPL'
    and horizon_days = 20
  group by label;
  ```

- **Determinism audit** — if labels change between re-runs, something
  is non-deterministic in the labeling pipeline (random seed leak,
  asof_date drift). Compare `barrier_events` snapshots across two
  runs of the same commit hash.

### When to skip this table

If budget is tight or analyst workflow doesn't need it, **skip** —
labels are pure functions of (price_history, thresholds, horizon)
and recomputable in <1 s per ticker. Include only after `meta-label`
ships and the experiment-tracking surface highlights label-stability
as a debugging surface.
