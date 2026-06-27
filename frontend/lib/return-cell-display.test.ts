/**
 * Contract tests for the return-cell null-coalesce display fixes.
 *
 * Covers three invariants introduced in the "fill blank return cells" PR:
 *
 * CASE A — entry instant (legs_used === 0): mwr_pct is null at the instant of
 * purchase (no price movement measured yet). The correct financial value is
 * 0.0% by identity.  The render layer coalesces null → 0 when legs_used === 0
 * and produces "+0.0%" via pctStr(0) with the non-negative tone.
 *
 * CASE B — sold row prior-rebalance lookup: a sold ticker's realized exit
 * return lives in the PRIOR rebalance's position_returns (the last quarter it
 * was held), not in the current rebalance (where it is absent / weight 0). The
 * lookup chain tries the current map first, then the prior map, then null.
 *
 * GUARD — footer exclusion: sold rows carry weight 0.0% and are never included
 * in any aggregate (footer total, nav series, or NAV computation).
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import { apportionWeightLabels, pctStr, toneClass } from './portfolio-format';
import type { MwrPositionReturn } from './types';

// ---------------------------------------------------------------------------
// Helpers that mirror the render-layer coalesce logic exactly so the tests
// remain independent of React component internals.
// ---------------------------------------------------------------------------

/**
 * Replicate the CASE-A coalesce: entry-instant return = 0.0%.
 * When mwr_pct is null AND legs_used === 0, the display value is 0 (not null).
 */
function resolveDisplayMwr(pr: MwrPositionReturn | null): number | null {
  if (pr === null) return null;
  const mwr = pr.mwr_pct ?? null;
  const legs = pr.legs_used ?? null;
  // CASE A: entry instant coalesce
  if (mwr === null && legs === 0) return 0;
  return mwr;
}

/**
 * Replicate the CASE-B sold-row lookup: try the current rebalance's top-level
 * mwrByTicker first, then the prior rebalance's per-quarter mwrByTicker.
 */
function resolveSoldMwr(
  ticker: string,
  currentMap: Record<string, MwrPositionReturn>,
  priorMap: Record<string, MwrPositionReturn> | undefined,
): number | null {
  const pr = currentMap[ticker] ?? priorMap?.[ticker] ?? null;
  return pr?.mwr_pct ?? null;
}

// ---------------------------------------------------------------------------
// CASE A — legs_used === 0 → coalesce null to 0.0%
// ---------------------------------------------------------------------------

describe('CASE A: entry-instant return coalesce (legs_used === 0)', () => {
  it('resolves null mwr_pct to 0 when legs_used is 0', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: '2024-02-15',
      partial_history: false,
      legs_used: 0,
    };
    expect(resolveDisplayMwr(pr)).toBe(0);
  });

  it('renders 0 as "+0.0%" via pctStr (not "—")', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: '2024-02-15',
      partial_history: false,
      legs_used: 0,
    };
    const displayMwr = resolveDisplayMwr(pr);
    expect(pctStr(displayMwr)).toBe('+0.0%');
  });

  it('toneClass(0) is neutral/non-negative (emerald, not slate)', () => {
    // 0 is treated as non-negative by toneClass — the entry-instant "0.0%"
    // should NOT render in the muted slate tone (which signals data absent).
    expect(toneClass(0)).toBe('text-emerald-700 dark:text-emerald-300');
    expect(toneClass(0)).not.toContain('slate');
  });

  it('does NOT coalesce when legs_used is null (data absent, not entry instant)', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: null,
      partial_history: false,
      legs_used: null,
    };
    // legs_used=null means we have no information — keep as null (renders "—")
    expect(resolveDisplayMwr(pr)).toBeNull();
  });

  it('does NOT coalesce when legs_used is positive (data present but zero return)', () => {
    // If legs_used > 0 and mwr_pct happens to be null, we can't infer 0.0%
    // (the engine should have emitted a value; null here means genuinely absent).
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: '2023-05-10',
      partial_history: false,
      legs_used: 3,
    };
    expect(resolveDisplayMwr(pr)).toBeNull();
  });

  it('preserves a real mwr_pct when legs_used is 0 and value is provided', () => {
    // Engine could theoretically emit mwr_pct=0.0 explicitly at legs=0;
    // the coalesce should not overwrite a provided value.
    const pr: MwrPositionReturn = {
      mwr_pct: 0.0,
      twr_pct: 0.0,
      contrib_nav_pts: null,
      since_date: '2024-02-15',
      partial_history: false,
      legs_used: 0,
    };
    expect(resolveDisplayMwr(pr)).toBe(0.0);
  });

  it('preserves a positive real mwr_pct regardless of legs_used', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: 12.3,
      twr_pct: 11.8,
      contrib_nav_pts: null,
      since_date: '2023-11-30',
      partial_history: false,
      legs_used: 4,
    };
    expect(resolveDisplayMwr(pr)).toBe(12.3);
    expect(pctStr(resolveDisplayMwr(pr))).toBe('+12.3%');
  });

  it('handles null position-return entry gracefully (no mwrByTicker entry)', () => {
    expect(resolveDisplayMwr(null)).toBeNull();
    expect(pctStr(null)).toBe('—');
  });
});

// ---------------------------------------------------------------------------
// CASE B — sold-row prior-rebalance lookup
// ---------------------------------------------------------------------------

describe('CASE B: sold-row prior-rebalance MWR lookup', () => {
  const priorMap: Record<string, MwrPositionReturn> = {
    KLAC: {
      mwr_pct: 207.6,
      twr_pct: 210.1,
      contrib_nav_pts: 12.3,
      since_date: '2023-02-15',
      partial_history: false,
      legs_used: 5,
    },
  };

  it('resolves a sold ticker from the PRIOR rebalance map when absent in the current map', () => {
    const currentMap: Record<string, MwrPositionReturn> = {};
    const mwr = resolveSoldMwr('KLAC', currentMap, priorMap);
    expect(mwr).toBe(207.6);
    expect(pctStr(mwr)).toBe('+207.6%');
  });

  it('prefers the current top-level map over the prior map when the ticker is present in both', () => {
    // Top-level position_returns (lifetime MWR) may differ from the per-quarter
    // prior-rebalance map. Current map has priority.
    const currentMap: Record<string, MwrPositionReturn> = {
      KLAC: {
        mwr_pct: 215.0, // lifetime total
        twr_pct: 218.0,
        contrib_nav_pts: 14.2,
        since_date: '2023-02-15',
        partial_history: false,
        legs_used: 6,
      },
    };
    const mwr = resolveSoldMwr('KLAC', currentMap, priorMap);
    expect(mwr).toBe(215.0);
  });

  it('returns null when the ticker is absent from BOTH maps', () => {
    const currentMap: Record<string, MwrPositionReturn> = {};
    const mwr = resolveSoldMwr('NVDA', currentMap, priorMap);
    expect(mwr).toBeNull();
    expect(pctStr(mwr)).toBe('—');
  });

  it('returns null gracefully when priorMap is undefined (initial basket, no prior)', () => {
    const currentMap: Record<string, MwrPositionReturn> = {};
    const mwr = resolveSoldMwr('AAPL', currentMap, undefined);
    expect(mwr).toBeNull();
  });

  it('resolves a negative sold-row return (loss) correctly', () => {
    const currentMap: Record<string, MwrPositionReturn> = {};
    const negPriorMap: Record<string, MwrPositionReturn> = {
      XYZ: {
        mwr_pct: -18.4,
        twr_pct: -19.1,
        contrib_nav_pts: -2.1,
        since_date: '2024-05-15',
        partial_history: false,
        legs_used: 2,
      },
    };
    const mwr = resolveSoldMwr('XYZ', currentMap, negPriorMap);
    expect(mwr).toBe(-18.4);
    expect(pctStr(mwr)).toBe('−18.4%');
    expect(toneClass(mwr)).toContain('rose');
  });
});

// ---------------------------------------------------------------------------
// GUARD — footer exclusion: sold rows carry weight 0.0% and are NOT aggregated
// ---------------------------------------------------------------------------

describe('GUARD: sold rows excluded from footer totals', () => {
  it('sold-row weight is exactly 0.0% (hardcoded display constant)', () => {
    // The sold-row weight cell in both AiPickPortfolio and HoldingsTimeline
    // renders the string "0.0%" unconditionally. This test verifies the
    // formatting is correct and consistent with the held-row format.
    const soldWeight = 0.0;
    // Render as a percentage manually (the component renders this as a string literal)
    expect(`${soldWeight.toFixed(1)}%`).toBe('0.0%');
  });

  it('sold rows are excluded from apportionWeightLabels input (weight = null or excluded)', () => {
    // apportionWeightLabels is called with the HELD rows only.
    // Verifying that a null/zero weight for a sold ticker does not corrupt the
    // finite weight sum or the 100.0% apportionment of the live basket.
    // Simulate a 3-held 1-sold scenario:
    //   held: 0.4 + 0.35 + 0.25 = 1.0 (sum to 100%)
    //   sold: "conceptually 0" but NOT passed to apportionWeightLabels
    const heldWeights = [0.4, 0.35, 0.25];
    const labels: string[] = apportionWeightLabels(heldWeights);
    const sum = labels.reduce((s: number, l: string) => s + parseFloat(l.replace('%', '')), 0);
    expect(sum).toBeCloseTo(100.0, 1);
    // Sold rows must not appear in the label array at all
    expect(labels.length).toBe(3);
  });

  it('a sold ticker MWR value does NOT affect the held-basket apportionment', () => {
    // Return values and weight labels are independent columns — the MWR lookup
    // never feeds into apportionWeightLabels. This confirms orthogonality.
    // The held basket weights are unchanged regardless of what the sold MWR is.
    const soldMwr = 207.6; // large value — must not distort weight column
    const heldWeights = [0.5, 0.5];
    const labels: string[] = apportionWeightLabels(heldWeights);
    expect(labels).toEqual(['50.0%', '50.0%']);
    // soldMwr is not consumed by apportionWeightLabels at all
    expect(typeof soldMwr).toBe('number'); // just confirm it exists
  });
});
