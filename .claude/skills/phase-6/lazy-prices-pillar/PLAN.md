# Phase 6 — Lazy Prices Pillar (PLAN)

> **Status**: PLAN — new pillar; significant SEC EDGAR full-text
> infrastructure; multi-week scope. Defer execution.

## Goal

Per Research Report v1.0 §3 + Cohen-Malloy-Nguyen 2020 JF 75(3):1371-1415
"Lazy Prices", add a NEW 10th pillar `disclosure_change` that scores
each ticker by year-over-year **textual similarity** of consecutive
10-K (and optionally 10-Q) filings. Stocks with HIGH YoY similarity
(unchanged disclosure → "nonchangers") earn POSITIVE pillar score;
LOW similarity (substantive disclosure changes → "changers") earn
NEGATIVE pillar score (or a new `lazy_prices_changer` annotate flag).

Original Cohen-Malloy-Nguyen 2020 JF: "A portfolio that shorts
'changers' and buys 'nonchangers' earns up to 188 basis points per
month in alpha (over 22% per year)" — realistic capture in long-only
S&P 500 post-publication = 3-6%/yr per report.

## Files changed

- `compute/ingest/edgar_filings.py` (NEW) — full-text 10-K/10-Q fetcher with on-disk cache at `compute/cache/edgar_filings/<TICKER>/<accession>.txt.gz`. Proper `EDGAR_USER_AGENT` per SKILL.md Rule.
- `compute/features/lazy_prices.py` (NEW) — pure function: `compute_yoy_similarity(filing_curr_text, filing_prev_text) -> float`. Uses sklearn `TfidfVectorizer` (BSD-3) + `cosine_similarity`. Pre-processes by stripping XBRL tags, normalizing whitespace, removing tables.
- `compute/scoring/lazy_prices_pillar.py` (NEW) — pillar wrapper: load cache, compute YoY for each ticker, normalize to 0-100 within universe.
- `compute/scoring/pillars.py` — add `disclosure_change` pillar (or fold into JKP refactor)
- `compute/scoring/composite.py` — re-weight inclusion (or 10th pillar surface, NOT in composite — see Defense mode)
- `compute/scoring/risk_overlay.py` — `lazy_prices_changer` annotate (bottom-quintile YoY similarity)
- `compute/output/schemas.py` — `StockDetail.disclosure_change_score: float | None` + `Metadata.lazy_prices_*` diagnostics (cache hit rate, average similarity, changer count)
- `frontend/lib/types.ts` + snapshot — triple lockstep
- `frontend/components/PillarRadarChart.tsx` — add 10th axis (or replace if JKP refactor lands first)
- `tests/test_features/test_lazy_prices.py` — 15+ tests with synthetic fixtures + 1 `@network` smoke
- `docs/edgar_lazy_prices.md` (NEW) — cache layout, fetch retry policy, methodology

## Schema delta

MINOR bump: `0.10.x` → `0.11.0-phase6` (additive new pillar score field;
non-breaking since downstream-consumers ignore unknown fields).

## Defense mode

- `disclosure_change` pillar → POSITIVE ranking signal (within composite, gated on JKP refactor decision)
- `lazy_prices_changer` annotate → ANNOTATE only Phase 1; Rule 18 observability ships first

## Tests

- Unit (15+):
  - YoY similarity ∈ [0, 1] for any text pair
  - Identity test: cosine(text, text) ≈ 1.0
  - Orthogonal text: cosine ≈ 0
  - HTML/XBRL strip preserves token semantics
  - Cache hit returns identical bytes
- Hypothesis: shuffle invariance for bag-of-words (TF-IDF is order-invariant)
- Golden value: 2-3 known 10-K pairs (e.g., GE 2018 vs 2017 — high change cohort per CMN 2020)
- `@network` (1-2): live SEC EDGAR fetch of 1 recent 10-K (skipped if no `EDGAR_USER_AGENT`)

## Production verification

- `Metadata.lazy_prices_cache_hit_pct ≥ 95%` after first cron warm-cache
- `Metadata.lazy_prices_changer_count` ∈ [80, 120] (~ 20% of 502 universe per CMN 2020 base rate)
- Section L verify-helper extension (Section M?) — disclosure-change accounting equation

## Fallback triggers

- SEC EDGAR rate-limit exhaustion (10 req/sec) → batch + backoff; cold-cache populate over 2-3 days off-cron via dedicated workflow
- Cache size > 5GB (compressed) → exclude historical 10-Qs, keep 10-K only
- Cosine similarity skewed (>95% of stocks at sim > 0.9) → re-tune normalization (z-score within sector instead of universe)

## Acceptance checklist

- [ ] `compute/ingest/edgar_filings.py` honors EDGAR_USER_AGENT + rate limit
- [ ] Full-text strip preserves narrative tokens, drops XBRL noise
- [ ] sklearn TfidfVectorizer + cosine_similarity (BSD-3)
- [ ] Cache layout documented in `docs/edgar_lazy_prices.md`
- [ ] `disclosure_change` pillar (or annotate) integrated per JKP refactor decision
- [ ] Rule 18 `Metadata.lazy_prices_*` diagnostics ship FIRST
- [ ] 15+ unit + 1 hypothesis + 2 `@network` smoke
- [ ] PBO ≤ 0.5 + DSR > 0 + BH-FDR < 0.05 for new pillar
- [ ] `methodology-scientist`: LITERATURE-ANCHORED per CMN 2020 JF
- [ ] `security-reviewer`: PASS on edgar_filings.py (User-Agent + rate-limit + no PII)

## License posture

- SEC EDGAR full-text: public domain
- `scikit-learn`: BSD-3 ✅
- No paid data deps
- Cache: gitignored (rebuild from EDGAR if blown away)

## Estimated effort

**3-4 weeks focused dev**. Cold-cache populate alone is 2-3 days of
off-cron workflow runs. Recommend dedicated session series.
