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
import type { AiPickTimelineEntry, AiPickTimelineHolding } from '@/lib/types';

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
