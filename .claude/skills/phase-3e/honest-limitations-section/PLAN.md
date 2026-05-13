---
name: honest-limitations-section
description: Generate / update the "Honest Limitations" section in README.md
  before tagging v1.0. Documents what QuantRank does NOT claim (no backtest,
  no live trading, no causal claims) and ensures every defense layer's
  caveats are surfaced to users. Phase 3e prerequisite for v1.0 tag.
---

# honest-limitations-section — STUB

## When to use

- Phase 3e, immediately before merging the final PR before v1.0 tag
- Whenever a defense changes shape (e.g., feature flag flip,
  threshold change) that materially affects what users can rely on

## What to flesh out (TODO when implementing)

- Section structure (proposed):
  1. **What this is**: 1-paragraph summary
  2. **What this is NOT**: 1-paragraph honest disclaimer
     - "Not a backtest" (no out-of-sample WF validation yet)
     - "Not live trading advice" (no portfolio construction)
     - "Not causal" (correlations between rank + future return are
       proxies, not predictions)
  3. **Defense layer caveats**: per-defense honest limitations
     - Going-concern phrase scan: 10.8% FP rate (Phase 4 will refine)
     - Beneish M-score: built on US-GAAP filings only
     - Sloan accruals: known sector-bias on financials (issue #7)
     - Net stock issuance: depends on shares_outstanding XBRL tag
       (issue #10)
  4. **Data sources + caveats**: SEC EDGAR (latency variance),
     yfinance (no SLA), Wikipedia (delisting lag)
  5. **What v1.0 ships, what v1.5 / v2.0 will add**

## Acceptance criteria

- Every active defense has a stated honest limitation
- Every external data source has a stated caveat
- "Not a backtest" / "not live trading" claims appear at least
  twice in plain English
- README's `## What this is NOT` section is at least 3 paragraphs

## Related

- `README.md`
- `docs/METHODOLOGY.md` (academic methodology — links from honest
  limitations)
- `docs/RESEARCH_FINDINGS.md` (defense playbook details)
- SKILL.md Rule 15 — performance ceiling honesty
