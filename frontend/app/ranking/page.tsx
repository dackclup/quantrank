import type { Metadata } from 'next';

import { CountryTabs } from '@/components/CountryTabs';
import { IndexTabs } from '@/components/IndexTabs';
import RankingTable from '@/components/RankingTable';
import { getMetadata, getRankings } from '@/lib/data';

export const metadata: Metadata = {
  title: 'Ranking · QuantRank',
  description:
    'The full S&P 500 ranking — 502 names scored by an 8-pillar composite, searchable and sortable.',
};

export default function RankingPage() {
  const rankings = getRankings();
  const meta = getMetadata();

  return (
    <section className="space-y-6">
      {/* Two-tier market selector: country row (underline tabs) + index row
          (secondary pills). Grouped tightly so they read as one control unit.
          US is live (the S&P 500); every other country / index is a placeholder
          for the multi-country expansion. */}
      <div className="space-y-3">
        <CountryTabs />
        <IndexTabs />
      </div>
      <header className="max-w-3xl space-y-3">
        <h1 className="text-balance font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
          S&amp;P 500 ranking
        </h1>
        <p className="max-w-2xl text-pretty text-base text-slate-600 dark:text-slate-300">
          All{' '}
          <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
            {meta.universe_size}
          </span>{' '}
          companies, ranked by an 8-pillar composite score.
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono">{meta.universe}</span>
          {' · updated '}
          <span className="font-mono">{meta.last_update_utc}</span>
          {' · schema '}
          <span className="font-mono">{meta.version}</span>
        </p>
        <p className="max-w-2xl text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          Composite is the 8-pillar weighted score (quality, value, growth,
          momentum, health, profitability, technical, risk).{' '}
          <span className="font-mono">sentiment</span> and{' '}
          <span className="font-mono">ml</span> pillars are reserved for a
          later phase; their 0.20 weight is redistributed pro-rata across the
          active pillars. Risk-overlay flags annotate; flagged tickers cannot
          earn the entered-top-5 badge even at rank #1 by composite.
        </p>
      </header>

      {meta.universe_size === 0 || rankings.length === 0 ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">Compute pending.</p>
          <p className="mt-1">
            The first compute hasn&rsquo;t run yet. Scheduled cron: Mon-Fri
            22:00 UTC (after US market close), or trigger manually from the GitHub Actions tab.
          </p>
        </div>
      ) : (
        <RankingTable data={rankings} />
      )}
    </section>
  );
}
