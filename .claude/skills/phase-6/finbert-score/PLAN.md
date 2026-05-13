---
name: finbert-score
description: Score 10-K MD&A + 8-K + earnings call transcripts using FinBERT
  (financial-domain BERT variant) and produce a sentiment + uncertainty
  signal per ticker. Replaces the current Loughran-McDonald dictionary
  word-list approach in Defense #8 with embedding-based sentiment.
---

# finbert-score — STUB

## When to use

- Phase 6 sentiment v2 implementation
- After earnings call transcripts ingest is working
- May complement (not replace) the LM-dictionary phrase scan from
  PR-3d

## What to flesh out (TODO when implementing)

- Model: `ProsusAI/finbert` (HuggingFace, ~440MB)
- Inputs: 10-K MD&A text (already cached in
  `compute/cache/edgar_10k_text/`) + 8-K item bodies (already cached)
  + earnings transcripts (Phase 6 new)
- Outputs: 3 scores per ticker (positive, negative, neutral) +
  uncertainty (confidence)
- Module location: `compute/scoring/finbert_sentiment.py`
- Caching: per-document inference cache (FinBERT inference is the
  expensive step, ~50ms per chunk)

## Acceptance criteria

- Scores correlate with realized returns at >0 (low bar — most
  sentiment alpha decays per Hou-Xue-Zhang 2020)
- FP rate on going-concern-equivalent prompt is <5% (FinBERT is
  trained to handle financial negation)
- Pre-trained model — no fine-tuning required

## Related

- `phase-3d/going-concern-fp-audit` (the reason we want better
  than dictionary scan)
- Phase 6 schema bump: `Tier2Events.sentiment_score: float | None`
- `docs/RESEARCH_FINDINGS.md` §"Stretch Technique 2.X" — FinBERT
