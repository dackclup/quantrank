---
name: lazy-prices-detect
description: Implement the Lazy Prices signal (Cohen-Malloy-Nguyen 2020) — detect
  meaningful changes in 10-K/10-Q filings via cosine similarity vs prior filing
  and flag stocks where filings have changed substantially. The change itself
  is a return-predictive signal (Phase 6 sentiment).
---

# lazy-prices-detect — STUB

## When to use

- Phase 6 sentiment v2 implementation
- Adds a return-predictive signal that's distinct from
  level-of-sentiment (FinBERT) — measures DELTA in disclosure

## What to flesh out (TODO when implementing)

- Inputs: current 10-K text (cached in
  `compute/cache/edgar_10k_text/`) + prior year's 10-K text
- Method: cosine similarity on TF-IDF vectors (or sentence-BERT
  embeddings — heavier but more semantic)
- Output: `StockDetail.lazy_prices_change_score: float` (0 = no
  change, 1 = full rewrite)
- Threshold for "lazy_prices_alert" annotate flag: bottom-decile
  similarity (most-changed filings)
- Module location: `compute/scoring/lazy_prices.py`

## Acceptance criteria

- Reproduces Cohen-Malloy-Nguyen 2020 sample similarity
  distribution
- Bottom-decile (most-changed) filings show negative future return
  drift (the paper's core claim)
- No look-ahead bias — only uses prior filing available before
  current asof date

## Related

- Cohen-Malloy-Nguyen 2020 *JF*
- Phase 6 schema bump
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique 2.X"
