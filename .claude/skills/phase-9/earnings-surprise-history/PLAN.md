# Earnings Surprise History (Phase 9 planning stub)

**Status**: Planning. Derives "beats vs misses" track record from
already-cached quarterly EPS data + analyst consensus. Free, simple,
retail-loved.

## Purpose

A stock that beat consensus EPS 7 of last 8 quarters has different
expected return than one that missed 6 of 8. Even though analysts
adjust expectations, the post-earnings-announcement drift (PEAD) is
one of the most robust anomalies in finance literature (Bernard-Thomas
1989; Foster-Olsen-Shevlin 1984; Hou-Xue-Zhang 2020 confirms PEAD as
one of 14 surviving anomalies of the 452 they tested).

Phase 9 §4: surface 8-quarter beat/miss history as a chip + tooltip.

## Free data source

Two sources combined:
1. **Reported EPS** — already cached via SEC XBRL (`compute/ingest/fundamentals.py` has `eps_diluted` per quarter)
2. **Analyst consensus** — yfinance `Ticker.earnings_history` (free, weekly updates)

## Signal features

| Feature | Type | How it's computed |
|---|---|---|
| `beat_count_last_8q` | int 0-8 | reported_eps > consensus_eps |
| `miss_count_last_8q` | int 0-8 | reported_eps < consensus_eps × 0.95 (5% miss threshold) |
| `streak_current` | int (+ for beats, - for misses) | Consecutive beats or misses ending at last quarter |
| `avg_surprise_pct` | float | mean((reported - consensus) / consensus) × 100 |

## UI display

Beginner-friendly badge:

| Pattern | Pill | Tooltip |
|---|---|---|
| 7+ of 8 beats | 🟢 "Consistent beats" emerald-50 | "Beat consensus 7 of last 8 quarters" |
| 3+ consecutive beats | 🟢 "Hot streak" emerald-50 | "Beat consensus 3 quarters in a row" |
| 5+ misses | 🔴 "Frequent miss" red-50 | "Missed consensus 5 of last 8 quarters" |
| 3+ consecutive misses | 🔴 "Cold streak" red-50 | "Missed 3 quarters in a row" |
| Mixed (4-5 beats / 8) | — no badge | (most stocks) |

## Effort

| Step | LOC | Days |
|---|---|---|
| Consensus pull from yfinance `earnings_history` | ~80 | 1 |
| Surprise computation + streak | ~120 | 1 |
| Schema additions (`StockDetail.earnings_history` with 8 quarters) | ~40 | 0.5 |
| EarningsHistoryBadge component | ~80 | 0.5 |
| Detail-page mini-table (8 quarters: reported / consensus / surprise %) | ~150 | 1.5 |
| Tests | ~120 | 1 |
| **Total** | **~590 LOC** | **~5.5 days** |

## Decisions (locked)

1. ~~How many quarters?~~ → **8 (2 years)** — standard SOTA per Hou-Xue-Zhang 2020
2. ~~Miss threshold?~~ → **5% below consensus** (within-noise misses don't count)
3. ~~Beat threshold?~~ → **0% above consensus** (any positive surprise counts as beat)
4. ~~yfinance vs SEC primary?~~ → **Reported = SEC XBRL primary; Consensus = yfinance (consensus is in proprietary feeds; yfinance scrapes)**. Fallback both directions

## Dependencies

- Phase 0-2 fundamentals ingest (already done)
- Phase 4a workflow cache — caches yfinance earnings_history
- Phase 5 backtest validate IC of surprise signal over baseline

## Out of scope

- Real-time earnings call audio (Phase 6 `whisper-transcribe`)
- Sentiment of management Q&A (Phase 6)
- Forward guidance changes (separate stub)
