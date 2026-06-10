'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import { NavCompareChartLazy } from './NavCompareChartLazy';
import { AnnualReturnsTable } from './AnnualReturnsTable';
import { HoldingsCountSlider } from './HoldingsCountSlider';
import { HoldingsTimeline } from './HoldingsTimeline';
import { SectorChip } from './SectorChip';
import { SegmentedSelector, type SegmentOption } from './SegmentedSelector';
import type { AiPickData } from '@/lib/types';

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

export function AiPickPortfolio({ data }: { data: AiPickData }) {
  const { meta, dates, netByCount, grossByCount, conservativeByCount, benchmark, finalsByCount, latest, timeline, entryCloses, lastCloses } = data;

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

  const view = useMemo(() => {
    const net = netByCount[countKey] ?? [];
    const gross = grossByCount[countKey] ?? [];
    const cons = conservativeByCount[countKey] ?? [];
    const bser = benchmark[bench] ?? [];
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
    // 1Y / 3Y → quarterly boundary points; longer periods → yearly boundary points.
    const isQuarterly = years <= 3;
    const thinPoints: typeof points[0][] = [];
    if (isQuarterly) {
      let prevQ = '';
      for (const p of points) {
        const [y, m] = p.date.split('-');
        const q = `${y}-${Math.ceil(Number(m) / 3)}`;
        if (q !== prevQ) { p.yearStart = true; thinPoints.push(p); prevQ = q; }
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
      isQuarterly,
      endPortfolio: lastPoint ? lastPoint.portfolio : null,
      endBenchmark: lastPoint ? lastPoint.benchmark : null,
      periodPortfolio: lastPoint ? retFromBase(lastPoint.portfolio) : null,
      periodBenchmark: lastPoint ? retFromBase(lastPoint.benchmark) : null,
      periodGross,
      periodConservative,
      periodStart: dates[startIdx] ?? null,
    };
  }, [netByCount, grossByCount, conservativeByCount, benchmark, dates, countKey, bench, period, capital]);

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
              quarterly={view.isQuarterly}
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

      {/* Current picks */}
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
            const w = weights[h.ticker];
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
                  {isFinite_(w) ? `${(w * 100).toFixed(1)}%` : '—'}
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

      {/* Rotation history — every quarterly rebalance's holdings at the current
          basket size (entered/exited vs the prior quarter). The data the user
          asked to see: "what was held 5 years ago + how it rotated", not "today's
          picks back-projected". Reactive to the count slider. */}
      {/* Annual returns — Jitta-style calendar-year backtest table + CAGR row,
          derived in-browser from the selected count's net NAV vs the chosen
          index (reactive to the slider + benchmark picker; no schema change). */}
      <AnnualReturnsTable
        dates={dates}
        portfolio={netByCount[countKey] ?? []}
        benchmark={benchmark[bench] ?? []}
        portfolioLabel={portfolioLabel}
        benchmarkLabel={benchLabel}
      />

      {timeline.length > 0 && <HoldingsTimeline timeline={timeline} count={count} />}

      {/* Disclaimer — the artifact's own honest, result-dependent text (Rule 9: the
          global banner covers terminology; this is the backtest-specific provenance). */}
      <p className="text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        {meta.disclaimer}
      </p>
    </div>
  );
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
