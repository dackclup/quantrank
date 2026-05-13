---
name: yfinance-debug
description: Diagnose yfinance fetch failures (rate-limit, ticker-not-found,
  protocol drift) for individual tickers and report whether the issue is
  transient (re-run) or persistent (universe update needed). Use when prices
  stage fails for specific tickers or coverage drops below expected.
---

# yfinance-debug — STUB

## When to use

- Workflow log shows `fetch_prices raised for <ticker>` warnings
  exceeding the typical baseline (~0-2 per run)
- A known-listed ticker returns no price data
- yfinance API drift suspected (after `pip install -U yfinance`)

## What to flesh out (TODO when implementing)

- Single-ticker probe script: `python helper.py AAPL`
- Output: last fetched timestamp, row count, columns, sample values
- Distinguishes: rate-limit (429) vs not-found (404) vs auth-required
- yfinance version check
- Suggested re-try delay if rate-limited

## Acceptance criteria

- Diagnoses ticker in <10 seconds (single fetch)
- Surface yfinance version + last successful fetch timestamp
- Clear next-action recommendation per failure mode

## Related

- `compute/ingest/prices.py`
- yfinance issue tracker (link in `pyproject.toml` if pinned)
