---
name: meta-label
description: Implement López de Prado meta-labeling — train a secondary
  classifier on top of the primary model (composite ranking) to predict
  whether the primary's signal will be profitable. Phase 5 ML stack.
---

# meta-label — STUB

## When to use

- Phase 5 ML meta-learner work, after triple-barrier-label provides
  the targets

## What to flesh out (TODO when implementing)

- Primary model: existing 10-pillar composite (already produces a
  rank for every ticker every week)
- Meta-features: a subset of the 158 Alpha158 features + IPCA
  factor exposures + recent realized return
- Meta-target: triple-barrier label (1 / -1 / 0)
- Training: rolling window, no leakage past asof date
- Output: a calibrated probability `p_profitable` per stock per week
- Module location: `compute/ml/meta_label.py`

## Acceptance criteria

- Out-of-sample AUC > 0.55 on the meta-target (low bar; 0.5 is
  random)
- Calibration: predicted probability ≈ realized rate (Platt or
  isotonic)
- No look-ahead bias (verified by lag check)

## Related

- López de Prado 2018 Ch.4
- `phase-5/triple-barrier-label`
- `phase-5/conformal-predict` (uncertainty quantification on top)

## Supabase usage — experiment tracking

Phase 5 will run 50+ ablation studies (different hyperparameter
combinations, meta-feature subsets, primary-model variants). Track
them in `experiments` instead of standing up an MLflow / W&B
server. The Supabase MCP connector is already registered (see
`CLAUDE.md` §Connectors).

### Schema

```sql
create table experiments (
  experiment_id uuid primary key,
  branch text,
  primary_model text,           -- e.g., 'composite_v1.2.0-phase4.5'
  meta_features jsonb,          -- list of feature names
  hyperparameters jsonb,        -- {n_estimators: 500, max_depth: 6, learning_rate: 0.05}
  auc_oos numeric,              -- acceptance: > 0.55
  brier_score numeric,
  calibration_slope numeric,    -- Platt / isotonic — target ≈ 1.0
  lookahead_check_passed bool,
  notes text,
  created_at timestamptz default now()
);

create index experiments_branch on experiments (branch);
create index experiments_created on experiments (created_at desc);
```

### Write pattern

After every training run during meta-label development:

```python
from supabase import create_client
supabase.table('experiments').insert({
    'branch': 'feat/meta-label-v1',
    'primary_model': 'composite_v1.2.0-phase4.5',
    'meta_features': ['rsi_14', 'mom_12_1', 'pillar_growth', 'manipulation_index'],
    'hyperparameters': {'n_estimators': 500, 'max_depth': 6, 'learning_rate': 0.05},
    'auc_oos': 0.567,
    'brier_score': 0.221,
    'calibration_slope': 1.02,
    'lookahead_check_passed': True,
    'notes': 'Alpha158 mom subset; +0.012 AUC vs baseline',
}).execute()
```

### Query the leaderboard at any point

```sql
select primary_model, hyperparameters, auc_oos, brier_score
from experiments
where auc_oos > 0.55              -- acceptance threshold per PLAN
  and lookahead_check_passed
order by auc_oos desc
limit 20;
```

### Why Supabase over MLflow / W&B

- Zero infra to provision (MCP connector already registered)
- SQL-queryable from analyst tooling without an additional client
- Free tier 500 MB easily holds 10 000+ experiments at ~1 KB each
- No conflict with the static-site architecture — Supabase is the
  experiment metadata layer; production composite still ships
  JSON-only
