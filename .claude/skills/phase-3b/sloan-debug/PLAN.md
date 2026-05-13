---
name: sloan-debug
description: For a single ticker, expose the Sloan accruals computation (net
  income − operating cash flow) / total assets and the sector-decile threshold
  it's compared against. Use during triage when a stock is flagged
  sloan_accruals_top_decile incorrectly — typically a sector-semantics issue
  (financials use accruals as primary income source, not earnings quality
  signal). Tracks Phase 4 issue #7.
---

# sloan-debug — STUB

## When to use

- A bank / insurer is flagged `sloan_accruals_top_decile` (likely
  false positive — Phase 4 issue #7)
- A reviewer questions the threshold for a specific ticker
- After modifying the Sloan implementation in
  `compute/scoring/risk_overlay.py`

## What to flesh out (TODO when implementing)

- Single-ticker probe: `python helper.py JPM`
- Output: numerator (NI - OCF), denominator (Total Assets), ratio,
  sector decile threshold, decision
- Sector context: list all tickers in the same sector with their
  Sloan ratio, highlight which are in top-decile
- Phase 4 hint: if ticker is Financials, recommend the alternative
  metric Phase 4 will introduce (e.g., bank-specific accrual proxy)

## Acceptance criteria

- Resolves in <5s per ticker
- Reports threshold + percentile within sector
- Surfaces issue #7 context for affected sectors

## Related

- `compute/scoring/risk_overlay.py::compute_sloan_accruals`
- Sloan 1996 *The Accounting Review*
- Phase 4 issue #7 (Sloan-bank semantics fix)
