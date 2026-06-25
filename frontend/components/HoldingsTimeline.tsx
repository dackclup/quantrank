'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';

import type { AiPickTimelineEntry } from '@/lib/types';
import { Chip } from '@/components/Chip';
import { SectorChip } from '@/components/SectorChip';
import { apportionWeightLabels, pctStr, toneClass } from '@/lib/portfolio-format';

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
  // The slice width used for this row — equals each entry's own adaptiveCount
  // in adaptive mode, or the fixed `count` prop in slider mode.
  sliceCount: number;
  // FAIL-1: when the rebalance has a band_book, the held set is EXACT (not a
  // prefix). Attached wholesale from the entry so the drawer can access it.
  entry: AiPickTimelineEntry;
};

/**
 * Rotation history of the AI pick: every quarterly rebalance's holdings at the
 * current basket size, newest first, with the names that entered / exited vs the
 * prior quarter.
 *
 * Each quarter row is clickable to expand a slide-down drawer with a
 * Current-picks-style detail table (# · Status · Ticker · Sector · Return ·
 * Weight). Build-time-precomputed weightByTicker + returnByTicker drive the
 * numeric columns; when absent (legacy slider artifact) those columns render '—'.
 *
 * Two modes — selected automatically from the data:
 * - ADAPTIVE mode: when every entry carries `adaptiveCount`, each quarter is
 *   sliced to ITS OWN count (the adaptive basket varies quarter-to-quarter).
 *   The caption reflects the variable basket size instead of quoting a fixed N.
 * - SLIDER mode (legacy): all entries are sliced to the single `count` prop.
 *   Reactive to the count slider exactly as before — behavior is unchanged.
 *
 * Read-only display — links each ticker to its detail page.
 */
export function HoldingsTimeline({
  timeline,
  count,
}: {
  timeline: AiPickTimelineEntry[];
  count: number;
}) {
  // Adaptive mode: true when every entry in the timeline carries adaptiveCount.
  // A single missing entry falls back to slider mode (safe for partial artifacts).
  const isAdaptive = timeline.length > 0 && timeline.every(
    (e) => typeof e.adaptiveCount === 'number',
  );

  // Accordion state: set of row indices (in the displayed `rows` order) that are
  // currently expanded. Keyed by the row's date string for stability across slider
  // count changes (adaptive mode: always stable; slider mode: same dates).
  const [expandedDates, setExpandedDates] = useState<Set<string>>(new Set());

  const toggleRow = (date: string) => {
    setExpandedDates((prev) => {
      const next = new Set(prev);
      if (next.has(date)) {
        next.delete(date);
      } else {
        next.add(date);
      }
      return next;
    });
  };

  const { rows, avgTurnover } = useMemo(() => {
    const chrono: Row[] = [];
    let prev: string[] = [];
    let totalEntered = 0;
    for (let i = 0; i < timeline.length; i += 1) {
      const entry = timeline[i];
      // When the entry carries bandBook, use the EXACT held set
      // (the band book is NOT a prefix of `holdings`). Build sectorByTicker
      // from the full holdings list so band-carried names whose rank may have
      // fallen below the count slice still resolve.
      const hasBandBook = Array.isArray(entry.bandBook) && entry.bandBook.length > 0;
      const sectorByTicker: Record<string, string> = {};
      for (const h of entry.holdings) sectorByTicker[h.ticker] = h.sector;

      let held: string[];
      let sliceCount: number;
      if (hasBandBook) {
        // STATE 1: band book is the authoritative membership; sliceCount
        // equals bandHeldCount (== band_book.length).
        held = entry.bandBook as string[];
        sliceCount = held.length;
      } else {
        // STATE 2 (adaptive-pre-band) or slider mode: prefix slice.
        // In adaptive mode each quarter uses its own count.
        // In slider mode use the fixed `count` prop so legacy behavior is
        // completely unchanged.
        sliceCount = isAdaptive
          ? (entry.bandHeldCount ?? entry.adaptiveCount as number)
          : count;
        const slice = entry.holdings.slice(0, sliceCount);
        held = slice.map((h) => h.ticker);
      }

      const prevSet = new Set(prev);
      const heldSet = new Set(held);
      // i === 0 is the initial basket — "entered vs the prior quarter" is
      // undefined, so don't false-flag every name as new (the row carries the
      // "initial basket" sub-label instead).
      const entered = i === 0 ? new Set<string>() : new Set(held.filter((t) => !prevSet.has(t)));
      const exited = prev.filter((t) => !heldSet.has(t));
      if (i > 0) totalEntered += entered.size;
      chrono.push({
        date: entry.date,
        held,
        entered,
        exited,
        sectorByTicker,
        sliceCount,
        entry,
      });
      prev = held;
    }
    const transitions = Math.max(1, timeline.length - 1);
    chrono.reverse(); // newest first for display
    return { rows: chrono, avgTurnover: totalEntered / transitions };
  }, [timeline, count, isAdaptive]);

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
        {isAdaptive ? (
          <>
            ~<span className="font-mono tabular-nums">{avgTurnover.toFixed(1)}</span> names rotate each
            quarter — the AI re-sizes the basket each quarter
          </>
        ) : (
          <>
            ~<span className="font-mono tabular-nums">{avgTurnover.toFixed(1)}</span> of{' '}
            <span className="font-mono tabular-nums">{count}</span> names change each quarter
          </>
        )}
      </p>
      <ol className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((row, idx) => {
          const isInitial = idx === rows.length - 1; // last displayed = oldest
          // Buy / Hold / Sell split per rebalance. The initial basket is all
          // buys by definition (no prior quarter to hold from).
          const buys = isInitial ? row.held : row.held.filter((t) => row.entered.has(t));
          const holds = isInitial ? [] : row.held.filter((t) => !row.entered.has(t));
          const sells = row.exited;
          const isExpanded = expandedDates.has(row.date);
          const drawerId = `timeline-drawer-${row.date}`;
          const headerId = `timeline-header-${row.date}`;

          return (
            <li key={row.date} className="py-0">
              {/* Accordion header — full-width clickable button wrapping the
                  existing summary content. min-h-[44px] touch target per
                  project design system (interactive controls rule). */}
              <button
                type="button"
                id={headerId}
                aria-expanded={isExpanded}
                aria-controls={drawerId}
                onClick={() => toggleRow(row.date)}
                className="press flex w-full min-h-[44px] items-start gap-x-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:focus-visible:ring-emerald-400"
              >
                {/* Date + sub-labels (left column — fixed width to match the
                    old grid 5.5rem column) */}
                <span className="w-[5.5rem] shrink-0 pt-0.5 font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">
                  {monthLabel(row.date)}
                  {isInitial && (
                    <span className="mt-0.5 block text-[0.625rem] text-slate-400 dark:text-slate-500">
                      initial basket
                    </span>
                  )}
                  {isAdaptive && (
                    <span className="mt-0.5 block text-[0.625rem] tabular-nums text-slate-400 dark:text-slate-500">
                      {row.sliceCount} {row.sliceCount === 1 ? 'name' : 'names'}
                    </span>
                  )}
                </span>
                {/* Buy/Hold/Sell summary (middle — grows to fill) */}
                <div className="flex flex-1 flex-col gap-1">
                  <TimelineGroup
                    label="Buy"
                    labelClass="text-emerald-700 dark:text-emerald-400"
                    tickers={buys}
                    sectorByTicker={row.sectorByTicker}
                  />
                  <TimelineGroup
                    label="Hold"
                    labelClass="text-slate-500 dark:text-slate-400"
                    tickers={holds}
                    sectorByTicker={row.sectorByTicker}
                  />
                  <TimelineGroup
                    label="Sell"
                    labelClass="text-rose-600 dark:text-rose-400"
                    tickers={sells}
                    sectorByTicker={row.sectorByTicker}
                    muted
                  />
                  {buys.length === 0 && sells.length === 0 && !isInitial && (
                    <span className="text-xs text-slate-400 dark:text-slate-500">reweighted only</span>
                  )}
                </div>
                {/* Chevron disclosure indicator */}
                <span className="mt-1 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden="true">
                  <ChevronDown
                    size={14}
                    className={`transition-transform duration-200 ease-in-out motion-reduce:transition-none${isExpanded ? ' rotate-180' : ''}`}
                  />
                </span>
              </button>

              {/* Slide-down drawer — CSS grid-rows 0fr→1fr transition for exact
                  height-correct reveal without JS measurement (no clipping).
                  ease-in-out matches the app-wide single motion curve. */}
              <div
                id={drawerId}
                role="region"
                aria-labelledby={headerId}
                className={`grid transition-[grid-template-rows] duration-200 ease-in-out motion-reduce:duration-0${isExpanded ? ' grid-rows-[1fr]' : ' grid-rows-[0fr]'}`}
              >
                <div className="overflow-hidden">
                  <QuarterDrawer
                    row={row}
                    isInitial={isInitial}
                  />
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-quarter drawer — Current-picks-style detail table.
// Columns: # · Status · Ticker · Sector · Return · Weight.
// Held rows sorted weight-desc (mirrors AiPickPortfolio Current picks order).
// Sold rows appended after held rows.
// ---------------------------------------------------------------------------

function QuarterDrawer({
  row,
  isInitial,
}: {
  row: Row;
  isInitial: boolean;
}) {
  const { entry, held, entered, exited, sectorByTicker } = row;
  const weightByTicker = entry.weightByTicker;
  const returnByTicker = entry.returnByTicker;
  const hasData = Boolean(weightByTicker || returnByTicker);

  // Sort held rows by weight descending; tickers without weights preserve
  // composite-score order (stable — spread preserves the original held order
  // which is already composite-desc from the raw artifact).
  const sortedHeld = [...held].sort((a, b) => {
    const aW = weightByTicker?.[a];
    const bW = weightByTicker?.[b];
    const aFin = aW !== null && aW !== undefined && !Number.isNaN(aW) && aW > 0;
    const bFin = bW !== null && bW !== undefined && !Number.isNaN(bW) && bW > 0;
    if (aFin && bFin) return (bW as number) - (aW as number);
    if (aFin) return -1;
    if (bFin) return 1;
    return 0;
  });

  // Hamilton apportionment for the weight labels so per-row toFixed(1) rounding
  // doesn't drift the column total (same as AiPickPortfolio Current picks).
  const rawWeights = sortedHeld.map((t) => weightByTicker?.[t] ?? null);
  const weightLabels = apportionWeightLabels(rawWeights);

  return (
    <div className="mb-2 mt-0.5 rounded border border-slate-100 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-800/50">
      {!hasData && (
        <p className="text-xs text-slate-400 dark:text-slate-500">
          Weight and return data unavailable for this quarter.
        </p>
      )}
      {/* Grid header — 6 columns matching AiPickPortfolio adaptive branch:
          Mobile (5 tracks, sector hidden): [1.25rem auto 1fr 4.25rem 2.75rem]
          sm+ (6 tracks, sector visible):   [1.25rem auto auto 1fr 4.25rem 2.75rem] */}
      <div className="grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem] border-b border-slate-200 pb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:border-slate-700 dark:text-slate-400">
        <span>#</span>
        <span>Status</span>
        <span>Ticker</span>
        <span className="hidden sm:block">Sector</span>
        <span className="text-right">Return</span>
        <span className="text-right">Weight</span>
      </div>
      <ol className="divide-y divide-slate-100 dark:divide-slate-800">
        {sortedHeld.map((ticker, i) => {
          // Status: New if the ticker entered THIS quarter; Held otherwise.
          // For the initial basket, everything is "New" (i===0 → entered is empty
          // in the chronological build, but isInitial means no prior → all buys).
          const isNew = isInitial || entered.has(ticker);
          const retVal = returnByTicker?.[ticker] ?? null;
          return (
            <li
              key={ticker}
              className="grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem] py-2"
            >
              <span className="font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
                {i + 1}
              </span>
              {/* Status chip — New = emerald positive-light; Held = slate neutral.
                  Both xs size for compact table rows. Same tones as Current picks. */}
              {isNew ? (
                <Chip
                  size="xs"
                  tone="bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800"
                  dot="bg-emerald-500 dark:bg-emerald-400"
                >
                  New
                </Chip>
              ) : (
                <Chip
                  size="xs"
                  tone="bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:ring-slate-700"
                  dot="bg-slate-500 dark:bg-slate-400"
                >
                  Held
                </Chip>
              )}
              <Link
                href={`/stock/${ticker}/`}
                className="press font-mono text-sm font-semibold text-slate-900 hover:underline dark:text-slate-100"
              >
                {ticker}
              </Link>
              <span className="hidden sm:block">
                {sectorByTicker[ticker]
                  ? <SectorChip sector={sectorByTicker[ticker]} />
                  : null}
              </span>
              <span className={`text-right font-mono text-sm font-semibold tabular-nums ${toneClass(retVal)}`}>
                {pctStr(retVal)}
              </span>
              <span className="text-right font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                {weightLabels[i]}
              </span>
            </li>
          );
        })}

        {/* Sold rows — tickers exited AT this rebalance. Appended after held rows.
            First sold row gets a slightly stronger top border to visually separate
            the "out of basket" appendix from the active holdings. */}
        {exited.map((ticker, j) => {
          const retVal = returnByTicker?.[ticker] ?? null;
          const sector = sectorByTicker[ticker] ?? '';
          return (
            <li
              key={ticker}
              className={`grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem] py-2${j === 0 ? ' border-t border-t-slate-300 dark:border-t-slate-600' : ''}`}
            >
              <span className="font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
                {sortedHeld.length + j + 1}
              </span>
              {/* Sold chip — negative/red tone matching the design-system Negative
                  row (bg-red-50 text-rose-800 ring-red-200 + rose dot; same as the
                  Current picks Sold chip in AiPickPortfolio). */}
              <Chip
                size="xs"
                tone="bg-red-50 text-rose-800 ring-red-200 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800"
                dot="bg-rose-500 dark:bg-rose-400"
              >
                Sold
              </Chip>
              <Link
                href={`/stock/${ticker}/`}
                className="press font-mono text-sm font-semibold text-slate-500 hover:underline dark:text-slate-400"
              >
                {ticker}
              </Link>
              <span className="hidden sm:block">
                {sector ? <SectorChip sector={sector} /> : null}
              </span>
              {/* Return: entry→exit total return. Full emerald/rose tone so the
                  return is the row's headline even though ticker/sector are muted. */}
              <span className={`text-right font-mono text-sm font-semibold tabular-nums ${toneClass(retVal)}`}>
                {pctStr(retVal)}
              </span>
              {/* Weight: 0.0% — the ticker is no longer in the basket. */}
              <span className="text-right font-mono text-sm tabular-nums text-slate-400 dark:text-slate-500">
                0.0%
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One labeled sub-row of a rebalance (Buy / Hold / Sell). Sold names are no
// longer in the basket so they render dimmed; held/bought names link to the
// stock detail page.
// ---------------------------------------------------------------------------
// The collapsed-row summary lives INSIDE the accordion `<button>`, so its
// tickers are PLAIN TEXT — not links (interactive content can't nest inside a
// button, and the row's only action is toggling the drawer). The clickable
// ticker links live in the expanded QuarterDrawer instead. `muted` dims the
// Sell group so the eye reads it as "out of basket" while Buy/Hold stay legible.
function TimelineGroup({
  label,
  labelClass,
  tickers,
  sectorByTicker,
  muted = false,
}: {
  label: string;
  labelClass: string;
  tickers: string[];
  sectorByTicker: Record<string, string>;
  muted?: boolean;
}) {
  if (tickers.length === 0) return null;
  return (
    <div className="flex items-baseline gap-2">
      <span className={`w-8 shrink-0 text-[0.625rem] font-semibold uppercase tracking-[0.08em] ${labelClass}`}>
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        {tickers.map((t) => (
          <span
            key={t}
            title={sectorByTicker[t]}
            className={`font-mono text-sm font-semibold ${
              muted
                ? 'text-slate-400 dark:text-slate-500'
                : 'text-slate-700 dark:text-slate-300'
            }`}
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}
