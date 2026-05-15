# Dividend Coverage (Phase 9 planning stub)

**Status**: Planning. P0 retail-feature gap surfaced in 2026-05-15 audit
(after Phase 9-11 first roadmap pass). Income investors are 30-40% of
the retail audience and every comparable tool (Simply Wall St / Yahoo
Finance / Morningstar / Jitta) surfaces dividend data first-class.

## Purpose

Add per-stock dividend metrics: current yield, 5-year dividend growth
rate, payout ratio, ex-dividend date, dividend history chart. Critical
for income-focused retail investors who currently can't use QuantRank.

## Free data source

`yfinance.Ticker(ticker).dividends` + `Ticker.info` — fully free, same
data feed already in production for prices.

## Signal features (additive schema)

| Field | Type | Source |
|---|---|---|
| `dividend_yield_pct` | float \| None | yfinance `info["dividendYield"]` × 100 |
| `dividend_per_share_ttm` | float \| None | sum of last 4 dividend payments |
| `dividend_growth_5y_pct` | float \| None | (last_year / 5y_ago) ^ (1/5) - 1 |
| `payout_ratio_pct` | float \| None | TTM dividend / TTM EPS × 100 |
| `next_ex_date` | string \| None | yfinance `info["exDividendDate"]` |
| `dividend_history` | list[{date, amount}] | yfinance `dividends` series (last 5y) |
| `is_dividend_aristocrat` | bool | True if 25+ consecutive years of growth |

## UI display

### Beginner-friendly chip
Per-stock badge surfacing high-quality dividend status:

| Pattern | Pill | Tooltip |
|---|---|---|
| `dividend_yield_pct ≥ 4%` + payout < 80% | 🟢 "High yield" emerald-50 | "4%+ yield, payout sustainable" |
| `dividend_growth_5y_pct ≥ 10%` | 🟢 "Dividend grower" emerald-50 | "Dividends grew 10%+/year for 5y" |
| `is_dividend_aristocrat` | 🟢 "Aristocrat" emerald-50 ring-emerald-400 | "25+ years of consecutive dividend growth" |
| `dividend_yield_pct = 0` or `None` | — no chip | (non-payers) |
| `payout_ratio_pct > 100` | 🟡 "Payout risk" amber-50 | "Paying more than earnings — unsustainable" |

### Detail-page dividend card
New section between fair-price card and price chart:
- Yield + payout ratio + 5y growth (3 KPIs)
- Ex-date countdown ("Next ex-date: 12 days")
- Sparkline of 5-year dividend history

## Architecture

```
compute/ingest/dividends.py        # yfinance dividends + info["exDividendDate"]
compute/scoring/dividend.py        # quality classifier (aristocrat / grower / risky)
compute/output/schemas.py          # add dividend_yield_pct, etc. (additive)
frontend/components/DividendCard.tsx
frontend/components/DividendBadge.tsx
```

## Effort

| Step | LOC | Days |
|---|---|---|
| `dividends.py` ingest + cache | ~120 | 1 |
| Aristocrat / grower classifier + tests | ~150 | 1.5 |
| Schema additions (7 fields) + writer | ~80 | 0.5 |
| `DividendCard.tsx` + `DividendBadge.tsx` | ~250 | 2 |
| Detail-page integration | ~80 | 0.5 |
| Sparkline chart (Recharts) | ~120 | 1 |
| Tests + golden fixtures | ~180 | 1.5 |
| **Total** | **~980 LOC** | **~8 days** |

## Decisions (locked 2026-05-15)

1. ~~yfinance vs SEC primary?~~ → **yfinance primary** (cleanest API);
   SEC fallback for missing data via Form 10-K dividend disclosure
2. ~~How far back?~~ → **5 years** of dividend history (SOTA per
   Damodaran 2024)
3. ~~Show non-dividend payers' "no yield"?~~ → **NO chip** (avoid noise
   on growth-only stocks like NVDA)
4. ~~Aristocrat threshold?~~ → **25 years** (S&P standard definition)
5. ~~Payout risk threshold?~~ → **>100%** = unsustainable (per
   Markowitz 1952 capital structure framework)

## Dependencies

- Phase 4a workflow cache — add `compute/cache/dividends/` to workflow
  cache path
- Phase 5 backtest — Cohen-Pomorski 2007 (JF) found dividend-yield +
  payout-quality predicts return; validate IC

## Out of scope

- Special dividends (one-time vs regular) — flag in payment history but
  don't include in yield calc
- Tax considerations (qualified vs non-qualified) — out of educational
  scope
- Dividend reinvestment (DRIP) simulator — Phase 11+
- Stock buyback as quasi-dividend — separate stub (`shareholder-yield/`)

## References

- Damodaran 2024 — "Dividends and Stock Buybacks: A Tax-Adjusted Look"
- Cohen-Pomorski 2007 (JF) — Dividend predictability
- S&P Dow Jones Indices — Dividend Aristocrats methodology
