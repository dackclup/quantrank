'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';

import type { AiPickTimelineEntry, MwrPositionReturn } from '@/lib/types';
import { Chip } from '@/components/Chip';
import { SectorChip } from '@/components/SectorChip';
import {
  apportionWeightLabels,
  pctStr,
  toneClass,
} from '@/lib/portfolio-format';

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
  // The full entry — carries mwrByTicker + weightByTicker when the artifact
  // was generated with per-quarter MWR (PR-2a #618 / #619).
  entry: AiPickTimelineEntry;
  // The PRIOR quarter's mwrByTicker — used for CASE B: sold rows in this
  // quarter look up their realized exit return from the prior rebalance's
  // position_returns (the engine records the final MWR there, not in the
  // rebalance where the name exits). Absent for the initial basket (no prior).
  prevMwrByTicker?: Record<string, MwrPositionReturn>;
  // The PRIOR quarter's bandSectors — used to resolve sector chips for SOLD
  // names (names in `exited` were in last quarter's band_book, so their PIT
  // sector lives on the prior entry's bandSectors). Absent for the initial
  // basket and for pre-regen artifacts that lack band_sectors.
  prevBandSectors?: Record<string, string>;
};

/**
 * Rotation history of the AI pick: every quarterly rebalance's holdings at the
 * current basket size, newest first, with the names that entered / exited vs the
 * prior quarter.
 *
 * Each quarter row is a clickable accordion button that reveals a slide-down
 * QuarterDrawer with a detail table (# · Status · Ticker · Sector · Return ·
 * Weight). The Return column shows per-quarter MWR from the engine (the "Your
 * return" headline; PR-2b MWR/Carino redesign). When the artifact predates the
 * per-quarter MWR engine (pre-PR-2a #618), Return renders '—' gracefully.
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

  // Accordion state: set of date strings (row keys) that are currently expanded.
  // Keyed by date for stability across slider count changes.
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
      // CASE B: carry the previous entry's mwrByTicker so sold rows in the
      // QuarterDrawer can resolve their realized exit return. The engine writes
      // the final MWR into the quarter BEFORE the name exits (the last quarter
      // it was held), not into the quarter where it sold.
      const prevMwrByTicker = i > 0 ? timeline[i - 1].mwrByTicker : undefined;
      // CASE B (sector): carry the previous entry's bandSectors so sold rows can
      // resolve their sector chip — sold names were in LAST quarter's band_book.
      const prevBandSectors = i > 0 ? timeline[i - 1].bandSectors : undefined;
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
        ...(prevMwrByTicker !== undefined ? { prevMwrByTicker } : {}),
        ...(prevBandSectors !== undefined ? { prevBandSectors } : {}),
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
          const isExpanded = expandedDates.has(row.date);
          // Buy / Hold / Sell split per rebalance. The initial basket is all
          // buys by definition (no prior quarter to hold from).
          const buys = isInitial ? row.held : row.held.filter((t) => row.entered.has(t));
          const holds = isInitial ? [] : row.held.filter((t) => !row.entered.has(t));
          const sells = row.exited;

          // Unique IDs for the accordion a11y pair (aria-controls / aria-expanded).
          const headerId = `ht-btn-${row.date}`;
          const drawerId = `ht-drawer-${row.date}`;

          return (
            <li key={row.date} className="py-0">
              {/* Collapsed row — the entire row is an accordion button so the
                  touch target covers the full width. Tickers are PLAIN TEXT here
                  (not links) because an <a> nested in <button> is invalid HTML;
                  the expanded QuarterDrawer provides the clickable ticker links. */}
              <button
                type="button"
                id={headerId}
                aria-expanded={isExpanded}
                aria-controls={drawerId}
                onClick={() => toggleRow(row.date)}
                className="group flex w-full items-start gap-x-3 py-2.5 text-left min-h-[44px] focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:focus-visible:ring-emerald-400"
              >
                {/* Date column */}
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
                {/* Buy / Hold / Sell summary — plain-text tickers */}
                <div className="min-w-0 flex-1 flex flex-col gap-1">
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

              {/* Slide-down drawer — CSS grid-rows 0fr→1fr transition for
                  height-correct reveal without JS measurement (no clipping).
                  ease-in-out matches the app-wide single motion curve. */}
              <div
                id={drawerId}
                role="region"
                aria-labelledby={headerId}
                className={`grid transition-[grid-template-rows] duration-200 ease-in-out motion-reduce:transition-none${isExpanded ? ' grid-rows-[1fr]' : ' grid-rows-[0fr]'}`}
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
//
// Return = per-quarter MWR from entry.mwrByTicker[ticker].mwr_pct (PR-2b).
// Falls back to '—' when mwrByTicker is absent (pre-PR-2a #618 artifact).
// ---------------------------------------------------------------------------
function QuarterDrawer({
  row,
  isInitial,
}: {
  row: Row;
  isInitial: boolean;
}) {
  const { entry, held, entered, exited, sectorByTicker, prevMwrByTicker, prevBandSectors } = row;
  const mwrByTicker = entry.mwrByTicker;

  // Build the primary sector lookup for HELD rows: merge bandSectors (PIT map
  // covering every band_book ticker) over the holdings-derived sectorByTicker
  // fallback so that band-CARRIED names (HP/UAL/INTC) resolve correctly.
  // When bandSectors is absent (pre-regen artifact), falls back to the existing
  // holdings-based map — zero behavior change.
  const resolvedSectorByTicker: Record<string, string> = {
    ...sectorByTicker,
    ...(entry.bandSectors ?? {}),
  };
  const weightByTicker = entry.weightByTicker;
  const hasWeights = Boolean(weightByTicker && Object.keys(weightByTicker).length > 0);
  const hasMwr = Boolean(mwrByTicker && Object.keys(mwrByTicker).length > 0);

  // Sort held rows by weight descending; tickers without weights preserve
  // composite-score order (stable — spread preserves the original held order
  // which is already composite-desc from the raw artifact).
  const sortedHeld = [...held].sort((a, b) => {
    const aW = weightByTicker?.[a];
    const bW = weightByTicker?.[b];
    const aFin = aW !== null && aW !== undefined && !Number.isNaN(aW) && Number(aW) > 0;
    const bFin = bW !== null && bW !== undefined && !Number.isNaN(bW) && Number(bW) > 0;
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
      {/* Grid header — 6 columns matching AiPickPortfolio adaptive branch:
          Mobile (5 tracks, sector hidden): [1.25rem auto 1fr 4.25rem 2.75rem]
          sm+ (6 tracks, sector visible):   [1.25rem auto auto 1fr 4.25rem 2.75rem] */}
      <div className="grid items-center gap-2 grid-cols-[1.25rem_auto_1fr_4.25rem_2.75rem] sm:grid-cols-[1.25rem_auto_auto_1fr_4.25rem_2.75rem] border-b border-slate-200 pb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:border-slate-700 dark:text-slate-400">
        <span>#</span>
        <span>Status</span>
        <span>Ticker</span>
        <span className="hidden sm:block">Sector</span>
        {/* "Your return" label mirrors the Current-picks card headline. A tooltip
            explains MWR vs TWR terminology so users understand the distinction
            without needing a separate help page. Scoped to the column header so
            it surfaces on hover/focus for keyboard users too. */}
        <span
          className="text-right cursor-help"
          title="Your return = money-weighted return (MWR): your actual return given when the system trimmed or added at different prices."
          aria-label="Your return (money-weighted). See tooltip for explanation."
        >
          Your return
        </span>
        <span className="text-right">Weight</span>
      </div>
      <ol className="divide-y divide-slate-100 dark:divide-slate-800">
        {sortedHeld.map((ticker, i) => {
          // Status: New if the ticker entered THIS quarter; Held otherwise.
          // For the initial basket, everything is "New" (i===0 → entered is empty
          // in the chronological build, but isInitial means no prior → all buys).
          const isNew = isInitial || entered.has(ticker);
          const pr: MwrPositionReturn | null = mwrByTicker?.[ticker] ?? null;
          const mwr = pr?.mwr_pct ?? null;

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
                {resolvedSectorByTicker[ticker]
                  ? <SectorChip sector={resolvedSectorByTicker[ticker]} />
                  : null}
              </span>
              {/* Return cell — MWR headline ("Your return").
                  Genuine null (missing data or pre-engine artifact) renders '—'. */}
              <MwrReturnCell
                mwr={mwr}
                hasMwr={hasMwr}
              />
              <span className="text-right font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                {hasWeights ? weightLabels[i] : '—'}
              </span>
            </li>
          );
        })}

        {/* Sold rows — tickers exited AT this rebalance. Appended after held rows.
            First sold row gets a slightly stronger top border to visually separate
            the "out of basket" appendix from the active holdings. */}
        {exited.map((ticker, j) => {
          // CASE B: the engine writes a sold ticker's realized exit return into
          // the PRIOR rebalance's position_returns (the last quarter it was held),
          // NOT into the current rebalance's map (where it has weight 0 and is
          // absent). Look up prevMwrByTicker first; fall back to the current
          // quarter's map only if somehow present there (should not happen, but
          // keeps the lookup safe against future engine changes).
          const prSold: MwrPositionReturn | null =
            prevMwrByTicker?.[ticker] ?? mwrByTicker?.[ticker] ?? null;
          const mwrSold = prSold?.mwr_pct ?? null;
          // Sector for SOLD rows: prefer prevBandSectors (the prior quarter's PIT
          // sector map — the sold name was in LAST quarter's band_book) then fall
          // back to the current resolved map (covers the holdings-based fallback).
          const sector =
            prevBandSectors?.[ticker] ??
            resolvedSectorByTicker[ticker] ??
            '';
          // hasMwr for sold rows: use the broader check — if EITHER the current or
          // prior quarter has MWR data for ANY ticker, the column is enabled.
          const hasMwrForSold = hasMwr || Boolean(prevMwrByTicker && Object.keys(prevMwrByTicker).length > 0);
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
              {/* Sold row: realized exit return from the prior rebalance's map
                  (CASE B — prevMwrByTicker lookup at call site above). */}
              <MwrReturnCell
                mwr={mwrSold}
                hasMwr={hasMwrForSold}
              />
              {/* Weight: em-dash — the ticker is no longer in the basket; "0.0%"
                  would read as a real allocation. Muted alignment matches the
                  return-cell dash convention (text-slate-400 dark:text-slate-500).
                  GUARD: sold row weight is NEVER included in any aggregate total
                  (the footer reads only held rows; this is a display-only cell). */}
              <span className="text-right font-mono text-sm tabular-nums text-slate-400 dark:text-slate-500">
                —
              </span>
            </li>
          );
        })}
      </ol>
      {!hasMwr && (
        <p className="mt-2 text-[0.625rem] text-slate-400 dark:text-slate-500">
          Per-quarter return data unavailable for this quarter (pre-engine artifact).
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MWR Return cell — shared between held and sold rows in QuarterDrawer.
// Headline: MWR ("Your return").
// When hasMwr is false (legacy artifact), renders '—' consistently.
// Genuine null mwr (missing data) renders '—'; real mwr renders normally.
// CASE B (sold rows) is handled at the call site via prevMwrByTicker lookup.
// ---------------------------------------------------------------------------
function MwrReturnCell({
  mwr,
  hasMwr,
}: {
  mwr: number | null;
  hasMwr: boolean;
}) {
  // When the artifact has no MWR data at all, render a plain muted dash.
  // This path fires for all rows in a pre-#618 artifact.
  if (!hasMwr) {
    return (
      <span className="text-right font-mono text-sm font-semibold tabular-nums text-slate-400 dark:text-slate-500">
        —
      </span>
    );
  }

  // MWR data present but this specific ticker is absent → mwr=null (genuinely
  // missing data — e.g. sold ticker not in any known prior-rebalance map).
  if (mwr === null) {
    return (
      <span className="text-right font-mono text-sm font-semibold tabular-nums text-slate-400 dark:text-slate-500">
        —
      </span>
    );
  }

  return (
    <span
      className="text-right"
      aria-label={`Your return ${pctStr(mwr)}`}
    >
      {/* MWR headline */}
      <span className={`block font-mono text-sm font-semibold tabular-nums ${toneClass(mwr)}`}>
        {pctStr(mwr)}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// One labeled sub-row of a rebalance (Buy / Hold / Sell). The collapsed-row
// summary lives INSIDE the accordion `<button>`, so its tickers are PLAIN TEXT
// — not links (interactive content can't nest inside a button, and the row's
// only action is toggling the drawer). The clickable ticker links live in the
// expanded QuarterDrawer instead. `muted` dims the Sell group so the eye reads
// it as "out of basket" while Buy/Hold stay legible.
// ---------------------------------------------------------------------------
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
