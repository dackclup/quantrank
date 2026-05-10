---
name: going-concern-fp-audit
description: Identify going-concern false positives — tickers flagged
  going_concern_disclosure that are clearly not going-concern risks (S&P 500
  blue chips). Categorize by likely cause (negation in risk-factor language
  vs MD&A vs other). Feeds Phase 4 phrase-regex refinement.
---

# going-concern-fp-audit — STUB

## When to use

- Phase 4 implementation of the phrase-regex refinement
  (`/tmp/issue_drafts/issue_going_concern_phrase_refinement.md`)
- After running `verify-production-output` Section B and finding the
  rate >5%
- During tuning of the regex (negation lookbehind, MD&A restriction)

## What to flesh out (TODO when implementing)

- Read every flagged ticker's cached 10-K text from
  `compute/cache/edgar_10k_text/<ticker>.json`
- Search for the matched phrase + 50 chars of context
- Categorize by negation pattern:
  - "no substantial doubt" → negation FP
  - "the Company has substantial doubt" → likely TP
  - "if substantial doubt" → conditional FP
- Per-ticker report: ticker, matched phrase, context window,
  classification

## Acceptance criteria

- Categorizes ≥80% of FP candidates correctly
- Surfaces the specific phrase variants that produce most FPs
  (informs the negation lookbehind spec)
- Recommends regex refinements with FP rate impact estimate

## Related

- `compute/scoring/going_concern.py::scan_going_concern`
- `compute/ingest/filing_text.py` (the cached 10-K text source)
- `/tmp/issue_drafts/issue_going_concern_phrase_refinement.md`
