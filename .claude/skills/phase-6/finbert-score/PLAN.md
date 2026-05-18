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

## Supabase usage — pgvector for filing similarity

FinBERT produces 768-dim embeddings per MD&A section. Storing these
in Postgres + pgvector unlocks two analyses the per-stock JSON
snapshot cannot:

1. **MD&A similarity search** — "find 10 stocks whose 10-K MD&A
   reads most like NVDA's latest" → portfolio-level theme detection
2. **Year-over-year MD&A drift** — "did AAPL's MD&A language shift
   suddenly between FY24 and FY25?" → Cohen-Malloy-Nguyen 2020
   "Lazy Prices" signal complement (which uses raw-text diff;
   embeddings capture semantic shift)

The Supabase MCP connector is already registered (see `CLAUDE.md`
§Connectors).

### Schema

```sql
create extension if not exists vector;

create table mda_embeddings (
  ticker text not null,
  fiscal_year int not null,
  section text not null,           -- 'item_7_mda' | 'item_1_business' | 'item_1a_risk'
  embedding vector(768),           -- FinBERT default dim
  text_hash text,                  -- sha256 of source text for dedup
  finbert_pos numeric,             -- sentiment scores from same model pass
  finbert_neg numeric,
  finbert_neu numeric,
  finbert_uncertainty numeric,
  filed_at timestamptz,
  primary key (ticker, fiscal_year, section)
);

create index mda_embeddings_hnsw
  on mda_embeddings
  using hnsw (embedding vector_cosine_ops);

create index mda_embeddings_ticker on mda_embeddings (ticker, fiscal_year desc);
```

### Queries enabled

```sql
-- Top-10 stocks whose latest-year Item 7 MD&A reads like NVDA's
with nvda as (
  select embedding
  from mda_embeddings
  where ticker = 'NVDA'
    and section = 'item_7_mda'
  order by fiscal_year desc
  limit 1
)
select ticker, fiscal_year, embedding <=> (select embedding from nvda) as cosine_dist
from mda_embeddings
where section = 'item_7_mda'
  and ticker != 'NVDA'
order by embedding <=> (select embedding from nvda)
limit 10;

-- Year-over-year MD&A drift for AAPL
select fiscal_year,
       embedding <=> lag(embedding) over (order by fiscal_year) as yoy_distance
from mda_embeddings
where ticker = 'AAPL'
  and section = 'item_7_mda'
order by fiscal_year;
```

### Ingestion pattern

`compute/scoring/finbert_sentiment.py`:

1. For each ticker × fiscal_year × section, hash the source text
2. Skip if `(ticker, fiscal_year, section)` already present AND
   `text_hash` matches (text unchanged → no re-embed)
3. Else run FinBERT → embedding + sentiment scores
4. `INSERT ... ON CONFLICT (ticker, fiscal_year, section) DO UPDATE`

### Capacity / cost

- ~500 tickers × ~5 years × 3 sections = ~7 500 rows
- Row size: 768 × 4 bytes (float32) + metadata ≈ 3.2 KB
- Total ≈ 24 MB — well within Supabase 500 MB free tier
- HNSW index adds ~10-20% storage overhead (negligible)
- Cosine similarity query latency: < 100 ms for 7 500 rows with HNSW

### Why pgvector over an external vector DB

- Already part of the Supabase MCP connector — zero additional infra
- Co-located with `experiments` / `shap_values` / other Phase 5
  tables → cross-join queries are SQL-native (e.g., "for stocks
  with similar MD&A to NVDA, what's their meta-label probability?")
- pgvector handles datasets up to ~1 M rows comfortably; QuantRank
  is 4 orders of magnitude smaller
