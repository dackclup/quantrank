---
name: altman-debug
description: For a single ticker, recompute the Altman Z″-Score with full
  intermediate values exposed (working capital, retained earnings, EBIT,
  market value of equity, sales / total assets) and explain why the
  altman_distress veto did or did not fire. Use during defense-layer
  triage when a flagged stock seems incorrectly distressed.
---

# altman-debug — STUB

## When to use

- A reviewer questions why a specific stock has the
  `altman_distress` veto
- After modifying the Altman Z″ implementation in
  `compute/scoring/risk_overlay.py`
- During PR-3e Tier-3 Beneish work to compare against the existing
  Altman intermediate values

## What to flesh out (TODO when implementing)

- Single-ticker probe: `python helper.py AAPL`
- Output: 4 intermediate ratios + Z″ score + threshold band
  (distress / grey / safe per Altman 2000)
- Side-by-side: Altman 1968 (5-factor) vs Altman 2000 Z″ (4-factor,
  no MV/equity — emerging markets variant we use)
- Explanation: why this ticker is in the band it's in

## Acceptance criteria

- Resolves in <5s per ticker (data already cached after fundamentals
  stage)
- Reports all 4 (Z″) or 5 (Z) intermediate ratios with units
- Cites which Altman variant we use (`Altman 2000 Z″`) and why
  (no MV/equity column for un-listed comparables)

## Related

- `compute/scoring/risk_overlay.py::compute_altman_z_score`
- Altman 1968 *Journal of Finance* / Altman 2000 (emerging markets)
- `defense-scorecard` for the population-level fire rate (~54/502)
