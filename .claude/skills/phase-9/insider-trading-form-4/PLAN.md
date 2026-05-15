# Insider Trading via SEC Form 4 (Phase 9 planning stub)

**Status**: Planning. High-priority Phase 9 stub — retail users love
"insiders are buying" signal (popularized by Jitta + Pelosi Tracker).
Already in our EDGAR fetch surface; just need to consume Form 4.

## Purpose

SEC Form 4 = mandatory filing within 2 business days when corporate
insiders (CEO, CFO, directors, 10%+ shareholders) trade their own
company's stock. Cohen-Malloy-Pomorski 2012 (JFE) found insider
"opportunistic" buys (i.e., non-scheduled) predict 12-month excess
returns of +5-7%.

Phase 9 §2: ingest Form 4 filings, classify by insider role + trade
type, surface as a per-stock chip with badge.

## Free data source

SEC EDGAR Form 4 — fully free, ~3500 filings/day across S&P 500.
Already part of `compute/ingest/filing_text.py` infrastructure.

## Signal classification

Per-stock 12-month rolling features:

| Feature | Source | Predictive value |
|---|---|---|
| `insider_net_buy_dollars` | sum of buys minus sells (net) | Strong predictor (Cohen-Malloy-Pomorski 2012) |
| `ceo_or_cfo_buying` | bool — high-conviction signal | Strongest sub-signal |
| `cluster_buying` | 3+ insiders buying same month | Klan-buying effect (Akbas-Jiang-Koch 2016) |
| `routine_vs_opportunistic` | Routine = monthly options exercise; Opportunistic = discretionary buy | Only opportunistic predicts return |

## Architecture

```
compute/ingest/form_4.py        # Fetch + parse Form 4 XML
compute/scoring/insider.py      # Classify routine vs opportunistic
                                # Compute 12-month rolling net buy
compute/output/schemas.py       # Add StockDetail.insider_signal
frontend/components/InsiderBadge.tsx  # Beginner-friendly chip
```

## UI display

Beginner-friendly badge next to ticker (after recommendation badge):

| Signal | Pill | Tooltip |
|---|---|---|
| `ceo_or_cfo_opportunistic_buy_last_30d` | 🟢 "Insiders buying" emerald-50 | "CEO/CFO bought shares in last 30 days" |
| `cluster_buy_last_60d` | 🟢 "Insider cluster buy" emerald-50 | "3+ insiders bought in last 60 days" |
| `net_sell_last_90d` | 🔴 "Insiders selling" red-50 | "Net insider selling > $1M in last 90 days" |
| (none) | — no badge | not surfaced |

## Effort

| Step | LOC | Days |
|---|---|---|
| Form 4 XML parser (edgartools facade) | ~150 | 2 |
| Classify routine vs opportunistic | ~100 | 1 |
| Schema + writer wire-up | ~30 | 0.25 |
| InsiderBadge component | ~80 | 0.5 |
| Tests (XML fixtures from real filers) | ~150 | 1.5 |
| **Total** | **~510 LOC** | **~5 days** |

## Decisions (locked)

1. ~~Filter routine vs opportunistic?~~ → **Yes** (Cohen-Malloy-Pomorski
   2012 — only opportunistic predicts return)
2. ~~$ threshold for "meaningful"?~~ → **$10K minimum trade** (filter
   out tiny option exercises)
3. ~~Time window?~~ → **30d (CEO/CFO), 60d (cluster), 90d (net sell)**
4. ~~Pelosi/Congressional STOCK Act feed?~~ → **Defer to Phase 9.5**;
   different data source (Senate Periodic Transaction Reports)

## Dependencies

- Phase 4a workflow cache (already merged) — caches Form 4 XML
- Phase 5 backtest infra — validates IC > 0.01 over baseline

## Out of scope

- Form 13D/G (5%+ activist filings) — separate stub
- Form 144 (planned insider sales) — moved to Phase 9.x
- Hedge fund 13F flow — separate stub (`institutional-flow-13f/`)
