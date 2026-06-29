'use client';

import { useMemo } from 'react';
import { flagLabel } from '@/lib/flag-labels';

// Jitta-style annual backtest table: one row per calendar year (portfolio net
// return vs the chosen benchmark) + a highlighted CAGR (compound annual) footer.
// All figures are DERIVED in the browser from the NAV series the home already
// ships — no schema / compute change. Reactive to the count + benchmark the
// parent passes (same series the chart uses).

interface Props {
  dates: string[];
  /** Portfolio net NAV series (selected holding count), aligned to `dates`. */
  portfolio: (number | null)[];
  /** Benchmark NAV series (selected index), aligned to `dates`. */
  benchmark: (number | null)[];
  portfolioLabel: string;
  benchmarkLabel: string;
  /** Forwarded from AiPickData — true once PR #451 artifact lands. */
  vetoLayerReplayed: boolean;
  /** Names of vetoes excluded from the replay (only present when vetoLayerReplayed=true). */
  vetoesNotReplayed: { name: string }[] | undefined;
}

function isFin(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && !Number.isNaN(v);
}

function firstFin(series: (number | null)[]): number | null {
  for (let i = 0; i < series.length; i += 1) if (isFin(series[i])) return series[i] as number;
  return null;
}

function lastFin(series: (number | null)[]): number | null {
  for (let i = series.length - 1; i >= 0; i -= 1) if (isFin(series[i])) return series[i] as number;
  return null;
}

// year -> NAV at the LAST finite date in that year (dates are chronological, so
// the final write per year wins).
function yearEndNav(dates: string[], series: (number | null)[]): Map<number, number> {
  const m = new Map<number, number>();
  for (let i = 0; i < dates.length; i += 1) {
    if (isFin(series[i])) m.set(Number(dates[i].slice(0, 4)), series[i] as number);
  }
  return m;
}

// Calendar-year returns: year Y return = NAV(end of Y) / NAV(end of Y-1) - 1.
// The first year in the window is based off the inception NAV (so it is the
// since-inception partial-year return, flagged `partial` by the caller).
function annualReturns(
  dates: string[],
  series: (number | null)[],
): Map<number, number | null> {
  const ye = yearEndNav(dates, series);
  const out = new Map<number, number | null>();
  let prev = firstFin(series);
  for (const y of [...ye.keys()].sort((a, b) => a - b)) {
    const end = ye.get(y) as number;
    out.set(y, prev !== null && prev !== 0 ? end / prev - 1 : null);
    prev = end;
  }
  return out;
}

function pct2(frac: number | null): string {
  if (frac === null) return '—';
  const v = frac * 100;
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(2)}%`;
}

// Matches the home's toneClass (emerald positive / rose negative / slate null)
// so the table reads as one family with the headline + cost band.
function tone(frac: number | null): string {
  if (frac === null) return 'text-slate-500 dark:text-slate-400';
  return frac >= 0
    ? 'text-emerald-700 dark:text-emerald-300'
    : 'text-rose-700 dark:text-rose-300';
}

interface Row {
  year: number;
  portfolio: number | null;
  benchmark: number | null;
  partial: boolean;
}

export function AnnualReturnsTable({
  dates,
  portfolio,
  benchmark,
  portfolioLabel,
  benchmarkLabel,
  vetoLayerReplayed,
  vetoesNotReplayed,
}: Props) {
  const { rows, cagrPortfolio, cagrBenchmark, windowYears } = useMemo(() => {
    if (dates.length === 0) {
      return { rows: [] as Row[], cagrPortfolio: null, cagrBenchmark: null, windowYears: 0 };
    }

    const pAnn = annualReturns(dates, portfolio);
    const bAnn = annualReturns(dates, benchmark);
    const years = [...pAnn.keys()].sort((a, b) => a - b);
    const firstYear = years[0];
    const startsMidYear = Number(dates[0].slice(5, 7)) > 1;

    const rows: Row[] = years.map((y) => ({
      year: y,
      portfolio: pAnn.get(y) ?? null,
      benchmark: bAnn.get(y) ?? null,
      partial: y === firstYear && startsMidYear,
    }));

    // CAGR over the actual elapsed window (inception NAV -> final NAV).
    const first = new Date(`${dates[0]}T00:00:00Z`).getTime();
    const last = new Date(`${dates[dates.length - 1]}T00:00:00Z`).getTime();
    const yrs = (last - first) / (365.25 * 86_400_000);
    const cagr = (series: (number | null)[]): number | null => {
      const a = firstFin(series);
      const b = lastFin(series);
      return a !== null && b !== null && a > 0 && yrs > 0 ? Math.pow(b / a, 1 / yrs) - 1 : null;
    };

    return {
      rows,
      cagrPortfolio: cagr(portfolio),
      cagrBenchmark: cagr(benchmark),
      windowYears: yrs,
    };
  }, [dates, portfolio, benchmark]);

  if (rows.length === 0) return null;

  const hasPartial = rows.some((r) => r.partial);

  return (
    <div className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
      <h2 className="mb-1 font-slab text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
        Annual returns
      </h2>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Calendar-year backtest return — {portfolioLabel} (net of cost) vs {benchmarkLabel}.
      </p>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-[0.625rem] uppercase tracking-[0.08em] text-slate-500 dark:border-slate-700 dark:text-slate-400">
            <th scope="col" className="py-2 text-left font-semibold">Year</th>
            <th scope="col" className="py-2 text-right font-semibold">{portfolioLabel}</th>
            <th scope="col" className="py-2 text-right font-semibold">{benchmarkLabel}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((r) => (
            <tr key={r.year}>
              <th
                scope="row"
                className="py-2 text-left font-mono font-normal tabular-nums text-slate-700 dark:text-slate-300"
              >
                {r.year}
                {r.partial && (
                  <span className="text-slate-500 dark:text-slate-400" aria-hidden="true">
                    *
                  </span>
                )}
              </th>
              <td className={`py-2 text-right font-mono font-semibold tabular-nums ${tone(r.portfolio)}`}>
                {pct2(r.portfolio)}
              </td>
              <td className={`py-2 text-right font-mono tabular-nums ${tone(r.benchmark)}`}>
                {pct2(r.benchmark)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50">
            <th
              scope="row"
              className="py-2 text-left text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-600 dark:text-slate-300"
            >
              CAGR
            </th>
            <td className={`py-2 text-right font-mono text-base font-bold tabular-nums ${tone(cagrPortfolio)}`}>
              {pct2(cagrPortfolio)}
            </td>
            <td className={`py-2 text-right font-mono font-semibold tabular-nums ${tone(cagrBenchmark)}`}>
              {pct2(cagrBenchmark)}
            </td>
          </tr>
        </tfoot>
      </table>

      <p className="mt-2 text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        CAGR = compound annual growth over the {windowYears.toFixed(1)}-year backtest window
        ({dates[0]} → {dates[dates.length - 1]}). Backtest = raw
        top-by-composite picks, point-in-time —{' '}
        {vetoLayerReplayed ? (
          <>
            replays{' '}
            <span className="font-medium">
              {vetoesNotReplayed && vetoesNotReplayed.length > 0
                ? `${7 - vetoesNotReplayed.length} of 7`
                : 'all 7'}{' '}
              live defense vetoes
            </span>{' '}
            point-in-time
            {vetoesNotReplayed && vetoesNotReplayed.length > 0 && (
              <>
                {' '}(
                <span className="font-medium">
                  {vetoesNotReplayed.map((v) => flagLabel(v.name)).join(', ')}
                </span>{' '}
                excluded — needs filing-history data)
              </>
            )}
            ; still not the full live product.
          </>
        ) : (
          <>
            the defense-layer vetoes that filter the live Top-5
            are <span className="font-medium">not replayed here</span>, so this is the unfiltered
            signal&rsquo;s record, not the live product&rsquo;s.
          </>
        )}
        {' '}Backtest universe: <span className="font-medium">S&amp;P 500 only</span> (the cohort
        with a point-in-time survivorship ledger, 2016–present) — narrower than the S&amp;P 1500
        currently ranked on the site.
        {hasPartial && (
          <> {' '}* Partial year — since inception ({dates[0]}), not a full calendar year.</>
        )}
      </p>
    </div>
  );
}
