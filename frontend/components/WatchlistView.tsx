'use client';

import Link from 'next/link';
import { Star, X } from 'lucide-react';

import { SectorChip } from '@/components/SectorChip';
import { Sparkline } from '@/components/Sparkline';
import { StockLogo } from '@/components/StockLogo';
import type { StockSummary } from '@/lib/types';
import { useWatchlist } from '@/lib/useWatchlist';

// Client view for /portfolio. The saved SET lives in browser localStorage (via
// useWatchlist); the row DATA is the public ranking snapshot the Server
// Component passed in as a prop — never re-read on the client (the build-time
// data rule: lib/data.ts must not reach a 'use client' module). We filter the
// rankings to the saved tickers and render the matches ordered by composite
// rank. A saved ticker that's no longer in the universe (delisted since it was
// starred) simply has no row to render; it stays in storage harmlessly.
//
// Each row is a compact watchlist line — [logo · ticker · rank · sector] ·
// [price-trend Sparkline] · [price + daily-change chip] — with a trailing X to
// remove. The register stays calm/editorial (outlined-light change chip + a
// muted sign-aware sparkline), NOT a gamified trading row (PRODUCT.md
// anti-reference #1).

function WatchlistCard({
  row,
  onRemove,
}: {
  row: StockSummary;
  onRemove: (ticker: string) => void;
}) {
  const pct = row.price_change_1d_pct;
  const positive = pct != null && pct >= 0;

  return (
    <li className="hover-lift flex items-stretch overflow-hidden rounded border border-slate-200 bg-white transition-colors duration-100 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50">
      <Link
        href={`/stock/${row.ticker}/`}
        aria-label={`Open ${row.ticker} detail`}
        className="press flex min-w-0 flex-1 items-center gap-3 p-3"
      >
        {/* Left — logo + ticker (+ small rank) over the sector chip. */}
        <div className="flex shrink-0 items-center gap-2.5">
          <StockLogo ticker={row.ticker} size={32} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-base font-semibold text-slate-900 dark:text-slate-100">
                {row.ticker}
              </span>
              <span className="font-mono text-[0.625rem] tabular-nums text-slate-400 dark:text-slate-500">
                #{row.rank}
              </span>
            </div>
            <SectorChip sector={row.sector} size="xs" />
          </div>
        </div>

        {/* Middle — muted, sign-aware price-trend sparkline (the flexible column). */}
        <div className="min-w-0 flex-1 px-1">
          <Sparkline ticker={row.ticker} />
        </div>

        {/* Right — last price over the outlined-light daily-change chip. */}
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="font-mono text-base font-semibold tabular-nums text-slate-900 dark:text-slate-100">
            ${row.current_price.toFixed(2)}
          </span>
          {pct != null ? (
            <span
              className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[0.6875rem] font-semibold tabular-nums ring-1 ring-inset ${
                positive
                  ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
                  : 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800'
              }`}
            >
              <span aria-hidden="true">{positive ? '↗' : '↘'}</span>
              {positive ? '+' : ''}
              {pct.toFixed(2)}%
            </span>
          ) : (
            <span className="text-[0.6875rem] text-slate-400 dark:text-slate-500">past day n/a</span>
          )}
        </div>
      </Link>

      {/* Trailing X remove rail — a sibling of the row's <Link> (an interactive
          button can't validly nest inside an <a>); echoes the reference's
          right-side delete. Full-height rail with a >=44px hit target. */}
      <button
        type="button"
        onClick={() => onRemove(row.ticker)}
        aria-label={`Remove ${row.ticker} from watchlist`}
        className="flex min-w-[44px] shrink-0 items-center justify-center border-l border-slate-100 text-slate-400 press hover:bg-slate-100 hover:text-rose-600 dark:border-slate-800 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-rose-400"
      >
        <X className="h-[1.125rem] w-[1.125rem]" strokeWidth={2} aria-hidden="true" />
      </button>
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
        <ul className="max-w-3xl space-y-2">
          {rows.map((row) => (
            <WatchlistCard key={row.ticker} row={row} onRemove={remove} />
          ))}
        </ul>
      )}
    </section>
  );
}
