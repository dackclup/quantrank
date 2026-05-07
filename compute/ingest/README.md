# compute/ingest

Free-tier data fetchers, one module per source. Each module caches to
`compute/cache/` and uses `tenacity` retry on transient errors.

| Module | Source | Phase |
|---|---|---|
| `universe.py` | Wikipedia (S&P 500 constituents) | 1 |
| `prices.py` | yfinance OHLCV | 1 |
| `fundamentals.py` | edgartools (SEC EDGAR) | 2 |
| `insider.py` | edgartools Form 4 | 4 |
| `institutional.py` | edgartools 13F | 4 |
| `macro.py` | fredapi | 6 |
| `news.py` | finnhub + yfinance | 4 |
| `reddit.py` | PRAW | 4 |
