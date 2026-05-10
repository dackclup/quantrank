---
name: ensemble-method-debug
description: For a single ticker, expose all 6 fair-price methods (Graham, P/E,
  P/B, EV/EBITDA, RIM, DCF) with their inputs, intermediate calculations, and
  applicability decision. Use during triage when fair_price.median seems off
  or a method is unexpectedly skipped.
---

# ensemble-method-debug — STUB

## When to use

- Fair price for a ticker doesn't match expectations
- A method is showing `applicable: false` and the cause is unclear
- After modifying any method in `compute/valuation/`

## What to flesh out (TODO when implementing)

- Single-ticker probe: `python helper.py NVDA`
- Output per method:
  - Inputs (TBVPS, EPS, P/E peer, EV/EBITDA peer, etc.)
  - Intermediate values (e.g., DCF: WACC, terminal_g, PV_explicit_period)
  - Final price + applicability flag
  - If skipped, the reason (sector exclusion / missing input / outlier)
- Aggregate: median, max (excl. outliers), MoS%
- Cross-reference defenses: data_quality_input_corruption check (>$10K
  ceiling), outlier guard (5×/0.2× current price), terminal_g cap

## Acceptance criteria

- Resolves in <10s per ticker (data already cached)
- Each method's reasoning is auditable (inputs → intermediates →
  output)
- Highlights which methods drove the median vs which were excluded
  by which defense

## Related

- `compute/valuation/{graham,multiples,rim,dcf,ensemble}.py`
- `compute/valuation/tangible_book.py`
- `phase-3c/outlier-detection-debug` (drill into outlier exclusion)
