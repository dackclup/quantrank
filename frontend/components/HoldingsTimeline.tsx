'use client';

import Link from 'next/link';
import { useMemo } from 'react';

import type { AiPickTimelineEntry } from '@/lib/types';

// Fixed month names — locale-stable across SSR vs client (no `Date()`/Intl
// drift). The rebalance date is quarter-end + the 45-day filing lag, so it is
// the month the basket was actually rebalanced into; we show that honestly
// rather than back-deriving a fiscal-quarter label.
const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

function monthLabel(iso: string): string {
  const [y, m] = iso.split('-');
  return `${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

type Row = {
  date: string;
  held: string[];
  entered: Set<string>;
  exited: string[];
  sectorByTicker: Record<string, string>;
};

/**
 * Rotation history of the AI pick: every quarterly rebalance's holdings at the
 * current basket size, newest first, with the names that entered / exited vs the
 * prior quarter. Reactive to the count slider (slices each rebalance to the
 * top-`count`, the same cut `select_picks` makes). Read-only display — links each
 * ticker to its detail page.
 */
export function HoldingsTimeline({
  timeline,
  count,
}: {
  timeline: AiPickTimelineEntry[];
  count: number;
}) {
  const { rows, avgTurnover } = useMemo(() => {
    const chrono: Row[] = [];
    let prev: string[] = [];
    let totalEntered = 0;
    for (let i = 0; i < timeline.length; i += 1) {
      const slice = timeline[i].holdings.slice(0, count);
      const held = slice.map((h) => h.ticker);
      const sectorByTicker: Record<string, string> = {};
      for (const h of slice) sectorByTicker[h.ticker] = h.sector;
      const prevSet = new Set(prev);
      const heldSet = new Set(held);
      // i === 0 is the initial basket — "entered vs the prior quarter" is
      // undefined, so don't false-flag every name as new (the row carries the
      // "initial basket" sub-label instead).
      const entered = i === 0 ? new Set<string>() : new Set(held.filter((t) => !prevSet.has(t)));
      const exited = prev.filter((t) => !heldSet.has(t));
      if (i > 0) totalEntered += entered.size;
      chrono.push({ date: timeline[i].date, held, entered, exited, sectorByTicker });
      prev = held;
    }
    const transitions = Math.max(1, timeline.length - 1);
    chrono.reverse(); // newest first for display
    return { rows: chrono, avgTurnover: totalEntered / transitions };
  }, [timeline, count]);

  if (rows.length === 0) return null;

  return (
    <div className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900 md:p-6">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="font-slab text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Rotation history
        </h2>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono tabular-nums">{timeline.length}</span> quarterly rebalances
        </span>
      </div>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        ~<span className="font-mono tabular-nums">{avgTurnover.toFixed(1)}</span> of{' '}
        <span className="font-mono tabular-nums">{count}</span> names change each quarter
      </p>
      <ol className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((row, idx) => {
          const isInitial = idx === rows.length - 1; // last displayed = oldest
          // Buy / Hold / Sell split per rebalance. The initial basket is all
          // buys by definition (no prior quarter to hold from).
          const buys = isInitial ? row.held : row.held.filter((t) => row.entered.has(t));
          const holds = isInitial ? [] : row.held.filter((t) => !row.entered.has(t));
          const sells = row.exited;
          return (
            <li
              key={row.date}
              className="grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-1 py-2.5"
            >
              <span className="pt-0.5 font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">
                {monthLabel(row.date)}
                {isInitial && (
                  <span className="mt-0.5 block text-[0.625rem] text-slate-400 dark:text-slate-500">
                    initial basket
                  </span>
                )}
              </span>
              <div className="flex flex-col gap-1">
                <TimelineGroup
                  label="Buy"
                  labelClass="text-emerald-700 dark:text-emerald-400"
                  tickers={buys}
                  sectorByTicker={row.sectorByTicker}
                  linked
                />
                <TimelineGroup
                  label="Hold"
                  labelClass="text-slate-500 dark:text-slate-400"
                  tickers={holds}
                  sectorByTicker={row.sectorByTicker}
                  linked
                />
                <TimelineGroup
                  label="Sell"
                  labelClass="text-rose-600 dark:text-rose-400"
                  tickers={sells}
                  sectorByTicker={row.sectorByTicker}
                  linked={false}
                />
                {buys.length === 0 && sells.length === 0 && !isInitial && (
                  <span className="text-xs text-slate-400 dark:text-slate-500">reweighted only</span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// One labeled sub-row of a rebalance (Buy / Hold / Sell). Sold names are no
// longer in the basket so they render dimmed; held/bought names link to the
// stock detail page.
function TimelineGroup({
  label,
  labelClass,
  tickers,
  sectorByTicker,
  linked,
}: {
  label: string;
  labelClass: string;
  tickers: string[];
  sectorByTicker: Record<string, string>;
  linked: boolean;
}) {
  if (tickers.length === 0) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className={`w-8 shrink-0 text-[0.625rem] font-semibold uppercase tracking-[0.08em] ${labelClass}`}>
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        {tickers.map((t) => {
          const sector = sectorByTicker[t];
          return linked ? (
            <Link
              key={t}
              href={`/stock/${t}/`}
              title={sector}
              aria-label={`${t}${sector ? `, ${sector} sector` : ''}`}
              className="press inline-flex items-center font-mono text-sm font-semibold text-slate-700 hover:underline dark:text-slate-300"
            >
              {t}
            </Link>
          ) : (
            <span key={t} className="font-mono text-sm font-semibold text-slate-400 dark:text-slate-500">
              {t}
            </span>
          );
        })}
      </div>
    </div>
  );
}
