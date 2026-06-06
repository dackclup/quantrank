'use client';

import { Star } from 'lucide-react';

import { useWatchlist } from '@/lib/useWatchlist';

// "Save to watchlist" toggle for the stock-detail hero — styled as a borderless
// text-link to match the adjacent "Back to ranking" link (no border / no
// fill-box). The star's fill (outline -> filled) plus the label
// ("Save to watchlist" -> "In watchlist") carry the saved state; emerald text
// reinforces it (the watchlist semantic; amber stays reserved for warning).
//
// Renders a stable "not saved" state until `mounted` — the localStorage read
// only resolves post-hydration (see useWatchlist), so the server HTML + first
// client render both show "not saved" and only flip to filled after hydration.
// This avoids a hydration mismatch on the fill.

export function WatchlistButton({ ticker }: { ticker: string }) {
  const { isSaved, toggle, mounted } = useWatchlist();
  const saved = mounted && isSaved(ticker);

  return (
    <button
      type="button"
      onClick={() => toggle(ticker)}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`}
      className={
        'inline-flex min-h-[44px] shrink-0 items-center gap-1 text-sm press hover:opacity-70 ' +
        (saved
          ? 'text-emerald-700 dark:text-emerald-300'
          : 'text-slate-900 dark:text-slate-100')
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
