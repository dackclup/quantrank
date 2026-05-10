---
name: whisper-transcribe
description: Transcribe earnings call audio to text using Whisper for downstream
  sentiment analysis. Phase 6 sentiment v2 — extends beyond 10-K text scans
  (current Defense #8) to live management commentary.
---

# whisper-transcribe — STUB

## When to use

- Phase 6 sentiment v2 implementation
- Earnings call transcript ingest (input to FinBERT sentiment scoring)

## What to flesh out (TODO when implementing)

- Library: `openai-whisper` (local, free) or OpenAI API (cloud, paid)
- Input source: earnings call audio (TBD — Seeking Alpha? Bloomberg?
  AlphaSense?). Likely paid data source — flag the licensing
  dependency early.
- Output: per-call transcript with speaker diarization
  (CEO / CFO / analysts)
- Cache: `compute/cache/earnings_transcripts/<ticker>_<YYYY-MM-DD>.txt`
  (90-day TTL)
- Module location: `compute/ingest/earnings_audio.py`

## Acceptance criteria

- WER (word error rate) < 10% on benchmark calls
- Speaker diarization correctly attributes ≥80% of segments
- Transcripts cached and de-duplicated across runs

## Related

- OpenAI Whisper paper (2022)
- Phase 6 schema: `StockDetail.recent_earnings_transcripts`
- `phase-6/finbert-score` (downstream consumer)
