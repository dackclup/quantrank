/**
 * Contract test for the F3 fix — headline outperformance (periodPortfolio /
 * periodBenchmark) in AiPickPortfolio.tsx's buildView() MUST be derived from
 * the unrounded NAV-series ratios (last finite value from startIdx onward /
 * the anchor), NOT from the chart points' Math.round-ed dollar values.
 *
 * Rounding each series to the nearest dollar of CHART_BASE=10000 quantizes
 * each side to ~1bp before the delta is taken — for a near-zero true spread
 * this can silently zero out (or worse, invert) the displayed delta. This
 * test mirrors the two derivation paths independently (consistent with the
 * project's pure-function contract-test pattern — see
 * HoldingsTimeline.test.ts / RankingTable.test.ts, which mirror rather than
 * import component-internal logic) and proves they diverge for a crafted
 * near-zero-spread input, then asserts the CORRECT (unrounded) derivation is
 * exact.
 *
 * Run: cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';

function isFinite_(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && !Number.isNaN(v);
}

function firstFiniteFrom(series: (number | null)[], start: number): number | null {
  for (let i = start; i < series.length; i += 1) {
    if (isFinite_(series[i])) return series[i] as number;
  }
  return null;
}

function lastFiniteFrom(series: (number | null)[], start: number): number | null {
  for (let i = series.length - 1; i >= start; i -= 1) {
    if (isFinite_(series[i])) return series[i] as number;
  }
  return null;
}

// FIXED derivation — mirrors buildView() post-F3-fix: unrounded anchor + last
// finite value directly off the raw NAV series, no chart-point rounding.
function periodReturnUnrounded(series: (number | null)[], startIdx: number): number | null {
  const anchor = firstFiniteFrom(series, startIdx);
  const last = anchor != null ? lastFiniteFrom(series, startIdx) : null;
  return anchor && last != null ? (last / anchor - 1) * 100 : null;
}

// PRE-FIX (buggy) derivation — mirrors buildView() before the F3 fix: the
// series is first quantized to the nearest whole dollar of `capital` (the
// same rounding the chart points use for display), THEN the return is
// derived from that already-rounded dollar figure. Retained here ONLY to
// prove the fix changes behavior on a crafted near-zero-spread input.
function periodReturnFromRoundedChartPoint(
  series: (number | null)[],
  startIdx: number,
  capital: number,
): number | null {
  const anchor = firstFiniteFrom(series, startIdx);
  if (!anchor) return null;
  const lastRaw = series.length > 0 ? series[series.length - 1] : null;
  if (!isFinite_(lastRaw)) return null;
  const roundedDollar = Math.round((lastRaw / anchor) * capital);
  return (roundedDollar / capital - 1) * 100;
}

describe('AiPickPortfolio buildView — F3 unrounded period-return derivation', () => {
  const CHART_BASE = 10_000;

  it('matches simple exact math for a plain 2-point series (no rounding involved)', () => {
    // +5% over the window.
    const series = [10_000, 10_500];
    expect(periodReturnUnrounded(series, 0)).toBeCloseTo(5, 10);
  });

  it('skips trailing nulls to find the true last finite value (benchmark series can end early)', () => {
    // Benchmark line stops updating for the last two points (all trailing
    // nulls) — the period return must still resolve off the last REAL value,
    // not null.
    const series = [10_000, 10_100, 10_200, null, null];
    expect(periodReturnUnrounded(series, 0)).toBeCloseTo(2, 10);
  });

  it('returns null when the window has no finite anchor', () => {
    expect(periodReturnUnrounded([null, null], 0)).toBeNull();
  });

  it('honors startIdx — only considers the window from startIdx onward', () => {
    const series = [9_000, 10_000, 10_300];
    // Anchor is series[1] (startIdx=1), not series[0].
    expect(periodReturnUnrounded(series, 1)).toBeCloseTo(3, 10);
  });

  it('REGRESSION GUARD (F3): diverges from the pre-fix rounded-chart-point derivation on a near-zero true spread', () => {
    // Portfolio: true ratio is +0.0049% over the window (net_last just below
    // the $10000.50 rounding boundary) — the OLD path rounds this whole-cent
    // move away to exactly $10000 (0.0% displayed), silently discarding a
    // real (if tiny) lead.
    const net = [CHART_BASE, CHART_BASE + 0.49];
    // Benchmark: true ratio is -0.0049% (net_last just above the $9999.50
    // rounding boundary) — the OLD path ALSO rounds this to exactly $10000
    // (0.0% displayed).
    const bench = [CHART_BASE, CHART_BASE - 0.49];

    const fixedPortfolio = periodReturnUnrounded(net, 0);
    const fixedBenchmark = periodReturnUnrounded(bench, 0);
    const buggyPortfolio = periodReturnFromRoundedChartPoint(net, 0, CHART_BASE);
    const buggyBenchmark = periodReturnFromRoundedChartPoint(bench, 0, CHART_BASE);

    // Correct (unrounded) values are the exact tiny non-zero spread.
    expect(fixedPortfolio).toBeCloseTo(0.0049, 6);
    expect(fixedBenchmark).toBeCloseTo(-0.0049, 6);
    const fixedDelta = (fixedPortfolio as number) - (fixedBenchmark as number);
    expect(fixedDelta).toBeCloseTo(0.0098, 6);

    // The pre-fix path collapses BOTH sides to a 0.0% tie, hiding the real
    // (if small) portfolio lead entirely — proving the fix is load-bearing.
    expect(buggyPortfolio).toBe(0);
    expect(buggyBenchmark).toBe(0);
    expect(buggyPortfolio).not.toBeCloseTo(fixedPortfolio as number, 4);
    expect(buggyBenchmark).not.toBeCloseTo(fixedBenchmark as number, 4);
  });
});
