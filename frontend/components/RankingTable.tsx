'use client';

import Link from 'next/link';
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, useTransition } from 'react';
import { SearchX } from 'lucide-react';

import { LossChanceBadge } from '@/components/LossChanceBadge';
import { MidcapChip } from '@/components/MidcapChip';
import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { SmallcapChip } from '@/components/SmallcapChip';
import { StockListCard } from '@/components/StockListCard';
import { StockLogo } from '@/components/StockLogo';
import type { StockSummary } from '@/lib/types';
import { useFlip } from '@/lib/useFlip';

export type SortKey =
  | 'rank'
  | 'ticker'
  | 'name'
  | 'sector'
  | 'composite_score'
  | 'current_price'
  | 'fair_price'
  | 'margin_of_safety_pct'
  // `loss_chance_pct` has no column header (the Loss-Chance column isn't
  // header-sortable) but IS a valid sort key for the RankingView sort-chip row.
  // The generic comparator below handles it (number | null) like any other.
  | 'loss_chance_pct';
export type SortDir = 'asc' | 'desc';

// Window size: the number of rows rendered on initial load and each
// subsequent scroll-triggered append. Kept at 50 to match the prior
// pagination page-size — fast first-paint on mobile; additional rows
// mount as the user scrolls toward the bottom sentinel.
const WINDOW_SIZE = 50;

function formatPrice(p: number): string {
  return p.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
}

export default function RankingTable({
  data,
  cohortSize,
  showMidcapChip = true,
  showSmallcapChip = true,
  sortKey: sortKeyProp,
  sortDir: sortDirProp,
  onSortChange,
  hasActiveFilters = false,
  onClearFilters,
}: {
  data: StockSummary[];
  /**
   * Total number of stocks in the active cohort (before search filtering).
   * Used for the "X / N stocks" denominator in the search toolbar.
   * Defaults to `data.length` when omitted (whole-universe view).
   */
  cohortSize?: number;
  /**
   * Show the MidcapChip (S&P 400 badge) in table rows + mobile cards.
   * Set to false in single-cohort tabs (SPX / MID) where the tab itself
   * communicates the cohort — only needed in the "All stocks" mixed view.
   * Defaults to true for backward compatibility.
   */
  showMidcapChip?: boolean;
  /**
   * Show the SmallcapChip (S&P 600 badge) in table rows + mobile cards.
   * Set to false in single-cohort tabs (SPX / MID / SML) where the tab itself
   * communicates the cohort — only needed in the "All stocks" mixed view.
   * Defaults to true for backward compatibility; renders nothing today because
   * sp600 rows don't exist yet (data-driven dormancy — chip renders null for
   * non-sp600 index_membership values).
   */
  showSmallcapChip?: boolean;
  /**
   * Controlled sort state (optional). When provided, the table binds its
   * column-header sort to these props + reports changes via `onSortChange`,
   * so an EXTERNAL affordance (the RankingView sort-chip row) and the column
   * headers share ONE source of truth. When omitted, the table falls back to
   * its own internal sort state (backward-compatible standalone behavior).
   */
  sortKey?: SortKey;
  sortDir?: SortDir;
  onSortChange?: (key: SortKey, dir: SortDir) => void;
  /**
   * True when an upstream (drawer) filter is narrowing `data`. Drives the
   * empty-state copy + a "Clear filters" recovery action so a zero-match from
   * a FILTER (not just search) is recoverable.
   */
  hasActiveFilters?: boolean;
  /** Clear the upstream drawer filters (shown in the empty state). */
  onClearFilters?: () => void;
}) {
  const _cohortSize = cohortSize ?? data.length;
  // Search + multi-dimension filter view. Free-text search + windowed infinite
  // scroll live here; the structured filters (MoS / composite / sector) are
  // committed in the RankingView FilterDrawer and arrive pre-applied in `data`.
  const [search, setSearch] = useState('');

  // Ref for the uncontrolled search <input>. Used to programmatically reset
  // the DOM value when the "Clear search" button fires (the React state reset
  // alone is insufficient for an uncontrolled input — the browser owns the
  // displayed value, so we must also clear input.value directly).
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Defer the 1504-row search filter so keystrokes stay responsive.
  // The <input> is now UNCONTROLLED (no `value` binding) — the browser owns
  // the displayed text, so every keystroke commits at the DOM level instantly,
  // zero React render on the critical path. `setSearch` is pushed through
  // startTransition (see onChange below), making `search` itself a low-priority
  // state update. `deferredSearch` is a second-level deferral: the expensive
  // `filtered` useMemo and the FLIP reshuffle run even lower priority, exactly
  // when the scheduler has idle time. React 18 ships both primitives.
  //
  // Why keep useDeferredValue when setSearch is already in a transition?
  // The transition ensures the browser scheduler can interrupt `setSearch`
  // commits; useDeferredValue ensures the expensive filter memo runs at the
  // scheduler's absolute lowest priority (may trail even normal transitions).
  // The combination is harmless (additive deferral, no tearing risk on an
  // uncontrolled input) and keeps `deferredSearch` as the stable anchor for
  // the FLIP filterKey and window-reset effects — the invariant those effects
  // depend on is "fires exactly when filtered rows actually commit", and
  // `deferredSearch` guarantees that regardless of how `setSearch` was called.
  const deferredSearch = useDeferredValue(search);

  // startTransition wraps the column-sort state updates so the 1504-row
  // re-sort is interruptible / low-priority. The click feedback (the arrow
  // icon swap) remains immediate; only the expensive sort computation yields.
  // Also used for search onChange (see above).
  const [, startTransition] = useTransition();

  // Sort state — controlled when the parent passes sortKey/sortDir/onSortChange
  // (RankingView's sort-chip row), else internal (standalone fallback).
  const isSortControlled = sortKeyProp !== undefined && sortDirProp !== undefined && onSortChange !== undefined;
  const [sortKeyInternal, setSortKeyInternal] = useState<SortKey>('rank');
  const [sortDirInternal, setSortDirInternal] = useState<SortDir>('asc');
  const sortKey = isSortControlled ? sortKeyProp : sortKeyInternal;
  const sortDir = isSortControlled ? sortDirProp : sortDirInternal;

  // Windowed infinite scroll — `visibleCount` tracks how many rows of the
  // sorted result are currently mounted. Starts at WINDOW_SIZE; grows by
  // WINDOW_SIZE each time the bottom sentinel enters the viewport.
  // This replaces the previous Prev/Next pagination: rows are append-only
  // (never removed once mounted), so the a11y tree, keyboard navigation,
  // and FLIP positions are all preserved. Only the FIRST WINDOW_SIZE rows
  // mount on initial render → fast first-paint on mobile with ~1500 total rows.
  const [visibleCount, setVisibleCount] = useState(WINDOW_SIZE);

  // Free-text search over ticker + company name. Empty query passes everything.
  // Keyed off deferredSearch (not the immediate `search`) so the 1504-row
  // filter runs at low priority — the keystroke commits first, then this memo
  // re-runs. The <input> is uncontrolled so its displayed text is never
  // blocked by React scheduling.
  const filtered = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase();
    if (!q) return data;
    return data.filter(
      (row) => row.ticker.toLowerCase().includes(q) || row.name.toLowerCase().includes(q),
    );
  }, [data, deferredSearch]);

  // Reset the window when the deferred filter result changes — the result set
  // has updated, so re-start from the first WINDOW_SIZE rows. Keyed on
  // deferredSearch (not `search`) so the reset fires exactly when filtered
  // rows change, not one tick early while old results are still displayed.
  useEffect(() => {
    setVisibleCount(WINDOW_SIZE);
  }, [deferredSearch]);

  // Reset the window when the upstream (drawer) filter set changes the row
  // count. Keyed on `data` (a fresh array reference is produced on every
  // committed-filter change in RankingView).
  useEffect(() => {
    setVisibleCount(WINDOW_SIZE);
  }, [data]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      let cmp = 0;
      if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv;
      else cmp = String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  // Reset visible window on sort change so we re-baseline from the top.
  // This mirrors the old `setPage(1)` on sort.
  useEffect(() => {
    setVisibleCount(WINDOW_SIZE);
  }, [sortKey, sortDir]);

  // Slice the sorted result to the current window. When the user scrolls to
  // the bottom sentinel, visibleCount grows and more rows mount.
  const visibleRows = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;

  // IntersectionObserver-based bottom sentinel. When the sentinel <div>
  // enters the viewport, append the next WINDOW_SIZE rows. The observer
  // disconnects + reconnects whenever `hasMore` changes (no-op when all
  // rows are mounted).
  //
  // FLIP invariant: scroll-triggered appends do NOT change `filterKey`
  // (the search string) — the gate in useFlip stays closed on a load-more
  // event, so the FLIP reshuffle slide never fires on scroll. Only a
  // search-text change opens the gate. ✓
  // Ref for the "Show N more" button — targeted by the a11y skip-link so
  // keyboard users can bypass the ~50 row tab-stops per batch (WCAG 2.4.1).
  const loadMoreButtonRef = useRef<HTMLButtonElement | null>(null);

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const loadMore = useCallback(() => {
    setVisibleCount((c) => Math.min(c + WINDOW_SIZE, sorted.length));
  }, [sorted.length]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      // rootMargin: pre-trigger slightly before the sentinel fully enters so
      // the next batch is queued before the user hits the bottom hard stop.
      { rootMargin: '200px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  // FLIP reshuffle ($impeccable overdrive) — when a SEARCH change reorders the
  // visible rows, the surviving rows slide from their old position to the new
  // one (transform-only, 300ms, app ease-in-out, reduced-motion guarded).
  // Search-scoped on purpose: a column-sort turns over the whole visible
  // window, so a sort-triggered FLIP would fire on <5% of rows and read as
  // broken; a search keeps survivors in the DOM, so partial animation there is
  // semantically correct ("the field responded"). `orderKey` re-runs the
  // measure on ANY order change (sort / scroll silently re-baseline); `filterKey`
  // is what GATES the play.
  //
  // filterKey is keyed on deferredSearch (not `search`) so the FLIP gate
  // opens exactly when the deferred filtered rows actually commit — the rows
  // have already moved by the time useFlip fires, so the FLIP measures the
  // real old→new positions. Opening on `search` (immediate) would fire the
  // gate one React batch early, before filtered changes, giving stale positions.
  // This invariant is preserved by the uncontrolled-input refactor: `deferredSearch`
  // still trails `search` by exactly one scheduler yield, same as before.
  const orderKey = visibleRows.map((r) => r.ticker).join(',');
  const filterKey = deferredSearch;
  const tbodyFlipRef = useFlip<HTMLTableSectionElement>(orderKey, filterKey);
  const cardsFlipRef = useFlip<HTMLUListElement>(orderKey, filterKey);

  // Row stagger-entrance. The animate class is intentionally BAKED into the
  // static HTML (NOT gated behind a usePlayOnMount effect) so the rows start at
  // the `rise-in` keyframe's `from` state (opacity:0) from the very FIRST paint
  // (a one-frame-opaque-then-snap flash otherwise). Hydration-safe: `animateRows`
  // derives ONLY from `visibleCount` (WINDOW_SIZE) + `firstRenderRef.current`
  // (true) at first render, identical on the build-time prerender and the
  // client's hydration render. Plays ONCE per mount (`firstRenderRef` flipped
  // false by an empty-dep effect that runs before any interaction), never on an
  // in-page interaction (sort / search / scroll / FLIP reshuffle).
  const firstRenderRef = useRef(true);
  useEffect(() => {
    firstRenderRef.current = false;
  }, []);
  // Only stagger-animate the initial WINDOW_SIZE rows on first render.
  const animateRows = visibleCount === WINDOW_SIZE && firstRenderRef.current;

  const onSort = (key: SortKey) => {
    let nextDir: SortDir;
    if (sortKey === key) {
      nextDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      const descByDefault: SortKey[] = [
        'composite_score',
        'fair_price',
        'margin_of_safety_pct',
      ];
      nextDir = descByDefault.includes(key) ? 'desc' : 'asc';
    }
    // Wrap state updates in a transition so the 1504-row re-sort runs at
    // low priority (interruptible). The click is acknowledged immediately;
    // the expensive sorted useMemo AND the arrow-icon indicator swap yield
    // together at low priority (in controlled mode the arrow reads the
    // parent's sortKey/sortDir props, which only update once the deferred
    // onSortChange commits — single source of truth, no tearing). Desktop
    // INP fix for the 232–280ms column-sort longtask.
    if (isSortControlled) {
      startTransition(() => {
        onSortChange!(key, nextDir);
      });
    } else {
      startTransition(() => {
        setSortKeyInternal(key);
        setSortDirInternal(nextDir);
      });
    }
  };

  const headerCell = (key: SortKey, label: string, extraClass = '') => {
    const active = sortKey === key;
    return (
      <th
        scope="col"
        aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
        tabIndex={0}
        className={`cursor-pointer select-none px-3 py-2 text-left font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 ${extraClass}`}
        onClick={() => onSort(key)}
        // Keyboard parity for the click-to-sort header (WCAG 2.1.1 / 4.1.2).
        // tabIndex makes the columnheader focusable; Enter/Space activate the
        // same sort. preventDefault on Space stops the page from scrolling. The
        // visible focus indicator comes from the global `:focus-visible` ring in
        // globals.css — do NOT add `focus:outline-none` here without a replacement.
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSort(key);
          }
        }}
      >
        {label}
        <span className="ml-1 inline-block text-slate-500 dark:text-slate-400" aria-hidden="true">
          {active ? (
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className={`transition-transform duration-150 ${sortDir === 'desc' ? 'rotate-180' : ''}`}
            >
              <polyline points="2 3 5 7 8 3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : (
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-slate-300 opacity-60 dark:text-slate-700"
            >
              <polyline points="2 3 5 5 8 3" strokeLinecap="round" strokeLinejoin="round" />
              <polyline points="2 7 5 5 8 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </span>
      </th>
    );
  };

  return (
    <div className="relative space-y-3">
      {/* Toolbar: inline search + result count. */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12.5rem] max-w-xs flex-1">
          {/*
            UNCONTROLLED input (no `value` binding) — the browser owns the
            displayed text so keystrokes commit at the DOM level instantly,
            zero React render per character on the interaction's critical path.
            This removes the CONTROLLED-input re-render that was the root cause
            of the 208ms first-keystroke INP at 4× CPU throttle.

            onChange pushes the value into React state via startTransition so
            `setSearch` is low-priority and can be interrupted — the filter
            memo + FLIP reshuffle both depend on `deferredSearch` which trails
            even further, keeping all expensive work off the critical path.

            `inputRef` is used by "Clear search" to reset the DOM value
            synchronously alongside the React state reset (an uncontrolled
            input does not reflect state resets in the DOM automatically).
          */}
          <input
            ref={inputRef}
            type="search"
            placeholder="Search ticker or name…"
            aria-label="Search stocks by ticker or company name"
            defaultValue=""
            onChange={(e) => startTransition(() => setSearch(e.target.value))}
            className="min-h-[44px] w-full rounded-sm border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm placeholder-slate-500 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder-slate-400 dark:focus:border-slate-500 dark:focus:ring-slate-500"
          />
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <circle cx="9" cy="9" r="6" />
            <path d="M14 14l4 4" strokeLinecap="round" />
          </svg>
        </div>
        <div className="ml-auto text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
            {sorted.length.toLocaleString()}
          </span>
          <span className="tabular-nums text-slate-500 dark:text-slate-400"> / {_cohortSize.toLocaleString()} stocks</span>
        </div>
      </div>

      {/* A11y skip-link (WCAG 2.4.1 Bypass Blocks). Keyboard users tab through
          ~50 stock-row links per batch before reaching the "Show N more" button.
          This visually-hidden link appears on :focus-visible and moves focus
          directly to the load-more control, bypassing the row tab-stop sequence.
          Hidden when hasMore is false (all rows shown — nothing to skip to).
          The link is sr-only at rest (off-screen, never visible by default);
          it pops into view only on keyboard focus via the global :focus-visible
          ring in globals.css + the sr-only-until-focus pattern. */}
      {hasMore && (
        <a
          href="#ranking-load-more"
          className="sr-only focus:not-sr-only focus:absolute focus:z-30 focus:inline-flex focus:min-h-[44px] focus:items-center focus:rounded-sm focus:border focus:border-emerald-700 focus:bg-white focus:px-3 focus:py-1.5 focus:text-sm focus:font-medium focus:text-emerald-800 focus:shadow-sm dark:focus:border-emerald-600 dark:focus:bg-slate-900 dark:focus:text-emerald-300"
          onClick={(e) => {
            e.preventDefault();
            loadMoreButtonRef.current?.focus();
          }}
        >
          Skip to load more
        </a>
      )}

      {/* Desktop table (lg+). Portrait tablets (md→lg, 768–1023px) fall back
          to the card list below: the 6-col table needs ~700px but the md
          content area is only ~530px beside the sidebar. */}
      <div className="hidden overflow-x-auto rounded border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:block">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
          <thead className="bg-slate-50 text-[0.625rem] uppercase tracking-[0.14em] dark:bg-slate-900/60">
            <tr>
              {headerCell('rank', 'Rank')}
              {headerCell('ticker', 'Ticker')}
              {headerCell('name', 'Name')}
              {headerCell('sector', 'Sector')}
              {headerCell('composite_score', 'Score', 'text-right')}
              {headerCell('current_price', 'Price', 'text-right')}
              <th scope="col" className="px-3 py-2 text-right font-semibold text-slate-600 dark:text-slate-400">
                Loss Chance
              </th>
            </tr>
          </thead>
          <tbody ref={tbodyFlipRef} className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {visibleRows.map((row, i) => {
              // Stagger entrance on first home view this session — rows
              // cascade in (cap at 12 steps so the tail never waits > ~480ms;
              // rows beyond share the last delay). Replay-suppressed +
              // reduced-motion-safe via the shared motion system.
              const staggerClass = animateRows
                ? `animate-rise-in stagger-${Math.min(12, i + 1)}`
                : '';
              return (
                <tr key={row.ticker} data-flip-key={row.ticker} className={`hover-lift transition-colors duration-100 odd:bg-white even:bg-slate-100 hover:bg-slate-200 dark:odd:bg-slate-900 dark:even:bg-slate-900/50 dark:hover:bg-slate-800 ${staggerClass}`}>
                  <td className="px-3 py-2 font-mono tabular-nums text-slate-700 dark:text-slate-300">{row.rank}</td>
                  <td className="px-3 py-2 font-mono font-semibold text-slate-900 dark:text-slate-100">
                    <Link
                      href={`/stock/${row.ticker}/`}
                      className="inline-flex items-center gap-2 hover:text-slate-700 hover:underline dark:hover:text-slate-300"
                    >
                      <StockLogo ticker={row.ticker} size={22} />
                      <span>{row.ticker}</span>
                      <RecommendationBadge recommendation={row.recommendation} size="xs" />
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{row.name}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <SectorChip sector={row.sector} />
                      {showMidcapChip && <MidcapChip indexMembership={row.index_membership} size="sm" />}
                      {showSmallcapChip && <SmallcapChip indexMembership={row.index_membership} size="sm" />}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <ScoreBadge score={row.composite_score} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700 dark:text-slate-300">
                    {formatPrice(row.current_price)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <LossChanceBadge lossChancePct={row.loss_chance_pct} size="xs" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile + tablet cards (below lg) */}
      <ul ref={cardsFlipRef} className="space-y-2 lg:hidden">
        {visibleRows.map((row, i) => {
          const staggerClass = animateRows
            ? `animate-rise-in stagger-${Math.min(12, i + 1)}`
            : '';
          return (
            <li
              key={row.ticker}
              data-flip-key={row.ticker}
              className={`hover-lift rounded border border-slate-200 bg-white transition-colors duration-100 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50 ${staggerClass}`}
            >
              <Link
                href={`/stock/${row.ticker}/`}
                className="press flex flex-col gap-1 p-3"
              >
                <StockListCard row={row} showMidcapChip={showMidcapChip} showSmallcapChip={showSmallcapChip} />
              </Link>
            </li>
          );
        })}
      </ul>

      {/* Infinite-scroll sentinel — a zero-height div at the bottom of the
          rendered list. The IntersectionObserver above triggers `loadMore`
          when this enters the viewport (200px rootMargin pre-fires it
          slightly before the hard bottom so batches load smoothly).
          Hidden once all rows are mounted (hasMore = false). */}
      {hasMore && (
        <div
          ref={sentinelRef}
          aria-hidden="true"
          className="h-px"
          // Screen-reader note: the sentinel is aria-hidden because it
          // carries no semantic content. SR users navigate by row links;
          // all rows are in the a11y tree once mounted (append-only).
        />
      )}

      {/* "X of N" progress indicator + keyboard Load-more fallback.
          The counter is decoupled from the button:
          - Counter: visible whenever sorted.length > 0 (NOT gated on hasMore).
            When hasMore is false (all rows shown) it reads "Showing all N stocks";
            when hasMore is true it reads "Showing X of N". The aria-live region
            is always present so both the incremental count and the "all shown"
            completion state are announced to screen readers.
          - Load-more button: only shown while more rows remain (hasMore). The
            IntersectionObserver sentinel auto-loads for pointer/scroll users;
            the button is the accessible hybrid for keyboard-only users who
            cannot trigger the observer by scrolling.
          - Progress text: secondary/muted per the design system.
          - Load-more button: matches the "Clear search" / "Clear filters"
            family (same border, palette, min-h-[44px] touch target, .press
            feedback, global :focus-visible ring). Does NOT change
            `search` or `filterKey` — only `visibleCount` increments, so
            the FLIP reshuffle gate stays closed (search-scoped invariant
            is preserved, same as the scroll-triggered path). */}
      {hasMore && (
        /* role="region" + aria-label makes the load-more area a named landmark
           so screen-reader users can jump to it directly from the landmarks
           list (JAWS / NVDA "R" key). The id matches the skip-link href above. */
        <div
          id="ranking-load-more"
          role="region"
          aria-label="Load more stocks"
          tabIndex={-1}
          className="flex justify-center"
        >
          <button
            ref={loadMoreButtonRef}
            type="button"
            onClick={loadMore}
            className="inline-flex min-h-[44px] items-center rounded-sm border border-slate-300 bg-white px-4 py-1.5 text-sm font-medium text-slate-700 press hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Show{' '}
            <span className="font-mono font-semibold tabular-nums mx-1">
              {Math.min(WINDOW_SIZE, sorted.length - visibleCount).toLocaleString()}
            </span>
            {' '}more
          </button>
        </div>
      )}
      {sorted.length > 0 && (
        <p
          className="text-center text-xs tabular-nums text-slate-500 dark:text-slate-400"
          aria-live="polite"
          aria-atomic="true"
        >
          {hasMore ? (
            <>
              Showing{' '}
              <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {visibleCount.toLocaleString()}
              </span>
              {' of '}
              <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {sorted.length.toLocaleString()}
              </span>
            </>
          ) : (
            <>
              {'Showing all '}
              <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {sorted.length.toLocaleString()}
              </span>
              {' stocks'}
            </>
          )}
        </p>
      )}

      {visibleRows.length === 0 && (
        <div className="animate-fade-in flex flex-col items-center rounded border border-slate-200 bg-white px-6 py-10 text-center dark:border-slate-800 dark:bg-slate-900">
          {/* Empty-state delight ($impeccable delight): a REACHABLE moment (the
              user searched for a name that isn't in the universe). Warm + helpful,
              not wacky (finance = "read the room"): a muted glyph + a human
              heading + an actionable nudge on how to RECOVER. The icon is
              decorative (aria-hidden); fade-in is reduced-motion guarded. */}
          <SearchX
            aria-hidden="true"
            strokeWidth={1.5}
            className="mb-3 h-6 w-6 text-slate-300 dark:text-slate-600"
          />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
            {hasActiveFilters ? 'No stocks match your search and filters' : 'No stocks match your search'}
          </p>
          <p className="mt-1 max-w-xs text-xs text-slate-500 dark:text-slate-400">
            {hasActiveFilters
              ? 'Try another ticker or name, or loosen a filter to let more of the ranking through.'
              : "It may be outside the stocks we rank — try another ticker or the company's full name."}
          </p>
          {(search || hasActiveFilters) && (
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              {search && (
                <button
                  type="button"
                  onClick={() => {
                    // Uncontrolled input: must reset both the DOM value (browser-
                    // owned) and the React state. The DOM reset makes the input
                    // appear empty immediately; the React state reset clears
                    // `search` → `deferredSearch` → filtered rows via the normal
                    // deferred path. Both are required; either alone is incomplete.
                    if (inputRef.current) inputRef.current.value = '';
                    startTransition(() => setSearch(''));
                  }}
                  className="inline-flex min-h-[44px] items-center rounded-sm border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 press hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Clear search
                </button>
              )}
              {hasActiveFilters && onClearFilters && (
                <button
                  type="button"
                  onClick={onClearFilters}
                  className="inline-flex min-h-[44px] items-center rounded-sm border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 press hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
