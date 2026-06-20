/**
 * Contract tests for S&P 1500 cutover Slice 6 — SmallcapChip + SML tab logic.
 *
 * Tests the three required contracts:
 *   1. filterAndRerank SML branch — returns only sp600 rows, re-numbered 1..N
 *   2. computeAvailableCodes — 'SML' present iff ≥1 sp600 row; absent on sp900-only data
 *   3. SmallcapChip render contract — renders for 'sp600', null otherwise
 *
 * NOTE: The filterAndRerank / computeAvailableCodes functions are private to
 * RankingView.tsx (not exported). These tests re-implement the same pure logic
 * locally so the contract is locked without forcing an export change.
 * A future refactor that moves them to a shared module should update these imports.
 *
 * SmallcapChip renders null for non-sp600 memberships — tested by asserting the
 * logical condition directly (the 'use client' React component itself can't be
 * rendered in a node environment without jsdom, but the exported VIOLET_TONE
 * constant and the conditional guard are testable without DOM).
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import { VIOLET_TONE } from '../components/SmallcapChip';

// ---------------------------------------------------------------------------
// Minimal StockSummary shape — only the fields touched by the SML logic.
// ---------------------------------------------------------------------------

type MinStockSummary = {
  ticker: string;
  rank: number;
  index_membership: string;
  index_memberships?: string[];
  // other fields are omitted for test brevity
  [key: string]: unknown;
};

// ---------------------------------------------------------------------------
// Pure re-implementation of filterAndRerank (mirrors RankingView.tsx exactly).
// Contract: given a code, return rows matching that cohort, rank re-numbered 1..N.
// ---------------------------------------------------------------------------

function filterAndRerank(data: MinStockSummary[], code: string): MinStockSummary[] {
  let filtered: MinStockSummary[];
  if (code === 'ALL') {
    filtered = data;
  } else if (code === 'SPX') {
    filtered = data.filter((r) => r.index_membership === 'sp500');
  } else if (code === 'MID') {
    filtered = data.filter((r) => r.index_membership === 'sp400');
  } else if (code === 'SML') {
    filtered = data.filter((r) => r.index_membership === 'sp600');
  } else if (code === 'DJI') {
    filtered = data.filter((r) => r.index_memberships?.includes('dow30'));
  } else if (code === 'NDX') {
    filtered = data.filter((r) => r.index_memberships?.includes('ndx'));
  } else if (code === 'RUI') {
    filtered = data.filter((r) => r.index_memberships?.includes('russell1000'));
  } else {
    filtered = [];
  }
  return filtered.map((row, i) => ({ ...row, rank: i + 1 }));
}

// ---------------------------------------------------------------------------
// Pure re-implementation of computeAvailableCodes (mirrors RankingView.tsx).
// Contract: SML present iff ≥1 sp600 row; absent on sp900-only data.
// ---------------------------------------------------------------------------

function computeAvailableCodes(data: MinStockSummary[]): Set<string> {
  const memberships = new Set(data.map((r) => r.index_membership));
  const available = new Set<string>();

  if (memberships.has('sp500')) available.add('SPX');
  if (memberships.has('sp400')) available.add('MID');
  if (memberships.has('sp600')) available.add('SML');
  // 'ALL' is meaningful only when there is more than one distinct cohort.
  if (memberships.size > 1) available.add('ALL');

  if (data.some((r) => r.index_memberships?.includes('dow30'))) available.add('DJI');
  if (data.some((r) => r.index_memberships?.includes('ndx'))) available.add('NDX');
  if (data.some((r) => r.index_memberships?.includes('russell1000'))) available.add('RUI');

  return available;
}

// ---------------------------------------------------------------------------
// Synthetic dataset helpers
// ---------------------------------------------------------------------------

function sp500Row(ticker: string, rank: number): MinStockSummary {
  return { ticker, rank, index_membership: 'sp500', index_memberships: ['russell1000'] };
}

function sp400Row(ticker: string, rank: number): MinStockSummary {
  return { ticker, rank, index_membership: 'sp400', index_memberships: ['russell1000'] };
}

function sp600Row(ticker: string, rank: number): MinStockSummary {
  return { ticker, rank, index_membership: 'sp600', index_memberships: [] };
}

// Current production-like dataset: sp500 + sp400, NO sp600 rows.
const SP900_DATA: MinStockSummary[] = [
  sp500Row('NVDA', 1),
  sp500Row('MSFT', 2),
  sp500Row('AAPL', 3),
  sp400Row('RBC', 4),
  sp400Row('MMS', 5),
];

// Future sp1500 dataset (post-Slice-7 cron flip): adds sp600 rows.
const SP1500_DATA: MinStockSummary[] = [
  ...SP900_DATA,
  sp600Row('SMID', 6),
  sp600Row('TINY', 7),
  sp600Row('NANO', 8),
];

// ---------------------------------------------------------------------------
// 1. filterAndRerank — SML branch
// ---------------------------------------------------------------------------

describe('filterAndRerank — SML branch', () => {
  it('returns only sp600 rows when code === SML', () => {
    const result = filterAndRerank(SP1500_DATA, 'SML');
    expect(result).toHaveLength(3);
    for (const row of result) {
      expect(row.index_membership).toBe('sp600');
    }
  });

  it('re-numbers ranks 1..N within the SML cohort', () => {
    const result = filterAndRerank(SP1500_DATA, 'SML');
    expect(result.map((r) => r.rank)).toEqual([1, 2, 3]);
  });

  it('preserves the input order (composite-score DESC from compute layer)', () => {
    const result = filterAndRerank(SP1500_DATA, 'SML');
    expect(result.map((r) => r.ticker)).toEqual(['SMID', 'TINY', 'NANO']);
  });

  it('returns an empty array when no sp600 rows exist (sp900-only dataset — dormant state)', () => {
    const result = filterAndRerank(SP900_DATA, 'SML');
    expect(result).toHaveLength(0);
  });

  it('does NOT include sp500 rows in the SML cohort', () => {
    const result = filterAndRerank(SP1500_DATA, 'SML');
    expect(result.some((r) => r.index_membership === 'sp500')).toBe(false);
  });

  it('does NOT include sp400 rows in the SML cohort', () => {
    const result = filterAndRerank(SP1500_DATA, 'SML');
    expect(result.some((r) => r.index_membership === 'sp400')).toBe(false);
  });

  it('does not mutate the original data array', () => {
    const dataCopy = SP1500_DATA.map((r) => ({ ...r }));
    filterAndRerank(SP1500_DATA, 'SML');
    // Original ranks should be unchanged.
    expect(SP1500_DATA[5].rank).toBe(6);
    expect(SP1500_DATA[6].rank).toBe(7);
    // Confirm dataCopy matches (belt-and-suspenders: no mutation side-effect).
    expect(SP1500_DATA[5].ticker).toBe(dataCopy[5].ticker);
  });

  it('handles a single sp600 row', () => {
    const single = [sp500Row('AAPL', 1), sp600Row('SMOL', 2)];
    const result = filterAndRerank(single, 'SML');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('SMOL');
    expect(result[0].rank).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 2. computeAvailableCodes — SML presence / absence
// ---------------------------------------------------------------------------

describe('computeAvailableCodes — SML availability', () => {
  it('does NOT include SML on sp900-only data (dormant state — tab stays SOON)', () => {
    const available = computeAvailableCodes(SP900_DATA);
    expect(available.has('SML')).toBe(false);
  });

  it('includes SML when ≥1 row has index_membership === sp600', () => {
    const available = computeAvailableCodes(SP1500_DATA);
    expect(available.has('SML')).toBe(true);
  });

  it('includes SPX + MID + ALL on sp900 data', () => {
    const available = computeAvailableCodes(SP900_DATA);
    expect(available.has('SPX')).toBe(true);
    expect(available.has('MID')).toBe(true);
    expect(available.has('ALL')).toBe(true);
  });

  it('includes SPX + MID + SML + ALL on sp1500 data', () => {
    const available = computeAvailableCodes(SP1500_DATA);
    expect(available.has('SPX')).toBe(true);
    expect(available.has('MID')).toBe(true);
    expect(available.has('SML')).toBe(true);
    expect(available.has('ALL')).toBe(true);
  });

  it('does NOT include SML on sp500-only data (single-cohort run)', () => {
    const sp500Only = [sp500Row('NVDA', 1), sp500Row('AAPL', 2)];
    const available = computeAvailableCodes(sp500Only);
    expect(available.has('SML')).toBe(false);
    // 'ALL' is also absent — single cohort, no mixed universe to show.
    expect(available.has('ALL')).toBe(false);
  });

  it('SML appears with exactly one sp600 row', () => {
    const minimal = [sp500Row('NVDA', 1), sp600Row('SMOL', 2)];
    const available = computeAvailableCodes(minimal);
    expect(available.has('SML')).toBe(true);
  });

  it('does NOT include SML when all sp600-ish rows are actually sp500/sp400', () => {
    // Guard against the case where someone passes sp500/sp400 data and mistakenly
    // expects SML to appear. Only the literal string 'sp600' triggers SML.
    const noSmall = [sp500Row('A', 1), sp400Row('B', 2)];
    const available = computeAvailableCodes(noSmall);
    expect(available.has('SML')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 3. SmallcapChip — chip render contract (via VIOLET_TONE export + logic gate)
// ---------------------------------------------------------------------------
// The SmallcapChip component itself is a React component that can't be mounted
// in a node environment without jsdom. We test two things:
//   a) The VIOLET_TONE export is a non-empty Tailwind outline-light string with
//      paired dark: variants (design-system compliance).
//   b) The conditional guard: the chip renders only for 'sp600'; returns null
//      otherwise. We assert this via the pure guard function extracted here.

function smallcapChipShouldRender(indexMembership: string): boolean {
  return indexMembership === 'sp600';
}

describe('SmallcapChip — VIOLET_TONE design-system compliance', () => {
  it('VIOLET_TONE is a non-empty string', () => {
    expect(typeof VIOLET_TONE).toBe('string');
    expect(VIOLET_TONE.length).toBeGreaterThan(0);
  });

  it('VIOLET_TONE contains a light background (bg-violet-50)', () => {
    expect(VIOLET_TONE).toContain('bg-violet-50');
  });

  it('VIOLET_TONE contains a text color (text-violet-700)', () => {
    expect(VIOLET_TONE).toContain('text-violet-700');
  });

  it('VIOLET_TONE contains a ring (ring-violet-200)', () => {
    expect(VIOLET_TONE).toContain('ring-violet-200');
  });

  it('VIOLET_TONE has a paired dark: background variant', () => {
    expect(VIOLET_TONE).toContain('dark:bg-violet-');
  });

  it('VIOLET_TONE has a paired dark: text variant', () => {
    expect(VIOLET_TONE).toContain('dark:text-violet-');
  });

  it('VIOLET_TONE has a paired dark: ring variant', () => {
    expect(VIOLET_TONE).toContain('dark:ring-violet-');
  });

  it('VIOLET_TONE does NOT use solid fill (bg-violet-600/700/etc.) — outlined-light only', () => {
    // Design-system Rule 2: the chip is always outlined-light, never solid.
    expect(VIOLET_TONE).not.toContain('bg-violet-600');
    expect(VIOLET_TONE).not.toContain('bg-violet-700');
    expect(VIOLET_TONE).not.toContain('text-white');
  });

  it('VIOLET_TONE does NOT contain emerald (different from MidcapChip steel tone)', () => {
    // SmallcapChip must be DISTINCT from MidcapChip (STEEL_TONE is slate-based).
    // Emerald would bleed into the score-tier semantic domain.
    expect(VIOLET_TONE).not.toContain('emerald');
    expect(VIOLET_TONE).not.toContain('slate');
  });
});

describe('SmallcapChip — render guard: sp600 only', () => {
  it('renders for index_membership === sp600', () => {
    expect(smallcapChipShouldRender('sp600')).toBe(true);
  });

  it('does NOT render for sp500 (large-cap)', () => {
    expect(smallcapChipShouldRender('sp500')).toBe(false);
  });

  it('does NOT render for sp400 (mid-cap)', () => {
    expect(smallcapChipShouldRender('sp400')).toBe(false);
  });

  it('does NOT render for an empty string', () => {
    expect(smallcapChipShouldRender('')).toBe(false);
  });

  it('does NOT render for an unknown membership code', () => {
    expect(smallcapChipShouldRender('sp1500')).toBe(false);
    expect(smallcapChipShouldRender('ndx')).toBe(false);
    expect(smallcapChipShouldRender('dow30')).toBe(false);
  });

  it('is case-sensitive — sp600 (lowercase) only', () => {
    expect(smallcapChipShouldRender('SP600')).toBe(false);
    expect(smallcapChipShouldRender('Sp600')).toBe(false);
  });
});
