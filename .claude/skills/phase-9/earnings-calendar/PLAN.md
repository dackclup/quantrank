# Earnings Calendar (Phase 9 planning stub)

**Status**: Planning. P0 retail-feature gap surfaced in 2026-05-15 audit.
Every comparable tool (Bloomberg / Yahoo Finance / Public.com / Robinhood)
shows "next earnings date" prominently. Adds urgency + planning value.

## Purpose

"When does NVDA report next?" — common retail question. Stocks
approaching earnings have different risk profiles (Earnings
Announcement Premium, Frazzini-Lamont 2007). Surfacing next earnings
date + consensus estimate + last-quarter timing = beginner-friendly
context.

## Free data source

Two sources:
1. **yfinance**: `Ticker.calendar` returns `Earnings Date` + `Earnings
   Estimate` (when available)
2. **SEC EDGAR**: 8-K filings tagged with Item 2.02 (Results of
   Operations) — historical earnings announcement dates

## Signal features (additive schema)

| Field | Type | Description |
|---|---|---|
| `next_earnings_date` | string \| None | ISO date of next expected report |
| `days_until_earnings` | int \| None | Derived; computed at compute time |
| `next_eps_estimate` | float \| None | Analyst consensus EPS |
| `next_revenue_estimate` | float \| None | Analyst consensus revenue |
| `pre_earnings_window` | bool | True if `days_until_earnings ≤ 14` |
| `historical_announcement_pattern` | list[{quarter, date, time}] | Last 8 quarters timing |

## UI display

### Beginner-friendly chip on detail page
Surface when meaningful:

| Pattern | Pill | Tooltip |
|---|---|---|
| `pre_earnings_window` (≤14 days) | 🟡 "Earnings in N days" amber-50 | "Reports Wednesday after close — volatility likely" |
| Reports today / tomorrow | 🟠 "Earnings imminent" orange-50 | More urgent banner |
| (more than 14 days out) | — no chip | |

### Detail-page "Earnings Snapshot" card
- Next earnings date + countdown
- Consensus EPS estimate (analyst average)
- Consensus revenue estimate
- Historical timing pattern ("Reports Q3 earnings typically end of October")
- Link to last 4 earnings call audio (Phase 6 — once Whisper transcribe ships)

### Watchlist integration
Watchlist drawer sorts stocks by `days_until_earnings` ascending —
shows nearest earnings first. Beginner can plan "I'll check NVDA next
week" without manual tracking.

## Architecture

```
compute/ingest/earnings_calendar.py     # yfinance calendar + 8-K dates
compute/output/schemas.py               # 5 additive fields
frontend/components/EarningsBadge.tsx
frontend/components/EarningsCard.tsx
frontend/components/WatchlistDrawer.tsx # sort by earnings-days
```

## Effort

| Step | LOC | Days |
|---|---|---|
| yfinance calendar ingest + cache | ~100 | 1 |
| 8-K historical pattern extraction | ~120 | 1 |
| Schema additions (5 fields) + writer | ~50 | 0.5 |
| `EarningsBadge.tsx` + `EarningsCard.tsx` | ~250 | 2 |
| Watchlist sort integration | ~50 | 0.5 |
| Tests + fixtures | ~150 | 1 |
| **Total** | **~720 LOC** | **~6 days** |

## Decisions (locked 2026-05-15)

1. ~~yfinance vs SEC vs paid feed?~~ → **yfinance primary + SEC 8-K
   historical fallback**; no paid feeds
2. ~~"Pre-earnings window" threshold?~~ → **14 days** (Frazzini-Lamont
   2007 announcement-premium window)
3. ~~Show estimate accuracy history?~~ → **NO** — separate
   `phase-9/earnings-surprise-history/PLAN.md` covers it
4. ~~Post-earnings drift surface?~~ → **NO** — same separate stub
5. ~~How many historical patterns to show?~~ → **last 8 quarters** (2y)
   for retail planning

## Dependencies

- Phase 4a workflow cache — `compute/cache/earnings_calendar/`
- Phase 9 §4 `earnings-surprise-history/PLAN.md` — shares underlying
  yfinance feed; coordinate to avoid double-fetch
- Phase 6 `whisper-transcribe/PLAN.md` — once shipped, link to call
  transcripts from this card
- Phase 10 §2 `watchlist-localstorage/PLAN.md` — sort by earnings days

## Out of scope

- Pre/post-market earnings reactions
- Earnings call live transcription (Phase 6)
- Earnings-revision prediction (Phase 5+ ML)
- Tax-quarterly cadence (corporate vs retail timing differs)
