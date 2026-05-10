---
name: xbrl-tag-debug
description: For a given ticker + concept (e.g., AAPL + LongTermDebt), report
  which us-gaap XBRL tags edgartools resolves and which are missing. Use when
  fundamentals fields show up null for tickers that should have them — usually
  the concept fallback chain in fundamentals.py needs a new tag added.
---

# xbrl-tag-debug — STUB

## When to use

- A ticker's `RawMetrics.<field>` is null but the field is reported
  in their 10-K
- Adding a new financial metric to `_BALANCE_TAGS` / `_ANNUAL_TAGS`
  / `_TTM_TAGS` and unsure of the full us-gaap fallback chain
- After Phase 4 issue #10 (shares_outstanding), #7 (Sloan-bank
  semantics) — both are XBRL-tag-coverage issues

## What to flesh out (TODO when implementing)

- Single-ticker probe: `python helper.py AAPL LongTermDebt`
- Output: which tags edgartools resolved, sample values, sample
  filing dates, missing-tag candidates
- Compares against the current fallback chain in `fundamentals.py`
- Suggests new tags to add if a viable one is found

## Acceptance criteria

- Resolves in <30s per ticker
- Surfaces all us-gaap variants the entity has filed with
- Distinguishes "tag never filed" from "tag filed in older years only"
- Recommends tag addition if confidence is high (≥3 tickers
  benefit from the addition)

## Related

- `compute/ingest/fundamentals.py` `_BALANCE_TAGS` / `_ANNUAL_TAGS`
- edgartools `Company.get_facts().get_annual_fact()`
- Phase 4 issues #7, #10, #11
