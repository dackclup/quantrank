'use client';

import Link from 'next/link';
import { Star, X } from 'lucide-react';

import { StockListCard } from '@/components/StockListCard';
import type { StockSummary } from '@/lib/types';
import { useWatchlist } from '@/lib/useWatchlist';

// Client view for /portfolio. The saved SET lives in browser localStorage (via
// useWatchlist); the row DATA is the public ranking snapshot the Server
// Component passed in as a prop — never re-read on the client (the build-time
// data rule: lib/data.ts must not reach a 'use client' module). We filter the
// rankings to the saved tickers and render the matches ordered by composite
// rank. A saved ticker that's no longer in the universe (delisted since it was
// starred) simply has no row to render; it stays in storage harmlessly.

function WatchlistCard({
  row,
  onRemove,
}: {
  row: StockSummary;
  onRemove: (ticker: string) => void;
}) {
  return (
    <li className="relative hover-lift overflow-hidden rounded border border-slate-200 bg-white transition-colors duration-100 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50">
      {/* Remove from watchlist — an X in the top-left corner. Absolute + z-10
          so it sits ABOVE the row's <Link> as a sibling (never a nested
          interactive <button> inside the <a>); preventDefault + stopPropagation
          keep a corner tap from also following the link. The row reserves
          `pl-14` so the logo clears the 44px hit target. */}
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onRemove(row.ticker);
        }}
        aria-label={`Remove ${row.ticker} from watchlist`}
        className="absolute left-1 top-1 z-10 inline-flex h-11 w-11 items-center justify-center rounded-sm text-slate-400 press hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
      >
        <X className="h-[1.125rem] w-[1.125rem]" strokeWidth={2} aria-hidden="true" />
      </button>
      <Link
        href={`/stock/${row.ticker}/`}
        className="press flex flex-col gap-1 py-3 pl-14 pr-3"
      >
        <StockListCard row={row} />
      </Link>
    </li>
  );
}

export function WatchlistView({ rankings }: { rankings: StockSummary[] }) {
  const { tickers, mounted, remove } = useWatchlist();

  const savedSet = new Set(tickers);
  const rows = rankings
    .filter((s) => savedSet.has(s.ticker))
    .sort((a, b) => a.rank - b.rank);

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-slab text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Watchlist
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {mounted ? (
            <>
              <span className="font-mono tabular-nums">{rows.length}</span>
              {` saved ${rows.length === 1 ? 'name' : 'names'} · lives entirely in your browser`}
            </>
          ) : (
            'Your saved names live entirely in your browser'
          )}
        </p>
      </header>

      {!mounted ? (
        // Static-export HTML ships this branch (localStorage isn't readable at
        // build / first paint); it swaps to the list or empty-state after the
        // post-hydration read so users with saved names never see an
        // empty-state flash.
        <div className="animate-fade-in rounded border border-slate-200 bg-white px-6 py-12 text-center shadow-subtle dark:border-slate-800 dark:bg-slate-900">
          <p className="text-sm text-slate-500 dark:text-slate-400">Loading your watchlist…</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="animate-fade-in flex flex-col items-center rounded border border-slate-200 bg-white px-6 py-12 text-center shadow-subtle dark:border-slate-800 dark:bg-slate-900">
          <Star
            aria-hidden="true"
            strokeWidth={1.5}
            className="mb-3 h-9 w-9 text-slate-300 dark:text-slate-600"
          />
          <p className="text-base font-semibold text-slate-800 dark:text-slate-100">
            No saved names yet
          </p>
          <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
            Tap the star on any stock page to add it here.
            Your watchlist lives entirely in this browser; no account needed.
          </p>
          <Link
            href="/ranking"
            className="mt-6 inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 text-sm font-semibold text-white press hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
          >
            Browse the ranking
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <WatchlistCard key={row.ticker} row={row} onRemove={remove} />
          ))}
        </ul>
      )}
    </section>
  );
}
