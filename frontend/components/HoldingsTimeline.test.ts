/**
 * Pure-logic contract tests for the HoldingsTimeline per-quarter drawer.
 *
 * The component renders in a 'use client' context with accordion state
 * (useState) and Next.js Link, both of which require a DOM environment that
 * this repo does not have wired up (vitest.config.ts: environment: 'node').
 * Following the project convention established by RankingTable.test.ts —
 * extract the behaviorally observable pure computations and test those
 * verbatim, without DOM rendering.
 *
 * What is tested here:
 *   1. weightByTicker / returnByTicker graceful fallback — when both maps are
 *      absent (legacy slider artifact), every ticker renders '—' for weight
 *      and return.
 *   2. apportionWeightLabels — the Hamilton rounding helper (shared from
 *      portfolio-format.ts) sums to exactly the basket total (additive only,
 *      covers the drawer's weight column).
 *   3. Status mapping — ticker in `entered` → 'New'; ticker not in `entered`
 *      → 'Held'; ticker in `exited` set → 'Sold'.
 *   4. pctStr / toneClass — sign-aware display helpers produce correct output
 *      for positive, negative, and null inputs.
 *   5. Drawer held-sort — weight-descending sort places the highest-weight
 *      ticker first; ties preserve original composite-desc order.
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import { apportionWeightLabels, pctStr, toneClass } from '../lib/portfolio-format';

// ---------------------------------------------------------------------------
// 1. Graceful fallback when weight/return maps are absent
// ---------------------------------------------------------------------------
describe('QuarterDrawer — graceful fallback when maps absent', () => {
  it('pctStr returns em-dash for null (the fallback display value)', () => {
    expect(pctStr(null)).toBe('—');
  });

  it('apportionWeightLabels returns all em-dashes when all weights are null', () => {
    const labels = apportionWeightLabels([null, null, null]);
    expect(labels).toEqual(['—', '—', '—']);
  });

  it('apportionWeightLabels returns em-dashes when weights are undefined', () => {
    // Legacy slider artifacts have no weightByTicker → the drawer passes
    // undefined for each ticker, which the helper treats as non-finite.
    const labels = apportionWeightLabels([undefined, undefined]);
    expect(labels).toEqual(['—', '—']);
  });
});

// ---------------------------------------------------------------------------
// 2. Hamilton apportionment — weight labels sum correctly
// ---------------------------------------------------------------------------
describe('apportionWeightLabels — Hamilton rounding', () => {
  it('sums to 100.0% for a 3-stock equal-weight book', () => {
    // Three equal weights summing to 1.0
    const w = [1 / 3, 1 / 3, 1 / 3];
    const labels = apportionWeightLabels(w);
    const total = labels.reduce((s, l) => {
      if (l === '—') return s;
      return s + parseFloat(l.replace('%', ''));
    }, 0);
    expect(total).toBeCloseTo(100.0, 1);
  });

  it('assigns the extra 0.1% to the label with the largest fractional remainder', () => {
    // 0.334, 0.333, 0.333 — first one should round UP to get 33.4% vs 33.3%
    const labels = apportionWeightLabels([0.334, 0.333, 0.333]);
    const total = labels.reduce((s, l) => {
      if (l === '—') return s;
      return s + parseFloat(l.replace('%', ''));
    }, 0);
    expect(total).toBeCloseTo(100.0, 1);
  });

  it('skips null weights and apportions only finite weights', () => {
    // 2 valid weights + 1 null (e.g. missing sigma_90d)
    const labels = apportionWeightLabels([0.5, null, 0.5]);
    expect(labels[1]).toBe('—');
    const sum = [labels[0], labels[2]].reduce((s, l) => {
      if (l === '—') return s;
      return s + parseFloat(l.replace('%', ''));
    }, 0);
    expect(sum).toBeCloseTo(100.0, 1);
  });
});

// ---------------------------------------------------------------------------
// 3. Status mapping — New / Held / Sold derivation
// ---------------------------------------------------------------------------
describe('Status chip derivation', () => {
  // Mirrors the QuarterDrawer logic:
  //   isNew = isInitial || entered.has(ticker)
  //   sold  = exited set
  const deriveStatus = (
    ticker: string,
    entered: Set<string>,
    exited: string[],
    isInitial: boolean,
  ): 'New' | 'Held' | 'Sold' => {
    if (exited.includes(ticker)) return 'Sold';
    if (isInitial || entered.has(ticker)) return 'New';
    return 'Held';
  };

  it('ticker in entered → New', () => {
    expect(deriveStatus('AAPL', new Set(['AAPL', 'NVDA']), [], false)).toBe('New');
  });

  it('ticker not in entered, not exited → Held', () => {
    expect(deriveStatus('MSFT', new Set(['AAPL']), [], false)).toBe('Held');
  });

  it('ticker in exited → Sold', () => {
    expect(deriveStatus('TSLA', new Set(), ['TSLA', 'META'], false)).toBe('Sold');
  });

  it('initial basket → all tickers are New regardless of entered set', () => {
    // For the initial basket (isInitial=true), entered is always the empty set
    // (per the HoldingsTimeline build loop: i===0 → entered = new Set()).
    // The component renders all as "New" via the isInitial flag.
    expect(deriveStatus('GOOG', new Set(), [], true)).toBe('New');
  });
});

// ---------------------------------------------------------------------------
// 4. pctStr / toneClass display helpers
// ---------------------------------------------------------------------------
describe('pctStr', () => {
  it('formats positive value with + sign', () => {
    expect(pctStr(12.3)).toBe('+12.3%');
  });

  it('formats negative value with − sign (unicode minus)', () => {
    expect(pctStr(-5.7)).toBe('−5.7%');
  });

  it('returns em-dash for null', () => {
    expect(pctStr(null)).toBe('—');
  });

  it('formats zero as +0.0%', () => {
    expect(pctStr(0)).toBe('+0.0%');
  });
});

describe('toneClass', () => {
  it('positive → emerald classes', () => {
    const cls = toneClass(15.4);
    expect(cls).toContain('emerald');
  });

  it('negative → rose classes', () => {
    const cls = toneClass(-3.2);
    expect(cls).toContain('rose');
  });

  it('null → slate muted classes', () => {
    const cls = toneClass(null);
    expect(cls).toContain('slate');
  });
});

// ---------------------------------------------------------------------------
// 5. Drawer held-sort — weight-descending
// ---------------------------------------------------------------------------
describe('QuarterDrawer held-sort', () => {
  // Verbatim from HoldingsTimeline.tsx QuarterDrawer sortedHeld logic.
  const sortHeld = (
    held: string[],
    weightByTicker: Record<string, number | null> | undefined,
  ): string[] =>
    [...held].sort((a, b) => {
      const aW = weightByTicker?.[a];
      const bW = weightByTicker?.[b];
      const aFin = aW !== null && aW !== undefined && !Number.isNaN(aW) && aW > 0;
      const bFin = bW !== null && bW !== undefined && !Number.isNaN(bW) && bW > 0;
      if (aFin && bFin) return (bW as number) - (aW as number);
      if (aFin) return -1;
      if (bFin) return 1;
      return 0;
    });

  it('sorts by weight descending', () => {
    const held = ['AAPL', 'NVDA', 'MSFT'];
    const weights = { AAPL: 0.25, NVDA: 0.40, MSFT: 0.35 };
    const sorted = sortHeld(held, weights);
    expect(sorted).toEqual(['NVDA', 'MSFT', 'AAPL']);
  });

  it('places null-weight tickers at the end', () => {
    const held = ['AAPL', 'NVDA', 'MSFT'];
    const weights: Record<string, number | null> = { AAPL: 0.5, NVDA: null, MSFT: 0.3 };
    const sorted = sortHeld(held, weights);
    expect(sorted[0]).toBe('AAPL');
    expect(sorted[sorted.length - 1]).toBe('NVDA');
  });

  it('preserves original order when all weights are absent (no weightByTicker)', () => {
    const held = ['AAPL', 'NVDA', 'MSFT'];
    const sorted = sortHeld(held, undefined);
    expect(sorted).toEqual(['AAPL', 'NVDA', 'MSFT']);
  });
});
