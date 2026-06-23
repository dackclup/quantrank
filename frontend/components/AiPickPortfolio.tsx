'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { flagLabel } from '@/lib/flag-labels';

import { NavCompareChartLazy } from './NavCompareChartLazy';
import { AnnualReturnsTable } from './AnnualReturnsTable';
import { PerformanceTable } from './PerformanceTable';
import { HoldingsCountSlider } from './HoldingsCountSlider';
import { HoldingsTimeline } from './HoldingsTimeline';
import { Chip } from './Chip';
import { SectorChip } from './SectorChip';
import { SegmentedSelector, type SegmentOption } from './SegmentedSelector';
import type { AiPickData, AiPickTimelineEntry } from '@/lib/types';

const PERIODS: readonly { value: string; label: string; years: number }[] = [
  { value: '1Y', label: '1Y', years: 1 },
  { value: '3Y', label: '3Y', years: 3 },
  { value: '5Y', label: '5Y', years: 5 },
  { value: '7Y', label: '7Y', years: 7 },
  { value: 'MAX', label: 'Max', years: 100 },
];

const BENCHMARKS: readonly SegmentOption[] = [
  { value: 'spy', label: 'SPY' },
  { value: 'qqq', label: 'QQQ' },
  { value: 'dia', label: 'DIA' },
  { value: 'iwm', label: 'IWM' },
];

const MAX_CHART_POINTS = 180;

// Notional initial capital — both lines start here at the window's start and
// grow to their final value (Jitta-style growth-of-$10k framing).
const CHART_BASE = 10_000;

function isFinite_(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && !Number.isNaN(v);
}

// Largest-remainder (Hamilton) apportionment so the DISPLAYED 1-decimal weight
// percentages sum to exactly the basket total (100.0% for a normalized
// inverse-vol book). Raw weights sum to 1.0, but independent toFixed(1) rounding
// drifts the visible column to 99.9 / 100.1 / 100.2% — this removes that drift.
// Non-finite weights render '—' and are excluded from the apportionment; the
// target total honestly tracks the finite-weight sum (so a genuinely <100% book
// would still show <100%, just without per-row rounding noise).
function apportionWeightLabels(weights: (number | null | undefined)[]): string[] {
  const labels = weights.map(() => '—');
  const finiteIdx: number[] = [];
  weights.forEach((w, i) => { if (isFinite_(w)) finiteIdx.push(i); });
  if (finiteIdx.length === 0) return labels;
  const sumFinite = finiteIdx.reduce((s, i) => s + (weights[i] as number), 0);
  const target = Math.round(sumFinite * 1000);              // tenths of a percent (1000 = 100.0%)
  const tenths = finiteIdx.map((i) => (weights[i] as number) * 1000);
  const floors = tenths.map((t) => Math.floor(t));
  const used = floors.reduce((s, f) => s + f, 0);
  let remaining = Math.max(0, target - used);               // +0.1% units left to distribute
  const order = floors
    .map((_, k) => k)
    .sort((a, b) => (tenths[b] - floors[b]) - (tenths[a] - floors[a])); // largest fractional remainder first
  const add = floors.map(() => 0);
  for (let k = 0; k < order.length && remaining > 0; k += 1) { add[order[k]] = 1; remaining -= 1; }
  finiteIdx.forEach((i, k) => { labels[i] = `${((floors[k] + add[k]) / 10).toFixed(1)}%`; });
  return labels;
}

function money$(v: number | null): string {
  if (v === null) return '—';
  const abs = Math.abs(v);
  if (abs >= 1e18) return `$${(v / 1e18).toFixed(1)}Qi`;
  if (abs >= 1e15) return `$${(v / 1e15).toFixed(1)}Q`;
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (abs >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6)  return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3)  return `$${(v / 1e3).toFixed(0)}k`;
  return `$${Math.round(v)}`;
}

function firstFiniteFrom(series: (number | null)[], start: number): number | null {
  for (let i = start; i < series.length; i += 1) {
    if (isFinite_(series[i])) return series[i] as number;
  }
  return null;
}


function startIndexForYears(dates: string[], years: number): number {
  if (dates.length === 0) return 0;
  const last = new Date(`${dates[dates.length - 1]}T00:00:00Z`);
  last.setUTCFullYear(last.getUTCFullYear() - years);
  const cutoff = last.toISOString().slice(0, 10);
  for (let i = 0; i < dates.length; i += 1) {
    if (dates[i] >= cutoff) return i;
  }
  return 0;
}

function pctStr(v: number | null): string {
  if (v === null) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(1)}%`;
}

function toneClass(v: number | null): string {
  if (v === null) return 'text-slate-500 dark:text-slate-400';
  return v >= 0 ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300';
}

// Relative weight change vs the prior quarter for the Current-picks "Change"
// column. New (no prior weight) = +100%, Sold (no current weight) = −100%,
// otherwise (cur−prior)/prior. Arrow + signed text + 3-way tone.
function weightChange(current: number | null | undefined, prior: number | null | undefined) {
  const c = isFinite_(current) ? current : 0;
  const p = isFinite_(prior) ? prior : 0;
  const POS = 'text-emerald-700 dark:text-emerald-300';
  const NEG = 'text-rose-700 dark:text-rose-300';
  const NEU = 'text-slate-500 dark:text-slate-400';
  if (p === 0 && c > 0) return { arrow: '↑', text: '100.00%', tone: POS };
  if (c === 0 && p > 0) return { arrow: '↓', text: '−100.00%', tone: NEG };
  if (p === 0) return { arrow: '→', text: '0.00%', tone: NEU };
  const rel = ((c - p) / p) * 100;
  if (rel > 0) return { arrow: '↑', text: `${rel.toFixed(2)}%`, tone: POS };
  if (rel < 0) return { arrow: '↓', text: `−${Math.abs(rel).toFixed(2)}%`, tone: NEG };
  return { arrow: '→', text: '0.00%', tone: NEU };
}

// ---------------------------------------------------------------------------
// Shared chart-view builder — used by both adaptive + slider branches.
// ---------------------------------------------------------------------------
function buildView(
  net: (number | null)[],
  gross: (number | null)[],
  cons: (number | null)[],
  bser: (number | null)[],
  dates: string[],
  period: string,
  capital: number,
) {
  const years = PERIODS.find((p) => p.value === period)?.years ?? 5;
  const startIdx = startIndexForYears(dates, years);
  const pAnchor = firstFiniteFrom(net, startIdx);
  const gAnchor = firstFiniteFrom(gross, startIdx);
  const cAnchor = firstFiniteFrom(cons, startIdx);
  const bAnchor = firstFiniteFrom(bser, startIdx);

  const span = dates.length - startIdx;
  const step = Math.max(1, Math.ceil(span / MAX_CHART_POINTS));
  const point = (i: number) => ({
    date: dates[i],
    portfolio: pAnchor && isFinite_(net[i]) ? Math.round((net[i] as number) / pAnchor * capital) : null,
    benchmark: bAnchor && isFinite_(bser[i]) ? Math.round((bser[i] as number) / bAnchor * capital) : null,
    yearStart: false,
  });
  const points: ReturnType<typeof point>[] = [];
  for (let i = startIdx; i < dates.length; i += step) points.push(point(i));
  if (dates.length > 0 && (dates.length - 1 - startIdx) % step !== 0) {
    points.push(point(dates.length - 1));
  }
  // Mark the first sampled point of each calendar year — NavCompareChart draws
  // a hollow ring there and uses these as the year x-axis ticks (Jitta look).
  let prevYear = '';
  for (const p of points) {
    const yr = p.date.slice(0, 4);
    p.yearStart = yr !== prevYear;
    prevYear = yr;
  }

  const lastPoint = points[points.length - 1];
  // 1Y → quarterly · 3Y → semi-annual · 5Y+ → yearly boundary points
  const tickMode: 'quarter' | 'halfyear' | 'year' =
    years <= 1 ? 'quarter' : years <= 3 ? 'halfyear' : 'year';
  const thinPoints: typeof points[0][] = [];
  if (tickMode !== 'year') {
    let prevBucket = '';
    for (const p of points) {
      const [y, m] = p.date.split('-');
      const bucket = tickMode === 'quarter'
        ? `${y}-${Math.ceil(Number(m) / 3)}`
        : `${y}-${Math.ceil(Number(m) / 6)}`;
      if (bucket !== prevBucket) { p.yearStart = true; thinPoints.push(p); prevBucket = bucket; }
    }
  } else {
    for (const p of points) { if (p.yearStart) thinPoints.push(p); }
  }
  if (lastPoint && thinPoints[thinPoints.length - 1] !== lastPoint) {
    thinPoints.push(lastPoint);
  }
  const retFromBase = (v: number | null | undefined) =>
    v === null || v === undefined ? null : (v / capital - 1) * 100;
  const lastGross = gross.length > 0 ? gross[gross.length - 1] : null;
  const lastCons = cons.length > 0 ? cons[cons.length - 1] : null;
  const periodGross = gAnchor && lastGross != null ? (lastGross / gAnchor - 1) * 100 : null;
  const periodConservative = cAnchor && lastCons != null ? (lastCons / cAnchor - 1) * 100 : null;
  return {
    points: thinPoints,
    tickMode,
    endPortfolio: lastPoint ? lastPoint.portfolio : null,
    endBenchmark: lastPoint ? lastPoint.benchmark : null,
    periodPortfolio: lastPoint ? retFromBase(lastPoint.portfolio) : null,
    periodBenchmark: lastPoint ? retFromBase(lastPoint.benchmark) : null,
    periodGross,
    periodConservative,
    periodStart: dates[startIdx] ?? null,
  };
}

// ---------------------------------------------------------------------------
// Portfolio-sense held-set helper — mirrors HoldingsTimeline's per-entry
// membership derivation exactly (HoldingsTimeline.tsx lines ~66-92).
//
// Rule:
//   When the entry has a non-empty bandBook → the held set IS that array.
//   Otherwise → sliceCount = bandHeldCount ?? adaptiveCount; held set is the
//   holdings prefix sliced to that count. If both counts are absent, use all
//   holdings tickers (full fallback).
//
// This must stay identical to HoldingsTimeline's logic so the "Current picks"
// Status column and the "Rotation history" held/buy split never disagree.
// ---------------------------------------------------------------------------
function heldSetForEntry(entry: AiPickTimelineEntry): Set<string> {
  const hasBandBook = Array.isArray(entry.bandBook) && entry.bandBook.length > 0;
  if (hasBandBook) {
    return new Set(entry.bandBook as string[]);
  }
  const sliceCount = entry.bandHeldCount ?? entry.adaptiveCount;
  const tickers = sliceCount !== undefined
    ? entry.holdings.slice(0, sliceCount).map((h) => h.ticker)
    : entry.holdings.map((h) => h.ticker);
  return new Set(tickers);
}

// ---------------------------------------------------------------------------
// ADAPTIVE branch — shown when data.adaptive is non-null.
// The slider is removed; the AI sizes the basket automatically.
// ---------------------------------------------------------------------------
function AiPickAdaptiveBranch({ data }: { data: AiPickData }) {
  const { meta, dates, benchmark, timeline, vetoLayerReplayed, vetoesNotReplayed } = data;
  // adaptive is guaranteed non-null in this branch (the parent gates on it)
  const adaptive = data.adaptive!;

  const [bench, setBench] = useState<string>(meta.default_benchmark);
  const [period, setPeriod] = useState<string>('MAX');
  const [capital, setCapital] = useState<number>(CHART_BASE);

  const benchLabel = (BENCHMARKS.find((b) => b.value === bench)?.label ?? bench).toUpperCase();
  const portfolioLabel = `AI pick · adaptive`;

  const bser = useMemo(() => benchmark[bench] ?? [], [benchmark, bench]);

  const view = useMemo(
    () => buildView(adaptive.net, adaptive.gross, adaptive.conservative, bser, dates, period, capital),
    [adaptive.net, adaptive.gross, adaptive.conservative, bser, dates, period, capital],
  );

  const { latestCount, latestHoldings, latestBandHoldings, holdBandMin, rule, finals } = adaptive;
  // STATE 1 (band): use band_book order + band_weights; STATE 2: prefix book.
  const isBand = holdBandMin !== undefined && latestBandHoldings !== undefined;
  const displayHoldings = isBand ? latestBandHoldings! : latestHoldings;
  const displayCount = isBand ? latestBandHoldings!.length : latestCount;

  // Portfolio-sense "held" set: tickers present in the PRIOR quarter's basket.
  // Mirrors HoldingsTimeline's per-entry membership derivation exactly via
  // heldSetForEntry(). Edge case: timeline.length < 2 → initial basket only,
  // no prior quarter exists → every row is New (matches HoldingsTimeline's
  // i===0 initial-basket rule where entered = empty set → all rows are buys).
  const priorHeldSet = useMemo((): Set<string> => {
    if (timeline.length < 2) return new Set<string>();
    return heldSetForEntry(timeline[timeline.length - 2]);
  }, [timeline]);

  // Weight-descending sort for the "Current picks" table. Derived copy so
  // displayHoldings (used by held-set / topSector / displayCount above) is
  // never mutated. Non-finite weights sort to the bottom; equal weights keep
  // their original composite-score order (stable — spread preserves index).
  const weightSortedHoldings = useMemo(
    () =>
      [...displayHoldings].sort((a, b) => {
        const aFin = isFinite_(a.weight);
        const bFin = isFinite_(b.weight);
        if (aFin && bFin) return (b.weight as number) - (a.weight as number);
        if (aFin) return -1; // a finite, b not → a goes first
        if (bFin) return 1;  // b finite, a not → b goes first
        return 0;            // both non-finite → preserve original order
      }),
    [displayHoldings],
  );

  // Hamilton apportionment: displayed 1-decimal weight labels summing to
  // exactly the basket total (removes per-row toFixed(1) rounding drift).
  const weightLabels = useMemo(
    () => apportionWeightLabels(weightSortedHoldings.map((h) => h.weight)),
    [weightSortedHoldings],
  );

  // SOLD rows — tickers in the prior quarter's basket that are NOT in the
  // current basket. Derived from priorHeldSet (already computed above) and
  // the current basket membership. Edge cases: timeline.length < 2 means
  // priorHeldSet is empty (initial basket only) → soldTickers is empty →
  // no sold rows rendered. Sorted alphabetically for deterministic order.
  const soldRows = useMemo((): Array<{ ticker: string; sector: string }> => {
    if (timeline.length < 2) return [];
    const currentTickerSet = new Set(displayHoldings.map((h) => h.ticker));
    const soldTickers = [...priorHeldSet].filter((t) => !currentTickerSet.has(t)).sort();
    if (soldTickers.length === 0) return [];
    // Sector lookup from the prior quarter's holdings array
    const priorEntry = timeline[timeline.length - 2];
    const sectorByTicker: Record<string, string> = {};
    for (const h of priorEntry.holdings) {
      sectorByTicker[h.ticker] = h.sector;
    }
    return soldTickers.map((ticker) => ({ ticker, sector: sectorByTicker[ticker] ?? '' }));
  }, [timeline, priorHeldSet, displayHoldings]);

  // Per-holding total return since entry (for both held/new AND sold rows).
  // Mirrors the slider branch's plSince logic but uses heldSetForEntry()
  // for the adaptive membership test instead of count-slicing.
  //
  // Held/New: streak-start index is the earliest rebalance where the ticker
  // was already in the basket; entry close = close at that rebalance;
  // pct = (lastClose / entryClose - 1) * 100.
  //
  // Sold: streak-start index within the PRIOR basket membership;
  // sellIdx = timeline.length - 1 (latest rebalance, the one it left);
  // pct = (closeAtSell / entryClose - 1) * 100.
  const adaptivePlSince = useMemo((): Record<string, number | null> => {
    const result: Record<string, number | null> = {};

    // Held/New rows — current basket members
    for (const h of weightSortedHoldings) {
      const t = h.ticker;
      let idx = timeline.length - 1;
      while (idx > 0 && heldSetForEntry(timeline[idx - 1]).has(t)) idx -= 1;
      const entry = data.entryCloses[t]?.[idx] ?? null;
      const lastC = data.lastCloses[t] ?? null;
      result[t] = entry !== null && lastC !== null && entry !== 0
        ? (lastC / entry - 1) * 100
        : null;
    }

    // Sold rows — rotated-out names (streak within the prior basket)
    const sellIdx = timeline.length - 1;
    for (const s of soldRows) {
      const t = s.ticker;
      let idx = sellIdx;
      // Walk back through the PRIOR basket to find the streak start
      while (idx > 0 && heldSetForEntry(timeline[idx - 1]).has(t)) idx -= 1;
      const entry = data.entryCloses[t]?.[idx] ?? null;
      const atSell = data.entryCloses[t]?.[sellIdx] ?? null;
      result[t] = entry !== null && atSell !== null && entry !== 0
        ? (atSell / entry - 1) * 100
        : null;
    }

    return result;
  }, [timeline, weightSortedHoldings, soldRows, data.entryCloses, data.lastCloses]);

  const grossReturn = view.periodGross ?? (finals.gross !== null ? finals.gross - 100 : null);
  const consReturn  = view.periodConservative ?? (finals.conservative !== null ? finals.conservative - 100 : null);
  const netReturn   = view.periodPortfolio;
  const benchReturn = view.periodBenchmark;

  // Sector-concentration disclosure (methodology-scientist 2026-06-06).
  // Uses displayHoldings so the sector tally matches the rendered picks list.
  const topSector = displayHoldings.reduce<{ sector: string; n: number } | null>((best, h) => {
    const n = displayHoldings.filter((x) => x.sector === h.sector).length;
    return !best || n > best.n ? { sector: h.sector, n } : best;
  }, null);

  return (
    <div className="space-y-6">
      <div className="space-y-5 rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
        {/* Headline — full-window net return vs the chosen index */}
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
              AI pick · adaptive basket · net of cost
            </div>
            <div className={`font-mono text-4xl font-bold tabular-nums ${toneClass(netReturn)}`}>
              {pctStr(netReturn)}
            </div>
            <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              since {view.periodStart ?? meta.as_of_start} · {meta.rebalance_count} quarterly rebalances
            </div>
          </div>
          <div className="flex items-end gap-x-6 gap-y-3">
            <div className="text-right">
              <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                {benchLabel}
              </div>
              <div className={`font-mono text-2xl font-semibold tabular-nums ${toneClass(benchReturn)}`}>
                {pctStr(benchReturn)}
              </div>
              <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {netReturn !== null && benchReturn !== null
                  ? `${pctStr(netReturn - benchReturn)} vs index`
                  : 'benchmark'}
              </div>
            </div>
            {/* Outperformance — AI net return minus the benchmark return (the
                two inputs above). Sage/positive tone when ahead via toneClass. */}
            {netReturn !== null && benchReturn !== null && (
              <div className="text-right">
                <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                  Outperformance
                </div>
                <div className={`font-mono text-2xl font-semibold tabular-nums ${toneClass(netReturn - benchReturn)}`}>
                  {pctStr(netReturn - benchReturn)}
                </div>
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  AI net − {benchLabel}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Adaptive basket context — explains the sizing rule clearly.
            The band clause (when holdBandMin is present) describes the
            hysteresis device as a turnover/stability mechanism only —
            no performance claims per methodology discipline. */}
        <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {vetoLayerReplayed ? (
            <>
              AI-sized basket — this quarter{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {displayCount} {displayCount === 1 ? 'name' : 'names'}
              </span>{' '}
              {isBand ? (
                // Band-only copy — "enters; holdings stay while ≥holdBandMin"
                // lives ONLY here. STATE 1 artifacts only.
                <>
                  (every pick scoring{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    ≥{rule.composite_min.toFixed(0)}
                  </span>{' '}
                  enters{'; '}holdings stay while{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    ≥{holdBandMin!.toFixed(0)}
                  </span>
                  {' '}(reduces unnecessary turnover); min{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    {rule.min_picks}
                  </span>
                  {rule.max_picks === null ? (
                    <>, no cap{').'}</>
                  ) : (
                    <>, max{' '}
                      <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                        {rule.max_picks}
                      </span>
                      {').'}
                    </>
                  )}
                </>
              ) : (
                // Original pre-band wording for STATE 2 (current artifact).
                // "holds every pick scoring ≥N" — unchanged from the pre-V55 copy.
                <>
                  (holds every pick scoring{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    ≥{rule.composite_min.toFixed(0)}
                  </span>
                  ; min{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    {rule.min_picks}
                  </span>
                  {rule.max_picks === null ? (
                    <>, no cap{').'}</>
                  ) : (
                    <>, max{' '}
                      <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                        {rule.max_picks}
                      </span>
                      {').'}
                    </>
                  )}
                </>
              )}{' '}
              Replays{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {vetoesNotReplayed && vetoesNotReplayed.length > 0
                  ? `${7 - vetoesNotReplayed.length} of 7`
                  : 'all 7'}{' '}
                live defense vetoes
              </span>{' '}
              point-in-time
              {vetoesNotReplayed && vetoesNotReplayed.length > 0 && (
                <>
                  {' '}({vetoesNotReplayed.map((v) => flagLabel(v.name)).join(', ')} excluded)
                </>
              )}
              — a closer proxy to the live product, but still not identical.
            </>
          ) : (
            <>
              AI-sized basket — this quarter{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {displayCount} {displayCount === 1 ? 'name' : 'names'}
              </span>{' '}
              {isBand ? (
                // Band-only copy — "enters; holdings stay while ≥holdBandMin"
                // lives ONLY here. STATE 1 artifacts only.
                <>
                  (every pick scoring{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    ≥{rule.composite_min.toFixed(0)}
                  </span>{' '}
                  enters{'; '}holdings stay while{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    ≥{holdBandMin!.toFixed(0)}
                  </span>
                  {' '}(reduces unnecessary turnover); min{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    {rule.min_picks}
                  </span>
                  {rule.max_picks === null ? (
                    <>, no cap{').'}</>
                  ) : (
                    <>, max{' '}
                      <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                        {rule.max_picks}
                      </span>
                      {').'}
                    </>
                  )}
                </>
              ) : (
                // Original pre-band wording for STATE 2 (current artifact).
                // "holds every pick scoring ≥N" — unchanged from the pre-V55 copy.
                <>
                  (holds every pick scoring{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    ≥{rule.composite_min.toFixed(0)}
                  </span>
                  ; min{' '}
                  <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                    {rule.min_picks}
                  </span>
                  {rule.max_picks === null ? (
                    <>, no cap{').'}</>
                  ) : (
                    <>, max{' '}
                      <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
                        {rule.max_picks}
                      </span>
                      {').'}
                    </>
                  )}
                </>
              )}{' '}
              Factor-tilted book — the defense-layer vetoes that filter the live
              Top-5 are{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                not replayed here
              </span>
              .
            </>
          )}
        </p>

        {/* Controls — benchmark picker only (no count slider in adaptive mode) */}
        <div className="max-w-sm space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
            Compare with
          </span>
          <SegmentedSelector
            options={BENCHMARKS}
            value={bench}
            onChange={setBench}
            ariaLabel="Benchmark index"
            variant="primary"
          />
        </div>

        {/* Chart + timeframe */}
        <div className="space-y-2">
          <div className="flex items-baseline gap-1 text-xs text-slate-400 dark:text-slate-500">
            <span>$</span>
            <input
              type="number"
              min={100}
              step={1000}
              value={capital}
              aria-label="Initial capital in dollars"
              onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= 100) setCapital(v); }}
              className="w-24 rounded border border-slate-300 bg-transparent px-1.5 py-0.5 font-mono tabular-nums text-slate-600 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-600 dark:text-slate-300 dark:focus:border-slate-400 dark:focus:ring-slate-500 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            />
            <span>invested at window start</span>
          </div>
          <div className="relative">
            <NavCompareChartLazy
              data={view.points}
              portfolioLabel={portfolioLabel}
              benchmarkLabel={benchLabel}
              money
              baseline={capital}
              tickMode={view.tickMode}
            />
            {/* Stats overlay — top-left inside the plot area */}
            <div className="pointer-events-none absolute left-10 top-3 space-y-0.5">
              <div className="flex items-baseline gap-1 text-[10px] leading-tight">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-700 dark:bg-emerald-400" aria-hidden="true" />
                <span className="font-semibold text-slate-700 dark:text-slate-200">{portfolioLabel} (net)</span>
                <span className="font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">{money$(view.endPortfolio)}</span>
                {view.periodPortfolio !== null && (
                  <span className={`font-mono tabular-nums ${toneClass(view.periodPortfolio)}`}>{pctStr(view.periodPortfolio)}</span>
                )}
              </div>
              <div className="flex items-baseline gap-1 text-[10px] leading-tight">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500 dark:bg-indigo-400" aria-hidden="true" />
                <span className="font-semibold text-slate-700 dark:text-slate-200">{benchLabel}</span>
                <span className="font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">{money$(view.endBenchmark)}</span>
                {view.periodBenchmark !== null && (
                  <span className={`font-mono tabular-nums ${toneClass(view.periodBenchmark)}`}>{pctStr(view.periodBenchmark)}</span>
                )}
              </div>
            </div>
          </div>
          <SegmentedSelector
            options={PERIODS}
            value={period}
            onChange={setPeriod}
            ariaLabel="Chart timeframe"
            variant="primary"
          />
        </div>

        {/* Cost band */}
        <div className="grid grid-cols-3 gap-2 border-t border-slate-100 pt-4 text-center dark:border-slate-800">
          <CostStat label="Gross" value={grossReturn} />
          <CostStat label="Net (10bps)" value={netReturn} />
          <CostStat label="Net (25bps)" value={consReturn} />
        </div>
      </div>

      {/* Current picks — adaptive basket, full-width above the returns grid. */}
      <div className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <h2
            id="adaptive-picks-heading"
            className="font-slab text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100"
          >
            Current picks
          </h2>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            as of {data.latest?.date ?? meta.as_of_end}
          </span>
        </div>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          AI-sized basket —{' '}
          <span className="font-mono tabular-nums font-medium text-slate-600 dark:text-slate-300">
            {displayCount}
          </span>{' '}
          {displayCount === 1 ? 'stock' : 'stocks'} this quarter, inverse-volatility weighted.{' '}
          {isBand ? (
            <>
              Every pick scoring{' '}
              <span className="font-mono tabular-nums">≥{rule.composite_min.toFixed(0)}</span> enters;
              holdings stay while{' '}
              <span className="font-mono tabular-nums">≥{holdBandMin!.toFixed(0)}</span>{' '}
              (min <span className="font-mono tabular-nums">{rule.min_picks}</span>
              {rule.max_picks === null ? (
                <>, no cap).</>
              ) : (
                <>, max <span className="font-mono tabular-nums">{rule.max_picks}</span>).</>
              )}

            </>
          ) : (
            <>
              Every pick scoring{' '}
              <span className="font-mono tabular-nums">≥{rule.composite_min.toFixed(0)}</span> is
              included (min <span className="font-mono tabular-nums">{rule.min_picks}</span>
              {rule.max_picks === null ? (
                <>, no cap).</>
              ) : (
                <>, max <span className="font-mono tabular-nums">{rule.max_picks}</span>).</>
              )}
            </>
          )}
          {topSector && (
            <>
              {' '}Top sector:{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">{topSector.sector}</span>{' '}
              — <span className="font-mono tabular-nums">{topSector.n}</span> of{' '}
              <span className="font-mono tabular-nums">{displayCount}</span>.
            </>
          )}
          {' '}Return = total return since each holding entered the basket (sold names: through their exit rebalance).
        </p>
        {/* Grid header + rows share a common template:
            Mobile (6 tracks, sector hidden): [1.25rem auto 1fr 4.25rem 2.75rem 4.5rem]
            sm+ (7 tracks, sector visible):   [1.25rem auto auto 1fr 4.25rem 2.75rem 4.5rem]
            Column order (DOM): # · Status · Ticker · Sector · Return · Weight · Change.
            The Sector cell carries `hidden sm:block`; a display:none grid child is
            not placed, so mobile's 6 visible cells map cleanly to the 6 mobile tracks.
            Return track widened to 4.25rem so "−12.4%" fits cleanly. */}
        <div className="grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem_4.5rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem_4.5rem] border-b border-slate-200 pb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:border-slate-700 dark:text-slate-400">
          <span>#</span>
          <span>Status</span>
          <span>Ticker</span>
          <span className="hidden sm:block">Sector</span>
          <span className="text-right">Return</span>
          <span className="text-right">Weight</span>
          <span className="text-right">Change</span>
        </div>
        <ol aria-labelledby="adaptive-picks-heading" className="divide-y divide-slate-100 dark:divide-slate-800">
          {weightSortedHoldings.map((h, i) => {
            // Portfolio-sense held: ticker was in the prior quarter's basket.
            // Derived from priorHeldSet (computed above via heldSetForEntry,
            // mirroring HoldingsTimeline's per-entry slice logic exactly).
            // The score-band `carried` field is intentionally NOT used here —
            // it disagrees with the portfolio sense and HoldingsTimeline.
            const isHeld = priorHeldSet.has(h.ticker);
            return (
              <li key={h.ticker} className="grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem_4.5rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem_4.5rem] py-2">
                <span className="font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
                  {i + 1}
                </span>
                {/* Status chip — portfolio sense: Held = in prior quarter's basket,
                    New = entered this quarter. Text label carries the meaning to
                    screen readers (Rule 10: color is never the sole signal).
                    Held = slate neutral tone; New = emerald positive-light tone.
                    Both use size="xs" to stay compact in the tight table row. */}
                {isHeld ? (
                  <Chip
                    size="xs"
                    tone="bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:ring-slate-700"
                    dot="bg-slate-500 dark:bg-slate-400"
                  >
                    Held
                  </Chip>
                ) : (
                  <Chip
                    size="xs"
                    tone="bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800"
                    dot="bg-emerald-500 dark:bg-emerald-400"
                  >
                    New
                  </Chip>
                )}
                <Link
                  href={`/stock/${h.ticker}/`}
                  className="press font-mono text-sm font-semibold text-slate-900 hover:underline dark:text-slate-100"
                >
                  {h.ticker}
                </Link>
                <span className="hidden sm:block">
                  <SectorChip sector={h.sector} />
                </span>
                {/* Return cell — total return since entry (entry→today).
                    Uses adaptivePlSince, precomputed per-ticker via heldSetForEntry
                    streak walk. font-semibold matches the slider branch's Return cell. */}
                <span className={`text-right font-mono text-sm font-semibold tabular-nums ${toneClass(adaptivePlSince[h.ticker] ?? null)}`}>
                  {pctStr(adaptivePlSince[h.ticker] ?? null)}
                </span>
                <span className="text-right font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {weightLabels[i]}
                </span>
                {(() => { const ch = weightChange(h.weight, data.priorWeights[h.ticker]); return (
                  <span className={`flex items-center justify-between gap-1 font-mono text-xs tabular-nums ${ch.tone}`}>
                    <span aria-hidden="true">{ch.arrow}</span>
                    <span>{ch.text}</span>
                  </span>
                ); })()}
              </li>
            );
          })}
          {/* Sold rows — tickers rotated OUT of the basket this quarter.
              Continues the # sequence after the last holding. Rendered only
              when soldRows is non-empty (timeline.length >= 2 and at least one
              prior ticker is absent from the current basket).
              First sold row gets a slightly stronger top border to visually
              separate the "out of basket" appendix from the active holdings —
              the divide-y already places a hairline between rows; the first
              sold row's border-t-slate-300/dark:border-t-slate-600 is
              marginally darker so the eye reads the break.
              Sold ticker + sector + dashes are muted (text-slate-500/400) so
              they read as informational; the "Sold" chip keeps full contrast
              (WCAG AA — red-900 on red-50 ≈ 10:1). */}
          {soldRows.map((s, j) => (
            <li
              key={s.ticker}
              className={`grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem_4.5rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem_4.5rem] py-2${j === 0 ? ' border-t border-t-slate-300 dark:border-t-slate-600' : ''}`}
            >
              <span className="font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
                {weightSortedHoldings.length + j + 1}
              </span>
              {/* Sold chip — negative/red tone matching design-system Negative row
                  (bg-red-50 text-rose-800 ring-red-200 + rose dot bg-rose-500;
                  text-rose-800 not text-red-900 — only the former is on the
                  globals.css soft-OKLCH allowlist, per RecommendationBadge/
                  LossChanceBadge precedent)
                  with canonical paired dark: variants. Consistent with the
                  Rotation-history SELL color (HoldingsTimeline) and the
                  outlined-light chip family (SKILL.md Rule 2). */}
              <Chip
                size="xs"
                tone="bg-red-50 text-rose-800 ring-red-200 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800"
                dot="bg-rose-500 dark:bg-rose-400"
              >
                Sold
              </Chip>
              <Link
                href={`/stock/${s.ticker}/`}
                className="press font-mono text-sm font-semibold text-slate-500 hover:underline dark:text-slate-400"
              >
                {s.ticker}
              </Link>
              <span className="hidden sm:block">
                {s.sector ? <SectorChip sector={s.sector} /> : null}
              </span>
              {/* Return cell — total return from entry → sell rebalance (entry→exit).
                  Uses adaptivePlSince, computed via the streak-within-prior-basket
                  walk in the useMemo above. Full emerald/rose tone so the return is
                  the row's headline even though ticker/sector stay muted. */}
              <span className={`text-right font-mono text-sm font-semibold tabular-nums ${toneClass(adaptivePlSince[s.ticker] ?? null)}`}>
                {pctStr(adaptivePlSince[s.ticker] ?? null)}
              </span>
              <span className="text-right font-mono text-sm tabular-nums text-slate-400 dark:text-slate-500">
                0.0%
              </span>
              {(() => { const ch = weightChange(0, data.priorWeights[s.ticker]); return (
                <span className={`flex items-center justify-between gap-1 font-mono text-xs tabular-nums ${ch.tone}`}>
                  <span aria-hidden="true">{ch.arrow}</span>
                  <span>{ch.text}</span>
                </span>
              ); })()}
            </li>
          ))}
        </ol>
      </div>

      {/* Annual returns | Performance — side-by-side on desktop (2-col grid,
          items-start so unequal-height cards top-align), stacking to a single
          column on mobile. Sits below the full-width Current picks card. */}
      <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-2">
        {/* Annual returns — derived from the adaptive net series */}
        <AnnualReturnsTable
          dates={dates}
          portfolio={adaptive.net}
          benchmark={benchmark[bench] ?? []}
          portfolioLabel={portfolioLabel}
          benchmarkLabel={benchLabel}
          vetoLayerReplayed={vetoLayerReplayed}
          vetoesNotReplayed={vetoesNotReplayed}
        />
        {/* Performance — trailing-period returns, same series as AnnualReturnsTable */}
        <PerformanceTable
          dates={dates}
          portfolio={adaptive.net}
          benchmark={benchmark[bench] ?? []}
          portfolioLabel={portfolioLabel}
          benchmarkLabel={benchLabel}
          vetoLayerReplayed={vetoLayerReplayed}
          vetoesNotReplayed={vetoesNotReplayed}
        />
      </div>

      {timeline.length > 0 && (
        <HoldingsTimeline timeline={timeline} count={displayCount} />
      )}

      {/* Footer CTA (H-8) — primary route into the full ranking, paired with
          the educational-backtest caveat so the call-to-action is never read
          without the past-performance disclaimer beside it. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-5 dark:border-slate-800">
        <Link
          href="/ranking"
          className="press inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
        >
          View the full ranking
        </Link>
        <span className="max-w-md text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          Educational backtest. Past performance does not guarantee future results.
        </span>
      </div>

      <p className="text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        {meta.disclaimer}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SLIDER (legacy) branch — shown when data.adaptive is null.
// This is the EXISTING UI, unchanged, so the deploy is safe until the next
// backfill/cron regenerates the artifact with nav.adaptive.
// ---------------------------------------------------------------------------
function AiPickSliderBranch({ data }: { data: AiPickData }) {
  const { meta, dates, netByCount, grossByCount, conservativeByCount, benchmark, finalsByCount, latest, timeline, entryCloses, lastCloses, vetoLayerReplayed, vetoesNotReplayed } = data;

  // Default to the count with the highest Max-window net return so the first
  // view the user sees is the best-performing basket, not an arbitrary fixed default.
  const bestMaxCount = useMemo(() => {
    let best = meta.default_count;
    let bestVal = -Infinity;
    for (const [key, val] of Object.entries(finalsByCount)) {
      const n = val.net;
      if (n !== null && n > bestVal) { bestVal = n; best = Number(key); }
    }
    return best;
  }, [finalsByCount, meta.default_count]);

  const [count, setCount] = useState<number>(bestMaxCount);
  const [bench, setBench] = useState<string>(meta.default_benchmark);
  const [period, setPeriod] = useState<string>('MAX');
  const [capital, setCapital] = useState<number>(CHART_BASE);

  const countKey = String(count);
  const benchLabel = (BENCHMARKS.find((b) => b.value === bench)?.label ?? bench).toUpperCase();
  const portfolioLabel = `AI pick · ${count}`;

  const bser = useMemo(() => benchmark[bench] ?? [], [benchmark, bench]);

  const view = useMemo(
    () => buildView(
      netByCount[countKey] ?? [],
      grossByCount[countKey] ?? [],
      conservativeByCount[countKey] ?? [],
      bser,
      dates,
      period,
      capital,
    ),
    [netByCount, grossByCount, conservativeByCount, bser, dates, countKey, period, capital],
  );

  // All three cost-band columns are now period-aware (series exposed via grossByCount /
  // conservativeByCount); finalsByCount is kept only as a fallback when series are absent.
  const finals = finalsByCount[countKey] ?? { gross: null, net: null, conservative: null };
  const ret = (nav: number | null) => (nav === null ? null : nav - 100);
  const grossReturn = view.periodGross ?? ret(finals.gross);
  const consReturn = view.periodConservative ?? ret(finals.conservative);
  const netReturn = view.periodPortfolio;
  const benchReturn = view.periodBenchmark;

  const weights = latest ? (latest.weightsByCount[countKey] ?? {}) : {};
  const holdings = latest
    ? latest.holdings
        .slice(0, count)
        .sort((a, b) => (weights[b.ticker] ?? 0) - (weights[a.ticker] ?? 0))
    : [];

  // Hamilton apportionment: displayed 1-decimal weight labels summing to
  // exactly the basket total (removes per-row toFixed(1) rounding drift).
  const weightLabels = useMemo(
    () => apportionWeightLabels(holdings.map((h) => weights[h.ticker])),
    [holdings, weights],
  );

  // P/L since the holding's entry: walk the timeline backward while the ticker
  // stays inside the top-`count` slice — the streak start IS count-dependent (a
  // stock can be a recent top-3 entrant but a long-time top-10 member). Return =
  // last adjusted close / close at the entry rebalance (total-return basis).
  const plSince: Record<string, { pct: number | null; date: string | null }> = {};
  for (const h of holdings) {
    let idx = timeline.length - 1;
    while (idx > 0 && timeline[idx - 1].holdings.slice(0, count).some((x) => x.ticker === h.ticker)) {
      idx -= 1;
    }
    const entry = entryCloses[h.ticker]?.[idx] ?? null;
    const lastC = lastCloses[h.ticker] ?? null;
    plSince[h.ticker] = {
      pct: entry !== null && lastC !== null ? (lastC / entry - 1) * 100 : null,
      date: timeline[idx]?.date ?? null,
    };
  }

  // Sector-concentration disclosure (methodology-scientist 2026-06-06): with the
  // 2-per-sector cap removed, inverse-vol + the 0.35 cap bound single-NAME risk but
  // NOT single-SECTOR risk — so surface how concentrated the basket is in its
  // largest sector rather than leaving the reader to count chips.
  const topSector = holdings.reduce<{ sector: string; n: number } | null>((best, h) => {
    const n = holdings.filter((x) => x.sector === h.sector).length;
    return !best || n > best.n ? { sector: h.sector, n } : best;
  }, null);

  return (
    <div className="space-y-6">
      <div className="space-y-5 rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
        {/* Headline — full-window net return vs the chosen index */}
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
              AI pick · {count} {count === 1 ? 'stock' : 'stocks'} · net of cost
            </div>
            <div className={`font-mono text-4xl font-bold tabular-nums ${toneClass(netReturn)}`}>
              {pctStr(netReturn)}
            </div>
            <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              since {view.periodStart ?? meta.as_of_start} · {meta.rebalance_count} quarterly rebalances
            </div>
          </div>
          <div className="flex items-end gap-x-6 gap-y-3">
            <div className="text-right">
              <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                {benchLabel}
              </div>
              <div className={`font-mono text-2xl font-semibold tabular-nums ${toneClass(benchReturn)}`}>
                {pctStr(benchReturn)}
              </div>
              <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {netReturn !== null && benchReturn !== null
                  ? `${pctStr(netReturn - benchReturn)} vs index`
                  : 'benchmark'}
              </div>
            </div>
            {/* Outperformance — AI net return minus the benchmark return (the
                two inputs above). Sage/positive tone when ahead via toneClass. */}
            {netReturn !== null && benchReturn !== null && (
              <div className="text-right">
                <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
                  Outperformance
                </div>
                <div className={`font-mono text-2xl font-semibold tabular-nums ${toneClass(netReturn - benchReturn)}`}>
                  {pctStr(netReturn - benchReturn)}
                </div>
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  AI net − {benchLabel}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Concentration caveat — inline context so the "vs index" number is never
            read alone (methodology-scientist 2026-06-08: the small-N divergence is
            concentration / idiosyncratic-risk-driven, a disclosed proxy limit, NOT a
            calc error — it shrinks as N grows toward the index). */}
        <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {count < 10 ? (
            <>
              A concentrated{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {count}-stock
              </span>{' '}
              book carries high single-name risk and can trail a cap-weighted index
              for long stretches — add holdings to diversify, and read the full
              ladder, not any single line.
            </>
          ) : vetoLayerReplayed ? (
            <>
              This{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {count}-stock
              </span>{' '}
              factor-tilted book has no per-sector cap and replays{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {vetoesNotReplayed && vetoesNotReplayed.length > 0
                  ? `${7 - vetoesNotReplayed.length} of 7`
                  : 'all 7'}{' '}
                live defense vetoes
              </span>{' '}
              point-in-time
              {vetoesNotReplayed && vetoesNotReplayed.length > 0 && (
                <>
                  {' '}({vetoesNotReplayed.map((v) => flagLabel(v.name)).join(', ')} excluded)
                </>
              )}
              — a closer proxy to the live product, but still not identical.
            </>
          ) : (
            <>
              This{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {count}-stock
              </span>{' '}
              factor-tilted book has no per-sector cap, so it can diverge from a
              cap-weighted index in either direction — a backtest proxy, not the live
              veto-filtered product.
            </>
          )}
        </p>

        {/* Controls — count slider + benchmark picker */}
        <div className="grid gap-4 sm:grid-cols-2">
          <HoldingsCountSlider value={count} min={1} max={meta.max_holdings} onChange={setCount} />
          <div className="space-y-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
              Compare with
            </span>
            <SegmentedSelector
              options={BENCHMARKS}
              value={bench}
              onChange={setBench}
              ariaLabel="Benchmark index"
              variant="primary"
            />
          </div>
        </div>

        {/* Chart + timeframe */}
        <div className="space-y-2">
          <div className="flex items-baseline gap-1 text-xs text-slate-400 dark:text-slate-500">
            <span>$</span>
            <input
              type="number"
              min={100}
              step={1000}
              value={capital}
              onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= 100) setCapital(v); }}
              className="w-24 rounded border border-slate-300 bg-transparent px-1.5 py-0.5 font-mono tabular-nums text-slate-600 focus:border-slate-400 focus:outline-none dark:border-slate-600 dark:text-slate-300 dark:focus:border-slate-400 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            />
            <span>invested at window start</span>
          </div>
          {/* relative wrapper so the stats overlay can be positioned inside the chart area */}
          <div className="relative">
            <NavCompareChartLazy
              data={view.points}
              portfolioLabel={portfolioLabel}
              benchmarkLabel={benchLabel}
              money
              baseline={capital}
              tickMode={view.tickMode}
            />
            {/* Stats overlay — top-left inside the plot area (left offset clears the ~36px y-axis) */}
            <div className="pointer-events-none absolute left-10 top-3 space-y-0.5">
              <div className="flex items-baseline gap-1 text-[10px] leading-tight">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-700 dark:bg-emerald-400" aria-hidden="true" />
                <span className="font-semibold text-slate-700 dark:text-slate-200">{portfolioLabel} (net)</span>
                <span className="font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">{money$(view.endPortfolio)}</span>
                {view.periodPortfolio !== null && (
                  <span className={`font-mono tabular-nums ${toneClass(view.periodPortfolio)}`}>{pctStr(view.periodPortfolio)}</span>
                )}
              </div>
              <div className="flex items-baseline gap-1 text-[10px] leading-tight">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500 dark:bg-indigo-400" aria-hidden="true" />
                <span className="font-semibold text-slate-700 dark:text-slate-200">{benchLabel}</span>
                <span className="font-mono font-bold tabular-nums text-slate-900 dark:text-slate-100">{money$(view.endBenchmark)}</span>
                {view.periodBenchmark !== null && (
                  <span className={`font-mono tabular-nums ${toneClass(view.periodBenchmark)}`}>{pctStr(view.periodBenchmark)}</span>
                )}
              </div>
            </div>
          </div>
          <SegmentedSelector
            options={PERIODS}
            value={period}
            onChange={setPeriod}
            ariaLabel="Chart timeframe"
            variant="primary"
          />
        </div>

        {/* Cost band — all three columns are period-aware now that gross + conservative
            series are exposed from the backtest artifact. */}
        <div className="grid grid-cols-3 gap-2 border-t border-slate-100 pt-4 text-center dark:border-slate-800">
          <CostStat label="Gross" value={grossReturn} />
          <CostStat label="Net (10bps)" value={netReturn} />
          <CostStat label="Net (25bps)" value={consReturn} />
        </div>
      </div>

      {/* Current picks — full-width above the returns grid. */}
      <div className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <h2 className="font-slab text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Current picks
          </h2>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            as of {latest?.date ?? meta.as_of_end}
          </span>
        </div>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          Top {count} by composite (no sector cap), inverse-volatility weighted.
          The right column is each holding&apos;s total return since it entered the
          basket (first rebalance of its current streak).
          {topSector && (
            <>
              {' '}Top sector:{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">{topSector.sector}</span>{' '}
              — <span className="font-mono tabular-nums">{topSector.n}</span> of{' '}
              <span className="font-mono tabular-nums">{count}</span>.
            </>
          )}
        </p>
        <div className="flex items-center gap-3 border-b border-slate-200 pb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:border-slate-700 dark:text-slate-400">
          <span className="w-4 shrink-0">#</span>
          <span>Ticker</span>
          <span className="hidden sm:inline">Sector</span>
          <span className="ml-auto w-12 shrink-0 text-right">Weight</span>
          <span className="w-14 shrink-0 text-right">Return</span>
          <span className="w-14 shrink-0 text-right">Entry</span>
        </div>
        <ol className="divide-y divide-slate-100 dark:divide-slate-800">
          {holdings.map((h, i) => {
            const pl = plSince[h.ticker] ?? { pct: null, date: null };
            return (
              <li key={h.ticker} className="flex items-center gap-3 py-2">
                <span className="w-4 shrink-0 font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
                  {i + 1}
                </span>
                <Link
                  href={`/stock/${h.ticker}/`}
                  className="press font-mono text-sm font-semibold text-slate-900 hover:underline dark:text-slate-100"
                >
                  {h.ticker}
                </Link>
                <span className="hidden sm:inline">
                  <SectorChip sector={h.sector} />
                </span>
                <span className="ml-auto w-12 shrink-0 text-right font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {weightLabels[i]}
                </span>
                <span className={`w-14 shrink-0 text-right font-mono text-sm font-semibold tabular-nums ${toneClass(pl.pct)}`}>
                  {pctStr(pl.pct)}
                </span>
                <span className="w-14 shrink-0 text-right font-mono text-[0.6rem] tabular-nums text-slate-700 dark:text-slate-300">
                  {pl.date ? pl.date.slice(0, 7) : ''}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Annual returns | Performance — side-by-side on desktop (2-col grid,
          items-start so unequal-height cards top-align), stacking to a single
          column on mobile. Sits below the full-width Current picks card.
          Both tables are reactive to the count slider + benchmark picker. */}
      <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-2">
        {/* Annual returns — Jitta-style calendar-year backtest table + CAGR row */}
        <AnnualReturnsTable
          dates={dates}
          portfolio={netByCount[countKey] ?? []}
          benchmark={benchmark[bench] ?? []}
          portfolioLabel={portfolioLabel}
          benchmarkLabel={benchLabel}
          vetoLayerReplayed={vetoLayerReplayed}
          vetoesNotReplayed={vetoesNotReplayed}
        />
        {/* Performance — trailing-period returns, same series as AnnualReturnsTable */}
        <PerformanceTable
          dates={dates}
          portfolio={netByCount[countKey] ?? []}
          benchmark={benchmark[bench] ?? []}
          portfolioLabel={portfolioLabel}
          benchmarkLabel={benchLabel}
          vetoLayerReplayed={vetoLayerReplayed}
          vetoesNotReplayed={vetoesNotReplayed}
        />
      </div>

      {timeline.length > 0 && <HoldingsTimeline timeline={timeline} count={count} />}

      {/* Footer CTA (H-8) — primary route into the full ranking, paired with
          the educational-backtest caveat so the call-to-action is never read
          without the past-performance disclaimer beside it. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-5 dark:border-slate-800">
        <Link
          href="/ranking"
          className="press inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
        >
          View the full ranking
        </Link>
        <span className="max-w-md text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          Educational backtest. Past performance does not guarantee future results.
        </span>
      </div>

      {/* Disclaimer — the artifact's own honest, result-dependent text (Rule 9: the
          global banner covers terminology; this is the backtest-specific provenance). */}
      <p className="text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        {meta.disclaimer}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public export — routes to adaptive or slider branch based on data.adaptive.
// ---------------------------------------------------------------------------
export function AiPickPortfolio({ data }: { data: AiPickData }) {
  if (data.adaptive !== null) {
    return <AiPickAdaptiveBranch data={data} />;
  }
  return <AiPickSliderBranch data={data} />;
}

function CostStat({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <div className="text-[0.625rem] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className={`font-mono text-sm font-semibold tabular-nums ${toneClass(value)}`}>
        {pctStr(value)}
      </div>
    </div>
  );
}
