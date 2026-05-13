---
name: going-concern-phrase-refine
description: Implement Phase 4 refinements to the going-concern phrase regex
  (negation lookbehind, MD&A section restriction) to drop FP rate from PR-3d
  observed 10.8% to <5% target. Validates with going-concern-fp-audit + a
  known-positive corpus.
---

# going-concern-phrase-refine — STUB

## When to use

- Phase 4 work on `/tmp/issue_drafts/issue_going_concern_phrase_refinement.md`
- After collecting a known-positive corpus (small-cap restated
  filings) and known-negative corpus (S&P 500 healthy 10-Ks)

## What to flesh out (TODO when implementing)

- Option A: Negation lookbehind on each phrase pattern:
  - `(?<!\bno\s)(?<!\bnot\s)(?<!\bany\s)` prefix
- Option B: MD&A section restriction (Item 7 only, skip Item 1A risk
  factors). Requires lightweight section-header regex (NOT the
  expensive `hybrid_section_detector` we removed in PR-3d)
- Option C: Both A + B
- Option D (last resort): FinBERT classifier
- Test corpus: ~50 known TP + ~100 known TN, measure FP/FN before
  + after refinement

## Acceptance criteria

- FP rate ≤ 5% on S&P 500
- Recall ≥ 80% on known-positive corpus
- No regression in scan latency (<100µs/filing)
- Added tests in `tests/test_scoring/test_going_concern.py`

## Related

- `compute/scoring/going_concern.py::GOING_CONCERN_PHRASES`
- `phase-3d/going-concern-fp-audit` (companion analysis tool)
- `/tmp/issue_drafts/issue_going_concern_phrase_refinement.md`
