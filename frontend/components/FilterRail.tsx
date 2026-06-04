'use client';

import { FilterControls, type FilterSetters, type FilterState } from '@/components/FilterControls';

// DESKTOP (xl+) filter surface: a PERSISTENT left rail beside the ranking table —
// the screener-canonical "filters always visible" pattern (impeccable critique P1:
// a 502-row screener must not hide its primary task behind a modal drawer). Shares
// the filter BODY (`FilterControls`) with the mobile `FilterDrawer`; this is the
// non-modal shell — NO backdrop, NO focus trap, NO body-scroll-lock (it is part of
// the page, not a dialog). `hidden xl:flex`, so below xl it collapses to nothing and
// the `FilterDrawer` (+ its trigger button in the toolbar) takes over. The rail
// engages at xl (≥1280), NOT lg: at lg (1024-1279) a 288px rail squeezed the 7-col
// table below its ~700px floor (immediate horizontal scroll), so below xl the drawer
// is the better fit (frontend-design-reviewer WARN; user-chosen breakpoint).
//
// Sticky below the AppShell header (`xl:top-14`); the body scrolls inside its own
// `max-h` so a long sector list never pushes the table down.

export function FilterRail({
  state,
  setters,
  sectors,
  totalCount,
  filteredCount,
}: {
  state: FilterState;
  setters: FilterSetters;
  sectors: string[];
  totalCount: number;
  filteredCount: number;
}) {
  const { search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet } = state;
  const scoreActive = scoreRange[0] !== 0 || scoreRange[1] !== 100;
  const activeCount =
    (search ? 1 : 0) +
    (sectorSet.size ? 1 : 0) +
    (scoreActive ? 1 : 0) +
    (tierSet.size ? 1 : 0) +
    (mosSet.size ? 1 : 0) +
    (recommendationSet.size ? 1 : 0);

  return (
    <aside
      aria-label="Filters"
      className="hidden w-72 shrink-0 flex-col overflow-hidden self-start rounded border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 xl:sticky xl:top-14 xl:flex xl:max-h-[calc(100vh-4.5rem)]"
    >
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <span className="text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Filters
        </span>
        <span className="font-mono text-xs tabular-nums">
          <span className="font-semibold text-slate-900 dark:text-slate-100">
            {filteredCount.toLocaleString()}
          </span>
          <span className="text-slate-500 dark:text-slate-400"> / {totalCount.toLocaleString()}</span>
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <FilterControls state={state} setters={setters} sectors={sectors} />
      </div>

      <footer className="flex items-center justify-between gap-2 border-t border-slate-200 px-4 py-2.5 dark:border-slate-800">
        <button
          type="button"
          onClick={setters.clearAll}
          disabled={activeCount === 0}
          className="press inline-flex items-center text-xs font-medium text-slate-600 underline-offset-2 hover:text-slate-900 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline dark:text-slate-400 dark:hover:text-slate-100 dark:disabled:text-slate-500"
        >
          Clear all
        </button>
        {activeCount > 0 && (
          <span className="text-[0.6875rem] tabular-nums text-slate-500 dark:text-slate-400">
            {activeCount} active
          </span>
        )}
      </footer>
    </aside>
  );
}
