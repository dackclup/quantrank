---
name: nsi-debug
description: For a single ticker, expose the Net Stock Issuance computation
  (Δ shares outstanding YoY) and the sector-decile threshold for the
  net_issuance_top_decile veto. Use during triage when a stock is flagged
  but the issuance level seems normal — usually a shares_outstanding XBRL
  tag issue (Phase 4 issue #10).
---

# nsi-debug — STUB

## When to use

- A stock with no known dilution event is flagged
  `net_issuance_top_decile`
- After modifying the NSI implementation in
  `compute/scoring/risk_overlay.py`
- During debug of `shares_outstanding` data-quality issues
  (Phase 4 issue #10)

## What to flesh out (TODO when implementing)

- Single-ticker probe: `python helper.py NVDA`
- Output: shares_outstanding (current), shares_outstanding (prior
  year), Δ%, sector decile threshold, decision
- Cross-check against `RawMetrics.shares_outstanding` and
  fundamentals snapshot to detect XBRL tag drift
- Sector context: top 10 issuers in sector with their NSI%

## Acceptance criteria

- Resolves in <5s per ticker
- Surfaces XBRL tag fallback chain used for shares_outstanding
- Detects the Phase 4 issue #10 pattern (stale or wrongly-tagged
  shares figure)

## Related

- `compute/scoring/risk_overlay.py::compute_net_issuance`
- Pontiff-Woodgate 2008 *JF*
- Phase 4 issue #10 (shares_outstanding XBRL fix)
