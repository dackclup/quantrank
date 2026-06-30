/**
 * Contract tests for the bandSectors sector-resolution logic in HoldingsTimeline.
 *
 * These tests verify the three resolution paths:
 *   1. bandSectors present → held band-carried names (HP/UAL) resolve sector
 *   2. bandSectors absent  → falls back to holdings-derived sectorByTicker (no regression)
 *   3. SOLD row resolution → prevBandSectors (prior quarter) is the primary source
 *
 * The tests operate on the pure data-model logic (the merge + fallback rules),
 * NOT on the React component tree — consistent with the project's pure-function
 * contract-test pattern (see portfolio-format.test.ts). DOM is not needed.
 *
 * Run: cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import type { AiPickTimelineEntry, AiPickTimelineHolding, MwrPositionReturn } from '@/lib/types';

// ---------------------------------------------------------------------------
// Helpers that mirror the QuarterDrawer resolution logic exactly —
// these are the pure functions being contracted (extracted here so tests
// stay independent of the React rendering layer).
// ---------------------------------------------------------------------------

/**
 * Build the effective sector map for HELD rows in a QuarterDrawer.
 * Mirrors: { ...sectorByTicker, ...(entry.bandSectors ?? {}) }
 */
function buildResolvedSectorByTicker(
  sectorByTicker: Record<string, string>,
  bandSectors: Record<string, string> | undefined,
): Record<string, string> {
  return {
    ...sectorByTicker,
    ...(bandSectors ?? {}),
  };
}

/**
 * Build the sector string for a SOLD row in a QuarterDrawer.
 * Mirrors: prevBandSectors?.[ticker] ?? resolvedSectorByTicker[ticker] ?? ''
 */
function resolveSoldSector(
  ticker: string,
  prevBandSectors: Record<string, string> | undefined,
  resolvedSectorByTicker: Record<string, string>,
): string {
  return prevBandSectors?.[ticker] ?? resolvedSectorByTicker[ticker] ?? '';
}

/**
 * Build the holdings-derived sectorByTicker fallback from an entry's holdings.
 * Mirrors: for (const h of entry.holdings) sectorByTicker[h.ticker] = h.sector;
 */
function buildHoldingsSectorByTicker(holdings: AiPickTimelineHolding[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const h of holdings) map[h.ticker] = h.sector;
  return map;
}

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeEntry(opts: {
  holdings: AiPickTimelineHolding[];
  bandSectors?: Record<string, string>;
}): AiPickTimelineEntry {
  return {
    date: '2024-09-30',
    holdings: opts.holdings,
    ...(opts.bandSectors !== undefined ? { bandSectors: opts.bandSectors } : {}),
  };
}

// ---------------------------------------------------------------------------
// 1. Held rows: bandSectors present — band-carried names resolve their sector
// ---------------------------------------------------------------------------

describe('bandSectors → held-row sector resolution', () => {
  it('resolves sector for a band-carried name absent from holdings', () => {
    // HP and UAL are in the band_book but NOT in holdings (they fell below
    // the composite_min slice). Their sectors live only on bandSectors.
    const entry = makeEntry({
      holdings: [
        { ticker: 'AAPL', sector: 'Information Technology' },
        { ticker: 'MSFT', sector: 'Information Technology' },
      ],
      bandSectors: {
        AAPL: 'Information Technology',
        MSFT: 'Information Technology',
        HP: 'Energy',
        UAL: 'Industrials',
      },
    });

    const sectorByTicker = buildHoldingsSectorByTicker(entry.holdings);
    const resolved = buildResolvedSectorByTicker(sectorByTicker, entry.bandSectors);

    expect(resolved['HP']).toBe('Energy');
    expect(resolved['UAL']).toBe('Industrials');
  });

  it('bandSectors overrides holdings when they disagree (PIT sector wins)', () => {
    // PIT sector may differ from today's sector for a ticker that changed
    // GICS classification between rebalances.
    const entry = makeEntry({
      holdings: [{ ticker: 'INTC', sector: 'Information Technology' }],
      bandSectors: { INTC: 'Semiconductors' },
    });

    const sectorByTicker = buildHoldingsSectorByTicker(entry.holdings);
    const resolved = buildResolvedSectorByTicker(sectorByTicker, entry.bandSectors);

    // bandSectors (primary) wins over holdings-derived (fallback)
    expect(resolved['INTC']).toBe('Semiconductors');
  });

  it('resolves normally for a ticker present in both holdings and bandSectors', () => {
    const entry = makeEntry({
      holdings: [{ ticker: 'NVDA', sector: 'Information Technology' }],
      bandSectors: { NVDA: 'Information Technology' },
    });

    const sectorByTicker = buildHoldingsSectorByTicker(entry.holdings);
    const resolved = buildResolvedSectorByTicker(sectorByTicker, entry.bandSectors);

    expect(resolved['NVDA']).toBe('Information Technology');
  });
});

// ---------------------------------------------------------------------------
// 2. Graceful fallback: bandSectors absent — holdings-derived map is sole source
// ---------------------------------------------------------------------------

describe('bandSectors absent → graceful fallback (no regression)', () => {
  it('returns the holdings-derived sector when bandSectors is undefined', () => {
    const entry = makeEntry({
      holdings: [
        { ticker: 'AAPL', sector: 'Information Technology' },
        { ticker: 'JPM', sector: 'Financials' },
      ],
      // No bandSectors — pre-regen artifact
    });

    const sectorByTicker = buildHoldingsSectorByTicker(entry.holdings);
    const resolved = buildResolvedSectorByTicker(sectorByTicker, entry.bandSectors);

    expect(resolved['AAPL']).toBe('Information Technology');
    expect(resolved['JPM']).toBe('Financials');
  });

  it('returns empty string for a ticker absent from both map and holdings when bandSectors absent', () => {
    const entry = makeEntry({ holdings: [] });
    const sectorByTicker = buildHoldingsSectorByTicker(entry.holdings);
    const resolved = buildResolvedSectorByTicker(sectorByTicker, entry.bandSectors);

    expect(resolved['UNKNOWN'] ?? '').toBe('');
  });
});

// ---------------------------------------------------------------------------
// 3. Sold rows: prevBandSectors (prior quarter) is the primary sector source
// ---------------------------------------------------------------------------

describe('SOLD row sector resolution via prevBandSectors', () => {
  it('resolves sold ticker sector from prior quarter bandSectors', () => {
    // RIG and WU were in LAST quarter's band_book; they sold this quarter.
    // Their sector appears on the PRIOR entry's bandSectors.
    const prevBandSectors: Record<string, string> = {
      RIG: 'Energy',
      WU: 'Financials',
      AAPL: 'Information Technology',
    };

    // Current quarter's resolved map doesn't include the sold tickers
    const currentResolved: Record<string, string> = {
      AAPL: 'Information Technology',
      MSFT: 'Information Technology',
    };

    expect(resolveSoldSector('RIG', prevBandSectors, currentResolved)).toBe('Energy');
    expect(resolveSoldSector('WU', prevBandSectors, currentResolved)).toBe('Financials');
  });

  it('falls back to current resolvedSectorByTicker when prevBandSectors is undefined', () => {
    // Pre-regen artifact: prevBandSectors absent. The sold ticker may still
    // resolve via the current holdings-based map (e.g. if it appears in holdings).
    const currentResolved: Record<string, string> = {
      RIG: 'Energy',
    };

    expect(resolveSoldSector('RIG', undefined, currentResolved)).toBe('Energy');
  });

  it('falls back to empty string when both sources lack the sold ticker', () => {
    // Genuinely unknown — no sector data available anywhere.
    const currentResolved: Record<string, string> = {};

    expect(resolveSoldSector('UNKNOWN', undefined, currentResolved)).toBe('');
  });

  it('prevBandSectors takes precedence over currentResolved for the same ticker', () => {
    // Sector classification changed between quarters — prior (PIT) value wins.
    const prevBandSectors: Record<string, string> = { TSLA: 'Consumer Discretionary' };
    const currentResolved: Record<string, string> = { TSLA: 'Information Technology' };

    // For the sold row the PIT sector from last quarter is more accurate
    expect(resolveSoldSector('TSLA', prevBandSectors, currentResolved)).toBe('Consumer Discretionary');
  });
});

// ---------------------------------------------------------------------------
// 4. AiPickTimelineEntry type — bandSectors is optional (no regression on legacy entries)
// ---------------------------------------------------------------------------

describe('AiPickTimelineEntry.bandSectors type contract', () => {
  it('entry without bandSectors is valid (field is optional)', () => {
    const entry: AiPickTimelineEntry = {
      date: '2024-06-30',
      holdings: [{ ticker: 'AAPL', sector: 'Information Technology' }],
    };
    // bandSectors is absent — TypeScript must not require it
    expect(entry.bandSectors).toBeUndefined();
  });

  it('entry with bandSectors carries the correct shape', () => {
    const entry: AiPickTimelineEntry = {
      date: '2024-09-30',
      holdings: [],
      bandSectors: { HP: 'Energy', UAL: 'Industrials' },
    };
    expect(entry.bandSectors?.['HP']).toBe('Energy');
    expect(entry.bandSectors?.['UAL']).toBe('Industrials');
  });

  it('bandSectors with an empty map is valid and resolves to empty string for any ticker', () => {
    const entry = makeEntry({ holdings: [], bandSectors: {} });
    const sectorByTicker = buildHoldingsSectorByTicker(entry.holdings);
    const resolved = buildResolvedSectorByTicker(sectorByTicker, entry.bandSectors);
    expect(resolved['HP'] ?? '').toBe('');
  });
});

// ---------------------------------------------------------------------------
// 5. mwrForSoldTicker precedence — AiPickPortfolio Current-picks sold rows
//
// Contracts the resolution order in mwrForSoldTicker():
//   priorMwrByTicker?.[ticker]  (realized-exit, canonical)  FIRST
//   data.mwrByTicker[ticker]    (top-level flat map)         FALLBACK
//
// This mirrors HoldingsTimeline QuarterDrawer's sold-row lookup:
//   prevMwrByTicker?.[ticker] ?? mwrByTicker?.[ticker] ?? null
//
// The inversion from the original flat-map-first order is the BUGFIX that
// makes both tables show the same realized-exit MWR for sold tickers.
//
// Ground truth example (KLAC, May-2026 rebalance):
//   top-level flat map  → mwr_pct=578.37, legs_used=22  (WRONG — one leg short)
//   prior-quarter map   → mwr_pct=711.69, legs_used=23  (CORRECT — through exit)
// ---------------------------------------------------------------------------

/**
 * Pure implementation of mwrForSoldTicker() extracted from AiPickPortfolio.tsx.
 * Mirrors the component function exactly so the test contracts the same logic.
 */
function mwrForSoldTicker(
  ticker: string,
  flatMwrByTicker: Record<string, MwrPositionReturn>,
  priorMwrByTicker: Record<string, MwrPositionReturn> | undefined,
): MwrPositionReturn | null {
  return priorMwrByTicker?.[ticker] ?? flatMwrByTicker[ticker] ?? null;
}

/**
 * Pure implementation of mwrForTicker() (HELD rows) — unchanged path.
 * Must NOT look at priorMwrByTicker.
 */
function mwrForTicker(
  ticker: string,
  flatMwrByTicker: Record<string, MwrPositionReturn>,
): MwrPositionReturn | null {
  return flatMwrByTicker[ticker] ?? null;
}

function makeMwr(mwr_pct: number, legs_used: number): MwrPositionReturn {
  return {
    mwr_pct,
    twr_pct: null,
    contrib_nav_pts: null,
    since_date: '2020-08-14',
    partial_history: false,
    legs_used,
  };
}

describe('mwrForSoldTicker — sold-row MWR resolution precedence (Current-picks fix)', () => {
  it('returns the prior-quarter value (realized exit) when both maps contain the ticker', () => {
    // KLAC ground-truth scenario: flat map has 22 legs (stale), prior-quarter has 23 (realized).
    const flatMap: Record<string, MwrPositionReturn> = {
      KLAC: makeMwr(578.37, 22),
    };
    const priorMap: Record<string, MwrPositionReturn> = {
      KLAC: makeMwr(711.69, 23),
    };

    const result = mwrForSoldTicker('KLAC', flatMap, priorMap);

    expect(result?.mwr_pct).toBe(711.69);
    expect(result?.legs_used).toBe(23);
  });

  it('Current-picks sold row and HoldingsTimeline sold row now return the SAME mwr_pct', () => {
    // Assert the two resolution functions agree — this is the core contract.
    const flatMap: Record<string, MwrPositionReturn> = {
      KLAC: makeMwr(578.37, 22),
    };
    const priorMap: Record<string, MwrPositionReturn> = {
      KLAC: makeMwr(711.69, 23),
    };

    // Current-picks (mwrForSoldTicker — prior FIRST)
    const currentPicksResult = mwrForSoldTicker('KLAC', flatMap, priorMap);
    // HoldingsTimeline (prevMwrByTicker first, then current mwrByTicker — identical logic)
    const holdingsTimelineResult = priorMap['KLAC'] ?? flatMap['KLAC'] ?? null;

    expect(currentPicksResult?.mwr_pct).toBe(holdingsTimelineResult?.mwr_pct);
    expect(currentPicksResult?.legs_used).toBe(holdingsTimelineResult?.legs_used);
  });

  it('falls back to the flat map when prior-quarter map is undefined (no prior quarter)', () => {
    const flatMap: Record<string, MwrPositionReturn> = {
      AAPL: makeMwr(123.45, 10),
    };

    const result = mwrForSoldTicker('AAPL', flatMap, undefined);

    expect(result?.mwr_pct).toBe(123.45);
  });

  it('falls back to the flat map when prior-quarter map does not contain the ticker', () => {
    const flatMap: Record<string, MwrPositionReturn> = {
      NVDA: makeMwr(999.0, 15),
    };
    const priorMap: Record<string, MwrPositionReturn> = {
      // NVDA absent — only other tickers present
      MSFT: makeMwr(50.0, 8),
    };

    const result = mwrForSoldTicker('NVDA', flatMap, priorMap);

    // Falls back to flat map when prior map lacks the ticker
    expect(result?.mwr_pct).toBe(999.0);
  });

  it('returns null when both maps lack the ticker', () => {
    const flatMap: Record<string, MwrPositionReturn> = {};
    const priorMap: Record<string, MwrPositionReturn> = {};

    const result = mwrForSoldTicker('UNKNOWN', flatMap, priorMap);

    expect(result).toBeNull();
  });

  it('returns null when both maps are empty', () => {
    const result = mwrForSoldTicker('TSLA', {}, undefined);
    expect(result).toBeNull();
  });
});

describe('mwrForTicker — HELD-row MWR resolution (unchanged path)', () => {
  it('resolves from the flat map for held rows (prior-quarter map is NOT consulted)', () => {
    const flatMap: Record<string, MwrPositionReturn> = {
      AAPL: makeMwr(200.0, 12),
    };
    // Even if prior map had a different value, held rows MUST use the flat map.
    const result = mwrForTicker('AAPL', flatMap);
    expect(result?.mwr_pct).toBe(200.0);
  });

  it('returns null for a ticker absent from the flat map', () => {
    const flatMap: Record<string, MwrPositionReturn> = {};
    expect(mwrForTicker('MSFT', flatMap)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 7. Sold-row ORDER consistency — Current-picks must match Rotation-history
//
// Bug (owner-spotted, 2026-06-29): Current-picks sold rows were alphabetically
// sorted (CF then KLAC for May-2026 basket) while Rotation-history used
// prior-basket order (KLAC then CF, matching the "SELL KLAC CF" header).
//
// Root cause: AiPickPortfolio.tsx `soldRows` did
//   `[...priorHeldSet].filter(t => !currentSet.has(t)).sort()`
// which spread a Set (order-lost) then sorted alphabetically. HoldingsTimeline
// used `prev.filter(t => !heldSet.has(t))` where `prev` is the ordered array.
//
// Fix: `soldRows` now derives from `orderedHeldForEntry(priorEntry).filter(...)`
// — the same ordered array HoldingsTimeline uses for `prev`.
//
// These tests contract the pure ordering logic for both derivation paths to
// ensure they produce IDENTICAL results for the same prior-basket data.
// ---------------------------------------------------------------------------

import { orderedHeldForEntry } from './AiPickPortfolio';

/**
 * Mirrors AiPickPortfolio.tsx `soldRows` derivation AFTER the fix:
 *   orderedHeldForEntry(priorEntry).filter(t => !currentSet.has(t))
 */
function deriveSoldTickersCurrentPicks(
  priorEntry: AiPickTimelineEntry,
  currentTickers: string[],
): string[] {
  const currentSet = new Set(currentTickers);
  return orderedHeldForEntry(priorEntry).filter((t) => !currentSet.has(t));
}

/**
 * Mirrors HoldingsTimeline.tsx `exited` derivation:
 *   prev.filter(t => !heldSet.has(t))
 * where `prev` is the prior quarter's `held` (= orderedHeldForEntry result).
 */
function deriveSoldTickersHoldingsTimeline(
  priorEntry: AiPickTimelineEntry,
  currentTickers: string[],
): string[] {
  const heldSet = new Set(currentTickers);
  // HoldingsTimeline computes `prev` as the ordered `held` array from the
  // PREVIOUS iteration — which is exactly orderedHeldForEntry on that entry.
  const prev = orderedHeldForEntry(priorEntry);
  return prev.filter((t) => !heldSet.has(t));
}

describe('sold-row ORDER — Current-picks matches Rotation-history (ordering fix 2026-06-29)', () => {
  it('May-2026 scenario: KLAC before CF in prior basket → sold order is [KLAC, CF], not alphabetical [CF, KLAC]', () => {
    // Prior basket order mirrors the real May-2026 rebalance: KLAC appeared
    // before CF in the band_book / composite-desc holdings.
    const priorEntry: AiPickTimelineEntry = {
      date: '2025-11-30',
      holdings: [
        { ticker: 'NVDA', sector: 'Information Technology' },
        { ticker: 'KLAC', sector: 'Information Technology' },
        { ticker: 'MSFT', sector: 'Information Technology' },
        { ticker: 'CF',   sector: 'Materials' },
        { ticker: 'AAPL', sector: 'Information Technology' },
      ],
    };
    // Current basket retains NVDA, MSFT, AAPL — KLAC and CF were sold.
    const currentTickers = ['NVDA', 'MSFT', 'AAPL', 'JPM'];

    const currentPicksOrder  = deriveSoldTickersCurrentPicks(priorEntry, currentTickers);
    const holdingsTimelineOrder = deriveSoldTickersHoldingsTimeline(priorEntry, currentTickers);

    // Both must produce [KLAC, CF] (prior-basket order), NOT [CF, KLAC] (alphabetical).
    expect(currentPicksOrder).toEqual(['KLAC', 'CF']);
    expect(holdingsTimelineOrder).toEqual(['KLAC', 'CF']);
    // Core contract: the two tables agree.
    expect(currentPicksOrder).toEqual(holdingsTimelineOrder);
  });

  it('bandBook present: sold order follows bandBook sequence, not holdings order', () => {
    // When bandBook is present, it is the authoritative membership + order.
    const priorEntry: AiPickTimelineEntry = {
      date: '2025-08-31',
      holdings: [
        // Holdings list has CF first (alphabetically earlier)
        { ticker: 'CF',   sector: 'Materials' },
        { ticker: 'KLAC', sector: 'Information Technology' },
        { ticker: 'NVDA', sector: 'Information Technology' },
      ],
      // bandBook order: KLAC first (composite-desc)
      bandBook: ['NVDA', 'KLAC', 'CF'],
    };
    const currentTickers = ['NVDA'];  // KLAC and CF both sold

    const currentPicksOrder  = deriveSoldTickersCurrentPicks(priorEntry, currentTickers);
    const holdingsTimelineOrder = deriveSoldTickersHoldingsTimeline(priorEntry, currentTickers);

    // Order from bandBook: [KLAC, CF] — NOT [CF, KLAC] (holdings order or alpha)
    expect(currentPicksOrder).toEqual(['KLAC', 'CF']);
    expect(holdingsTimelineOrder).toEqual(['KLAC', 'CF']);
    expect(currentPicksOrder).toEqual(holdingsTimelineOrder);
  });

  it('no sold tickers: both return empty array', () => {
    const priorEntry: AiPickTimelineEntry = {
      date: '2025-05-31',
      holdings: [
        { ticker: 'NVDA', sector: 'Information Technology' },
        { ticker: 'MSFT', sector: 'Information Technology' },
      ],
    };
    const currentTickers = ['NVDA', 'MSFT', 'AAPL'];

    expect(deriveSoldTickersCurrentPicks(priorEntry, currentTickers)).toEqual([]);
    expect(deriveSoldTickersHoldingsTimeline(priorEntry, currentTickers)).toEqual([]);
  });

  it('all prior tickers sold: both return full prior list in prior-basket order', () => {
    const priorEntry: AiPickTimelineEntry = {
      date: '2025-02-28',
      holdings: [
        { ticker: 'Z',    sector: 'Real Estate' },
        { ticker: 'AAPL', sector: 'Information Technology' },
        { ticker: 'META', sector: 'Communication Services' },
      ],
    };
    const currentTickers = ['NVDA', 'MSFT'];  // entirely new basket

    const currentPicksOrder  = deriveSoldTickersCurrentPicks(priorEntry, currentTickers);
    const holdingsTimelineOrder = deriveSoldTickersHoldingsTimeline(priorEntry, currentTickers);

    // Prior-basket order [Z, AAPL, META], NOT alphabetical [AAPL, META, Z]
    expect(currentPicksOrder).toEqual(['Z', 'AAPL', 'META']);
    expect(holdingsTimelineOrder).toEqual(['Z', 'AAPL', 'META']);
    expect(currentPicksOrder).toEqual(holdingsTimelineOrder);
  });

  it('bandHeldCount present (no bandBook): uses prefix slice order', () => {
    const priorEntry: AiPickTimelineEntry = {
      date: '2025-11-30',
      holdings: [
        { ticker: 'NVDA', sector: 'Information Technology' },
        { ticker: 'KLAC', sector: 'Information Technology' },
        { ticker: 'CF',   sector: 'Materials' },
        // 4th holding is outside the slice (bandHeldCount=3)
        { ticker: 'AAPL', sector: 'Information Technology' },
      ],
      bandHeldCount: 3,
    };
    const currentTickers = ['NVDA'];

    const currentPicksOrder  = deriveSoldTickersCurrentPicks(priorEntry, currentTickers);
    const holdingsTimelineOrder = deriveSoldTickersHoldingsTimeline(priorEntry, currentTickers);

    // Only first 3 holdings form the prior basket (bandHeldCount=3).
    // Sold: [KLAC, CF] in slice order — AAPL (4th holding) is NOT in prior basket.
    expect(currentPicksOrder).toEqual(['KLAC', 'CF']);
    expect(holdingsTimelineOrder).toEqual(['KLAC', 'CF']);
    expect(currentPicksOrder).toEqual(holdingsTimelineOrder);
  });
});

// ---------------------------------------------------------------------------
// 8. Leg-return computation — snapToTradingDayIndex + computeLegReturns
//
// These tests contract the pure helpers exported from HoldingsTimeline.tsx
// that power the per-quarter book vs benchmark summary in each QuarterDrawer.
//
// The snap behavior mirrors Python's bisect_left semantics (as in
// `compute/validation/basket_rule_validation.py::_snap_to_trading_day`):
//   - exact match → that date's index
//   - date between two trading days → next trading day (first >= query)
//   - date past the last trading day → last date index (clamp)
//   - empty dates → -1
//
// The leg-return computation mirrors _extract_quarterly_returns:
//   bookRet  = portfolioNav[end] / portfolioNav[start] − 1  (as %)
//   idxRet   = benchmarkNav[end] / benchmarkNav[start] − 1  (as %)
//   null boundary NAV → null return (never crash)
//   last leg → partial: true, end = last finite NAV index
// ---------------------------------------------------------------------------

import { snapToTradingDayIndex, computeLegReturns } from './HoldingsTimeline';

describe('snapToTradingDayIndex — bisect_left semantics', () => {
  const DATES = ['2023-01-03', '2023-04-03', '2023-07-03', '2023-10-02'];

  it('exact match → that date\'s index', () => {
    expect(snapToTradingDayIndex('2023-04-03', DATES)).toBe(1);
  });

  it('date between two trading days → next trading day (first date >=)', () => {
    // 2023-04-01 (Saturday) → next is 2023-04-03 (index 1)
    expect(snapToTradingDayIndex('2023-04-01', DATES)).toBe(1);
  });

  it('date before first trading day → index 0', () => {
    expect(snapToTradingDayIndex('2022-12-30', DATES)).toBe(0);
  });

  it('date past last trading day → clamps to last index', () => {
    // 2024-01-02 is past the end → index 3 (last)
    expect(snapToTradingDayIndex('2024-01-02', DATES)).toBe(3);
  });

  it('empty dates → -1', () => {
    expect(snapToTradingDayIndex('2023-04-03', [])).toBe(-1);
  });

  it('first date in array → index 0', () => {
    expect(snapToTradingDayIndex('2023-01-03', DATES)).toBe(0);
  });
});

describe('computeLegReturns — per-leg book vs benchmark returns', () => {
  // Synthetic dates: 4 weekly dates (trading days)
  const DATES = ['2023-01-03', '2023-01-10', '2023-01-17', '2023-01-24'];
  // Rebalances at dates[0] and dates[2] → 2 legs
  const TIMELINE_DATES = ['2023-01-03', '2023-01-17'];

  // NAV series: starts at 100, grows to 110 then 121
  const PORTFOLIO_NAV: (number | null)[] = [100, 105, 110, 121];
  // Benchmark: starts at 100, grows to 104 then 108
  const BENCHMARK_NAV: (number | null)[] = [100, 102, 104, 108];

  it('produces one result per timeline entry', () => {
    const legs = computeLegReturns(TIMELINE_DATES, DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    expect(legs).toHaveLength(2);
  });

  it('leg 0: start=dates[0] (index 0), end=dates[2] (index 2) — not partial', () => {
    const legs = computeLegReturns(TIMELINE_DATES, DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    // bookRet  = (110/100 - 1)*100 = +10%
    // idxRet   = (104/100 - 1)*100 = +4%
    expect(legs[0].partial).toBe(false);
    expect(legs[0].portfolio).toBeCloseTo(10, 5);
    expect(legs[0].benchmark).toBeCloseTo(4, 5);
  });

  it('leg 1 (last): start=dates[2] (index 2), end=last-finite index (3) — partial:true', () => {
    const legs = computeLegReturns(TIMELINE_DATES, DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    // bookRet  = (121/110 - 1)*100 = +10%
    // idxRet   = (108/104 - 1)*100 = ~3.85%
    expect(legs[1].partial).toBe(true);
    expect(legs[1].portfolio).toBeCloseTo(10, 5);
    expect(legs[1].benchmark).toBeCloseTo((108 / 104 - 1) * 100, 5);
  });

  it('null NAV at start boundary → null return (graceful, no crash)', () => {
    const navWithNull: (number | null)[] = [null, 105, 110, 121];
    const legs = computeLegReturns(TIMELINE_DATES, DATES, navWithNull, BENCHMARK_NAV);
    // Leg 0 starts at index 0 which is null → portfolio null
    expect(legs[0].portfolio).toBeNull();
    // Benchmark is fine (100 at index 0)
    expect(legs[0].benchmark).toBeCloseTo(4, 5);
  });

  it('null benchmark NAV at start boundary → benchmark null, portfolio still works', () => {
    const benchNull: (number | null)[] = [null, 102, 104, 108];
    const legs = computeLegReturns(TIMELINE_DATES, DATES, PORTFOLIO_NAV, benchNull);
    expect(legs[0].portfolio).toBeCloseTo(10, 5);
    expect(legs[0].benchmark).toBeNull();
  });

  it('all nulls in portfolio NAV → empty result (lastFiniteNavIndex = -1)', () => {
    const allNull: (number | null)[] = [null, null, null, null];
    const legs = computeLegReturns(TIMELINE_DATES, DATES, allNull, BENCHMARK_NAV);
    expect(legs).toHaveLength(0);
  });

  it('empty dates → empty result', () => {
    const legs = computeLegReturns(TIMELINE_DATES, [], [], []);
    expect(legs).toHaveLength(0);
  });

  it('empty timeline → empty result', () => {
    const legs = computeLegReturns([], DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    expect(legs).toHaveLength(0);
  });

  it('mismatched nav vs dates lengths → empty result', () => {
    const legs = computeLegReturns(TIMELINE_DATES, DATES, [100, 110], BENCHMARK_NAV);
    expect(legs).toHaveLength(0);
  });

  it('snap behavior: rebalance date falls between trading days → snaps to next', () => {
    // TIMELINE_DATES[0] = '2023-01-04' (Wed; not in DATES)
    // Next trading day in DATES is '2023-01-10' (index 1)
    const timelineDatesOffGrid = ['2023-01-04', '2023-01-17'];
    const legs = computeLegReturns(timelineDatesOffGrid, DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    // Leg 0: start=index 1 (105), end=index 2 (110)
    // bookRet = (110/105 - 1)*100 ≈ 4.76%
    expect(legs[0].partial).toBe(false);
    expect(legs[0].portfolio).toBeCloseTo((110 / 105 - 1) * 100, 5);
  });

  it('rebalance date past end of dates → snaps to last date (clamp)', () => {
    // TIMELINE_DATES[1] past the series end — snapToTradingDayIndex clamps to
    // the last index (3). Leg 0 uses the clamped index 3 as its end boundary.
    // Leg 1 (last leg) starts at clamped index 3 and ends at lastFiniteNavIndex=3.
    const futureDate = ['2023-01-03', '2025-01-01'];
    const legs = computeLegReturns(futureDate, DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    // Leg 0: NOT the last leg → partial:false
    //   start=index 0 (100), end=snapToTradingDayIndex('2025-01-01')=index 3 (121)
    //   bookRet = (121/100 - 1)*100 = 21%
    expect(legs[0].partial).toBe(false);
    expect(legs[0].portfolio).toBeCloseTo(21, 5);
    // Leg 1: last leg → partial:true
    //   start=index 3 (121), end=lastFiniteNavIndex=3 (121) — same index → null
    expect(legs[1].partial).toBe(true);
    expect(legs[1].portfolio).toBeNull();
  });

  it('single rebalance → single partial leg from start to end of series', () => {
    const singleRebalance = ['2023-01-03'];
    const legs = computeLegReturns(singleRebalance, DATES, PORTFOLIO_NAV, BENCHMARK_NAV);
    expect(legs).toHaveLength(1);
    expect(legs[0].partial).toBe(true);
    // start=index 0 (100), end=last finite=index 3 (121)
    // bookRet = (121/100 - 1)*100 = 21%
    expect(legs[0].portfolio).toBeCloseTo(21, 5);
  });
});
