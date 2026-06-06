'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import { NavCompareChartLazy } from './NavCompareChartLazy';
import { HoldingsCountSlider } from './HoldingsCountSlider';
import { ScoreBadge } from './ScoreBadge';
import { SectorChip } from './SectorChip';
import { SegmentedSelector, type SegmentOption } from './SegmentedSelector';
import type { AiPickData } from '@/lib/types';

const PERIODS: readonly { value: string; label: string; years: number }[] = [
  { value: '1Y', label: '1Y', years: 1 },
  { value: '3Y', label: '3Y', years: 3 },
  { value: '5Y', label: '5Y', years: 5 },
];

const BENCHMARKS: readonly SegmentOption[] = [
  { value: 'spy', label: 'SPY' },
  { value: 'qqq', label: 'QQQ' },
  { value: 'dia', label: 'DIA' },
  { value: 'iwm', label: 'IWM' },
];

const MAX_CHART_POINTS = 180;

function isFinite_(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && !Number.isNaN(v);
}

function firstFiniteFrom(series: (number | null)[], start: number): number | null {
  for (let i = start; i < series.length; i += 1) {
    if (isFinite_(series[i])) return series[i] as number;
  }
  return null;
}

function lastFinite(series: (number | null)[]): number | null {
  for (let i = series.length - 1; i >= 0; i -= 1) {
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
  const { meta, dates, netByCount, benchmark, finalsByCount, latest } = data;

  const [count, setCount] = useState<number>(meta.default_count);
  const [bench, setBench] = useState<string>(meta.default_benchmark);
  const [period, setPeriod] = useState<string>('5Y');

  const countKey = String(count);
  const benchLabel = (BENCHMARKS.find((b) => b.value === bench)?.label ?? bench).toUpperCase();
  const portfolioLabel = `AI pick · ${count}`;

  const view = useMemo(() => {
    const net = netByCount[countKey] ?? [];
    const bser = benchmark[bench] ?? [];
    const years = PERIODS.find((p) => p.value === period)?.years ?? 5;
    const startIdx = startIndexForYears(dates, years);
    const pAnchor = firstFiniteFrom(net, startIdx);
    const bAnchor = firstFiniteFrom(bser, startIdx);

    const span = dates.length - startIdx;
    const step = Math.max(1, Math.ceil(span / MAX_CHART_POINTS));
    const point = (i: number) => ({
      date: dates[i],
      portfolio: pAnchor && isFinite_(net[i]) ? Math.round(((net[i] as number) / pAnchor) * 1000) / 10 : null,
      benchmark: bAnchor && isFinite_(bser[i]) ? Math.round(((bser[i] as number) / bAnchor) * 1000) / 10 : null,
    });
    const points: ReturnType<typeof point>[] = [];
    for (let i = startIdx; i < dates.length; i += step) points.push(point(i));
    if (dates.length > 0 && (dates.length - 1 - startIdx) % step !== 0) {
      points.push(point(dates.length - 1));
    }

    const lastPoint = points[points.length - 1];
    return {
      points,
      periodPortfolio: lastPoint ? (lastPoint.portfolio === null ? null : lastPoint.portfolio - 100) : null,
      periodBenchmark: lastPoint ? (lastPoint.benchmark === null ? null : lastPoint.benchmark - 100) : null,
    };
  }, [netByCount, benchmark, dates, countKey, bench, period]);

  // Full-window (since inception) returns for the headline + cost band.
  const finals = finalsByCount[countKey] ?? { gross: null, net: null, conservative: null };
  const ret = (nav: number | null) => (nav === null ? null : nav - 100);
  const netReturn = ret(finals.net);
  const grossReturn = ret(finals.gross);
  const consReturn = ret(finals.conservative);
  const benchFull = ret(lastFinite(benchmark[bench] ?? []));

  const holdings = latest ? latest.holdings.slice(0, count) : [];
  const weights = latest ? (latest.weightsByCount[countKey] ?? {}) : {};

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
              since {meta.as_of_start} · {meta.rebalance_count} quarterly rebalances
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
              {benchLabel}
            </div>
            <div className={`font-mono text-2xl font-semibold tabular-nums ${toneClass(benchFull)}`}>
              {pctStr(benchFull)}
            </div>
            <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {netReturn !== null && benchFull !== null
                ? `${pctStr(netReturn - benchFull)} vs index`
                : 'benchmark'}
            </div>
          </div>
        </div>

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
          <NavCompareChartLazy
            data={view.points}
            portfolioLabel={portfolioLabel}
            benchmarkLabel={benchLabel}
          />
          <SegmentedSelector
            options={PERIODS}
            value={period}
            onChange={setPeriod}
            ariaLabel="Chart timeframe"
          />
          {/* Legend — color paired with text label (Rule 10) */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-xs text-slate-600 dark:text-slate-300">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-700 dark:bg-emerald-400" aria-hidden="true" />
              {portfolioLabel} (net) {view.periodPortfolio !== null && <span className="font-mono tabular-nums">{pctStr(view.periodPortfolio)}</span>}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-indigo-500 dark:bg-indigo-400" aria-hidden="true" />
              {benchLabel} {view.periodBenchmark !== null && <span className="font-mono tabular-nums">{pctStr(view.periodBenchmark)}</span>}
            </span>
            <span className="text-slate-400 dark:text-slate-500">· rebased to 100 at window start</span>
          </div>
        </div>

        {/* Cost band — gross / net / higher-slippage (honesty: show the gap) */}
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
          {topSector && (
            <>
              {' '}Top sector:{' '}
              <span className="font-medium text-slate-600 dark:text-slate-300">{topSector.sector}</span>{' '}
              — <span className="font-mono tabular-nums">{topSector.n}</span> of{' '}
              <span className="font-mono tabular-nums">{count}</span>.
            </>
          )}
        </p>
        <ol className="divide-y divide-slate-100 dark:divide-slate-800">
          {holdings.map((h, i) => {
            const w = weights[h.ticker];
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
                <span className="ml-auto font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {isFinite_(w) ? `${(w * 100).toFixed(1)}%` : '—'}
                </span>
                <ScoreBadge score={h.composite_score} />
              </li>
            );
          })}
        </ol>
      </div>

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
