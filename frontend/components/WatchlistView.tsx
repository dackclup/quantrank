'use client';

import Link from 'next/link';
import { Star } from 'lucide-react';

import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { StockLogo } from '@/components/StockLogo';
import { WatchlistButton } from '@/components/WatchlistButton';
import type { StockSummary } from '@/lib/types';
import { useWatchlist } from '@/lib/useWatchlist';

// Client view for /portfolio. The saved SET lives in browser localStorage (via
// useWatchlist); the row DATA is the public ranking snapshot the Server
// Component passed in as a prop — never re-read on the client (the build-time
// data rule: lib/data.ts must not reach a 'use client' module). We filter the
// rankings to the saved tickers and render the matches ordered by composite
// rank. A saved ticker that's no longer in the universe (delisted since it was
// starred) simply has no row to render; it stays in storage harmlessly.

function WatchlistCard({ row }: { row: StockSummary }) {
  return (
    <li className="hover-lift flex items-stretch overflow-hidden rounded border border-slate-200 bg-white transition-colors duration-100 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50">
      <Link
        href={`/stock/${row.ticker}/`}
        className="press flex min-w-0 flex-1 items-center gap-3 p-3"
      >
        <StockLogo ticker={row.ticker} size={36} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-lg font-semibold text-slate-900 dark:text-slate-100">
              {row.ticker}
            </span>
            <RecommendationBadge recommendation={row.recommendation} size="xs" />
          </div>
          <div className="truncate text-sm text-slate-600 dark:text-slate-300">{row.name}</div>
          <div className="mt-1">
            <SectorChip sector={row.sector} size="xs" />
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <ScoreBadge score={row.composite_score} size="md" />
          <span className="font-mono text-sm tabular-nums text-slate-700 dark:text-slate-300">
            ${row.current_price.toFixed(2)}
          </span>
        </div>
      </Link>
      {/* Dedicated right rail so the star never overlaps the row's <Link> (an
          interactive button can't validly nest inside an <a>). */}
      <div className="flex shrink-0 items-center border-l border-slate-100 pl-1 pr-1.5 dark:border-slate-800">
        <WatchlistButton ticker={row.ticker} />
      </div>
    </li>
  );
}

export function WatchlistView({ rankings }: { rankings: StockSummary[] }) {
  const { tickers, mounted } = useWatchlist();

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
            Tap the star icon on any stock — in the ranking or on a stock page — to add it here.
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
            <WatchlistCard key={row.ticker} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}
