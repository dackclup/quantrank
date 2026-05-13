---
name: universe-refresh
description: Refresh the cached S&P 500 universe from Wikipedia and report any
  additions / removals (delistings, M&A) since the last cached version. Use when
  rankings.json count diverges from expected 502 or after long absence to catch
  index reconstitution events.
---

# universe-refresh — STUB

## When to use

- Workflow run reports `universe_size != 502` (typical Wikipedia
  return is 503 with FI delisted; see PR-3d Run #15)
- After known S&P 500 reconstitution events
- Quarterly / monthly proactive refresh

## What to flesh out (TODO when implementing)

- Path to universe cache file (`compute/cache/universe/sp500.csv`?)
- Wikipedia URL parsed (`https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`)
- Diff format: added / removed / sector-changed
- Cache invalidation trigger (force-refresh flag)
- Test fixture for delisted ticker handling (e.g., `FI`)

## Acceptance criteria

- Reports universe size delta vs cached version
- Lists added / removed tickers with prior sector
- Handles yfinance-not-found tickers gracefully
- Updates cache atomically (tmp + os.replace pattern)

## Related

- `compute/ingest/universe.py`
- `phase-2/sec-api-health-check` (CIK lookup for new entrants)
