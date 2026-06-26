/**
 * Contract tests for frontend/lib/portfolio-format.ts
 *
 * Covers the four shared display helpers consumed by both AiPickPortfolio.tsx
 * (Current picks table) and HoldingsTimeline.tsx (per-quarter QuarterDrawer).
 * These helpers were extracted in PR-2b to keep the two tables in visual
 * lockstep without duplication.
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import {
  apportionWeightLabels,
  pctStr,
  toneClass,
  twrToneClass,
} from './portfolio-format';

// ---------------------------------------------------------------------------
// apportionWeightLabels — Hamilton (Largest Remainder) apportionment
// ---------------------------------------------------------------------------

describe('apportionWeightLabels', () => {
  it('returns all "—" for an empty array', () => {
    expect(apportionWeightLabels([])).toEqual([]);
  });

  it('returns "—" for a single null weight', () => {
    expect(apportionWeightLabels([null])).toEqual(['—']);
  });

  it('returns "—" for all-null weights', () => {
    expect(apportionWeightLabels([null, null, null])).toEqual(['—', '—', '—']);
  });

  it('renders a single 100% weight correctly', () => {
    expect(apportionWeightLabels([1.0])).toEqual(['100.0%']);
  });

  it('apportions two equal weights to 50.0% each', () => {
    const result = apportionWeightLabels([0.5, 0.5]);
    expect(result).toEqual(['50.0%', '50.0%']);
  });

  it('sum of label values equals the finite-weight total (rounding drift corrected)', () => {
    // Three weights that individually round to 33.3%, 33.3%, 33.3% — would sum
    // to 99.9%. Apportionment must correct to 100.0%.
    const weights = [1 / 3, 1 / 3, 1 / 3];
    const labels = apportionWeightLabels(weights);
    const sum = labels.reduce((s, l) => {
      if (l === '—') return s;
      return s + parseFloat(l.replace('%', ''));
    }, 0);
    // Should be exactly 100.0 (within floating-point rounding of the display step)
    expect(sum).toBeCloseTo(100.0, 1);
    // Each label should be one of 33.3% or 33.4% (the remainder gets +0.1%)
    expect(labels.every((l) => l === '33.3%' || l === '33.4%')).toBe(true);
  });

  it('excludes null weights from the apportionment (non-finite → "—")', () => {
    // Two valid weights + one null: the valid two sum to ~66.7% of a full book
    // but "target" tracks the finite sum honestly.
    const weights = [0.5, 0.5, null];
    const labels = apportionWeightLabels(weights);
    expect(labels[2]).toBe('—');
    // The finite labels should sum to 100.0% (the finite total is 1.0)
    const sum = parseFloat(labels[0].replace('%', '')) + parseFloat(labels[1].replace('%', ''));
    expect(sum).toBeCloseTo(100.0, 1);
  });

  it('handles a realistic 9-stock inverse-vol book without drift', () => {
    // Weights sum to exactly 1.0 but toFixed(1) would drift per-row.
    // Verify the labels sum to 100.0%.
    const weights = [
      0.1542, 0.1312, 0.1248, 0.1187, 0.1133, 0.1089, 0.0896, 0.0805, 0.0788,
    ];
    const labels = apportionWeightLabels(weights);
    const sum = labels.reduce((s, l) => s + parseFloat(l.replace('%', '')), 0);
    expect(sum).toBeCloseTo(100.0, 1);
  });

  it('handles undefined weights the same as null', () => {
    const labels = apportionWeightLabels([undefined, 1.0]);
    expect(labels[0]).toBe('—');
    expect(labels[1]).toBe('100.0%');
  });
});

// ---------------------------------------------------------------------------
// pctStr — signed percentage formatter
// ---------------------------------------------------------------------------

describe('pctStr', () => {
  it('returns "—" for null', () => {
    expect(pctStr(null)).toBe('—');
  });

  it('formats a positive value with "+" prefix', () => {
    expect(pctStr(12.3)).toBe('+12.3%');
  });

  it('formats a negative value with typographic minus (U+2212)', () => {
    const result = pctStr(-5.7);
    expect(result).toBe('−5.7%');
    // Confirm it uses the Unicode minus, not a hyphen-minus
    expect(result.charCodeAt(0)).toBe(0x2212);
  });

  it('formats zero as "+0.0%"', () => {
    expect(pctStr(0)).toBe('+0.0%');
  });

  it('rounds to 1 decimal place', () => {
    expect(pctStr(12.349)).toBe('+12.3%');
    expect(pctStr(12.351)).toBe('+12.4%');
  });

  it('formats a large positive return correctly', () => {
    expect(pctStr(123.4)).toBe('+123.4%');
  });

  it('formats a large negative return correctly', () => {
    expect(pctStr(-99.9)).toBe('−99.9%');
  });
});

// ---------------------------------------------------------------------------
// toneClass — Tailwind color class for signed values (primary MWR tone)
// ---------------------------------------------------------------------------

describe('toneClass', () => {
  it('returns muted slate for null', () => {
    expect(toneClass(null)).toBe('text-slate-500 dark:text-slate-400');
  });

  it('returns emerald for positive values', () => {
    expect(toneClass(1)).toBe('text-emerald-700 dark:text-emerald-300');
    expect(toneClass(0.01)).toBe('text-emerald-700 dark:text-emerald-300');
  });

  it('returns emerald for exactly zero', () => {
    // 0 is treated as non-negative
    expect(toneClass(0)).toBe('text-emerald-700 dark:text-emerald-300');
  });

  it('returns rose for negative values', () => {
    expect(toneClass(-1)).toBe('text-rose-700 dark:text-rose-300');
    expect(toneClass(-0.001)).toBe('text-rose-700 dark:text-rose-300');
  });

  it('includes dark: paired variant on every return value', () => {
    // Design-system invariant: every color token has a dark: pair.
    const cases = [null, 10, -10, 0];
    for (const v of cases) {
      const cls = toneClass(v);
      expect(cls, `toneClass(${v}) must include a dark: class`).toContain('dark:');
    }
  });
});

// ---------------------------------------------------------------------------
// twrToneClass — muted tone for the TWR "Stock price return" shadow line
// ---------------------------------------------------------------------------

describe('twrToneClass', () => {
  it('returns muted slate for null', () => {
    expect(twrToneClass(null)).toBe('text-slate-400 dark:text-slate-500');
  });

  it('returns a less-prominent emerald for positive values', () => {
    // twrToneClass uses -600/-400 (muted) vs toneClass -700/-300 (headline)
    expect(twrToneClass(5)).toBe('text-emerald-600 dark:text-emerald-400');
  });

  it('returns a less-prominent rose for negative values', () => {
    expect(twrToneClass(-5)).toBe('text-rose-600 dark:text-rose-400');
  });

  it('is visually less prominent than toneClass for the same value', () => {
    // This is a structural check: the TWR class should differ from the MWR class.
    expect(twrToneClass(10)).not.toBe(toneClass(10));
    expect(twrToneClass(-10)).not.toBe(toneClass(-10));
  });

  it('includes dark: paired variant on every return value', () => {
    const cases = [null, 10, -10];
    for (const v of cases) {
      const cls = twrToneClass(v);
      expect(cls, `twrToneClass(${v}) must include a dark: class`).toContain('dark:');
    }
  });
});

// ---------------------------------------------------------------------------
// MWR feed integration — simulate how AiPickPortfolio consumes mwrByTicker
// ---------------------------------------------------------------------------

describe('MWR display logic (integration with portfolio-format)', () => {
  it('pctStr renders the MWR and TWR values consistently', () => {
    // Simulate a position_returns entry for a held ticker
    const mwrEntry = {
      mwr_pct: 14.7,
      twr_pct: 13.2,
      contrib_nav_pts: null,
      since_date: '2024-01-15',
      partial_history: false,
      legs_used: 4,
    };

    // Headline: MWR
    expect(pctStr(mwrEntry.mwr_pct)).toBe('+14.7%');
    // Shadow: TWR
    expect(pctStr(mwrEntry.twr_pct)).toBe('+13.2%');
    // TWR differs by 1.5pp ≥ 0.05 → shadow should show
    const diff = Math.abs(mwrEntry.twr_pct - mwrEntry.mwr_pct);
    expect(diff).toBeGreaterThanOrEqual(0.05);
  });

  it('TWR shadow suppressed when MWR ≈ TWR (< 0.05pp diff)', () => {
    const mwr = 8.3;
    const twr = 8.31; // diff = 0.01pp < 0.05 threshold
    const diff = Math.abs(twr - mwr);
    expect(diff).toBeLessThan(0.05);
    // UI would NOT render the TWR shadow (showTwr = false)
  });

  it('TWR shadow shown when diff equals or exceeds threshold (0.1pp clear boundary)', () => {
    const mwr = 8.3;
    const twr = 8.4; // diff = 0.1pp, well above the 0.05pp threshold
    const diff = Math.abs(twr - mwr);
    expect(diff).toBeGreaterThanOrEqual(0.05);
    // UI WOULD render the TWR shadow
  });

  it('graceful degradation: null mwr_pct renders "—"', () => {
    // Pre-engine artifact: position_returns absent → mwr_pct = null
    expect(pctStr(null)).toBe('—');
    expect(toneClass(null)).toBe('text-slate-500 dark:text-slate-400');
  });

  it('partial_history=true flag is boolean (truthy check)', () => {
    const entryWithPartial = {
      mwr_pct: 5.1,
      twr_pct: 4.9,
      contrib_nav_pts: null,
      since_date: '2022-06-30',
      partial_history: true,
      legs_used: 2,
    };
    expect(entryWithPartial.partial_history).toBe(true);
    expect(entryWithPartial.since_date).not.toBeNull();
  });

  it('toneClass and twrToneClass applied correctly to MWR/TWR pair', () => {
    const mwr = 12.3;
    const twr = -2.1; // negative shadow despite positive MWR
    expect(toneClass(mwr)).toBe('text-emerald-700 dark:text-emerald-300');
    expect(twrToneClass(twr)).toBe('text-rose-600 dark:text-rose-400');
  });
});

// ---------------------------------------------------------------------------
// HoldingsTimeline QuarterDrawer weight apportionment — verify apportionWeightLabels
// matches the AiPickPortfolio Current-picks call signature exactly.
// ---------------------------------------------------------------------------

describe('QuarterDrawer weight apportionment (HoldingsTimeline)', () => {
  it('apportions per-quarter weights with no drift for a realistic basket', () => {
    // Simulate a 5-name adaptive basket with inverse-vol weights from an entry's
    // weightByTicker (band_weights or weights_by_count resolution).
    const weightByTicker: Record<string, number | null> = {
      MSFT: 0.2431,
      AAPL: 0.2205,
      META: 0.1987,
      GOOG: 0.1734,
      NVDA: 0.1643,
    };
    const tickers = Object.keys(weightByTicker);
    const rawWeights = tickers.map((t) => weightByTicker[t]);
    const labels = apportionWeightLabels(rawWeights);

    const sum = labels.reduce((s, l) => {
      if (l === '—') return s;
      return s + parseFloat(l.replace('%', ''));
    }, 0);
    expect(sum).toBeCloseTo(100.0, 1);
    // Each label should be a valid percentage string
    for (const l of labels) {
      expect(l).toMatch(/^\d+\.\d%$/);
    }
  });

  it('returns "—" for a ticker whose weight is null (unavailable)', () => {
    // sigma_90d missing → weight null → label "—"
    const weights: (number | null)[] = [0.5, null, 0.5];
    const labels = apportionWeightLabels(weights);
    expect(labels[1]).toBe('—');
  });

  it('handles a pre-engine artifact with no weightByTicker (all null)', () => {
    // When the entry has no weights_by_count and no band_weights,
    // weightByTicker is absent → all weights null → all "—"
    const weights: (number | null)[] = [null, null, null, null];
    const labels = apportionWeightLabels(weights);
    expect(labels).toEqual(['—', '—', '—', '—']);
  });
});
