# compute/scoring

Turns features into 0-100 pillar scores, a composite StockRank, and an
ensemble fair price. All sector-relative for fundamentals (Rule 6 in SKILL.md).

| Module | Role | Phase |
|---|---|---|
| `normalize.py` | Winsorize, sector-rank, percentile | 3 |
| `pillars.py` | Aggregate features → 8 pillar scores | 3 |
| `composite.py` | Weighted sum → 0-100 | 3 |
| `fair_price.py` | DCF + Graham + RIM + multiples ensemble | 3 |
| `risk_overlay.py` | Beneish/Sloan/Z″ vetoes | 3 |
