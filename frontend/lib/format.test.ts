/**
 * Contract tests for frontend/lib/format.ts
 *
 * Guards the three display helpers against regressions in rounding, sign
 * handling, null/NaN fallbacks, and clamping behaviour — these drive every
 * MoS + fair-price numeric display on the ranking table and stock-detail page.
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import { formatMosPct, formatFairPrice, mosColorClass, formatDividendYield } from './format';

// ---------------------------------------------------------------------------
// formatMosPct
// ---------------------------------------------------------------------------

describe('formatMosPct — null / NaN inputs', () => {
  it('returns em-dash display for null', () => {
    const r = formatMosPct(null);
    expect(r.display).toBe('—');
    expect(r.tooltip).toBeNull();
    expect(r.isClamped).toBe(false);
  });

  it('returns em-dash display for NaN', () => {
    const r = formatMosPct(NaN);
    expect(r.display).toBe('—');
    expect(r.tooltip).toBeNull();
    expect(r.isClamped).toBe(false);
  });
});

describe('formatMosPct — lower clamp (< −99)', () => {
  it('clamps values below −99 with the display sentinel', () => {
    const r = formatMosPct(-100);
    expect(r.display).toBe('< −99%');
    expect(r.isClamped).toBe(true);
    expect(r.tooltip).toContain('-100.0%');
    expect(r.tooltip).toContain('clamped');
  });

  it('clamps extreme negative (−9999)', () => {
    const r = formatMosPct(-9999);
    expect(r.display).toBe('< −99%');
    expect(r.isClamped).toBe(true);
  });

  it('does NOT clamp −99 exactly (boundary: −99 is NOT < −99)', () => {
    // −99 is the lower boundary: −99 < −99 is false, so it should NOT clamp.
    const r = formatMosPct(-99);
    expect(r.isClamped).toBe(false);
    expect(r.display).toBe('-99.0%');
  });
});

describe('formatMosPct — upper clamp (> 500)', () => {
  it('clamps values above 500 with the display sentinel', () => {
    const r = formatMosPct(501);
    expect(r.display).toBe('> +500%');
    expect(r.isClamped).toBe(true);
    expect(r.tooltip).toContain('501.0%');
    expect(r.tooltip).toContain('clamped');
  });

  it('clamps a very large positive number', () => {
    const r = formatMosPct(99999);
    expect(r.display).toBe('> +500%');
    expect(r.isClamped).toBe(true);
  });

  it('does NOT clamp 500 exactly (boundary: 500 is NOT > 500)', () => {
    const r = formatMosPct(500);
    expect(r.isClamped).toBe(false);
    expect(r.display).toBe('+500.0%');
  });
});

describe('formatMosPct — in-range values', () => {
  it('renders zero as "+0.0%" with a plus sign', () => {
    const r = formatMosPct(0);
    expect(r.display).toBe('+0.0%');
    expect(r.isClamped).toBe(false);
    expect(r.tooltip).toBeNull();
  });

  it('renders a positive value with a leading "+"', () => {
    const r = formatMosPct(12.345);
    expect(r.display).toBe('+12.3%');
    expect(r.isClamped).toBe(false);
  });

  it('renders a negative value without a "+" prefix', () => {
    const r = formatMosPct(-15.678);
    expect(r.display).toBe('-15.7%');
    expect(r.isClamped).toBe(false);
  });

  it('rounds to 1 decimal place', () => {
    expect(formatMosPct(10.05).display).toBe('+10.1%');
    expect(formatMosPct(-5.04).display).toBe('-5.0%');
  });

  it('handles a small positive MoS (near-fair zone)', () => {
    const r = formatMosPct(3.1);
    expect(r.display).toBe('+3.1%');
  });
});

// ---------------------------------------------------------------------------
// formatFairPrice
// ---------------------------------------------------------------------------

describe('formatFairPrice — null / NaN inputs', () => {
  it('returns em-dash for null', () => {
    expect(formatFairPrice(null)).toBe('—');
  });

  it('returns em-dash for NaN', () => {
    expect(formatFairPrice(NaN)).toBe('—');
  });
});

describe('formatFairPrice — defensive absurd-value guard', () => {
  it('returns em-dash for values >= $1,000,000 (regression guard)', () => {
    expect(formatFairPrice(1_000_000)).toBe('—');
    expect(formatFairPrice(9_999_999)).toBe('—');
  });

  it('formats $999,999.99 normally (just below the absurd threshold)', () => {
    expect(formatFairPrice(999_999.99)).toBe('$999999.99');
  });
});

describe('formatFairPrice — sub-penny guard', () => {
  it('returns "< $0.01" for a value below one cent', () => {
    expect(formatFairPrice(0.001)).toBe('< $0.01');
    expect(formatFairPrice(0.009)).toBe('< $0.01');
    expect(formatFairPrice(0.0)).toBe('< $0.01');
  });

  it('does NOT apply the sub-penny guard at exactly $0.01', () => {
    // 0.01 is NOT < 0.01, so it should render normally.
    expect(formatFairPrice(0.01)).toBe('$0.01');
  });
});

describe('formatFairPrice — normal range', () => {
  it('formats a typical stock price to 2 decimal places', () => {
    expect(formatFairPrice(123.456)).toBe('$123.46');
    expect(formatFairPrice(50.0)).toBe('$50.00');
  });

  it('rounds correctly at the half-cent boundary', () => {
    expect(formatFairPrice(10.005)).toBe('$10.01');
    expect(formatFairPrice(10.004)).toBe('$10.00');
  });

  it('formats a high-price stock (e.g. BRK.A style) correctly', () => {
    expect(formatFairPrice(500_000)).toBe('$500000.00');
  });
});

// ---------------------------------------------------------------------------
// mosColorClass
// ---------------------------------------------------------------------------

describe('mosColorClass — null / NaN inputs', () => {
  it('returns the muted slate class for null', () => {
    expect(mosColorClass(null)).toBe('text-slate-400');
  });

  it('returns the muted slate class for NaN', () => {
    expect(mosColorClass(NaN)).toBe('text-slate-400');
  });
});

describe('mosColorClass — tier mapping', () => {
  it('returns emerald-700 for strongly undervalued MoS (>= 20)', () => {
    expect(mosColorClass(20)).toBe('text-emerald-700');
    expect(mosColorClass(50)).toBe('text-emerald-700');
    expect(mosColorClass(500)).toBe('text-emerald-700');
  });

  it('returns emerald-600 for mildly positive MoS (0 < mos < 20)', () => {
    expect(mosColorClass(0.1)).toBe('text-emerald-600');
    expect(mosColorClass(10)).toBe('text-emerald-600');
    expect(mosColorClass(19.9)).toBe('text-emerald-600');
  });

  it('returns slate-500 for small negative MoS (−20 < mos <= 0)', () => {
    expect(mosColorClass(0)).toBe('text-slate-500');
    expect(mosColorClass(-10)).toBe('text-slate-500');
    expect(mosColorClass(-19.9)).toBe('text-slate-500');
  });

  it('returns rose-600 for deeply overvalued MoS (<= −20)', () => {
    expect(mosColorClass(-20)).toBe('text-rose-600');
    expect(mosColorClass(-50)).toBe('text-rose-600');
    expect(mosColorClass(-100)).toBe('text-rose-600');
  });
});

describe('mosColorClass — boundary precision', () => {
  it('boundary at 20 belongs to emerald-700 (>= 20)', () => {
    expect(mosColorClass(20)).toBe('text-emerald-700');
  });

  it('boundary at 0 belongs to slate-500 (> 0 is false, > -20 is true)', () => {
    // 0 is not > 0 (fails the emerald-600 branch) but is > -20 → slate-500.
    expect(mosColorClass(0)).toBe('text-slate-500');
  });

  it('boundary at −20 belongs to rose-600 (not > −20)', () => {
    expect(mosColorClass(-20)).toBe('text-rose-600');
  });
});

// ---------------------------------------------------------------------------
// formatDividendYield — three display states
// ---------------------------------------------------------------------------
//
// Mirrors the HeroAttributeTiles "Dividend" tile contract:
//   - Payer (yield > 0)             → "X.XX%"  (always 2 decimal places)
//   - Confirmed non-payer (yield === 0 OR paysDividend === false) → "None"
//   - Unavailable (yield === null)  → "—"
//
// IMPORTANT: dividendYieldPct is in PERCENT on the wire (2.67 = 2.67%).
// ---------------------------------------------------------------------------

describe('formatDividendYield — unavailable (null yield)', () => {
  it('returns em-dash when yield is null', () => {
    expect(formatDividendYield(null, null)).toBe('—');
  });

  it('returns em-dash when yield is null even if paysDividend is true', () => {
    // Null yield wins — data is unavailable regardless of the boolean.
    expect(formatDividendYield(null, true)).toBe('—');
  });

  it('returns em-dash when yield is null and paysDividend is false', () => {
    expect(formatDividendYield(null, false)).toBe('—');
  });
});

describe('formatDividendYield — confirmed non-payer', () => {
  it('returns "None" when yield is 0', () => {
    expect(formatDividendYield(0, null)).toBe('None');
  });

  it('returns "None" when yield is 0 and paysDividend is false', () => {
    expect(formatDividendYield(0, false)).toBe('None');
  });

  it('returns "None" when paysDividend is explicitly false (even if yield is positive)', () => {
    // Schema contract: paysDividend === false means confirmed non-payer.
    // A positive yield with false paysDividend is an anomalous state — "None"
    // is the conservative display.
    expect(formatDividendYield(2.67, false)).toBe('None');
  });
});

describe('formatDividendYield — payer (yield > 0)', () => {
  it('formats a typical dividend yield to 2 decimal places', () => {
    expect(formatDividendYield(2.67, true)).toBe('2.67%');
  });

  it('formats a small yield correctly', () => {
    expect(formatDividendYield(0.50, true)).toBe('0.50%');
  });

  it('formats a high yield correctly (e.g. a REIT)', () => {
    expect(formatDividendYield(8.12, true)).toBe('8.12%');
  });

  it('rounds to 2 decimal places (JS toFixed semantics)', () => {
    // Due to IEEE 754 binary floating-point, 2.675 is actually stored as
    // slightly below 2.675, so toFixed(2) gives "2.67", not "2.68".
    // Use exact representable midpoints to test the round-half-up path.
    expect(formatDividendYield(2.675, true)).toBe('2.67%'); // IEEE 754 sub-half
    expect(formatDividendYield(2.685, true)).toBe('2.69%'); // rounds up
    expect(formatDividendYield(2.674, true)).toBe('2.67%');
    expect(formatDividendYield(2.676, true)).toBe('2.68%');
  });

  it('works when paysDividend is null (yield alone is enough to know it pays)', () => {
    // paysDividend is present on schema 0.10.27+; null on older snapshots.
    // A non-null positive yield should still render as a payer even without
    // the boolean.
    expect(formatDividendYield(3.14, null)).toBe('3.14%');
  });
});
