import Link from 'next/link';

import { getMarketStats, type MarketStatItem, type MarketStatTone } from '@/lib/market-stats';

// MarketStatsBar — a thin, horizontally-scrolling "ticker" strip under the app
// header, modeled on the Seeking Alpha market bar but filled with QuantRank's
// OWN universe snapshot (avg composite / median MoS / flagged count / today's
// biggest mover). Server component: it reads the build-imported rankings.json
// via getMarketStats(), so there is no client fetch and no new data source.
// NOT a live feed — the numbers are "as of" the last weekly compute (the
// trailing "Updated" item shows the date). See frontend/lib/market-stats.ts
// for the derivation + the "not live" rationale.

const TONE_TEXT: Record<MarketStatTone, string> = {
  pos: 'text-emerald-600 dark:text-emerald-400',
  neg: 'text-rose-600 dark:text-rose-400',
  neutral: 'text-slate-500 dark:text-slate-400',
};

export function MarketStatsBar({ items }: { items?: MarketStatItem[] }) {
  const stats = items ?? getMarketStats();
  if (stats.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Universe snapshot"
      className="border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95"
    >
      {/* Horizontal scroll on overflow (mobile); scrollbar hidden so the strip
          stays clean. The dividers come from `divide-x` between items. */}
      <div className="flex items-stretch divide-x divide-slate-200 overflow-x-auto px-2 dark:divide-slate-800 md:px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {stats.map((item) => (
          <StatItem key={item.label} item={item} />
        ))}
      </div>
    </div>
  );
}

function StatItem({ item }: { item: MarketStatItem }) {
  const tone: MarketStatTone = item.tone ?? 'neutral';
  // When there is a delta, the value is the (neutral) ticker and the delta
  // carries the color. When there is no delta but a tone (e.g. Median MoS),
  // the value itself is tinted.
  const valueTone = !item.delta && item.tone ? TONE_TEXT[tone] : 'text-slate-900 dark:text-slate-100';

  // min-h-[44px] keeps the linked mover items at the project's touch-target
  // floor; items-center vertically centers the strip at that height.
  const layout = 'flex min-h-[44px] shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2 text-xs';
  const inner = (
    <>
      <span className="text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
        {item.label}
      </span>
      <span className={`font-mono font-semibold tabular-nums ${valueTone}`}>{item.value}</span>
      {item.delta && (
        <span className={`inline-flex items-center gap-0.5 font-mono tabular-nums ${TONE_TEXT[tone]}`}>
          <TrendCaret tone={tone} />
          {item.delta}
        </span>
      )}
    </>
  );

  if (item.href) {
    return (
      <Link
        href={item.href}
        className={`${layout} press transition-colors hover:bg-slate-50 dark:hover:bg-slate-900`}
        title={`${item.label}: ${item.value}${item.delta ? ` ${item.delta}` : ''}`}
      >
        {inner}
      </Link>
    );
  }
  return <span className={layout}>{inner}</span>;
}

// Small directional caret so direction is signalled by shape too (not color
// alone — design-system Rule 10). Neutral renders nothing; the signed value
// already encodes a flat/zero move.
function TrendCaret({ tone }: { tone: MarketStatTone }) {
  if (tone === 'neutral') return null;
  return (
    <svg width="8" height="8" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true" className="shrink-0">
      {tone === 'pos' ? <path d="M6 2 11 10 1 10 Z" /> : <path d="M6 10 1 2 11 2 Z" />}
    </svg>
  );
}
