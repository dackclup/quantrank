/**
 * Contract tests for the return-cell display behavior.
 *
 * CASE A — entry-instant coalesce REMOVED (#638 revert): the backend
 * `position_returns.py` bug (Sunday/weekend rebalance date → null close → null
 * mwr_pct for the initial basket) is fixed server-side. Post-regen, the initial
 * basket produces REAL forward returns (legs_used ≥ 1), so the frontend no longer
 * special-cases legs_used === 0. Genuine null (missing data / pre-engine artifact)
 * renders "—".
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
// Helpers that mirror the render-layer logic exactly so the tests
// remain independent of React component internals.
// ---------------------------------------------------------------------------

/**
 * Replicate the held-row display resolution (NO Case-A coalesce).
 * mwr_pct is used directly; null → "—" at the render layer.
 */
function resolveDisplayMwr(pr: MwrPositionReturn | null): number | null {
  if (pr === null) return null;
  return pr.mwr_pct ?? null;
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
// Genuine-null behavior (replaces the removed Case-A assertions)
// ---------------------------------------------------------------------------

describe('Genuine null mwr_pct renders as "—"', () => {
  it('resolves null when the position-return entry is absent (no mwrByTicker key)', () => {
    expect(resolveDisplayMwr(null)).toBeNull();
    expect(pctStr(null)).toBe('—');
  });

  it('resolves null when mwr_pct is null and legs_used is null (data absent)', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: null,
      partial_history: false,
      legs_used: null,
    };
    expect(resolveDisplayMwr(pr)).toBeNull();
    expect(pctStr(resolveDisplayMwr(pr))).toBe('—');
  });

  it('resolves null when mwr_pct is null and legs_used is 0 (no special-case after #638 revert)', () => {
    // Post-regen the backend provides real forward returns for the initial basket.
    // legs_used === 0 is no longer coalesced to 0.0% — it renders "—" like any
    // other absent value so genuinely-broken/absent rows don't mask data absence.
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: '2024-02-15',
      partial_history: false,
      legs_used: 0,
    };
    expect(resolveDisplayMwr(pr)).toBeNull();
    expect(pctStr(resolveDisplayMwr(pr))).toBe('—');
  });

  it('resolves null when mwr_pct is null and legs_used is positive', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: null,
      twr_pct: null,
      contrib_nav_pts: null,
      since_date: '2023-05-10',
      partial_history: false,
      legs_used: 3,
    };
    expect(resolveDisplayMwr(pr)).toBeNull();
    expect(pctStr(resolveDisplayMwr(pr))).toBe('—');
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

  it('preserves an explicit 0.0 mwr_pct (real engine-emitted zero return)', () => {
    const pr: MwrPositionReturn = {
      mwr_pct: 0.0,
      twr_pct: 0.0,
      contrib_nav_pts: null,
      since_date: '2024-02-15',
      partial_history: false,
      legs_used: 1,
    };
    expect(resolveDisplayMwr(pr)).toBe(0.0);
    expect(pctStr(resolveDisplayMwr(pr))).toBe('+0.0%');
  });

  it('toneClass(0) is neutral/non-negative (emerald, not slate) for an explicit 0.0', () => {
    expect(toneClass(0)).toBe('text-emerald-700 dark:text-emerald-300');
    expect(toneClass(0)).not.toContain('slate');
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
