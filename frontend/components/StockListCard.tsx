import { MidcapChip } from '@/components/MidcapChip';
import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { SmallcapChip } from '@/components/SmallcapChip';
import { StockLogo } from '@/components/StockLogo';
import { formatMosPct } from '@/lib/format';
import type { StockSummary } from '@/lib/types';

// Shared rich list-card body for a single stock. Rendered as a Fragment of
// flex-col siblings, so it drops straight into a `flex flex-col gap-1` <Link>
// wrapper (the consumer owns the <li> + <Link> + any FLIP / stagger / remove
// overlay). Used by BOTH the ranking mobile-card list (RankingTable) and the
// /portfolio watchlist (WatchlistView) so the two surfaces render an identical
// card — header (rank pill + sector chip · logo + ticker + recommendation ·
// name · score donut) over a 2-column quote block (price + daily change ·
// loss-chance band).

export function StockListCard({
  row,
  showMidcapChip = true,
  showSmallcapChip = true,
}: {
  row: StockSummary;
  /**
   * Show the "Mid-cap" chip beside the sector chip. Set to false in
   * single-cohort tabs (SPX / MID) where the tab already communicates
   * the cohort; true (default) in the "All stocks" mixed view.
   */
  showMidcapChip?: boolean;
  /**
   * Show the "Small-cap" chip beside the sector chip. Set to false in
   * single-cohort tabs (SPX / MID / SML) where the tab already communicates
   * the cohort; true (default) in the "All stocks" mixed view.
   * Renders nothing today (data-driven dormancy — SmallcapChip returns null
   * for non-sp600 index_membership values until sp600 data lands post-Slice 7).
   */
  showSmallcapChip?: boolean;
}) {
  const mos = formatMosPct(row.margin_of_safety_pct);

  return (
    <>
      {/* Header — rank pill + sector chip on the top line, then
          [logo] TICKER [recommendation] on the next line, then company
          name. ScoreBadge floats on the right. */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="inline-flex items-center rounded-sm bg-slate-100 px-1.5 py-0.5 font-mono font-medium text-slate-600 tabular-nums dark:bg-slate-800 dark:text-slate-300">
              #{row.rank}
            </span>
            <SectorChip sector={row.sector} size="xs" />
            {showMidcapChip && <MidcapChip indexMembership={row.index_membership} />}
            {showSmallcapChip && <SmallcapChip indexMembership={row.index_membership} />}
          </div>
          <div className="mt-1 flex items-center gap-2">
            <StockLogo ticker={row.ticker} size={32} />
            <span className="font-mono text-xl font-semibold">{row.ticker}</span>
            <RecommendationBadge recommendation={row.recommendation} size="xs" />
          </div>
          <div className="truncate text-sm text-slate-700 dark:text-slate-300">{row.name}</div>
        </div>
        <div className="shrink-0">
          <ScoreBadge score={row.composite_score} size="md" />
        </div>
      </div>
      {/* 2-column symmetric quote block — label sits inline BEFORE the number
          ("PRICE $123.01 USD"), with the supporting pill on the second line. */}
      <div className="mt-1 grid grid-cols-2 gap-3">
        <div className="flex flex-col items-start gap-1">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Price
            </span>
            <span className="font-mono text-[0.8125rem] font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              ${row.current_price.toFixed(2)}
            </span>
            <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              USD
            </span>
          </div>
          {row.price_change_1d_pct != null && (() => {
              const pct = row.price_change_1d_pct;
              const positive = pct >= 0;
              // Daily change reads as an outlined-light chip in the one shared
              // chip family — NOT a solid green/red dopamine pill (PRODUCT.md
              // "calm, never urgent"). The ↗/↘ arrow is a non-color affordance
              // so direction still reads without color (state is never
              // color-only).
              const pillCls = positive
                ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
                : 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800';
              const absCls = positive
                ? 'text-emerald-700 dark:text-emerald-300'
                : 'text-rose-700 dark:text-rose-300';
              // Derive absolute $ change from current_price + pct (the same
              // identity CurrentPriceLine uses on the detail page:
              // abs = price * pct / (100 + pct)).
              const abs = (row.current_price * pct) / (100 + pct);
              return (
                <div className="flex items-center gap-1.5 text-[0.6875rem]">
                  <span className={`font-mono font-semibold tabular-nums ${absCls}`}>
                    {positive ? '+' : ''}
                    {abs.toFixed(2)}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-semibold tabular-nums ring-1 ring-inset ${pillCls}`}
                  >
                    <span aria-hidden="true">{positive ? '↗' : '↘'}</span>
                    {positive ? '+' : ''}
                    {pct.toFixed(2)}%
                  </span>
                  <span className="whitespace-nowrap text-slate-500 dark:text-slate-400">past day</span>
                </div>
              );
            })()}
        </div>
        <div className="flex flex-col items-end gap-1">
          {row.loss_chance_pct != null ? (
            (() => {
              const pct = row.loss_chance_pct;
              const rounded = Math.round(pct);
              // Match LossChanceBadge band rubric (band thresholds mirror
              // frontend/components/LossChanceBadge.tsx).
              const band =
                rounded < 25 ? { tone: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-700 dark:bg-emerald-400', label: 'Low' } :
                rounded < 40 ? { tone: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500 dark:bg-emerald-400', label: 'Moderate-low' } :
                rounded < 60 ? { tone: 'text-slate-700 dark:text-slate-300', dot: 'bg-slate-500 dark:bg-slate-400', label: 'Neutral' } :
                rounded < 80 ? { tone: 'text-red-700 dark:text-red-300',     dot: 'bg-rose-500 dark:bg-rose-400',   label: 'Moderate-high' } :
                           { tone: 'text-red-700 dark:text-red-300',     dot: 'bg-rose-500 dark:bg-rose-400',   label: 'High' };
              return (
                <>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Loss Chance
                    </span>
                    <span className={`font-mono text-[0.8125rem] font-semibold tabular-nums ${band.tone}`}>
                      {rounded}%
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1 text-[0.6875rem] text-slate-500 dark:text-slate-400">
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${band.dot}`} aria-hidden="true" />
                    {band.label}
                  </span>
                </>
              );
            })()
          ) : (
            <>
              <div className="flex items-baseline gap-1.5">
                <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Loss Chance
                </span>
                <span className="font-mono text-[0.8125rem] font-semibold tabular-nums text-slate-300 dark:text-slate-600">—</span>
              </div>
              <span className="text-[0.6875rem] text-slate-500 dark:text-slate-400">Unavailable</span>
            </>
          )}
        </div>
      </div>
      {mos.tooltip && <span className="sr-only">{mos.tooltip}</span>}
    </>
  );
}
