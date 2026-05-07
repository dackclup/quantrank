# compute/ml

LightGBM ranker over all features → ML pillar score; SHAP top-5 per stock.
Populated in Phase 5.

| Module | Role |
|---|---|
| `train.py` | LightGBM walk-forward training |
| `validate.py` | IC, IR, PBO |
| `shap_explain.py` | Top-5 factors per stock |
