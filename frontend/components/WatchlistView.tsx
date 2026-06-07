'use client';

import Link from 'next/link';
import { Star, Trash2 } from 'lucide-react';

import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { StockLogo } from '@/components/StockLogo';
import { WatchlistChart } from '@/components/WatchlistChart';
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
// Each saved name is a large card: the company name + composite-score donut up
// top, price / loss-chance / valuation-vs-fair beneath, and a price chart with a
// dashed fair-value line. Calm/editorial (PRODUCT.md anti-ref #1: not a gamified
// trading row) — the valuation signal is the emerald/rose fair line + a labelled
// "under / over fair value", never color alone.

function WatchlistCard({
  row,
  onRemove,
}: {
  row: StockSummary;
  onRemove: (ticker: string) => void;
}) {
  const mos = row.margin_of_safety_pct;
  // Positive MoS = price sits below fair value = undervalued (emerald); negative
  // = priced above fair value = overvalued (rose).
  const undervalued = mos != null && mos >= 0;

  return (
    <li className="relative overflow-hidden rounded border border-slate-200 bg-white shadow-subtle transition-colors duration-100 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/40">
      {/* Whole-card overlay link — keeps the rich card a single navigation
          target without nesting interactive children inside an <a>. The content
          layer is pointer-events-none so clicks fall through to this link; the
          trash button below the chart re-enables pointer events (pointer-events-auto + z-20). */}
      <Link
        href={`/stock/${row.ticker}/`}
        aria-label={`Open ${row.name} (${row.ticker}) detail`}
        className="absolute inset-0 z-0"
      />
      <div className="pointer-events-none relative z-10 p-4">
        {/* Header — sector tag over [logo + name + ticker + recommendation]
            (left); composite-score donut (right). items-center so the left
            block and the taller-or-shorter score block share a centerline
            (score number sits level with the logo/name). */}
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <SectorChip sector={row.sector} size="xs" />
            <div className="mt-2 flex min-w-0 items-center gap-3">
              <StockLogo ticker={row.ticker} size={40} />
              <div className="min-w-0">
                <div className="truncate font-slab text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {row.name}
                </div>
                <div className="mt-0.5 flex items-center gap-2">
                  <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{row.ticker}</span>
                  <RecommendationBadge recommendation={row.recommendation} size="xs" />
                </div>
              </div>
            </div>
          </div>
          <div className="shrink-0">
            <ScoreBadge score={row.composite_score} size="md" />
          </div>
        </div>

        {/* Stats — price + loss-chance (left); valuation vs fair value (right). */}
        <div className="mt-4 flex items-end justify-between gap-3">
          <div className="flex gap-6">
            <div>
              <div className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Price
              </div>
              <div className="font-mono text-base font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                ${row.current_price.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Loss chance
              </div>
              <div className="font-mono text-base font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {row.loss_chance_pct != null ? `${row.loss_chance_pct.toFixed(1)}%` : '—'}
              </div>
            </div>
          </div>
          {mos != null && (
            <div className="text-right">
              <div
                className={`font-mono text-base font-semibold tabular-nums ${
                  undervalued ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300'
                }`}
              >
                {mos >= 0 ? '+' : ''}
                {mos.toFixed(1)}%
              </div>
              <div
                className={`text-[0.6875rem] ${
                  undervalued ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'
                }`}
              >
                {undervalued ? 'under fair value' : 'over fair value'}
              </div>
            </div>
          )}
        </div>

        {/* Price chart with the dashed fair-value line. */}
        <div className="mt-4">
          <WatchlistChart
            ticker={row.ticker}
            fairPrice={row.fair_price}
            currentPrice={row.current_price}
          />
        </div>

        {/* Remove control — below the chart, right-aligned. pointer-events-auto
            + z-20 so the click lands on the button, above the whole-card overlay
            link; everywhere else on the card still navigates. */}
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            onClick={() => onRemove(row.ticker)}
            aria-label={`Remove ${row.ticker} from watchlist`}
            className="pointer-events-auto relative z-20 inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2 text-sm text-slate-500 press hover:text-rose-600 dark:text-slate-400 dark:hover:text-rose-400"
          >
            <Trash2 className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
            Remove from watchlist
          </button>
        </div>
      </div>
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
        <ul className="space-y-3">
          {rows.map((row) => (
            <WatchlistCard key={row.ticker} row={row} onRemove={remove} />
          ))}
        </ul>
      )}
    </section>
  );
}
