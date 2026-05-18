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

## Supabase usage (Phase 4.5e / Phase 9 implementation)

Form 4 features require rolling-window aggregation across weekly
compute runs (30 / 60 / 90 days). The static-site JSON snapshot
per-run cannot store cross-run state — Supabase Postgres is the
cross-run persistence layer. The Supabase MCP connector is already
registered (see `CLAUDE.md` §Connectors); no additional infra to
provision beyond schema + grants.

### Schema

```sql
create table insider_filings (
  filing_id text primary key,
  ticker text not null,
  filer_name text,
  filer_role text,          -- 'CEO' | 'CFO' | 'DIRECTOR' | 'OFFICER' | '10%_OWNER'
  txn_type text not null,   -- 'S' sell | 'P' purchase | 'A' grant | 'M' option-exercise
  txn_classification text,  -- 'routine' | 'opportunistic' (Cohen-Malloy-Pomorski 2012)
  shares bigint,
  price numeric,
  value_usd numeric,
  filed_at timestamptz not null,
  fiscal_year int,
  ingested_at timestamptz default now()
);

create index insider_filings_ticker_filed_at on insider_filings (ticker, filed_at desc);
create index insider_filings_filed_at on insider_filings (filed_at desc);
```

### Rolling-window queries

Three queries run during the weekly compute, each emitting a
risk-overlay annotate flag:

```sql
-- 30-day CEO/CFO opportunistic sell cluster (fires `c_suite_unusual_sell`)
select ticker, count(*) as sells
from insider_filings
where filed_at > now() - interval '30 days'
  and filer_role in ('CEO', 'CFO')
  and txn_type = 'S'
  and txn_classification = 'opportunistic'
  and value_usd >= 10000          -- $10K floor per "Decisions (locked) #2"
group by ticker
having count(*) >= 2;

-- 60-day cluster buy (3+ distinct insiders, fires `cluster_buy_last_60d`)
select ticker, count(distinct filer_name) as insider_count
from insider_filings
where filed_at > now() - interval '60 days'
  and txn_type = 'P'
  and txn_classification = 'opportunistic'
group by ticker
having count(distinct filer_name) >= 3;

-- 90-day net sell > $1M (fires `net_sell_last_90d`)
select ticker,
       sum(case when txn_type = 'S' then -value_usd else value_usd end) as net_usd
from insider_filings
where filed_at > now() - interval '90 days'
  and value_usd >= 10000
group by ticker
having sum(case when txn_type = 'S' then -value_usd else value_usd end) < -1000000;
```

### Ingestion pattern

`compute/ingest/form_4.py`:

1. Query Supabase for `max(ingested_at)` per ticker (incremental fetch
   watermark)
2. SEC EDGAR fetch new Form 4 XML since watermark via edgartools
3. Parse + classify routine vs opportunistic (Cohen-Malloy-Pomorski
   2012 § "monthly scheduled grants")
4. `INSERT INTO insider_filings ... ON CONFLICT (filing_id) DO
   NOTHING` (idempotent re-runs)
5. Weekly compute then runs the 3 rolling-window queries and writes
   the flag fields into `StockDetail.insider_signal`

### Capacity / cost

- ~3 500 Form 4 filings/day across S&P 500 → ~1.3M rows/year
- Row size ~150 bytes → ~200 MB for 1 full year
- Supabase free tier: 500 MB database + 2 GB egress/month → fits
- Year-3+ archival: move rows older than 5 years to Supabase Storage
  cold tier (or drop — backfillable from EDGAR)

### Reserved-slot wiring

The 4.5e weights are already declared in
`compute/scoring/manipulation_index.py`:

- `INSIDER_SELL_CLUSTER_WEIGHT_RESERVED = 10.0`
- `C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED = 5.0`

Once the Supabase table exists + queries are integrated, uncomment
the two `FLAG_WEIGHTS` lines and the integration goes live in
the `manipulation_index` rollup with no code-path change elsewhere.
