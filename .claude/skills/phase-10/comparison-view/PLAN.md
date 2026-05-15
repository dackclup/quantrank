# Stock Comparison View (Phase 10 planning stub)

**Status**: Planning. Lets user compare 2-3 stocks side-by-side on
all metrics. Direct response to "should I buy NVDA or AMD?" use case.
Differentiates from Jitta (which doesn't have this).

## Purpose

Single most-requested retail feature for stock screeners. Use cases:
- "NVDA vs AMD vs INTC — which is the best semi play?"
- "Compare KO with PEP" (rival in same sector)
- "ETF check — VOO vs VTI" (when Phase 8 adds ETFs)

Currently user has to open 2-3 tabs and eyeball compare. Comparison
view = one screen with all metrics aligned.

## Architecture

```
frontend/app/compare/[tickers]/page.tsx   # /compare/NVDA-AMD-INTC route
frontend/components/ComparisonTable.tsx   # main grid
frontend/components/ComparisonPicker.tsx  # add/remove ticker
frontend/components/ComparisonPillarChart.tsx  # overlay radar
frontend/lib/comparison-storage.ts        # last-compared persist
```

URL shape: `/compare/NVDA-AMD-INTC/` — sharable + bookmarkable.
2-3 tickers (4+ becomes unreadable on mobile). Add picker UX
lets user replace one.

## Comparison metrics (aligned rows)

| Section | Metrics shown side-by-side |
|---|---|
| **Identity** | Ticker, name, sector, sub-industry |
| **Headline** | Composite score, recommendation, loss chance % |
| **Valuation** | Current price, fair price (median), max fair, MoS % |
| **Pillars** (radar overlay) | quality, value, growth, momentum, health, profitability, technical, risk |
| **Raw metrics** | Revenue (TTM), Net income, P/E, P/B, EV/EBITDA, market cap |
| **Defense flags** | Altman, Sloan, NSI, Beneish, Dechow, data quality |
| **Annotations** | recommendation badge, loss chance, insider buy (Phase 9), institutional flow (Phase 9), earnings beats (Phase 9) |
| **Price chart** | Overlaid 1Y prices, normalized to 100 at start |

## Visual spec

```
┌────────────────┬──────────┬──────────┬──────────┐
│                │  NVDA    │  AMD     │  INTC    │
├────────────────┼──────────┼──────────┼──────────┤
│ Sector         │ IT       │ IT       │ IT       │
│ Composite      │ 70.7  🟢 │ 65.3  🟢 │ 41.2  🟠 │
│ Recommendation │ Sell  🔴 │ Hold  ⚪ │ Hold  ⚪ │
│ Loss Chance    │ 57%   🟡 │ 49%   🟡 │ 53%   🟡 │
│ MoS            │ -271%    │ -45%     │ -28%     │
│ ... (rows)
├────────────────┴──────────┴──────────┴──────────┘
│  [Pillar radar overlay — 3 colored polygons]    │
├─────────────────────────────────────────────────┤
│  [Price chart 1Y normalized — 3 lines]          │
└─────────────────────────────────────────────────┘
```

## Effort

| Step | LOC | Days |
|---|---|---|
| Route + URL parsing | ~80 | 1 |
| `ComparisonTable.tsx` aligned grid | ~400 | 3 |
| `ComparisonPicker.tsx` ticker swap UI | ~200 | 1.5 |
| `ComparisonPillarChart.tsx` overlay radar | ~250 | 2 |
| Overlay normalized price chart | ~180 | 1.5 |
| `comparison-storage.ts` last-N persisted | ~80 | 0.5 |
| "Compare" CTA on detail page | ~50 | 0.5 |
| URL sharing (copy link) | ~50 | 0.5 |
| Tests | ~200 | 1.5 |
| **Total** | **~1490 LOC** | **~12 days** |

## Decisions (locked)

1. ~~Max comparisons?~~ → **3 stocks** (4+ unreadable on mobile)
2. ~~Static export vs SSR?~~ → **Static export** — pre-render top-100
   pair combinations (CF-HST, NVDA-AMD, etc.); user-picked combos
   handled client-side
3. ~~URL shape?~~ → **`/compare/NVDA-AMD-INTC/`** (kebab-joined,
   alphabet-ordered for consistent caching)
4. ~~Allow comparing stocks from different sectors?~~ → **YES** —
   tech vs financial is a valid comparison even if pillar weights
   differ

## Pre-render strategy

For static export, we can't dynamically generate every combination
(50K+ pairs). Strategy:
- Pre-render top-50 most-likely combinations (siblings in sector, 
  popular pairs like NVDA-AMD)
- Other combinations rendered client-side from already-loaded JSON
  (no extra fetch needed)

## Dependencies

- Phase 4d recommendation-badge (done) — for the recommendation column
- Phase 4e loss-chance (done) — for the loss chance column
- Phase 9 alt-data signals — for new columns (insider, 13F, earnings
  surprise)

## Out of scope

- Multi-currency comparison (Phase 8+ global universe)
- Time-aligned cross-asset comparison (e.g., stock vs bond yield)
- Historical comparison (how did NVDA-AMD compare 1 year ago?)
- Save comparison as URL share to social media
