# Exchange Pill (Phase 4 planning stub)

**Status**: Planning. User request 2026-05-14 — add an exchange-of-listing
pill (`NASDAQ` / `NYSE` / `NYSE American`) **immediately before** the
existing Sector pill on both the overview ranking table and the per-stock
detail page, plus a filter chip in the existing filter panel. Joins the
Phase 4 UX trio (recommendation-badge / loss-chance / price-chart-
enhancements) as the **fourth UX feature** queued for v1.1.

Companion stub to:
- [`recommendation-badge/PLAN.md`](../recommendation-badge/PLAN.md)
- [`loss-chance/PLAN.md`](../loss-chance/PLAN.md)
- [`price-chart-enhancements/PLAN.md`](../price-chart-enhancements/PLAN.md)

## Spec (user request, 2026-05-14)

### Display location

1. **Overview / Ranking table** (`frontend/components/RankingTable.tsx`):
   - Place the exchange pill **immediately to the left** of the existing
     Sector pill — same row, smaller-weight visual
   - Example for NVDA: `[NASDAQ] [Information Technology]`
   - Example for CF (S&P-500 #1 at v1.0.3): `[NYSE] [Materials]`

2. **Stock detail page** (`frontend/app/stock/[ticker]/page.tsx`):
   - Same `[Exchange] [Sector] · Sub-industry` layout in the header row
   - Example: `[NASDAQ] [Information Technology] · Semiconductors`

### Filter

Add to the existing filter panel (`frontend/components/FilterBar.tsx`):

- Multi-select chips: `[NYSE] [NASDAQ] [NYSE American] [Cboe]`
- Default = all selected (show everything)
- URL param: `?exchange=NASDAQ,NYSE`
- Persists across page reloads via URL

## Data source

The Wikipedia S&P 500 page does **not** carry an exchange-of-listing
column. Three candidate sources:

| Source | Coverage | Cost | Notes |
|---|---|---|---|
| **`yfinance.Ticker.info["exchange"]`** | 100% S&P 500 | Free | Already-cached as part of PR 4b §1 cross-source validator (`compute/cache/yfinance_info/<ticker>.json`). yfinance returns codes like `"NMS"` (NASDAQ Global Select), `"NYQ"` (NYSE), `"ASE"` (NYSE American) which need mapping to display labels |
| SEC EDGAR submissions JSON `.exchanges[]` | 100% | Free | Authoritative; under `/submissions/CIK<...>.json`. Already inside the EDGAR fetch surface of `compute/ingest/fundamentals.py`. Adds one field per ticker to extract. Display values match SEC convention (e.g., `"NASDAQ"`, `"NYSE"`) — no mapping needed |
| Static hard-coded map | 100% | Free, brittle | Fragile vs. M&A / delisting / Phase 8 universe expansion |

**Decision (locked 2026-05-14)**: **SEC EDGAR submissions JSON** primary,
yfinance `.info["exchange"]` as fallback.

Rationale:
- SEC is authoritative — display values are clean (`"NASDAQ"` not `"NMS"`)
- yfinance fallback covers any ticker where the EDGAR `.exchanges[]`
  field is empty / missing (rare but documented in audit #6 — DEI tags
  occasionally lag)
- Avoids a 502-stock yfinance `.info` polling pass solely for this
  feature — reuses the already-cached value if present

## Source mapping

SEC EDGAR `.exchanges[]` values seen in S&P 500 (2026-05-14):

| EDGAR value | Display label | Pill color (Tailwind) |
|---|---|---|
| `"Nasdaq"` | **NASDAQ** | `bg-blue-700 text-white` (NASDAQ blue, soft-palette) |
| `"NYSE"` | **NYSE** | `bg-indigo-700 text-white` (NYSE navy, soft) |
| `"NYSEArca"` | **NYSE Arca** | `bg-indigo-400 text-indigo-900` (lighter, distinguished from main NYSE) |
| `"NYSEAMER"` | **NYSE American** | `bg-cyan-700 text-white` (less common; tertiary) |
| `"CboeBZX"` / `"CBOE"` | **Cboe** | `bg-slate-700 text-white` (rare; neutral) |
| (empty / unknown) | omit pill | n/a |

yfinance `.info["exchange"]` fallback mapping:

| yfinance code | Display label |
|---|---|
| `"NMS"` | NASDAQ |
| `"NGM"` | NASDAQ |
| `"NCM"` | NASDAQ |
| `"NYQ"` | NYSE |
| `"PCX"` | NYSE Arca |
| `"ASE"` | NYSE American |
| `"BTS"` | Cboe |

Both mappings live in `compute/ingest/exchange.py` as flat dicts so
contributors can extend without touching ingest logic.

## Architecture changes

| Layer | Change |
|---|---|
| `compute/ingest/exchange.py` (new) | `fetch_exchange(ticker, cik)` — try SEC submissions `.exchanges[0]` first, fall back to `yfinance_info[ticker].exchange`, return display label via the mapping dicts. Returns `None` when both miss |
| `compute/ingest/fundamentals.py` | No change — exchange is parsed from the existing submissions JSON in `_load_submissions_json` (already fetched per ticker for the filings index); the new module just reads the same blob |
| `compute/output/schemas.py` | Add `exchange: str \| None = None` to both `StockSummary` and `StockDetail` |
| `compute/main.py` | Call `fetch_exchange()` in the per-ticker loop after `fetch_fundamentals` (cik is already known); populate `StockSummary.exchange` + `StockDetail.exchange` |
| `frontend/lib/types.ts` | Mirror `exchange: string \| null` field |
| `frontend/lib/schema-snapshot.json` | Regenerate via `schema_check --update-snapshot` |
| `frontend/components/ExchangePill.tsx` (new) | Reusable pill component — accepts `exchange: Exchange`, renders `<span>` with mapped Tailwind classes. Returns `null` when exchange is `null` (no pill rendered) |
| `frontend/components/RankingTable.tsx` | Insert `<ExchangePill />` **before** the existing Sector pill |
| `frontend/app/stock/[ticker]/page.tsx` | Insert `<ExchangePill size="md" />` before Sector in the header row |
| `frontend/components/FilterBar.tsx` | Add 4-chip multi-select control (NYSE / NASDAQ / NYSE American / Cboe) with URL param sync |
| `frontend/app/page.tsx` filter state | Add `exchange` query param parsing + apply filter to rankings array before rendering |

LOC estimate: ~260 LOC across 9 files.

## Schema impact

Additive (per [`v1-to-v1-1-migration/PLAN.md`](../v1-to-v1-1-migration/PLAN.md) policy):

```python
class StockSummary(BaseModel):
    ...
    exchange: str | None = None  # PR 4N — exchange of listing

class StockDetail(BaseModel):
    ...
    exchange: str | None = None
```

Schema bump: `1.1.0-rcN` (joins the PR 4d / 4e / 4f UX trio in the
`v1.1.0-rc1..8` series before final `v1.1.0-phase4` tag).

## Cache impact

Zero new cache directories. Exchange data comes from:
1. SEC EDGAR submissions JSON — already cached as part of the EDGAR
   per-ticker fetch in `compute/ingest/fundamentals.py`
2. `compute/cache/yfinance_info/<ticker>.json` — already populated by
   PR 4b §1 cross-source validator

No `cache-v5` bump required when this lands (the new module reads from
existing cache surfaces).

## Test plan

- [ ] Unit test `fetch_exchange()` with mock submissions JSON:
  - `.exchanges = ["Nasdaq"]` → returns `"NASDAQ"`
  - `.exchanges = ["NYSE"]` → returns `"NYSE"`
  - `.exchanges = []` → falls through to yfinance fallback
  - both sources empty → returns `None`
- [ ] Unit test mapping dicts cover all observed EDGAR/yfinance values
  in current S&P 500
- [ ] Integration test: build `StockSummary` for NVDA → `exchange = "NASDAQ"`;
  for CF → `exchange = "NYSE"`
- [ ] Snapshot regen — `schema_check` passes
- [ ] TypeScript: `exchange: string | null` type narrowed correctly in
  `ExchangePill` component
- [ ] Frontend visual: pill renders in both light + dark mode; sits
  immediately before Sector pill with consistent spacing
- [ ] Filter: URL param round-trips; default = all selected; filter
  state correctly intersects with existing Sector filter (AND logic)
- [ ] Mobile: pills wrap cleanly on narrow viewports

## Visual spec

```tsx
// ExchangePill component (proposal — mirrors SectorPill's structure)
type Exchange = "NASDAQ" | "NYSE" | "NYSE Arca" | "NYSE American" | "Cboe";

const TONES: Record<Exchange, string> = {
  "NASDAQ":        "bg-blue-700 text-white dark:bg-blue-300 dark:text-blue-900",
  "NYSE":          "bg-indigo-700 text-white dark:bg-indigo-300 dark:text-indigo-900",
  "NYSE Arca":     "bg-indigo-400 text-indigo-900 dark:bg-indigo-700 dark:text-indigo-100",
  "NYSE American": "bg-cyan-700 text-white dark:bg-cyan-300 dark:text-cyan-900",
  "Cboe":          "bg-slate-700 text-white dark:bg-slate-300 dark:text-slate-900",
};

export function ExchangePill({ exchange }: { exchange: string | null }) {
  if (!exchange || !(exchange in TONES)) return null;
  const tone = TONES[exchange as Exchange];
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${tone}`}>
      {exchange}
    </span>
  );
}
```

Soft-palette rule preserved (matches recommendation-badge / loss-chance):
- `bg-blue-700` (NASDAQ) not pure `bg-blue-600`
- `bg-indigo-700` (NYSE) not pure navy `bg-blue-900`
- Light + dark mode variants per Tailwind dark: prefix

## Effort estimate

| Step | LOC | Time |
|---|---|---|
| 1. `compute/ingest/exchange.py` + mapping dicts | ~80 | 2-3 hr |
| 2. Schema additive (`StockSummary.exchange` + `StockDetail.exchange`) + `main.py` wire-up | ~30 | 1 hr |
| 3. Unit tests for ingest (mock submissions JSON + yfinance fallback) | ~80 | 2-3 hr |
| 4. `ExchangePill.tsx` component + 2 placement sites | ~50 | 2 hr |
| 5. Filter UI + URL param sync | ~40 | 2 hr |
| 6. Schema snapshot regen + verification ladder | ~10 | 1 hr |
| **Total** | **~290 LOC** | **~10-12 hr** |

Fits as one focused PR (`feat(ui): exchange pill with filter`).

## When to ship

After the locked Phase 4 UX trio (PR 4d / 4e / 4f) per
[`v1-to-v1-1-migration/PLAN.md`](../v1-to-v1-1-migration/PLAN.md)
sequencing. Suggested slot: **PR 4e.5** or **PR 4g.5** depending on
review load — same schema-additive minor bump as the trio, no new infra
dependency.

Independent of price-chart-enhancements (4f) — can ship in any order
relative to it. Soft-dependency on recommendation-badge (4d) only for
the filter-bar UX pattern reuse (same multi-select chip control).

## Decisions (locked 2026-05-14)

1. ~~Data source: yfinance vs SEC vs hard-coded?~~ → **SEC primary +
   yfinance fallback** (per `Data source` table above)
2. ~~Pill placement: before or after Sector?~~ → **Before** (per user
   request: "อยู่ด้านหน้าของ pill Sectors")
3. ~~Filter UI: standalone toggle or grouped with Sector filter?~~ →
   **Standalone multi-select chips** (matches recommendation-badge
   filter pattern; AND-intersection with Sector filter)
4. ~~URL param key?~~ → **`?exchange=`** (consistent with
   `?rec=` / `?sector=` plural-noun convention)
5. ~~Tailwind palette?~~ → **Soft-palette: blue family** (NASDAQ blue,
   NYSE indigo, NYSE Arca lighter indigo, NYSE American cyan, Cboe
   slate). Mirrors recommendation-badge soft-palette rule

## Out of scope

- **International exchanges** — Phase 8 universe expansion (`universe-
  expand-sp1500/PLAN.md`); current S&P 500 is US-only so all values fall
  into the 4-5 US exchanges
- **Historical exchange changes** — e.g., a stock that moved from NYSE
  American → NYSE. Current snapshot only; no historical track
- **Compound listings** — ADRs / dual-listed securities. SEC primary
  source returns the SEC-of-record exchange, which is correct for the
  ranking layer

## References

- SEC EDGAR submissions JSON schema (`https://data.sec.gov/submissions/
  CIK<...>.json` — `.exchanges[]` field documented in EDGAR API docs)
- yfinance `.info["exchange"]` code mapping — Yahoo Finance source codes
  (NYQ, NMS, NGM, NCM, ASE, PCX, BTS, etc.)
- README "Honest Limitations" — note yfinance scraper drift caveat;
  exchange code is more stable than `marketCap` (which is the cross-
  source validator target) — exchange codes rarely change post-listing
