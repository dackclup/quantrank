# compute/features

Pure feature functions — each takes raw data, returns a value or Series indexed
by ticker. No I/O. No state. Add a golden-value unit test for every metric.

Pillar coverage by phase:

| Pillar | Module | Phase |
|---|---|---|
| Fundamental health | `fundamental.py`, `health.py` | 2-3 |
| Value | `value.py` | 3 |
| Quality / Profitability | `quality.py`, `profitability.py` | 3 |
| Growth | `growth.py` | 3 |
| Momentum | `momentum.py` | 1-3 |
| Technical | `technical.py` | 3 |
| Risk | `risk.py` | 3 |
| Sentiment | `sentiment.py` | 4 |
| Advanced valuation | `advanced_valuation.py` | 4 |
| Anomaly | `anomaly.py` | 4 |
| Macro / regime | `macro_regime.py` | 6 |

Reference all formulas to `stock_ranking_knowledge.md` — never reinvent.
