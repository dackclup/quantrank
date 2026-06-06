'use client';

import type { MouseEvent } from 'react';
import { Star } from 'lucide-react';

import { useWatchlist } from '@/lib/useWatchlist';

// Star toggle for saving a ticker to the browser-local watchlist. Reused on the
// ranking-table rows (icon-only square) and the stock-detail hero (labeled
// pill, where there's room and discoverability matters more).
//
// Renders a stable "not saved" state until `mounted` — the localStorage read
// only resolves post-hydration (see useWatchlist), so the server HTML + first
// client render both show "not saved" and only flip to filled after hydration.
// This avoids a hydration mismatch on the fill.
//
// In the ranking table the button sits next to a row-wide <Link>, so the click
// handler stops propagation + prevents default — a tap on the star (un)saves
// without navigating to the stock page.

interface WatchlistButtonProps {
  ticker: string;
  /** Render a labeled pill (star + text) instead of the icon-only square.
   *  Default = icon-only (ranking rows). */
  labeled?: boolean;
}

export function WatchlistButton({ ticker, labeled = false }: WatchlistButtonProps) {
  const { isSaved, toggle, mounted } = useWatchlist();
  const saved = mounted && isSaved(ticker);

  const onClick = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    toggle(ticker);
  };

  const aria = saved ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`;

  if (labeled) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-pressed={saved}
        aria-label={aria}
        className={
          'inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-sm border px-3 py-2 text-sm font-medium press ' +
          (saved
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 dark:hover:bg-emerald-900/50'
            : 'border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800')
        }
      >
        <Star
          className="h-4 w-4"
          strokeWidth={2}
          fill={saved ? 'currentColor' : 'none'}
          aria-hidden="true"
        />
        <span>{saved ? 'In watchlist' : 'Save to watchlist'}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={saved}
      aria-label={aria}
      title={saved ? 'In your watchlist' : 'Add to watchlist'}
      className={
        'inline-flex min-h-[44px] w-11 items-center justify-center rounded-sm press hover:bg-slate-100 dark:hover:bg-slate-800 ' +
        (saved
          ? 'text-emerald-600 hover:text-emerald-700 dark:text-emerald-500 dark:hover:text-emerald-400'
          : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300')
      }
    >
      <Star
        className="h-[1.125rem] w-[1.125rem]"
        strokeWidth={2}
        fill={saved ? 'currentColor' : 'none'}
        aria-hidden="true"
      />
    </button>
  );
}
