'use client';

import { useMemo } from 'react';
import { flagLabel } from '@/lib/flag-labels';

// Seeking-Alpha-style "Performance" table: trailing-period returns for the
// portfolio vs the benchmark. Structurally mirrors AnnualReturnsTable (same
// Props, helpers, and design tokens) so the two tables read as siblings
// side-by-side. NO tfoot/CAGR/TOTAL footer row — periods speak for themselves.

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

function lastFin(series: (number | null)[]): number | null {
  for (let i = series.length - 1; i >= 0; i -= 1) if (isFin(series[i])) return series[i] as number;
  return null;
}

// Subtract N calendar months from an ISO YYYY-MM-DD string (UTC semantics).
function subtractMonths(isoDate: string, months: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() - months);
  return d.toISOString().slice(0, 10);
}

// Subtract N calendar years from an ISO YYYY-MM-DD string (UTC semantics).
function subtractYears(isoDate: string, years: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - years);
  return d.toISOString().slice(0, 10);
}

// Walk dates from the end backward; return the NAV at the latest date
// <= cutoffISO that is finite. Returns null if no such date exists
// (cutoff predates the first date in the series).
function navAtOrBefore(
  dates: string[],
  series: (number | null)[],
  cutoffISO: string,
): number | null {
  for (let i = dates.length - 1; i >= 0; i -= 1) {
    if (dates[i] <= cutoffISO && isFin(series[i])) return series[i] as number;
  }
  return null;
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

interface PerformanceRow {
  label: string;
  portfolio: number | null;
  benchmark: number | null;
}

// Trailing return for a single window: lastFin(series) / base - 1.
// Returns null when base is null or 0 (window start predates inception or
// inception NAV is zero) — rendered as "—" honestly, no clamping to inception.
function trailingReturn(series: (number | null)[], base: number | null): number | null {
  const end = lastFin(series);
  if (end === null || base === null || base === 0) return null;
  return end / base - 1;
}

export function PerformanceTable({
  dates,
  portfolio,
  benchmark,
  portfolioLabel,
  benchmarkLabel,
  vetoLayerReplayed,
  vetoesNotReplayed,
}: Props) {
  const { rows, lastDate, firstDate } = useMemo((): {
    rows: PerformanceRow[];
    lastDate: string;
    firstDate: string;
  } => {
    if (dates.length === 0) {
      return { rows: [], lastDate: '', firstDate: '' };
    }

    const lastDate = dates[dates.length - 1];
    const firstDate = dates[0];
    const currentYear = Number(lastDate.slice(0, 4));

    // YTD base is computed per series inside the closure below (portfolio and
    // benchmark may have different finite ranges). Prior year-end cutoff:
    const ytdCutoff = `${currentYear - 1}-12-31`;

    const windows: Array<{ label: string; base: (series: (number | null)[]) => number | null }> = [
      {
        label: '1 Month',
        base: (s) => navAtOrBefore(dates, s, subtractMonths(lastDate, 1)),
      },
      {
        label: '3 Month',
        base: (s) => navAtOrBefore(dates, s, subtractMonths(lastDate, 3)),
      },
      {
        label: '6 Month',
        base: (s) => navAtOrBefore(dates, s, subtractMonths(lastDate, 6)),
      },
      {
        label: '9 Month',
        base: (s) => navAtOrBefore(dates, s, subtractMonths(lastDate, 9)),
      },
      {
        label: 'YTD',
        base: (s) => {
          // Prior year-end NAV: last finite NAV on or before Dec 31 of prior year.
          const priorYearEnd = navAtOrBefore(dates, s, ytdCutoff);
          if (priorYearEnd !== null) return priorYearEnd;
          // History starts in the current year — use first finite NAV (inception).
          for (let i = 0; i < s.length; i += 1) { if (isFin(s[i])) return s[i] as number; }
          return null;
        },
      },
      {
        label: '1 Year',
        base: (s) => navAtOrBefore(dates, s, subtractYears(lastDate, 1)),
      },
      {
        label: '3 Year',
        base: (s) => navAtOrBefore(dates, s, subtractYears(lastDate, 3)),
      },
      {
        label: '5 Year',
        base: (s) => navAtOrBefore(dates, s, subtractYears(lastDate, 5)),
      },
      {
        label: '10 Year',
        base: (s) => navAtOrBefore(dates, s, subtractYears(lastDate, 10)),
      },
    ];

    const rows: PerformanceRow[] = windows.map(({ label, base }) => ({
      label,
      portfolio: trailingReturn(portfolio, base(portfolio)),
      benchmark: trailingReturn(benchmark, base(benchmark)),
    }));

    return { rows, lastDate, firstDate };
  }, [dates, portfolio, benchmark]);

  if (rows.length === 0) return null;

  return (
    <div className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
      <h2 className="mb-1 font-slab text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
        Performance
      </h2>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Trailing-period backtest return — {portfolioLabel} (net of cost) vs {benchmarkLabel}.
      </p>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-[0.625rem] uppercase tracking-[0.08em] text-slate-500 dark:border-slate-700 dark:text-slate-400">
            <th scope="col" className="py-2 text-left font-semibold">Period</th>
            <th scope="col" className="py-2 text-right font-semibold">{portfolioLabel}</th>
            <th scope="col" className="py-2 text-right font-semibold">{benchmarkLabel}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((r) => (
            <tr key={r.label}>
              <th
                scope="row"
                className="py-2 text-left font-normal text-slate-700 dark:text-slate-300"
              >
                {r.label}
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
      </table>

      <p className="mt-2 text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        Trailing-period total return derived from the backtest NAV series ({firstDate} → {lastDate}). Backtest = raw
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
      </p>
    </div>
  );
}
